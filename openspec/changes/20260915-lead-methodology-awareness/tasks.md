# Tareas — 20260915-lead-methodology-awareness

estado: cerrada

## Invocaciones planificadas
<!-- rol, momento del ciclo, y qué produce cada una -->
- Python Data Engineer (implementación + tests, invocación única, puede requerir reanudaciones —
  no cuentan como nuevas delegaciones): `methodology.md` (nuevo, `.tmpl` + copia renderizada) +
  correcciones puntuales de `SKILL.md`/`kdd.md`/`decision-ledger.md`/`verificador.md` (ambas
  copias) + fix de sintaxis en `production-readiness.md.tmpl`/`operations.md.tmpl` (solo `.tmpl`)
  + entrada de manifest + tests livianos de contenido, siguiendo `design.md` al pie de la letra.
- Data Science Reviewer (revisión, DESPUÉS de implementación completa): revisa el diff. Solo
  informa hallazgos.
- Python Data Engineer (post-revisión, si hace falta): corrige, `estado: en_verificacion`.
- Python Data Engineer (cierre, planificada): `verification.md` con evidencia real,
  `estado: cerrada`.

## Tareas
- [x] `tools/ds_init/profiles/python_jupyter_data/templates/methodology.md.tmpl` (nuevo): las 23
  secciones normativas de R1 de `spec.md` (jerarquía, stage behavior, status, alignment,
  readiness, promotion, risk, lifecycle, KDD, foundations, evidence, SDD, decision ledger,
  one-writer, delegación proporcional, bounded remediation, notebooks, EDA, human-in-the-loop,
  fail-closed, adopción, workflow, prohibiciones) — referencia, sin duplicar el detalle de
  comandos ya cubierto por `verificador.md`/`kdd.md`/`eda.md`/`decision-ledger.md`/
  `production-readiness.md`/`operations.md`.
- [x] `.claude/skills/lead-data-scientist/methodology.md` (copia renderizada, idéntica al `.tmpl`
  ya que este documento no usa placeholders de proyecto).
- [x] `tools/ds_init/manifest.py`: entrada `PLANTILLA` para `methodology.md.tmpl` (mismo patrón
  que `kdd.md.tmpl`/`eda.md.tmpl`/`decision-ledger.md.tmpl`; `stage_minimo` default, sin
  especificar explícito).
- [x] `tools/ds_init/profiles/python_jupyter_data/templates/SKILL_lead_data_scientist.md.tmpl` Y
  `.claude/skills/lead-data-scientist/SKILL.md`: corregir `## KDD (lifecycle del proyecto)` (ya
  no describe KDD como "el lifecycle del proyecto" con las 10 etapas como referencia primaria —
  CRISP-DM backbone, pointer a `methodology.md`); agregar pointer a `methodology.md` (lectura bajo
  demanda) en el lugar natural junto a los pointers existentes. Preservar el resto del contenido
  de esa sección (declaración de etapa por change, sync al cerrar) sin cambios.
- [x] `tools/ds_init/profiles/python_jupyter_data/templates/kdd.md.tmpl` Y
  `.claude/skills/lead-data-scientist/kdd.md`: corregir §1 (frase de encuadre), pointer a
  `methodology.md`. Resto del documento sin cambios.
- [x] `tools/ds_init/profiles/python_jupyter_data/templates/decision-ledger.md.tmpl` Y
  `.claude/skills/lead-data-scientist/decision-ledger.md`: misma corrección puntual en §1.
- [x] `tools/ds_init/profiles/python_jupyter_data/templates/verificador.md.tmpl` Y
  `.claude/skills/lead-data-scientist/verificador.md`: agregar entradas para `lifecycle migrate`;
  `project init/calibrate/set-risk/status/readiness/promote`; `mlops status/record/evidence add`;
  `status` unificado (sin `--change-id`) — según R4 de `spec.md`, mismo estilo terso existente,
  agregadas al final de la lista de comandos sin reordenar lo existente.
- [x] `tools/ds_init/profiles/python_jupyter_data/templates/production-readiness.md.tmpl`:
  corregir la línea de `promote` (`--target` → `<stage>` posicional). Solo el `.tmpl` (la copia
  renderizada no existe todavía en este repo, ver `design.md` punto 4 — no crearla como parte de
  este change).
- [x] `tools/ds_init/profiles/python_jupyter_data/templates/operations.md.tmpl`: misma corrección
  de sintaxis.
- [x] Tests livianos de contenido (nuevo archivo, p. ej. `tools/tests/test_skill_methodology.py`
  o extendiendo un test existente si aplica mejor): verificar sobre los `.tmpl` fuente — presencia
  de los 5 pasos KDD canónicos, las 8 fases CRISP-DM, los 4 `PROJECT_STAGES` en `methodology.md.tmpl`;
  distinción explícita `project_stage`/`installation_stage`; sintaxis exacta de `promote`
  (posicional) y `readiness --target` (con flag) en `methodology.md.tmpl`; las 14 prohibiciones del
  brief §24 presentes; ausencia de las 10 etapas legacy como catálogo principal; ausencia de la
  frase obsoleta "KDD... es en qué etapa del lifecycle de Data Science está el proyecto" (sin
  matiz) en `SKILL.md.tmpl`/`kdd.md.tmpl`/`decision-ledger.md.tmpl`; ausencia de `--target` en la
  línea de `promote` de `production-readiness.md.tmpl`/`operations.md.tmpl`.
- [x] Test de sincronización `.tmpl` ↔ renderizado: para cada uno de los 5 archivos que SÍ tienen
  copia local (`SKILL.md`, `kdd.md`, `decision-ledger.md`, `verificador.md`, `methodology.md`),
  confirmar contenido idéntico entre `.tmpl` y `.claude/skills/lead-data-scientist/*.md`.
- [ ] Verificación manual del Lead (con Bash, fuera del alcance del subagente): correr
  `ds_guard project readiness --target <stage> --help` / `ds_guard project promote --help` (o
  invocación real read-only) para confirmar que la sintaxis documentada coincide exactamente con
  lo que `ds_guard.py` acepta.
- [ ] Ejecutar suite completa (`tools/tests/`, `tools/harmessi/tests/`, `tools/ds_init/tests/`)
  para confirmar sin regresión, y `harmessi doctor` para confirmar el mismo baseline de `[ERROR]`
  (capturar el valor exacto vigente al momento de correr, documentarlo en `verification.md`).

## Dependencias
`methodology.md.tmpl` no depende de código nuevo — consume conceptualmente lo ya construido en
Changes 1,3,5,6,7,8 (sin importar ni modificar ningún módulo Python). Las correcciones de
`SKILL.md`/`kdd.md`/`decision-ledger.md`/`verificador.md` son independientes entre sí, pueden ir
en paralelo. El fix de `production-readiness.md.tmpl`/`operations.md.tmpl` es independiente de
todo lo demás. Tests al final.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->
