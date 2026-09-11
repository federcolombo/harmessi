# SDD ligero — referencia

Se lee bajo demanda, solo cuando una tarea se clasifica como mediana, metodológica/alto riesgo o
sensible según el routing de `SKILL.md`. Nunca para una tarea pequeña.

## 1. Aplicabilidad

- Pequeña: sin SDD.
- Mediana: SDD abreviado.
- Metodológica, de alto riesgo o sensible (holdout/dataset sellado): SDD completo.
- No se reconstruye retroactivamente ningún artefacto para fases ya cerradas del proyecto.

## 2. Ciclo

explorar → proponer → especificar → diseñar → dividir en tareas pequeñas → implementar →
verificar → cerrar o archivar.

## 3. Artefactos por cambio

```
openspec/changes/<change-id>/
  proposal.md
  spec.md          # solo completo
  design.md         # solo completo
  tasks.md
  verification.md    # nace cuando hay evidencia real que registrar
```

`<change-id>` = `YYYYMMDD-slug` (kebab-case).

`openspec/` todavía no existe — se crea junto con el primer cambio real que use este proceso, no
antes.

## 4. Quién escribe qué

El Lead nunca edita archivos, tampoco los de `openspec/`. Todo artefacto SDD lo escribe
`python-data-engineer`, con el contenido que el Lead le pasa explícito en el prompt de
delegación — el subagente ejecuta, no redacta la decisión de fondo. El campo `estado:` vive
únicamente en `tasks.md` — ningún otro artefacto, `proposal.md` incluido, lleva su propio campo
`estado`, para no crear una segunda fuente de verdad.

## 5. Contenido mínimo y cuándo nace cada archivo

| Archivo | Contenido | Nace | ¿Abreviado? |
|---|---|---|---|
| `proposal.md` | Problema, objetivo, evidencia (archivo:línea o notebook/celda), supuestos descartados, alcance, fuera de alcance, aprobación (ver §7). La exploración vive acá, no aparte. | Borrador, junto con el resto de los artefactos del primer paso (ver §6) | Sí — con spec-lite y design-lite como subsecciones |
| `spec.md` | Requisitos y criterios de aceptación verificables. | Borrador, con `proposal.md` | No |
| `design.md` | Decisión metodológica/técnica, alternativas descartadas, riesgos; la aprobación humana explícita vive en `proposal.md` (registro único por cambio, no se duplica). | Borrador, con `proposal.md` | No |
| `tasks.md` | Tareas pequeñas, estado (`estado:` al tope), dependencias, invocaciones planificadas del cambio (ver §8). | Junto con los primeros borradores — nunca después | Sí, siempre |
| `verification.md` | Evidencia real obtenida, diferencias contra la spec, limitaciones, pendientes, resultado final. | Solo cuando ya hay evidencia real que registrar (no al entrar en `en_verificacion`) | No como archivo — sección final de `tasks.md` |

## 6. Flujo por categoría

### Mediana (SDD abreviado)

La decisión de fondo ya está tomada (así la define el routing de `SKILL.md`). Ambos modos —
abreviado y completo — nacen en `propuesta_pendiente`; el abreviado no salta directo a
`aprobada_implementacion`.

1. `ds_guard init --modo abreviado` crea `proposal.md` + `tasks.md` con
   `estado: propuesta_pendiente`.
2. `python-data-engineer` completa esos dos artefactos — problema, evidencia, alcance, criterios
   de aceptación (spec-lite), decisión técnica (design-lite), tareas. **No escribe código.**
3. El usuario revisa `proposal.md` y aprueba, pide ajustes (ronda de revisión, máx. 2) o rechaza.
4. `ds_guard approve --artefacto proposal.md` registra la aprobación con hash.
5. `ds_guard transition --a aprobada_implementacion`.
6. Recién ahí se implementa: invocación planificada de `python-data-engineer` — código escrito,
   `estado: en_implementacion`. `data-science-reviewer` (si toca features/pipeline/contratos de
   datos) revisa el diff antes de que se ejecute nada; solo informa hallazgos, no cambia estados.
   Invocación planificada de `python-data-engineer` que corre después (haya o no reviewer, haya o
   no hallazgos): si hay hallazgos los corrige (reinvocación correctiva, cuenta intento); en
   cualquier caso deja `estado: en_verificacion`. El usuario ejecuta y trae el output al chat (el
   estado permanece en `en_verificacion`). Delegación de cierre (invocación planificada, no
   reintento): agrega la sección de verificación a `tasks.md` con la evidencia real y pasa
   `estado: cerrada`. Checkpoint de cierre en el chat. El archivo permanece en
   `openspec/changes/<id>/` (§9).

### Metodológica / alto riesgo / sensible (SDD completo)

Los artefactos nacen como borrador antes de la aprobación, para que el usuario revise el artefacto
mismo. Orden de verificación: **reviewer antes de ejecutar, metodólogo después de ejecutar.**

