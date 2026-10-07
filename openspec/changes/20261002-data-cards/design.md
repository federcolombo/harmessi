# Diseño — 20261002-data-cards

## Decisión metodológica/técnica

**D1 — Data Card = especialización por composición de la Foundation.** No hay tipo nuevo de Card: es un
`CardEnvelope(card_kind="data_card")` cuyo `body` valida `datacard.py` mediante el hook `validate_body` de
Change 0. Identidad, `EvidenceRef`, `HumanAttestation`, `Claim`, estados, serialización y
`evaluate`/`evaluate_file` se reutilizan tal cual. No se duplican tipos de v0.6–v0.8.

**D2 — Un dataset lógico, `1..N` fuentes, sin linaje.** `source_refs[]` dentro del body; cada una apunta a
un `EvidenceRef` de la Card por `evidence_id` (la única fuente de verdad del pin). El `source_id` lógico
se valida contra el prefijo del `ref_id` (`<source_id>__<hash12>`, convención v0.8). `role` es un
identificador libre (patrón de `SourceRef.role`); no hay taxonomía: sólo una convención sugerida
(`primary`, `enrichment`, `derived_input`). Dataset ensamblado/derivado = varias `source_refs` + una nota
descriptiva, sin DAG, sin transformaciones, sin conectores.

**D3 — Referencia, no copia.** El body contiene descripción humana (propósito, población, unidad,
limitaciones, usos). Nada de esquema, estadísticas ni profiling: eso vive en la observación y en el
contrato y se cita por pin. Data Card ≠ Data Contract: el contrato valida estructura; la Card describe el
data product y cita (declaración + resultado).

**D4 — Tres tipos de afirmación, un solo criterio.** (a) Empíricas («esta fuente fue observada»,
«el contrato aplica y se evaluó») → `EvidenceRef` observado con pin. (b) Humanas («el equipo X es dueño»)
→ `HumanAttestation`. (c) Descriptivas libres (`description`, `intended_uses`…) → contexto, no evidencia.
Los requisitos empíricos (`source:*`, `contract:*`) no aceptan atestaciones (R24 de Change 0).

**D5 — Requisitos derivados, no persistidos.** `requirements_for(card)` genera un requisito `required`
por fuente y otros `recommended` (ownership, contrato). Así el nivel de exigencia puede endurecerse en
Change 3 (policy de riesgo) sin tocar los archivos de Card. Una fuente sin soporte deja la Card
`incomplete`; no se promueve ningún `unknown` a PASS.

**D6 — Stale por fuente lógica.** La Card cita una observación concreta (`source_id__hash12` + hash). Como
el id embebe el hash, una observación nueva es otro directorio; comparar sólo «¿existe el directorio
pinneado?» nunca detectaría el cambio. Por eso el resolver compara el pin contra la observación **vigente
más reciente del mismo `source_id`**. Efecto buscado por el autor: si la fuente cambió, la Card no se
actualiza sola y queda `stale` hasta reemitirla (nueva revisión de la Card con el nuevo pin). Costo
aceptado: una Card que describe deliberadamente una observación histórica quedará `stale`; es el
comportamiento conservador. «Más reciente» = mayor `provenance.generated_at`, desempate determinista por
nombre de directorio.

**D7 — Ubicación: `governance/cards/data/<card_id>.json`.**
- *Project-owned y versionable por Git*: directorio nuevo del proyecto, fuera de `.harmessi/` (cuyo
  contenido es evidencia runtime untracked por defecto) y fuera de `.claude/`, `tools/`, `.ds_init/`.
- *Sin drift*: Doctor sólo audita `.ds_init/control.json["archivos"]` (managed); `governance/` no está en
  el `MANIFEST`, así que editar una Card no puede producir `HARMESSI-DRIFT`.
- *Sin colisión silenciosa*: no existe hoy en el repo ni lo instala `ds_init`; `docs/` y `openspec/` ya
  tienen semántica (documentación libre del usuario / SDD por Change). `write_data_card` es fail-closed
  (`exclusive`) y nunca sobrescribe un archivo existente de otra identidad.
- *Compatible con adopción*: un proyecto existente sin `governance/` no cambia; si ya lo usara para otra
  cosa, sólo se escribe en el subárbol `cards/data/` y sin pisar.
- `kind` en la ruta (`data/`) deja espacio para `governance/cards/model/` (Change 2). No hay descubrimiento
  por escaneo en este Change (Change 4 lo hará); las funciones reciben rutas o `card_id`.
- Alternativas descartadas: `.harmessi/cards` (mezcla durable con efímero), `docs/cards` (colisión con
  documentación del usuario; `docs/` no es parte del layout instalado), `openspec/cards` (SDD-scoped),
  `cards/` (genérico, riesgo de colisión).

