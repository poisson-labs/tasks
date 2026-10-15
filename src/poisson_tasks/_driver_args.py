"""The Colab driver's command line, and the answers that need nothing heavy.

`python -m poisson_tasks.calibration_run` loads the calibration code, and that loads the
tokenizer file, which a fresh install does not have until it is fetched.  `--help`, a mistaken
command line and a bundle that is not one are answered before any of that: when the driver is run
as a program it calls `early()` first, and `early()` exits when it has answered.  So this module
imports the standard library only, and holds what those answers need: the parser, the names it
offers, and the check of a bundle's path.

**What each step reads.**  The notebook adds one set of options (`--local`, `--durable`,
`--mirror-interval`, `--design`) to nearly every step, and its cells are frozen, so a step accepts
the options it does not read.  `READS` says which it reads; the others are accepted, are not
required, and are not shown in the step's help.  `tests/test_fd6_scripts.py` holds the table.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import zipfile
from collections.abc import Sequence
from typing import Any

__all__ = [
    "DESIGNS",
    "KNOB_PROBE",
    "MANIFEST",
    "PORT",
    "READS",
    "bundle_refusal",
    "build_parser",
    "early",
]

PORT = 8000
"""The port the pinned server listens on unless told otherwise."""
KNOB_PROBE = "knob-probe"
DESIGNS: tuple[str, ...] = ("card", KNOB_PROBE)
"""What a run of the driver measures: the calibration card, or the knob probe.  `--design` chooses,
on every step that takes the run's folders."""
MANIFEST = "MANIFEST.sha256"
"""The file in a bundle that names every other file and its sha256."""

_UNREAD = pathlib.Path("/nonexistent/an-option-this-step-does-not-read")
"""What a step that does not read a folder is given for it: a path nothing can be written under."""

# Each shared option, with the help a step that reads it shows.
_SHARED: dict[str, tuple[dict[str, Any], str]] = {
    "--local": ({"type": pathlib.Path},
                "the runtime's local working folder, lost when the runtime drops"),
    "--durable": ({"type": pathlib.Path},
                  "the folder that survives the runtime (Google Drive on Colab)"),
    "--port": ({"type": int, "default": PORT},
               f"the port the model server listens on (default: {PORT})"),
    "--mirror-interval": ({"type": float, "default": 30.0},
                          "seconds between copies of the local folder to the durable one "
                          "(default: 30)"),
    "--design": ({"choices": DESIGNS, "default": "card"},
                 "what the run measures: card, the calibration card, or knob-probe, the knob "
                 "probe (default: card)"),
}

READS: dict[str, tuple[str, ...]] = {
    "serve": ("--local", "--port"),
    "stop-server": ("--local",),
    "preflight": ("--local", "--durable", "--port", "--design"),
    "phase1": ("--local", "--durable", "--port", "--mirror-interval", "--design"),
    "probe": ("--local", "--durable", "--port", "--mirror-interval", "--design"),
    "phase3": ("--local", "--durable", "--port", "--mirror-interval", "--design"),
    "status": ("--durable",),
    "rerun-void": ("--local", "--durable", "--mirror-interval", "--design"),
    "bundle": ("--durable", "--design"),
}
"""The shared options each step reads.  The steps that take the run's folders are these; a step
reads a folder or does not, and the others it accepts and ignores."""

_STEPS = (
    ("stop-server", "stop the server this runtime started, by the process id it recorded"),
    ("preflight", "check the GPU, the serving stack, that thinking is off and the generator, "
                  "and record them"),
    ("phase1", "the plumbing pass, with its gate"),
    ("probe", "the hardest levels; stop if the model floors"),
    ("status", "what the durable folder holds"),
)

_BUNDLE = "a bundle is the .zip `bundle` writes, or the folder it unzips to"


def bundle_refusal(bundle: pathlib.Path) -> str | None:
    """Why `bundle` is not one, in one sentence, or `None`: it does not exist, a file that is not
    a .zip archive, or a folder with no manifest.  A .zip's own manifest is checked once it is
    unpacked."""
    root = pathlib.Path(bundle)
    if not root.exists():
        return f"{bundle}: no such bundle ({_BUNDLE})"
    if root.is_file() and not zipfile.is_zipfile(root):
        return f"{bundle} is not a bundle: it is not a .zip archive ({_BUNDLE})"
    if root.is_dir() and not (root / MANIFEST).is_file():
        return f"{bundle} is not a bundle: it holds no {MANIFEST} ({_BUNDLE})"
    return None


