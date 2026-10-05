"""The environment report behind `doctor`, frozen as tests: `providers.environment_report`.

The invariant is FD2.7 of the front door's plan (spec §4.7, and §1.2 items 1, 7, 8 and 15):
- the report names `sys.executable` and the folder the package was imported from, and flags that
  folder when it is outside `sys.prefix`: the hands-on test's F1, a package imported from an
  editable install or from another project's environment;
- it gives the tokenizer file's status, present, missing or with the wrong digest, and its path;
  whether `HOME/.local/bin/uv` exists, where the harness's bootstrap puts uv; and whether the
  platform is supported;
- it opens no socket.

A report on another copy of the package runs in a fresh interpreter, with that copy first on
`PYTHONPATH`, so the copy's tokenizer file can be missing or altered without touching the one in
this checkout.  Every test reaches the module through `importlib`, so the file collects on a tree
with no `poisson_tasks.providers`.

Shapes decided here
-------------------

**1. `EnvironmentReport`'s fields** are `python`, `python_version`, `package`,
`package_outside_environment`, `tokenizer`, `tokenizer_path`, `uv`, `platform`,
`platform_supported`, `key_env` and `key_set`.  `tokenizer` is one of `"present"`, `"missing"`
and `"wrong digest"`.

**2. "Inside `sys.prefix`" is a path comparison, after resolving both**: a folder whose name only
starts with the prefix's name is outside it, and a prefix reached through a symbolic link (macOS's
`/tmp` is one) is the folder it links to.

**3. Supported means macOS or Linux** (spec §4.3, which refuses `run` on Windows), read from
`sys.platform` (`platform.system()` is set to agree in each case).

**4. With a config, the report names its key variable and whether that variable holds a value**,
with no network; `key_set` is `None` when the config names no key variable.  It never holds the
key: `tests/test_fd2_key.py` searches it for one.

Not pinned here, and left to the build: whether `uv` there is executable; what the report says
about a tokenizer file it cannot read; and `fetch_tokenizer`, which no invariant of the plan
covers, and whose pinning is left to a ruling.
"""

from __future__ import annotations

import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

from tests.fd2_fakes import network_guard


def providers() -> Any:
    return importlib.import_module("poisson_tasks.providers")


def config() -> Any:
    return importlib.import_module("poisson_tasks.config")


def package_dir() -> Path:
    return Path(str(importlib.import_module("poisson_tasks").__file__)).resolve().parent


def test_fd2_7_the_report_names_this_python_and_where_the_package_came_from() -> None:
    report = providers().environment_report()
    assert report.python == sys.executable
    assert report.python_version == platform.python_version()
    assert Path(report.package).resolve() == package_dir()
    assert (report.key_env, report.key_set) == (None, None)


# The prefix, and whether the package is then outside it.
PREFIXES = {
    "an-ancestor": False,
    "an-ancestor-through-a-symlink": False,
    "another-folder": True,
    "a-folder-whose-name-starts-the-same": True,
}


