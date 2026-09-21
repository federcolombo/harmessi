# Spec — 20260918-report-evidence-and-validation

Principio: el binario verifica existencia y coherencia ESTRUCTURAL y hace cumplir lo determinista.
Interpretación, causalidad, adecuación y "si una conclusión excede la evidencia" son del
Lead/metodólogo/reviewer. Ausencia de evidencia no es PASS. Todos los checks son
`dsguard.checks.CheckResult`; un PASS por regla sin violaciones; ninguna función de check lanza.

## Requisitos

### R1. Restricciones transversales
`evidence.py` y `validation.py` importan solo stdlib, `reporting.core`, `reporting.governance`,
`dsguard.*`, `ds_profile.fingerprint` (solo ese módulo) y, `validation.py`, `profiles.eda`
(patrón `sys.path.insert(0, tools_dir)`). Sin pandas/Plotly/HTML/red. Salidas deterministas. Solo
`describe_source` y `load_report_dir` levantan `EvidenceError` (subclase de `Exception`); todo lo
demás que devuelve `list[CheckResult]` o `dict` no lanza.

### R2. Layout persistido
`<out_dir>/`: `manifest.json`; `insights.json`; `artifacts/report.json` (metadata del `Report` y
capítulos con SOLO ids de tablas/figuras/insights); `artifacts/tables/<table_id>.json`
(`TableArtifact.to_dict`, filas tipadas); `artifacts/figures/<figure_id>.json`
(`FigureArtifact.to_dict`); `report.html` (Change 4, no generado acá). Cada artefacto se guarda
UNA vez. JSON persistido: `sort_keys=True, indent=2, ensure_ascii=False`, `\n` final.
- Dado un Report con T tablas y F figuras, cuando `prepare_artifacts`, entonces devuelve
  `insights.json`, `artifacts/report.json`, T archivos de tabla y F de figura; ninguna tabla ni
  figura aparece dentro de `report.json`.

### R0. Acceso de lectura antes de abrir (enmienda, ciclo reviewer 1)
`read_allowed(repo_root, path) -> (bool, str)` evalúa el acceso de LECTURA con
`pathguard.cargar_config` + `pathguard.evaluar_tool_call({"tool_name": "Read", ...})` (mismo
evaluador que governance/hook: secretos, holdouts con/sin excepción vigente, fuera del repo;
`guardrails.json` corrupto ⇒ `(False, motivo)`, fail-closed). Nunca lanza. NINGUNA función de
`evidence.py` abre el contenido de un archivo de datos (fuente, input, manifest o artefacto) sin
evaluar `read_allowed` ANTES. Los mensajes de error usan rutas relativas al repo, nunca rutas
absolutas locales.

### R3. `describe_source(repo_root, path, *, role="input", rows=None, min_date=None, max_date=None, date_column=None) -> dict`
Enmienda: `describe_source` llama `read_allowed` ANTES de `calcular_fingerprint`; denegado ⇒
`EvidenceError` ("acceso denegado", el archivo no se abre).
Fuente `kind="file"`: `path` relativo posix dentro del repo, `sha256` y
`algorithm="sha256/bin/v1"` vía `ds_profile.fingerprint.calcular_fingerprint`, `size_bytes`, y
los opcionales no nulos. Cuando el archivo no existe o resuelve fuera del repo (incluye `..` y
symlink) entonces `EvidenceError`. No lee más de lo que hashea.

### R4. `describe_generated_source(description, params, *, role="input") -> dict`
Fuente `kind="generated"` (datos sintéticos o derivados sin archivo): `description`, `params`
JSON-seguros, `algorithm="sha256/bin/v1"` y `sha256` = sha256 de `canonical_json(params)`. Cuando
`params` no es JSON-seguro o `description` está vacía, entonces `EvidenceError`.

### R5. `prepare_artifacts(report) -> dict[str, bytes]`
Ruta relativa posix → bytes UTF-8 de R2. Determinista: mismo `Report` ⇒ mismos bytes.

### R6. Helpers de entorno
- `new_run_id(now=None) -> str`: `run-YYYYMMDDTHHMMSSZ-<sufijo>`; con `now` fijo el prefijo es
  determinista.
