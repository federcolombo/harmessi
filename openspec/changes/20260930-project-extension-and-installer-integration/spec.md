# Spec — 20260930-project-extension-and-installer-integration

Notación: `Rn` con criterio verificable, `Given/When/Then` cuando aplica. Ningún requisito reabre
`tools/autonomy/core.py`, `tools/autonomy/policy.py`, `tools/datasources/core.py`,
`tools/leadrun/core.py`/`runtime.py` (Changes 0-2, cerrados) ni `proposal.md`/`spec.md`/`design.md`
de Change 3 (cerrado) — todo lo de acá compone esos módulos por import o los extiende por archivos
nuevos, nunca edita su contenido salvo que el requisito lo diga explícitamente.

## 1. Project capabilities (M8)

**R1 — Campo `capabilities` aditivo en `EntradaManifiesto`.** `tools/ds_init/manifest.py` gana un
campo `capabilities: tuple = ()` en `EntradaManifiesto` (default = sin filtro, ninguna entrada
existente lo declara, comportamiento idéntico a hoy). Vocabulario inicial: `predictive_modeling`
(único candidato con contenido real a excluir en este Change — `data_analysis`/`reporting` quedan
documentados como vocabulario futuro, sin entradas reales que filtrar todavía, para no inventar una
distinción sin efecto observable).
- Given el manifiesto actual sin ninguna entrada con `capabilities` declarado, When se construye el
  plan para cualquier perfil/stage, Then el resultado es idéntico al de antes de este Change
  (mismo test de paridad que ya usa `tools/ds_init/tests/test_manifest.py`).

**R2 — Filtro capability-aware.** Nueva función `manifest_para_perfil_stage_y_capabilities(perfil,
stage, capabilities_habilitadas)` (nombre exacto a definir en implementación, wrapper aditivo sobre
`manifest_para_perfil_y_stage` ya existente, sin modificarla) que además excluye las entradas cuyo
`capabilities` no sea subconjunto de `capabilities_habilitadas`. `predictive_modeling` deshabilitado
excluye, cuando sea técnicamente separable, tooling de holdout/modeling exclusivo, model-quality,
promotion/readiness ML, MLOps, agentes/skills exclusivos de modelado — identificados por auditoría
de implementación (tarea de SDD→implementación: listar exactamente qué entradas del manifiesto hoy
son "exclusivas de modelado").
- Given `predictive_modeling=false` explícito, When se construye el plan, Then las entradas
  marcadas `capabilities=("predictive_modeling",)` no aparecen; las que no declaran `capabilities`
  siguen apareciendo igual (autonomy, pathguard, source governance, Data Contracts, ds_profile,
  decision ledger, reporting, evidence, seguridad, trazabilidad — R3 de la decisión M8).

**R3 — Doctor distingue `N/A` de `MISSING`/`ERROR`.** Un asset no provisionado por
`predictive_modeling=false` reporta `N/A — capability not enabled`, nunca `MISSING` ni `ERROR`.
- Aceptación: test de `harmessi doctor` sobre una instalación con la capability deshabilitada — 0
  `ERROR`, los assets excluidos aparecen como `N/A` con esa razón explícita.

**R4 — Sin segunda distribución; `installation_stage` y `capabilities` son ejes distintos.**
`stage_minimo` (ya existente) y `capabilities` (nuevo) se aplican de forma independiente y
compuesta (intersección), nunca uno sustituye al otro.
- Aceptación: test que confirma que filtrar por stage sin capabilities, y por capabilities sin
  cambiar stage, dan resultados distintos y ambos se pueden combinar sin conflicto.

**R5 — Backward compatibility explícita.** Sin declarar `predictive_modeling=false`, una
instalación/upgrade se comporta exactamente igual que antes de este Change; un upgrade nunca
desactiva ni elimina assets automáticamente; activar una capability después provisiona lo faltante
vía `sync`/upgrade sin borrar nada existente.

