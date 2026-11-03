# Spec — 20260928-project-autonomy-contract

## Requisitos

- **R1 — Paquete y neutralidad**: existen `tools/autonomy/__init__.py` (vacio salvo docstring),
  `core.py` y `policy.py`. `core.py` importa solo stdlib (`dataclasses`, `typing`, `re`,
  `unicodedata`, `__future__`; `unicodedata` se agrega por R18); no importa ningun modulo `tools.*` ni hermano. `policy.py` importa stdlib y solo
  `from . import core as autonomy_core`; no hace I/O, no importa `pathlib`/`os`/`sys`/`json`.
  Ningun paquete de la familia independiente (`dsguard`, `ds_profile`, `dsimpact`, `reporting`,
  `providers`, `routing`, `fallback`, `harmessi_bench`, `datacontracts`, `modelquality`,
  `qualityevidence`) importa `tools.autonomy`. *Aceptacion*: `test_v08_autonomy_neutrality.py`
  (por `ast`, ambas direcciones); `MODULOS_CORE` de `test_architecture_boundaries.py` incluye
  `tools/autonomy/core.py` y `policy.py`.

- **R2 — Vocabulario**: en `core.py`, tuplas `MODES = ("autonomous", "supervised")`,
  `DEFAULT_MODE = "supervised"`, `EXECUTORS = ("lead", "human", "lead_or_human")`,
  `APPROVALS = ("none", "policy", "human", "human_conditional")`,
  `OUTCOMES = ("proceed", "stop_human")`. `PolicyDecision` es dataclass `frozen` con
  `action_class, mode, executor, approval, outcome, stop_code (str|None)`. `human_conditional`
  significa: requiere humano solo si aplica una condicion del flujo (transicion marcada, parametro
  de sesion faltante). *Aceptacion*: test de constantes y de `frozen`.

- **R3 — Tabla de politica**: `POLICY_TABLE` (dato) y `resolve_action(action_class, mode) ->
  PolicyDecision` (pura). Clase o modo desconocido -> `AutonomyError(ValueError)` con codigo
  estable, nunca `KeyError`. Contenido exacto `(executor, approval, outcome)` por
  `autonomous / supervised`:

  | Clase | autonomous | supervised |
  |---|---|---|
  | `diagnostic_read` | lead, none, proceed | lead, none, proceed |
  | `execute_project_code` | lead, none, proceed | lead_or_human, human, proceed |
  | `approve_run_manifest` | lead, policy, proceed | human, human, proceed |
  | `approve_proposal` | human, human, proceed | human, human, proceed |
  | `continue_preapproved_decision` | lead, policy, proceed | lead, human, proceed |
  | `decide_unlisted_methodological` | human, -, stop_human (STOP 2) | idem |
  | `sdd_transition_post_approval` | lead, none, proceed | lead, human_conditional, proceed |
  | `corrective_reinvocation_in_window` | lead, none, proceed | lead, none, proceed |
  | `remediation_extend` | human, -, stop_human (STOP 8) | idem |
  | `session_open_close` | lead, policy, proceed | lead, human_conditional, proceed |
  | `access_sealed` | human, stop_human (STOP 1) | idem |
  | `provide_secret` | human, stop_human (STOP 6) | idem |
  | `install_dependency` | human, stop_human (STOP 4) | idem |
  | `write_outside_scope_or_source_or_raw` | human, stop_human (STOP 5) | idem |
  | `commit_tag_publish` | human, human, proceed | human, human, proceed |

  En las filas STOP el campo `approval` es `human`. *Aceptacion*: test con una asercion por fila
  y por modo (15 clases x 2 modos = 30); test de exhaustividad (`ACTION_CLASSES` x `MODES` cubre
  la tabla sin huecos ni sobrantes); toda fila `stop_human` tiene `stop_code` y ninguna fila
  `proceed` lo tiene; los STOP lo son en ambos modos.

