# Spec — 20261002-card-and-evidence-foundation

Notación: cada requisito `Rn` tiene criterio de aceptación verificable. Errores de contrato usan
`CardError(code, msg)` con códigos registrados en una única tupla `CODES` (`CARD-*`).

## Requisitos

### A. Paquete y dependencias (R1–R4)
**R1 — Paquete neutral.** `tools/cards/core.py` es solo-stdlib y no importa `tools.*` ni hermanos;
`assess.py` importa solo `core` (y `dsguard.checks` de forma perezosa, como otros paquetes).
Aceptación: test AST de neutralidad (regla 13) verde.
**R2 — Python ≥3.9**, sin dependencias nuevas.
**R3 — Inerte.** Sin cambios en `tools/ds_guard.py`, `tools/ds_init/manifest.py`, Doctor,
`guardrails.json` ni `STOP_CATALOG`. Aceptación: test compara `STOP_CATALOG` con snapshot; `git diff` de
esos archivos vacío.
**R4 — Sin Cards concretas.** Ningún módulo define campos de dataset, de modelo ni dimensiones
Responsible AI. El `body` específico de cada `card_kind` queda fuera del contrato base (ver R8).

### B. Identidad y versionado (R5–R9)
**R5 — `card_id`**: `[a-z0-9][a-z0-9_-]{0,63}` (paridad con `SOURCE_ID_PATTERN`, test de paridad);
estable entre revisiones; ids reservados rechazados.
**R6 — `card_kind`** ∈ `CARD_KINDS = ("data_card", "model_card")` (nombres reservados; Changes 1/2 los
definen).
**R7 — Versionado**: `schema_version` del envelope (=1) y `kind_schema_version` (int ≥1). Un
`schema_version` desconocido falla cerrado `CARD-SCHEMA-UNSUPPORTED` (sin interpretación parcial).
**R8 — Envelope**: `CardEnvelope(schema_version, card_kind, kind_schema_version, card_id, title,
subject, created_at, generated_at, evidence, attestations, claims, body, extensions)`. `subject` es un
identificador lógico (nunca ruta física). `body` es un objeto JSON opaco validado por un `validate_body`
inyectable (lo aportan Changes 1/2); sin validador, el body debe ser `{}`.
**R9 — `revision_id`** = `card_id + "__" + content_sha256[:12]`; determinista e idempotente.
`content_sha256()` excluye `generated_at` (convención `SourceObservation`).

