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
- **Reproducible validation (`dsguard`)** — deterministic, reproducible
  SHA-256 hashing of approved artifacts (`sha256/lf/v1`, LF-normalized) and an
  append-only `control.json` approval ledger, so an approval can never
  silently drift from the artifact it was granted for.
- **Safe notebook execution (`nbrunner`)** — a JSON run manifest schema that
  declares the interpreter (must resolve inside the project's own `.venv`),
  the notebook's approved hash, and explicit allow-lists for input/output
  paths, plus a hard, project-configurable deny-list (e.g. `data/raw/**` is
  always output-forbidden) enforced independently of what any manifest
  declares.
- **A safe installer (`ds_init`)** — `--dry-run` by default, atomic
  `--execute` (staged, journaled, with full rollback on any failure), never
  overwrites files that already exist in the destination, and merges
  `.claude/settings.json` instead of clobbering it.

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

Harmessi ships one CLI today, the installer:

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
anything is moved into place, and any failure mid-installation rolls back
everything already applied.

## Profile

The current (and only) profile is `python-jupyter-data`: agents, the
`lead-data-scientist` skill, `dsguard`, `nbrunner`, and SDD templates for a
Python/Jupyter data science project.

## Development

```bash
python -m unittest discover -s tools/ds_init/tests -p "test_*.py"
python -m tools.ds_init.check_manifest_parity   # dev-only, read-only drift check
```

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
