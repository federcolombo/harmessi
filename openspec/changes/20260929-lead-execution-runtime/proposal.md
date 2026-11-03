# Propuesta — 20260929-lead-execution-runtime

## Problema

`docs/roadmap/v0.8.md` (Change 2, "lead-execution-runtime") exige que el Lead pueda ejecutar
scripts, tests y notebooks del proyecto con governance y evidencia, sin darle ejecución al writer
ni crear un shell irrestricto (decisión material M5, confirmada). Hoy no existe ningún runtime
gobernado para scripts/tests genéricos: solo hay un motor de ejecución de notebooks
(`tools/nbrunner/`, Change previo a v0.8) y un mecanismo de aprobación de política
(`tools/autonomy/`, Change 0, cerrado) que todavía no está compuesto con ninguna ejecución real.

## Objetivo

Dar de alta `tools/leadrun/`, un runtime gobernado que evalúa la forma de un comando contra una
allowlist declarativa, lo ejecuta (script/pytest directamente, notebook componiendo `nbrunner`),
compone la aprobación de `tools/autonomy/` según el modo (`autonomous`/`supervised`) y persiste un
`ExecutionRecord` — todo por el único camino que Change 0 (M5) reconoce como evidencia válida de
cierre de un Change autónomo.

## Evidencia

**Hallazgo del audit — script de notebooks referenciado pero inexistente.**
`tools/nbrunner/hook_validar_comando.py:66-69` fija la única forma de comando que el hook de
`PreToolUse` del agente `notebook-runner` permite:

```
r'^"(?P<interprete>[^"]+)" tools/notebook_runner\.py run --manifest '
r'(?P<manifest>[A-Za-z0-9_./-]+)(?: --dry-run| --execute)?$'
```

y `.claude/agents/notebook-runner.md` documenta ese mismo comando como la forma de invocación del
subagente. Se verificó que `tools/notebook_runner.py` **no existe** en el repositorio: un
`Glob("tools/notebook_runner.py")` desde la raíz no devuelve ningún archivo, y el único paquete
relacionado es `tools/nbrunner/` con los módulos `core.py`, `execute.py`, `fsdiff.py`,
`manifest.py`, `hook_validar_comando.py`, `hook_launcher.py` — ninguno de nivel superior. Es un gap
preexistente (no introducido por este Change), pero Change 2 lo cierra porque el roadmap asume
"notebooks vía runner ya existente" como una de las formas de comando permitidas
(`docs/roadmap/v0.8.md:433-436`, "runner de notebooks con manifest").