## 2. Fuentes externas file-backed de solo lectura (M9)

**R6 — Declaración de path externo en local override (M10), nunca en el core.** Un `source_id` ya
registrado (Change 1) puede tener, en la capa de local override, un path físico fuera del repo. El
core de `tools/datasources` (`SourceRef`/`SourceObservation`/`SourceProvenance`) **no cambia**: sigue
sin ningún campo de path. El adapter de archivo (`file_observer.py`, Change 1, cerrado) resuelve el
path real consultando la capa de local override en tiempo de observación — vía un parámetro
inyectado, no un import nuevo de `tools.dsguard`/`tools.ds_guard` dentro de `tools/datasources`
(mantiene la regla 11 de `ARCHITECTURE.md`, dirección de dependencias).

**R7 — Enforcement de solo lectura.** Para el path externo declarado: lectura y perfilado/
observación autorizados; write/edit/delete/move/rename/overwrite bloqueados por `pathguard`
(extensión aditiva de `tools/dsguard/pathguard.py` — mismo criterio que holdouts/`data/raw`
existentes, una nueva categoría de ruta protegida, no un mecanismo nuevo).
- Given una fuente externa declarada read-only, When el Lead (o un subagente) intenta escribir/
  mover/borrar esa ruta vía una herramienta interceptada por `pathguard`, Then se bloquea igual que
  ya bloquea holdouts hoy.

**R8 — Portabilidad.** La ruta absoluta nunca entra en `DataContract`, `SourceObservation` portable,
evidence portable, ni manifest compartido — vive solo en la capa de local override.
- Aceptación: test que confirma que ninguna observación persistida bajo `.harmessi/observations/`
  contiene la ruta externa en texto plano.

**R9 — Sin reglas de filesystem para fuentes sin path.** SQL/API/warehouse siguen el modelo
`source_id` + extensión del proyecto ya fijado por M6 (Change 1) — R6-R8 de acá no les aplican.

## 3. Layering de configuración (M10)

**R10 — Tres capas explícitas.** `managed defaults → project config → local machine overrides →
effective config`, compuesto en `tools/ds_guard.py` (mismo patrón que `_resolver_budgets` de
Change 3: composición externa, sin tocar `pathguard.py`/`tools/autonomy/policy.py`). Ubicación de
cada capa: project config versionado en git (ubicación exacta en implementación, p. ej.
`.harmessi/project-config.json`, sin secretos); local overrides no necesariamente versionado
(ubicación exacta en implementación, p. ej. `.harmessi/local-overrides.json`, con una entrada
sugerida en `.gitignore` del manifiesto si corresponde).

**R11 — Fail-closed, solo restringe.** `permiso_efectivo = policy_humana ∩ project_config ∩
local_override` (o semántica equivalente fail-closed). Un override no puede: habilitar `autonomous`
si la policy humana no lo habilita; desellar una fuente; ampliar `write`; desactivar protección de
secretos; desactivar holdout/protecciones; ampliar remediation/budgets (Change 3) por encima del
máximo humano.
- Given una policy humana `supervised` y un local override que declara `mode: autonomous`, When se
  resuelve el modo efectivo, Then sigue siendo `supervised` — el override se ignora en esa clave
  específica (nunca error silencioso que oculte la intersección: se reporta como
  `AUTONOMY-POLICY-*` existente si aplica, o se documenta el código nuevo si hace falta).

**R12 — Doctor distingue 4 categorías.** Managed files OK / customización de proyecto soportada /
override local soportado / drift no autorizado de managed files. Un override válido **no** produce
`HARMESSI-DRIFT`.

**R13 — Declaración del path externo de M9 vive en local override.** Confirma la integración entre
M9 y M10: la única ubicación soportada para declarar el path físico de una fuente externa es esta
capa — R6 y R10 son la misma pieza de mecanismo, no dos independientes.

## 4. Integridad detectiva de fuentes externas (M12)

