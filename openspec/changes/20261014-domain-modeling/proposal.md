# Propuesta — 20261014-domain-modeling

## Problema
Change 5 de v0.10: la primera skill componible, `domain-modeling`, no existe y el proyecto no tiene un lugar versionable donde fijar qué significa un concepto de dominio (target, población, unidad de análisis, universo, cutoff, KPI, reglas de inclusión/exclusión). Sin eso el Lead reinfiere negocio desde nombres de columnas y vuelve a preguntar lo mismo en cada Change.

## Objetivo
Entregar la skill `domain-modeling` bajo la foundation de Change 4, el artifact `GLOSSARY.md` (project-owned, Git, markdown) con estados `hypothesis|approved`, un validador determinista y `ds_guard glossary check|hash`, de modo que `approved` exija una aprobación humana verificable (T1 `console_confirmed`) y un LLM nunca pueda promover una hypothesis.

## Evidencia
- Roadmap/Arquitectura congelados: `docs/roadmap/v0.10.md` (Change 5, M4/M4b), `ARCHITECTURE.md` §7.1.
- Foundation: `tools/dsguard/skill_contract.py`, `templates/skill.md`, `.claude/skills/lead-data-scientist/skills/` (vacío), `methodology.md` §27–§28.
- Aprobaciones: `tools/cards/approvals.py` (`resolve_approval_ref`, `trust_tier`), `tools/dsguard/sdd.py::resolver_aprobacion_registrada`; `ds_guard approve --channel console_confirmed` acepta cualquier archivo del Change (`ds_guard.py::cmd_approve`); T1 vive en `tools/dsguard/human_presence.py` (NO se toca).
- Separación ya existente: Decision Ledger (`tools/dsguard/decision.py`), Data Contract (`tools/datacontracts/`), Data/Model Cards (`tools/cards/`).
- No existe `GLOSSARY.md` ni installer que lo cree; `skills/` está vacío.

## Supuestos descartados
1. Que haga falta una primitive de presencia nueva: se reutiliza `approve --channel console_confirmed` (T1).
2. Que el installer deba crear `GLOSSARY.md`: no; aparece cuando el proyecto usa domain modeling.
3. Que el glossary necesite DB, registry o catálogo: markdown + Git alcanza.
4. Que un LLM pueda decidir `approved` por uso repetido: no.

## Alcance
`skills/domain-modeling.md`; `tools/dsguard/glossary.py` (parser+validador stdlib); `ds_guard glossary check|hash` y chequeo dentro de `validate` si existe `GLOSSARY.md`; manifest (skill + módulo), Doctor (skill esperada); docs (methodology §33, SKILL.md, verificador.md, ARCHITECTURE, roadmap); tests.

## Fuera de alcance
Crear `GLOSSARY.md` por installer, DB/registry/catálogo, resolución semántica automática de sinónimos, tocar `human_presence.py`, fusionar glossary con ledger/contract/card, otras skills (problem-framing, diagnosing-bugs, codebase-design, tdd), push.

## Decisiones congeladas (usuario, 2026-10-14)
Estados `hypothesis|approved`; `approved` solo con señal humana explícita (T1) reutilizando approvals; ambigüedad material = definiciones plausibles distintas que afectan target, población, unidad de análisis, universo, cutoff, KPI, regla de inclusión/exclusión, variable/concepto usado en una decisión o interpretación de resultados materiales ⇒ no inventar, registrar hypothesis y pedir resolución humana si es necesaria; Domain Model ≠ Decision Ledger ≠ Data Contract ≠ Data Card.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- tools/dsguard/glossary.py
- tools/ds_guard.py
- tools/harmessi/doctor.py
- tools/ds_init/manifest.py
- tools/tests/test_glossary.py
- tools/tests/test_ds_guard_glossary_cli.py
- tools/tests/test_skill_methodology.py
- tools/tests/test_architecture_boundaries.py
- tools/harmessi/tests/test_doctor_skill_contract.py
- tools/ds_init/tests/test_manifest.py
- tools/ds_init/tests/test_glossary_install.py
- .claude/skills/lead-data-scientist/skills/domain-modeling.md
- .claude/skills/lead-data-scientist/methodology.md
- .claude/skills/lead-data-scientist/SKILL.md
- .claude/skills/lead-data-scientist/verificador.md
- tools/ds_init/profiles/python_jupyter_data/templates/methodology.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/SKILL_lead_data_scientist.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/verificador.md.tmpl
- ARCHITECTURE.md
- docs/roadmap/v0.10.md

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
