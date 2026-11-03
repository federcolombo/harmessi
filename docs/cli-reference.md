# Referencia de CLIs

Referencia de los CLIs publicos de Harmessi, derivada del `argparse` real. Para el
detalle de cada flag, usar `--help` del subcomando. El contexto y los limites estan
en el `README.md`.

## `ds_guard`

```
python -m tools.ds_guard <subcomando> [subcomando] [opciones]
```

Verificador determinista de SDD, madurez, lifecycle y MLOps. Se instala en los
proyectos (`tools/ds_guard.py`).

### Subcomandos de nivel superior

| Subcomando | Descripcion (del help del parser) |
|---|---|
| `init` | Crea el scaffolding de un cambio nuevo desde las plantillas versionadas. |
| `status` | Con `--change-id`: estado del cambio SDD (informativo). Sin `--change-id`: status unificado de proyecto, de solo lectura. |
| `validate` | Corre chequeos deterministas sobre el cambio. |
| `approve` | Registra la aprobacion (hash) de uno o mas artefactos. |
| `transition` | Aplica una transicion de estado SDD. |
| `session` | Gestion de sesiones de trabajo (`start`, `note`, `status`, `close`, `aggregate`, `efficiency`). |
| `notebook-diff` | Diff por celdas de uno o mas `.ipynb` contra una revision de git. Nunca ejecuta. |
| `kdd` | Lifecycle KDD del proyecto (`openspec/kdd/state.json`): `init`, `status`, `transition`. |
| `lifecycle` | Lifecycle metodologico neutral del proyecto (`openspec/lifecycle/state.json`): `migrate`. |
| `project` | Estado de madurez/gobernanza del proyecto (`.harmessi/project.json`): `init`, `calibrate`, `set-risk`, `status`, `readiness`, `promote`. |
| `mlops` | Fundamentos MLOps del proyecto: `status`, `record`, `evidence add`. |
| `science` | Scientific validity checks (cutoff/holdout/leakage/baseline), solo lectura: `status`. |
| `efficiency` | Reporte de eficiencia de agentes por Change (solo lectura): `report`. |
| `impact` | Impact Preflight estatico (`tools/dsimpact`), solo lectura: `scan`. |
| `contract` | Contratos de datos (`tools/datacontracts`): `validate`, `diff`, `impact`, solo lectura. |
| `exec` | Runtime de ejecucion del Lead (`tools/leadrun`): `script`, `pytest`, `notebook`, `approve`. |
| `dependency` | Clasificacion e instalacion gobernada aditiva de dependencias del proyecto pre-aprobadas: `classify`, `install`. |
| `output-roots` | Output roots declarados para que codigo del proyecto los consulte (control cooperativo, no sandbox): `list`. |
| `source` | Fuentes de datos neutrales (`tools/datasources`): `list`, `check`, `observe`, `check-stale`. |
| `quality` | Calidad de modelo y evidencia (`tools/modelquality`, `tools/qualityevidence`): `evaluate`, `evidence show`, `drift`. |
| `cards` | Cards de governance (Data Card, Model Card, assessment): `validate`, `report`. |
| `archive` | Archiva un cambio cerrado de `openspec/changes/` a `openspec/archive/` (git mv). |
| `remediation` | Bounded remediation (`control['remediaciones']`): `resolve`, `extend`. |
| `decision` | Decision ledger del proyecto (`openspec/decisions/ledger.jsonl`): `add`, `supersede`, `revoke`, `correct`, `verify`, `list`, `show`. |
| `scope` | Scope autorizado de un Change: consulta y enmiendas gobernadas: `show`, `amend`. |
| `glossary` | `GLOSSARY.md` del dominio (solo lectura): `check`, `hash`. |
| `ownership` | Ownership de writers de un Change (solo lectura): `check`. |
| `guardrails` | Re-adopcion gobernada de guardrails (closed list aditiva): `readopt`. |

### `ds_guard scope`

- `scope amend`: la accion mostrada en la confirmacion T1 es compacta (`scope-amend: <op> +N -M hash=<12>`) cuando la lista completa supera 120 caracteres; la lista exacta se ve con `--dry-run`. Detalle en `ARCHITECTURE.md` §12.3.
- `scope attest-protected --change-id <id> --path <ruta> --motivo <texto> --usuario <nombre> [--fecha <AAAA-MM-DD>] [--dry-run]`: atesta con confirmacion T1 `console_confirmed` el contenido actual de una ruta Protected atestable, en `protected-attestations.jsonl` del Change. No modifica el archivo ni exime de Protected. Detalle en `ARCHITECTURE.md` §12.2.

### Codigos de salida generales

Segun el docstring de `tools/ds_guard.py`:

| Codigo | Significado |
|---|---|
| 0 | Correcto. |
| 1 | Gate/validacion incumplida (incluye `SESION-AUSENTE`). |
| 2 | Error de uso/configuracion. |
| 3 | Error de entorno/git/herramienta (p. ej. `impact scan` sin `tools/dsimpact/` en una instalacion `discovery`). |

Algunos subcomandos informativos (p. ej. `status` sin `--change-id`) devuelven 0
siempre; ver el help de cada uno.

## Otros CLIs

