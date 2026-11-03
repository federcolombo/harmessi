# Tareas — 20260915-mlops-foundations-experiment

estado: cerrada

## Invocaciones planificadas
<!-- rol, momento del ciclo, y qué produce cada una -->
- Python Data Engineer (implementación + tests, invocación única): `tools/dsguard/mlops_foundations.py`
  + grupo `mlops` en `ds_guard.py` + manifest + tests, todo en un solo paso.
- Data Science Reviewer (revisión, DESPUÉS de implementación completa): revisa el diff. Solo
  informa hallazgos.
- Python Data Engineer (post-revisión, planificada): corrige si hace falta,
  `estado: en_verificacion`.
- Python Data Engineer (cierre, planificada): `verification.md` con evidencia real,
  `estado: cerrada`.

## Tareas
- [x] `tools/dsguard/mlops_foundations.py`: `check_reproducibilidad`, `check_versionado`,
  `check_lineage`, `check_artifacts` (cada una `(repo_root, project_stage) -> CheckResult`).
- [x] `_resolver_project_stage`/lógica con-dato en `evaluar_foundations`: `.harmessi/project.json`
  ausente → `None` + `CheckResult N/A` informativo; corrupto → propaga, se vuelve
  `technical_error`; válido → `project_stage` real.
- [x] `evaluar_foundations(repo_root)`: read-only, corre los 4 checks vía `checks.ejecutar_checks`,
  incluye el resultado informativo de `project_stage`.
- [x] `registrar_evidencia(repo_root, resultados)`: snapshot en `evidencia[]` de cada capability,
  nunca toca `estado`, escritura atómica, requiere lifecycle existente.
- [x] Grupo `mlops` en `ds_guard.py`: `status [--json]` (read-only), `record [--json]` (evalúa +
  persiste).
- [x] `tools/ds_init/manifest.py`: entrada VERBATIM de `mlops_foundations.py`.
- [x] `tools/tests/test_manifest_dsguard_parity.py`: test explícito hardcodeado para
  `mlops_foundations.py`.
- [x] `tools/ds_init/tests/test_integracion_instalacion.py`: agregar `mlops_foundations.py` a
  `archivos_clave`.
- [x] Tests — resolución de `project_stage`: discovery (N/A con mensaje específico),
  `.harmessi/project.json` ausente (N/A con mensaje de `project init`, distinto del de
  discovery), `.harmessi/project.json` corrupto (`technical_error`), `project_stage` válido
  no-discovery (evaluación real).
- [x] Tests — `check_reproducibilidad`: PASS (todo en regla), WARN por working tree sucio, WARN
  por `data/` sin fingerprint, WARN por falta de lockfile, combinaciones.
- [x] Tests — `check_versionado`: PASS sin `data/`, PASS con `data/`+fingerprint, WARN con `data/`
  sin fingerprint.
- [x] Tests — `check_lineage`: N/A sin lifecycle, WARN con lifecycle (con y sin evidencia
  indirecta de pasos KDD) — confirmar que NUNCA da PASS.
- [x] Tests — `check_artifacts`: PASS con profile presente, PASS con `models/`/`reports/` con
  contenido, WARN sin nada.
- [x] Tests — `evaluar_foundations` read-only: bytes de `lifecycle/state.json` y
  `.harmessi/project.json` idénticos antes/después, en todos los casos anteriores.
- [x] Tests — `evaluar_foundations` no frena ante excepción de un check individual (mock de una
  excepción en uno de los 4, confirmar que los otros 3 igual se evalúan).
- [x] Tests — `registrar_evidencia`: agrega snapshot correcto a las 4 capabilities, nunca toca
  `estado` (bytes de ese campo específico idénticos), requiere lifecycle existente (error claro
  si no), dos llamadas seguidas agregan dos entradas (no dedup, no error).
- [x] Tests — CLI: `mlops status`/`mlops record` end-to-end vía subprocess real contra un repo git
  temporal (con y sin `project.json`/`lifecycle`), exit codes correctos.
- [x] Tests — manifest: `mlops_foundations.py` con entrada VERBATIM (test explícito); scratch
  install deja el archivo presente.
- [x] Ejecutar suite completa (`tools/tests/`, `tools/harmessi/tests/`, `tools/ds_init/tests/`)
  para confirmar sin regresión, y `harmessi doctor` para confirmar 0 ERROR nuevo (los 3 WARN de
  drift existentes no se tocan).

## Dependencias
Los 4 checks antes que `evaluar_foundations`; `evaluar_foundations` antes que
`registrar_evidencia`/CLI; manifest/parity puede ir en paralelo; tests al final de cada pieza.
Depende de Changes 1 (`lifecycle.py`), 2 (`kdd_compat.py` indirectamente, vía lifecycle), 3
(`maturity.py`), 4 (`checks.py`), todos cerrados.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->
