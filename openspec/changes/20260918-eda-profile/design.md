# Diseño — 20260918-eda-profile

## Contexto
El Change 0 dejó contratos neutrales en `tools/reporting/core.py` (`Report`, `Chapter`,
`Insight`, `TableArtifact`, con `metadata` genérico en `Chapter` `:746-756` y `Report`
`:807-820`). El Change 1 aportó gobernanza (`governance.py`) que reusa `dsguard.checks`. El
Change 2 agrega el primer profile: EDA. Debe montarse sobre el core sin modificarlo y servir de
base a los Changes 3-5.

## Decisiones

### D1. Profile aparte, sin tocar el core
`profiles/eda.py` importa stdlib, `reporting.core` y `dsguard.checks` (`CheckResult`), con el
patrón `sys.path.insert(0, tools_dir)` + `from dsguard import checks` de `governance.py`. No
importa `governance` (ningún acoplamiento entre módulos hermanos) ni pandas/Plotly/HTML. El
core no importa `profiles`. La declaración viaja en `Report.metadata["eda"]` y
`Chapter.metadata["eda_block"]`, que el core ya trata como JSON-puro opaco.

### D2. El binario verifica estructura, no adecuación
Cada regla `EDA-*` responde a una pregunta decidible sin juicio metodológico: ¿el bloque fue
evaluado? ¿el estado es válido? ¿hay razón no trivial? ¿el aplicado tiene capítulo e insight?
¿la tabla de cobertura coincide con la declaración? La adecuación (si la razón es buena, si el
insight dice algo, si la técnica elegida corresponde) es del metodólogo/reviewer. Ausencia de
evaluación no es PASS: un bloque sin evaluar es FAIL.

### D3. Catálogo de bloques con familias informativas
`BLOCK_CATALOG` es una tupla de `BlockInfo` con 11 bloques (los 9 del roadmap más
`leakage_review` y `population_and_unit`, reversibles, ver proposal.md). Las familias son
tuplas de strings para orientar al autor y al reviewer; ninguna se valida ni se exige, y ninguna
técnica concreta está codificada: el proyecto decide cómo calcular. Bloques del proyecto con
prefijo reservado `x_` siguen el mismo contrato, lo que evita bifurcar el profile por dominio.

### D4. Tres estados y autoderivación
`applicable | not_applicable | omitted`. `partial` se descarta (ver alternativas). La
imposibilidad estructural (sin target o sin tiempo) se autoderiva en `derive_evaluations`
(`auto=True`, razón generada) para no obligar a escribir prosa ritual sobre lo obvio. El
validador recalcula la precondición desde la declaración y desde `scientific_policy`, de modo
que la bandera `auto` no se pueda usar para evadir la exigencia de razón (`EDA-AUTO-INVALID`).
Un bloque declarado `applicable` sin precondición NO se degrada a `not_applicable auto`: se
conserva para que el validador emita `EDA-TARGET-DECLARED`/`EDA-TIME-DECLARED` FAIL; degradarlo
en silencio permitía evadir R16 omitiendo el target. Solo se fuerza lo no declarado o declarado
`not_applicable`/`omitted`. R16 mira además los capítulos `bivariate_target`.
`derive_evaluations` recibe `scientific_policy` como keyword opcional (extensión mínima de la
firma acordada) para considerar `temporal.date_column`; el profile no lee la política de disco.

### D5. Cobertura sin score
El capítulo `analysis_coverage` con la tabla `eda_coverage` (columnas exactas `block, state,
reason, limitations`) es la representación del "qué se evaluó y por qué no se hizo". Sin
porcentaje, fila agregada ni "n/N": un número de completitud invita a optimizar el número. La
descripción menciona el `decision_scope` para que el lector interprete la cobertura en su
contexto. Ids reservados para poder validar la tabla sin ambigüedad. `limitations` no cambia el
estado: permite honestidad sin penalizar.

### D6. Scope y leakage
- `exploratory`: omitir con razón es válido (PASS). `bivariate_target` aplicado emite WARN
  ("no es insumo de selección de features"): la exploración con target no autoriza decisiones
  de features (CLAUDE.md §2).
