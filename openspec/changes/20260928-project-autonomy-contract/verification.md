# Verificación — 20260928-project-autonomy-contract

## Resultado por requisito (R1-R19)

Tabla requisito -> evidencia. Rutas relativas a la raíz del repo. Clases de test entre paréntesis.

| Req | Evidencia (tests / archivos) |
|-----|------------------------------|
| R1 Paquete y neutralidad | `tools/tests/test_v08_autonomy_neutrality.py` (`TestCoreAutonomySoloStdlib`, `TestPolicyAutonomySoloStdlibYCore`, `TestNingunPaqueteImportaAutonomy`, `TestSanityDeLosDetectores`); `tools/autonomy/tests/test_core.py::TestNeutralidadDeImports`; `test_policy.py::TestImportsYProsa` |
| R2 Vocabulario | `test_core.py::TestVocabularioYTabla::test_constantes`, `test_desconocidos_lanzan_autonomy_error` |
| R3 Tabla de política | `test_core.py::TestVocabularioYTabla` (`test_tabla_una_asercion_por_fila_y_modo`, `test_exhaustividad`, `test_stop_code_solo_en_filas_stop_human`, `test_stop_igual_en_ambos_modos`, `test_approve_proposal_human_en_ambos_modos`, `test_policy_decision_frozen`) |
| R4 Catálogos y registro único de códigos | `test_core.py::TestCatalogos` (`test_doce_stop`, `test_limit`, `test_all_codes`, `test_todo_codigo_usado_esta_registrado`, `test_stop_de_cada_fila_existe`) |
| R5 Sin prosa en el core | `test_core.py::test_constantes_str_sin_prosa`, `test_sin_constante_rol_modo_extra`; `test_policy.py::test_constantes_str_publicas_sin_espacios` |
| R6 Roles | `test_core.py::TestRoles` (`test_roles`, `test_invariantes`, `test_role_capabilities_devuelve_copia`, `test_rol_desconocido`) |
| R7 Aprobación por política | `test_core.py::TestPolicyApproval` (`test_valida_y_roundtrip`, `test_invalidas`, `test_faltantes`, `test_entrada_humana_no_valida_como_policy`, `test_is_policy_actor`) |
| R8 Policy humana, parseo fail-closed | `test_policy.py::TestParseValida`, `TestParseAusencia`, `TestParseDegradacion`, `TestFailClosedCorreccion2` |
| R9 Estrechamiento | `test_core.py::TestNarrowMode` (`test_cuatro_pares`, `test_nunca_amplia`, `test_desconocido_es_supervised`) |
| R10 Permisos de fuente y coherencia | `test_policy.py::TestAccesoFuentes`, `TestCoherencia`, `TestFailClosedCorreccion2` (ids no canónicos, `sealed_unknown`) |
| R11 Decisiones pre-aprobadas | `test_policy.py::TestResolucion`; `test_core.py::TestPreApprovedDecision` |
| R12 `pathguard.cargar_config` | `tools/tests/test_pathguard.py` (`test_policy_version_max_es_2`, `test_version_ausente_carga`, `test_versiones_soportadas_cargan`, `test_versiones_no_soportadas_levantan_error_config`, `test_hook_deniega_ante_version_no_soportada`, `test_hook_permite_lectura_con_version_2`, `test_doctor_reporta_error_ante_version_no_soportada`) |
| R13 El writer no ejecuta | `tools/tests/test_v08_writer_no_execution.py::TestWriterNoEjecuta` (`test_conjunto_exacto_de_tools`, `test_sin_herramientas_de_ejecucion_ni_delegacion`) |
| R14 Instalabilidad y archivos tocados | `tools/autonomy/tests/test_installability.py::TestInstalabilidadAutonomy`; `tools/tests/test_architecture_boundaries.py`; `python -m tools.ds_init.check_manifest_parity` |
| R15 Compatibilidad | Sin test dedicado con nombre propio (ver nota). Cubierto por: `test_pathguard.py::test_version_ausente_carga`, `test_policy.py::TestParseAusencia` (`test_sin_autonomy_supervised_sin_hallazgos`, `test_ausencia_no_bloquea_nada`), y la regresión completa (ningún test existente fue editado) |
| R16 `ApprovalRef` | `test_core.py::TestApprovalRef` (`test_valida`, `test_invalidas`, `test_incompleta_y_no_dict_no_lanzan`, `test_roundtrip_bytes`, `test_mismo_tipo_en_todos_lados`) |
| R17 Responsabilidades por rol y modo | `test_core.py::TestRoleResponsibilities` (`test_exhaustivo_rol_modo_clase`, `test_solo_lead_y_human_ejecutan_y_stops_solo_human`, `test_lee_las_dos_fuentes_en_cada_llamada`, `test_patch_dict_sobre_tabla`, `test_ejemplos_concretos`, `test_desconocidos`) |
| R18 Namespace reservado `policy:` | `test_core.py::TestNamespaceReservado` (`test_reservados`, `test_aceptados`, `test_caracteres_invisibles`, `test_identidad_no_imprimible`, `test_no_str_y_vacio`, `test_entrada_humana`, `test_policy_approval_con_usuario_es_hallazgo`) |
| R19 Invariantes de autoaprobación y límites | `test_core.py::TestPolicyApproval` (`test_clases_permitidas_calculadas_desde_tabla`, `test_approve_proposal_y_stop_invalidas`, `test_clases_permitidas_siguen_la_tabla`); `TestCatalogos` (`test_limit_disjunto_de_stop`, `test_ningun_approval_derivado_de_limit`) |

