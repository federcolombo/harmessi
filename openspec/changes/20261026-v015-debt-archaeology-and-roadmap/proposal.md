# Propuesta — 20261026-v015-debt-archaeology-and-roadmap

## Problema
La deuda histórica de Harmessi (roadmaps v0.4–v0.14, release notes, ARCHITECTURE) no está consolidada en un
único inventario. ARCHITECTURE §4/§4.1 sigue diciendo "deuda no resuelta" y está desactualizada. Sin una
clasificación explícita no se puede planificar v0.15 ni decidir si v1.0 es planificable.

## Objetivo
Producir la matriz única de deuda y el roadmap congelado de v0.15 (8 Changes), solo documentación.

## Evidencia
Auditoría sobre `main == origin/main == 0207977` (v0.14.0 publicada), por lectura y grep, sin ejecutar tests.
Los ítems y su evidencia puntual (archivo:línea) están en `docs/roadmap/v0.15-debt-matrix.md`.

## Supuestos descartados
- La telemetría de subagentes "nunca poblada": el hook ya puebla `sesion["subagentes"]` (`hook_presupuesto.py:364`).
- La deuda de ARCHITECTURE §4 pto 1 (hooks con lógica pura): ya resuelta (D-001).

## Alcance
- Matriz de deuda: tabla única, cada ítem en exactamente una categoría (A resuelto, B v0.15, C limitación aceptada, D post-v1, E obsoleto).
- Roadmap de v0.15: objetivo, principios, decisiones D1–D7, 8 Changes y criterios de salida.
- Mapeo de los 14 criterios de `docs/roadmap/v1.0.md` a los Changes.
- Entrada de índice de v0.15 en `docs/roadmap/README.md`.

## Fuera de alcance
- Código, tests, schemas, datos, plantillas, `ARCHITECTURE.md` (su actualización va en C6).
- Cualquier ejecución o instalación; declarar v1.0.
- PKI, SaaS, GUI/TUI, catálogo propio, scheduler, marketplace, memoria global privada, auto-optimización de Protected, mejora recursiva infinita, plataforma MLOps genérica.

## Holdout policy (condicional — solo cambios "sensible")
No aplica: no se toca ningún holdout.

## Impacto en production-readiness (opcional)
Ninguno. La decisión de ciclo de vida production/deployment/monitoring se planifica en C3.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md`.

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md`.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado
- docs/roadmap/v0.15.md
- docs/roadmap/v0.15-debt-matrix.md
- docs/roadmap/README.md

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
