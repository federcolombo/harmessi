# Proposal — 20260917-v0-4-release-hardening

## Problema

Changes 0-4 completaron el roadmap de v0.4 (scientific validity checks, impact preflight, scope
isolation, portable-core doc, agent efficiency reporting), pero el repo todavía no está endurecido
para publicarse: la versión canónica sigue en `0.3.0`, `README.md` no menciona ninguno de los 4
componentes nuevos (`science status`, `impact scan`, `efficiency report`, scope check ampliado), no
hay release notes de v0.4.0, y `.ds_init/control.json` de este mismo repo quedó desactualizado desde
antes de Change 0 (WARN de drift ya visto en `harmessi doctor` en cada change de esta sesión).

Este change sigue el mismo patrón ya usado para v0.3 (`openspec/changes/
20260916-v0-3-release-hardening/`, mismo autor/aprobación) — reusado como precedente, no
reinventado — pero ESCALADO para v0.4: no se repite la validación E2E exhaustiva de features de v0.3
que ya pasaron su propio hardening y no fueron tocadas en v0.4 (readiness/promotion/evidence/legacy
compat) — la regresión completa (`tools/tests`, `tools/harmessi/tests`, `tools/ds_init/tests`,
`tools/ds_profile/tests`, `tools/dsimpact/tests`) ya cubre eso sin regresiones (confirmado en cada
Change 0-4 de esta sesión). El foco de este change son los 4 componentes NUEVOS de v0.4.

## Objetivo

Endurecer el repo para el release v0.4.0: versión canónica única, README actualizado con los 4
componentes nuevos, release notes + known limitations en `verification.md`, smoke E2E de los
componentes nuevos sobre scratch installs reales, regresión completa final, privacidad transversal,
`harmessi doctor` sin `ERROR`, `.ds_init/control.json` regenerado una sola vez al final — sin
agregar ninguna feature nueva ni tocar ningún engine/gate/schema salvo bug real demostrado.

## Alcance

1. **Versión**: `tools/ds_init/version.py` (`HARNESS_VERSION = "0.4.0"`), `CITATION.cff`
   (`version: 0.4.0`, `date-released` actualizado a 2026-09-17). Ninguna otra fuente de versión
   nueva.
2. **README.md**: agregar los 4 componentes nuevos a la sección `### ds_guard` (grupos `science`,
   `impact`, `efficiency`) y una mención de la ampliación de `ALCANCE-RUTA`/scope check — mínimo
   necesario, sin reescribir el documento.
3. **Release notes v0.4.0** (texto en `verification.md`, no un archivo publicado): resumen de
   Changes 0-4, deuda explícita registrada durante la sesión (ver `docs/roadmap/v0.4.md`, cada
   Change ya documenta la suya).
4. **Known limitations v0.5+** (en `verification.md`): las 5 deudas de `ARCHITECTURE.md` §4, la
   deuda de captura automática de agentes de Change 4, y cualquier limitación nueva que surja de la
   validación E2E de este change.
5. **Validación E2E de los componentes NUEVOS** (ejecutada por el Lead, sin subagente): scratch
   installs discovery + experiment con TODOS los módulos de v0.4 presentes; smoke de `ds_guard
   science status`, `ds_guard impact scan --since`, `ds_guard efficiency report`, y de la ampliación
   de scope (`validate` detectando un archivo fuera de alcance ya commiteado); regresión completa
   final (las 5 suites); `harmessi doctor` final, 0 `ERROR`.
6. **Privacidad transversal**: grep exhaustivo sobre TODO el working tree (no solo los archivos
   tocados por Change 5) para `AGD`/`UNCO`/`Model-churn`/rutas `C:\`/emails personales fuera de
   metadata pública legítima/secrets — confirmando lo que cada Change 0-4 ya barrió individualmente,
   más los archivos nuevos de este change (`README.md`, `CITATION.cff`, `verification.md`).
7. **`.ds_init/control.json` regenerado una sola vez, al final**, vía `control.regenerar_control`
   (mecanismo oficial ya existente, sin reimplementar), después de que todos los demás cambios de
   este change ya estén aplicados.

## Fuera de alcance

Cutoff/baseline como gate de readiness, wiring de scientific validity/scope/efficiency a
readiness/promote, captura automática de agentes (deuda ya registrada en Change 4), reestructuración
física core/adapter (deuda ya registrada en Change 3), cualquier feature nueva. Tag, push, GitHub
Release, commit final sin aprobación humana — el usuario ya indicó explícitamente frenar para
revisión humana al terminar este change.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-17
- Alcance aprobado: continuación de "Continuar Harmessi v0.4 en modo autónomo de versión" — Change 5
  según `docs/roadmap/v0.4.md`, sin push/merge/tag/release, frenar para revisión humana al terminar.
