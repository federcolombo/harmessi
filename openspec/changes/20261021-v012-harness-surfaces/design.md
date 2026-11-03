# Diseño — 20261021-v012-harness-surfaces

## Decisión
La superficie se **deriva** de la ruta (D3 del roadmap): una tabla de prefijos/archivos en `skill_contract.py`, sin metadata. Default de seguridad: lo desconocido bajo `.claude/` o `tools/` es *protected*; el resto es *project-owned*.
`optimizable` es una lista explícita (allowlist), no un default.

## Alternativas descartadas
- Campo `surface` en frontmatter: ornamental, además una skill podría mentir sobre sí misma.
- Módulo nuevo `surfaces.py`: sin otro consumidor; se reutiliza `skill_contract.py` (manifest ya lo incluye).
- Hacer fallar Doctor: una skill es guidance; se mantiene WARN.

## Notas
- Optimizable ≠ auto-modificable: en v0.12 cualquier cambio sigue siendo un Change normal. La distinción prepara v0.14 (mejora dirigida por evidencia) y prohíbe por diseño tocar *Protected*.
- `templates/` (scaffolding con estructura parseada) y `sdd.md`/`verificador.md`/`decision-ledger.md` quedan *Protected* (su forma la consumen validadores).
- Riesgo: clasificar mal un archivo. Mitigación: test contra rutas reales del repo.

## Decisiones materiales pendientes
Ninguna.
