# Verificación — 20260914-lifecycle-migration-and-kdd-repoint

## Evidencia obtenida
Implementación completa en 3 delegaciones + correcciones puntuales:
- `tools/dsguard/kdd_compat.py` (nuevo, capa de compatibilidad legacy: catálogo, mapeo, merge de convergencia, `migrar_desde_legacy`, operaciones repuntadas).
- `tools/dsguard/lifecycle.py` (+`calcular_estado_fase`, roll-up puro).
- `tools/dsguard/kdd.py` (reescrito, adapter delgado).
- `tools/ds_guard.py` (grupo `lifecycle migrate`, repunte de `cmd_kdd_init/status/transition`, exit codes consistentes).
- `tools/ds_init/manifest.py` (2 entradas VERBATIM nuevas + `EXCLUSIONES_PERMANENTES`).
- `.claude/skills/lead-data-scientist/kdd.md` + template sincronizado (callout factual + aclaraciones sobre `futura`).
- Tests: `tools/tests/test_kdd_compat.py` (nuevo, 34 tests), `tools/tests/test_kdd.py` (reescrito, 21 tests), `tools/tests/test_lifecycle.py` (extendido, +8 tests de roll-up), `tools/tests/test_manifest_dsguard_parity.py` (extendido), `tools/ds_init/tests/test_integracion_instalacion.py` (extendido).

Verificación real ejecutada por el Lead:
- Smoke test manual contra un fixture fabricado a mano (legacy con 10 etapas, estados variados, incluida convergencia evaluation+interpretation y futura con evidencia) confirmando: migración correcta, roll-up correcto (`data_preparation` en_progreso con preprocessing=cerrada+transformation=no_iniciada), sinónimos evaluation/interpretation, provenance de `futura` preservada, MLOps nunca auto-poblado, idempotencia, legacy congelado (bytes idénticos), transición en vivo recalculando roll-up, y el error claro de "legacy sin migrar".
- `python -m unittest tools.tests.test_kdd_compat tools.tests.test_kdd tools.tests.test_lifecycle tools.tests.test_manifest_dsguard_parity -v`: 99/99 OK.
- `python -m unittest discover -s tools/tests`: 262/262 OK, sin regresiones (incluye `test_decision.py`, `test_remediation.py`, `test_pathguard.py`, etc.).
- `python -m unittest discover -s tools/ds_init/tests`: 59/59 OK; instalación scratch confirma 54 archivos aplicados (antes 52), incluyendo `lifecycle.py`/`kdd_compat.py`.
- `harmessi doctor`: 26 OK / 4 WARN / 0 ERROR. Los 3 WARN de `HARMESSI-DRIFT` (`kdd.md`, `ds_guard.py`, `kdd.py`) son el comportamiento esperado documentado en Change 0 (drift al modificar archivos administrados, no un bug); el 4to WARN es `CORE-WORKING-TREE` (cambios sin commitear, esperado durante el desarrollo).
- Revisión de `data-science-reviewer`: sin hallazgos bloqueantes. Confirmó mapeo/merge/roll-up exactos según `spec.md`/`design.md`, dependencia unidireccional `lifecycle.py`←`kdd_compat.py`←`kdd.py` sin ciclos (verificado por grep de imports), `_CRITERIOS_DETECTABLES` y funciones asociadas preservadas sin alterar, envoltura de excepciones (`_envolver`) cubre todos los casos que `ds_guard.py` necesita, dedup de `sync_al_cerrar` por `change_id` (no `(change_id, artefacto)`) coincide exactamente con v0.2. Encontró 2 hallazgos accionables, ambos corregidos: (1) inconsistencia de exit code entre `cmd_kdd_init` (devolvía 1) y `cmd_kdd_status`/`cmd_kdd_transition` (2) para el mismo escenario "legacy sin migrar" — corregido, `cmd_kdd_init` ahora tiene el mismo pre-chequeo y devuelve 2; (2) `kdd.md`/template seguían documentando `KDD-ETAPA-FUTURA` como comportamiento vigente cuando ya no puede ocurrir tras el repunte — corregido con aclaraciones puntuales en ambos archivos, sin reescribir el resto. Un tercer hallazgo (asimetría cosmética en `EXCLUSIONES_PERMANENTES` respecto de archivos de test dev-only nuevos) quedó sin acción por decisión del Lead — sin riesgo funcional, ninguno de esos archivos está en `MANIFEST` hoy.
- Tests re-corridos después de las 2 correcciones: 99/99 OK, sin regresión.

## Fingerprint de dataset/artefacto (condicional — cambio sensible o reproducibilidad crítica)
No aplica — no hay dataset ni artefacto de modelo en este change de arquitectura del harness.

## Diferencias contra la spec
Ninguna sustancial. Nota de trazabilidad: el reviewer señaló que el cálculo de `changes`/`evidencia`/`actualizado_utc` a nivel de fase en `migrar_desde_legacy` (para fases con roll-up) recorre las etapas legacy en una pasada separada de la que calcula el estado de los pasos — mismo resultado correcto, pero es trabajo duplicado menor (dos pasadas sobre las mismas fuentes en vez de reutilizar lo ya calculado) — no es un desvío de la spec, es una observación de eficiencia menor sin impacto funcional, no se actuó sobre ella.

## Limitaciones
`kdd.md`/template no reciben el rewrite completo de "Lead methodology awareness" (project_stage/risk_level/readiness) — eso sigue siendo un change posterior, tal como fue aprobado explícitamente (K6). La asimetría cosmética de `EXCLUSIONES_PERMANENTES` (ver arriba) queda como deuda menor documentada, no bloqueante.

## Pendientes derivados
Ninguno bloqueante para este change. Recordatorio para changes futuros del roadmap: `unified-status-surface` (posterior) es el lugar natural para exponer `ds_guard lifecycle status/transition` de propósito general, explícitamente no incluidos acá.

## Resultado final
Todos los criterios de aceptación de `spec.md` cumplidos con evidencia real. Migración, roll-up, merge de convergencia, provenance, compatibilidad SDD/decision ledger, manifest/instalación scratch y documentación factual mínima — todo implementado, testeado y revisado. Change listo para cierre.
