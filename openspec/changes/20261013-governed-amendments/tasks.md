# Tareas — 20261013-governed-amendments

estado: cerrada

## Invocaciones planificadas
- Lead: coordina, gobierna y hace la revisión de consistencia; NO escribe archivos de implementación.
- Instancias de `python-data-engineer` con ownership DISJUNTO de archivos (declarado acá antes de lanzar):
  - Writer A: `tools/dsguard/scope_amendments.py` + `tools/tests/test_scope_amendments.py`.
  - Writer B: `tools/dsguard/guardrails_adoption.py` + `tools/tests/test_guardrails_readopt.py`.
  - Writer C: `tools/dsguard/scope.py` + `tools/dsguard/pathguard.py` + `tools/tests/test_scope.py` + `tools/tests/test_pathguard.py`.
  - Writer D: `tools/ds_guard.py` (subcomandos `scope amend|show`, `guardrails readopt`, rechazo de re-aprobación, consumidores).
  - Writer E: `tools/harmessi/doctor.py` + `tools/harmessi/tests/test_doctor_guardrails.py`.
  - Writer F (al final; único dueño de docs y boundaries): `tools/tests/test_architecture_boundaries.py`, `ARCHITECTURE.md`,
    `docs/roadmap/v0.10.md`, `.claude/skills/lead-data-scientist/sdd.md`.
  - Regla: un writer que necesite un archivo ajeno no lo edita y lo devuelve al Lead. Nadie toca lifecycle, `estado:` ni
    `control.json`.
- Reviewer `data-science-reviewer`: máximo 2 ciclos, después de los tests dirigidos. Foco:
  - El agente no auto-amplía scope ni auto-readopta.
  - T0 nunca alcanza; sin consola de control soportada, fail-closed sin degradar.
  - T1 ligada al diff exacto (operación, target, estado antes/después, Change/proyecto); sin replay ni token persistente.
  - Closed list exacta de cuatro campos; `sealed_sources` solo ADD; diff mixto o inelegible se rechaza por completo.
  - Sin aplicación parcial; atomicidad en el orden aprobado (recalcular, concurrencia, T1, releer, temporal validado, `os.replace`).
  - Sin generic baseline accept (`accept-current-state`/`adopt-all`); `sync` no adopta ni enmienda.
  - La caché de `control.json` no supera a la cadena; divergencia reconstruye desde la cadena y emite `ALCANCE-CACHE-DIVERGENTE`.
  - Cadena alterada = fail-closed en consumidores y en Doctor.
  - `proposal.md` con enmiendas efectivas no se re-aprueba (exit 2).
  - Pathguard protege los registros sin romper el CLI gobernado (lectura, validate, dry-run y escritura interna siguen funcionando).
- Regresión relevante (UNA, al final): scope, enforcement de scope en `exec`, pathguard/`hook_rutas`, rutas Unicode, approvals/T1,
  drift semántico de guardrails, Doctor guardrails, interacción con managed hashing, `sync` relevante, architecture boundaries,
  approvals SDD y tests nuevos. NO regresión completa, NO Cards/governance completas, NO `ds_profile`, NO Domain Modeling.

## Tareas
- [x] T0 — Aprobación humana del SDD y de las decisiones materiales M1-M4 (hecha, 2026-10-13: M1-M4 resueltas en SÍ).
- [x] T1 — `scope_amendments.py` + tests (Writer A).
- [x] T2 — `guardrails_adoption.py` + tests (Writer B).
- [x] T3 — `scope.alcance_efectivo`, hallazgo y pathguard + tests (Writer C).
- [x] T4 — Subcomandos y rechazo de re-aprobar `proposal.md` con enmiendas en `ds_guard.py` (Writer D).
- [x] T5 — Doctor: drift de guardrails con adopciones + tests (Writer E).
- [x] T6 — Reviewer `data-science-reviewer` (máx. 2 ciclos) y fixes.
- [x] T7 — Docs/boundaries (Writer F) y una regresión relevante.
- [x] T8 — ACEPTACIÓN MANUAL HUMANA de ambas operaciones con T1 real (ver abajo).
- [x] T9 — Verificación y cierre (solo tras T8).

### T8 — Aceptación manual humana
El agente NO puede autoejecutarla ni registrar una T1 a nombre del usuario. El Change NO se cierra ni se commitea hasta que el humano
la ejecute y confirme el resultado de AMBAS operaciones (scope amendment y guardrails readopt), en la PowerShell real del usuario,
sobre repos/Changes temporales descartables, con cleanup:

1. Enmienda de scope: `ds_guard scope amend` con `--add`/`--remove` sobre un Change temporal aprobado; verificar `--dry-run` sin T1,
   ejecución real con challenge T1, línea nueva en `amendments.jsonl` y `scope show` coherente.
2. Negativo desde el agente/subproceso (Bash, PowerShell del agente, atajo `!`): debe fallar cerrado, sin registro y sin degradar.
3. Re-adopción: agregar a mano una entrada en una clave elegible de un `guardrails.json` temporal, correr
   `ds_guard guardrails readopt` (dry-run, luego real con T1), verificar `guardrails-adoptions.jsonl` y que Doctor deja de reportar drift
   para esa clave. Probar un diff inelegible (por ejemplo `excepciones`): debe rechazarse por completo.
4. Cleanup: eliminar el Change/proyecto temporal y confirmar con `git status` que no queda rastro.

## Dependencias
Change 2 cerrado (provee `human_presence`). T0 hecha. T1, T2 y T3 dependen de T0. T4 depende de T1, T2 y T3. T5 depende de T2. T6 depende de T4 y
T5. T7 depende de T6. T8 depende de T7. T9 depende de T8.

## Próximo paso exacto
Lanzar Writers A, B y C (T1-T3) con ownership disjunto; la aceptación manual T8 queda reservada al humano.
