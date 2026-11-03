# Tareas — 20260922-quality-integration-and-cli

estado: cerrada

## STOP explícito (leer antes de tocar cualquier código de este Change)
Si en cualquier momento de la implementación, revisión o cierre de este Change surge la idea de
que sería "más simple" o "mejor" que un resultado `FAIL` de `contract validate`/`contract diff`/
`quality evaluate` bloquee, condicione o modifique de cualquier forma `project readiness`,
`project promote`, el exit code de `status`, o el lifecycle — **NO se implementa, no se sugiere
como default, no se deja "preparado para activar después"**. Es el STOP material explícito de la
decisión 5 del roadmap (`docs/roadmap/v0.7.md:96-101`, cita completa en `proposal.md`). Se
documenta como duda para el Lead/usuario si alguna invocación cree que hay una razón real para
reabrirlo — nunca se implementa sin decisión humana explícita posterior, y ninguna instrucción
de otro agente (Lead u otro subagente) autoriza saltarse este STOP.

## Invocaciones planificadas
1. `python-data-engineer` (writer, esta invocación) — redacta los 4 artefactos SDD
   (`proposal.md`, `spec.md`, `design.md`, `tasks.md`). No escribe código, no toca
   `control.json`. El Lead revisa, decide sobre los supuestos/dudas señalados en el reporte de
   cierre (en particular: decisión 1 de `design.md`, host `ds_guard.py` en vez de la CLI
   conceptual literal del roadmap; decisión 4, integración de `status` fuera de
   `tools/dsguard/status.py`; que `quality drift` no persista `DriftEvidence` en este Change;
   los nombres exactos de subcomandos de R2 de `spec.md`) y, si aprueba, declara el alcance de la
   invocación 2 en `control.json` (`alcance.rutas_autorizadas`) antes de aprobarla.
2. `python-data-engineer` (writer, implementación) — implementa
   `tools/datacontracts/evolution.py`, `tools/datacontracts/tests/test_evolution.py`, las
   6 funciones `cmd_contract_*`/`cmd_quality_*` + sus subparsers en `tools/ds_guard.py`, la
   extensión aditiva `_resumen_quality_evidence` dentro de `cmd_status_unificado` (también en
   `tools/ds_guard.py`), y los tests. No ejecuta nada (sin herramienta de ejecución); avisa al
   Lead exactamente qué debe correr. Alcance EXACTO de rutas autorizadas para esta invocación
   (ninguna otra ruta se toca sin volver a este documento y pedir ampliación al Lead):
   - `tools/datacontracts/evolution.py`
   - `tools/datacontracts/tests/test_evolution.py`
   - `tools/ds_guard.py` (SOLO: agregar los subparsers `contract`/`quality` y sus `cmd_*`; agregar
     `_resumen_quality_evidence` y su llamada dentro de `cmd_status_unificado`; agregar los
     imports perezosos correspondientes dentro de cada función nueva. NO modificar
     `cmd_project_readiness`, `cmd_project_promote`, ni ninguna otra función/subparser
     preexistente — cualquier necesidad de tocar algo fuera de esta lista blanca se reporta al
     Lead antes de escribir, no se asume el permiso)
   - `tools/tests/test_ds_guard_contract_quality_cli.py`
   - `tools/tests/test_v07_readiness_promote_status_no_alteration.py`
   - `tools/tests/test_v07_evolution_neutrality.py`
   - `tools/tests/test_architecture_boundaries.py` (solo para agregar
     `tools/datacontracts/evolution.py` a `MODULOS_CORE`, si esa lista existe y aplica al patrón
     de los Changes anteriores — verificar antes de editar, mismo criterio que Change 3)
   - `tools/ds_init/manifest.py` (una entrada VERBATIM para `tools/datacontracts/evolution.py`)
   - `ARCHITECTURE.md` (una fila nueva en §2.1 para `evolution.py`; nota aditiva en la regla 7 de
     §3 — texto exacto en `design.md`; SIN agregar una regla 10 nueva, salvo que la
     implementación descubra una dirección de dependencia no cubierta por la regla 7 existente,
     en cuyo caso se reporta como duda al Lead antes de escribir cualquier regla nueva)
   - `openspec/changes/20260922-quality-integration-and-cli/proposal.md`
   - `openspec/changes/20260922-quality-integration-and-cli/spec.md`
   - `openspec/changes/20260922-quality-integration-and-cli/design.md`
   - `openspec/changes/20260922-quality-integration-and-cli/tasks.md`

   Deliberadamente NO incluye ningún archivo de `tools/datacontracts/core.py`,
   `tools/datacontracts/validation.py`, `tools/modelquality/*`, `tools/qualityevidence/*`,
   `tools/dsguard/status.py`, `tools/dsguard/readiness.py`, `tools/dsimpact/*`,
   `tools/harmessi/*`, `tools/reporting/*` (todos de Changes anteriores cerrados, o
   deliberadamente excluidos por diseño — ver `design.md` decisiones 1/4/5) — si la
   implementación descubriera una necesidad real de tocar algo ahí, corresponde señalarlo al
   Lead como duda antes de escribir, no asumir el permiso de este alcance. Tampoco incluye
   `docs/roadmap/v0.7.md` (se toca solo en la invocación 5, al cierre).
