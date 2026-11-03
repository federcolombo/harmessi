# Verificación — 20261103-readme-v1-editorial

Números de la corrida del 2026-11-03 (Windows 11, `.venv` del proyecto).

## Cambios
- `README.md` reescrito (inglés): intro, Why Harmessi?, Who is it for?, is/is-not, Quickstart, Provider and CLI support,
  Footprint, Capabilities (8 bloques), Interfaces (core vs specialized), Command reference, Platform and CI status,
  Contracts, Documentation, Release notes (tabla v0.9–v1.0.0), Development, License.
- Ajuste factual mínimo: `docs/portability.md`, `docs/release-process.md`, `docs/installation.md`, `ARCHITECTURE.md`.
- Sin cambios de código, tests, licencia, `docs/releases/**` ni del tag `v1.0.0`.

## Footprint (manifest real)
`manifest_para_perfil_stage_y_capabilities('python-jupyter-data','experiment',{'predictive_modeling'})`: 136 entradas =
135 archivos con fuente + `.ds_init/control.json` generado; 2 027 552 bytes de fuentes = 1.93 MiB.

## Tests
| Comando | Resultado |
|---|---|
| `pytest -q tools/tests/test_license_anchor.py test_privacy_sweep.py test_public_docs.py test_v1_release_hardening_smoke.py` | 46 passed, 131 subtests passed |
| `pytest -q` de `test_public_docs`, `test_v1/v015/v014/v013/v012/v011_release_hardening_smoke`, `test_license_anchor`, `test_v013_ci_workflow` (antes del último fix de licencia) | 141 passed, 6 skipped; el único fallo (`test_license_anchor`, línea con «Apache» sin marcador «Historical note») se corrigió y re-pasó |
| `python -m tools.ds_init.check_manifest_parity` | OK |

`test_parallel_change_isolation::test_informativos_constante` falla de forma preexistente (ver verificación de
`20261102-v1-release-hardening`); no se tocó.

## Revisión (data-science-reviewer, solo lectura)
Hallazgos A (wording «currently validated live»), B (matiz Bash/PowerShell en la intro), C (cifra de discovery sin
evidencia), D (lenguaje de novedad), E (falta v0.9 en la tabla): corregidos. F (`docs/releases/v1.0.0.md` aún decía
«pending observation»): resuelto tras la enmienda de scope.
H (trazabilidad): completada con este archivo.

## Abierto
- (Resuelto en el cierre) `docs/releases/v1.0.0.md` ya no dice «pending observation».
- La observación GREEN de `portability-smoke` sobre `5f4a0ca` proviene de lo informado por el autor; no hay `gh` en este entorno.

## Cierre (2026-11-03)
- Enmienda de scope T1 (`console_confirmed`, revisión 1, `scope_hash` d624d1d8…): agrega
  `openspec/changes/20261102-v1-release-hardening/control.json` (registro del cierre residual de la sesión s4, conservado)
  y `docs/releases/v1.0.0.md`.
- `docs/releases/v1.0.0.md`: reemplazado «the 1.0.0 commit is pending observation» por la evidencia informada por el autor
  (commit `5f4a0ca`, `portability-smoke` GREEN en push a `main` y tag `v1.0.0`, Python 3.12, lista acotada). Tag y GitHub Release intactos.
- Hallazgo F del reviewer: resuelto con esa corrección. Sin reviewer adicional: el último cambio es una frase de notas.
- Checks tras el cambio: `test_public_docs`, `test_v1_release_hardening_smoke`, `test_license_anchor`, `test_privacy_sweep`: 46 passed, 131 subtests.
