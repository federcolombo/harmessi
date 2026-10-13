# Tareas — 20261009-approval-trust-human-presence

estado: cerrada

## Invocaciones planificadas
- Lead: coordina, gobierna y hace la revisión de consistencia; NO escribe archivos de implementación.
- Instancias de `python-data-engineer` con ownership DISJUNTO de archivos (declarado acá antes de lanzar):
  - Writer A: `tools/dsguard/human_presence.py` + `tools/tests/test_human_presence.py`.
  - Writer B: `tools/ds_guard.py` + `tools/tests/test_approval_channel_cli.py` + `tools/tests/test_ds_guard_exec_approve.py`.
  - Writer C: `tools/cards/approvals.py` + `tools/cards/tests/**`.
  - Writer D (al final; único dueño de docs y boundaries): `tools/tests/test_architecture_boundaries.py`, `ARCHITECTURE.md`,
    `docs/roadmap/v0.10.md`, `.claude/skills/lead-data-scientist/sdd.md`.
  - Regla: un writer que necesite un archivo ajeno no lo edita y lo devuelve al Lead. Nadie toca lifecycle, `estado:` ni
    `control.json`.
- Reviewer `data-science-reviewer`: máximo 2 ciclos, después de los tests dirigidos. Foco:
  - Ningún camino trivial (flags, pipe, archivo, variable de entorno) produce T1.
  - `isatty()` no es prueba suficiente.
  - Sin fallback T1 a T0 (fail-closed).
  - Challenge ligado a artefacto, hash y acción; sin replay.
  - ApprovalRef no inventa tier.
  - Compatibilidad histórica (ausencia de `approval_channel` = `declared`).
  - Sin acople a provider (solo stdlib).
  - Privacidad del registro (sin challenge, respuesta, datos de terminal ni usuario del SO).
  - Los claims de seguridad en código y docs coinciden con la garantía real (presencia, no identidad).
- Regresión relevante (UNA, al final): approvals SDD, exec approvals, ApprovalRef/Cards approvals, checkpoints `@approved`, autonomy
  approval refs, architecture boundaries y los tests nuevos. NO regresión completa, NO `ds_profile`, NO hashing managed, NO model
  governance completa.
- Nombre del canal: `console_confirmed` (`channel_version` `console/v1`); sin aliases ni compatibilidad con `tty_confirmed`.

## Tareas
- [x] T0 — Aprobación humana del SDD por hash y decisión material (hecha, 2026-10-13: opción B, `console_confirmed`).
- [x] T1 — Primitive `human_presence.py` + tests (Writer A).
- [x] T2 — Integración en `approve` y `exec approve` con helper único de registro + tests (Writer B).
- [x] T3 — Exposición de solo lectura del canal en Cards + tests (Writer C).
- [x] T4 — Reviewer `data-science-reviewer` (máx. 2 ciclos) y fixes.
- [x] T5 — Docs/boundaries (Writer D) y una regresión relevante.
- [x] T6 — ACEPTACIÓN MANUAL HUMANA (obligatoria antes del cierre; ver abajo).
- [x] T7 — Verificación y cierre (solo tras T6).

### T6 — Aceptación manual humana
El agente NO puede autoejecutarla ni registrar una T1 a nombre del usuario. El Change NO se cierra ni se commitea hasta que el humano la
ejecute y confirme el resultado.

1. Preparación (desde la raíz del repo, en la terminal REAL del usuario, PowerShell). Crear un Change temporal descartable:
   ```powershell
   python tools/ds_guard.py init --change-id 20261013-acept-t1-descartable --modo abreviado
   ```
   Completar su `proposal.md` con contenido mínimo (cualquier texto) para tener un artefacto aprobable.
2. Positivo (debe funcionar):
   ```powershell
   python tools/ds_guard.py approve --change-id 20261013-acept-t1-descartable --artefacto proposal.md --usuario <nombre-sin-arroba> --fecha 2026-10-13 --alcance "aceptacion T1" --cita "prueba manual descartable" --channel console_confirmed
   ```
   Resultado esperado: Harmessi muestra un challenge, el usuario lo escribe en esa misma consola, la aprobación se registra y la entrada
   de `aprobaciones[]` del Change temporal incluye `approval_channel: console_confirmed`, `confirmed_at` y `channel_version: console/v1`
   (y nada del challenge ni de la respuesta).
3. Negativo desde el agente/subproceso: pedir al agente que ejecute el mismo comando desde su herramienta Bash, desde PowerShell del
   agente y vía el atajo `!` del provider, sobre el mismo Change temporal. Resultado esperado: falla cerrado (error explícito, sin
   registrar entrada `console_confirmed`, sin degradar a `declared`). Si el atajo `!` produjera T1, registrarlo como hallazgo (no se
   asume T1 por el atajo).
4. Compatibilidad: `ds_guard approve` sin `--channel` sigue registrando `declared` (sin campo `approval_channel`).
5. Cleanup: borrar `openspec/changes/20261013-acept-t1-descartable/` y su entrada en `.ds_init/control.json`/`control` del Change según
   el procedimiento vigente, y confirmar con `git status` que no queda rastro del Change temporal.
6. Verificar en un host POSIX (si el autor dispone de uno) los chequeos de `/dev/tty`; de lo contrario, dejar la limitación registrada
   en la verificación.

## Dependencias
Change 1 cerrado. T1 depende de T0 (hecha). T2 y T3 dependen de T1. T4 depende de T2 y T3. T5 depende de T4. T6 depende de T5. T7
depende de T6.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->
Lanzar Writer A (T1) con ownership disjunto; la aceptación manual T6 queda reservada al humano.
