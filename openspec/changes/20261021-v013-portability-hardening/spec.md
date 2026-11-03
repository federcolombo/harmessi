# Spec — 20261021-v013-portability-hardening

## A. dsimpact fail-closed (unknown ≠ empty)
**R1.** `git_source.contenido_before(repo_root, since, staged, path, *, status)` y `contenido_after(repo_root, staged, path, *, status)` reciben el `status` del cambio. Devuelven `None` **solo** cuando la ausencia es esperada: `before` con `status == added`; `after` con `status == deleted`. En cualquier otro caso, si el contenido no puede obtenerse (git no disponible, ref/blob ilegible, `returncode != 0`, archivo del working tree ausente/ilegible/permisos) lanzan `GitSourceError` con un mensaje claro y sin rutas absolutas.
**R2.** Para `renamed`, `before` lee `old_path`. Los llamadores (`scan.py`) pasan `status` y `old_path` correctos. La decodificación UTF-8 con reemplazo existente se conserva; un error de decodificación no cuenta como ausencia.
**R3.** `scan.py` no captura `GitSourceError` internamente (no la convierte en resultado vacío); la CLI de `dsimpact` la traduce a mensaje + el exit code ya definido para errores de uso de Git. Ningún camino reporta «0 consumidores» cuando el contenido necesario no pudo leerse.
**R4.** Tests: Git no disponible (PATH sin git simulado), ref válida con blob ausente en un `modified`, working tree con archivo ilegible/ausente en un `modified`, `added`/`deleted` siguen devolviendo `None`, `renamed` usa `old_path`; el caso feliz no cambia sus resultados. Reuso de `dsguard.repo`; sin capa Git nueva.

## B. Sección `## Skills cargados` duplicada
**R5.** `validar_referencias_skills(texto_tasks, existentes)` emite `SKILL-TRAZA-SECCION-DUPLICADA` si el encabezado exacto `## Skills cargados` aparece más de una vez como título real (no dentro de bloques de código ni de comentarios HTML). Hallazgo determinista, una vez por archivo, con mensaje que indica cuántas veces; **no** se fusionan secciones y las referencias se siguen leyendo de la primera.
**R6.** Backward compatibility: ningún `tasks.md` existente en `openspec/changes/` tiene la sección duplicada (verificado); `templates/tasks.md` y su mirror tienen exactamente una. Tests: 0, 1, 2, 3 ocurrencias; en code fence; en comentario HTML; encabezado con otro nivel (`###`) no cuenta.
**R7.** Docs actualizados (methodology/sdd y sus `.tmpl`, ARCHITECTURE): la sección duplicada produce hallazgo. Se mantiene la paridad md↔`.tmpl`.

## C. Portabilidad
**R8.** Las CLIs `harmessi_bench` y `providers.conformance` no lanzan `UnicodeEncodeError` con consola no UTF-8: antes de imprimir reconfiguran `stdout`/`stderr` con `errors="replace"` cuando `reconfigure` existe (best-effort, sin cambiar encoding si no es posible). Test con stream cp1252 simulado.
**R9.** `docs/portability.md`: tabla de auditoría (pathlib/paths, subprocess, encodings, finales de línea, shell, lookup de ejecutables, temp dirs, symlinks/junctions, consola, Git, variables de entorno) con hallazgo, acción tomada en v0.13 y estado (`resuelto` / `cubierto por test` / `deuda`), y la matriz honesta de validación: Windows = real (este host), Linux/macOS = contrato/CI sin ejecución observada.
**R10.** `test_v013_portability_audit.py`: análisis estático (AST/regex) de los módulos nuevos de v0.13 (`harmessi_bench/*`, `providers/conformance.py`, `datasources/conformance.py`, `dsimpact/git_source.py`): `open`/`read_text`/`write_text` de texto con `encoding=` explícito, sin `shell=True`, sin `os.system`, sin separadores de ruta hardcodeados en literales de ruta, sin `/tmp` ni `C:\`.
**R11.** `test_v013_portability_smoke.py` ejercita en el host real: directorios con espacios y Unicode (incluye normalización NFC/NFD del nombre), escritura/lectura con CRLF y LF (el `suite_hash` y `identity_hash` invariantes), temp dirs, subprocess (`sys.executable -c` con salida Unicode capturada como bytes), Git en un repo temporal con espacios/Unicode (commit, `get_head`, `is_tree_clean`, lectura `leer_en_commit`, `dsimpact` sobre un cambio real), y symlink/junction solo si el SO lo permite (skip explícito si no).

## D. CI
**R12.** `.github/workflows/portability-smoke.yml`: `on: push`/`pull_request`/`workflow_dispatch`; job con matriz `os: [ubuntu-latest, windows-latest, macos-latest]` y `python-version: ["3.12"]`; pasos: checkout, setup-python, instalar solo `pytest`, ejecutar una lista **acotada** de módulos de test de portabilidad/contrato (`harmessi_bench`, conformance, portability, ci workflow, skill contract) con `fail-fast: false`; permisos mínimos (`contents: read`); sin secretos ni tokens; sin la suite completa.
**R13.** `test_v013_ci_workflow.py` valida estructuralmente el workflow (los tres OS, un único Python, `permissions: contents: read`, sin `secrets.`, sin `pull_request_target`, las rutas de test citadas existen). No afirma ejecución remota.
**R14.** Documentación honesta: «Linux/macOS: no validados por ejecución en este release; el workflow existe y fue verificado estructuralmente».

## E. Boundaries
**R15.** Sin cambios a hooks, permisos, roles, settings ni guardrails. `dsguard.repo` no se modifica. Sin dependencias nuevas.

## Criterios de aceptación
- [ ] R1–R4 dsimpact. - [ ] R5–R7 sección duplicada. - [ ] R8–R11 portabilidad. - [ ] R12–R14 CI. - [ ] R15 boundaries.
- [ ] Tests de dsimpact, skill_contract/methodology, harmessi_bench, conformance, portabilidad y paridad md↔tmpl verdes.
