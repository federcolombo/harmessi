# Diseño — 20260911-ds-profile-project-eda

## Decisión metodológica/técnica
`ds_profile`: paquete nuevo `tools/ds_profile/` (`__init__.py`, `__main__.py`, `cli.py`, `io_readers.py`, `fingerprint.py`, `schema.py`, `column_stats.py`, `quality_flags.py`, `sampling.py`, `holdout_guard.py`, `report.py`), invocado `python -m tools.ds_profile run ...`, sin tocar `tools/ds_guard.py`. `io_readers.py` expone una interfaz común de lectura (iterador de chunks/filas + metadata de schema) con un lector CSV (stdlib `csv`+`statistics`) y un lector Parquet (`pyarrow`, import perezoso dentro de la función que lo necesita — nunca a nivel de módulo — capturando `ImportError` para terminar con exit 3 y mensaje claro). `fingerprint.py` calcula un hash sha256 streaming de los bytes crudos del archivo (sin normalización de línea, a diferencia de `hash_lf_v1`), local a este paquete. `holdout_guard.py` importa `dsguard.pathguard.cargar_config`/`resolver_ruta_relativa` y `dsguard.repo.path_matches_any` (mismo patrón `sys.path.insert` que ya usa `tools/nbrunner/execute.py:145-149`) para evaluar `--input` antes de abrirlo. Output vía `report.py`: ensambla el dict del JSON y lo escribe atómico (reusa el patrón `os.replace` ya usado en `dsguard.core.escribir_texto_atomico`, reimplementado localmente para no importar `dsguard.core` como dependencia dura de `ds_profile`); `--markdown` genera `profile.md` como formateador puro sobre el mismo dict, sin cálculo nuevo.

Project EDA: skill `.claude/skills/lead-data-scientist/eda.md` (cargado bajo demanda, mismo patrón que `kdd.md`) + plantilla `.claude/skills/lead-data-scientist/templates/eda.md` (secciones: Objetivo, Dataset y fingerprint, Cutoff/scope, Hallazgos, Riesgos de leakage, Hipótesis, Conclusiones válidas para modelado, Limitaciones). El artefacto `eda.md` de un cambio SDD es opcional y no se agrega a los artefactos fijos de `ds_guard init`/`ds_guard validate` — decisión explícita del usuario para no ampliar el alcance de gates existentes.

## Target (condicional — feature_engineering, modeling)
No aplica: no hay decisión de modelado en este cambio.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica: no hay decisión de modelado en este cambio.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica: no hay decisión de modelado en este cambio.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica directamente al contenido de este cambio (no genera features de un dataset real). Riesgo indirecto documentado: si `ds_profile`/Project EDA se usan mal (ignorando sus flags o el cutoff declarado), podrían dar una falsa sensación de seguridad anti-leakage — mitigado porque `ds_profile` nunca decide nada de negocio (solo hechos) y `eda.md` exige declarar cutoff/fingerprint explícitamente.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
Sampling con `RANDOM_STATE` fijo (semilla default 42, overridable vía `--seed`), reservoir sampling determinista sobre el stream de lectura — mismo input + misma semilla + mismos límites reproduce la misma muestra.

## Alternativas descartadas
- pandas para CSV también: descartado por decisión explícita del usuario (stdlib puro, sin instalar dependencias nuevas ahora); la interfaz de `io_readers.py` queda desacoplada para poder incorporarlo después sin rediseñar el resto.
- polars/duckdb/great_expectations/ydata-profiling: sin beneficio claro sobre el alcance pedido; sumarían dependencias pesadas no justificadas (CLAUDE.md §1).
- Integrar `ds_profile` en `tools/ds_guard.py` o `tools.harmessi`: descartado, confirmado explícitamente por el usuario — paquete propio.
- Ejecutar `ds_profile` vía `nbrunner`: descartado — es una consulta de solo lectura, no requiere manifest ni aprobación previa de corrida.
- `analysis/eda/` como árbol nuevo para el output de Project EDA: descartado a favor de `eda.md` dentro del cambio SDD existente (`openspec/changes/<id>/`), para no duplicar el lugar donde vive la evidencia de un cambio.
- Agregar el hash binario nuevo a `dsguard/core.py` (compartido con el futuro pendiente de `nbrunner`): descartado por ahora, queda local a `ds_profile` para minimizar archivos modificados fuera del paquete nuevo; se puede compartir más adelante si `nbrunner` lo necesita.

## Riesgos
- El enforcement de holdout vía `Bash`/`PowerShell` (el hook `PreToolUse` de `pathguard`) sigue siendo best-effort por texto — mitigado por la segunda capa dentro de `ds_profile` mismo (`holdout_guard.py`), que sí es determinista porque opera sobre el `--input` ya parseado por `argparse`, no sobre el string crudo del comando.
- Los umbrales de muestreo (2,000,000 filas / 500 MB) son un default razonable, no validado contra un dataset real de un proyecto instalado — documentado como limitación, ajustable por CLI.
- CSV sin pandas implica más código propio (cuantiles/`value_counts` a mano) — más superficie de bugs que reusar pandas, mitigado con tests exhaustivos por tipo de columna.
- Limitación conocida y aceptada para v0.2 (hallazgo de `data-science-reviewer` sobre la corrida de revisión de este cambio): la clasificación de dtype (`column_stats.clasificar_dtype`) evalúa `booleano` antes que `entero`, y el chequeo de `booleano` acepta el conjunto de valores `{"0","1"}` además de `{"true","false"}`. Una columna genuinamente entera cuyos valores observados (exactos o de la muestra) resultan ser subconjunto de `{0,1}` (p. ej. un conteo con rango bajo en un dataset chico) se clasifica como `booleano`, y por lo tanto no recibe `min`/`max`/`media`/`std`/`mediana`/`cuantiles` en el perfil (esos campos solo se calculan para `dtype` `entero`/`flotante`). Se documenta como limitación de v0.2 en vez de corregirse ahora para no reabrir el diseño de clasificación de dtype ya aprobado; una corrección futura debería decidir un criterio de desambiguación (p. ej. nombre de columna, o requerir ambos valores 0 y 1 presentes) con aprobación explícita, no cambiarse por iniciativa unilateral de una corrección de bug.

## Aprobación humana
Ver `proposal.md` — registro único por cambio, no se duplica acá.
