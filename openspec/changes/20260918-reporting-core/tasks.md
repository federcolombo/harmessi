# Tareas — 20260918-reporting-core

estado: cerrada

## Invocaciones planificadas
1. `python-data-engineer` (writer, esta invocación) — redacta los 4 artefactos SDD y declara el
   alcance en `control.json` (`alcance.rutas_autorizadas`). No escribe código.
2. `python-data-engineer` (writer, implementación) — implementa `tools/reporting/__init__.py`,
   `core.py`, los tests (`tools/reporting/tests/`, `tools/tests/test_v06_core_neutrality.py`),
   las entradas de `MANIFEST`, `MODULOS_CORE`, `ARCHITECTURE.md` y el estado "EN CURSO" del
   roadmap. No ejecuta nada (sin herramienta de ejecución).
3. Lead — corre los tests nuevos y la suite completa (incluye `tools/ds_init/tests/`,
   `tools/tests/test_architecture_boundaries.py`, `test_v05_core_neutrality.py`,
   `test_manifest_dsguard_parity.py`) y `python -m tools.ds_init.check_manifest_parity`; entrega
   los resultados reales.
4. `data-science-reviewer` — revisa el diff completo (SDD + implementación), solo lectura.
5. `python-data-engineer` (writer, cierre) — aplica fixes de la revisión, escribe
   `verification.md` con la evidencia real del Lead, tilda `[x] Change 0` en
   `docs/roadmap/v0.6.md` y deja `estado: en_verificacion`.

## Tareas
- [ ] `tools/reporting/__init__.py` mínimo (sin lógica ni imports de hermanos).
- [ ] `tools/reporting/core.py`: vocabularios, constantes canónicas, `SCHEMA_VERSION`,
      `ReportingContractError`, validador de ids, normalización JSON-segura con copia profunda.
- [ ] `core.py`: `TableArtifact` (+ `from_rows`, `from_frame` con duck typing y coerción de
      celdas), `FigureSpec` (+ `columns_used()`), `FigureArtifact`, `Insight`, `Chapter`,
      `Report` (unicidad, accesores `iter_*`/`get_*`).
- [ ] `core.py`: `to_dict()`/`from_dict()` por contrato, `canonical_json`,
      `Report.content_sha256()`.
- [ ] `tools/reporting/tests/__init__.py` y `test_core.py` (ortogonalidad 4×3, ids,
      `TableArtifact`, `from_frame` con dobles, `FigureSpec`, `FigureArtifact`, `Insight`,
      unicidad, no validación semántica, serialización/hash, copia profunda).
- [ ] `tools/reporting/tests/test_installability.py` (entradas de `MANIFEST` presentes,
      VERBATIM, `discovery`, fuentes existentes).
- [ ] `tools/tests/test_v06_core_neutrality.py` (imports permitidos de `core.py`, sin
      plotly/pandas/numpy/html/dsguard/ds_profile/tools.*, sin hermanos; dirección inversa:
      los demás paquetes no importan `reporting`).
- [ ] `tools/tests/test_architecture_boundaries.py`: agregar `tools/reporting/core.py` a
      `MODULOS_CORE`.
- [ ] `tools/ds_init/manifest.py`: dos entradas VERBATIM; leer antes
      `tools/ds_init/tests/test_manifest.py`, `test_manifest_dsguard_parity.py`,
      `test_control_file.py` y `tools/harmessi/tests/test_doctor.py` (usos de `MANIFEST`) y
      mantenerlos verdes sin editarlos (si fuera inevitable, listar la edición mínima en el
      alcance antes de hacerla).
- [ ] `ARCHITECTURE.md`: fila en §2.1 y regla 6 en §3.
- [ ] `docs/roadmap/v0.6.md`: reemplazar el bloque "Estado: PLANIFICADA..." por "EN CURSO en
      `v0.6-dev`" (el tildado `[x] Change 0` se hace en la invocación de cierre).
- [ ] `verification.md` (invocación 5).
- [ ] Tildar `[x] Change 0` en `docs/roadmap/v0.6.md` (invocación 5).

## Dependencias
- Ningún Change previo de v0.6 (es el primero). Depende de que exista la rama `v0.6-dev`.
- Lectura (no modificación) de `tools/ds_init/tests/test_manifest.py`,
  `tools/tests/test_manifest_dsguard_parity.py` y `tools/tests/test_v05_core_neutrality.py`
  como patrón/restricción.
- Los Changes 1–4 dependen de este (consumen `Report`, `FigureSpec.columns_used()`,
  `content_sha256()`, los nombres canónicos de archivo).
- Alcance autorizado (`control.json`): los 5 artefactos SDD, `verification.md`,
  `tools/reporting/{__init__,core}.py`, `tools/reporting/tests/{__init__,test_core,
  test_installability}.py`, `tools/tests/test_v06_core_neutrality.py`,
  `tools/tests/test_architecture_boundaries.py`, `tools/ds_init/manifest.py`,
  `ARCHITECTURE.md`, `docs/roadmap/v0.6.md`.

## Próximo paso exacto
Invocación 2: un writer implementa el código y los tests según `spec.md` R1–R17, sin ejecutar
nada, y avisa al Lead qué debe correr. (Estado: `propuesta_pendiente`, no `pausada_bloqueada`.)
