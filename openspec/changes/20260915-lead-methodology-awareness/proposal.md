# Propuesta — 20260915-lead-methodology-awareness

## Problema
La documentación operativa del Lead (`.claude/skills/lead-data-scientist/`) quedó congelada en su
mayor parte en el modelo v0.2: `SKILL.md` describe KDD como "el lifecycle del proyecto" (10 etapas
legacy, `openspec/kdd/state.json`) sin mencionar CRISP-DM como backbone real ni `project_stage`/
`installation_stage`/`risk_level`/`readiness`/`mlops foundations`/`status` unificado (Changes
1,3,5,6,7,8). `kdd.md`/`decision-ledger.md` repiten la misma frase de encuadre desactualizada.
`verificador.md` no documenta NINGUNO de los comandos `lifecycle migrate`, `project
init/calibrate/set-risk/status/readiness/promote`, `mlops status/record/evidence add`, ni `status`
unificado — el Lead no tiene, hoy, ninguna referencia escrita de cómo invocarlos correctamente.
Además, `production-readiness.md.tmpl`/`operations.md.tmpl` (Change 7) tienen un bug real de
sintaxis: documentan `ds_guard project promote --target <stage> --reason ...`, pero la CLI real
(Change 6, `tools/ds_guard.py:1476`) usa `<stage>` **posicional**, no `--target`.

## Objetivo
Actualizar la documentación de la skill para que el Lead entienda la jerarquía metodológica real
(CRISP-DM backbone / KDD subordinado / MLOps progresivo / SDD transversal), adapte su
comportamiento según `project_stage`, use `ds_guard status`/`readiness` como puerta de entrada en
vez de recalcular manualmente, distinga `project_stage` de `installation_stage`, y respete las
prohibiciones explícitas del brief — sin agregar ningún engine, estado persistido o lógica
determinista nueva, y sin tocar runtime salvo la corrección puntual y demostrada del bug de
sintaxis de `promote`.

## Evidencia
- `.claude/skills/lead-data-scientist/SKILL.md:88-98` (`## KDD (lifecycle del proyecto)`): describe
  KDD como "en qué etapa del lifecycle de Data Science está el proyecto
  (`problem_understanding` → ... → `monitoring`, persistido en `openspec/kdd/state.json`)" — el
  modelo v0.2 pre-Change-1, sin ninguna mención de `openspec/lifecycle/state.json`, CRISP-DM,
  `project_stage`, `readiness` o `status`.
- `.claude/skills/lead-data-scientist/kdd.md:3` ya tiene, desde Change 2, un aviso explícito: "La
  experiencia metodológica completa del Lead (project_stage, risk_level, readiness) se documenta
  en un change posterior" — confirmando que este change es exactamente ese destino previsto.
- `.claude/skills/lead-data-scientist/kdd.md:10-14`/`decision-ledger.md:14` repiten la misma frase
  de encuadre ("KDD es el lifecycle del proyecto... SDD no lo reemplaza") sin corregir para
  reflejar que CRISP-DM es el backbone real y KDD es el proceso técnico subordinado dentro de él.
- `.claude/skills/lead-data-scientist/verificador.md` (238 líneas): documenta `status` (SDD),
  `validate`, `approve`, `transition`, `session *`, `notebook-diff`, `kdd *` (legacy),
  `decision *`, `remediation *`, `archive` — CERO menciones de `lifecycle`, `project`, `mlops`, ni
  del `status` unificado sin `--change-id` (Change 8). Confirmado con grep explícito.
- `tools/ds_init/profiles/python_jupyter_data/templates/production-readiness.md.tmpl:66` y
  `operations.md.tmpl:63`: `ds_guard project promote --target production... --reason <texto>`.
  `tools/ds_guard.py:1476`: `p_project_promote.add_argument("stage",
  choices=list(readiness.TARGETS_VALIDOS))` — posicional, sin `--target`. Confirmado que el flag
  `--target` solo existe en `project readiness` (`tools/ds_guard.py:1469`), no en `promote`. Bug
  real, demostrado por lectura directa del código fuente — corrección puntual de documentación, no
  de runtime.
- `.claude/agents/{python-data-engineer,metodologo,data-science-reviewer,notebook-runner}.md`:
  auditados, sin referencias obsoletas a KDD 10 etapas ni a conceptos pre-Change-1 — no requieren
  cambios de contenido para este change.
- `tools/dsguard/status.py` (Change 8), `readiness.py`/`mlops_evidence.py` (Change 6),
  `mlops_foundations.py` (Change 5), `maturity.py` (Change 3), `lifecycle.py` (Change 1) — todos
  reusados como fuente de verdad de lo que la nueva documentación debe describir, ninguno
  modificado.
- Precedente de mecánica ya establecido: cada doc de la skill vive como par `.tmpl` (fuente,
  `tools/ds_init/profiles/python_jupyter_data/templates/*.md.tmpl`, tratamiento `PLANTILLA`) +
  copia renderizada en `.claude/skills/lead-data-scientist/*.md` de este propio repo (self-hosted,
  ya sincronizada en changes anteriores, p. ej. `20260910-sincronizar-plantillas-bloque5`) — este
  change edita AMBAS copias de cada archivo tocado, nunca solo una.

