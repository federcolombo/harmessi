# Propuesta — 20261008-cross-platform-managed-hashing

> Change 1 de v0.10 («Integration & Stabilization + Composable Data Science Skills»), roadmap en `docs/roadmap/v0.10.md`. Cubre solo la
> deuda A. Es audit + SDD únicamente: NO implementa nada.

## Problema
El managed hash de `.ds_init/control.json` se calcula sobre bytes crudos, por lo que el mismo contenido textual lógico produce hashes
distintos según el fin de línea (LF/CRLF) del checkout (`core.autocrlf`, Windows/Linux/macOS, merge/release). En un clon limpio de otra
plataforma, Doctor reporta falsos drifts sobre archivos que no fueron modificados.

## Objetivo
Que el mismo contenido textual lógico dé el mismo managed hash independientemente de LF/CRLF, sin volver permisivo el drift real.

## Evidencia
Medido sobre el código y el working tree actuales de `v0.10-dev`, no de memoria.

- `tools/ds_init/control.py::sha256_de_archivo` hashea bytes crudos en bloques de 65536. `generar_control` (usado por `writer.instalar` y
  `regenerar_control`) y `tools/harmessi/doctor.py::_check_hashes_drift` (~l.557) lo comparan con `.ds_init/control.json` →
  `archivos[].sha256` (hex plano, sin algoritmo declarado; `control.json` no tiene `schema_version` top-level).
- Sobre los 119 archivos managed de este repo (99 `.py`, 18 `.md`, 2 `.json`; el manifest tiene 134 entradas: 111 `.py`, 20 `.md`, 3 `.json`,
  todas texto) el baseline coincide en bytes con el working tree actual (Doctor 0 WARN). Ese working tree es mixto: 81 archivos CRLF, 35 LF
  y 3 sin saltos de línea (vacíos).
- Corrección a Change 0: los «3 archivos sin LF/CRLF» de su verificación eran archivos vacíos (sin saltos de línea); no hay anomalía de
  hashing adicional.
- El caso del writer que adelantó manualmente el estado de `tasks.md` en Change 0 NO se trata acá: queda como evidencia para el Change 4
  (Composable Skills Foundation + Writer Semantics).
- Con `core.autocrlf=true`, un clon limpio de Windows daría 35 falsos drifts; un clon Linux daría 81. No hay `.gitattributes`.
- El instalador copia bytes de la fuente (`shutil.copyfile`, `newline=""`): el EOL instalado sigue al EOL del checkout de origen.

### Inventario de contratos de hash

| # | Qué hashea | Bytes o lógico | Algoritmo | Dónde persiste | ¿Cambia en este Change? |
|---|---|---|---|---|---|
| 1 | Managed baseline, `control.py::sha256_de_archivo` | bytes crudos | sha256 hex plano, sin id | `.ds_init/control.json` `archivos[].sha256` | SÍ (único) |
| 2 | `dsguard/core.py::hash_lf_v1` | texto: utf-8-sig, CRLF/CR→LF | `sha256/lf/v1` | `aprobaciones[].hash` de cada Change, manifests nbrunner, code hash de `leadrun`, `cards/approvals.py` (ApprovalRef/checkpoints `@approved`) | NO (ya EOL-agnóstico; no se reutiliza para managed: descarta BOM y exige UTF-8) |
| 3 | `ds_guard.py` ~l.354, hash inline de `proposal.md` (misma algoritmia que `hash_lf_v1`, comentada como tal) | texto | equivalente a `sha256/lf/v1` | `aprobaciones[]` | NO; hallazgo de duplicación, no se toca |
| 4 | `datasources/runtime.py` ~l.470, hash de código del adapter | bytes con CRLF/CR→LF sin decodificar | sha256 hex | provenance de SourceObservation | NO |
| 5 | Pins de Cards/evidencia: `cards/assess.py::_hash_binario_sha256` (`sha256/bin/v1`), `cards/resolvers.py` ~l.617 (sha256 de bytes del archivo) | bytes exactos | `sha256/bin/v1` / sha256 | `EvidenceRef` y pins | NO, por diseño (frontera managed vs evidence) |
| 6 | `ds_profile/fingerprint.py` (`sha256/bin/v1`), `dsguard/mlops_evidence.py` y `dsguard/scientific_validity.py` (`_hash_binario_sha256`), `qualityevidence/evidence.py`, `reporting/evidence.py`, `reporting/validation.py` (sha256 de bytes de artefactos) | bytes exactos | sha256 | estado/evidencia de proyecto | NO |
| 7 | `content_sha256()` de JSON canónico en `cards/core.py`, `cards/govpolicy.py` (incl. `BASE_POLICY_SHA256`), `datacontracts`, `datasources`, `modelquality`, `qualityevidence`, `reporting`, `leadrun` | lógico (canonical_json) | sha256 | EvidenceRef, Cards, reportes | NO (independiente de EOL por construcción) |
| 8 | `dsguard/notebooks.py::_hash_source` (fuente de celda), `ds_guard.py` ~l.1416 `hash_comando`, `ds_profile/report.py` blake2b de fila | lógico / no persistido de archivos | varios | — | NO |

