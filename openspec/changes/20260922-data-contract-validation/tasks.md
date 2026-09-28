# Tareas — 20260922-data-contract-validation

estado: cerrada

## Invocaciones planificadas
1. `python-data-engineer` (writer, esta invocación) — redacta los 4 artefactos SDD
   (`proposal.md`, `spec.md`, `design.md`, `tasks.md`). No escribe código, no toca
   `control.json`. El Lead revisa, decide sobre las dudas señaladas en el reporte de
   cierre (política de `CONTRACT-FIELD-UNEXPECTED`, import narrow de
   `ds_profile.holdout_guard`, alcance exacto de `ARCHITECTURE.md`) y, si aprueba,
   declara el alcance de la invocación 2 en `control.json`
   (`alcance.rutas_autorizadas`) antes de aprobarla.
2. `python-data-engineer` (writer, implementación) — implementa
   `tools/datacontracts/validation.py`, `tools/datacontracts/tests/test_validation.py`,
   `tools/tests/test_v07_validation_neutrality.py`, la línea en `MODULOS_CORE` de
   `tools/tests/test_architecture_boundaries.py`, la fila y la ampliación de la regla 7
   en `ARCHITECTURE.md`. No ejecuta nada (sin herramienta de ejecución); avisa al Lead
   exactamente qué debe correr.
3. Lead — corre los tests nuevos y la suite completa (incluye
   `tools/datacontracts/tests/` completo -- Change 0 y Change 1 -- ,
   `tools/tests/test_v07_core_neutrality.py`, `tools/tests/test_v07_validation_neutrality.py`,
   `tools/tests/test_architecture_boundaries.py`, `tools/tests/test_v05_core_neutrality.py`,
   `tools/tests/test_v06_core_neutrality.py`, `tools/ds_profile/tests/` -- regresión de
   `holdout_guard` sin tocar, `pytest tools -q` completo); entrega los resultados reales.
4. `data-science-reviewer` — revisa el diff completo (SDD + implementación), solo
   lectura. Presta especial atención a: (a) que `validate_contract` nunca devuelva
   `PASS` sin evidencia suficiente (R12 de `spec.md`), en particular los casos de
   `sampling.activo=True`; (b) que ningún `CheckResult` filtre `profile["dataset_path"]`
   ni ninguna ruta absoluta local (R3/R14); (c) que el import de
   `ds_profile.holdout_guard` sea EXACTAMENTE ese único símbolo, nada más de
   `ds_profile`; (d) que `tools/datacontracts/core.py` no tenga ningún diff.
5. `python-data-engineer` (writer, cierre) — aplica fixes de la revisión, escribe
   `verification.md` con la evidencia real del Lead, tilda `[x] Change 1` en
   `docs/roadmap/v0.7.md` y deja `estado: en_verificacion`.

## Tareas
- [x] `proposal.md` (esta invocación).
- [x] `spec.md` (esta invocación).
- [x] `design.md` (esta invocación).
- [x] `tasks.md` (esta invocación).
- [x] `tools/datacontracts/validation.py`: constante `CODES` (14 códigos, ver `spec.md`
      R2), bridge `_DTYPE_ESPERADO_POR_FAMILIA` (R6), gate de evidencia
      `CONTRACT-EVIDENCE-MISSING`/`CONTRACT-INPUT` (R3/R5), reglas estructurales
      (`CONTRACT-FIELD-MISSING`/`-UNEXPECTED`/`-TYPE-MISMATCH`/`-NULLABILITY`/`-KEY`,
      R6/R8/R9/R11), reglas por `constraint_type` (los 10 tipos, R10), función pura
      `validate_contract(contract, profile) -> list` (R3), función con I/O
      `validate_contract_against_profile_file(contract, profile_path, repo_root) ->
      list` usando `ds_profile.holdout_guard.verificar_permitido` (R4, decisión de
      diseño 3 -- si el Lead prefiere el default estricto, ver alternativa documentada
      en `design.md` antes de implementar).
