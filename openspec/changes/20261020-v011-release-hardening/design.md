# Diseño — 20261020-v011-release-hardening

- **D1** Sin features: todo cambio de código es corrección técnica mínima revelada por la regresión o el dogfooding, documentada en verification.
- **D2** Regresión por batches seriales por directorio de tests (tools/tests, dsguard, ds_init/tests, harmessi/tests, cards, ds_profile, reporting, datacontracts, datasources, etc.), cada batch en una invocación, exit code y conteos registrados; los batches que excedan 10 min se parten por módulo.
- **D3** Comparación contra baseline: worktree temporal del tag `v0.10.0`, sólo para fallas dudosas, módulo por módulo.
- **D4** Dogfooding en directorios temporales fuera del repo; el proyecto B se instala ejecutando `ds_init` desde un checkout del tag `v0.10.0` (worktree/archive en directorio temporal), luego se actualiza con el `ds_init` actual.
- **D5** La publicación es el último paso y se condiciona a verificación de remoto y tag.