### Hallazgos nuevos
- **F-1. `sync` rehashea todo.** `sync` (`tools/ds_init/cli.py` ~l.369) llama `regenerar_control`, que rehashea TODOS los archivos managed del
  manifest, incluidos los modificados por el usuario («omitir-por-existente» no los excluye del rehash). Hoy un `sync --execute` re-baselinea
  en silencio modificaciones reales y oculta drift. Resuelto por la decisión M-A aprobada (sync no adopta drift).
- **F-2. Pins de evidencia y autocrlf (fuera de alcance).** Los pins byte-exact de archivos de evidencia versionados en Git pueden verse
  afectados por autocrlf en un checkout CRLF. Se registra como candidato futuro y no se cambia (frontera managed ≠ evidence).
- **F-3. Guardrails.** `_check_hashes_drift` solo invoca la comparación semántica (`_drift_guardrails_json`, closed-list de
  `guardrails_drift.RUTAS_MUTABLES`) cuando el hash difiere. Con hash canónico, un cambio solo de EOL ya no llega a esa rama; la semántica
  de la closed-list queda intacta.

## Supuestos descartados
1. Reutilizar `hash_lf_v1` para managed: descarta BOM y exige UTF-8, por lo que no es «solo EOL».
2. Heurística «si decodifica, es texto»: no se usa; el tipo se declara en el manifest.
3. Que `.gitattributes` resuelva el problema por sí solo: no cubre copias, instalaciones previas ni checkouts sin la configuración.
4. Que existan managed binarios hoy: no los hay (todo el manifest es texto).

## Hipótesis (condicional — solo cambios metodológicos)
No aplica: es un cambio de infraestructura/hashing, no prueba una hipótesis sobre datos.

## Alcance
Un único primitive de managed hashing en `tools/ds_init/` (algoritmo versionado por entrada, streaming, solo stdlib), usado por el
instalador, `regenerar_control` y Doctor; lectura backward-compatible de baselines legacy; migración segura y explícita; `sync` conservador
(clasifica pristine/legacy/drift/nuevo, actualiza pristine y no adopta drift; DENTRO del alcance); tests.

### Decisiones de diseño propuestas (resumen; el detalle va en `design.md`)
- **D1.** Algoritmo managed-text `sha256/eol-lf/v1`: sobre bytes, CRLF→LF y CR→LF, sin decodificar, sin quitar BOM, sin tocar
  espacios/tabs/trailing whitespace/orden JSON/Unicode/mayúsculas.
- **D2.** Binarios con `sha256/bin/v1` (convención existente). El tipo se declara en el manifest con un campo `contenido` (`texto` por
  defecto | `binario`), sin heurísticas.
- **D3.** Cada entrada de `archivos[]` lleva `hash_alg`; su ausencia significa legacy bytes crudos. Sin `schema_version` ni bump.
- **D4.** Estrategia de compatibilidad elegida = A (legacy reconocido + migración explícita determinista). Una entrada legacy verifica sin
  drift si su hash coincide con el hash crudo del archivo actual, de su forma LF-canónica o de su forma CRLF; si no, es drift real como hoy.
  Doctor lo reporta como baseline legacy migrable (informativo, no WARN) con la acción sugerida. La migración solo convierte entradas que
  verifican (nunca rehashea contenido modificado), es determinista e idempotente, dry-run por defecto y `--execute` explícito. Migración de
  algoritmo ≠ re-adopción.
- **D5.** Primitive única compartida por instalador, `regenerar_control`, Doctor y migración.
- **D6.** Guardrails: sin cambios.
- **D7.** `.gitattributes`: Harmessi NO lo gestiona ni lo instala (no se sobrescribe el del proyecto); solo se documenta como defensa opcional.
- **D8.** `sync`: conservador, reconcilia sin adoptar drift (ver M-A aprobada).

### Decisiones aprobadas (2026-10-08)

**M-A (congelada): `sync` reconcilia, NO adopta** («sync never adopts pre-existing drift»). Antes de escribir, `sync` clasifica cada
archivo contra el baseline ANTERIOR:
- (A) pristine según baseline y `hash_alg`.
- (B) legacy (sin `hash_alg`) verificablemente equivalente por EOL.
- (C) drift real.
- (D) entrada nueva.

Reglas:
- Pristine + versión distinta distribuida: `sync` puede actualizar el archivo (con backup/rollback del journal) y registra el hash del NUEVO
  contenido con el algoritmo vigente (managed upgrade, no re-adopción).
