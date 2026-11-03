# Spec — 20261005-operational-autonomy-hardening

Cada `Rn` tiene criterio de aceptación verificable. Todo cambio es aditivo o más estricto; un proyecto sin las claves
nuevas se comporta como antes salvo el efecto de seguridad declarado en R5 (límites `limits` que antes se ignoraban).

## A. Límites agregados: `limits` vs `budgets` (R1–R10)

**R1 — Representación canónica.** `autonomy.budgets` (`aggregate_minutes`, `max_sessions`, `session_minutes`,
`max_concurrent_subagents`, `remediation_max_intentos_default`) es la canónica hacia adelante; `autonomy.limits`
(`max_sessions`, `max_total_minutes`) sigue legible (legacy). Mapeo: `limits.max_sessions → max_sessions`,
`limits.max_total_minutes → aggregate_minutes`. No hay tercer lugar de configuración.
**R2 — Resolución.** Un único resolvedor (`_resolver_budgets`, firma y retorno actuales intactos; una variante
`_resolver_budgets_con_fuentes` devuelve además las fuentes) calcula por eje: solo `budgets` ⇒ ese valor; solo
`limits` ⇒ el traducido; ambos ⇒ el MENOR (más estricto); ninguno ⇒ default actual. Nunca uno pisa al otro ampliando.
**R3 — Fail-closed.** Un valor presente y no entero positivo (bool excluido) en `limits.max_sessions`/`max_total_minutes`
levanta `BudgetsInvalidosError` (`AUTONOMY-POLICY-LIMITS`) igual que `budgets`; `limits` no-dict ⇒ mismo error. Las
claves desconocidas dentro de `limits` se ignoran en el resolvedor (las reporta `policy.py`).
**R4 — Fuentes visibles.** Por eje, la fuente efectiva es `budgets`, `limits`, `ambas (mínimo=…)` o `default`.
`session aggregate` (texto y `--json`) y `session status` muestran: valor efectivo, fuente(s) y, cuando difieren,
ambos valores; consumo (`minutos_consumidos_totales`, `sesiones_totales`) y restante (`límite − consumo`, mínimo 0).
`--json` conserva las claves actuales (`limites_configurados` = valores efectivos) y agrega `limites_fuentes` y
`restante`. El rechazo de `session start` por límite incluye la fuente.
**R5 — Enforcement real.** Con límite efectivo `aggregate_minutes` y consumo agregado ≥ límite, `session start`
se rechaza (exit 2, `AUTONOMY-LIMIT-AGGREGATE-BUDGET`) sin escribir `control.json`; idem `max_sessions`. Esto aplica
también a proyectos que solo declaraban `limits` (corrección de seguridad). El resultado es LIMIT/`checkpoint_resumable`:
sin STOP, sin aprobación automática (test E2E con consumo > límite y con sesiones ≥ máximo).
**R6 — `autonomous` con `budgets`.** `parse_autonomy_policy` considera satisfechos los límites requeridos para
`mode: autonomous` si cada eje está provisto por `limits` o por `budgets` (`aggregate_minutes`≡`max_total_minutes`),
y expone `max_sessions`/`max_total_minutes` = mínimo de ambas fuentes. Un valor inválido en cualquiera de las dos
degrada a `supervised` (hallazgo `AUTONOMY-POLICY-LIMITS`). Con `limits` completos el resultado es idéntico al actual
(tests existentes intactos). No se modifican `STOP_CATALOG`, `POLICY_TABLE` ni ninguna decisión de autonomía.
**R7 — Documentación.** ARCHITECTURE y la plantilla del Lead documentan solo `autonomy.budgets`; `limits` se
describe como legacy compatible. Ningún template generado escribe `limits`.
**R8–R10** reservadas para ajustes de implementación que no cambien R1–R7.

## B. Recuperación de presupuesto agotado y allowlist de sesión (R11–R17)

