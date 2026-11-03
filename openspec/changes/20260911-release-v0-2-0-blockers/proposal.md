# Propuesta — 20260911-release-v0-2-0-blockers

## Problema
Una auditoría final de release de Harmessi v0.2.0 encontró 1 BLOCKER real (confirmado empíricamente instalando en un repo Git temporal: `tools/dsguard/decision.py` no tiene entrada en `MANIFEST`, por lo que `ds_guard.py` falla con `ImportError` al primer uso en cualquier proyecto instalado desde `main`) y 4 hallazgos IMPORTANTES (versión declarada `0.1.0` en `version.py`/`CITATION.cff` pese a ser el release v0.2.0; `README.md` desactualizado, no menciona `ds_profile`; `SKILL_lead_data_scientist.md.tmpl` no propaga las referencias a `ds_profile`/Project EDA que sí tiene `SKILL.md` real; `CLAUDE.md.tmpl` con el mismo gap) más 1 hallazgo MENOR (`test_decision.py`/`test_remediation.py` sin documentar en `EXCLUSIONES_PERMANENTES`).

## Objetivo
Corregir el BLOCKER y los hallazgos IMPORTANTES/MENOR mínimos necesarios para que v0.2.0 quede lista para taggear, sin agregar features nuevas ni refactorizar fuera de alcance.

## Evidencia
- Auditoría de release (mensaje del usuario en el chat), citando hallazgos B1 (blocker), C1-C4 (importantes), D1 (menor).
- `tools/ds_guard.py:34`: `from dsguard import core, decision, kdd, notebooks, repo, sdd`.
- `tools/ds_init/manifest.py`: sin ninguna entrada `decision.py` entre las de `tools/dsguard/`.
- Instalación real en scratch repo (corrida por el Lead durante la auditoría): `ImportError: cannot import name 'decision' from 'dsguard'` al correr `ds_guard.py status`.
- `tools/ds_init/version.py:13`: `HARNESS_VERSION = "0.1.0"`. `CITATION.cff:5`: `version: 0.1.0`.
- `README.md`: sección de capacidades sin mención de `ds_profile`.
- `diff .claude/skills/lead-data-scientist/SKILL.md tools/ds_init/profiles/python_jupyter_data/templates/SKILL_lead_data_scientist.md.tmpl`: los 2 párrafos de `ds_profile`/`eda.md` del Bloque 6 ausentes del `.tmpl`.

## Supuestos descartados
No aplica — la corrección fue especificada exacta por el usuario.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica: no es un cambio metodológico.

## Alcance
1. Agregar `tools/dsguard/decision.py` a `MANIFEST` (`tools/ds_init/manifest.py`), mismo patrón VERBATIM que sus módulos hermanos (`core.py`, `repo.py`, `sdd.py`, `kdd.py`, `notebooks.py`).
2. Agregar/ajustar tests que detecten específicamente esta omisión para `decision.py` (no un scanner genérico de imports vs. manifest — eso es deuda futura explícita).
3. `tools/ds_init/version.py`: `HARNESS_VERSION = "0.2.0"`.
4. `CITATION.cff`: `version: 0.2.0`, `date-released: 2026-09-11`.
5. `README.md`: reflejar 3 CLIs (installer/`ds_init`, `harmessi doctor`, `ds_profile`) y agregar descripción breve de `ds_profile` + Project EDA (output `.harmessi/profiles/<profile_id>/profile.json`, CSV stdlib, Parquet opcional vía pyarrow). Sin documentar features de v0.3 como si existieran.
6. Propagar a `tools/ds_init/profiles/python_jupyter_data/templates/SKILL_lead_data_scientist.md.tmpl` las referencias a `ds_profile`/Project EDA que ya tiene `.claude/skills/lead-data-scientist/SKILL.md`, preservando los placeholders de plantilla existentes (ej. `{{NOMBRE_PROYECTO}}`).
7. Actualizar `tools/ds_init/profiles/python_jupyter_data/templates/CLAUDE.md.tmpl` (sección del harness instalado) para incluir `ds_profile`/Project EDA/`eda.md`, sin agregar Reporting/CRISP-DM nuevo/`project_stage`/otras capacidades de v0.3.
8. Agregar `tools/tests/test_decision.py` y `tools/tests/test_remediation.py` a `EXCLUSIONES_PERMANENTES` si corresponde al criterio ya usado ahí (archivos de test de desarrollo sin entrada en `MANIFEST`).
9. Verificación empírica final: instalación real en un repo Git temporal descartable, confirmando `ds_guard.py status` sin `ImportError`, decision ledger cargable, versión estampada 0.2.0, y que el `SKILL.md`/`CLAUDE.md` instalados mencionen `ds_profile`/Project EDA.

