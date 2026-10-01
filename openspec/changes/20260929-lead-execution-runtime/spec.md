# Especificación — 20260929-lead-execution-runtime

Notación: cada requisito `Rn` tiene un criterio de aceptación verificable (test o inspección
nombrada), estilo `Given/When/Then` cuando aplica. "Falla" = devuelve un resultado con `status`
`FAIL`/`technical_error` (`tools/dsguard/checks.py:14-30`, `CheckResult`) donde corresponda, o un
`ExecutionRecord` con `exit_code != 0` — ningún componente público de `tools/leadrun/core.py` o
`allowlist.py` lanza hacia el llamador salvo `TypeError`/`ValueError` de validación de tipos.

## 1. Paquete y dependencias

**R1 — Paquete `tools/leadrun/`.** Módulos: `core.py`, `allowlist.py`, `scripts.py`, `notebooks.py`,
`runtime.py`, `__init__.py`.
- `core.py`: solo stdlib (`dataclasses`, `typing`, `re`, `json`, `hashlib`, `__future__`); sin `os`,
  `pathlib`, `sys`, `subprocess`, `importlib`, sin imports de hermanos ni de `tools.*`.
- `allowlist.py`: puro sobre `str`/`tuple` (sin I/O de filesystem real: la resolución canónica de
  rutas usa `pathlib.PurePosixPath`/`os.path.normpath` en memoria, sin tocar el disco); puede
  importar `core` (relativo).
- `scripts.py`: I/O (`subprocess`, `pathlib`, `time`); importa `core` y `allowlist`.
- `notebooks.py`: I/O; importa `core`, `allowlist`, y **compone** `tools.nbrunner.core`,
  `tools.nbrunner.execute`, `tools.nbrunner.fsdiff`, `tools.nbrunner.manifest` (import directo, sin
  duplicar ninguna función). Dirección única: `tools.nbrunner.*` nunca importa `tools.leadrun.*`.
- `runtime.py`: I/O; importa `core`, `allowlist`, `scripts`, `notebooks`, y además
  `dsguard.checks` (patrón ya usado por `datasources/runtime.py`,
  `openspec/changes/20260928-source-neutral-data-access/spec.md:15-16`) y
  `tools.datasources.scan` (`scan_secrets`/`scan_locators`, excepción de dependencia análoga a M1,
  documentada en R9). `runtime.py` **no** importa `tools.autonomy` ni `tools.dsguard.pathguard`
  directamente: esa composición vive en `ds_guard.py` (R14, mismo patrón que Change 1).
- Aceptación: `tools/tests/test_v08_leadrun_neutrality.py` (patrón `ast` de
  `test_v08_datasources_neutrality.py`) afirma estos conjuntos de imports por módulo y falla si
  `core.py`/`allowlist.py` importan algo fuera de la lista permitida.

**R2 — Dirección de dependencias.** `tools/nbrunner/*` y sus tests (si existieran) no importan
`tools.leadrun`. Ningún paquete de `dsguard`, `ds_profile`, `dsimpact`, `reporting`, `providers`,
`routing`, `fallback`, `harmessi_bench`, `modelquality`, `qualityevidence`, `datasources`,
`datacontracts` importa `tools.leadrun`.
- Given: se recorren por `ast` todos los `.py` de esos paquetes y de `tools/nbrunner/`.
- When: se buscan imports de `tools.leadrun` o `leadrun`.
- Then: cero matches; el mismo test de R1 lo verifica.

**R3 — Sin dependencias nuevas.** `tools/leadrun/*` y `tools/notebook_runner.py` importan
únicamente stdlib y módulos ya presentes en el repo (`tools.nbrunner.*`, `dsguard.checks`,
`tools.datasources.scan`, `dsguard.core.hash_lf_v1`).
- Aceptación: mismo test `ast` de R1 lista explícitamente los módulos de terceros permitidos (ninguno).

## 2. Tipos y serialización (`core.py`)

**R4 — `ExecutionForm`.** Enum-like cerrado de strings: `"script"`, `"pytest"`, `"notebook"`,
`"cli_diagnostic"`. Cualquier otro valor es inválido.
- Aceptación: `validar_execution_form("script")` → válido; `validar_execution_form("shell")` →
  inválido con código `EXEC-FORM-INVALID` (catálogo único de códigos `EXEC-*`, R6).

