# Spec — 20261008-cross-platform-managed-hashing

Change 1 de v0.10: Cross-platform Managed Hashing (solo deuda A: falsos `HARMESSI-DRIFT` por LF/CRLF). Este Change es audit + SDD; no incluye implementación. Los requisitos describen el contrato que verificará el Change de implementación.

Contexto verificado del código actual:
- `tools/ds_init/control.py::sha256_de_archivo` hashea bytes crudos.
- `generar_control` y `regenerar_control` (usados por `writer.instalar` y por `sync` en `tools/ds_init/cli.py`) y `tools/harmessi/doctor.py::_check_hashes_drift` consumen `.ds_init/control.json` -> `archivos[].sha256` (hex plano; sin `schema_version`).
- `hash_lf_v1` (`sha256/lf/v1`, `tools/dsguard/core.py`) ya es EOL-agnóstico y sirve a aprobaciones, ApprovalRef y checkpoints: NO se toca.
- Convención existente de ids de algoritmo: `sha256/lf/v1`, `sha256/bin/v1`.
- Los 134 entries del manifest actual son texto (.py/.md/.json).
- `sync` hoy rehashea todos los managed (hallazgo F-1: oculta modificaciones); la sección G lo reemplaza por un modo conservador.
- `_check_hashes_drift` invoca la comparación semántica de guardrails solo cuando el hash difiere.

## A. Primitive única de hash managed (R1-R4)
**R1.** Existe un único módulo `tools/ds_init/managed_hash.py`, solo stdlib, que expone `hash_managed_file(path, algoritmo)`. Lee en streaming por bloques; nunca carga el archivo entero en memoria.
**R2.** Constantes de algoritmo:
- `sha256/eol-lf/v1` (texto): opera sobre bytes, sin decodificar. Convierte CRLF -> LF y luego CR solitario -> LF. No quita BOM; no toca espacios, tabs, trailing whitespace, orden de claves JSON, Unicode ni mayúsculas/minúsculas. Maneja correctamente un `\r` al final de un bloque cuyo `\n` llega en el bloque siguiente (el resultado no depende del tamaño de bloque).
- `sha256/bin/v1` (binario): bytes exactos.
**R3.** Función de verificación de una entrada de baseline que devuelve uno de: `ok` | `ok_legacy` (verifica por la vía legacy, migrable) | `drift` | `algoritmo_desconocido`. `algoritmo_desconocido` es fail-closed: se trata como drift/ERROR explícito, nunca como `ok`.
**R4.** Instalador, `regenerar_control`, Doctor y migración usan SOLO esta primitive. `sha256_de_archivo` puede quedar como wrapper/alias de compatibilidad si hace falta, sin duplicar lógica.

## B. Tipo de contenido (R5-R7)
**R5.** `EntradaManifiesto` incorpora el campo `contenido` con valores `texto` (por defecto) | `binario`. Sin heurísticas de decodificación.
**R6.** El algoritmo se elige exclusivamente por `contenido`: `texto` -> `sha256/eol-lf/v1`; `binario` -> `sha256/bin/v1`.
**R7.** Un test de paridad exige que las extensiones típicamente binarias (png, ico, zip, whl, pdf, parquet, pyc, etc.) declaren `binario` en el manifest.

## C. Formato de control.json (R8-R11)
**R8.** Cada entrada nueva de `archivos[]` lleva `hash_alg`. La ausencia de `hash_alg` significa legacy (bytes crudos).
**R9.** Lectura backward-compatible: un `control.json` legacy se lee sin error y sin modificarse.
**R10.** La escritura es determinista y sale únicamente del planner/control oficial (`generar_control` / `regenerar_control`); nunca a mano.
**R11.** Sin bump de `schema_version` ni de versión del harness en este Change. Las claves existentes quedan inalteradas (`hash_alg` es aditiva).

## D. Verificación legacy (estrategia A) (R12-R13)
**R12.** Una entrada sin `hash_alg` verifica (`ok_legacy`) si su `sha256` coincide con alguno de:
1. el hash crudo del archivo actual;
2. el hash crudo de la forma LF-canónica del archivo actual;
3. el hash crudo de la forma CRLF (LF-canónico con `\n` -> `\r\n`).
**R13.** Cualquier otro caso es `drift` real, incluidos archivos de EOL mixto cuyo baseline no corresponde a ninguna de las tres formas. No se acepta ninguna modificación de contenido. Legacy acepta SOLO diferencias de EOL (crudo, forma LF o forma CRLF); limitación documentada: baselines históricos de EOL mixto no verifican; sin heurísticas adicionales.

