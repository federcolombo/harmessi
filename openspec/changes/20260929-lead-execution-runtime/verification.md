# Verificación — 20260929-lead-execution-runtime

## Resumen ejecutivo

Change 2 de v0.8 (SDD aprobado por el autor, 2026-09-29) implementa el runtime de ejecución
gobernada del Lead (`tools/leadrun/`): tipos y catálogo único de códigos `EXEC-*` (`core.py`),
reconocimiento puro de la forma de un comando (`allowlist.py`), ejecución de script/pytest
(`scripts.py`), composición de `tools.nbrunner.*` para notebooks (`notebooks.py`), el orquestador
único que produce y persiste `ExecutionRecord` (`runtime.py`), el script de nivel superior
`tools/notebook_runner.py` que cierra el gap de audit documentado en `proposal.md` (referenciado
por `tools/nbrunner/hook_validar_comando.py` pero inexistente en el repo antes de este Change), y
los subcomandos `ds_guard.py exec script|pytest|notebook` que componen la aprobación de
`execute_project_code` × modo sin que `tools/leadrun/` importe `autonomy`/`pathguard` directamente.

Una revisión de `data-science-reviewer` (T8, solo lectura) encontró 1 hallazgo BLOQUEANTE (R16:
reimplementación en vez de reutilizar `dsguard.core.escribir_texto_atomico`) y 1 gap de diseño no
documentado (timeout producía `CheckResult` `WARN` en vez de `FAIL`, dejando el exit code del
proceso en `0` para una ejecución que en realidad no completó) — ambos corregidos y re-verificados
por el Lead en la misma sesión de cierre. La regresión completa final corre en verde: **2939
passed, 10 skipped, 0 failed**, corrida en 6 lotes secuenciales acotados en memoria (ver
"Ejecución real").

**Change 2 cumple R1-R18 con las aclaraciones y correcciones documentadas** (ver "Resultado final").

## Commits del Change (orden, rama `v0.8-dev`)

| Commit | Qué aportó |
|---|---|
| `66bdfc1` | T1-T3 — `tools/leadrun/core.py` (tipos, catálogo `EXEC-*`), `allowlist.py` (`evaluar_comando`, 4 formas), `tools/notebook_runner.py` + `tools/leadrun/notebooks.py` (cierra el gap de audit). 74/74 tests de esta invocación. |
| `5de76d7` | T4 — `tools/leadrun/scripts.py` (`ejecutar_script`/`ejecutar_pytest` sobre `subprocess.run`). 6/6 tests, incluido un timeout real de ~1s. |
| `77d515e` | T5 — `tools/leadrun/runtime.py`, único punto que persiste `ExecutionRecord`. 85/85 tests. |
| `1d9e319` | T6 — CLI `ds_guard.py exec script\|pytest\|notebook`, `_resolver_aprobacion_exec`. Bug real encontrado y corregido en la misma invocación: `tools/leadrun/notebooks.py` usaba imports calificados `tools.nbrunner`/`tools.launcher_common` que fallan cuando `ds_guard.py` corre como script (solo `tools/`, no la raíz del repo, queda en `sys.path`) — corregido a imports bare, consistente con el propio `sys.path.insert` del módulo. 98/98 tests (`tools/leadrun` + `test_notebook_runner.py` + `test_ds_guard_exec.py`, nuevo). |
| `80722c9` | T7 — `tools/tests/test_v08_leadrun_neutrality.py`, entradas de manifiesto + test de stage, `ARCHITECTURE.md` (regla 12), `tools/tests/test_v08_leadrun_writer_frontmatter.py` (R18). Bug real encontrado y corregido en el propio fixture de sanity del test nuevo (caso copiado de la plantilla de `datasources` verificaba `import re` contra el set de imports equivocado). 21/21 tests nuevos. |
| `b0660dc` | T8 — correcciones de la revisión de `data-science-reviewer`: R16 (reutiliza `dsguard.core.escribir_texto_atomico` en vez de reimplementar tmp+`os.replace`) y timeout (`CheckResult` `FAIL` en vez de `WARN`, para que el exit code del proceso refleje que la ejecución no completó). 119/119 tests del alcance de `leadrun`. |

## Resultado por requisito (R1-R18)

### §1 Paquete y dependencias (R1-R3)