**D8 — Resolvers stdlib en `cards`, sin importar otros paquetes.** Leen JSON y recomputan hashes con el
mismo JSON canónico que v0.7/v0.8; la equivalencia se fija con tests de paridad que sí importan los tipos
reales (`SourceObservation`, `DataContract`, `QualityEvidenceManifest`). Alternativa descartada:
importarlos (rompe la neutralidad de la regla 13) o ponerlos en `ds_guard` (acopla el adapter y complica
el testing). `data_contract_result` = manifest de `qualityevidence` con `subject_kind=
data_contract_evaluation` (no se inventa un artefacto nuevo).

**D9 — Extensión de la Foundation.** Sólo `write_card(..., exclusive=False)` (aditiva): crear sin pisar es
una necesidad de cualquier Card (también Model Cards), por eso es foundation-level y no DataCard-specific.
Change 0 no se reabre históricamente; su suite es la prueba de no regresión.

**D10 — Fail-closed uniforme.** Resolvers que no pueden leer/validar → `unverifiable`; integridad rota
→ `unverifiable`; ausente → `missing`; body inválido → `invalid`. Nunca excepción cruda ni PASS por
ausencia.

## Archivos previstos
Nuevos: `tools/cards/datacard.py`, `tools/cards/resolvers.py`,
`tools/cards/tests/{test_datacard,test_resolvers,test_datacard_location}.py`,
`tools/tests/test_v09_datacards_inert.py`, `tools/tests/test_v09_datacards_parity.py`.
Modificados: `tools/cards/assess.py` (exclusive), `tools/cards/tests/test_serialization.py` (casos de
`exclusive`, adición), `ARCHITECTURE.md` (regla 13 y §8), `docs/roadmap/v0.9.md` (progreso),
`docs/roadmap/v0.10.md` (deuda de UX de scope; ya agregada). No se tocan: `ds_guard.py`, `ds_init/*`,
Doctor, `autonomy`, `leadrun`, `datasources`, `datacontracts`, `qualityevidence`, `modelquality`,
`reporting`.

## Tests previstos
Objetos reales ligeros: `SourceObservation` construida con `datasources.core` y persistida con el mismo
layout que `runtime._persistir_observacion`; `DataContract` real; manifest real de `qualityevidence`
(`write_manifest`). Casos: Card con 1 fuente; con N fuentes (y mismo `source_id` en dos períodos);
`source_id` lógicos; ninguna ruta física en el JSON serializado; observación inexistente; hash/pin
mismatch; observación re-emitida (cambia → stale; idéntica → fresh); contrato fresh/stale/missing/
adulterado; manifest `data_contract_result` vs subject incorrecto; `declared`; `anchored` estructural;
requisito empírico no satisfecho por atestación; revisión de Card independiente de revisión de
observación; serialización determinista y round-trip→assess; archivo mal formado/clave desconocida/
schema ajeno/evidencia colgante → invalid; `write_data_card` exclusivo y `replace` con identidad;
sin drift con Doctor real; paridad de hashes con `datasources`/`datacontracts`/`qualityevidence`;
inercia (STOP, manifest, capabilities, `ds_guard`/Doctor/runtime sin menciones de `data_cards`).

## Target (condicional)
No aplica.

## Features permitidas/prohibidas (condicional)
No aplica.

## Estrategia de split/validación (condicional)
No aplica.

## Leakage risks (condicional)
No hay datasets ni features. Riesgo análogo de integridad: que la Card «apruebe» por edición o describa
datos distintos de los observados. Mitigación: estado derivado, pin por hash, stale por fuente lógica,
atestación ≠ evidencia empírica. Los resolvers nunca leen datos de proyecto ni holdouts.

## Reproducibilidad (opcional)
Sin aleatoriedad; relojes inyectables; JSON canónico determinista.

## Alternativas descartadas
- Un `KindSpec` registrado globalmente (estado global).
- Guardar requisitos o status dentro de la Card.
- Copiar esquema/estadísticas de la observación dentro de la Card.
- Un DAG/linaje o un enum grande de roles.
- Detectar cambio sólo por existencia del directorio pinneado.
- Importar `datasources`/`datacontracts`/`qualityevidence` desde `cards`.

## Riesgos
- *Evidencia untracked*: en clones nuevos los pins quedan `missing` (fail-closed); documentado (R27).
- *Duplicación de layout*: los resolvers conocen `.harmessi/observations|quality`; los tests de paridad
  fallan si v0.8/v0.7 cambian el layout.
- *Stale por «más reciente»* puede ser ruidoso en fuentes que cambian a menudo: es la semántica pedida;
  Change 3 podrá matizarla con policy.
- *Scope creep del body*: se mantiene cerrado (claves enumeradas) y lo opcional es opcional.

## Decisiones materiales
Ninguna pendiente: ubicación (D7) y semántica de stale (D6) están dentro de lo delegado por el autor.
Se informan en la revisión para el registro.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
