# Harmessi

Harmessi is a governed agentic harness for Data Science projects in Python and
Jupyter.

Source available — [PolyForm Shield 1.0.0](LICENSE). See [License](#license).

Harmessi installs onto an existing Git repository and adds specialized agents,
deterministic guardrails and reproducible workflows: a lightweight
spec-driven-development (SDD) loop, hash-based approvals, path protection for
secrets and holdouts, and a manifest-based notebook runner that only touches the
inputs and outputs a run explicitly declares. It does not replace your
notebooks, Python code, libraries or infrastructure; it governs how an agent
works on them.

The core difference is that governance does not live only in prompts. Approvals,
scope, path protection and notebook execution are enforced by deterministic code
(`PreToolUse` hooks and CLIs that fail closed), so they apply to every agent and
to the orchestrating Lead alike, not only when a model chooses to follow
instructions. The path-protection guarantee is exact for structured file tools;
for shell commands it is a best-effort scan (see [Capabilities](#capabilities)).

## Why Harmessi?

Agentic coding tools are fast, but on a Data Science project they tend to fail in
specific ways. Harmessi targets those failure modes:

- **Uncontrolled agent edits.** Only one role can write code; every Change has a
  declared scope, and out-of-scope edits are detected.
- **Methodology and decisions getting lost.** Proposals, specs, approvals and a
  decision ledger are plain files in Git, tied to the exact artifact they approved.
- **Leakage and holdout exposure.** Holdouts and sealed datasets are write-protected
  and read-denied by default, secrets are always blocked, and cutoff/holdout/leakage
  checks are declared rather than inferred.
- **Arbitrary notebook execution.** Notebooks run only from an approved manifest:
  approved hash, interpreter inside the project's `.venv`, explicit input/output
  allow-lists and a hard deny-list.
- **Weak reproducibility and unclear evidence.** Profiles, run manifests and
  validation results are small JSON/Markdown files that record what was run, on
  what, and with which hashes.

Harmessi turns these concerns into a governed, verifiable workflow instead of a
convention.

## Who is it for?

- Data Scientists and ML practitioners who want to use coding or agentic CLIs on
  their own projects without giving up control.
- Technical DS/ML teams that need decisions, approvals and evidence to be
  reviewable in Git.
- Python + Jupyter + Git projects (the current and only profile is
  `python-jupyter-data`).

It is not a general-purpose platform for any kind of software engineering.

## What Harmessi is — and is not

| Harmessi is | Harmessi is not |
|---|---|
| An agentic Data Science harness | An ML framework |
| A set of specialized, permission-scoped roles | An experiment tracker replacement |
| SDD and governance as plain files in Git | An Airflow / Kubernetes replacement |
| Deterministic guardrails (hooks and CLIs) | A deployment platform |
| Reproducible evidence (hashes, manifests, profiles) | A compliance engine |
| Safe, manifest-based notebook execution | An automatic judge of model fairness or safety |
| Support for a CRISP-DM / KDD / MLOps lifecycle | |

## Quickstart

Harmessi is run from a checkout of this repository; it is not installed as a
package.

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

Requirements:

- Python 3.12 is the verified version (see [Platform and CI status](#platform-and-ci-status)).
  Python 3.9 is the declared minimum; it is not executed (neither in CI nor in the
  verification of this release).
- Git.
- A destination repository that is itself a Git repo with a clean working tree.

After installing, run `python -m tools.harmessi doctor --destino /path/to/your/project`
from the checkout to verify the installation (see [`harmessi doctor`](#harmessi-doctor)).

## Provider and CLI support

Harmessi has provider adapters, routing and fallback across four providers. Their
support levels in v1 are:

| Provider / CLI | Level in v1 |
|---|---|
| Claude Code | Primary host/runtime, the one validated live (see below) |
| Claude Code (provider adapter) | `live-validated` (one real run on 2026-10-26, single Windows 11 host, one CLI version; historical evidence, not a standing guarantee) |
| Codex CLI | `contract-tested` |
| Gemini CLI | `contract-tested` |
| Grok CLI | `contract-tested` |

`contract-tested` means the adapter meets the common `ProviderAdapter` contract
against test doubles, with no credentials and no network; it does not prove the
behavior of the real CLI.

Harmessi does **not** claim that you can open Claude Code, Codex, Gemini or Grok
interchangeably and get the same complete harness. The installed structure still
uses Claude Code's `.claude/` directory, agents, skills and hooks. Provider
neutrality means a common adapter contract, not semantic equivalence and not
host equivalence. The evidence record and the support matrix are in
[docs/providers.md](docs/providers.md).

## Footprint

Measured against the current v1 manifest, the default installation (stage
`experiment` with the `predictive_modeling` capability) provisions about 135
managed files — roughly 1.9 MiB of Harmessi content — plus a generated
`.ds_init/control.json`. The `discovery` stage is lighter. These figures describe
the current v1 manifest, not a permanent guarantee.

- That weight is small next to a project's `.venv`, datasets, notebooks and models.
- Harmessi uses mainly the Python standard library; `pyarrow` is optional and only
  needed to profile Parquet files.
- Artifacts generated by day-to-day use are mostly small JSON and Markdown files.
- Installation is progressive: `discovery → experiment → production_candidate →
  production` (`ds_init sync --stage <stage>` extends an installed project).

## Capabilities

- **Specialized roles and a Lead orchestrator.** A `python-data-engineer`
  implementation agent (the only one with write access), read-only
  `data-science-reviewer` and `metodologo` agents, and a `notebook-runner` agent for
  controlled execution, driven by a `lead-data-scientist` skill that runs a
  lightweight SDD loop (proposal → spec → design → tasks → verification) instead of
  ad hoc prompting. Skills are guidance, not enforcement.
- **Deterministic governance (`dsguard`).** Approvals are bound by SHA-256 hash
  (`sha256/lf/v1`, LF-normalized) to the artifact they were granted for and recorded
  in an append-only `control.json` ledger, so an approval cannot silently drift.
  Change scope, an append-only decision ledger and bounded remediation are checked
  by `ds_guard`. The hash proves content identity, not human approval or authorship.
- **Technical path protection (`dsguard.pathguard`).** A `PreToolUse` hook that
  applies to every agent and to the Lead: secrets (`.env`, private keys, SSH files,
  cloud credentials) are blocked for read and write; holdouts and sealed datasets are
  write-denied always and read-denied unless an explicit, auditable exception is
  recorded in `.claude/guardrails.json`; `data/raw` is write-protected but readable;
  and `.claude/guardrails.json` itself cannot be edited through `Write`, `Edit` or
  `NotebookEdit`. The guarantee is exact for `Write`/`Edit`/`NotebookEdit`/`Read`/`Grep`
  (structured, resolved paths, symlinks and `..` included); for `Bash`/`PowerShell` it
  is a best-effort text scan, explicitly not equivalent, since no shell parser is involved.
- **Safe notebook execution (`nbrunner`).** A JSON run manifest declares the
  interpreter (it must resolve inside the project's own `.venv`), the notebook's
  approved hash and explicit allow-lists for input and output paths, on top of a hard,
  project-configurable deny-list (for example, `data/raw/**` is always
  output-forbidden) enforced independently of the manifest. The hook launchers are
  pure Python with no dependency on `bash`, and fail closed if the authorized
  interpreter cannot be resolved.
- **A governed lifecycle (CRISP-DM + KDD + MLOps).** A single persisted state
  (`openspec/lifecycle/state.json`) uses CRISP-DM as the methodological backbone,
  KDD as the technical process inside the relevant phases, and MLOps as three tiers of
  progressive capabilities. Project maturity (`project_stage`: `discovery`,
  `experiment`, `production_candidate`, `production`) is tracked separately from the
  installed capabilities (`installation_stage`); `ds_guard project readiness` evaluates
  a deterministic gate matrix and `ds_guard project promote` advances one stage at a
  time. Closing a Change appends evidence and never auto-advances a phase.
- **Data work.** `ds_profile` computes reproducible facts and quality flags for CSV and
  Parquet datasets (with holdouts protected even from a direct CLI call); Project EDA is
  the Lead-driven process that interprets those facts while respecting cutoff and
  holdout boundaries; `ds_guard science` runs cutoff, holdout, leakage and baseline
  checks declared in an optional `.harmessi/scientific-policy.json`, never inferred.
- **Evidence, Cards and reporting (opt-in).** Data Cards, Model Cards and a progressive
  model-governance assessment by `risk_level` over six Responsible AI dimensions
  (fairness, explainability, privacy, security, accountability, human oversight), plus
  governed HTML reporting (`python -m tools.reporting`). Harmessi governs *evidence*: a
  Card references evidence that already exists and validates that it is present, current
  and coherent. It does **not** claim that a model or dataset is ethical, fair, safe,
  private, secure or compliant. Harmessi covers the lifecycle up to readiness evidence;
  deployment and monitoring are an integration boundary
  ([docs/production-lifecycle.md](docs/production-lifecycle.md)).
- **Installer, diagnostics and evaluation.** A safe installer (`ds_init`: dry-run by
  default, atomic and journaled `--execute`, never overwrites existing files, merges
  `.claude/settings.json`, transactional `upgrade` and `recover`), a read-only health
  check (`harmessi doctor`), provider detection, routing and fallback, and a
  deterministic evaluation framework (`harmessi-bench`) kept apart from the unit tests.
  Evaluation never promotes or modifies harness surfaces on its own.

## Interfaces

Core day-to-day interfaces include:

- **`ds_guard`** — SDD, approvals, lifecycle, maturity and the unified project status.
- **`ds_init`** — the installer, upgrader and recovery tool.
- **`harmessi doctor`** — a read-only health check of an installed project.
- **`ds_profile`** — the deterministic dataset profiler.

Additional and specialized tooling:

- `harmessi providers`, `harmessi routing` and `harmessi fallback` — provider
  detection, declarative routing and fallback.
- `python -m tools.reporting` — governed reporting.
- `harmessi-bench` — evaluation runs and comparison (checkout only).
- Provider and source-observer conformance (checkout only, or installed in projects
  where noted).

Each one is documented in the [Command reference](#command-reference) below.

## Command reference

Core day-to-day interfaces: [`ds_guard`](#ds_guard), [`ds_init`](#ds_init-the-installer),
[`harmessi doctor`](#harmessi-doctor) and [`ds_profile`](#ds_profile). Additional and
specialized tooling: [providers, conformance, routing and fallback](#harmessi-providers),
[reporting](#reporting) and [`harmessi-bench`](#harmessi-bench); conformance and
evaluation tools run from a checkout.

### `ds_guard`

```
python -m tools.ds_guard <group> <command> [options]
```

The main day-to-day CLI once a project is installed: SDD (`init`, `status
--change-id`, `validate`, `approve`, `transition`, `session ...`,
`notebook-diff`, `archive`), lifecycle (`lifecycle migrate`), project
maturity (`project init|calibrate|set-risk|status|readiness|promote`),
MLOps (`mlops status|record|evidence add`), the decision ledger (`decision
add|supersede|revoke|list|show`), bounded remediation (`remediation
resolve|extend`), and the unified project view (`status`, with no
`--change-id`, `--json`/`--verbose` optional). All state it manages lives in
plain JSON (`.harmessi/project.json`, `openspec/lifecycle/state.json`,
`openspec/changes/*/control.json`, `openspec/decisions/ledger.jsonl`) — no
hidden state, no separate database. Full command-by-command reference lives
in the installed `.claude/skills/lead-data-scientist/verificador.md`/
`methodology.md` (read by the Lead orchestrator, not duplicated here).

`ds_guard` also groups two deterministic checks: `science
status`/`science status --json` (`tools/dsguard/scientific_validity.py`) runs
scientific validity checks (temporal cutoff, holdout, direct leakage,
baseline) declared via an optional `.harmessi/scientific-policy.json` — never
inferred by heuristic; `efficiency report --change-id <id> [--json]`
(`tools/dsguard/efficiency.py`) re-evaluates a change's already-recorded
sessions/remediations against its own declared budget, adding signal without
gating anything. Separately, `ALCANCE-RUTA` (the scope check in
`validate`/`gate_cierre`) covers the full diff since
`control["baseline"]["commit"]`, not just the current working tree, so an
out-of-scope file that was already committed is still caught even if the
working tree is clean again.

### `ds_guard impact scan`

```
python -m tools.ds_guard impact scan --since <ref>|--staged [--json]
```

A static impact preflight (`tools/dsimpact/`, a separate package installed
from the `experiment` stage onward): it detects which files/symbols/contracts
a diff might affect, always reporting them as "potentially affected", never
as "broken". On a `discovery` installation, where `tools/dsimpact/` isn't
present, it degrades gracefully — exit code `3` and a clear message instead
of a traceback.

### `harmessi doctor`

```
python -m tools.harmessi doctor [--destino DESTINO]
```

Diagnoses an already-installed project (default `--destino`: the current
directory) and prints one `[OK]` / `[WARN]` / `[ERROR]` line per check,
grouped under `CORE`, `HARMESSI`, and `RUNTIME`, plus a summary count. Exits
`0` if there is no `[ERROR]`, `1` otherwise. It never writes to the
destination (aside from a temporary file it creates and deletes as part of
the permissions check) and never repairs anything — it is diagnosis only.
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

Memory is bounded by design: before reading rows, `ds_profile` decides between
exact and sampled mode from file metadata and an explicit memory budget
(`--max-mb-exactos`, an estimate rather than a hard sandbox limit). Cheap
metrics (counts, nulls, min/max, mean/std, dtype) stay exact in both modes;
metrics that need many values (distinct counts, top values, quantiles,
duplicate rows) fall back to a deterministic sample when the source exceeds the
budget, and the profile says so (`sampling.motivo`, `exactitud`). The
estimate is per dtype when the reader provides a schema (Parquet;
`sampling.estimacion`), and exact-mode Parquet profiles are computed column by
column (`sampling.modo_lectura`) with a result identical to the row-by-row path.
The defaults (2 000 000 rows / 500 MB) are heuristics that have not been
validated against a real production dataset; tune `--max-filas-exactas` and
`--max-mb-exactos` for your data.

Project EDA — documented for the Lead in the installed
`.claude/skills/lead-data-scientist/eda.md` — is the process that interprets
these deterministic facts for modeling decisions while respecting cutoff and
holdout boundaries; it consumes `ds_profile`'s output rather than duplicating
its computation.

### `ds_init` (the installer)

```
python -m tools.ds_init [install|sync|migrate-hashes|upgrade|recover] --destino DESTINO
    [--nombre NOMBRE] [--notebooks-dir NOTEBOOKS_DIR] [--venv-dir VENV_DIR]
    [--integrar-claude] [--stage {discovery,experiment,production_candidate,production}]
    [--dry-run | --execute]
```

- `install` (default) sets up a new destination; `sync` extends an installed one to a
  higher `--stage`; `upgrade` brings it to the current harness version; `recover`
  reverts an interrupted run; `migrate-hashes` migrates the managed-hash contract.
- `--destino` must be an existing Git repository with a clean working tree.
- `--nombre` is the project name (required for `install`).
- `--notebooks-dir` (default `notebooks`) and `--venv-dir` (default `.venv`) apply to `install` only.
- `--integrar-claude` merges a delimited block into an existing `CLAUDE.md` (`install` only).
- `--stage`: for `install`, `discovery` or `experiment` (default `experiment`); for `sync`, any of the four (required).
- `--dry-run` (default) reports the plan and writes nothing; `--execute` performs the real write after a successful preflight.

`install` (the default action) sets up a new destination — `discovery` is a
deliberately light bundle (viability/exploration tooling only); `experiment`
(the default) adds the full DS agent stack. `sync` extends an
*already-installed* destination up to a higher `--stage`, adding only the
files missing for that stage — idempotent, never overwrites an existing
file, never deletes anything, and rejects a `--stage` lower than what's
already installed as a no-op rather than silently doing nothing.

`--dry-run` is the default for both actions: it always runs preflight checks
and prints the full plan without writing anything. Only `--execute` writes
to disk, and it does so atomically — a staged tree is validated in full
(JSON parses, no unresolved template placeholders, no forbidden strings)
before anything is moved into place. Any exception raised while applying the
staged tree or generating `.ds_init/control.json` rolls back everything
already applied, restoring the destination to its pre-`--execute` state; a
rollback failure on one individual entry doesn't stop the rest from being
reverted, and any entry that still couldn't be restored is named in the
error message.

The in-process rollback does not cover the process itself being killed or the
machine losing power mid-installation. In that case the destination can be
left with a stray `.ds_init_staging_<timestamp>/` directory and a persistent
journal under `.ds_init/journal/<timestamp>/` (journal phase plus backups).
`ds_init install|sync|upgrade` detect that on the next run and refuse to
proceed, pointing to `recover` (see below).

#### Upgrading an installed project (`upgrade`)

```
python -m tools.ds_init upgrade --destino <path>             # dry-run (default)
python -m tools.ds_init upgrade --destino <path> --execute   # apply
```

`upgrade` brings an already-installed project to the current harness version.
It shows installed vs. current version and a summary (to update / to create /
drift / preserved / blocking). It only updates managed files that are still
pristine (match their recorded baseline), creates managed files that are new
in the manifest (for the persisted stage and capabilities), and merges
`settings.json` as before. It never touches project-owned files (notebooks,
data, Cards, Data Contracts, decision ledger, amendments, `GLOSSARY.md`,
approvals in `openspec/changes/**/control.json`), never overwrites an existing
`guardrails.json`, and reports drifted files without touching or adopting
them. `--execute` re-computes the plan, takes `.ds_init/lock`, and applies
everything (files plus the regenerated `control.json`, written atomically) in
one journaled transaction with backups. It is idempotent: a second run
changes nothing. With nothing pending it reports that there is nothing to do and exits 0.

#### Recovering from an interrupted run (`recover`)

```
python -m tools.ds_init recover --destino <path>             # dry-run (default)
python -m tools.ds_init recover --destino <path> --execute   # revert
```

`recover` reverts an interrupted transaction to the previous consistent state
from its journal and backups, then removes the staging and journal. It is
rollback only, never roll-forward; after it, `upgrade`/`install` converge. If
the journal is unreadable or a needed backup is missing it exits with code 2,
touches nothing, and prints the exact manual steps; the same happens if a
journal path is invalid (absolute, `..`, `:` in a component, inside `.git/`,
resolving outside the destination, or not in the MANIFEST nor under
`.ds_init/`). If a file to be reverted was edited after the interruption
(its hash is neither the one the transaction wrote nor the backup's),
`recover --execute` aborts with exit 2 and lists it; `--forzar` reverts it
anyway and keeps your copy as `<path>.recover-bak`. A journal in phase
`completo` is treated as clean (housekeeping: it is just deleted), and a
journal directory without `journal.json` is a cleanable leftover.
`migrate-hashes --execute` also takes the lock and refuses to run with an
orphan staging/journal; the `control.json.bak-<timestamp>` backups it creates
are kept (they are not cleaned up by `recover`).
`harmessi doctor` reports `HARMESSI-VERSION` (WARN with the `upgrade` remedy)
and `HARMESSI-MIGRACION` (FAIL on partial staging/journal, WARN on a leftover
lock or completed journal).

Honest limits: no downgrade; no data migration; `.ds_init/lock` is a
cooperative lock, not a defense against a hostile actor; after a kill the
lock can remain (`.ds_init/lock`): delete it by hand if no `ds_init` process
is alive (there is no pid detection, on purpose); Doctor runs from the Harmessi checkout;
`upgrade` does not re-create a managed file you deleted by hand (restore it
from Git).

### `harmessi providers`

```
python -m tools.harmessi providers list [--json]
```

Clean detection of the 4 provider adapters (Claude Code, Codex CLI, Gemini
CLI, Grok CLI) via `tools/providers/`. Only Claude Code CLI has been verified
against a real binary during Harmessi's own development — the other 3
degrade to "not available" without attempting to install anything or
fabricate a signal. `--json` reports, per provider, `available`,
`authenticated` (always `null` today — no cheap way to check it without a
real session), `version`, and declared capabilities. Run it from a Harmessi
source checkout, the same way as `harmessi doctor`.

#### Provider conformance (checkout only)

```
python -m tools.providers.conformance [--provider ID] [--smoke] [--live] [--json]
```

Checks each adapter against test doubles (no credentials, no network) and
reports a support level: `contract-tested`, `locally-smoke-tested`
(`--smoke`: real `detect()` on this host) or `live-validated` (`--live` AND
`HARMESSI_LIVE_PROVIDER=1`; may cost money, never runs by default). Exit 0 if
every evaluated provider reaches at least `contract-tested`, 1 otherwise, 2
if `--live` is used without the environment variable (nothing is invoked).
The declared table is `SOPORTE_DECLARADO` in `tools/providers/conformance.py`:
`claude_code` is declared `live-validated` (one real run on 2026-10-26, a
single Windows 11 host, CLI `2.1.310`; not reproducible in CI and not covering
other versions or OSes), while `codex`, `gemini` and `grok` stay
`contract-tested` (their CLIs were not available to verify against). No
provider is declared above its recorded evidence: see the support matrix and
the evidence record in [docs/providers.md](docs/providers.md). The
report also lists `advertencias` (e.g. `codex: ignora model`) when an adapter
does not forward `model`/`effort`; they never fail the check. The doubles
cover `subprocess.run/Popen/check_output/check_call/call` and `shutil.which`
(also from-imports in the adapter's module), and no synthetic API key set in
the environment may reach the command, `env=` or `input=`.

The test that runs the real `detect()` of `claude` is opt-in: set
`HARMESSI_SMOKE_LOCAL=1` (and have `claude` in PATH), otherwise it is skipped.

#### Source observer conformance (installed in projects)

```python
from tools.datasources import conformance

report = conformance.verificar_observer(
    my_factory,                       # factory(source_id, options)
    source_id="my-source",
    options={"path": "data/archivo.csv"},
    request={"source_id": "my-source"},
    evidencia="real",                 # "fixture" or "real": declared by you
    options_error={"path": "data/no_existe.csv"},  # optional: must make the observer fail
)
print(report.to_json())               # report.ok is the global verdict
```

It validates shape, capabilities, `SourceObservation` parsing, no invented
facets, rejection of invalid `source_id` and errors as bounded exceptions
(`SourceError`, `RuntimeError`, `ValueError`, `FileNotFoundError`,
`OSError`; a `KeyError`/`TypeError`/... fails and names the type), no secrets
or absolute paths, reproducible `content_sha256`, and no installers or process
launchers (static AST check over the factory's file: `subprocess`/`pip`/`uv`/
`poetry`/`setuptools`/`runpy`/`ctypes` imports at any level except under
`TYPE_CHECKING`, `__import__`/`import_module` of them, `os.system/popen/
spawn*/exec*`; not exhaustive, sibling modules are not followed). If
`options_error` is not given, the `error_acotado` check is not evaluated and
the report is `ok=False`, `completo=False` unless you pass
`permitir_no_evaluados=True`. Heuristic, not a security guarantee.

### `harmessi routing`

```
python -m tools.harmessi routing show|resolve --role <r> [--task-type <t>] [--policy <path>] [--check-availability] [--json]
```

Declarative, deterministic resolution of provider/model/effort by role +
task type from an optional policy file (default `.harmessi/routing.json`;
its absence means no policy declared, never an inferred one). `show` prints
the loaded policy (or says explicitly that none is declared); `resolve`
returns a `RoutingDecision` for a given `--role`/`--task-type`, optionally
checking real availability via `tools.providers.list_providers()` with
`--check-availability`. Routing never infers or optimizes automatically —
`provider_available` is informational only, it never changes the resolved
`provider_id`.

### `harmessi fallback`

```
python -m tools.harmessi fallback resolve-chain|invoke --role <r> [--task-type <t>] [--policy <path>] [--prompt <p>] [--model <m>] [--effort <e>] [--json]
```

A technical fallback engine: `resolve-chain` reports the candidate provider
chain (`provider_id` + `fallback_chain`) for a role/task and each member's
real availability, without invoking anything; `invoke` actually runs it,
trying the next provider in the chain only when the previous one is
genuinely unavailable (quota, not installed, unreachable) — it never retries
on a semantic error, a code error, or a disagreement of any kind. Each
attempt is recorded as a `HandoffRecord` in the result, including the ones
that failed, so a fallback never hides the original error. Automatic
fallback is enabled only by an `availability_error` of `quota`,
`unavailable` or `unauthenticated`; `ok=False` with no `availability_error`
never triggers it. Routing is declarative, and `provider_available` is
informational only. Provider-neutrality means the 4 adapters implement the same
`ProviderAdapter` contract and pass conformance with doubles; only Claude Code
is validated live. Details and the POST-v1 decision on T2 are in
[docs/providers.md](docs/providers.md).

### `reporting`

```
python -m tools.reporting check-inputs --flow-scope <scope> --input <path> [--input <path> ...] [--repo-root <dir>] [--json]
python -m tools.reporting check-destination --report-id <id> --scope <scope> --report-kind <kind> --out-dir <dir> [--sensitive-artifact <id> ...] [--repo-root <dir>] [--json]
python -m tools.reporting validate --dir <report_dir> [--repo-root <dir>] [--json]
python -m tools.reporting render --dir <report_dir> [--style <json>] [--include-sensitive] [--check] [--repo-root <dir>] [--json]
```

Governed reporting CLI. Only `render` writes, and only `report.html`
(atomically); the other subcommands are read-only. `check-inputs` checks that
a flow does not take its inputs from an exploratory output;
`check-destination` checks that a report destination is safe for its scope (an
exit 0 does not replace the full gate of the Python `publish` API, which has
no CLI subcommand); `validate` runs the full gate over a persisted report
directory; `render` produces a self-contained `report.html` from a validated
directory and refuses (exit 1, nothing written) on any FAIL. With `--check` it
writes nothing and compares the existing file against a fresh render, which
may report a difference if the plotly.js bundle available now differs from
the one used at publish time. Relative paths resolve against `--repo-root`
(default: the current directory). Exit codes: `0` no FAIL, `1` at least one
FAIL, `2` invalid usage, `3` environment error.

### `harmessi-bench`

```
python -m tools.harmessi_bench.cli run (--scenarios <path> | --suite <manifest>) --provider <p> [--model <m>] [--effort <e>] --run-id <id> [--resume] [--seed <n>] [--json]
python -m tools.harmessi_bench.cli suite-check --suite <manifest> [--json]
python -m tools.harmessi_bench.cli compare --baseline <run_id> --candidate <run_id> [--json]
```

A separate CLI, not a subcommand of `harmessi` — invoked as
`python -m tools.harmessi_bench.cli`, with no `__main__.py` of its own.
An evals framework, deliberately kept apart from the deterministic unit test
suites: `run` executes a set of reproducible scenarios against a real
provider (via the same `tools/providers` adapters) and scores each one with
a deterministic scorer (`contains`/`regex`/`exact` — no LLM-as-judge),
saving the result to `.harmessi/evals/<run_id>/result.json`; `compare`
diffs two saved runs and reports regressions/improvements. Scoring is a
surface-level text proxy, not a measure of semantic quality.

The framework is a versioned evaluation foundation:

- `--suite <manifest>` runs a versioned suite (`suite_id`, `suite_version`,
  content `suite_hash` computed by the code) instead of a loose
  `--scenarios` file; exactly one of the two is required. `suite-check`
  validates a manifest (exit 0 valid, 1 invalid). A public synthetic suite
  ships at `tools/harmessi_bench/suites/harmessi-core-synthetic.suite.json`.
- `result.json` carries `schema_version`, `evaluator_version` and the
  `suite` block; older files without them are still read.
- `compare` prints a verdict: `candidate_better`, `baseline_better`,
  `equivalent` or `inconclusive`. It uses only the deterministic
  `score.passed`, and falls back to `inconclusive` when in doubt: different
  scenario sets, a provider outage (`availability_error`), a different suite
  or `evaluator_version`, or regressions and improvements at once.
- Evals are not tests: the unit tests prove deterministic correctness, the
  evals observe behavior; a verdict is evidence, not a promotion. A case may
  declare `surface_under_test` only for Optimizable surfaces; Protected and
  project-owned paths are rejected, and nothing here writes or promotes harness
  surfaces. It runs from a Harmessi checkout only (not part of the installed
  manifest). No LLM-as-judge and no leaderboard.
- Reproducible runs: every `run` stores a `run_manifest` in
  `result.json` (harness version, Git commit or `unknown`, skill/surface
  hashes, provider/model/effort, evaluator, suite, `identity_hash`; ids and
  hashes only, no environment, hostname, user or absolute paths).
  `--resume` completes an existing run by running only the scenarios without
  an `ok` result, and refuses (exit 1, nothing modified) if the configuration
  differs materially; an existing `run_id` with a manifest needs `--resume`
  or a new id. `--seed <n>` is recorded as informational only (the provider
  may ignore it). Persisted excerpts are redacted best-effort (user paths,
  emails, common tokens): this reduces accidental leaks, it is not a
  guarantee. `compare` adds `config_diff`. Configuration reproducibility is
  not bit-for-bit reproducibility: the model output stays stochastic.

## Platform and CI status

Everything under `tools/` (the installer, `doctor`, `dsguard`, `nbrunner` and both
`PreToolUse` hook launchers) is pure Python, invoked as `python -m tools....` or via
the Python interpreter directly; no step depends on `bash`, PowerShell or any other
shell. `subprocess` is always called with an argument list (never `shell=True`), and
the two hook launchers resolve the project's `.venv` interpreter with the layout of the
host OS (`Scripts/python.exe` on Windows, `bin/python` on Linux/macOS), honor a custom
`venv_dir` from `control.json`, and support Git worktrees. Run
`python -m tools.harmessi doctor` on an installed project to verify this end to end.

Evidence for v1:

- The public v1.0.0 commit is `5f4a0ca`.
- The `portability-smoke` workflow (`.github/workflows/portability-smoke.yml`) was
  observed GREEN on the push to `main` and on the `v1.0.0` tag, on Ubuntu, Windows and
  macOS, with Python 3.12.
- That workflow runs a bounded list of tests (portability, contract and conformance
  checks). It is **not** the full test suite on every platform; the full suite has been
  executed on Windows.
- Python 3.9 remains the declared minimum but is not executed.

See [docs/portability.md](docs/portability.md) for the platform audit.

## Contracts, versioning and deprecation

`docs/contracts/inventory.json` (human view: `docs/contracts/README.md`) is an
inventory of the CLIs, schemas and other contracts a third party could consume,
classified as stable / public-candidate / internal / experimental. Six contracts
are `stable` from 1.0.0 (the `ds_guard`, `ds_init` and `harmessi` CLIs and the
SourceObservation, source registry and eval result schemas); the stability promise
covers only those. Everything else is experimental or internal, falls outside the
promise and may change in a minor release. See also
[docs/versioning.md](docs/versioning.md) (how 0.x and 1.x are read, and the
compatibility window) and [docs/deprecation.md](docs/deprecation.md) (deprecation
convention).

## Documentation

- [Installation](docs/installation.md)
- [Concepts](docs/concepts.md)
- [CLI reference](docs/cli-reference.md)
- [Providers](docs/providers.md)
- [Security and trust](docs/security-and-trust.md)
- [Evaluation](docs/evaluation.md)
- [Production lifecycle](docs/production-lifecycle.md)
- [Portability](docs/portability.md)
- [Versioning](docs/versioning.md) and [Deprecation](docs/deprecation.md)
- [Release process](docs/release-process.md)
- [Roadmaps](docs/roadmap/README.md)

### Release notes

| Release | Notes |
|---|---|
| v1.0.0 — first stable release | [docs/releases/v1.0.0.md](docs/releases/v1.0.0.md) |
| v0.15.0 — pre-v1.0 consolidation | [docs/releases/v0.15.0.md](docs/releases/v0.15.0.md) |
| v0.14.0 — Evidence-Driven Harness Improvement | [docs/releases/v0.14.0.md](docs/releases/v0.14.0.md) |
| v0.13.0 — portability, evaluation and contract hardening | [docs/releases/v0.13.0.md](docs/releases/v0.13.0.md) |
| v0.12.0 — data scientist experience and composable skills | [docs/releases/v0.12.0.md](docs/releases/v0.12.0.md) |
| v0.11.0 — operational robustness and recovery | [docs/releases/v0.11.0.md](docs/releases/v0.11.0.md) |
| v0.10.0 — integration and stabilization | [docs/releases/v0.10.0.md](docs/releases/v0.10.0.md) |
| v0.9.0 — Data Cards, Model Cards and Model Governance | [docs/releases/v0.9.0.md](docs/releases/v0.9.0.md) |

## Development

```bash
python -m unittest discover -s tools/ds_init/tests -p "test_*.py"
python -m unittest discover -s tools/harmessi/tests -p "test_*.py"
python -m unittest discover -s tools/tests -p "test_*.py"
python -m unittest discover -s tools/ds_profile/tests -p "test_*.py"
python -m tools.ds_init.check_manifest_parity   # dev-only, read-only drift check
```

## License

Harmessi v1.0+ is **source available**, not OSI open source, under the
[PolyForm Shield License 1.0.0](LICENSE). Internal use, including inside a company,
is permitted. Offering a product or service that competes with Harmessi requires a
separate commercial license. See [LICENSE](LICENSE), [NOTICE](NOTICE) and
[COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md). Installations made by `ds_init`
include `HARMESSI-LICENSE.txt`, which carries the license terms and notice of the
Harmessi components; it does not relicense your project.

Historical note: versions v0.x were published under Apache License 2.0.
