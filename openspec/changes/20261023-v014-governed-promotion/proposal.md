# Propuesta — 20261023-v014-governed-promotion

## Problema
Una candidate `promotable` no tiene camino gobernado hacia el harness activo; sin él, la promoción sería manual y sin evidencia ligada, o peor, un bypass.

## Objetivo
`promotion.py`: generar una propuesta de promoción (diff + evidencia + hashes) y un gate fail-closed que solo permite aplicarla dentro de un Change normal con aprobaciones T1 (`console_confirmed`).

## Evidencia
`tools/dsguard/sdd.py` (`resolver_aprobacion_registrada`), `tools/dsguard/scope.py` (`alcance_efectivo`), `tools/dsguard/human_presence.py` (`CANAL_CONSOLE`), `tools/harmessi_improve/decision.py` (`verificar_promotable`), `docs/roadmap/v0.14.md` D7.

## Supuestos descartados
- Que la evaluación reemplace al Change: Evaluation ≠ verificación de release; el Change sigue exigiendo tests, reviewer y approvals.
- Un ledger de promociones: se reutiliza el Decision Ledger; solo se emite el texto candidato.

## Alcance
`tools/harmessi_improve/promotion.py`, tests, ARCHITECTURE.md.

## Fuera de alcance
CLI (Change 5), cambios al trust model, promoción de una candidate real en el release.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-10-23
- Alcance aprobado: Harmessi v0.14 Change 4
- Versión de artefactos referenciada: ver control.json
