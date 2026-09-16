# Tareas — 20260914-fix-harness-version-drift

estado: cerrada

## Invocaciones planificadas
<!-- rol, momento del ciclo, y qué produce cada una -->
- Python Data Engineer, al cerrar implementación: aplicar `regenerar_control()` una
  vez sobre `este mismo repo (checkout local de Harmessi)` para corregir su
  `.ds_init/control.json` real. Produce: `control.json` actualizado con
  `harness_version` y `archivos` vigentes.
- Python Data Engineer, al cerrar implementación: correr
  `python -m pytest tools/ds_init/tests/test_control_file.py` y `harmessi doctor` (o
  el entrypoint equivalente). Produce: constancia del resultado en la sección de
  verificación al cerrar el cambio.

## Tareas
- [x] Agregar `fecha_utc` opcional a `generar_control()` en `tools/ds_init/control.py`.
- [x] Implementar `regenerar_control()` en `tools/ds_init/control.py`.
- [x] Agregar tests nuevos a `tools/ds_init/tests/test_control_file.py` (repo git
      temporal, nunca este repo).
    - [x] preserva `configuracion` exactamente
    - [x] preserva `fecha_utc` original
    - [x] actualiza `harness_version` al valor vigente
    - [x] reconstruye `archivos` exclusivamente desde el manifest vigente (no unión)
    - [x] no conserva entradas obsoletas que ya no estén en el manifest (test con una
          entrada ficticia obsoleta en `control_previo["archivos"]`)
- [x] Invocación planificada: aplicar `regenerar_control()` una vez sobre
      `este mismo repo (checkout local de Harmessi)` para corregir su `.ds_init/control.json`
      real.
- [x] Invocación planificada: correr
      `python -m pytest tools/ds_init/tests/test_control_file.py` y
      `harmessi doctor` (o el entrypoint equivalente), y dejar constancia del
      resultado en la sección de verificación al cerrar el cambio.

## Dependencias
Las tareas 1-2 (control.py) deben completarse antes de la 3 (tests) y antes de la 4
(invocación real sobre este repo). La tarea 5 (verificación) depende de que 1-4 estén
aplicadas.

Aclaración de alcance temporal: aplicar `regenerar_control()` sobre este repo (tarea 4)
es una recalibración puntual — no evita que `harmessi doctor` vuelva a reportar drift
más adelante durante v0.3. Ver `proposal.md` § Supuestos descartados.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->
No aplica — estado actual es `propuesta_pendiente`, no `pausada_bloqueada`.

## Verificación

**Tests unitarios** — `python -m unittest tools.ds_init.tests.test_control_file -v`:
10/10 tests OK (4 preexistentes sin regresión + 6 nuevos:
`test_generar_control_sin_fecha_utc_estampa_ahora`,
`test_preserva_configuracion_exactamente`, `test_preserva_fecha_utc_original`,
`test_actualiza_harness_version_al_valor_vigente`,
`test_reconstruye_archivos_exclusivamente_desde_manifest_vigente`,
`test_no_conserva_entradas_obsoletas`).

**Suite completa de `ds_init`** —
`python -m unittest discover -s tools/ds_init/tests -p "test_*.py"`: 59/59 tests OK,
sin regresiones en ningún otro módulo (`test_manifest`, `test_preflight`,
`test_settings_merge`, `test_writer_staging`, `test_cli`,
`test_integracion_instalacion`, `test_leakage_check`, `test_control_file`).

**Aplicación real sobre este repo** (tarea 4) — se invocó `regenerar_control()` una vez
sobre `.ds_init/control.json` de este mismo repo. Resultado verificado:
- `harness_version`: `"0.1.0"` → `"0.2.0"`.
- `fecha_utc`: sin cambios, `"2026-09-09T18:08:09Z"` (preservada tal como exigía el
  criterio de aceptación).
- `configuracion`: sin cambios.
- `archivos`: de 10 a 52 entradas — se agregaron 42 rutas (todo el tooling incorporado
  por los commits `24c07e4`, `b653e6a`, `07f4c14` posteriores al install original:
  `tools/dsguard/*.py`, `tools/nbrunner/*.py`, `tools/ds_profile/*.py`,
  `tools/ds_guard.py`, `.claude/skills/lead-data-scientist/{kdd,decision-ledger,eda}.md`
  y sus templates, `.claude/guardrails.json`), ninguna ruta original de las 10 se quitó.

**`harmessi doctor` antes/después** (tarea 5):
- Antes: 25 [OK], 10 [WARN], 0 [ERROR]. De esos 10 WARN: 1 era `HARMESSI-VERSION`
  (harness_version desactualizado), 8 eran `HARMESSI-DRIFT` (archivos administrados
  originales cuyo hash ya no coincidía con lo registrado — `SKILL.md`, `sdd.md`,
  `verificador.md`, `settings.json`, los 4 `.claude/agents/*.md` — habían sido
  modificados por commits posteriores sin refrescar `control.json`), y 1 era
  `CORE-WORKING-TREE` (cambios sin confirmar, esperable durante el desarrollo del
  change, no relacionado con el fix).
- Después: 27 [OK], 1 [WARN], 0 [ERROR]. `HARMESSI-VERSION` = OK. `HARMESSI-DRIFT` = OK
  ("Ningún archivo administrado difiere de su hash registrado") — los 8 WARN de drift
  real desaparecieron como efecto correcto de recalcular hashes contra el contenido
  actual, no solo el de versión. El único WARN remanente es `CORE-WORKING-TREE`
  (esperado, cambios de este mismo change sin commitear todavía).

**Revisión de `data-science-reviewer`**: sin hallazgos bloqueantes. Dos observaciones no
bloqueantes, dejadas sin acción por decisión del Lead (no requeridas por los criterios
de aceptación aprobados, no representan un defecto funcional):
1. `regenerar_control()` no valida explícitamente que `control_previo` tenga las claves
   `perfil`/`configuracion` (produciría `KeyError` sin mensaje claro si faltaran) ni que
   los archivos del manifiesto existan realmente en destino (produciría
   `FileNotFoundError` si no) — comportamiento ya documentado como asunción explícita
   en el docstring de la función, no cubierto por los AC de `proposal.md`.
2. `regenerar_control()` importa `manifest_para_perfil` con `import` local dentro de la
   función en vez de al tope del módulo — asimetría cosmética con el resto de
   `control.py`, sin import circular real, sin impacto funcional.

**Gate de implementación**: se detectó que `control.json` del change no tenía
declaradas en `alcance.rutas_autorizadas` las rutas reales de implementación (solo los
3 artefactos SDD del scaffold inicial) — se corrigió agregando
`tools/ds_init/control.py`, `tools/ds_init/tests/test_control_file.py` y
`.ds_init/control.json` a esa lista (ya estaban nombradas textualmente en
`## Alcance` de `proposal.md`, así que no es una ampliación de alcance sin aprobar,
solo sincronizar el campo machine-checked con lo ya aprobado en prosa).
`ds_guard validate --gate implementacion` pasa sin hallazgos tras esa corrección.

**Resultado final**: todos los criterios de aceptación de `proposal.md` §
Criterios de aceptación (spec-lite) se cumplieron con evidencia real, sin pérdida de
`fecha_utc` histórica, sin romper `writer.py` (test de no-regresión pasa), sin
introducir escritura atómica nueva (documentado como decisión explícita, no como
omisión).
