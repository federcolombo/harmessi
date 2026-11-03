# Propuesta — 20261023-v014-evidence-comparison-decisions

## Problema
Un probe produce corridas, pero nada decide qué dice la evidencia ni impide que una candidate quede `promotable` por declaración.

## Objetivo
`decision.py`: recomputar desde `result.json` reales, con la política congelada del probe, un veredicto (reusando `compare_runs`), registrarlo con hash y ser el único camino hacia `evaluated/promotable/rejected/inconclusive`.

## Evidencia
`tools/harmessi_bench/compare.py` (veredictos y comparabilidad), `tools/harmessi_improve/probe.py` (`probe.json`, hashes de `result.json`), `candidate.transicionar`, `docs/roadmap/v0.14.md` D5–D6.

## Supuestos descartados
- Reimplementar el veredicto: `compare_runs` se llama sobre corridas agregadas.
- Recibir criterios como parámetro de la decisión: salen del `probe.json` congelado.

## Alcance
`tools/harmessi_improve/decision.py`, tests, ARCHITECTURE.md.

## Fuera de alcance
Promoción (Change 4), lessons, CLI. Dimensiones sin fuente confiable (tokens, retries, STOP) quedan declaradas como no soportadas.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-10-23
- Alcance aprobado: Harmessi v0.14 Change 3
- Versión de artefactos referenciada: ver control.json
