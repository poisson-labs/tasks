"""The wheel gate (step 6 of docs/releasing.md): a built wheel's guided session in a real pseudo-terminal, every word
of the session once on setup's defaults (10 tasks a level, 1 attempt), against the fixture model, in both looks.
Offline: proxies point at a closed port, uv runs with UV_OFFLINE=1, and the only servers are the fixture models on
127.0.0.1.

usage: python -I scripts/release/drive.py <checkout with tests/> <gate folder holding venv/> <transcripts folder> [scene ...]
(scenes: built-in-pretty, own-tools-pretty, built-in-plain, own-tools-plain; all when none named)

Run it with the interpreter of a driver venv that holds the same wheel with pytest and hypothesis: it imports the
checkout's test helpers.  The gate folder's venv/ holds the wheel with its dependencies from pypi.org.  Both venvs need
the tokenizer file in their poisson_tasks/data/.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

REPO, GATE, OUT = (Path(arg).resolve() for arg in sys.argv[1:4])
ONLY = set(sys.argv[4:])
sys.path.insert(0, str(REPO))
WHEEL_PY = GATE / "venv" / "bin" / "python"

from tests import fd9_support as f9  # noqa: E402
from tests.fd3_support import KEY, stub_bin  # noqa: E402
from tests.fd5_support import uv_cache  # noqa: E402
from tests.fixtures.model_server import FixtureModel  # noqa: E402
from tests.o2_support import reference_model  # noqa: E402


class _Sys:
    """`sys` for `fd9_support.Pty`, whose child is `sys.executable -m poisson_tasks`: the wheel's
    interpreter, not this one."""

    executable = str(WHEEL_PY)

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        return getattr(sys, name)


f9.sys = _Sys()  # type: ignore[assignment]
_pump = f9.Pty._pump


def _live_pump(self, wait):  # type: ignore[no-untyped-def]
    got = _pump(self, wait)
    live = getattr(self, "live", None)
    if got and live is not None and time.monotonic() - getattr(self, "_dumped", 0) > 2:
        self._dumped = time.monotonic()
        live.write_text(self.plain, encoding="utf-8")
    return got


f9.Pty._pump = _live_pump

PROMPTS = (re.compile(r"(›\s*(a step's number, a word, help or quit|a number or a word)?|"
                      r"type a number or a word, then Enter \(help, quit\):)\s*$"))
DOWN, UP, ENTER = "\x1b[B", "\x1b[A", "\r"
MENU = re.compile(r"(Which episode\?|card\.md, \d+ sections|Which run\?|Which tool's output\?|"
                  r"Which field of its output\?|Into which tool\?|Which of its inputs\?)")
results: list[dict] = []


def env_for(home: Path, base_url: str) -> dict[str, str]:
    stubs = stub_bin(home.parent / "stub-bin")
    closed = "http://127.0.0.1:9"
    env = {
        "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}", "HOME": str(home),
        "TMPDIR": str(home.parent / "tmp"), "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8",
        "TERM": "xterm-256color", "COLORTERM": "truecolor", "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1", "UV_OFFLINE": "1", "OPENAI_BASE_URL": base_url,
        "OPENAI_API_KEY": KEY, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
    }
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy",
                 "all_proxy"):
        env[name] = closed
    cache = uv_cache()
    if cache:
        env["UV_CACHE_DIR"] = cache
    (home.parent / "tmp").mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    return env


class Driver:
    def __init__(self, scene: str, pty: f9.Pty, look: str) -> None:
        self.scene, self.pty, self.look = scene, pty, look
        self.log: list[str] = []

    def tail(self, since: int, chars: int = 1500) -> str:
        """The screen's text from `since`, its last `chars`, without control characters (the
        prompt leaves a backspace behind)."""
        return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", self.pty.plain[since:][-chars:])

    def at_prompt(self, since: int) -> bool:
        lines = [line for line in self.tail(since).splitlines() if line.strip()]
        return bool(lines) and bool(PROMPTS.search(lines[-1]))

    def pick_last(self, since: int) -> None:
        """The last option of the menu on screen: Up (questionary wraps) in the pretty look, the
        highest number in the plain one."""
        if self.look == "pretty":
            self.pty.send(UP, settle=0.5)
            self.pty.send(ENTER, settle=1.0)
            return
        numbers = [int(n) for n in re.findall(r"^\s+(\d+)\) ", self.tail(since, 6000),
                                             re.MULTILINE)]
        self.pty.type(str(max(numbers)))

    def note(self, what: str) -> None:
        print(f"{time.strftime('%H:%M:%S')} {self.scene}: {what}", flush=True)

    def word(self, word: str, *, start: str = "n", until: float = 900) -> None:
        """Type `word`, answer whatever it asks (menus: the last option; `Start?`: `start`; any
        other question: Enter), until the session's prompt is back."""
        since = len(self.pty.plain)
        self.log.append(word)
        self.note(f"word {word}")
        self.pty.type(word, settle=1.5)
        deadline = time.monotonic() + until
        handled = 0
        while time.monotonic() < deadline:
            self.pty.quiet(1.5, timeout=until)
            if self.pty.process.poll() is not None:
                return
            text = self.pty.plain[since:]
            menus = MENU.findall(text)
            if len(menus) > handled and not self.at_prompt(since):
                handled = len(menus)
                self.note(f"menu {menus[-1]}: the last option")
                self.pick_last(since)
                continue
            last = [line for line in self.tail(since).splitlines() if line.strip()][-1:]
            last_line = last[0] if last else ""
            if re.search(r"Start\? \[y/N\]\s*$", last_line):
                self.pty.type(start, settle=2.0)
                continue
            if self.at_prompt(since):
                return
            self.pty.live.write_text(self.pty.plain, encoding="utf-8")
            self.note(f"waiting; last line {last_line[-120:]!r}")
            if re.search(r"(\[Y/n\]|\[y/N\]|›\s*(\[.*\])?|\]\s*)$", last_line.rstrip()) or \
                    re.search(r"\?\s*(\(.*\))?\s*$", last_line) or \
                    re.match(r"^\s*(Description:|❯|\d+\) )", last_line):
                self.pty.send(ENTER, settle=1.5)
                continue
            time.sleep(1.0)
        raise AssertionError(f"{self.scene}: {word!r} never came back to the prompt\n"
                             f"{self.tail(since, 4000)}")

    def setup_answers(self, since: int, *, own: bool, until: str) -> None:
        """Every question of setup answered with its default, but the first (own tools: the
        second option) and the tool file (`petstore.json`), until `until` shows."""
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            self.pty.quiet(1.5)
            text = self.pty.plain[since:]
            if re.search(until, text):
                return
            last = [line for line in self.tail(since).splitlines() if line.strip()][-1:]
            last_line = last[0] if last else ""
            if own and "What do you want to test?" in text and not getattr(self, "_kind", False):
                self._kind = True
                if self.look == "pretty":
                    self.pty.send(DOWN, settle=0.5)
                    self.pty.send(ENTER, settle=1.5)
                else:
                    self.pty.type("2", settle=1.5)
                continue
            if own and "Your tool file" in last_line + self.tail(since, 300) and \
                    not getattr(self, "_file", False):
                self._file = True
                self.pty.type("petstore.json", settle=1.5)
                continue
            if not (re.search(r"(\[Y/n\]|\[y/N\]|\]\s*|\?\s*(\(.*\))?\s*)$", last_line.rstrip() + " ")
                    or re.match(r"^\s*(Description:|❯|\d+\) )", last_line)):
                time.sleep(1.0)  # no question on screen: a verb is still working
                continue
            self.note(f"setup: Enter at {last_line[-60:]!r}")
            self.pty.send(ENTER, settle=1.5)
        raise AssertionError(f"{self.scene}: setup never reached {until!r}\n{self.tail(since)}")


