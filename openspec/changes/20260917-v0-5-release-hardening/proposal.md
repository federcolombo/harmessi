# Propuesta — 20260917-v0-5-release-hardening

## Problema

Los Changes 0-4 de v0.5 (`multi-provider-adapters`, `harmessi-bench`, `provider-routing`,
`fallback-and-handoffs`, `cross-provider-hardening`) están implementados, revisados y cerrados
individualmente, cada uno con su propio `verification.md`. Pero falta consolidar la versión: número
canónico, documentación pública de las 4 capacidades nuevas (`providers`/`routing`/`fallback`/
`harmessi-bench`), regresión completa final sobre las 9 suites del repo, evidencia real de evals
mínimas, smoke cross-provider/routing/fallback, backward compatibility contra v0.4, sweep de
privacidad transversal, y una revisión final que mire el conjunto de v0.5, no cada Change por
separado.

## Objetivo

Cerrar v0.5 con el mismo rigor que el hardening de v0.4
(`openspec/changes/20260917-v0-4-release-hardening`): versión consistente, suites completas, evals
mínimas, smoke cross-provider/routing/fallback, backward compatibility, scratch installs,
privacidad/portabilidad, docs/release notes, reviewer transversal, regeneración final de
`.ds_init/control.json`, `harmessi doctor` sin `[ERROR]`.

## Evidencia

- `docs/roadmap/v0.5.md` (roadmap de la versión, sección "Change 5 — v0.5-release-hardening", gate
  de release explícito).
- `openspec/changes/20260917-v0-4-release-hardening/verification.md` (precedente de formato y
  rigor exacto a replicar: R1-R7, evidencia real de suites/scratch installs/doctor/control.json).
- `openspec/changes/20260917-multi-provider-adapters/verification.md`,
  `openspec/changes/20260917-harmessi-bench/verification.md`,
  `openspec/changes/20260917-provider-routing/verification.md`,
  `openspec/changes/20260917-fallback-and-handoffs/verification.md`,
  `openspec/changes/20260917-cross-provider-hardening/verification.md` (los 5 `verification.md` ya
  reales de los Changes 0-4 de v0.5, cada uno con su propia evidencia de tests/smoke/reviewer).

## Supuestos descartados

Que hace falta registrar `tools/providers/`, `tools/routing/`, `tools/fallback/` y
`tools/harmessi_bench/` en el manifiesto de instalación de `tools/ds_init/` para que un proyecto
instalado los reciba. Descartado tras verificar que `tools/harmessi/cli.py` (el CLI base de
`harmessi doctor`, ya existente desde v0.2-v0.4) NUNCA estuvo en ese manifiesto tampoco: es un
patrón ya establecido en este repo que ciertas herramientas (`harmessi doctor`, y ahora sus
subcomandos nuevos `providers`/`routing`/`fallback`, más el CLI separado `harmessi_bench.cli`) se
corren directamente desde un checkout de Harmessi, no se instalan en el proyecto destino. Se
documenta explícitamente acá para que no quede como un gap sin explicar.

## Alcance

- Versión canónica: `tools/ds_init/version.py` (`HARNESS_VERSION`), `CITATION.cff` (`version`,
  `date-released`).
- Documentación: `README.md` (4 subsecciones nuevas en `## Commands`), `docs/roadmap/v0.5.md`
  (checklist + resumen por Change).
- Regresión completa final + evidencia de evals/smoke/backward-compat/privacidad, aportada por el
  Lead en una invocación posterior y volcada en `verification.md`.
- Reviewer transversal sobre el conjunto de v0.5 (los 5 Changes juntos, no cada uno por separado).
- Regeneración final de `.ds_init/control.json` de este propio repo.
- `harmessi doctor` final sin `[ERROR]`.
- Los 4 artefactos SDD de este propio Change 5.

## Fuera de alcance

- Cualquier feature nueva (este Change es hardening puro).
- Instalar Codex CLI, Gemini CLI o Grok CLI (siguen sin binario real en este entorno).
- Tag, push, GitHub Release o merge a `main` — explícitamente prohibido por el usuario en este
  Change, requiere aprobación humana final y separada.

## Holdout policy (condicional — solo cambios "sensible")

No aplica — este Change no toca ningún dataset ni holdout de un proyecto DS, es hardening de
release del harness.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-17
- Alcance aprobado: Change 5 — v0.5-release-hardening
- Versión de artefactos referenciada: esta versión de `proposal.md`/`spec.md`/`design.md`/
  `tasks.md`, commit baseline `a042ee683e8638cd637c63ae2c68cc50540df479` (rama `v0.5-dev`).
- Cita o descripción fiel de qué se aprobó: mismo formato de aprobación ya usado en los Changes
  0-4 de v0.5 y en el hardening de v0.4 — el usuario aprobó ejecutar el gate de release de v0.5
  (versión, docs, suites completas, evals mínimas, smoke cross-provider/routing/fallback, backward
  compatibility, scratch installs, privacidad transversal, reviewer transversal, regeneración de
  `control.json`, `harmessi doctor` final), sin features nuevas, sin tag/push/GitHub Release/merge
  a `main` hasta una aprobación humana explícita y separada para publicar.
