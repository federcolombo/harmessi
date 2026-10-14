# Spec — 20261013-governed-amendments

Change 3 de v0.10: Governed Amendments. Este Change es audit + SDD; no incluye implementación. Los requisitos describen el contrato que verificará el Change de implementación. Cubre dos operaciones gobernadas: (A) enmienda del scope autorizado de un Change aprobado y (B) re-adopción de guardrails sobre una closed list aditiva. Es el primer consumidor obligatorio de T1 `console_confirmed` (Change 2, R32).

Contexto verificado del código actual:
- La fuente de verdad del scope es `control["alcance"]["rutas_autorizadas"]`, materializado por `cmd_approve` (`tools/ds_guard.py`, ~l.415-435) desde los artefactos por defecto del Change unidos a la sección `## Alcance autorizado` de `proposal.md` (parser `sdd._normalizar_entrada_alcance`).
- Consumidores: `tools/dsguard/scope.py::evaluar_alcance` (~l.73); status/validate (`ds_guard.py` ~l.225, `repo.files_out_of_scope`); runtime `exec` (`ds_guard.py` ~l.2290 → allowlist de `leadrun`).
- Los outputs intrínsecos del harness (`.harmessi/executions/**`, `openspec/decisions/ledger.jsonl`) se excluyen con `scope.es_output_intrinseco` (lista cerrada; no se amplía).
- `control.json` no está autenticado.
- `.claude/guardrails.json` está protegido por pathguard (Write/Edit/NotebookEdit y Bash best-effort). Doctor lo compara contra la plantilla del repo origen con `guardrails_drift.RUTAS_MUTABLES` (`version` y `autonomy.mode|version|budgets|limits` se ignoran); el resto es drift permanente (`doctor._drift_guardrails_json`).
- Pathguard hoy protege solo `guardrails.json`.
- Primitive de T1 existente (Change 2): `tools/dsguard/human_presence.py::solicitar_confirmacion(contexto={change_id, artefacto, hash, accion})` y `campos_registro(resultado)` → `approval_channel`, `confirmed_at`, `channel_version="console/v1"`. Este Change NO añade primitive nueva.

## A. Principios y T1 obligatorio (R1-R7)
**R1.** Toda mutación de scope y toda re-adopción de guardrails exige T1 `console_confirmed`. T0 `declared` nunca alcanza, ni como fallback ni por flag.

**R2.** Sin consola de control soportada, la operación falla cerrada (exit 2, sin escritura). No se degrada a `declared`.

**R3.** No existe flag de canal `declared` para estas operaciones ni un `--yes`/`--force` que sustituya a T1.

**R4.** Se reutilizan `solicitar_confirmacion` y `campos_registro` tal cual; no se crea ninguna primitive de presencia nueva.

**R5.** Texto normativo obligatorio (inglés y castellano, mismo significado) en el contrato y en la documentación de usuario:
- «A `console_confirmed` approval means that a declared approval was accompanied by an interactive confirmation received through a supported control console for that specific operation. It does not prove the identity or authorship of the declared user and is not resistant to a deliberately synthesized local console input.»
- «una aprobación declarada con ese metadata fue acompañada por una señal T1 de presencia interactiva; Harmessi NO verificó que la persona declarada haya realizado físicamente esa aprobación.»

**R6.** T1 es señal de presencia interactiva; NO es identidad, autoría, firma ni no-repudio. `--usuario` sigue siendo metadata declarada.

**R7.** Las operaciones no dependen de ningún provider de agentes (core neutral).

## B. Enmienda de scope: CLI y semántica (R8-R17)
**R8.** Comando: `ds_guard scope amend --change-id X [--add P]... [--remove P]... --motivo M --usuario U [--fecha F] [--dry-run] [--expected-scope-hash H]`. `--add` y `--remove` son repetibles; debe haber al menos uno.

**R9.** Comando de lectura: `ds_guard scope show --change-id X` informa revisión (`seq`), `scope_hash` vigente y rutas efectivas. No muta ni pide T1.

**R10.** Toda ruta de `--add` se valida con `_normalizar_entrada_alcance`; las protecciones existentes (sin `..`, sin absolutas, sin comodines repo-wide, sin paths protegidos) quedan intactas. Una ruta inválida rechaza toda la operación.

**R11.** Las rutas por defecto del propio Change (artefactos del Change) no se pueden quitar: `--remove` de una de ellas rechaza toda la operación.