## Fuera de alcance
`nbrunner/*` y `.gitignore` (salvo que la validación revele un problema funcional real). Scanner genérico de imports vs. manifest. Cualquier feature de v0.3 (Reporting, CRISP-DM nuevo, `project_stage`, `discovery`/`production_candidate`/`production`, `risk_level`, Impact Preflight, scope isolation, portable core, multi-provider). No se hace commit/tag/push en este cambio.

## Holdout policy (condicional — solo cambios "sensible")
No aplica.

## Impacto en production-readiness (opcional)
No aplica.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
- [ ] `tools/dsguard/decision.py` tiene entrada `VERBATIM` en `MANIFEST`, mismo patrón que sus hermanos.
- [ ] Test nuevo detecta específicamente si `decision.py` (u otro módulo que `ds_guard.py` importe a nivel de módulo desde `dsguard`) queda sin entrada en `MANIFEST` — falla si se repite esta omisión puntual.
- [ ] Instalación real en scratch repo: `ds_guard.py status` corre sin `ImportError`; algún comando de `decision` (ej. `ds_guard.py decision list`) también corre sin `ImportError`.
- [ ] `HARNESS_VERSION` = `"0.2.0"`; `CITATION.cff` con `version: 0.2.0` y `date-released: 2026-09-11`; instalación real en scratch repo estampa `0.2.0` en `CLAUDE.md`/`.ds_init/control.json`.
- [ ] `README.md` menciona los 3 CLIs y describe `ds_profile`/Project EDA sin prometer nada de v0.3.
- [ ] `SKILL_lead_data_scientist.md.tmpl` y `CLAUDE.md.tmpl` instalados en el scratch repo mencionan `ds_profile`/`eda.md`/Project EDA.
- [ ] `EXCLUSIONES_PERMANENTES` incluye `test_decision.py`/`test_remediation.py` si corresponde.
- [ ] Toda la regresión existente (`tools/ds_profile/tests`, `tools/tests`, `tools/ds_init/tests`, `tools/harmessi/tests`, `check_manifest_parity`, `harmessi doctor`) sigue en verde.

## Decisión técnica (design-lite — solo SDD abreviado)
Cambios puntuales y localizados, sin tocar el resto del diseño de ningún bloque anterior. `tools/ds_init/manifest.py`: una `EntradaManifiesto` nueva para `decision.py`, mismo bloque donde están sus hermanos (`core.py`/`repo.py`/`sdd.py`/`kdd.py`/`notebooks.py`). Test de la omisión: agregar (en `tools/ds_init/tests/` o `tools/tests/`, el implementador decide el archivo más apropiado según convención existente) un test explícito que confirme que cada módulo `dsguard/*.py` importado por `ds_guard.py` a nivel de módulo tiene su entrada en `MANIFEST` — acotado a esta verificación puntual, no un scanner genérico reusable para todo el repo (eso es deuda futura). `version.py`/`CITATION.cff`: edición de constante/campo, sin lógica nueva. `README.md`/`SKILL_lead_data_scientist.md.tmpl`/`CLAUDE.md.tmpl`: edición de prosa, preservando estructura y placeholders existentes — copiar el contenido real de `SKILL.md` para las 2 secciones nuevas, no redactar una versión distinta.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-11
- Alcance aprobado: los 9 puntos de "## Alcance" arriba, exactamente como los especificó el usuario.
- Versión de artefactos referenciada: primer borrador de `proposal.md`/`tasks.md` de este cambio.
- Cita o descripción fiel de qué se aprobó: *"Corregí únicamente los hallazgos mínimos de la auditoría final necesarios para dejar Harmessi v0.2.0 READY. No agregues features nuevas. No refactorices fuera de alcance. No hagas tag ni push. Usá el flujo SDD normal y mantené el cambio acotado."*, con el detalle punto por punto de las secciones 1 a 6 más "Validación final obligatoria" de ese mensaje.

## Motivo de rechazo
No aplica.

## Desacuerdo registrado
No aplica.
