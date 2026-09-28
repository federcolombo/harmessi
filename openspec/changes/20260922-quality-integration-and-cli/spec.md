# Spec — 20260922-quality-integration-and-cli

## Requisitos

- **R1 — Host único, sin cuarto patrón**: los comandos nuevos viven en `tools/ds_guard.py` (el
  launcher top-level, NO `tools/dsguard/*`, NO `tools/harmessi/cli.py`, NO una CLI de paquete
  nueva `python -m tools.datacontracts.cli`/`python -m tools.modelquality.cli`). Dos subparsers
  nuevos de primer nivel: `contract` y `quality`, agregados a `construir_parser()` con el mismo
  estilo que `impact` (`tools/ds_guard.py:1645-1655`). `python -m tools.ds_guard --help` lista
  ambos junto a `project`/`lifecycle`/`mlops`/`science`/`impact`/etc.

- **R2 — Subcomandos exactos**:
  - `ds_guard.py contract validate --contract <path> --profile <path> [--json]`
  - `ds_guard.py contract diff --old <path> --new <path> [--policy <path>] [--json]`
  - `ds_guard.py contract impact --contract <path> [--since <ref> | --staged] [--fields
    <n1,n2,...>] [--json]` (mutuamente excluyente `--since`/`--staged`, igual que
    `dsimpact scan`; `--fields` opcional, default: todos los `fields[].name` del contrato)
  - `ds_guard.py quality evaluate --policy <path> --metrics <path> [--baselines <path>] [--json]`
  - `ds_guard.py quality evidence show --evidence-id <id> [--json]`
  - `ds_guard.py quality drift --baseline-profile <path> --current-profile <path> --metric <name>
    --field <name> --mode {absolute_diff,relative_diff} [--threshold <float>]
    [--baseline-label <str>] [--current-label <str>] [--json]`
  - Todos los `--json` producen un `dict`/`list` serializable con `json.dumps(..., ensure_ascii=False)`
    (mismo criterio que `providers list --json`, `routing show --json`), nunca un stream NDJSON.

