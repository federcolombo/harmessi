# Tareas — 20260917-remove-personal-email

estado: cerrada

## Invocaciones planificadas
1. `python-data-engineer` (esta sesión): fix de contenido (25 apariciones del email en 9 archivos)
   + guarda técnica (`core.validar_usuario_sin_email`, cableada en los 5 command handlers de
   `tools/ds_guard.py`) + tests nuevos + documentación de la convención, todo en un solo paso dado
   que la decisión ya está completamente especificada por el Lead.
2. Lead: corre los tests nuevos (`tools/tests/test_validar_usuario_sin_email.py`,
   `tools/tests/test_ds_guard_usuario_guard.py`) + regresión de `tools/tests` completa + `git grep`
   final para confirmar cero apariciones del email + sweep de privacidad transversal + escribe
   `verification.md`.

## Tareas
- [x] `openspec/changes/20260917-multi-provider-adapters/control.json`: 4 entradas de
      `aprobaciones` corregidas (email removido del campo `usuario`).
- [x] `openspec/changes/20260917-multi-provider-adapters/proposal.md`: línea "Usuario" corregida.
- [x] `openspec/changes/20260917-harmessi-bench/control.json`: 4 entradas corregidas.
- [x] `openspec/changes/20260917-harmessi-bench/proposal.md`: línea "Usuario" corregida.
- [x] `openspec/changes/20260917-provider-routing/control.json`: 4 entradas corregidas.
- [x] `openspec/changes/20260917-fallback-and-handoffs/control.json`: 4 entradas corregidas.
- [x] `openspec/changes/20260917-cross-provider-hardening/control.json`: 4 entradas corregidas.
- [x] `openspec/changes/20260917-v0-4-release-hardening/verification.md`: línea 18 reformulada sin
      el email literal.
- [x] `openspec/changes/20260917-v0-5-release-hardening/verification.md`: párrafo del sweep de
      privacidad transversal reformulado sin el email literal, con nota de resolución agregada.
- [x] `tools/dsguard/core.py`: función `validar_usuario_sin_email` agregada.
- [x] `tools/ds_guard.py`: guarda cableada en `cmd_approve`, `cmd_remediation_extend`,
      `cmd_decision_add`, `cmd_decision_supersede`, `cmd_decision_revoke`.
- [x] `tools/tests/test_validar_usuario_sin_email.py`: creado, tests de la función pura.
- [x] `tools/tests/test_ds_guard_usuario_guard.py`: creado, tests de integración + estructurales.
- [x] `.claude/skills/lead-data-scientist/sdd.md`: nota de convención agregada.
- [x] `.claude/skills/lead-data-scientist/decision-ledger.md`: nota de convención agregada.
- [x] `openspec/changes/20260917-remove-personal-email/verification.md`: evidencia final escrita,
      ver `openspec/changes/20260917-remove-personal-email/verification.md`.

## Dependencias
Ninguna -- las 16 rutas son independientes entre sí (ediciones puntuales, sin orden de aplicación
obligatorio) y ya están completamente especificadas por el Lead.

## Próximo paso exacto
No aplica -- no es un estado `pausada_bloqueada`.

## Verificación

Evidencia completa en `openspec/changes/20260917-remove-personal-email/verification.md`. Resumen:
email personal eliminado de las 24 apariciones tracked encontradas (0 restantes, confirmado por
`git grep` exacto y por regex amplia de email -- únicos 20 resultados de la regex amplia son
fixtures `test@example.com`, sin relación); guarda técnica real agregada
(`tools/dsguard/core.py::validar_usuario_sin_email`) en los 5 comandos de `ds_guard` que persisten
un campo `usuario`; 1 regresión real encontrada (desincronización `.tmpl`/renderizado de
`decision-ledger.md`) y corregida; 846 tests pasaron entre las 3 suites afectadas
(`tools/tests`/`tools/ds_init/tests`/`tools/harmessi/tests`), 0 failures. El email sigue existiendo
en el historial de commits de `v0.5-dev` y ya está en `main` (pusheado a `origin` desde el release
de v0.4.0) -- limpieza de historial queda como decisión separada del usuario.