- **R4 — Catalogos y registro unico de codigos**: `STOP_CATALOG` con los 12 STOP del roadmap
  (numero 1-12, codigo `AUTONOMY-STOP-01`..`AUTONOMY-STOP-12`, clave estable en ingles, p. ej.
  `sealed_access`, `unlisted_methodological_decision`, `leakage_doubt`, `new_dependency`,
  `write_outside_scope`, `secret_required`, `data_loss_risk`, `remediation_exhausted`,
  `approach_refuted`, `requirement_contradiction`, `scope_expansion`, `bypass_needed`).
  `LIMIT_CATALOG` con `session_budget` y `aggregate_budget` (codigos `AUTONOMY-LIMIT-*`); un LIMIT
  NO es STOP: su resultado documentado es `checkpoint_resumable`, nunca pregunta al humano.
  `TECHNICAL_ERROR_CODE = "AUTONOMY-TECHNICAL-ERROR"` (constante documentada: no es STOP ni
  resultado de calidad). `ALL_CODES` es el registro unico (tupla de todos los `AUTONOMY-*`,
  incluidos los de policy y coherencia de R8/R10 y los de R16-R18: `AUTONOMY-APPROVAL-REF-INVALID`,
  `AUTONOMY-APPROVAL-INVALID`, `AUTONOMY-IDENTITY-INVALID`, `AUTONOMY-IDENTITY-RESERVED`).
  *Aceptacion*: sin duplicados; todo codigo
  cumple `^AUTONOMY-[A-Z0-9-]+$`; ningun LIMIT figura en `STOP_CATALOG`; el STOP de cada fila de R3
  existe en el catalogo.

- **R5 — Sin prosa en el core (deuda 8)**: las constantes publicas de `core.py` y `policy.py` son
  codigos/claves estables (`[a-z0-9_-]` o `AUTONOMY-*`), sin espacios ni frases. Los hallazgos
  llevan `code`, `path` (clave dentro de la policy) y `detail_key` estable; el texto para el usuario
  es responsabilidad del consumidor. *Aceptacion*: test recorre las constantes str publicas y exige
  `re.fullmatch(r"[A-Za-z0-9_.:-]+", valor)` (sin espacios).

- **R6 — Roles**: `ROLES = ("lead","writer","reviewer","metodologo","runner","human")` y
  `ROLE_CAPABILITIES` (dato): por rol, `write_files`, `execute`, `read_only` (bool). Invariantes:
  solo `writer` tiene `write_files=True`; `writer.execute is False`; `reviewer` y `metodologo`
  `read_only=True`; `lead.write_files is False`. La ejecucion del Lead es via runtime gobernado
  (Change 2); aqui solo se declara. `role_capabilities(rol)` pura; rol desconocido -> `AutonomyError`.
  *Aceptacion*: `test_core` con cada invariante. La vista derivada de responsabilidades por rol y
  modo es R17 (no hay segunda tabla rol x modo).

- **R7 — Aprobacion por politica**: `PolicyApproval` (frozen): `approved_by` (forma canonica
  estricta `policy:<slug>`, `^policy:[a-z0-9][a-z0-9_-]*$`, minusculas, sin espacios; p. ej.
  `policy:autonomous`), `action_class` (de `ACTION_CLASSES`, restringida por R19 i),
  `human_approval_ref: ApprovalRef` (el tipo unico de R16, no una estructura equivalente) y ningun
  campo `usuario`. `validate_policy_approval(dict)` devuelve lista de hallazgos (no lanza por datos
  raros); `to_dict`/`from_dict` deterministas (claves ordenadas, mismos bytes en round-trip).
  `is_policy_actor(approved_by)` distingue el prefijo. Una entrada humana (con `usuario`, sin
  `approved_by`) no valida como `PolicyApproval`; una con `approved_by` `policy:` y con `usuario`
  es invalida. El namespace `policy:` es reservado (R18). *Aceptacion*: tests valida / invalida
  (prefijo ausente, forma no canonica como `policy:` con mayusculas o espacios, hash mal formado,
  clase desconocida, `usuario` presente, ref incompleta) / round-trip identico en bytes.

