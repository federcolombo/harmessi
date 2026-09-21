# Especificación — 20260918-eda-profile

Principio rector: el binario verifica ESTRUCTURA y aplicabilidad explícita; el metodólogo y el
reviewer evalúan adecuación. Ausencia de evaluación no es PASS. Ninguna técnica se hardcodea.

## R1. Paquete e imports
- Given el paquete `tools/reporting/`, When se agrega el profile, Then existen
  `profiles/__init__.py` (vacío), `profiles/eda.py`, `examples/__init__.py` (vacío) y
  `examples/eda_generic.py`.
- `profiles/eda.py` importa solo stdlib, `reporting.core` y `dsguard.checks` (`CheckResult`),
  con el patrón de `governance.py` (`sys.path.insert(0, tools_dir)` + `from dsguard import
  checks`). NO importa `governance`, `pandas`, Plotly ni HTML.
- `core.py` no importa `profiles`. Then el test de neutralidad del core sigue verde sin editarse.
- El profile es de solo lectura, determinista (mismas entradas ⇒ mismas salidas) y sin red.

## R2. Catálogo
- Given `BLOCK_CATALOG` (tupla de `BlockInfo(block_id, question, families,
  requires_target=False, requires_time=False)`), Then contiene exactamente estos 11 bloques, en
  este orden, con estas familias informativas (tuplas de strings):
  - `data_quality`: missingness, duplicates_and_keys, type_and_domain_validity, outlier_screening
  - `univariate`: distribution_summary, dispersion_and_shape, categorical_frequency
  - `bivariate_target` (requires_target): association_measure, group_contrast, rate_by_group
  - `multivariate`: correlation_structure, dimensionality_reduction, interaction_screening
  - `temporal` (requires_time): trend, seasonality_or_periodicity, regime_change, cohort_like
  - `concentration`: top_share, inequality_index, long_tail
  - `segmentation`: unsupervised_grouping, rule_based_segments, profile_contrast
  - `entity_relations`: cardinality_and_keys, join_integrity, graph_structure
  - `process_cycles`: duration_and_latency, state_transitions, stage_flow
  - `leakage_review`: temporal_availability, post_outcome_fields, snapshot_vs_event,
    target_proxy_screening
  - `population_and_unit`: unit_of_analysis, inclusion_exclusion, denominator_definition,
    coverage_over_time
- Las familias son solo informativas: ninguna se valida contra el capítulo ni se exige. Then el
  catálogo no nombra ni implementa técnicas concretas.
- Bloques extra del proyecto: permitidos con prefijo reservado `x_`, mismo contrato (state +
  reason; si `applicable`, capítulo con insight); nunca `requires_target`/`requires_time`.
- `EDA-EXTENSION-SHADOWS-CATALOG` WARN: bloque `x_<sufijo>` cuyo sufijo coincide con un id del
  catálogo (casefold, `-` y `_` equivalentes), p. ej. `x_bivariate_target`. Emite PASS si no hay
  ninguno. Es un aviso: la extensión no hereda las reglas del bloque que imita (ver R24).

## R3. Estados y `BlockEvaluation`
- `STATES == ("applicable", "not_applicable", "omitted")` (sin `partial`).
- `BlockEvaluation(block, state, reason="", limitations="", auto=False)`; `limitations` es texto
  libre opcional que no cambia el estado y se muestra en la tabla de cobertura.
- `not_applicable`: imposible estructuralmente (sin target/tiempo/entidad). `omitted`: aplicable
  y no realizado, con razón. `applicable`: realizado, con capítulo e insight.
- Given tipos inválidos en los campos, When se construye, Then lanza `ReportingContractError`
  (la construcción puede lanzar; la validación de reportes no, ver R8).

## R4. Autoderivación
- `derive_evaluations(target, time_column, evaluations, *, scientific_policy=None)` devuelve la
  tupla completa de evaluaciones.
- Given un bloque con `requires_target` y `target is None`, When se deriva, Then su evaluación
  es (o pasa a ser, salvo que el usuario lo haya declarado `applicable`, ver más abajo) `not_applicable` con
  `auto=True` y reason "estructuralmente no aplicable: sin target declarado", sin exigir prosa.
- Given `requires_time` y `time_column is None` y sin
  `scientific_policy["temporal"]["date_column"]`, Then igual con "sin columna temporal
  declarada".
- Given target/tiempo presentes, Then no se autoderiva y una evaluación `auto=True` recibida se
  conserva tal cual para que el validador la rechace (R12).
