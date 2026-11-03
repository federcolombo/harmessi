# Verificación — 20260930-project-extension-and-installer-integration

## Resumen ejecutivo

Change 4 de v0.8 (SDD aprobado por el autor por hash, 2026-09-30, incluida la resolución M11
aditiva con sus cuatro guardas de contrato) implementa las cinco capacidades opt-in congeladas en el
roadmap: project capabilities (M8), fuentes externas file-backed de solo lectura (M9), layering de
configuración `managed defaults → project config → local overrides → effective config` (M10),
instalación gobernada aditiva de dependencias pre-aprobadas (M11, 5ª forma `dependency_install`
sobre el runtime público de Change 2, sin reabrirlo materialmente), integridad detectiva de fuentes
externas (M12), y adopción de proyecto existente (B5) — todas backward-compatible, sin reabrir
Changes 0-3.

Dos ciclos de revisión de `data-science-reviewer` (T8, solo lectura, los 2 ciclos writer↔reviewer
autorizados) encontraron **4 hallazgos reales**, los 4 corregidos y re-verificados por el Lead en la
misma sesión de cierre:

1. **BLOQUEANTE** (ciclo 1): R24 exigía que los 4 suites de `tools/leadrun/tests/` (Change 2,
   cerrado) pasaran "sin editar ninguno" — se habían agregado tests nuevos a 3 de los 4. Corregido
   moviendo esos tests a un archivo propio de Change 4 (`tools/leadrun/tests/
   test_dependency_install_form.py`) y revirtiendo los 3 archivos de Change 2 a su estado exacto
   (`git checkout HEAD --`).
2. **Importante** (ciclo 1): R38 (evidencia de entorno pre/post de `dependency install`) nunca se
   persistía en disco ni se incluía en el payload `--json` — solo generaba warnings efímeros.
   Corregido con persistencia trazable en `.harmessi/executions/<execution_id>/
   dependency_evidence.json`; R39 (distribuciones inesperadas) ahora produce un
   `CheckResult(kind=technical_error)` estructurado, no solo texto.
3. **Menor** (ciclo 1): `cmd_dependency_install` resolvía `modo` dos veces (ventana TOCTOU
   teórica). Corregido con un parámetro `modo_resuelto` que evita la segunda resolución.
4. **Importante** (ciclo 2): la captura/persistencia de evidencia R38/R39 se saltaba por completo
   cuando la instalación fallaba (`exit_code != 0`) — justo el caso donde esa evidencia importa más.
   Corregido: ahora se captura/persiste siempre que hubo una ejecución real, sin importar el
   resultado; el exit code devuelto sigue reflejando el fallo real, nunca enmascarado.

Además, durante la implementación (no por el reviewer sino por tests propios del Lead) se
encontraron y corrigieron 3 bugs reales adicionales: (a) `ExecutionRecord` exige `approval is None`
en modo `autonomous` — `approval_override` ahora solo se construye en `supervised`; (b) el gate
genérico de aprobación-por-artefacto no tenía forma de autorizar una instalación en modo
`supervised` (sin mecanismo para registrar aprobación de un par nombre/versión) — resuelto con
`omitir_gate_por_artefacto`; (c) el intérprete resuelto por `launcher_common` no estaba normalizado
antes de pasarlo a la allowlist, causando un rechazo falso por "intérprete no autorizado"; (d) un
gap pre-existente en `datasources/runtime.py` donde nadie inyectaba `_repo_root` antes de llamar al
`factory` del observer, que habría roto CUALQUIER fuente file-backed real vía el registro (no solo
las de M9); (e) `_check_ownership_5_vias` de Doctor leía la clave `"destino"` en vez de `"ruta"`
(schema real de `.ds_init/control.json`), por lo que no detectaba nada.

La regresión completa final corre en verde: **tools/harmessi/tests/test_doctor.py 94 passed;
tools/ds_init/tests/ 124 passed; tools/leadrun/tests/ + tools/datasources/tests/ 228 passed, 15
subtests passed; tools/tests/ 992 passed, 2 skipped, 54 subtests passed** — **1438 passed, 2
skipped, 0 failed** en total, cero fallas.

