# Verificación — 20261026-v015-evidence-privacy-hardening

## Resumen
Change C5 de v0.15: endurecimiento de evidencia/privacidad/procedencia (B-20..B-25), robustez de `harmessi_bench` (B-24) y fixture real de Data Card v1 del tag v0.14.0 (hueco heredado de C3). Se resuelve además `DATA_CARD_KIND_SCHEMA_VERSIONS_LEIDAS` (falla real de `test_v013_contract_inventory`).

## Cambios de código
- `tools/harmessi_bench/{storage,cli,suite}.py`: `run_id` reservados de Windows y punto final rechazados; `result.json` corrupto con error claro; flag opt-in `--fail-on-failure` (el default sigue en exit 0); `bloque_suite` incompleto y casos con `case_contract_version` distinta de 1 rechazados.
- Tests nuevos: `tools/harmessi_bench/tests/test_v015_b24_hardening.py`, `tools/harmessi_improve/tests/test_v015_evidence_hardening.py`, `tools/tests/test_privacy_sweep.py`, `tools/tests/test_compat_datacard_v014.py`; ajuste de ids en `test_runmanifest.py`; exclusión con motivo en `test_v013_contract_inventory.py`.
- Fixture: `tools/tests/fixtures/compat/v0_14/{data_card.json,MANIFEST_data_card.json}` generado con el código del tag v0.14.0 por `generate_datacard_v014.py` (sin privacidad: 0 coincidencias de rutas/emails).
- Docs: matriz B-20..B-25, roadmap §C5, `docs/versioning.md`, ARCHITECTURE.

## Evidencia obtenida
- `test_v013_contract_inventory` 38 passed; `test_compat_datacard_v014` 5 passed.
- `harmessi_bench` completo: 337 passed (tras corregir 2 tests que usaban el `run_id` reservado «con»).
- `test_v015_evidence_hardening` 24 passed, 1 skipped (symlink real sin privilegios; la rama se cubre con `es_enlace` parcheado).
- `test_privacy_sweep` verde con el alcance ampliado (docs/**, ARCHITECTURE.md, README.md, fixtures, suites/escenarios de bench): sin hallazgos y WHITELIST vacía.
- Revisión independiente: 0 bloqueantes, 2 mayores (R4 de la spec sobre GLOSSARY ausente; alcance del barrido) y menores; aplicados o documentados en `tasks.md` (Desvíos).

## Limitaciones
- Privacidad heurística (sin detección perfecta); no barre términos de GLOSSARY ni código fuente.
- Procedencia no criptográfica (D5): un `probe.json` re-hasheado consistentemente no se detecta; `proposal.json` no ata `probe.json`.
- Cobertura de symlink real en Windows no demostrada en este host (skip explícito).
- `scenario_id` no se normaliza (NFC y NFD son ids distintos).
- Cierre SDD formal PENDIENTE: la transición a `cerrada` no pasa retroactivamente (gate de alcance: C4, C5 y C6 comparten `tools/tests/**` y el baseline de cada uno ve los cambios de los otros). El Change queda en `en_verificacion`, implementado, probado y revisado; ver brecha de proceso en `docs/roadmap/v0.15.md`.
