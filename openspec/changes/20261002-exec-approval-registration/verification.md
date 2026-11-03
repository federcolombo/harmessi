# Verificación — 20261002-exec-approval-registration

## Resumen ejecutivo
Change correctivo preexistente (interlude de v0.9-dev). Agrega `ds_guard exec approve {pytest,script,
notebook}`, la vía soportada para registrar la aprobación de ejecuciones gobernadas que el runtime ya
exigía y consumía. SDD aprobado por hash el 2026-10-02, con M1 resuelta (script v2 + legacy
reconocida). Todas las ejecuciones de este Change pasaron por el runtime gobernado
(`ds_guard exec pytest`) y sus aprobaciones se registraron con el subcomando nuevo, sin editar
`control.json` a mano. Las corridas están en `.harmessi/executions/` (no versionado).

## Resultados por requisito (resumen)
- **R1–R4 (CLI):** `exec approve` con los mismos argumentos semánticos que `exec` (compartidos vía
  `_agregar_args_exec_*`), metadata humana obligatoria, sin `--hash`, ayuda con el modelo de confianza.
- **R5–R7 (builders):** `_construir_exec_pytest/_script/_notebook` y `_validar_request_exec`
  compartidos por `exec` y `exec approve`; el hash se calcula solo en los builders. Confirmado por
  diff contra HEAD: artefacto, argv, mensajes de error y exit codes de pytest/notebook idénticos.
- **R8, R10 (pytest/notebook):** semántica preservada (`sha256/argv-canonical-json` y `sha256/lf/v1`).
  Hash de pytest fijado con vector literal congelado en tests.
- **R9, R9b (script):** nueva semántica v2 (`sha256/script-content+argv/v2`: ruta, contenido,
  intérprete normalizado, argumentos en orden); legacy `sha256/lf/v1` aceptada con aviso a stderr solo
  si la entrada más reciente del artefacto es legacy; una v2 desincronizada no cae a legacy.
- **R11–R16:** registro con la estructura existente vía `core.escribir_control`; fail-closed previo
  (request + allowlist); aprobación ligada al Change; consumo por el runtime real (E2E).
- **R17–R19:** `approve`, autonomous, `STOP_CATALOG`, `ExecutionRecord`, runtime de Change 2: sin
  cambios (`STOP_CATALOG` ausente del diff). Suite preexistente de exec sin editar y en verde.
- **R20:** `sdd.md` y `sdd.md.tmpl` documentan la vía concreta; `.ds_init/control.json` regenerado con
  `control.regenerar_control` (precedente `8a8d6ec`; 2 hashes actualizados); Doctor: 27 OK, 1 WARN
  (working tree con cambios sin confirmar), 0 ERROR, 1 N/A.

## Ejecuciones reales
- Dirigida (exec approve + exec preexistente): 1ª corrida 4 fallos (ver abajo); tras fix, **30 passed**.
- Regresión relevante (ds_guard exec/dependency/budgets/usuario/source/config/contract/integrity,
  autonomy_sdd, remediation, decision, harness_smoke, architecture_boundaries, manifest parity,
  leadrun/tests, autonomy/tests): **480 passed, 261 subtests passed**, 0 failed.

## Proceso de revisión (ciclo 1 de máximo 2)
- Fallos de la 1ª corrida dirigida (4): (a) `-h` de las formas sin la descripción → corregido en
  producción; (b) `legacy: True` en el dict `approval` rompía una suite preexistente que exige el dict
  exacto → se quitó (queda el aviso en stderr; R9b lo permitía); (c) y (d) supuestos erróneos del test
  (intérprete y texto de argparse) → corregidos.
- Reviewer: 0 bloqueantes. Importantes (cobertura de tests: ligadura de ruta/intérprete del hash v2,
  vectores fijos reales, casos de R9b, discriminación allowlist vs. error de builder, control.json
  byte a byte) → corregidos por el writer; re-test verde. No hizo falta ciclo 2.
- Observaciones menores aceptadas: el chequeo `leadrun_core is None` duplicado es inocuo; una
  excepción de `escribir_control` produce traceback igual que `cmd_approve` (paridad); aprobar un
  manifest de notebook autoriza `--execute` y `--dry-run` (el runtime siempre valida con `modo=
  "execute"`; R10).

## Límites y pendientes
- **Modelo de confianza:** declaración humana registrada bajo el trust model del harness; `exec
  approve` no distingue humano de agente (paridad con `approve`). Deuda v0.10: «Approval origin / human
  authorization authenticity» (`docs/roadmap/v0.10.md`).
- `exec` no fija el intérprete a `.venv` (preexistente): `exec approve` mantiene paridad y por lo tanto
  tampoco lo exige.
- F3: dos variantes de flags de pytest sobre las mismas rutas comparten artefacto y vale la última
  aprobada; el hash exacto diferencia la ejecución. Documentado.
- Aprobaciones legacy de script quedan reconocidas con aviso, sin migración automática.
- **Limitación del validator:** `ds_guard validate` evalúa `ALCANCE-RUTA` sobre TODO el working tree y
  no distingue archivos de otro Change abierto; con Change 0 (Cards) pausado y `.harmessi/` sin
  ignorar, reporta esos archivos como fuera de alcance de este Change. Se verificó que todos los
  hallazgos corresponden a (i) archivos de Change 0 (en su `rutas_autorizadas`) o (ii) evidencia de
  ejecuciones en `.harmessi/` (no versionada); ningún archivo ajeno a esos conjuntos aparece. No se
  falseó el scope. Las `rutas_autorizadas` de este Change se editaron en `control.json` porque `ds_guard`
  no ofrece un comando para ampliarlas (limitación operativa documentada, no corregida aquí).

## Resultado final
Corrective Change completo. `exec approve` registra y `exec` consume la misma identidad de ejecución.
