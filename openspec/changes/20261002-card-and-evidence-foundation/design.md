# Diseño — 20261002-card-and-evidence-foundation

## Decisión metodológica/técnica

**D0.1 Paquete nuevo `tools/cards/`, familia independiente.** v0.7/v0.8 duplican deliberadamente
helpers (`canonical_json`, `_exigir_*`, escritura atómica) en vez de importarse entre sí. Se sigue el
precedente con tests de paridad (como `test_v08_source_id_parity`). Descartado: módulo común nuevo
(acopla familias, rompe "lo más nuevo no es importado por lo más viejo").

**D0.2 Referencias por pin, no por copia.** `EvidenceRef` = `kind + ref_id + content_sha256 (+member,
locator, schema_version, pinned_at)`, patrón de `DeclarationRef`/`EvidenceSource`. El hash es
obligatorio porque hace calculable el stale sin tocar el artefacto. Ids existentes: observación
`source_id__hash12`, ejecución `command_form__hash12`, `qe-…`, `dr-…`, `report_id`+`run_id`,
`decision_id`. `ObservedMetric`/`BaselineReference`/`SourceProvenance` viven dentro de un contenedor: se
citan con contenedor + `member`.

**D0.3 Dos clases, un solo punto de decisión.** `Requirement.accepts` decide qué clase satisface; el
evaluador no interpreta texto. Implementa D2 sin epistemología: `observed` vs `attestation`
(+ `trust` declared/anchored).

**D0.4 Estado derivado, nunca almacenado.** Como el ledger de decisiones (`resolver_estados`): estados
de evidencia, requisito y Card se calculan en cada `evaluate`. La Card no tiene campo `status`: no puede
quedar desactualizada ni editarse para "aprobar".

**D0.5 Resolución inyectada.** `assess.py` no sabe resolver `quality_evidence` ni `source_observation`:
recibe `resolvers`. Evita imports cruzados (reglas 7–12); Changes 1/2/4 cablean `resolve_evidence_ref`,
`compare_fingerprint`, etc. Único resolver incluido: archivo por hash binario. Fail-closed: excepción,
resolver ausente o hash no calculable → `unverifiable`.

**D0.6 Roll-up.** `invalid > stale > incomplete > complete`. `unverifiable`/`unresolvable` en un
requisito `required` cuentan como no satisfecho. Mapeo a `CheckResult`: required→FAIL,
recommended→WARN. Es validación de governance (D1): un FAIL aquí nunca bloquea runtime.

**D0.7 Identidad.** `card_id` lógico estable; `revision_id = card_id__hash12` por contenido (idempotente,
con detección de colisión como en `observations`). Una Card editada = nueva revisión, mismo `card_id`.

**D0.8 Tiempo.** Solo staleness por hash en Change 0. Ventanas de antigüedad son policy → Change 3 (D5);
`pinned_at`/`attested_at` ya se guardan para que esa policy no requiera cambiar el contrato.

**Qué NO pertenece al contrato base:** campos de dataset/modelo; `source_refs[1..N]` (Change 1);
métricas, baselines y contexto de evaluación específicos (Change 2); `risk_level`, dimensiones RAI y
policy de riesgo (Change 3); capabilities, CLI, Doctor, rendering e instalación (Change 4); resolución
de `ApprovalRef` contra control.json/ledger; frescura por tiempo; lineage/DAG; STOP; copias de payload.

## Target (condicional)
No aplica.

## Features permitidas/prohibidas (condicional)
No aplica.

## Estrategia de split/validación (condicional)
No aplica (sin holdout ni datos).

## Leakage risks (condicional)
No aplica a datos. Riesgo análogo de integridad: que una Card "apruebe" por edición. Mitigación: estado
derivado (D0.4), pin por hash, y `HumanAttestation` no satisface requisitos empíricos (R24).

## Reproducibilidad (opcional)
Sin aleatoriedad. `clock` inyectable; vectores de hash fijos en tests.

