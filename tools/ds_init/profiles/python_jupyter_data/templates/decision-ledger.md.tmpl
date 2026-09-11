# Decision ledger — referencia

Se lee bajo demanda, cuando hace falta registrar, consultar o interpretar una decisión
metodológica/técnica relevante del proyecto, o cuando un cambio SDD cita una decisión ya
registrada. Nunca se carga por defecto.

## 1. Qué es y qué no es

El decision ledger es un registro **append-only** de decisiones relevantes del proyecto
(`openspec/decisions/ledger.jsonl`), a nivel de proyecto — no de cambio SDD. Distinto de SDD y de
KDD:

- SDD (`sdd.md`) especifica/decide/implementa/verifica un **cambio** puntual.
- KDD (`kdd.md`) es en qué etapa del lifecycle de Data Science está el **proyecto**.
- El decision ledger es el **registro histórico de decisiones** tomadas a lo largo del proyecto
  (target, unidad de análisis, cutoff, métrica primaria, baseline, umbral, excepciones
  metodológicas, etc.), citables desde cualquier cambio SDD futuro sin tener que releer el chat
  completo donde se aprobaron.

No reemplaza la aprobación humana explícita de `proposal.md`/`design.md` (SDD) — la complementa
como un índice consultable de decisiones ya tomadas, cada una con su cita a la aprobación
original.

## 2. Ubicación y modelo de datos

`openspec/decisions/ledger.jsonl`: nace perezoso (no lo crea `ds_init`) con el primer
`ds_guard decision add`. Un objeto JSON por línea, nunca reescrita: cada línea es un evento
inmutable con `accion` ∈ {`registrar`, `supersede`, `revocar`}.

El **estado** de una decisión (`activa`/`superseded`/`revocada`) nunca se almacena: se deriva
siempre escaneando el archivo completo (mismo criterio ya aplicado a `tasks.md estado:` frente a
`control["transiciones"]`, y a `kdd.py` frente a `state.json`). Precedencia: revocada >
superseded > activa.

Campos de una entrada `registrar`/`supersede`: `schema_version`, `seq`, `decision_id`
(`YYYYMMDD-slug`, único en todo el ledger), `utc`, `accion`, `referencia` (`null` en `registrar`,
`decision_id` anterior en `supersede`), `tipo` (uno de: `target`, `unidad_de_analisis`, `cutoff`,
`split_strategy`, `metrica_primaria`, `baseline`, `feature_decision`, `model_decision`,
`threshold`, `criterio_metodologico`, `produccion`, `excepcion_metodologica`), `resumen`,
`rationale`, `change_id` (opcional), `kdd_etapa` (opcional, del catálogo de `kdd.py`), `evidencia`
(lista de punteros — **nunca copia contenido**, apunta a `proposal.md`/`design.md`/etc.),
`aprobado_por`, `fecha_aprobacion`, `cita`, `registrado_por`.

Campos de una entrada `revocar`: `schema_version`, `seq`, `decision_id: null`, `utc`,
`accion: "revocar"`, `referencia` (obligatoria), `motivo`, `aprobado_por`, `fecha_aprobacion`,
`registrado_por`. No admite `tipo`/`resumen`/`rationale`/`evidencia`/`kdd_etapa`.

## 3. Comandos

Ninguno requiere `--change-id` de un cambio SDD como los demás comandos de `ds_guard` — el ledger
es de proyecto, no de cambio.

- **`decision add --decision-id <id> --tipo <tipo> --resumen <texto> --rationale <texto>
  --usuario <u> --fecha <f> --cita <texto> [--change-id <id>] [--kdd-etapa <etapa>]
  [--evidencia <puntero> ...] [--json]`**: registra una decisión nueva. Se rehúsa si
  `decision_id` ya existe, si falta algún campo obligatorio, si `tipo` no es válido, o si el
  ledger tiene alguna línea corrupta (fail-closed, nada se escribe).
