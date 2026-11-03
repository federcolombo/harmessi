# Propuesta — 20261102-v1-release-hardening

## Problema
Con los 6 contratos `stable` preparados (Change `20261030-v1-contract-stabilization`, cerrado GREEN), quedan los gaps de
`docs/roadmap/v1-readiness.md` que impiden publicar 1.0.0: G1 (licencia sin ancla en tests), G5 (README declara Python 3.9+
pero CI solo ejecuta 3.12), G6 (upgrade 0.15.0→1.0.0 sin probar; sin notas ni baseline de 1.0.0) y G13 (las instalaciones de
`ds_init` no incluyen aviso de licencia de Harmessi; PolyForm Shield exige pasar los términos al redistribuir).

## Objetivo
Dejar el árbol listo para taggear 1.0.0 (versión, notas, baseline, asset de licencia, anclas y evidencia de upgrade), sin
features nuevas y sin tocar el repo público.

## Evidencia
- `docs/roadmap/v1-readiness.md` (G1, G5, G6, G13, G11, G14) y relevamiento de solo lectura del 2026-11-02.
- `tools/ds_init/manifest.py` (`MANIFEST`, `EntradaManifiesto`; última entrada `.ds_init/control.json`), `tools/ds_init/control.py:310`
  (`regenerar_control`), `docs/release-process.md` §7.
- `tools/ds_init/version.py:14` (`HARNESS_VERSION = "0.15.0"`), `tools/tests/test_v015_compat_window.py:80` (ancla estricta).
- `README.md:195` (`Python 3.9+`), `docs/installation.md:9`, `tools/harmessi/doctor.py:62`, `.github/workflows/portability-smoke.yml:23`.
- No existe ningún test de licencia (grep de `Apache|PolyForm|Required Notice` en `tools/**/*.py`: 0 resultados).

## Supuestos descartados
- "El bump rompe los smokes v010–v015": falso, comparan con `>=`; el único ancla estricta es `test_v015_compat_window.py:80`.
- "Los guards contra tags se rompen con 1.0.0": falso, comparan contenido de `.claude/*`, no versión (y se saltean sin tag).

## Hipótesis (condicional — solo cambios metodológicos)
No aplica.

## Alcance
1. Asset managed `HARMESSI-LICENSE.txt` (raíz): VERBATIM, `stage_minimo` discovery, en `manifest.py`, `.gitattributes` (LF) y baseline.
   Declara los términos/notice de los componentes Harmessi y aclara que NO relicencia el proyecto del usuario. Sin `LICENSE` genérico.
2. Ancla de licencia (G1) en `tools/tests/test_license_anchor.py`: `LICENSE` idéntico al texto oficial PolyForm Shield 1.0.0
   (golden en `tools/tests/fixtures/license/`, comparado normalizando CRLF), `Required Notice:` en `NOTICE`, sin "Apache"/"open source"
   fuera de notas históricas con allowlist explícita.
3. README (G5): Python 3.12 verificado en CI; 3.9 mínimo declarado y no ejecutado (también `docs/installation.md`). Sección License
   coherente con el asset. Bloque v1.0.0 en el README conservando los de v0.15.0 y v0.14.0.
4. Versión 1.0.0: `tools/ds_init/version.py`, `CITATION.cff` (versión y fecha real), `docs/releases/v1.0.0.md` (incluye G11 y G14),
   `tools/tests/test_v015_compat_window.py:80`, smoke `test_v1_release_hardening_smoke.py`.
5. Docs en presente: `docs/versioning.md`, `docs/contracts/README.md`, `docs/release-process.md`, `docs/installation.md`.
6. Tests de install/upgrade/doctor del asset (`tools/ds_init/tests/test_v1_license_asset.py`): install lo crea; upgrade desde baseline 0.15.0
   lo crea como managed nuevo y la segunda corrida no hace nada; Doctor sin `HARMESSI-DRIFT`.
7. Baseline `.ds_init/control.json` regenerado **una sola vez**, al final, con `regenerar_control`.
8. Regresión serial en lotes, install limpio, upgrade 0.15.0→1.0.0 idempotente, Doctor 0 ERROR, barrido de privacidad, clon sin tags,
   matriz final de readiness en `verification.md`. Estado en `docs/roadmap/v1-readiness.md`.

## Fuera de alcance
- Features nuevas; cambios a `.claude/settings.json`, agentes o guardrails; cambiar la matriz de CI; promover otros contratos.
- Endurecer `schema_version` (`True`/`1.0` en `tools/datasources/registry.py`): deuda LOW aceptada, POST-v1 (código de producción).
- Taggear, mergear a `main`, push, borrar tags o releases, tocar el repo público: es la Fase E, con STOP humano.

## Holdout policy (condicional — solo cambios "sensible")
No aplica: no toca datos ni holdouts.

## Impacto en production-readiness (opcional)
Cierra los blockers V1 G1, G5, G6 y G13.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver spec.md.

## Decisión técnica (design-lite — solo SDD abreviado)
Ver design.md.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado
- .gitattributes
- .ds_init/control.json
- ARCHITECTURE.md
- CITATION.cff
- HARMESSI-LICENSE.txt
- README.md
- docs/contracts/README.md
- docs/installation.md
- docs/release-process.md
- docs/releases/v1.0.0.md
- docs/roadmap/v1-readiness.md
- docs/versioning.md
- openspec/changes/20261102-v1-release-hardening/amendments.jsonl
- openspec/changes/20261102-v1-release-hardening/verification.md
- tools/ds_init/manifest.py
- tools/ds_init/version.py
- tools/ds_init/tests/test_v1_license_asset.py
- tools/tests/fixtures/license/**
- tools/tests/test_license_anchor.py
- tools/tests/test_v015_compat_window.py
- tools/tests/test_v1_release_hardening_smoke.py

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
