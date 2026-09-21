"""The reference tokenizer: o200k_base, built offline from one local encoding file.

TG-ADR-13 makes o200k_base through tiktoken the one design-time measurement, with the
encoding file held locally and hashed.  This module is the only place that encoding is
built: N5-N7 and N9 in TG-M2 and G14 in TG-M3 import it, and nothing anywhere calls
`tiktoken.get_encoding`.

**The file is not part of this repository or of the distribution.**  The terms under
which the encoding file may be redistributed could not be established, so it is fetched
once, after installation, by `python -m task_generator.fetch_encoding`, which reads the
URL and the expected digest out of the installed tiktoken.  NOTICE records what the file
is and where it comes from; `fetch_encoding` is the only code here that touches the
network, and it is never called from this module.

Three routes into tiktoken 0.14.0 are closed here, all three for one reason -- a test
has to build this encoder with the network gone and without leaving a byte behind
(the TG-M1 build, finding 9):

* `tiktoken.get_encoding("o200k_base")` fetches the encoding over HTTPS.
* `tiktoken.load.read_file_cached` writes a copy under `$TMPDIR/data-gym-cache`, keyed
  by the sha1 of its argument.  It does that for a *local* path too, not only a URL.
* `tiktoken.load.load_tiktoken_bpe` calls `read_file_cached`, so it is closed as well.

So the local file is read here, checked against the sha256 tiktoken 0.14.0 pins for it,
parsed, and handed to `tiktoken.Encoding` with the `pat_str` and the special tokens
copied from that version's `o200k_base` constructor.
"""

from __future__ import annotations

import base64
import functools
import hashlib
import pathlib

import tiktoken

__all__ = ["reference_encoding", "count_tokens"]

_ENCODING_NAME = "o200k_base"
_ENCODING_PATH = pathlib.Path(__file__).resolve().parent / "data" / "o200k_base.tiktoken"

# The `expected_hash` tiktoken 0.14.0 pins for o200k_base in
# `tiktoken_ext/openai_public.py`.  An independent source: the file is checked against
# the library's own literal, not against a digest taken of the file itself.
_ENCODING_SHA256 = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"

# Copied verbatim from tiktoken 0.14.0's `o200k_base`, only rewrapped to the line
# length.  `_check_matches_library` in the devlog's step-2 note is how it was compared.
_PAT_STR = "|".join(
    [
        r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+"
        r"(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
        r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*"
        r"(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
        r"\p{N}{1,3}",
        r" ?[^\s\p{L}\p{N}]+[\r\n/]*",
        r"\s*[\r\n]+",
        r"\s+(?!\S)",
        r"\s+",
    ]
)
_SPECIAL_TOKENS = {"<|endoftext|>": 199999, "<|endofprompt|>": 200018}


def _mergeable_ranks() -> dict[bytes, int]:
    """Parse the local file, after checking it is the one tiktoken pins.

    The check is not decoration.  Nothing downstream would notice a corrupted encoding
    file: a flipped byte moves a rank, every count shifts, and the token band and the
    equal-count sets frozen against it become quietly wrong.
    """
    if not _ENCODING_PATH.exists():
        raise FileNotFoundError(
            f"the {_ENCODING_NAME} encoding file is not here: {_ENCODING_PATH}. "
            f"It is not shipped with this package; fetch it once with "
            f"`python -m task_generator.fetch_encoding`."
        )
    blob = _ENCODING_PATH.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != _ENCODING_SHA256:
        raise ValueError(
            f"{_ENCODING_PATH} is not the encoding tiktoken 0.14.0 pins: "
            f"sha256 {digest}, expected {_ENCODING_SHA256}"
        )
    ranks: dict[bytes, int] = {}
    for line in blob.splitlines():
        if not line:
            continue
        token, rank = line.split()
        ranks[base64.b64decode(token)] = int(rank)
    return ranks


@functools.lru_cache(maxsize=1)
def reference_encoding() -> tiktoken.Encoding:
    """The o200k_base encoding, built from the local file with no network and no cache.

    Cached, because building it parses 200k lines.  A test that has to see the build
    itself -- T2, which disables the network -- therefore has to run in a fresh
    interpreter, and the tests say so.
    """
    return tiktoken.Encoding(
        name=_ENCODING_NAME,
        pat_str=_PAT_STR,
        mergeable_ranks=_mergeable_ranks(),
        special_tokens=_SPECIAL_TOKENS,
    )


def count_tokens(text: str) -> int:
    """The o200k_base token count of `text`.

    `encode_ordinary`, so that a string carrying something that looks like a special
    token is counted as the text it is rather than raising.  The engine's vocabulary
    cannot produce one; TG-M2's prompts are rendered from model output-adjacent
    material, and a counter that raises there would be the wrong failure.
    """
    return len(reference_encoding().encode_ordinary(text))