**R14 — Fingerprint pre/post alrededor de una ejecución gobernada.** Para toda fuente file-backed
declarada read-only (M9) que participe como entrada de una ejecución vía `ds_guard exec ...`
(Change 2, sin modificar): fingerprint (tamaño + `mtime`) capturado ANTES de invocar
`leadrun_runtime.ejecutar` y recalculado DESPUÉS — compuesto en `tools/ds_guard.py`, mismo patrón
que la referencia liviana de métricas de eficiencia de Change 3 (no toca `tools/leadrun/`). Hash de
contenido (`sha256`) solo si está configurado, el costo es razonable (umbral de tamaño a definir en
implementación), o la policy lo exige — nunca por default sobre archivos grandes.

**R15 — Discrepancia mapea a `data_loss_risk`, STOP 7 ya existente.** Si el fingerprint post difiere
del pre, la ejecución queda marcada con ese código (sin crear un STOP nuevo, sin tocar
`tools/autonomy/core.py`). El mensaje declara explícitamente "la fuente cambió durante la ventana
gobernada", nunca "Harmessi demuestra que el agente la modificó" — se persiste evidencia suficiente
(qué cambió del fingerprint) para que un humano investigue, sin afirmar causalidad no verificada.

**R16 — Evidencia local, nunca portable.** El fingerprint se persiste como evidencia local (p. ej.
junto al `ExecutionRecord` referenciado, o en un directorio propio bajo `.harmessi/`), referenciada
por `source_id` — nunca en `DataContract`/`SourceObservation` portable/manifest compartido (mismo
principio que R8).

**R17 — Diagnóstico de permisos OS, solo lectura.** `harmessi doctor` reporta si una ruta externa
declarada read-only parece también protegida por el sistema operativo: en POSIX, información de
permisos cuando sea observable; en Windows, solo información obtenible de forma fiable sin mutar
nada (el atributo "solo lectura" de Windows no se confunde con una garantía completa de ACL). Si no
puede determinarlo con certeza, reporta explícitamente `OS read-only guarantee: unknown/partial`.
Doctor **nunca** ejecuta `chmod`/`icacls`/mutación de ACL/atributos.
- Aceptación: test con una ruta de fixture marcada read-only por el OS (donde el test pueda
  hacerlo de forma confiable en el entorno de CI) y otra sin marcar — Doctor reporta distinto en
  cada caso, y un tercer caso (permiso no determinable) reporta `unknown/partial` sin fallar.

**R18 — Helper cooperativo de output roots.** El runtime de ejecución (Change 2, sin modificar)
puede recibir, opcionalmente, una declaración de output roots permitidos que el código del proyecto
puede consultar — **control cooperativo, no sandbox**: no intercepta escrituras arbitrarias del
proceso, no reemplaza permisos del OS ni el fingerprint pre/post. Documentado como tal en el
docstring del helper y en la ayuda del CLI.

## 5. Adopción de proyecto existente (B5)

**R19 — Confirmar y no duplicar lo ya existente.** `tools/ds_init/preflight.py::validar_destino`
(repo Git + working tree limpio, sin exigir proyecto vacío) y
`tools/ds_init/planner.py::_accion_para_entrada` (`ACCION_OMITIR_EXISTENTE`, nunca sobrescribe) ya
implementan el núcleo de B5 — confirmado por auditoría (`proposal.md`). Este Change no reescribe
esos módulos.
- Aceptación: test end-to-end nuevo (no existía) que instala sobre un repo git con código/archivos
  de usuario preexistentes y working tree limpio, confirmando 0 archivos de usuario sobrescritos.

**R20 — Mensaje de colisión enriquecido.** El mensaje hoy solo imprime la ruta. Se extiende
(`tools/ds_init/cli.py`, sin tocar la lógica de `planner.py`/`preflight.py`) para incluir: ruta,
tipo de conflicto (archivo ya existe con tratamiento `X`), asset que Harmessi quería instalar
(descripción de la `EntradaManifiesto`), alternativas soportadas (override vía config de proyecto/
local, ubicación alternativa si aplica, resolución humana). Nunca mueve/renombra nada
automáticamente.

