# Propuesta — 20261103-readme-v1-editorial

## Problema
El README público de v1.0.0 se leía como changelog (narrativa v0.10–v0.15 en el cuerpo) y contenía afirmaciones
desactualizadas: «1.0.0 commit is pending observation» y «Linux/macOS no observados» (`README.md:203`,
`README.md:645`, `README.md:659-664`), contradichas por la evidencia real de v1 (portability-smoke GREEN sobre el
push de `main` y el tag `v1.0.0`, commit `5f4a0ca`). Una persona nueva no entiende en 60 s qué es, para quién, qué no
reemplaza, qué providers soporta ni cuánto pesa.

## Objetivo
Mejora editorial post-release (solo documentación, README en inglés) sin tocar runtime, contratos, arquitectura,
licencia ni el tag `v1.0.0`.

## Evidencia
- `README.md` (estructura y wording actual), `docs/portability.md:9-13`, `docs/release-process.md:152-166`,
  `docs/installation.md:135-138`, `ARCHITECTURE.md:970`.
- Footprint: `manifest_para_perfil_stage_y_capabilities('python-jupyter-data','experiment',{'predictive_modeling'})`
  = 136 entradas (135 archivos managed con fuente + `.ds_init/control.json` generado); 2 027 552 bytes de fuentes
  = 1.93 MiB (calculado en esta corrida).
- Tests que anclan el README: `test_v1_release_hardening_smoke.py` (v1.0.0/v0.15.0/v0.14.0, «Python 3.12», «Python 3.9»,
  «not executed», «bounded list of tests», `HARMESSI-LICENSE.txt`), `test_v011..v015_release_hardening_smoke.py`
  (`v0.1x`, `docs/releases/v0.1x.0.md`, «Evidence-Driven Harness Improvement»), `test_public_docs.py` (enlaces; «pending
  observation» en `docs/release-process.md`), `test_privacy_sweep.py`, `test_license_anchor.py`.

## Supuestos descartados
- Que hiciera falta tocar tests: una sección «Release notes» con tabla v0.9–v1.0 conserva todos los anclajes sin cambiar código.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica.

## Alcance
Reescritura editorial de `README.md` (inglés) y ajuste factual mínimo de `docs/portability.md`,
`docs/release-process.md` (la frase genérica «pending observation» se conserva por `test_public_docs.py`),
`docs/installation.md` (§Límites) y `ARCHITECTURE.md` (línea de CI) para no contradecir al README.

## Fuera de alcance
Runtime/código, tests (salvo que un check documental lo exija), contratos, licencia, `docs/releases/**`, tag y GitHub
Release `v1.0.0`, historial Git, Change `20261102-v1-release-hardening`.

## Holdout policy (condicional — solo cambios "sensible")
No aplica.

## Impacto en production-readiness (opcional)
Ninguno.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
1. README 100 % inglés; secciones: intro, Why Harmessi?, Who is it for?, is/is-not, Quickstart, Provider and CLI
   support, Footprint, Capabilities (≤ 8 bloques), Interfaces (core vs specialized), Documentation, License.
2. Sin narrativa v0.10–v0.15 en Capabilities; enlaces a `docs/releases/` conservados.
3. Hechos: `5f4a0ca`, Ubuntu/Windows/macOS GREEN, Python 3.12, lista acotada (no suite completa), Python 3.9 declarado no ejecutado.
4. Providers: Claude Code host/runtime validado y adapter live-validated; Codex/Gemini/Grok contract-tested; sin afirmar equivalencia de host.
5. Footprint con números verificados contra el manifest, marcados «current v1 manifest».
6. Enlaces internos resueltos; `test_public_docs`, `test_v1/v015..v011_release_hardening_smoke`, `test_privacy_sweep`,
   `test_license_anchor`, `check_manifest_parity` verdes; reviewer final sin hallazgos abiertos.

## Decisión técnica (design-lite — solo SDD abreviado)
Una sola sección «Release notes» (tabla) lleva los enlaces/anclajes históricos; el cuerpo describe solo el producto
actual. Sin cambios de código.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-11-03
- Alcance aprobado: Change 20261103-readme-v1-editorial (mejora editorial del README v1.0, solo documentación)
- Versión de artefactos referenciada: proposal.md
- Cita o descripción fiel de qué se aprobó: «Autorizado. ... Abrí un Change nuevo: 20261103-readme-v1-editorial ... Aplicá la mejora editorial ya definida» (mensaje del usuario, 2026-11-03)

## Alcance autorizado
- README.md
- docs/portability.md
- docs/release-process.md
- docs/installation.md
- ARCHITECTURE.md
- openspec/changes/20261103-readme-v1-editorial/verification.md

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