Paquete `tools/leadrun/` con la separación de módulos exacta de R1: `core.py` solo-stdlib
(`hashlib`, `json`, `re`, `dataclasses`, `typing`, `__future__`), sin imports relativos ni de
`os`/`pathlib`/`sys`/`subprocess`/`importlib`; `allowlist.py` puro sobre `str`/`tuple` (`os.path`
solo para manipulación de strings en memoria, nunca I/O real); `scripts.py` con I/O
(`subprocess`/`time`/`pathlib`); `notebooks.py` compone `tools.nbrunner.{core,fsdiff,manifest}` +
`tools.launcher_common` a nivel de módulo (import bare, no calificado — ver nota de T6 en la tabla
de commits), con `tools.nbrunner.execute` importado de forma perezosa solo dentro de
`ejecutar_manifest` (eager-import de `nbformat`/`nbclient`, mismo patrón que `ds_profile` en
`tools/datasources/file_observer.py`, Change 1); `runtime.py` con I/O e `importlib` implícito vía
`dsguard.checks`/`datasources.scan`, sin importar `tools.autonomy` ni `tools.dsguard.pathguard`
directamente. Verificado por `tools/tests/test_v08_leadrun_neutrality.py` (T7, commit `80722c9`),
patrón `ast` idéntico a `test_v08_datasources_neutrality.py` de Change 1. Dirección de dependencias
(R2) — ningún paquete de `dsguard`, `ds_profile`, `dsimpact`, `reporting`, `providers`, `routing`,
`fallback`, `harmessi_bench`, `autonomy`, `modelquality`, `qualityevidence`, `datasources`,
`datacontracts`, `nbrunner` importa `tools.leadrun`/`leadrun`, **sin ninguna excepción documentada**
(a diferencia de la regla 11/M1 de Change 1) — ni siquiera `ds_guard.py` a nivel de módulo (la
composición es vía `_importar_perezoso`/`_leadrun_modulos()`, imports perezosos dentro de
funciones). Sin dependencias nuevas de terceros (R3). **Cumplido.**

### §2 Tipos y serialización (R4-R7)

`ExecutionForm` cerrado a 4 valores (`script`/`pytest`/`notebook`/`cli_diagnostic`, R4);
`ExecutionRequest` frozen con validación de metacaracteres de encadenamiento (`&`, `;`, `|`,
backtick, `$`, `(`, `)`, `<`, `>`, salto de línea) y campos obligatorios (R5); catálogo único de 8
códigos `EXEC-*` en `core.CODES` (R6), verificado por T7 con un escaneo `ast` de literales
`EXEC-[A-Z-]+` sobre todo `tools/leadrun/*.py` (incluidos tests) y `tools/notebook_runner.py`, cero
códigos huérfanos fuera del catálogo. `ExecutionRecord` frozen con serialización determinista
(orden de claves fijo, `to_dict()`/`from_dict()` inversas exactas, R7); `approval: Optional[dict]`
recibido ya serializado (dict o `None`) desde el llamador, sin que `core.py` importe `autonomy` —
excepción de tipo de dato, no de import, análoga a la ya documentada para M1 en Change 1. Cubierto
por los tests de `core.py` del commit `66bdfc1` (33 tests) y reforzado por T7. **Cumplido.**

### §3 Allowlist (R8-R9)

`evaluar_comando(argv_o_texto, alcance, interprete_autorizado) -> (permitido, forma, motivo)`
reconoce las 4 formas declarativas (script/pytest/notebook/cli_diagnostic) sin decidir autorización
semántica (R9, no consulta `control.json`/`autonomy`, verificado por un test que corre sin ningún
`control.json` presente en el filesystem). Reutiliza literalmente `PATRON_COMANDO` de
`tools/nbrunner/hook_validar_comando.py:66-69` para la forma notebook, sin modificar ese archivo.
Los 8 casos `Given/When/Then` de R8 (encadenamiento, traversal, intérprete ajeno, fuera de alcance,
las 4 formas positivas) están cubiertos por tests parametrizados del commit `66bdfc1` (58 tests) — el
chequeo de metacaracteres corre en `core.contiene_metacaracter_prohibido` ANTES de evaluar
cualquier forma específica (composición reutilizada por `allowlist.py`, no reimplementada), por lo
que la cobertura es funcionalmente completa por composición aunque no haya un caso explícito por
cada metacarácter en cada una de las 4 formas por separado — nota de cobertura de test no
bloqueante, documentada por el reviewer de T8. **Cumplido.**

