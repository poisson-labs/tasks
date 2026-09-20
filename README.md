# task-generator

A deterministic generator of tool-use tasks over one mock stateful domain.
Each task is generated together with its verifier. Tasks are emitted as a
verifiers v1 taskset and as Proofload rollout targets, one per pre-registered
arm. Generation makes no model calls and no network calls.

"task-generator" is a working label, not a name.

Status: scaffold. No module is built yet.

## Setup

Needs Python 3.11 and a Proofload checkout at `../proofload`.

```
python3.11 -m venv .venv
.venv/bin/pip install -e ../proofload
.venv/bin/pip install -e ".[dev]"
```