- **R8 — Policy humana, parseo fail-closed** (`policy.py`):
  `parse_autonomy_policy(guardrails: dict, guard_policy_version_max: int|None) ->
  (AutonomyPolicy, list[PolicyFinding])`. `AutonomyPolicy` frozen: `mode`, `max_sessions`,
  `max_total_minutes`, `sealed_sources` (tupla), `source_access` (mapa inmutable
  source_id -> `(read, write)`), `declared_mode`, `sealed_unknown` (bool, default `False`). Esquema en `guardrails.json` (aditivo; `version`
  puede ser 2; con `version: 2` puede existir el objeto `autonomy`): `mode`
  (`autonomous|supervised`), `limits` {`max_sessions` int>0, `max_total_minutes` int>0; OBLIGATORIOS
  si `mode=autonomous`}, `sealed_sources` (lista de `source_id`), `source_access` (`source_id` ->
  {`read`: bool, `write`: bool}, es el MAXIMO). Reglas:
  1. sin `autonomy` (o dict vacio/`None`) -> `supervised`, sin hallazgos (= comportamiento v0.7);
  2. si pide `autonomous` o declara `sealed_sources` y `guard_policy_version_max` es `None` o
     menor que la version requerida (2) -> modo efectivo `supervised` + `AUTONOMY-POLICY-UNSUPPORTED`;
  3. `version` desconocida (no int, bool, <1, > version soportada por el propio core), `autonomy` con
     `version` < 2, tipos invalidos, limites faltantes/no positivos bajo `autonomous` ->
     `supervised` + hallazgo (`AUTONOMY-POLICY-INVALID`, `-VERSION`, `-LIMITS`); nunca `autonomous`
     ante duda;
  4. claves desconocidas dentro de `autonomy` se toleran y NO habilitan nada (hallazgo informativo
     opcional `AUTONOMY-POLICY-UNKNOWN-KEY`);
  5. nunca lanza por datos raros (entrada no-dict incluida);
  6. fail-closed de sellos: los `sealed_sources` validos se CONSERVAN en la `AutonomyPolicy`
     devuelta aunque el modo efectivo se degrade a `supervised` (guard sin capacidad, version
     desconocida, limites faltantes, etc.). Un sello nunca se descarta por degradacion;
  7. si la clave `autonomy` esta presente pero no es un objeto, o `sealed_sources` esta presente
     pero no es una lista de strings no vacios, `AutonomyPolicy` lleva `sealed_unknown=True` (campo
     nuevo, frozen, default `False`) + hallazgo `AUTONOMY-POLICY-INVALID`. Con `sealed_unknown=True`,
     `is_source_sealed` devuelve True para TODA fuente y `effective_source_access` devuelve
     `read=False, write=False` para toda fuente (fail-closed). La ausencia total de `autonomy` NO
     activa `sealed_unknown`.
  *Aceptacion*: tests para policy valida, faltan limites, version desconocida, `autonomy` con
  version 1, guard `None`, guard con version menor, tipos invalidos, claves desconocidas; `mode`
  efectivo nunca es `autonomous` en ninguno de los casos de degradacion; sello conservado bajo
  degradacion por guard `None`; `sealed_unknown` (autonomy no-objeto, `sealed_sources` mal formado)
  bloquea toda fuente; ausencia de `autonomy` no bloquea nada.

- **R9 — Estrechamiento**: `narrow_mode(current, requested) -> str`: devuelve `supervised` si
  cualquiera de los dos lo es; un modo desconocido se trata como `supervised`. *Aceptacion*: los 4
  pares validos (solo `autonomous, autonomous` da `autonomous`) y propiedad "nunca amplia":
  resultado no mas permisivo que `current` ni que `requested`.

- **R10 — Permisos de fuente y coherencia**: `is_source_sealed(policy, source_id)`;
  `effective_source_access(policy, source_id, registry_access|None) -> SourceAccess(read, write)`.
  Maximo = policy: fuente no listada en `source_access` -> `read=True, write=False`; fuente sellada
  -> `read=False, write=False` (aunque `source_access` diga otra cosa). Si `policy.sealed_unknown`
  (R8 regla 7): `is_source_sealed` es True para toda fuente y `effective_source_access` devuelve
  `read=False, write=False` para toda fuente, con cualquier `registry_access`. Efectivo = maximo AND
  registro (`registry_access=None` -> solo el maximo); el registro nunca amplia. Ademas
  `sealed_coherence_findings(sealed_source_ids, file_backed_sources: dict[str, str],
  holdout_patterns: list[str], matcher: Callable[[str, Sequence[str]], bool]) ->
  list[PolicyFinding]`: `AUTONOMY-SEALED-UNSEALED-HOLDOUT` si la ruta relativa POSIX de una fuente
  file-backed matchea un holdout y su `source_id` no esta sellado; `AUTONOMY-SEALED-PATH-MISMATCH`
  si un `source_id` sellado file-backed no matchea ningun holdout. Fuentes selladas no file-backed
  no generan hallazgo. *Aceptacion*: recorrido exhaustivo (policy x registro, sellada o no) con
  `efectivo <= maximo`; sellada no observable aunque el registro la permita; coherencia con
  `matcher` inyectado en ambas direcciones.

