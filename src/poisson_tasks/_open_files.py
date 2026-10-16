"""Room for the files a run holds open, made at the run's start (ruled 2026-10-15).

A run holds files open in proportion to the episodes it has in flight: each episode's harness
program and tool server are processes of their own, read through pipes, and its model calls and
tool calls are loopback connections.  macOS starts a shell with a soft limit of 256 open files
per process, so a run at the knob probe's concurrency of 128 failed at its start with `OSError`
24, too many open files.

So every way a run starts goes through `room`: it raises this process's soft limit as far as the
hard limit allows, for the run's length only, and puts it back after.  When even that is less than
the run needs, `check` refuses before anything starts, in one line naming the number needed and
how to raise the limit.  `needed` is that number, from the measurements filed with this fix.

On macOS the hard limit is usually unlimited, and a process can still open no more than the
system's limit per process (`kern.maxfilesperproc`): that is as far as the soft limit goes there.
Linux goes through the same code, where the hard limit is the whole story.  Where the `resource`
module is not there (Windows), nothing is checked or changed and the run goes ahead as before.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterator
from typing import NamedTuple

__all__ = ["OpenFilesRefused", "check", "needed", "room"]

_BASE = 64
"""Files a run holds open with nothing in flight, with room to spare: the interpreter's, the run's
log and ledger, the interception server's socket and the event loop's."""
_PER_EPISODE = 5
"""Files one episode in flight may hold open, with room to spare over what was measured."""
_OPEN_MAX = 10240
"""macOS's `OPEN_MAX`: as far as the soft limit goes when the hard limit is unlimited and the
system's limit per process cannot be read."""


class OpenFilesRefused(OSError):
    """A run that needs more open files than this process can have: one line, with the number
    needed and how to raise the limit.  Nothing was started."""


class _Limits(NamedTuple):
    soft: int
    hard: int
    top: int
    """As far as the soft limit can go."""
    system: bool
    """Whether `top` is the system's limit per process rather than the hard limit."""


def needed(concurrency: int) -> int:
    """The open files a run with `concurrency` episodes in flight may need at once."""
    return _BASE + _PER_EPISODE * max(1, int(concurrency))


def _per_process_cap() -> int | None:
    """The system's limit on open files per process apart from the hard limit
    (`kern.maxfilesperproc` on macOS), or `None` where there is none or it cannot be read."""
    if sys.platform != "darwin":
        return None
    try:
        import ctypes
        import ctypes.util

        libc = ctypes.CDLL(ctypes.util.find_library("c"))
        value = ctypes.c_int(0)
        size = ctypes.c_size_t(ctypes.sizeof(value))
        status = libc.sysctlbyname(b"kern.maxfilesperproc", ctypes.byref(value),
                                   ctypes.byref(size), None, ctypes.c_size_t(0))
    except (OSError, AttributeError):
        return None
    return value.value if status == 0 and value.value > 0 else None


def _limits() -> _Limits | None:
    """This process's limits on open files, or `None` where there is no `resource` module."""
    try:
        import resource
    except ImportError:
        return None
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    cap = _per_process_cap()
    if hard == resource.RLIM_INFINITY:
        return _Limits(soft, hard, _OPEN_MAX if cap is None else cap, True)
    if cap is not None and cap < hard:
        return _Limits(soft, hard, cap, True)
    return _Limits(soft, hard, hard, False)


def check(concurrency: int) -> None:
    """Refuse a run with `concurrency` episodes in flight when this process cannot be given the
    open files it needs (`OpenFilesRefused`); change nothing."""
    limits = _limits()
    if limits is None:
        return
    need = needed(concurrency)
    if limits.top >= need:
        return
    if limits.system:
        how = (f"this system allows {limits.top:,} per process; raise that to at least {need:,} "
               f"(sudo sysctl -w kern.maxfilesperproc={need})")
    else:
        how = (f"the hard limit is {limits.top:,}; raise it to at least {need:,} "
               f"(ulimit -Hn {need}, which takes root)")
    raise OpenFilesRefused(
        f"a run of {concurrency:,} episodes at once needs up to {need:,} open files and {how}; "
        "nothing was started"
    )


@contextlib.contextmanager
def room(concurrency: int) -> Iterator[None]:
    """`check`, then the block with this process's soft limit on open files raised as far as it
    goes; the soft limit is put back after the block."""
    check(concurrency)
    limits = _limits()
    if limits is None or limits.soft >= limits.top:
        yield
        return
    import resource

    resource.setrlimit(resource.RLIMIT_NOFILE, (limits.top, limits.hard))
    try:
        yield
    finally:
        resource.setrlimit(resource.RLIMIT_NOFILE, (limits.soft, limits.hard))