- Given el usuario declaró `applicable` (o un estado inválido) un bloque `requires_target`/
  `requires_time` cuya precondición falla, When se deriva, Then se CONSERVA lo declarado (no se
  degrada en silencio a `not_applicable`) para que el validador emita `EDA-TARGET-DECLARED`/
  `EDA-TIME-DECLARED` (R14) FAIL. Solo se completa o fuerza `not_applicable auto=True` cuando el
  bloque no fue declarado o fue declarado `not_applicable`/`omitted`.
- Bloques del catálogo sin evaluación y sin autoderivación NO se completan: quedan ausentes y el
  validador los reporta (R10).

## R5. Declaración en el reporte
- `Report.metadata["eda"] == {"profile": "eda", "profile_version": 1, "target": str|null,
  "time_column": str|null, "applicability": {bloque: {"state", "reason", "limitations",
  "auto"}}}`.
- Cada capítulo de un bloque lleva `Chapter.metadata["eda_block"] = <bloque>`.

## R6. Capítulo y tabla de cobertura
- `coverage_table(evaluations, decision_scope) -> TableArtifact` con `table_id="eda_coverage"`,
  columnas EXACTAS `("block", "state", "reason", "limitations")`, una fila por bloque evaluado
  (orden del catálogo, luego `x_*` ordenados), y descripción que menciona el `decision_scope`.
- Prohibido por diseño: score, porcentaje, fila agregada, "n/N" (un número de completitud
  convierte el instrumento en checklist).
- El capítulo autogenerado tiene `chapter_id="analysis_coverage"`, `metadata["eda_role"] =
  "coverage"`. Los ids `analysis_coverage` y `eda_coverage` están reservados: Given un capítulo
  o tabla del usuario con esos ids, When se construye con `build_eda_report`, Then lanza
  `ReportingContractError`.

## R7. `build_eda_report`
- `build_eda_report(report_id, title, decision_scope, chapters, evaluations, *, target=None,
  time_column=None, summary="", conclusion="", metadata=None, scientific_policy=None) ->
  Report`, `report_kind="eda"`.
- Given entradas válidas, Then aplica `derive_evaluations`, inserta el capítulo de cobertura
  PRIMERO, fusiona `metadata` del usuario con la clave `"eda"` (R5) y no muta los argumentos.
- Given `metadata` con clave `"eda"`, Then lanza `ReportingContractError` (la clave es del
  profile).
- Es determinista: dos llamadas con las mismas entradas ⇒ mismo `content_sha256`.

## R8. `validate_eda_report`: contrato general
- `validate_eda_report(report, *, scientific_policy=None) -> list[CheckResult]`. Códigos
  `EDA-*`. NUNCA lanza, incluso con metadata corrupta o tipos raros (los trata como declaración
  ausente o inválida, según corresponda). Determinista.
- Emite un PASS por regla sin violaciones (nunca lista vacía si aplica) y un resultado por cada
  violación.
- Given `report.report_kind != "eda"` y sin `metadata["eda"]`, Then devuelve N/A (un
  `CheckResult` no aplicable) y nada más.
- Given un objeto que no es `Report`, Then devuelve un FAIL `EDA-PROFILE` y no lanza.

## R9. `EDA-PROFILE` y `EDA-APPLICABILITY-MISSING`
- Given `metadata["eda"]` presente y `report_kind != "eda"`, Then `EDA-PROFILE` FAIL.
- Given `report_kind == "eda"` y una declaración con `applicability` dict, When `decl["profile"]
  != "eda"` o `decl["profile_version"]` no es el entero `1` (ni bool, ni float, ni str), Then
  `EDA-PROFILE` FAIL (las demás reglas se siguen evaluando). Si la declaración no tiene
  `applicability` dict, `EDA-PROFILE` es PASS (coherencia de kind) y decide `EDA-APPLICABILITY-MISSING`.
- Given `report_kind == "eda"` sin `metadata["eda"]` (o no es dict, o sin `applicability`
  dict), Then `EDA-APPLICABILITY-MISSING` FAIL y las reglas dependientes de la declaración no se
  evalúan.

## R10. Cobertura del catálogo
- `EDA-BLOCK-UNEVALUATED` FAIL por cada bloque del catálogo ausente en `applicability`.
- `EDA-BLOCK-UNKNOWN` FAIL por cada id fuera del catálogo y sin prefijo `x_`.
- `EDA-BLOCK-STATE` FAIL si `state` no está en `STATES` (incluye `"partial"`).

