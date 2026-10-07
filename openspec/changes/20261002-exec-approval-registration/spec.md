# Spec — 20261002-exec-approval-registration

Notación: cada requisito `Rn` tiene criterio de aceptación verificable. Todo error: exit 2 (uso) o 3
(entorno), sin escribir `control.json` (fail-closed).

## Requisitos

### A. CLI (R1–R4)
**R1 — Subcomando.** `ds_guard exec approve {pytest,script,notebook}`. Reutiliza los MISMOS argumentos
semánticos que `exec <forma>` (`--change-id`, `--interpreter`, `--paths`/`script`+args/`--manifest`
`--execute`, flags tras `--`), excepto `--timeout`/`--json`, más metadata humana obligatoria:
`--usuario`, `--fecha`, `--alcance`, `--cita`.
**R2 — Prohibiciones.** No existe `--hash`, string de comando libre, ni forma desconocida; argparse
rechaza lo no declarado.
**R3 — Usuario.** `--usuario` se valida con `core.validar_usuario_sin_email` (igual que `approve`).
**R4 — Ayuda.** `ds_guard exec approve -h` describe la semántica (ligada a la ejecución exacta) y el
modelo de confianza (registro declarativo, sin autenticación criptográfica).

### B. Builders compartidos (R5–R7)
**R5 — Un solo builder por forma.** Se extraen de `cmd_exec_pytest/script/notebook` funciones puras
`_construir_exec_<forma>(args, repo_root)` que devuelven `(argv, artefacto, hash_comando, algoritmo)`;
tanto `exec` como `exec approve` las usan. Prohibido un segundo cálculo de hash o normalización.
**R6 — Validación única del request.** La construcción de `ExecutionRequest` y la evaluación con
`leadrun.allowlist.evaluar_comando` se extraen a un helper compartido usado por `_ejecutar_exec_comun` y
por `exec approve`. Lo que el runtime rechazaría no puede aprobarse (R12).
**R7 — Equivalencia.** Para el mismo pedido semántico, `approve` y `exec` producen el mismo
`(artefacto, hash)` (test de igualdad directa entre builders y end-to-end).

### C. Semántica de hash por forma — PRESERVADA (R8–R10)
**R8 — pytest.** artefacto `"pytest:" + "|".join(paths)`; hash `leadrun.core.content_sha256(list(argv))`
con `argv = [interpreter, "-m", "pytest", *paths, *flags]` (el orden de paths/flags importa; el intérprete
se compara tal como lo recibe `exec`). `algoritmo = "sha256/argv-canonical-json"`.
**R9 — script (M1 resuelta: semántica v2, versionada).** Las aprobaciones NUEVAS de script ligan la
identidad completa de la ejecución: artefacto = `args.script`; hash = `content_sha256` del objeto
`{"algorithm": "sha256/script-content+argv/v2", "script": <ruta repo-relativa POSIX>, "script_sha256":
hash_lf_v1(repo_root/script), "argv": [<intérprete normalizado con allowlist.normalizar_interprete>,
script, *argumentos del script en orden]}`; `algoritmo = "sha256/script-content+argv/v2"`. Cambiar el
contenido, un argumento, su orden, la ruta o el intérprete invalida la aprobación.
**R9b — Legacy de script.** `exec script` acepta además una aprobación histórica cuya entrada más
reciente para el artefacto tenga `algoritmo == "sha256/lf/v1"` y `hash == hash_lf_v1(script)`
(semántica histórica: solo contenido). Es reconocida y NO es error, pero se reporta como
`aprobación legacy (sha256/lf/v1): no liga argumentos; re-aprobar con 'ds_guard exec approve script'`
en stderr y, si el esquema de `ExecutionRecord.approval` lo admite sin cambios, como marca
`legacy: true` en la evidencia. `exec approve script` NUNCA crea entradas legacy. Sin migración
automática. Una entrada v2 mal formada o con hash distinto NO cae al camino legacy (se decide por el
`algoritmo` de la entrada más reciente).
**R10 — notebook.** artefacto = `args.manifest`; hash `hash_lf_v1(repo_root/manifest)`; `algoritmo =
"sha256/lf/v1"`. Sin cambios, salvo que el audit de implementación demuestre un hueco material
equivalente al de script (ver design D8).

### D. Registro (R11–R14)
**R11 — Registro.** Se agrega una entrada a `control["aprobaciones"]` con la estructura existente
(`artefacto, algoritmo, hash, registrado_utc, usuario, fecha_declarada, alcance_aprobado, cita`) usando
`_cargar_change` y `core.escribir_control`. Sin otro store.
**R12 — Fail-closed previo.** Antes de escribir: request construido correctamente (script/manifest
legible), `ExecutionRequest` válido y `evaluar_comando` permitido contra el alcance del Change;
cualquier fallo → sin escritura.
**R13 — Ligado al Change.** La entrada se escribe en el `control.json` de `--change-id`; una aprobación
de otro Change no satisface a `exec` de este.
**R14 — Salida.** Imprime `artefacto`, `algoritmo` y hash registrado (informativo); exit 0. No imprime
sugerencias de edición manual.

### E. Consumo (R15–R16)
**R15 — Consumo sin cambios.** `exec` consume la entrada vía `_resolver_aprobacion_exec` →
`validar_aprobacion` sin modificaciones de semántica; target/flag/script/manifest distinto → «aprobación
ausente/desincronizada».
**R16 — Modos.** `supervised` sigue exigiendo aprobación; `autonomous` no cambia; `exec approve` en modo
autonomous registra igual la entrada (inocua) sin alterar el modo.

### F. Compatibilidad (R17–R19)
**R17** `ds_guard approve`, aprobaciones existentes, proposal/spec/design, `STOP_CATALOG`, checkpoints,
dependency pre-approval, `ExecutionRecord`, runtime de Change 2: sin cambios.
**R18** Suites preexistentes de exec/approve (`test_ds_guard_exec.py` y afines) pasan SIN editarse.
**R19** El refactor de builders no cambia argv, artefacto ni hash de ninguna forma respecto de
`HEAD` (test de regresión que fija vectores).

### G. Documentación (R20)
**R20** `sdd.md` y `sdd.md.tmpl` (idénticos en contenido) indican la vía concreta
`ds_guard exec approve …` para `supervised`, y el modelo de confianza; `.ds_init/control.json` se
regenera por la vía soportada para que Doctor no reporte drift.

## Criterios de aceptación
1. supervised + pytest sin aprobación → bloqueado.
2. `exec approve pytest` → entrada creada; `exec pytest` exacto → ejecuta (E2E real, `ExecutionRecord`).
3. Otro target, otro flag, otro orden, otro `--change-id` → no match.
4. Request inválido (ruta fuera de alcance, absoluta, traversal, forma no reconocida) → exit 2, sin
   entrada.
5. Sin `--hash`; argparse rechaza flags desconocidos.
6. `approve` de archivos físicos sigue igual; autonomous sin cambios.
7. Script v2: cambiar contenido, argumento, orden o intérprete invalida; legacy `sha256/lf/v1` sigue
   aceptada con aviso; `exec approve script` nunca crea legacy; v2 no cae a legacy.
8. Notebook: aprobar manifest → `exec notebook` permitido; manifest modificado → no.
9. `control.json` escrito por `escribir_control`; los tests no insertan JSON a mano.

## Unidad de análisis / grain (condicional)
No aplica.

## Cutoff / information boundary (condicional)
No aplica.

## Baseline (condicional)
No aplica.

## Métrica primaria (condicional)
No aplica.

## Métricas secundarias (opcional)
No aplica.