**R5 — `ExecutionRequest`** (frozen): `command_form: str`, `interpreter: str`, `argv: tuple[str, ...]`,
`scope: tuple[str, ...]`, `timeout_seconds: int`.
- `command_form` ∈ los valores de R4.
- `argv` no vacío; ningún elemento contiene los metacaracteres de encadenamiento prohibidos
  (`&`, `;`, `|`, backtick, `` $ ``, `(`, `)`, `<`, `>`, salto de línea) — mismo criterio que
  `tools/nbrunner/hook_validar_comando.py` aplica implícitamente al anclar `PATRON_COMANDO` con
  `^...$` y una clase de caracteres cerrada para el manifest (líneas 58-69).
  - `scope` es una tupla de rutas/patrones (viene del llamador — D3 del encargo: `allowlist.py` no
    decide el origen del alcance).
  - `timeout_seconds` entero positivo.
- Aceptación: `ExecutionRequest.from_dict`/constructor rechaza con `EXEC-REQUEST-INVALID` cualquier
  campo faltante, `argv` vacío, o un elemento de `argv` con un metacarácter prohibido; tests
  parametrizados válido/inválido por campo.

**R6 — Catálogo único de códigos `EXEC-*`.** `core.py` define una única fuente de códigos
(`EXEC-FORM-INVALID`, `EXEC-REQUEST-INVALID`, `EXEC-COMMAND-REJECTED`, `EXEC-APPROVAL-MISSING`,
`EXEC-APPROVAL-STALE`, `EXEC-SCOPE-VIOLATION`, `EXEC-TIMEOUT`, `EXEC-RUNTIME-ERROR`). Ningún otro
módulo de `tools/leadrun/` ni `tools/notebook_runner.py` define un código `EXEC-*` fuera de esta
lista (evita la "segunda tabla de constantes" prohibida por `docs/roadmap/v0.8.md:925-927`).
- Aceptación: test que recorre `tools/leadrun/*.py` y `tools/notebook_runner.py` por `ast` buscando
  literales `r"EXEC-[A-Z-]+"` y falla si alguno no está en el catálogo de `core.py`.

**R7 — `ExecutionRecord`** (frozen, serialización determinista — orden de claves fijo, igual
criterio que `SourceObservation`,
`openspec/changes/20260928-source-neutral-data-access/spec.md:58-59`): `execution_id`,
`command_form`, `argv` (tupla ya redactada, ver R9), `code_hash` (`Optional[str]`: hash
`sha256/lf/v1` vía `dsguard.core.hash_lf_v1` del script/notebook; `None` para `cli_diagnostic`),
`exit_code: int`, `duration_seconds: float`, `stdout_summary: str`, `stderr_summary: str`
(truncados a un límite fijo documentado en el propio módulo; redactados si `scan_secrets`/
`scan_locators` encuentran algo), `outputs_hash: Optional[str]` (hash agregado de salidas
persistidas permitidas, `None` si no aplica), `executed_by: str` (`"lead"` o `"human"`),
`mode: str` (`"autonomous"` o `"supervised"`), `approval: Optional[dict]` (serialización de
`tools.autonomy.core.PolicyApproval.to_dict()` si la aprobación fue por política, o `None` si fue
aprobación humana directa o si el modo es `autonomous`), `generated_at: str` (ISO-8601 UTC, vía
`dsguard.core.ahora_utc`), `timed_out: bool`.
- `to_dict()`/`from_dict()` son inversas exactas (round-trip determinista, mismos bytes al volver a
  serializar).
- `tools/leadrun/core.py` **no** importa `tools.autonomy` (R1): `approval` se recibe ya serializado
  (un `dict` o `None`) desde el llamador (`runtime.py`, que tampoco importa `autonomy` — la
  serialización de `PolicyApproval` ocurre en `ds_guard.py`, R14), documentado como excepción de
  dependencia de **tipo de dato**, no de import, análoga a la ya documentada para M1
  (`openspec/changes/20260928-source-neutral-data-access/spec.md:22-26`).
- Aceptación: test de round-trip; test de que `code_hash is None` cuando `command_form ==
  "cli_diagnostic"`; test de que `approval is None` en todo registro con `mode == "autonomous"`.

## 3. Allowlist (`allowlist.py`)

