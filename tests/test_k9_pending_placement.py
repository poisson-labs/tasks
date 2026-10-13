"""Pending a yes/no: the driver is a module of the package, beside the notebook's driver.

**The question.**  "The driver is committed beside the notebook.  It is not a user command and adds
nothing to the command-line tool."  It could be a file in `notebooks/` or a module of the package.

**Proposed: `poisson_tasks.knob_probe`**, run as `python -m poisson_tasks.knob_probe`, beside
`poisson_tasks.calibration_run`, the module the notebook already drives and which the spec says
holds the probe's design.  The notebook's probe design imports the probe's arms and gates from it,
which a file in `notebooks/` could not offer the installed package; it is type-checked with the
package.  `notebooks/` keeps the notebook and its requirements.  **A no** moves it to
`notebooks/`, and the Qwen design then carries its own copy of the design and the gates.
"""

from __future__ import annotations

from tests.k9_support import REPO


def test_the_driver_is_a_module_of_the_package_and_notebooks_holds_the_notebook() -> None:
    from poisson_tasks import knob_probe as probe

    assert probe.__file__ is not None
    assert (REPO / "src" / "poisson_tasks" / "knob_probe.py").samefile(probe.__file__)
    assert sorted(p.name for p in (REPO / "notebooks").iterdir()) == [
        "calibration_model_b.ipynb",
        "requirements-colab.txt",
    ]