## R11. Razones
- `EDA-BLOCK-REASON` FAIL para `not_applicable`/`omitted` con `auto` falso y razón
  insuficiente. Normalización ANTES de comparar: strip, colapsar espacios, casefold, quitar
  puntuación. Es insuficiente si el resultado es vacío o está en la lista de triviales (`na`,
  `n a`, `todo`, `tbd`, `none`, `no aplica`, `-` y equivalentes tras normalizar) o tiene menos
  de 5 palabras de al menos 3 caracteres o menos de 3 palabras DISTINTAS entre ellas (p. ej.
  "TBD TBD TBD TBD TBD" es insuficiente). Los espacios y separadores Unicode (NBSP, ZWSP) se
  tratan como separadores al normalizar (todo carácter no alfanumérico ni espacio pasa a espacio).
- La lista de triviales es REDUNDANTE POR DISEÑO (defensa en profundidad): todas sus entradas
  tienen menos de 5 palabras significativas y ya las rechaza el umbral; se conserva como red
  explícita por si el umbral se relaja. No es código muerto involuntario.
- `EDA-REASON-DUPLICATED` FAIL si la misma razón normalizada aparece en 3 o más bloques
  distintos (excluye `auto=True`).
- Given "N/A.", "  TBD ", "No aplica!!", When se valida, Then FAIL; Given una razón de 5+
  palabras significativas, Then PASS de esa regla.

## R12. `EDA-AUTO-INVALID`
- FAIL si `auto=True` y (a) el bloque no tiene `requires_target`/`requires_time`, o (b) la
  precondición se cumple (target/tiempo sí declarados, considerando
  `scientific_policy["temporal"]["date_column"]`), o (c) `state != "not_applicable"`. Es el
  anti-gaming: el validador recalcula, no confía en la bandera.

## R13. Capítulos e insights
- `EDA-BLOCK-NO-CHAPTER` FAIL: bloque `applicable` sin capítulo con `eda_block` = bloque.
- `EDA-BLOCK-NO-INSIGHT` FAIL: bloque `applicable` sin al menos 1 `Insight` en sus capítulos.
- `EDA-BLOCK-CONTRADICTION` WARN: capítulo cuyo bloque está `not_applicable` u `omitted`.
- `EDA-CHAPTER-BLOCK-UNKNOWN` FAIL: capítulo con `eda_block` no evaluado en la declaración.
- Capítulos sin `eda_block` (contexto, cierre) son legítimos y no generan resultado.

## R14. Precondiciones declaradas
- `EDA-TARGET-DECLARED` FAIL: bloque `applicable` con `requires_target` y `target` null.
- `EDA-TIME-DECLARED` FAIL: bloque `applicable` con `requires_time` sin `time_column` ni
  `scientific_policy["temporal"]["date_column"]`.
- `EDA-NA-CONTRADICTS-DECLARATION` WARN: bloque `not_applicable` NO auto con `requires_target` y
  target declarado, o `requires_time` y tiempo declarado (incluida
  `scientific_policy["temporal"]["date_column"]`). Emite PASS si no hay ninguno.

## R15. `EDA-OMITTED-SCOPE`
- Given `decision_scope` en `model_valid`/`operational` y algún bloque `omitted`, Then WARN
  (visible para el reviewer, no bloquea).
- Given scope `exploratory`, Then PASS: omitir con razón es válido; un EDA completo no significa
  ejecutar todo.

## R16. `EDA-LEAKAGE-REVIEW-REQUIRED`
- Given scope `model_valid`/`operational`, `bivariate_target` `applicable` O cualquier capítulo con
  `eda_block == "bivariate_target"` (en cualquier estado declarado del bloque: omitirlo o
  marcarlo no aplicable no evade la regla) y `leakage_review` no
  `applicable`, Then FAIL: medir asociación con el target sin revisar disponibilidad temporal es
  el fallo a impedir.
- Given scope `exploratory`, Then no aplica esta regla (PASS).

## R17. `EDA-EXPLORATORY-TARGET-USE`
- Given scope `exploratory` y `bivariate_target` `applicable`, Then WARN con el aviso "no es
  insumo de selección de features". Given otro scope o bloque no aplicable, Then PASS.

## R18. `EDA-COVERAGE-TABLE`
- FAIL si falta el capítulo `analysis_coverage` o la tabla `eda_coverage`, si sus columnas no
  son exactamente `("block", "state", "reason", "limitations")`, si tiene filas de más o de
  menos respecto de la declaración, si alguna fila no coincide con la declaración, o si hay
  fila agregada/score/porcentaje fuera del contrato. Given una tabla construida por
  `coverage_table` a partir de la misma declaración, Then PASS.