**R8 — `evaluar_comando(argv_o_texto, alcance, interprete_autorizado) -> (permitido, forma, motivo)`.**
Función pura: reconoce la FORMA de un comando (no decide autorización semántica de `autonomy`,
solo si el comando matchea una de las 4 formas declarativas). Recibe `interprete_autorizado` ya
normalizado (mismo criterio de comparación por igualdad exacta post-normalización que
`tools/nbrunner/hook_validar_comando.py:46-51`, `normalizar_interprete`) — nunca infiere el
intérprete "por forma de ruta".

Formas reconocidas:
- (a) **script**: `"<intérprete>" <script.py> [args...]` — `script.py` resuelve, canónico (sin
  `..`, sin absoluta rechazada explícitamente antes de unir con la raíz — mismo gotcha que
  `tools/nbrunner/hook_validar_comando.py:76-79` documenta para el manifest), dentro de `alcance`.
- (b) **pytest**: `"<intérprete>" -m pytest <rutas...> [flags sin metacaracteres]` — cada ruta
  dentro de `alcance`; los flags se filtran con la misma clase de caracteres básica
  (`[A-Za-z0-9_./=-]`) que ya usa `PATRON_COMANDO` para el manifest
  (`tools/nbrunner/hook_validar_comando.py:66-68`).
- (c) **notebook**: `"<intérprete>" tools/notebook_runner.py run --manifest <ruta> [--dry-run|--execute]`
  — MISMO patrón que `PATRON_COMANDO` de `tools/nbrunner/hook_validar_comando.py:66-69` (regex
  reutilizada literalmente, importada o copiada carácter por carácter con cita a esa línea — no se
  reinventa) y la misma validación de contención bajo
  `openspec/changes/**/runs/*.json` (`_validar_manifest`,
  `tools/nbrunner/hook_validar_comando.py:72-110`, adaptada a `evaluar_comando`).
- (d) **cli_diagnostic**: `"<intérprete>" tools/ds_guard.py ...`, o
  `"<intérprete>" -m tools.ds_profile ...`, o `"<intérprete>" -m tools.harmessi ...` — siempre
  reconocida, sin dependencia de `alcance` (clase `diagnostic_read`, `tools/autonomy/core.py:182-183`).
- Cualquier otra forma: `permitido=False`, `forma=None`, motivo explícito de qué no matchea.
- Ninguna forma acepta metacaracteres de encadenamiento en ningún argumento (R5).
- Aceptación (`Given/When/Then`):
  - Given argv `["<venv>/python", "scripts/entrenar.py", "&&", "rm", "-rf", "/"]`, When se evalúa,
    Then `permitido=False` (metacarácter de encadenamiento en `argv`, no matchea ninguna forma).
  - Given texto `'"<venv>/python" tools/notebook_runner.py run --manifest openspec/changes/x/runs/r.json; rm -rf data'`,
    When se evalúa, Then `permitido=False` — el `;` rompe el anclaje `$` de la forma (c).
  - Given argv `["<venv>/python", "scripts/entrenar.py"]` con `scripts/entrenar.py` fuera de
    `alcance`, When se evalúa, Then `permitido=False`, motivo de alcance.
  - Given argv `["/usr/bin/python3", "scripts/entrenar.py"]` con `scripts/entrenar.py` dentro de
    `alcance` pero `interprete_autorizado` distinto, When se evalúa, Then `permitido=False`
    (intérprete no coincide).
  - Given argv `["<venv>/python", "tools/ds_guard.py", "status"]`, When se evalúa, Then
    `permitido=True`, `forma="cli_diagnostic"`, sin requerir `alcance`.
  - Given argv `["<venv>/python", "-m", "pytest", "tools/leadrun/tests", "-k", "test_algo"]` con la
    ruta dentro de `alcance`, When se evalúa, Then `permitido=True`, `forma="pytest"`.
  - Given argv de la forma (c) con `--manifest ../../secreto.json` (traversal), When se evalúa, Then
    `permitido=False` — mismo criterio de `_validar_manifest`.
  - Given argv de la forma (a) con un script cuyo nombre contiene un espacio seguido de `$(`, When se
    evalúa, Then `permitido=False`.

**R9 — `allowlist.py` no decide autorización semántica.** `evaluar_comando` nunca consulta
`tools.autonomy` ni `control.json`: si la forma es reconocida y dentro de alcance, devuelve
`permitido=True` aunque la política de `autonomy` termine exigiendo aprobación humana antes de
ejecutar (eso lo resuelve `runtime.py` + `ds_guard.py`, R14-R15). Reutilizable sin cambios por el
futuro hook estricto de `v0.10.md` (M5 de Change 0, `docs/roadmap/v0.8.md:415-416`).
- Aceptación: test que llama `evaluar_comando` sin ningún `control.json` presente en el filesystem
  (I/O simulado inexistente) y obtiene el mismo resultado que con uno presente — prueba de pureza.