**R12.** Add de una ruta ya presente y remove de una ruta ausente son no-op deterministas. Si todos los elementos son no-op: sin mutación, sin T1 y sin entrada en el historial (exit 0 con mensaje explícito).

**R13.** Solo se enmiendan Changes aprobados y no cerrados ni descartados. Un Change sin aprobar, cerrado o descartado se rechaza.

**R14.** No existe reemplazo total del scope (`--set`/`--replace`): solo add/remove incrementales.

**R15.** La comparación de rutas usa la misma normalización que `_normalizar_entrada_alcance` (separadores, espacios, Unicode normalizado de forma consistente, directorios `dir/**`); la igualdad para duplicados y no-op se define sobre la forma normalizada.

**R16.** Los outputs intrínsecos del harness (`es_output_intrinseco`) no requieren ni generan enmiendas; la lista cerrada no se amplía.

**R17.** Reducir scope (`--remove`) afecta solo el trabajo futuro: no borra artifacts, evidencia ni historia, no reescribe tasks, y las rutas de ownership de writers NO se modifican por enmienda (queda para Change 4). Los harness-owned paths no cambian.

## C. Historial encadenado y scope efectivo (R18-R28)
**R18.** El historial vive en `openspec/changes/<id>/amendments.jsonl`, append-only, una entrada JSON por línea.

**R19.** Campos de cada entrada: `schema_version`, `seq`, `utc`, `operacion` (`add`|`remove`|`mixta`), `add`, `remove`, `rutas_despues` (lista completa y ordenada), `scope_hash_before`, `scope_hash_after`, `prev_hash`, `motivo`, `usuario`, `fecha_declarada`, `approval_channel`, `confirmed_at`, `channel_version`, `entry_hash`.

**R20.** `entry_hash` = sha256 del JSON canónico (`sort_keys=True`, separadores fijos, UTF-8) de la entrada sin el campo `entry_hash`. `prev_hash` es el `entry_hash` de la entrada anterior (cadena vacía fija en `seq=1`). `scope_hash` = sha256 del JSON canónico de la lista ordenada de rutas.

**R21.** El scope efectivo de un Change es `rutas_despues` de la última entrada válida de la cadena; sin entradas, es el scope materializado al aprobar (revisión 0). `control["alcance"]["rutas_autorizadas"]` pasa a ser caché derivada.

**R22.** Función única `scope.alcance_efectivo(change_dir, control) -> (rutas, hallazgos)`, usada por los tres consumidores (`evaluar_alcance`, status/validate, runtime `exec`). Ningún consumidor lee la caché directamente.

**R23.** Fail-closed ante cualquier anomalía: cadena rota (`prev_hash`/`entry_hash`), `approval_channel != console_confirmed`, `seq` fuera de orden o con huecos, `scope_hash_before` que no coincide con el estado derivado de la entrada anterior, JSON inválido. `exec` rechaza; validate emite el hallazgo `ALCANCE-ENMIENDA-INVALIDA`; el scope efectivo en ese caso es el vigente antes de la entrada inválida para reporte, y `exec` no autoriza nada nuevo.

**R24.** La primera enmienda ata `scope_hash_before` al scope vigente (revisión 0) calculado desde la caché al aprobar; si la caché no coincide con el hash de aprobación registrado, se rechaza.

**R25.** Scope efectivo = scope inicial aprobado + secuencia válida de enmiendas. La caché `control.json["alcance"]["rutas_autorizadas"]` es solo compatibilidad y NUNCA supera al historial: si diverge, el efectivo se reconstruye determinísticamente desde la cadena, se emite el hallazgo `ALCANCE-CACHE-DIVERGENTE` y una edición manual de `control.json` no se convierte en enmienda.

**R26.** Editar `amendments.jsonl` a mano rompe los hashes y se detecta (detección de edición ingenua). No es criptografía: quien pueda reescribir toda la cadena coherentemente la falsifica; el historial de git es evidencia externa.

**R27.** Tras aplicar una enmienda, la caché de `control.json` se actualiza como optimización; si esa escritura falla, el estado sigue consistente porque la fuente de verdad es la cadena.

**R28.** Re-aprobar `proposal.md` de un Change con enmiendas efectivas se rechaza con exit 2, sin rebase ni replay (decisión aprobada M4). Cambiar materialmente la proposal exige un flujo futuro o un nuevo Change; el mensaje lo indica.

## D. Atomicidad y concurrencia (R29-R33)
**R29.** Ambas operaciones tienen modo `--dry-run`: calculan y muestran el diff exacto, no piden T1 y no mutan.