### §4 Ejecución de script/pytest (R10)

`ejecutar_script(request) -> ExecutionRecord` vía `subprocess.run(argv, cwd=repo_root,
timeout=..., capture_output=True, text=True)`, sin volver a evaluar la forma (ya evaluada por
`allowlist.py`). Timeout capturado (`subprocess.TimeoutExpired`), `exit_code` sentinel `124`
(convención POSIX), `timed_out=True`; proceso huérfano en Windows con hijos anidados documentado
como límite honesto no resuelto (mismo límite ya declarado por `tools/nbrunner/execute.py` para
notebooks). `ejecutar_pytest` reutiliza `ejecutar_script` sin duplicar la llamada a `subprocess`.
Cubierto por 6 tests del commit `5de76d7`, incluido un timeout real (~1s) contra un script de
fixture con bucle infinito. **Cumplido.**

### §5 `tools/notebook_runner.py` (R11)

Script de nivel superior que cierra el gap de audit documentado en `proposal.md` (T0): compone
`tools.leadrun.notebooks` (que a su vez compone `tools.nbrunner.{core,execute,fsdiff,manifest}`)
sin ninguna lógica nueva de validación. Secuencia exacta de R11 (cargar manifest → validar
interprete/hash/aprobación/rutas prohibidas → dry-run informa sin ejecutar → execute hace
snapshot/ejecuta/snapshot/diff/clasifica/cuarentena) implementada en `notebooks.ejecutar_manifest`
(commit `66bdfc1`). Los 4 casos `Given/When/Then` de R11 (hash desincronizado, ejecución exitosa +
clasificación + cuarentena, aprobación ausente, dry-run nunca ejecuta) cubiertos por
`tools/leadrun/tests/test_notebooks.py`. Paridad con `PATRON_COMANDO` de
`hook_validar_comando.py:66-69` verificada end-to-end por `tools/tests/test_notebook_runner.py` y
por los tests de `ds_guard exec notebook` de `test_ds_guard_exec.py` — `hook_validar_comando.py` no
fue tocado por este Change. **Cumplido.**

### §6 Composición de aprobación (R12)

`_resolver_aprobacion_exec` en `tools/ds_guard.py` (no en `tools/leadrun/`, dirección de
dependencias R1/R2) compone `pathguard.cargar_config` + `autonomy.policy.parse_autonomy_policy` +
`autonomy.core.resolve_action("execute_project_code", modo)` + `nbrunner.manifest.validar_aprobacion`
(modo `"execute"`) para el caso `supervised`. En `autonomous`, `executor="lead"`, `approval=None`
(el Lead ejecuta sin pedir aprobación por corrida). En `supervised` sin aprobación vigente, no se
ejecuta el comando y no se genera un `ExecutionRecord` de éxito — código `EXEC-APPROVAL-MISSING`/
`EXEC-APPROVAL-STALE` según `estado_real`. Cubierto por `tools/tests/test_ds_guard_exec.py` (4
clases de test, subprocess real contra repo git temporal, mismo patrón que
`test_ds_guard_source_cli.py` de Change 1). **Cumplido.**

### §7 Gate de evidencia (R13)

`runtime.py` es el único punto de `tools/leadrun/` que persiste un `ExecutionRecord` —
confirmado por inspección directa de código (no solo por comentario, per instrucción explícita de
T8): `scripts.py` y `notebooks.py` devuelven dicts crudos, sin importar `json` ni
`leadrun_core.ExecutionRecord`, sin ninguna referencia a `.harmessi/executions/`. Cualquier
ejecución fuera de este runtime (Bash directo del Lead) no genera evidencia — límite de
proceso/SDD documentado explícitamente (sin sandbox ni hook preventivo en este Change, mismo
límite honesto que `docs/roadmap/v0.8.md` fija para M5; el hook preventivo global queda para
v0.10). `tools/leadrun/tests/test_runtime.py::TestUnicoProductor` cubre el caso de
`scripts.ejecutar_script` llamado directamente sin persistencia; no hay un test equivalente
explícito para `notebooks.ejecutar_manifest` — nota de cobertura de test no bloqueante (T8), código
de producción confirmado correcto por inspección. **Cumplido.**

