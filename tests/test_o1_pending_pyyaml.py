"""Pending a decision: `pyyaml` is a declared dependency of the package.

The own-tools design reads OpenAPI "YAML or JSON".  The package depends on `verifiers==0.3.1`
and `tiktoken==0.14.0` and nothing else; PyYAML is installed beside them today only because
`verifiers` pulls in `datasets` and `huggingface_hub`, which require it.  A reader that imports
`yaml` on the strength of that is one upstream change away from an `ImportError` in a user's
`init`.  This test pins the recommendation: `pyyaml` is named in `[project].dependencies`, as a
floor (`pyyaml>=6.0`), so the YAML path is the package's own promise.  It is in its own commit,
so if it is declined it is dropped alone; the readers' tests do not depend on it.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


def test_pyyaml_is_a_declared_dependency() -> None:
    pyproject = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
    names = [re.split(r"[\s<>=!~;\[]", dep, maxsplit=1)[0].lower() for dep in pyproject["project"]["dependencies"]]
    assert "pyyaml" in names
