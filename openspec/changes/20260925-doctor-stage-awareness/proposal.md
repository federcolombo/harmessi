# Propuesta — 20260925-doctor-stage-awareness

## Problema

Durante el hardening de v0.7 (Change 5, `20260925-v07-release-hardening`, cerrado con veredicto
`READY FOR v0.7.0 RELEASE`), un scratch install fresco en stage `discovery` produjo 4
`[ERROR] HARMESSI-AGENTE-FALTANTE` al correr `harmessi doctor --destino` (uno por cada agente de
`_AGENTES_ESPERADOS`). El Lead releyó el texto ya aprobado de R16/R21 de
`openspec/changes/20260925-v07-release-hardening/spec.md` y confirmó que el gate exige
literalmente 0 `[ERROR]` en AMBOS scratch installs (`experiment` y `discovery`), sin excepción para
`discovery` — no hay ninguna cláusula que exima a `discovery` de ese requisito.

La causa raíz es que `tools/harmessi/doctor.py::_check_agents` (líneas 498-539) no recibe ni
consulta `installation_stage` en absoluto: itera incondicionalmente sobre la tupla hardcodeada
`_AGENTES_ESPERADOS` (4 `(nombre, ruta_rel)`, líneas 74-79) y emite `FAIL` `HARMESSI-AGENTE-FALTANTE`
si cualquiera de los 4 archivos de agente no existe, sin importar el stage instalado. En un
proyecto `discovery`, los agentes legítimamente no se instalan (`tools/ds_init/manifest.py`
declara `stage_minimo="experiment"` para las 4 entradas de agentes, líneas 127-154), por lo que el
check los reporta como faltantes cuando en realidad nunca debieron instalarse en ese stage.

## Objetivo

Hacer que `_check_agents` sea consciente de `installation_stage` (mismo patrón ya existente en
`_check_archivos_administrados`, líneas 376-427), para que `harmessi doctor` dé 0 `[ERROR]` tanto en
`experiment` como en `discovery`, sin dejar de reportar `FAIL` cuando un agente que sí aplica al
stage instalado falta de verdad.

## Evidencia

- `tools/harmessi/doctor.py:498-539` — `_check_agents(destino)`: firma actual sin `control_data`
  ni `installation_stage`; itera `_AGENTES_ESPERADOS` sin condición de stage.
- `tools/harmessi/doctor.py:74-79` — `_AGENTES_ESPERADOS`: tupla hardcodeada de 4
  `(nombre, ruta_rel)`, sin relación con ningún stage.
- `tools/harmessi/doctor.py:376-427` — `_check_archivos_administrados(destino, control_data)`: SÍ
  es consciente de `installation_stage` — si `installation_stage is not None`, filtra con
  `manifest_mod.manifest_para_perfil_y_stage(perfil, installation_stage)`; si es `None` (legacy),
  usa `manifest_mod.manifest_para_perfil(perfil)`. Un archivo de un stage superior al instalado no
  produce ningún `CheckResult` (línea 408-409: `if ruta.exists(): continue`, sin `else` que reporte
  falta — la ausencia esperada de un stage superior simplemente no entra al bucle de reporte porque
  esas entradas ni siquiera están en la lista `entradas` filtrada).
- `tools/harmessi/doctor.py:1047` — `ejecutar()` llama a `_check_agents` pasando solo `destino`:
  `resultados += _ejecutar_check(SECCION_HARMESSI, "HARMESSI-AGENTE", _check_agents, destino)`, sin
  `control_data`, aunque `control_data` ya está disponible en ese punto (calculado en la línea 1039
  y ya usado por `_check_archivos_administrados` en la línea 1044, inmediatamente antes).
- `tools/ds_init/manifest.py:127-154` — las 4 `EntradaManifiesto` de agentes
  (`.claude/agents/python-data-engineer.md`, `data-science-reviewer.md`, `metodologo.md`,
  `notebook-runner.md`) declaran `stage_minimo="experiment"` explícito: según la fuente de verdad
  del proyecto, un agente nunca es parte del stage `discovery`.
- `tools/ds_init/manifest.py:811-830` — `manifest_para_perfil_y_stage(perfil, stage)`: filtra
  `manifest_para_perfil(perfil)` conservando solo entradas cuyo `stage_minimo` sea `stage` o
  anterior en `ORDEN_STAGES` (acumulativo).
- `openspec/changes/20260925-v07-release-hardening/spec.md:73-77,103-104,129-132,143-144` —
  R16/R21 y sus criterios de aceptación: exigen 0 `[ERROR]` de `harmessi doctor --destino` sobre
  scratch installs `experiment` y `discovery`, sin excepción textual para ninguno de los dos.

## Supuestos descartados

