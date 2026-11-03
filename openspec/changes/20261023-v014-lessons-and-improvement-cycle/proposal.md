# Propuesta — 20261023-v014-lessons-and-improvement-cycle

## Problema
Falta (a) capturar aprendizaje reutilizable respaldado por evidencia sin convertirlo en memoria libre ni filtrar conocimiento del proyecto, (b) un ciclo de mejora acotado con techo duro y sin recursión, y (c) una CLI para operar el flujo.

## Objetivo
`lessons.py` (contrato estructurado, privacidad, aplicabilidad, vigencia, creación gobernada), `cycle.py` (ciclo acotado, sin anidamiento ni auto-optimización del engine) y `cli.py` (`python -m tools.harmessi_improve`).

## Evidencia
`tools/harmessi_improve/{budget,candidate,probe,decision,promotion}.py`; `tools/harmessi_bench/redact.py`; `tools/dsguard/glossary.py`; `docs/roadmap/v0.14.md` D8–D9.

## Supuestos descartados
- Lessons como memoria del LLM: son archivos estructurados, acotados, inspeccionables y ligados a decisiones recomputables.
- Estados sin consumidor: solo `hypothesis`, `evidence-backed`, `deprecated`; el estado lo calcula el módulo, no el autor.

## Alcance
`lessons.py`, `cycle.py`, `cli.py`, `__main__.py`, tests, neutralidad, ARCHITECTURE.md.

## Fuera de alcance
Biblioteca global de lessons, aprendizaje automático en ejecuciones normales, ledger de promociones nuevo, telemetría.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-10-23
- Alcance aprobado: Harmessi v0.14 Change 5
- Versión de artefactos referenciada: ver control.json
