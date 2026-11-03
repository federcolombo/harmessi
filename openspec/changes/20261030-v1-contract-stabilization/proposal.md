# Propuesta — 20261030-v1-contract-stabilization

## Problema
`docs/versioning.md` dice "Ningún contrato es `stable` hoy" y `test_inventario_no_promete_estabilidad_v1` fija esa
negación. v1.0 debe significar que terceros pueden usar los contratos principales con estabilidad razonable (ver
`docs/roadmap/v1.0.md`). Hoy los 6 `public-candidate` no cumplen los criterios de promoción: los flags de las CLIs
no tienen ancla y los fixtures de los 3 schemas son sintéticos.

## Objetivo
Promover a `stable` exactamente los 6 `public-candidate` y activar la política 1.x para ellos, sin features nuevas.

## Evidencia
- `docs/roadmap/v1-readiness.md` (G2, G3, G7) y relevamiento de solo lectura del 2026-10-30.
- `tools/tests/test_v013_contract_inventory.py:24` (`CLASES`), `:196-205`, `:292-333` (tests atados a `public-candidate`).
- Lectores: `tools/datasources/core.py` (`SourceObservation.from_dict`), `tools/datasources/registry.py`
  (`validate_registry`), `tools/harmessi_bench/storage.py` (`load_run`). Ninguno rechaza claves top-level desconocidas.
- Parsers: `tools/ds_guard.py:5315`, `tools/ds_init/cli.py:77`, `tools/harmessi/cli.py:20`.

## Supuestos descartados
- "Fail-closed ante campo desconocido" se cumple en los 3 schemas: falso. Se decide y ancla la política opuesta (aditivo tolerado).

## Hipótesis (condicional — solo cambios metodológicos)
<!-- qué se espera confirmar/descartar, si el cambio prueba una hipótesis concreta -->

## Alcance
1. Clase `stable` en el vocabulario; los 6 contratos pasan de `public-candidate` a `stable` en `inventory.json`.
2. Política de campos desconocidos: top-level aditivo tolerado en SourceObservation, registro de fuentes y resultado de eval,
   documentado y anclado con tests (versión futura o ausente siguen rechazadas según cada lector).
3. Snapshot de superficie de las 3 CLIs (subcomandos, flags, required, choices) generado del código del tag `v0.15.0`;
   test: todo lo del snapshot existe en la CLI viva (se permiten adiciones).
4. Fixtures reales de los 3 schemas generados del tag `v0.15.0` (`generate_v015.py`, `v0_15/` con MANIFEST); tests de lectura,
   versión futura y versión ausente.
5. Reescribir el test que niega estabilidad v1 (pasa a afirmar que solo los 6 ids son `stable`) y ampliar los tests de
   inventario a `{public-candidate, stable}`.
6. Docs: `versioning.md`, `deprecation.md`, `contracts/README.md`, `README.md`, `ARCHITECTURE.md`: política 1.x a partir de
   1.0.0, ventana, fuera de la promesa lo `experimental`/`internal`.
7. Estado en `docs/roadmap/v1-readiness.md`.

## Fuera de alcance
- Features nuevas; cambiar el runtime o los schemas; promover otros contratos; bump a 1.0.0, baseline, manifest de ds_init,
  `HARMESSI-LICENSE.txt` (van en `v1-release-hardening`).
- Cambios a código de producción salvo que un test revele un defecto de contrato (se reporta como hallazgo).

## Holdout policy (condicional — solo cambios "sensible")
No aplica: no toca datos ni holdouts.

## Impacto en production-readiness (opcional)
<!-- nota libre; pasa a condicional cuando esa etapa KDD se active en un bloque futuro -->

## Criterios de aceptación (spec-lite — solo SDD abreviado)
<!-- en SDD completo, ver spec.md en su lugar -->

## Decisión técnica (design-lite — solo SDD abreviado)
<!-- en SDD completo, ver design.md en su lugar -->

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado
- docs/contracts/inventory.json
- docs/contracts/README.md
- docs/versioning.md
- docs/deprecation.md
- docs/roadmap/v1-readiness.md
- README.md
- ARCHITECTURE.md
- tools/tests/test_v013_contract_inventory.py
- tools/tests/test_v015_compat_window.py
- tools/tests/test_v1_stable_contracts.py
- tools/tests/fixtures/compat/generate_v015.py
- tools/tests/fixtures/compat/v0_15/**
- tools/datasources/tests/**
- tools/harmessi_bench/tests/**

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
