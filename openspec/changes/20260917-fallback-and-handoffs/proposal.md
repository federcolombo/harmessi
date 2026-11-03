# Propuesta — 20260917-fallback-and-handoffs

## Problema
Harmessi tiene adapters de proveedor de IA (Change 0), un framework de evals (Change 1) y routing
declarativo provider/model/effort por rol+tarea (Change 2), pero ninguna forma de continuar
automáticamente ante la indisponibilidad real y acotada de un proveedor (cuota agotada, CLI no
instalada, sesión no autenticada), ni un mecanismo explícito para que el trabajo de un Change
continúe entre sesiones/proveedores sin reiniciar trabajo ya hecho ni duplicar auditorías ya
corridas.

## Objetivo
Agregar `tools/fallback/core.py` (motor técnico de fallback: reintenta con el siguiente proveedor
de una cadena SOLO cuando `InvocationResult.availability_error` es elegible -- `"quota"`,
`"unavailable"` o `"unauthenticated"` -- nunca ante error semántico/de código, hallazgo de
`data-science-reviewer`, test fallido o mala calidad de output, señales que este módulo ni
siquiera importa) y `tools/fallback/handoff.py` (contexto mínimo de continuidad a nivel SDD: qué
ya se hizo, qué falta, qué ya se auditó, para no reiniciar trabajo ni duplicar revisión entre
sesiones/proveedores). Extiende de forma aditiva el schema de `RoutingRule`/`RoutingDecision` de
Change 2 con `fallback_chain: List[str] = []` (default vacío: cualquier política de routing
existente sigue funcionando exactamente igual).

## Evidencia
- `docs/roadmap/v0.5.md`, Change 3 (`fallback-and-handoffs`).
- `tools/providers/core.py::classify_availability_error` (Change 0, ya commiteado) -- única fuente
  de los 3 valores de disponibilidad (`"quota"`/`"unavailable"`/`"unauthenticated"`) que este
  Change reusa sin agregar ninguna heurística nueva.
- `tools/routing/core.py::RoutingRule`/`RoutingDecision` y `tools/routing/policy.py` (Change 2, ya
  commiteado) -- base sobre la que se extiende de forma aditiva.
- Verificado en este entorno de forma directa (sin fabricar nada): `codex` (CLI no instalada acá)
  seguido de `claude_code` (CLI instalada y autenticada) es una cadena de fallback real y
  demostrable de punta a punta -- el primer proveedor falla limpio con
  `availability_error="unavailable"`, el segundo responde de verdad. Este es el smoke que el Lead
  corre fuera de esta sesión (ver `tasks.md`).

## Supuestos descartados
Se descartó la interpretación de que "handoffs" en el roadmap se refiere solo a la continuidad
técnica entre CLIs de proveedor (lo que ya cubriría `tools/fallback/core.py` por sí solo). El
roadmap exige explícitamente "sin duplicar auditorías" y "preservando SDD, estado del Change y
trazabilidad" -- estos son conceptos de continuidad de TRABAJO a nivel de Change/sesión, no de
invocación de proveedor. Por eso `tools/fallback/handoff.py` existe como pieza separada del motor
técnico de `core.py`, en vez de conflacionar ambos conceptos en un mismo módulo.

## Alcance
- `tools/fallback/` completo: `__init__.py`, `core.py`, `handoff.py`, `tests/__init__.py`,
  `tests/test_core.py`, `tests/test_handoff.py`.
- Extensión aditiva de `tools/routing/core.py`, `tools/routing/policy.py`,
  `tools/routing/examples/policy.example.json`, `tools/routing/tests/test_core.py`,
  `tools/routing/tests/test_policy.py` (Change 2, ya cerrado).
- Wiring en `tools/harmessi/cli.py`: subcomando `fallback` con `resolve-chain` e `invoke`, y su
  test `tools/harmessi/tests/test_fallback_cli.py`.
- `ARCHITECTURE.md` §2.1: dos filas nuevas, una por cada módulo de `tools/fallback/` (sin
  conflacionarlos).
- `openspec/changes/20260917-fallback-and-handoffs/verification.md`.

## Fuera de alcance
- Cross-provider hardening real con múltiples CLIs de proveedor instaladas simultáneamente
  (Change 4 del roadmap).
- Release hardening (Change 5 del roadmap).
- Cualquier heurística que use resultados de `harmessi_bench` (calidad de output) o hallazgos de
  `data-science-reviewer` para decidir fallback -- explícitamente prohibido por el roadmap y por
  este proposal; el motor de fallback de este Change no importa `tools.harmessi_bench` en ningún
  punto.

## Holdout policy (condicional — solo cambios "sensible")
No aplica: este Change es infraestructura del harness (motor de fallback entre CLIs de proveedor y
contexto de continuidad SDD), no toca ningún dataset ni holdout de proyecto.

## Decisión de extensión de schema (documentada explícitamente)
`RoutingRule`/`RoutingDecision` de Change 2 (ya cerrado y commiteado) se extienden con un campo
nuevo `fallback_chain: List[str] = field(default_factory=list)`, agregado AL FINAL de cada
dataclass, aditivo y con default vacío. No rompe ninguna política ni test existente de Change 2:
los 11 tests preexistentes de `tools/routing/tests` siguen pasando sin modificación, y este Change
solo agrega tests nuevos. El Lead evaluó que esto NO constituye un "cambio incompatible de
schema/contrato" (condición STOP del roadmap) precisamente porque es aditivo y retrocompatible: un
`routing.json` existente sin el campo sigue cargando y resolviendo exactamente igual que antes.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md` (SDD completo para este Change).

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md` (SDD completo para este Change).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-17
- Alcance aprobado: Change 3 — fallback-and-handoffs (`tools/fallback/` completo, extensión
  aditiva de `tools/routing/*`, wiring en `tools/harmessi/cli.py`, `ARCHITECTURE.md` §2.1)
- Versión de artefactos referenciada: esta versión de `proposal.md`/`spec.md`/`design.md`/
  `tasks.md`, commit base `af8df4f` (`v0.5-dev`)
- Cita o descripción fiel de qué se aprobó: mismo contrato de autonomía de `docs/roadmap/README.md`
  ya aplicado a Changes 0/1/2 del mismo usuario y misma fecha (2026-09-17) -- el usuario aprobó de
  antemano que `python-data-engineer` ejecute el Change 3 del roadmap v0.5 en una sola sesión,
  incluyendo la extensión aditiva de schema de Change 2 documentada arriba, sujeta a revisión de
  `data-science-reviewer` antes de cierre.

## Motivo de rechazo
No aplica (estado no es `descartada`).

## Desacuerdo registrado
No aplica (no hubo 2 rondas de revisión sin acuerdo).
