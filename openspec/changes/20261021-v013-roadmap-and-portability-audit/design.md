# Diseño — 20261021-v013-roadmap-and-portability-audit

## Método
Lectura de `main`: `harmessi_bench`, `providers`, `datasources`, `dsimpact/git_source.py`, `dsguard/skill_contract.py`, `dsguard/repo.py`, roadmaps v0.12/v1.0, README de roadmaps.

## Decisiones
- **D1 — Extender `harmessi_bench`.** Sin paquete paralelo.
- **D2 — Lectura retrocompatible.** Casos/resultados sin versión se leen como versión 0; lo nuevo se escribe versionado.
- **D3 — Veredicto conservador.** Ante duda `inconclusive`; sin LLM-as-judge.
- **D4 — Sección `## Skills cargados` duplicada.** Hallazgo de validación; sin fusión automática.
- **D5 — CI.** Workflow de smoke; regresión completa local/de release; ejecución remota no afirmada si no se observa.

## No se reabre
Role ≠ Skill ≠ Runtime, un rol writer, Lead no writer, T0/T1, amendments, Harness Surfaces, recovery/upgrade de v0.11.

## Decisiones materiales pendientes
Ninguna.
