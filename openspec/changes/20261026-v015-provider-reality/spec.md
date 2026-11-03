# Spec — 20261026-v015-provider-reality

## Requisitos
- R1. `docs/providers.md` publica la matriz provider × {detected, contract-tested, smoke-tested, live-validated, limitaciones conocidas} para `claude_code`, `codex`, `gemini`, `grok`, y aclara que no hay adapter `antigravity` (se cubre por `gemini`).
- R2. `docs/providers.md` incluye un registro de evidencia live con fecha, OS, versión de CLI, comando exacto y resultado. Para `claude_code`: 2026-10-26, Windows 11, Python 3.12.5, `2.1.310 (Claude Code)`, `HARMESSI_LIVE_PROVIDER=1 python -m tools.providers.conformance --smoke --live --json`, `live-validated`. Declara que es host único, no reproducible en CI y sin cobertura de otras versiones ni OS.
- R3. `SOPORTE_DECLARADO["claude_code"].nivel_declarado == "live-validated"`; `codex`, `gemini` y `grok` siguen `contract-tested`. El texto de `evidencia` de cada uno no afirma más que la evidencia.
- R4. Ningún provider se declara por encima de `contract-tested` sin registro de evidencia coincidente (provider, nivel) en `docs/providers.md`.
- R5. El fallback automático solo se habilita por `availability_error` ∈ {quota, unavailable, unauthenticated}. `ok=False` con `availability_error=None` (error semántico o de código) nunca lo dispara, en `is_fallback_eligible` y en la ejecución de la cadena, con paridad entre providers.
- R6. El chequeo de modelo de conformance reconoce la forma `--flag=modelo` como modelo pasado con flag; no emite la advertencia "ignora model" en ese caso. Sigue rechazando un modelo pasado sin flag.
- R7. Los límites heurísticos de conformance no corregidos se documentan en `docs/providers.md`: `communicate`/`stdin.write`, `os.system`/`os.popen`, from-imports, `partial`/callables, restauración de parches.
- R8. El docstring de `claude_code.py` no cita `2.1.274` como versión vigente: referencia `2.1.310` como versión validada en vivo el 2026-10-26 (host único).
- R9. README y `docs/providers.md` documentan: routing declarativo, `provider_available` informativo, fallback solo por quota/availability, y la promesa real de provider-neutrality (los 4 adapters implementan `ProviderAdapter` y pasan conformance con dobles; solo Claude Code está validado en vivo). T2 queda POST-v1 con razón.
- R10. El inventario actualiza las notas de `cli-providers-conformance` (si corresponde) y `provider-adapter` con el estado de soporte; el inventario sigue válido contra sus tests.
- R11. Roadmap y matriz de deuda marcan B-07, B-08, B-09 (parcial: `--model=x` cerrado, resto documentado) y B-10 como cerrados con referencia a la evidencia.

## Criterios de aceptación
- [ ] `docs/providers.md` existe con la matriz, el registro de evidencia, los límites de conformance y la sección de fallback (R1, R2, R7, R9).
- [ ] `test_v015_provider_matrix.py`: la tabla de la doc coincide con `SOPORTE_DECLARADO` en los 4 providers (R1, R3).
- [ ] `test_v015_provider_matrix.py`: todo nivel declarado ≥ smoke-tested/live-validated tiene registro de evidencia coincidente (provider, nivel); un test negativo con un `SOPORTE_DECLARADO` sintético sin registro falla (R4).
- [ ] `test_v015_provider_matrix.py`: la doc no declara `live-validated` para codex/gemini/grok (R4).
- [ ] Tests en `tools/fallback/tests/test_core.py` y `test_cross_provider_parity.py`: `availability_error=None` con `ok=False` no avanza la cadena para los 4 providers; `quota`, `unavailable` y `unauthenticated` sí (R5).
- [ ] Test en `tools/routing/tests/test_core.py`: `provider_available` es informativo y no altera la decisión de routing (R9).
- [ ] Test en `tools/providers/tests/test_conformance.py`: un adapter doble que pasa `--model=modelo-sintetico` no genera la advertencia "ignora model" y pasa el chequeo; un adapter que pasa el modelo sin flag falla (R6).
- [ ] `claude_code.py` no contiene `2.1.274` como versión vigente (R8). Los tests ajenos que usen `2.1.274` como fixture no se tocan.
- [ ] Los tests de smoke de release v0.13/v0.14 y de inventario pasan con el nuevo `SOPORTE_DECLARADO` (R3, R10).
- [ ] La suite completa pasa, sin regresiones (verificado por el Lead; el writer no ejecuta).
- [ ] Ningún número ni versión citados en docs salen de memoria: salen de la corrida del 2026-10-26 transcripta en `docs/providers.md`.
