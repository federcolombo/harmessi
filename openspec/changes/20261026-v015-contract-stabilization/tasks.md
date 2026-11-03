# Tareas — 20261026-v015-contract-stabilization

estado: cerrada

## Invocaciones planificadas
- Writer SDD (esta etapa): proposal, spec, design, tasks.
- Reviewer (un solo ciclo previsto): revisión de proposal/spec/design antes de aprobar.
- Writer implementación (python-data-engineer): T1..T12 dentro del alcance autorizado, sin ejecutar.
- Lead: corre `generate_v014.py` sobre `git archive v0.14.0`, obtiene los baselines con
  `git show`, y corre los tests nuevos/afectados (sin regresión completa).
- Reviewer de cierre: verifica criterios R1..R11 contra evidencia.

## Ownership de writers
<!-- solo si se lanzan 2+ instancias writer en paralelo; declarar ANTES de lanzar.
### W1 — python-data-engineer — T1
- ruta/archivo.py
- directorio/**
-->

## Historial de ownership
<!-- fecha — instancia — ruta — motivo (cambios de ownership hechos ANTES de que el writer edite) -->

## Skills cargados
<!-- - <skill> — <tarea> — <motivo>  (solo si la skill cambió una decisión, un criterio de aceptación, la delegación —incluido el puntero a la skill en el campo 2—, el scope/ownership o el diseño; si sin ella el resultado habría sido otro. Una lectura exploratoria sin efecto, o una skill que perdió un conflicto sin influir, no lleva bullet. Un bullet por skill; si hubo conflicto, el criterio va en el motivo del bullet de la que ganó) -->

## Tareas
- [x] T1 (R4) `tools/harmessi_bench/runmanifest.py`: validar `manifest_version` en
  `evaluar_compatibilidad` (futura/no entera/bool -> incompatible con razón); sin cambiar
  `MANIFEST_VERSION`. Tests en `tools/harmessi_bench/tests/test_runmanifest.py`.
- [x] T2 (R7) `tools/harmessi/deprecation.py`: campo `guia`, validación en `validar_registro`, guía en
  el mensaje de `advertir`; registro vacío. Tests en `tools/harmessi/tests/test_deprecation.py`
  incluido el cruce con inventory (pasa vacío; falla con nombre inexistente inyectado).
- [x] T3 (R6) `tools/harmessi_bench/cli.py`: flag opt-in `--fail-on-regression` en `compare` (exit 1
  según el criterio de regresión existente; default 0 intacto). Tests en
  `tools/harmessi_bench/tests/test_cli.py` (con y sin flag).
- [x] T4 (R6) Tests de exit codes documentados en `tools/harmessi/tests/test_cli.py`,
  `tools/ds_init/tests/test_cli.py` y `tools/harmessi_improve/tests/test_cli.py`; si un código no
  documentado exige cambio fuera del envelope, devolver al Lead.
- [x] T5 (R3) Escribir `tools/tests/fixtures/compat/generate_v014.py` (solo-checkout; flujo candidate
  -> probe -> decide --apply -> promote propose -> lesson add; copia a `fixtures/compat/v0_14/`;
  uso y recreación del árbol con `git archive v0.14.0` documentados en el docstring).
- [x] T6 (R3, R5) Pedir al Lead: ejecutar el generador y `git show v0.13.0:.ds_init/control.json` /
  `git show v0.14.0:.ds_init/control.json` hacia `fixtures/compat/v0_13/` y `v0_14/`. El Writer no
  ejecuta ni edita a mano los fixtures; verificar que existan antes de cerrar T7.
- [x] T7 (R1, R2, R3, R5, R10) `tools/tests/test_v015_compat_window.py`: ancla de ventana en doc,
  lectura de fixtures con lectores actuales, regeneración estructural con skip si falta el tag,
  rechazos por lector (desconocido/ausente/no soportada/sin versión), baselines v0_13/v0_14,
  constantes de versión.
- [x] T8 (R1) `tools/tests/test_v013_compat_window.py`: marcar los tests v0.11/v0.12 como best-effort
  (docstring/comentario) sin cambiar aserciones.
- [x] T9 (R9) `docs/contracts/inventory.json`: campo `compat` en las entradas requeridas; exit codes
  garantizados en las 3 CLIs; nota de baseline sin `schema_version`; `inventory_version` y conteo 50
  intactos. `tools/tests/test_v013_contract_inventory.py`: test que exige `compat` y valida claves.
  Ajustar mínimamente los smokes v0.13/v0.14 solo si hace falta, sin tocar el pin `==1`.
- [x] T10 (R1, R2, R5, R8) `docs/versioning.md` y `docs/contracts/README.md`: ventana, tabla de compat
  por contrato improve, regla de bump, decisión del baseline, SemVer 0.x vs 1.x por tipo, cambio
  incompatible, promoción, nomenclatura, exit codes garantizados.
- [x] T11 (R7) `docs/deprecation.md`: política completa, mapeo de nombres, ejemplo trabajado,
  visibilidad (stderr y notas de release).
- [x] T12 (R11) `ARCHITECTURE.md` (referencias breves), `docs/roadmap/v0.15-debt-matrix.md` (B-01..B-06
  con evidencia) y `docs/roadmap/v0.15.md` §C1 (estado), tras la corrida del Lead.

## Dependencias
- T6 depende de T5 y de los tags locales `v0.13.0`/`v0.14.0`.
- T7 depende de T1 (manifest) y T6 (fixtures); T9 y T10 dependen de las decisiones D5/D6; T12 depende
  de la corrida de tests por el Lead.
- Aprobación de `proposal.md` antes de cualquier edición de implementación.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->
