# Verificación — 20261021-v013-provider-adapter-conformance

## Resumen
Conformance de providers (`tools/providers/conformance.py`, solo-checkout) con niveles `contract-tested` / `locally-smoke-tested` / `live-validated` y `SOPORTE_DECLARADO`; suite de conformance de observers de fuente (`tools/datasources/conformance.py`, instalada, registrada en MANIFEST). Sin cambios en `ProviderAdapter`, `SourceObservation` ni `SourceCapabilities`.

## Evidencia obtenida
- pytest serial (providers, datasources, smoke del Change, arquitectura, neutralidad v08, manifest, manifest-completitud), con `HARMESSI_SMOKE_LOCAL=1`: ver línea de resumen de la corrida final de este Change (todos verdes, 1 skip por pandas ausente).
- `python -m tools.providers.conformance --smoke`: `claude_code` alcanzó `locally-smoke-tested` en este host (detect() real, versión `2.1.306 (Claude Code)`); `codex`, `gemini`, `grok` alcanzaron `contract-tested` (su CLI no está verificada contra el binario real).
- `ds_guard validate`: sin hallazgos.
- Reviewer ciclo 1: 0 blocker, 1 HIGH (chequeo de secretos vacuo), 7 MED. Fixes: secretos inspeccionados en cmd/env/input con variables reales de API, dobles para run/Popen/check_*/which y from-imports, soporte declarado conservador, smoke opt-in (`HARMESSI_SMOKE_LOCAL=1`), advertencias model/effort, excepciones acotadas, `completo`/`ok` coherentes, AST ampliado. Ciclo 2 (justificado por el HIGH): 0 blocker/HIGH.

## Real vs fixture
- **Real:** `detect()` de `claude` en este host (Windows) con `--smoke`.
- **Fixture:** todos los chequeos de contrato de providers (dobles de `subprocess`/`which`); los observers conformantes e inválidos.
- **No realizado:** smoke real de `FileObserver` (pandas no está instalado en el entorno; se omite explícitamente, no se instala una dependencia mayor); ninguna validación live de provider (nunca `live-validated`).

## SOPORTE_DECLARADO
Los 4 providers: `contract-tested`. El nivel `locally-smoke-tested` se reporta cuando se corre `--smoke` en un host con la CLI, no se declara de forma estática.

## Limitaciones conocidas (deuda)
Un secreto escrito por `communicate(input=...)`/`stdin.write` de un Popen no se detecta; `os.system`/`os.popen`/`asyncio.create_subprocess_*` y from-imports fuera del módulo del adapter no están doblados (la afirmación es para adapters que usan `subprocess`/`shutil` por módulo); `AssertionError` del observer copia su mensaje al detalle; `--model=x` (con `=`) genera advertencia falsa; factories `partial`/callables no pasan el chequeo AST; evasiones `from os import system`/alias; falta test explícito de restauración de parches. El chequeo AST de «no instala nada» no es exhaustivo.

## Divergencias respecto del SDD
R3: un chequeo smoke/live fallido deja `nivel_alcanzado = contract-tested` (no `None`); solo un chequeo de contrato fallido lo deja en `None`. `ok` de observers es False con chequeos no evaluados salvo `permitir_no_evaluados=True`.

## Resultado final
Change 3 verificado con tests focalizados verdes. Listo para commit.
