# Verificación — 20261026-v015-debt-archaeology-and-roadmap

## Resumen
Change 0 de v0.15: arqueología de deuda y roadmap. Solo documentación y SDD; sin cambios en `tools/**`.

## Archivos entregados
- `docs/roadmap/v0.15.md` (133 líneas).
- `docs/roadmap/v0.15-debt-matrix.md` (177 líneas).
- `docs/roadmap/README.md` (+1 línea para v0.15).
- Artefactos SDD en `openspec/changes/20261026-v015-debt-archaeology-and-roadmap/`.

## Evidencia obtenida
- Verificación del Lead con grep sobre la tabla de la matriz: 116 filas (22 A / 34 B / 33 C / 19 D / 8 E).
- 20 filas B bloqueantes de v1: B-01, 02, 03, 04, 05, 07, 08, 10, 13, 17, 20, 21, 23, 26, 27, 28, 29, 30, 32, 33.
- Auditoría con tres barridos de solo lectura: (1) roadmaps v0.4–v0.9 + ARCHITECTURE; (2) roadmaps/releases v0.10–v0.14 + docs + CI; (3) verification/design v0.11–v0.14 + README + código.
- Entorno: main == origin/main == `0207977`; sin tag `v0.15.0`; solo `claude` 2.1.310 disponible (codex, gemini, grok y antigravity ausentes); sin `gh`.

## Hallazgos clave
- La telemetría de subagentes sí se puebla por hook; la premisa histórica está obsoleta.
- ARCHITECTURE §4/§4.1 está desactualizada.
- Siguen vigentes: `ds_profile` columnar, bytes/dtype y Data Card as-of.
- H1 sigue UNCONFIRMED.
- T2 pasa a POST-v1.

## Limitaciones
- No se ejecutaron tests (cambio solo de documentación).
- Ítems marcados "no verificado" en los informes de barrido: A-04, A-17, A-34, A-44, A-49, B-02, B-11 (doc), B-13, B-20, B-30, B-41, B-44, B-59, C-08, C-19. Su clasificación se basa en lectura de documentos y puede revisarse en el Change que los toque.
- Revisor no convocado (solo documentación, como en v0.14 C0).

## Divergencias respecto del SDD
Ninguna.

## Deudas abiertas
Las listadas como B en `docs/roadmap/v0.15-debt-matrix.md`; las 20 bloqueantes de v1 quedan para los Changes siguientes.

## Resultado final
Change 0 cerrado: roadmap v0.15 y matriz de deuda entregados.
