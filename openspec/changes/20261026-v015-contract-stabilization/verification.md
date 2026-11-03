# Verificación — 20261026-v015-contract-stabilization

## Resumen
Change de v0.15 de estabilización de contratos: ventana de compatibilidad contra fixtures reales de v0.14.0, validación de `manifest_version` en `resume`, `bench compare --fail-on-regression`, `guia` obligatoria en deprecaciones, y documentación asociada (`docs/deprecation.md`, matriz de deuda, roadmap v0.15, contratos). `inventory_version` sigue en 1, con 50 contratos.

## Cambios de código
- `tools/harmessi_bench/runmanifest.py`: `resume` valida `manifest_version`; rechaza valores `<1` y `>1`.
- `tools/harmessi_bench/cli.py`: `compare --fail-on-regression` sale con exit 1 solo ante el veredicto `baseline_better`; el comportamiento por defecto no cambia.
- `tools/harmessi/deprecation.py`: el campo `guia` pasa a ser obligatorio.
- Fixtures reales v0.14.0 en `tools/tests/fixtures/compat/v0_14/` (7 json + `MANIFEST.json`), generados con `tools/tests/fixtures/compat/generate_v014.py` sobre `git archive v0.14.0`. Baselines reales `git show v0.13.0/v0.14.0:.ds_init/control.json` en `v0_13/` y `v0_14/`.

## Evidencia obtenida
Tests corridos por el Lead, todos verdes:
- (a) T1–T4 (`test_runmanifest`, `test_deprecation`, bench `test_cli`, `test_cli` de harmessi/ds_init/improve): 170 passed, 7 subtests. Corrida previa a los fixes del reviewer.
- (b) Compat + inventario (`test_v015_compat_window`, `test_v013_contract_inventory`, `test_v013_compat_window`): 122 passed.
- (c) Smokes v0.13/v0.14 + `test_manifest_completitud`: 62 passed, 16 subtests.
- (d) Corrida final tras los fixes del reviewer (`test_v015_compat_window`, `test_v013_contract_inventory`, `test_v013_compat_window`, bench `test_runmanifest` y `test_cli`, `test_deprecation`, smokes v013/v014): 292 passed, 1 warning, 16 subtests. El warning es un DeprecationWarning de `tar.extractall` sin `filter` (Python 3.12).

Revisión (reviewer, 1 ciclo, informe parcial): sin BLOCKER. Tres HIGH de wording/alcance de docs: H1 (garantía de exit codes en 0.x) y H3 (alcance de `manifest_version`, solo en resume) aplicados; H2 resultó falso (los lectores existen). MEDIUM/LOW aplicados, salvo M4 (ver Divergencias).

## Limitaciones
- La regeneración de fixtures contra el tag se saltea si no existe el tag local. En CI sin tags, R3 se respalda solo con los fixtures commiteados.
- El fixture de proposal no incluye `change.diff`; se valida por hash.
- `HARNESS_VERSION` está anclado a 0.14.0 en `test_v015_compat_window`; hay que actualizarlo en C7.
- La compat de source-observation, registry, eval-case, suite y run-manifest no tiene fixture real.
- El reviewer no llegó a revisar, por límite de turnos: `docs/deprecation.md`, `test_deprecation`, los tests nuevos de compat del inventario, las ventanas de lectores no-improve, los exit codes de ds_init/harmessi/improve y la matriz/roadmap. Quedan cubiertos por tests verdes, no por revisión.
- Sin regresión completa (corresponde a C7).

## Divergencias respecto del SDD
- La convención de nombres de deprecación `<id-inventory>[: detalle]` se agregó durante la implementación y está documentada en `docs/deprecation.md`.
- M4: se aserta `len(ya_actuales)+len(no_verificables)==len(archivos)` porque en el directorio temporal los archivos no existen (el reviewer pedía otra aserción).

## Resultado final
Implementación completa y verde en las corridas acotadas indicadas. Pendiente: regresión completa y actualización de `HARNESS_VERSION` en C7.
