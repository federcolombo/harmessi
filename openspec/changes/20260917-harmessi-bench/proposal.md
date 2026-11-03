# Propuesta — 20260917-harmessi-bench

## Problema
Harmessi no tiene ningún mecanismo para medir calidad de comportamiento de agentes/harness de
forma reproducible y comparable entre configuraciones (provider/model/effort) o entre versiones;
los tests unitarios existentes verifican correctness determinista de código, no calidad agentic —
el roadmap v0.5 pide separar ambos explícitamente.

## Objetivo
Crear `tools/harmessi_bench/`, framework mínimo de evals con escenarios reproducibles, ejecución
contra un target reusando los adapters de Change 0, scoring determinista y almacenamiento/
comparación de resultados en JSON plano.

## Evidencia
- `docs/roadmap/v0.5.md`, sección "Change 1 — harmessi-bench".
- `tools/providers/core.py` (Change 0, commit `b254f13`, ya expone `ProviderAdapter`/
  `InvocationRequest`/`InvocationResult` reusables).
- `README.md` (patrón ya establecido de `.harmessi/profiles/<profile_id>/profile.json` para
  `ds_profile`, reusado acá para `.harmessi/evals/<run_id>/`).

## Supuestos descartados
Que evaluar "Lead/agentes/harness" (como dice el roadmap) implica simular un flujo multi-agente
completo de principio a fin. Descartado por alcance: v0.5 evalúa escenarios puntuales de
prompt→output contra un target, no flujos completos de Lead con SDD real (eso requeriría orquestar
subagentes reales dentro de un eval, con costo y complejidad no acotados, fuera de "framework
mínimo").

## Hipótesis (condicional — solo cambios metodológicos)
No aplica — este cambio no prueba una hipótesis metodológica, es infraestructura de evals del
harness.

## Alcance
`tools/harmessi_bench/` completo (core, scenarios, runner, storage, compare, cli, examples, tests),
`ARCHITECTURE.md`.

## Fuera de alcance
Routing (Change 2), fallback (Change 3), leaderboard público, evaluación real de flujos
multi-agente completos, LLM-as-judge, conversión de tests unitarios existentes en evals.

## Holdout policy (condicional — solo cambios "sensible")
No aplica — este cambio no toca datos ni holdouts de ningún proyecto DS, es tooling del harness.

## Impacto en production-readiness (opcional)
No aplica en esta etapa del harness.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md` (SDD completo).

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md` (SDD completo).

## Aprobación
- Usuario: Federico Colombo.
- Fecha: 2026-09-17.
- Alcance aprobado: Change 1 — harmessi-bench, `docs/roadmap/v0.5.md`.
- Versión de artefactos referenciada: primer borrador de estos 4 artefactos.
- Cita o descripción fiel de qué se aprobó: "Ejecutá autónomamente toda Harmessi v0.5 siguiendo
  `docs/roadmap/v0.5.md` ... Change 1 — harmessi-bench ... No pidas confirmación humana entre pasos
  normales." (instrucción explícita del usuario, 2026-09-17, invocando el "Contrato de autonomía"
  ya definido en `docs/roadmap/README.md`). El Lead verificó que ninguna de las 10 condiciones STOP
  de `docs/roadmap/README.md` aplica a este Change antes de proceder sin ronda de revisión
  interactiva adicional.

## Motivo de rechazo
No aplica — estado no es `descartada`.

## Desacuerdo registrado
No aplica — no hubo rondas de revisión sin acuerdo.
