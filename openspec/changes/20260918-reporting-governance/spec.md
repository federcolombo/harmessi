# Spec — 20260918-reporting-governance

## Requisitos

- **R1 — Módulos y restricciones transversales**: se agregan `tools/reporting/governance.py`,
  `tools/reporting/cli.py` y `tools/reporting/__main__.py`. `tools/reporting/core.py` y
  `tools/reporting/__init__.py` (Change 0) NO se modifican. `governance.py` importa: stdlib
  (`json`, `sys`, `dataclasses`, `datetime`, `pathlib`, `typing`, más `__future__`); `dsguard`
  con el mismo patrón que `tools/ds_profile/holdout_guard.py:25-31` (`sys.path.insert(0,
  tools_dir)` + `from dsguard import checks, pathguard, repo as repo_mod, scientific_validity,
  core as dsguard_core`); y `from . import core as reporting_core`. No importa `ds_profile`,
  Plotly, HTML/templating, pandas ni numpy. Transversales a todo lo que exporta `governance.py`:
  (a) **solo lectura**: nunca escribe, crea, mueve ni borra nada en disco; (b) **nunca lanza**:
  ninguna función pública (`evaluate_governance`, `evaluate_destination`, `check_flow_inputs`,
  `output_allowed`) propaga una excepción, ni con contextos mal formados (tipos incorrectos,
  `None`) ni con archivos de configuración corruptos (una excepción inesperada de un check se
  convierte en `checks.resultado_de_excepcion`); (c) **determinista**: el mismo estado de disco
  y el mismo contexto producen los mismos resultados en el mismo orden (única dependencia
  temporal: el vencimiento de excepciones de lectura de `guardrails.json`, evaluado por
  `pathguard` contra el reloj UTC); (d) **no lee contenido de holdouts ni de fuentes de datos**:
  solo evalúa rutas.

- **R2 — Vocabulario único de resultados**: todo resultado es un `dsguard.checks.CheckResult` con
  status en `PASS`/`WARN`/`FAIL`/`N/A` (`checks.py:14-18`); no se crea ningún segundo engine,
  status, ni clase de resultado. Los códigos son exactamente: `REPORT-POLICY`,
  `REPORT-DEST-SAFE`, `REPORT-DEST-SCOPE`, `REPORT-DEST-CROSS-SCOPE`, `REPORT-SENSITIVE-DEST`,
  `REPORT-SOURCE-ACCESS`, `REPORT-HOLDOUT-ACCESS`, `REPORT-HOLDOUT-SOURCE`,
  `REPORT-ISOLATION-INPUT`, `REPORT-SCI-CUTOFF` (más `<codigo_base>-EXCEPCION` cuando
  `checks.ejecutar_checks` captura una excepción inesperada). Los resultados por elemento
  (fuente, input, ruta) llevan ese elemento en `subject`. **Ausencia ≠ PASS**: un dato no
  declarado, desconocido o no verificable nunca produce `PASS`; produce `FAIL`, `WARN` o `N/A`
  según el check, y ningún check devuelve una lista vacía.

- **R3 — Policy opcional `.harmessi/reporting-policy.json`**: archivo opcional, solo lectura,
  `schema_version: 1`. Ausente => defaults deterministas (R4), NUNCA heurística. Campos
  desconocidos (a nivel top-level) se ignoran (forward-compat). Existe pero no es JSON válido, no
  es un objeto, `schema_version` distinta de `1`, `destination_roots` no es objeto,
  `sensitive_destination_roots` no es lista de `str`, un valor de `destination_roots` no es
  `str` no vacío, o una clave de `destination_roots` está fuera de `DECISION_SCOPES` =>
  `ReportingPolicyError` (fail-closed: nunca se recupera con defaults). API pública:
  `ReportingPolicy` (dataclass `frozen=True`: `destination_roots: dict`, `sensitive_destination_roots:
  tuple`, `source: str` con `"default"` o la ruta relativa del archivo),
  `ReportingPolicyError(Exception)`, `load_policy(repo_root) -> ReportingPolicy` (levanta
  `ReportingPolicyError`; es la única función pública de `governance.py` que puede lanzar, y
  ningún check la deja propagar).