@pytest.mark.parametrize("prefix", list(PREFIXES))
def test_fd2_7_a_package_outside_sys_prefix_is_flagged(
    prefix: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = package_dir()
    if prefix == "an-ancestor":
        value = str(package.parent.parent)
    elif prefix == "an-ancestor-through-a-symlink":
        link = tmp_path / "env"
        link.symlink_to(package.parent.parent, target_is_directory=True)
        value = str(link)
    elif prefix == "another-folder":
        value = str(tmp_path)
    else:
        value = str(package)[:-3]  # ".../poisson_tas"
    monkeypatch.setattr(sys, "prefix", value)
    assert providers().environment_report().package_outside_environment is PREFIXES[prefix]


TOKENIZER = {"present": "present", "missing": "missing", "one-byte-changed": "wrong digest",
             "empty": "wrong digest"}


@pytest.mark.parametrize("state", list(TOKENIZER))
def test_fd2_7_a_copy_of_the_package_is_named_and_flagged_with_its_tokenizers_status(
    state: str, tmp_path: Path,
) -> None:
    """F1's case itself: another copy of the package first on the path.  The report names that
    copy, flags it, and reads that copy's tokenizer file, even when it is missing."""
    root = tmp_path / "site"
    shutil.copytree(package_dir(), root / "poisson_tasks",
                    ignore=shutil.ignore_patterns("__pycache__"))
    copy = root / "poisson_tasks"
    data = copy / "data" / "o200k_base.tiktoken"
    assert data.is_file()
    if state == "missing":
        data.unlink()
    elif state == "one-byte-changed":
        blob = bytearray(data.read_bytes())
        blob[len(blob) // 2] ^= 0x01
        data.write_bytes(bytes(blob))
    elif state == "empty":
        data.write_bytes(b"")
    code = textwrap.dedent(f"""\
        import json, poisson_tasks
        assert poisson_tasks.__file__.startswith({str(root)!r}), poisson_tasks.__file__
        from poisson_tasks import providers
        r = providers.environment_report()
        print(json.dumps([r.package, r.package_outside_environment, r.tokenizer,
                          r.tokenizer_path]))
    """)
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=300,
        env={**os.environ, "PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert done.returncode == 0, done.stderr[-3000:]
    package, outside, tokenizer, path = json.loads(done.stdout.strip().splitlines()[-1])
    assert Path(package).resolve() == copy.resolve()
    assert outside is True
    assert tokenizer == TOKENIZER[state]
    assert Path(path).resolve() == data.resolve()


@pytest.mark.parametrize("where", ["home-local-bin", "nowhere", "elsewhere-on-the-path"])
def test_fd2_7_uv_is_looked_for_in_home_local_bin(
    where: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Where the harness's bootstrap installs uv and puts first on `PATH` (spec §1.2 item 1); a uv
    elsewhere on `PATH` is not that one."""
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    other = tmp_path / "bin"
    other.mkdir()
    for folder in ((home / ".local" / "bin") if where == "home-local-bin" else None,
                   other if where == "elsewhere-on-the-path" else None):
        if folder is not None:
            (folder / "uv").write_text("#!/bin/sh\n", encoding="utf-8")
            (folder / "uv").chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", f"{other}{os.pathsep}{os.environ.get('PATH', '')}")
    assert providers().environment_report().uv is (where == "home-local-bin")


@pytest.mark.parametrize(("name", "system", "supported"),
                         [("darwin", "Darwin", True), ("linux", "Linux", True),
                          ("win32", "Windows", False)])
def test_fd2_7_macos_and_linux_are_supported_and_windows_is_not(
    name: str, system: str, supported: bool, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", name)
    monkeypatch.setattr(platform, "system", lambda: system)
    report = providers().environment_report()
    assert (report.platform, report.platform_supported) == (name, supported)


OPENAI_COMPATIBLE = ["--provider", "openai-compatible", "--model", "llama-3.3-70b",
                     "--base-url", "https://gateway.example.test/openai/v1",
                     "--api-key-env", "MY_API_KEY", "--no-price"]


@pytest.mark.parametrize(("argv", "value", "expected"), [
    (OPENAI_COMPATIBLE, None, ("MY_API_KEY", False)),
    (OPENAI_COMPATIBLE, "", ("MY_API_KEY", False)),
    (OPENAI_COMPATIBLE, "sk-test-value", ("MY_API_KEY", True)),
    (["--provider", "ollama"], "sk-test-value", ("", None)),
], ids=["not-set", "empty", "set", "no-key-variable"])
def test_fd2_7_with_a_config_the_report_says_whether_its_key_is_set_and_opens_no_socket(
    argv: list[str], value: str | None, expected: tuple[str, bool | None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MY_API_KEY", raising=False)
    if value is not None:
        monkeypatch.setenv("MY_API_KEY", value)
    made = config().config_from_init_args(argv)
    with network_guard(monkeypatch) as events:
        report = providers().environment_report(made)
    assert events == []
    assert (report.key_env, report.key_set) == expected
