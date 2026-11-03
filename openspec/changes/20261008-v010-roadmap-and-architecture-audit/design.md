# Diseño — 20261008-v010-roadmap-and-architecture-audit

Los diseños de los Changes 1–5 son diseño conceptual a refinar en el SDD de cada Change, con las decisiones aprobadas fijas.

## Decisiones aprobadas 2026-10-08
M1 (trust T1), M2 (writer), M3 (re-adopción acotada), M4 (GLOSSARY / ambigüedad material) y M5 (TDD-DS guideline) fueron aprobadas por el humano; ya no son materiales pendientes. Detalle en D4, D5/D5b, D6, D7 y D8.

## Decisión metodológica/técnica

### D1. Roadmap mínimo
7 Changes (0–6): C0 audit; C1 Cross-platform Managed Hashing (solo A); C2 Approval Trust / T1 Human-Presence Semantics; C3 Governed Amendments; C4 Composable Skills Foundation + Writer Semantics; C5 Domain Modeling; C6 Release Hardening.
Dependencias: 1→3, 2→3, 4→5, {1..5}→6; 1 y 2 independientes. Las fusiones no deben agrandar Changes: tareas separables.

### D2. Role vs Skill vs Runtime
- Role = quién + permisos (subagentes).
- Skill = enfoque metodológico reusable: markdown pequeño, versionado, cargado bajo demanda; frontmatter mínimo (`name`, `purpose`, `when_to_load`, `roles`, `artifacts`); sin permisos, tools ni hooks propios; sin instalación de dependencias; no bypassa STOP ni governance. La composición aplicada a un Change se registra en `tasks.md`.
- Runtime/Tool = ejecución determinista con evidence.
- Ya existen skills de facto en `.claude/skills/lead-data-scientist/*.md`, instaladas por `tools/ds_init/manifest.py`: no se crea runtime de skills nuevo si ya soportan la composición; primero se formaliza lo existente. Sin marketplace.
- Provider-neutral: markdown puro; `.claude/skills/` es el adapter de Claude Code.

### D3. Hashing de line endings (Change 1)
- Para extensiones de texto: hash del contenido normalizado a LF (reutiliza el criterio de `hash_lf_v1`). La entrada de baseline lleva `hash_alg` explícito.
- Compatibilidad legacy (sin `hash_alg`): no es drift si coincide el hash raw, el LF-normalizado o el CRLF-normalizado del archivo actual; cualquier otra diferencia es drift real.
- Binarios o no decodificables: hash raw.
- `.gitattributes` complementario opcional, nunca dependencia.
- Evidencia: baseline mixto 35 LF / 81 CRLF / 3 otro sobre 119 archivos.

### D4. Trust / authenticity (Change 2) — M1 aprobada
Tiers:
- T0 `declared`: declaración registrada bajo el trust model actual. `--usuario` es metadata declarada, no demuestra presencia ni identidad; se mantiene por backward compat.
- T1 `approval_channel = tty_confirmed`: confirmación interactiva explícita desde un terminal de control soportado durante el registro. Es una señal de presencia de usuario («stronger human-presence signal»), NO prueba de identidad; NO identidad/autoría criptográfica, non-repudiation, firma ni identidad legal.
  - Un proceso no interactivo/agente no obtiene `tty_confirmed` solo con `--usuario`, flag, stdin redirigido, pipe o archivo.
  - Requiere terminal/consola de control real (p. ej. CONIN$ / /dev/tty); falla cerrado si no existe. `isatty()` solo no se asume suficiente.
  - Change 2 audita la implementación concreta y sus límites.
- T2 (canal separado / restricciones de adapter): diseño futuro documentado; no se implementa salvo que el audit de Change 2 demuestre que T1 no mejora nada.
- T3 PKI/firmas: OUT OF SCOPE.
Change 2 permanece. ApprovalRef y Cards no cambian. La fusión del Change 2 en el 3 ya no aplica.

### D5. Enmiendas auditadas (Change 3)
- Primitive `scope amend` append-only en `control["alcance"]["enmiendas"]`: seq, rutas, motivo, usuario, fecha, `approval_channel`, hash de propuesta base, hash encadenado.
- Solo amplía; reutiliza `_normalizar_entrada_alcance` (protecciones de rutas); alcance efectivo = base ∪ enmiendas; fail-closed ante cadena rota o Change cerrado.
- Persistencia en un lugar versionable (no `.harmessi/`), a decidir en su SDD.
- Aprovecha T1 (Change 2) para que un agente no pueda auto-adoptarse cambios.

### D5b. Re-adopción acotada a closed list (Change 3) — M3 aprobada
Boundary explícito: **closed-list re-adoption ≠ general managed-baseline acceptance**.
- Operación first-class, auditada, human-authorized, hash-bound, fail-closed, específica de paths/keys soportados.
- El audit de Change 3 determina exactamente los campos elegibles. Los candidatos iniciales (holdouts, data_raw, secretos_extra, write_scopes, excepciones, autonomy.sealed_sources, autonomy.source_access) son *candidatos a confirmar por el audit de Change 3*, no lista cerrada; en particular, source sealing queda excluido salvo contrato explícito de customización.
- NO se re-adoptan security ceilings, protected paths, hooks, tool permissions, source sealing ni otros controles sensibles salvo contrato explícito de customización.
- Re-adopción ≠ ignorar drift: el humano acepta una modificación soportada como nuevo baseline para una superficie permitida. Todo fuera de la lista sigue siendo drift y se compara contra la plantilla.
- Descartado: primitive general «accept current managed state».
- Flujo: audit + autorización humana + mutación hash-bound (hash canónico del subconjunto).

