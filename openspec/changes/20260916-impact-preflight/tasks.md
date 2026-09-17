# Tareas — 20260916-impact-preflight

estado: en_progreso

## Invocaciones planificadas
- `python-data-engineer` (1 sesión, con reanudaciones por turn-limit si hace falta): implementa
  `tools/dsimpact/*` + wrapper en `ds_guard.py` + manifest + methodology.md + tests, según
  `design.md`/`spec.md`.
- `data-science-reviewer` (1 sesión, solo lectura): revisa contra `spec.md`/`design.md` y las
  prohibiciones del brief (falsos "broken", ruido de tokens genéricos, duplicados, parsing frágil
  de notebooks, paths absolutos, side effects, dependencia nueva, análisis semántico disfrazado,
  duplicación de Git utilities, scope creep hacia Change 2).
- `python-data-engineer` (fixes, hasta 2 ciclos): corrige BLOCKER/IMPORTANT.
- Lead: corre la suite real vía Bash, verifica read-only/manifest parity/doctor/scratch install
  experiment, escribe el reporte final.

## Tareas
- [ ] `tools/dsimpact/__init__.py`, `__main__.py`, `cli.py`.
- [ ] `tools/dsimpact/git_source.py` (R1).
- [ ] `tools/dsimpact/py_changes.py` (R2/R3/R4).
- [ ] `tools/dsimpact/consumers_py.py` (R5/R6).
- [ ] `tools/dsimpact/notebooks_source.py` (R8).
- [ ] `tools/dsimpact/generic_filter.py` (R7).
- [ ] `tools/dsimpact/scan.py` (orquestador: dedup/orden, R9/R10).
- [ ] `tools/ds_guard.py`: subcomando `impact scan`, import perezoso (R12/design.md §4).
- [ ] `tools/ds_init/manifest.py`: entradas VERBATIM `stage_minimo="experiment"`.
- [ ] `.claude/skills/lead-data-scientist/methodology.md` + `.tmpl`: sección nueva mínima.
- [ ] `tools/dsimpact/tests/*`: tests mínimos completos (ver `spec.md` criterios de aceptación).
- [ ] `tools/tests/test_manifest_dsguard_parity.py`: clase de paridad nueva (si aplica al patrón
      de import perezoso -- ajustar el test de paridad de imports directos si hace falta, sin
      romper su intención original).
- [ ] Regresión: `tools/tests`, `tools/ds_init/tests`, `tools/harmessi/tests`,
      `check_manifest_parity`, `harmessi doctor`, scratch install `experiment`.

## Dependencias
Ninguna externa. Reusa `dsguard.repo`/`dsguard.notebooks` tal cual, sin modificarlos (salvo
`ds_guard.py`/`manifest.py`, que sí se tocan para la integración).

## Próximo paso exacto
N/A (no pausada).
