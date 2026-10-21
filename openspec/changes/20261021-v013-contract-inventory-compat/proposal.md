# Propuesta — 20261021-v013-contract-inventory-compat

> Change 5 de v0.13: Contract Inventory, Compatibility & Deprecation Foundation. Prepara v1.0 sin declarar estabilidad.

## Problema
Los contratos que un tercero podría consumir (CLIs y exit codes, schemas JSON versionados, contrato de skills, assets managed, adapters) están dispersos y sin clasificar; no hay ventana de compatibilidad documentada ni tests focalizados de lectura de artefactos de releases anteriores; no existe convención de deprecación ni lectura documentada de SemVer para 0.x vs 1.x. Sin eso no se sabe qué habrá que congelar para v1.0.

## Objetivo
Inventario clasificado (`public candidate` / `internal` / `experimental`) anclado a la realidad por un test; tests de compatibilidad de lectura de artefactos v0.11 y v0.12; ventana de soporte documentada; convención + primitiva mínima de deprecación; documento de versionado. Sin prometer estabilidad v1.0 y sin framework.

## Evidencia
- Versionados existentes: `SourceObservation.SCHEMA_VERSION = 1` (`tools/datasources/core.py`), registro de fuentes `SCHEMA_VERSION` (`registry.py`), `RESULT_SCHEMA_VERSION`, `CASE_CONTRACT_VERSION`, `MANIFEST_VERSION`, `suite_contract_version` (v0.13 Changes 1–2), `HARNESS_VERSION` (`tools/ds_init/version.py`), frontmatter cerrado de skills (`skill_contract.py`), `.ds_init/control.json` (baseline managed), `control.json` por Change.
- CLIs: `tools/ds_guard.py` (muchos subcomandos), `tools/ds_init/cli.py`, `tools/harmessi/cli.py`, `tools/harmessi_bench/cli.py`, `tools/dsimpact/cli.py`, `tools/providers/conformance.py`.
- `docs/roadmap/v1.0.md`: criterios (contratos CLI estables, schemas versionados y migrables, compatibilidad formal, estrategia de deprecación, versionado semántico consistente).
- Tags públicos `v0.11.0` y `v0.12.0` (artefactos reales de referencia; los fixtures de compatibilidad se derivan de su forma y se genericizan).

## Supuestos descartados
- Que haya deprecaciones reales hoy: no las hay; la primitiva queda con registro vacío.
- Compatibilidad infinita: se documenta una ventana (versión actual + las dos menores previas para lectura; más antiguo, mejor esfuerzo).
- Un framework de deprecación/migración nuevo: no.

## Alcance
- `docs/contracts/inventory.json` (fuente legible por máquina) + `docs/contracts/README.md` (vista humana, vocabulario y reglas de cambio) cubriendo: CLIs (subcomandos y exit codes observados en el código), schemas/versiones persistentes, contrato de skills, assets managed/baseline, contratos de adapters/providers, contrato de superficies (Protected/Optimizable/Project-owned) y comportamiento de upgrade. Cada entrada: `id`, `clase`, `ubicacion`, `version_campo`/`version` si aplica, `notas`.
- `tools/tests/test_v013_contract_inventory.py`: ancla el inventario (subcomandos de cada CLI existen y los del inventario no sobran/faltan para las CLIs `public candidate`; constantes de versión coinciden con el valor del inventario; rutas citadas existen; clases válidas; ningún `public candidate` sin versión cuando es un schema persistente).
- Fixtures sintéticos genéricos `tools/tests/fixtures/compat/{v0_11,v0_12}/` y `tools/tests/test_v013_compat_window.py`: lectura por el código actual de resultados de eval sin `schema_version`, observaciones `SourceObservation` v1, registro de fuentes, baseline `.ds_init/control.json`, `control.json` de Change, frontmatter de skills y traza `## Skills cargados` de esas releases; más una verificación opcional contra los tags `v0.11.0`/`v0.12.0` si existen localmente (skip explícito si no).
- `docs/versioning.md`: lectura de SemVer 0.x vs 1.x para cambios incompatibles, schemas y CLI; relación versión del harness ↔ versiones de schema; ventana de compatibilidad.
- `docs/deprecation.md` y `tools/harmessi/deprecation.py` (solo-checkout): `Deprecation` (nombre, tipo, desde, reemplazo, remoción más temprana), `DEPRECATIONS = ()`, validación de entradas y `advertir()` con formato fijo (`DeprecationWarning`); tests.
- ARCHITECTURE.md, README.md, roadmap (Change 5).

## Fuera de alcance
Declarar v1.0 o congelar contratos; migraciones nuevas; modificar CLIs, exit codes o schemas existentes (si el inventario halla una inconsistencia se documenta); instalar la primitiva de deprecación en proyectos; cambios de versión de producto.

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
- tools/harmessi/deprecation.py
- tools/harmessi/tests/test_deprecation.py
- tools/tests/test_v013_contract_inventory.py
- tools/tests/test_v013_compat_window.py
- tools/tests/fixtures/compat/**
- ARCHITECTURE.md
- README.md
- docs/roadmap/v0.13.md
- openspec/changes/20261021-v013-contract-inventory-compat/**
