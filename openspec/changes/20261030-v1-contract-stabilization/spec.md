# Spec — 20261030-v1-contract-stabilization

## Requisitos
- R1 Vocabulario: `stable` es una clase válida; definición en `docs/contracts/README.md` (ventana declarada, fixtures reales,
  lector con política de versión, ancla doc-test, y ancla de superficie para CLIs).
- R2 Exactamente 6 ids son `stable`: cli-ds-guard, cli-ds-init, cli-harmessi, schema-source-observation,
  schema-source-registry, schema-eval-result. Los demás conservan su clase.
- R3 Política de campos desconocidos top-level: aditivo tolerado en los 3 schemas; versión futura rechazada en los 3;
  versión ausente rechazada en SourceObservation y registro, leída como 0 (legado) en eval-result.
- R4 Superficie CLI: snapshot generado del tag `v0.15.0`; quitar o renombrar un subcomando o flag del snapshot, o cambiar
  required/choices de forma incompatible, rompe el test. Agregar no.
- R5 Fixtures reales de `v0.15.0` para los 3 schemas, con `MANIFEST.json` (tag, versión, sha256) y generador solo-checkout.
- R6 Política 1.x documentada como vigente desde 1.0.0 (patch/minor/major por tipo ya tabulado); ventana 1.0: lee 1.x y los
  artefactos con fixture de 0.15; todo `experimental`/`internal` queda explícitamente fuera de la promesa.
- R7 El test de inventario deja de negar estabilidad y pasa a afirmar R2.

## Criterios de aceptación
- [ ] R1: `CLASES` incluye `stable`; README de contratos define la clase.
- [ ] R2: test que lista los ids `stable` y falla si hay otros o falta alguno.
- [ ] R3: tests por schema para clave extra top-level, versión futura y versión ausente con el comportamiento de R3.
- [ ] R4: `cli_surface.json` en `v0_15/`; test de inclusión sobre las 3 CLIs; test que detecta un flag removido (parser sintético).
- [ ] R5: `v0_15/` con fixtures de los 3 schemas y MANIFEST verificado (normalizando CRLF); lectura OK con lectores actuales.
- [ ] R6: `versioning.md` sin "Ningún contrato es `stable` hoy" ni "Hoy no se promete estabilidad v1.0"; doc-test ancla la ventana 1.0.
- [ ] R7: `test_inventario_no_promete_estabilidad_v1` reemplazado; sin tests atados solo a `public-candidate` para estos 6.
- [ ] Tests nuevos y tocados verdes; `test_public_docs`, `test_privacy_sweep` verdes.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
<!-- qué representa cada fila del dataset sobre el que se trabaja -->

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
<!-- fecha de corte y qué información es anterior/posterior a ella; base del chequeo anti-leakage -->

## Baseline (condicional — modeling)
<!-- modelo/heurística de referencia y su métrica, contra la que se compara todo lo nuevo -->

## Métrica primaria (condicional — modeling, evaluation)

## Métricas secundarias (opcional)
