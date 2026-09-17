# Tareas — 20260917-multi-provider-adapters

estado: cerrada

## Invocaciones planificadas
1. `python-data-engineer` — esta misma sesión: completa los 4 artefactos SDD e implementa código +
   tests.
2. Lead — corre la suite de tests nueva + regresión de `tools/harmessi/tests`, y ejecuta
   manualmente (fuera de la suite) una invocación real de `claude -p` para verificar
   `ClaudeCodeAdapter.invoke()` end-to-end; la evidencia va a `verification.md`.
3. `data-science-reviewer` — revisa el diff completo (el Lead corre `git diff` y se lo pasa).
4. `python-data-engineer` — aplica fixes si hay hallazgos del reviewer (cuenta como reintento
   correctivo solo si los hay) y escribe `verification.md` con la evidencia que el Lead le pasa,
   dejando `estado: en_verificacion` antes del cierre.
5. `data-science-reviewer` (ronda 1) ya corrió sobre el diff completo y encontró 4 hallazgos
   "importante": `invoke()` sin `try/except` en los 4 adapters, falsos positivos en
   `classify_availability_error` (sacado `"no such file"` de `unavailable`, límite de palabra para
   `429`/`401`, patrones de auth más específicos), `role`/`translate_role()` sin uso documentado
   como intencional, y `test_providers_cli.py` sin mock/skipif sobre CLI real. `python-data-engineer`
   aplicó los 4 fixes correspondientes en esta misma reinvocación (cuenta 1/2 del contrato de
   autonomía).
6. `python-data-engineer` registró la evidencia de verificación en `verification.md` (ver ese
   archivo para el detalle completo de regresión, smoke real, ronda de review y fixes aplicados).

## Tareas
- [x] Crear `tools/providers/core.py`.
- [x] Crear los 4 adapters (`tools/providers/claude_code.py`, `codex.py`, `gemini.py`, `grok.py`).
- [x] Crear `tools/providers/__init__.py`.
- [x] Extender `tools/harmessi/cli.py` con el subcomando `providers list`.
- [x] Crear los 3 archivos de test (`tools/providers/tests/test_core.py`,
      `tools/providers/tests/test_adapters.py`, `tools/harmessi/tests/test_providers_cli.py`).
- [x] Actualizar `ARCHITECTURE.md` §2.1.

## Dependencias
Ninguna — no se toca código existente de `dsguard`/`dsimpact`/`ds_profile`/`ds_init`.

## Próximo paso exacto
No aplica (estado no es `pausada_bloqueada`).
