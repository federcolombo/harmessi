# Propuesta — 20261005-operational-autonomy-hardening

> Corrective A de v0.9, originado en feedback real de Harmessi 0.8.0 (`docs/feedback/20261005_segmentacion-pc.md`).
> No renumera Changes 0–5 de v0.9. Change 4 (`20261005-cards-governance-integration`) permanece sin tocar.

## Problema
Un proyecto autónomo real expuso fallas operativas del runtime de autonomía de v0.8:
(h1) un tope agregado configurado en `autonomy.limits` nunca se aplicó; (h2/h3) al vencer el presupuesto el mensaje
no da el comando para recuperar la sesión y el hook solo acepta una forma rígida; (b) la comparación del
intérprete en Windows falla por case; (e/i/f1) el Change nace sin forma soportada de declarar su alcance, sin
`verification.md` aunque el cierre lo exige, y con dos semánticas distintas de directorio; (N1) un falso positivo
del hook de rutas sobre un comando de lectura.

## Objetivo
Cerrar esas fallas con cambios mínimos, backward-compatible y solo hacia más estricto en seguridad: límites realmente
aplicados, recuperación guiada, comparación de intérprete simétrica, alcance declarable en `proposal.md` y aprobado
por hash, defaults correctos y outputs internos del harness fuera del scope funcional.

## Evidencia (audit 2026-10-05, archivo:línea)
- h1: `_resolver_budgets` (`ds_guard.py:474-548`) solo lee `autonomy.budgets`; `autonomy.limits`
  (`max_sessions`, `max_total_minutes`) lo parsea únicamente `autonomy/policy.py:239-289`, y nadie en el CLI lo
  consume. `session start` ya aplica los topes agregados (`ds_guard.py:746-755`, `sdd.chequear_limite_agregado`
  `sdd.py:1063-1107`) pero con la config equivocada. Además `policy.py:263-264` EXIGE `limits.*` para que
  `mode: autonomous` no degrade a supervised: hoy `budgets` solo no habilita autonomía.
- h2/h3: mensajes `hook_presupuesto.py:250,260,270,310,343` sin comando; allowlist `_PATRON_DS_GUARD_SESSION`
  (`hook_presupuesto.py:109-112`) = intérprete entre comillas + `tools/ds_guard.py session note|status|close`;
  `session start` con sesión activa falla por `SesionYaActivaError` (`ds_guard.py:767`) y sin sesión activa el hook permite todo.
- b: `ds_guard.py:1945,1954-1956` pasa `args.interpreter` crudo como `interprete_autorizado`; `allowlist.py:322-323`
  normaliza solo `argv[0]`. La hash de pytest usa el intérprete crudo (`ds_guard.py:2264,2270`); la de script ya lo normaliza (`:2245`).
- e/i/f1: `cmd_init` (`ds_guard.py:3701-3704`) autoriza solo 5 artefactos; `repo.path_matches_any` (`repo.py:109-121`,
  `fnmatchcase`, usada por validate/scope y por otros 8 módulos) entiende `dir/**` y NO prefijos; `_coincide_alcance`
  de exec (`allowlist.py:112-125`) entiende prefijos de directorio y NO `dir/**`. `.harmessi/executions/**` y
  `openspec/decisions/ledger.jsonl` (`decision.py:59`) los escribe el propio harness y `evaluar_alcance`
  (`scope.py:51-65`) y `cmd_status` (`ds_guard.py:224`) los marcan `ALCANCE-RUTA`.
- N1: `pathguard._evaluar_ruta_estructurada`/`_evaluar_grep` (`pathguard.py:322-391`) ya permiten `Read`/`Grep` sobre
  `guardrails.json` (solo bloquean escritura estructurada). El falso positivo está en Bash: `_evaluar_shell`
  (`pathguard.py:469-496`) + `_es_escritura_shell` (`:422-426`) tratan toda `>` como escritura, incluida `2>/dev/null`.

## Supuestos descartados
- «`aggregate` no aplica el límite porque `session start` no lo chequea»: sí lo chequea; lo que falla es la lectura de config.
- «La autorización del intérprete compara contra una ruta externa»: compara contra el propio `--interpreter`
  (`ds_guard.py:1945`); es un chequeo de forma, y por eso basta normalizar ambos lados.
- «Hay que tocar `Read`/`Grep` estructurados por N1»: ya están permitidos; el defecto es solo de Bash.
- «Se puede cambiar `repo.path_matches_any`»: la usan otros módulos; la semántica canónica se agrega donde falta.

## Alcance
`ds_guard.py` (budgets, session, init, approve, status, exec hash), `tools/autonomy/policy.py` (aceptar `budgets`
para el requisito de límites de `autonomous`), `tools/dsguard/{sdd,scope,hook_presupuesto,pathguard}.py`,
`tools/leadrun/allowlist.py`, plantilla `proposal.md`, tests y documentación (ARCHITECTURE).

## Fuera de alcance
`ds_guard scope add`/enmienda de alcance a mitad de Change (deuda v0.10 reformulada: «mid-Change authorized scope
amendment UX»); Corrective B/C y Change 4; parsers de checkpoints/dependencias; `ds_profile`; drift de
`guardrails.json`; rediseño del hook o un parser de shell; nuevos STOP; cambios a `repo.path_matches_any`.

## Principios
Solo más estricto en seguridad; un límite configurado jamás se ignora en silencio; fail-closed ante valores
inválidos; agotar un límite produce `checkpoint_resumable`/LIMIT, nunca STOP ni aprobación automática; sin tercer
lugar de configuración; el scope se aprueba por hash junto con la propuesta.

## Deudas
v0.10: approval-origin authenticity, LF/CRLF hashing, mid-Change authorized scope amendment UX (reformulada),
composable skills, domain-modeling, one-writer. Corrective B (checkpoints circulares, `.postN`, drift de
`guardrails.json`) y C (`ds_profile`) quedan pendientes.

## Criterios de cierre
Ver spec.md: `limits`/`budgets` con semántica «más estricto» aplicada en E2E (`session start` bloqueado por tiempo y
por cantidad); mensaje de recuperación con comandos literales que el hook acepta; intérprete simétrico;
`## Alcance autorizado` parseado y materializado al aprobar; `verification.md` por defecto; outputs internos fuera de
`ALCANCE-RUTA`; `Read`/`Grep` de guardrails permitidos y Write/Edit/redirecciones reales bloqueados; regresión verde.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- openspec/changes/20261005-operational-autonomy-hardening/**
- ARCHITECTURE.md
- docs/roadmap/v0.9.md
- docs/roadmap/v0.10.md
- tools/ds_guard.py
- tools/autonomy/policy.py
- tools/autonomy/tests/**
- tools/dsguard/sdd.py
- tools/dsguard/scope.py
- tools/dsguard/hook_presupuesto.py
- tools/dsguard/pathguard.py
- tools/leadrun/allowlist.py
- tools/leadrun/tests/**
- tools/tests/**
- tools/modelquality/tests/**
- tools/qualityevidence/tests/**
- tools/datasources/tests/**
- tools/datacontracts/tests/**
- tools/cards/tests/**
- tools/ds_init/tests/**
- tools/harmessi/tests/**
- tools/reporting/tests/**
- .claude/skills/lead-data-scientist/templates/proposal.md

## Motivo de rechazo

## Desacuerdo registrado