- Legacy verificado: migra la entrada (y actualiza el archivo si corresponde).
- Drift: NO se reescribe el archivo, NO se rehashea, la entrada del baseline se conserva tal cual, mensaje accionable y Doctor sigue viendo
  el drift. Nunca «sync terminó y Doctor dejó de ver la modificación».
- Archivo existente sin entrada previa: no se adopta (se omite como hoy), salvo que su contenido coincida con el distribuido.
- Entradas de merge (`.claude/settings.json`, `CLAUDE.md` con `--integrar-claude`): el merge se sigue aplicando por necesidad funcional, pero
  el baseline se actualiza solo si el previo era pristine o no existía; si había drift se conserva la entrada previa.
- `regenerar_control` explícito sigue siendo la primitive de rebaseline de mantenimiento (ahora con el algoritmo nuevo); `sync` deja de
  usarlo de forma indiscriminada (modo conservador por parámetro de clasificación, sin renombrar APIs públicas).
- Separación obligatoria: hash migration (mismo contenido lógico, algoritmo viejo→nuevo) ≠ managed upgrade (pristine + nuevo asset
  distribuido) ≠ re-adoption (el humano acepta una modificación; Change 3, no este).

**Otras decisiones aprobadas**
- Algoritmos `sha256/eol-lf/v1` (CRLF→LF, CR→LF, resto intacto, sin decodificar) y `sha256/bin/v1`; el manifest declara la clase (`contenido`).
- `hash_alg` por entrada; ausencia = legacy; desconocido = fail-closed; sin bump general de schema/versión.
- Primitive única `tools/ds_init/managed_hash.py`; no se migran ApprovalRef, Cards, EvidenceRef, SourceObservation, DataContracts, reporting
  ni hashes científicos.
- `hash_lf_v1`, ApprovalRef y checkpoints intactos; guardrails intactos (capas distintas).
- `.gitattributes` NO forma parte del correctness (solo recomendación opcional documentada).
- Legacy acepta solo diferencias de EOL (crudo, forma LF o forma CRLF); limitación documentada para baselines históricos de EOL mixto.

Puntos menores resueltos por defecto: Doctor informa legacy migrable sin WARN; el downgrade a un Harmessi anterior sobre un control migrado
puede dar drift (riesgo aceptado, la migración es explícita).

### Archivos previstos
| Archivo | Cambio |
|---|---|
| `tools/ds_init/managed_hash.py` (nuevo) | primitive de managed hashing |
| `tools/ds_init/control.py` | uso del primitive, `hash_alg` por entrada |
| `tools/ds_init/manifest.py` | campo `contenido` |
| `tools/ds_init/cli.py` | migración y `sync` conservador |
| `tools/ds_init/planner.py`, `tools/ds_init/writer.py` | clasificación y actualización de archivos pristine en `sync` |
| `tools/harmessi/doctor.py` | `_check_hashes_drift` |
| `tools/ds_init/tests/`, `tools/harmessi/tests/` | tests |
| `tools/tests/test_architecture_boundaries.py` | boundaries del módulo nuevo |
| `ARCHITECTURE.md` | breve nota de frontera managed vs evidence |
| `docs/roadmap/v0.10.md` | estado del Change 1 |

## Fuera de alcance
ApprovalRef/trust, scope amendment, re-adopción de guardrails, writer semantics, skills, domain-modeling, Cards, ds_profile, reporting,
refactor general de hashing, `.gitattributes` gestionado, cambio de pins/evidencia, bump de versión del harness (lo hace el release
hardening) y regeneración de `.ds_init/control.json` de este repo (una sola vez, en Change 6).

## Holdout policy (condicional — solo cambios "sensible")
No aplica: no se toca ningún holdout ni dataset sellado.

## Impacto en production-readiness (opcional)
Ninguno directo.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md` (SDD completo).

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md` (SDD completo).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-10-08
- Alcance aprobado: Implementación, validación y cierre de Change 1 cross-platform managed hashing
- Versión de artefactos referenciada: proposal.md/spec.md/design.md vigentes al momento del hash
- Cita o descripción fiel de qué se aprobó: «Aprobación humana explícita del SDD de Change 1 y decisión M-A sobre sync»

## Alcance autorizado

- tools/ds_init/managed_hash.py
- tools/ds_init/control.py
- tools/ds_init/manifest.py
- tools/ds_init/cli.py
- tools/ds_init/planner.py
- tools/ds_init/writer.py
- tools/ds_init/tests/**
- tools/harmessi/doctor.py
- tools/harmessi/tests/**
- tools/tests/test_architecture_boundaries.py
- ARCHITECTURE.md
- docs/roadmap/v0.10.md

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