- [x] `tools/datacontracts/tests/test_validation.py`: fixtures sintéticas de
      `DataContract` + `profile` dict (nunca un dataset real ni `ds_profile.run`); los
      14 códigos con caso positivo y caso de violación; corte temprano del gate de
      evidencia (perfil `None`/no-dict/sin claves mínimas); los tres casos de
      `unique.exactitud`; unicidad compuesta (`WARN` siempre); el bridge completo
      (7 `type_family`, incluido `"unknown"`); privacidad (`dataset_path` nunca en
      ningún `message`/`detail`/`subject`); nunca-`PASS`-por-falta-de-evidencia (R12);
      excepción inesperada convertida en `technical_error` sin propagar.
- [x] `tools/tests/test_v07_validation_neutrality.py`: mismo patrón `ast` que
      `test_v07_core_neutrality.py`, imports de `validation.py` limitados al set
      permitido (R1); regresión de que `core.py` sigue solo-stdlib; sanity de los
      detectores (violación de prueba detectada).
- [x] `tools/tests/test_architecture_boundaries.py`: agregar
      `tools/datacontracts/validation.py` a `MODULOS_CORE`.
- [x] `ARCHITECTURE.md`: fila nueva en §2.1 para `validation.py` y ampliación de texto
      de la regla 7 en §3 (texto exacto en `design.md`).
- [x] `verification.md` (invocación 5).
- [x] Tildar `[x] Change 1` en `docs/roadmap/v0.7.md` (invocación 5; nada más del
      roadmap se toca).

## Dependencias
- Change 0 (`data-contracts-core`), cerrado: este Change consume `DataContract`,
  `ContractField`, `Constraint`, `TYPE_FAMILIES`, `CONSTRAINT_TYPES`, `SEVERITIES` sin
  modificarlos.
- Lectura (no modificación) de `tools/ds_profile/holdout_guard.py` (solo el símbolo
  `verificar_permitido`), `tools/ds_profile/report.py`/`column_stats.py` (como
  referencia de forma de `profile.json`, sin importarlos), `tools/dsguard/checks.py`,
  `tools/reporting/validation.py` (patrón de referencia).
- Los Changes 2-5 de v0.7 dependen de este de forma indirecta (consumen el mismo
  vocabulario `PASS`/`WARN`/`FAIL`/`N/A` y el patrón función-pura-más-puerta-de-I/O), sin
  importar directamente `validate_contract` salvo que un Change futuro lo decida
  explícitamente en su propio SDD.
- Alcance a autorizar en `control.json` (`alcance.rutas_autorizadas`) para la
  invocación 2, exactamente estas rutas:
  - `openspec/changes/20260922-data-contract-validation/proposal.md`
  - `openspec/changes/20260922-data-contract-validation/spec.md`
  - `openspec/changes/20260922-data-contract-validation/design.md`
  - `openspec/changes/20260922-data-contract-validation/tasks.md`
  - `tools/datacontracts/validation.py`
  - `tools/datacontracts/tests/test_validation.py`
  - `tools/tests/test_v07_validation_neutrality.py`
  - `tools/tests/test_architecture_boundaries.py`
  - `ARCHITECTURE.md`
  - `docs/roadmap/v0.7.md` (solo para tildar `[x] Change 1`, al cierre — invocación 5)

  Deliberadamente NO incluye `tools/datacontracts/core.py` ni `tools/datacontracts/
  __init__.py` ni `tools/datacontracts/tests/test_core.py` — Change 0 está cerrado, y
  si la implementación descubriera una necesidad real de tocar `core.py`, corresponde
  señalarlo al Lead como duda antes de escribir ahí, no asumir el permiso de este
  alcance.

## Próximo paso exacto
El Lead revisa estos 4 artefactos contra `docs/roadmap/v0.7.md`, `ARCHITECTURE.md` y
`tools/datacontracts/core.py`, decide sobre las dudas señaladas en el reporte de cierre
de esta invocación (política de `CONTRACT-FIELD-UNEXPECTED`, import narrow de
`ds_profile.holdout_guard` vs. reimplementar con `dsguard.pathguard` directamente, si
hace falta tocar `ARCHITECTURE.md` con el texto propuesto), y si los aprueba declara el
alcance de la invocación 2 en `control.json` y la aprueba (`ds_guard approve`).
