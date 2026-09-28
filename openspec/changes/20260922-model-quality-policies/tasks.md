# Tareas — 20260922-model-quality-policies

estado: cerrada

## Invocaciones planificadas
1. `python-data-engineer` (writer, esta invocación) — redacta los 4 artefactos SDD
   (`proposal.md`, `spec.md`, `design.md`, `tasks.md`). No escribe código, no toca
   `control.json`. El Lead revisa, decide sobre los supuestos/dudas señalados en el
   reporte de cierre (selección de `ObservedMetric`/`BaselineReference` ambigua = `WARN`,
   `evidence_ref` como `Optional[str]` genérico sin hash, las tres fórmulas de
   `comparison_mode`, el nombre `tools/modelquality`) y, si aprueba, declara el alcance
   de la invocación 2 en `control.json` (`alcance.rutas_autorizadas`) antes de aprobarla.
2. `python-data-engineer` (writer, implementación) — implementa
   `tools/modelquality/__init__.py`, `core.py`, `validation.py`, los tests
   (`tools/modelquality/tests/`), `tools/tests/test_v07_modelquality_neutrality.py`, las
   dos líneas en `MODULOS_CORE` de `tools/tests/test_architecture_boundaries.py`, las
   tres entradas de `MANIFEST` y las dos filas + regla 8 de `ARCHITECTURE.md`. No ejecuta
   nada (sin herramienta de ejecución); avisa al Lead exactamente qué debe correr.
3. Lead — corre los tests nuevos y la suite completa (incluye
   `tools/modelquality/tests/`, `tools/tests/test_v07_modelquality_neutrality.py`,
   `tools/tests/test_architecture_boundaries.py`, `tools/tests/test_v05_core_neutrality.py`,
   `tools/tests/test_v06_core_neutrality.py`, `tools/tests/test_v07_core_neutrality.py`,
   `tools/tests/test_v07_validation_neutrality.py`, `tools/datacontracts/tests/`
   (regresión, deben seguir verdes sin ningún diff en ese paquete), `tools/ds_init/tests/`)
   y `python -m tools.ds_init.check_manifest_parity`; entrega los resultados reales.
4. `data-science-reviewer` — revisa el diff completo (SDD + implementación), solo
   lectura. Presta especial atención a: (a) que `evaluate_policy` nunca devuelva `PASS`
   sin `evidence_ref` presente (R15 de `spec.md`); (b) que el fold de `QUALITY-RESULT`
   sea genuinamente monotónico (nunca "mejora" al incorporar una etapa posterior); (c)
   que `tools/modelquality/core.py` sea solo-stdlib y no importe
   `tools.datacontracts`/`dsguard`/`ds_profile` en ningún caso; (d) que
   `tools/modelquality/validation.py` no tenga ninguna superficie de I/O ni de lectura de
   archivo (ninguna función que abra un `Path`); (e) que `tools/datacontracts/{core,
   validation}.py` no tengan ningún diff.
5. `python-data-engineer` (writer, cierre) — aplica fixes de la revisión, escribe
   `verification.md` con la evidencia real del Lead, tilda `[x] Change 2` en
   `docs/roadmap/v0.7.md` y deja `estado: en_verificacion`.

## Tareas
- [x] `proposal.md` (esta invocación).
- [x] `spec.md` (esta invocación).
- [x] `design.md` (esta invocación).
- [x] `tasks.md` (esta invocación).
- [x] `tools/modelquality/__init__.py` mínimo (sin lógica ni imports de hermanos).
- [x] `tools/modelquality/core.py`: vocabularios, `SCHEMA_VERSION`, `EXTENSION_PREFIX`,
      `ModelQualityError`, validadores de id (`^[a-z0-9][a-z0-9_-]{0,63}$` + reservados
      Windows, implementación propia) y de `metric_name` (`^[a-z][a-z0-9_]*$`,
      implementación propia), normalización JSON-segura con copia profunda (ver
      `spec.md` R1-R3).
- [x] `core.py`: `EvaluationContext`, `MetricRequirement` (regla de coherencia mínima
      threshold/baseline, ver R5), `ObservedMetric` (con validación de forma de
      `uncertainty`, R7), `BaselineReference`, `ModelQualityPolicy` (unicidad de
      `requirement_id`, accesores `get_requirement`/`requirements_for`).
- [x] `core.py`: `to_dict()`/`from_dict()` por dataclass, `canonical_json`,
      `ModelQualityPolicy.content_sha256()` (R11).
- [x] `tools/modelquality/validation.py`: constante `CODES` (11 códigos, R12), función
      de selección compartida (`metric_name` + coincidencia de contexto, usada tanto
      para `ObservedMetric` como para `BaselineReference`, R14.1/R14.4), las tres
      fórmulas de `comparison_mode` (R14.4), `_peor`/`_acumular` (fold monotónico, R14.5),
      gate de entrada `QUALITY-INPUT`, función pura `evaluate_policy(policy,
      observed_metrics, baselines=()) -> list` (R13/R14).
- [x] `tools/modelquality/tests/__init__.py` y `test_core.py` (ids, `metric_name`, los 2
      `uncertainty_kinds` con params válidos/inválidos, regla de coherencia mínima de
      `MetricRequirement`, unicidad de `requirement_id` en `ModelQualityPolicy`,
      serialización/hash, copia profunda, ausencia de parámetros de datos reales en
      cualquier constructor).
