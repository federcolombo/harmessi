# Tareas — 20260915-readiness-and-promotion

estado: cerrada

## Invocaciones planificadas
<!-- rol, momento del ciclo, y qué produce cada una -->
- Python Data Engineer (implementación + tests, invocación única): `tools/dsguard/mlops_evidence.py`
  + `tools/dsguard/readiness.py` + `project readiness`/`project promote`/`mlops evidence add` en
  `ds_guard.py` + manifest + tests, todo en un solo paso, siguiendo `design.md` al pie de la
  letra (nombres de función, códigos de `CheckResult`, algoritmo de `promote`).
- Data Science Reviewer (revisión, DESPUÉS de implementación completa): revisa el diff. Solo
  informa hallazgos.
- Python Data Engineer (post-revisión, si hace falta): corrige, `estado: en_verificacion`.
- Python Data Engineer (cierre, planificada): `verification.md` con evidencia real,
  `estado: cerrada`.

## Tareas
- [x] `tools/dsguard/mlops_evidence.py`: `EvidenciaError`, `TIERS_EVIDENCIABLES =
  ("production_readiness", "operations")`, hash sha256 binario chunked local (no importar
  `ds_profile`), validación de ruta reusando `pathguard.cargar_config`/
  `pathguard.resolver_ruta_relativa`/`repo.path_matches_any` (holdouts+secretos+excepciones de
  lectura, fail-closed si `guardrails.json` corrupto).
- [x] `agregar_evidencia(repo_root, tier, capability, artifact_rel_path, reason) -> dict`: valida
  tier/capability/reason/artifact (existe, es archivo, dentro del repo, no protegido); calcula
  sha256; dedup determinista por `{capability, path, hash}`; escribe
  `{"tipo":"artifact_evidence","path","sha256","reason","utc"}` en
  `mlops.<tier>.<capability>.evidencia` vía `lifecycle.escribir_estado`; requiere lifecycle
  existente (propaga si no).
- [x] `evidencia_valida(repo_root, tier, capability) -> (bool, detalle)`: `True` solo si hay una
  entrada `artifact_evidence` con archivo presente + dentro del repo + hash actual coincide;
  evidencia obsoleta o ausente → `False` con detalle explicativo.
- [x] `tools/dsguard/readiness.py`: `TARGETS_VALIDOS = ("experiment", "production_candidate",
  "production")`, `PromotionError`, tabla de secuencia
  `{"discovery":"experiment","experiment":"production_candidate","production_candidate":"production"}`,
  códigos `READINESS-*` per `spec.md` (uno por gate, sin inventar de más ni de menos).
- [x] `evaluar_readiness(repo_root, "experiment")`: `READINESS-PROJECT-VALID` +
  `READINESS-LIFECYCLE-VALID` únicamente (nada de risk/CRISP-DM/foundations en este target).
