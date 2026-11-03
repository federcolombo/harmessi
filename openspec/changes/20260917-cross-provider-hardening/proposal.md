# Propuesta — 20260917-cross-provider-hardening

## Problema

Changes 0-3 de v0.5 (`multi-provider-adapters`, `harmessi-bench`, `provider-routing`,
`fallback-and-handoffs`) fueron implementados y verificados individualmente, pero solo 1 de los 4
providers soportados (`claude_code`) está realmente instalado en este entorno. Hace falta una
verificación ESTRUCTURAL y de CONTRATO -- no dependiente de que las otras 3 CLIs (Codex, Gemini,
Grok) estén instaladas -- que confirme que el comportamiento del harness es genuinamente uniforme
entre los 4 proveedores, y que el core (`tools/providers/core.py`, `tools/routing/core.py`,
`tools/fallback/core.py`, `tools/harmessi_bench/core.py`) no tiene ninguna dependencia accidental
de Claude Code específicamente.

## Objetivo

Agregar 4 archivos de test nuevos (contrato paramétrico de los 4 adapters, paridad de fallback
entre providers, paridad de routing entre providers, neutralidad estructural del core vía escaneo
de imports) que hagan estas garantías automáticas y permanentes: si alguien agrega un 5to provider
o rompe la neutralidad del core, un test falla en CI, no queda como convención tácita sostenida
solo por revisión manual.

## Evidencia

- `docs/roadmap/v0.5.md`, sección "Change 4 — cross-provider-hardening": "verificar que los
  contratos de Harmessi se comporten de forma coherente entre los proveedores soportados" +
  "ausencia de dependencia accidental de Claude en el core neutral" + "No agregar features nuevas
  en este Change salvo fixes necesarios para compatibilidad real".
- `ARCHITECTURE.md` y `tools/tests/test_architecture_boundaries.py` (patrón ya establecido de
  v0.4 Change 3, `20260916-portable-core`): escaneo de imports vía `ast`, no un analizador
  semántico completo -- mismo criterio de "límite deliberado, no sobreingeniería" que se reutiliza
  acá para la neutralidad del core de v0.5.
- `tools/providers/tests/test_adapters.py` (Change 0): `TestDeteccionSinCliInstalada` y
  `TestClaudeCodeInvokeArmadoComando` ya dejan documentada, por asimetría de estructura, la
  limitación menor de que solo `claude_code` tiene tests de armado de comando explícitos y una
  prueba real de detección (`test_claude_code_detect_real`, condicionada con `skipif`) -- este
  Change cierra esa asimetría de cobertura llevando el mismo parametrize de disponibilidad
  (`shutil.which` forzado a `None`) a los 4 adapters por igual.
- `tools/fallback/core.py` (Change 3), docstring del módulo: "Este archivo no importa
  `tools.harmessi_bench` ni ningún módulo de revisión en ningún punto -- es verificable por
  lectura directa" -- garantía ya confirmada manualmente por el reviewer de Change 3; este Change
  la vuelve automática vía test estructural.

## Supuestos descartados

Que "cross-provider hardening" requiere tener las 4 CLIs (Claude Code, Codex, Gemini, Grok)
instaladas para verificar algo real. Descartado explícitamente: la verificación más valiosa y
duradera es estructural (el core nunca puede depender de un proveedor concreto, sin importar
cuántos estén instalados en un entorno dado), complementada con smoke test real SOLO para el/los
proveedor/es realmente disponibles en este entorno (`claude_code`), documentado en
`verification.md` como matriz de cobertura real -- nunca fabricado ni inferido para los proveedores
ausentes.

## Alcance

Exactamente los 4 archivos de test descriptos en `spec.md` (R1-R4):
- `tools/tests/test_v05_core_neutrality.py`
- `tools/providers/tests/test_contract_parity.py`
- `tools/fallback/tests/test_cross_provider_parity.py`
- `tools/routing/tests/test_cross_provider_parity.py`

Sin ningún cambio a código de producción (`tools/providers/*.py` salvo `tests/`,
`tools/routing/*.py` salvo `tests/`, `tools/fallback/*.py` salvo `tests/`,
`tools/harmessi_bench/*.py`), salvo que la verificación descubra una incompatibilidad real entre
proveedores -- en cuyo caso el Lead decide un fix puntual como reinvocación correctiva, explícita y
separada, nunca como parte del alcance original de este Change.

## Fuera de alcance

- Cualquier feature nueva (el roadmap lo prohíbe explícitamente para Change 4).
- Instalación de Codex CLI, Gemini/Antigravity o Grok CLI.
- Smoke test real contra proveedores no instalados en este entorno -- inventaría disponibilidad,
  prohibido explícitamente por las reglas de autonomía del usuario y por el criterio de
  `design.md`.

## Holdout policy (condicional — solo cambios "sensible")

No aplica: este Change no toca datasets, holdouts ni features de ningún proyecto de ciencia de
datos -- es verificación estructural del harness/framework en sí.

## Criterios de aceptación (spec-lite — solo SDD abreviado)

Ver `spec.md` (SDD completo).

## Decisión técnica (design-lite — solo SDD abreviado)

Ver `design.md` (SDD completo).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-17
- Alcance aprobado: Change 4 — cross-provider-hardening (v0.5): 4 archivos de test nuevos de
  verificación estructural/contractual cross-provider, sin features nuevas ni código de producción
  nuevo salvo reinvocación correctiva explícita.
- Versión de artefactos referenciada: `docs/roadmap/v0.5.md` (commit base `d676e5b`, rama
  `v0.5-dev`), consistente con la aprobación ya otorgada para Changes 0-3 bajo el mismo contrato de
  autonomía de `docs/roadmap/README.md`.
- Cita o descripción fiel de qué se aprobó: mismo criterio y formato de aprobación que Changes 0-3
  de v0.5 (usuario Federico Colombo, fecha 2026-09-17, alcance explícito por Change, sin necesidad
  de una ronda de aprobación separada por artefacto dado que el roadmap ya secuencia y acota
  Change 4 en detalle suficiente).

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
