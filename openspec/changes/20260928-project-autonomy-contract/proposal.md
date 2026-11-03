# Propuesta — 20260928-project-autonomy-contract

## Problema

El harness instalado en un proyecto modela `agente escribe -> humano ejecuta -> humano devuelve
el output -> Lead continua` (roadmap `docs/roadmap/v0.8.md`, "Limitacion 1"). No existe hoy un
contrato de datos que diga, para cada accion del Lead, quien la ejecuta, que aprobacion requiere y
cuando debe detenerse. La semantica esta repartida en prosa de plantillas administradas; un
proyecto que quiere operar de forma autonoma tiene que editarlas a mano (drift). Ademas la policy
humana (`.claude/guardrails.json`) no tiene forma de expresar modo, limites agregados ni fuentes
selladas por `source_id`, y el guard instalado no valida la version de esa policy.

## Objetivo

Definir, como codigo puro y verificable (sin ejecutar nada nuevo), el **contrato de autonomia**
de v0.8 (Change 0 del roadmap):

1. vocabulario de modos, ejecutores, aprobaciones y resultados, y la tabla clase de accion x modo
   resuelta por una funcion pura;
2. catalogos STOP 1-12 y LIMIT con codigos estables (`AUTONOMY-*`, registro unico);
3. roles con capacidades como dato, con invariantes testeables (el writer no ejecuta);
4. policy humana (M2): extension aditiva de `guardrails.json`, parseo fail-closed, estrechamiento
   de modo y permisos de fuente `policy inter registro`;
5. aprobaciones por politica distinguibles de las humanas (M3, decision 11 del roadmap), con un
   unico tipo de referencia `ApprovalRef` (`change_id`, `artefacto`, `hash`) y un namespace
   `policy:` reservado que ninguna identidad humana puede usar;
6. tipo y validacion pura de decisiones metodologicas pre-aprobadas (M3), vinculadas por
   `ApprovalRef` al hash de `proposal.md`;
7. responsabilidades por rol y modo como vista derivada pura (`role_responsibilities`) de
   `ROLE_CAPABILITIES` + `POLICY_TABLE`, sin segunda tabla rol x modo;
8. un cambio minimo, aditivo y fail-closed en `pathguard.cargar_config` para que un guard que no
   entiende la version de la policy deniegue en vez de ignorarla.

## Evidencia (audit obligatorio del roadmap; verificada leyendo el codigo)

**"El usuario ejecuta" en plantillas administradas** (`tools/ds_init/profiles/python_jupyter_data/templates/`):

- `sdd.md.tmpl:72` — "El usuario ejecuta y trae el output al chat (el estado permanece en
  `en_verificacion`)".
- `sdd.md.tmpl:106` — paso 9: "El usuario ejecuta y trae el output. El estado permanece en
  `en_verificacion`".
- `sdd.md.tmpl:126` — fila `en_verificacion`: "Esperando que el usuario ejecute y traiga el output".
- `sdd.md.tmpl:129` — fila `pausada_bloqueada`: incluye "ejecucion que ningun agente puede correr".
- `SKILL_lead_data_scientist.md.tmpl:46` — el writer "No ejecuta codigo ni notebooks en esta
  version" (correcto; se mantiene).
- `SKILL_lead_data_scientist.md.tmpl:152-154` — causa de pausa: "hace falta ejecutar algo que ningun
  agente puede correr en esta version".
- `SKILL_lead_data_scientist.md.tmpl:202` — seccion "Restriccion de esta version".
- `agent_python_data_engineer.md.tmpl:4` — frontmatter `tools: Read, Edit, Write, NotebookEdit,
  Grep, Glob` (sin Bash); `:34` lo repite en prosa. **Se mantiene** (decision 1 del roadmap).

Su reescritura es del Change 3; este Change solo fija el contrato que esas plantillas consultaran.

**Unidad de aprobacion (M3).** `ds_guard.py:309-347` (`cmd_approve`): cada entrada de
`control["aprobaciones"]` guarda `artefacto`, `algoritmo` (`sha256/lf/v1`), `hash`, `registrado_utc`,
`usuario`, `fecha_declarada`, `alcance_aprobado` y `cita`. El hash del `proposal.md` cubre cualquier
seccion estructurada que se agregue a ese archivo. El decision ledger ya tiene
`TIPOS_DECISION` (`tools/dsguard/decision.py:33`). **Conclusion del audit: propuesta aprobada +
`control.json` + ledger ALCANZAN como unidad de aprobacion; no se justifica un artefacto "carta"
nuevo.** Limitacion declarada: `cmd_approve` imprime (`ds_guard.py:347`) "el hash acredita
identidad de contenido, no aprobacion humana"; `--usuario` es texto declarado. La distincion
humano/politica se sostiene por el namespace reservado `policy:` (`approved_by` de forma canonica
estricta; ninguna identidad humana puede usarlo, incluso con variantes de mayusculas, espacios o
caracteres de ancho completo) y por el registro, no por autenticacion.