### D6. One-writer (Change 4) — M2 aprobada
- Un ROL writer (`python-data-engineer`) + N instancias SOLO con ownership de archivos disjunto declarado en `tasks.md` antes de lanzar.
- Prohibidos: paths solapados, ownership ambiguo, dos writers en el mismo archivo, expansión unilateral (si un writer necesita un archivo ajeno no edita y lo devuelve al Lead para replanificar).
- El Lead coordina y gobierna; no se vuelve writer por conveniencia. Resuelve la contradicción entre `20261007-v09-release-hardening/tasks.md` («Lead implementa directamente») y SKILL.md.
- Archivos compartidos (tests, manifest, `control.json`, docs índice) con un único dueño. Trazabilidad por `git diff` contra ownership.
- Enforcement: contrato + validación determinista donde sea viable (p. ej. warning de `validate` por solapamiento); sin locks distribuidos, sin scheduler, sin hook por instancia.

### D7. domain-modeling (Change 5) — M4 aprobada
- Fronteras (sin duplicar; referencias por id): Domain Model = qué significa un concepto; Decision Ledger (`openspec/decisions/ledger.jsonl`) = por qué se decidió; Data Contract (`tools/datacontracts`) = qué estructura/evidencia cumple el dato; Data Card = qué describe un data product concreto.
- Artefacto: `GLOSSARY.md` en la raíz del proyecto (texto estructurado, sin registry/DB, no runtime evidence). Project-owned, Git-versionable, NO managed, fuera de `control.json.archivos`. El installer NO lo crea ni sobrescribe, salvo que Change 5 demuestre necesidad clara de scaffolding explícito.
- Entrada: término, definición, estado, unidad_de_análisis/población/evento/fecha cuando aplique, sinónimos, no_confundir_con, `approval_ref {change_id, artefacto, hash}` para `approved`.
- Estados: `hypothesis` (propuesta por Lead/writer/otra skill, marcada explícitamente, no es verdad del negocio) y `approved` (solo tras intervención humana válida con referencia de aprobación verificable, resolver `tools/cards/approvals.py`; sin ella = inválido/fail-closed; no se infiere de uso repetido). Inferencia del LLM ≠ definición aprobada; el Lead/writer solo crean `hypothesis`.
- M4b, ambigüedad MATERIAL = definiciones plausibles alternativas que cambian significativamente target, población, unidad de análisis, universo, cutoff, métrica de negocio, interpretación de un KPI relevante, regla de negocio de inclusión/exclusión, significado de una variable/concepto usado en una decisión, o interpretación material de resultados/decisiones. Sinónimo o wording menor NO es checkpoint (ejemplo: dos definiciones que cambian quién entra a la población → checkpoint).
- Flujo: aprobado → reutilizar y citar; ausente y no material → hipótesis marcada y citada como supuesto; material → checkpoint humano → anclado y trazable.
- Doctor/validate chequean estructura y ancla, no el significado.

### D8. Skills y TDD-DS — M5 aprobada
- Entran: foundation + domain-modeling.
- Se difieren: problem-framing/grill-me, diagnosing-bugs, codebase-design.
- code-review NO es skill: ya es el rol `data-science-reviewer`.
- TDD-DS = GUIDELINE en `methodology.md`, no skill propia en v0.10: software determinista → TDD clásico cuando aporte; contratos/pipelines → invariants/test-first; EDA → evidence-first; modelado → protocolo de evaluación / scientific validity; sin red→green→refactor artificial en exploración. Reevaluar si en uso real aparece comportamiento reusable.

### D9. Diferidos
- `ds_profile` columnar / bytes-por-dtype (bounded-memory de v0.9 resolvió lo principal; optimización futura).
- Data Card historical/as-of (extensión de contrato de Cards; no reabrir Cards en stabilization).
- ALCANCE-RUTA con Changes paralelos.
- Ownership por instancia en hook.

### D10. Verificación y revisión de Change 0
Smoke de roadmap, architecture boundaries, `ds_guard validate`, privacidad, `git diff --check`; sin regresión completa. No se lanza reviewer separado: revisión de consistencia del Lead.

## Target (condicional — feature_engineering, modeling)
No aplica (Change documental).

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica; no se toca ningún holdout.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica; sin datos ni features.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
Sin desvíos.

## Alternativas descartadas
- Skill = agente disfrazado; permisos duplicados en skills; un subagente por metodología; plugin framework / marketplace.
- Hashing AST/semántico (costo sin beneficio); depender de `core.autocrlf`.
- Mutación libre de `control.json`; primitive general «accept current managed state».
- One-writer opción B (instancia única): sacrifica paralelismo sin evidencia de races.
- Code-review como skill (duplica el rol `data-science-reviewer`).
- TDD-DS como skill propia en v0.10; T3 PKI/firmas; GLOSSARY entregado por el installer.

## Riesgos
- Sobre-diseño de la foundation de skills. Mitigación: formalizar lo existente.
- T1 depende de que exista terminal de control y no prueba identidad. Mitigación: `declared` sigue válido; fail-closed solo cuando la política lo exige; límites documentados por el audit de Change 2.
- Fusiones (C+E en 3, D con foundation en 4) que agranden Changes. Mitigación: tareas separables.
- Los diseños pueden refinarse en cada SDD; las decisiones M1–M5 quedan fijas.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
Ver `proposal.md`. Las decisiones M1–M5 fueron aprobadas el 2026-10-08.
