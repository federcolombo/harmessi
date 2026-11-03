# Tareas — 20261026-v015-evidence-privacy-hardening

estado: cerrada

## Invocaciones planificadas
- python-data-engineer (writer único, secuencial T1..T8): implementa en su ownership; no ejecuta.
- data-science-reviewer: revisa el Change completo tras T8 (privacidad sin sobre-afirmar, retrocompatibilidad, honestidad de límites).
- Lead: corre tests en `.venv` por lotes, genera el fixture v0.14.0 (git archive fuera del repo), cierra el Change.
<!-- rol, momento del ciclo, y qué produce cada una -->

## Ownership de writers
<!-- solo si se lanzan 2+ instancias writer en paralelo; declarar ANTES de lanzar.
### W1 — python-data-engineer — T1
- ruta/archivo.py
- directorio/**
-->

## Historial de ownership
<!-- fecha — instancia — ruta — motivo (cambios de ownership hechos ANTES de que el writer edite) -->

## Skills cargados
<!-- - <skill> — <tarea> — <motivo>  (solo si la skill cambió una decisión, un criterio de aceptación, la delegación —incluido el puntero a la skill en el campo 2—, el scope/ownership o el diseño; si sin ella el resultado habría sido otro. Una lectura exploratoria sin efecto, o una skill que perdió un conflicto sin influir, no lleva bullet. Un bullet por skill; si hubo conflicto, el criterio va en el motivo del bullet de la que ganó) -->

## Tareas
- [x] T1 (F) Lead: generar fixture Data Card v1 con el código del tag v0.14.0 (`generate_datacard_v014.py` solo-checkout) -> `tools/tests/fixtures/compat/v0_14/data_card.json` + MANIFEST; el writer agrega el generador y el test de lectura v0.15.
- [x] T2 (B-20) Test de barrido de privacidad transversal + lista blanca mínima + tests positivo/negativo.
- [x] T3 (B-21) Tests e2e de cadena candidate->probe->decision->proposal->apply con manipulación por eslabón; decisión sobre atar probe en proposal (aditivo) o limitación.
- [x] T4 (B-22) Tests de scope_hash/enmiendas en el gate de promoción y de ledger_text sin escritura.
- [x] T5 (B-23/B-25) Tests GLOSSARY ausente y lesson symlink/junction; documentar project-owned vs global.
- [x] T6 (B-24) Bench: run_id reservados Windows, result.json corrupto, bloques incompletos, caso v0 como suite, NFC/NFD, `--fail-on-failure` opt-in; tests.
- [x] T7 Documentación: matriz B-20..B-25, roadmap §C5, `docs/versioning.md`, ARCHITECTURE/README si cambia lo documentado.
- [x] T8 Cierre del writer: lista de tests para el Lead; confirmar que no se tocó `.claude/settings.json` ni hashes managed.

### Desvíos respecto de spec/proposal (revisión independiente)
- R4 de spec.md dice que GLOSSARY ausente degrada a `privacidad_no_superada`, pero el comportamiento real y testeado es: ausente -> no degrada; existente e ilegible -> degrada. No se cambió producción (es comportamiento previo).
- Alcance A prometía barrer GLOSSARY: no implementado (ruidoso/no estable); declarado en la matriz B-20.

## Dependencias

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->