- `resolve_git_commit(repo_root) -> (commit|None, dirty|None)` vía `dsguard.repo.get_head` y
  `list_dirty_files`; nunca lanza (sin git ⇒ `(None, None)`).
- `resolve_harmessi_version(repo_root) -> str|None`: `harness_version` de `.ds_init/control.json`;
  nunca lanza.

### R7. `build_manifest(...) -> dict`
Firma: `build_manifest(report, *, repo_root, run_id, artifact_bytes, sources=(), exclusions=(),
holdout_access, data_cutoff=None, source_notebook=None, git_commit=<auto>, git_dirty=<auto>,
harmessi_version=<auto>, clock=None)`. `holdout_access` es obligatorio (sin default). `clock`
inyectable; `generated_at` con formato `YYYY-MM-DDTHH:MM:SSZ` (`dsguard.core.ahora_utc` si no hay
clock). Esquema (`schema_version: 1`):
`report_id, run_id, report_kind, decision_scope, data_cutoff, git_commit, git_dirty,
harmessi_version, generated_at, sources[], exclusions[], holdout_access ("none"|"read"),
sensitivity {contains_sensitive, sensitive_artifacts[]}, source_notebook ({path, sha256,
algorithm}|null), artifacts[] ({id, kind: table|figure|report|insights, file, sha256}), hashes
{report_content}`.
- `sources[]`: `kind, role, sha256, algorithm` + (`file`: `path, size_bytes, rows, min_date,
  max_date, date_column`; `generated`: `description, params`).
- `exclusions[]`: `{description, reason, rows_excluded}`.
- `artifacts[].sha256` = sha256 de los BYTES PERSISTIDOS (política del Change 0), nunca del objeto
  re-serializado; `hashes.report_content` = `Report.content_sha256()`. El manifest no se lista a
  sí mismo. `sensitive_artifacts` = ids de tablas/figuras con `sensitive=True`.
- Dado un Report sin fuentes, cuando `build_manifest`, entonces construye el manifest con
  `sources: []` (no lanza); `REPORT-SOURCES-NONE` lo rechaza en validación (R15).

### R8. `write_report_dir(out_dir, artifact_bytes, manifest) -> list[str]`
SOLO escribe (sin decidir permisos: el guard es de governance/`publish`). Cada archivo con
`dsguard.core.escribir_texto_atomico` y el `manifest.json` ÚLTIMO, de modo que un corte a mitad
deja un directorio sin manifest (FAIL `REPORT-MANIFEST-MISSING`, no un reporte "a medias válido").
Devuelve las rutas relativas escritas, en orden.

### R9. `load_report_dir(out_dir) -> (Report, manifest)`
Enmienda (lectura verificada, single-read): `read_within(out_dir, rel, *, repo_root=None) -> bytes`
exige `rel` seguro (sin `..`, `\x00`, nombres reservados de Windows, absolutas; fallo ⇒
`EvidenceError`, nunca `ValueError`), resuelve con `resolve()` y exige que quede bajo
`out_dir.resolve()`, rechaza symlinks/junctions (el archivo y sus padres bajo `out_dir`), exige
`read_allowed` si se pasa `repo_root` y lee los bytes UNA vez. `read_report_dir(out_dir, *,
repo_root=None) -> (files, manifest)` lee así todos los archivos; `report_from_bytes(files,
manifest) -> Report` reconstruye SOLO desde bytes ya leídos (sin disco) y verifica
`hashes.report_content`. `load_report_dir` = `read_report_dir` + `report_from_bytes` (misma
firma y comportamiento externo). `expected_artifacts(report) -> {archivo: (id, kind)}` es el
conjunto exacto de archivos de `prepare_artifacts`, reusado por `build_manifest`. `build_manifest`
normaliza `source_notebook` (ruta posix relativa; `EvidenceError` si es absoluta/con `..`).
Lee `manifest.json`, `artifacts/report.json`, tablas, figuras e `insights.json`, reensambla el dict
de `Report.to_dict` y llama `Report.from_dict`; verifica `Report.content_sha256()` contra
`hashes.report_content`. Cuando falta un archivo, JSON corrupto, id sin archivo o hash distinto,
entonces `EvidenceError` con mensaje que nombra el archivo.

