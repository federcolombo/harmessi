# Verificación — 20260915-project-maturity-state-and-calibration

## Evidencia obtenida

Implementación en 1 delegación (código + tests, política de eficiencia del usuario):
`tools/dsguard/maturity.py` (nuevo — catálogos, `MaturityEstadoError`, `state_path`,
`estado_riesgo`, `inferir_stage`, `estado_inicial`, `validar_estructura`, `leer_estado`,
`escribir_estado`, `project_init`, `calibrar`, `set_risk`, `project_status`), grupo
`project init/calibrate/set-risk/status` en `tools/ds_guard.py`, entrada VERBATIM de
`maturity.py` + `.harmessi/` en `EXCLUSIONES_PERMANENTES` en `tools/ds_init/manifest.py`,
`tools/tests/test_maturity.py` (nuevo, 41 tests), `tools/tests/test_manifest_dsguard_parity.py`
(extendido, +1 test), `tools/ds_init/tests/test_integracion_instalacion.py` (extendido).

Verificación real ejecutada por el Lead:
- `python -m unittest tools.tests.test_maturity tools.tests.test_manifest_dsguard_parity -v`:
  46/46 OK.
- `python -m unittest discover -s tools/tests`: 304/304 OK (2 skipped, no relacionados, ya
  conocidos de changes anteriores), sin regresión.
- `python -m unittest discover -s tools/ds_init/tests`: 59/59 OK.
- `harmessi doctor`: 26 OK / 4 WARN / 0 ERROR (mismo patrón de drift esperado ya documentado
  en Changes 0 y 2 por archivos modificados, más working tree sin commitear).
- Smoke test manual (CLI real contra repo git temporal): `project init` sin flags →
  `project_stage=experiment`, `via=explicit_init`, exit 0; `project init --stage discovery
  --adopt` (ambos) → rechazado por argparse (`add_mutually_exclusive_group`), exit 2; `project
  status` sin `.harmessi/project.json` → mensaje claro pidiendo `project init`, exit 2; `project
  calibrate` sin `.harmessi/project.json` → mensaje claro, exit 1.
- Revisión de `data-science-reviewer`: sin hallazgos bloqueantes ni importantes. Confirmó los 7
  casos de `project_init` cubiertos 1:1 con `spec.md`; dependencia unidireccional real
  (`maturity.py` importa `lifecycle`/`kdd_compat` solo para `state_path`/`state_path_legacy`,
  ninguno de los dos importa `maturity`); `risk_status` rechazado explícitamente por
  `validar_estructura` si alguien intenta persistirlo, `estado_riesgo()` confirmada pura;
  prevención de bypass de `calibrate` exactamente `via == "promote"` sin campo nuevo; CLI con
  `mutually_exclusive_group` real más chequeo redundante en la función (defensa en profundidad);
  manifest/exclusiones correctos, y confirmó que `tools/ds_init/writer.py` aborta activamente la
  instalación si algo viola `EXCLUSIONES_PERMANENTES` (no es solo documentación, es un
  fail-safe ejecutado).

## Fingerprint de dataset/artefacto (condicional — cambio sensible o reproducibilidad crítica)

No aplica — no hay dataset ni artefacto de modelo en este change de arquitectura del harness.

## Diferencias contra la spec

Ninguna.

## Limitaciones

`project promote`/readiness/checks engine siguen fuera de alcance (changes posteriores del
roadmap), tal como fue aprobado. `harmessi project ...` (superficie pública) queda preparado
(funciones de `maturity.py` sin acoplamiento a `argparse`) pero no implementado — también
aprobado explícitamente (L8).

## Pendientes derivados

Ninguno bloqueante. Recordatorio para un change futuro de `promote`: debe escribir literalmente
`via: "promote"` en `stage_history` para que el chequeo de bypass de `calibrate` (ya activo) lo
detecte correctamente.

## Resultado final

Todos los criterios de aceptación de `spec.md` cumplidos con evidencia real, incluido el ajuste
L2 (separación `init` nuevo vs `init --adopt`). Change listo para cierre.
