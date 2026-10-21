# Propuesta — 20261021-v013-provider-adapter-conformance

> Change 3 de v0.13: Provider & Adapter Conformance. Dos conceptos separados: A. providers de modelo (`tools/providers`); B. adapters/observers de fuente (`tools/datasources`).

## Problema
Los 4 adapters de provider (`claude_code`, `codex`, `gemini`, `grok`) solo tienen tests de interfaz y de ausencia de CLI; los de `codex`, `gemini` y `grok` nunca se verificaron contra la CLI real
(lo declaran sus docstrings) y no existe un lugar que diga qué nivel de soporte tiene cada uno. Los observers de fuente tienen contrato (`factory(source_id, options)` → `.capabilities()`/`.observe(request)`)
y `SourceObservation` versionado, pero no hay una suite reutilizable que un autor de observer (Harmessi o un proyecto) pueda correr para saber si cumple el contrato.

## Objetivo
- **A.** Interfaz mínima de conformance de providers, sin credenciales, y una declaración honesta de niveles de soporte (`contract-tested` / `locally-smoke-tested` / `live-validated`); live opt-in y nunca declarado sin evidencia.
- **B.** Suite reusable de conformance de observers con fixtures, que registre qué evidencia fue real y qué fue fixture.

## Evidencia
- `tools/providers/core.py` (`ProviderAdapter`, `ProviderInfo`, `InvocationRequest/Result`, `classify_availability_error`), `claude_code.py`/`codex.py`/`gemini.py`/`grok.py` (usan `shutil.which` y `subprocess.run`), tests existentes `test_adapters.py`, `test_contract_parity.py`.
- `tools/datasources/core.py` (`SourceObservation`, `SCHEMA_VERSION = 1`, `SourceCapabilities`, `validate_capabilities`, `CODES`), `runtime.py`, `file_observer.py`, `scan.py` (detección de secretos).
- `tools/datasources` se instala en proyectos (MANIFEST); `tools/providers` es solo-checkout.

## Supuestos descartados
- Que hubiera una matriz de soporte de providers: no existe; no se inventa una compleja (tres niveles).
- Llamadas pagas o con credenciales como requisito: no; live es opt-in explícito.
- Adapters que requieran credenciales privadas para validarse: se valida contrato con fixtures y se hace smoke real solo con el observer de archivos locales sobre datos sintéticos.

## Alcance
- `tools/providers/conformance.py` (nuevo): `verificar_conformidad(adapter, ...)` con chequeos sin credenciales (forma, detección con CLI ausente simulada, parseo de versión, contrato de invocación contra un `subprocess` falso, clasificación de fallas y timeouts, forma de configuración) y `SOPORTE_DECLARADO` (provider → nivel + evidencia). Smoke local opcional (`detect()` real) y live opt-in (variable `HARMESSI_LIVE_PROVIDER` + flag explícito).
- `tools/datasources/conformance.py` (nuevo, instalado): `verificar_observer(factory, ...)` con chequeos de forma, capacidades válidas, observación que parsea como `SourceObservation` con `source_id` correcto, faceta no soportada no fabricada, `source_id` inválido rechazado, sin fuga de secretos/rutas absolutas, reproducibilidad (`content_sha256`), módulo sin instalación automática (AST), y `CheckResult`/reporte con `evidencia` real|fixture.
- Registro en MANIFEST (`tools/datasources/conformance.py`) y listas de arquitectura/neutralidad.
- Fixtures: observer conformante, observer inválido (varios modos) y provider falso conformante/no conformante.
- Smoke real: `FileObserver` sobre un CSV sintético temporal; `detect()` real de los providers presentes en el host.
- Docs: ARCHITECTURE.md, README.md, roadmap (niveles y evidencia real vs fixture).

## Fuera de alcance
Llamadas live por defecto; credenciales; T2 de seguridad de providers; nuevos providers o adapters; cambios en el contrato de `SourceObservation` o de `ProviderAdapter`; portabilidad/CI (Change 4); versión de producto.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- tools/providers/conformance.py
- tools/providers/__init__.py
- tools/providers/tests/*.py
- tools/datasources/conformance.py
- tools/datasources/__init__.py
- tools/datasources/tests/*.py
- tools/ds_init/manifest.py
- tools/ds_init/tests/test_manifest.py
- tools/tests/test_architecture_boundaries.py
- tools/tests/test_v08_datasources_neutrality.py
- tools/tests/test_v013_conformance_smoke.py
- ARCHITECTURE.md
- README.md
- docs/roadmap/v0.13.md
- openspec/changes/20261021-v013-provider-adapter-conformance/**
