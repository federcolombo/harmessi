# Evaluación (`harmessi-bench`)

`harmessi-bench` corre un conjunto de casos (prompts con un criterio de acierto determinista) contra un provider real, guarda la corrida como JSON y permite comparar dos corridas. Sirve para detectar regresiones de comportamiento entre dos configuraciones del harness, no para medir calidad semántica.

Código: `tools/harmessi_bench/`. Se usa solo desde un checkout del repositorio (`python -m tools.harmessi_bench.cli ...`).

## Suite pública: `harmessi-core-synthetic`

Archivos: `tools/harmessi_bench/suites/harmessi-core-synthetic.suite.json` (manifest) y `harmessi-core-synthetic.cases.json` (casos). Los casos son sintéticos y genéricos.

Verificación del manifest:

```
python -m tools.harmessi_bench.cli suite-check --suite tools/harmessi_bench/suites/harmessi-core-synthetic.suite.json --json
```

Salida observada:

```json
{"valida": true, "suite_id": "harmessi-core-synthetic", "suite_version": 1,
 "suite_hash": "71ae5ae23c2a654fb0192169fec12d9b6ace24932334080951bc133f870c002b",
 "case_contract_version": 1, "casos": 9}
```

(La salida real es JSON indentado; acá se compactó.) Si cambia el contenido de la suite, cambia `suite_hash`.

### Casos

| case_id | categoría | scorer |
|---|---|---|
| `framing-aclarar-pedido` | problem-framing | `regex` |
| `framing-supuesto-explicito` | problem-framing | `contains` |
| `debugging-primer-paso` | debugging | `exact` |
| `debugging-causa-raiz` | debugging | `contains` |
| `domain-modeling-termino-ambiguo` | domain-modeling | `contains` |
| `codebase-design-reuso` | codebase-design | `regex` |
| `recovery-idempotencia` | recovery | `exact` |
| `tool-contract-json` | tool-contract | `regex` |
| `tool-contract-codigo-salida` | tool-contract | `contains` |

### Scorers

Son deterministas (`tools/harmessi_bench/core.py`):

- `regex`: pasa si `re.search(patron, texto)` encuentra coincidencia.
- `contains`: pasa si todos los `valores` aparecen como subcadena del texto.
- `exact`: pasa si `texto.strip() == valor` (se recortan solo los bordes).

El propio archivo de casos lo declara: son un proxy superficial de texto, no una medición semántica. Un modelo puede responder bien con otras palabras y fallar el caso, o cumplir el patrón sin razonar. No hay LLM-as-judge.

## Cómo correr

```
python -m tools.harmessi_bench.cli run \
  --suite tools/harmessi_bench/suites/harmessi-core-synthetic.suite.json \
  --provider <provider> --run-id <id>
```

Requiere un provider real registrado en `tools/providers` cuya CLI esté instalada y disponible (`detect()`); si no lo está, el comando termina con código 1. No existe un comando público para correr sin provider: el `FakeAdapter` es solo para los tests del repositorio. Estado de soporte de cada provider: `docs/providers.md`.

Opciones (`tools/harmessi_bench/cli.py`): `--model`, `--effort`, `--json`, `--resume` (completa una corrida existente corriendo solo los escenarios sin resultado `ok`), `--seed` (informativo: se registra en el manifest, el provider puede ignorarlo). `--scenarios <archivo>` es la alternativa a `--suite` para casos propios (mutuamente excluyentes).

`run_id` debe cumplir `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`, sin nombres reservados de Windows ni punto final. Un `run_id` que ya existe con `run_manifest` no se sobrescribe: usar `--resume` o un id nuevo.

### Códigos de salida

- `run`: 0 por defecto, aunque haya escenarios fallidos. Con `--fail-on-failure`, 1 si algún escenario no pasó (tras imprimir y guardar).
- `compare`: 0 si la comparación se realizó. Con `--fail-on-regression`, 1 solo si el veredicto es `baseline_better`.
- En ambos comandos 1 también es el código de error de uso (run_id inexistente o inválido, manifest inválido, provider no disponible, etc.). Un CI no distingue regresión de error sin leer la salida.

