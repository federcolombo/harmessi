---
estado: cerrada
---

# Tareas — 20260929-lead-execution-runtime

Orden de invocaciones planificadas. `T0` ya está hecha (es el audit documentado con evidencia en
`proposal.md`, por el Lead en modo lectura). `T1..Tn` son invocaciones futuras del
`python-data-engineer` (único subagente con permiso de escritura), en el orden en que deben pedirse
— core/allowlist primero (nada más depende de ejecución real todavía), el script que cierra el gap
del audit antes que `scripts.py` (para no dejar el hallazgo documentado-pero-no-cerrado más tiempo
del necesario), `runtime.py` al final porque compone todo lo anterior, CLI después de tener algo que
invocar, tests de repo/manifiesto/neutralidad intercalados con cada pieza (no al final en bloque), y
la suite completa solo en el gate de cierre.

## T0 — Audit (hecho, Lead, solo lectura)

- [x] Confirmar que `tools/notebook_runner.py` no existe (Glob sin resultados) pese a estar
  referenciado por `tools/nbrunner/hook_validar_comando.py:66-69` y `.claude/agents/notebook-runner.md`.
- [x] Confirmar que no existe `tools/nbrunner/tests/` ni `tools/tests/test_nbrunner.py`.
- [x] Leer completos `tools/nbrunner/hook_validar_comando.py` y `tools/nbrunner/manifest.py`.
- [x] Leer la tabla de política de `tools/autonomy/core.py` (`POLICY_TABLE`, `ApprovalRef`,
  `PolicyApproval`) y confirmar la fila `execute_project_code`.
- [x] Confirmar `stage_minimo` real de las entradas de `nbrunner` en `tools/ds_init/manifest.py`.
- [x] Confirmar la invocación real de las 3 CLIs (`ds_guard.py`, `-m tools.ds_profile`,
  `-m tools.harmessi`) contra `README.md`.
- Evidencia de todo lo anterior: `proposal.md`, sección "Evidencia".

## T1 — `tools/leadrun/core.py` (python-data-engineer)

- Implementar `ExecutionForm`, `ExecutionRequest`, `ExecutionRecord`, catálogo único de códigos
  `EXEC-*` (R4-R7 de `spec.md`). Solo stdlib.
- QA: tests unitarios de validación/round-trip de cada tipo (parte de R5, R7).
- Entregable de esta invocación: `tools/leadrun/__init__.py`, `tools/leadrun/core.py`,
  `tools/leadrun/tests/test_core.py`.

## T2 — `tools/leadrun/allowlist.py` (python-data-engineer)

- Implementar `evaluar_comando` con las 4 formas de D2 (R8-R9). Reutilizar literalmente
  `PATRON_COMANDO` de `tools/nbrunner/hook_validar_comando.py:66-69` para la forma (c), sin
  modificar ese archivo.
- QA: los casos `Given/When/Then` de R8 completos (encadenamiento, traversal, intérprete ajeno,
  fuera de alcance, las 4 formas positivas) como tests parametrizados.
- Entregable: `tools/leadrun/allowlist.py`, `tools/leadrun/tests/test_allowlist.py`.

## T3 — `tools/notebook_runner.py` + `tools/leadrun/notebooks.py` (python-data-engineer)

Antes que `scripts.py` porque cierra el gap del audit (D7) y porque `tools/leadrun/runtime.py`
necesita ambos caminos (script y notebook) disponibles antes de poder componerlos de forma
simétrica.

- Implementar `tools/leadrun/notebooks.py` componiendo `tools.nbrunner.{core,execute,fsdiff,
  manifest}` (sin lógica nueva de validación, R11 de `spec.md`, §3 de `design.md`).
- Implementar `tools/notebook_runner.py` (`run --manifest <ruta> [--dry-run|--execute]`) siguiendo
  exactamente la secuencia de R11: cargar manifest → validar (interprete/hash/aprobación/rutas
  prohibidas) → dry-run informa sin ejecutar → execute hace snapshot/ejecuta/snapshot/diff/
  clasifica/cuarentena → imprime resultado + exit code.
- QA: los 4 casos `Given/When/Then` de R11 (hash desincronizado, ejecución exitosa, aprobación
  ausente, compatibilidad con `PATRON_COMANDO` sin tocar `hook_validar_comando.py`).
- Entregable: `tools/notebook_runner.py`, `tools/leadrun/notebooks.py`,
  `tools/leadrun/tests/test_notebooks.py`, `tools/tests/test_notebook_runner.py`.

## T4 — `tools/leadrun/scripts.py` (python-data-engineer)