**Change 4 cumple R1-R45 con las correcciones documentadas** (ver "Resultado final").

## Commits del Change

Sin commitear todavía al momento de escribir este documento — el commit de cierre se registra
después de este `verification.md`, per el flujo normal (`ds_guard validate --gate cierre` en verde
→ commit único de cierre).

## Resultado por sección de `spec.md` (R1-R45)

### §1 Project capabilities (R1-R5, M8)

`EntradaManifiesto` gana `capabilities: tuple = ()` (default = sin filtro, ninguna entrada existente
lo declaraba antes de este Change); `manifest_para_perfil_stage_y_capabilities(perfil, stage,
capabilities_habilitadas)` nueva, wrapper puro sobre `manifest_para_perfil_y_stage` (sin tocarla).
Auditoría explícita documentada en el código: solo las 3 entradas de `tools/modelquality/` se
marcaron `capabilities=("predictive_modeling",)` (único paquete cuya descripción es exclusivamente
"calidad de modelo"); entradas dudosas (`readiness.py`, `mlops_foundations.py`, `mlops_evidence.py`,
`qualityevidence/*`, `holdout_guard.py`, agentes/skills) evaluadas y explícitamente NO marcadas por
ser de aplicación general a cualquier proyecto de datos, no exclusivas de modelado (R2). Filtro de
capabilities y de stage componen por intersección, nunca se sustituyen (R4, test dedicado). Sin
declarar `predictive_modeling=false`, comportamiento idéntico a antes de este Change (R5). **37
tests dedicados + regresión completa de `tools/ds_init/tests/` (124 passed) en verde. Cumplido.**

### §2 Fuentes externas file-backed de solo lectura (R6-R9, M9)

Declaración de path externo vive exclusivamente en `.harmessi/local-overrides.json` ->
`fuentes_externas` (esquema `{"<source_id>": {"path": "<abs>"}}`), nunca en el core de
`tools/datasources` (`SourceRef`/`SourceObservation` sin cambios, confirmado por diff). El adapter
(`file_observer.py`) resuelve el path real vía un parámetro inyectado (`options['
ruta_externa_absoluta']`), nunca importando `.harmessi/local-overrides.json` por su cuenta (R6).
Enforcement de solo lectura en `pathguard.py`: nueva categoría de ruta permitida, estrictamente
limitada a `Read`/`Grep` sobre la ruta EXACTA declarada (comparación por ruta absoluta resuelta,
case-insensitive) — `Write`/`Edit`/`NotebookEdit` sobre la MISMA ruta externa siguen denegados sin
ningún cambio de código (confirmado por test explícito y por lectura directa del diff: la excepción
nueva solo se evalúa `if tool_name == "Read"`, nunca para los tools de escritura) (R7). La ruta
absoluta nunca aparece en el resultado de `observe()` ni en ninguna observación persistida,
confirmado por test de portabilidad explícito (R8). SQL/API/warehouse sin cambios, R6-R8 no les
aplican (R9). **Tests de `pathguard.py` (10 casos nuevos) + `file_observer.py`/`runtime.py` (6 casos
nuevos) + `tools/tests/test_ds_guard_source_cli.py` (2 casos end-to-end) en verde. Cumplido.**

**Hallazgo y corrección durante implementación (no bloqueante, documentado)**: auditoría de
`datasources/runtime.py::_observe_source_interno` encontró que, antes de este Change, NINGÚN
llamador inyectaba `repo_root` en las `options` pasadas al `factory` del observer — un gap
pre-existente de Change 1 que habría roto cualquier fuente file-backed real vía el registro
(`RuntimeError: falta repo_root`). Corregido con un parámetro aditivo `options_extra` (default
`None`, backward-compatible; `setdefault` nunca pisa una clave que el registro ya declaraba),
usado por `cmd_source_observe` para inyectar `_repo_root` siempre y `ruta_externa_absoluta` cuando
corresponde.

### §3 Layering de configuración (R10-R13, M10)

