# Tareas — 20260928-project-autonomy-contract

estado: cerrada

## Invocaciones planificadas

1. **python-data-engineer (esta, ya hecha)**: redacta `proposal.md`, `spec.md`, `design.md`,
   `tasks.md`. Sin codigo.
2. **python-data-engineer (implementacion)**: tras la aprobacion humana de la propuesta. Escribe
   `tools/autonomy/*`, tests, cambio en `pathguard.py`, manifest, `ARCHITECTURE.md`. No ejecuta.
3. **Lead (ejecucion)**: corre los tests nuevos, luego la suite completa
   `.venv/Scripts/python -m pytest tools -q` y `python -m tools.ds_init.check_manifest_parity`;
   entrega los resultados reales.
4. **data-science-reviewer**: revision de solo lectura del diff completo contra `spec.md`
   (R1-R19), con foco en seguridad de `pathguard`, fail-closed y neutralidad.
5. **python-data-engineer (cierre)**: aplica fixes del reviewer y de la ejecucion, escribe
   `verification.md` con evidencia real, tilda Change 0 en `docs/roadmap/v0.8.md` y deja
   `estado: en_verificacion`.

## Tareas

Invocacion 2 (lectura previa: `test_manifest.py`, `test_manifest_dsguard_parity.py`,
`test_control_file.py`, `tools/harmessi/tests/test_doctor.py` usos de MANIFEST):

- [x] T1 `tools/autonomy/__init__.py` y `core.py`: vocabulario, `PolicyDecision`, `POLICY_TABLE`,
  `resolve_action`, `AutonomyError`, catalogos STOP/LIMIT, `TECHNICAL_ERROR_CODE`, `ALL_CODES`,
  `ROLES`/`ROLE_CAPABILITIES`, `ApprovalRef` + `validate_approval_ref` + `to_dict`/`from_dict`,
  `PolicyApproval` (con `human_approval_ref: ApprovalRef`, `approved_by` canonico) + validacion +
  round-trip, `PreApprovedDecision` (con `approval_ref: ApprovalRef`, `artefacto == "proposal.md"`),
  `MethodologicalResolution` (`approval_ref: ApprovalRef | None`), `role_responsibilities`
  (derivada, sin segunda tabla), `is_reserved_policy_namespace`, `validate_human_identity`,
  `validate_human_approval_entry` (import `unicodedata`), codigos `AUTONOMY-APPROVAL-REF-INVALID`,
  `AUTONOMY-APPROVAL-INVALID`, `AUTONOMY-IDENTITY-INVALID`, `AUTONOMY-IDENTITY-RESERVED` en
  `ALL_CODES`, restriccion de `PolicyApproval.action_class`, `narrow_mode`, `PolicyFinding`
  (R2-R7, R9, R11, R16-R19).
- [x] T2 `tools/autonomy/policy.py`: `AutonomyPolicy`, `parse_autonomy_policy`,
  `is_source_sealed`, `effective_source_access` (incl. `sealed_unknown`, conservacion de sellos
  bajo degradacion), `sealed_coherence_findings` (matcher inyectado),
  `resolve_methodological_decision` (devuelve `MethodologicalResolution` con `approval_ref:
  ApprovalRef | None`) (R8, R10, R11).
