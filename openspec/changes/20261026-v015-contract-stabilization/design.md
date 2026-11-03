# Diseño — 20261026-v015-contract-stabilization

## Decisión metodológica/técnica

### D1 — Ventana de compat pre-v1
Versión actual + 2 menores previas (0.15, 0.14, 0.13), limitada a artefactos con test. v0.11 y v0.12
salen de la promesa; sus tests existentes se conservan como best-effort, documentado. Los contratos
improve nacieron en 0.14: su ventana es 0.14-0.15.

### D2 — Contratos improve
Lector estricto fail-closed; sin migración mientras `contract_version == 1`. Regla futura: un bump de
`contract_version` exige que el lector lea la versión anterior dentro de la ventana y un fixture del
tag que la produjo. Política por caso: campo desconocido -> rechazo; versión no soportada o futura ->
rechazo con excepción propia; ausencia de versión -> rechazo. Se documenta en una tabla por contrato
(versión, lector, unknown-field, versión no soportada, migración, ventana). `budget_version` y
`policy_version` son campos aparte con versión 1.

Matriz de comportamiento de los demás contratos (documentada, sin cambio de código salvo D4):
result.json (ausente = 0 legado, 0/1 legibles, futura -> ValueError, desconocidos aceptados);
eval case (0/1, ignora desconocidos); eval suite (claves exactas, versión 1); run manifest (D4).

### D3 — Fixtures reales de v0.14.0
`tools/tests/fixtures/compat/generate_v014.py`, solo-checkout: dado un directorio con el árbol de
`git archive v0.14.0`, ejecuta el flujo con `crear_repo` (`tools/harmessi_improve/tests/_helpers.py`)
y `FakeAdapter` (`_fakes.py`) parcheando `tools.harmessi_improve.cli._resolver_adapter`: candidate
create -> probe -> decide --apply -> promote propose -> lesson add, y copia los artefactos a
`tools/tests/fixtures/compat/v0_14/`. El test v0.15 los lee con los lectores actuales y, si el tag
existe, regenera y compara estructura (skip si no). Los fixtures no se editan a mano. Se necesita el
árbol del tag (no el actual) porque los hashes internos atan contenido y deben provenir del código
que produjo el artefacto.

### D4 — Validación de `manifest_version`
En `runmanifest.py`, `evaluar_compatibilidad` rechaza `manifest_version` futura, no entera o bool con
razón explícita. Aditivo; `MANIFEST_VERSION` no cambia.

### D5 — Baseline `.ds_init/control.json`
No se agrega `schema_version`. Se versiona por `harness_version` + `hash_alg` por entrada. Se
documenta en `inventory.notas`, `versioning.md` y `contracts/README.md`. Fixtures de baseline v0_13 y
v0_14 con `git show <tag>:.ds_init/control.json`; test de lectura/migración con los lectores
actuales. El baseline real del repo no se modifica (C7).

### D6 — Exit codes y flags
Las CLIs `public-candidate` (cli-ds-guard, cli-ds-init, cli-harmessi) pasan a "candidatos
garantizados": 0/1/2(/3) documentados como contrato en inventory y `versioning.md`; cambiar el
significado es incompatible. `harmessi_bench compare`: 0 = comparación realizada (veredicto en la
salida); se agrega `--fail-on-regression` opt-in (exit 1 si el veredicto es `baseline_better` o la
condición de regresión que ya defina el código existente; sin cambio del default) con tests y
documentación.

### D7 — Deprecación
`Deprecation` gana `guia` (no vacía). Nombres documentados: deprecated_since=`desde`,
replacement=`reemplazo`, earliest_removal=`remocion_minima`, migration guidance=`guia`. El mensaje de
`advertir` incluye la guía; `validar_registro` valida `guia`; test que cruza nombres del registro con
inventory (pasa con registro vacío). `docs/deprecation.md`: ejemplo trabajado y visibilidad (stderr,
notas de release). El registro sigue vacío.

