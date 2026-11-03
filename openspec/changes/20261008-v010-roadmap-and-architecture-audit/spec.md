# Spec — 20261008-v010-roadmap-and-architecture-audit

Change 0 de v0.10: auditoría + congelamiento de roadmap. Solo documentación; ningún cambio en `tools/**`.
Las decisiones M1–M5 están aprobadas por el humano (2026-10-08; ver design.md). Los diseños de los Changes 1–5 siguen siendo diseño conceptual a refinar en el SDD de cada Change, con esas decisiones fijas.

## A. Roadmap (R1–R3)
**R1.** `docs/roadmap/v0.10.md` contiene: objetivo, principios, Changes 0–6 con criterios de aceptación, dependencias, deudas diferidas y boundaries.
**R2.** Conserva la historia útil y las claves exigidas por `tools/tests/test_v09_release_hardening_smoke.py::test_v010_preserva_deuda_viva`:
"approval origin", "line endings", "mid-change authorized scope amendment", "composable engineering", "domain-modeling", "one-writer".
**R3.** Documenta explícitamente toda decisión que cambie la hipótesis previa: (a) C+E fusionados en el Change 3 y no en el Change 1; (b) D fusionado con la
foundation de skills en el Change 4; (c) el sub-ítem de cardinalidad de `ds_profile` ya está resuelto (no se arrastra como deuda).
**R3b.** Roadmap aprobado: C0 audit; C1 Cross-platform Managed Hashing (solo A); C2 Approval Trust / T1 Human-Presence Semantics (independiente); C3 Governed Amendments (scope amendment + closed-list re-adoption); C4 Composable Skills Foundation + Writer Semantics; C5 Domain Modeling; C6 Release Hardening. Dependencias: 1→3, 2→3, 4→5, 1–5→6; 1 y 2 independientes.

## B. Arquitectura (R4–R5)
**R4.** `ARCHITECTURE.md` §7 congela SOLO: Role vs Skill vs Runtime, frontera domain-modeling, frontera trust/authenticity y principio de writer-concurrency.
**R5.** Sin otros cambios no aprobados en `ARCHITECTURE.md`; `tools/tests/test_architecture_boundaries.py` sigue verde.

## C. Alcance (R6–R7)
**R6.** Fuera de alcance explícito: implementación de los Changes 1–6, edición de `control.json`, cambios en `tools/**`, versión, nuevas dependencias. El alcance de rutas autorizado es el declarado en `proposal.md` (más `verification.md`, ruta por defecto).
**R7.** Los congelados de v0.9 (ApprovalRef, Cards, `STOP_CATALOG`, `approval_mode`, contratos de Cards/governance) quedan intactos.

## D. Privacidad (R8–R9)
**R8.** Sin datos, nombres de proyectos reales, rutas personales ni emails en los archivos del Change, del roadmap ni de ARCHITECTURE.
**R9.** `docs/feedback/` permanece fuera de Git y no se cita.

## E. Verificación (R10–R11)
**R10.** Se ejecutan: smoke de roadmap, `test_architecture_boundaries.py`, `ds_guard validate`, revisión de privacidad, `git diff --check`. Sin regresión completa. No se lanza reviewer separado: revisión de consistencia a cargo del Lead.
**R11.** `git diff --stat` muestra solo archivos de docs y `openspec/`; ningún código funcional modificado.

## F. Criterios de aceptación por Change futuro (R12–R17)
Lista corta; se copian al roadmap. Cada uno se refina en el SDD de su Change, con las decisiones M1–M5 fijas.

**R12. Change 1 — Hashing de line endings (cross-platform managed hashing, solo A).**
- Un archivo managed de texto tiene el mismo veredicto de drift con LF o CRLF.
- Una modificación lógica sigue siendo drift.
- Baselines históricos (sin `hash_alg`) siguen verificando sin regenerar.
- Binarios/no decodificables se hashean raw.

**R13. Change 2 — Approval Trust / T1 Human-Presence Semantics (M1).**
- Registro de aprobación con `approval_channel` aditivo y backward compatible. T0 `declared` = declaración registrada bajo el trust model actual (`--usuario` es metadata declarada; no demuestra presencia ni identidad; se mantiene por backward compat).
- T1 `tty_confirmed` = confirmación interactiva explícita desde un terminal de control soportado durante el registro. Es una señal de presencia de usuario («stronger human-presence signal»), NO prueba de identidad; NO identidad/autoría criptográfica, non-repudiation, firma ni identidad legal.
- Un proceso no interactivo/agente no obtiene `tty_confirmed` solo con `--usuario`, flag, stdin redirigido, pipe o archivo; requiere terminal/consola de control real (p. ej. CONIN$ / /dev/tty) y falla cerrado si no existe. `isatty()` solo no se asume suficiente.
- Change 2 audita la implementación concreta y sus límites.
- La política puede exigir `tty_confirmed` para operaciones dadas.
- T2 (canal separado / restricciones de adapter) = diseño futuro documentado; no se implementa salvo que el audit de Change 2 demuestre que T1 no mejora nada. T3 PKI/firmas: OUT OF SCOPE.
- ApprovalRef y Cards sin cambios.

