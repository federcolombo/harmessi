# Propuesta — 20260930-autonomous-sdd-and-remediation

## Problema

Change 0 (`20260928-project-autonomy-contract`) construyó el mecanismo de política de autonomía
(`tools/autonomy/core.py`: `POLICY_TABLE`, catálogo STOP/LIMIT, `PreApprovedDecision`,
`PolicyApproval`, `ApprovalRef`) y Change 2 (`20260929-lead-execution-runtime`) construyó el runtime
que lo hace cumplir en ejecución (`tools/leadrun/`). Pero **nada de eso está todavía conectado al
ciclo SDD real que sigue el Lead** — confirmado por lectura directa, no de memoria:

- `.claude/skills/lead-data-scientist/sdd.md:72,106` sigue diciendo literalmente "El usuario ejecuta
  y trae el output al chat" como el mecanismo de `en_verificacion`;
- `.claude/skills/lead-data-scientist/SKILL.md:154` sigue condicionando una pausa a "hace falta
  ejecutar algo que ningún agente puede correr en esta versión" — el propio Change 2 ya lo resolvió
  técnicamente, pero el skill no lo sabe;
- `tools/dsguard/sdd.py` (`transition`, `session_start`, `session_note`) no importa `tools.autonomy`
  en absoluto — la tabla de política existe pero ningún consumidor real la consulta;
- `tools/autonomy/core.py` ya anticipa varias piezas que hoy están sin usar: la fila
  `continue_preapproved_decision` de `POLICY_TABLE` (política en `autonomous`, humano en
  `supervised`), el tipo `PreApprovedDecision` completo (con `scope`, `summary`, `approval_ref`) y el
  código `AUTONOMY-LIMIT-AGGREGATE-BUDGET` del `LIMIT_CATALOG` — reservado pero sin ningún productor;
- `session_start` (`tools/dsguard/sdd.py:642-686`) ya acepta presupuesto configurable **por sesión**
  (`minutos`, `max_tareas`, `max_roles`, `max_reintentos`, `max_rondas_revision`,
  `max_continuaciones_por_subagente`), pero no existe ningún concepto de presupuesto **agregado**
  entre sesiones de un mismo Change — abrir una sesión nueva no hereda ni respeta lo ya consumido;
  cada entrada de sesión ya reserva un campo `subagentes: {}` (`sdd.py:678`) pero nunca se puebla ni
  se usa.

Además, feedback de reutilización real en un proyecto externo pidió explícitamente: máxima autonomía
técnica con intervención humana solo en decisiones de negocio, soporte para proyectos sin modelado
predictivo, fuentes externas de solo lectura, customización por proyecto/máquina sin editar managed
files, y budgets configurables — con backward compatibility total. La enmienda del roadmap
(`docs/roadmap/v0.8.md`, commit `80c2a93`, decisiones M7-M10) ya resolvió esto a nivel de roadmap;
este Change implementa la parte que le corresponde a Change 3: M7 (`approval_mode`, checkpoints de
negocio, budgets configurables).

## Objetivo

Conectar el mecanismo de autonomía de Change 0 al ciclo SDD real (skill/plantillas administradas),
de forma que el Lead deje de pedirle al humano "ejecutar y traer el output"; agregar
`approval_mode: per_change` (default, backward-compatible) / `checkpoints` (opt-in, M7) sin crear una
segunda arquitectura de approvals; hacer configurables los budgets ya existentes (con los valores
actuales como default) y agregar el concepto de presupuesto **agregado** entre sesiones que hoy no
existe.

## Evidencia

- `.claude/skills/lead-data-scientist/sdd.md:72,106` — "El usuario ejecuta y trae el output al chat".
- `.claude/skills/lead-data-scientist/SKILL.md:154` — pausa por "ejecutar algo que ningún agente
  puede correr en esta versión".
- `tools/autonomy/core.py:190-218` — fila `continue_preapproved_decision` de `POLICY_TABLE`, ya
  resuelta pero sin consumidor.
- `tools/autonomy/core.py:101-108` — `LIMIT_CATALOG` con `CODE_LIMIT_AGGREGATE_BUDGET`
  (`AUTONOMY-LIMIT-AGGREGATE-BUDGET`), código reservado sin ningún productor real hoy.
- `tools/autonomy/core.py:615-641` — `PreApprovedDecision` (`decision_type`, `summary`, `scope`,
  `approval_ref`) ya validado y serializable; ninguna implementación real lo usa todavía fuera de sus
  propios tests.
- `tools/dsguard/sdd.py:642-686` — `session_start` con presupuesto por sesión ya configurable
  (parámetros con nombre), sin ningún agregado entre sesiones; `activa["subagentes"] = {}` reservado
  y sin poblar.
- `tools/dsguard/sdd.py:459-554` — `remediation_note` con `max_intentos_default: int = 2` ya
  parametrizable por el llamador, hoy hardcodeado en el CLI en vez de leído de policy.
- `docs/roadmap/v0.8.md` (commit `80c2a93`, sección "M7 — Modo de aprobación de autonomía") —
  decisión material ya congelada que este Change implementa.

## Supuestos descartados

- Que hacía falta un nuevo tipo de dato para "business checkpoint": `PreApprovedDecision` ya cubre
  exactamente esa forma (decisión declarada, alcance, referencia a la aprobación humana por hash);
  se reutiliza con un `decision_type` nuevo, no se crea un tipo paralelo.
