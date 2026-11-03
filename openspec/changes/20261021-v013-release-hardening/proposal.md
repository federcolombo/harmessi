# Propuesta — 20261021-v013-release-hardening

> Change 6 de v0.13: Release Hardening + Evaluation Dogfooding. Sin features nuevas: prepara `0.13.0`.

## Problema
Los Changes 0–5 dejaron evaluación/benchmarks, runs reproducibles, conformance, portabilidad e inventario de contratos, pero falta cerrar el release: marcadores de versión, notas, baseline managed, regresión completa, instalación fresca y upgrade desde `v0.12.0`, Doctor, privacidad y un dogfood que ejercite el conjunto de punta a punta.

## Objetivo
Dejar `main` listo para `v0.13.0` con evidencia: marcadores `0.13.0` coherentes, notas en inglés que no sobre-prometen, smoke de release, baseline managed regenerado una sola vez (sin adoptar drift), regresión completa serial con ledger, fresh install y upgrade verdes, Doctor sin errores de producto, privacidad limpia, dogfood de evaluación/provider/adapter/portabilidad con fixtures sintéticos.

## Evidencia
- `tools/ds_init/version.py` (`0.12.0`), `CITATION.cff`, `README.md`, `docs/releases/v0.12.0.md`, `tools/tests/test_v012_release_hardening_smoke.py` (patrón a replicar).
- Estado de Changes 0–5 de v0.13 cerrados en `v0.13-dev` (commits `e46c6a1`, `1ce2075`, `72bf54e`, `e106ba6`, `eb213a1`, `ecae1d2`).
- `.ds_init/control.json` baseline en `0.12.0`; `regenerar_control` en `tools/ds_init/control.py`.
- `gh` no está instalado; no hay `.github` observable remotamente desde este host.

## Supuestos descartados
- Que la ejecución remota de Actions pueda observarse: no; se registra «remote CI execution not observed during release».
- Declarar validación Linux/macOS: no hay host; solo contratos/CI config.
- Que v0.13 mejore o promueva cambios del harness: no; solo habilita comparación basada en evidencia.

## Alcance
- Versión `0.13.0` (`version.py`, `CITATION.cff`, `README.md`), notas `docs/releases/v0.13.0.md` (inglés), roadmap/README de roadmaps publicados, smoke `tools/tests/test_v013_release_hardening_smoke.py`.
- Baseline `.ds_init/control.json` regenerado una vez.
- Regresión completa serial (P=1) por módulo con ledger fuera del repo.
- Fresh install y upgrade `v0.12.0` → `v0.13.0` en directorios temporales; imports desde el destino instalado.
- Doctor, `migrate-hashes` dry-run, barrido de privacidad.
- Dogfood: (A) suite baseline; (B) candidate manual (variante deliberadamente simple de una superficie Optimizable usada solo como fixture); (C) identidades de run distintas; (D) comparación; (E) veredictos better/worse/equivalent/inconclusive; (F) resume incompatible rechazado; provider (disponible local / faltante / unsupported) y adapter (conformante / inválido); portabilidad en Windows (espacios, Unicode, CRLF/LF, paths, temp dirs, subprocess, Git).

## Fuera de alcance
Features nuevas; generación o promoción automática de candidates; lecciones globales; telemetría; observar Actions; GitHub Release (si no hay `gh`: «GitHub Release UI pending»).

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
- docs/releases/v0.13.0.md
- docs/roadmap/v0.13.md
- docs/roadmap/README.md
- docs/contracts/inventory.json
- docs/contracts/README.md
- docs/versioning.md
- .ds_init/control.json
- tools/tests/test_v013_release_hardening_smoke.py
- tools/tests/test_v012_release_hardening_smoke.py
- tools/tests/test_v013_contract_inventory.py
- openspec/changes/20261021-v013-release-hardening/**
