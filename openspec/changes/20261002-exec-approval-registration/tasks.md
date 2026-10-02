# Tareas — 20261002-exec-approval-registration

estado: cerrada

## Invocaciones planificadas
- Writer (`python-data-engineer`): T1–T4; único que edita código.
- Reviewer (`data-science-reviewer`): tras T4; máx. 2 ciclos writer↔reviewer.
- Ejecución de tests: runtime gobernado `ds_guard exec` (con la aprobación que este mismo Change habilita;
  el bootstrap de las primeras corridas lo cubre la propia implementación, ver "Próximo paso").

## Tareas
- [x] T0 — Aprobación humana del SDD y resolución de M1.
- [x] T1 — Refactor: builders `_construir_exec_*`, `_validar_request_exec`, `_agregar_args_exec_*` sin
  cambio de comportamiento.
- [x] T2 — Subcomando `exec approve {pytest,script,notebook}` + `_registrar_aprobacion_exec`.
- [x] T3 — Tests nuevos `tools/tests/test_ds_guard_exec_approve.py`.
- [x] T4 — Documentación (`sdd.md`, `sdd.md.tmpl`, ayuda CLI) y regeneración de `.ds_init/control.json`.
- [x] T5 — Revisión independiente, fixes, verification.md, cierre, commit local separado del de Change 0.

## Dependencias
Ninguna. Bloquea la ejecución gobernada de tests de `20261002-card-and-evidence-foundation` (que queda
pausado).

## Próximo paso exacto
Aprobación humana del SDD. Nota de bootstrap: las corridas de test de ESTE Change en modo supervised
necesitan una aprobación de ejecución que todavía no tiene vía soportada; se resolverá con el primer
tramo implementado (T1–T2, que no requiere ejecutar nada) y una corrida inicial aprobada por el humano
mediante el subcomando nuevo.
