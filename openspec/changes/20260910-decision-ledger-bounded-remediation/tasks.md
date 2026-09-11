# Tareas — 20260910-decision-ledger-bounded-remediation

estado: cerrada

## Invocaciones planificadas
- `python-data-engineer` (1ra, ya en curso): redactar borradores `proposal.md`/`spec.md`/
  `design.md`/`tasks.md` — esta misma invocación.
- `python-data-engineer` (2da, planificada): implementar `tools/dsguard/decision.py`, extender
  `tools/dsguard/sdd.py`, `tools/ds_guard.py`, `tools/dsguard/hook_presupuesto.py`, escribir
  `tools/tests/test_decision.py` y `tools/tests/test_remediation.py`, actualizar
  `.claude/skills/lead-data-scientist/{sdd.md,SKILL.md,verificador.md}` y crear
  `.claude/skills/lead-data-scientist/decision-ledger.md`.
- `data-science-reviewer` (planificada): revisar el diff de la implementación antes de ejecutar
  nada.
- `python-data-engineer` (planificada, corre siempre después del reviewer): corrige hallazgos si
  los hay (reinvocación correctiva, cuenta intento) y deja `estado: en_verificacion`.
- El Lead corre la suite de regresión (`tools/tests`, `tools/ds_init/tests`,
  `tools/harmessi/tests`, `check_manifest_parity`, `harmessi doctor`) vía Bash y trae el output.
- `python-data-engineer` (planificada, cierre): escribe `verification.md` con la evidencia real
  de los tests corridos.

## Tareas
- [x] Borradores SDD (`proposal.md`/`spec.md`/`design.md`/`tasks.md`).
- [x] `tools/dsguard/decision.py`: módulo nuevo (ledger de decisiones).
- [x] Extensión de `tools/dsguard/sdd.py`: `control["remediaciones"]`, ventanas, resolve, extend.
- [x] Extensión de `tools/ds_guard.py`: subcomandos `decision *`, `remediation {resolve,extend}`,
      flags nuevos en `session note`.
- [x] Extensión de `tools/dsguard/hook_presupuesto.py`: deniega `Agent` nuevo si
      `reintentos >= max_reintentos`.
- [x] `tools/tests/test_decision.py`.
- [x] `tools/tests/test_remediation.py`.
- [x] Documentación: `decision-ledger.md` nuevo; `sdd.md` §8, `SKILL.md`, `verificador.md`
      actualizados.
- [ ] Revisión de `data-science-reviewer` sobre el diff completo.
- [ ] Corrección de hallazgos (si los hay).
- [ ] Regresión completa de la suite (Lead, vía Bash).
- [ ] `verification.md` con evidencia real.

## Dependencias
Ninguna dependencia externa nueva — solo biblioteca estándar de Python, mismo criterio que el
resto de `tools/dsguard/`.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->