**R21 — Ownership de 5 vías en Doctor.** `harmessi doctor` distingue: (1) archivo preexistente del
usuario, nunca administrado por Harmessi (los destinos omitidos por colisión, R19-R20, nunca entran
al registro de hashes); (2) managed file de Harmessi; (3) project config soportada (M10); (4) local
override soportado (M10); (5) drift no autorizado de un managed file. Harmessi solo gestiona los
assets que posee — no incorpora lo preexistente del usuario al manifiesto ni a ningún registro de
hashes.

## 6. Instalación/configuración de autonomía (ya descripto en el roadmap original, sin cambios de fondo)

**R22 — `supervised` por defecto (M4), coherencia de versión de policy (M2).** Sin cambios respecto
del roadmap original de este Change: instalación nueva y upgrade quedan en `supervised` salvo
elección explícita; el upgrade actualiza guard/runtime antes de permitir `autonomous`; Doctor
detecta una policy con capacidad de seguridad no soportada por la versión instalada.

**R23 — Camino de upgrade plan-first desde v0.7.** Sin cambios respecto del roadmap original: dry-
run por defecto, archivo sin cambios se actualiza, archivo con drift se reporta como conflicto y
nunca se pisa en silencio, archivos del proyecto nunca se tocan, el upgrade no activa `autonomous`.

## 7. Dependencias del proyecto — instalación gobernada aditiva (M11, resolución 2026-09-30)

**Decisión material confirmada por el autor (supersede la versión anterior de esta sección, que
solo exponía clasificación sin vía de instalación):** una dependencia pre-aprobada (M11) SÍ debe
poder instalarse sin intervención humana adicional en modo `autonomous`, reutilizando el runtime
público de Change 2 (`tools/leadrun/`) mediante una **extensión aditiva** — no un segundo runtime,
no shell arbitrario. Ver `design.md` D7 para el análisis completo de por qué esto es aditivo y no
una reapertura material de Change 2.

**R24 — Nueva forma cerrada `dependency_install` en el vocabulario de `tools/leadrun`.**
`tools/leadrun/core.py::EXECUTION_FORMS` gana una 5ª forma: `"dependency_install"` (única línea
tocada de ese archivo; las 4 formas existentes y su validación no cambian). `tools/leadrun/
allowlist.py` gana `_evaluar_forma_dependency_install`, función nueva y aislada (no toca las 4
funciones de forma existentes), que reconoce EXACTAMENTE el patrón de 6 tokens:
`"<intérprete>" -m pip install --no-deps <nombre>==<versión>` — pin exacto con `==`, `--no-deps`
obligatorio (evita instalar transitivas no pre-aprobadas), sin ningún otro flag admitido, un solo
paquete por invocación. `tools/leadrun/runtime.py::ejecutar` gana una rama de despacho que reutiliza
`scripts.ejecutar_script` para esta forma (**mismo camino exacto que ya usa `cli_diagnostic`**,
`code_hash=None` por el mismo motivo: no hay un único archivo canónico que hashear). `tools/leadrun/
scripts.py` **no cambia en absoluto** (ejecutor genérico de subprocess, ya sirve cualquier `argv`).
- Aceptación: los tests existentes de `tools/leadrun/tests/{test_core,test_allowlist,test_scripts,
  test_runtime}.py` (Change 2, cerrado) pasan SIN editar ninguno — prueba de que las 4 formas
  originales no cambiaron de comportamiento.

**R25 — Clasificación ANTES de construir la solicitud de ejecución.** `ds_guard.py` (nuevo
subcomando `ds_guard dependency install --change-id <id> --nombre <n> --version <v>`) llama
`sdd.clasificar_dependencia(nombre, version, dependencias_efectivas)` **antes** de construir
cualquier `ExecutionRequest`. Si el resultado no es `"no_stop"`, se rechaza inmediato (exit 2, el
mismo código STOP de `new_dependency` ya usado por `dependency classify`) — la ejecución nunca llega
a la allowlist ni al runtime.

