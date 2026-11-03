# Tareas — 20260915-unified-status-surface

estado: cerrada

## Invocaciones planificadas
<!-- rol, momento del ciclo, y qué produce cada una -->
- Python Data Engineer (implementación + tests, invocación única, puede requerir varias
  reanudaciones por límite de turnos — no cuentan como nuevas delegaciones): `status.py` +
  extensión de `cmd_status`/parser en `ds_guard.py` + manifest + toda la batería de tests de
  `spec.md`, siguiendo `design.md` al pie de la letra.
- Data Science Reviewer (revisión, DESPUÉS de implementación completa): revisa el diff. Solo
  informa hallazgos.
- Python Data Engineer (post-revisión, si hace falta): corrige, `estado: en_verificacion`.
- Python Data Engineer (cierre, planificada): `verification.md` con evidencia real,
  `estado: cerrada`.

## Tareas
- [x] `tools/dsguard/status.py` (nuevo): `next_target(project_stage) -> Optional[str]` (tabla de
  sucesión pública, sin importar símbolos privados de `readiness.py`).
- [x] `_seccion_project(repo_root)`: reusa `maturity.leer_estado`/`maturity.estado_riesgo`;
  maneja ausente (uninitialized) y corrupto (tecnico=True) sin excepción.
- [x] `_seccion_installation(repo_root)`: `json.load()` plano de `.ds_init/control.json`; si
  `installation_stage` ausente, import perezoso opcional de `tools.ds_init.legacy` (try/except
  ImportError + try/except Exception alrededor de la llamada) para inferencia; nunca escribe
  nada.
- [x] `_seccion_alignment(project_stage, installation_stage)`: `"aligned"`/`"sync_needed"`/
  `"ahead"`/`"unknown"` según R5 de `spec.md`.
- [x] `_seccion_lifecycle(repo_root)`: reusa `lifecycle.leer_estado`; resumen de 8 fases CRISP-DM
  y 5 pasos KDD canónicos (nunca las 10 etapas legacy); maneja ausente/corrupto sin excepción.
- [x] `_seccion_mlops_foundations(repo_root)`: reusa `mlops_foundations.evaluar_foundations` tal
  cual, sin reinterpretar severidad.
- [x] `_seccion_mlops_evidencia(repo_root, tier, capabilities)`: por cada capability,
  `mlops_evidence.evidencia_valida(repo_root, tier, cap)`, reusa el `detalle` devuelto tal cual.
  Usada para `production_readiness` (5) y `operations` (7).
- [x] Proporcionalidad por stage (R10): colapsar `production_readiness`/`operations` según
  `project_stage`, salvo `--verbose`.
- [x] `_seccion_readiness(repo_root, project_stage)`: `next_target`; si `None`, mensaje de stage
  final; si no, `readiness.evaluar_readiness(repo_root, next_target)` (sin reimplementar),
  deriva `ready`/`technical_error`/`blocking`/`warnings` según R4 de `spec.md`.
- [x] `_seccion_harness(repo_root)`: import perezoso opcional de `tools.harmessi.doctor` +
  `try/except Exception` alrededor de `doctor.ejecutar(repo_root)`; si falla o no disponible,
  `disponible=False` con mensaje claro, nunca excepción cruda.
- [x] `evaluar_status(repo_root) -> dict`: orquesta las 7 secciones, siempre solo lectura, nunca
  lanza excepción no controlada.
- [x] `formatear_texto(status, verbose=False) -> str`: output humano compacto y jerárquico según
  §22 del brief (o variante mejor, manteniéndolo corto/escaneable).
- [x] `formatear_json(status) -> dict` (o str ya serializado) — determinista, sin duplicar campos
  redundantes gigantes, documentado como experimental/interno.
- [x] `ds_guard.py`: `p_status.add_argument("--change-id", required=False)` (era `True`);
  `p_status.add_argument("--verbose", action="store_true")`; `cmd_status` bifurca: con
  `--change-id` → comportamiento actual EXACTO sin tocar una línea de esa rama; sin
  `--change-id` → llama `status.evaluar_status`/`formatear_texto`/`formatear_json`.