1. Explorar (Lead, sin subagente).
2. `metodologo` (1er uso del rol) — insumo para `spec.md`/`design.md`.
3. Delegación planificada a `python-data-engineer` (2do subagente): crea los cuatro borradores —
   `proposal.md`, `spec.md`, `design.md`, `tasks.md` — con `estado: propuesta_pendiente`.
   `tasks.md` ya enumera las invocaciones planificadas siguientes.
4. El usuario revisa los artefactos (no un resumen de chat) y aprueba, pide ajustes o rechaza.
   - **Rondas de revisión**: cada ronda de ajustes pedidos antes de la primera aprobación cuenta
     como una ronda de revisión, no como intento correctivo. **Máximo 2 rondas por sesión.** Si
     tras la segunda ronda no hay acuerdo: `estado: pausada_bloqueada`, con el desacuerdo
     registrado en `proposal.md` — no se sigue iterando sin aprobar dentro de la misma sesión.
   - Rechazo definitivo (no ajuste): `estado: descartada`, motivo breve en `proposal.md`.
5. Con aprobación registrada (§7): si el usuario aprueba alcance y spec/design juntos, se pasa
   directo de `propuesta_pendiente` a `aprobada_implementacion`. `aprobada_diseño` se usa
   **solo** cuando el alcance quedó aprobado pero spec/design todavía requieren ajuste — es un
   estado intermedio, no un paso obligatorio.
6. Implementación: invocación planificada de `python-data-engineer` → código escrito,
   `estado: en_implementacion`.
7. `data-science-reviewer` revisa el código antes de que se ejecute (3er subagente). Solo informa
   hallazgos — no cambia estados.
8. Invocación planificada de `python-data-engineer` que **siempre corre** después del paso 7,
   haya o no haya hallazgos: si los hay, los corrige (esa parte es reinvocación correctiva y
   cuenta contra el límite de intentos); en cualquier caso, es quien deja
   `estado: en_verificacion` — nunca el reviewer, nunca el usuario.
9. El usuario ejecuta y trae el output. El estado permanece en `en_verificacion` — nadie lo cambia
   en este paso.
10. `metodologo` revisa resultados y conclusiones **cuando requieran interpretación
    metodológica** — es una segunda invocación planificada del mismo rol, no un reintento.
11. Cierre: invocación planificada crea `verification.md` con la evidencia real (nace acá, no
    antes) → `estado: cerrada`. El archivo permanece en `openspec/changes/<id>/`.

Reabrir un artefacto **ya aprobado** porque incumplió su criterio de aceptación sí consume el
límite de intentos (2 reinvocaciones del mismo subagente, `SKILL.md`) — distinto de una ronda de
revisión de borrador (máx. 2, antes de aprobar) y distinto de una invocación planificada
(enumerada de antemano en `tasks.md`, no consume ni intentos ni cupo nuevo).

## 7. Estados y evidencia de aprobación

| Estado | Significa | Aplica a |
|---|---|---|
| `propuesta_pendiente` | Los borradores existen (4 en completo, `proposal.md`+`tasks.md` en abreviado); usuario no revisó/aprobó todavía | Ambas |
| `aprobada_diseño` | Alcance aprobado; spec/design aún requieren ajuste | Solo completo, y solo si la aprobación no fue conjunta |
| `aprobada_implementacion` | Todo aprobado (o, en abreviado, alcance confirmado en el chat) | Ambas |
| `en_implementacion` | `python-data-engineer` trabajando | Ambas |
| `en_verificacion` | Implementación terminada y, si hubo revisión de código, ya incorporada. Esperando que el usuario ejecute y traiga el output. Lo fija siempre `python-data-engineer`, en la invocación planificada que corre después de la revisión (haya o no hallazgos) — nunca el reviewer, nunca el usuario | Ambas |
| `cerrada` | `verification.md` (o su sección en `tasks.md`) completo con evidencia real | Ambas |
| `descartada` | Usuario rechazó definitivamente el borrador; motivo breve en `proposal.md` | Ambas |
| `pausada_bloqueada` | Tope de tiempo, intentos agotados, 2 rondas de revisión sin acuerdo, decisión no aprobada, archivo fuera de alcance, holdout/dataset sellado, o ejecución que ningún agente puede correr | Ambas, desde cualquier estado salvo `cerrada`/`descartada` |

**Evidencia de aprobación** (nunca un "sí" sin más): usuario, fecha, alcance aprobado, y
referencia a la versión de los artefactos aprobada. Si el usuario responde "sí" refiriéndose
inequívocamente a la versión presentada inmediatamente antes en el chat, esa referencia cubre el
requisito — no hace falta pedirle que repita alcance y artefactos: el Lead completa esos datos a
partir del contexto inmediato y los deja explícitos en el prompt de delegación. Cuando el mensaje
del usuario ya es descriptivo por sí mismo, se cita literal.

## 8. Invocaciones planificadas vs. reintentos vs. rondas de revisión

Tres contadores distintos, ninguno se confunde con otro:

- **Invocación planificada**: parte prevista del mismo cambio (ej. cierre/verificación,
  metodólogo revisando resultados). Se enumera en `tasks.md` desde el primer borrador. No
  consume el límite de intentos ni agrega cupo de subagente nuevo (el rol ya estaba contado).
  Sigue respetando el presupuesto de tiempo/tareas de la sesión.
