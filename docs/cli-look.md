# One command-line look

**Standard:** `docs/cli-look.md`
**Applies to:** every Poisson Labs tool that has a command line. Each tool keeps a byte-for-byte copy of this page, and a test in the tool holds the tool to it.

A person who has used one of the lab's tools should be able to use the next without reading its manual. This page is the look they can count on: what a command prints first, where problems go, what the exit code means, and how the same result is drawn on a terminal and in a pipe. Where a rule names a command, `<tool>` stands for the tool's own command.

---

## The rules

**L1. One command per tool, with verbs under it, and `python -m <package>` does the same.** A tool is installed as one command, `<tool>`, whose first argument is a verb (`<tool> run`, `<tool> card`). Running the package as a module gives the same command.

**L2. Help that a stranger can act on.** Every verb's help gives:

- a description paragraph;
- every argument, with its help text and its default, or "no default";
- at least one example command.

Help goes to standard output and exits 0. It never needs an optional dependency, the network or a key.

**L3. The result comes first.** The first line a verb prints on standard output is a verdict line: a lowercase verdict word or phrase from that verb's closed set, two spaces, and one sentence. Detail follows, either as `label  value` lines indented two spaces, or as a report after one blank line.

**L4. Problems go to standard error, one line each, and say what to do.**

- An error is `error: <what happened, in plain words>`, with optional `  next: <exact command>` lines indented two spaces.
- A warning is `note: <sentence>`.
- Where there are valid alternatives, the line lists them.
- An error never contains a traceback, raw library exception text, a Python repr (a tuple, a quoted list), an internal identifier, or a key.
- An unexpected failure prints `error: an unexpected failure inside <tool> (<ExceptionType>); the details are in <log path>`, and the traceback goes to that file, or to standard error as well with `--debug`.

**L5. Exit codes mean the same in every tool.** See the table below.

**L6. Ctrl-C is a stop, not a crash.** It prints `stopped  interrupted: <what was kept>`, then `next: <the resume command>` where one exists, and exits 130.

**L7. Anything that spends money shows the plan first, checks the cap before asking, and keeps the plan on screen when it refuses.**

- The plan has a verdict line, and an estimate that names its source.
- It asks with `[y/N]` on standard error, and `--yes` skips the question.
- A standard input that is not a terminal, without `--yes`, prints the plan and refuses.
- `--dry-run` prints the plan and stops.

**L8. Keys are named, never read except to use, and never shown.** A setting holds the name of the variable that holds a key, never the key.

**L9. `--json` makes standard output exactly one strict JSON document.**

- `schema` is the first key, then `verdict` (the word) and `sentence` (the verdict line's sentence).
- There is no `NaN` or `Infinity`.
- The exit code is the same as without `--json`.
- Errors stay on standard error, in text.

**L10. Numbers read the same everywhere.**

- Rates and shares have three decimals.
- P-values have three decimals, or `2.3e-08` below 0.001.
- Dollars read `$1.00`, or with two significant digits below $0.10 (`$0.021`, `$0.0052`).
- Counts have thousands separators (`4,200`).
- Durations read `1 min 40 s` and `1 h 36 min`.
- Hashes have 12 hex characters in text, and are in full in JSON.
- Times are in UTC with `Z`.

**L11. Plain words.** No internal identifiers, ruling numbers or session names anywhere a user reads: output, help, the README, user documents, the changelog. A product's documented names are fine.

**L12. A verb that writes files says what it wrote, and refuses to overwrite without `--force`.**

**L13. A verb that has an obvious next step ends with `next: <exact command>`.** When `--config` was given, every `next:` command that reads the settings file carries it as given.

**L14. Configs are strict.** An unknown key in any config or spec file is refused, with the nearest known key.

**L15. Options may come before or after the verb, and abbreviations are refused.**

**L16. Two renderings of one result, and the plain one is the contract.** Every verb builds one result: the verdict word, its sentence, the detail and the next commands. It is printed one of two ways.

- **Plain** is text only, with no escape sequence and the standard library only. Tests, documents and the conformance test pin this rendering. It falls back to ASCII when the stream cannot encode the glyphs (`·`, `–`, `×`). On a terminal it wraps its own long lines at the terminal's width with a hanging indent, never inside a question's bracketed default; piped, every fact stays on one line.
- **Pretty** is the same facts in the same order, drawn with Rich, and with questionary for a dialogue's menus. It runs only when standard output and standard error are both terminals, `NO_COLOR` is unset or empty, `CI` is unset, `TERM` is not `dumb`, standard output is UTF-8, and neither `--json` nor `--plain` was given. Otherwise the plain rendering runs, byte for byte. It is claimed for macOS and Linux terminals, not for Windows, and never in CI.
- **Colour has four meanings and no others.** Green: the command did what was asked (`ok`, `done`, `passed`). Yellow: it stopped short or cannot say (`stopped`, `refused`, `too small to tell`, `note:`). Red: an error or a failed check (`error:`, `not ready`, `fail`). Dim: secondary text. A verdict word that is neither good nor bad (`plan`, `different`) is bold and has no colour. A number is never coloured.
- Only the terminal's 16 named colours, bold and dim are used, so the user's theme decides the shades.
- A command printed for the user to copy is never hard-wrapped.
- Questions and progress stay on standard error. A live display is removed when the work ends, so what remains on screen is the result.
- When a table is too wide for the terminal, the pretty style moves a unit that every cell repeats into the header, with nothing dropped.
- The conformance test runs each invocation both ways. Piped, the pretty build must equal the plain build byte for byte. On a pseudo-terminal, with escape sequences removed, the first line must carry the same verdict word and sentence, and the exit code must be the same. `--json` must be identical.

---

## Exit codes

| code | meaning |
|---|---|
| 0 | Done: the result is printed, whatever it says. A result that reads "too small to tell" is still 0. |
| 1 | Refused: nothing was spent or written. |
| 2 | The command line is wrong (usage). |
| 3 | Stopped or failed after work started, or an unexpected failure. What was kept is printed. |
| 4 | A check you asked for did not pass: a verification, a readiness check, a recompute that differs. |
| 130 | Interrupted. |

Exit 4 belongs to a check the user asked for, never to a result the user did not ask to gate on. A script that wants a result to fail asks for that.
