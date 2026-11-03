# Spec — 20260925-doctor-stage-awareness

## Requisitos

- **R1 — Instalación `experiment` fresca sin `ERROR` de agentes**: un scratch install fresco en
  stage `experiment` no produce ningún `[ERROR]` `HARMESSI-AGENTE-FALTANTE` (ni ningún otro
  `[ERROR]` nuevo introducido por este Change) al correr `harmessi doctor --destino`.
- **R2 — Instalación `discovery` fresca sin `ERROR` de agentes**: un scratch install fresco en
  stage `discovery` no produce ningún `[ERROR]` `HARMESSI-AGENTE-FALTANTE` al correr
  `harmessi doctor --destino`, porque ningún agente aplica a ese stage (`stage_minimo="experiment"`
  en `tools/ds_init/manifest.py` para las 4 entradas de agentes).
- **R3 — Un agente realmente obligatorio y ausente sigue dando `ERROR`**: si el `installation_stage`
  instalado sí incluye un agente dado (según `manifest_para_perfil_y_stage`) y el archivo de ese
  agente falta en disco, `_check_agents` sigue emitiendo `FAIL` `HARMESSI-AGENTE-FALTANTE` para ese
  agente, exactamente como hoy.
- **R4 — No se silencian errores globalmente**: el fix es específico a la relación
  agente↔stage_minimo; no cambia la severidad, el código o el comportamiento de ningún otro check
  de Doctor (`_check_archivos_administrados`, `_check_hashes_drift`, `_check_skill_lead_data_scientist`,
  `_check_settings`, `_check_hooks`, `_check_installation_stage`, etc. quedan bit a bit iguales).
- **R5 — Backward compatibility en proyectos existentes**: `_check_agents` preserva exactamente el
  comportamiento actual en los dos casos que ya existían antes de este Change: (a) `control_data`
  es `None` (sin `control.json` legible) — se siguen considerando los 4 agentes como esperados,
  igual que hoy; (b) `control_data` no `None` pero sin clave `installation_stage` (legacy) — se
  siguen considerando los 4 agentes como esperados, igual que hoy. Ningún proyecto ya instalado en
  `experiment`, `production_candidate` o `production` cambia de resultado en `HARMESSI-AGENTE*`
  (en esos 3 stages los 4 agentes ya aplican hoy y siguen aplicando).
- **R6 — Fuente de verdad única, sin lista duplicada**: la determinación de qué agentes aplican al
  `installation_stage` instalado se hace consultando `tools/ds_init/manifest.py`
  (`manifest_para_perfil_y_stage`/`manifest_para_perfil` sobre las rutas `destino` de
  `_AGENTES_ESPERADOS`), nunca mediante una lista nueva de "agentes por stage" ni una condición
  hardcodeada tipo `if stage == "experiment"`.

## Criterios de aceptación

- **R1**: Given un repo git temporal recién inicializado, When se instala el perfil
  `python-jupyter-data` con `stage="experiment"` (`ds_init_writer.instalar`/CLI equivalente) y
  luego se corre `harmessi doctor --destino` (o `doctor_mod.ejecutar(destino)`) sobre ese repo,
  Then ningún resultado tiene `nivel == "ERROR"` con `codigo == "HARMESSI-AGENTE-FALTANTE"`, y el
  conteo total de `[ERROR]` es 0.
- **R2**: Given un repo git temporal recién inicializado, When se instala el perfil
  `python-jupyter-data` con `stage="discovery"` y luego se corre `harmessi doctor --destino` sobre
  ese repo, Then ningún resultado tiene `nivel == "ERROR"` con `codigo == "HARMESSI-AGENTE-FALTANTE"`,
  y `_check_agents(destino, control_data)` no devuelve ningún `CheckResult` cuyo `subject` sea la
  ruta de alguno de los 4 agentes (ni `PASS`, ni `FAIL`, ni `WARN`); el conteo total de `[ERROR]`
  es 0.
- **R3**: Given una instalación real en stage `experiment` (o cualquier stage donde el agente
  aplique según `manifest_para_perfil_y_stage`) a la que se le borra manualmente el archivo de un
  agente (p. ej. `.claude/agents/notebook-runner.md`), When se corre `_check_agents(destino,
  control_data)`, Then el resultado incluye un `CheckResult` con `status == checks.STATUS_FAIL` y
  `code == "HARMESSI-AGENTE-FALTANTE"` para ese agente.
- **R4**: Given el diff final de este Change sobre `tools/harmessi/doctor.py`, When se inspecciona
  con `git diff`, Then el único cuerpo de función modificado (fuera de imports/firma/call site) es
  `_check_agents`, y ninguna otra función `_check_*` ni su firma cambia.
- **R5**: Given (a) `control_data is None`, o (b) `control_data` es un dict sin clave
  `installation_stage` (legacy), When se corre `_check_agents(destino, control_data)` sobre una
  instalación completa real (los 4 agentes presentes en disco), Then el resultado es idéntico
  (mismos códigos, mismos `status`, mismo conteo) al que produce el código anterior a este Change
  para esos mismos dos casos; en particular, sobre este propio repositorio (`installation_stage`
  ya declarado `"experiment"` en su `.ds_init/control.json`) el resultado de `harmessi doctor`
  no cambia de manera observable.
- **R6**: Given el código final de `_check_agents`, When se lee su implementación, Then la
  determinación de agentes aplicables al stage se resuelve exclusivamente vía
  `tools.ds_init.manifest.manifest_para_perfil_y_stage`/`manifest_para_perfil` (mismas funciones que
  usa `_check_archivos_administrados`) sobre las rutas `destino` de `MANIFEST`, y no existe en el
  diff ninguna lista nueva de agentes-por-stage ni ninguna comparación literal contra el string de
  un stage particular (`if installation_stage == "experiment"` o equivalente) fuera del propio
  `ORDEN_STAGES`/`manifest_para_perfil_y_stage` ya existentes.

## Unidad de análisis / grain (condicional)

No aplica — este Change no trabaja sobre un dataset ni define observaciones/filas; opera sobre
resultados de checks de una herramienta de diagnóstico (`harmessi doctor`).

## Cutoff / information boundary (condicional)

No aplica — no hay target temporal ni fecha de corte involucrados.

## Baseline (condicional)

No aplica — no es un Change de modelado.

## Métrica primaria (condicional)

No aplica.

## Métricas secundarias (opcional)

No aplica.
