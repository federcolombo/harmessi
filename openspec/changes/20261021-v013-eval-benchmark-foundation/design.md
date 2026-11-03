# Diseño — 20261021-v013-eval-benchmark-foundation

## Principio
Extender `harmessi_bench` con el menor cambio posible; todo lo nuevo es opcional/retrocompatible. Sin dependencias nuevas (stdlib).

## Piezas
- `core.py`: `CASE_CONTRACT_VERSION`, `EVALUATOR_VERSION = "harmessi-bench-scorers/1"`, dos campos opcionales en `Scenario`. Sigue sin imports de providers.
- `scenarios.py`: versión del contrato de casos, duplicados, boundary de superficies (import perezoso de `tools.dsguard.skill_contract.superficie_de_ruta`).
- `suite.py` (nuevo): `Suite`, `load_suite`, `calcular_suite_hash`, `resumir`, `render_resumen`. Puro stdlib salvo `scenarios`.
- `storage.py`: `schema_version`/`evaluator_version`/`suite`; lectura tolerante a legado y rechazo de versiones futuras.
- `compare.py`: veredicto con reglas explícitas y conservadoras (ante duda `inconclusive`). Las corridas legadas carecen de `evaluator_version`/`suite`: si falta la
  metadata de comparabilidad en un solo lado ⇒ `inconclusive`; si falta en ambos lados se permite comparar (dos corridas legadas del mismo set) y el motivo lo registra.
- `cli.py`: `--suite`, `suite-check`, veredicto en `compare`.
- `suites/`: manifest + casos públicos sintéticos.

## Decisiones
- **Hash de suite sobre contenido canónico**: reproducible entre SO (no depende de CRLF/LF ni de rutas).
- **Veredicto solo por `score.passed`**: simple, auditable, determinista; los scores fraccionales no cambian el veredicto (evita falsa precisión).
- **Disponibilidad ≠ calidad**: un `availability_error` hace `inconclusive`, nunca `baseline_better`.
- **Boundary de superficies como validación del caso**, no como mecanismo de promoción: no existe ni se crea una vía de escritura.
- **Solo-checkout**: la evaluación del harness se corre desde el clone de Harmessi; no se amplía el manifest instalado.

## Riesgos
Los scorers superficiales son un proxy de texto, no medición semántica; se documenta. Los campos nuevos de `ComparisonReport` tienen default: los consumidores existentes no se rompen.

## No se reabre
Roles, T0/T1, scorers deterministas de v0.5, `.harmessi/evals/<run_id>/result.json` como ubicación.

## Decisiones materiales pendientes
Ninguna.