**R26 — `dependencias_efectivas` compone M10 (nunca amplía).** `dependencias_efectivas =
control["dependencias_preaprobadas"] ∩ restricción_de_project_config ∩ restricción_de_local_override`
(mismo principio fail-closed de R11 de la sección 3: las capas inferiores solo pueden acotar la
lista/rango pre-aprobado por la propuesta humana, nunca agregar una dependencia ni ampliar un rango
que la propuesta no declaró).

**R27 — Solo el `.venv` del proyecto, nunca global ni el de Harmessi.** El intérprete de la
instalación se resuelve con el mismo mecanismo ya usado en todo el repo
(`launcher_common.resolver_venv_dir`/`ruta_interprete_venv`) — el mismo intérprete que ya exige
`allowlist.evaluar_comando` para script/pytest. `pip install` queda scoped a ese intérprete por
semántica estándar de `python -m pip` (nunca `--user`, nunca instalación global — ningún flag que lo
permita entra en el patrón cerrado de R24). Las dependencias de Harmessi (solo-stdlib, sin
`requirements.txt` propio) nunca son destino de esta operación — no hay ninguna vía para apuntar el
intérprete de la instalación al `.venv` de Harmessi mismo, dado que `interprete_autorizado` siempre
es el del proyecto en el flujo de `ds_guard exec`/`dependency install`.

**R28 — Evidencia: `ExecutionRecord` + referencia a la pre-aprobación.** La instalación es una
ejecución gobernada más: `leadrun_runtime.ejecutar` persiste el `ExecutionRecord` igual que
cualquier otra forma (R13 de Change 2, sin tocar) — comando efectivo (redactado si aplica), exit
code, duración, `executed_by`, `mode`. El campo `approval` (ya `Optional[dict]` genérico, Change 2
nunca lo tipa) transporta, compuesto en `ds_guard.py`: `{"tipo": "dependency_preapproval",
"dependencia": {"nombre": ..., "version": ...}, "declarado_en": "proposal.md"}` — la trazabilidad a
la aprobación humana es la misma que ya liga `control["dependencias_preaprobadas"]` al hash de
`proposal.md` (Change 3, `cmd_approve`), sin inventar una `ApprovalRef` nueva por instalación
individual.

**R29 — Revalidación de entorno post-instalación.** Tras una instalación exitosa (`exit_code == 0`),
`ds_guard.py` re-consulta la versión efectivamente instalada (p. ej. `importlib.metadata.version` o
`pip show`, ejecutado igual que cualquier diagnóstico de solo lectura) y la compara contra la
solicitada — una discrepancia se reporta como hallazgo, sin bloquear retroactivamente lo ya
instalado (evidencia para que un humano revise, mismo espíritu que M12).

**R30 — Fallo consume remediation existente, sin contador paralelo.** Un `exit_code != 0` de la
instalación se resuelve exactamente como cualquier otro fallo de `ds_guard exec` (Change 2/3): el
`CheckResult` resultante es `FAIL`, y una reinvocación correctiva consume la ventana de
`control["remediaciones"]` ya existente — no se crea un contador nuevo.

**R31 — Escape del contrato, bloqueado por construcción.** El subcomando `dependency install` NO
acepta ningún argumento libre de pip (sin `--extra-args`, sin `--index-url`, sin `-r
requirements.txt`) — solo `--nombre`/`--version`, ambos validados (nombre debe figurar en
`dependencias_efectivas`, version debe ser exactamente la del rango aprobado vía `clasificar_
dependencia`) antes de construir el `argv` fijo de R24. El writer nunca invoca este subcomando (no
tiene la herramienta Bash, igual que el resto del contrato de ejecución).

