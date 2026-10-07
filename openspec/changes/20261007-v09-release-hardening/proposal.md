# Propuesta — 20261007-v09-release-hardening

> Change 5 de v0.9 (último): integración final, consistencia y release readiness de `v0.9-dev`. NO agrega features. Sin push, tag, merge a
> `main` ni GitHub Release.

## Problema
`v0.9-dev` reúne Changes 0–4 y Correctives A/B/C, pero la versión canónica sigue en 0.8.0, el roadmap v0.9 está desactualizado (dice «ningún
Change implementado»), no hay notas de release ni documentación pública de las capacidades de v0.9, y el contenido versionado conserva restos de
privacidad (un nombre de archivo de feedback real en 4 documentos y una ruta personal de usuario en una propuesta histórica).

## Objetivo
Dejar `v0.9-dev` READY TO RELEASE v0.9.0: versión coherente, roadmap/docs/release notes honestos, sweep de privacidad limpio, matriz de
instalación/adopción y E2E de Cards verificados, correctives revalidados y UNA regresión global final.

## Evidencia (audit 2026-10-07)
- Estado: 56 Changes bajo `openspec/changes`; los de v0.9 (Changes 0–4, Correctives A/B/C y exec-approval-registration) están `cerrada`; los 6
  `en_progreso` (v0.3/v0.4) son históricos preexistentes y no pertenecen a v0.9. `origin` solo `main`; `v0.9-dev` local; sin tag v0.9.
- Versión: `tools/ds_init/version.py` (`HARNESS_VERSION`), `CITATION.cff` (`version`, `date-released`), `.ds_init/control.json` (`version` + hashes),
  `docs/roadmap/README.md` y `v0.9.md` (convención de `d0cbd1b`, release de v0.8.0).
- Privacidad (sweep sobre 731 archivos tracked): `segmentacion-pc` en `docs/roadmap/v0.9.md` y las propuestas de Corrective A/B/C;
  `/c/Users/<usuario>/` en `20260917-multi-provider-adapters/proposal.md`. `fijaciones_granos`, `planes_comerciales`, emails y tokens: sin hallazgos
  (los valores tipo credencial son fixtures de tests del scanner).
- Cobertura existente de la matriz de instalación: `tools/ds_init/tests/test_cards_capabilities.py` (default, `data_cards`, `model_governance`,
  inválido sin escribir, sync sin reactivación implícita); Cards/reporting/Doctor E2E en `tools/cards/tests`, `tools/harmessi/tests`,
  `tools/reporting/tests`.

## Supuestos descartados
«Hay que tocar subsistemas para el release»: no; solo versión, documentación, sanitización y un smoke de release. «Subir TOOL_VERSION de
ds_profile / versiones de algoritmo con Harmessi»: no, tienen versionado independiente.

## Alcance
Versión canónica 0.9.0 (`version.py`, `CITATION.cff`, `.ds_init/control.json` regenerado UNA vez al final, `docs/roadmap/README.md`); roadmap
v0.9/v0.10; README (sección acotada de v0.9); `docs/releases/v0.9.0.md`; sanitización de privacidad y `.gitignore` de `docs/feedback/`; un smoke de
release (`tools/tests/test_v09_release_hardening_smoke.py`); verificación E2E de matriz/adopción/Cards/reporting/inercia/correctives con los tests
existentes y una corrida real de instalación en directorios temporales; UNA regresión global.

## Fuera de alcance
Features nuevas, cambios de contrato, nuevas dependencias, push/tag/merge/Release, re-audit de Changes históricos, subir versiones internas de
componentes.

## Principios
Sin feature creep; fail-closed; honestidad (Harmessi gobierna evidencia: no afirma ético, justo, seguro, privado ni conforme); sin datos de
proyectos reales en material público.

## Deudas
Las de `docs/roadmap/v0.10.md` (consolidadas, sin las ya resueltas).

## Criterios de cierre
Ver spec.md.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- openspec/changes/20261007-v09-release-hardening/**
- openspec/changes/20260917-multi-provider-adapters/proposal.md
- openspec/changes/20261005-operational-autonomy-hardening/proposal.md
- openspec/changes/20261006-sdd-parsers-and-guardrail-ownership/proposal.md
- openspec/changes/20261007-ds-profile-bounded-memory/proposal.md
- docs/roadmap/v0.9.md
- docs/roadmap/v0.10.md
- docs/roadmap/README.md
- docs/releases/**
- README.md
- ARCHITECTURE.md
- CITATION.cff
- .gitignore
- .ds_init/control.json
- tools/ds_init/version.py
- tools/tests/**
- tools/ds_init/tests/**
- tools/datasources/tests/**

## Motivo de rechazo

## Desacuerdo registrado
