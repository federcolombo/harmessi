# Propuesta — 20261021-v013-roadmap-and-portability-audit

> Change 0 de v0.13 («Portability, Evaluation & Contract Hardening»): auditoría de portabilidad/evaluación y congelamiento de roadmap. Solo docs/SDD: NO implementa nada.

## Problema
Para llegar a contratos públicos estables (v1.0) y habilitar la mejora basada en evidencia (v0.14) faltan primitivas de evaluación reproducible, conformance
de providers/adapters, endurecimiento de portabilidad e inventario de contratos. Sin auditar lo existente (`harmessi_bench`, providers, datasources) se arriesga duplicarlo.

## Objetivo
Auditar contra `main` (`95f3cde`), confirmar qué existe/está parcial/sigue vivo y congelar un roadmap v0.13 mínimo, ordenado y con boundaries.

## Evidencia
- `tools/harmessi_bench/{core,runner,storage,compare,scenarios,cli}.py`: framework de evals de v0.5 (scorers deterministas, `result.json`, `compare_runs`); sin versionado, suites, veredicto ni run manifest.
- `tools/providers/core.py` y adapters; `tools/datasources/core.py` (`SourceObservation`, `SCHEMA_VERSION = 1`).
- `tools/dsimpact/git_source.py` `contenido_before`/`contenido_after`: `None` ante cualquier fallo de `git show`.
- `tools/dsguard/skill_contract.py` `referencias_skills_cargados`: solo lee la primera sección `## Skills cargados`.
- No existe `.github/`; `gh` no está instalado.
- `docs/roadmap/v1.0.md`, `v0.12.md`, `docs/releases/v0.12.0.md`.

## Supuestos descartados
- Que hiciera falta un paquete de evals nuevo: `harmessi_bench` existe y se extiende.
- Que existiera CI: no hay workflow.
- Que los providers estuvieran verificados por nivel: no hay niveles declarados.

## Alcance
`docs/roadmap/v0.13.md`, línea v0.13 en `docs/roadmap/README.md` y este SDD. Changes 1–6 con objetivo, scope, boundaries y decisiones D1–D5.

## Fuera de alcance
Implementar Changes 1–6; tocar `tools/**`, hooks, templates, manifest; versión, tag, push.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- docs/roadmap/v0.13.md
- docs/roadmap/README.md
- openspec/changes/20261021-v013-roadmap-and-portability-audit/**