## Formato de `.harmessi/evals/<run_id>/result.json`

Escritura atómica (temporal + reemplazo). `schema_version` actual: 1; se leen 0 (legado, campo ausente) y 1; una versión mayor se rechaza. Campos (`tools/harmessi_bench/storage.py`):

- `schema_version`, `evaluator_version`, `run_id`, `harmessi_version`, `timestamp_utc`.
- `target`: `provider_id`, `model`, `effort`.
- `resultados`: lista, uno por caso, con `run_id`, `scenario_id`, `target`, `exit_code`, `ok`, `availability_error`, `duration_s`, `stdout_excerpt`, `score` (`passed`, `score`, `detail`), `harmessi_version`, `timestamp_utc`.
- `suite` (si se usó `--suite`): `suite_id`, `suite_version`, `suite_hash`.
- `cases_hash`: identifica el contenido de los casos corridos (también sin suite).
- `run_manifest` (aditivo): `manifest_version`, `run_id`, `harmessi_version`, `git` (`commit`, `clean`), `skills` (hashes), `surfaces_hash`, `guardrails_hash`, `target`, `evaluator_version`, `suite`, `cases_hash`, `seed`, `platform` (sistema, versión de Python, implementación), `started_utc`, `finished_utc`, `sesiones`, `problemas`, `identity_hash` (`tools/harmessi_bench/runmanifest.py`).

No se persiste el prompt ni secretos. `stdout_excerpt` está acotado y `score.detail` se trunca a 300 caracteres; ambos pasan por redacción best-effort (ver Límites).

## Comparar un candidato contra un baseline propio

Flujo: correr dos veces la misma suite con distinta configuración (por ejemplo, antes y después de cambiar una skill, o con otro modelo) y comparar.

```
python -m tools.harmessi_bench.cli run --suite <suite> --provider <p> --run-id base
# ... cambiar la configuración que se quiere evaluar ...
python -m tools.harmessi_bench.cli run --suite <suite> --provider <p> --run-id candidato
python -m tools.harmessi_bench.cli compare --baseline base --candidate candidato [--fail-on-regression]
```

`compare` (`tools/harmessi_bench/compare.py`) clasifica cada `scenario_id` común como regresión, mejora o sin cambio según `score.passed`, informa los casos presentes en un solo lado y las diferencias materiales de configuración (`config_diff`). Veredictos:

- `candidate_better`: al menos una mejora y ninguna regresión.
- `baseline_better`: al menos una regresión y ninguna mejora.
- `equivalent`: sin diferencias en `score.passed` (avisa si ningún caso pasa en ninguna corrida: en ese caso no es informativa).
- `inconclusive`: ante duda. Entre otras causas: sin escenarios comunes, conjuntos de casos distintos, resultados con `ok=False` o `availability_error` (disponibilidad no es calidad), `suite`/`cases_hash`/`evaluator_version` distintos, un `run_manifest` ausente o incompleto en solo un lado, o regresiones y mejoras a la vez.

Cambiar provider, modelo, skills, superficies, guardrails o la versión de Harmessi no vuelve inconclusa la comparación: es lo que se evalúa y queda listado en `config_diff`.

## Límites

- Reproducibilidad por configuración, no bit-for-bit: el manifest registra versión, git, hashes de skills/superficies/guardrails, suite y casos, pero las respuestas de un modelo pueden variar entre corridas.
- `--seed` es informativo: se registra pero el provider puede ignorarlo.
- Redacción best-effort: `redactar_texto` (`tools/harmessi_bench/redact.py`) no garantiza eliminar todo secreto o dato personal de lo persistido.
- Solo desde checkout: no es una API ni un paquete instalable estable.
- Una muestra no es un baseline estadístico: cada comparación usa una sola corrida por lado y el veredicto lo declara (`una sola muestra`).
- Sin LLM-as-judge: solo `score.passed` determinista.
- Los scorers son un proxy superficial de texto (ver arriba).
- NO se publica baseline numérico: requiere provider real y solo hay un host live-validado (ver `docs/providers.md`). El baseline documentado es la configuración reproducible: `suite_version` + `suite_hash` + casos + formato de resultado.
