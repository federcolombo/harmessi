# Tareas — 20260925-doctor-stage-awareness

estado: cerrada

## Invocaciones planificadas

1. **[Esta invocación] `python-data-engineer` — SDD (sin código)**: redacta `proposal.md`,
   `spec.md`, `design.md`, `tasks.md`. No toca `control.json`, no toca código, no corre nada.
2. **`python-data-engineer` — implementación + tests**: aplica el Cambio 1-4 de `design.md`
   exclusivamente sobre:
   - `tools/harmessi/doctor.py` (firma y cuerpo de `_check_agents`, líneas 498-539; call site en
     `ejecutar()`, línea 1047).
   - `tools/harmessi/tests/test_doctor.py`:
     - adapta `test_agents_ok`/`test_agents_error_si_falta` (líneas 235-242) a la firma nueva
       (`_check_agents(destino, control_data)`).
     - agrega tests nuevos: (a) `_check_agents` sobre instalación real `stage="discovery"` da
       0 resultados con `subject` en las 4 rutas de agentes (R2); (b) `_check_agents` sobre
       instalación real `stage="experiment"` con un agente borrado sigue dando `FAIL`
       `HARMESSI-AGENTE-FALTANTE` (R3); (c) `_check_agents` con `control_data=None` y con
       `control_data` sin `installation_stage` reproducen el resultado legacy sin cambios (R5);
       (d) smoke de `doctor_mod.ejecutar(destino)` sobre scratch `discovery` con 0 `[ERROR]`
       (R2, a nivel integración, no solo función aislada).
   - `docs/roadmap/v0.7.md`: nota breve (no sección nueva) registrando el release-blocker y su
     estado ("en curso" en esta invocación).
   No toca ningún archivo de la lista "Fuera de alcance" de `proposal.md`. No toca
   `.ds_init/manifest.py` ni `.ds_init/control.json`. No corre el gate completo de v0.7 (eso es
   invocación 3).
3. **Lead (`SKILL.md`, sin subagente) — gate**: corre `pytest tools/harmessi -q` (y, si aplica,
   `pytest tools -q` completo) sobre el estado resultante de la invocación 2; corre scratch
   installs frescos `experiment` y `discovery` + `harmessi doctor --destino` sobre ambos,
   confirmando 0 `[ERROR]` en los dos (repitiendo el procedimiento de R16/R21 del hardening de
   v0.7, esta vez con el fix aplicado).
4. **`data-science-reviewer` — revisión**: revisa el diff completo de la invocación 2 contra los
   4 artefactos SDD de este Change (¿la firma/cuerpo final coincide con `design.md`? ¿algún archivo
   fuera de alcance quedó tocado? ¿R1-R6 de `spec.md` quedan verificables con lo implementado?).
5. **`python-data-engineer` — fixes (condicional)**: solo si la invocación 4 encuentra hallazgos
   que requieran corrección; mismo alcance de rutas que la invocación 2, sin ampliarlo.
6. **Lead — cierre**: redacta `verification.md` de este Change con el veredicto (release-blocker
   resuelto / pendiente) y actualiza la nota de `docs/roadmap/v0.7.md` a su estado final; decide si
   v0.7.0 pasa a `READY FOR RELEASE` (posiblemente re-confirmando el resto del gate de Change 5 sin
   repetirlo en extenso, por cita).

## Tareas

- [x] Invocación 1 — `proposal.md`/`spec.md`/`design.md`/`tasks.md` (este documento).
- [x] Invocación 2 — implementar `_check_agents` + call site + tests + nota en roadmap.
- [x] Invocación 3 — Lead corre el gate (regresión + scratch installs `experiment`/`discovery`).
- [x] Invocación 4 — revisión de `data-science-reviewer`.
- [x] Invocación 5 — fixes si la revisión los pide (condicional; sin hallazgos bloqueantes, 0 fixes
  aplicados).
- [x] Invocación 6 — `verification.md` + cierre + nota final en roadmap.
- [x] `verification.md`

## Dependencias

- Invocación 2 depende de que esta invocación (1) esté aprobada por el usuario (ver "Aprobación"
  en `proposal.md`; ya está registrada en esta redacción, pero la ejecución de la invocación 2
  debe confirmar que el Lead no encontró objeciones al SDD antes de tocar código).
- Invocación 3 depende de que la invocación 2 haya cerrado sin tests rotos localmente
  (`pytest tools/harmessi -q` en verde) antes de correr el gate completo.
- Invocación 4 depende del diff final de la invocación 2 (o 5, si hubo fixes).
- Invocación 6 depende de que la invocación 4 no deje hallazgos abiertos sin resolver o
  explícitamente registrados como limitación aceptada.

## Próximo paso exacto

No aplica (`estado: propuesta_pendiente`, no `pausada_bloqueada`). Próximo paso normal: el Lead
revisa este SDD y, si lo aprueba, dispara la invocación 2.
