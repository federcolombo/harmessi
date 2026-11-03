# Propuesta — 20261023-v014-candidate-model-isolation

## Problema
No existe una representación de una variante experimental de una superficie Optimizable que sea aislada, reproducible por hash y que rechace estructuralmente Protected y Project-owned.

## Objetivo
Contrato `Candidate` + almacenamiento aislado + budgets de mejora (base de todo ciclo acotado).

## Evidencia
`tools/dsguard/skill_contract.py:192` (`superficie_de_ruta`), `tools/harmessi_bench/redact.py` (`redactar_texto`), `tools/harmessi_bench/runmanifest.py` (`hash_contenido`), `tools/ds_init/check_manifest_parity.py:51` (`SOLO_CHECKOUT`), `docs/roadmap/v0.14.md` (D1–D3, D9).

## Supuestos descartados
- Carpeta de candidates fuera de `.harmessi/`: `.harmessi/` ya es Protected, ignorado por Git y no instalado.
- Un registro de candidates versionado en Git: sería evidencia experimental trackeada.

## Alcance
Paquete `tools/harmessi_improve/` (`candidate.py`, `budget.py`), tests, registro en `SOLO_CHECKOUT`, ARCHITECTURE.md, test de neutralidad/arquitectura.

## Fuera de alcance
Probe, decisión, promoción, lessons, CLI (Changes 2–5).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-10-23
- Alcance aprobado: Harmessi v0.14 Change 1
- Versión de artefactos referenciada: ver control.json