### §8 CLI (R14)

Subcomandos `ds_guard.py exec script|pytest|notebook`, mismo patrón que `contract`/`source` de
Change 1 (imports perezosos, `--json`, exit codes 0/1/2/3). `--change-id` resuelve `scope` desde
`control["alcance"]["rutas_autorizadas"]` (mismo mecanismo ya usado por `ALCANCE-RUTA`). Los 3 casos
`Given/When/Then` de R14 (autonomous sin aprobación ejecuta; supervised sin aprobación rechaza —
tanto con guardrails explícito `supervised` como sin `guardrails.json` en absoluto, default
`supervised`; supervised con aprobación vigente ejecuta con `executed_by="human"`) cubiertos por
`tools/tests/test_ds_guard_exec.py` (commit `1d9e319`). El caso de timeout (no cubierto por un
`Given/When/Then` explícito de R14) fue corregido en T8: antes, un timeout producía exit code de
proceso `0` (indistinguible de éxito para cualquier caller); ahora produce `FAIL` → exit code `1`,
consistente con que `exit_code=124` es un valor no-cero. **Cumplido**, con la corrección de timeout
aplicada y re-verificada en la regresión final.

### §9 Neutralidad (R15-R16)

Test de neutralidad `ast` único (R15): `tools/tests/test_v08_leadrun_neutrality.py` (T7, commit
`80722c9`) cubre R1-R3, R2 y R6 en un único módulo, con caso negativo sintético para probar que el
propio detector funciona — un bug real en el propio fixture de sanity (caso copiado de la plantilla
de `datasources` verificaba `import re` contra el set de imports equivocado) fue encontrado y
corregido antes de commitear. Persistencia atómica (R16): `_persistir_registro` reutiliza
`dsguard.core.escribir_texto_atomico` para el paso de escritura final (corregido en T8, commit
`b0660dc` — antes reimplementaba a mano el patrón tmp+`os.replace`, violando el texto explícito de
R16 "reutilizado por import, no reimplementado"; la detección de colisión de hash, que sí es propia
de este módulo, no cambió). **Cumplido**, con la corrección de R16 aplicada y re-verificada.

### §10 Instalabilidad (R17-R18)

7 `EntradaManifiesto` nuevas en `tools/ds_init/manifest.py` (VERBATIM, `stage_minimo="experiment"`,
R17) para `tools/leadrun/{__init__,core,allowlist,scripts,notebooks,runtime}.py` y
`tools/notebook_runner.py`, coherente con las entradas ya existentes de `tools/nbrunner/*`. Test de
filtrado por stage (`tools/ds_init/tests/test_manifest_v08_leadrun_stage.py`, T7): `discovery` no
incluye ninguna de las 7 entradas nuevas, `experiment` sí. `EXCLUSIONES_PERMANENTES` extendida con
los tests de desarrollo nuevos (no se instalan en un proyecto usuario). Frontmatter del writer sin
cambios (R18): `.claude/agents/python-data-engineer.md` conserva exactamente `tools: Read, Edit,
Write, NotebookEdit, Grep, Glob` — verificado por `tools/tests/test_v08_leadrun_writer_frontmatter.py`
(snapshot exacto del bloque frontmatter, complementario del test general de Change 0,
`test_v08_writer_no_execution.py`, sin duplicarlo). **Cumplido.**

## Ejecución real (corrida por el Lead, 2026-09-30)

La regresión completa se corrió en **6 lotes secuenciales** (no en una única invocación monolítica)
para mantener acotado el uso de memoria del sistema tras dos corridas previas abortadas por presión
de memoria del harness (ver "Desvíos y aclaraciones"):

| Lote | Alcance | Resultado |
|---|---|---|
| 1/6 | `tools/autonomy tools/datacontracts tools/datasources tools/leadrun` | 541 passed, 411 subtests passed (7.73s) |
| 2/6 | `tools/ds_init tools/ds_profile tools/dsimpact` | 312 passed, 5 skipped, 4 subtests passed (647.20s) |
| 3/6 | `tools/fallback tools/harmessi tools/harmessi_bench tools/modelquality tools/providers tools/qualityevidence tools/routing` | 416 passed, 8 subtests passed (614.74s) |
| 4/6 | `tools/reporting` | 842 passed, 3 skipped, 637 subtests passed (162.37s) |
| 5/6 | `tools/tests` (primeras 21 de 42) | 501 passed, 2 skipped, 38 subtests passed (620.51s) |
| 6/6 | `tools/tests` (últimas 21 de 42) | 327 passed, 9 subtests passed (284.45s) |

