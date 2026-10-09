# Tareas — 20261009-unicode-git-paths-corrective

estado: cerrada

## Invocaciones planificadas
- Writer A: `tools/dsguard/repo.py` + `tools/tests/test_git_name_status_z.py` (primitive, su parseo y ejecución con git real).
- Writer B: `tools/dsguard/scope.py`, `tools/dsimpact/git_source.py` + `tools/tests/test_git_paths_unicode_consumers.py`; ajuste de `tools/tests/test_scope.py` / `tools/dsimpact/tests/test_git_source.py` solo si algún test existente lo requiere.
- Writer C: `docs/roadmap/v0.10.md`.
- Regla: un writer que necesite un archivo ajeno NO lo edita, lo devuelve al Lead. Ningún writer toca lifecycle, `estado:` ni control.json (transiciones solo con `ds_guard transition` del Lead).
- Reviewer `data-science-reviewer`: máximo 2 ciclos.
- Regresión relevante: scope, repo/git helpers, dsimpact git source, architecture boundaries, tests SDD de scope, tests Unicode nuevos. Sin full regression, sin Cards/governance/ds_profile.

## Tareas
- [ ] T0: aprobación por hash de la propuesta (autorización anticipada del usuario en el pedido del Corrective).
- [x] T1: primitive en `tools/dsguard/repo.py` (`GitOutputError`, `parse_name_status_z`, `diff_name_status`) y tests en `tools/tests/test_git_name_status_z.py` (Writer A).
- [x] T2: consumidores `scope.py` (con `ALCANCE-GIT-ILEGIBLE`) y `dsimpact/git_source.py`, con tests en `tools/tests/test_git_paths_unicode_consumers.py` (Writer B).
- [x] T3: registro del corrective en `docs/roadmap/v0.10.md` (Writer C).
- [x] T4: revisión con `data-science-reviewer` (máx. 2 ciclos) y correcciones.
- [x] T5: verificación de la regresión relevante, cierre y commit local. Sin push.

## Dependencias
- T2 depende de T1 (la primitive).
- T3 es independiente de T1 y T2.
- T4 depende de T1, T2 y T3.
- T5 depende de T4.

## Verificación
Detalle completo en `verification.md` de este Change.
- Root cause: con `core.quotepath=true`, `git diff --name-status -M` entrega rutas con comillas y escapes octales; `scope.py` y `dsimpact/git_source.py` las parseaban sin `-z` y comparaban el texto escapado contra el alcance, dando `ALCANCE-RUTA` falso.
- Primitive final en `tools/dsguard/repo.py`: `parse_name_status_z` (pura, valida estado con `fullmatch`, nunca resultado parcial), `diff_name_status`, `GitOutputError` y `GitCommandError`. `scope.py` falla cerrado con `ALCANCE-GIT-ILEGIBLE` ante salida ilegible; `git_source` mapea a `GitSourceError`.
- Tests: 62 OK iniciales; tras los fixes del reviewer, 177 OK (lote scope/Unicode/boundaries/smoke roadmap/SDD) y 68 OK (`tools/dsimpact/tests` completo). Sin full regression.
- Reproducción end-to-end sin mocks: resultado idéntico con quotepath true y false (solo la ruta no autorizada da `ALCANCE-RUTA`).
- Reviewer: 1 de 2 ciclos; 0 blockers/altos; 3 medios corregidos (fullmatch del parser, `scope` usa `diff_name_status`, limitación de `\r` documentada) y bajos corregidos.
- Deuda registrada en `docs/roadmap/v0.10.md`, sin implementar: `list_dirty_files` sin returncode, `scope` traga `Exception`, R/C evalúa solo el lado nuevo, `text=True` altera `\r`, documentar `ALCANCE-GIT-ILEGIBLE` en `verificador.md`, refs con `-` sin `--`.

## Próximo paso exacto
Aprobar la propuesta (T0) y lanzar los writers A, B y C.