Nota R15: no hay un test cuyo propósito único sea "sin `autonomy` ni `version` 2 se comporta como v0.7";
la compatibilidad se sostiene por los tests de ausencia listados y por la regresión completa sin
edición de tests existentes. Se declara acá para que el Lead decida si lo considera suficiente.

## Ejecución real (corrida por el Lead, 2026-09-28)

- **Regresión completa final** (`.venv/Scripts/python -m pytest tools -q`): `2643 passed, 10 skipped,
  966 subtests passed in 1594.48s (0:26:34)`, exit code 0. Baseline previo al cambio: exit code 0
  (dos corridas; conteo no registrado).
- **Corrida dirigida final**: `293 passed, 2 skipped, 257 subtests passed` sobre `tools/autonomy`,
  `test_v08_autonomy_neutrality`, `test_v08_writer_no_execution`, `test_architecture_boundaries`,
  `test_pathguard`, `test_hook_rutas`, `test_manifest_dsguard_parity`,
  `tools/ds_init/tests/test_manifest.py`. Además una corrida de
  `tools/ds_init/tests/test_control_file.py` y `tools/harmessi/tests` (Doctor) junto a esas: exit
  code 0.
- **Paridad de manifest** (`python -m tools.ds_init.check_manifest_parity`): `[OK] Todas las rutas
  VERBATIM del manifiesto existen`, exit 0.
- **Guard** (`python tools/ds_guard.py validate --change-id 20260928-project-autonomy-contract`):
  "Sin hallazgos".

### Archivos

- Nuevos: `tools/autonomy/{__init__,core,policy}.py`,
  `tools/autonomy/tests/{__init__,test_core,test_policy,test_installability}.py`,
  `tools/tests/test_v08_autonomy_neutrality.py`, `tools/tests/test_v08_writer_no_execution.py`.
- Modificados: `tools/dsguard/pathguard.py` (`POLICY_VERSION_MAX = 2` y validación de `version`,
  ~12 líneas), `tools/tests/test_pathguard.py`, `tools/tests/test_architecture_boundaries.py`,
  `tools/ds_init/manifest.py` (3 entradas VERBATIM stage discovery), `ARCHITECTURE.md` (filas §2.1,
  regla 10, §6 "regla 11").
- No tocados: `doctor.py`, skills, plantillas, CLI e instalador. Ningún test existente fue editado.

## Revisión y disposición de hallazgos

Una revisión de `data-science-reviewer` sobre la implementación. Veredicto: REQUIERE CORRECCIONES;
0 BLOQUEANTES, 4 IMPORTANTES, ~10 MENORES. Se hizo 1 ciclo writer <-> reviewer. **No hubo segunda
revisión formal** de las correcciones (se declara explícitamente).

IMPORTANTES, todas corregidas:

1. `parse_autonomy_policy` con entrada no-dict y no-None ahora deja `sealed_unknown=True`.
2. `source_access` no-dict cierra toda fuente (`sealed_unknown=True`).
3. `source_id` canónico obligatorio (`SOURCE_ID_PATTERN = [a-z0-9][a-z0-9_-]{0,63}`,
   `is_valid_source_id`): sellos o claves de `source_access` no canónicos -> `sealed_unknown=True`;
   ids de consulta no canónicos se tratan como sellados.
4. Descripciones de `ARCHITECTURE.md` §2.1 y del manifest corregidas con los nombres reales.

MENORES de seguridad y calidad, corregidas: caracteres Cf/Cc invisibles en
`is_reserved_policy_namespace` y `validate_human_identity`; `scope` y `artefacto` con espacios
laterales, backslash o "." rechazados; tests débiles endurecidos (R17 sin constantes rol x modo
anidadas, LIMIT vs approval); pathguard: casos `None`/`-1`/`[]`/`"1"`, control positivo con version 2,
restauración de `sys.path`; test de la rama defensiva `except Exception`.

Preguntas del reviewer respondidas: ninguna vía por la que `parse_autonomy_policy` devuelva
`autonomous` indebidamente; `effective_source_access` nunca supera el máximo;
`resolve_methodological_decision` no continúa decisiones no listadas, con ref inválida ni de otro
artefacto; `PolicyApproval` no acepta `approve_proposal`, clases STOP ni `usuario`;
`role_responsibilities` recalcula desde las dos fuentes; `core.py` no importa `json`.

## Desvíos y aclaraciones fail-closed

`spec.md`, `design.md` y `proposal.md` quedan sin modificar por estar aprobados por hash; se registran
acá como enmiendas de implementación. Todas endurecen; ninguna relaja lo aprobado.

- (a) Un bloque `autonomy` no vacío exige `version` de nivel superior explícita int >= 2 (ausente
  equivale a 1, como en pathguard); si no, `supervised` + `AUTONOMY-POLICY-VERSION` con detail
  `missing_version`. R8 regla 3 lo cubría solo para versión presente.
- (b) Formato canónico de `source_id` (`SOURCE_ID_PATTERN`). El Change 1 (DataSourceRef) debe usar ids
  que lo cumplan o ampliar el patrón con revisión de `policy.py`.
- (c) `source_access` no-dict y entrada `guardrails` no-dict cierran toda fuente (`sealed_unknown`).
- (d) Decisiones pre-aprobadas duplicadas del mismo tipo con refs distintas -> STOP 2 (ambigüedad).
- (e) `role_responsibilities` devuelve `{"capabilities": {...}, "actions": {...}}` (forma concreta no
  fijada por R17); implicaciones `executes`/`approves`/`registers_policy`/`stops`.
- (f) `validate_human_identity` rechaza además identidades no imprimibles (Cf/Cc).

## Límites y pendientes

**Change 3**
- Verificar `human_approval_ref` y `approval_ref` contra `control.json` y que el hash siga
  coincidiendo.
- Interfaz de consulta de la policy para Lead/skills.
- Enforcement de `session_budget` / `aggregate_budget`.
- Apertura/cierre autónoma de sesiones.
- Integración de approvals por policy con el ledger.
- Conectar el namespace `policy:` con `--usuario`.
- Test de comparación tabla <-> prosa del skill.
- Formato de la sección de decisiones pre-aprobadas en `proposal.md`.

**Change 4**
- Check dedicado de Doctor para versión/incompatibilidad de policy.
- Upgrade de guard/pathguard antes de habilitar `autonomous`.
- Integración installer/managed files.
- Diagnóstico del modo efectivo.
- Exponer alias público del matcher de pathguard (`_matchea_patrones` es privado) para
  `sealed_coherence_findings`.
- Escalar `UNKNOWN-KEY` (`AUTONOMY-POLICY-UNKNOWN-KEY`) a WARN al menos.

**Limitaciones conocidas**
- Un guard anterior a este cambio ignora `autonomy`/`version` y no puede detectarse a sí mismo
  (cubierto por el requisito de upgrade previo, Change 4).
- No es sandbox.
- Identidad humano/policy sin autenticación (solo colisión estructural).
- Los STOP 3, 7, 9, 10, 11 y 12 no tienen clase de acción en la tabla: son criterios semánticos del
  Lead.

## Resultado final

**Change 0 cumple R1-R19 con las aclaraciones fail-closed listadas.**