- **R3 — Import perezoso opcional, degradación idéntica a `impact scan`**: cada subcomando
  importa su paquete (`tools.datacontracts`, `tools.modelquality`, `tools.qualityevidence`) DENTRO
  de la función `cmd_*` correspondiente, nunca a nivel de módulo de `tools/ds_guard.py`. Si el
  import falla (paquete no instalado en el stage actual), el comando imprime un mensaje explícito
  a `stderr` (mismo formato que `tools/ds_guard.py:810-814`: "... no está instalado en este stage
  -- correr 'ds_init sync --stage <stage_minimo> --execute'") y devuelve exit code 3. `ds_guard.py`
  nunca reimplementa lógica de validación/evaluación/clasificación: cada `cmd_*` solo parsea
  argumentos, carga JSON de disco (`from_dict`), llama UNA función pública del paquete
  correspondiente, y formatea la salida.

- **R4 — Exit codes coherentes con el resto de `ds_guard.py`**: `0` si el comando corrió sin
  bloqueo funcional (incluye el caso "hay hallazgos `FAIL`/`WARN`" para comandos de solo
  diagnóstico, ver R5); `1` si `checks.hay_bloqueo(resultados)` es verdadero Y el comando es de
  tipo "gate informativo" (mismo criterio que `cmd_project_readiness`,
  `tools/ds_guard.py:1163-1183`: `return checks.exit_code(resultados)`) — aplica a `contract
  validate` y `quality evaluate`, cuyo resultado es una lista de `CheckResult`; `2` error de uso/
  entrada (archivo no encontrado, JSON inválido, `DataContractError`/`ModelQualityError`/
  `QualityEvidenceError` de forma); `3` error de entorno (paquete no instalado en el stage, no
  estar en un repo Git). `contract diff`, `contract impact`, `quality evidence show` y
  `quality drift` son de solo lectura/diagnóstico: exit code `0` siempre que el comando corra sin
  error (nunca `1` por contenido — mismo criterio que `dsimpact scan`, que nunca devuelve `1` por
  "hay findings").

- **R5 — Ningún subcomando escribe fuera de lo explícitamente pedido**: `contract validate` y
  `quality evaluate` aceptan un flag opcional `--record-evidence` que, si está presente, además
  de imprimir el resultado, construye y escribe un `QualityEvidenceManifest` vía
  `tools.qualityevidence.evidence.build_manifest`/`write_manifest` (funciones públicas ya
  existentes, sin modificarlas) bajo `.harmessi/quality/<evidence_id>/manifest.json`; sin ese
  flag, ningún subcomando de este Change escribe nada en disco salvo el propio `--json` a stdout.
  `quality drift` NUNCA escribe evidencia (no existe `--record-evidence` para ese subcomando: no
  hay ninguna función pública de persistencia de `DriftEvidence`, ver `proposal.md` "Supuestos
  descartados").

- **R6 — `tools/datacontracts/evolution.py`**: módulo nuevo, único agregado a un paquete de un
  Change anterior (excepción prevista por Change 0). Importa únicamente `tools.datacontracts.core`
  (sibling), `dsguard.checks` y stdlib (`__future__`, `dataclasses`, `typing`); NO importa
  `ds_profile`, `dsimpact`, `tools.modelquality`, `tools.qualityevidence`, `tools.reporting`,
  pandas ni numpy. Docstrings/comentarios en español, `snake_case`. Define
  `classify_contract_change(old: DataContract, new: DataContract, policy: Optional[CompatibilityPolicy]
  = None) -> list[CheckResult]`, pura (sin I/O), determinista (mismo par de contratos + misma
  política → misma lista, mismo orden).

- **R7 — Categorías exactas y su determinismo**: `classify_contract_change` produce como máximo
  un `CheckResult` por `(categoría, subject)` detectado, código `CONTRACT-EVOLUTION-<CATEGORIA>`
  (`ADDITIVE-COMPATIBLE`, `REMOVAL`, `REQUIRED-FIELD-ADDITION`, `TYPE-CHANGE`,
  `CONSTRAINT-TIGHTENING`, `CONSTRAINT-LOOSENING`, `UNKNOWN-NEEDS-REVIEW`), `subject` = nombre de
  campo o `constraint_id` afectado, `message` describe el cambio en texto (valor viejo → valor
  nuevo). Reglas deterministas (todas verificables solo con la forma de `DataContract`, sin
  ningún conocimiento de dominio):
  - **Campos** (comparados por `name`, presente/ausente en `old.fields`/`new.fields`):
    - nuevo en `new`, `required == False` → `additive compatible`.
    - presente en `old`, ausente en `new` → `removal`.
    - ausente en `old`, presente en `new` con `required == True` → `required-field addition`.
    - presente en ambos con `type_family` distinto → `type change` (aunque también difieran
      `required`/`nullable`: se reporta un único finding `type change` por campo, con el detalle
      de TODAS las dimensiones que cambiaron en el mensaje, para no fragmentar un mismo campo en
      hallazgos redundantes).
    - presente en ambos con mismo `type_family` pero `required` pasa de `False` a `True` →
      `required-field addition` (mismo código que un campo nuevo requerido: el efecto sobre un
      consumidor existente es idéntico — antes podía omitirlo, ahora no).
    - presente en ambos con mismo `type_family`, `required` pasa de `True` a `False`, o
      `nullable` cambia en cualquier dirección → `constraint loosening`/`constraint tightening`
      según corresponda (`nullable: False->True` o `required: True->False` = loosening;
      `nullable: True->False` = tightening), `subject` = nombre del campo.
  - **Constraints** (emparejadas SOLO por `constraint_id` idéntico presente en ambas versiones;
    sin matching heurístico por `field`+`constraint_type` — ver "Alternativas descartadas" de
    `design.md`): si el campo al que pertenece la constraint ya generó un finding de `removal`
    (campo eliminado) o de `additive compatible`/`required-field addition` (campo nuevo), la
    constraint NO genera un finding adicional (ya está cubierta por el finding del campo, evita
    doble reporte). Para constraints sobre campos que persisten en ambas versiones:
    - `constraint_id` solo en `old` → `constraint loosening` (regla eliminada).
    - `constraint_id` solo en `new` → `constraint tightening` (regla nueva).
    - `constraint_id` en ambas con `constraint_type` distinto → `unknown / needs review`
      (redefinición del tipo de regla, no comparable en un eje de tightening/loosening).
    - `constraint_id` en ambas con mismo `constraint_type` en (`min_value`, `min_length`,
      `date_min`): valor sube → `tightening`; baja → `loosening`.
    - mismo `constraint_type` en (`max_value`, `max_length`, `date_max`): valor sube →
      `loosening`; baja → `tightening`.
    - mismo `constraint_type == "allowed_values"`: `new.values` subconjunto propio de
      `old.values` → `tightening`; superconjunto propio → `loosening`; conjuntos distintos sin
      relación de subconjunto → `unknown / needs review`.
    - mismo `constraint_type` en (`not_null`, `unique`): sin parámetros comparables — solo
      `severity` puede cambiar (ver abajo); si nada más cambió, no genera finding (constraint
      idéntica).
    - mismo `constraint_type == "invariant"`: SIEMPRE `unknown / needs review` si `params["note"]`
      difiere (texto libre no parseable), independientemente de si `params["fields"]` cambió.
    - `severity` cambia `WARN -> FAIL` → `tightening`; `FAIL -> WARN` → `loosening` (finding
      propio, separado del de `params`, si `params` también cambió).
  - **Siempre `unknown / needs review`, sin excepción** (nunca inferido por ningún otro camino):
    cualquier `BusinessRule` agregada/eliminada/modificada (declarativas, nunca evaluadas, ver
    `tools/datacontracts/core.py:461-490`); `dataset_role` distinto; `keys` distintas (agregada,
    quitada o reordenada); `compatibility_policy.policy_id` distinto (cambio de política en sí,
    no de contrato).
  - Ningún otro camino produce `PASS`/`FAIL`/`WARN` de una categoría que no esté en esta lista;
    cualquier combinación no cubierta explícitamente arriba cae en `unknown / needs review`.

- **R8 — Mapeo de `status` vía `CompatibilityPolicy`**: si `policy is None`, TODOS los
  `CheckResult` de `classify_contract_change` tienen `status = "N/A"` (clasificado, no evaluado
  contra ninguna política — nunca un `PASS` inventado). Si `policy` está presente, el `status` de
  cada finding se calcula mapeando `COMPAT_ACTIONS` del campo `on_<categoria>` correspondiente
  (`on_removed_field`, `on_required_field_added`, `on_type_change`, `on_constraint_tightening`,
  `on_constraint_loosening`, `on_unknown_change`; `additive compatible` no tiene campo de
  política propio — SIEMPRE `PASS` si hay política, `N/A` si no, nunca bloquea): `"block" ->
  STATUS_FAIL`, `"warn" -> STATUS_WARN`, `"allow" -> STATUS_PASS`. Una excepción inesperada al
  clasificar un finding puntual produce `CheckResult(STATUS_FAIL, "CONTRACT-EVOLUTION-EXCEPCION",
  ..., kind=KIND_TECHNICAL_ERROR)` para ESE finding, sin abortar el resto (mismo patrón que
  `checks.ejecutar_checks`).

- **R9 — `contract diff` (CLI)**: carga `--old`/`--new` con `DataContract.from_dict(json.load(...))`
  y, si `--policy` está presente, `CompatibilityPolicy.from_dict(...)`; llama
  `classify_contract_change`; imprime cada finding (`status`, `code`, `subject`, `message`) y un
  resumen de conteo por categoría. `--old`/`--new` con `contract_id` distinto es válido (compara
  estructura, no identidad) pero el mensaje de resumen lo advierte explícitamente (nunca oculta
  que se están comparando contratos con `contract_id` distinto).

- **R10 — `contract impact` (CLI, composición de `dsimpact`)**: carga `--contract` con
  `DataContract.from_dict`; construye `targets = {contract.contract_id} | (campos pedidos por
  `--fields`, o todos los `field.name` de `contract.fields` si `--fields` está ausente)`; obtiene
  `candidatos = dsimpact.git_source.listar_consumidores_candidatos(repo_root)`; para cada
  candidato (excluyendo el propio `--contract` si coincide en path), según extensión, llama
  `dsimpact.consumers_py.buscar_en_texto_python(texto, set(), targets)` (`.py`/celdas de
  `.ipynb`, targets como strings, nunca como símbolos — un `contract_id`/nombre de campo se
  referencia como literal, no como identificador Python declarado), `dsimpact.consumers_text.
  buscar_en_json(texto, targets)` (`.json`) o `dsimpact.consumers_text.buscar_en_texto_plano(texto,
  targets)` (`.yaml`/`.yml`/`.toml`/`.md`). Ningún archivo se lee con `git show`: siempre el
  filesystem actual (mismo criterio que `listar_consumidores_candidatos`, no hay noción de "antes/
  después" en este subcomando porque no hay diff de Git involucrado — `--since`/`--staged` NO se
  usan para extraer targets, solo quedan reservados para un futuro Change que sí compare dos
  versiones de contrato vía Git; en ESTE Change son aceptados por el parser pero no tienen efecto
  observable, documentado explícitamente en el `--help`). Vocabulario de salida: `"potentially
  affected consumers"`, análogo textual a `tools/dsimpact/cli.py:65-103` (`formatear_texto`),
  NUNCA "broken"/"roto". `evidence_type` de cada hallazgo es siempre `"CONTRACT_REFERENCE"` (sin
  la escalada de 3 pasos de `dsimpact._evidence_type`, que es específica de diffs de código —
  ver `design.md`, decisión 5).

- **R11 — `quality evaluate` (CLI)**: carga `--policy` con `ModelQualityPolicy.from_dict`,
  `--metrics` con una lista de `ObservedMetric.from_dict` (el JSON de entrada es una lista de
  objetos, uno por métrica observada), `--baselines` (opcional) con una lista de
  `BaselineReference.from_dict`; llama `tools.modelquality.validation.evaluate_policy(policy,
  observed_metrics, baselines)`; imprime cada `CheckResult` y el peor status agregado.

- **R12 — `contract validate` (CLI)**: carga `--contract` con `DataContract.from_dict`; llama
  `tools.datacontracts.validation.validate_contract_against_profile_file(contract, Path(args.profile),
  repo_root)` (firma real, `tools/datacontracts/validation.py:848`); imprime cada `CheckResult` y
  el peor status agregado.

- **R13 — `quality evidence show` (CLI)**: llama `tools.qualityevidence.evidence.read_manifest(
  repo_root, args.evidence_id)`; imprime el manifest (campos principales en texto: `evidence_id`,
  `subject_kind`, `declaration`, `generated_at`, conteo de `check_results` por status +
  `technical_errors` por separado — decisión 4 del roadmap, nunca mezclados en el mismo conteo) o
  el `dict` completo con `--json`. Un `evidence_id` inexistente o un manifest con hash
  inconsistente produce exit code 2 con el mensaje de `QualityEvidenceError` tal cual (nunca lo
  reinterpreta).

- **R14 — `quality drift` (CLI)**: llama `tools.qualityevidence.evidence.drift_from_profiles`
  (firma real, `tools/qualityevidence/evidence.py:467-479`) con los paths/labels/mode/threshold
  dados; imprime el `DriftEvidence` resultante (`metric_name`, `baseline_value`, `current_value`,
  `observed_difference`, `result_status`, `result_message`). Sin `--threshold`, `result_status`
  es SIEMPRE `"N/A"` (propiedad ya garantizada por `build_drift_evidence`, este Change no la
  reimplementa ni la contradice). No escribe ningún archivo (R5).

- **R15 — Extensión aditiva de `ds_guard.py status` (unificado, sin `--change-id`)**: dentro de
  `cmd_status_unificado` (`tools/ds_guard.py:94-111`), DESPUÉS de obtener
  `resultado = status.evaluar_status(repo_root)` sin modificarlo, se calcula localmente (función
  nueva `_resumen_quality_evidence(repo_root) -> dict`, definida en `tools/ds_guard.py`, import
  perezoso de `tools.qualityevidence.evidence` dentro de esa función) un resumen de solo lectura:
  lista los directorios bajo `.harmessi/quality/` (si existe; si no, `{"disponible": False,
  "mensaje": "sin evidencia de calidad todavía"}`), para cada uno intenta `read_manifest`
  (verificación de hash incluida) y agrega conteos por `status` (`PASS`/`WARN`/`FAIL`/`N/A`) y un
  conteo SEPARADO de `technical_errors` (decisión 4 del roadmap: nunca contaminar el conteo de
  calidad), más `generated_at` de la evidencia más reciente. Un manifest corrupto/con hash
  inconsistente se reporta como entrada individual `{"evidence_id": ..., "valido": False, "motivo":
  str(exc)}`, nunca aborta el resumen completo. Este resumen se agrega como clave NUEVA
  `"quality_evidence"` al `dict` antes de imprimir (`--json`) o como sección nueva AL FINAL del
  texto (nunca insertada entre secciones existentes, nunca modifica ninguna clave/línea
  preexistente). Si `tools.qualityevidence` no está instalado en el stage actual, el resumen es
  `{"disponible": False, "mensaje": "tools.qualityevidence no disponible en este stage"}` (nunca
  una excepción cruda, mismo criterio que `_seccion_harness` de `status.py:417-441`, replicado
  acá SIN importar ese módulo). Exit code de `status` (unificado) permanece `0` en todos los
  casos, exactamente igual que antes de este Change (ver R16).

- **R16 — No alteración de `tools/dsguard/status.py`**: `tools/dsguard/status.py` no tiene NINGÚN
  diff en este Change (verificado en `verification.md` con `git diff --stat`, y por la ausencia
  de esa ruta en `tasks.md` "Alcance de rutas autorizadas"). `evaluar_status(repo_root)` devuelve,
  con y sin `.harmessi/quality/` presente en el filesystem, un `dict` IDÉNTICO (mismas 8 claves,
  mismo contenido) — se prueba con un test directo a esa función (sin pasar por `ds_guard.py`).

- **R17 — No alteración de `project readiness`/`project promote`**: `tools/dsguard/readiness.py`
  no tiene ningún diff en este Change; `cmd_project_readiness`/`cmd_project_promote` de
  `tools/ds_guard.py` tampoco. Se prueba, en un proyecto de prueba sintético con
  `.harmessi/project.json`/lifecycle inicializados: `ds_guard.py project readiness --target
  <t> [--json]` produce stdout + exit code IDÉNTICOS con y sin `.harmessi/quality/**/
  manifest.json` presente; `ds_guard.py project promote <stage> --reason <r> [--json]` produce
  stdout + exit code + el `.harmessi/project.json` resultante IDÉNTICOS con y sin evidencia de
  calidad presente (ambas corridas parten del mismo estado inicial, en directorios de prueba
  separados, para que "promote" no mute el fixture compartido).

- **R18 — `technical_error` separado en toda superficie nueva**: cualquier resumen/conteo
  agregado por este Change (R7/R15) reporta `technical_error` en un campo separado del conteo de
  calidad (`PASS`/`WARN`/`FAIL`/`N/A`), nunca sumado ni mezclado — mismo principio que decisión 4
  del roadmap, ya aplicado por `status._seccion_readiness` (`status.py:391` — `technical_error`
  separado de `blocking`).

- **R19 — Registro único de códigos**: `CONTRACT-EVOLUTION-*` se define UNA sola vez, como
  constantes de módulo en `tools/datacontracts/evolution.py` (p. ej. `CODE_ADDITIVE_COMPATIBLE =
  "CONTRACT-EVOLUTION-ADDITIVE-COMPATIBLE"`, etc.); `tools/ds_guard.py` nunca redeclara esos
  strings como literales — los importa o los recibe ya puestos en `CheckResult.code`. Ningún
  código nuevo de este Change duplica un código ya usado por `CONTRACT-*` (Change 1) o
  `QUALITY-*` (Change 2).

- **R20 — Privacidad**: ningún mensaje impreso por los 6 subcomandos nuevos ni por la extensión
  de `status` reproduce una ruta absoluta local (mismo criterio que Change 3, ya garantizado por
  las funciones que este Change invoca sin modificar — `validate_contract_against_profile_file`,
  `drift_from_profiles`, `read_manifest`); rutas mostradas son siempre repo-relativas.

- **R21 — Tests de neutralidad**: `tools/tests/test_v07_evolution_neutrality.py` (R6, patrón
  `ast`) y el smoke `tools/tests/test_ds_guard_contract_quality_cli.py` (R2-R14, invoca
  `ds_guard.construir_parser()`/`main()` con `argv` sintéticos, fixtures de contrato/política/
  perfil/manifest 100% sintéticos en `tempfile`, nunca datos reales) son parte obligatoria del
  cierre de este Change, junto con `test_v07_readiness_promote_status_no_alteration.py` (R16-R17).
