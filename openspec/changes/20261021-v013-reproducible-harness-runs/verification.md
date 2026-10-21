# Verificación — 20261021-v013-reproducible-harness-runs

## Resumen
Run manifest versionado (`manifest_version = 1`) con `identity_hash`, redacción best-effort de datos sensibles, escritura atómica de `result.json`, `run --resume` con rechazo explícito de configuración incompatible, `--seed`, validación de `run_id`, `sesiones` de procedencia y `config_diff` en `compare`.

## Evidencia obtenida
- pytest serial sobre `tools/harmessi_bench/tests`, smokes `test_v013_run_manifest_smoke` y `test_v013_eval_foundation_smoke`, `test_v05_core_neutrality`, `test_architecture_boundaries`, `test_manifest_completitud`: 318 passed.
- `ds_guard validate`: sin hallazgos.
- Reviewer ciclo 1: 0 blocker, 2 HIGH (escritura no atómica; manifest recomputado tras la corrida), MED/LOW. Fixes aplicados (atómico con tmp + `os.replace`, manifest del inicio y verificación de identidad al terminar, hashes ilegibles ⇒ manifest incompleto ⇒ no se corre ni persiste, `sesiones`, redacción ampliada, `run_id` validado, `run_manifest` inválido ⇒ fail-closed).
- Reviewer ciclo 2 (justificado por los HIGH): sin blocker ni HIGH nuevos.

## Divergencias respecto del SDD
- spec R2 lista `git.commit` como material por omisión de la lista de exclusiones; R10 y design lo declaran informativo. La implementación sigue R10/design (el commit no entra en `identity_hash`; la identidad es el contenido de skills/superficies/guardrails/evaluator/target). Se documenta en ARCHITECTURE §10.1.
- Campos adicionales no materiales: `sesiones`, `problemas`.

## Limitaciones conocidas (deuda)
Sin soporte de ejecuciones concurrentes sobre el mismo `run_id` (single-writer); la identidad no cubre agents/CLAUDE.md/código de tools; redacción best-effort (valores sin comillas < 16 caracteres, valores no string, sobre-redacción de `/users/` en URLs, `stdout_excerpt` se corta antes de redactar); `run_id` reservado en Windows (`nul`, `con`) falla tras invocar al provider; result existente corrupto con campos nulos produce traceback; `run` con todos los escenarios `ok=False` devuelve exit 0.

## Niveles de reproducibilidad
Configuración (identity_hash) ≠ determinismo de ejecución (solo scorers y compare) ≠ resultado estocástico (LLM). Sin promesa bit a bit.

## Resultado final
Change 2 verificado con tests focalizados verdes. Listo para commit.
