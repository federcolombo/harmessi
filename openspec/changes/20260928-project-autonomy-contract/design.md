# Diseno — 20260928-project-autonomy-contract

## Decisiones de diseno

**D1 — Paquete `tools/autonomy/` independiente.** `core.py` solo-stdlib, sin imports de hermanos;
`policy.py` importa solo `from . import core as autonomy_core` (mismo estilo relativo que
`datacontracts/validation.py:74`; sin `sys.path.insert` porque no hay paquetes externos, evitando la
deuda 5 de `ARCHITECTURE.md` §4.1). Puro sobre dicts ya cargados: sin I/O ni `Path`. La familia
existente no lo importa (test `ast` bidireccional, patron de `test_v07_core_neutrality`). Registro
unico de codigos `AUTONOMY-*` en `core.py` (deuda 6); sin prosa (deuda 8).

**D2/D3 — Vocabulario y tabla como dato.** `POLICY_TABLE` es un dict `(clase, modo) ->
PolicyDecision`; `resolve_action` solo consulta la tabla (sin `if mode == ...` fuera de ella:
riesgo "supervised como segunda arquitectura" del roadmap). Una fila = una aserccion de test; la
exhaustividad se verifica contra `ACTION_CLASSES x MODES`. `human_conditional` codifica "requiere
humano solo si aplica una condicion del flujo"; evaluar la condicion es del Change 3.

**D4 — Roles como datos.** Capacidades booleanas por rol; invariantes por test. Refleja la
decision 1 del roadmap (writer sin ejecucion) y que el Lead no edita archivos; su ejecucion sera via
runtime gobernado (Change 2), aqui solo se declara.
Congelado (A2): capacidades (`ROLE_CAPABILITIES`) = que puede hacer tecnicamente un rol; tabla
(`POLICY_TABLE`) = quien ejecuta/aprueba segun modo; responsabilidad efectiva = derivacion de ambas.
No se persiste una segunda tabla rol x modo: `role_responsibilities(role, mode)` es una funcion pura
que recalcula la vista en cada llamada (executor `lead`->lead ejecuta; `human`->human;
`lead_or_human`->ambos; approval `human`/`human_conditional`->human aprueba; `policy`->lead registra
la aprobacion por policy; `stop_human`->human decide). Para writer/reviewer/metodologo/runner solo
expone capacidades, sin implicacion por `action_class`. Riesgo evitado: dos fuentes de verdad que
divergen (mismo criterio que D2/D3).

**D5 — Policy humana.** Extension aditiva de `guardrails.json` con `version: 2` y objeto `autonomy`
(claves en R8). El parser recibe `guard_policy_version_max` del llamador (`None` = guard que no
publica la capacidad): asi `policy.py` no importa `pathguard` y el llamador (Change 3/4) pasa
`pathguard.POLICY_VERSION_MAX` o `None`. Todo lo dudoso degrada a `supervised` con hallazgo; nunca
lanza. `effective_source_access` es `min` sobre booleanos (AND): la policy fija el maximo, el
registro solo resta.
Enmienda fail-closed de sellos (M2 del roadmap): un sello nunca se pierde en silencio. Los
`sealed_sources` validos se conservan aunque el modo se degrade a `supervised`, y un `autonomy` o
`sealed_sources` mal formado activa `sealed_unknown=True` (toda fuente sellada, sin acceso) en vez de
convertirse en "sin sellos". Solo la ausencia total de `autonomy` equivale a "sin sellos".

**Matcher inyectado (coherencia file-backed).** `sealed_coherence_findings` recibe
`matcher: Callable[[str, Sequence[str]], bool]`. Alternativas: (a) importar `pathguard` -> viola la
independencia de familia y crea acoplamiento de core a guard; (b) copiar el criterio casefold +
`path_matches_any` (`pathguard.py:194-201`) -> duplica logica de seguridad y puede divergir; (c)
inyectar. Elegida (c): el llamador (Change 4, doctor) pasa el matcher de pathguard, de modo que el
criterio es unico. Riesgo: hoy es `_matchea_patrones` (privado); Change 4 debera exponer un alias
publico o aceptar el acople; los tests de este Change usan un matcher de prueba simple.

**D6 — `pathguard` minimo.** Solo `POLICY_VERSION_MAX = 2` y validacion de `version` en
`cargar_config`; sin campos nuevos en `ConfigGuardrails` (`pathguard.py:96-102`). Un guard viejo (sin
este cambio) ignora `autonomy` y `version` (`pathguard.py:135-147`): eso se cubre por dos capas: (1)
guard nuevo rechaza versiones > 2 y el hook deniega; (2) `parse_autonomy_policy` degrada a
`supervised` con `AUTONOMY-POLICY-UNSUPPORTED` si el guard no publica la capacidad (`None`) o es
menor. Limite honesto: un guard anterior a este cambio no puede detectarse a si mismo; por eso el
upgrade del guard es previo a permitir `autonomous` (Change 4) y ningun componente habilita
`autonomous` sin `guard_policy_version_max` explicito.