## R19. Ejemplo genérico
- `examples/eda_generic.py`: `RANDOM_STATE = 42`; `build_example_report() -> Report`; datos
  SINTÉTICOS con `random.Random(RANDOM_STATE)` y estadísticas con stdlib (sin pandas); dominio
  neutro "registros sintéticos" con columnas `record_id, grupo, segmento, medida, fecha_evento,
  resultado`; `decision_scope="exploratory"`.
- Capítulos reales: `data_quality`, `univariate`, `bivariate_target` (tasa por grupo CON
  denominador; figura top-N respaldada por tabla COMPLETA), `temporal`, `concentration`,
  `population_and_unit`. `segmentation`, `multivariate`, `leakage_review` = `omitted` con
  razones distintas y suficientes; `entity_relations`, `process_cycles` = `not_applicable` con
  razones distintas.
- Cada figura tiene `backing_table_id` válido y sus columnas presentes en la tabla; cada capítulo
  aplicado tiene ≥ 1 `Insight` con `evidence_refs` válidos, `population`, `time_scope`,
  `claim_type` y `uncertainty` cuando corresponde.
- Given `validate_eda_report(build_example_report())`, Then sin ningún FAIL (WARN permitidos,
  p. ej. `EDA-EXPLORATORY-TARGET-USE`). Given dos llamadas, Then mismo `content_sha256`.
- Ningún dato, nombre, ruta ni dominio de proyectos reales; sin pandas.

## R20. Instalabilidad
- Given `tools/ds_init/manifest.py`, Then contiene 4 entradas VERBATIM (`profiles/__init__.py`,
  `profiles/eda.py`, `examples/__init__.py`, `examples/eda_generic.py`), `stage_minimo` default,
  tras la de `tools/reporting/__main__.py`. `test_installability.py` afirma su presencia.

## R21. Arquitectura
- `ARCHITECTURE.md` §2.1 agrega filas para `profiles/eda.py` (profile sobre el core; importa
  `dsguard.checks`) y `examples/eda_generic.py`. `MODULOS_CORE` de
  `tools/tests/test_architecture_boundaries.py` suma ambas rutas.

## R22. Backward compatibility
- `core.py`, `governance.py`, `cli.py`, `__main__.py` y `reporting/__init__.py` NO se
  modifican (`git diff` vacío). Ningún archivo existente cambia de comportamiento: solo hay
  adiciones (manifest, filas de docs, rutas en `MODULOS_CORE`, aserciones). Ningún check
  existente de `dsguard` cambia.

## R23. Tests (`unittest`, sin red, sin pandas)
- `test_eda_profile.py`: cada regla y cada código `EDA-*` con casos PASS/WARN/FAIL/N-A;
  normalización de razones y gaming; autoderivación; tabla de cobertura exacta y sin score;
  extensiones `x_`; scopes `exploratory`/`model_valid`/`operational`; `scientific_policy` para
  tiempo; nunca lanza con metadata corrupta o tipos raros; determinismo.
- `test_eda_example.py`: el ejemplo pasa sin FAIL; hash determinista; figura↔tabla íntegra; sin
  datos privados; sin importar pandas.

## R24. Límites declarados (no garantías)
- El binario solo filtra lo obviamente vacío. La suficiencia de razones y insights y la
  adecuación metodológica las juzga el metodólogo/reviewer.
- Un insight puede ser trivial: `applicable ⇒ ≥ 1 Insight` sigue siendo gameable; se declara
  como deuda, no como garantía.
- Las familias del catálogo no se validan contra los capítulos: un capítulo puede declararse
  de un bloque sin usar ninguna de sus familias.
- Un PASS del validador no equivale a un EDA metodológicamente correcto.
- El escape `x_` con un nombre no coincidente con el catálogo (p. ej. `x_asociacion_con_resultado`)
  puede re-implementar un análisis bivariado con el target sin que R16 lo vea: el binario no
  adivina semántica. `EDA-EXTENSION-SHADOWS-CATALOG` solo avisa cuando el sufijo coincide.
- La razón de 5+ palabras con 3+ distintas sigue siendo gameable con texto genérico
  (mitigación parcial: `EDA-REASON-DUPLICATED`); la lista de razones triviales es redundante.
- Nuevos códigos (WARN): `EDA-NA-CONTRADICTS-DECLARATION` (R14) y
  `EDA-EXTENSION-SHADOWS-CATALOG` (R2); ambos forman parte de `CODES` y se prueban en R23.