## 4. Ejecución de script/pytest (`scripts.py`)

**R10 — `ejecutar_script(request: ExecutionRequest) -> ExecutionRecord`.** Recibe un
`ExecutionRequest` ya evaluado como `permitido=True` por `allowlist.py` (no vuelve a evaluar la
forma). Ejecuta vía `subprocess.run(argv, cwd=repo_root, timeout=request.timeout_seconds,
capture_output=True, text=True)`.
- Given un script que termina con `exit(0)` y stdout corto, When se ejecuta, Then `ExecutionRecord`
  con `exit_code=0`, `timed_out=False`, `stdout_summary` contiene el texto (truncado si excede el
  límite documentado).
- Given un script que excede `timeout_seconds`, When se ejecuta, Then se captura
  `subprocess.TimeoutExpired`, el proceso se termina (POSIX: garantizado por
  `subprocess.run(timeout=...)`; Windows con hijos anidados: puede quedar un proceso huérfano — MISMO
  límite honesto que ya declara `tools/nbrunner/execute.py` para notebooks, documentado también acá,
  no resuelto con una solución nueva), y el `ExecutionRecord` resultante tiene `timed_out=True`,
  `exit_code` sentinel documentado (p. ej. `124`, convención POSIX de timeout) y código
  `EXEC-TIMEOUT` en el motivo.
- Given un script cuyo `code_hash` (hash del archivo al momento de la invocación) no coincide con un
  `code_hash` esperado si el llamador lo provee (uso opcional, para paridad con notebooks), When se
  ejecuta, Then el mismo `ExecutionRecord` lo refleja en el campo `code_hash` (no bloquea por sí
  solo: el bloqueo de hash es exclusivo de notebooks, R11, porque solo ahí existe un manifest con
  `hash_aprobado`).
- `ejecutar_pytest` es la misma función parametrizada por `command_form="pytest"` (reutiliza
  `ejecutar_script`, no duplica la llamada a `subprocess`).
- Aceptación: tests con scripts de fixture sintéticos (`exit 0`, `exit 1`, bucle infinito con
  timeout corto) bajo `tools/leadrun/tests/`.

## 5. `tools/notebook_runner.py` (cierra el gap del audit)

**R11 — Script de nivel superior `tools/notebook_runner.py`, subcomando `run --manifest <ruta>
[--dry-run|--execute]`.** Resuelve el intérprete/repo con el mismo patrón que otros CLIs de nivel
superior del repo (`_repo_root()`, ya usado por `tools/ds_guard.py`), y compone
`tools.leadrun.notebooks` (que a su vez compone `tools.nbrunner.{core,execute,fsdiff,manifest}`,
R1) — **sin ninguna lógica nueva de validación de notebooks**: solo el ensamblado que hoy falta.
Secuencia:
1. `manifest.cargar_manifest(ruta)` (`tools/nbrunner/manifest.py:93-119`) — si falla,
   `ManifestInvalidoError` se reporta y exit code `!= 0`, sin ejecutar nada más.
2. `manifest.validar_interprete` (líneas 124-140), `validar_hash_notebook` (145-157),
   `validar_rutas_prohibidas` (257-293) — cualquier `Finding` bloqueante detiene antes de ejecutar.
3. `manifest.validar_aprobacion(control, artefacto, hash_manifest, modo)` (líneas 173-223) con
   `modo="dry_run"` si `--dry-run`, `modo="execute"` si `--execute` — en `execute` sin aprobación
   vigente, el script termina sin ejecutar (mismo contrato que `validar_aprobacion` ya define).
4. Si `--dry-run`: informa resultado de 1-3 sin ejecutar el notebook, exit 0 si no hubo
   `Finding` bloqueante.
5. Si `--execute`: snapshot antes (`fsdiff.snapshot`), `execute.ejecutar_notebook`, snapshot
   después, `fsdiff.diferencia`/`clasificar`, cuarentena de lo fuera de contrato
   (`tools/nbrunner/fsdiff.py` y `tools/nbrunner/core.py`, funciones ya citadas en el encargo:
   `snapshot`/`diferencia`/`clasificar`/`cuarentena`) — imprime resultado + exit code.
