# Before a run: what it costs, and what it changes on your machine

What a first run spends, what it writes outside the folder you work in, what it changes about
your shell's limits, and what it sends over the network. The [README](../README.md) has the
short version; this page has every item.

## Money

`run` prints its estimate before it asks, and the estimate names where it comes from (a
published card, scaled to your plan). A first look is 30 episodes against `gpt-5-nano`: about
two cents.

Every run has a finite cap, by default the larger of $1.00 and twice the estimate, rounded up
to a whole dollar. The cap is checked on measured usage, so a run can pass it by at most what
the calls already in flight cost. [config.md](config.md) has the cap's settings.

## What gets written outside your folder

`init` and `run` write only to the folder you work in (`tasks.toml`, `runs/`, `tasks/`), apart
from the following, which the first run does once or on every run.

### The tokenizer file

The tokenizer file, 3.6 MB, is fetched once from openaipublic.blob.core.windows.net into the
installed package. It is not shipped with the package; `poisson-tasks doctor --fix` fetches it
too.

### uv, for the harness

On every run, the first episode runs the harness's setup.

- With uv 0.6.10 or later already on your `PATH` (or in `~/.local/bin`, which the setup looks
  in first), the installer is not fetched and your uv is left as it is.
- Without one, uv's installer from astral.sh puts `uv` and `uvx` in `~/.local/bin` (and its
  receipt in `~/.config/uv`), replacing an older uv there.
- Either way, four packages and their dependencies come from PyPI into uv's cache.
- `run` sets `UV_NO_MODIFY_PATH=1` so the installer does not edit your shell start-up files.

The plan prints this in its `harness` line, and so does `doctor`:

<!-- docs-check: run -->
```bash
poisson-tasks doctor --offline | grep harness
```

<!-- docs-check: output -->
```
  harness    ok      each run's first episode sets up uv with astral.sh's installer unless uv 0.6.10 or later is already on your PATH, and fetches four packages and their dependencies from PyPI
```

### verifiers and uv's leftovers

- verifiers' cache, in `~/.cache/verifiers`;
- one `/tmp/vf-port-<hex>` file per episode, which verifiers leaves behind;
- one empty `uv-<16 hex>.lock` file in the temporary folder, which uv writes for the harness's
  script environment and keeps.

## Your limit on open files

For its own length, `run` raises its process's limit on open files as far as your hard limit
allows (macOS starts a shell at 256, and a run of 128 episodes at once needs up to 704). It
changes nothing outside that process. When the hard limit is too low it refuses before it
starts, in one line saying how to raise it.

Your shell's soft and hard limits are:

<!-- docs-check: run -->
```bash
ulimit -Sn; ulimit -Hn
```

## Commands verifiers installs

Installing the package also installs verifiers, and verifiers installs commands beside
`poisson-tasks`: `eval`, `init`, `debug`, `replay`, `validate`, `gepa` and `vf-*`. A bare
`init` is verifiers' command, not this package's; this package's is `poisson-tasks init`.

## What goes over the network

A run sends your key to your model's endpoint and nowhere else, and uploads nothing: it runs
verifiers with `push` off. Generating tasks, `generate`, `verify`, `export`, `card` and
`doctor --offline` open no connection to a model.
