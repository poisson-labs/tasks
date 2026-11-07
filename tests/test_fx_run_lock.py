"""#34, the lock: a run's `run.lock` is gone when the run is, and is never taken from a run that
is still going.

`run` holds `<run folder>/run.lock` (an advisory `flock`, so a process that dies loses it) for the
run's length, with its pid and start time written in the file (`tests/test_fd9_verbs.py`, G9).  It
used to leave the file behind when the run ended, whatever the way: a folder that was finished,
stopped or failed then held a `run.lock` naming a pid that was long gone, which reads as a lock
that was never cleared.  The file is now removed by the run that holds it when the run ends.

What each test holds:

- the file is gone after a run that ends, after one that raises and after one the user stops
  (`KeyboardInterrupt` reaches the `with` as an exception, as for any other);
- a run that finds the folder held is refused and leaves the holder's file where it is, still
  held, and a second refusal leaves it too;
- a run removes only the file it holds: if the file at the path is another one by the time it
  ends (it was removed and made again, and another run holds the new file), the new one stays;
- a file that no process holds, left by a process that was killed, does not stop the next run, and
  is cleared when that run ends;
- a run that opens the file while the previous holder is removing it never holds an unlinked file:
  it takes the one the path names now, so two runs are never both "holding" the folder.

The first three of the second group are controls: they pass before the change, and hold it to
never removing a live run's lock.  The end-to-end test runs the `run` verb on the fixture model.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

import pytest

from poisson_tasks.cli._result import Refusal
from poisson_tasks.cli._run import LOCK_FILE, _locked, _refuse_held
from tests.fd3_support import harness_env, needs_uv
from tests.fd5_support import World, invoke, world
from tests.fd9_support import PROG, States, hold_lock, kept_hashes, lock_is_held, run_folder, states

__all__ = ["harness_env", "states", "world"]


def _held(path: Path) -> bool:
    """Whether some process holds `path` now, found by trying to take it."""
    if not path.exists():
        return False
    with open(path, "a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
    return False


def test_fx34_1_the_lock_file_is_gone_when_a_run_ends(tmp_path: Path) -> None:
    """Red before the change: the file stays, naming a pid that has gone."""
    with _locked(tmp_path):
        assert (tmp_path / LOCK_FILE).is_file()
        assert _held(tmp_path / LOCK_FILE)
    assert not (tmp_path / LOCK_FILE).exists(), "the run ended and left its lock file"


def test_fx34_2_the_lock_file_is_gone_when_the_run_raises(tmp_path: Path) -> None:
    """Red before the change.  Any exception ends the `with`, an unexpected failure among them."""
    with pytest.raises(RuntimeError):
        with _locked(tmp_path):
            raise RuntimeError("the run failed")
    assert not (tmp_path / LOCK_FILE).exists()


def test_fx34_3_the_lock_file_is_gone_when_the_user_stops_the_run(tmp_path: Path) -> None:
    """Red before the change.  Ctrl-C arrives in the run as `KeyboardInterrupt`."""
    with pytest.raises(KeyboardInterrupt):
        with _locked(tmp_path):
            raise KeyboardInterrupt
    assert not (tmp_path / LOCK_FILE).exists()


def test_fx34_4_a_run_that_finds_the_folder_held_is_refused_and_leaves_the_holders_file(
    tmp_path: Path,
) -> None:
    """A control: green before the change, and the change must keep it green.  The holder is
    another process; the second `_locked` is refused, and so is a second refusal, and the file,
    its bytes and its hold are the holder's still."""
    with hold_lock(tmp_path):
        path = tmp_path / LOCK_FILE
        before = path.read_bytes()
        for _ in range(2):
            with pytest.raises(Refusal):
                with _locked(tmp_path):
                    pytest.fail("a run entered a folder another process holds")
            with pytest.raises(Refusal):
                _refuse_held(tmp_path)
            assert path.is_file(), "a run that was refused removed the live run's lock file"
            assert path.read_bytes() == before
            assert lock_is_held(tmp_path)