- Mantiene el comando EXACTO que ya exige `PATRON_COMANDO`
  (`tools/nbrunner/hook_validar_comando.py:66-69`) — este Change no toca esa regex ni ese archivo
  (fuera del alcance de escritura, `proposal.md`).
- Aceptación (paridad con lo que `hook_validar_comando.py` ya exige):
  - Given un manifest con hash desincronizado, When se corre `--dry-run`, Then el script reporta
    `NBRUNNER-HASH-DESINCRONIZADO` y no llama a `ejecutar_notebook`.
  - Given un manifest válido con aprobación vigente, When se corre `--execute`, Then se ejecuta el
    notebook, se genera fsdiff, se clasifica y cualquier salida fuera de contrato queda en
    cuarentena.
  - Given un manifest válido sin aprobación vigente, When se corre `--execute`, Then el script
    termina con `APROB-AUSENTE` y exit code `!= 0`, sin ejecutar el notebook.
  - Given el comando completo `"<intérprete>" tools/notebook_runner.py run --manifest
    openspec/changes/x/runs/r.json --dry-run`, When se valida contra `PATRON_COMANDO` de
    `hook_validar_comando.py` sin modificarlo, Then matchea (prueba de que el script nuevo es
    compatible con el hook ya existente, cerrando el gap).

## 6. Composición de aprobación (`ds_guard.py`, no en `tools/leadrun/`)

**R12 — Función privada de composición en `ds_guard.py` para `execute_project_code`.** Análoga a la
de Change 1 para `access_check` (`tools/ds_guard.py:1033`, `_importar_perezoso("dsguard",
"pathguard")`, y `:1060`, `_importar_perezoso("autonomy", "policy")`). Compone
`pathguard.cargar_config` + `autonomy.policy.parse_autonomy_policy` +
`autonomy.core.resolve_action("execute_project_code", modo)` (`tools/autonomy/core.py:184-185`, R3
de `tools/autonomy` — ya congelada, este Change no la reabre).
- Given modo `autonomous`, When se resuelve la composición, Then `executor="lead"`,
  `approval="none"` — el Lead ejecuta sin pedir aprobación por corrida (`ExecutionRecord.approval =
  None`).
- Given modo `supervised`, When se resuelve la composición, Then `executor="lead_or_human"`,
  `approval="human"` — antes de ejecutar, `runtime.py` exige que
  `tools.nbrunner.manifest.validar_aprobacion(control, artefacto, hash_comando_o_manifest,
  "execute")` devuelva `estado == "vigente"` (mismo mecanismo `vigente`/`ausente`/`desincronizada`
  ya citado en R11, reutilizado también para scripts/pytest con `artefacto` = identificador
  determinista del `ExecutionRequest`, p. ej. `sha256` de `argv` unido).
- Given `supervised` sin aprobación vigente, When se invoca `runtime.py`, Then no se ejecuta el
  comando, no se genera un `ExecutionRecord` de éxito; se devuelve un resultado con código
  `EXEC-APPROVAL-MISSING` o `EXEC-APPROVAL-STALE` (según `estado_real` de `validar_aprobacion`) y
  exit code `!= 0` en el CLI.

## 7. Gate de evidencia (límite documentado, no enforcement técnico)

**R13 — Solo `runtime.py` produce `ExecutionRecord` persistido.** No existe ningún otro punto en
`tools/leadrun/` que persista un `ExecutionRecord`. Cualquier ejecución fuera de este runtime (Bash
directo del Lead) no genera evidencia — esto lo hace cumplir el proceso/SDD de Change 3 (fuera de
alcance de este Change); acá solo se construye el mecanismo, sin sandbox ni hook preventivo.
- Aceptación: inspección de código — `grep` sobre `tools/leadrun/*.py` y `tools/notebook_runner.py`
  confirma que la única función que escribe un `ExecutionRecord` a disco (persistencia atómica, R16)
  está en `runtime.py`; test de que llamar `scripts.ejecutar_script` o `notebooks.*` directamente
  (bypaseando `runtime.py`) no escribe ningún archivo de registro.
- La documentación de este Change (proposal/design) declara explícitamente que **no** hay sandbox ni
  prevención técnica de ejecución directa fuera del runtime — mismo límite honesto que
  `docs/roadmap/v0.8.md:418-431` fija para M5.