- **R11 — Decisiones pre-aprobadas**: `PreApprovedDecision` (frozen): `decision_type` (str no
  vacio), `summary` (str no vacio), `scope` (tupla de paths/patrones relativos POSIX dentro del
  Change: no absolutos, sin `..`, sin unidad de disco, no vacios) y `approval_ref: ApprovalRef`
  (obligatorio; el mismo tipo de R16; su `artefacto` debe ser exactamente `proposal.md`: la decision
  queda vinculada a la aprobacion humana y al hash de la propuesta que la habilita).
  `validate_pre_approved(item, known_types)` (`item` dict o instancia) -> hallazgos; rechaza
  referencia ausente, mal formada, hash invalido o `artefacto` distinto de `proposal.md`.
  `resolve_methodological_decision(mode, decision_type, pre_approved, known_types) ->
  MethodologicalResolution(decision (PolicyDecision), approval_ref: ApprovalRef | None)`:
  listada, valida y con tipo en `known_types` -> `continue_preapproved_decision` segun modo, con
  `approval_ref` = la ref de la decision listada; no listada o tipo desconocido ->
  `decide_unlisted_methodological` (STOP 2) en ambos modos, con `approval_ref=None`. `known_types`
  lo inyecta el llamador (core no duplica `dsguard.decision.TIPOS_DECISION`). El formato de la
  seccion en `proposal.md` es del Change 3. Este Change solo valida forma/tipos/hash y determinismo;
  NO consulta `control.json` (la verificacion contra `control.json` es del Change 3, R16).
  *Aceptacion*: listada / no listada / tipo desconocido / scope invalido, en ambos modos; ademas
  `PreApprovedDecision` sin ref (dict) -> hallazgo, con ref a otro artefacto -> hallazgo; listada
  devuelve la ref; no listada devuelve `None` + STOP 2; `approval_ref_required` no existe en ningun
  lado.

- **R12 — `pathguard.cargar_config` (aditivo, fail-closed)**: constante publica
  `POLICY_VERSION_MAX = 2` en `tools/dsguard/pathguard.py`. `cargar_config` rechaza con
  `ConfigGuardrailsError` un `version` presente que no sea `int` (`bool` excluido), sea < 1 o >
  `POLICY_VERSION_MAX`; el mensaje indica actualizar Harmessi. `version` ausente = 1. No se agregan
  campos a `ConfigGuardrails` ni cambia otra semantica; las claves desconocidas siguen ignoradas
  por `cargar_config` (la interpretacion es de `tools/autonomy`). `doctor.py` no se modifica: su
  `_check_guardrails_json` reutiliza `cargar_config` y reporta el rechazo. *Aceptacion* (en
  `test_pathguard.py`): ausente/1/2 cargan; 0, 3, `"2"`, `True`, `2.5` lanzan
  `ConfigGuardrailsError`; `POLICY_VERSION_MAX == 2`; el `.claude/guardrails.json` del repo carga; el
  hook deniega ante el rechazo (test existente de fail-closed extendido o nuevo caso); test que
  `_check_guardrails_json` reporta el error sin cambios en doctor.

- **R13 — El writer no ejecuta**: `test_v08_writer_no_execution.py` lee
  `agent_python_data_engineer.md.tmpl`, parsea la linea `tools:` del frontmatter y afirma que es
  exactamente el conjunto `{Read, Edit, Write, NotebookEdit, Grep, Glob}` y que no contiene `Bash`,
  `PowerShell` ni `Agent`. Coherencia con R6 (`writer.execute is False`).

