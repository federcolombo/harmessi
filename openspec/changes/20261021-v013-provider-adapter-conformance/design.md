# Diseño — 20261021-v013-provider-adapter-conformance

## Principio
Declarar soporte solo cuando está verificado. La conformance es una función pura que devuelve un reporte; los dobles de `subprocess`/`which` se inyectan con `unittest.mock.patch`, así que no se toca el contrato de los adapters.

## Providers
- Los adapters importan `shutil` y `subprocess` como módulos: parchear `shutil.which` y `subprocess.run` globalmente durante cada chequeo es suficiente y no requiere refactor.
- Tres niveles, derivados de evidencia: contrato (siempre posible), smoke local (`detect()` real) y live (opt-in doble: flag + variable de entorno). El reporte nunca sube de nivel por documentación.
- `SOPORTE_DECLARADO` es una tabla chica en código con una `evidencia` textual; un test la ancla a `PROVIDER_REGISTRY`.
- Sin matriz compleja: tres niveles, un registro.

## Observers
- Vive junto al contrato (`tools/datasources/`), se instala en el proyecto (los proyectos pueden escribir observers propios) y es solo-stdlib sobre `core` (+ `scan` para secretos).
- Evidencia `real` vs `fixture` la declara quien llama, y el reporte la propaga. El smoke real usa el observer de archivos locales sobre datos sintéticos; sin `ds_profile`, skip.
- Reproducibilidad se mide con `content_sha256` (excluye `generated_at`).
- El chequeo de «no instala nada» es estático (AST de imports a nivel de módulo): barato, honesto, y documentado como no exhaustivo.

## Riesgos
- La conformance de providers verifica la forma contra dobles; no garantiza el comportamiento de la CLI real (por eso existen smoke/live y los niveles).
- El chequeo de secretos es heurístico.

## No se reabre
Contrato de `ProviderAdapter`, `SourceObservation`, `SourceCapabilities`, política de autonomía, T0/T1.

## Decisiones materiales pendientes
Ninguna.