### D8 — SemVer, promoción e inventory
`versioning.md`: patch/minor/major en 1.x por tipo de contrato (CLI comando/flag/exit code, schema
persistido, SourceObservation/adapter, skills frontmatter, Cards, contratos improve, inventory);
definición de "cambio incompatible"; promoción experimental -> public-candidate -> stable (ventana +
fixtures reales + test de lector + ancla); `contract_version` y `schema_version` como nomenclatura
equivalente. `inventory.json`: campo opcional `compat` por entrada con schema {lector,
campos_desconocidos, version_no_soportada, migracion, ventana} para los 7 improve + run-manifest +
eval-case + eval-suite + 3 schemas public-candidate + schema-ds-init-baseline; test que lo exige en
esas entradas; sin cambiar `inventory_version` (los smokes pinean ==1; solo campos opcionales).

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica (sin datos ni modelado).

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
Sin aleatoriedad. Los fixtures dependen del tag local `v0.14.0`; el script generador es
determinista salvo campos volátiles (timestamps, paths temporales), por lo que la comparación contra
el tag es estructural. Los fixtures committeados son la fuente de verdad para los tests en CI.

## Alternativas descartadas
- Subir `inventory_version` a 2: rompe los pins `==1` de los smokes v0.13/v0.14.
- Agregar `schema_version` al baseline: toca manifest de ds_init, Doctor y baseline; es de C7.
- Fixtures de improve escritos a mano: invalidados por los hashes internos.
- Migración preventiva de improve: no hay versión 2; sería código muerto sin test real.
- Cambiar el default de `compare` a exit 1 con regresión: rompe tests y consumidores; se usa flag
  opt-in.
- Ventana desde v0.11: sin artefactos con test fiable; promesa no sostenible.

## Riesgos
- Los fixtures dependen del tag local `v0.14.0`: si falta, la regeneración se saltea (skip con razón)
  pero los fixtures committeados siguen vigentes. Mitigación: documentar en el generador cómo
  recrear el árbol (`git archive`).
- Windows: rutas, separadores de línea (`\r\n` vs `\n`) y extracción de `git archive` pueden alterar
  bytes/hashes; el generador debe escribir con newline controlado y los tests comparar estructura,
  no bytes. `git show` en Windows puede aplicar conversión de EOL: leer como bytes.
- El generador solo se puede ejecutar en un checkout con el tag; el Writer no ejecuta nada, de modo
  que la generación y los tests los corre el Lead. Los fixtures v0_14 quedan pendientes hasta esa
  corrida.
- `--fail-on-regression` define "regresión" según la lógica existente: si es ambigua se devuelve al
  Lead, no se inventa.
- Falsa sensación de garantía: la ventana cubre solo artefactos con test; se declara en la doc.
- Los pins de smokes v0.13/v0.14 y el test de inventory pueden necesitar ajustes mínimos (por eso
  están en el alcance); no se relajan aserciones.

## Plan de pruebas
Nuevos:
- `tools/tests/test_v015_compat_window.py`: anclaje de ventana en doc, lectura de fixtures v0_13
  (baseline) y v0_14 (improve + baseline), regeneración estructural vs tag (skip si falta), rechazo
  de unknown-field/clave ausente/versión no soportada/ausente por lector, constantes de versión
  (R10).
Afectados:
- `tools/harmessi/tests/test_deprecation.py` (guia, mensaje, cruce con inventory, registro vacío).
- `tools/harmessi_bench/tests/test_runmanifest.py` (manifest_version) y
  `tools/harmessi_bench/tests/test_cli.py` (`--fail-on-regression`, default 0).
- `tools/harmessi_improve/tests/test_cli.py`, `tools/ds_init/tests/test_cli.py`,
  `tools/harmessi/tests/test_cli.py` (exit codes documentados).
- `tools/tests/test_v013_contract_inventory.py` (`compat` exigido), `test_v013_compat_window.py`
  (marcado best-effort), smokes v0.13/v0.14 (solo si el conteo/estructura lo requiere; pin `==1`
  intacto).
No se corre regresión completa en este Change; solo los tests nuevos y afectados listados, corridos
por el Lead.

## Impact preflight
Scope envelope: exactamente las rutas de "Alcance autorizado" de `proposal.md` (docs de versionado,
deprecación y contratos, inventory, roadmap/matriz, fixtures v0_13/v0_14 y generador, tests de compat
v0.13/v0.15, `deprecation.py`, `runmanifest.py` y `cli.py` de bench, tests CLI listados, smokes
v0.13/v0.14 y `ARCHITECTURE.md`).
No se toca: manifest de ds_init, Doctor, baseline `.ds_init/control.json` del repo (sin cambios; se
gestiona en C7), `MANIFEST_VERSION`, `inventory_version`, lectores improve (solo se prueban; sin
cambio de código), `.claude/**`, `tools/ds_guard.py` y `tools/dsguard/**`, ni código de ds_init o
harmessi fuera de `deprecation.py`. Si un test de exit code revela un código no documentado que exija
cambiar código fuera del envelope, se devuelve al Lead.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
