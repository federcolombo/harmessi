# Verificación — 20260925-doctor-stage-awareness

Evidencia real aportada por el Lead, ordenada por los requisitos de `spec.md`. Los números salen de
las corridas, no de memoria. Este `verification.md` cierra el Change correctivo que resuelve el
release-blocker registrado en `docs/roadmap/v0.7.md` tras el cierre de Change 5
(`v0.7-release-hardening`).

## (a) Contexto del release-blocker

Tras cerrar Change 5 con veredicto `READY FOR v0.7.0 RELEASE`, un scratch install fresco en stage
`discovery` reveló que `harmessi doctor` reportaba 4 `[ERROR] HARMESSI-AGENTE-FALTANTE` falsos: los
4 archivos de agente tienen `stage_minimo="experiment"` en el manifest y legítimamente no se
instalan en `discovery`, pero `tools/harmessi/doctor.py::_check_agents` no era consciente de
`installation_stage` (a diferencia de `HARMESSI-ARCHIVOS-ESPERADOS`, que sí lo es), violando R16/R21
del hardening ya aprobado. Este Change (`_check_agents` + call site en `ejecutar()`, ambos en
`tools/harmessi/doctor.py`) corrige el defecto haciendo que la función consulte
`manifest_para_perfil_y_stage` como única fuente de verdad, sin lista duplicada.

## (b) Regresión de la suite del paquete

- **Ciclo de remediación pre-revisión**: un test de smoke se ajustó para neutralizar el artefacto
  conocido de scratch sin `.venv` (mismo mecanismo de neutralización ya existente en el archivo para
  otros smokes; no es lógica nueva, es la aplicación del patrón ya aprobado).
- `pytest tools/harmessi -q` (post-fix): **99 passed, 0 failed**.
- `pytest tools -q` completo: **no se corrió** en esta invocación. El usuario autorizó
  explícitamente omitirlo porque el fix queda confinado a Doctor/installer
  (`tools/harmessi/doctor.py` + `tools/harmessi/tests/test_doctor.py`), sin tocar ninguna feature de
  v0.7. Queda registrado como omisión autorizada, no como pendiente abierto.

## (c) Scratch installs reales — antes/después del fix

- **Scratch `experiment`** (`.venv --without-pip`, mismo criterio que v0.6/v0.7 para evitar el
  artefacto conocido de `RUNTIME-INTERPRETE`): `harmessi doctor --destino` → **27 OK, 1 WARN, 0
  ERROR, 1 N/A**. Se mantiene en 0 ERROR (ya lo estaba antes del fix, dado que `experiment` sí
  requiere los 4 agentes).
- **Scratch `discovery`** (mismo criterio): `harmessi doctor --destino` → **23 OK, 1 WARN, 0 ERROR,
  1 N/A**.
  - **Antes del fix**: 4 `[ERROR] HARMESSI-AGENTE-FALTANTE` (los 4 agentes de `stage_minimo=
    "experiment"`, no aplicables a `discovery`).
  - **Después del fix**: **0 ERROR**.
  - **Este es el resultado que resuelve el release-blocker**: confirma que `_check_agents` ahora
    filtra correctamente por `installation_stage` usando la misma fuente única de verdad
    (`manifest_para_perfil_y_stage`) que el resto del doctor, sin introducir una lista de agentes
    duplicada ni hardcodeada.
- `harmessi doctor` sobre este propio repo: **26 OK, 14 WARN** (preexistente, pendiente de la
  alineación de versión canónica que está en un stash aparte, no relacionado con este Change), **0
  ERROR**, 1 N/A.

## (d) Chequeos transversales

- `check_manifest_parity`: **OK**.
- `git diff --check`: **limpio** (sin conflictos de whitespace).
- Privacy sweep: **sin hallazgos**.
- `ds_guard validate --gate implementacion`: **sin findings**.

## (e) Revisión (`data-science-reviewer`, invocación 4)

Revisó el diff completo de la invocación 2 contra los 4 artefactos SDD del Change:

- Confirmó, línea por línea, que la implementación coincide exactamente con `design.md`, **sin
  desviaciones**.
- Confirmó que la fuente única de verdad (`manifest_para_perfil_y_stage`) se usa sin ninguna lista
  duplicada de agentes.
- Confirmó, con un test real (no mock), que un agente genuinamente faltante en el stage que lo
  requiere sigue dando `FAIL` (comportamiento de R3 preservado).
- Confirmó que el comportamiento legacy (sin `installation_stage`, o `control_data=None`) no cambió.
- Confirmó, vía `git diff`, que **cero archivos** quedaron fuera del alcance autorizado.

**1 hallazgo NO bloqueante**: gap de cobertura — falta un test explícito del caso positivo de
`_check_agents` con `stage="experiment"` vía la rama stage-aware (ya cubierto indirectamente por el
scratch install real de (c)). El Lead decidió aceptarlo sin fix adicional, dado que el
comportamiento ya está verificado a nivel de integración con datos reales.

**0 hallazgos bloqueantes. 0 ciclos de remediación post-revisión usados.**

## Resultado final

**Release-blocker RESUELTO.**

Razones concretas:

- El síntoma exacto que originó el blocker (4 `[ERROR] HARMESSI-AGENTE-FALTANTE` falsos en scratch
  `discovery`) pasó de **4 ERROR a 0 ERROR** en una corrida real, no simulada.
- Scratch `experiment` se mantiene en **0 ERROR**, confirmando que el fix no alteró el
  comportamiento correcto ya existente para el stage que sí requiere los 4 agentes (R3 preservado).
- `pytest tools/harmessi -q` en verde (**99 passed, 0 failed**) tras el ciclo de remediación
  pre-revisión.
- `check_manifest_parity` OK, `git diff --check` limpio, privacy sweep sin hallazgos, `ds_guard
  validate --gate implementacion` sin findings.
- Revisión de `data-science-reviewer` con **0 hallazgos bloqueantes** y confirmación línea por línea
  de que la implementación coincide con `design.md` sin desviaciones ni archivos fuera de alcance;
  el único hallazgo no bloqueante (gap de cobertura de un caso ya verificado por integración) fue
  aceptado explícitamente sin fix.
- `pytest tools -q` completo no se corrió, por autorización explícita del usuario dado el alcance
  confinado del fix (Doctor/installer, sin tocar features de v0.7); queda registrado como omisión
  autorizada, no como deuda oculta.

**Aclaración explícita**: este veredicto resuelve el release-blocker específico de
`_check_agents`/`installation_stage`. No re-corre ni sustituye el gate completo de Change 5
(`v0.7-release-hardening`); la nota de `docs/roadmap/v0.7.md` queda actualizada para reflejar la
resolución, pero cualquier decisión final de push/merge/tag/release de v0.7.0 sigue sujeta a
aprobación humana explícita, tal como ya estaba establecido en el cierre de Change 5.