## E. Doctor (R14-R19)
**R14.** Entrada nueva (con `hash_alg`): Doctor compara con el algoritmo declarado.
**R15.** Una diferencia solo de EOL no genera drift. Un cambio real sí lo genera: `hello\nWORLD\n` vs `hello\nworld\n`, whitespace, trailing space, tab.
**R16.** Entrada legacy migrable (`ok_legacy`): reporte informativo (no WARN) con acción sugerida (comando de migración).
**R17.** Algoritmo desconocido: fail-closed (ERROR explícito).
**R18.** Guardrails: sin cambios en la lógica semántica (closed-list `RUTAS_MUTABLES`); la comparación semántica solo se evalúa cuando el hash canónico difiere.
**R19.** Cobertura de tests: EOL no agrega falso drift a `.claude/guardrails.json`; una customización no soportada sigue siendo drift.

## F. Migración (R20-R26)
**R20.** Subcomando `migrate-hashes` de `ds_init` (ver R46/R49) que convierte SOLO entradas legacy que verifican (R12) al algoritmo nuevo, recomputando sobre el contenido actual.
**R21.** Entradas que no verifican se dejan intactas y se reportan; el drift persiste.
**R22.** Dry-run por defecto; `--execute` explícito.
**R23.** Determinista e idempotente: una segunda corrida no produce cambios.
**R24.** Sin edición manual de `control.json`.
**R25.** Sin rehash silencioso de contenido modificado.
**R26.** Migración de algoritmo != re-adopción de guardrails: no comparten código ni semántica.

## G. `sync` (R27-R35b) — decisión M-A aprobada
Principio: `sync` reconcilia, NO adopta; sync never adopts pre-existing drift. El subcomando `sync` clasifica ANTES de escribir, contra el baseline ANTERIOR (nunca contra hashes ya regenerados), cada entrada en: pristine (`ok`) / legacy verificable por EOL (`ok_legacy`) / drift real (incluye `algoritmo_desconocido`, fail-closed) / entrada nueva (sin entrada previa).
**R27.** Pristine + asset distribuido distinto: se actualiza el archivo (journal con backup y rollback) y se registra el hash del NUEVO contenido con el algoritmo vigente. Si el contenido distribuido es idéntico al actual, no se escribe (`sin_cambios`).
**R27b.** Legacy verificado: la entrada migra al algoritmo vigente (y el archivo se actualiza si corresponde, como en R27).
**R27c.** Drift: el archivo NO se reescribe; la entrada del baseline se conserva TAL CUAL (sin rehash); mensaje accionable por entrada; Doctor sigue reportando el drift. `sync` no oculta la modificación (cierra el hallazgo F-1).
**R27d.** Archivo existente sin entrada previa: no se adopta (se omite como hoy), salvo que su contenido coincida con el distribuido (algoritmo vigente), en cuyo caso se registra.
**R27e.** Entradas de merge (`.claude/settings.json`, `CLAUDE.md` con `--integrar-claude`): el merge se sigue aplicando por necesidad funcional; el baseline se actualiza solo si el previo era pristine o no existía; si había drift se conserva la entrada previa.
**R27f.** `control.json` nunca queda sin las entradas conservadas durante `sync`: la escritura de control del instalador recibe las entradas conservadas (`entradas_conservadas`), también tras reintento por fallo parcial.
**R28.** `regenerar_control` explícito conserva su semántica de rebaseline total (con el algoritmo nuevo) como primitive de mantenimiento. `sync` lo usa solo en modo conservador vía el parámetro `clasificacion`, sin renombrar APIs públicas ni cambiar sus defaults.
**R28b.** Separación: migración de hash != managed upgrade != re-adopción (Change 3). Ningún camino mezcla las tres semánticas.

## G2. API de contrato (R45-R49)
Fijada aquí para implementación en paralelo por los writers.
**R45.** `tools/ds_init/managed_hash.py`: `ALG_TEXTO="sha256/eol-lf/v1"`, `ALG_BINARIO="sha256/bin/v1"`, `CONTENIDO_TEXTO`, `CONTENIDO_BINARIO`, `ESTADO_OK`, `ESTADO_OK_LEGACY`, `ESTADO_DRIFT`, `ESTADO_ALG_DESCONOCIDO`, `algoritmo_para_contenido(contenido)`, `hash_managed_file(ruta, algoritmo, bloque=65536)`, `hash_crudo_file(ruta)`, `verificar_entrada(ruta, entrada, bloque=65536) -> (estado, detalle)`.
**R46.** `control`: `generar_control(..., entradas_conservadas=None)` escribe entradas `{ruta, sha256, hash_alg}`; `clasificar_baseline(destino, control_previo) -> dict[ruta -> {"estado", "entrada"}]`; `regenerar_control(..., clasificacion=None, resultado=None)` (con `clasificacion` -> modo conservador); `migrar_hashes(destino, *, ejecutar=False) -> InformeMigracion` con campos `migradas`, `ya_actuales`, `no_verificables`, `desconocidas`; escribe `control.json` determinista solo con `ejecutar=True`.
**R47.** `manifest`: campo `contenido` (`texto` por defecto) en `EntradaManifiesto` y helper `contenido_de(ruta)`.
**R48.** `planner`: `ACCION_ACTUALIZAR_MANAGED`; `construir_plan(..., clasificacion=None)`; con `None` el comportamiento es idéntico al actual.
**R49.** `writer`: `ResultadoInstalacion` suma `actualizados` y `sin_cambios` (listas, default vacío). `cli`: subcomando `migrate-hashes [--execute]` (dry-run por defecto) y `sync` conservador.

