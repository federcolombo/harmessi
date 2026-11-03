# Verificación — 20261026-v015-provider-reality

## Resumen
Change de v0.15 (C2) de realidad de providers: matriz de soporte publicada en `docs/providers.md` con registro de evidencia live, `claude_code` declarado `live-validated` (host único) y los otros 3 en `contract-tested`, tests de coincidencia doc/código, verificación de que el fallback solo se dispara por quota/availability, y corrección del falso positivo `--model=x` de conformance.

## Cambios de código
- `tools/providers/conformance.py`: `SOPORTE_DECLARADO["claude_code"]` pasa a `live-validated` con evidencia que remite a `docs/providers.md`; el chequeo de modelo reconoce `--model=x` y `-m=x` (solo el flag de modelo) sin la advertencia "ignora model".
- `tools/providers/claude_code.py`: solo el docstring (versión validada `2.1.310`, host único).
- Tests nuevos o ajustados: `tools/tests/test_v015_provider_matrix.py`, `tools/providers/tests/test_conformance.py`, `tools/fallback/tests/test_core.py`, `tools/fallback/tests/test_cross_provider_parity.py`, `tools/routing/tests/test_core.py`.
- Documentación: `docs/providers.md` (nuevo), README, ARCHITECTURE §10.2, `docs/contracts/inventory.json` (notas), roadmap v0.15 y matriz de deuda.

## Evidencia obtenida
Validación live real del 2026-10-26 (Windows 11 Pro 10.0.22631, Python 3.12.5), comando `HARMESSI_LIVE_PROVIDER=1 python -m tools.providers.conformance --smoke --live --json`:
- `claude_code`: `nivel_alcanzado=live-validated`; `smoke_detect_real` ok (`2.1.310 (Claude Code)`); `live_invocacion` ok (invocación real mínima con `ok=True`); 6 chequeos de contrato con dobles ok.
- `codex`, `gemini`, `grok`: `contract-tested`; `smoke_detect_real` con `ok=False` (CLI no disponible en este host); `codex` `live_invocacion` fallida (exit=127, error=unavailable).
- No se instaló nada ni se usaron credenciales adicionales.

Tests corridos por el Lead, antes de los fixes del reviewer: 274 passed, 3 skipped, 57 subtests (`test_v015_provider_matrix`, tests de providers/fallback/routing, inventario, conformance smoke, smokes v0.13/v0.14, `test_architecture_boundaries`, `test_providers_cli`). Los fixes posteriores (abajo) requieren nueva corrida.

Revisión (reviewer, 1 ciclo): 0 BLOCKER, 0 HIGH, 2 MEDIUM aplicados. M1: la viñeta histórica del README (v0.13) se prefijó con "(en v0.13)". M2: el test de matriz valida también las columnas detected/contract-tested/smoke-tested/live-validated contra el registro. Además, LOW: columnas rotuladas sin ambigüedad en la doc y supresión de `--model=x` restringida a `--model`/`-m`.

## Limitaciones
- Evidencia de host único, un solo SO (Windows), una versión de CLI; no reproducible en CI.
- No valida la calidad semántica de las respuestas.
- `codex`, `gemini` y `grok` siguen `contract-tested`; no se validaron en vivo.
- T2 (canal de aprobación / seguridad por provider) queda POST-v1.
- Sin regresión completa de la suite (corresponde a C7).

## Divergencias respecto del SDD
- Ninguna material. Se reescribieron dos tests existentes de `test_conformance.py` que asumían los 4 providers en `contract-tested`.

## Deudas
- B-09 parcial: `--model=x` cerrado; `communicate`/`stdin.write`, `os.system`/`os.popen`, from-imports, `partial`/callables y la restauración de parches quedan documentados como límite heurístico en `docs/providers.md`.

## Resultado final
Implementación completa. Pendiente: nueva corrida de los tests tras los fixes del reviewer y cierre por el Lead.
