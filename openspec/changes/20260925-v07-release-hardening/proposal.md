# Propuesta — 20260925-v07-release-hardening

## Problema

Los Changes 0-4 de v0.7 (`data-contracts-core`, `data-contract-validation`,
`model-quality-policies`, `quality-evidence-and-drift`, `quality-integration-and-cli`) están
implementados, revisados y cerrados individualmente, cada uno con su propio `verification.md` y su
propio alcance de regresión (nunca el repo completo). Falta consolidar la versión: regresión
completa del repo (`pytest tools -q`, alcance deliberadamente reservado para este Change, ver
`openspec/changes/20260922-quality-integration-and-cli/verification.md:20-23`), un smoke de
"reporting consumption" que hoy no existe como test explícito, confirmación de que el smoke de
impact preflight ya escrito alcanza, scratch installs frescos con el manifest de v0.7 completo,
backward compatibility formal contra `v0.6.0`, sweep de privacidad sobre todo el diff de v0.7,
paridad de manifest y Doctor sin `ERROR`, y un veredicto final explícito.

## Objetivo

Cerrar v0.7 con el mismo rigor que los hardenings de v0.4-v0.6: verificar el gate candidato
completo de `docs/roadmap/v0.7.md` ("Change 5 — v0.7-release-hardening"), corregir solo defectos de
hardening, y emitir un veredicto explícito `READY FOR v0.7.0 RELEASE` o
`NOT READY FOR v0.7.0 RELEASE` con razones concretas y evidencia real.

## Evidencia