- [x] `tools/ds_init/manifest.py`: entrada VERBATIM de `status.py` (mismo `stage_minimo` que el
  resto de `tools/dsguard/*.py`: `"discovery"`, default).
- [x] `tools/tests/test_manifest_dsguard_parity.py`: clase explícita para `status.py`.
- [x] `tools/ds_init/tests/test_integracion_instalacion.py`: agregar `status.py` a
  `archivos_clave`; confirmar que `ds_guard status` (sin `--change-id`) corre sin `ImportError`
  desde un destino scratch instalado (con `harness.disponible=False`, esperado).
- [x] Tests: `--change-id` existente sin cambios (regresión byte a byte donde aplique) --
  `tools/tests/test_status.py::TestCliNoColision`.
- [x] Tests: los 4 stages (discovery/experiment/production_candidate/production) — proporcionalidad
  de `mlops.production_readiness`/`operations`, `next_target` correcto por stage --
  `TestProporcionalidadPorStage`.
- [x] Tests: alignment — iguales, project mayor, installation mayor, legacy con inferencia
  disponible, legacy sin `tools.ds_init` disponible (mock de ImportError) --
  `TestSeccionInstallationYAlignment`.
- [x] Tests: risk — null/low/medium/high; `production_candidate` con risk null refleja el FAIL de
  readiness sin que `status` decida nada -- `TestSeccionProject`.
- [x] Tests: lifecycle — parcial/completo/ausente/corrupto -- `TestSeccionLifecycle`.
- [x] Tests: foundations — PASS/WARN/N-A tal cual (nunca reinterpretado a FAIL), technical_error
  si project.json corrupto -- `TestSeccionFoundations` (technical_error de project.json corrupto
  cubierto indirectamente vía `TestSeccionProject.test_corrupto_tecnico` + `TestSeccionReadiness`
  para el caso equivalente de lifecycle corrupto, que es el escenario technical_error real de
  R4/AC).
- [x] Tests: readiness — READY, NOT READY, technical_error visible explícitamente, production sin
  next_target -- `TestSeccionReadiness`, `TestProporcionalidadPorStage.test_production_ambos_detalle_sin_next_target`.
- [x] Tests: evidence — válida/ausente/obsoleta, para al menos una capability de cada tier --
  `TestSeccionEvidencia`.
- [x] Tests: harness — disponible (corrido desde este repo, conteos coinciden con `harmessi
  doctor` real) y no disponible (mock de ImportError o fixture sin `tools/harmessi/`), sin
  excepción en ningún caso, resto de secciones no se corta -- `TestSeccionHarness`.
- [x] Tests: read-only — bytes idénticos de project.json/control.json/lifecycle/state.json
  antes/después, en TODOS los escenarios anteriores -- `TestReadOnly`.
- [x] Tests: JSON — determinista, serializable, no muta -- `TestFormatearJson`.
- [x] Tests: output humano — determinista, compacto, sin hallazgos duplicados -- `TestFormatearTexto`.
- [ ] Ejecutar suite completa (`tools/tests/`, `tools/harmessi/tests/`, `tools/ds_init/tests/`)
  para confirmar sin regresión, y `harmessi doctor` para confirmar el mismo baseline (26 OK / 5
  WARN / 0 ERROR / 1 N/A) — no corregir WARN/N-A existentes salvo bug real revelado. PENDIENTE: el
  Python Data Engineer no tiene Bash/ejecución en este harness -- el Lead debe correr esto y
  reportar el resultado antes de cerrar el change.

## Dependencias
`status.py` depende de (sin modificarlos) `maturity.py` (Change 3), `lifecycle.py` (Change 1),
`checks.py` (Change 4), `mlops_foundations.py` (Change 5), `readiness.py`/`mlops_evidence.py`
(Change 6), y opcionalmente (import perezoso) `tools.harmessi.doctor`/`tools.ds_init.legacy`
(Change 7/Bloque 2). Manifest/parity puede ir en paralelo a la CLI. Tests al final de cada pieza.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->
