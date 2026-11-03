# Propuesta — 20261026-v015-public-docs-evals

## Problema
Seis deudas de readiness pública siguen abiertas (matriz v0.15, B-26..B-30 y B-34):

- B-26: existe una suite sintética (`tools/harmessi_bench/suites/harmessi-core-synthetic.*`, 9 casos, scorers deterministas) pero no hay doc de evaluación ni baseline documentado (versión de suite, casos, formato de resultado, límites de reproducibilidad); `run` exige un provider real y no hay forma pública de correr offline (FakeAdapter solo en tests).
- B-27: faltan docs públicas como documento propio: installation, upgrade, concepts, CLI reference, skills, governance, evaluation, harness improvement, troubleshooting, security/trust limitations, release process; README no menciona `python -m tools.reporting`; ARCHITECTURE §4/§4.1 lista como deuda cosas ya resueltas; `verificador.md` no documenta `SKILL-TRAZA-SECCION-DUPLICADA` (detectado en `tools/dsguard/skill_contract.py:429-436`).
- B-28: Doctor solo corre desde un checkout (`--destino <proyecto>`); un proyecto instalado no incluye `tools/harmessi` ni `tools/ds_init`; sin requisitos documentados (Python >= 3.9, sin pyproject/requirements).
- B-29: no hay runbook de release reproducible.
- B-30: CI (`.github/workflows/portability-smoke.yml`: checkout@v5, setup-python@v6, Python 3.12) sin observación remota.
- B-34: no existe `.gitattributes`; con `core.autocrlf=true` los fixtures byte-exact (MANIFEST sha256, compat v0_11..v0_14, golden_*.json, templates de ds_init) pueden romper los hashes en un clone Windows.
<!-- qué problema motiva este cambio -->

## Objetivo
Cerrar o reclasificar con evidencia B-26..B-30 y B-34: documentación pública derivada del código y verificada por un test de consistencia, `.gitattributes` mínimo, runbook de release y límites explícitos donde no hay observación (CI remoto, baseline numérico).
<!-- qué se busca lograr, en una frase -->

## Evidencia
- Auditoría de solo lectura del Lead (2026-10-26): README.md:170-257,369,534-636; ARCHITECTURE.md:340,373,399,769-775; `tools/harmessi/doctor.py:62,1820`; `tools/dsguard/skill_contract.py:429-436`; `tools/harmessi_bench/suites/`; `.github/workflows/portability-smoke.yml`; `tools/ds_init/manifest.py:221`.
- `docs/roadmap/v0.15.md` §C6; `docs/roadmap/v0.15-debt-matrix.md` B-26..B-30, B-34; `docs/versioning.md`; `docs/providers.md`.
- `git config core.autocrlf` = true en el checkout de desarrollo (Windows).
<!-- archivo:línea o notebook/celda citados — nunca de memoria -->

## Supuestos descartados
- «Se puede publicar un baseline numérico»: no; `run` requiere provider real y solo hay un host live-validado (claude_code); inventar o medir una sola muestra como baseline sería sobre-afirmar. Se documenta el baseline como configuración reproducible (suite_version, suite_hash, casos, formato) sin scores, y el límite se declara.
- «Doctor puede correr desde el proyecto instalado»: no sin copiar `tools/harmessi` y `tools/ds_init` al destino (cambio de manifest/baseline fuera de alcance); se documenta el requisito.
- «El CI remoto se puede observar»: sin `gh` ni remoto observable en esta sesión; queda «pending observation» (C7).
<!-- qué se creía y la exploración desmintió -->

## Hipótesis (condicional — solo cambios metodológicos)
<!-- qué se espera confirmar/descartar, si el cambio prueba una hipótesis concreta -->

## Alcance
- A (B-34): `.gitattributes` mínimo con `eol=lf` para fixtures byte-exact, golden y templates de ds_init (sin `* text=auto` global que cambie el resto del repo).
- B (B-27/B-28): documentos nuevos bajo `docs/`: `installation.md` (requisitos, instalación, Doctor desde checkout vs proyecto instalado, upgrade, troubleshooting), `concepts.md` (conceptos, skills, governance, harness improvement), `cli-reference.md` (derivado de los parsers argparse), `evaluation.md` (B-26), `security-and-trust.md`, `release-process.md` (B-29); README con índice de docs y `python -m tools.reporting`; ARCHITECTURE §4/§4.1 actualizada (resuelto vs vigente); `verificador.md` y su template documentan `SKILL-TRAZA-SECCION-DUPLICADA`.
- C (B-26): `docs/evaluation.md` con suite_id/suite_version/suite_hash/casos reales leídos de los JSON, formato de `result.json`, verdicts de compare, límites de reproducibilidad, cómo correr (requiere provider real; sin comando offline público), y explícitamente: sin baseline numérico publicado.
- D (B-30): documentar el estado de CI y dejar «pending observation» (sin cambiar versiones de acciones sin observarlas).
- E: test `tools/tests/test_public_docs.py`: existencia de los docs requeridos, enlaces relativos de README/docs resolubles, `cli-reference.md` menciona cada subcomando de `ds_guard`, `evaluation.md` coincide con suite_version/suite_hash/case_ids reales, `.gitattributes` cubre los paths byte-exact.
- F: matriz de deuda y roadmap §C6.

## Fuera de alcance
- Publicar scores o baseline numérico; LLM-as-judge; leaderboard; datos privados.
- Copiar `tools/harmessi`/`tools/ds_init` a proyectos instalados (cambia manifest y baseline; C7 gestiona el baseline).
- Cambiar versiones de acciones de CI sin observación; agregar Python 3.9 a la matriz sin poder verificarlo.
- Versión 0.15.0 y baseline de hashes managed (C7).

## Holdout policy (condicional — solo cambios "sensible")
<!-- si el cambio toca o podría tocar un holdout/dataset sellado: acceso solicitado, por qué, qué
decisión depende de eso, y la autorización del usuario transcripta literal (ver SKILL.md,
categoría "Sensible") -->

## Impacto en production-readiness (opcional)
<!-- nota libre; pasa a condicional cuando esa etapa KDD se active en un bloque futuro -->

## Criterios de aceptación (spec-lite — solo SDD abreviado)
<!-- en SDD completo, ver spec.md en su lugar -->

## Decisión técnica (design-lite — solo SDD abreviado)
<!-- en SDD completo, ver design.md en su lugar -->

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado
- docs/**
- README.md
- ARCHITECTURE.md
- .gitattributes
- tools/tests/test_public_docs.py
- tools/ds_init/profiles/python_jupyter_data/templates/verificador.md.tmpl
- .claude/skills/lead-data-scientist/verificador.md
- tools/tests/test_skill_methodology.py
- tools/tests/test_skill_contract.py
<!-- opcional: rutas que este Change puede tocar, una por línea como `- ruta` o `- dir/**`
(repo-relativas, sin `..`, sin rutas absolutas ni comodines repo-wide). Al aprobar proposal.md,
ds_guard las materializa en control.json junto con los artefactos por defecto del Change;
queda ligado al hash de la propuesta aprobada. Sin bullets, el alcance no se modifica. -->

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