**R11 — Mensaje literal.** Todo bloqueo por `PRESUPUESTO AGOTADO` del hook (Bash/PowerShell, Write/Edit, Agent,
SendMessage) incluye un bloque de recuperación con comandos listos para copiar, generados con el intérprete real
(`sys.executable` del hook, entre comillas), el `change_id` de la sesión activa (`control["change_id"]`) y la sintaxis
real de la CLI:
`"<interprete>" tools/ds_guard.py session status --change-id <id>`,
`"<interprete>" tools/ds_guard.py session close --change-id <id> --estado pausada` y
`"<interprete>" tools/ds_guard.py session start --change-id <id>` (indicado como «después del cierre»).
Nada hardcodeado de esta máquina; si no se conoce el `change_id` o el intérprete, se omite el comando afectado sin
inventarlo (y el mensaje lo dice).
**R12 — Coincidencia hook↔mensaje.** Cada comando literal de `status`/`close` del mensaje es aceptado por el
allowlist del mismo hook (test que lo verifica sobre el texto generado). `session start` NO se agrega al allowlist:
con sesión activa (aunque esté agotada) no puede evadirse; tras `close` ya no hay sesión activa y el hook permite todo.
**R13 — Variantes seguras del mismo intérprete.** El token de intérprete de `session note|status|close` puede ir con
o sin comillas y, normalizado (`normcase`+`normpath`, separadores equivalentes, case en Windows), debe ser idéntico al
intérprete autorizado; una ruta relativa se resuelve contra la raíz del repo y se compara igual. Sin comillas solo
si no contiene espacios. Un nombre sin ruta (`python`) o cualquier otro ejecutable ⇒ rechazado. Se mantiene el rechazo
de metacaracteres de encadenado (`& ; | \` $ ( ) < > \n`).
**R14** `status` (lectura) no necesita `--change-id` distinto del activo; el requisito de `--change-id` de la CLI no
cambia (el mensaje lo incluye).
**R15–R17** reservadas.

## C. Normalización del intérprete (R18–R21)

