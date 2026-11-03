# Propuesta — 20261008-v010-roadmap-and-architecture-audit

> Change 0 de v0.10 («Integration & Stabilization + Composable Data Science Skills»): auditoría y congelamiento de roadmap. Es docs/SDD
> únicamente: NO implementa features.

## Problema
Las deudas preservadas de v0.9 (`docs/roadmap/v0.10.md`) se arrastran sin haber sido contrastadas con el código actual de `v0.10-dev`
(== `main` == tag v0.9.0, `ff9a39d`). Algunas siguen vigentes, otras ya se resolvieron, y varias se solapan (hashing, trust model, enmiendas
de alcance, re-adopción de guardrails, semántica de writers). Sin una auditoría, el roadmap de v0.10 corre el riesgo de implementar deudas ya
cerradas, duplicar mecanismos o fijar un orden de Changes con dependencias mal declaradas.

## Objetivo
Auditar cada deuda contra el código vigente, detectar solapamientos, definir la arquitectura objetivo y congelar un roadmap mínimo y coherente
de v0.10, con las decisiones M1–M5 aprobadas por el humano (2026-10-08).

## Evidencia
Todo lo citado sale de la lectura/medición del código actual de `v0.10-dev`, no de memoria.

- **A. LF/CRLF vigente.** `tools/ds_init/control.py::sha256_de_archivo` hashea bytes crudos; `tools/harmessi/doctor.py::_check_hashes_drift`
  compara contra `.ds_init/control.json`. Medido: de 119 archivos managed, el baseline coincide con el blob LF de git en 35, con CRLF en 81 y
  con ninguno en 3 (baseline MIXTO). `core.autocrlf=true`, 560 archivos con CRLF en el working tree, no hay `.gitattributes`. Ya existe
  `tools/dsguard/core.py::hash_lf_v1`. Managed = 99 `.py`, 18 `.md`, 2 `.json` (ninguno binario).
- **B. Approval authenticity vigente.** `ds_guard approve`, `exec approve`, `remediation` y `decision` aceptan `--usuario` libre (solo se
  bloquean emails). `tools/cards/approvals.py` (`NOTA_ANCHOR` / R39) declara que ApprovalRef no prueba identidad, presencia ni no repudio.
- **C. Scope amendment vigente.** El alcance inicial sale de `## Alcance autorizado` y se materializa en `approve` (`tools/ds_guard.py`
  ~343-370, `tools/dsguard/sdd.py::_normalizar_entrada_alcance`). Ampliarlo a mitad de un Change obliga a re-aprobar toda la propuesta.
- **D. One-writer, ambigüedad vigente.** `methodology.md` §14 («nunca dos writers concurrentes sobre el mismo cambio») vs la práctica de v0.9
  (varias instancias de `python-data-engineer` sobre archivos disjuntos). `pathguard.py` aplica `write_scopes` por `agent_type`, no por
  instancia, y el template trae `write_scopes: {}`. Además `20261007-v09-release-hardening/tasks.md` dice «Lead implementa directamente… un
  solo editor», lo que contradice «El Lead no edita archivos» de `SKILL.md`.
- **E. Guardrails re-adoption vigente y acotada.** `tools/dsguard/guardrails_drift.py::RUTAS_MUTABLES` es una lista cerrada (`version`,
  `autonomy.mode|version|budgets|limits`). Personalizar `holdouts`, `data_raw`, `secretos_extra`, `write_scopes`, excepciones,
  `autonomy.sealed_sources` o `autonomy.source_access` produce HARMESSI-DRIFT permanente.
- **F. ds_profile.** El sub-ítem «flags de cardinalidad mezclan denominador en modo muestreado» YA NO EXISTE: `tools/ds_profile/column_stats.py`
  ~309-311 usa `len(valores_orden)`. Quedan vigentes, pero diferidos, la variante columnar y bytes-por-dtype.
- **G. Data Card as-of.** `tools/cards/resolvers.py` ~286 resuelve la observación vigente más reciente; un contrato current/as-of es una
  extensión y las Cards están congeladas, por lo que se difiere.
- **H. Skills de facto ya existentes.** `.claude/skills/lead-data-scientist/{sdd,kdd,eda,decision-ledger,methodology,verificador,production-readiness}.md`
  más `templates/`, instaladas por `tools/ds_init/manifest.py` con `stage_minimo`. No existe convención previa de glosario de dominio (solo
  menciones en roadmap/ARCHITECTURE); la Data Card ya tiene `business_meaning`, `population` y `unit_of_analysis` por dataset.

## Supuestos descartados
1. «Doctor ya reporta drift por LF/CRLF hoy»: en este checkout Doctor da 0 WARN porque `control.json` se regeneró en este estado; el problema
   aparece en un clon limpio o en otra plataforma.