## Supuestos descartados
No se crea ningún engine nuevo, estado persistido nuevo, ni lógica determinista nueva. No se
modifica `readiness.py`/`checks.py`/`lifecycle.py`/`maturity.py`/`mlops_evidence.py`/
`mlops_foundations.py`/`status.py`/instalador — el único cambio de código real es la corrección de
2 líneas de sintaxis de CLI en 2 documentos `.tmpl` (`--target` → posicional), no un cambio de
comportamiento de `ds_guard.py`. No se reescribe `SKILL.md` completo — se corrige la sección
puntual obsoleta y se agrega un pointer a un documento nuevo. No se fragmenta la skill en muchos
archivos nuevos — un único documento nuevo (`methodology.md`).

## Hipótesis (condicional — solo cambios metodológicos)
No aplica — cambio de documentación/orquestación del harness.

## Alcance
1. **`methodology.md`** (nuevo, `.tmpl` + copia renderizada): jerarquía CRISP-DM/KDD/MLOps/SDD,
   comportamiento por `project_stage`, `status` como puerta de entrada, `project_stage` vs
   `installation_stage`, reglas de `readiness`/`promotion`/`risk_level`/`lifecycle`/`evidence`,
   workflow Inspect→Classify→Plan→Execute→Verify→Close, acciones prohibidas del Lead,
   human-in-the-loop, fail-closed, nuevo proyecto vs adopción — todo per brief §2-§24.
2. **`SKILL.md`**: corrige `## KDD (lifecycle del proyecto)` (encuadre CRISP-DM-backbone
   correcto, sin duplicar contenido de `methodology.md`) + agrega pointer a `methodology.md`
   (lectura bajo demanda, mismo patrón que `kdd.md`/`eda.md`).
3. **`kdd.md`/`decision-ledger.md`**: corrección puntual de la frase de encuadre desactualizada,
   apuntando a `methodology.md` para la jerarquía completa — sin reescribir el resto.
4. **`verificador.md`**: agrega entradas para `lifecycle migrate`, `project
   init/calibrate/set-risk/status/readiness/promote`, `mlops status/record/evidence add`, `status`
   unificado (sin `--change-id`) — mismo estilo terso ya usado, sin duplicar el detalle de diseño
   de esos comandos (que vive en los `design.md` de sus changes de origen).
5. **`production-readiness.md.tmpl`/`operations.md.tmpl`**: corrige el bug de sintaxis
   `--target` → `<stage>` posicional en la línea de `promote` (2 archivos, 1 línea cada uno).
6. **Manifest**: entrada VERBATIM/PLANTILLA de `methodology.md.tmpl`; ningún cambio de
   `stage_minimo` para los docs ya clasificados en Change 7 (siguen `discovery`, salvo
   `production-readiness.md`/`operations.md` que ya eran `production_candidate`/`production`).
7. **Tests**: livianos, de contenido (presencia/ausencia de cadenas concretas en los `.tmpl`
   fuente), sin parser de Markdown — ver `spec.md`.

## Fuera de alcance
Cambios a `readiness.py`/`checks.py`/`lifecycle.py`/`maturity.py`/`mlops_evidence.py`/
`mlops_foundations.py`/`status.py`/`ds_init` (salvo la corrección puntual de sintaxis ya descrita).
Cutoff/baseline enforceable, Impact Preflight/dsimpact, Scope & Change Isolation, Portable Core,
evals/harmessi-bench, reporting, Data Contracts avanzados, Responsible AI, token telemetry,
multi-provider, `harmessi` CLI pública, deployment/CI-CD/monitoring reales. Ningún cambio a
`.claude/agents/*.md` (auditados, sin hallazgos que ameriten cambio).

## Holdout policy (condicional — solo cambios "sensible")
No aplica.

## Impacto en production-readiness (opcional)
Indirecto — corrige la única referencia escrita de cómo invocar `promote` correctamente, reduce
el riesgo de que el Lead (o un futuro operador humano) intente una sintaxis de CLI inexistente.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md`.

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md`.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-15
- Alcance aprobado: "lead-methodology-awareness — actualizar la skill para que el Lead entienda
  CRISP-DM/KDD/MLOps/SDD como jerarquía única, use status/readiness como puerta de entrada,
  distinga project_stage de installation_stage, y respete las prohibiciones explícitas del brief;
  sin nueva fuente de verdad ni engine nuevo; documento nuevo único (methodology.md); corrección
  puntual del bug de sintaxis de `promote` en 2 .tmpl existentes"
- Versión de artefactos referenciada: hashes a registrar en `control.json` de este change
- Cita o descripción fiel de qué se aprobó: brief íntegro del usuario para Change 9 ("LLM decide
  lo semántico; el binario calcula y hace cumplir lo determinista." + lista explícita de 30
  secciones normativas).

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
