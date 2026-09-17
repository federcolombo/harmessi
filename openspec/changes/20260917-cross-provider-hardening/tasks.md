# Tareas — 20260917-cross-provider-hardening

estado: cerrada

## Invocaciones planificadas

1. **`python-data-engineer`** (esta sesión) -- SDD (`proposal.md`/`spec.md`/`design.md`/`tasks.md`)
   + los 4 archivos de test de `spec.md` R1-R4. Scope declarado desde el inicio en `control.json`.
   No corre pytest ni `ds_guard approve`/`transition` (sin herramienta de ejecución).
2. **Lead** -- corre las 4 suites nuevas + regresión completa de `tools/providers/tests` +
   `tools/routing/tests` + `tools/fallback/tests` (confirma 0 regresiones sobre Changes 0-3); arma
   la matriz de cobertura de smoke real por adapter (`claude_code=REAL`, ya cubierto en
   Changes 0/1/3; `codex/gemini/grok=N/A no instalados`) para `verification.md`.
3. **`data-science-reviewer`** -- revisa el diff completo, con foco en: (a) si los tests de
   paridad realmente prueban paridad genuina entre los 4 proveedores (no solo repiten el mismo
   caso 4 veces con distinto nombre sin variar nada sustantivo); (b) si el escaneo AST de
   neutralidad del core (R1) es preciso, sin falsos negativos (p. ej. imports diferidos no
   detectados) ni falsos positivos (p. ej. el string `"claude"` en un docstring marcado
   incorrectamente como violación).
4. **`python-data-engineer`** -- aplica fixes puntuales si el reviewer encuentra hallazgos, y
   escribe `verification.md` con la matriz de cobertura real armada por el Lead en el paso 2.
5. **`python-data-engineer`** -- escribe `verification.md` (evidencia completa de las 4 rondas
   anteriores, incluida la matriz de cobertura de smoke por adapter). Ver
   `openspec/changes/20260917-cross-provider-hardening/verification.md`.

## Tareas

- [x] `tools/tests/test_v05_core_neutrality.py`: neutralidad estructural del core (R1).
- [x] `tools/providers/tests/test_contract_parity.py`: contrato paramétrico de los 4 adapters
      (R2).
- [x] `tools/fallback/tests/test_cross_provider_parity.py`: paridad de fallback entre providers
      (R3).
- [x] `tools/routing/tests/test_cross_provider_parity.py`: paridad de routing entre providers
      (R4).
- [x] `verification.md`: matriz de cobertura de smoke real por adapter (a completar por el Lead
      tras correr las suites, en la invocación 2/4 de este flujo).

## Dependencias

Lee, pero no modifica, código de producción de Changes 0-3 (`tools/providers/*.py`,
`tools/routing/*.py`, `tools/fallback/*.py`, `tools/harmessi_bench/*.py`, excluyendo sus
subdirectorios `tests/`). Depende de que esos 4 Changes ya estén mergeados en `v0.5-dev` (commit
base `d676e5b`, confirmado en `control.json`).

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->
No aplica (estado no es `pausada_bloqueada`).