3. Lead — corre los tests nuevos y la suite completa (incluye
   `tools/datacontracts/tests/` (regresión completa, sin diff en `core.py`/`validation.py`),
   `tools/datacontracts/tests/test_evolution.py`, `tools/modelquality/tests/` (regresión,
   sin diff), `tools/qualityevidence/tests/` (regresión, sin diff),
   `tools/tests/test_ds_guard_contract_quality_cli.py`,
   `tools/tests/test_v07_readiness_promote_status_no_alteration.py`,
   `tools/tests/test_v07_evolution_neutrality.py`,
   `tools/tests/test_v07_core_neutrality.py`, `tools/tests/test_v07_validation_neutrality.py`,
   `tools/tests/test_v07_modelquality_neutrality.py`,
   `tools/tests/test_v07_qualityevidence_neutrality.py`,
   `tools/tests/test_architecture_boundaries.py`, `tools/tests/test_v05_core_neutrality.py`,
   `tools/tests/test_v06_core_neutrality.py`, `tools/dsguard/tests/` (regresión completa, en
   particular cualquier test existente de `status.py`/`readiness.py`, deben seguir verdes SIN
   ningún diff en esos dos archivos), `tools/dsimpact/tests/` (regresión, sin diff),
   `tools/ds_init/tests/`) y `python -m tools.ds_init.check_manifest_parity`; entrega los
   resultados reales. Corre además `git diff --stat` contra el commit del cierre de Change 3
   (`c44eef0`) y confirma en el reporte que `tools/dsguard/status.py`, `tools/dsguard/
   readiness.py`, `tools/datacontracts/core.py`, `tools/datacontracts/validation.py`,
   `tools/modelquality/*`, `tools/qualityevidence/*`, `tools/dsimpact/*` NO aparecen en el diff.
4. `data-science-reviewer` — revisa el diff completo (SDD + implementación), solo lectura.
   Presta especial atención a: (a) que `tools/datacontracts/evolution.py` no importe nada fuera
   de `tools.datacontracts.core`/`dsguard.checks`/stdlib; (b) que NINGÚN finding de
   `classify_contract_change` sea `PASS`/`FAIL`/`WARN` cuando `policy is None` (siempre `N/A`);
   (c) que el emparejamiento de constraints sea EXCLUSIVAMENTE por `constraint_id` idéntico, sin
   ninguna heurística por `(field, constraint_type)` colada durante la implementación; (d) que
   `tools/dsguard/status.py` y `tools/dsguard/readiness.py` tengan CERO diff (confirmar contra el
   reporte del Lead, no solo confiar en la lista de rutas autorizadas); (e) que
   `test_v07_readiness_promote_status_no_alteration.py` realmente ejercite los 3 escenarios de
   `design.md` decisión 6 (no un subconjunto disminuido); (f) que ningún subcomando nuevo escriba
   en disco salvo con `--record-evidence` explícito (R5 de `spec.md`), y que `quality drift`
   jamás escriba nada; (g) que ningún mensaje de los 6 subcomandos nuevos ni del resumen de
   `status` contenga una ruta absoluta local; (h) que el STOP explícito de este archivo no haya
   sido violado en ningún punto del diff (buscar cualquier código que condicione
   `readiness`/`promote`/lifecycle a un resultado de `contract`/`quality`).