**R14. Change 3 — Governed Amendments (scope amendment + closed-list re-adoption).**
- `ds_guard scope amend` agrega enmiendas append-only auditadas (quién/cuándo/por qué/canal, hash de propuesta base, cadena de hashes); solo amplía.
- Reutiliza la validación de rutas existente; rechaza un Change cerrado; fail-closed ante cadena rota.
- Re-adopción acotada a closed list: operación first-class, auditada, human-authorized, hash-bound, fail-closed, específica de paths/keys soportados. El audit de Change 3 determina exactamente los campos elegibles.
- NO se re-adoptan security ceilings, protected paths, hooks, tool permissions, source sealing ni otros controles sensibles salvo contrato explícito de customización.
- Re-adopción ≠ ignorar drift: el humano acepta una modificación soportada como nuevo baseline para una superficie permitida. Todo fuera de la lista sigue siendo drift. Descartado: primitive general «accept current managed state».
- Flujo: audit + autorización humana + mutación hash-bound.

**R15. Change 4 — Composable Skills Foundation + Writer Semantics (M2, M5).**
- Un ROL writer (`python-data-engineer`) + N instancias SOLO con ownership de archivos disjunto declarado en `tasks.md` antes de lanzar. Prohibidos: paths solapados, ownership ambiguo, dos writers en el mismo archivo, expansión unilateral (un writer que necesita un archivo ajeno no edita y lo devuelve al Lead para replanificar). El Lead coordina y gobierna; no se vuelve writer por conveniencia. Esto resuelve la contradicción entre `20261007-v09-release-hardening/tasks.md` («Lead implementa directamente») y SKILL.md.
- Enforcement: contrato + validación determinista donde sea viable; sin locks distribuidos, sin scheduler, sin hook por instancia.
- Contrato de composable skill: markdown pequeño, versionado, cargado bajo demanda, reusable; sin permisos ni hooks propios, sin instalación de dependencias, sin bypass de STOP/governance; frontmatter mínimo `name`, `purpose`, `when_to_load`, `roles`, `artifacts`; sin marketplace; sin runtime de skills nuevo si `.claude/skills/lead-data-scientist/*.md` ya soporta la composición; primero formalizar lo existente. Validado por Doctor.
- TDD-DS = guideline en `methodology.md`, no skill propia en v0.10.

**R16. Change 5 — Domain Modeling (M4).**
- `GLOSSARY.md` en la raíz: project-owned, Git-versionable, no managed, sin registry/DB, no runtime evidence. El installer NO lo crea ni sobrescribe salvo que Change 5 demuestre necesidad clara de scaffolding explícito.
- Estados `hypothesis` (propuesta por Lead/writer/otra skill, marcada explícitamente, no es verdad del negocio) y `approved` (solo tras intervención humana válida con referencia de aprobación verificable; sin ella = inválido/fail-closed; no se infiere de uso repetido). Ninguna auto-promoción.
- Ambigüedad MATERIAL (checkpoint humano) = definiciones plausibles alternativas que cambian significativamente target, población, unidad de análisis, universo, cutoff, métrica de negocio, interpretación de un KPI relevante, regla de negocio de inclusión/exclusión, significado de una variable/concepto usado en una decisión, o interpretación material de resultados/decisiones. Sinónimo o wording menor NO es checkpoint; dos definiciones que cambian quién entra a la población → checkpoint.
- Fronteras sin duplicar, referencias por id: Domain Model = qué significa un concepto; Decision Ledger = por qué se decidió; Data Contract = qué estructura/evidencia cumple el dato; Data Card = qué describe un data product concreto.

**R17. Change 6 — Release hardening v0.10.0.**
- Versión 0.10.0, smoke, sweep de privacidad, test-only symlink/junction, regeneración única de `control.json`.

## G. Skills y diferidos (R18–R19)
**R18.** Skills: entra domain-modeling; guideline TDD-DS; diferidas problem-framing/grill-me, diagnosing-bugs, codebase-design; code-review NO es skill (rol `data-science-reviewer`).
**R19.** Diferidas: `ds_profile` columnar (el bounded-memory de v0.9 resolvió lo principal; optimización futura); Data Card historical/as-of (extensión de contrato de Cards; no reabrir Cards en stabilization).

## Criterios de aceptación del Change 0
- [ ] R1–R3b: roadmap v0.10 completo, claves preservadas, decisiones cambiadas documentadas, dependencias.
- [ ] R4–R5: ARCHITECTURE §7 acotado; boundaries verde.
- [ ] R6–R9: alcance, congelados y privacidad respetados.
- [ ] R10–R11: verificación liviana ejecutada y diff solo docs.
- [ ] R12–R19: criterios de Changes futuros e decisiones M1–M5 reflejados en el roadmap.