- Implementar `ejecutar_script`/`ejecutar_pytest` sobre `subprocess.run(..., timeout=...)` (R10).
- QA: fixtures sintéticos de script (`exit 0`, `exit 1`, timeout) bajo `tools/leadrun/tests/
  fixtures/`; verificar truncado/redacción de `stdout_summary`/`stderr_summary` con
  `tools.datasources.scan` (R9 de `spec.md`, `runtime.py` es quien invoca el scan — confirmar en
  esta tarea si el scan se aplica en `scripts.py` o se delega a `runtime.py`; el diseño (§1 de
  `spec.md`) fija el import de `scan` en `runtime.py`, no en `scripts.py`, así que `scripts.py`
  devuelve el `ExecutionRecord` sin redactar y `runtime.py` redacta antes de persistir).
- Entregable: `tools/leadrun/scripts.py`, `tools/leadrun/tests/test_scripts.py`.

## T5 — `tools/leadrun/runtime.py` (python-data-engineer)

- Orquestar `ExecutionRequest -> allowlist -> (scripts.py | notebooks.py) -> redacción con
  datasources.scan -> ExecutionRecord -> persistencia atómica` (R7, R9, R13, R16).
- Implementar el gate: sin aprobación vigente en `supervised`, no ejecuta y no persiste éxito
  (R12-R13).
- QA: test de que `runtime.py` es el único punto que persiste `ExecutionRecord` (R13); test de
  persistencia atómica (R16); test de redacción de secretos en `argv`/summaries usando fixtures con
  patrones de credencial (mismos casos positivos/negativos que ya usa
  `tools/datasources/scan.py` — reutilizados, no reinventados).
- Entregable: `tools/leadrun/runtime.py`, `tools/leadrun/tests/test_runtime.py`.

## T6 — CLI `ds_guard.py exec script|pytest|notebook` (python-data-engineer)

- Subcomandos con imports perezosos, `--json`, exit codes 0/1/2/3 (R14), `--change-id` para
  resolver `scope` vía `control["alcance"]["rutas_autorizadas"]` (mismo mecanismo de
  `tools/ds_guard.py:217-218`).
- Función privada de composición de aprobación (`execute_project_code` × modo, R12) en `ds_guard.py`
  — no en `tools/leadrun/` (dirección de dependencias, R1/R2 de `spec.md`).
- QA: los 3 casos `Given/When/Then` de R14 (autonomous sin aprobación ejecuta; supervised sin
  aprobación rechaza; supervised con aprobación vigente ejecuta).
- Entregable: cambios en `tools/ds_guard.py` (subcomandos nuevos, sin tocar los existentes de
  `contract`/`source`), `tools/tests/test_ds_guard_exec.py`.

## T7 — Tests de repo, manifiesto y neutralidad (python-data-engineer)

- `tools/tests/test_v08_leadrun_neutrality.py` (R1-R3, R15).
- Entradas nuevas en `tools/ds_init/manifest.py` para `tools/leadrun/*` y
  `tools/notebook_runner.py`, `stage_minimo="experiment"` (R17).
- Test de filtrado por stage (R17) y test de que el frontmatter del writer no cambió (R18).
- Actualizar `ARCHITECTURE.md` (inventario §2 y regla de dependencia §3) para listar `tools/leadrun`
  como familia independiente que compone `nbrunner`/`autonomy`/`datasources`, siguiendo el patrón ya
  usado para `tools/datasources` en Change 1.
- Entregable: `tools/tests/test_v08_leadrun_neutrality.py`, cambios en `tools/ds_init/manifest.py`,
  `ARCHITECTURE.md`.

## T8 — Revisión (data-science-reviewer, read-only)

- Revisar T1-T7 contra `spec.md` completo (R1-R18) y contra los riesgos de `design.md` (§4).
- Verificar en particular: R8 (casos de encadenamiento malicioso), R11 (paridad exacta con
  `hook_validar_comando.py`), R13 (único productor de evidencia), R18 (frontmatter del writer sin
  cambios).
- Hallazgos abiertos vuelven a T1-T7 según corresponda (remediation acotada existente, no un
  contador nuevo).

## T9 — Cierre (Lead)

- Gate final: correr la suite completa (`.venv/Scripts/python -m pytest tools -q`, o el equivalente
  del proyecto) — única invocación de la suite completa en todo este Change; todas las tareas
  anteriores corren solo sus tests de módulo/paquete nuevos.
- Verificar contra `spec.md` que los 18 requisitos tienen evidencia de aceptación citada por
  archivo:línea de la corrida real (no de memoria, `CLAUDE.md` §2 "Verificación").
- Actualizar `docs/roadmap/v0.8.md` (checklist de estado) marcando Change 2 como cerrado, solo tras
  aprobación humana de este `proposal.md` (`## Aprobación` pasa de "Pendiente" a completada).
- `verification.md` de cierre (formato ya usado por Change 0/Change 1) con evidencia de cada
  criterio de cierre de `docs/roadmap/v0.8.md:628-634`.
