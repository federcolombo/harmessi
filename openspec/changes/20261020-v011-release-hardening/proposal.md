# Propuesta — 20261020-v011-release-hardening

> Change 6 de v0.11 (Operational Robustness & Recovery): integración y release hardening. Sin features nuevas.

## Problema
Los Changes 1–5 se cerraron con evidencia local (tests dirigidos, en release train mode por restricciones de memoria). Antes de publicar `v0.11.0` hace falta: versión, notas de release, smoke de release, baseline managed coherente, Doctor final, barrido de privacidad, dogfooding reproducible (proyecto nuevo, upgrade desde el tag público `v0.10.0`, upgrade interrumpido con recovery) y la regresión completa que se difirió.

## Objetivo
Dejar el candidato `0.11.0` verificado de extremo a extremo y publicarlo (main fast-forward, tag anotado `v0.11.0`, push de main y del tag, GitHub Release si `gh` está disponible), sin publicar `v0.11-dev`.

## Evidencia
Verifications de Changes 0–5; tag público `v0.10.0` (d55e440 → 2e76956); roadmap `docs/roadmap/v0.11.md`.

## Alcance
Versión `0.11.0` (`tools/ds_init/version.py`, `CITATION.cff`, README), `docs/releases/v0.11.0.md` (inglés), actualización de roadmaps, smoke `test_v011_release_hardening_smoke.py` y adaptación de smokes anteriores que fijan la versión, regeneración única de `.ds_init/control.json`, regresión completa en batches seriales (P=1) con ledger, dogfooding A/B/C con fixtures sintéticos, Doctor final, privacidad, correctivos técnicos mínimos que revele la regresión.

## Fuera de alcance
Features nuevas, cambios de contratos congelados, H1/hook, deudas diferidas del roadmap, CI cross-platform, v0.12.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- tools/**
- .claude/skills/**
- .claude/agents/**
- docs/**
- README.md
- CITATION.cff
- ARCHITECTURE.md
- .ds_init/control.json
- .gitignore
- openspec/changes/20261020-v011-release-hardening/**
- openspec/decisions/ledger.jsonl

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
