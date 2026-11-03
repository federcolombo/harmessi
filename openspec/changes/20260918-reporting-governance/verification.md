# Verificación — 20260918-reporting-governance

## Evidencia obtenida

- **Tests del Change** (`pytest tools/reporting/tests tools/tests/test_v06_core_neutrality.py tools/tests/test_architecture_boundaries.py tools/tests/test_v05_core_neutrality.py tools/tests/test_manifest_dsguard_parity.py tools/ds_init/tests/test_manifest.py`):
  - 1ª corrida (antes de la revisión): `279 passed, 1 skipped`, 303 subtests, en `7.89s`.
  - Tras los fixes del ciclo 1: `305 passed, 0 skipped`, 363 subtests, en `11.03s` (el fallback de junction de Windows ejercita los tests de enlaces que antes se omitían).
- **Paridad de manifest** (`python -m tools.ds_init.check_manifest_parity`): `[OK]`.
- **Suites que consumen `MANIFEST`** (`tools/ds_init/tests/test_control_file.py` + `tools/harmessi/tests/test_doctor.py`): se re-corren en background; ver cierre del Lead.
- **Smoke real de la CLI sobre este repo** (`python -m tools.reporting`). Esta corrida fue ANTES del fix de mojibake: apareció mojibake de tildes en consola y quedó corregido en el ciclo 1 (reconfigure UTF-8 en `__main__.py`).
  - `check-destination --report-id demo --scope exploratory --report-kind eda --out-dir reports/exploratory/demo` → exit 0 (`REPORT-POLICY`/`REPORT-DEST-SAFE`/`REPORT-DEST-SCOPE` PASS, `REPORT-SENSITIVE-DEST` N/A).
  - El mismo reporte con `--out-dir reports/model_valid/demo` → exit 1, `REPORT-DEST-CROSS-SCOPE` ("vector de leakage exploratorio <-> model_valid").
  - `check-inputs --flow-scope model_valid --input reports/exploratory/demo/artifacts/t.json` → exit 1, `REPORT-ISOLATION-INPUT`.
  - Ningún archivo creado en el repo (`git status` sin `reports/`).
- **Reviewer** (`data-science-reviewer`, ciclo 1 de 2): APRUEBA CON FIXES. 0 bloqueantes, 4 importantes, 5 menores. Importantes: aislamiento (input ancestro del root o glob daba PASS), mojibake en consola Windows, `REPORT-HOLDOUT-SOURCE` daba PASS sin holdouts configurados, cobertura de bypasses/symlink/`..`. Aplicados:
  - Aislamiento: ancestro o glob => FAIL; roots comparados en forma textual y resuelta.
  - Consola: reconfigure UTF-8 en `__main__.py`; escape de caracteres de control en la salida de texto.
  - Holdout: declarado sin patrones => FAIL; sin declarar => N/A.
  - Cobertura nueva: `..`, rutas absolutas, prefijo, manifest en la raíz, junction.
  - `resolve_output_dir` valida ids vía `core.es_id_valido` (adición aditiva en `core.py`, golden hash intacto).
  - `output_allowed(require_codes)` y `REQUIRED_DESTINATION_CODES`.
  - CLI: `--sensitive-artifact` en `check-destination`.
  - R19: tests de instalabilidad de las 3 entradas de manifest.
  - Enmiendas a spec R6/R14/R15/R17/R18 y `design.md`.
- **Sweep de privacidad**: grep de nombres, rutas y emails privados en `tools/reporting`, este Change y `ARCHITECTURE.md` → 0 resultados.
- **Alcance**: todos los archivos modificados/nuevos están dentro de `alcance.rutas_autorizadas` (incluye `core.py`, `test_core.py` y `test_installability.py`, agregados en el ciclo 1).

## Fingerprint de dataset/artefacto

No aplica -- infraestructura del harness, sin dataset.

## Diferencias contra la spec

- Las enmiendas listadas arriba (R6/R14/R15/R17/R18 y `design.md`), ya re-aprobadas por hash en el cierre.
- `REPORT-DEST-SCOPE` y `REPORT-SENSITIVE-DEST` comparan solo contra el root textual (fail-closed si el root es un enlace); el aislamiento usa ambas formas.

## Limitaciones

1. Governance declarativa: no observa lecturas en runtime de un notebook; el control de `pathguard` sobre Bash/PowerShell es best-effort.
2. El chequeo por hash de contenido contra artefactos exploratorios y la búsqueda de manifests hacia abajo se difieren al Change 3.
3. `_matchea_holdout` y `_bajo_root` son la 4ª réplica del matching de `pathguard` (deuda: promover `_matchea_patrones` a función pública en un Change posterior).
4. `REPORT-SCI-CUTOFF` da N/A sin policy científica (el Change 4 debe valorar WARN para `model_valid`/`operational`).
5. `sources` debe ser una lista de `str` y `data_cutoff` solo `YYYY-MM-DD` o `...Z` (el Change 3 normaliza antes de llamar).
6. Riesgo TOCTOU y symlinks preexistentes en `artifacts/`: el `publish` del Change 4 debe reevaluar antes de escribir y usar `REQUIRED_DESTINATION_CODES`.
7. `check-destination` solo verifica destino: un exit 0 no es el gate completo de `publish`.

## Pendientes derivados

- Change 3: normalizar `sources`/`data_cutoff`, chequeo por hash de contenido y búsqueda de manifests hacia abajo.
- Change 4: `publish` reevalúa el destino antes de escribir con `REQUIRED_DESTINATION_CODES`; valorar WARN de `REPORT-SCI-CUTOFF` sin policy científica; agregar `validate`/`render` a la CLI.
- Change posterior: promover `_matchea_patrones` de `pathguard` a función pública.

## Resultado final

**CERRADO — Change 1 cumple R1–R23.**
