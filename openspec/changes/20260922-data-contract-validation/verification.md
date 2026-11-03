# Verificación — 20260922-data-contract-validation

## Evidencia obtenida

- **Suite nueva del Change tras implementación**: `307 passed`, `5 skipped`, `32 subtests
  passed`, `0 failed`.
- **Regresión completa del repo** (`pytest tools -q`): `2180 passed`, `10 skipped`, `709 subtests
  passed`, `0 failed`, en `1530.38s`.
- **Paridad de manifest** (`check_manifest_parity`): `OK`, sin cambios introducidos por este
  Change.
- **Doctor** (`harmessi doctor`): `0 ERROR`, mismo perfil de `WARN` preexistente que en el cierre
  de Change 0, no relacionado con este Change.
- **Reviewer** (`data-science-reviewer`, revisión del diff completo SDD + implementación, solo
  lectura): **0 hallazgos bloqueantes**, **3 hallazgos no bloqueantes**. Decisión del Lead sobre
  cada uno:
  1. Requería fix de documentación (`spec.md`/`design.md` desactualizados frente al criterio real
     de duplicado bajo muestreo) — **APLICADO**.
  2. Riesgo aceptado y diferido (asimetría entre `CONTRACT-RANGE` y `CONTRACT-DATE-RANGE`,
     inalcanzable hoy) — **documentado en `design.md`, sin fix**.
  3. Requería test faltante (rama "ruta no resoluble" del guard de holdout) — **APLICADO**.

## Ciclo de remediación

- Ciclo 1 de 2 usados: aplicado por `python-data-engineer` (fixes de los hallazgos 1 y 3 del
  reviewer), verificado por el Lead con re-tests tras el ciclo de fixes: `161 passed`, `28
  subtests passed`, `0 failed` sobre `tools/datacontracts/tests` +
  `tools/tests/test_v07_core_neutrality.py` + `tools/tests/test_v07_validation_neutrality.py` +
  `tools/tests/test_architecture_boundaries.py`.
- No hizo falta un segundo ciclo: el hallazgo 2 quedó como riesgo aceptado y diferido, sin
  requerir código adicional.

## Fingerprint de dataset/artefacto

No aplica -- validación en memoria de infraestructura del harness (evaluación determinista de
`DataContract` contra `profile.json` de `ds_profile`), sin dataset propio de este Change.

## Diferencias contra la spec

`spec.md`/`design.md` estaban desactualizados frente al criterio real implementado de duplicado
bajo muestreo (hallazgo 1 del reviewer); corregido en el ciclo de remediación 1 para reflejar el
comportamiento real del código. La asimetría entre `CONTRACT-RANGE` y `CONTRACT-DATE-RANGE`
(hallazgo 2) queda documentada como limitación conocida en `design.md`, sin cambio de
comportamiento.

## Limitaciones

1. `validate_contract` nunca produce `PASS` sin evidencia suficiente; bajo `sampling.activo=True`
   las reglas que dependen de valores exactos quedan no verificables (`WARN`/`N/A`).
2. Asimetría conocida y aceptada entre `CONTRACT-RANGE` y `CONTRACT-DATE-RANGE`: hoy inalcanzable
   con la evidencia que produce `ds_profile`; ver `design.md`.
3. No se construye un segundo profiler: toda observación proviene de `ds_profile` (`profile.json`
   y `ds_profile.holdout_guard.verificar_permitido`, importado de forma narrow).
4. No hay lenguaje universal de validación ni DSL de expresiones arbitrarias.

## Pendientes derivados

- Los Changes 2–5 de v0.7 pueden consumir el vocabulario `PASS`/`WARN`/`FAIL`/`N/A` y el patrón
  función-pura-más-puerta-de-I/O establecido en este Change, sin importar directamente
  `validate_contract` salvo que un Change futuro lo decida explícitamente en su propio SDD.
- La asimetría `CONTRACT-RANGE`/`CONTRACT-DATE-RANGE` queda como deuda documentada para una
  eventual extensión aditiva de `ds_profile`, a decidir en SDD futuro.

## Resultado final

**CERRADO — Change 1 (`data-contract-validation`) aprobado para cerrar.** Suite nueva y regresión
completa en verde, paridad de manifest OK, doctor sin `ERROR`, revisión del
`data-science-reviewer` sin hallazgos bloqueantes y los 3 hallazgos no bloqueantes resueltos
(2 con fix aplicado y verificado, 1 con riesgo aceptado y documentado), 1 de 2 ciclos de
remediación usados.