## H. Instalación fresca cross-platform (R29-R31)
**R29.** Un fixture construye bytes LF y CRLF explícitos (sin depender de `core.autocrlf` del host) para los archivos textuales.
**R30.** Ambas instalaciones producen los mismos hashes managed para los archivos textuales y Doctor no reporta falso drift en ninguna.
**R31.** Regeneración estable: dos corridas consecutivas producen el mismo resultado.

## I. Frontera y no-regresión (R32-R37)
**R32.** `hash_lf_v1`, ApprovalRef, checkpoints `@approved`, pins de Cards/EvidenceRef, SourceObservation, DataContract, reporting y `ds_profile` NO cambian; sus tests existentes siguen verdes sin modificarse.
**R33.** `tools/ds_init/managed_hash.py` usa solo stdlib y respeta `test_architecture_boundaries.py`.
**R34.** Sin regresión en installer, sync, adoption, capability filtering y drift de guardrails.
**R35.** Un proyecto sin diferencias de EOL mantiene comportamiento equivalente.
**R36.** Harmessi no gestiona ni sobrescribe `.gitattributes`.
**R37.** Sin nuevas dependencias.

## J. Tests mínimos (R38-R43)
Todos construidos con bytes explícitos.
**R38.** Hash canónico: LF, CRLF, CR; igualdad lógica; cambio real; whitespace/trailing/tab distinto; EOL mixto; archivo vacío; sin newline final; CRLF partido entre bloques.
**R39.** Binario: bytes distintos -> hash distinto; sin normalización accidental; `\r\n` binario != `\n`.
**R40.** Legacy: lectura de control legacy; migración segura; archivo legacy modificado NO se acepta; migración determinista e idempotente; entrada con `hash_alg` desconocido fail-closed.
**R41.** Instalador/Doctor: fresh LF, fresh CRLF, OK en ambos, drift real detectado, regeneración estable.
**R42.** Guardrails (R19).
**R43.** Hashes de aprobación intactos (`hash_lf_v1` sin cambios).
**R43b.** Tests adicionales M-A:
- legacy pristine: baseline legacy LF + checkout CRLF equivalente -> verificable, migrable, sin drift;
- legacy modificado: cambio real de texto -> NO migrable, el drift permanece;
- current pristine + upgrade: baseline v1 pristine + nueva versión distribuida -> `sync` actualiza y el hash nuevo corresponde al contenido distribuido;
- current drift + sync: baseline v1 + modificación del usuario + `sync` -> sin rebaseline silencioso; la modificación no aparece como pristine después;
- EOL-only current difference: sin drift;
- cambio real de whitespace/trailing/tab: drift;
- merge con drift previo conserva la entrada previa;
- archivo existente sin entrada no se adopta;
- `control.json` conserva las entradas durante `sync`;
- los tests existentes que comparaban `sha256` contra el hash crudo se actualizan para usar `verificar_entrada`.

## K. Verificación del Change de implementación (R44)
**R44.** Tests dirigidos por writer, reviewer, una regresión global, Doctor sin ERROR, `git diff --check` y revisión de privacidad.

## Fuera de alcance explícito
- Cambiar `hash_lf_v1`, aprobaciones, ApprovalRef, checkpoints, pins de Cards/EvidenceRef.
- Pins byte-exact de evidencia versionada bajo autocrlf (hallazgo F-2; candidato futuro).
- Re-adopción de guardrails y enmiendas de alcance (Change 3).
- Gestionar o escribir `.gitattributes`.
- Hash AST/semántico, normalización de whitespace/Unicode, detección heurística de binarios.
- Bump de `schema_version` o de versión del harness; regeneración de `control.json` de este repo (Change 6).
- Implementación en este Change.

## Criterios de aceptación
- [ ] R1-R7: primitive única, algoritmos y `contenido` especificados sin ambigüedad.
- [ ] R8-R13: formato de control y verificación legacy especificados; modificaciones reales nunca aceptadas.
- [ ] R14-R19: comportamiento de Doctor y guardrails especificado.
- [ ] R20-R28b, R45-R49: migración, `sync` conservador (M-A aprobada) y API de contrato especificados.
- [ ] R29-R37: fixture cross-platform y fronteras de no-regresión especificados.
- [ ] R38-R44: tests mínimos y verificación del Change de implementación listados.
- [ ] Sin código funcional modificado en este Change; sin nombres de proyectos reales, rutas personales ni emails.

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