- **Ronda de revisión**: ajuste pedido por el usuario a un borrador **antes** de la primera
  aprobación. Máximo 2 por sesión; agotadas sin acuerdo → `pausada_bloqueada`.
- **Reintento/reinvocación correctiva**: se reabre un artefacto **ya aprobado**, o se corrige un
  hallazgo de `data-science-reviewer` sobre código ya implementado, porque no cumplió su criterio
  de aceptación. Cuenta contra el límite de 2 reinvocaciones de `SKILL.md`.

### Bounded remediation (`control["remediaciones"]`)

Extensión de este mismo §8 (Bloque 5, `20260910-decision-ledger-bounded-remediation`): además del
contador agregado `sesiones[].reintentos` (el freno que lee `hook_presupuesto.py` en tiempo real),
`control.json` del cambio lleva un detalle por finding en `control["remediaciones"]` — no lo
reemplaza, es un nivel de trazabilidad adicional.

| Tipo (`--remediation-tipo`) | `--finding-id` | Uso típico |
|---|---|---|
| `retry_tecnico` | Opcional | Reintento técnico puntual sin un finding formal asociado |
| `bug` | Obligatorio | Corrección de un bug de implementación sobre código ya aprobado |
| `metodologica` | Obligatorio | Corrección sobre un hallazgo metodológico del reviewer/metodólogo |

Cada remediación nace con una **ventana** de intentos (`ventana: 1`, sin autorización humana,
`max_intentos` = default de sesión). Un intento se registra con
`ds_guard session note --tipo reintento --finding-id <id> --remediation-tipo <tipo> --causa <texto>
--cambio-aplicado <texto> --resultado <texto>`; si la ventana vigente ya está en su máximo, el
comando se rehúsa entero (`REMEDIACION-LIMITE`) — ni el intento ni el agregado
`sesiones[].reintentos` avanzan.

- **`ds_guard remediation resolve --remediation-id <id> --resultado <texto>`**: cierra la
  remediación (`estado: resuelta`), conserva todos los intentos como historial. Un segundo
  `resolve` sobre la misma remediación se rehúsa (`REMEDIACION-YA-RESUELTA`); ningún intento nuevo
  se admite después de resuelta (`REMEDIACION-RESUELTA`).
- **`ds_guard remediation extend --remediation-id <id> --usuario <u> --fecha <f> --motivo <texto>
  [--max-intentos 2]`**: agrega una ventana nueva (nunca reinicia ni borra las anteriores),
  siempre con autorización humana explícita. Sobre una remediación ya `resuelta` se rehúsa
  (`REMEDIACION-RESUELTA`) — reabrir un finding cerrado es una remediación nueva, no un extend.

**Regla explícita: un cambio de enfoque metodológico no es una remediación.** Reemplazar el
target, la estrategia de split, la métrica primaria, etc. no se resuelve con
`session note --tipo reintento` ni con `remediation extend` — requiere pasar por el decision
ledger (`ds_guard decision supersede`, ver
`.claude/skills/lead-data-scientist/decision-ledger.md`) y, si corresponde, reabrir el SDD del
cambio afectado con aprobación explícita del usuario.

## 9. Archivado

Al cerrar, el cambio **permanece** en `openspec/changes/<id>/` con `estado: cerrada` hasta que se
archive explícitamente. `ds_guard archive`, con `git mv` exclusivamente (nunca automático) — lo
invoca el Lead, exige `estado: cerrada`, evidencia de cierre válida (gate de cierre en verde), el
directorio versionado y el working tree limpio. Por defecto corre en `--dry-run` (informa
origen/destino, no mueve nada); requiere `--execute` explícito para el `git mv` real. Detalle de
comandos y hallazgos en `.claude/skills/lead-data-scientist/verificador.md`.

## 10. Relación con la documentación existente

- Vive en SDD: problema/evidencia/decisión/tareas/verificación de un cambio acotado.
- Sigue en la documentación del proyecto: estado vigente y acumulado del diseño, handoff vigente y
  esquema de datos — SDD no los reemplaza, se suma como nivel más granular dentro de la jerarquía
  de `CLAUDE.md`.
- El histórico de fase del proyecto (en qué etapa de Data Science está: Data Understanding,
  Modeling, Evaluation, etc.) ya no es un concepto sin artefacto: lo cubre KDD, un nivel por
  encima de SDD — ver `.claude/skills/lead-data-scientist/kdd.md`. Un cambio puede declarar a qué
  etapa pertenece (`control["kdd"]`); cerrarlo agrega evidencia a esa etapa, nunca la avanza por sí
  solo.
- El handoff se actualiza cuándo ya se actualiza hoy: al cerrar una fase, aparte. Ningún cambio SDD
  individual lo dispara por sí solo.
- Los artefactos SDD **enlazan, nunca copian** `CLAUDE.md`, el documento maestro, el handoff y el
  esquema de datos.
