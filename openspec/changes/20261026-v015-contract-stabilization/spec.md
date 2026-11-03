# Spec — 20261026-v015-contract-stabilization

## Requisitos

- R1 (B-01, D1) Ventana de compat pre-v1 explícita: versión actual + 2 menores previas (0.15, 0.14,
  0.13), limitada a artefactos con test. v0.11/v0.12 salen de la promesa; sus tests existentes se
  conservan como best-effort, documentado. Los contratos improve tienen ventana 0.14-0.15.
- R2 (B-01, D2) Contratos improve (candidate, probe, decision, proposal, lesson, budget_state,
  policy): lector estricto fail-closed, sin migración mientras la versión sea 1, tabla de compat
  por contrato y regla de bump futura.
- R3 (B-01, D3) Fixtures reales generados del tag v0.14.0 mediante script solo-checkout; el test
  v0.15 los lee con los lectores actuales.
- R4 (D4) El run manifest valida `manifest_version`: futura, no entera o bool -> incompatible con
  razón explícita; aditivo, `MANIFEST_VERSION` no cambia.
- R5 (B-02, D5) El baseline `.ds_init/control.json` no gana `schema_version`; se versiona por
  `harness_version` + `hash_alg`; decisión documentada; fixtures v0_13/v0_14 desde
  `git show <tag>:.ds_init/control.json` con test de lectura/migración con los lectores actuales.
- R6 (B-03, D6) Exit codes de las CLIs `public-candidate` (cli-ds-guard, cli-ds-init, cli-harmessi)
  documentados como "candidatos garantizados"; `harmessi_bench compare` mantiene 0 = comparación
  realizada y agrega `--fail-on-regression` opt-in.
- R7 (B-04, D7) Política de deprecación completa con `guia` obligatoria, mensaje con guía, validación
  de registro, cruce con inventory y docs con ejemplo trabajado.
- R8 (B-05, D8) SemVer pre-1.0 vs 1.x documentado por tipo de contrato, definición de "cambio
  incompatible", política de promoción y nomenclatura `contract_version`/`schema_version`.
- R9 (D8) `inventory.json` incluye campo opcional `compat` en las entradas requeridas, sin cambiar
  `inventory_version`.
- R10 (B-06) Constantes de versión (`HARNESS_VERSION`, `MANIFEST_VERSION`, `inventory_version`,
  `contract_version` improve) tienen test de compat dedicado, con `HARNESS_VERSION` anclado.
- R11 Trazabilidad: filas B-01..B-06 de la matriz y estado de C1 en el roadmap actualizados con
  evidencia al cierre.

## Criterios de aceptación

Cada criterio es verificable por test o por inspección de archivo; ninguno requiere regresión
completa.

R1
- [ ] `docs/versioning.md` contiene la sección de ventana de compat con 0.15/0.14/0.13, la limitación
  "solo artefactos con test" y el tratamiento best-effort de v0.11/v0.12.
- [ ] `test_v015_compat_window.py` falla si la ventana documentada deja de listar 0.13-0.15 (anclaje
  doc-test).
- [ ] Los tests de v0.11/v0.12 existentes siguen presentes y quedan marcados/documentados como
  best-effort (docstring o comentario), sin borrarlos.

R2
- [ ] `docs/contracts/README.md` tiene una tabla con una fila por cada uno de los 7 contratos improve y
  columnas: versión, lector, unknown-field, versión no soportada, migración, ventana.