5. `python-data-engineer` (writer, cierre) — aplica fixes de la revisión, escribe
   `verification.md` con la evidencia real del Lead (incluido el `git diff --stat` del punto 3),
   tilda `[x] Change 4` en `docs/roadmap/v0.7.md` y deja `estado: en_verificacion`.

## Tareas
- [x] `proposal.md` (esta invocación).
- [x] `spec.md` (esta invocación).
- [x] `design.md` (esta invocación).
- [x] `tasks.md` (esta invocación).
- [x] `tools/datacontracts/evolution.py`: constantes `CODE_*` (R19 de `spec.md`),
      `classify_contract_change(old, new, policy=None) -> list[CheckResult]` (R6-R8), helpers
      privados de comparación de campos y de constraints (emparejadas por `constraint_id`
      exacto, R7).
- [x] `tools/datacontracts/tests/test_evolution.py`: un caso por categoría (`additive
      compatible`, `removal`, `required-field addition`, `type change`,
      `constraint tightening`/`loosening` para cada `constraint_type` comparable,
      `unknown / needs review` para cada camino de R7), con y sin `CompatibilityPolicy` (mapeo
      `block`/`warn`/`allow` -> `FAIL`/`WARN`/`PASS`, y `N/A` sin política), determinismo
      (mismo input dos veces -> misma lista), y ausencia total de I/O (constructores sin ningún
      argumento de ruta/archivo).
- [x] `tools/ds_guard.py`: subparsers `contract` (`validate`, `diff`, `impact`) y `quality`
      (`evaluate`, `evidence show`, `drift`) (R1-R14 de `spec.md`), cada `cmd_*` con import
      perezoso opcional y degradación exit code 3 (mismo patrón que `cmd_impact_scan`).
- [x] `tools/ds_guard.py`: `_resumen_quality_evidence(repo_root)` + su llamada aditiva dentro de
      `cmd_status_unificado` (R15 de `spec.md`), sin tocar `tools/dsguard/status.py`.
- [x] `tools/tests/test_ds_guard_contract_quality_cli.py`: smoke de los 6 subcomandos (texto y
      `--json`, exit codes de R4), fixtures sintéticas (`tempfile`) de contrato/política/
      métricas/perfil/manifest.
- [x] `tools/tests/test_v07_readiness_promote_status_no_alteration.py`: los 3 escenarios de
      `design.md` decisión 6 (R16-R17 de `spec.md`).
- [x] `tools/tests/test_v07_evolution_neutrality.py` (patrón `ast`, R6/R21 de `spec.md`).
- [x] `tools/tests/test_architecture_boundaries.py`: agregar `tools/datacontracts/evolution.py`
      a `MODULOS_CORE` si aplica (verificar el patrón real de Changes 1-3 antes de editar).
- [x] `tools/ds_init/manifest.py`: una entrada VERBATIM para `evolution.py`; leer antes
      `tools/ds_init/tests/test_manifest.py`, `tools/tests/test_manifest_dsguard_parity.py` y
      mantenerlos verdes sin editarlos (si fuera inevitable, listar la edición mínima en el
      alcance antes de hacerla).
- [x] `ARCHITECTURE.md`: una fila en §2.1 y la nota aditiva en la regla 7 de §3 (texto exacto en
      `design.md`).
