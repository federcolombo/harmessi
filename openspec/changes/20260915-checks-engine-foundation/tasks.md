# Tareas — 20260915-checks-engine-foundation

estado: cerrada

## Invocaciones planificadas
- Python Data Engineer (implementación + tests, invocación única): `tools/dsguard/checks.py` +
  retrofit completo de `tools/harmessi/doctor.py` + manifest + tests. Produce: código + tests en
  un solo paso (política de eficiencia del usuario).
- Data Science Reviewer (revisión de código, DESPUÉS de implementación completa): revisa el
  diff. Solo informa hallazgos.
- Python Data Engineer (post-revisión, planificada): corrige si hace falta, `estado:
  en_verificacion`.
- Python Data Engineer (cierre, planificada): `verification.md` con evidencia real, `estado:
  cerrada`.

## Tareas
- [x] `tools/dsguard/checks.py`: `CheckResult` (dataclass frozen, validación en
      `__post_init__`, incluye `kind` y su validación), `STATUS_PASS/WARN/FAIL/NA`,
      `ejecutar_checks`, `contar_por_status`, `hay_bloqueo`, `exit_code`, `filtrar_por_status`.
- [x] Retrofit de las ~20 funciones `_check_*` en `tools/harmessi/doctor.py`: devuelven
      `list[CheckResult]` (vocabulario PASS/WARN/FAIL/N/A) en vez de `list[ResultadoCheck]`.
- [x] `_ejecutar_check`: delega en `checks.ejecutar_checks`, traduce `CheckResult→ResultadoCheck`
      (`PASS→OK, WARN→WARN, FAIL→ERROR`, `subject→ubicacion`).
- [x] `_ejecutar_check_con_dato`: mantiene su forma `(dato, list[ResultadoCheck])`, reusa la
      misma traducción internamente.
- [x] `formatear()`: agrega el segmento `[N/A]` al resumen SOLO si el conteo es > 0.
- [x] `tools/ds_init/manifest.py`: entrada VERBATIM de `tools/dsguard/checks.py`.
- [x] `tools/tests/test_manifest_dsguard_parity.py`: test explícito hardcodeado para
      `checks.py` (mismo patrón que `lifecycle.py`/`kdd_compat.py`/`maturity.py`).
- [x] `tools/tests/test_checks.py` (nuevo): los 13 casos de "Engine" de `spec.md`.
- [x] Tests: `kind="check"` en FAIL funcional; `kind="technical_error"` en excepción capturada;
      ambos bloquean igual; serialización conserva `kind`.
- [x] `tools/harmessi/tests/test_doctor.py`: agregar (sin tocar las aserciones existentes) tests
      nuevos para el mapeo PASS→OK/WARN→WARN/FAIL→ERROR, el manejo condicional de N/A en
      `formatear()`, y una verificación de que los códigos/mensajes/exit code se preservan.
- [x] `tools/ds_init/tests/test_integracion_instalacion.py`: agregar
      `tools/dsguard/checks.py` a `archivos_clave`.
- [x] Ejecutar `harmessi doctor` real sobre este repo antes/después del retrofit y confirmar 27
      OK / 3 WARN / 0 ERROR sin cambios de código/mensaje/orden (más allá de un hallazgo real).
- [x] Ejecutar suite completa (`tools/tests/`, `tools/harmessi/tests/`, `tools/ds_init/tests/`)
      para confirmar sin regresión.

## Dependencias
`checks.py` antes que el retrofit de `doctor.py`; retrofit antes que los tests de
`test_doctor.py` nuevos; manifest/parity puede ir en paralelo; verificación end-to-end (doctor
real + suites) al final. Depende de Changes 1-3 (cerrados) solo por convención de patrón
(`lifecycle.py`/`kdd_compat.py`/`maturity.py` como referencia), sin dependencia de código real.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->
