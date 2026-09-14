# Verificación — 20260914-lifecycle-core-schema

## Evidencia obtenida

**Implementación**: `tools/dsguard/lifecycle.py` (catálogos, `estado_inicial`, `validar_estructura`,
`leer_estado`, `escribir_estado`, `lifecycle_init`) y `tools/tests/test_lifecycle.py` (24 tests),
siguiendo exactamente el schema aprobado en `spec.md`/`design.md` (8 fases CRISP-DM, 5 pasos KDD,
3 tiers/16 capacidades MLOps, `ESTADOS_VALIDOS` sin `futura`, sin `fase_actual`/`paso_actual`
persistidos).

**`openspec/lifecycle/state.json`**: generado invocando `lifecycle.lifecycle_init()` real sobre
este repo (no escrito a mano) — `schema_version: 1`, `migrado_desde: null`, 8 fases + 5 pasos + 16
capacidades MLOps, todas `"no_iniciada"`.

**Tests**: `python -m unittest tools.tests.test_lifecycle -v`: 24/24 OK. Suite completa
`python -m unittest discover -s tools/tests -p "test_*.py"`: 219/219 OK (2 skipped, no
relacionados — dependientes de entorno), sin regresiones en ningún otro módulo de `dsguard`.

**Gate de implementación**: `ds_guard validate --gate implementacion` → sin hallazgos (alcance
declarado correctamente en `control.json` antes de implementar, a diferencia del Change 0 donde
se corrigió después).

**Revisión de `data-science-reviewer`**: sin hallazgos bloqueantes. Confirmó: los 8/5/16 nombres
coinciden exactamente con `spec.md`; `MAPEO_KDD_A_CRISPDM` es derivado por código, no
hardcodeado; `escribir_estado` es atómica vía `core.escribir_texto_atomico` sin ningún
`open(..., "w")` que la esquive; `leer_estado`/`validar_estructura` no escriben nada; los 24 tests
usan siempre directorios temporales, nunca este repo real; el `state.json` real generado es
coherente con `lifecycle_init()`. Dos observaciones no bloqueantes, dejadas sin acción por
decisión del Lead (no exigidas por los criterios de aceptación aprobados): (1)
`_validar_entrada_trackeable` y `validar_estructura` no rechazan claves extra desconocidas dentro
de una entrada individual ni a nivel raíz del archivo — solo verifican presencia de las claves
conocidas, no ausencia de claves no reconocidas adicionales; (2) el gap de `proposal.md §
Aprobación` sin completar, ya corregido en un paso anterior.

## Fingerprint de dataset/artefacto (condicional — cambio sensible o reproducibilidad crítica)

No aplica — no hay dataset ni artefacto de modelo involucrado en este change de arquitectura del
harness.

## Diferencias contra la spec

Ninguna — los 8/5/16 nombres, el mapeo CRISP-DM↔KDD, la forma `{estado, changes, evidencia,
actualizado_utc}`, `ESTADOS_VALIDOS` sin `futura`, y la ausencia de `fase_actual`/`paso_actual`
persistidos coinciden exactamente con `spec.md`/`design.md`, confirmado por
`data-science-reviewer`.

## Limitaciones

Las 2 observaciones no bloqueantes de la revisión que no requieren acción por decisión del Lead
(no exigidas por los criterios de aceptación aprobados):

1. `_validar_entrada_trackeable`/`validar_estructura` no rechazan claves extra desconocidas dentro
   de una entrada individual ni a nivel raíz del archivo.
2. El gap de `proposal.md § Aprobación` sin completar, ya corregido en un paso anterior.

## Pendientes derivados

Ninguno bloqueante para este change. Recordatorio: Change 2
(`lifecycle-migration-and-kdd-repoint`) debe implementar la migración real desde
`openspec/kdd/state.json` v0.2 con la nota de `futura`→`no_iniciada` preservando provenance, tal
como quedó documentado en `design.md`.

## Resultado final

Todos los criterios de aceptación de `spec.md` cumplidos con evidencia real; change listo para
cierre.
