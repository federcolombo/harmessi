# Tareas — 20260916-scope-and-change-isolation

estado: en_progreso

## Invocaciones planificadas
- `python-data-engineer` (1 sesión): `scope.py` + consolidación en `sdd.py`/`ds_guard.py` + docs +
  tests + manifest.
- `data-science-reviewer` (1 sesión, solo lectura).
- `python-data-engineer` (fixes, hasta 2 ciclos).
- Lead: tests reales, manifest parity, doctor, commit local.

## Tareas
- [ ] `tools/dsguard/scope.py` nuevo.
- [ ] `tools/dsguard/sdd.py::gate_cierre` consolidado.
- [ ] `tools/ds_guard.py::cmd_validate` consolidado.
- [ ] `.claude/skills/lead-data-scientist/verificador.md` + `.tmpl` actualizados (idénticos).
- [ ] `tools/ds_init/manifest.py`: entrada VERBATIM para `scope.py`, stage discovery (default, sin
      override -- mismo criterio que `sdd.py`/`repo.py`, SDD/validate son core).
- [ ] Tests nuevos + regresión existente de `ALCANCE-RUTA`/`files_out_of_scope`.
- [ ] Regresión completa + manifest parity + doctor.

## Dependencias
Ninguna externa. No toca `dsimpact`, `scientific_validity`, `readiness`, `lifecycle`.

## Próximo paso exacto
N/A.