**Hallazgo del audit — sin suite de tests de `nbrunner` en el repo.**
Ni `tools/nbrunner/tests/` ni `tools/tests/test_nbrunner.py` existen (`Glob` sobre ambas rutas no
devuelve archivos; un intento de lectura directa de `tools/tests/test_nbrunner.py` falla con "Path
does not exist"). El motor de `nbrunner` (`core.py`, `manifest.py`, `execute.py`, `fsdiff.py`) no
tiene, hoy, ninguna suite de tests visible en el repositorio que lo ejercite por import directo ni
a través de un script. Esto es una segunda deuda preexistente, no introducida por este Change; se
documenta en `design.md` como riesgo y en `tasks.md` se agregan tests de `tools/notebook_runner.py`
(el script nuevo) y de `tools/leadrun/notebooks.py` (la composición), pero **no** se retro-arregla
`tools/nbrunner/` en sí — eso excede el alcance de "componer, no modificar" (D1 del encargo,
`ARCHITECTURE.md:131`).

**Tabla de política ya congelada (Change 0, cerrado).** `tools/autonomy/core.py:184-185` fija la
fila `execute_project_code`: en `autonomous`, `("lead", "none", "proceed", None)` — el Lead ejecuta
sin aprobación por corrida; en `supervised`, `("lead_or_human", "human", "proceed", None)` —
requiere aprobación humana. `tools/autonomy/core.py:202-203` fija `session_open_close` de forma
análoga (no se usa en este Change, pero confirma el patrón de la tabla). `resolve_action` (línea
244) es la consulta pura ya existente que este Change reutiliza, sin reabrirla (Change 0 está
cerrado; ver `openspec/changes/20260928-project-autonomy-contract/spec.md`).

**Mecanismo de aprobación humana ya existente para reutilizar.**
`tools/nbrunner/manifest.py:173-223` (`validar_aprobacion`) ya implementa la comparación
`vigente`/`ausente`/`desincronizada` contra `control.json["aprobaciones"]` por hash del manifest,
con semántica separada para `modo="dry_run"` (nunca bloquea) y `modo="execute"` (bloqueante). Este
Change lo reutiliza para `supervised` en vez de reimplementar una segunda comparación de
aprobaciones (evita la "segunda tabla de constantes/códigos" que `docs/roadmap/v0.8.md:925-933`
prohíbe como deuda).

**Patrón de composición de Change 1 (cerrado) a replicar.** Change 1
(`openspec/changes/20260928-source-neutral-data-access/`) resolvió su integración con `ds_guard.py`
componiendo una función privada de control de acceso inyectada, con imports perezosos
(`tools/ds_guard.py:1089`, `_importar_perezoso("datasources", "runtime")`) y subcomandos nuevos
(`source`/`contract`) que no tocan el paquete de origen. Este Change replica el mismo patrón para
`execute_project_code`: la composición de aprobación vive en `ds_guard.py`, no en `tools/leadrun/`.

**Patrón de alcance ya existente para reutilizar.** `tools/ds_guard.py:217-218` ya lee
`control.get("alcance", {}).get("rutas_autorizadas", [])` y lo pasa a
`repo.files_out_of_scope(repo_root, rutas_autorizadas)` (`tools/dsguard/repo.py:124`) para la
validación `ALCANCE-RUTA`; este Change reutiliza esa misma lectura de `control.json` para poblar el
`scope` de un `ExecutionRequest` (D8), sin crear un segundo mecanismo de alcance.

**Detector de secretos ya existente para reutilizar.** `tools/datasources/scan.py:107`
(`scan_secrets`) y `:150` (`scan_locators`) son el detector determinista y best-effort que Change 1
ya usa para el registro de fuentes; este Change lo reutiliza por import directo para redactar
`argv`/`stdout_summary`/`stderr_summary` de un `ExecutionRecord`, documentado como excepción de
dependencia análoga a la de M1 (Change 1 ya documentó una excepción similar para
`datacontracts.validation`).

**Invocación real de las 3 CLIs propias de Harmessi** (para la forma d de la allowlist, D2),
confirmada contra `README.md`: `tools/ds_guard.py` se invoca como script directo
(`"<intérprete>" tools/ds_guard.py ...`, patrón ya usado por `hook_validar_comando.py` para
notebooks); `tools/ds_profile` se invoca como módulo (`README.md:191`,
`python -m tools.ds_profile run --input INPUT --output OUTPUT [--markdown]`); `tools/harmessi` se
invoca como módulo (`README.md:177`, `python -m tools.harmessi doctor [--destino DESTINO]`, y
variantes `providers`/`routing`/`fallback` en las líneas 286/301/317). No hay una cuarta forma de
invocación real: `tools/harmessi_bench` se invoca aparte
(`python -m tools.harmessi_bench.cli`, README.md:332-337, "with no `__main__.py` of its own yet"),
pero no forma parte del encargo (D2 solo cita `ds_guard`, `ds_profile`, `harmessi`), así que queda
fuera de la allowlist de este Change salvo que el autor confirme lo contrario.

**`stage_minimo` real de las entradas de `nbrunner` en el manifiesto de instalación.**
`tools/ds_init/manifest.py:132-184` (las 5 `EntradaManifiesto` de `tools/nbrunner/*`) declaran
`stage_minimo="experiment"` de forma consistente. Las entradas nuevas de `tools/leadrun/*` y de
`tools/notebook_runner.py` (D7) usan el mismo `stage_minimo="experiment"` por coherencia con su
dependencia directa de `nbrunner` (ver `design.md`).

## Supuestos descartados

- Se descartó extender `tools/nbrunner/manifest.py` con un campo `kind` para cubrir scripts/tests
  (alternativa que el roadmap deja abierta a SDD, `docs/roadmap/v0.8.md:613-614`): el encargo del
  Lead (D1) ya cerró esta decisión a favor de un paquete hermano que compone, por el mismo criterio
  usado en Change 1 con `tools/datasources`. Se documenta como alternativa descartada en
  `design.md`, no se reabre acá.
- Se descartó dotar a `allowlist.py` de conocimiento del origen del `scope` (por ejemplo, leyendo
  `control.json` directamente): el `scope` se recibe como parámetro para que la función pura sea
  reutilizable por el futuro hook de v0.10 (M5 de Change 0) sin acoplarse a `dsguard`/`control.json`.

## Alcance

- Paquete nuevo `tools/leadrun/` (`core.py`, `allowlist.py`, `scripts.py`, `notebooks.py`,
  `runtime.py`).
- Script nuevo de nivel superior `tools/notebook_runner.py` (cierra el hallazgo del audit).
- Subcomandos nuevos `ds_guard.py exec script|pytest|notebook` con la composición de aprobación
  (`execute_project_code` × modo) inyectada, análoga a la de Change 1.
- Entradas nuevas en el manifiesto de instalación (`tools/ds_init/manifest.py`) para los archivos de
  arriba, con `stage_minimo` coherente.
- Test de neutralidad de dependencias (`ast`), tests de repo/manifiesto.

## Fuera de alcance

Idéntico a `docs/roadmap/v0.8.md:625-626`: shell irrestricto, sandbox/contenedores, instalación de
dependencias, red arbitraria, ejecución por parte del writer, scheduling/orquestación, ejecución
remota. Además (D13 del encargo): el hook preventivo de `Bash` (v0.10, M5 de Change 0); retro-
arreglar la ausencia de tests de `nbrunner` (segundo hallazgo del audit, documentado pero no
resuelto); cualquier cambio a `tools/nbrunner/*` existente o a sus tests (no hay, según el
hallazgo) — se compone, no se modifica.

## Holdout policy

No aplica: este Change no observa ni ejecuta contra datasets sellados. La composición de aprobación
(D6) respeta `pathguard`/`guardrails.json`/holdouts existentes vía `dsguard.pathguard.cargar_config`,
sin ampliarlos ni restringirlos.

## Impacto en production-readiness

No aplica en este bloque KDD.

## Criterios de aceptación (spec-lite)

Ver `spec.md` (R1-R18). Resumen: paquete/dependencias correctos y neutrales; tipos y serialización
deterministas; allowlist cerrada que reconoce exactamente las 4 formas de D2 y rechaza cualquier
comando encadenado o fuera de alcance; ejecución de script/pytest con timeout y captura resumida;
`tools/notebook_runner.py` nuevo con paridad exacta frente a lo que `hook_validar_comando.py` ya
exige; composición de aprobación correcta en `autonomous` (sin aprobación por corrida) y en
`supervised` (bloqueante sin aprobación vigente, reusando `validar_aprobacion`); el gate de
evidencia documentado como límite (no como enforcement técnico en este Change); CLI con imports
perezosos y exit codes 0/1/2/3; instalabilidad con `stage_minimo` coherente.

## Decisión técnica (design-lite)

Ver `design.md`: alternativas descartadas, riesgos (proceso huérfano en Windows, timeout no
robusto, sin sandbox, colisión de nombre de paquete si la hubiera, ausencia de tests de `nbrunner`).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-29
- Alcance aprobado: Change 2 - lead-execution-runtime (`docs/roadmap/v0.8.md`)
- Versión de artefactos referenciada: aprobación humana explícita registrada por hash
  (`sha256/lf/v1`) mediante `ds_guard approve` sobre `proposal.md`/`spec.md`/`design.md`, con
  entradas vivas en `control.json` -> `aprobaciones` (hashes `54e2efc1…`/`c189346f…`/`26743054…`,
  `registrado_utc: 2026-09-29T17:58:51Z`).
- Cita o descripción fiel de qué se aprobó: «si», en respuesta directa al paquete de revisión
  presentado ("SDD ALINEADO CON ROADMAP") para `proposal.md`/`spec.md`/`design.md` del Change 2.
  Incluye el hallazgo del audit (`tools/notebook_runner.py` inexistente) y su cierre dentro de
  este Change (cita literal ya registrada en `control.json`).

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
