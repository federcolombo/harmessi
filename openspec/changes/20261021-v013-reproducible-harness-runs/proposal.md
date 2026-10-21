# Propuesta — 20261021-v013-reproducible-harness-runs

> Change 2 de v0.13: Reproducible Harness Runs. Extiende `tools/harmessi_bench` (Change 1); no crea otro sistema de runs.

## Problema
Una corrida de eval guarda `run_id`, `target` y `harmessi_version`, pero no identifica inequívocamente con qué harness se obtuvo la evidencia (commit, skills,
superficies, evaluator, plataforma). Dos corridas pueden compararse sin saber qué cambió, y un `run_id` reutilizado puede mezclar evidencia de configuraciones distintas.
Además `result.json` persiste texto de salida del modelo sin redacción de rutas de usuario, emails ni tokens.

## Objetivo
Un **run manifest** mínimo, versionado y sin secretos que identifique la corrida; un **resume seguro** que rechaza configuraciones materialmente incompatibles;
**redacción** de datos sensibles antes de persistir; y la distinción documentada entre reproducibilidad de configuración, determinismo de ejecución y resultado estocástico.

## Evidencia
- `tools/harmessi_bench/storage.py`, `runner.py`, `cli.py`, `compare.py` (Change 1): `schema_version`, `evaluator_version`, `suite`, `cases_hash`.
- `tools/dsguard/repo.py`: `get_head`, `is_tree_clean`, `leer_en_commit` (lista blanca de subcomandos de Git; solo lectura) → se reusa, sin capa Git nueva.
- `tools/dsguard/skill_contract.superficie_de_ruta` y `.claude/skills/lead-data-scientist/skills/*.md`: el conjunto de skills/superficies Optimizable es hasheable.
- `harmessi_bench` es solo-checkout (no se instala en proyectos).

## Supuestos descartados
- Reproducibilidad bit a bit con LLMs: no se promete.
- Capturar variables de entorno, prompts completos o configuración arbitraria de provider: solo ids, hashes, versiones y campos de una lista blanca.
- Telemetría o servicio: la evidencia es local (`.harmessi/evals/<run_id>/`).

## Alcance
- `runmanifest.py` (nuevo): construcción del manifest (`manifest_version = 1`) con harmessi_version, commit y estado limpio/sucio (o `unknown`), hashes de skills y de superficies Optimizable, hash de guardrails (runtime policy), provider/model/effort, evaluator_version, suite/cases_hash, seed opcional, plataforma mínima, timestamps, `identity_hash`.
- `redact.py` (nuevo): redacción de rutas de usuario, emails y tokens; aplicada al persistir `stdout_excerpt` y `score.detail`.
- `storage.py`: persiste `run_manifest`; `compare.py`: `config_diff` entre manifests y reglas de comparabilidad; `cli.py`: `run --resume`, `--seed`, y protección de `run_id` existente con manifest.
- Resume safety: `evaluar_compatibilidad(existente, nuevo)` → incompatibilidades materiales (manifest_version, harmessi_version, suite/cases_hash, skill set/superficies, evaluator_version, provider, model, contract versions) → fallo explícito; no mezcla evidencia.
- Docs: ARCHITECTURE.md, README.md, roadmap (niveles de reproducibilidad y límites).

## Fuera de alcance
Conformance de providers/adapters (Change 3); portabilidad/CI (Change 4); inventario de contratos (Change 5); generación o promoción de candidates; telemetría; cambios de versión de producto.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- tools/harmessi_bench/__init__.py
- tools/harmessi_bench/core.py
- tools/harmessi_bench/runmanifest.py
- tools/harmessi_bench/redact.py
- tools/harmessi_bench/storage.py
- tools/harmessi_bench/compare.py
- tools/harmessi_bench/runner.py
- tools/harmessi_bench/cli.py
- tools/harmessi_bench/suite.py
- tools/harmessi_bench/tests/*.py
- tools/tests/test_v05_core_neutrality.py
- tools/tests/test_v013_run_manifest_smoke.py
- ARCHITECTURE.md
- README.md
- docs/roadmap/v0.13.md
- openspec/changes/20261021-v013-reproducible-harness-runs/**
