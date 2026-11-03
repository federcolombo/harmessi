# Propuesta — 20261026-v015-release-hardening

## Problema
El release v0.15.0 (consolidación pre-v1.0) necesita su hardening final: versión, baseline de hashes managed (una sola vez), notas de release, matriz de readiness contra los 14 criterios de `docs/roadmap/v1.0.md`, y la evidencia de regresión completa serial, instalación limpia, upgrade v0.14.0→v0.15.0, Doctor y privacidad (B-31..B-33 de la matriz). Además hay una brecha de proceso registrada: C4, C5 y C6 quedaron en `en_verificacion` (ver `docs/roadmap/v0.15.md`).
<!-- qué problema motiva este cambio -->

## Objetivo
Publicar v0.15.0 sin features nuevas, con evidencia reproducible y una conclusión honesta de readiness (READY FOR v1.0 PLANNING o NOT READY con gaps).
<!-- qué se busca lograr, en una frase -->

## Evidencia
- `docs/roadmap/v0.15.md` §C7 y criterios de salida; `docs/roadmap/v1.0.md` (14 criterios); `docs/roadmap/v0.15-debt-matrix.md` (B-31..B-33); `docs/release-process.md` (runbook).
- `tools/ds_init/version.py` (HARNESS_VERSION = 0.14.0), `CITATION.cff`, `docs/releases/v0.14.0.md`, `tools/tests/test_v014_release_hardening_smoke.py` (patrón del smoke de release).
- Memoria operativa de v0.14.0: regresión serial con ledger por módulo, install limpio y upgrade idempotentes, baseline regenerado una vez.
<!-- archivo:línea o notebook/celda citados — nunca de memoria -->

## Supuestos descartados
- «Se puede observar el CI remoto»: sin `gh` ni observación remota en esta sesión; queda «pending observation» tras el push.
- "Los Changes C4-C6 están cerrados en SDD": falso; quedan en `en_verificacion` (brecha de proceso registrada, no se fuerza).
<!-- qué se creía y la exploración desmintió -->

## Hipótesis (condicional — solo cambios metodológicos)
<!-- qué se espera confirmar/descartar, si el cambio prueba una hipótesis concreta -->

## Alcance
- A: `HARNESS_VERSION` 0.15.0, `CITATION.cff`, README (enlace a las notas), `docs/releases/v0.15.0.md`, smoke `tools/tests/test_v015_release_hardening_smoke.py` (patrón v0.14).
- B: baseline de hashes managed regenerado UNA vez (`.ds_init/control.json`), verificando que solo cambian hashes de archivos efectivamente modificados y harness_version.
- C: matriz de readiness v1 (14 criterios, PASS/PARTIAL/FAIL/ACCEPTED LIMITATION con evidencia) en `docs/roadmap/v0.15.md` y conclusión; actualización de la matriz de deuda (B-31..B-33) y estado del release.
- D: verificación (Lead): regresión completa serial P=1, instalación limpia, upgrade v0.14.0→v0.15.0 con idempotencia, Doctor, barrido de privacidad; todo en `verification.md`.
- E: merge a main, tag anotado `Harmessi v0.15.0` y push (autorización humana explícita del 2026-10-26).

## Fuera de alcance
- Features nuevas; declarar v1.0; GitHub Release UI (acción manual); observación del CI remoto (posterior al push).
- Cerrar formalmente C4-C6 en SDD (requiere acción humana, ver brecha).

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
- tools/ds_init/version.py
- CITATION.cff
- README.md
- docs/releases/v0.15.0.md
- docs/roadmap/v0.15.md
- docs/roadmap/v0.15-debt-matrix.md
- docs/release-process.md
- .ds_init/control.json
- tools/tests/test_v015_release_hardening_smoke.py
- tools/tests/test_v014_release_hardening_smoke.py
- tools/tests/test_public_docs.py
<!-- opcional: rutas que este Change puede tocar, una por línea como `- ruta` o `- dir/**`
(repo-relativas, sin `..`, sin rutas absolutas ni comodines repo-wide). Al aprobar proposal.md,
ds_guard las materializa en control.json junto con los artefactos por defecto del Change;
queda ligado al hash de la propuesta aprobada. Sin bullets, el alcance no se modifica. -->

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