2. «Scope y re-adopción van con el hashing»: dependen del trust model, no del hash.
3. «Flags de cardinalidad muestreadas»: ya corregido (ver F).
4. «Una skill nueva = un agente nuevo»: una skill es una pieza de método versionada; el agente es un rol con permisos. Son ejes distintos.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica: es un cambio de auditoría/documentación, no prueba una hipótesis sobre datos.

## Clasificación de deudas

| Tema | Estado actual | Problema real | Severidad | Dependencia | v0.10 | Change propuesto | Tipo |
|---|---|---|---|---|---|---|---|
| A. LF/CRLF | vigente | falso drift cross-platform | alta | — | SÍ | 1 | stabilization (blocker de clon/CI) |
| B. Approval authenticity | vigente | garantía no definida | media | — | SÍ (tier T1) | 2 | stabilization/trust |
| C. Scope amendment | vigente | ampliar exige re-aprobar todo | media | B | SÍ | 3 | UX |
| D. One-writer | vigente (doc) | ambigüedad ya causó un desvío | media | — | SÍ | 4 | methodology |
| E. Guardrails re-adoption | vigente, acotada | drift permanente en proyectos reales | media | A, B | SÍ (acotada) | 3 | UX |
| F1. Cardinalidad muestreada | ya no existe | — | — | — | NO | — | cerrado |
| F2. ds_profile columnar / bytes por dtype | vigente | beneficio bajo | baja | — | NO | — | future candidate |
| G. Data Card as-of | vigente | extensión de contrato | baja | Cards congeladas | NO | — | future candidate |
| H. Composable skills foundation | nuevo | formalizar lo existente | media | D | SÍ | 4 | methodology |
| I. domain-modeling | nuevo | re-preguntar significado de dominio | media | H, B | SÍ | 5 | methodology |
| J. Otras skills (problem-framing, diagnosing-bugs, codebase-design, code-review) y skill TDD | nuevo | sin casos reales; code-review ya es un rol | baja | H | NO (TDD-DS = guideline en Change 4) | — | future candidate |
| K. ALCANCE-RUTA no distingue Changes paralelos | vigente | workaround conocido | baja | C | NO | — | future candidate |
| L. Cobertura symlink/junction Windows | parcial | tests | baja | — | test-only | 6 | stabilization |

## Roadmap aprobado
Cambia la hipótesis inicial del pedido (que agrupaba scope/re-adopción con el hashing): la evidencia muestra que estas dependen del trust model,
no del hash, y que hashing es el único blocker independiente. Se separa en Changes con dependencias explícitas.

- **Change 0 — Audit** (este Change): auditoría y congelamiento de roadmap.
- **Change 1 — Cross-platform managed hashing**: solo A.
- **Change 2 — Approval Trust / T1 Human-Presence Semantics**: B, tier T1 `tty_confirmed` (independiente; permanece por M1).
- **Change 3 — Governed Amendments**: C (scope amendment) + E (re-adopción acotada a closed list, M3), con un patrón único de «enmienda
  auditada humana, hash-bound, fail-closed».
- **Change 4 — Composable Skills Foundation + Writer Semantics**: Role/Skill/Runtime, skill contract mínimo, one-writer role + instancias
  disjuntas (D, M2), foundation de composable skills (H) y guideline TDD-DS (M5).
- **Change 5 — Domain Modeling** (I): primera skill; `GLOSSARY.md` (M4).
- **Change 6 — v0.10 release hardening** (incluye L como test-only).

Dependencias: 1→3, 2→3, 4→5, {1..5}→6.

## Decisiones aprobadas (2026-10-08)
El humano aprobó explícitamente M1–M5 y el roadmap v0.10 (estado: aprobado).

- **M1. Garantía de aprobación.**
  - T0 `declared`: declaración registrada bajo el trust model; `--usuario` es metadata declarada, no demuestra presencia ni identidad; se
    mantiene por backward compat.
  - T1 `approval_channel = tty_confirmed`: confirmación interactiva explícita desde un terminal de control soportado durante el registro.
    Es una señal de presencia de usuario («stronger human-presence signal»), NO prueba de identidad; NO es identidad/autoría criptográfica,
    non-repudiation, firma ni identidad legal. Un proceso no interactivo/agente no debe obtener `tty_confirmed` solo con `--usuario`, un
    flag, stdin redirigido, pipe o archivo; requiere interacción con terminal/consola de control real y falla cerrado si no existe.
    `isatty()` solo no se asume suficiente: Change 2 audita la implementación concreta y sus límites.
  - T2 (canal separado / restricciones de adapter): diseño futuro documentado; no se implementa salvo que el audit de Change 2 demuestre que
    T1 no mejora nada. T3 (PKI/firmas): fuera de alcance. Change 2 permanece en el roadmap.
