# Propuesta — 20261026-v015-provider-reality

## Problema
La matriz de soporte de providers no está publicada y `SOPORTE_DECLARADO` (`tools/providers/conformance.py` ~L99-123) declara los 4 providers como `contract-tested` sin registro de evidencia viva (B-07, B-08). Sin matriz honesta no se puede cumplir el criterio v1 n.º 7 (compatibilidad de providers soportados). Además: (a) la garantía de gobernanza "el fallback automático ocurre solo por quota/availability, nunca por error semántico o de código" (`tools/fallback/core.py` L12-14, `_CAUSAS_ELEGIBLES` L34) debe verificarse con tests explícitos y documentarse (B-10; routing declarativo, `provider_available` informativo, C-26); (b) el chequeo de comando de conformance trata `--model=x` (con `=`) como si el adapter ignorara el modelo (B-09); (c) el docstring de `tools/providers/claude_code.py` L3 cita la versión `2.1.274`, desactualizada.

## Objetivo
Publicar una matriz de soporte de providers sin nivel superior a la evidencia, con un registro de validación viva de `claude_code`, y verificar y documentar que el fallback solo se dispara por quota/availability.

## Evidencia
- Corrida del Lead el 2026-10-26 (Windows 11, Python 3.12.5): `HARMESSI_LIVE_PROVIDER=1 python -m tools.providers.conformance --smoke --live --json`.
  - `claude_code` → `nivel_alcanzado: live-validated` (detect real, versión `2.1.310 (Claude Code)`; invocación real mínima `ok=True`; 6 chequeos de contrato con dobles `ok`).
  - `codex`, `gemini`, `grok` → `contract-tested` (`smoke_detect_real` falla: CLI no instalada; live exit=127 `unavailable`). No se instaló nada ni se usaron credenciales.
- `tools/providers/conformance.py` L99-123: `SOPORTE_DECLARADO` con 4 × `contract-tested`; L344-352: chequeo de modelo que usa `_MODELO_SINTETICO in cmd` (no reconoce `--model=modelo-sintetico`).
- `tools/fallback/core.py` L12-14, L34, L37-41, L128: `is_fallback_eligible` es la única decisión de fallback.
- `tools/providers/claude_code.py` L3: versión `2.1.274`.
- `docs/roadmap/v0.15-debt-matrix.md` L75-78 (B-07, B-08, B-09, B-10), L133 (C-26); `docs/roadmap/v0.15.md` C2.
- No existe adapter `antigravity`: Gemini/Antigravity se cubre por el adapter `gemini`.
- `docs/providers.md` no existe aún.

## Supuestos descartados
- "Ningún provider es validable en vivo": `claude_code` sí lo es en el entorno del Lead, sin instalar nada ni credenciales nuevas.
- "Existe adapter para Antigravity": no existe; se cubre por `gemini`.

## Alcance
1. Matriz publicada en `docs/providers.md`: provider × {detected, contract-tested, smoke-tested, live-validated, limitaciones conocidas}, más un registro de evidencia live (fecha, OS, versión de CLI, comando exacto, resultado). La evidencia live es de host único: no reproducible en CI, no cubre otras versiones ni otros OS.
2. `SOPORTE_DECLARADO`: `claude_code` pasa a `live-validated` solo con registro de evidencia en `docs/providers.md`; `codex`, `gemini`, `grok` siguen `contract-tested` sin afirmar más.
3. Test `tools/tests/test_v015_provider_matrix.py`: la doc y `SOPORTE_DECLARADO` coinciden; todo nivel declarado ≥ smoke/live tiene registro de evidencia (provider, nivel); un provider sin registro no puede declararse por encima de `contract-tested`.
4. B-10: tests que prueban que `ok=False` con `availability_error=None` nunca dispara fallback y que `quota`/`unavailable`/`unauthenticated` sí; documentado en `docs/providers.md` y README.
5. B-09: corregir el falso positivo de `--model=x` + test; los demás huecos (`communicate`/`stdin.write`, `os.system`/`popen`, from-imports, `partial`/callables, test de restauración de parches) se documentan como límite heurístico conocido, sin implementarlos.
6. Corregir el docstring de `claude_code.py` (versión validada 2.1.310).
7. Documentar la promesa de provider-neutrality real y decidir T2 = POST-v1 con razón.
8. Actualizar notas de `providers-conformance` / `provider-adapter` en el inventario; actualizar roadmap v0.15 y matriz de deuda (B-07..B-10); ajustar tests de smoke de release v0.13/v0.14 si dependen de la tabla declarada.

## Fuera de alcance
- Instalar providers ausentes (codex, gemini, grok) o usar credenciales.
- Adapter `antigravity` propio.
- Implementar detección de evasiones de conformance (B-09 más allá de `--model=x`).
- T2 (queda POST-v1).
- Reescribir routing/fallback: solo se verifican y documentan.
- Otros archivos de adapters (`codex`, `gemini`, `grok`).

## Holdout policy (condicional — solo cambios "sensible")
No aplica.

## Impacto en production-readiness (opcional)
Cierra el criterio v1 n.º 7 con evidencia acotada. La validación live es de host único; no se promete nada más.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md`.

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md`.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado
- docs/providers.md
- README.md
- ARCHITECTURE.md
- docs/roadmap/v0.15.md
- docs/roadmap/v0.15-debt-matrix.md
- docs/contracts/inventory.json
- tools/providers/conformance.py
- tools/providers/tests/test_conformance.py
- tools/providers/core.py
- tools/providers/tests/test_core.py
- tools/providers/claude_code.py
- tools/fallback/tests/test_core.py
- tools/fallback/tests/test_cross_provider_parity.py
- tools/routing/tests/test_core.py
- tools/tests/test_v015_provider_matrix.py
- tools/tests/test_v014_release_hardening_smoke.py
- tools/tests/test_v013_release_hardening_smoke.py

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
