# Harmessi

An agentic operating system for Data Science projects in Python and
Jupyter — specialized agents, governed workflows, reproducible validation,
and safe notebook execution.

Harmessi installs a small, opinionated harness into an existing Git
repository: purpose-built subagents, a lightweight spec-driven-development
(SDD) workflow, a deterministic approval/guard mechanism, and a manifest-based
notebook runner that only ever touches the inputs/outputs a run explicitly
declares. It is generic by design — no organization names, datasets, or local
paths are baked in — so it can be dropped into any Python + Jupyter data
science project.

## Capabilities

- **Specialized agents** — a `python-data-engineer` implementation agent (the
  only one with write access), plus read-only `data-science-reviewer` and
  `metodologo` agents, and a `notebook-runner` agent for controlled execution.
- **A governed workflow** — a `lead-data-scientist` orchestrator skill that
  drives a lightweight SDD loop (proposal → spec → design → tasks →
  verification) instead of ad hoc prompting.
- **KDD project lifecycle** — a separate, persisted state
  (`openspec/kdd/state.json`) tracking which Data Science lifecycle stage
  (Problem Understanding → ... → Monitoring) the project is in, kept distinct
  from SDD's per-change state: a change can declare which stage(s) it
  belongs to, and closing it appends evidence to that stage without ever
  auto-advancing it — advancing a stage stays an explicit, approved action.
- **Reproducible validation (`dsguard`)** — deterministic, reproducible
  SHA-256 hashing of approved artifacts (`sha256/lf/v1`, LF-normalized) and an
  append-only `control.json` approval ledger, so an approval can never
  silently drift from the artifact it was granted for.
- **Technical path protection (`dsguard.pathguard`)** — a `PreToolUse` hook
  that enforces, for every agent and the Lead alike, not just prompt-level
  instructions: secrets (`.env`, private keys, SSH files, cloud credentials —
  read and write, always) and holdouts/sealed datasets (write always denied,
  read denied unless an explicit, auditable exception is recorded in
  `.claude/guardrails.json`) are blocked outright; `data/raw` stays
  write-protected but readable; `.claude/guardrails.json` itself can't be
  edited by any agent or the Lead through `Write`/`Edit`/`NotebookEdit`. The
  guarantee is exact for `Write`/`Edit`/`NotebookEdit`/`Read`/`Grep`
  (structured, resolved paths — symlinks and `..` included); for
  `Bash`/`PowerShell` it's a best-effort text scan, explicitly not
  equivalent, since no shell parser is involved.