## 8. CLI (`ds_guard.py exec ...`)

**R14 — Subcomandos `exec script|pytest|notebook`.** Mismo patrón que `contract`/`source` de
Change 1 (imports perezosos: `_importar_perezoso("leadrun", "runtime")`, etc.; `--json`; exit codes
0/1/2/3 — mismo esquema que `cmd_source_list`/`cmd_source_check`,
`tools/ds_guard.py:1083-1144`: `0` éxito, `2`/`3` según el tipo de fallo).
- `--change-id <id>` resuelve `scope` leyendo `control["alcance"]["rutas_autorizadas"]`
  (`tools/ds_guard.py:217-218`, mismo mecanismo que ya usa `ALCANCE-RUTA`, vía
  `dsguard.repo.files_out_of_scope`, `tools/dsguard/repo.py:124` — reutilizado, no reinventado).
- Construye un `ExecutionRequest`, evalúa con `allowlist.evaluar_comando`, si `permitido=False`
  imprime el motivo por stderr y exit code `2`; si `permitido=True`, compone la aprobación (R12) y
  delega en `runtime.py`.
- Aceptación: `ds_guard.py exec script --change-id <id> -- <intérprete> <script.py>` en `autonomous`
  sin aprobación previa ejecuta y produce un `ExecutionRecord` con `approval=None`; la misma
  invocación en `supervised` sin aprobación previa termina con exit `2` y ningún `ExecutionRecord`
  de éxito; con aprobación vigente registrada, `supervised` ejecuta y el `ExecutionRecord` resultante
  tiene `mode="supervised"` y `approval` no nulo si fue por política, o `executed_by="human"` si el
  humano fue quien corrió el comando aprobado.

## 9. Neutralidad

**R15 — Test de neutralidad `ast`.** `tools/tests/test_v08_leadrun_neutrality.py` (o ubicación
equivalente bajo `tools/tests/`) verifica R1-R3 y R2 (dirección de dependencias) en un único módulo
de test, siguiendo el patrón de `test_v08_datasources_neutrality.py`.
- Aceptación: correr la suite (`.venv` del proyecto) da 0 fallos; el test falla deliberadamente si
  se agrega un import prohibido (verificado con un caso negativo en la propia suite).

**R16 — Persistencia atómica.** `runtime.py` persiste `ExecutionRecord` con el mismo patrón de
escritura atómica que `dsguard.core.escribir_texto_atomico`/`escribir_control` (reutilizado por
import, no reimplementado).
- Aceptación: test de que una interrupción simulada a mitad de escritura no deja un archivo de
  registro parcialmente escrito (mismo test que ya cubre `escribir_texto_atomico`, aplicado al
  camino de `runtime.py`).

## 10. Instalabilidad

**R17 — Entradas nuevas en el manifiesto de instalación.** `tools/ds_init/manifest.py` gana
`EntradaManifiesto` para `tools/leadrun/__init__.py`, `core.py`, `allowlist.py`, `scripts.py`,
`notebooks.py`, `runtime.py`, y `tools/notebook_runner.py`, todas con `tratamiento=VERBATIM` y
`stage_minimo="experiment"` — coherente con las 5 entradas ya existentes de `tools/nbrunner/*`
(`tools/ds_init/manifest.py:132-184`, todas `stage_minimo="experiment"`), porque `tools/leadrun/`
depende de `tools.nbrunner` (R1) y no tiene sentido instalarlo en un stage anterior donde `nbrunner`
todavía no está presente.
- Aceptación: `harmessi doctor` sobre una instalación fresca en stage `experiment` reporta 0
  `ERROR` de drift para los archivos nuevos; una instalación en stage `discovery` (anterior a
  `experiment`) no instala `tools/leadrun/*` ni `tools/notebook_runner.py` (test de filtrado por
  stage, mismo patrón que `tools/ds_init/manifest.py:892-906`).

**R18 — El frontmatter del writer no cambia.** `agent_python_data_engineer.md.tmpl` (o su
equivalente instalado, `.claude/agents/python-data-engineer.md`) conserva exactamente su lista de
`tools` — el writer no gana ninguna capacidad de ejecución con este Change (decisión 1 del roadmap,
`docs/roadmap/v0.8.md:450-451`, ya verificada por un test de Change 0 y no reabierta acá).
- Aceptación: test de hash/diff del frontmatter del writer antes/después de este Change: sin
  cambios.