### R10. `exploratory_hash_index(repo_root) -> dict[sha256 -> {report_id, file}]`
Enmienda: `exploratory_index_status(repo_root) -> ExploratoryIndex` (dataclass frozen: `index`,
`truncated`, `error`, `unreadable_manifests`) es la API pública; `exploratory_hash_index` es su
wrapper (`.index`). El escaneo NO desciende bajo un directorio que ya contiene un `manifest.json`
de reporte Harmessi (un reporte es una hoja: no agota `MAX_DIRS_SCAN` con `artifacts/`); un
`manifest.json` ilegible, > 16 MB, sin acceso (`read_allowed`) o de forma inválida se CUENTA en
`unreadable_manifests`; un error de `os.walk` (`onerror`) ⇒ `error`.
Escanea recursivamente el root exploratory de `governance.load_policy` buscando `manifest.json`
con forma de reporte Harmessi (`schema_version`, `report_id`, `artifacts`) y
`decision_scope == "exploratory"`; indexa los `artifacts[].sha256` con su `file`. Acotado a un
máximo documentado de directorios (`MAX_DIRS_SCAN`); manifests ilegibles se ignoran. Si la policy
es inválida devuelve `{}` (la falla de policy la reporta governance, `REPORT-POLICY`).

### R11. `check_inputs_hash_isolation(repo_root, flow_scope, inputs, *, index=None) -> list[CheckResult]`
Enmienda: `read_allowed` se evalúa por archivo ANTES de hashearlo; denegado ⇒ FAIL
`technical_error` "no verificable: acceso denegado (no se abrió)" con el subject relativo (no se
abre el archivo). Un error de recorrido de un directorio input (`os.walk` `onerror`) ⇒ FAIL
`technical_error`. `unreadable_manifests > 0` ⇒ WARN adicional `REPORT-ISOLATION-HASH` (y sin PASS).
`index` (un `ExploratoryIndex` ya calculado) evita reindexar.
Código `REPORT-ISOLATION-HASH`. Para `flow_scope` `model_valid`/`operational`: FAIL si el sha256 de
un archivo input —o de cada archivo bajo un directorio input, acotado a `MAX_FILES_HASH`—
coincide con un artefacto persistido de un reporte exploratory. `exploratory` ⇒ N/A (PASS
informativo). Fail-closed: input ilegible o cota superada ⇒ FAIL `technical_error`. Nunca lanza.
- Dado un CSV copiado byte a byte desde `artifacts/tables/x.json` exploratory a otra ruta, cuando
  `flow_scope="model_valid"`, entonces FAIL nombrando `report_id` y `file` de origen.
- Dado el mismo input y `flow_scope="exploratory"`, entonces sin FAIL.

### R12. `validate_report(report, *, scientific_policy=None) -> list[CheckResult]` — figuras
- `REPORT-FIGURE-NO-TABLE` FAIL: figura sin `backing_table_id`. Dado un gráfico sin tabla de
  respaldo, entonces FAIL ("ningún gráfico sin su tabla" es hecho verificable).
- `REPORT-FIGURE-DANGLING-TABLE` FAIL: `backing_table_id` no resuelve a una TABLA del reporte
  (un id de figura o insight no cuenta).
- `REPORT-FIGURE-SPEC-COLUMNS` FAIL: `spec.columns_used()` ⊄ columnas de la tabla de respaldo.
  Dado un spec que usa `x`, cuando la tabla no tiene columna `x`, entonces FAIL nombrando la
  columna.
- `REPORT-FIGURE-TABLE-EMPTY` FAIL: tabla de respaldo con 0 filas.
- `REPORT-SENSITIVE-FIGURE` WARN: figura no sensible respaldada por tabla sensible (posible fuga
  vía gráfico; la decisión es del revisor).