- [x] `evaluar_readiness(repo_root, "production_candidate")`: prerrequisitos (con manejo "no se
  pudo evaluar" si faltan, sin short-circuit) + `READINESS-RISK-CLASSIFIED` +
  `READINESS-CRISPDM-<FASE>` (6 fases) + `READINESS-FOUNDATIONS-<CAP>` (4, vía
  `mlops_foundations.evaluar_foundations` reinterpretado, `lineage` preservado tal cual) +
  `READINESS-PRODREADY-<CAP>` (5, vía `mlops_evidence.evidencia_valida`).
- [x] `evaluar_readiness(repo_root, "production")`: todo lo de `production_candidate` +
  `READINESS-CRISPDM-DEPLOYMENT` (`cerrada`) + `READINESS-CRISPDM-MONITORING` (`en_progreso`/
  `cerrada`, `no_iniciada`→FAIL) + `READINESS-OPS-<CAP>` (7, vía
  `mlops_evidence.evidencia_valida(..., "operations", ...)`).
- [x] `promote(repo_root, target, reason) -> dict`: valida reason/target; calcula único próximo
  stage secuencial válido (rechaza salto/downgrade/repetición sin siquiera evaluar readiness); si
  coincide, corre `evaluar_readiness` (solo lectura); si `hay_bloqueo` → no muta, devuelve
  resultados; si pasa → muta ÚNICAMENTE `.harmessi/project.json` vía `maturity.escribir_estado`
  (`project_stage` + `stage_history` con `via="promote"`).
- [x] `ds_guard.py`: `project readiness --target <...> [--json]` (read-only, exit
  `checks.exit_code`), `project promote <stage> --reason "..." [--json]` (exit 0/1/2 según
  resultado), subgrupo `mlops evidence add --tier --capability --artifact --reason [--json]`
  (exit 0/1/2). Salida texto de `readiness`: título + una línea por resultado + `Resultado:
  READY`/`NOT READY`. `--json`: lista de `to_dict()` + `ready: bool`.
- [x] `tools/ds_init/manifest.py`: entradas VERBATIM de `mlops_evidence.py`/`readiness.py`.
- [x] `tools/tests/test_manifest_dsguard_parity.py`: clase explícita hardcodeada para ambos
  módulos nuevos (mismo patrón que las 4 clases existentes).
- [x] `tools/ds_init/tests/test_integracion_instalacion.py`: agregar ambos módulos a
  `archivos_clave`.
- [x] Tests `mlops_evidence.py`: todos los criterios de aceptación de `spec.md` (válido, fuera de
  repo, inexistente, directorio, tier inválido, tier=foundations rechazado, capability no
  perteneciente al tier, reason vacío, holdout sin excepción, secreto, guardrails corrupto, dedup
  exacto, mismo path con hash distinto sí agrega, lifecycle ausente propaga,
  `evidencia_valida` con archivo presente/borrado/modificado/ausente). Ver
  `tools/tests/test_mlops_evidence.py`.
- [x] Tests `evaluar_readiness` — target `experiment`: lifecycle+project válidos → todo PASS;
  lifecycle ausente → FAIL; project.json corrupto → technical_error; confirmar que NO exige
  risk/CRISP-DM/foundations en este target. Ver `tools/tests/test_readiness.py`.
- [x] Tests `evaluar_readiness` — target `production_candidate`: risk null → FAIL; cada fase
  CRISP-DM faltante (una por una, `no_iniciada` y `en_progreso`) → FAIL específico; foundations
  WARN en repro/versionado/artifacts (uno por uno) → FAIL de readiness; lineage WARN → WARN no
  bloqueante; cada una de las 5 production_readiness capabilities sin evidencia (una por una) →
  FAIL específico; todo completo → `ready=True`.
- [x] Tests `evaluar_readiness` — target `production`: prerequisitos de candidate siguen
  aplicando; deployment no cerrada → FAIL; monitoring `no_iniciada` → FAIL, `en_progreso`/
  `cerrada` → no bloquea ese gate; cada una de las 7 operations capabilities sin evidencia (una
  por una) → FAIL; evidencia con hash stale → FAIL; todo completo → `ready=True`.
- [x] Tests `evaluar_readiness` read-only estricto: bytes idénticos de `project.json`,
  `lifecycle/state.json` antes/después, en TODOS los escenarios anteriores (incluidos los que
  fallan).
- [x] Tests `promote`: secuencia correcta (los 3 pasos) → mutación correcta + 1 entrada
  `stage_history`; salto → rechazado sin mutación; downgrade → rechazado sin mutación; reason
  vacío/ausente → rechazado sin mutación; readiness con FAIL → sin mutación; readiness con
  technical_error → tratado como FAIL, sin mutación; promoción exitosa no reescribe entradas
  previas de `stage_history`; repetir `promote production_candidate` ya en ese stage → rechazado,
  sin duplicar historial; después de un `promote` exitoso, `maturity.calibrar(...)` levanta
  `MaturityEstadoError` (confirmar el lock de Change 3 end-to-end).
- [x] Tests CLI end-to-end vía subprocess real contra repo git temporal: `project readiness
  --target` (los 3 targets, texto y `--json`, exit codes); `project promote` (éxito, FAIL de
  readiness, transición inválida, `--reason` faltante); `mlops evidence add` (éxito, cada error
  de dominio, lifecycle ausente).
- [x] Tests manifest: paridad explícita para ambos módulos; scratch install deja ambos archivos
  presentes; instalación scratch corre `readiness`/`promote`/`mlops evidence`/`mlops
  status`/`project status`/`checks` sin import faltante.
- [ ] Ejecutar suite completa (`tools/tests/`, `tools/harmessi/tests/`, `tools/ds_init/tests/`)
  para confirmar sin regresión, y `harmessi doctor` para confirmar 0 ERROR nuevo. Pendiente: el
  Python Data Engineer no tiene Bash en este harness -- el Lead corre la suite y `harmessi doctor`
  después de esta invocación.

## Dependencias
`mlops_evidence.py` antes que `readiness.py` (readiness lo consume). `readiness.py` antes que la
CLI. Manifest/parity puede ir en paralelo a la CLI. Tests al final de cada pieza. Depende de
Changes 1 (`lifecycle.py`), 3 (`maturity.py`), 4 (`checks.py`), 5 (`mlops_foundations.py`), todos
cerrados. Reusa `pathguard.py`/`repo.py` sin modificarlos.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->