**R30.** El modo ejecución recalcula todo desde cero (no confía en el dry-run) y muestra el diff exacto antes del prompt.

**R31.** Orden exacto de ejecución: (1) recalcular inmediatamente antes; (2) optimistic concurrency (`--expected-scope-hash` / `--expected-guardrails-hash`); (3) T1; (4) releer y verificar que el estado no cambió (si cambió, abortar sin escribir); (5) construir el contenido completo nuevo del registro (anterior + línea nueva) en archivo temporal del mismo directorio y validar la cadena del temporal; (6) `os.replace`; (7) refrescar la caché de control, best-effort y solo scope (si falla, el estado sigue consistente porque la cadena es la fuente de verdad); (8) validación posterior. Nunca es estado válido «aprobación registrada + mutación incompleta».

**R32.** El registro de la operación es la fuente de verdad; la caché se escribe después. Un crash tras el `os.replace` deja estado consistente y recuperable.

**R33.** Si la escritura falla tras T1, no queda estado parcial y la confirmación ya consumida no se reutiliza.

## E. T1 binding (R34-R38)
**R34.** Se invoca `solicitar_confirmacion` con `artefacto="scope-amendment"` o `artefacto="guardrails-readopt"`, `accion` descriptiva de la operación y `hash` = sha256 del diff canónico `{operación, estado antes, cambio exacto, estado después}`.

**R35.** La confirmación liga: tipo de operación, target, hash del estado actual, diff exacto, hash del estado resultante y Change/proyecto. Single-use, no reutilizable para otra mutación ni operación (otro diff implica otro `hash` y otro challenge), sin token persistente.

**R36.** Los campos T1 (`approval_channel`, `confirmed_at`, `channel_version`) se embeben en el registro de la operación vía `campos_registro` (operation approval); no se exige `proposal.md` ni `control["aprobaciones"]`.

**R37.** No se persiste el challenge, la respuesta ni datos del terminal (privacidad de Change 2 R19).

**R38.** Sin consola de control, EOF, timeout, respuesta incorrecta o replay: exit 2 y sin escritura.

## F. Re-adopción de guardrails (R39-R52)
**R39.** Comando: `ds_guard guardrails readopt --motivo M --usuario U [--dry-run] [--expected-guardrails-hash H]`. Prohibidos `accept-current-state` y `adopt-all`.

**R40.** Calcula el diff semántico entre el archivo actual y el baseline (plantilla del repo origen unida a las adopciones previas válidas).

**R41.** Closed list EXACTA (decisión aprobada M2): `holdouts`, `data_raw`, `secretos_extra`, `autonomy.sealed_sources`. Solo monotónica de endurecimiento: effective_new = effective_previous + elementos nuevos válidos; nunca remover, reemplazar, modificar, relajar, reducir ni reinterpretar. Elemento duplicado = no-op. Cada elemento es string no vacío, sin traversal ni rutas absolutas. Estructura no list-like → fail-closed sin coerciones. `autonomy.sealed_sources` admite solo ADD (desellar no es re-adoptable; satisface el boundary de Change 0 sobre «source sealing»).

**R42.** EXCLUIDOS: `excepciones`, `write_scopes`, `autonomy.source_access`, hooks, permisos de tools, security ceilings, protected paths, claves desconocidas y las cuatro mutables de Corrective B (`autonomy.mode|version|budgets|limits`, que no necesitan re-adopción). La closed list no se amplía sin decisión material.

**R43.** TODO el diff debe pertenecer a la closed list y ser aditivo. Diff mixto (adición permitida más cualquier remoción, modificación o clave prohibida), solo inelegible, `guardrails.json` malformado o conflicto de baseline → rechazo TOTAL sin aplicar parcialmente ni escritura.

**R44.** Diff vacío → no-op: sin mutación, sin T1, sin registro.

**R45.** Registro project-level propio (decisión aprobada M3): `openspec/decisions/guardrails-adoptions.jsonl`, append-only con cadena simple. NO es `ledger.jsonl`, NO usa acciones ni semántica del decision ledger, NO depende de `decision amend`; schema y validator propios. Sin blockchain, firma ni event sourcing genérico: tamper evidence básico, no autoría. Campos: `schema_version`, `seq`, `utc`, `adiciones` (por clave), `guardrails_hash_before`, `guardrails_hash_after` (sobre el JSON normalizado), `prev_hash`, `motivo`, `usuario`, `fecha_declarada`, `approval_channel`, `confirmed_at`, `channel_version`, `entry_hash`; mismo hash canónico que R20.

