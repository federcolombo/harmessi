# Spec — 20260910-decision-ledger-bounded-remediation

## Requisitos
- R1. `openspec/decisions/ledger.jsonl`: un objeto JSON por línea, nace perezoso con el primer
  `decision add`. Cada línea es un evento inmutable con `accion` ∈ {`registrar`, `supersede`,
  `revocar`}; ninguna línea existente se reescribe nunca.
- R2. Campos de una entrada `registrar`/`supersede`: `schema_version`, `seq`, `decision_id`
  (`YYYYMMDD-slug`, único en todo el ledger), `utc`, `accion`, `referencia` (null en `registrar`,
  `decision_id` anterior en `supersede`), `tipo` (uno de: `target`, `unidad_de_analisis`, `cutoff`,
  `split_strategy`, `metrica_primaria`, `baseline`, `feature_decision`, `model_decision`,
  `threshold`, `criterio_metodologico`, `produccion`, `excepcion_metodologica`), `resumen`,
  `rationale`, `change_id` (opcional), `kdd_etapa` (opcional, del catálogo de `kdd.py`),
  `evidencia` (lista de punteros — nunca copia contenido), `aprobado_por`, `fecha_aprobacion`,
  `cita`, `registrado_por`.
- R3. Campos de una entrada `revocar`: `schema_version`, `seq`, `decision_id: null`, `utc`,
  `accion: "revocar"`, `referencia` (`decision_id` a revocar, obligatorio), `motivo`,
  `aprobado_por`, `fecha_aprobacion`, `registrado_por`. No admite `tipo`/`resumen`/`rationale`/
  `evidencia`/`kdd_etapa`.
- R4. `decision_id` de una entrada `registrar`/`supersede` debe ser único en todo el ledger
  (incluidas entradas de cualquier `accion`); intentar reusar uno existente se rehúsa.
- R5. `referencia` de una entrada `supersede`/`revocar` debe apuntar a un `decision_id` que ya
  exista en el ledger (de una entrada `registrar` o `supersede` previa); si no existe, se rehúsa.
- R6. Estado derivado de un `decision_id` (nunca almacenado): `revocada` si alguna entrada
  `revocar` posterior lo referencia; si no, `superseded` (con `superseded_por` = el `decision_id`
  de la entrada `supersede` que lo referencia) si alguna entrada `supersede` posterior lo
  referencia; si no, `activa`. Precedencia: revocada > superseded > activa.
- R7. `--usuario`, `--fecha`, `--cita` (`--motivo` en `revoke`, sin `--cita`) son obligatorios en
  `add`/`supersede`/`revoke` — el comando no corre sin ellos.
- R8. Lectura (`list`/`show`): tolerante a líneas corruptas — una línea que no parsea como JSON se
  reporta como hallazgo `DECISION-LINEA-CORRUPTA` (con número de línea) y se omite del resultado,
  sin abortar la lectura de las demás líneas.
- R9. Escritura (`add`/`supersede`/`revoke`): fail-closed — si al leer el archivo existente
  cualquier línea no parsea como JSON válido, la escritura completa se rehúsa (nada se agrega),
  con hallazgo `DECISION-LEDGER-CORRUPTO`.
- R10. Escritura atómica: se lee el archivo completo, se agrega la línea nueva al final, se
  escribe el archivo completo a un `.tmp` en el mismo directorio y se hace `os.replace` (mismo
  patrón que `core.escribir_texto_atomico`). Nunca un `open(..., "a")` directo.
- R11. `control["remediaciones"]`: lista de registros por `finding_id` (o sin `finding_id` para
  `retry_tecnico` puntual), cada uno con `remediation_id`, `finding_id` (nullable), `origen`
  (`reviewer`|`metodologo`|`ds_guard`|`usuario`|`lead`, libre), `tipo` ∈ {`retry_tecnico`, `bug`,
  `metodologica`} (fijado en la primera nota y validado en las siguientes), `estado` ∈ {`abierta`,
  `resuelta`}, `creado_utc`, `ventanas` (lista, ver R13), `resuelto_utc`/`resultado_final`
  (nulos hasta `resolve`).
- R12. Reglas de `finding_id` según `tipo`: `bug` y `metodologica` requieren `--finding-id` no
  vacío (si falta, se rehúsa con `REMEDIACION-FINDING-REQUERIDO`); `retry_tecnico` admite
  `--finding-id` opcional. `cambio_de_enfoque` no es un valor válido de `--remediation-tipo` (el
  CLI lo rechaza como choice inválido).
- R13. Estructura de ventanas: `ventanas: [{ventana: 1, max_intentos: <int>, autorizado_por: null,
  fecha_autorizacion: null, motivo: null, intentos: []}, ...]`. La ventana 1 nace automáticamente
  al crear la remediación (sin autorización humana, `max_intentos` = default de sesión). Toda
  ventana 2+ nace únicamente vía `remediation extend`, con `autorizado_por`/`fecha_autorizacion`/
  `motivo` obligatorios. Ningún `extend` modifica una ventana ya existente ni sus `intentos`.
- R14. Un intento (`session note --tipo reintento --finding-id ... --remediation-tipo ...`) se
  agrega a la última ventana de la remediación correspondiente si `len(intentos) < max_intentos`
  de esa ventana; si ya está en el máximo, el comando se rehúsa entero (no incrementa ni el
  contador agregado de sesión ni la remediación) con hallazgo `REMEDIACION-LIMITE`.
