# Diseño — 20261006-sdd-parsers-and-guardrail-ownership

## Decisiones

**D1 — Checkpoint: referencia simbólica `@approved`, hash concreto materializado.** El problema es autorreferencia, no la falta de un hash:
el registro de aprobación ya contiene el hash real. Se separa la DECLARACIÓN (`@approved`, en el proposal) de la REFERENCIA CONCRETA
(`approval_ref.hash` en `control["decisiones_preaprobadas"]`, con la forma exacta de `PreApprovedDecision`, sin tocar `autonomy`). `approve`
calcula `hash_lf_v1(proposal.md)` una sola vez y lo usa tanto para la entrada de `aprobaciones` como para materializar los `@approved` del
propio Change (garantiza igualdad). Para otro `change_id` se usa la primitiva (D2). Alternativa descartada: quitar el hash del bullet y
parsear solo `change_id` (rompe el formato `approval_ref` ya validado por `validate_pre_approved`, que exige un sha256).

**D2 — Una primitiva, dos adaptadores.** La resolución «aprobación vigente» se implementa UNA vez en dsguard
(`sdd.resolver_aprobacion_registrada`) y la usan `cards.approvals` (adaptador `AnchorResolution`) y los checkpoints (`verificar_checkpoints`).
`cards.approvals` conserva solo lo propio de Cards (forma de `approval_ref`, metadatos informativos, `AnchorResolution`). No hay segundo
resolver ni segunda definición de «vigente». El refactor se protege con los tests de Change 4 (sin debilitarlos).

**D3 — Placeholder de ceros: legible pero nunca aprobado.** Aceptar sintácticamente el cero evita romper la aprobación de proposals históricos
(`parse` no lo rechaza); como no existe ninguna entrada con hash cero, la resolución es `missing`/`placeholder` por construcción, así que
jamás concede nada. Se avisa `deprecated`; no se migra automáticamente.

**D4 — `verificar_checkpoints` informativo.** Hoy ningún código de producción consume `decisiones_preaprobadas` (el llamador de
`resolve_methodological_decision` debe armar la lista). El Corrective expone la verificación y la muestra en `ds_guard status`; NO cambia el
runtime de autonomía (D1/D5/D6 intactos) ni agrega gating. Es el «runtime posterior» mínimo con referencia verificable.

**D5 — Subset PEP 440 propio y chico.** Se necesita: igualdad, límites, rangos y comparar contra la versión instalada. Un parser universal sería
sobreingeniería y arriesga divergencias; `packaging` agregaría una dependencia core. Clave de orden:
`(release sin ceros finales, fase_pre, post, dev)` con `dev`-sin-pre ⇒ -∞ en la fase pre; sin pre ni post ni dev ⇒ final; `post` ⇒ después de
final; `dev` ⇒ antes de lo que modifica. Mismo contrato de `(operador, versión)` que hoy, mismo `ValueError` hacia el llamador. El segmento
`+local` solo se tolera en la versión consultada porque los paquetes instalados (p. ej. `torch`) lo traen y un especificador sin local lo
ignora en PEP 440. Se documenta que las reglas especiales de exclusión de pre-releases de PEP 440 para `>`/`<` NO se implementan.

**D6 — Drift semántico SOLO para guardrails, baseline = plantilla distribuida.** El instalador copia VERBATIM la plantilla; el control solo
guarda su sha256. Para decidir «cambió algo fuera de lo mutable» hace falta el baseline: la plantilla del manifiesto
(`raiz_repo_origen()`), siempre disponible porque Doctor corre desde el repo de Harmessi. Si la plantilla cambiara entre versiones, el efecto
es un drift conservador (WARN), no un falso negativo. No se agrega un campo al `control.json` (evita migración de esquema). Hash igual ⇒ sin
trabajo; hash distinto ⇒ comparación estructural tras quitar la lista cerrada.

**D7 — Lista mutable mínima y razonada.** Para activar autonomía hay que editar: `version` (de 1 a ≥2, exigido por `policy.py`),
`autonomy.mode`, `autonomy.budgets`/`limits` (límites requeridos) y opcionalmente `autonomy.version`. Eso es exactamente la lista cerrada.
`holdouts`/`data_raw`/`secretos_extra`/`write_scopes`/`excepciones` son los controles de pathguard (rutas protegidas, excepciones de holdout) y
`sealed_sources`/`source_access` son techos de acceso: se mantienen managed (ante la duda). Costo conocido y aceptado: personalizar esos campos
sigue marcando drift hasta que exista una re-adopción soportada (deuda registrada).

**D8 — Validar lo mutable en Doctor.** Hoy Doctor no parsea la policy de autonomía; sin este check, relajar el drift dejaría pasar valores
inválidos en silencio. `HARMESSI-AUTONOMY-CONFIG` reutiliza `parse_autonomy_policy` (sin lógica nueva de policy) y valida las 5 claves de
`budgets`; vive en un helper puro de `guardrails_drift` para poder testearlo sin Doctor.

## Riesgos y mitigaciones
- **Refactor de `cards.approvals`:** tests de Change 4 como red; el adaptador conserva su API pública.
- **Aceptar `@approved` solo con resolver:** sin resolver es hallazgo (nunca checkpoint sin hash real).
- **Plantilla cambia:** drift conservador, documentado.
- **Parser de versiones fuera de subset:** fail-closed con mensaje; no se adivina el orden.
- **Race de writers:** propiedad de archivos disjunta (ver tasks.md); `sdd.py` tiene un único dueño.

## Archivos previstos
`tools/dsguard/sdd.py`, `tools/dsguard/pep440_subset.py` (nuevo), `tools/dsguard/guardrails_drift.py` (nuevo), `tools/ds_guard.py`
(`approve`, `status`), `tools/cards/approvals.py`, `tools/harmessi/doctor.py`, `tools/ds_init/manifest.py`; tests nuevos
`tools/tests/test_sdd_checkpoints_approved.py`, `tools/tests/test_pep440_subset.py`, `tools/tests/test_dependency_versions_subset.py`,
`tools/tests/test_guardrails_drift.py`, `tools/harmessi/tests/test_doctor_guardrails.py`; docs ARCHITECTURE y roadmaps.

## Fuera de alcance
Ver proposal.md.