**R46.** La operación NO modifica `.claude/guardrails.json` ni `control.json`.

**R47.** T1 binding con `hash` = sha256 del diff canónico de las adiciones (R34).

**R48.** El diff exacto (clave por clave, elementos añadidos) se muestra antes del prompt de T1.

**R49.** La baseline efectiva es plantilla ∪ adopciones válidas acumuladas; una adopción futura parte del baseline ya ampliado.

**R50.** Cadena de adopciones inválida (hash, `seq`, canal) → ninguna adopción cuenta y se emite hallazgo.

**R51.** Las claves mutables de Corrective B no necesitan re-adopción; no se incluyen en la closed list.

**R52.** Dry-run, execute, concurrencia y atomicidad: aplican R29-R33 con `expected_guardrails_hash`.

## G. Doctor (R53-R57)
**R53.** Para una clave elegible, si la diferencia con la plantilla son únicamente adiciones previamente re-adoptadas con cadena válida (igualdad de conjuntos con la unión adoptada), no cuenta como drift.

**R54.** Elemento extra no adoptado, adoptado eliminado, clave prohibida cambiada, cadena rota o `guardrails.json` malformado → hallazgo/drift según la severidad existente.

**R55.** Con adopciones válidas, Doctor emite un PASS informativo que las menciona. El managed hash de Change 1 no se actualiza para simular aceptación.

**R56.** Cadena de adopciones inválida: la diferencia sigue siendo drift y se emite un hallazgo.

**R57.** La semántica de la closed list mutable (`RUTAS_MUTABLES`) no cambia. Doctor nunca re-adopta.

## H. sync, managed hashing y upgrade (R58-R60)
**R58.** `sync` nunca re-adopta ni enmienda scope ni emite T1: un `guardrails.json` existente se omite como hoy.

**R59.** El hash por archivo del baseline gestionado de Change 1 no se toca; `regenerar_control` no se reutiliza.

**R60.** upgrade/migration y re-adopción son conceptos separados: ninguno invoca al otro.

## I. Pathguard (R61-R63)
**R61.** (Decisión aprobada M1) Pathguard protege `openspec/changes/<change-id>/amendments.jsonl` y `openspec/decisions/guardrails-adoptions.jsonl` contra Write/Edit/NotebookEdit y escrituras detectables por shell (redirecciones y comandos de escritura), con el patrón de `guardrails.json`.

**R62.** NO bloquea lectura, validate, `--dry-run` ni la escritura interna legítima de `ds_guard scope amend` / `guardrails readopt` (proceso Python). No existe ruta alternativa de «editar y reparar»: un registro alterado manualmente es inválido y fail-closed.

**R63.** Pathguard NO hace auténtico criptográficamente el registro. La seguridad descansa en T1 `console_confirmed` + binding exacto + cadena/hash + validación fail-closed + Git como evidencia externa. `control.json` no se protege (no está autenticado; la caché nunca supera a la cadena).

## J. Autonomía (R64-R65)
**R64.** El Lead llega hasta «necesito ampliar scope X por motivo Y» (corre el dry-run) y se DETIENE solo para el T1 humano; luego continúa.

**R65.** No hay pasos humanos adicionales más allá de ese STOP.

## K. Tests a prever (R66-R95)
Scope amend:
**R66.** add y remove básicos; scope efectivo cambia en `evaluar_alcance`, status/validate y `exec`.
**R67.** Duplicados y no-op deterministas (sin T1, sin entrada).
**R68.** Conflicto de `--expected-scope-hash` y cambio concurrente tras T1.
**R69.** T0 rechazado; T1 exitoso con canal inyectado; agente o no-consola rechazado.
**R70.** Edición manual de la caché ignorada; edición de la cadena detectada.
**R71.** Matching Unicode, espacios y directorios.
**R72.** Outputs del harness sin enmiendas espurias.
**R73.** Re-aprobación de proposal con enmiendas rechazada (exit 2).
**R74.** Change cerrado, descartado o no aprobado rechazado.
**R75.** Rutas por defecto no removibles; ruta inválida rechaza todo.
**R76.** Atomicidad: fallo de escritura tras T1 no deja estado a medias.