def scene(name: str, look: str, folder: Path, env: dict[str, str], body) -> dict:  # type: ignore[no-untyped-def]
    argv = ["--plain"] if look == "plain" else []
    started = time.monotonic()
    with f9.pty_session(argv, env=env, cwd=folder, columns=100) as pty:
        pty.live = OUT / f"{name}.live.txt"
        driver = Driver(name, pty, look)
        error = None
        try:
            body(driver)
            code = pty.wait(120)
        except AssertionError as failed:
            error = str(failed)[:4000]
            code = None
        (OUT / f"{name}.ans").write_bytes(pty.raw)
        (OUT / f"{name}.txt").write_text(pty.plain, encoding="utf-8")
        text = pty.plain
    found = {
        "scene": name, "look": look, "exit": code, "error": error,
        "seconds": round(time.monotonic() - started), "words": driver.log,
        "unexpected_failure": "unexpected failure" in text,
        "not_checked_yet": "not checked yet" in text,
        "run_each_with": "run each with" in text,
        "None_dot": bool(re.search(r"\bNone\.", text)),
        "bytes": len(pty.raw),
    }
    results.append(found)
    print(json.dumps(found), flush=True)
    return found


def built_in(look: str, model: FixtureModel) -> None:
    root = OUT.parent / "folders" / f"built-in-{look}"
    shutil.rmtree(root, ignore_errors=True)
    folder = root / "work"
    folder.mkdir(parents=True)
    env = env_for(root / "home", model.base_url)

    def body(d: Driver) -> None:
        d.pty.expect(r"Enter to start, or quit")
        d.pty.quiet(1.0)
        since = len(d.pty.plain)
        d.pty.type("y", settle=1.5)  # y starts step 1
        d.setup_answers(since, own=False, until=r"Enter for step 3")
        d.pty.quiet(1.0)
        d.pty.send(ENTER, settle=2.0)
        d.pty.expect(r"Start\? \[y/N\]", since=since)
        d.pty.quiet(1.0)
        d.pty.type("y", settle=2.0)
        d.pty.expect(r"Step 5 of 5", since=since, timeout=900)
        d.pty.expect(r"^next\s*$", since=d.pty.plain.rindex("Step 5 of 5"), timeout=120)
        d.pty.quiet(2.0)
        for word in ("card", "more", "replies", "task", "verify", "runs", "settings", "export",
                     "check", "home", "help"):
            d.word(word)
        d.word("again", start="y")
        for word in ("setup", "run", "flow"):
            d.word(word)
        d.pty.type("quit", settle=1.0)

    scene(f"built-in-{look}", look, folder, env, body)


