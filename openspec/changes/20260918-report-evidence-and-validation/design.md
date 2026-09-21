# Diseño — 20260918-report-evidence-and-validation

## Decisión metodológica/técnica

### D1. Verificar estructura, no interpretación
El binario decide lo determinista: existencia de tabla de respaldo, resolución de referencias,
columnas del spec ⊂ columnas de la tabla, hashes de bytes, coherencia manifest↔Report, aislamiento.
No decide si un insight excede su evidencia, si la evidencia es adecuada ni si una tabla es
relevante: esos casos emiten WARN de revisión (`REPORT-INSIGHT-REVIEW-REQUIRED`) o quedan
documentados como límite (R24). Ausencia de evidencia no es PASS (`REPORT-SOURCES-NONE`,
`REPORT-MANIFEST-MISSING`).

### D2. Una sola fuente de verdad: se reusa lo existente
- Hash de archivo: `ds_profile.fingerprint.calcular_fingerprint` (`sha256/bin/v1`,
  `fingerprint.py:15,18`), no un hash nuevo.
- Git y escritura atómica: `dsguard.repo.get_head`/`list_dirty_files` (`repo.py:46,53`),
  `dsguard.core.ahora_utc`/`escribir_texto_atomico` (`core.py:42,88`).
- Decisiones de destino/holdout/aislamiento/cutoff: `governance.evaluate_governance` y
  `check_flow_inputs`; `validation.py` arma el `GovernanceContext` desde el manifest, no
  reimplementa reglas.
- Validación EDA: `profiles.eda.validate_eda_report`.
- Dirección de dependencias: `reporting → ds_profile` SOLO `fingerprint` (regla nueva en
  `ARCHITECTURE.md`). `core.py`, `governance.py`, `profiles/eda.py` no se modifican.

### D3. Layout sin duplicación, hashes de bytes persistidos
`manifest.json`, `insights.json`, `artifacts/report.json` (esqueleto: metadata + capítulos con ids),
`artifacts/tables/<id>.json`, `artifacts/figures/<id>.json`. Cada artefacto vive una sola vez. Los
sha256 del manifest son de los BYTES PERSISTIDOS (política del Change 0, `core.py:17-24`): verificar
es releer y hashear, sin re-serializar. `hashes.report_content` (`content_sha256`) agrega un control
lógico: `load_report_dir` reensambla el dict de `Report.to_dict` y `Report.from_dict`, y compara.
Escritura atómica archivo a archivo y `manifest.json` ÚLTIMO: un corte deja un directorio SIN
manifest, que la puerta rechaza (no hay estado "manifest válido con artefactos a medias").

### D4. Manifest como contrato explícito
Esquema con `schema_version: 1` y enums cerrados. `holdout_access` obligatorio en `build_manifest`
(declaración explícita, no default). `git_commit`/`git_dirty`/`harmessi_version` se resuelven
automáticamente pero son inyectables para tests; sin git ⇒ `None` y `REPORT-PROVENANCE` WARN (la
reproducibilidad se degrada, no se bloquea el trabajo en repos sin commit).
`describe_generated_source` cubre datos sintéticos: hash de `canonical_json(params)`, de modo que
hasta lo generado tiene identidad reproducible.

### D5. Aislamiento por hash
`REPORT-ISOLATION-INPUT` (governance) mira ruta y manifest ancestro; copiar un artefacto
exploratory a otra ruta lo evade. `exploratory_hash_index` indexa los `artifacts[].sha256` de
manifests exploratory bajo el root de la policy y `check_inputs_hash_isolation` compara los hashes
de los inputs de un flujo `model_valid`/`operational`. Cotas (`MAX_DIRS_SCAN`, `MAX_FILES_HASH`)
evitan procesos largos; superarlas es FAIL `technical_error` (fail-closed), no PASS. Cubre copias
byte-idénticas, no derivados.

### D6. Validación en tres niveles, una puerta
`validate_report` (Report en memoria), `validate_manifest` (manifest ± Report) y
`validate_report_dir` (disco, orden fijo: manifest → integridad → fuentes → contenido → governance
→ hash-isolation). La `scientific_policy` se lee UNA vez y el mismo dict alimenta a todo (fix del
reviewer del Change 2). `validate_report_dir` es la que `publish`/Change 4 debe invocar antes de
renderizar; el guard de permisos de escritura sigue siendo de governance, no de `write_report_dir`.
Enmienda (ciclo reviewer 1): `validate_report_dir` lee el directorio UNA vez (`read_report_dir`) y
usa esos bytes para hashear y reconstruir (`report_from_bytes`); ninguna fuente/artefacto se abre sin
`read_allowed` previo (fuente denegada ⇒ `REPORT-SOURCE-UNVERIFIABLE`, nunca STALE/PASS); el
conjunto de artefactos se compara con `expected_artifacts(report)` (`REPORT-ARTIFACT-SET`); los
mensajes no llevan rutas locales ni texto de excepciones (solo el tipo).

### D7. FAIL vs WARN
FAIL: hecho verificable roto (sin tabla, ref colgante, sin evidencia, hash distinto, sin fuentes,
sin manifest). WARN: requiere juicio humano o degrada reproducibilidad (causal/recommendation,
incertidumbre faltante, `git_dirty`, figura pública sobre tabla sensible, archivo no listado).
`REPORT-INSIGHT-NO-EVIDENCE` es FAIL (ver alternativas).