- `docs/roadmap/v0.7.md:393-428` (sección "Change 5 — v0.7-release-hardening": "Sin features
  nuevas", gate candidato completo, resultado final obligatorio).
- `docs/roadmap/README.md:21-52` (contrato de autonomía: `audit → SDD → implementación → tests →
  reviewer → fixes → re-tests → verification → close`; 10 motivos de parada; máximo 2 ciclos
  writer↔reviewer).
- `openspec/changes/20260918-v0-6-release-hardening/{proposal,spec,design,tasks,verification}.md`
  (precedente exacto del mismo tipo de Change en este repo: estructura, nivel de detalle, y qué
  significa "sin features nuevas" en la práctica — permite fixtures/smokes de test y el propio
  `verification.md`; prohíbe cualquier cambio de comportamiento de producción).
- `openspec/changes/20260922-data-contracts-core/verification.md:5-18` (Change 0: 218 passed + 28
  subtests en la suite propia; regresión completa en ese momento 2108 passed/10 skipped/709
  subtests/0 failed; 0 hallazgos del reviewer).
- `openspec/changes/20260922-data-contract-validation/verification.md:5-21` (Change 1: 307
  passed/5 skipped/32 subtests; regresión 2180 passed/10 skipped/709 subtests; 3 hallazgos no
  bloqueantes, 1 ciclo de remediación de 2).
- `openspec/changes/20260922-model-quality-policies/verification.md:5-17` (Change 2: 416
  passed/28 subtests; regresión 2306 passed/10 skipped/709 subtests; 0 hallazgos bloqueantes, 0
  ciclos de remediación de revisión usados).
- `openspec/changes/20260922-quality-evidence-and-drift/verification.md:3-41` (Change 3: 2 bugs
  reales pre-revisión, uno de ellos rompía toda instalación real de `ds_init` por el patrón
  `{{n}}` en mensajes de error; regresión final 2410 passed/10 skipped/709 subtests/0 failed; 1
  hallazgo bloqueante de privacidad y 1 no bloqueante, ambos resueltos en 1 ciclo de remediación).
- `openspec/changes/20260922-quality-integration-and-cli/verification.md:1-64` (Change 4: 648
  passed/28 subtests sobre el alcance exacto del SDD, SIN correr `pytest tools -q` completo por
  decisión explícita del Lead — ese alcance "queda reservado como gate obligatorio de Change 5"; 0
  hallazgos bloqueantes, 1 ciclo de remediación de 2; cero diff confirmado en 7 rutas críticas de
  no-alteración de readiness/promote/status).
- `ARCHITECTURE.md:57-64,138-199` (reglas 7-9 de dirección de dependencias de las 3 familias
  nuevas de v0.7, ya verificadas Change a Change; ninguna regla nueva se agrega en Change 5).
- `tools/reporting/evidence.py:249-263` (`describe_source(repo_root, path, ...)` puede hashear
  cualquier archivo del repo por path, incluido un manifest de `qualityevidence`, sin importar ese
  paquete — confirma en código la integración descrita en `ARCHITECTURE.md:192-194`).
- `tools/tests/test_ds_guard_contract_quality_cli.py:234-257` (`TestContractImpact`: 2 tests ya
  existentes de `contract impact`, `test_staged_potentially_affected` y
  `test_texto_vocabulario_potentially_affected` — smoke de integración con impact ya cubierto).
- Búsqueda de `tools/tests/test_v07_*.py` (glob): existen `test_v07_core_neutrality.py`,
  `test_v07_validation_neutrality.py`, `test_v07_modelquality_neutrality.py`,
  `test_v07_qualityevidence_neutrality.py`, `test_v07_evolution_neutrality.py`,
  `test_v07_readiness_promote_status_no_alteration.py`; NINGUNO cubre explícitamente un smoke de
  "reporting consumption" (`reporting.evidence.describe_source` sobre un manifest sintético de
  `qualityevidence`) ni un smoke de neutralidad agregado de las 3 familias nuevas de v0.7 en
  conjunto.
- Búsqueda en `tools/reporting/tests/` (glob de 10 archivos): ninguno referencia
  `qualityevidence`, `datacontracts` ni `modelquality` — confirma que el smoke de consumo cruzado
  no existe hoy.

## Supuestos descartados

Que la regresión de cada Change individual (alcance acotado a las rutas de ese SDD) equivale a
"regresión completa del repo". No equivale: Change 4 corrió 648 tests sobre su propio alcance y
dejó explícito por escrito que `pytest tools -q` completo queda reservado para este Change 5
(`openspec/changes/20260922-quality-integration-and-cli/verification.md:20-23`).

Que el smoke de `TestContractImpact` ya escrito (Change 4) cubre "integración con impact" de forma
suficiente para el gate de release. Se mantiene el supuesto de que SÍ alcanza (2 tests concretos,
vocabulario "potentially affected" verificado), pero queda como decisión explícita de este SDD, no
implícita — ver `design.md`.

## Alcance

- Verificación completa del gate candidato de `docs/roadmap/v0.7.md:397-420` (ver `spec.md` R1-R20
  para el desglose exacto ítem por ítem).
- Un smoke NUEVO de "reporting consumption": `tools/tests/test_v07_release_hardening_smoke.py`,
  que instancia `reporting.evidence.describe_source` sobre un manifest sintético de
  `qualityevidence` (`QualityEvidenceManifest`/`build_manifest`/`write_manifest` de Change 3),
  confirmando hash correcto y ausencia de import cruzado entre `tools.reporting` y
  `tools.qualityevidence`.
- Un smoke NUEVO de neutralidad agregada: en el mismo archivo, una verificación de que
  `tools.datacontracts`, `tools.modelquality` y `tools.qualityevidence` en conjunto siguen sin ser
  importados por `dsguard`/`ds_profile`/`dsimpact`/`reporting`/`providers`/`routing`/`fallback`/
  `harmessi_bench` (agregado sobre los 5 tests de neutralidad ya existentes, que verifican cada
  familia por separado, nunca las 3 juntas contra el mismo universo de paquetes).
- Scratch installs frescos (`experiment` y `discovery`) vía `tools/ds_init`, ejecutados por el Lead
  en el scratchpad de la sesión, confirmando que las ~9 entradas VERBATIM nuevas de Changes 0-4
  quedan instaladas.
- Backward compatibility formal contra `v0.6.0` (`git diff --stat v0.6.0..HEAD` sobre las rutas de
  Changes anteriores a v0.7).
- Sweep de privacidad transversal sobre todo el diff de v0.7.
- Paridad de manifest y `harmessi doctor` sobre el estado final.
- Reviewer transversal sobre el conjunto de los 5 Changes de v0.7 (no repite revisiones
  individuales).
- Correcciones de hardening acotadas (solo si la verificación o el reviewer hallan defectos):
  `tools/datacontracts/**`, `tools/modelquality/**`, `tools/qualityevidence/**`,
  `tools/ds_guard.py`, `ARCHITECTURE.md`, `docs/roadmap/v0.7.md` (solo estado/checklist del Change
  5), `tools/tests/test_v07_release_hardening_smoke.py`, `tools/ds_init/manifest.py` (solo si una
  corrección de hardening agrega/renombra un archivo).
- `verification.md` del Change y los 4 artefactos SDD.

## Fuera de alcance

- Cualquier feature nueva.
- Cualquier cambio de comportamiento de `tools/datacontracts/*`, `tools/modelquality/*`,
  `tools/qualityevidence/*`, `tools/ds_guard.py` más allá de una corrección puntual de hardening.
- Tocar `dsguard/status.py`, `dsguard/readiness.py`, `dsimpact/*`, `reporting/*` (salvo el smoke
  nuevo en `tools/tests/`, que no modifica ningún archivo de esos paquetes).
- Instalar Great Expectations, Pandera o cualquier dependencia nueva (decisión 8 del roadmap; sin
  necesidad identificada en este Change, a diferencia del hardening de v0.6 con Plotly).
- Documentar en README los subcomandos `ds_guard.py contract`/`quality` (decisión de diseño,
  ver `design.md`; se difiere como deuda para v0.8/v0.9, mismo patrón que la deuda de
  `python -m tools.reporting` declarada en el hardening de v0.6).
- Actualizar número de versión canónico (`tools/ds_init/version.py`, `CITATION.cff`) y regenerar
  `.ds_init/control.json`: fuera de esta invocación 1 (redacción de SDD); si el veredicto final es
  `READY`, esa alineación de versión es tarea de una invocación posterior de este mismo Change,
  igual que en v0.6 (invocación 2 de
  `openspec/changes/20260918-v0-6-release-hardening/tasks.md:9-11`), pero **no se toca
  `control.json`** en esta invocación 1.
- Push, merge a `main`, tag, GitHub Release y borrado de `v0.7-dev`: parada humana final.

## Holdout policy (condicional — solo cambios "sensible")

No aplica — no se toca ningún dataset ni holdout real; el smoke de "reporting consumption" y el de
neutralidad agregada usan fixtures 100% sintéticos y genéricos (sin datos reales, dominios ni
organizaciones particulares, según exige `docs/roadmap/v0.7.md:422-423`) en directorios temporales.
Los smokes de holdout/scientific-governance que consolida el gate (Change 1
`ds_profile.holdout_guard.verificar_permitido`, Change 3 `drift_from_profiles`) ya están cubiertos
por Changes anteriores; este Change solo confirma que siguen verdes, sin abrir ningún holdout.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-25
- Alcance aprobado: Change 5 — v0.7-release-hardening (`docs/roadmap/v0.7.md`)
- Versión de artefactos referenciada: esta versión de `proposal.md`/`spec.md`/`design.md`/
  `tasks.md` (commit de esta invocación).
- Cita o descripción fiel de qué se aprobó: encargo del usuario al Lead (2026-09-25) para
  "redactar (NO código todavía, salvo fixtures/tests explícitamente de hardening que el propio SDD
  decida) los 4 artefactos SDD del Change 5 de v0.7 (`v0.7-release-hardening`) ... NO toques
  `control.json`", con el gate candidato completo de `docs/roadmap/v0.7.md` como alcance a
  redactar y el resultado final obligatorio `READY FOR v0.7.0 RELEASE` /
  `NOT READY FOR v0.7.0 RELEASE`; bajo el Contrato de autonomía de `docs/roadmap/README.md`
  ("Para cada Change: `audit → SDD → implementación → tests → reviewer → fixes → re-tests →
  verification → close`. No pedir confirmación humana entre pasos normales.").
