# Propuesta — 20260917-provider-routing

## Problema
Harmessi ahora tiene múltiples adapters de proveedor (v0.5 Change 0,
`multi-provider-adapters`, `tools/providers/`) pero ninguna forma explícita,
configurable y trazable de decidir qué provider/model/effort corresponde a
cada rol/tarea -- hoy la única opción implícita es Claude Code, sin ningún
mecanismo de decisión declarado.

## Objetivo
Crear `tools/routing/`, un resolutor puramente declarativo (`RoutingPolicy`
→ `RoutingDecision`) que decide provider/model/effort por rol+tipo de tarea
según reglas explícitas ya escritas por un humano, sin inferir ni optimizar
automáticamente, y sin routing inteligente basado en costos/tokens no
observables.

## Evidencia
- `docs/roadmap/v0.5.md`, Change 2 (`provider-routing`).
- `tools/providers/core.py` (Change 0, ya commiteado): expone
  `ProviderInfo`/`list_providers` reusables para chequear disponibilidad,
  opcionalmente, desde el CLI de este Change.
- `README.md` (patrón de `.harmessi/scientific-policy.json`): política
  opcional, ausencia = N/A sin heurística, mismo criterio editorial reusado
  acá para `.harmessi/routing.json`.
- Verificado en este entorno (Change 0/1 ya lo confirmaron): solo
  `claude_code` está disponible, por lo que la recomendación del roadmap de
  "reviewer de familia de modelo distinta cuando esté disponible" no se
  puede satisfacer con una segunda familia real hoy -- se documenta como
  limitación (ver `design.md`, "Riesgos", y `verification.md`), no se
  inventa una falsa disponibilidad.

## Supuestos descartados
Que routing debería auto-seleccionar el "mejor" provider/model basado en
resultados de `harmessi-bench` de forma automática -- descartado
explícitamente por el roadmap ("no inventar una optimización automática
basada en costos/tokens no observables"). "Cuando corresponda, usar
resultados reales de evals como evidencia" es guía para quien ESCRIBE una
regla de `RoutingPolicy` a mano, citándolo en el campo `reason`, no una
feature de auto-tuning del propio módulo.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica.

## Alcance
- `tools/routing/` completo: `core.py`, `policy.py`, `examples/
  policy.example.json`, `tests/__init__.py`, `tests/test_core.py`,
  `tests/test_policy.py`.
- Wiring en `tools/harmessi/cli.py`: subcomando `routing` con
  `routing show` y `routing resolve`.
- `tools/harmessi/tests/test_routing_cli.py`.
- `ARCHITECTURE.md` §2.1 (fila nueva para `tools/routing/core.py`).

## Fuera de alcance
- Fallback automático de provider (Change 3 del roadmap).
- Auto-optimización basada en costos/tokens/evals.
- Invención de disponibilidad o performance de un provider no verificado.
- Escribir una política real (`.harmessi/routing.json`) para este propio
  repo -- el ejemplo vive en `tools/routing/examples/`, no en `.harmessi/`.

## Holdout policy (condicional — solo cambios "sensible")
No aplica -- este cambio no toca ningún dataset ni holdout de un proyecto
de ciencia de datos, es infraestructura de configuración del harness.

## Impacto en production-readiness (opcional)
No aplica en este bloque.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md` (SDD completo).

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md` (SDD completo).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-17
- Alcance aprobado: Change 2 — provider-routing
- Versión de artefactos referenciada: esta versión de `proposal.md`,
  `spec.md`, `design.md`, `tasks.md` (commit de este Change)
- Cita o descripción fiel de qué se aprobó: mismo contrato de autonomía de
  `docs/roadmap/README.md` ya aplicado a Changes 0 y 1 de v0.5 -- el usuario
  aprobó de antemano la ejecución de los Changes del roadmap v0.5 en el
  orden declarado, bajo el mismo criterio de evidencia/alcance/reversión
  documentado ahí, adaptado acá explícitamente a "Change 2 —
  provider-routing".

## Motivo de rechazo
No aplica (estado: no descartada).

## Desacuerdo registrado
No aplica.