def unread(path: pathlib.Path | None) -> pathlib.Path:
    """The folder a step was given, or the path a step that does not read it is given."""
    return _UNREAD if path is None else path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m poisson_tasks.calibration_run",
        description=(
            "The driver the Colab notebook calls, one step to a notebook cell. It serves one "
            "pinned model with vLLM on the notebook's GPU and runs a calibration card, or the "
            "knob probe, against it. Every step saves to a durable folder, so a runtime that "
            "drops resumes where it stopped. It is for rebuilding the published cards; it is "
            "not the user's command, and `poisson-tasks` is."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="STEP")

    def step(name: str, text: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=text, description=text[0].upper() + text[1:] + ".")

    def shared(p: argparse.ArgumentParser, name: str) -> None:
        """All the shared options on the step: the ones it reads, with help (and the folders it
        reads required), and the others accepted without it."""
        for option, (kwargs, text) in _SHARED.items():
            reads = option in READS[name]
            folder = option in ("--local", "--durable")
            p.add_argument(option, **kwargs, required=reads and folder,
                           help=text if reads else argparse.SUPPRESS)

    p = step("install-vllm", "install the pinned vLLM into a virtual environment of its own")
    p.add_argument("--venv", type=pathlib.Path, required=True,
                   help="the folder to make the virtual environment in")
    p.add_argument("--dry-run", action="store_true",
                   help="say what would be installed, and install nothing")

    p = step("serve", "start the pinned server and wait until it is healthy")
    shared(p, "serve")
    p.add_argument("--vllm", default="vllm",
                   help="the vllm executable (default: vllm, found on the path)")
    p.add_argument("--tokenizer-config", type=pathlib.Path, default=None,
                   help="a tokenizer_config.json to read the chat template from (default: "
                        "downloaded from the pinned revision)")
    p.add_argument("--timeout", type=float, default=1800.0,
                   help="seconds to wait for the server to be healthy (default: 1800)")

    for name, text in _STEPS:
        shared(step(name, text), name)

    p = step("phase3", "the main run: every arm of the design, resumable")
    shared(p, "phase3")
    p.add_argument("--wall-clock-hours", type=float, required=True,
                   help="the compute allowance, in hours, across every resume; the run "
                        "stops cleanly at whichever of this, the token budget or the "
                        "provider's credit comes first")

    p = step("rerun-void", "the knob probe's step: set an arm that was void by its instrument "
                           "rate aside for its one re-run")
    shared(p, "rerun-void")
    p.add_argument("--arm", required=True,
                   help="the arm to set aside, as it is written in the probe's outcome, "
                        "such as history:t2400")
    p.add_argument("--cause", required=True,
                   help="what failed: the server, the key or the provider")

    p = step("finalize", "rebuild the card from a durable folder, with no GPU")
    p.add_argument("--durable", type=pathlib.Path, required=True,
                   help="the durable folder the run kept")
    p.add_argument("--out", type=pathlib.Path, required=True,
                   help="the folder to write the card into")
    p.add_argument("--port", type=int, default=PORT,
                   help=f"the port the server was on, which the card records (default: {PORT})")

    p = step("bundle", "zip the card, the reports and vLLM's log with a sha256 manifest, "
                       "for downloading and `verify`")
    shared(p, "bundle")

    p = step("verify", "check a bundle's manifest and recompute its card from its records")
    p.add_argument("bundle", type=pathlib.Path,
                   help="the bundle: the .zip `bundle` writes, or the folder it unzips to")
    p.add_argument("--into", type=pathlib.Path, default=None,
                   help="copy the bundle's files into this folder once they check out "
                        "(default: copy nothing)")
    return parser


def early(argv: Sequence[str] | None = None) -> None:
    """Answer what needs nothing heavy and exit; return when the command has to run.

    `--help` and a mistaken command line are argparse's own answers (exit 0 and exit 2).  A bundle
    that is not one is one `error:` line and exit 1."""
    args = build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.command == "verify":
        sentence = bundle_refusal(args.bundle)
        if sentence is not None:
            print(f"error: {sentence}", file=sys.stderr, flush=True)
            raise SystemExit(1)