- Se descartó que el fix requiera una lista nueva de "agentes por stage": ya existe una fuente de
  verdad canónica (`tools/ds_init/manifest.py::MANIFEST`, vía `manifest_para_perfil_y_stage`) que
  cubre exactamente esta necesidad para las mismas rutas de destino de los 4 agentes, sin
  duplicación.
- Se descartó tratar esto como una relajación del gate: el usuario decidió explícitamente que
  `discovery` NO queda exceptuado; el fix corrige el código para que cumpla el texto ya aprobado,
  no cambia el texto del gate.

## Alcance

- `tools/harmessi/doctor.py`: cambio de firma y cuerpo de `_check_agents` (consciente de
  `installation_stage`, consultando `manifest_para_perfil_y_stage`/`manifest_para_perfil` sobre
  `MANIFEST`), y el call site en `ejecutar()` (línea 1047) para pasarle `control_data`.
- `tools/harmessi/tests/test_doctor.py`: ajuste de los tests existentes que llaman a
  `_check_agents` con la firma vieja (líneas 235-242, `test_agents_ok`/`test_agents_error_si_falta`),
  y tests nuevos que cubran R1-R6 de `spec.md` (instalación `discovery` fresca sin `FAIL` de
  agentes, agente realmente obligatorio y ausente en `experiment` sigue dando `FAIL`, legacy sin
  `installation_stage` sin cambio de comportamiento).
- `docs/roadmap/v0.7.md`: una nota breve registrando este release-blocker y su cierre (no una
  sección nueva).
- Los 4 artefactos SDD de este Change (esta invocación) y `verification.md` (invocación de cierre).

## Fuera de alcance

Explícitamente prohibido tocar en este Change (fijado por el usuario, no ampliable sin nueva
autorización):

- `tools/datacontracts/*`
- `tools/modelquality/*`
- `tools/qualityevidence/*`
- `tools/reporting/*`
- `tools/dsguard/readiness.py`
- `cmd_project_readiness`/`cmd_project_promote` de `tools/ds_guard.py`
- `tools/dsguard/status.py`
- `tools/dsimpact/*`
- cualquier feature de v0.7 (Data Contracts, Model Quality, Quality Evidence)
- `tools/ds_init/manifest.py`/`.ds_init/control.json`: no se modifican salvo que el fix
  legítimamente lo requiera; el análisis de esta invocación concluye que NO lo requiere — el fix
  consume `MANIFEST`/`manifest_para_perfil_y_stage` tal como existen hoy, sin alterarlos.
- `control.json` de este propio Change (`openspec/changes/20260925-doctor-stage-awareness/control.json`):
  no se toca en esta invocación.

## Holdout policy (condicional — solo cambios "sensible")

No aplica. Este Change no toca datos, holdouts ni datasets sellados: es un fix de una herramienta
de diagnóstico de instalación (`harmessi doctor`) sobre archivos de agentes del propio harness, sin
relación con ningún target, feature ni evaluación de modelo.

## Impacto en production-readiness (opcional)

Es un blocker de release de v0.7.0: sin este fix, `harmessi doctor` reporta falsos `[ERROR]` en
cualquier instalación fresca en stage `discovery`, lo cual haría fallar el gate R16/R21 del
hardening ya aprobado. No introduce ni modifica ningún criterio de production-readiness existente
(`tools/dsguard/readiness.py` queda explícitamente fuera de alcance).

## Criterios de aceptación (spec-lite — solo SDD abreviado)

Ver `spec.md` (SDD completo).

## Decisión técnica (design-lite — solo SDD abreviado)

Ver `design.md` (SDD completo).

## Aprobación

- Usuario: Federico Colombo
- Fecha: 2026-09-25
- Alcance aprobado: "Change correctivo doctor-stage-awareness, release-blocking para v0.7.0,
  autorizado explícitamente por el usuario tras determinar que R16/R21 del hardening de v0.7
  (`openspec/changes/20260925-v07-release-hardening/spec.md`) exigen 0 ERROR en el scratch
  discovery sin excepción"
- Versión de artefactos referenciada: HEAD en `eb7819433e7ac2f6b16cfbc2125f4c9563c0be5d`
  (branch `v0.7-dev`), inmediatamente posterior al cierre de Change 5
  (`20260925-v07-release-hardening`, veredicto `READY FOR v0.7.0 RELEASE`)
- Cita o descripción fiel de qué se aprobó: el usuario, al revisar los 4 `[ERROR]`
  `HARMESSI-AGENTE-FALTANTE` del scratch install `discovery` durante el cierre de Change 5, decidió
  explícitamente NO aceptar una excepción para `discovery` frente al texto ya aprobado de R16/R21,
  y en consecuencia: "v0.7.0 permanece NOT READY hasta corregir esto" y autorizó "este Change
  correctivo mínimo y release-blocking, ANTES de publicar v0.7.0".

## Motivo de rechazo

No aplica (Change no descartado).

## Desacuerdo registrado

No aplica (sin rondas de revisión con desacuerdo todavía).