## Archivos
Nuevos: `tools/cards/{__init__,core,assess}.py`, `tools/cards/tests/{__init__,test_core,test_evidence,
test_attestation,test_assess,test_serialization}.py`, `tools/tests/test_v09_cards_neutrality.py`,
`test_v09_cards_parity.py`, `test_v09_cards_inert.py` (STOP_CATALOG + manifest + ds_guard sin cambios).
Modificados: `ARCHITECTURE.md` (regla 13, §8), `docs/roadmap/v0.9.md` (estado). No se tocan:
`ds_guard.py`, `ds_init/*`, `autonomy/*`, `doctor.py`.

## Tests (resumen)
Unitarios por R5–R40 con fixtures sintéticos de cada `kind`; tabla de identidades (paridad con
`validate_human_identity`); matriz requisito×clase×trust×estado de evidencia; round-trip/hash; paridad
de `canonical_json` con `datasources`; AST de neutralidad; no-STOP; texto D1.

## Retrocompatibilidad
Paquete no instalado ni importado por nada existente; suites v0.7/v0.8 sin edición. La activación
(capabilities opt-in `data_cards`/`model_governance`) es Change 4. Nota del audit para Change 4:
`CAPABILITIES_CONOCIDAS` hoy implica "todas las conocidas por defecto", así que agregar las nuevas ahí
las activaría por defecto → deben ser opt-in explícitas; y no existe validación de combinaciones
inválidas: `model_governance` sin `predictive_modeling` (D3) es código nuevo de Change 4.

## Alternativas descartadas
- Guardar `status` en la Card (editable, stale silencioso).
- `EvidenceRef` sin hash obligatorio (stale incalculable).
- Reusar `ApprovalRef` como atestación, o importar `autonomy` desde `cards`.
- Registro global mutable de `card_kind` (estado global, dependiente del orden de import).
- Módulo común de utilidades entre familias.
- Frescura por tiempo ya en Change 0.

## Riesgos
- Cambiar el envelope en Changes 1–2 obliga a bump de `schema_version`: mitigado con `x_*` y `body`
  opaco validado por kind.
- Sobrediseño del evaluador (convertirlo en motor de policy): se limita a `Requirement` explícitos
  provistos por el llamador.
- Duplicación de helpers: aceptada por precedente, cubierta con tests de paridad.

## Decisiones O1–O3 — RESUELTAS por el autor (2026-10-02)
- **O1:** unión estricta `attestation_kind` `declared` (sin `approval_ref`) / `anchored` (`approval_ref`
  obligatorio y estructuralmente válido); fail-closed; verificación real contra control.json/ledger en
  Change 4; sin cripto/PKI. Reemplaza el `trust` derivado propuesto abajo (R21, R23).
- **O2:** Change 0 no define ubicación física de Cards (decide Change 1).
- **O3:** `tools/cards/` fuera del manifest hasta Change 4, sin excepciones en el installer.
- Requisitos futuros preservados para Change 4: `data_cards`/`model_governance` NO pueden agregarse a
  `CAPABILITIES_CONOCIDAS` si eso las activa por defecto (opt-in explícito), y validar
  `model_governance=true` + `predictive_modeling=false` como configuración inválida fail-closed.

## Decisiones abiertas originales (histórico, ya resueltas arriba)
- **O1 — Anclaje de atestaciones.** Un archivo editable por el writer podría contener atestaciones
  fabricadas. Recomendado: `trust` `declared`/`anchored` (anclada = `approval_ref` de forma válida); un
  `Requirement` puede exigir `anchored`; Change 0 solo valida forma; la resolución real contra
  control.json/ledger va en Change 4 (el adapter sí puede importar `autonomy`/`dsguard`). Alternativa:
  resolver de anclas inyectado ya en Change 0 (más alcance, mismo contrato).
- **O2 — Ubicación de las Cards** (no afecta el contrato de Change 0). Recomendado: Change 0 solo lee/
  escribe por ruta; la convención (p. ej. `.harmessi/cards/<kind>/<card_id>.json`, versionada en git) se
  fija en Change 1 y se descubre en Change 4.
- **O3 — Instalación diferida.** Recomendado: `tools/cards/` fuera del `MANIFEST` en Change 0 (inerte,
  solo repo origen) y provisionado en Change 4 con capabilities. Alternativa: instalarlo ya sin gating
  (cambia el conjunto de archivos gestionados de todo proyecto).

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