def own_tools(look: str) -> None:
    root = OUT.parent / "folders" / f"own-{look}"
    shutil.rmtree(root, ignore_errors=True)
    folder = root / "work"
    folder.mkdir(parents=True)
    shutil.copy(REPO / "tests" / "fixtures" / "o1" / "petstore-openapi-3.0.json",
                folder / "petstore.json")
    with reference_model() as reference:
        env = env_for(root / "home", reference.base_url)

        def body(d: Driver) -> None:
            from poisson_tasks import config, runs

            d.pty.expect(r"Enter to start, or quit")
            d.pty.quiet(1.0)
            since = len(d.pty.plain)
            d.pty.send(ENTER, settle=1.5)
            d.setup_answers(since, own=True, until=r"Enter for step 3")
            plan = config.resolve_plan(config.load_config(folder / "tasks.toml"), root=folder)
            for spec in plan.arms:
                for bundle in runs.own_bundles(plan, spec, plan.seeds):
                    reference.register(bundle)
            d.pty.quiet(1.0)
            d.pty.send(ENTER, settle=2.0)
            d.pty.expect(r"Start\? \[y/N\]", since=since)
            d.pty.quiet(1.0)
            d.pty.type("y", settle=2.0)
            d.pty.expect(r"Step 5 of 5", since=since, timeout=900)
            d.pty.expect(r"^next\s*$", since=d.pty.plain.rindex("Step 5 of 5"), timeout=120)
            d.pty.quiet(2.0)
            for word in ("replies", "flow", "more", "runs"):
                d.word(word)
            d.pty.type("quit", settle=1.0)

        scene(f"own-tools-{look}", look, folder, env, body)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    model = FixtureModel()
    model.start()
    try:
        for look in ("pretty", "plain"):
            if not ONLY or f"built-in-{look}" in ONLY:
                built_in(look, model)
            if not ONLY or f"own-tools-{look}" in ONLY:
                own_tools(look)
        hosts = sorted({value for seen in model.requests for name, value in seen.headers.items()
                        if name.lower() == "host"})
    finally:
        model.close()
    (OUT / "scenes.json").write_text(json.dumps({"scenes": results, "fixture_hosts": hosts},
                                                indent=2) + "\n", encoding="utf-8")
    bad = [r for r in results if r["exit"] != 0 or r["error"] or r["unexpected_failure"]
           or r["not_checked_yet"] or r["run_each_with"] or r["None_dot"]]
    print("BAD" if bad else "ALL SCENES OK", flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