- [x] `tools/modelquality/tests/test_validation.py`: fixtures sintéticas de
      `ModelQualityPolicy` + `ObservedMetric`/`BaselineReference` (nunca un dataset ni
      modelo real); los 11 códigos con caso positivo y caso de violación; los 3 casos de
      selección fallida (`MISSING`/`MISMATCH`/`AMBIGUOUS`) con corte temprano
      verificado; las 3 fórmulas de `comparison_mode` con caso `PASS` y caso de
      violación cada una, más el caso `baseline.value == 0` bajo
      `relative_to_baseline`; nunca-`PASS`-sin-`evidence_ref` (R15); fold monotónico con
      al menos un caso de 3 etapas de distinta severidad; excepción inesperada
      convertida en `technical_error` sin propagar ni afectar otros requirements.
- [x] `tools/modelquality/tests/test_installability.py` (entradas de `MANIFEST`
      presentes, VERBATIM, `discovery`, fuentes existentes).
- [x] `tools/tests/test_v07_modelquality_neutrality.py` (patrón `ast`, cubriendo AMBOS
      módulos: imports permitidos de `core.py` y de `validation.py` por separado, sin
      `tools.datacontracts`/`ds_profile`/`dsguard` en `core.py`, sin
      `tools.datacontracts`/`ds_profile`/pandas/numpy en `validation.py`; dirección
      inversa: `dsguard`, `ds_profile`, `dsimpact`, `reporting`, `tools.datacontracts`,
      `providers`, `routing`, `fallback`, `harmessi_bench` no importan
      `tools.modelquality`).
- [x] `tools/tests/test_architecture_boundaries.py`: agregar
      `tools/modelquality/core.py` y `tools/modelquality/validation.py` a
      `MODULOS_CORE`.
- [x] `tools/ds_init/manifest.py`: tres entradas VERBATIM; leer antes
      `tools/ds_init/tests/test_manifest.py`, `tools/tests/test_manifest_dsguard_parity.py`,
      `tools/ds_init/tests/test_control_file.py` y `tools/harmessi/tests/test_doctor.py`
      (usos de `MANIFEST`) y mantenerlos verdes sin editarlos (si fuera inevitable,
      listar la edición mínima en el alcance antes de hacerla).
- [x] `ARCHITECTURE.md`: dos filas en §2.1 y regla 8 en §3 (texto exacto en `design.md`).
- [x] `verification.md` (invocación 5).
- [x] Tildar `[x] Change 2` en `docs/roadmap/v0.7.md` (invocación 5; nada más del
      roadmap se toca).

## Dependencias
- Change 0 (`data-contracts-core`) y Change 1 (`data-contract-validation`), cerrados:
  este Change NO consume ningún tipo de `tools.datacontracts` (familia independiente,
  ver `design.md` decisión 1); la dependencia es solo de PRECEDENTE de patrón (dataclass
  `frozen=True`, función pura + `CheckResult`, `canonical_json`/`content_sha256`), no de
  código compartido.
- Lectura (no modificación) de `tools/dsguard/checks.py` (vocabulario `CheckResult`),
  `tools/datacontracts/core.py` y `validation.py` (patrón de referencia, sin importarlos),
  `ARCHITECTURE.md` (regla 7, precedente directo de la regla 8 nueva).
- Los Changes 3-5 de v0.7 dependen de este (consumen `ModelQualityPolicy`,
  `MetricRequirement`, `ObservedMetric`, `BaselineReference`, `EvaluationContext`,
  `evaluate_policy`, los códigos `QUALITY-*`); en particular, Change 3 decidirá si
  reinterpreta `evidence_ref` como una ruta persistida con hash, sin que este Change se
  comprometa de antemano con esa forma (ver `design.md`, decisión 2).
- Alcance a autorizar en `control.json` (`alcance.rutas_autorizadas`) para la
  invocación 2, exactamente estas rutas:
  - `openspec/changes/20260922-model-quality-policies/proposal.md`
  - `openspec/changes/20260922-model-quality-policies/spec.md`
  - `openspec/changes/20260922-model-quality-policies/design.md`
  - `openspec/changes/20260922-model-quality-policies/tasks.md`
  - `tools/modelquality/__init__.py`
  - `tools/modelquality/core.py`
  - `tools/modelquality/validation.py`
  - `tools/modelquality/tests/__init__.py`
  - `tools/modelquality/tests/test_core.py`
  - `tools/modelquality/tests/test_validation.py`
  - `tools/modelquality/tests/test_installability.py`
  - `tools/tests/test_v07_modelquality_neutrality.py`
  - `tools/tests/test_architecture_boundaries.py`
  - `tools/ds_init/manifest.py`
  - `ARCHITECTURE.md`
  - `docs/roadmap/v0.7.md` (solo para tildar `[x] Change 2`, al cierre — invocación 5)

  Deliberadamente NO incluye ningún archivo de `tools/datacontracts/` (Changes 0-1,
  cerrados) — si la implementación descubriera una necesidad real de tocar algo ahí,
  corresponde señalarlo al Lead como duda antes de escribir, no asumir el permiso de
  este alcance.

## Próximo paso exacto
El Lead revisa estos 4 artefactos contra `docs/roadmap/v0.7.md` (en particular la
decisión 1 y el orden de evaluación confirmado, secciones 228-294), `ARCHITECTURE.md` y
el precedente de `tools/datacontracts`, decide sobre los supuestos/dudas señalados en el
reporte de cierre de esta invocación (semántica exacta de los tres `comparison_mode`,
`evidence_ref` como `Optional[str]` sin hash, selección `WARN`-si-ambigua en vez de
heurística, ausencia de `ContractVersion`-análogo para `ModelQualityPolicy`), y si los
aprueba declara el alcance de la invocación 2 en `control.json` y la aprueba
(`ds_guard approve`). Invocación 2: un writer implementa el código y los tests según
`spec.md` R1-R21, sin ejecutar nada, y avisa al Lead qué debe correr. (Estado:
`propuesta_pendiente`, no `pausada_bloqueada`.)