**Total: 2939 passed, 10 skipped, 0 failed, 1107 subtests passed** — cero fallas en el conjunto
completo del repositorio (crece sobre el baseline de `2820 passed, 10 skipped` que dejó Change 1,
consistente con las ~119 pruebas nuevas de `tools/leadrun` y afines). No se corrió
`check_manifest_parity` por separado en esta invocación de cierre — las 7 rutas VERBATIM nuevas ya
están cubiertas por el test de stage de T7 (existencia real de archivo, no solo declaración en
`MANIFEST`).

## Proceso de revisión (1 ronda) y disposición de hallazgos

Una invocación de `data-science-reviewer` (T8, solo lectura), cubrió por inspección de código: los 6
módulos de `tools/leadrun/`, `tools/notebook_runner.py`, el bloque `exec` de `tools/ds_guard.py`,
`tools/dsguard/checks.py`/`core.py`, y los tests nuevos. No corrió la suite (sin herramienta de
ejecución en su rol) — toda su verificación fue por inspección directa de código de test contra
código de producción, con una lista explícita de "no verificado en esta pasada" (contenido completo
de las nuevas `EntradaManifiesto`, `ARCHITECTURE.md`, y la ejecución real de la suite) que el Lead
cerró de forma independiente en esta misma sesión (ver "§9" y "§10" arriba, y "Ejecución real").

**1 hallazgo BLOQUEANTE, corregido y re-verificado** (commit `b0660dc`):

1. **R16**: `_persistir_registro` reimplementaba a mano `tmp_path.write_bytes(...)` +
   `os.replace(...)` en vez de reutilizar `dsguard.core.escribir_texto_atomico` (que ya hace
   exactamente lo mismo y acepta `str` directamente) — violación textual explícita de R16
   ("reutilizado por import, no reimplementado"). Funcionalmente el código reimplementado era
   correcto (mismo mecanismo tmp+`os.replace`, ya cubierto por los tests de idempotencia/colisión
   existentes), así que no era un riesgo de integridad de datos, pero sí una violación directa del
   requisito. Corregido; `import os` quedó sin uso en el archivo y fue eliminado.

**1 gap de diseño no documentado, corregido y re-verificado** (commit `b0660dc`, no bloqueante per
el texto literal de `spec.md`, pero real):

2. Un timeout producía `CheckResult` `status=WARN`; `checks.exit_code()` solo bloquea con `FAIL`,
   así que `ds_guard.py exec script ...` sobre un comando que excede `timeout_seconds` terminaba con
   exit code de **proceso** `0` (éxito), aunque `ExecutionRecord.timed_out=True` quedara
   correctamente persistido como evidencia. Corregido a `FAIL` — consistente con que
   `exit_code=124` (sentinel de timeout) ya habría caído en la rama `FAIL` de no ser por el chequeo
   de `timed_out` interceptándolo antes.

**2 notas de cobertura de test, sin acción de código requerida** (documentadas arriba en §3 y §7):
R8 sin un caso explícito por metacarácter en cada una de las 4 formas de `allowlist.py` (cobertura
funcional completa por composición); R13 sin un test que llame `notebooks.ejecutar_manifest`
directamente para confirmar que no persiste evidencia (confirmado por inspección de código de
producción, no de test).

## Desvíos y aclaraciones de implementación

`proposal.md`, `spec.md` y `design.md` quedan sin modificar por estar aprobados por hash; se
registran acá como enmiendas de implementación. Ninguna relaja un criterio de cierre de `spec.md` ni
del roadmap.

