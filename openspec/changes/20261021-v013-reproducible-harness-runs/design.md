# Diseño — 20261021-v013-reproducible-harness-runs

## Principio
Ids + hashes + versiones. El manifest identifica la configuración, no registra el contenido. Todo opcional/aditivo para no romper corridas del Change 1 ni v0.5.

## Piezas
- `runmanifest.py`: `construir_manifest`, `calcular_identity_hash`, `evaluar_compatibilidad`, `hash_skills`, `hash_superficies`. Lectura de archivos con normalización CRLF→LF antes de hashear. Git solo vía `dsguard.repo` con captura de cualquier excepción (unknown).
- `redact.py`: regex puras; marcadores fijos; idempotente.
- `storage.py`: aplica `redactar_texto` al serializar, persiste `run_manifest`.
- `compare.py`: `config_diff` y reglas de comparabilidad por manifest.
- `cli.py`: `--resume`, `--seed`, protección de `run_id` existente con manifest.

## Decisiones
- **Qué es material**: lo que cambia la identidad de la evidencia (harness version, suite/casos, skills/superficies, guardrails, evaluator, provider/model/effort). El commit es informativo porque cambia en cada Change sin alterar las superficies; la identidad de las superficies es el hash de contenido.
- **Qué es comparable**: baseline y candidate pueden diferir en skills/superficies/provider (eso es lo que se evalúa) pero no en suite/casos/evaluator.
- **Resume**: nunca fusiona resultados de configuraciones distintas; la incompatibilidad es explícita y no destructiva.
- **Unknown ≠ clean**: si Git no responde, se registra `unknown`, no se asume árbol limpio.
- **Sin entorno**: no se captura `os.environ` ni nombre de host/usuario; plataforma mínima (`system`, versión de Python, implementación).
- **Redacción best-effort**: reduce fugas accidentales; no es garantía criptográfica. Se documenta.

## Riesgos
Falsos positivos de redacción (se prefiere sobre-redactar); regex de tokens no exhaustivas (documentado).

## No se reabre
Roles, T0/T1, ubicación `.harmessi/evals`, veredicto determinista de Change 1.

## Decisiones materiales pendientes
Ninguna.
