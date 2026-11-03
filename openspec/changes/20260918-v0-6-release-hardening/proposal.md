# Propuesta — 20260918-v0-6-release-hardening

## Problema

Los Changes 0-4 de v0.6 (`reporting-core-contracts`, `reporting-governance`, `eda-profile`,
`report-evidence-manifest-validation`, `reporting-design-system-html`) están implementados,
revisados y cerrados individualmente. Falta consolidar la versión: número canónico `0.6.0`, estado
real del roadmap, regresión completa sobre las 10 suites, smokes de las garantías centrales del
reporting (aislamiento `exploratory`, `model_valid`, holdout, figura↔tabla, reproducibilidad del
manifest, HTML offline, tema), portabilidad, backward compatibility contra v0.5, sweep de
privacidad transversal y una revisión que mire el conjunto de v0.6.

Además hay una limitación conocida y vigente: el `plotly.js` REAL nunca se ejecutó. Toda la
verificación de figuras (HTML offline, dark en pantalla / light en `@media print`) se hizo con un
bundle FALSO. Por decisión del usuario no se instala Plotly ni ninguna dependencia nueva, así que
esa verificación sigue PENDIENTE y condiciona el resultado final de este Change.

## Objetivo

Cerrar v0.6 con el mismo rigor que los hardenings de v0.4 y v0.5: verificar, corregir solo
defectos de hardening, alinear versión/estado y emitir un veredicto explícito
`READY FOR v0.6.0 RELEASE` o `NOT READY FOR v0.6.0 RELEASE` con razones concretas y evidencia.

## Evidencia

- `docs/roadmap/v0.6.md` (sección "Change 5 — v0.6-release-hardening" y gate de release).
- `openspec/changes/20260917-v0-5-release-hardening/{proposal,spec,design,tasks}.md` y su
  `verification.md` (precedente de estructura y rigor).
- Los `verification.md` de los Changes 0-4 de v0.6 (evidencia individual ya cerrada).
- Restricción vigente del usuario (2026-09-21) sobre dependencias nuevas, transcripta abajo.

## Supuestos descartados

Que verificar con un bundle FALSO de figuras equivale a verificar con el `plotly.js` real. No
equivale: solo prueba la estructura del HTML (0 recursos externos, CSS de pantalla/impresión,
contratos figura↔tabla). El comportamiento del `plotly.js` real y de `Plotly.react` en
`beforeprint` no se verificó y se declara explícitamente como no verificado, no como verificado.

## Alcance

- Versión canónica: `tools/ds_init/version.py` (`HARNESS_VERSION`), `CITATION.cff` (`version`,
  `date-released`), `.ds_init/control.json` regenerado (siempre ÚLTIMO).
- Estado: `docs/roadmap/v0.6.md` (encabezado de estado y checklist del Change 5 solo si
  corresponde al cierre). No se tocan v0.7-v0.9 ni `docs/roadmap/README.md`.
- Verificación completa: 10 suites secuenciales, contract tests, scratch installs reales
  (`experiment` y `discovery`), smokes R7-R15, backward compatibility, sweeps de privacidad y
  portabilidad, `harmessi doctor`.
- Reviewer transversal sobre el conjunto de los 5 Changes de v0.6.
- Correcciones de hardening acotadas (solo si la verificación o el reviewer hallan defectos):
  `tools/reporting/**`, `ARCHITECTURE.md`, `tools/ds_init/manifest.py`,
  `tools/tests/test_architecture_boundaries.py`, `tools/tests/test_v06_core_neutrality.py`.
- `verification.md` del Change y los 4 artefactos SDD.

## Fuera de alcance

- Cualquier feature nueva.
- Instalar Plotly o cualquier dependencia nueva. Antes de cualquier `pip install` el Lead debe
  presentar al usuario 5 puntos: por qué es necesaria, si puede seguir opcional, qué
  contrato/dependencia agrega, alternativas sin dependencia, e impacto en instalación y backward
  compat.
- Push, merge a `main`, tag, GitHub Release y borrado de `v0.6-dev`: parada humana final.
- Documentar en README los comandos `python -m tools.reporting` (no pedido en este Change).

## Deuda declarada para v0.7+

README sin los comandos `python -m tools.reporting`; `.gitattributes -text` para `reports/**`
(riesgo `core.autocrlf` sobre bytes); ancla externa del hash del manifest; verificación con
`plotly.js` real; otros SO y CI; múltiples renderers; LLM-as-judge.

## Holdout policy (condicional — solo cambios "sensible")

No aplica — no se toca ningún dataset ni holdout; los smokes de holdout usan fixtures sintéticos
en directorios temporales y verifican que el acceso se deniega sin abrir.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-21
- Alcance aprobado: Change 5 — v0.6-release-hardening (`docs/roadmap/v0.6.md`)
- Versión de artefactos referenciada: esta versión de `proposal.md`/`spec.md`/`design.md`/
  `tasks.md` (commit de este Change).
- Cita o descripción fiel de qué se aprobó: "Ejecutá autónomamente Harmessi v0.6 completa: ...
  Change 5 — v0.6-release-hardening ... Para cada Change: audit → SDD → implementación → tests →
  reviewer → fixes → re-tests → verification → close → commit local"; "Resultado final
  obligatorio: READY FOR v0.6.0 RELEASE o NOT READY FOR v0.6.0 RELEASE con razones concretas";
  "NO instales Plotly ni ninguna dependencia nueva ... STOP y presentame [5 puntos]"; "No push. No
  merge. No tag. No release." (instrucciones explícitas del usuario, 2026-09-18 y 2026-09-21, bajo
  el Contrato de autonomía de `docs/roadmap/README.md`).
