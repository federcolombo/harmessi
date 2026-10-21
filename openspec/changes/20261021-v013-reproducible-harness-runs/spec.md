# Spec — 20261021-v013-reproducible-harness-runs

## A. Run manifest
**R1.** `runmanifest.MANIFEST_VERSION = 1`. `construir_manifest(...)` devuelve un dict JSON-serializable con: `manifest_version`, `run_id`, `harmessi_version`, `git` (`commit`, `clean`; `"unknown"`/`None` si Git no puede leerse de forma confiable — nunca un valor inventado), `skills` (nombre → sha256 de contenido de `.claude/skills/lead-data-scientist/skills/*.md`), `surfaces_hash` (hash de las superficies Optimizable), `guardrails_hash` (hash de la política de runtime, o `null` si no existe), `target` (`provider_id`, `model`, `effort`), `evaluator_version`, `suite` (`suite_id`, `suite_version`, `suite_hash`) o `null`, `cases_hash`, `seed` (o `null`), `platform` (`system`, `python`, `implementation`), `started_utc`, `finished_utc`, `identity_hash`.
**R2.** `identity_hash` = sha256 de la serialización canónica de los campos **materiales** (todos salvo `run_id`, `started_utc`, `finished_utc`, `platform`, `git.clean` y `seed` informativo); dos corridas con la misma configuración material tienen el mismo `identity_hash`. Hash de contenido normalizando finales de línea (CRLF = LF) para no depender del SO.
**R3.** Lectura de Git solo vía `tools.dsguard.repo` (`get_head`, `is_tree_clean`); fallo ⇒ `commit = "unknown"`, `clean = null`, sin excepción. Unknown ≠ clean.
**R4.** El manifest no contiene: variables de entorno, hostname, usuario, rutas absolutas, prompts completos, salidas del modelo ni credenciales. Solo ids, hashes y versiones.

## B. Redacción
**R5.** `redact.redactar_texto(texto)` reemplaza: rutas de usuario (Windows `X:\Users\<n>\...`, POSIX `/home/<n>/`, `/Users/<n>/`), emails y tokens (prefijos `sk-`, `ghp_`, `github_pat_`, `AKIA`, `xox*-`, `Bearer <tok>`, cadenas largas hex/base64 tras `key|token|secret|password=`), por marcadores (`<RUTA_USUARIO>`, `<EMAIL>`, `<TOKEN>`). Idempotente, nunca lanza, `None`/no-str intactos.
**R6.** `save_run` aplica `redactar_texto` a `stdout_excerpt` y `score.detail` de cada resultado antes de persistir (además del acotado existente).

## C. Persistencia y comparación
**R7.** `save_run(..., run_manifest=None)` guarda el bloque `run_manifest` (opcional, aditivo; `schema_version` sigue en 1). `load_run` lo devuelve tal cual; ausente ⇒ corrida sin manifest.
**R8.** `compare_runs` agrega `config_diff` (lista ordenada de claves materiales que difieren entre manifests, vacía si no hay o falta alguno) y mantiene el resto. Si solo una corrida tiene manifest ⇒ `inconclusive` (motivo explícito). Si ambos tienen manifest y difieren `manifest_version`, `evaluator_version`, `suite`/`cases_hash` ⇒ `inconclusive`. Diferencias en skills/superficies/provider/model son lo que se compara: no son `inconclusive`, se listan en `config_diff`. Ninguna corrida con manifest sin los campos requeridos ⇒ `inconclusive`.
**R9.** Misma `identity_hash` en baseline y candidate ⇒ el motivo lo registra («misma configuración material: repetición»); el veredicto se decide igual por score.

## D. Resume safety
**R10.** `evaluar_compatibilidad(existente, nuevo)` devuelve la lista de incompatibilidades materiales entre dos manifests: `manifest_version`, `harmessi_version`, `suite`, `cases_hash`, `skills`, `surfaces_hash`, `guardrails_hash`, `evaluator_version`, `target.provider_id`, `target.model`, `target.effort`. Lista vacía ⇒ compatible. `git.commit` distinto sin otras diferencias es compatible con advertencia (no material).
**R11.** CLI `run --resume`: requiere que `<root>/<run_id>/result.json` exista y tenga `run_manifest`; si hay incompatibilidades ⇒ exit 1 con las razones (nunca mezcla evidencia, no modifica el result existente); si es compatible, solo corre los escenarios sin resultado `ok=True` y combina los resultados. Sin `--resume`, un `run_id` existente **con** manifest ⇒ exit 1 (pedir `--resume` o un `run_id` nuevo); un `run_id` legado sin manifest se sobrescribe como hasta ahora.
**R12.** `run --seed N` registra el seed en el manifest (informativo; no se afirma que el provider lo respete).

## E. Niveles y límites
**R13.** La documentación distingue reproducibilidad de configuración (identity_hash), determinismo de ejecución (solo scorers y compare; no el modelo) y resultado estocástico (LLM), sin promesa bit a bit.
**R14.** Cero telemetría; todo local en `.harmessi/evals/<run_id>/`.

## F. Boundaries
**R15.** `runmanifest.py` y `redact.py` no importan providers, red ni `subprocess` (Git vía `dsguard.repo`); no escriben fuera de `storage`. Nada promueve ni modifica superficies.

## Criterios de aceptación
- [ ] R1–R4 manifest. - [ ] R5–R6 redacción. - [ ] R7–R9 persistencia y comparación. - [ ] R10–R12 resume. - [ ] R13–R15 docs y boundaries.
- [ ] Tests de `tools/harmessi_bench`, neutralidad, smoke del Change y manifest-completitud verdes.