- **R4 — Policy: defaults y forma de los roots**: `destination_roots` es un mapa
  `{scope: "<dir relativo>"}`; un scope ausente usa el default `reports/<scope>` para cada uno de
  `exploratory`, `model_valid`, `operational` (override parcial permitido). `sensitive_destination_roots`
  default `[]`. Todo root (de scope o sensible) debe estar en forma canónica estricta, sin
  normalización silenciosa: no vacío; relativo (sin `/` inicial ni letra de unidad/`:`); separador
  `/` (sin `\`); sin segmentos vacíos, `.` ni `..`; sin `/` final; y sin metacaracteres de
  `fnmatch` (`*`, `?`, `[`, `]`), porque de cada root se deriva el patrón `<root>/**` que evalúa
  `dsguard.repo.path_matches_any`. Una violación => `ReportingPolicyError`.

- **R5 — Policy: relaciones entre roots (base del aislamiento)**: los 3 roots de scope
  resultantes (tras aplicar defaults) deben ser distintos y NO anidados entre sí (ninguno es igual
  ni prefijo por segmentos de otro), comparados con `casefold`. Cada `sensitive_destination_root`
  debe ser subdirectorio ESTRICTO de algún root de scope. Una violación => `ReportingPolicyError`.
  El matching de pertenencia de una ruta a un root es `path_matches_any(ruta.casefold(),
  [f"{root.casefold()}/**"])` (case-insensitive, como `pathguard`): una ruta pertenece al root solo
  si es un subdirectorio/archivo ESTRICTO de él (el root mismo NO pertenece; `reports/exploratory-x`
  NO pertenece a `reports/exploratory`).

- **R6 — `resolve_output_dir`**: `resolve_output_dir(policy, decision_scope, report_id) -> str`
  devuelve `"<root>/<report_id>"` con el root del scope (posix, relativo al repo). Levanta
  `ReportingPolicyError` si `decision_scope` no está en `DECISION_SCOPES` o si `report_id` no
  cumple el contrato de ids de `reporting_core` (`reporting_core.es_id_valido`: regex
  `^[a-z0-9][a-z0-9_-]{0,63}$` sin salto de línea final y sin nombres reservados de Windows; ello
  excluye `.`, `con`, `a:b`, `x\n`, `/`, `\` y `..`). No crea nada en disco.
  (Enmienda ciclo 1: `es_id_valido` es una adición pública puramente aditiva a `core.py`, sin
  cambio de comportamiento ni de `content_sha256`.)

- **R7 — Contexto**: `GovernanceContext` es una dataclass `frozen=True` con `repo_root, report_id,
  report_kind, decision_scope, out_dir, sources (tuple[str]), holdout_access, data_cutoff
  (Optional[str]), sensitive_artifacts (tuple[str]), agent_type (Optional[str])` (defaults:
  `sources=()`, `holdout_access=None`, `data_cutoff=None`, `sensitive_artifacts=()`,
  `agent_type=None`); `sources` y `sensitive_artifacts` se normalizan de `list` a `tuple`; no
  valida valores al construir (los valores inválidos los reporta cada check como `FAIL`, no una
  excepción). `context_from_report(repo_root, report, out_dir, *, sources=(), holdout_access=None,
  data_cutoff=None, agent_type=None)` toma `report_id`, `report_kind` y `decision_scope` del
  `Report` de `reporting_core` y arma `sensitive_artifacts` con los ids de las tablas
  (`iter_tables()`) y luego las figuras (`iter_figures()`) con `sensitive=True`, en orden de
  declaración.

- **R8 — `REPORT-POLICY`**: PASS si la policy carga (mensaje indica si es `default` o la ruta del
  archivo); FAIL `kind=technical_error` si `load_policy` levanta `ReportingPolicyError`
  (mensaje con el motivo). Si falla, el agregador (R17) devuelve solo este resultado (fail-closed,
  mismo precedente que `SCI-POLICY`, `scientific_validity.py:532-562`).

- **R9 — `REPORT-DEST-SAFE`**: evalúa con `pathguard.evaluar_tool_call({"tool_name": "Write",
  "tool_input": {"file_path": <ruta>}, "agent_type": ctx.agent_type}, config, repo_root)` — el
  mismo evaluador del hook (secretos, holdouts, `data_raw`, `guardrails.json` protegido,
  `write_scopes`) — las cuatro rutas `<out_dir>/report.html`, `<out_dir>/manifest.json`,
  `<out_dir>/insights.json` y `<out_dir>/artifacts/_` (nombres canónicos de `reporting_core`:
  `REPORT_FILENAME`, `MANIFEST_FILENAME`, `INSIGHTS_FILENAME`, `ARTIFACTS_DIRNAME`). Todas
  permitidas => un PASS. Cada ruta denegada => un FAIL con `subject=<ruta>` y el motivo textual
  de `pathguard`. `out_dir` fuera del repo o no resoluble => FAIL (denegación de `pathguard`).
  `guardrails.json` corrupto (`ConfigGuardrailsError`) => FAIL `kind=technical_error`. Un
  `out_dir` no `str` o vacío => FAIL.

- **R10 — `REPORT-DEST-SCOPE` / `REPORT-DEST-CROSS-SCOPE`**: `out_dir` (resuelto con
  `pathguard.resolver_ruta_relativa`, que sigue symlinks) debe ser subdirectorio ESTRICTO del root
  de su `decision_scope`: PASS `REPORT-DEST-SCOPE`. Si cae bajo el root de OTRO scope => FAIL
  `REPORT-DEST-CROSS-SCOPE` (mensaje: destino de otro scope; vector de leakage exploratorio ↔
  model_valid). Si es igual al root, o cae fuera de todos los roots => FAIL `REPORT-DEST-SCOPE`.
  Un `decision_scope` fuera de `DECISION_SCOPES` => FAIL `REPORT-DEST-SCOPE` (el scope nunca se
  infiere).

- **R11 — `REPORT-SENSITIVE-DEST`**: sin `sensitive_artifacts` => N/A. Con artefactos sensibles,
  `out_dir` debe ser subdirectorio estricto de algún `sensitive_destination_root` => PASS; si no,
  o si la policy no declara ninguno (default `[]`) => FAIL (absence ≠ PASS: el mensaje indica
  declarar `sensitive_destination_roots`).

- **R12 — `REPORT-SOURCE-ACCESS`** (un resultado por fuente): cada fuente de `ctx.sources` se
  evalúa con `pathguard.evaluar_tool_call` con `tool_name="Read"`. Permitida => PASS; denegada
  (secreto, holdout sin excepción de lectura vigente, fuera del repo o no resoluble, fail-closed)
  => FAIL con `subject=<fuente>` y el motivo de `pathguard`. Sin fuentes => un N/A. Fuente no
  `str` o vacía => FAIL. `guardrails.json` corrupto => FAIL `kind=technical_error`.

- **R13 — `REPORT-HOLDOUT-ACCESS`**: `ctx.holdout_access` debe ser exactamente `"none"` o
  `"read"`: `None` o cualquier otro valor => FAIL (no declarado ≠ `"none"`). `"none"` => PASS.
  `"read"` => PASS solo si se cumplen TODAS: `report_kind == "evaluation"`, `decision_scope !=
  "exploratory"` (y ∈ `DECISION_SCOPES`), y la policy científica (leída con
  `scientific_validity.leer_policy`) tiene `holdout.declared is True` y
  `holdout.final_evaluation.authorized is True`; si alguna falla => FAIL indicando cuál. Policy
  científica corrupta (`ScientificPolicyError`) => FAIL `kind=technical_error`. El PASS de `"read"`
  incluye el `reason` declarado en `final_evaluation` si existe.

- **R14 — `REPORT-HOLDOUT-SOURCE`** (un resultado por fuente): una fuente que resuelve dentro del
  repo y matchea `config.holdouts` (matching casefold vía `repo_mod.path_matches_any`, sin réplica
  privada de `pathguard`) es FAIL si `holdout_access != "read"` (contradicción declaración vs
  fuentes) o si `"read"` no está autorizado según R13; con `"read"` autorizado => PASS con nota.
  Una fuente que no matchea ningún holdout => PASS. Una fuente fuera del repo o no resoluble => N/A
  (la denegación ya la reporta R12). Sin fuentes => un N/A. `guardrails.json` corrupto => FAIL
  `kind=technical_error`. Nunca se abre el contenido de la fuente. **Enmienda ciclo 1 (ausencia
  != PASS)**: si `config.holdouts` está vacío (sin protección estructural), una fuente dentro del
  repo NO es PASS: si la policy científica (`leer_policy`) declara `holdout.declared is True` =>
  FAIL (holdout declarado sin protección estructural; mismo criterio que `SCI-HOLDOUT-PROTECTION`);
  si no lo declara => N/A. Policy científica corrupta => FAIL `kind=technical_error`. Con patrones
  presentes, una fuente que no matchea sigue siendo PASS.

- **R15 — `REPORT-ISOLATION-INPUT`**: función pública `check_flow_inputs(repo_root, flow_scope,
  inputs) -> list[CheckResult]`, un resultado por input. `flow_scope == "exploratory"` => N/A (el
  flujo exploratorio puede leer cualquier output). Para `model_valid`/`operational`, un input es
  FAIL si: (a) cae bajo el root exploratory de la policy (R5), o (b) el propio input (si es un
  directorio existente) o algún directorio ancestro suyo dentro del repo, hasta la raíz del repo
  inclusive, contiene un `manifest.json` que sea un manifest de reporte Harmessi (objeto JSON con
  las claves `report_id` y `decision_scope`) con `decision_scope == "exploratory"`. Un
  `manifest.json` ajeno (sin esas claves), ilegible o no JSON se IGNORA (no es evidencia). No se
  abre ningún `manifest.json` cuya lectura `pathguard` deniegue. Input no `str`/vacío, fuera del
  repo o no resoluble => FAIL (fail-closed: no se puede verificar). Sin otro hallazgo => PASS.
  `flow_scope` fuera de `DECISION_SCOPES` => un FAIL. Sin inputs => un N/A. Policy corrupta => un
  FAIL `kind=technical_error` (`REPORT-POLICY`). El chequeo por hash de contenido queda diferido
  al Change 3 (ver `design.md`). **Enmienda ciclo 1**: (a) se amplía a "el input (resuelto) es
  IGUAL, cae BAJO o es ANCESTRO del root exploratory" (incluye `.`/raíz del repo y `reports`),
  con comparación lexical casefold (misma regla que la no-anidación de R5); el input se compara
  contra el root en ambas formas, textual y resuelta con `pathguard.resolver_ruta_relativa`
  (un root que es symlink/junction); (b) un input con metacaracteres de glob `*`, `?`, `[`, `]`
  => FAIL ("no verificable"). La búsqueda hacia ABAJO de manifests exploratorios anidados dentro
  de un input-directorio queda diferida al chequeo por hash del Change 3.

- **R16 — `REPORT-SCI-CUTOFF`**: lee `.harmessi/scientific-policy.json` con
  `scientific_validity.leer_policy`. Sin `temporal.declared is True` => N/A. Con temporal
  declarado pero sin `cutoff_utc` => WARN (mismo criterio que `SCI-CUTOFF`,
  `scientific_validity.py:193-195`); `cutoff_utc` con formato inválido (no `YYYY-MM-DDTHH:MM:SSZ`,
  vía `dsguard_core.parsear_utc`) => FAIL. `ctx.data_cutoff` se acepta como `YYYY-MM-DD` (se
  interpreta como `T00:00:00Z`) o `YYYY-MM-DDTHH:MM:SSZ`; cualquier otro formato => FAIL en todo
  scope. Scopes `model_valid`/`operational`: `data_cutoff` ausente (`None` o vacío) => FAIL;
  `data_cutoff > cutoff_utc` => FAIL; `<=` => PASS. Scope `exploratory`: ausente => WARN;
  `> cutoff_utc` => WARN con mensaje que indica que el output exploratorio cubre datos posteriores
  al cutoff de modelado y NO debe alimentar `model_valid`; `<=` => PASS. Scope inválido => FAIL.
  Policy científica corrupta => FAIL `kind=technical_error` (mensaje con el motivo y la mención
  `SCI-POLICY`). El chequeo compara la declaración del reporte contra el cutoff de la policy; no
  duplica `SCI-CUTOFF`, que compara el profile del dataset.

- **R17 — Agregador / output guard**: `evaluate_destination(ctx) -> list[CheckResult]` corre, en
  este orden fijo, `REPORT-POLICY`, `REPORT-DEST-SAFE`, `REPORT-DEST-SCOPE`,
  `REPORT-SENSITIVE-DEST`. `evaluate_governance(ctx) -> list[CheckResult]` corre esos cuatro y
  luego `REPORT-SOURCE-ACCESS`, `REPORT-HOLDOUT-ACCESS`, `REPORT-HOLDOUT-SOURCE`,
  `REPORT-ISOLATION-INPUT` (aplicada a `ctx.sources` con `flow_scope=ctx.decision_scope`: es N/A
  para `exploratory`) y `REPORT-SCI-CUTOFF`, con `checks.ejecutar_checks`. Si la policy de
  reporting no carga, devuelve únicamente el `FAIL` `REPORT-POLICY` (R8). Nunca lanza.
  `output_allowed(results) -> bool` es `True` sii no hay ningún `FAIL` (usa
  `checks.hay_bloqueo`; `WARN` y `N/A` no bloquean). Este es el output guard: el Change 4
  (`publish`) lo llamará y rehusará escribir ante cualquier `FAIL`. **Enmienda ciclo 1**: firma
  `output_allowed(results, *, require_codes=()) -> bool`: además de "sin FAIL", si `require_codes`
  no está vacío exige que cada código aparezca en `results` (si falta => `False`); `[]` es `True`
  salvo que se pidan `require_codes`. Constante pública
  `REQUIRED_DESTINATION_CODES = (REPORT-POLICY, REPORT-DEST-SAFE, REPORT-DEST-SCOPE)`; `publish`
  debe usar `output_allowed(res, require_codes=REQUIRED_DESTINATION_CODES)` para que "no se evaluó
  nada" no cuente como permitido. Ante una entrada que no es una lista de `CheckResult` devuelve
  `False` (fail-closed).

- **R18 — CLI**: `python -m tools.reporting` (`argparse`; `__main__.py` sigue el patrón de
  `tools/ds_profile/__main__.py:1-9`). Subcomandos:
  `check-inputs --flow-scope {exploratory,model_valid,operational} --input <ruta> (repetible,
  requerido) [--repo-root <dir>] [--json]` (llama a `check_flow_inputs`) y
  `check-destination --report-id <id> --scope {exploratory,model_valid,operational}
  --report-kind {eda,model,evaluation,production} --out-dir <ruta> [--repo-root <dir>] [--json]`
  (valida `report_id`/`scope`/`report-kind` construyendo un `Report` mínimo de `reporting_core`,
  arma el contexto con `holdout_access="none"` y sin fuentes, y llama a `evaluate_destination`).
  `--repo-root` default `Path.cwd()`; rutas relativas se resuelven contra `--repo-root` (como
  `pathguard`). Exit codes: `0` sin `FAIL`; `1` al menos un `FAIL` (`checks.exit_code`); `2` error
  de uso (argumentos inválidos, incluido un `report_id` que viole el contrato de ids); `3` error de
  entorno (`--repo-root` inexistente o no es directorio). Salida en `stdout`: por defecto una línea
  por resultado (`[STATUS] CODE [subject] mensaje`); con `--json`, un objeto con claves ordenadas
  `allowed` (bool), `counts` (por status) y `results` (`CheckResult.to_dict()`). Mensajes de error
  de uso/entorno a `stderr`. El CLI no escribe nada en disco ni contiene `sys.stdin`. Los Changes 3
  y 4 agregarán `validate` y `render`.

- **R19 — Instalabilidad**: `tools/ds_init/manifest.py` agrega tres `EntradaManifiesto` VERBATIM
  (`tools/reporting/governance.py`, `tools/reporting/cli.py`, `tools/reporting/__main__.py`;
  `fuente == destino`) con `stage_minimo` por defecto (`discovery`), insertadas inmediatamente
  después de la de `tools/reporting/core.py`. Los tests de `tools/reporting/tests/` no van al
  manifest. `tools/ds_init/tests/test_manifest.py`, `tools/tests/test_manifest_dsguard_parity.py`
  y `python -m tools.ds_init.check_manifest_parity` siguen verdes sin editarse. Las dependencias
  de `governance.py` en `dsguard` (`checks`, `pathguard`, `repo`, `scientific_validity`, `core`)
  ya se instalan desde `discovery`.

- **R20 — Arquitectura y frontera**: `ARCHITECTURE.md` §2.1 agrega filas para
  `tools/reporting/governance.py` (core neutral respecto del protocolo de hooks; importa `dsguard`,
  dirección permitida por la regla 6) y `tools/reporting/cli.py` (CLI `argparse` portable);
  ambos se agregan a `MODULOS_CORE` de `tools/tests/test_architecture_boundaries.py` (misma lista
  que §2.1). `tools/tests/test_v06_core_neutrality.py` NO se modifica y sigue verde: `core.py`
  sigue solo-stdlib y ningún paquete previo (`dsguard`, `ds_profile`, `dsimpact`, `providers`,
  `routing`, `fallback`, `harmessi_bench`) importa `reporting`.

- **R21 — No duplicación y backward compatibility**: `dsguard/pathguard.py`,
  `dsguard/scientific_validity.py`, `dsguard/checks.py`, `dsguard/repo.py`, `dsguard/core.py`,
  `ds_profile/*`, `.claude/guardrails.json`, `tools/reporting/core.py` y
  `tools/reporting/__init__.py` no cambian de comportamiento ni de bytes. No se replica ningún
  helper privado de `pathguard` ni se crea otro engine de checks; holdout (`guardrails.json` +
  `pathguard`), hashes, scientific validity, provenance y lifecycle siguen siendo de sus dueños.
  Las únicas modificaciones a archivos existentes son aditivas: tres entradas en `MANIFEST`, filas
  en `ARCHITECTURE.md`, dos líneas en `MODULOS_CORE` y el tildado del roadmap.

- **R22 — Roadmap**: `docs/roadmap/v0.6.md` tilda `[x] Change 1` en la invocación de cierre; nada
  más del roadmap cambia; v0.7-v0.9 no se tocan.

- **R23 — Tests deterministas**: `tools/reporting/tests/test_governance.py` y
  `tools/reporting/tests/test_cli.py` (`unittest`, repos temporales con `tempfile`, sin red, sin
  aleatoriedad, sin holdouts reales; los holdouts de prueba son patrones sintéticos en un
  `guardrails.json` temporal). Cobertura mínima: ver criterios de aceptación.

## Criterios de aceptación

**R1 — restricciones transversales**
- Given `governance.py`, When se escanea su AST, Then los imports son solo stdlib,
  `dsguard.*` (vía `from dsguard import ...`) y `from . import core`; ningún import de
  `ds_profile`, `plotly`, `pandas`, `numpy`; y no contiene llamadas a `write_text`, `write_bytes`,
  `mkdir`, `unlink`, `rename`, `rmdir`, `touch` ni `open(...)` con modo de escritura.
- Given un repo temporal, When se corre cada función pública (y el CLI), Then el árbol de
  archivos (rutas, tamaños y mtimes) es idéntico antes y después.
- Given contextos mal formados (`sources=None`, `out_dir=None`, `decision_scope=123`,
  `repo_root` inexistente) y archivos corruptos, When se llama `evaluate_governance` /
  `evaluate_destination` / `check_flow_inputs` / `output_allowed`, Then no lanzan y devuelven
  `list[CheckResult]` con al menos un `FAIL` (o `bool` para `output_allowed`).
- Given el mismo repo y contexto, When se evalúa dos veces, Then las listas son iguales, con los
  mismos códigos en el mismo orden.
- Given `test_v06_core_neutrality.py` y `test_architecture_boundaries.py` sin modificar
  (salvo `MODULOS_CORE`), Then siguen verdes.

**R2 — vocabulario**
- Given cualquier resultado, Then `isinstance(r, checks.CheckResult)` (con el mismo módulo
  `checks` que importa `governance`) y `r.status ∈ {PASS, WARN, FAIL, N/A}`; los `code` observados
  en toda la suite pertenecen al conjunto de R2 (o terminan en `-EXCEPCION`).
- Given cualquier check sin datos que evaluar, Then devuelve al menos un resultado (nunca lista
  vacía) y ese resultado no es `PASS`.

**R3/R4/R5 — policy**
- Given un repo sin `.harmessi/reporting-policy.json`, When `load_policy`, Then
  `source == "default"`, roots `reports/exploratory`, `reports/model_valid`,
  `reports/operational` y `sensitive_destination_roots == ()`.
- Given una policy con solo `destination_roots: {"model_valid": "out/mv"}`, Then los otros dos
  scopes conservan el default; con `sensitive_destination_roots: ["reports/operational/sens"]`
  válido.
- Given una policy con un campo top-level desconocido, Then se ignora sin error.
- Given JSON inválido, un array, `schema_version: 2`, `destination_roots: []`,
  `sensitive_destination_roots: "x"`, un root `123`, o la clave `"model-valid"`, Then
  `ReportingPolicyError`.
- Given roots `"/abs"`, `"C:/x"`, `"a\\b"`, `"../x"`, `"a/../b"`, `"a//b"`, `"a/"`, `"."`, `""`,
  `"a/*"`, `"a[1]"`, `"a?"`, Then `ReportingPolicyError` en cada caso.
- Given dos scopes con el mismo root, un root anidado en otro (`out` y `out/mv`), o la misma
  colisión solo por mayúsculas (`Out` vs `out/mv`), Then `ReportingPolicyError`.
- Given un `sensitive_destination_root` igual a un root de scope, o fuera de todos ellos, Then
  `ReportingPolicyError`; dentro de un root de scope (estricto), válido.
- Given `resolve_output_dir(policy, "model_valid", "informe-1")`, Then `"reports/model_valid/informe-1"`;
  con scope `"otro"`, `report_id` vacío o `"a/b"`, Then `ReportingPolicyError`.
- Given `reports/exploratory-x/r1` y root `reports/exploratory`, Then NO pertenece al root;
  `reports/exploratory/r1` sí; `reports/exploratory` (el root) no.

**R7 — contexto**
- Given un `Report` con una tabla `sensitive=True`, otra `False`, una figura `sensitive=True`,
  When `context_from_report`, Then `report_id`/`report_kind`/`decision_scope` coinciden con el
  `Report` y `sensitive_artifacts == (id_tabla_sensible, id_figura_sensible)`.
- Given `sources=["a.csv"]` (lista), Then `ctx.sources == ("a.csv",)`.

**R8 — `REPORT-POLICY`**
- Given policy ausente, Then PASS con mensaje que menciona el default; policy válida en
  archivo, Then PASS que menciona la ruta; policy corrupta, Then FAIL `kind=technical_error` y
  `evaluate_governance` devuelve exactamente ese único resultado.

**R9 — `REPORT-DEST-SAFE`**
- Given un `out_dir` limpio bajo el root del scope, Then un PASS.
- Given `out_dir` dentro de `.ssh/`, o cuyo `report.html` cae en un patrón de secreto
  (p. ej. `secretos_extra`), Then FAIL con el motivo de `pathguard` y `subject` con la ruta.
- Given `out_dir` dentro de un holdout de `guardrails.json` (sintético), Then FAIL (holdout, la
  escritura nunca se autoriza); una excepción de lectura vigente NO lo habilita.
- Given `out_dir = data/raw/x`, Then FAIL (`data_raw`); `out_dir = .claude` con
  `manifest.json` no protege, pero `out_dir` que produce `.claude/guardrails.json` no ocurre con
  los nombres canónicos: se prueba que `guardrails.json` corrupto => FAIL `technical_error`.
- Given `agent_type` con `write_scopes` que no incluyen el `out_dir`, Then FAIL (fuera del
  `write_scope`); con `agent_type` cuyo scope lo incluye, PASS.
- Given `out_dir` fuera del repo (absoluto en otro directorio temporal, o `../x`), Then FAIL.
- Given `out_dir` con mayúsculas distintas a un patrón de holdout, Then FAIL (casefold).

**R10 — destino por scope**
- Given `decision_scope="exploratory"` y `out_dir="reports/exploratory/r1"`, Then PASS.
- Given `decision_scope="model_valid"` y `out_dir="reports/exploratory/r1"`, Then FAIL con código
  `REPORT-DEST-CROSS-SCOPE`; y a la inversa (`exploratory` en `reports/model_valid/r1`).
- Given `out_dir="reports/model_valid"` (el root), `"reports"`, `"otro/dir"` o `"."`, Then FAIL
  `REPORT-DEST-SCOPE`.
- Given `decision_scope="invalido"`, Then FAIL `REPORT-DEST-SCOPE` (sin inferencia).
- Given una policy custom con roots propios, Then el mismo comportamiento sobre los roots
  custom (y `reports/...` deja de ser destino válido).
- Given `out_dir` que es un symlink hacia otro scope (si el SO lo permite; el test se omite con
  `skipTest` si no), Then FAIL cross-scope.
- Given `out_dir="Reports/EXPLORATORY/r1"`, Then PASS (casefold).

**R11 — sensibles**
- Given cero artefactos sensibles, Then N/A.
- Given un artefacto sensible y policy default (sin roots sensibles), Then FAIL.
- Given un artefacto sensible, root sensible `reports/model_valid/sens` y `out_dir` dentro,
  Then PASS; `out_dir` fuera del root sensible, Then FAIL.

**R12 — `REPORT-SOURCE-ACCESS`**
- Given fuentes limpias, Then un PASS por fuente con `subject`.
- Given una fuente en un holdout sin excepción de lectura, Then FAIL; con excepción de lectura
  vigente (ruta exacta, `vence_utc` futura), Then PASS; con excepción vencida (`vence_utc`
  pasada), Then FAIL.
- Given una fuente `.env` o `*.pem`, Then FAIL (secreto).
- Given una fuente fuera del repo, Then FAIL.
- Given `sources=()`, Then un N/A; una fuente `""` o `123`, Then FAIL.

**R13 — `REPORT-HOLDOUT-ACCESS`**
- Given `holdout_access=None`, `"READ"`, `"write"` o `""`, Then FAIL; `"none"`, PASS.
- Given `"read"` con `report_kind="evaluation"`, `decision_scope="model_valid"` y una policy
  científica con `holdout.declared: true` y `final_evaluation.authorized: true`, Then PASS
  (con el `reason` en el mensaje si existe).
- Given `"read"` con esa policy pero `report_kind="eda"`, o `decision_scope="exploratory"`, o
  policy sin `holdout`, o `declared: true` sin `final_evaluation`, o `authorized: false`, Then
  FAIL en cada caso.
- Given `"read"` con `.harmessi/scientific-policy.json` corrupto, Then FAIL `technical_error`.

**R14 — `REPORT-HOLDOUT-SOURCE`**
- Given una fuente dentro de un holdout y `holdout_access="none"`, Then FAIL (contradicción); con
  `holdout_access=None`, Then FAIL.
- Given esa fuente con `"read"` autorizado (R13) y excepción de lectura vigente, Then PASS con nota;
  con `"read"` no autorizado, Then FAIL.
- Given una fuente fuera de todo holdout, Then PASS; fuera del repo, Then N/A; sin fuentes, Then
  un N/A; `guardrails.json` corrupto, Then FAIL `technical_error`.
- Given una matriz de rutas con mayúsculas/minúsculas y subdirectorios, Then la decisión de
  `REPORT-HOLDOUT-SOURCE` (¿matchea holdout?) coincide con la de `pathguard.evaluar_tool_call`
  `Read` (holdout denegado sin excepción) para todas ellas (guarda contra deriva del matching).

**R15 — `REPORT-ISOLATION-INPUT`**
- Given `flow_scope="exploratory"` y cualquier input, Then N/A.
- Given `flow_scope="model_valid"` u `"operational"` y un input en `reports/exploratory/r1/artifacts/t.csv`,
  Then FAIL (root); con root exploratory custom, el mismo comportamiento sobre el custom.
- Given un input en un directorio cuyo ancestro tiene un `manifest.json` con `report_id` y
  `decision_scope: "exploratory"` (fuera del root exploratory), Then FAIL (manifest); con
  `decision_scope: "model_valid"`, Then PASS; con un `manifest.json` ajeno (`{"name": "x"}`),
  ilegible o no JSON, Then PASS (ignorado).
- Given un input que es el propio directorio de reporte exploratorio, Then FAIL (su `manifest.json`).
- Given un `manifest.json` ancestro ubicado en un directorio denegado por `pathguard` (holdout),
  Then no se abre.
- Given un input en `data/interim/x.parquet` sin manifests ancestros, Then PASS.
- Given un input fuera del repo o `""`, Then FAIL; `flow_scope="otro"`, Then FAIL; `inputs=()`,
  Then N/A; policy corrupta, Then FAIL `technical_error`.
- Given un input con casing distinto al root (`Reports/Exploratory/x`), Then FAIL.

**R16 — `REPORT-SCI-CUTOFF`** (policy con `temporal: {declared: true, cutoff_utc: "2026-01-01T00:00:00Z"}`)
- Given scope `model_valid` y `operational` (cada uno) y `data_cutoff` ∈ {ausente, `"2025-12-31"`,
  `"2026-01-01"`, `"2026-01-02"`, `"2026-01-01T00:00:00Z"`, `"2026-01-01T00:00:01Z"`}, Then
  ausente => FAIL, `"2025-12-31"` => PASS, `"2026-01-01"` => PASS (igual, `<=`),
  `"2026-01-02"` => FAIL, `...T00:00:00Z` => PASS, `...T00:00:01Z` => FAIL.
- Given scope `exploratory` y los mismos valores, Then ausente => WARN, `> cutoff` => WARN con el
  mensaje sobre no alimentar `model_valid`, `<=` => PASS.
- Given `data_cutoff="01/01/2026"` o `"2026-13-40"` en cualquier scope (con temporal declarado),
  Then FAIL.
- Given policy sin `temporal` (o `declared: false`) o sin `.harmessi/scientific-policy.json`,
  Then N/A en los tres scopes.
- Given `temporal.declared: true` sin `cutoff_utc`, Then WARN; con `cutoff_utc` inválido, Then FAIL.
- Given `.harmessi/scientific-policy.json` corrupto, Then FAIL `technical_error`.

**R17 — agregador**
- Given un contexto totalmente válido (scope y destino coherentes, sin sensibles, `holdout_access="none"`,
  fuentes limpias, sin temporal), Then `output_allowed(...)` es `True` y no hay `FAIL`.
- Given un solo `FAIL` (cualquiera), Then `output_allowed(...)` es `False`; con solo `WARN` y `N/A`,
  `True`; con lista vacía, `True`.
- Given el mismo contexto, Then el orden de códigos es
  `REPORT-POLICY, REPORT-DEST-SAFE, REPORT-DEST-SCOPE, REPORT-SENSITIVE-DEST,
  REPORT-SOURCE-ACCESS..., REPORT-HOLDOUT-ACCESS, REPORT-HOLDOUT-SOURCE...,
  REPORT-ISOLATION-INPUT..., REPORT-SCI-CUTOFF` (los resultados por fuente contiguos y en el orden
  de `sources`).
- Given `evaluate_destination`, Then devuelve exactamente los cuatro primeros checks y no evalúa
  fuentes ni cutoff.
- Given un contexto `model_valid` cuya fuente cae en `reports/exploratory/...`, Then
  `evaluate_governance` incluye `FAIL` `REPORT-ISOLATION-INPUT`; con scope `exploratory`, el mismo
  input da N/A.
- Given `guardrails.json` corrupto, Then FAIL `technical_error` en `REPORT-DEST-SAFE` sin que
  `evaluate_governance` lance; policy de reporting corrupta, Then el único resultado.

**R18 — CLI**
- Given `check-destination` con un destino coherente y limpio, Then exit `0`; con destino
  cross-scope, exit `1`; con `--scope invalido` o `--report-id "A/b"`, exit `2`; con
  `--repo-root` inexistente, exit `3`.
- Given `check-inputs --flow-scope model_valid --input reports/exploratory/r1/t.csv`, Then exit
  `1`; con `--flow-scope exploratory`, exit `0`; con dos `--input` (repetido), Then un resultado
  por input; sin `--input`, exit `2`.
- Given `--json`, Then `stdout` es JSON válido con `allowed`, `counts` y `results`, con claves
  ordenadas, y `allowed` coincide con el exit code (`true` <=> `0`).
- Given cualquier invocación, Then el árbol del repo no cambia y `cli.py` no contiene
  `sys.stdin`.
- Given un `--out-dir` relativo, Then se resuelve contra `--repo-root`, no contra el cwd.

**R19 — instalabilidad**
- Given `MANIFEST`, Then contiene exactamente una entrada `VERBATIM` con `destino == fuente` para
  cada una de `tools/reporting/governance.py`, `cli.py`, `__main__.py`, con
  `stage_minimo == "discovery"`, las tres rutas existen en el repo y aparecen justo después de
  `tools/reporting/core.py`.
- Given `manifest_para_perfil_y_stage(perfil, "discovery")`, Then incluye los tres destinos.
- Given `test_manifest.py`, `test_manifest_dsguard_parity.py` y `check_manifest_parity`, Then
  siguen verdes sin editarse.

**R20/R21/R22 — arquitectura, compatibilidad y roadmap**
- Given `MODULOS_CORE`, Then contiene `tools/reporting/governance.py` y `tools/reporting/cli.py`
  y `test_architecture_boundaries.py` sigue verde.
- Given `git diff` del Change, Then los archivos preexistentes modificados son solo `manifest.py`,
  `ARCHITECTURE.md`, `test_architecture_boundaries.py`, `docs/roadmap/v0.6.md` y
  `control.json`; `pathguard.py`, `scientific_validity.py`, `checks.py`, `core.py` (de
  `reporting`), `.claude/guardrails.json` no aparecen.
- Given `docs/roadmap/v0.6.md` al cierre, Then `[x] Change 1` y los demás Changes intactos.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica: infraestructura del harness; no hay dataset.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
Aplica de forma indirecta: `REPORT-SCI-CUTOFF` (R16) compara el `data_cutoff` DECLARADO de un
reporte contra `temporal.cutoff_utc` de `.harmessi/scientific-policy.json`. Un reporte
`model_valid`/`operational` no puede cubrir datos posteriores al cutoff; uno `exploratory` sí,
pero se marca con `WARN` y no debe alimentar `model_valid`. No se lee ningún dataset: es una
declaración, no una medición (la medición sobre el profile es `SCI-CUTOFF`).

## Baseline (condicional — modeling)
No aplica.

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
No aplica.
