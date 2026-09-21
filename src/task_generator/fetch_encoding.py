"""Fetch the o200k_base encoding file into the package, using tiktoken itself.

The reference tokenizer reads one local file, `data/o200k_base.tiktoken`, and never
reaches the network (see `tokenizer.py`).  That file is **not** in this repository and
is not shipped in the distribution: the terms under which the encoding file may be
redistributed could not be established, so it is fetched once, here, instead of being
copied in.  What it is and where it comes from is set out in NOTICE.

Run it after installing the package::

    python -m task_generator.fetch_encoding

Nothing is hard-coded but the encoding's name.  The URL and the expected sha256 are
read out of the installed tiktoken, so the file this writes is the file that version of
tiktoken would have fetched for itself, and a tiktoken upgrade that moved either one
would be followed here rather than silently disagreed with.

The download goes through `tiktoken.load.read_file`, which fetches and returns the
bytes and writes nothing: `read_file_cached` is the one that leaves a copy under
`$TIKTOKEN_CACHE_DIR`, and the tokenizer's offline guarantee (T2) is that no such copy
appears.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

import tiktoken.load

__all__ = ["ENCODING_NAME", "ENCODING_PATH", "encoding_source", "fetch", "main"]

ENCODING_NAME = "o200k_base"
ENCODING_PATH = pathlib.Path(__file__).resolve().parent / "data" / f"{ENCODING_NAME}.tiktoken"


def encoding_source() -> tuple[str, str]:
    """The URL and expected sha256 the installed tiktoken holds for `ENCODING_NAME`.

    tiktoken states both inside the encoding's constructor, as the two arguments it
    passes to `load_tiktoken_bpe`, and exposes them nowhere else.  So the constructor is
    called with that loader stood aside: it records the pair and returns an empty rank
    table, and the constructor's own return value is discarded.  Calling it is what
    keeps this honest -- a constructor that changed its URL, its hash or its loader
    would be followed or would fail here, rather than leaving a stale copy behind.
    """
    import tiktoken_ext.openai_public as public

    recorded: dict[str, str] = {}

    def record(blobpath: str, expected_hash: str | None = None) -> dict[bytes, int]:
        recorded["blobpath"] = blobpath
        recorded["expected_hash"] = expected_hash or ""
        return {}

    constructor = getattr(public, ENCODING_NAME)
    original = public.load_tiktoken_bpe
    public.load_tiktoken_bpe = record
    try:
        constructor()
    finally:
        public.load_tiktoken_bpe = original

    if not recorded.get("blobpath") or not recorded.get("expected_hash"):
        raise RuntimeError(
            f"tiktoken {_tiktoken_version()} does not build {ENCODING_NAME} from a hashed "
            f"file; this module cannot fetch it. Recorded: {recorded!r}"
        )
    return recorded["blobpath"], recorded["expected_hash"]


def _tiktoken_version() -> str:
    import importlib.metadata

    try:
        return importlib.metadata.version("tiktoken")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - not installed
        return "(unknown version)"


def fetch(*, force: bool = False) -> pathlib.Path:
    """Put the encoding file in place and return its path.

    Idempotent: a file already there and already matching the expected hash is left
    alone and nothing is fetched, unless `force`.  The write is atomic, so an
    interrupted fetch leaves no half file for the tokenizer to read.
    """
    blobpath, expected = encoding_source()

    if not force and ENCODING_PATH.exists():
        if hashlib.sha256(ENCODING_PATH.read_bytes()).hexdigest() == expected:
            return ENCODING_PATH

    blob: bytes = tiktoken.load.read_file(blobpath)
    digest = hashlib.sha256(blob).hexdigest()
    if digest != expected:
        raise RuntimeError(
            f"{blobpath} is not the file tiktoken {_tiktoken_version()} expects: "
            f"sha256 {digest}, expected {expected}"
        )

    ENCODING_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ENCODING_PATH.with_suffix(ENCODING_PATH.suffix + ".part")
    tmp.write_bytes(blob)
    tmp.replace(ENCODING_PATH)
    return ENCODING_PATH


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    force = "--force" in args
    unknown = [a for a in args if a != "--force"]
    if unknown:
        print(f"usage: python -m {__spec__.name} [--force]", file=sys.stderr)
        return 2

    blobpath, expected = encoding_source()
    existed = ENCODING_PATH.exists()
    path = fetch(force=force)
    verb = "already present" if existed and not force else f"fetched from {blobpath}"
    print(f"{ENCODING_NAME}: {verb}\n  path   {path}\n  sha256 {expected}")
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point
    raise SystemExit(main())