- R15. Un intento sobre una remediación con `estado: resuelta` se rehúsa siempre
  (`REMEDIACION-RESUELTA`), incluso si la última ventana tiene lugar disponible.
- R16. `remediation resolve` pasa `estado: abierta → resuelta`, registra `resuelto_utc` y
  `resultado_final`, conserva `ventanas`/`intentos` intactos. Un segundo `resolve` sobre una
  remediación ya `resuelta` se rehúsa (`REMEDIACION-YA-RESUELTA`) — no hay resolve idempotente
  silencioso, para no permitir sobreescribir `resultado_final`/`resuelto_utc` en silencio.
- R17. `remediation extend` sobre una remediación `resuelta` se rehúsa (`REMEDIACION-RESUELTA`) —
  reabrir un finding resuelto requiere una remediación nueva, no extender la cerrada.
- R18. `sesiones[].reintentos` (agregado existente) se sigue incrementando en cada intento
  válido de remediación — no se reemplaza ni se duplica como concepto: sigue siendo el freno que
  lee `hook_presupuesto.py` en tiempo real; `remediaciones[]` es el detalle y freno adicional por
  finding, no un sustituto.
- R19. `hook_presupuesto.py`: además de los chequeos de tiempo/continuaciones ya existentes,
  deniega un `Agent` nuevo si `reintentos >= max_reintentos` de la sesión activa (mismo criterio
  fail-safe: sin sesión activa o dato ilegible, permite).

## Criterios de aceptación
- [ ] `decision add` con todos los campos requeridos crea la primera línea del ledger con
      `seq: 0` y el resto de los campos exactos de R2.
- [ ] Dos `decision add` sucesivos conservan la primera línea byte a byte (append-only real).
- [ ] `decision supersede --referencia <id>` no reescribe la entrada `<id>`; `decision show <id>`
      reporta `estado: superseded`, `superseded_por: <nuevo id>`.
- [ ] `decision revoke --referencia <id>` no reescribe la entrada `<id>`; `decision show <id>`
      reporta `estado: revocada`.
- [ ] `decision supersede`/`revoke` con `--referencia` inexistente se rehúsa, exit code de uso
      (2), nada escrito.
- [ ] `decision add` con `--decision-id` ya usado se rehúsa, exit 2, nada escrito.
- [ ] Ledger con una línea corrupta: `decision list`/`show` reportan `DECISION-LINEA-CORRUPTA` y
      igual muestran el resto de las entradas válidas.
- [ ] `decision add` sobre un ledger con una línea corrupta se rehúsa entero
      (`DECISION-LEDGER-CORRUPTO`), archivo sin modificar (verificado con `capturar_bytes`
      antes/después).
- [ ] `session note --tipo reintento --finding-id X --remediation-tipo bug ...` sin
      `--causa/--cambio-aplicado/--resultado` según corresponda crea la remediación si no existe,
      agrega el primer intento a la ventana 1.
- [ ] El intento `max_intentos + 1` sobre el mismo finding se rehúsa, exit 2, nada escrito (ni el
      intento ni el agregado `sesiones[].reintentos`).
- [ ] `remediation resolve` pasa la remediación a `resuelta`, conserva todos los intentos previos.
- [ ] Un segundo `remediation resolve` sobre la misma remediación se rehúsa.
- [ ] Un intento nuevo sobre una remediación ya `resuelta` se rehúsa.
- [ ] `--remediation-tipo bug` o `metodologica` sin `--finding-id` se rehúsa
      (`REMEDIACION-FINDING-REQUERIDO`).
- [ ] `--remediation-tipo retry_tecnico` sin `--finding-id` se permite.
- [ ] `remediation extend` agrega una ventana 2 nueva sin tocar los intentos de la ventana 1.
- [ ] Tras el extend, un intento nuevo se agrega a la ventana 2 y se permite hasta su propio
      `max_intentos`.
- [ ] Agotada la ventana 2, un tercer intento se rehúsa hasta un nuevo `remediation extend`
      (ventana 3) con nueva autorización explícita (`--usuario/--fecha/--motivo`).
- [ ] Ningún `remediation extend` modifica el contenido de ventanas anteriores (verificado
      byte a byte / campo a campo antes y después).
- [ ] `hook_presupuesto.py`: con sesión activa y `reintentos >= max_reintentos`, un `Agent` nuevo
      se deniega (exit 2, mensaje explicativo); sin sesión activa o con `max_reintentos` no
      alcanzado, se permite igual que antes.
- [ ] Regresión: toda la suite existente (`tools/tests`, `tools/ds_init/tests`,
      `tools/harmessi/tests`) sigue en verde sin cambios de comportamiento cuando no se usan los
      flags nuevos (`--finding-id`/`--remediation-tipo`/etc. ausentes).

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica — cambio técnico de tooling/harness, sin decisión de ML de fondo.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica — cambio técnico de tooling/harness, sin decisión de ML de fondo.

## Baseline (condicional — modeling)
No aplica — cambio técnico de tooling/harness, sin decisión de ML de fondo.

## Métrica primaria (condicional — modeling, evaluation)
No aplica — cambio técnico de tooling/harness, sin decisión de ML de fondo.

## Métricas secundarias (opcional)
No aplica.
