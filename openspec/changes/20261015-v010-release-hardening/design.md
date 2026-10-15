# Diseño — 20261015-v010-release-hardening
- Orden: contenido final (versión, notas, README, roadmap, tests) → `migrate-hashes --execute` si procede y regeneración del baseline (último cambio de contenido) → smoke dirigido → regresión completa → Doctor → commits → fetch → fast-forward de main → tag → push.
- Regeneración del baseline: se usa `ds_init.control.regenerar_control` sobre el repo (mismo mecanismo que «Refresh release control» de v0.9), tras comprobar que cada archivo en drift figura en `git diff v0.9.0..HEAD` (cambio legítimo, no adopción silenciosa). Se documenta la lista en verification.md.
- Correctivos: cualquier bug de estabilización hallado por la regresión se corrige dentro de este Change (scope amplio `tools/**`, `docs/**`, `.claude/skills|agents/**`) con un writer de ownership explícito; sin Change 7 salvo alteración semántica material.
- Notas de release: inglés; se redactan después de los hechos (conteos de tests y Doctor se citan solo si salen de la corrida).
- Riesgos: la regresión completa tarda (~30–60 min en Windows); `gh` puede no existir; `origin/main` puede haber avanzado.