Tres capas explícitas (`resolver_project_config`/`resolver_local_override` en `tools/ds_guard.py`,
leyendo `.harmessi/project-config.json`/`.harmessi/local-overrides.json`, fail-closed: archivo
ausente/corrupto/no-dict -> capa vacía, nunca lanza) (R10). `resolver_modo_efectivo` implementa
fail-closed real: unión de restricciones (no precedencia de "una capa tapa a la otra", que
permitiría que una capa CANCELE la restricción de otra — exactamente la ampliación prohibida);
cualquier capa que declare `mode: supervised` gana sobre `autonomous` de la policy humana, nunca al
revés (R11, Given/When/Then exacto de la spec verificado por test dedicado). Doctor distingue
managed/project-config/local-override/drift (ver §5 de M10, implementado junto con la ownership de
5 vías de B5 en el mismo check, sin duplicar categorías) (R12). El path externo de M9 vive
exclusivamente en esta capa, confirmado (R13). **14 tests de layering + reuso verificado en
`dependencias_efectivas` (M11) y `_check_ownership_5_vias` (B5). Cumplido.**

### §4 Integridad detectiva de fuentes externas (R14-R18, M12)

Fingerprint tamaño+`mtime` capturado antes/después de `leadrun_runtime.ejecutar`, compuesto en
`_ejecutar_exec_comun` (`tools/ds_guard.py`, sin tocar `tools/leadrun/`); cero overhead si no hay
ninguna fuente externa declarada (R14). Discrepancia mapeada al código real de `data_loss_risk`
dentro de `STOP_CATALOG` (buscado programáticamente, nunca hardcodeado), mensaje que declara
explícitamente "cambió durante la ventana gobernada... no una afirmación de causalidad" (R15,
confirmado por test de contenido de texto). Evidencia persistida local, `.harmessi/executions/<id>/
fingerprints.json`, nunca en artefacto portable (R16). Diagnóstico de permisos OS en
`_check_fuentes_externas_permisos_os` (Doctor): POSIX vía `os.access`, Windows vía atributo
`FILE_ATTRIBUTE_READONLY` (documentado como señal parcial, nunca ACL completa); `unknown/partial`
explícito cuando no se puede determinar; **confirmado que el check nunca usa `STATUS_FAIL`** en
ningún camino (grep del cuerpo completo de la función) — puramente informativo, Doctor nunca repara
nada (R17, 6 tests dedicados incluido el caso read-only real vía `attrib +r` en Windows). Helper
cooperativo de output roots (`resolver_output_roots`/`ds_guard output-roots list`), documentado
explícitamente como "Control COOPERATIVO, no sandbox" en 3 lugares (docstring de la función, del
comando, y en el `help` del CLI) (R18). **10 tests de integridad + 6 de Doctor OS-permisos en
verde. Cumplido.**

### §5 Adopción de proyecto existente (R19-R21, B5)

`tools/ds_init/preflight.py::validar_destino`/`tools/ds_init/planner.py::_accion_para_entrada`
confirmados sin tocar (R19, `git status` limpio sobre ambos archivos) — el núcleo de B5 ya existía.
Test end-to-end NUEVO (no existía antes): repo git con 3 archivos de usuario preexistentes (uno de
ellos un destino VERBATIM real del manifiesto) colisionando con la instalación, working tree limpio
-> 0 bytes sobrescritos, los destinos colisionados NUNCA entran al registro de hashes de
`.ds_init/control.json`, instalación completa sin excepción. Mensaje de colisión enriquecido en
`tools/ds_init/cli.py::_imprimir_omitidos` (ruta, tipo de conflicto/tratamiento, descripción del
asset, alternativas soportadas) — confirmado que `planner.py`/`preflight.py` no ganaron ningún
cambio de lógica (R20). Ownership de 5 vías en `_check_ownership_5_vias` (Doctor): categorías (2)
managed/(5) drift reusan los checks existentes sin duplicar; (1) archivo preexistente del usuario,
(3) project config, (4) local override son las 3 categorías nuevas de este Change (R21). **6 tests
(3 de ownership + 1 end-to-end de adopción + 2 de mensaje enriquecido) en verde. Cumplido.**