- **(a) Estilo de import bare en `notebooks.py` (corregido en T6, commit `1d9e319`):** el diseño
  original usaba imports calificados `from tools.nbrunner import ...`/`from tools import
  launcher_common`, que requieren la raíz del repo en `sys.path`. Cuando `ds_guard.py` corre como
  script (`python tools/ds_guard.py ...`), Python solo agrega `tools/` (su propio directorio) a
  `sys.path[0]`, no la raíz del repo — reproducido con un subprocess real contra un repo git
  temporal, confirmado con `ModuleNotFoundError("No module named 'tools'")`. Corregido a imports
  bare (`from nbrunner import ...`, `import launcher_common`), consistente con el propio
  `sys.path.insert(0, _TOOLS_DIR)` del módulo y con el patrón ya establecido en
  `tools/datasources/runtime.py` (Change 1). `tools/notebook_runner.py` sí usa el import calificado
  `from tools.leadrun import notebooks` — correcto en su caso, porque ese script agrega
  explícitamente tanto `tools/` como la raíz del repo a `sys.path` antes de ese import (verificado
  end-to-end por los tests reales del subcomando `exec notebook`).
- **(b) `nbformat`/`nbclient` no instalados ni declarados en el repo (T3, commit `66bdfc1`):**
  `tools/nbrunner/execute.py` los importa a nivel de módulo; `notebooks.py` los importa de forma
  perezosa (solo dentro de `ejecutar_manifest`, en la rama `--execute`) para que validar un
  manifest en `--dry-run` no requiera tenerlas instaladas — mismo patrón que `ds_profile` en
  `tools/datasources/file_observer.py` de Change 1.
- **(c) Sin excepción documentada de dirección inversa (a diferencia de Change 1/M1):** ningún
  paquete importa `tools.leadrun`, ni siquiera `ds_guard.py` a nivel de módulo (composición vía
  imports perezosos dentro de funciones). Asimetría real, no un olvido — documentada explícitamente
  en la regla 12 de `ARCHITECTURE.md` §3.
- **(d) Proceso huérfano en Windows con hijos anidados (R10, ya declarado en `design.md`):** mismo
  límite honesto que `tools/nbrunner/execute.py` ya declara para notebooks; no se resuelve en este
  Change, sin solución nueva.
- **(e) Sin sandbox ni hook preventivo (R13, M5 del roadmap):** el runtime gobernado es el único
  mecanismo de evidencia; no intercepta Bash directo del Lead fuera de `ds_guard exec ...`. El hook
  estricto global queda para v0.10 (mismo límite ya declarado en `docs/roadmap/v0.8.md`).

Adicionalmente:

- **Ejecución de la regresión final en 6 lotes secuenciales, no en una única invocación:** dos
  corridas previas de la suite completa (una durante T7, otra al iniciar T9) fueron interrumpidas
  por el harness por presión de memoria del sistema mientras la sesión estaba inactiva esperando el
  resultado — no una falla de los tests en sí. Se cambió a lotes más chicos, en primer plano, para
  que cada proceso de `pytest` libere su memoria por completo antes de que empiece el siguiente
  (evita mantener un único proceso grande, más los subprocesos reales que lanzan varios tests de CLI
  como `test_ds_guard_exec.py`/`test_ds_guard_source_cli.py`, vivo durante toda la duración de la
  suite). Las 6 corridas completaron sin ser interrumpidas, cero fallas.

## Límites y pendientes

**Change 3 (o posterior)**
- Hook preventivo global sobre el Bash del Lead (v0.10, M5 del roadmap) — reutilizará
  `allowlist.evaluar_comando` sin cambios (diseñado para eso desde R9).
- Timeout real de proceso huérfano en Windows con hijos anidados: sigue sin una solución técnica
  nueva, documentado como límite honesto heredado de `tools/nbrunner/execute.py`.
- Test explícito de "único productor" (R13) que llame `notebooks.ejecutar_manifest` directamente
  (hoy confirmado solo por inspección de código de producción, no por un test dedicado).
- Casos explícitos por metacarácter en cada una de las 4 formas de `allowlist.py` (hoy cubierto por
  composición vía `core.contiene_metacaracter_prohibido`, no por un test directo por forma).

**Fuera de alcance explícito de Change 2** (según `proposal.md`): sandbox técnico de ejecución,
enforcement preventivo vía hook global (v0.10), paralelismo/colas de ejecución, límites de
recursos (CPU/memoria) por ejecución, integración con `harmessi doctor`.

**Sin sandbox:** mismo límite ya documentado por Change 1 y por el roadmap v0.8 — el runtime
gobierna el acceso que media (allowlist, aprobación, evidencia), pero no intercepta código del
proyecto que se ejecuta fuera de `ds_guard exec ...`.

## Resultado final

**Change 2 cumple R1-R18 con las aclaraciones y correcciones documentadas.**