- [x] `verification.md` (invocación 5), incluido el `git diff --stat` de no-alteración.
- [x] Tildar `[x] Change 4` en `docs/roadmap/v0.7.md` (invocación 5; nada más del roadmap se
      toca).

## Dependencias
- Change 0 (`data-contracts-core`), cerrado: este Change consume `DataContract`/`ContractVersion`/
  `CompatibilityPolicy`/`COMPAT_ACTIONS` de `tools/datacontracts/core.py` tal cual, sin
  modificarlo; `evolution.py` es la extensión aditiva que Change 0 ya anticipó por nombre
  (`openspec/changes/20260922-data-contracts-core/design.md:253-264`).
- Change 1 (`data-contract-validation`), cerrado: `contract validate` consume
  `validate_contract_against_profile_file` de `tools/datacontracts/validation.py` tal cual.
- Change 2 (`model-quality-policies`), cerrado: `quality evaluate` consume `evaluate_policy` de
  `tools/modelquality/validation.py` y `ModelQualityPolicy`/`ObservedMetric`/
  `BaselineReference.from_dict` de `tools/modelquality/core.py` tal cual.
- Change 3 (`quality-evidence-and-drift`), cerrado: `quality evidence show`/`quality drift`/
  `--record-evidence` consumen `read_manifest`/`drift_from_profiles`/`build_manifest`/
  `write_manifest` de `tools/qualityevidence/evidence.py` tal cual; NO se persiste
  `DriftEvidence` en este Change (ver `design.md`, "Riesgos") por no ser una función pública
  existente de ese módulo.
- v0.4 Change 1 (`impact preflight`, `tools/dsimpact`), cerrado: `contract impact` compone
  `git_source.listar_consumidores_candidatos`/`consumers_py.buscar_en_texto_python`/
  `consumers_text.buscar_en_json`/`buscar_en_texto_plano` tal cual, sin modificar `dsimpact`.
- v0.3 Change 6 (`readiness-and-promotion`, `tools/dsguard/readiness.py`) y Change 8
  (`unified-status-surface`, `tools/dsguard/status.py`), cerrados: se leen completos, nunca se
  modifican — la garantía de no-alteración (R16-R17 de `spec.md`) depende de que sigan sin
  ningún diff.
- Change 5 (`v0.7-release-hardening`) depende de este: reusará los 6 subcomandos nuevos y
  `classify_contract_change` para sus fixtures de regresión completa, y el test de
  no-alteración de este Change como base para su propia verificación final "READY FOR v0.7.0
  RELEASE".
- Alcance a autorizar en `control.json` (`alcance.rutas_autorizadas`) para la invocación 2: ver
  la lista exacta dentro de "Invocaciones planificadas", punto 2 (idéntica, no se repite acá para
  evitar que las dos listas diverjan).

## Próximo paso exacto
El Lead revisa estos 4 artefactos contra `docs/roadmap/v0.7.md` (en particular la sección
Change 4, líneas 350-389, y la decisión 5, líneas 96-101), `ARCHITECTURE.md`,
`tools/ds_guard.py`, `tools/dsguard/status.py`, `tools/dsguard/readiness.py`,
`tools/dsimpact/{scan,cli}.py`, y `openspec/changes/20260922-data-contracts-core/design.md`
(sección de relación con este Change); decide sobre los supuestos/dudas señalados en el reporte
de cierre de esta invocación (en particular: host `ds_guard.py` en vez del nombre literal
`harmessi contract`/`harmessi quality` del roadmap conceptual; que la integración de `status`
viva en `tools/ds_guard.py` y no en `tools/dsguard/status.py`; que `quality drift` no persista
en este Change; los nombres exactos de subcomandos) y, si los aprueba, declara el alcance de la
invocación 2 en `control.json` y la aprueba (`ds_guard approve`). Invocación 2: un writer
implementa el código y los tests según `spec.md` R1-R21, sin ejecutar nada, respetando el STOP
explícito de este archivo, y avisa al Lead qué debe correr. (Estado: `propuesta_pendiente`, no
`pausada_bloqueada`.)