- **Safe notebook execution (`nbrunner`)** — a JSON run manifest schema that
  declares the interpreter (must resolve inside the project's own `.venv`),
  the notebook's approved hash, and explicit allow-lists for input/output
  paths, plus a hard, project-configurable deny-list (e.g. `data/raw/**` is
  always output-forbidden) enforced independently of what any manifest
  declares.
- **A safe installer (`ds_init`)** — `--dry-run` by default, atomic
  `--execute` (staged, journaled, with rollback on any handled failure —
  including `control.json` generation), never overwrites files that already
  exist in the destination, and merges `.claude/settings.json` instead of
  clobbering it.
- **A health check (`harmessi doctor`)** — read-only diagnostic over an
  installed project: Python/Git/venv sanity, whether the managed files
  (`control.json`, agents, the `lead-data-scientist` skill, settings, hooks)
  are present and match their recorded hash, and whether the configured
  `PreToolUse` hooks and their launchers actually work — including flagging
  any hook that still depends on an external shell instead of invoking
  Python directly.
- **Cross-platform hook launchers** — the `PreToolUse` hook launchers
  (`tools/nbrunner/hook_launcher.py`, `tools/dsguard/hook_launcher_presupuesto.py`)
  are pure Python, with no dependency on `bash` or any other shell: they
  resolve the shared Git repo (Git worktrees included), respect a
  custom `venv_dir` from `control.json`, and use the correct interpreter
  layout for the host OS (`Scripts/python.exe` on Windows, `bin/python` on
  Linux/macOS) — failing closed if the authorized interpreter can't be
  resolved.
- **Deterministic dataset profiling (`ds_profile`) and Project EDA** — a
  standalone CLI that computes reproducible facts and quality flags for a
  CSV or Parquet dataset (no business interpretation), written to
  `.harmessi/profiles/<profile_id>/profile.json`, with holdouts protected in
  depth via `dsguard.pathguard` even from a direct CLI call; Project EDA is
  the Lead-driven process that interprets those facts for modeling decisions
  while respecting cutoff and holdout boundaries.

## Requirements

- Python 3.9+
- Git
- A destination repository that is itself a Git repo with a clean working
  tree

## Quickstart

```bash
git clone https://github.com/federcolombo/harmessi.git
cd harmessi
python -m venv .venv
.venv/Scripts/activate        # Windows (PowerShell: .venv\Scripts\Activate.ps1)
# source .venv/bin/activate    # macOS/Linux

# See the plan without touching anything (default behavior):
python -m tools.ds_init --destino /path/to/your/project --nombre my-project

# Apply it for real:
python -m tools.ds_init --destino /path/to/your/project --nombre my-project --execute
```

## Commands

Harmessi ships three CLIs today: the installer, a read-only health check, and
a deterministic dataset profiler.

### `harmessi doctor`

```
python -m tools.harmessi doctor [--destino DESTINO]
```

Diagnoses an already-installed project (default `--destino`: the current
directory) and prints one `[OK]` / `[WARN]` / `[ERROR]` line per check,
grouped under `CORE`, `HARMESSI`, and `RUNTIME`, plus a summary count. Exits
`0` if there is no `[ERROR]`, `1` otherwise. It never writes to the
destination (aside from a temporary file it creates and deletes as part of
the permissions check) and never repairs anything — v0.2 is diagnosis only.
Run it from a Harmessi source checkout, the same way as `ds_init`.

### `ds_profile`

```
python -m tools.ds_profile run --input INPUT --output OUTPUT [--markdown]
```

A deterministic dataset profiling CLI: it reports facts and quality flags
about a CSV or Parquet file — row count, schema, null counts, cardinality,
quantiles, a reproducible fingerprint, and deterministic quality flags — and
never interprets business meaning. CSV is read with pure stdlib (no pandas
dependency); Parquet support is optional and imported lazily via `pyarrow` —
if it isn't installed, `ds_profile` exits with code `3` and a clear message
instead of failing obscurely. Output is written to
`.harmessi/profiles/<profile_id>/profile.json` (the JSON is the source of
truth; pass `--markdown` to also derive a human-readable `profile.md`). Like
`nbrunner`, it defends holdouts in depth: it reuses `dsguard.pathguard` to
refuse profiling a declared holdout even when invoked directly from the CLI,
not only through an agent.

Project EDA — documented for the Lead in the installed
`.claude/skills/lead-data-scientist/eda.md` — is the process that interprets
these deterministic facts for modeling decisions while respecting cutoff and
holdout boundaries; it consumes `ds_profile`'s output rather than duplicating
its computation.

### `ds_init` (the installer)

```
usage: python -m tools.ds_init [-h] --destino DESTINO --nombre NOMBRE
                               [--notebooks-dir NOTEBOOKS_DIR]
                               [--venv-dir VENV_DIR] [--integrar-claude]
                               [--dry-run | --execute]

Inicializador del harness de agentes/tooling para proyectos de ciencia de
datos (perfil python-jupyter-data).

options:
  -h, --help            show this help message and exit
  --destino DESTINO     Repo local destino (debe existir, ser Git, working
                        tree limpio).
  --nombre NOMBRE       Nombre del proyecto, usado en placeholders de
                        plantillas.
  --notebooks-dir NOTEBOOKS_DIR
                        Directorio de notebooks del proyecto destino (default:
                        notebooks).
  --venv-dir VENV_DIR   Directorio del entorno virtual del proyecto destino
                        (default: .venv).
  --integrar-claude     Integra un bloque delimitado en un CLAUDE.md ya
                        existente (R9).
  --dry-run             Informa el plan, no escribe nada (comportamiento por
                        defecto).
  --execute             Ejecuta la escritura real, tras preflight exitoso.
```

`--dry-run` is the default: it always runs preflight checks and prints the
full installation plan without writing anything. Only `--execute` writes to
disk, and it does so atomically — a staged tree is validated in full (JSON
parses, no unresolved template placeholders, no forbidden strings) before
anything is moved into place. Any exception raised while applying the staged
tree or generating `.ds_init/control.json` rolls back everything already
applied, restoring the destination to its pre-`--execute` state; a rollback
failure on one individual entry doesn't stop the rest from being reverted,
and any entry that still couldn't be restored is named in the error message.

This guarantee covers exceptions handled within the same process — it does
not cover the process itself being killed or the machine losing power
mid-installation. In that case the destination can be left with a stray
`.ds_init_staging_<timestamp>/` directory (holding the journal and any
backups). `ds_init` detects that on the next run and refuses to proceed with
a specific message, but it does not repair or resume the interrupted
installation automatically — recovering from that state (inspecting and,
once safe, deleting the leftover staging directory) is a manual step.

### Platform compatibility

Harmessi runs on Windows, Linux, and macOS. Everything under `tools/`
(the installer, `doctor`, `dsguard`, `nbrunner`, and both `PreToolUse` hook
launchers) is pure Python, invoked as `python -m tools....` or via the
Python interpreter directly — no step depends on `bash`, PowerShell, or any
other shell. `subprocess` is always called with an argument list (never
`shell=True`), and the two hook launchers resolve the project's `.venv`
interpreter using the correct layout for the host OS (`Scripts/python.exe`
on Windows, `bin/python` on Linux/macOS), honoring a custom `venv_dir` from
`control.json` when one was used at install time, and correctly supporting
Git worktrees (the shared repo's own `.venv`, not the worktree's checkout,
is always the one used). Run `python -m tools.harmessi doctor` on an
installed project to verify this end to end, including whether any
configured hook still depends on an external shell.

## Profile

The current (and only) profile is `python-jupyter-data`: agents, the
`lead-data-scientist` skill, `dsguard`, `nbrunner`, and SDD templates for a
Python/Jupyter data science project.

## Development

```bash
python -m unittest discover -s tools/ds_init/tests -p "test_*.py"
python -m unittest discover -s tools/harmessi/tests -p "test_*.py"
python -m unittest discover -s tools/tests -p "test_*.py"
python -m unittest discover -s tools/ds_profile/tests -p "test_*.py"
python -m tools.ds_init.check_manifest_parity   # dev-only, read-only drift check
```

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
