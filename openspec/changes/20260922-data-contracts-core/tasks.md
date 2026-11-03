# Tareas — 20260922-data-contracts-core

estado: cerrada

## Invocaciones planificadas
1. `python-data-engineer` (writer, esta invocación) — redacta los 4 artefactos SDD
   (`proposal.md`, `spec.md`, `design.md`, `tasks.md`). No escribe código, no toca
   `control.json`. El Lead declara el alcance en `control.json`
   (`alcance.rutas_autorizadas`) para la invocación 2 antes de aprobarla.
2. `python-data-engineer` (writer, implementación) — implementa
   `tools/datacontracts/__init__.py`, `core.py`, los tests
   (`tools/datacontracts/tests/`), `tools/tests/test_v07_core_neutrality.py`, la línea
   en `MODULOS_CORE` de `tools/tests/test_architecture_boundaries.py`, las dos entradas
   de `MANIFEST` y la fila/regla 7 de `ARCHITECTURE.md`. No ejecuta nada (sin
   herramienta de ejecución).
3. Lead — corre los tests nuevos y la suite completa (incluye
   `tools/datacontracts/tests/`, `tools/tests/test_v07_core_neutrality.py`,
   `tools/tests/test_architecture_boundaries.py`, `tools/tests/test_v05_core_neutrality.py`,
   `tools/tests/test_v06_core_neutrality.py`, `tools/ds_init/tests/`) y
   `python -m tools.ds_init.check_manifest_parity`; entrega los resultados reales.
4. `data-science-reviewer` — revisa el diff completo (SDD + implementación), solo
   lectura.
5. `python-data-engineer` (writer, cierre) — aplica fixes de la revisión, escribe
   `verification.md` con la evidencia real del Lead, tilda `[x] Change 0` en
   `docs/roadmap/v0.7.md` y deja `estado: en_verificacion`.

## Tareas
- [x] `proposal.md` (esta invocación).
- [x] `spec.md` (esta invocación).
- [x] `design.md` (esta invocación).
- [x] `tasks.md` (esta invocación).
- [x] `tools/datacontracts/__init__.py` mínimo (sin lógica ni imports de hermanos).
- [x] `tools/datacontracts/core.py`: vocabularios, `SCHEMA_VERSION`, `EXTENSION_PREFIX`,
      `DataContractError`, validador de ids de contrato (`^[a-z0-9][a-z0-9_-]{0,63}$` +
      reservados Windows) y validador de nombre de campo (`^[a-z][a-z0-9_]*$`),
      normalización JSON-segura con copia profunda.
- [x] `core.py`: `ContractField`, `Constraint` (validación de `params` por
      `constraint_type`, ver `spec.md` R6), `BusinessRule`, `ContractVersion`,
      `CompatibilityPolicy`, `DataContract` (unicidad, referencias de campo existentes,
      accesores `get_field`/`constraints_for`/`get_constraint`/`get_business_rule`).
- [x] `core.py`: `to_dict()`/`from_dict()` por contrato, `canonical_json`,
      `DataContract.content_sha256()`.
- [x] `tools/datacontracts/tests/__init__.py` y `test_core.py` (ids, nombres de campo,
      los 10 `constraint_type` con params válidos/inválidos, `BusinessRule` sin
      evaluación, `ContractVersion` semver, `CompatibilityPolicy` con los 6 campos
      requeridos, unicidad y referencias en `DataContract`, serialización/hash, copia
      profunda, ausencia de parámetros de datos reales en cualquier constructor).
- [x] `tools/datacontracts/tests/test_installability.py` (entradas de `MANIFEST`
      presentes, VERBATIM, `discovery`, fuentes existentes).
- [x] `tools/tests/test_v07_core_neutrality.py` (mismo patrón `ast` que
      `test_v06_core_neutrality.py`: imports permitidos de `core.py`, sin
      ds_profile/dsguard/pandas/numpy/reporting/tools.*, sin hermanos; dirección
      inversa: `dsguard`, `ds_profile`, `dsimpact`, `reporting`, `providers`,
      `routing`, `fallback`, `harmessi_bench` no importan `datacontracts`).
- [x] `tools/tests/test_architecture_boundaries.py`: agregar
      `tools/datacontracts/core.py` a `MODULOS_CORE`.
- [x] `tools/ds_init/manifest.py`: dos entradas VERBATIM; leer antes
      `tools/ds_init/tests/test_manifest.py`, `tools/tests/test_manifest_dsguard_parity.py`,
      `tools/ds_init/tests/test_control_file.py` y `tools/harmessi/tests/test_doctor.py`
      (usos de `MANIFEST`) y mantenerlos verdes sin editarlos (si fuera inevitable,
      listar la edición mínima en el alcance antes de hacerla).
- [x] `ARCHITECTURE.md`: fila en §2.1 y regla 7 en §3 (texto exacto en `design.md`).
- [x] `verification.md` (invocación 5).
- [x] Tildar `[x] Change 0` en `docs/roadmap/v0.7.md` (invocación 5; nada más del
      roadmap se toca).

## Dependencias
- Ningún Change previo de v0.7 (es el primero). Depende de que exista la rama
  `v0.7-dev` (o, si se trabaja sobre `v0.7-dev` directamente como muestra `git status`,
  de que el branch actual sea el correcto antes de commitear).
- Lectura (no modificación) de `tools/ds_init/tests/test_manifest.py`,
  `tools/tests/test_manifest_dsguard_parity.py`, `tools/tests/test_v05_core_neutrality.py`
  y `tools/tests/test_v06_core_neutrality.py` como patrón/restricción.
- Los Changes 1–5 de v0.7 dependen de este (consumen `DataContract`, `ContractField`,
  `Constraint`, `BusinessRule`, `ContractVersion`, `CompatibilityPolicy`,
  `content_sha256()`, los vocabularios canónicos).
- Alcance a autorizar en `control.json` (`alcance.rutas_autorizadas`) para la
  invocación 2, exactamente estas rutas:
  - `openspec/changes/20260922-data-contracts-core/proposal.md`
  - `openspec/changes/20260922-data-contracts-core/spec.md`
  - `openspec/changes/20260922-data-contracts-core/design.md`
  - `openspec/changes/20260922-data-contracts-core/tasks.md`
  - `tools/datacontracts/__init__.py`
  - `tools/datacontracts/core.py`
  - `tools/datacontracts/tests/__init__.py`
  - `tools/datacontracts/tests/test_core.py`
  - `tools/datacontracts/tests/test_installability.py`
  - `tools/tests/test_v07_core_neutrality.py`
  - `tools/tests/test_architecture_boundaries.py`
  - `tools/ds_init/manifest.py`
  - `ARCHITECTURE.md`
  - `docs/roadmap/v0.7.md` (solo para tildar `[x] Change 0`, al cierre — invocación 5)

## Próximo paso exacto
El Lead revisa estos 4 artefactos contra `docs/roadmap/v0.7.md` y `ARCHITECTURE.md`,
decide sobre los supuestos/dudas señalados en el reporte de cierre de esta invocación,
y si los aprueba declara el alcance de la invocación 2 en `control.json` y la aprueba
(`ds_guard approve`). Invocación 2: un writer implementa el código y los tests según
`spec.md` R1–R17, sin ejecutar nada, y avisa al Lead qué debe correr. (Estado:
`propuesta_pendiente`, no `pausada_bloqueada`.)
