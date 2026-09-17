# Propuesta — 20260917-multi-provider-adapters

## Problema
Harmessi depende hoy exclusivamente de la CLI de Claude Code para toda invocación de agentes.
`ARCHITECTURE.md` (v0.4 Change 3, "Deuda registrada" §4, puntos 2 y 4) ya documenta que el
acoplamiento a Claude Code — el contrato de datos de `pathguard.evaluar_tool_call` acoplado a la
forma exacta del JSON de `PreToolUse` (`tool_name`/`tool_input`/`agent_type`), y el instalador
(`tools/ds_init/*`) orientado únicamente a Claude Code — es el principal obstáculo para soportar
otro proveedor, sin resolverlo: queda explícitamente para v0.5.

## Objetivo
Crear adapters finos (Claude Code, Codex CLI, Gemini CLI, Grok CLI) que resuelvan invocación,
detección de capacidades/disponibilidad, identificación de provider/model y traducción mínima de
roles, sin implementar routing inteligente (Change 2) ni contaminar el core con lógica específica
de un proveedor.

## Evidencia
- `ARCHITECTURE.md`, sección "4. Deuda registrada", puntos 2 y 4.
- `docs/roadmap/v0.5.md`, sección "Change 0 — multi-provider-adapters".
- Verificado en este entorno con `command -v`: `claude` disponible
  (`/c/Users/fcolombo/.local/bin/claude`, versión `2.1.274`); `codex`/`gemini`/`grok`/`antigravity`
  ausentes de PATH.

## Supuestos descartados
Que "Gemini / Antigravity" (como aparecen juntos en la lista de proveedores objetivo del roadmap)
son un único proveedor con una sola CLI. Descartado: Antigravity es un producto IDE de Google sin
contrato de CLI headless público y estable conocido; este Change implementa el adapter para Gemini
CLI (`gemini`, con modo no interactivo `-p` documentado públicamente) y deja Antigravity fuera de
alcance explícito. No es un cambio arquitectónico material ni una contradicción de requisitos, es
una acotación de qué significa "Gemini/Antigravity" en términos de una CLI invocable, documentada
acá para que quede trazable.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica — este cambio no prueba una hipótesis metodológica, es infraestructura de invocación.

## Alcance
`tools/providers/` completo (core neutral + 4 adapters + tests), extensión de
`tools/harmessi/cli.py` con el subcomando `providers list`, actualización mínima de
`ARCHITECTURE.md` §2.1.

## Fuera de alcance
Routing inteligente (Change 2), fallback automático (Change 3), harmessi-bench (Change 1), adapter
de Antigravity IDE, instalación o autenticación automática de cualquier CLI de proveedor, cambios a
`ds_init`/instalación progresiva por stage (los adapters no se gatean por stage en este Change).

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
- Alcance aprobado: Change 0 — multi-provider-adapters tal como está descripto en
  `docs/roadmap/v0.5.md`.
- Versión de artefactos referenciada: primer borrador de estos 4 artefactos.
- Cita o descripción fiel de qué se aprobó: "Ejecutá autónomamente toda Harmessi v0.5 siguiendo
  `docs/roadmap/v0.5.md` ... Change 0 — multi-provider-adapters ... No pidas confirmación humana
  entre pasos normales." (instrucción explícita del usuario, 2026-09-17, invocando el "Contrato de
  autonomía" ya definido en `docs/roadmap/README.md`). El Lead verificó que ninguna de las 10
  condiciones STOP de `docs/roadmap/README.md` aplica a este Change antes de proceder sin ronda de
  revisión interactiva adicional.

## Motivo de rechazo
No aplica — estado no es `descartada`.

## Desacuerdo registrado
No aplica — no hubo rondas de revisión sin acuerdo.