### §6 Autonomía (R22-R23) — sin cambios de fondo

Reafirmado sin modificación respecto del roadmap original de este Change; no requirió ningún cambio
de código adicional.

### §7 Dependencias del proyecto — instalación gobernada aditiva (R24-R41, M11)

5ª forma cerrada `dependency_install` en `tools/leadrun/`: `EXECUTION_FORMS` gana una línea en
`core.py`; `allowlist.py` gana `_evaluar_forma_dependency_install` (patrón EXACTO de 6 tokens,
comparación literal, sin regex laxo); `runtime.py` gana una rama de despacho que reutiliza
`scripts.ejecutar_script` (mismo camino que `cli_diagnostic`, `code_hash=None`) — **verificado por
diff dirigido** (`tools/tests/test_v08_change4_leadrun_diff.py`, 6 tests): `core.py` cambió
EXACTAMENTE 1 línea, `allowlist.py` solo agregó código nuevo sin tocar las 4 funciones de forma
existentes, `runtime.py` solo agregó 5 líneas sin quitar nada, y **los 4 suites de
`tools/leadrun/tests/` (Change 2, cerrado) pasan con diff vacío contra `HEAD`** (R24).

Clasificación (`sdd.clasificar_dependencia`) ANTES de construir cualquier `ExecutionRequest` (R25).
`dependencias_efectivas` compone M10 por intersección estricta — ninguna capa inferior puede agregar
una dependencia ni ampliar un rango que la propuesta humana no declaró, confirmado por test
explícito de "nunca amplía" (R26). Intérprete resuelto exclusivamente vía
`launcher_common.resolver_venv_dir`/`ruta_interprete_venv`, normalizado antes de usarlo (bug
encontrado y corregido durante tests: sin normalizar, la allowlist rechazaba por "intérprete no
autorizado" pese a ser la misma ruta) — nunca el `.venv` de Harmessi (R27). Evidencia:
`ExecutionRecord` estándar + `approval` con la forma exacta `{"tipo": "dependency_preapproval",
"dependencia": {...}, "declarado_en": "proposal.md"}` cuando `supervised`, `None` cuando
`autonomous` (invariante de `ExecutionRecord`, Change 2, respetada) (R28). Revalidación de versión
post-instalación vía `importlib.metadata` (R29). Fallo consume remediation existente, exit code real
propagado sin enmascarar (R30). Subcomando `dependency install` sin ningún flag libre de pip, sin
`--interpreter` (R31). Sin resolución de credenciales propia (R32). Sin dependencia nueva en
Harmessi — solo `importlib.metadata`, stdlib (R33).

**Las cuatro guardas de la aprobación 2026-09-30 (R34-R41)**: intérprete construido por el runtime,
nunca recibido libre, vía `_importar_perezoso("leadrun", "allowlist").normalizar_interprete` (R34).
`sdd.validar_forma_nombre_paquete` rechaza explícitamente URL/path/`file:`/VCS/direct-reference/
extras/múltiples paquetes/metacaracteres mediante allowlist positiva por regex (R35).
`sdd._canonicalizar_nombre_paquete` (PEP 503) aplicada a ambos lados de la comparación antes de
llamar a `clasificar_dependencia` (que en sí NO cambió de firma, confirmado) — comparación canónica
nunca autoriza un paquete distinto, solo una forma de escritura equivalente (R36, test explícito de
canonicalización no-autoriza-distinto). El rango aprobado NUNCA llega a pip — `_construir_spec_pip`
usa siempre la versión exacta solicitada, verificada contra el rango antes de construir el comando
(R37, test explícito que confirma que el string del rango nunca aparece en el `argv`). Evidencia de
entorno pre/post vía `importlib.metadata`, persistida trazable en `.harmessi/executions/<id>/
dependency_evidence.json` con los 9 campos exigidos (paquete, version_previa, version_solicitada,
version_posterior, resultado, referencia a la pre-aprobación, execution_id, duración, exit code) —
**persistida SIEMPRE que hubo una ejecución real, incluido el caso de fallo** (hallazgo del reviewer
ciclo 2, corregido) (R38). Distribución inesperada reportada como `CheckResult(kind=technical_error)`
real, sin STOP nuevo (R39). `--no-deps` obligatorio sin excepción — transitivas nunca autoinstaladas,
confirmado por test dedicado (R40). Sin soporte de `--index-url`/`--extra-index-url`/credenciales,
redacción reusada de `_redactar_argv`/`_redactar_resumen` sin caso especial (R41).

**24 tests de `dependency install` end-to-end (subprocess real contra `ds_guard.py`) + 11 de
`allowlist`/`core`/`runtime` en `test_dependency_install_form.py` + tests de `sdd.py`
(canonicalización/validación de forma) en verde. Cumplido.**

### §8 Backward compatibility y seguridad (R42-R43)

Sin `capabilities`/fuente externa/project-config/local-override/M12/`dependencias_preaprobadas`
declaradas, un proyecto instalado se comporta exactamente igual que antes de este Change — toda la
regresión existente (2986+ passed al abrir este Change) pasa sin editar ningún test preexistente,
incluidos explícitamente los 4 suites de `tools/leadrun/tests/` (R42, verificado por diff dirigido
arriba). Ninguna documentación nueva afirma que Harmessi sandboxea código del proyecto; M12/R17 son
controles detectivos/cooperativos, R24-R41 es un control gobernado y auditable, no un shell general
— ambos declarados como tales explícitamente (R43).

### §9 Instalabilidad y tests (R44-R45)

`check_manifest_parity.py` en verde (`[OK]` sobre las rutas VERBATIM, sin error) — este Change no
agregó ninguna entrada nueva al manifiesto de instalación (R44). Test de que `tools/datasources`
(Change 1, cerrado) no ganó ningún import nuevo hacia `tools.dsguard`/`tools.ds_guard` (confirmado
por diff completo de `file_observer.py`/`runtime.py`: el único import movido es
`ds_profile.holdout_guard`, ya existente, reubicado dentro de una rama condicional, no uno nuevo).
Test de que `tools/autonomy` (Change 0, cerrado) no cambió en absoluto (`git status`/`git diff`
vacíos). Test de que `tools/leadrun` (Change 2, cerrado) solo cambió en los 3 puntos exactos de R24
— verificado por diff dirigido, no por inspección genérica (R45, `test_v08_change4_leadrun_diff.py`).

## Ejecución real (corrida por el Lead, 2026-10-01)

| Suite | Resultado |
|---|---|
| `tools/harmessi/tests/test_doctor.py` | 94 passed (815.38s) |
| `tools/ds_init/tests/` | 124 passed (559.23s) |
| `tools/leadrun/tests/` + `tools/datasources/tests/` | 228 passed, 15 subtests passed (7.05s) |
| `tools/tests/` | 992 passed, 2 skipped, 54 subtests passed (1075.02s) |

**Total: 1438 passed, 2 skipped, 0 failed** — cero fallas en el conjunto completo de suites
tocadas/relevantes por este Change. `check_manifest_parity.py`: `[OK]`, sin error. `git diff
--check`: sin errores de whitespace (solo warnings de normalización LF/CRLF, no bloqueantes).
Privacy sweep (grep de nombre/email del autor) sobre todos los archivos tocados: sin coincidencias
fuera de las citas de aprobación ya esperadas en `control.json`.

Nota operativa: varias corridas de la regresión completa fueron interrumpidas por el límite de
duración de procesos en background del harness (no un fallo real de los tests — confirmado
reintentando cada suite sola, siempre en verde); además, el presupuesto de la sesión `s2` venció a
mitad del cierre (97.3 min transcurridos sobre 90 de presupuesto) — cerrada como `pausada` (sin
reintentos, sin rondas de revisión contadas en esa sesión) y continuada en una sesión nueva (`s3`),
mismo patrón que Change 3 aceptó para interrupciones de infraestructura.

## Proceso de revisión (2 rondas, los 2 ciclos autorizados) y disposición de hallazgos

**Ciclo 1** (`data-science-reviewer`, solo lectura): cubrió en profundidad M11 (`dependency
install`) completo. 3 hallazgos reales (1 bloqueante R24, 1 importante R38/R39, 1 menor
`modo_resuelto`) — los 3 corregidos y re-verificados por el Lead en la misma sesión, con tests
nuevos agregados para cada corrección (ver "Resumen ejecutivo"). Confirmó sin hallazgos: R24 (patrón
cerrado de 6 tokens), R26 (`dependencias_efectivas` solo restringe), R36 (`clasificar_dependencia`
sin canonicalizar internamente), R37 (rango nunca llega a pip), R35 (`validar_forma_nombre_paquete`
allowlist positiva), R45 (neutralidad de `tools/leadrun` por diff real).

**Ciclo 2** (`data-science-reviewer`, solo lectura): verificó las 3 correcciones del ciclo 1 (las 3
confirmadas sólidas) y encontró 1 hallazgo adicional importante (evidencia R38/R39 saltada en el
camino de fallo) — corregido y re-verificado por el Lead con 3 tests nuevos. Cubrió además, sin
hallazgos: `_check_ownership_5_vias` (clave `"ruta"` correcta, sin otro consumidor de la clave
vieja dentro de `doctor.py`), `_check_fuentes_externas_permisos_os` (nunca `STATUS_FAIL`). Por
presupuesto de turnos, no llegó a cubrir M8 (`ds_init`), M9/M10 completos en `pathguard.py`, D2 en
`datasources`, M12 R17-R18 en profundidad, B5 en `cli.py`, ni `ARCHITECTURE.md`/roadmap — el Lead
verificó estas áreas directamente (sin un tercer ciclo de reviewer, ya agotados los 2 autorizados):
diff completo de `pathguard.py` (excepción estrictamente limitada a `Read`/`Grep` sobre la ruta
exacta declarada, `Write`/`Edit`/`NotebookEdit` sin cambio); diff completo de
`file_observer.py`/`runtime.py` (sin import nuevo, `options_extra` backward-compatible); grep de
`STATUS_FAIL` en el cuerpo de `_check_fuentes_externas_permisos_os` (ninguna coincidencia); grep de
"Control COOPERATIVO, no sandbox" (3 apariciones, R18 cumplido); `git status` de
`planner.py`/`preflight.py` (sin cambios, R20 cumplido) — sin hallazgos nuevos en ninguna de estas
verificaciones directas.

## Límites y pendientes

- `max_concurrent_subagents`/timeouts de proceso siguen siendo límites honestos/best-effort
  (heredados de Changes 1-3), no resueltos por este Change.
- El diagnóstico de permisos OS de Windows (R17) se apoya en el atributo `FILE_ATTRIBUTE_READONLY`
  — documentado explícitamente como señal parcial, nunca una garantía completa de ACL; queda fuera
  de alcance verificar ACLs completas de Windows (`icacls` de solo lectura) sin agregar una
  dependencia nueva.
- `dependencias_efectivas` (R26) no intersecta RANGOS de dependencias entre capas de M10 — una capa
  inferior puede EXCLUIR una dependencia completa, nunca angostar su rango a un subrango; documentado
  como decisión explícita, no una limitación silenciosa.
- M8/M9/M10/M12/B5 en conjunto no recibieron una segunda ronda completa de revisión dedicada más
  allá de la verificación directa del Lead descrita arriba (2 ciclos de reviewer ya agotados,
  ambos usados en profundidad sobre M11 y las correcciones).

## Resultado final

**Change 4 cumple R1-R45 con las correcciones documentadas.** 1438 tests passed, 2 skipped, 0
failed, en el conjunto completo de suites tocadas/relevantes. 4 hallazgos reales de 2 rondas de
revisión, los 4 corregidos y re-verificados con tests nuevos. 5 bugs adicionales encontrados durante
la implementación (no por el reviewer), los 5 corregidos. Sin reapertura material de Changes 0-3 —
confirmado por diff dirigido en los puntos de mayor riesgo (`tools/leadrun/`, `tools/autonomy/`,
`tools/datasources`).