- [ ] Test: para cada lector, un artefacto con campo desconocido -> excepción propia ("claves
  inesperadas"); con clave ausente -> excepción propia; con `contract_version` 2 -> excepción propia
  ("no soportada"); sin `contract_version` -> excepción propia. Cubre candidate, probe, decision,
  proposal, lesson, budget_state y `ProbePolicy.desde_dict`.
- [ ] La regla de bump (lector lee versión previa dentro de ventana + fixture del tag que la produjo)
  está en `versioning.md` y enlazada desde la tabla.

R3
- [ ] `generate_v014.py` existe, está documentado como solo-checkout, usa `git archive v0.14.0` en un
  directorio indicado, ejecuta el flujo candidate create -> probe -> decide --apply -> promote
  propose -> lesson add con `crear_repo` y `FakeAdapter` y copia a `tools/tests/fixtures/compat/v0_14/`.
- [ ] `tools/tests/fixtures/compat/v0_14/` contiene un artefacto de cada uno de candidate, probe,
  decision, proposal, lesson, budget_state y policy, generados (no editados a mano).
- [ ] `test_v015_compat_window.py` carga cada fixture con el lector actual sin excepción y verifica
  `contract_version == 1` y la consistencia de hash interno.
- [ ] Si el tag `v0.14.0` existe, un test regenera y compara estructura (claves y versiones, no
  hashes volátiles); si el tag no existe, el test hace skip con razón explícita.

R4
- [ ] `evaluar_compatibilidad` devuelve incompatible con razón explícita para `manifest_version`
  mayor a `MANIFEST_VERSION`, no entera (str, float) y bool; compatible para la versión actual.
- [ ] `MANIFEST_VERSION` no cambia (test).
- [ ] Los tests previos de `test_runmanifest.py` siguen pasando sin modificar sus aserciones
  existentes.

R5
- [ ] `docs/contracts/inventory.json` (nota de `schema-ds-init-baseline`), `versioning.md` y
  `contracts/README.md` documentan la decisión "sin schema_version; `harness_version` + `hash_alg`".
- [ ] Existen `fixtures/compat/v0_13/` y `v0_14/` con `control.json` obtenido con
  `git show <tag>:.ds_init/control.json`.
- [ ] Test: los lectores actuales leen ambos baselines; el resultado de migración/lectura se verifica
  (entradas, `hash_alg` conocido, `harness_version` del tag).
- [ ] `.ds_init/control.json` del repo, manifest de ds_init y Doctor no aparecen modificados.

R6
- [ ] `inventory.json` documenta exit codes 0/1/2(/3) para cli-ds-guard, cli-ds-init y cli-harmessi
  con semántica por código, y `versioning.md` declara que cambiar el significado es incompatible.
- [ ] Tests CLI de ds_init y harmessi afirman cada exit code documentado.
- [ ] `harmessi_bench compare` sin flag: exit 0 con veredicto `baseline_better` (aserción existente
  intacta).
- [ ] `harmessi_bench compare --fail-on-regression`: exit 1 con veredicto de regresión y exit 0 sin
  regresión; test para ambos casos; `--help` documenta el flag.
- [ ] Los tests de `harmessi_improve/tests/test_cli.py` afirman los exit codes documentados del
  contrato.

R7
- [ ] `Deprecation` tiene campo `guia`; `validar_registro` rechaza `guia` vacía o solo espacios.
- [ ] Mapeo documentado: deprecated_since=desde, replacement=reemplazo, earliest_removal=
  remocion_minima, migration guidance=guia.
- [ ] El mensaje de `advertir` incluye la guía (test sobre `DeprecationWarning`/mensaje).
- [ ] Test que cruza nombres del registro con inventory pasa con registro vacío y falla si un nombre
  registrado no existe en inventory (verificado con registro de prueba inyectado).
- [ ] El registro real sigue vacío (test).
- [ ] `docs/deprecation.md` contiene ejemplo trabajado y sección de visibilidad (stderr y notas de
  release).

R8
- [ ] `versioning.md` define patch/minor/major en 1.x por tipo: CLI (comando/flag/exit code), schema
  persistido, SourceObservation/adapter, skills frontmatter, Cards, contratos improve e inventory.
- [ ] Define "cambio incompatible" y los requisitos de promoción experimental -> public-candidate ->
  stable (ventana + fixtures reales + test de lector + ancla).
- [ ] Declara `contract_version` y `schema_version` como nomenclatura equivalente.

R9
- [ ] Las entradas de los 7 contratos improve, run-manifest, eval-case, eval-suite, los 3 schemas
  public-candidate y schema-ds-init-baseline tienen `compat` con las 5 claves {lector,
  campos_desconocidos, version_no_soportada, migracion, ventana}.
- [ ] Test en `test_v013_contract_inventory.py` (o v015) que exige `compat` en esas entradas y valida
  las claves.
- [ ] `inventory_version` sigue siendo 1; los smokes v0.13/v0.14 pasan sin cambiar su pin; el conteo
  de contratos sigue 50.

R10
- [ ] Test dedicado ancla `HARNESS_VERSION`, `MANIFEST_VERSION`, `inventory_version` y las
  `contract_version` improve a sus valores esperados; cambiarlos exige tocar el test.

R11
- [ ] `v0.15-debt-matrix.md` marca B-01..B-06 con estado y evidencia de cierre (o reclasificación
  justificada) y `v0.15.md` §C1 refleja el estado, ambos al cierre del Change.
- [ ] `ARCHITECTURE.md` referencia la ventana de compat y la política de deprecación sin duplicar su
  contenido.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica.

## Baseline (condicional — modeling)
No aplica (el baseline `.ds_init/control.json` es un artefacto de harness, tratado en R5).

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
No aplica.
