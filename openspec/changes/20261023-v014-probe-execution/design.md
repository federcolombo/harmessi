# Diseño — 20261023-v014-probe-execution

- `policy.py`: `ProbePolicy` dataclass congelada, `hash_policy`, `PolicyInvalida`.
- `probe.py`: `GuidanceAdapter`, `ejecutar_probe(repo_root, candidate_id, suite_path, adapter, target, policy, probe_id, seed=None, resume=False, ahora=None)`, `cargar_probe`, `ProbeRechazado`, `ProbeIncompatible`. Orden: precondiciones → consumo de budget → `probe.json` (estado `running`, política congelada) → repeticiones (baseline y candidate con el mismo `run_scenario_set`) → clasificación → `probe.json` final. Escrituras atómicas.
- `runmanifest.sustituir_superficie(manifest, repo_root, ruta_relativa, contenido)`: función pública en `harmessi_bench` que devuelve un manifest con la superficie sustituida y `identity_hash` recalculado; no toca el disco.
- Guía baseline = contenido activo; guía candidate = `content.md`. Sin LLM-as-judge: los scorers son los deterministas de v0.13.
