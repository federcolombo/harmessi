# Tareas — 20261014-composable-skills-writer-semantics

estado: cerrada

## Invocaciones planificadas
- Lead: coordina, gobierna, valida y hace la revisión de consistencia; NO escribe archivos de implementación. Ejecuta git y `ds_guard`.
- Instancias de `python-data-engineer` con ownership DISJUNTO (ver `## Ownership de writers`; plan propuesto, declarado antes de lanzar y no vigente hasta T0).
- Reviewer `data-science-reviewer`: máximo 2 ciclos, después de los tests dirigidos. Foco: skills sin autoridad (sin permisos/hooks/instalación); contrato cerrado de frontmatter; ownership ⊆ scope y disjunto; sin hook por instancia; el Lead no escribe implementación; writers no tocan `estado:`; `SDD-ESTADO-DIVERGENTE` sin falsos positivos históricos; continuación ≠ reintento ≠ ronda ≠ ciclo; default de `--max-continuaciones` = 1; `maxTurns` y 90 min intactos; neutralidad de proveedor; TDD-DS breve; sin `domain-modeling`/`GLOSSARY.md`/skill `tdd`. Las continuaciones técnicas NO cuentan como ciclos de reviewer.
- Metodólogo: no se convoca (no hay decisión de ML/target/leakage).
- Regresión relevante (UNA, al final): tests nuevos, `test_skill_methodology`, `test_architecture_boundaries`, manifest/paridad, scope/approvals/session/hook_presupuesto, Doctor skills, ds_guard CLI relevante. NO regresión completa, NO Cards/governance, NO `ds_profile`, NO Domain Modeling.

## Ownership de writers
Plan propuesto (formato de R10). Olas: 1 → 2 → 3 → 4. Dentro de una ola, las instancias son concurrentes solo si el Lead lo decide (default serial).

### W1 — python-data-engineer — T1
- tools/dsguard/skill_contract.py
- tools/tests/test_skill_contract.py

### W2 — python-data-engineer — T2
- tools/dsguard/ownership.py
- tools/tests/test_ownership.py

### W3 — python-data-engineer — T3
- tools/dsguard/sdd.py
- tools/tests/test_sdd_estado_divergente.py

### W4 — python-data-engineer — T4
- tools/ds_guard.py
- tools/tests/test_ds_guard_ownership_cli.py

### W5 — python-data-engineer — T5
- tools/harmessi/doctor.py
- tools/harmessi/tests/test_doctor_skill_contract.py
- tools/ds_init/manifest.py
- tools/ds_init/tests/test_manifest.py
- tools/ds_init/tests/test_manifest_dsguard_parity.py

### W6 — python-data-engineer — T6
- .claude/skills/lead-data-scientist/SKILL.md
- .claude/skills/lead-data-scientist/methodology.md
- .claude/skills/lead-data-scientist/templates/skill.md
- tools/ds_init/profiles/python_jupyter_data/templates/SKILL_lead_data_scientist.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/methodology.md.tmpl

### W7 — python-data-engineer — T7
- .claude/skills/lead-data-scientist/sdd.md
- .claude/skills/lead-data-scientist/verificador.md
- .claude/skills/lead-data-scientist/templates/tasks.md
- tools/ds_init/profiles/python_jupyter_data/templates/sdd.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/verificador.md.tmpl
- .claude/agents/python-data-engineer.md
- .claude/agents/data-science-reviewer.md
- .claude/agents/metodologo.md
- tools/ds_init/profiles/python_jupyter_data/templates/agent_python_data_engineer.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/agent_data_science_reviewer.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/agent_metodologo.md.tmpl

### W8 — python-data-engineer — T8b (condicional a payload real; archivo self-governing: exclusivo y serial, R22)
- tools/dsguard/hook_presupuesto.py
- tools/tests/test_operational_session_recovery.py

### W9 — python-data-engineer — T9 (última; dueño único de docs transversales y boundaries)
- ARCHITECTURE.md
- docs/roadmap/v0.10.md
- tools/tests/test_skill_methodology.py
- tools/tests/test_architecture_boundaries.py

Regla: un writer que necesite un archivo ajeno no lo edita y lo devuelve al Lead. Nadie toca lifecycle, `estado:` ni `control.json`.

