# Tareas — 20261016-v011-sessions-continuations-recovery

estado: en_implementacion

## Invocaciones planificadas
- Lead coordina/valida; writer único `python-data-engineer` (serial); reviewer 1 ciclo.

## Tareas
- [x] T1 — Implementación + tests (writer) — hecho; tests OK: test_session_recovery 22, test_operational_session_recovery 26, test_operational_budgets 28, test_ds_guard_budgets_cli 36, test_skill_methodology 52, test_manifest_dsguard_parity 11
- [ ] T2 — Reviewer y fixes
- [ ] T3 — verification, cierre, commit

## PUNTO DE CORTE (2026-10-16, fin de jornada)
Estado: Change 3 en `en_implementacion`, implementación completa y tests dirigidos verdes. WIP commiteado localmente en `v0.11-dev`.
Pendiente: (1) reviewer ciclo 1 de Change 3 (se había lanzado pero su reporte no llegó a registrarse: RE-LANZAR `data-science-reviewer` con foco: --retomar no evade límites, aviso stderr no contamina stdout/--json, hook solo cambió un string (H1 intacto), constante única, compat control.json, `{{`/`}}` en MANIFEST); (2) fixes + tests de los fixes; (3) verification.md (secciones `## Evidencia obtenida` y `## Resultado final` obligatorias), transición en_verificacion → cerrada con sesión activa, `session close`, commit; (4) Change 4 (4B primero), 5, 6, release.
Recuperación: si la sesión venció, `session close --estado pausada` y luego `session start --change-id <id> --minutos 480 --retomar` (comandos literales, uno por llamada).