## Target / Features / Split
No aplica (sin modelado).

## Leakage risks
- Copia de un output exploratory hacia un flujo `model_valid`/`operational` (cubierto por
  `REPORT-ISOLATION-HASH` para copias byte-idénticas; derivados quedan como límite declarado).
- Fuentes hasheadas (enmienda, ciclo reviewer 1): el acceso se evalúa ANTES de abrir. Toda lectura
  de `evidence.py` (`describe_source`, inputs de `check_inputs_hash_isolation`, manifests del
  índice, `read_within` con `repo_root`) pasa antes por `read_allowed` (mismo evaluador que el
  hook: secretos, holdouts con/sin excepción vigente, fuera del repo, `guardrails.json`
  corrupto ⇒ denegado). Hashear un holdout es abrirlo: se deniega sin abrir. El chequeo de
  governance (`REPORT-HOLDOUT-*`) sigue siendo la puerta de decisión; este módulo no depende de
  que se haya corrido antes. No se exponen datos sellados en el manifest (solo ruta y hash).
- Ciclo 2: la lectura con acceso evaluado requiere pasar `repo_root` (`load_report_dir`,
  `read_report_dir`, `read_within`); sin él es uso local explícito. El `publish` del Change 4 DEBE
  usar el camino con `repo_root`. Límites aceptados: `resolve_harmessi_version` lee config del
  harness sin `read_allowed`; con `out_dir` fuera del repo la ruta del propio usuario puede
  aparecer como `subject` en governance; nombres de archivos dentro de un holdout pueden aparecer
  como `subject` de un FAIL (sin leer contenido); `read_allowed` recarga `guardrails.json` en cada
  llamada (costo, no correctitud). Un `OSError` al listar el directorio del reporte es FAIL
  `technical_error` (`REPORT-ARTIFACT-UNLISTED`), no PASS.
- Sha256 autoatestados: el manifest y los artefactos viven juntos; quien reescribe ambos de forma
  consistente no es detectable (integridad ≠ autenticidad). Mitigación: commit/firma externos.
- TOCTOU: hay una ventana entre `read_allowed` y la lectura, y entre hashear y usar una fuente.
  Se reduce con lecturas single-read (`read_within`, `read_report_dir`) y con
  `report_from_bytes` (reconstruye solo desde bytes ya leídos), pero no se elimina.
- Rutas: `read_within` rechaza `..`, `\x00`, nombres reservados de Windows y symlinks/junctions
  bajo `out_dir` (un artefacto no puede redirigir la lectura fuera del reporte).
- Un manifest exploratory no autoriza uso en selección de features: sigue siendo criterio del
  metodólogo (CLAUDE.md §2).

## Reproducibilidad
Sin aleatoriedad. Con `clock` y `run_id` fijos, mismo Report + fuentes + commit ⇒ bytes idénticos
(test). `run_id` real usa sufijo aleatorio SOLO en `new_run_id`, inyectable en tests.

## Alternativas descartadas
- **Segunda fuente de verdad / manifest duplicado** (p. ej. un hash propio o un manifest paralelo
  al de `ds_profile`): divergiría de `sha256/bin/v1`; se reusa `fingerprint`.
- **Hashear el objeto re-serializado en vez de bytes**: un cambio de formato invisible al objeto
  rompería la verificación o, peor, ocultaría manipulación de bytes; se hashean los bytes
  persistidos (política del Change 0).
- **Tablas embebidas en `report.json` además de `artifacts/tables/`**: duplica datos, dos copias
  pueden divergir y engorda el esqueleto; una sola copia por artefacto.
- **CSV en vez de JSON tipado para tablas**: pierde tipos (`TableArtifact` tiene filas tipadas y
  `from_dict`), obliga a inferirlos al releer y rompe el round-trip y el hash lógico.
- **`REPORT-INSIGHT-NO-EVIDENCE` como WARN**: un insight sin `evidence_refs` es una afirmación sin
  sustento verificable; degradarlo a WARN permitiría publicar narrativa sin evidencia. FAIL.
- **Que el binario juzgue si el insight excede la evidencia**: requiere semántica; se delega a
  revisión (WARN `REPORT-INSIGHT-REVIEW-REQUIRED`).
- **`write_report_dir` decide permisos**: mezclaría escritura con política; el guard es de
  governance/`publish`.

## Riesgos
- Falso sentido de seguridad: PASS de `validate_report_dir` prueba coherencia estructural e
  integridad, no calidad ni adecuación (R24). Mitigación: WARN de revisión y límites documentados.
- Costo del hash de fuentes grandes: `calcular_fingerprint` lee por chunks; el índice y el escaneo
  están acotados; sin cotas superadas por defecto en repos típicos.
- `git_dirty`/commit ausente en repos sin historia: WARN, no bloqueo.
- El índice exploratory depende de manifests presentes: sin ellos no detecta nada.
- Acoplamiento a `Report.from_dict`/`to_dict` del core: cubierto por el test de round-trip.
- `cli.py` es archivo compartido: el cambio es aditivo y los tests previos deben seguir verdes.

## Aprobación humana
El registro de aprobación vive en `proposal.md` (sección "Aprobación").
