# Tareas — 20261026-v015-public-docs-evals

estado: cerrada

## Invocaciones planificadas
- python-data-engineer (writer único, secuencial T1..T7): implementa; no ejecuta.
- data-science-reviewer: revisa docs y test tras T7 (afirmaciones no observadas, comandos inexistentes, privacidad).
- Lead: corre tests por lotes y cierra el Change.
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
- [x] T1 (B-34) `.gitattributes` acotado + verificación `git ls-files --eol` por el Lead.
- [x] T2 (B-27/B-28) `docs/installation.md` y `docs/cli-reference.md` derivados de README y de los parsers argparse.
- [x] T3 (B-26) `docs/evaluation.md` con datos leídos de los JSON de suite.
- [x] T4 (B-27) `docs/concepts.md` y `docs/security-and-trust.md`.
- [x] T5 (B-29/B-30) `docs/release-process.md` (runbook) con estado de CI «pending observation».
- [x] T6 (B-27) README (índice, `python -m tools.reporting`), ARCHITECTURE §4/§4.1, `verificador.md` + template.
- [x] T7 `tools/tests/test_public_docs.py` + matriz de deuda y roadmap §C6.

## Dependencias

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->