Se ejecutan desde un checkout de Harmessi (no se instalan en el proyecto), salvo
`ds_profile`, cuya disponibilidad depende del stage; ver el `README.md`.

| Comando | Para que sirve |
|---|---|
| `python -m tools.harmessi doctor [--destino DESTINO]` | Diagnostico de solo lectura de un proyecto instalado. Sale 0 sin `[ERROR]`, 1 en caso contrario. Ver [installation.md](installation.md). |
| `python -m tools.ds_profile run --input INPUT --output OUTPUT [--profile-id ID] [--max-filas-exactas N] [--max-mb-exactos N] [--top-n N] [--seed N] [--markdown]` | Perfilado determinista de un CSV o Parquet (`--max-mb-exactos`: presupuesto de memoria en MiB; si se supera se perfila una muestra determinista); escribe `.harmessi/profiles/<profile_id>/profile.json`. Parquet requiere `pyarrow` (sin el: exit 3). |
| `python -m tools.ds_init [install\|sync\|migrate-hashes\|upgrade\|recover] --destino DESTINO [--nombre N] [--notebooks-dir D] [--venv-dir D] [--integrar-claude] [--stage S] [--disable-capability C] [--enable-capability C] [--forzar] [--dry-run \| --execute]` | Instalador/sincronizador. `--dry-run` es el defecto. `--disable-capability` / `--enable-capability` (repetibles, `install` y `sync`) deshabilitan o habilitan capabilities; las opt-in (`data_cards`, `model_governance`, esta última requiere `predictive_modeling`) están deshabilitadas por default y deshabilitar nunca borra archivos ya instalados. `--forzar` (solo `recover`) revierte aunque un archivo se haya editado tras la interrupción y conserva la copia actual como `<ruta>.recover-bak`; `recover` sale 2 si el journal es ilegible o falta un backup. |
| `python -m tools.harmessi providers list [--json]` | Deteccion de los 4 adapters de provider. |
| `python -m tools.providers.conformance [--provider ID] [--smoke] [--live] [--json]` | Conformance de adapters contra test doubles. Exit 0 si todos alcanzan al menos `contract-tested`, 1 si no, 2 si se usa `--live` sin `HARMESSI_LIVE_PROVIDER=1`. Ver `docs/providers.md`. |
| `python -m tools.harmessi routing show\|resolve --role R [--task-type T] [--policy P] [--check-availability] [--json]` | Resolucion declarativa de provider/modelo/effort. |
| `python -m tools.harmessi fallback resolve-chain\|invoke --role R [--task-type T] [--policy P] [--prompt P] [--model M] [--effort E] [--json]` | Cadena de fallback tecnico por disponibilidad. |
| `python -m tools.reporting check-inputs \| check-destination \| validate \| render` | Reportes gobernados (ver abajo). |
| `python -m tools.harmessi_bench.cli run \| compare \| suite-check` | Framework de evals (ver abajo). |

### `tools.reporting`

```
python -m tools.reporting [--repo-root REPO_ROOT] [--json] <comando> ...
```

| Comando | Descripcion | Flags principales |
|---|---|---|
| `check-inputs` | Verifica que los inputs de un flujo no provengan de un output exploratorio. | `--flow-scope`, `--input` (repetible) |
| `check-destination` | Verifica que el destino de un reporte sea seguro y coherente con su scope. Un exit 0 no reemplaza el gate completo de `publish`. | `--report-id`, `--scope`, `--report-kind`, `--out-dir`, `--sensitive-artifact` (repetible) |
| `validate` | Valida un directorio de reporte persistido. Solo lectura. | `--dir` |
| `render` | Renderiza `report.html` autocontenido y determinista desde un directorio de reporte validado. Con `--check` no escribe. | `--dir`, `--style`, `--check`, `--include-sensitive` (incluye tablas/figuras sensibles; por defecto se omiten con un placeholder) |

### `harmessi-bench`

Invocado como `python -m tools.harmessi_bench.cli` (no hay `__main__.py`).

| Subcomando | Descripcion | Flags |
|---|---|---|
| `run` | Corre un set de escenarios contra un target. | `--scenarios <path>` o `--suite <manifest>` (exactamente uno), `--provider` (obligatorio), `--model`, `--effort`, `--run-id` (obligatorio), `--resume`, `--seed`, `--json`, `--fail-on-failure` |
| `compare` | Compara dos corridas guardadas. | `--baseline`, `--candidate` (obligatorios), `--json`, `--fail-on-regression` |
| `suite-check` | Valida el manifest de una suite. | `--suite` (obligatorio), `--json` |

- `--fail-on-failure` (en `run`): opt-in; sale con 1 si algun escenario no paso.
  Sin el flag, `run` devuelve 0 aunque haya escenarios fallidos.
- `--fail-on-regression` (en `compare`): opt-in; sale con 1 si el veredicto es
  `baseline_better`. Los veredictos `inconclusive`, `equivalent` y
  `candidate_better` nunca fallan.
- En ambos casos el exit 1 tambien es el codigo de error de uso/guardado, asi que
  un consumidor automatico no distingue fallo de error sin mirar la salida.
- `suite-check` sale 0 si el manifest es valido y 1 si no.
- El resultado de `run` se guarda en `.harmessi/evals/<run_id>/result.json`.