Readopt:
**R77.** Diff solo closed-list elegible aplicado.
**R78.** Mixto permitido más prohibido: rechazo total; solo prohibido: rechazo.
**R79.** T0 rechazado; T1 exitoso.
**R80.** Clave desconocida, guardrails malformado, conflicto de baseline: rechazo.
**R81.** No-op sin mutación; remoción rechazada.
**R82.** Doctor refleja el nuevo baseline; drift posterior (elemento extra o faltante) correcto.
**R83.** Hash gestionado de Change 1 coherente; `sync` no re-adopta.

Transversales:
**R84.** Pathguard: escritura a los dos registros denegada (Write/Edit/NotebookEdit y shell best-effort); lectura permitida.
**R85.** T1 binding: challenge no reutilizable entre operaciones ni entre diffs.
**R86.** Boundaries: módulos nuevos solo stdlib, sin imports de provider (`test_architecture_boundaries.py`).
**R87.** Privacidad: sin challenge, respuesta ni datos de terminal en los registros.
**R88.** Dry-run no pide T1 ni muta en ambas operaciones.
**R89.** `alcance_efectivo` es el único camino de lectura del scope (test de no regresión sobre consumidores).
**R90.** Aprobación histórica T0 de Changes sin enmiendas sigue funcionando sin cambios.

Foco del reviewer (todos obligatorios):
**R90a.** El agente no auto-amplía scope ni auto-readopta guardrails; T0 nunca alcanza.
**R90b.** T1 ligada al diff exacto; sin replay entre operaciones.
**R90c.** Closed list exacta; `sealed_sources` solo ADD; sin partial apply; sin generic baseline accept.
**R90d.** Caché no supera a la cadena (`ALCANCE-CACHE-DIVERGENTE`); cadena alterada fail-closed (`ALCANCE-ENMIENDA-INVALIDA`).
**R90e.** `sync` no adopta; proposal con enmiendas efectivas no se re-aprueba.
**R90f.** Pathguard protege los registros sin romper el CLI gobernado ni el dry-run.
**R90g.** Atomicidad: fallo tras T1 no deja estado a medias y el estado es recuperable.

Aceptación manual humana (no automatizable), sobre un Change/proyecto temporal descartable:
**R91.** `scope amend` con T1 real en la terminal del usuario funciona y queda registrado.
**R92.** `guardrails readopt` con T1 real funciona y Doctor refleja el baseline.
**R93.** Ambos comandos desde la herramienta de shell del agente fallan cerrados.
**R94.** Verificación POSIX en un host POSIX (no probado en el audit).
**R95.** Verificación del Change de implementación: tests dirigidos por writer, reviewer con máximo 2 ciclos, regresión relevante, `git diff --check` y revisión de privacidad.

## L. Fuera de alcance y límites explícitos (R96-R101)
**R96.** Sin criptografía: la cadena detecta edición ingenua, no resiste reescritura coherente de toda la cadena.
**R97.** Un agente con capacidad de escribir fuera de pathguard (p. ej. shell no cubierto) o de sintetizar input de consola puede falsificar registros o T1.
**R98.** T1 no es identidad ni autorización (Change 2, R3-R4).
**R99.** No se modifica el ownership de writers por enmienda (Change 4), ni se amplía `es_output_intrinseco`.
**R100.** No se autentica `control.json` ni se reescriben aprobaciones históricas.
**R101.** Sin implementación en este Change; sin T2/T3; sin T1 en `decision`/`remediation`.
**R102.** Fuera de alcance preservado: default de 90 min, ledger amend, enum de decisiones, scratchpad, turn limits/reanudaciones, writer lifecycle y validación de T1 en host POSIX real.

## Criterios de aceptación
- [ ] R1-R7: T1 obligatorio, fail-closed, sin flag declared y con texto normativo EN/ES.
- [ ] R8-R17: CLI de scope y semántica de add/remove/no-op.
- [ ] R18-R28: historial encadenado, `alcance_efectivo` único y fail-closed.
- [ ] R29-R38: dry-run, concurrencia óptima, atomicidad y T1 binding por operación.
- [ ] R39-R52: re-adopción sobre closed list aditiva con rechazo total en casos mixtos.
- [ ] R53-R60: Doctor, sync y managed hashing coherentes.
- [ ] R61-R65: pathguard de los dos registros y autonomía con un solo STOP humano.
- [ ] R66-R95: tests, aceptación manual y verificación listados.
- [ ] R96-R102: límites explícitos documentados.
- [ ] Sin código funcional modificado en este Change.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica (Change documental sin datos).

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica.

## Baseline (condicional — modeling)
No aplica.

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
No aplica.
