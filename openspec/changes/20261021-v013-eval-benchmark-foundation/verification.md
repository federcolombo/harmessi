# Verificación — 20261021-v013-eval-benchmark-foundation

## Resumen
Se extendió `tools/harmessi_bench` (caso/suite/resultado versionados, `suite_hash` y `cases_hash` canónicos, veredicto baseline vs candidate de 4 estados, suite pública sintética de 9 casos, CLI `--suite`/`suite-check`). Sin scorer LLM, sin promoción de superficies.

## Evidencia obtenida
- Tests focalizados (pytest, serial): `tools/harmessi_bench/tests` + smoke `test_v013_eval_foundation_smoke` + `test_v05_core_neutrality` = 167 passed; junto con `test_architecture_boundaries`, `test_manifest_completitud` y neutralidad v06/v07: 210 passed (corrida previa a la última corrección de storage, repetida luego sobre los 167 de arriba).
- `suite-check` sobre la suite pública: válida (`harmessi-core-synthetic` v1, 9 casos).
- `ds_guard validate`: sin hallazgos.
- Reviewer: 1 ciclo. 0 blocker, 2 HIGH, 6 MED, varios LOW. Fixes aplicados como continuación: H1 (`cases_hash` persistido siempre; sin suite se exige hash igual, o `inconclusive`), H2 (`detail` acotado), M1 (id duplicado/ausente en una corrida => `ValueError`), M2 (validación de caso: id, prompt, scorer conocido), M3/M4 (motivo con n y pasados; aviso si 0 pasaron en ambos), M5 (niveles de evidencia en ARCHITECTURE §10), L1 (OSError y mensajes sin rutas absolutas), L2 (claves desconocidas del manifest rechazadas). No hay segundo ciclo: los fixes no cambian materialmente lo revisado.

## Divergencias respecto del SDD
- La regla de `cases_hash` (H1) complementa R13 y está documentada en ARCHITECTURE §10; spec/design aprobados por hash no se reeditaron.
- H2 se resolvió en `storage.py` (acota `score.detail` a 300 caracteres al persistir) y en `core.py` (`scorer_exact`); NO se tocó `runner.py` porque estaba fuera del scope autorizado y una enmienda exige T1 humana. Se revirtió esa edición.

## Deuda registrada (LOW del reviewer, no bloquean)
Bloques `suite` incompletos sin validar en `compare`/`render_resumen` (L3); caso v0 aceptado como suite (L4); `ok` serializado como null (L5); neutralidad solo a nivel de import de módulo y `scenarios.py` con import perezoso (L6); helpers duplicados (L7); duplicados de `scenario_id` en archivos v0.5 ahora fallan al cargar (L8); regex de privacidad del smoke sobre JSON crudo (L9); normalización Unicode NFC/NFD y de `surface_under_test` en el hash (M6); suite pública débil ante eco del prompt y una sola muestra (M3).

## Limitaciones
Los scorers deterministas son un proxy de texto, no medición semántica; sin repeticiones ni umbrales estadísticos. Validado en Windows.

## Resultado final
Change 1 verificado con tests focalizados verdes. Listo para commit.