- **`decision supersede --referencia <id-anterior> --decision-id <id-nuevo> --tipo <tipo>
  --resumen <texto> --rationale <texto> --usuario <u> --fecha <f> --cita <texto> [...]`**: registra
  una decisión que reemplaza a otra. `--referencia` debe apuntar a una decisión existente
  (`registrar`/`supersede` previa) — si no, se rehúsa. La entrada original **nunca se reescribe**;
  su estado derivado pasa a `superseded`.
- **`decision revoke --referencia <id> --motivo <texto> --usuario <u> --fecha <f>`**: revoca una
  decisión existente (sin `--cita`, sin `--tipo`). Misma validación de referencia que `supersede`.
- **`decision list [--tipo <tipo>] [--estado activa|superseded|revocada] [--change-id <id>]
  [--json]`**: lista decisiones (`registrar`/`supersede`, nunca `revocar`) con su estado derivado,
  filtradas por los parámetros dados.
- **`decision show --decision-id <id> [--json]`**: una decisión puntual con su estado derivado,
  `superseded_por` si aplica, y el detalle de la entrada que la afectó (motivo de revocación, o
  `decision_id` que la supersedió). `DECISION-ID-INEXISTENTE` si no existe.

Lectura (`list`/`show`) tolerante: una línea corrupta se reporta como `DECISION-LINEA-CORRUPTA` y
se omite, sin abortar el resto. Escritura (`add`/`supersede`/`revoke`) fail-closed: cualquier línea
corrupta existente bloquea la escritura entera (`DECISION-LEDGER-CORRUPTO`).

## 4. Ownership: quién propone, quién registra, quién aprueba

- **Propone**: el Lead o el `metodologo`, como parte de una decisión metodológica/técnica normal
  (routing de `SKILL.md`) — nunca de forma aislada del proceso SDD.
- **Aprueba**: el usuario, de forma explícita, igual que cualquier decisión relevante de
  `CLAUDE.md` §3. El campo `--cita` del comando debe reflejar esa aprobación real, no una
  inferencia del Lead.
- **Registra**: el Lead, único rol con Bash, corriendo `ds_guard decision add/supersede/revoke`
  con los valores exactos ya aprobados (mismo patrón que ya aplica con `approve`/`transition`/
  `session note`: ejecución mecánica del comando, sin redactar ni re-decidir el contenido).
  Consistente con el default `registrado_por="lead"` de `tools/dsguard/decision.py`.
  `python-data-engineer` no tiene Bash (`.claude/agents/python-data-engineer.md`) y no lo corre —
  ver `verificador.md` §7.

## 5. Cuándo se registra

**Explícito, nunca automático.** A diferencia del sync de KDD (que se dispara solo al cerrar un
cambio), ninguna transición SDD escribe en el ledger por sí sola. Se registra una decisión cuando:

- Es de un tipo del catálogo (`target`, `cutoff`, `baseline`, `threshold`, etc.) y ya tiene
  aprobación explícita del usuario.
- Se quiere dejar citable para cambios futuros sin releer el chat original.

No se registra por cada cambio SDD que se cierra, ni por cada aprobación de artefacto — solo por
decisiones de fondo que vale la pena poder referenciar después. `evidencia` apunta al artefacto
real (`proposal.md`/`design.md` del cambio donde se tomó), nunca copia su contenido.

## 6. Relación con bounded remediation

Distinto de `control["remediaciones"]` (ver `sdd.md` §8): un cambio de enfoque metodológico
(reemplazar el target, cambiar la estrategia de split, etc.) **no es una remediación** — requiere
pasar por el decision ledger (`supersede` de la decisión anterior) más, si corresponde, reabrir el
SDD del cambio afectado. Remediation es para corregir errores técnicos o bugs de implementación
dentro del mismo alcance ya aprobado, con un límite acotado de intentos por finding.