## Historial de ownership
- 2026-10-14 — `templates/skill.md` pasó de W6 a W5 (creado junto con el manifest y Doctor).
- 2026-10-14 — la documentación del plan W6/W7 se ejecutó con 5 instancias de writer disjuntas por archivo (methodology+tmpl; SKILL.md+tmpl; sdd.md+tmpl+templates/tasks.md; verificador+tmpl; agentes md+tmpl).
- 2026-10-14 — W9 se dividió: tests de contenido/boundaries (instancia aparte) y ARCHITECTURE/roadmap (otra).
- 2026-10-14 — los fixes de los ciclos de reviewer los aplicaron las mismas instancias dueñas de cada archivo (continuación de la misma instancia).

## Skills cargados
<!-- vacío: este Change no carga ninguna skill componible (ninguna existe todavía) -->

## Tareas
- [x] T0 — Aprobación humana del SDD y resolución de M1–M7 (HECHA 2026-10-14; registrada con `ds_guard approve`).
- [x] T1 — `skill_contract.py` + tests (W1). Ola 1.
- [x] T2 — `ownership.py` + tests (W2). Ola 1.
- [x] T3 — `SDD-ESTADO-DIVERGENTE` en `sdd.py` + tests (W3). Ola 1.
- [x] T4 — `ds_guard`: `ownership check`, integración en `validate` (ownership, divergencia, referencias a skills), `session start --max-continuaciones`, mostrar el tope en `session status` (W4). Ola 2; depende de T1, T2, T3.
- [x] T5 — Doctor `HARMESSI-SKILL-CONTRATO`, manifest (plantilla `skill.md` y módulos nuevos) y tests de paridad (W5). Ola 2; depende de T1.
- [x] T6 — Docs del lado skill (W6): taxonomía, contrato, carga/composición/precedencia, §14 reescrita (rol vs instancia), guideline TDD-DS, evals ≠ tests, plantilla `skill.md`. Ola 3.
- [x] T7 — Docs del lado proceso (W7): ownership en `sdd.md`/plantilla de `tasks.md`, vocabulario de continuaciones, contrato de reanudación, `ESTADO-AGENTE`, bloque de turnos en agentes, sesión/recovery en `verificador.md`, emergencias y self-governing. Ola 3.
- [x] T8a (omitida: sin payload real) — Solo si el runtime normal produce de forma natural y segura un payload real de Agent/SendMessage durante este Change, usarlo como evidencia de H1. NO se pide captura manual ni se intercepta nada. Sin payload: omitir T8b y registrar H1 como deuda verificada solo con tests sintéticos.
- [ ] T8b (omitida; condicional a T8a) — Corrección condicional del hook (W8) (condicional; probable omisión). Solo con T8a; exclusivo y serial; smoke del Lead antes de cualquier otra escritura.
- [x] T9 — Reviewer (máx. 2 ciclos) y fixes; luego docs transversales, boundaries y UNA regresión relevante (W9).
- [x] T10 — Verificación (`verification.md`) y cierre. Sin push. Change 5 no se abre.

## Dependencias
T0 antes de todo. T4 depende de T1, T2, T3. T5 depende de T1. T6 y T7 dependen de T1–T3 (contenido). T8b depende de T8a. T9 depende de T4–T7 (y T8b si existe). T10 depende de T9. Concurrencia: ver `## Ownership de writers`; las olas 1 y 3 son candidatas a concurrente por ownership naturalmente disjunto; la ola 2 y W8 se evalúan al momento.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->

## Verificación
Detalle completo en `verification.md`.
- Regresión relevante (35 módulos): 1218 tests OK (skipped=8); 6 módulos afectados tras fixes del ciclo 2: 168 OK.
- `ds_guard validate` y `ds_guard ownership check` de este Change: sin hallazgos; censo `SDD-ESTADO-DIVERGENTE`: 0 divergencias históricas.
- Reviewer: 2 ciclos (0 bloqueantes, I1–I3 resueltos) + 1 continuación técnica; H1 UNCONFIRMED, T8a/T8b omitidas.
- Resultado: cumple M1–M7 y la spec; listo para Change 5; sin push.
