# Propuesta — 20260911-ds-profile-project-eda

## Problema
No existe ningún profiling determinista de datos en Harmessi, ni una definición operativa de qué EDA es válida para decisiones de modelado (respetando cutoff, holdout y anti-leakage). Sin esto, cualquier exploración de datos que informe target/features/modelo queda sin evidencia reproducible ni trazabilidad de qué dataset/fingerprint la sustenta.

## Objetivo
Agregar `ds_profile` (CLI Python determinista que calcula hechos y flags sobre un dataset) y definir Project EDA (proceso/skill que interpreta esos hechos respetando cutoff/holdout, sin decidir automáticamente nada de negocio).

## Evidencia
- `tools/dsguard/core.py:26` (`hash_lf_v1`): hash de texto normalizado a LF, no aplicable a datasets binarios — confirma que hace falta un hash nuevo.
- `.venv/Scripts/python.exe -m pip list` (corrida real): solo `pytest` instalado; no hay pandas/pyarrow/numpy/nbformat/nbclient/psutil, ni `requirements*.txt`/`pyproject.toml` en el repo.
- `tools/nbrunner/execute.py` (413 líneas, leído completo): ejecuta notebooks de verdad vía `nbclient`, pero no existe `tools/notebook_runner.py` (el CLI que lo expondría) ni `tools/tests/test_nbrunner.py`, aunque está referenciado en `EXCLUSIONES_PERMANENTES` de `tools/ds_init/manifest.py:341`.
- `tools/dsguard/pathguard.py` (457 líneas, leído completo): `cargar_config`, `resolver_ruta_relativa`, `dsguard.repo.path_matches_any` son la API pública reusable para defensa en profundidad de holdouts; garantía real para `Read`/`Write`/`Edit`/`NotebookEdit`, best-effort por texto para `Bash`/`PowerShell` (`_evaluar_shell`).
- `.claude/skills/lead-data-scientist/kdd.md` §8: ya reserva `spec.md → ## Unidad de análisis`, `spec.md → ## Cutoff / information boundary` y `verification.md → ## Fingerprint de dataset/artefacto` como anclajes — no hace falta tocar `kdd.py`.
- `tools/ds_init/manifest.py:107-346`: patrón exacto de instalación (`EntradaManifiesto`, tratamientos `VERBATIM`/`PLANTILLA`/`GENERADO`/`MERGE`, `EXCLUSIONES_PERMANENTES`).

## Supuestos descartados
- Se creyó que podía convenir integrar `ds_profile` dentro de `tools/ds_guard.py` o de `tools.harmessi` — descartado: el usuario confirmó explícitamente paquete propio `tools/ds_profile/`, invocado `python -m tools.ds_profile`, sin tocar `ds_guard.py`.
- Se evaluó usar pandas para CSV también — descartado: el usuario confirmó CSV con stdlib puro (`csv`+`statistics`), sin pandas, para no instalar nada nuevo ahora.
- Se evaluó reusar `nbrunner` como vehículo de ejecución de `ds_profile` — descartado: `ds_profile` es de solo lectura y determinista, no requiere manifest ni aprobación previa de una corrida.
- Se evaluó agregar el hash binario nuevo a `dsguard/core.py` (compartido con el futuro pendiente de `nbrunner`) — descartado por ahora: queda local a `tools/ds_profile/fingerprint.py` para minimizar archivos modificados fuera del paquete nuevo.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica: cambio de alto riesgo técnico (harness/tooling), sin decisión de ML de fondo (target/features/modelo).

## Alcance
Ver `spec.md` (Requisitos) y `design.md` (Decisión técnica) para el detalle completo. Resumen: paquete `tools/ds_profile/` (CLI + cálculo determinista + tests), skill `eda.md` + plantilla `templates/eda.md`, actualización de `tools/ds_init/manifest.py` y `.claude/skills/lead-data-scientist/SKILL.md`.

## Fuera de alcance
EDA exploratoria/personal con todo el histórico bajo autorización; `report-analyst`; `/report eda`; HTML/report engine; empaquetado de figuras/tablas; multi-provider; enforcement automático (`enforceable`) de cutoff/boundary en gates KDD; `tools/notebook_runner.py`/ejecución automatizada de EDA vía `nbrunner`; nuevos criterios detectables en `kdd.py`; instalar pandas/pyarrow/cualquier dependencia nueva de forma automática.

## Holdout policy (condicional — solo cambios "sensible")
No aplica: esta categoría no es "sensible", no hay acceso a holdout de ningún dataset real involucrado en este cambio.

## Impacto en production-readiness (opcional)
No aplica en v0.2 (etapa KDD `production_readiness` todavía `futura`).

## Criterios de aceptación (spec-lite — solo SDD abreviado)
No aplica: SDD completo, ver `spec.md`.

## Decisión técnica (design-lite — solo SDD abreviado)
No aplica: SDD completo, ver `design.md`.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-11
- Alcance aprobado: el descrito arriba en "Alcance", con las 6 decisiones confirmadas explícitas (CLI en `tools/ds_profile/` sin tocar `ds_guard.py`; output `.harmessi/profiles/<id>/profile.json` con JSON fuente de verdad; `eda.md` artefacto SDD opcional sin tocar el set fijo de `ds_guard init`; Parquet vía `pyarrow` import perezoso con exit 3 si falta; CSV con stdlib puro sin pandas, capa de lectura desacoplada; sin instalar dependencias nuevas ahora)
- Versión de artefactos referenciada: primer borrador de `proposal.md`/`spec.md`/`design.md`/`tasks.md` de este cambio (`20260911-ds-profile-project-eda`)
- Cita o descripción fiel de qué se aprobó: *"Confirmado: para v0.2 usar CSV con stdlib puro. [...] Aprobado el diseño final del Bloque 6. Avanzá ahora con el cambio SDD y la implementación del scope propuesto"*, con el detalle punto por punto de las secciones 1 a 10 de ese mensaje (paquete `tools/ds_profile/`, CLI, output, política exacta/muestreada, defensa en profundidad de holdouts, Project EDA/`eda.md`, model-valid EDA, actualización de manifest/SKILL.md, tests, regresión).

## Motivo de rechazo
No aplica.

## Desacuerdo registrado
No aplica.