- **R14 — Instalabilidad y archivos tocados**: `tools/ds_init/manifest.py` agrega entradas
  `VERBATIM` con `stage_minimo` discovery para `tools/autonomy/__init__.py`, `core.py`, `policy.py`
  (mismo patron que `tools/datacontracts`); `tools/autonomy/tests/test_installability.py` sigue el
  patron de `tools/datacontracts/tests/test_installability.py`; se mantienen verdes sin editarlos
  `tools/ds_init/tests/test_manifest.py`, `tools/tests/test_manifest_dsguard_parity.py`,
  `test_control_file.py` y `tools/harmessi/tests/test_doctor.py` (si hubiera que editar uno, se
  registra como hallazgo). Archivos que la implementacion toca: `tools/autonomy/{__init__,core,
  policy}.py`; `tools/autonomy/tests/{__init__,test_core,test_policy,test_installability}.py`;
  `tools/tests/test_v08_autonomy_neutrality.py`; `tools/tests/test_v08_writer_no_execution.py`;
  `tools/tests/test_architecture_boundaries.py`; `tools/ds_init/manifest.py`;
  `tools/dsguard/pathguard.py`; `tools/tests/test_pathguard.py`; `ARCHITECTURE.md` (filas de §2.1
  para `core.py`/`policy.py`; regla de dependencia 10 para la familia `tools/autonomy`; en §6 la
  mencion "regla 10" de la familia de fuentes pasa a "regla 11"); `docs/roadmap/v0.8.md` (tildar
  Change 0 solo al cerrar). Sin dependencias nuevas.

- **R15 — Compatibilidad**: sin `autonomy` ni `version` 2, el comportamiento es identico a v0.7
  (`supervised`). Ningun cambio a CLI, skills, plantillas ni `sdd.md`.