**R18 — Simétrica.** `leadrun.allowlist.evaluar_comando` normaliza con `normalizar_interprete` tanto `argv[0]` como
`interprete_autorizado` antes de compararlos. Mismo ejecutable (case/separadores/`normpath`) ⇒ permitido; otro ⇒
«intérprete no autorizado».
**R19 — Hash de pytest.** La identidad `sha256/argv-canonical-json` de `exec pytest` usa el intérprete NORMALIZADO en
`argv[0]` (la ejecución sigue usando el valor provisto). Equivale al valor previo para quien ya pasaba el intérprete
normalizado (aprobaciones existentes siguen válidas) y hace que mayúsculas/minúsculas/separadores no cambien la identidad.
**R20 — Tests portables:** construidos con `sys.executable` y variantes derivadas (upper/lower, `/` vs `\`), sin rutas personales.
**R21** Sin cambios en el resto del runtime de `exec`.

## D. Alcance autorizado en `proposal.md` (R22–R32)

**R22 — Sección.** `## Alcance autorizado` (título exacto en su línea). Cada bullet `- <ruta>` (con o sin backticks)
declara una ruta/patrón; líneas que no sean bullets se ignoran (comentarios de plantilla).
**R23 — Validación (fail-closed, todo-o-nada).** Cada entrada, tras normalizar (`strip`, `\` rechazado, quitar `./`,
colapsar `//`, barra final ⇒ `/**`): repo-relativa; sin ruta absoluta (`/`, `C:\`, `~`); sin segmento `..`; sin
espacios ni caracteres de shell (`$ ; & | < > ( ) " ' \``), ni `? [ ] { } !`; sin `.git` como primer segmento; `*` solo
dentro de un segmento (`test_foo_*.py`) o `**` únicamente como último segmento (`dir/**`); el primer segmento no puede
contener `*` (impide `*` / `**` / `*/x` repo-wide); máx. 500 entradas, 260 caracteres. Cualquier entrada inválida ⇒
hallazgo `SDD-ALCANCE-INVALIDO` y la aprobación de `proposal.md` se rechaza completa (exit 2, sin escribir nada).
**R24 — Materialización.** Al aprobar `proposal.md` (cualquier `approval_mode`), si la sección existe y es válida:
`control["alcance"]["rutas_autorizadas"]` = ordenado y sin duplicados de (artefactos por defecto del Change ∪ entradas
declaradas). Reemplaza el contenido anterior (declarativo); la CLI imprime lo agregado y lo retirado. Si la sección
no existe o no tiene bullets, el alcance NO se toca (compatibilidad). Sin edición manual de `control.json`.
**R25 — Por hash.** El scope queda ligado al hash de `proposal.md` aprobado; re-aprobar con el mismo contenido
re-materializa idénticamente (idempotente); cambiar la sección exige nueva aprobación.
**R26** El parser es una función pura `sdd.parsear_alcance_autorizado(texto) -> (rutas, hallazgos)`.
**R27 — Plantilla.** La plantilla `proposal.md` incluye `## Alcance autorizado` con comentario guía. `init` sigue
creando solo los artefactos del Change (la sección es opcional hasta la primera aprobación).
**R28–R32** reservadas.

## E. Semántica de directorio (R33–R36)

**R33 — Canónica.** `dir/**` significa «el directorio y todos sus descendientes», sin alcanzar hermanos
(`scripts/**` no cubre `scripts_old/x.py`). Es la forma recomendada y la que materializa R23 para `dir/`.
**R34 — validate/scope.** Sin cambios en `repo.path_matches_any` (ya cumple R33 vía `fnmatchcase`); test que fija
`scripts/**` ⇒ `scripts/a.py` y `scripts/b/c.py`, no `scripts_old/a.py`.
**R35 — exec.** `_coincide_alcance` acepta además entradas `dir/**` (prefijo `dir/`); conserva la semántica previa
de entrada exacta o prefijo de directorio plano (legacy). Declarar solo `dir/**` basta para `exec script|pytest` y
para `validate`.
**R36** Un patrón con `*` dentro de un segmento (p. ej. `tools/tests/test_x_*.py`) en exec se resuelve con `fnmatch`
sobre la ruta completa; sin `*`, comportamiento actual.

## F. `verification.md` y outputs internos (R37–R42)

**R37 — Default.** `cmd_init` agrega `openspec/changes/<id>/verification.md` a `rutas_autorizadas` (junto a los 5
artefactos); `init` no crea el archivo. Changes existentes no cambian.
**R38 — Outputs intrínsecos.** `scope.es_output_intrinseco(ruta)` es verdadero SOLO para `.harmessi/executions/**`
y `openspec/decisions/ledger.jsonl` (rutas exactas conocidas). `scope.evaluar_alcance` y `cmd_status` los excluyen
de `ALCANCE-RUTA`. Ninguna otra ruta interna (p. ej. `.harmessi/project.json`) queda exenta; sin allowlist genérica.
**R39 — No relaja exec.** Los outputs intrínsecos no quedan autorizados para `exec` (solo se excluyen del evaluador
de scope de validate/status).
**R40** Una ruta funcional fuera de scope sigue produciendo `ALCANCE-RUTA`.
**R41–R42** reservadas.

## G. N1 — falso positivo de lectura (R43–R46)

**R43** `Read`/`Grep` estructurados sobre `guardrails.json` siguen permitidos; `Write`/`Edit`/`NotebookEdit` sobre
`guardrails.json` siguen bloqueados (tests explícitos).
**R44** En `_evaluar_shell`, la detección de escritura ignora redirecciones inocuas: `N>/dev/null`, `N>>/dev/null`,
`&>/dev/null`, `>/dev/null`, `N>&M` (p. ej. `2>&1`) y `>$null`/`>nul`/`2>nul`. Cualquier otra redirección (`>`, `>>`
a un archivo real) y los patrones de escritura (`rm`, `tee`, `sed -i`, `cp`, `mv`, `git add`, …) mantienen el bloqueo.
`grep … guardrails.json 2>/dev/null | head` se permite; `echo x >> .claude/guardrails.json` y
`cat a > .claude/guardrails.json 2>/dev/null` siguen bloqueados.
**R45** No se construye un parser de shell. La limitación (Bash es best-effort) se documenta en el docstring del módulo.
**R46** Sin cambios a la protección de secretos, holdouts ni data/raw.

## H. Compatibilidad e inercia (R47–R51)

**R47** `STOP_CATALOG`, `POLICY_TABLE`, `approval_mode`, checkpoints de negocio, dependency install, exec approvals,
Cards y model governance: sin cambios (tests de inercia/neutralidad existentes verdes). `tools/autonomy/policy.py`
solo cambia en R6; sin nuevos imports.
**R48** Proyecto sin `limits` ni `budgets`: defaults actuales. Proyecto con solo `budgets`: comportamiento actual de
los comandos de sesión.
**R49** `repo.path_matches_any` y sus consumidores (reporting, nbrunner, ds_profile, mlops, scientific_validity) sin cambios.
**R50** `ds_guard` mantiene sus exit codes 0/1/2/3.
**R51** El hook sigue siendo fail-safe: cualquier error leyendo `control.json`/sesión permite la acción, como hoy.

## Tests requeridos (mínimo)
Budgets: limits-only, budgets-only, iguales, distintos (más estricto, ambos órdenes), limits inválido, budgets
inválido, sin ninguno, aggregate enforcement E2E (`session start` bloqueado por minutos y por cantidad), fuentes y
restante en `aggregate`/`status`, `policy` con `budgets`-only autonomous y con ambos. Recuperación: mensaje con
change-id/intérprete/sintaxis reales, aceptación por el allowlist, `close`→`start` posible, `start` fuera del
allowlist. Intérprete: case, separadores, mismo/distinto, hash de pytest estable. Scope: sección parseable, exacto,
dir/glob, `..`, absoluto, shell, `*` repo-wide, aprobación materializa, idempotencia, sin sección no toca,
`verification.md` por defecto, executions/ledger exentos, ruta funcional bloqueada, `scripts/**` vs hermano, exec con
`dir/**`. Hook: Read/Grep permitidos, Write/Edit bloqueados, Bash con `2>/dev/null` permitido, Bash con redirección
real bloqueado.