- [x] T3 `tools/autonomy/tests/test_core.py`: tabla exhaustiva (una aserccion por fila x modo);
  STOP siempre stop en ambos modos; `DEFAULT_MODE` supervised; `narrow_mode` nunca amplia;
  invariantes de roles; `PolicyApproval` valida / invalida / round-trip mismos bytes;
  `PreApprovedDecision`; registro de codigos sin duplicados; constantes sin prosa. Tests nuevos
  (R16-R19): `ApprovalRef` valida / invalida (hash corto, mayusculas, artefacto con `..`,
  `change_id` invalido) / round-trip de bytes identicos; `PreApprovedDecision` sin ref -> hallazgo,
  con ref a otro artefacto -> hallazgo; resolucion listada devuelve la ref, no listada devuelve
  `None` + STOP 2; `PolicyApproval` y `PreApprovedDecision` usan el mismo tipo `ApprovalRef`;
  `role_responsibilities` exhaustivo rol x modo x action_class (consistente con la tabla, solo
  lead/human ejecutan, writer nunca ejecuta, STOP solo los decide human, la vista se recalcula desde
  `ROLE_CAPABILITIES` + `POLICY_TABLE` y no existe estructura rol x modo a mano);
  `is_reserved_policy_namespace` rechaza `policy:autonomous`, ` Policy:x`, `POLICY:x`, `policy：x`,
  `\tpolicy:x` y acepta `policyx`, `mypolicy:x`, `Federico`; `validate_human_identity`;
  `validate_human_approval_entry` (con `approved_by` -> hallazgo); policy approval con `usuario` ->
  hallazgo; `PolicyApproval` para `approve_proposal` o clase STOP invalida; ninguna fila de
  `POLICY_TABLE` con approval derivado de un LIMIT y `LIMIT_CATALOG ∩ STOP_CATALOG = ∅`.
- [x] T4 `tools/autonomy/tests/test_policy.py`: `parse_autonomy_policy` (valida, faltan limites,
  version desconocida, `autonomy` con version 1, guard `None`, guard version menor, tipos
  invalidos, claves desconocidas toleradas sin habilitar nada; sello conservado bajo degradacion
  por guard `None`; `sealed_unknown` bloquea toda fuente; ausencia de `autonomy` no bloquea
  nada); default sin policy = supervised;
  efectivo policy AND registro nunca mayor que la policy (recorrido exhaustivo); fuente sellada no
  observable aunque el registro la permita; coherencia con matcher; decision listada / no listada
  (con `approval_ref` devuelto / `None`).
- [x] T5 `tools/autonomy/tests/__init__.py` y `test_installability.py` (patron de
  `tools/datacontracts/tests/test_installability.py`).
- [x] T6 `tools/tests/test_v08_autonomy_neutrality.py` (`ast`, incluye direccion inversa) y
  `tools/tests/test_v08_writer_no_execution.py` (R13). El test de neutralidad permite `unicodedata`
  en `core.py` (R1) y afirma que `core.py` no importa `json`.
- [x] T7 `tools/tests/test_architecture_boundaries.py`: agregar `tools/autonomy/core.py` y
  `policy.py` a `MODULOS_CORE`.
- [x] T8 `tools/ds_init/manifest.py`: entradas VERBATIM (`stage_minimo` discovery) para los 3
  archivos del paquete; no editar los tests de manifest salvo necesidad demostrada (registrar
  como hallazgo).
- [x] T9 `tools/dsguard/pathguard.py`: `POLICY_VERSION_MAX = 2` y validacion de `version` en
  `cargar_config` (R12); sin otros cambios.
- [x] T10 `tools/tests/test_pathguard.py`: version ausente/1/2 ok; 0/3/`"2"`/`True`/`2.5`
  rechazadas; constante = 2; guardrails del repo carga; el hook deniega; doctor reporta el rechazo
  (sin tocar `doctor.py`).
- [x] T11 `ARCHITECTURE.md`: filas §2.1, regla de dependencia 10 (familia `tools/autonomy`) y en
  §6 "regla 10" -> "regla 11" para la familia de fuentes.

Invocaciones 3-5:

- [x] T12 Lead: tests nuevos, suite completa y paridad de manifest, con resultados reales.
- [x] T13 Reviewer: revision del diff; hallazgos.
- [x] T14 Cierre: fixes, `verification.md`, tildar Change 0 en `docs/roadmap/v0.8.md`,
  `estado: en_verificacion`.

## Dependencias

T1 -> T2 -> T3/T4 -> T5. T8 despues de T1-T2 (los archivos deben existir). T9 -> T10. T12 requiere
T1-T11; T13 requiere T12; T14 requiere T13. Requisito previo a T1: aprobacion humana de
`proposal.md`, `spec.md` y `design.md` registrada con `ds_guard approve` (por hash).

## Proximo paso exacto

Registrar la aprobacion por hash (`ds_guard approve` sobre `proposal.md`, `spec.md` y `design.md`)
y lanzar la invocacion 2 (implementacion).
