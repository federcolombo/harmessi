# Diseño — 20261021-v012-release-hardening

- Réplica del release train de v0.11 Change 6. El writer solo toca docs/versión/smoke/tests; el Lead ejecuta regresión, instala, hace dogfooding y regenera `.ds_init/control.json` una sola vez al final del código.
- Dogfooding con script reproducible (fuera del repo, en el scratchpad) sobre directorios temporales; los resultados cualitativos se resumen en verification.md.
- Memoria acotada: P=1, foreground, batches por módulo; OOM ⇒ reducir granularidad, no repetir igual.
## Decisiones materiales pendientes
Ninguna.
