# Diseño — 20261007-v09-release-hardening

## Decisión metodológica/técnica
**D1 — Release hardening sin código funcional.** Solo metadata de versión, documentación, sanitización y un smoke. Cualquier bug pequeño y claramente
bloqueante hallado se corrige aquí; un problema que requiera diseño nuevo se reporta como STOP.
**D2 — Una fuente de versión.** `tools/ds_init/version.py` es canónica; `CITATION.cff` y `.ds_init/control.json` la reflejan (convención de `d0cbd1b`).
El smoke verifica la igualdad de las tres.
**D3 — Sanitización mínima.** Se reemplaza el nombre del archivo de feedback por una referencia genérica («informe de feedback externo, no versionado») y la ruta
de usuario por `<home>`. Editar propuestas históricas cambia su hash: aceptable porque son de Changes cerrados y no hay Cards ancladas a ellas.
**D4 — Smoke de release, no mega-fixture.** La matriz de instalación y los E2E de Cards ya existen; el smoke agrega solo invariantes de release (versión,
higiene, privacidad, dependencias, roadmap). Una corrida real de instalación en temporales se hace una vez como evidencia, sin test nuevo.
**D5 — Regeneración única de control.json** al final, después de todo cambio de archivos managed.
**D6 — Release notes en `docs/releases/v0.9.0.md`** (el repo no tenía convención de archivo; las notas de GitHub Release se derivan de este documento).

## Alternativas descartadas
Subir versiones internas de componentes; reescribir el historial de git; marcar v0.9 «publicada» antes del release humano; duplicar fixtures de instalación.

## Riesgos
Test de privacidad con falsos positivos: acotado por patrones concretos y exclusiones explícitas. Smoke dependiente de `git`: se omite si no hay repo.

## Aprobación humana
Ver proposal.md.