**R32 — Sin resolución de credenciales propia.** Harmessi no gestiona ni inyecta credenciales para
`pip install` — cualquier autenticación a un índice privado depende de la configuración de entorno/
`pip.conf` ya existente del proyecto, fuera del alcance de Harmessi (mismo principio ya establecido:
Harmessi nunca es un gestor de secretos).

**R33 — Sin dependencia nueva en Harmessi.** `ds_guard.py` invoca `python -m pip install ...` como
subprocess (exactamente como ya invoca scripts/pytest/notebooks) — no importa `pip` como librería en
ningún código propio de Harmessi.

### Cuatro guardas adicionales (aprobación humana 2026-09-30, aclaran el contrato, no lo cambian)

**R34 — Intérprete construido por el runtime, nunca recibido libre.** El intérprete SIEMPRE es el
resuelto por el mismo mecanismo ya usado para el resto de `ds_guard exec ...` (el
`interprete_autorizado` que `allowlist.evaluar_comando` ya exige) — nunca un path aportado por el
llamador/writer, nunca Python global, nunca otro venv arbitrario, nunca el `.venv` del propio
Harmessi. La forma efectiva (`<venv-python> -m pip install --no-deps <nombre>==<versión>`) la
construye `ds_guard.py` internamente; el subcomando CLI nunca acepta un argv/comando libre ni un
`pip` invocado sin `python -m` por delante.

**R35 — Rechazo explícito de formas de paquete no soportadas.** El `--nombre` recibido se valida
como nombre de distribución PyPI simple (PEP 508 `name`, sin extras) ANTES de cualquier otro
procesamiento — se rechaza sin ejecutar nada: URLs (`http://`/`https://`), paths locales, `file:`,
referencias VCS (`git+...`), direct references (`name @ url`), extras (`package[extra]`), múltiples
paquetes en una invocación (`--nombre` es un único token, sin espacios/comas), y cualquier
metacaracter de shell (reutiliza `core.contiene_metacaracter_prohibido`, ya existente).

**R36 — Canonicalización de nombre (PEP 503), sin dependencia nueva.**
`_canonicalizar_nombre_paquete(nombre) -> str` = `re.sub(r"[-_.]+", "-", nombre).lower()` (regla
exacta de PEP 503, solo `re` de stdlib). La comparación contra `dependencias_efectivas` (R26) usa el
nombre canonicalizado de AMBOS lados (lo declarado en `proposal.md` y lo solicitado por
`--nombre`) — dos nombres que difieren solo en mayúsculas/`-`/`_`/`.` se tratan como el mismo
paquete, **nunca** como autorización para un paquete distinto. `clasificar_dependencia` (Change 3,
cerrada) **no cambia**: sigue haciendo comparación exacta de string; recibe los nombres ya
canonicalizados desde `ds_guard.py` (Change 4).

**R37 — Rango aprobado nunca llega a pip.** Flujo obligatorio: versión exacta solicitada
(`--version`) → nombre canonicalizado (R36) → `clasificar_dependencia` confirma que esa versión
puntual satisface el rango aprobado → se aplican restricciones de project/local config (R26) → si
pasa, se construye el comando cerrado con esa versión exacta (`==<versión>`) → se ejecuta. El rango
de la propuesta (p. ej. `>=1.2,<2`) **nunca** se pasa a `pip` ni se usa para que el resolver de pip
elija una versión — pip solo ve un pin exacto, siempre.

**R38 — Evidencia de entorno pre/post.** Antes de ejecutar: se captura la versión previamente
instalada del paquete solicitado si existía (`importlib.metadata.version`, `None` si no estaba) y
el conjunto de nombres de distribuciones instaladas en el venv (`importlib.metadata.distributions()`).
Después de ejecutar: se recapturan ambos. Se persiste, trazable (junto a la referencia de
`ExecutionRecord` ya existente, R28, sin duplicar sus campos): paquete solicitado, versión previa,
versión solicitada, versión posterior, resultado, referencia a la pre-aprobación, `execution_id`,
duración, exit code.

