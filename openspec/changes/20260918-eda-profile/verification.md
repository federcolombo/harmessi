# Verificación — 20260918-eda-profile

## Evidencia obtenida

- **Tests del Change** (`pytest tools/reporting/tests tools/tests/test_v06_core_neutrality.py tools/tests/test_architecture_boundaries.py tools/tests/test_v05_core_neutrality.py tools/tests/test_manifest_dsguard_parity.py tools/ds_init/tests/test_manifest.py`):
  - 1ª corrida (antes de la revisión): `412 passed`, 444 subtests, en `12.29s`. Había 1 fallo de un test propio, corregido por el writer (reintento técnico registrado en la sesión).
  - Tras los fixes del ciclo 1/2: `437 passed`, 469 subtests, en `11.03s`.
- **Paridad de manifest** (`check_manifest_parity`): `[OK]`.
- **Suites lentas que consumen `MANIFEST`** (`tools/ds_init/tests/test_control_file.py` + `tools/harmessi/tests/test_doctor.py`): `94 passed` en `372.35s`, corridas con las 4 entradas de manifest del Change; los fixes no tocaron `manifest.py`.
- **Ejemplo real** (`build_example_report()` + `validate_eda_report`): tras el ciclo 1, 19 PASS + 1 WARN esperado (`EDA-EXPLORATORY-TARGET-USE`), 0 FAIL; determinista (mismo hash en 2 llamadas). Antes de los fixes: 17 PASS + 1 WARN.
- **Reviewer** (`data-science-reviewer`; una primera revisión fue interrumpida sin reporte por un corte de sesión y se repitió): APRUEBA CON FIXES. 0 bloqueantes, 2 importantes, 8 menores, cosméticos.
  - Importantes: hueco de diseño (el guard de leakage R16 y `EDA-OMITTED-SCOPE` eran evadibles omitiendo `target`, declarando `omitted`/`not_applicable` manual o usando un bloque `x_`) y tests "nunca lanza" que no podían fallar.
  - Aplicados: `derive_evaluations` conserva un `applicable` declarado con precondición fallida (FAIL `EDA-TARGET-DECLARED`/`EDA-TIME-DECLARED` en vez de degradar en silencio); R16 dispara también por capítulo `eda_block=bivariate_target` en cualquier estado; WARN nuevos `EDA-NA-CONTRADICTS-DECLARATION` y `EDA-EXTENSION-SHADOWS-CATALOG` (20 códigos en `CODES`); `EDA-PROFILE` valida `profile`/`profile_version`; razones exigen ≥ 3 palabras distintas.
  - Tests con dientes: sin `-EXCEPCION`, `mock.patch` de excepción interna, `assertRaisesRegex("reservado")`, round-trip `to_dict`/`from_dict`.
  - Ejemplo: textos derivados de la corrida (nulos calculados, población que dice qué excluye, sin inferencia no sustentada), unidades unificadas a proporción 0-1, test de semilla no tautológico.
  - Descartado con motivo: hallazgo 10 (los tests usaban funciones privadas de normalización; menor, mismo paquete); en el ejemplo ya se eliminó su uso.
- **Sweep de privacidad**: grep de nombres, rutas y emails privados en `tools/reporting`, este Change y `ARCHITECTURE.md` → 0 resultados. Grep de técnicas hardcodeadas (PCA, k-means, RFM, Pareto, bootstrap, chi-cuadrado, cohorte como palabras) en `eda.py` y `eda_generic.py` → 0 resultados (las familias informativas son strings sin lógica).
- **Alcance / backward compat**: `git diff` de `core.py`, `governance.py` y `cli.py` vacío. Archivos preexistentes modificados solo aditivamente: `manifest.py` (+4 entradas), `ARCHITECTURE.md` (2 filas), `test_architecture_boundaries.py` (2 rutas), `test_installability.py`.

## Fingerprint de dataset/artefacto

No aplica -- infraestructura del harness con datos sintéticos, sin dataset real.

## Diferencias contra la spec

- Enmiendas del ciclo (R2, R4, R9, R11, R14, R16, R24 y D4 de `design.md`), re-aprobadas por hash.
- La extensión del catálogo (`leakage_review`, `population_and_unit`) es una adición reversible a los 9 bloques candidatos del roadmap, adoptada tras consulta metodológica.

## Limitaciones

1. El binario solo filtra lo obviamente vacío; la suficiencia de razones e insights la juzga el metodólogo/reviewer.
2. Un insight trivial cumple `applicable => >= 1 Insight`.
3. El escape `x_` con nombre no coincidente con el catálogo puede re-implementar análisis sin que R16 lo vea (documentado en R24).
4. La tabla de cobertura solo detecta desajuste con la declaración (no un bloque `x_total` consistente).

## Pendientes derivados

Para el Change 3:
- Cargar `scientific_policy` UNA vez y pasarla a `build_eda_report` Y a `validate_eda_report` (si no, FAIL espurios `EDA-TIME-DECLARED`/`EDA-AUTO-INVALID`).
- La tabla `eda_coverage` compara el texto exacto de razones/limitaciones: no normalizar aguas abajo.
- El ejemplo formatea números como strings en los claims; un verificador numérico de evidencia no los reconocerá.

## Resultado final

CERRADO — Change 2 cumple R1–R24.
