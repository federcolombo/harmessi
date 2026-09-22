# Verificación — 20260922-model-quality-policies

## Evidencia obtenida

- **Suite nueva del Change tras implementación** (incluyó un fix menor sobre
  `test_v07_modelquality_neutrality.py` para 2 tests de sanidad del propio detector, sin cambios
  en `validation.py`/`core.py`): `416 passed`, `28 subtests passed`, `0 failed`.
- **Regresión completa del repo** (`pytest tools -q`): `2306 passed`, `10 skipped`, `709 subtests
  passed`, `0 failed`, en `1639.77s`.
- **Paridad de manifest** (`check_manifest_parity`): `OK`.
- **Doctor** (`harmessi doctor`): `0 ERROR`, mismo perfil de `WARN` preexistente, no relacionado
  con este Change.
- **Reviewer** (`data-science-reviewer`, revisión del diff completo SDD + implementación, solo
  lectura): **0 hallazgos bloqueantes**, **1 observación cosmética no bloqueante**: la whitelist
  `VALIDATION_STDLIB_PERMITIDOS` del test de neutralidad incluye `"json"` aunque `validation.py`
  no lo use hoy — no amerita fix, **aceptada tal cual por el Lead**, sin cambio de código.
- Confirmado explícitamente: `tools/datacontracts/{core,validation}.py` sin ningún diff.

## Ciclo de remediación

- 0 de 2 ciclos de remediación de revisión usados: el único ciclo de fix (2 tests de sanidad del
  propio detector de neutralidad rotos) fue **pre-revisión**, aplicado por el Lead antes de
  invocar al `data-science-reviewer`, no como remediación de un hallazgo de la revisión.
- La única observación de la revisión (whitelist con `"json"` no usado) quedó aceptada sin fix,
  no requirió ciclo de remediación.

## Fingerprint de dataset/artefacto

No aplica -- `tools/modelquality/{core,validation}.py` es infraestructura neutral en memoria
(evaluación determinista de `ModelQualityPolicy` contra `ObservedMetric`/`BaselineReference`
sintéticos), sin dataset propio ni cálculo de métricas de modelo (decisión 1 del roadmap).

## Diferencias contra la spec

Ninguna. La implementación se ajustó a `spec.md` R1-R21 y `design.md` tal como quedaron
aprobados por el Lead al cierre de la invocación 1; el único fix del ciclo pre-revisión corrigió
2 tests de sanidad del propio detector de neutralidad, sin tocar el comportamiento declarado en
`core.py`/`validation.py`.

## Limitaciones

1. `evaluate_policy` nunca calcula métricas: consume `ObservedMetric` ya reportado por el
   proyecto, con su evidencia (decisión 1 del roadmap, R15 de `spec.md`).
2. Sin evidencia vigente no hay `PASS`, aunque el valor cumpla el umbral; un `technical_error` en
   cualquier etapa se reporta aparte, sin afectar otros requirements.
3. `tools/modelquality/core.py` es solo-stdlib y no importa `tools.datacontracts`/`dsguard`/
   `ds_profile`; `tools/modelquality/validation.py` no tiene superficie de I/O ni lectura de
   archivo.
4. Sin lista cerrada de métricas ni calculadores de AUC/F1/RMSE/etc.; una métrica se declara por
   nombre + dirección + modo de comparación.

## Pendientes derivados

- Los Changes 3-5 de v0.7 consumen `ModelQualityPolicy`, `MetricRequirement`, `ObservedMetric`,
  `BaselineReference`, `EvaluationContext`, `evaluate_policy` y los códigos `QUALITY-*`
  establecidos en este Change. Change 3 decidirá si reinterpreta `evidence_ref` como una ruta
  persistida con hash, sin que este Change se comprometa de antemano con esa forma (ver
  `design.md`, decisión 2).
- La observación cosmética del reviewer (`"json"` en `VALIDATION_STDLIB_PERMITIDOS` sin uso
  actual) queda documentada acá como aceptada sin fix, disponible para revisarse si algún Change
  futuro introduce un uso real de `json` en `validation.py`.

## Resultado final

**CERRADO — Change 2 (`model-quality-policies`) aprobado para cerrar.** Suite nueva y regresión
completa en verde, paridad de manifest OK, doctor sin `ERROR`, revisión del
`data-science-reviewer` sin hallazgos bloqueantes y la única observación no bloqueante (whitelist
cosmética) aceptada sin fix, 0 de 2 ciclos de remediación de revisión usados, `tools/datacontracts/
{core,validation}.py` sin ningún diff.