**R39 — Detección de instalaciones inesperadas, sin STOP nuevo.** Se compara el conjunto de nombres
de distribuciones pre/post: el único cambio esperado es el paquete solicitado (aparece si no
estaba, o cambia de versión si ya estaba — eso NUNCA es un hallazgo). Cualquier OTRO nombre de
distribución nuevo en el post (`--no-deps` debería impedirlo, pero se verifica, no se asume) se
reporta como hallazgo — `CheckResult` con `kind=technical_error` (vocabulario ya existente,
`dsguard.checks.KIND_TECHNICAL_ERROR`), **nunca un STOP nuevo**, evidencia para revisión humana.

**R40 — Transitivas faltantes no se autoaprueban.** Si el paquete solicitado necesita otra
distribución no instalada y `--no-deps` impide que pip la traiga, la instalación puede fallar (exit
code de pip no-cero) — Harmessi NUNCA descubre ni instala esa dependencia transitiva
automáticamente. El fallo consume remediation existente (R30). Cualquier dependencia adicional
necesaria debe estar pre-aprobada explícitamente en la propuesta y ejecutarse mediante su propia
invocación de `dependency install` — nunca un efecto colateral de instalar otra.

**R41 — Sin soporte de índices/credenciales.** El patrón cerrado de R24/R35 no admite
`--index-url`/`--extra-index-url`/tokens/credenciales. Si el entorno del proyecto ya tiene
configuración de pip externa (p. ej. `pip.conf`), Harmessi no la lee, no la copia a evidence, no la
persiste. Ningún secreto puede aparecer en el comando (estructuralmente, por el patrón cerrado) ni
en la evidencia persistida — mismo mecanismo de redacción ya usado para cualquier `ExecutionRecord`
(Change 2/3, `_redactar_argv`/`_redactar_resumen`), aplicado igual acá, sin caso especial.

## 8. Backward compatibility y seguridad

**R42 — Ningún comportamiento cambia sin declarar una opción nueva.** Sin `capabilities` declarado,
sin fuente externa declarada, sin project config/local override, sin M12 configurado, sin
`dependencias_preaprobadas` declaradas: un proyecto instalado se comporta exactamente igual que
antes de este Change. Regresión completa existente (2986+ passed al momento de abrir este Change)
no requiere editar ningún test preexistente — incluidos, explícitamente, los 4 suites de
`tools/leadrun/tests/` de Change 2 (R24).

**R43 — No-sandbox, en todos lados donde corresponda.** Ninguna documentación nueva (SDD, skill,
ayuda de CLI) afirma que Harmessi sandboxea código del proyecto, previene escrituras arbitrarias, o
garantiza permisos de OS que no verificó. M12/R18 son controles detectivos/cooperativos; R24-R41
(instalación de dependencias) es un control gobernado y auditable, **no** un shell general — ambos
declarados como tales explícitamente, nunca presentados como una garantía más fuerte de la real.

## 9. Instalabilidad y tests

**R44 — Manifiesto y paridad.** Nuevas entradas (si las hubiera para módulos nuevos de este Change)
con `tratamiento`/`stage_minimo` correctos; `check_manifest_parity` sigue en verde.

**R45 — Tests de repo/neutralidad.** Test de que `tools/datasources` (Change 1, cerrado) no ganó
ningún import nuevo hacia `tools.dsguard`/`tools.ds_guard` por la integración de M9 (la resolución
del path externo se inyecta, no se importa). Test de que `tools/autonomy` (Change 0, cerrado) no
cambió en absoluto. Test de que `tools/leadrun` (Change 2, cerrado) solo cambió en los 3 puntos
exactos de R24 (`EXECUTION_FORMS`, la función nueva de `allowlist.py`, la rama de despacho de
`runtime.py`) — verificado por diff dirigido, no por inspección genérica.