- `model_valid`/`operational`: `omitted` emite WARN (visible, no bloquea, porque FAIL
  contradiría "justificar lo no realizado"); `bivariate_target` sin `leakage_review` aplicado es
  FAIL: es el fallo que el profile debe impedir. Se consume el cutoff/tiempo de
  `scientific_policy` (dict); no se crea `fit_population`, la población se audita por
  `population_and_unit`.

### D7. Validación nunca lanza; construcción sí
`validate_eda_report` es total: entradas corruptas producen resultados FAIL, no excepciones. Los
constructores (`BlockEvaluation`, `build_eda_report`) sí lanzan `ReportingContractError` ante
contrato inválido, coherente con el core.

### D8. Ejemplo genérico como fixture ejecutable
`examples/eda_generic.py` usa datos sintéticos con `random.Random(RANDOM_STATE)` y stdlib, scope
`exploratory` (nunca `model_valid`: un template model-valid sin cutoff real invita a copiarlo).
Sirve de fixture para Changes 3-5 (evidencia, renderer) y prueba que el contrato es alcanzable.
Se instala vía manifest.

## Módulos y firmas (sin código)
- `profiles/eda.py`: `BlockInfo`, `BLOCK_CATALOG`, `STATES`, `BlockEvaluation`,
  `derive_evaluations`, `coverage_table`, `build_eda_report`, `validate_eda_report`, más helpers
  privados de normalización de razones.
- `examples/eda_generic.py`: `RANDOM_STATE`, `build_example_report`.
- Sin CLI nuevo: `cli.py` (Change 1) no se toca.

## Flujo
1. El proyecto arma capítulos (con `eda_block`) y evaluaciones.
2. `build_eda_report` autoderiva, agrega el capítulo de cobertura y la declaración.
3. `validate_eda_report` (con `scientific_policy` opcional) devuelve `CheckResult`s.
4. Change 3 consume esos resultados junto con la validación de evidencia; Change 4 los renderiza.

## Alternativas descartadas
- EDA en el core: rompe la neutralidad (el core no puede conocer un kind).
- Técnicas hardcodeadas (PCA, clustering, RFM, etc.): el binario terminaría juzgando
  metodología y quedaría obsoleto; las familias informativas dan orientación sin exigencia.
- Estado `partial`: es un cajón de sastre que permite eludir la razón; lo parcial se expresa
  como `applicable` con `limitations` u `omitted` con razón.
- Campo `fit_population`: duplica la política científica; se consume el cutoff de
  `scientific-policy` y la población se audita en `population_and_unit`.
- Score de cobertura: convierte el instrumento en checklist optimizable.
- `applicable ⇒ tabla/figura/insight` a elección: exigir solo insight, porque una tabla o figura
  sin conclusión es ritual y el insight ya obliga a `evidence_refs` (Change 3 verificará su
  validez); exigir un tipo de artefacto concreto sería hardcodear técnica.
- FAIL de `omitted` en `model_valid`: contradice "justificar lo no realizado"; se usa WARN.
- Agregar `target_definition`: definir el target es decisión del usuario (CLAUDE.md §3).

## Riesgos y límites
- Razones genéricas de 5+ palabras pasan el filtro (mitigación: `EDA-REASON-DUPLICATED`, revisión
  humana). Insight trivial: `applicable ⇒ ≥ 1 Insight` es gameable; deuda declarada.
- El validador no sabe si un capítulo corresponde de verdad a su bloque: confía en `eda_block`.
- Riesgo de que el ejemplo se copie como plantilla: mitigado con scope `exploratory`,
  datos sintéticos y razones específicas.
- Los dos bloques extendidos podrían resultar redundantes: son reversibles.
- Un PASS no prueba adecuación metodológica (spec R24).
- El escape `x_` con nombre no coincidente con el catálogo re-implementa análisis sin que R16 lo
  vea; solo se avisa (WARN `EDA-EXTENSION-SHADOWS-CATALOG`) cuando el sufijo repite un id. Un
  `not_applicable` manual que contradice el target/tiempo declarado es WARN
  (`EDA-NA-CONTRADICTS-DECLARATION`), no FAIL: puede ser una decisión legítima con razón.
- `_RAZONES_TRIVIALES` es redundante por diseño (defensa en profundidad) frente al umbral de
  palabras; se documenta en spec R11.

## Compatibilidad
Solo adiciones. `core.py` y `governance.py` sin cambios; el test de neutralidad de core sigue
verde sin editarse.