- **R16 — `ApprovalRef` (referencia de aprobacion unica, M3)**: en `core.py`, dataclass `frozen`
  `ApprovalRef` con `change_id` (mismo formato de id de change `YYYYMMDD-slug`), `artefacto` (str no
  vacio, nombre relativo: sin `/`, `\` ni `..`) y `hash` (sha256 hex, 64 caracteres minusculas,
  `^[0-9a-f]{64}$`). `validate_approval_ref(dict) -> list[PolicyFinding]` (codigo
  `AUTONOMY-APPROVAL-REF-INVALID`; no lanza por datos raros); `to_dict`/`from_dict` deterministas
  (claves ordenadas; `from_dict` sobre datos invalidos lanza `AutonomyError`). Es el UNICO tipo de
  referencia: lo usan `PolicyApproval.human_approval_ref` (R7) y `PreApprovedDecision.approval_ref`
  (R11) y `MethodologicalResolution.approval_ref`. Change 0 define y valida forma/tipos/hash y
  determinismo; NO consulta `control.json`. Verificar que la referencia exista en `control.json`,
  que el hash siga coincidiendo y registrar la aprobacion por policy en el ledger es del Change 3.
  *Aceptacion*: ref valida; invalidas (hash corto, hash con mayusculas, `artefacto` con `..`,
  `change_id` invalido); round-trip de bytes identicos (serializando `to_dict` en el test con
  `json.dumps(sort_keys=True)`; `core.py` no importa `json`); `PreApprovedDecision` sin ref ->
  hallazgo; con ref a otro artefacto -> hallazgo; `PolicyApproval.human_approval_ref` y
  `PreApprovedDecision.approval_ref` son el mismo tipo (`ApprovalRef`; test de anotaciones/instancias).

- **R17 — Responsabilidades por rol y modo (vista derivada)**: NO existe una segunda tabla
  persistida rol x modo. Fuente de verdad unica: `ROLE_CAPABILITIES` (que puede hacer
  tecnicamente cada rol) + `POLICY_TABLE` (quien ejecuta y que aprobacion exige segun modo).
  `role_responsibilities(role, mode)` es pura y DERIVADA; para `lead` y `human` devuelve, por
  `action_class`, un conjunto ordenado (tupla) de implicaciones (vacio = `none`) tomadas de
  `("executes", "approves", "registers_policy", "stops")`, con estas reglas mecanicas: executor
  `lead` -> lead `executes`; `human` -> human `executes`; `lead_or_human` -> ambos `executes`;
  approval `human` o `human_conditional` -> human `approves`; approval `policy` -> lead
  `registers_policy` (registra la aprobacion por policy); outcome `stop_human` -> human `stops`
  (decide). Para `writer`, `reviewer`, `metodologo` y `runner` devuelve solo las capacidades de
  `ROLE_CAPABILITIES`, sin implicacion por `action_class`. Rol o modo desconocido -> `AutonomyError`.
  La funcion lee las dos fuentes en cada llamada (sin cache ni copia). *Aceptacion*: test
  exhaustivo rol x modo x action_class: derivacion consistente con la tabla; nadie salvo
  `lead`/`human` aparece como ejecutor; el writer nunca ejecuta; las filas STOP solo las decide el
  `human` (`stops` solo en `human`); test que reemplaza (monkeypatch) una fila de `POLICY_TABLE` y
  una capacidad de `ROLE_CAPABILITIES` y comprueba que la vista cambia (se recalcula desde las dos
  fuentes); test que afirma que `core.py` no define ninguna constante publica con claves
  (rol, modo) distinta de esas dos fuentes.

- **R18 — Namespace reservado `policy:` (invariante puro)**: `policy:` es un namespace reservado
  para aprobaciones por policy; una identidad humana NO puede usarlo. En `core.py` (stdlib +
  `unicodedata`): `is_reserved_policy_namespace(value) -> bool` normaliza con
  `unicodedata.normalize("NFKC", v).strip().casefold()` y devuelve True si empieza por `policy:`
  (rechaza ` Policy:x`, `POLICY:x`, `policy：x` con dos puntos de ancho completo, `\tpolicy:x`; no-str
  -> False). `validate_human_identity(usuario) -> list[PolicyFinding]` rechaza vacio/no-str
  (`AUTONOMY-IDENTITY-INVALID`) y toda identidad en el namespace reservado
  (`AUTONOMY-IDENTITY-RESERVED`). `validate_human_approval_entry(dict) -> list[PolicyFinding]` exige
  `usuario` valido (no reservado) y ausencia de `approved_by`
  (`AUTONOMY-APPROVAL-INVALID`), de modo que una aprobacion humana no pueda pasar
  estructuralmente por policy. `PolicyApproval`: sin `usuario`, `approved_by` con la forma
  canonica de R7. Sin autenticacion real de identidad en v0.8: solo se evita la colision
  estructural y el spoofing trivial. Conectar esta validacion con `--usuario`, la CLI,
  `control.json` y el ledger es del Change 3. *Aceptacion*: rechazados `policy:autonomous`,
  ` Policy:x`, `POLICY:x`, `policy：x`, `\tpolicy:x`; aceptados `policyx`, `mypolicy:x`,
  `Federico`; entrada humana con `approved_by` -> hallazgo; policy approval con `usuario` ->
  hallazgo.

- **R19 — Invariantes adicionales de autoaprobacion y limites**: (i) ningun Change puede
  autoaprobar su propia propuesta: `approve_proposal` es executor `human` y approval `human` en
  ambos modos (R3), y `PolicyApproval.action_class` solo puede ser una clase cuya fila tenga
  `approval == "policy"` en algun modo (derivado de `POLICY_TABLE`, hoy `approve_run_manifest`,
  `continue_preapproved_decision`, `session_open_close`); una `PolicyApproval` para
  `approve_proposal` o para cualquier clase STOP es invalida. (ii) `session_budget` y
  `aggregate_budget` son LIMIT, no approval gate: ninguna fila de `POLICY_TABLE` tiene un approval
  derivado de un LIMIT y `LIMIT_CATALOG ∩ STOP_CATALOG = ∅` (por codigo y por clave). (iii)
  `supervised` por defecto, sin policy equivale a v0.7, el writer no ejecuta y el Lead no escribe:
  ya cubiertos por R2, R6, R8 (regla 1), R13 y R15; no se duplican. (iv) `autonomous` no implica
  sandbox (design, riesgo 2). *Aceptacion*: tests de (i) y (ii) sobre `POLICY_TABLE`, `STOP_CATALOG` y
  `LIMIT_CATALOG`; el conjunto permitido de (i) se calcula desde la tabla, no esta listado a mano.

## Criterios de aceptacion globales

Los tests nuevos pasan; `.venv/Scripts/python -m pytest tools -q` verde; `python -m
tools.ds_init.check_manifest_parity` sin diferencias; el diff no toca archivos fuera de R14.