**D7 — `PolicyApproval`, `ApprovalRef` y namespace `policy:`.** `PolicyApproval` queda separada por
estructura de la entrada humana (`approved_by` vs `usuario`) y por namespace. `approved_by` tiene
forma canonica estricta `policy:<slug>` (`^policy:[a-z0-9][a-z0-9_-]*$`). Serializacion en tests con
`json.dumps(sort_keys=True, separators, ensure_ascii=False)` y LF sobre `to_dict` (el core no importa
`json`). Se prueba a nivel de core.
- *Referencia unica (A1)*: `ApprovalRef(change_id, artefacto, hash)` frozen, con `to_dict`/`from_dict`
  deterministas, es el unico tipo de referencia a una aprobacion humana: lo usan
  `PolicyApproval.human_approval_ref`, `PreApprovedDecision.approval_ref` (con `artefacto ==
  "proposal.md"`: la decision queda vinculada a la aprobacion humana y al hash de la propuesta que la
  habilita) y `MethodologicalResolution.approval_ref: ApprovalRef | None` (reemplaza a
  `approval_ref_required`; `None` en STOP). Change 0 solo define y valida forma/tipos/hash y
  determinismo; NO consulta `control.json`. Change 3 verifica que la referencia exista en
  `control.json`, que el hash siga coincidiendo y registra la aprobacion por policy en el ledger.
- *Namespace reservado (A3)*: `policy:` esta reservado a aprobaciones por policy.
  `is_reserved_policy_namespace` normaliza con NFKC + strip + casefold (agrega `unicodedata` al
  conjunto stdlib del core), `validate_human_identity` y `validate_human_approval_entry` impiden que
  una identidad humana use el namespace o que una entrada humana lleve `approved_by`. Es un
  invariante puro: sin autenticacion real de identidad en v0.8 (solo evita colision estructural y
  spoofing trivial). Change 3 lo conecta con `--usuario`, la CLI, `control.json` y el ledger
  (reemplaza el hallazgo abierto anterior sobre `validar_usuario_sin_email`).
- *Anti-autoaprobacion (A5)*: `approve_proposal` es human/human en ambos modos y
  `PolicyApproval.action_class` solo admite clases con `approval == "policy"` en algun modo
  (derivado de `POLICY_TABLE`, no listado a mano): ningun Change puede autoaprobar su propuesta.
  `session_budget`/`aggregate_budget` son LIMIT, no approval gate; `LIMIT_CATALOG ∩ STOP_CATALOG = ∅`.

**D8 — Pre-aprobadas.** Solo tipo y validacion pura; `known_types` inyectado para no duplicar
`dsguard.decision.TIPOS_DECISION` (`decision.py:33`). Cada decision lleva su `approval_ref`
(`ApprovalRef` a `proposal.md`).

**Diferimientos confirmados.** Change 3: verificar `human_approval_ref` y la ref de
`PreApprovedDecision` contra `control.json` (y que el hash siga coincidiendo); interfaz de consulta de
la policy para Lead/skills; enforcement de `session_budget` y `aggregate_budget`;
apertura/cierre/reanudacion autonoma de sesiones dentro de esos limites; integracion de approvals por
policy con el ledger; conectar A3 con `--usuario`. Change 4: check dedicado de Doctor para
version/incompatibilidad de la policy; upgrade de guard/pathguard antes de habilitar `autonomous`;
integracion installer/managed files; diagnostico explicito del modo efectivo. Permanece en Change 0:
el fail-closed basico de `pathguard.cargar_config` (R12). Sin cambios: R3, STOP 01-12, LIMIT.

**D9 — Limites de alcance.** Sin CLI, skills ni instalador; solo entradas de MANIFEST.

## Alternativas descartadas

- Artefacto "carta de autonomia" multi-Change: el audit muestra que propuesta + control.json +
  ledger alcanzan (proposal.md).
- Guardar el modo en `control.json` o en un archivo nuevo: el agente puede editarlos; la policy
  humana debe vivir en `guardrails.json`, protegido por el hook.
- Tabla como `if/elif` en el runtime: duplica prosa y datos; se prefiere dato unico.
- Que `parse_autonomy_policy` importe `pathguard`: acopla familias.
- Hacer que `cargar_config` interprete `autonomy`: mezcla responsabilidades del guard de rutas con
  politica de autonomia y agranda una superficie de seguridad critica.

## Riesgos

1. **Guard viejo ignora claves nuevas**: ver D6; mitigacion en dos capas y requisito de upgrade previo.
2. **No es sandbox**: la policy y el guard median lo que pasa por Harmessi; un script del proyecto
   puede abrir una fuente por su cuenta. `sealed_sources` por `source_id` solo gobierna el
   acceso mediado. Se documenta, no se oculta (roadmap "Limites honestos").
3. **Divergencia tabla en core vs prosa del skill (Change 3)**: el skill debe consultar la tabla,
   no copiarla; mitigacion: la tabla es el contrato, Change 3 agrega un test que compare las
   filas citadas en el skill con `POLICY_TABLE`. Aqui queda como pendiente declarado.
4. **Identidad humana/politica no autenticada**: `--usuario` es texto declarado; el namespace
   reservado `policy:` (R18) evita la colision estructural y el spoofing trivial, y el registro da
   trazabilidad; no hay autenticacion. Conectar la validacion con `--usuario` es del Change 3.
5. **Cambio en `pathguard` (verbatim-managed, seguridad critica)**: un `version` erroneo en un
   `guardrails.json` existente bloquearia al hook (fail-closed). El del repo actual es `1` y carga;
   test explicito. Doctor lo reporta como error sin cambios.
7. **Sello mal formado**: un `sealed_sources` o `autonomy` invalido no debe leerse como "sin
   sellos"; mitigacion: `sealed_unknown` fail-closed y conservacion de sellos bajo degradacion (R8
   reglas 6-7, R10).
6. **Manifest**: agregar entradas puede afectar tests de paridad; se leen antes y se mantienen verdes.

## Verificacion

Sin ejecucion por parte del writer: el Lead corre los tests nuevos, la suite completa y la paridad
de manifest (ver `tasks.md`, invocacion 3).
