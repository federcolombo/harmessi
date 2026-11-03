# Tareas — 20260916-kdd-enforceable-checks

estado: en_progreso

## Invocaciones planificadas
- `python-data-engineer` (1 sesión): implementa las 6 subetapas + tests + manifest + methodology.md,
  según `design.md`/`spec.md`.
- `data-science-reviewer` (1 sesión, solo lectura): revisa el diff completo contra `spec.md`/
  `design.md` y las prohibiciones del brief (falsa validez científica, heurísticas disfrazadas,
  duplicación de pathguard/readiness/status, scope creep).
- `python-data-engineer` (fixes, hasta 2 ciclos): corrige BLOCKER/IMPORTANT del reviewer.
- Lead: corre la suite de tests real vía Bash (ningún subagente ejecuta código), verifica
  read-only/manifest parity/doctor, escribe el reporte final.

## Tareas
- [ ] `tools/dsguard/scientific_validity.py`: modelo + policy + 7 checks (`SCI-CUTOFF`,
      `SCI-HOLDOUT-PROTECTION`, `SCI-HOLDOUT-USAGE`, `SCI-LEAKAGE-TARGET`, `SCI-LEAKAGE-FORBIDDEN`,
      `SCI-LEAKAGE-SPLIT`, `SCI-BASELINE`) + orquestador `evaluar_scientific_checks`.
- [ ] `tools/dsguard/status.py`: sección `science`.
- [ ] `tools/ds_guard.py`: `science status [--json]`.
- [ ] `tools/ds_init/manifest.py`: entrada VERBATIM.
- [ ] `.claude/skills/lead-data-scientist/methodology.md` + `.tmpl`: sección nueva mínima.
- [ ] `tools/tests/test_scientific_validity.py`: tests mínimos completos (ver `spec.md` criterios).
- [ ] `tools/tests/test_status.py`: sección `science` presente.
- [ ] `tools/tests/test_manifest_dsguard_parity.py`: clase de paridad nueva.
- [ ] Regresión: `tools/tests`, `tools/ds_init/tests`, `tools/ds_profile/tests`,
      `tools/harmessi/tests`, `check_manifest_parity`, `harmessi doctor`.

## Dependencias
Ninguna externa. Reusa `checks.py`/`pathguard.py`/`repo.py`/`core.py`/`lifecycle.py` tal cual, sin
modificarlos.

## Próximo paso exacto
N/A (no pausada).