- **M2. One-writer.** Un ROL writer (`python-data-engineer`) + N instancias SOLO con ownership de archivos disjunto declarado en `tasks.md`
  antes de lanzar (ej.: Writer A: archivos…, Writer B: archivos…). Prohibidos: paths solapados, ownership ambiguo, dos writers sobre un
  archivo, expansión unilateral. Si un writer necesita un archivo ajeno, no lo edita y lo devuelve al Lead para replanificar. El Lead
  coordina y gobierna; NO se vuelve writer por conveniencia. Esto resuelve la contradicción entre tareas históricas («Lead implementa
  directamente») y `SKILL.md`. Enforcement: contrato + validación determinista donde sea viable; sin locks distribuidos ni scheduler.
- **M3. Re-adopción.** ACOTADA a closed list; NO existe primitive general «accept current managed state». Operación first-class, auditada,
  human-authorized, hash-bound, fail-closed, específica de paths/keys soportados. El audit de Change 3 determina exactamente los campos
  elegibles. NO se re-adoptan security ceilings, protected paths, hooks, tool permissions, source sealing ni otros controles sensibles salvo
  contrato explícito de customización. Re-adopción ≠ ignorar drift: todo cambio fuera de la lista sigue siendo drift.
- **M4. Artefacto de dominio.** `GLOSSARY.md` en la raíz del proyecto (project-owned, Git-versionable, no managed, sin registry/DB, no runtime
  evidence); el installer NO lo crea ni sobrescribe salvo que Change 5 demuestre necesidad clara de scaffolding explícito.
  - **M4b. Ambigüedad MATERIAL** = definiciones alternativas plausibles que cambian significativamente target, población, unidad de análisis,
    universo, cutoff, métrica de negocio, interpretación de un KPI relevante, regla de negocio de inclusión/exclusión, significado de una
    variable/concepto usado en una decisión, o interpretación material de resultados/decisiones posteriores. Sinónimo o wording menor NO es
    checkpoint.
  - Estados: `hypothesis` (propuesta por Lead/writer/otra skill, marcada explícitamente) y `approved` (solo tras intervención humana válida,
    con referencia de aprobación verificable; `approved` sin aprobación verificable es inválido/fail-closed; no se infiere de uso repetido).
  - Fronteras (sin duplicar; referencias por id): Domain Model = qué significa un concepto; Decision Ledger = por qué se decidió; Data
    Contract = qué estructura/evidencia cumple el dato; Data Card = qué describe un data product concreto.
- **M5. TDD-DS.** GUIDELINE en `methodology.md`, no skill: software determinista → TDD clásico cuando aporte valor; contratos/pipelines →
  invariants/test-first; EDA → evidence-first; modelado → protocolo de evaluación/scientific validity; sin red-green-refactor artificial en
  exploración. Reevaluar en una versión futura si surge comportamiento reusable.

## Alcance
Los cinco artefactos de este Change (`proposal.md`, `spec.md`, `design.md`, `tasks.md` y `control.json`, este último generado por `ds_guard init`),
`docs/roadmap/v0.10.md`, `docs/roadmap/README.md` y `ARCHITECTURE.md` §7.

## Fuera de alcance
Toda implementación (`tools/**`); reabrir lo congelado en v0.9 (Cards Foundation, Data/Model Cards, Governance Assessment, BASE_POLICY v1,
capability model, `report_kind`, ds_profile `bounded_v1`, Correctives A/B/C); compliance engine; registry/catálogo nuevo; orquestación;
marketplace de skills; GUI/TUI; PKI; lineage; ejecución distribuida; backend cloud; `docs/feedback/`.

## Holdout policy (condicional — solo cambios "sensible")
No aplica: no se toca ningún holdout ni dataset sellado.

## Impacto en production-readiness (opcional)
Ninguno directo; las decisiones M1-M3 afectan el trust model que luego consume esa etapa.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md` (SDD completo).

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md` (SDD completo).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-10-08
- Alcance aprobado: Aprobación y cierre de Change 0 v0.10 roadmap-and-architecture-audit
- Versión de artefactos referenciada: proposal.md/spec.md/design.md vigentes al momento del hash
- Cita o descripción fiel de qué se aprobó: «Aprobación humana explícita de roadmap v0.10 y decisiones M1-M5»

## Alcance autorizado

- docs/roadmap/v0.10.md
- docs/roadmap/README.md
- ARCHITECTURE.md
- openspec/changes/20261008-v010-roadmap-and-architecture-audit/**

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