### R13. `validate_report` — insights
- `REPORT-INSIGHT-CLAIMS` FAIL: `technical_claim`, `business_claim`, `population` o `time_scope`
  vacíos tras `strip`.
- `REPORT-INSIGHT-NO-EVIDENCE` FAIL: sin `evidence_refs` (decidido FAIL, no WARN: un insight sin
  evidencia es una afirmación sin sustento verificable).
- `REPORT-INSIGHT-DANGLING-REF` FAIL: ref que no resuelve a tabla o figura del reporte.
- `REPORT-INSIGHT-UNCERTAINTY` WARN: `claim_type` ≠ `descriptive` sin `uncertainty`.
- `REPORT-INSIGHT-REVIEW-REQUIRED` WARN: `claim_type` `causal`/`recommendation` exige revisión
  semántica del Lead/metodólogo; el binario NO juzga si excede la evidencia. Dado un insight
  causal con evidencia válida, entonces WARN, nunca PASS silencioso ni FAIL.

### R14. Delegación EDA
Si `report_kind == "eda"` o existe `report.metadata["eda"]`, `validate_report` agrega
`profiles.eda.validate_eda_report(report, scientific_policy=scientific_policy)` (mismo dict).
`profiles/eda.py` no se modifica.

### R15. `validate_manifest(manifest, report=None) -> list[CheckResult]`
- `REPORT-MANIFEST-SCHEMA` FAIL: campos/tipos/enums/formatos inválidos o ausentes (`schema_version`,
  `holdout_access`, `generated_at`, sha256 de 64 hex, `artifacts[].kind`, `sources[].kind`, etc.).
- `REPORT-MANIFEST-CONSISTENCY` FAIL (solo con `report`): `report_id`, `report_kind`,
  `decision_scope`, `hashes.report_content` o `sensitivity.sensitive_artifacts` no coinciden con
  el Report.
- `REPORT-SOURCES-NONE` FAIL: `sources` vacío ("absencia ≠ PASS").
- `REPORT-PROVENANCE` WARN: `git_commit` ausente, `git_dirty` true o `harmessi_version` ausente
  (reproducibilidad degradada, no bloqueo).

### R16. `validate_report_dir(repo_root, out_dir) -> list[CheckResult]` — puerta completa
Orden: (1) `REPORT-MANIFEST-MISSING` FAIL (sin `manifest.json`, incluso si hay `report.html`);
`REPORT-MANIFEST-UNREADABLE` FAIL `technical_error` (JSON inválido/no objeto); si fallan, corta
con esos resultados. (2) `REPORT-ARTIFACT-MISSING` FAIL (listado sin archivo);
`REPORT-ARTIFACT-HASH` FAIL (bytes alterados); `REPORT-ARTIFACT-UNLISTED` WARN (archivo bajo
`artifacts/` no listado). (3) `REPORT-SOURCE-MISSING` FAIL (fuente `file` inexistente);
`REPORT-SOURCE-STALE` FAIL (hash actual ≠ manifest). (4) `load_report_dir` + `validate_report` +
`validate_manifest` sobre el Report cargado (carga fallida ⇒ FAIL `technical_error`, sin
excepción). (5) governance: `governance.evaluate_governance` con un `GovernanceContext` armado
desde el manifest (sources tipo file, `holdout_access`, `data_cutoff`, `sensitive_artifacts`,
`out_dir`). (6) Cuando el scope es `model_valid`/`operational`, `check_inputs_hash_isolation`
sobre las fuentes file. `REPORT-EXPLORATORY-IN-MODEL-FLOW` es el caso agregado: path/manifest
(`REPORT-ISOLATION-INPUT` de governance) o hash (`REPORT-ISOLATION-HASH`).
Enmienda (ciclo reviewer 1, `validation.py`):
- Acceso antes de abrir: manifest, artefactos y fuentes pasan por `evidence.read_allowed` ANTES
  de cualquier apertura/hash. Una fuente `file` denegada (holdout sin excepción vigente, secreto,
  fuera del repo, path inseguro, `guardrails.json` corrupto) ⇒ FAIL `technical_error`
  `REPORT-SOURCE-UNVERIFIABLE` ("no verificable: acceso denegado, no se abrió"); nunca PASS ni
  `REPORT-SOURCE-STALE` para esa fuente, y no se abre ni se hashea. El paso 6 delega el mismo
  criterio por archivo a `check_inputs_hash_isolation(..., index=)`.