def test_fx34_5_a_run_in_this_process_holds_the_file_until_it_ends(tmp_path: Path) -> None:
    """A control: green before the change.  While the `with` is open the file is held, and a
    second run in the same process, which flocks through its own open file, is refused."""
    with _locked(tmp_path):
        with pytest.raises(Refusal):
            with _locked(tmp_path):
                pytest.fail("two runs held one folder")
        assert (tmp_path / LOCK_FILE).is_file()
        assert _held(tmp_path / LOCK_FILE)
    assert not _held(tmp_path / LOCK_FILE)


def test_fx34_6_a_run_removes_only_the_file_it_holds(tmp_path: Path) -> None:
    """A control: green before the change, and a plain `unlink` at the end of the run breaks it.
    While run A is going its file is removed by hand and made again, and another process (run C)
    holds the new file.  When A ends it must leave C's file, and C's hold, alone."""
    path = tmp_path / LOCK_FILE
    run_a = _locked(tmp_path)
    run_a.__enter__()
    path.unlink()
    with hold_lock(tmp_path):
        run_a.__exit__(None, None, None)
        assert path.is_file(), "run A removed the file run C holds"
        assert lock_is_held(tmp_path), "run C's hold is gone"


def test_fx34_7_a_file_no_process_holds_does_not_stop_a_run_and_is_cleared_after_it(
    tmp_path: Path,
) -> None:
    """A file left by a process that was killed (it names a pid and holds nothing) is taken by the
    next run, and is cleared when that run ends.  The first half is green before the change."""
    path = tmp_path / LOCK_FILE
    path.write_text(json.dumps({"pid": 2**22 + 12345, "since": "03:14Z"}) + "\n", encoding="utf-8")
    with _locked(tmp_path):
        held = json.loads(path.read_text(encoding="utf-8"))
        assert held["pid"] == os.getpid()
    assert not path.exists()


def test_fx34_8_a_run_never_holds_a_file_the_path_no_longer_names(tmp_path: Path) -> None:
    """The race the removal opens: run B opens the file, run A (which held it) removes it and
    ends, and B's `flock` then succeeds on a file that has no name.  A third run, C, would then
    make a new file and hold that too, and the folder would have two holders.  B must notice the
    path names no such file, and take the one it does.  The test plays A's removal between B's
    open and B's flock by removing the file as B first asks for its lock.  Red before the change,
    too: the run then goes on holding the nameless file."""
    path = tmp_path / LOCK_FILE
    real_flock = fcntl.flock
    calls: list[str] = []

    def removing_first(handle: object, how: int) -> None:
        if not calls and how & fcntl.LOCK_EX:
            calls.append("removed")
            path.unlink()
        real_flock(handle, how)  # type: ignore[arg-type]

    path.write_text("", encoding="utf-8")
    fcntl.flock = removing_first  # type: ignore[assignment]
    try:
        with _locked(tmp_path):
            assert path.is_file(), "the run holds a file the folder cannot name"
            assert _held(path), "the file the folder names is not the one the run holds"
    finally:
        fcntl.flock = real_flock  # type: ignore[assignment]
    assert calls == ["removed"]
    assert not path.exists()


@needs_uv
def test_fx34_9_a_run_that_finishes_leaves_no_lock_file_in_its_folder(
    harness_env: Path, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The verb end to end, against the fixture model: `run` on a stopped folder finishes it, and
    the folder holds no `run.lock` after.  The fixture state's folders hold one that no process
    holds (as a run that ended once left it), so the file is there before and gone after.  Red
    before the change: it is there after."""
    work = states.copy("C1", world.work)
    folder = run_folder(work)
    assert (folder / LOCK_FILE).is_file() and not lock_is_held(folder)
    ran = invoke(["run", "--yes"], prog=PROG, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert len(kept_hashes(folder)) == 2
    assert not (folder / LOCK_FILE).exists(), "the finished run left its lock file"
