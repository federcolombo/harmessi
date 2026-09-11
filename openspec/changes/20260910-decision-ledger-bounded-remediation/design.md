# Diseño — 20260910-decision-ledger-bounded-remediation

## Decisión metodológica/técnica
Dos capacidades independientes, cada una reusando al máximo la mecánica ya existente:

1. **Decision ledger** (`openspec/decisions/ledger.jsonl`): archivo JSONL global del proyecto
   (no por cambio), de eventos inmutables (`registrar`/`supersede`/`revocar`). El estado
   (`activa`/`superseded`/`revocada`) de cada `decision_id` nunca se almacena: se deriva siempre
   escaneando el archivo completo en `list`/`show`, para no crear una segunda fuente de verdad
   (mismo criterio ya aplicado a `tasks.md estado:` frente a `control["transiciones"]`).
   Lectura tolerante a corrupción de línea (un hallazgo, se sigue leyendo el resto); escritura
   fail-closed ante cualquier línea existente corrupta (nada se agrega). Escritura siempre
   atómica: leer todo, agregar la línea, escribir todo a `.tmp` + `os.replace` — nunca un append
   real al archivo (evita el riesgo de línea parcial ante una escritura interrumpida).

2. **Bounded remediation** (`control["remediaciones"]`, dentro del `control.json` del cambio):
   un registro por finding, con una lista de "ventanas" de intentos. La ventana 1 nace sola al
   primer intento sobre un finding nuevo (sin autorización humana, `max_intentos` = default de
   sesión). Agotada una ventana, el único camino para seguir intentando es `remediation extend`,
   que agrega una ventana nueva (nunca reinicia ni borra la anterior) con autorización explícita
   (`--usuario/--fecha/--motivo`). `remediation resolve` cierra el finding definitivamente
   (`estado: resuelta`), conservando todos los intentos como historial; no admite un segundo
   resolve ni intentos nuevos después de resuelto.

   El contador agregado existente `sesiones[].reintentos` **no se reemplaza**: sigue siendo el
   freno que lee `hook_presupuesto.py` en tiempo real (extensión mínima: denegar `Agent` nuevo si
   `reintentos >= max_reintentos`). `remediaciones[]` es un nivel de detalle y un freno adicional
   por finding, evaluado únicamente al momento de `session note`/`remediation resolve|extend`
   (bookkeeping determinista, no un hook nuevo).

## Target (condicional — feature_engineering, modeling)
No aplica — cambio técnico de tooling/harness, sin decisión de ML de fondo.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica — cambio técnico de tooling/harness, sin decisión de ML de fondo.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica — cambio técnico de tooling/harness, sin decisión de ML de fondo.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica — cambio técnico de tooling/harness, sin decisión de ML de fondo.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No se desvía del default: no hay aleatoriedad involucrada en ninguno de los dos mecanismos.

## Alternativas descartadas
- `ledger.json` como array único en vez de JSONL: descartado — una línea corrupta o una escritura
  interrumpida arriesgaría el archivo entero; JSONL aísla el daño a una línea y da diffs de git
  limpios (una línea = una decisión).
- `estado` almacenado como campo mutable en cada entrada del ledger: descartado — dos fuentes de
  verdad (el campo guardado y lo que un scan derivaría) pueden desincronizarse; se deriva siempre.
- Ledger de remediación global (`openspec/remediations/...`) separado del `control.json` del
  cambio: descartado — preferencia explícita del usuario de reusar `control.json`, evita un
  tercer artefacto global.
- `remediation reset` (reinicio de contador): descartado por el usuario — pierde historial;
  reemplazado por `remediation extend` (ventanas acumulativas, append-only).
- Enforcement en tiempo real por finding dentro de `hook_presupuesto.py`: descartado para v0.2 —
  requeriría que el payload de `Agent` cargue `finding_id`, que hoy no existe; el hook solo
  enforcea el agregado de sesión (ya suficiente como freno duro), el detalle por finding queda en
  el comando de bookkeeping (`session note`), que el Lead ya está obligado a correr.

## Riesgos
- Mistagging de `tipo` (declarar "bug" cuando en realidad es un cambio de enfoque): no hay
  enforcement técnico posible sin conocer semántica del contenido; queda como guidance de
  `sdd.md`/`SKILL.md`, mismo nivel de confianza que el resto de los campos de aprobación.
- Ledger de decisiones citando/copiando contenido de `proposal.md`/`design.md` en vez de
  apuntarlo: mitigado por convención (`evidencia` como lista de punteros), sin gate automático en
  v0.2 (ver deuda).
- Doble contador de reintentos (agregado + por finding) desincronizándose: mitigado manteniendo
  el agregado como única autoridad para el hook, y actualizándolo siempre en el mismo commit de
  escritura que el intento por finding (una sola función, `remediation_note`, toca ambos).

## Aprobación humana
El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único por
cambio y vive en la sección "Aprobación" de `proposal.md` — no se duplica acá.

## Deuda para v0.3+ (nota informativa, no bloquea este cambio)
- Persistir los findings de reviewer/metodólogo como artefacto propio (hoy siguen efímeros en el
  chat/prompt; solo la referencia a ellos queda en `remediaciones[]`).
- Enforcement en tiempo real del hook por `finding_id` específico.
- Hash/cadena de integridad sobre el ledger de decisiones (tamper-evidence más allá del historial
  de git).
- Gates de calidad automatizados que crucen decision ledger con cierre de etapas KDD.
- Validación de integridad en `decision_supersede`/`decision_revoke`: hoy ninguno de los dos
  chequea si la `referencia` ya está `superseded`/`revocada` antes de aceptar una nueva
  `supersede`/`revocar` sobre ella — permite, por ejemplo, dos `supersede` compitiendo sobre el
  mismo `decision_id`. `resolver_estados` no crashea ante esto (aplica "último evento en orden de
  aparición gana"), pero no hay ningún gate en v0.2 que lo detecte o lo impida.