- Lectura single-read: `evidence.read_report_dir(out_dir, repo_root=repo)` una sola vez; los
  MISMOS bytes se hashean (`REPORT-ARTIFACT-HASH`) y reconstruyen el Report
  (`evidence.report_from_bytes`), sin releer disco. Si esa lectura falla (ruta de error) se relee
  solo el manifest y cada artefacto listado individualmente (una vez cada uno). Symlinks/junctions,
  `\x00`, nombres reservados y accesos denegados ⇒ FAIL (`REPORT-ARTIFACT-HASH` `technical_error`
  o `REPORT-MANIFEST-UNREADABLE`), nunca excepción.
- `REPORT-ARTIFACT-SET` FAIL: `manifest["artifacts"]` debe listar EXACTAMENTE
  `evidence.expected_artifacts(report)`: faltante, extra, duplicado, `id`/`kind` que no coincide
  con el archivo, ruta insegura o `artifacts: []`. Sin Report cargado ⇒ N/A (el fallo de carga
  ya es `REPORT-LOAD` FAIL). `REPORT-ARTIFACT-UNLISTED` WARN cubre además `insights.json` no
  listado, archivos/enlaces en la raíz del `out_dir` distintos de `manifest.json`/`report.html`/
  `artifacts/` y enlaces bajo `artifacts/`.
- Los sha256 son AUTOATESTADOS: un manifest reescrito de forma consistente con los artefactos no
  se detecta; el ancla externa (commit/firma) es del hardening.
- Una sola indexación exploratory (`exploratory_index_status`) se pasa como `index=` y el WARN de
  manifests ilegibles se propaga. Mensajes con rutas relativas al repo (`<fuera-del-repo>/nombre`
  fuera de él); las excepciones internas informan el TIPO, no su texto.
- Dado un reporte válido y sin cambios, entonces cero FAIL.
- Dado el mismo reporte con un byte alterado en una tabla, entonces `REPORT-ARTIFACT-HASH` FAIL.
- Dado una fuente `file` modificada tras generar, entonces `REPORT-SOURCE-STALE` FAIL.

### R17. Política científica única
`validate_report_dir` carga `scientific_policy` UNA vez desde disco
(`scientific_validity.leer_policy`) y la pasa a todo lo que la usa (lección del reviewer del
Change 2: el mismo dict a `build_eda_report` y `validate_eda_report`). Policy ilegible ⇒ FAIL
`technical_error`, no default silencioso.

### R18. CLI `validate`
`python -m tools.reporting validate --dir <report_dir> [--repo-root R] [--json]`. Exit 0 sin FAIL,
1 con FAIL, 2 uso, 3 entorno (repo inválido). Solo lectura; misma forma de salida que
`check-inputs`. Dado `--dir` sin manifest, entonces exit 1 con `REPORT-MANIFEST-MISSING`.

### R19. CLI `check-inputs` aditivo
`check-inputs` suma `check_inputs_hash_isolation` a lo que ya emite; sin renombrar ni quitar
códigos ni cambiar exit codes existentes. Los tests previos del CLI pasan sin cambios.

### R20. Reproducibilidad
Con `clock` y `run_id` fijos, mismo `Report` + mismas fuentes + mismo commit ⇒ manifest y todos los
artefactos byte-idénticos. `write_report_dir` + `load_report_dir` es round-trip: el `Report`
cargado tiene el mismo `content_sha256`.

### R21. Instalabilidad y arquitectura
`tools/ds_init/manifest.py`: 2 entradas VERBATIM (`tools/reporting/evidence.py`,
`tools/reporting/validation.py`), `stage_minimo` default; aserciones en `test_installability.py`.
`ARCHITECTURE.md` §2.1: filas nuevas (evidence: importa governance, dsguard,
`ds_profile.fingerprint`; validation: importa `profiles.eda`) y regla de dirección: reporting →
ds_profile SOLO `fingerprint`. `MODULOS_CORE` de `test_architecture_boundaries.py` suma ambas
rutas.