- Que el presupuesto agregado necesita un contador nuevo persistido: alcanza con una vista derivada
  sobre `control["sesiones"]` ya existente (mismo patrón que `session_status` deriva
  `minutos_transcurridos`), evitando la "segunda tabla de constantes/contadores" que
  `docs/roadmap/v0.8.md` prohíbe explícitamente.

## Hipótesis (condicional — solo cambios metodológicos)

N/A — Change de infraestructura/gobernanza, no metodológico.

## Alcance

- `approval_mode` declarado por Change (`control.json`, nuevo campo, default ausente =
  `per_change`), inmutable tras `aprobada_implementacion` (cambiarlo a mitad de Change es expansión
  de scope, STOP 11);
- checkpoints de negocio = `PreApprovedDecision` con `decision_type="business_checkpoint"`,
  declarados en `proposal.md` (nueva sección `## Checkpoints de negocio`, condicional a
  `approval_mode: checkpoints`) y persistidos en `control.json` al aprobar la propuesta;
- mecanismo de continuación automática entre checkpoints, vía la fila `continue_preapproved_decision`
  de `POLICY_TABLE` ya existente (sin tocar `tools/autonomy/core.py`, Change 0 ya está cerrado);
- budgets configurables vía `.claude/guardrails.json` (`autonomy.budgets`, extensión aditiva de la
  policy de Change 0), con los valores hoy hardcodeados en `session_start`/`remediation_note` como
  default — sin declarar la clave, comportamiento idéntico al actual;
- presupuesto **agregado** (tiempo total, máximo de sesiones) como vista derivada sobre
  `control["sesiones"]`, sin contador paralelo; agotarlo produce un checkpoint resumible
  (`AUTONOMY-LIMIT-AGGREGATE-BUDGET`), nunca aprobación automática ni STOP salvo condición STOP real;
- `max_concurrent_subagents`: best-effort, autorreportado por el Lead (extensión de `session note`),
  no un lock técnico — límite honesto, documentado como tal;
- reescritura de `.claude/skills/lead-data-scientist/sdd.md.tmpl` y las referencias de `SKILL.md.tmpl`
  citadas arriba, para consultar la política en vez de asumir "el usuario ejecuta";
- `remediation extend` sigue siendo siempre humano (ninguna fila de `POLICY_TABLE` lo cambia, Change 0
  ya lo fijó así — `remediation_extend` → `stop_human`/`remediation_exhausted` en ambos modos).

## Fuera de alcance

- Reabrir Change 0, 1 o 2 (`tools/autonomy/core.py`, `tools/autonomy/policy.py`,
  `tools/datasources/*`, `tools/leadrun/*` no se tocan salvo que un hallazgo real lo exija, y en ese
  caso es STOP, no una decisión silenciosa);
- project capabilities (M8), fuentes externas file-backed (M9), layering de configuración (M10) —
  Change 4;
- entrenamiento automático de modelos, selección automática de features/modelos, decidir por el
  humano en un STOP, commits/tags automáticos, políticas nuevas de calidad (ya excluido por el
  roadmap para Change 3);
- un lock de concurrencia real de subagentes (no existe primitiva técnica para eso en el harness
  actual; se documenta como límite honesto, no se inventa un mecanismo que no se puede garantizar);
- cambiar el vocabulario de `ESTADOS_VALIDOS`/`TRANSICIONES_VALIDAS` de `tools/dsguard/sdd.py`
  (aditivo únicamente, decisión 13 del roadmap: vocabulario y schemas de SDD/control son solo
  aditivos).

## Holdout policy (condicional)

N/A — este Change no toca datos ni fuentes.

## Impacto en production-readiness (opcional)

N/A.

## Criterios de aceptación (spec-lite)

Ver `spec.md`.

## Decisión técnica (design-lite)

Ver `design.md`.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-30
- Alcance aprobado: Change 3 - autonomous-sdd-and-remediation (`docs/roadmap/v0.8.md`, M7)
- Versión de artefactos referenciada: aprobación humana explícita registrada por hash
  (`sha256/lf/v1`) mediante `ds_guard approve` sobre `proposal.md`/`spec.md`/`design.md`, con
  entradas vivas en `control.json` -> `aprobaciones` (incluye la decisión congelada de R12a,
  incorporada al texto de `spec.md`/`design.md` ANTES de calcular el hash aprobado).
- Cita o descripción fiel de qué se aprobó: «Apruebo explícitamente proposal.md, spec.md y design.md
  del Change 3 autonomous-sdd-and-remediation. El SDD está alineado con el roadmap enmendado.» —
  fija además la decisión de R12a (reapertura tras `pausada_bloqueada` consume una nueva unidad de
  `max_sessions`) y confirma explícitamente el resto del SDD (per_change/checkpoints,
  `PreApprovedDecision`, `continue_preapproved_decision`, los 12 STOP inmutables, los 5 budgets
  configurables, LIMIT vs approval gate, concurrencia best-effort documentada honestamente, reuso de
  remediation, sin estados SDD paralelos, backward compatibility). Autoriza continuar
  autónomamente con la implementación completa de Change 3 (implementación → tests dirigidos →
  reviewer → fixes → re-tests → verification → cierre → commit local, máximo 2 ciclos
  writer↔reviewer), sin volver a pedir aprobación por decisiones ya cubiertas por este SDD; STOP
  solo ante contradicción material nueva, dependencia nueva, backward compatibility rota, expansión
  sustancial de scope, bypass/excepción, reviewer que refuta el enfoque, o remediation agotada.

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