**Comportamiento de `pathguard` (M2).** `tools/dsguard/pathguard.py:111-152` (`cargar_config`) lee
solo cinco claves conocidas con `datos.get(...)` (`holdouts`, `data_raw`, `secretos_extra`,
`excepciones`, `write_scopes`; lineas 135-147), ignora en silencio cualquier otra clave y **no lee ni
valida `version`**. Un guard viejo con una policy `autonomy`/`sealed_sources` la ignoraria sin aviso:
hoy el requisito fail-closed de M2 no esta cubierto por el codigo. `ConfigGuardrails`
(lineas 96-102) no tiene campo de version. El doctor (`tools/harmessi/doctor.py:712-730`,
`_check_guardrails_json`) ya reutiliza `cargar_config`, por lo que detecta cualquier rechazo nuevo
sin cambios. El criterio de matching de patrones esta en `pathguard._matchea_patrones` (194-201,
casefold + `repo.path_matches_any`).

**Estilo de imports.** `tools/datacontracts/core.py:40-46` importa solo stdlib; los hermanos usan
`from . import core as datacontracts_core` (`validation.py:74`, `evolution.py:54`) y solo insertan
`sys.path` para paquetes externos. `tools/autonomy` sigue el mismo patron relativo, sin `sys.path`
(no necesita paquetes externos).

## Supuestos descartados

- "Hace falta una carta de autonomia multi-Change": descartado por el audit (arriba).
- "`pathguard` ya es fail-closed ante policies nuevas": falso (ignora claves y `version`).
- "El registro puede ampliar permisos de fuente": descartado por M2 (solo restringe).
- "La autenticacion distingue humano de politica": falso; se sostiene por namespace reservado y
  registro (limite declarado; no es sandbox ni autenticacion).
- "Una segunda tabla persistida rol x modo": descartada; la responsabilidad efectiva se deriva de
  `ROLE_CAPABILITIES` + `POLICY_TABLE`.

## Alcance

Paquete nuevo `tools/autonomy/` (`core.py` solo-stdlib; `policy.py` puro sobre dicts), sus tests, dos
tests de repo (`test_v08_autonomy_neutrality.py`, `test_v08_writer_no_execution.py`), entradas de
MANIFEST, un cambio aditivo en `tools/dsguard/pathguard.py` (`POLICY_VERSION_MAX = 2` y validacion
de `version`), y documentacion en `ARCHITECTURE.md`. Archivos exactos en `spec.md` (R14).

## Fuera de alcance

CLI (`ds_guard autonomy ...`), cambios a skills/plantillas/`sdd.md` (Change 3), formato de la seccion
de decisiones pre-aprobadas dentro de `proposal.md` (Change 3), runtime de ejecucion (Change 2),
fuentes/adapters (Change 1), instalador y check de doctor de coherencia (Change 4; `doctor.py` no se
toca), dependencias nuevas, ejecucion de cualquier codigo del proyecto.

Diferimientos confirmados por el autor:

- **Change 3**: verificar `human_approval_ref` (y la ref de `PreApprovedDecision`) contra
  `control.json` y que el hash siga coincidiendo (Change 0 solo valida forma/tipos/hash y
  determinismo y NO consulta `control.json`); interfaz de consulta de la policy para Lead/skills;
  enforcement de `session_budget` y `aggregate_budget`; apertura/cierre/reanudacion autonoma de
  sesiones dentro de esos limites; integracion de las aprobaciones por policy con el ledger
  (incluido su registro); conectar la validacion del namespace `policy:` con `--usuario`, la CLI,
  `control.json` y el ledger.
- **Change 4**: check dedicado de Doctor para version/incompatibilidad de la policy; upgrade de
  guard/pathguard antes de habilitar `autonomous`; integracion installer/managed files; diagnostico
  explicito del modo efectivo.
- **Permanece en Change 0**: el fail-closed basico de `pathguard.cargar_config` (R12).
- **Sin cambios**: R3 (tabla), STOP 01-12 (R4), LIMIT, y la estructura de aprobaciones humanas/policy
  salvo lo definido en R16 y R18.

## Aprobacion

Aprobacion humana explicita del autor, registrada el 2026-09-28 mediante `ds_guard approve` por hash
(la entrada vive en `control.json` -> `aprobaciones`), con esta cita literal: «Apruebo
conceptualmente proposal.md, spec.md y design.md del Change 0 con las siguientes tres decisiones
obligatorias … registrá ESTA respuesta como mi aprobación humana explícita de proposal.md, spec.md
y design.md». Decisiones incorporadas: A1 (`ApprovalRef` y vinculo al hash de la propuesta), A2
(`role_responsibilities` derivada) y A3 (namespace `policy:` reservado), mas los diferimientos
arriba listados. Las decisiones M1-M6 del roadmap ya estan confirmadas por el autor.