### C. EvidenceRef — evidencia observada/de sistema (R10–R15)
**R10 — Campos**: `evidence_id` (local a la Card), `kind` ∈ `OBSERVED_KINDS`
(`source_observation, source_provenance, data_contract_result, quality_evidence, observed_metric,
baseline_reference, drift_evidence, execution_record, report_artifact, harmessi_contract`), `ref_id`,
`content_sha256` (64 hex minúsculas, OBLIGATORIO: es el pin), `schema_version` (int, opcional), `member`
(opcional, p. ej. `provenance` o nombre de métrica), `locator` (opcional), `pinned_at` (UTC).
**R11 — Referencia, no copia.** No hay campo de payload; test de que el dict serializado no contiene
claves fuera de la lista cerrada (más `x_*`).
**R12 — Portabilidad.** `locator` debe ser ruta POSIX relativa sin `..`, sin unidad de disco, sin `\`,
sin URL/DSN con credenciales (`CARD-LOCATOR-NOT-PORTABLE`). Las rutas físicas de fuentes externas nunca
entran (decisión v0.8).
**R13 — Provenance refs.** Una referencia a `SourceProvenance` es un `EvidenceRef` de `kind`
`source_provenance` con `ref_id` = id de observación y `member="provenance"`; se prueba con fixture
sintético. (La estructura `source_refs[1..N]` es del Change 1.)
**R14 — Ids únicos** entre evidencias y atestaciones de la Card (`CARD-DUPLICATE-ID`).
**R15 — Clase.** Toda `EvidenceRef` tiene clase `observed` (constante derivada, no serializada).

### D. HumanAttestation (R16–R21)
**R16 — Campos**: `attestation_id`, `claim` (texto no vacío), `actor`, `authority` (rol/autoridad),
`attested_at` (UTC), `scope` (texto no vacío), `reference` (opcional; id de evidencia de la misma Card o
locator portable), `attestation_kind` ∈ {`declared`,`anchored`} (obligatorio, unión estricta, ver R21),
`approval_ref` (dict `{change_id, artefacto, hash}` validado por FORMA con las reglas de
`autonomy.ApprovalRef`, sin importar `autonomy`), `narrative` (opcional).
**R17 — Actor.** No vacío, sin caracteres no imprimibles, y rechaza el namespace reservado `policy:`
(mismas reglas que `validate_human_identity`; test de paridad por tabla de casos).
**R18 — Fecha.** `attested_at` posterior al `clock` inyectado → `CARD-ATTESTATION-FUTURE`.
**R19 — Narrativa no es evidencia.** `narrative` no participa en ninguna evaluación de soporte.
**R20 — Clase.** Toda `HumanAttestation` tiene clase `attestation` (constante derivada).
**R21 — Unión estricta declared/anchored (O1 resuelta).** `attestation_kind` es explícito, nunca
derivado. `declared` ⇒ `approval_ref` ausente/null (presente ⇒ `CARD-ATTESTATION-KIND-INVALID`).
`anchored` ⇒ `approval_ref` obligatorio y de forma válida (ausente o malformado ⇒ Card `invalid`).
Valores desconocidos e híbridos se rechazan. `declared` no verifica identidad/autoridad/autenticidad ni
puede presentarse como aprobación verificada; no satisface requisitos que exigen `anchored` ni
`observed`. `anchored` en Change 0 significa SOLO «estructuralmente coherente»: no se verifica contra
`control.json`, hash de proposal ni ledger (Change 4; si esa verificación falla, la atestación no cuenta
como `anchored`). Sin firma criptográfica, identidad digital ni PKI en v0.9.

### E. Claims y requisitos (R22–R25)
**R22 — `Claim`**: `claim_id`, `requirement_id` (opcional), `statement` (no vacío), `supports` (tupla de
`evidence_id`/`attestation_id` existentes en la Card; `CARD-DANGLING-SUPPORT`).
**R23 — `Requirement`** (provisto externamente por kind/policy; NO persistido en la Card):
`requirement_id`, `severity` ∈ {`required`,`recommended`}, `accepts` ⊆ {`observed`,`attestation`} no
vacío, `accepted_kinds` (opcional, subconjunto de `OBSERVED_KINDS`), `min_attestation_kind` ∈
{`declared`,`anchored`} (default `declared`).
**R24 — Regla de trust.** Si `accepts` no contiene `attestation`, ninguna `HumanAttestation` satisface
el requisito, con independencia de su contenido. Si `accepted_kinds` está presente, evidencias de otro
kind no satisfacen.
**R25 — Template vacío no es evidencia.** Una Card con `claims`, `evidence` y `attestations` vacíos, o
con textos en blanco, no satisface ningún requisito (`missing`/`empty`).

### F. Evaluación (R26–R33)
**R26 — Resolución inyectada.** `assess.evaluate(card, requirements, resolvers, clock)`; `resolvers` es
un mapa `kind → callable(EvidenceRef) → Resolution`. Un resolver que lanza se trata como `unverifiable`
(nunca propaga ni da PASS).
**R27 — `Resolution`**: `state` ∈ {`found`,`missing`,`unverifiable`}, `current_sha256` (opcional),
`detail`.
**R28 — Estado por evidencia** (derivado, no persistido): `fresh` (found e igual hash), `stale` (found y
hash distinto), `unresolvable` (missing), `unverifiable` (sin resolver para el kind, o `unverifiable`).
**R29 — Estado por requisito**: `satisfied`, `missing` (sin claim ligado), `empty` (claim sin
`supports`), `untrusted_type` (solo hay soporte de clase/kind no aceptado o `attestation_kind` insuficiente),
`stale`, `unresolvable`, `unverifiable`. `satisfied` exige ≥1 soporte válido, aceptado y `fresh` (u
atestación con `attestation_kind` suficiente); un soporte `stale` no impide `satisfied` si otro soporte válido y
`fresh` basta por sí mismo, pero queda reportado.
**R30 — Estado de Card** (derivado, precedencia): `invalid` (falla estructural R5–R25) > `stale` (algún
requisito `required` en `stale`) > `incomplete` (algún `required` no `satisfied`) > `complete`.
La ausencia de evidencia nunca produce `complete`.
**R31 — Resolver genérico por archivo** `file_sha256_resolver(repo_root)`: hashea el `locator` relativo
(binario, `sha256/bin/v1`) tras validar que queda dentro de `repo_root`; archivo ausente → `missing`.
**R32 — Salida `CheckResult`**: `required` no satisfecho → `FAIL`; `recommended` → `WARN`; `complete`
→ `PASS`; sin requisitos aplicables → `N/A`. Códigos `CARD-REQUIREMENT-*` / `CARD-EVIDENCE-STALE`.
**R33 — Separación de dominios (D1).** Ni `evaluate` ni su salida consultan ni modifican
autonomía/`approval_mode`/STOP; los mensajes dicen «card governance requirements not satisfied» y
nunca «autonomous execution forbidden» (test de texto).

### G. Timestamps (R34–R35)
**R34 — Formato** `%Y-%m-%dT%H:%M:%SZ`, sin microsegundos; `clock` inyectable. `generated_at` se excluye
del hash; `created_at`, `pinned_at` y `attested_at` se incluyen.
**R35 — Sin hora implícita**: ninguna función de evaluación lee el reloj del sistema; solo las funciones
de escritura usan un `clock` por defecto.

### H. Serialización (R36–R40)
**R36** `to_dict` con orden de claves fijo; `from_dict` estricto (claves desconocidas rechazadas salvo
prefijo `x_`; tipos exactos).
**R37** `canonical_json`/`content_sha256` idénticos byte a byte a `datasources.core` (test de paridad con
vector fijo).
**R38** Round-trip `from_dict(to_dict(x)) == x` e idempotencia del hash.
**R39** `write_card(path, card)` atómico (`os.replace`), JSON `indent=2, sort_keys=True`; `read_card`
re-verifica estructura. Rutas dadas por el llamador; no escanea directorios y NO define ninguna ruta
canónica (`.harmessi/cards`, `docs/cards`, `cards/`, etc.): la ubicación se decide en Change 1 (O2).
`read_card` rechaza (Card `invalid`) un archivo cuyo contenido no sea estructuralmente válido y no
persiste ni lee un campo `status` como fuente de verdad (un `status` en el archivo se rechaza por clave
desconocida).
**R40** Ningún string serializado de ids/locators contiene rutas absolutas, DSN ni secretos (patrón de
R12 aplicado a todos).

### I. Retrocompatibilidad (R41–R43)
**R41** Un proyecto v0.8 instalado se comporta idéntico: suites existentes verdes sin edición.
**R42** `tools/cards/` no figura en `MANIFEST` (se instala en Change 4 con capabilities); el test de
paridad del manifest sigue verde.
**R43** `extensions` `x_*` permiten crecer sin bump de `schema_version`; un campo nuevo sin prefijo
exige bump (regla heredada de `datacontracts`).

## Criterios de aceptación
- Given un requisito `observed`-only y solo una `HumanAttestation` → `untrusted_type`, Card `incomplete`.
- Given evidencia pinneada y archivo modificado → `stale`, Card `stale`.
- Given Card vacía/plantilla → requisitos `missing`/`empty`, nunca `complete`.
- Given resolver ausente para un `kind` → `unverifiable`, nunca PASS.
- Given `approval_ref` mal formado o actor `policy:x` → Card `invalid`.
- Given `schema_version` desconocido → `CARD-SCHEMA-UNSUPPORTED`.
- Given la misma Card serializada dos veces → mismo `revision_id`.
- Given `STOP_CATALOG` antes/después → idéntico.
- Given atestación `declared` con `approval_ref` → `CARD-ATTESTATION-KIND-INVALID`; `anchored` sin o con `approval_ref` malformado → Card `invalid`; `anchored` válida → válida estructuralmente, sin afirmar verificación.
- Given `invalid`+`stale` / `invalid`+`incomplete` → `invalid`; `stale`+`incomplete` → `stale`.
- Given `content_sha256` de pin malformado, o archivo de Card cuyo `revision_id` declarado no coincide con el hash recomputado → `invalid`; hash resuelto distinto del pin (formato válido) → evidencia `stale`.
- Given Card serializada → deserializada → evaluada: mismo resultado; el archivo no contiene `status`.

## Unidad de análisis / grain (condicional)
No aplica (sin dataset).

## Cutoff / information boundary (condicional)
No aplica.

## Baseline (condicional)
No aplica.

## Métrica primaria (condicional)
No aplica.

## Métricas secundarias (opcional)
No aplica.