### R22. Compatibilidad hacia atrás
`tools/reporting/core.py`, `governance.py`, `profiles/eda.py`, `profiles/__init__.py`,
`__main__.py` y `__init__.py` sin cambios (`git diff` vacío). `cli.py` cambia solo de forma
aditiva.

### R23. Tests (`unittest`, repos temporales, sin red, fixtures genéricos)
`test_evidence.py`, `test_validation.py`, `test_cli_validate.py`. Base: `build_example_report()`
(eda_generic). Variantes rotas: figura sin tabla, columnas ausentes, ref colgante, artefacto
alterado, fuente stale/inexistente, manifest ausente/corrupto, copia de artefacto exploratory en
flujo `model_valid`. Además: reproducibilidad byte a byte, round-trip, "nunca lanza" con entradas
basura (`None`, tipos erróneos), un PASS por regla sin violaciones.

### R24. Límites honestos (se documentan en `validation.py`/`evidence.py` y `verification.md`)
- El binario NO evalúa si una conclusión excede la evidencia ni si la evidencia es adecuada; un
  insight puede referenciar una tabla irrelevante y pasar.
- La isolation por hash cubre copias byte-idénticas, no derivados (p. ej. un CSV re-exportado con
  otro formato o filtrado).
- El índice exploratory depende de manifests existentes bajo el root; sin manifests no hay nada
  que comparar.
- `git_dirty` es informativo (WARN); no bloquea.
- Los sha256 del manifest prueban integridad, no autoría ni aprobación.
- Los sha256 son autoatestados: un manifest reescrito de forma consistente con artefactos
  alterados (o ambos regenerados) no se detecta; requiere un anclaje externo (commit/firma).
- TOCTOU: entre `read_allowed` y la lectura, y entre hashear una fuente y usarla, el archivo
  puede cambiar; las lecturas son single-read pero no atómicas respecto del filesystem.
- `load_report_dir(out_dir, *, repo_root=None)`: con `repo_root` evalúa `read_allowed` antes de
  abrir cada archivo; sin `repo_root` es uso local explícito y NO evalúa acceso. El `publish` del
  Change 4 DEBE usar el camino con `repo_root`. `resolve_harmessi_version` lee
  `.ds_init/control.json` (config del harness, no datos) sin `read_allowed`, por diseño.
- `validate_report_dir`: si no se puede listar el directorio (`OSError`), `REPORT-ARTIFACT-UNLISTED`
  es FAIL `technical_error` ("no verificable"), nunca PASS.
- Con `out_dir` fuera del repo, la ruta que pasó el propio usuario puede aparecer como `subject`
  en resultados de governance; los nombres de archivos dentro de un holdout pueden aparecer como
  `subject` de un FAIL (no se lee el contenido). `read_allowed` recarga `guardrails.json` en cada
  llamada (costo, no correctitud).
- El escaneo por hash no ve reportes exploratory sin manifest legible; los manifests ilegibles
  solo se cuentan (WARN), no se pueden comparar.

## Criterios de aceptación
- [ ] R2-R11: `evidence.py` con round-trip y manifest determinista.
- [ ] R12-R17: cada código `REPORT-*` tiene un test de FAIL/WARN y uno de PASS.
- [ ] R18-R19: CLI `validate` y `check-inputs` aditivo con exit codes verificados.
- [ ] R20: byte-idéntico con reloj y run_id fijos.
- [ ] R21-R22: instalabilidad, arquitectura y `git diff` sin cambios en archivos protegidos.
- [ ] R23-R24: suites verdes (corridas por el Lead) y límites documentados.

## Unidad de análisis / grain
No aplica (sin datos de proyecto; los fixtures son sintéticos y genéricos).

## Cutoff / information boundary
El `data_cutoff` del manifest se propaga a `GovernanceContext` y lo evalúa `REPORT-SCI-CUTOFF`
de governance; este Change no agrega lógica de cutoff propia.
