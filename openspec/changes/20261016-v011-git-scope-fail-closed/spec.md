# Spec — 20261016-v011-git-scope-fail-closed

**R1.** `list_dirty_files`, `get_head`, `diff_check`, `is_tree_clean` y `files_out_of_scope` lanzan `GitCommandError` si Git responde con returncode ≠ 0; Git ausente sigue lanzando `RuntimeError`. Nunca devuelven `[]`/limpio/cadena vacía por un fallo.
**R2.** `archivos_tocados_desde_baseline` solo devuelve `[]` si `baseline_commit` es vacío/None; ref inválida/borrada → `GitCommandError` propagado; salida malformada → `GitIlegibleError` (sin cambios).
**R3.** `scope.evaluar_alcance` emite `ALCANCE-GIT-ILEGIBLE` (fail-closed) ante cualquier fallo de Git (comando, ausencia, salida ilegible) y no lanza.
**R4.** Rename (`R`): se evalúan ambas rutas (origen y destino). Copy (`C`): se evalúa el destino (el origen no se modifica). Aplica a working tree y a diff desde baseline.
**R5.** Una ref que empieza con `-` se rechaza (`GitCommandError`); las refs de `diff`/`show`/`rev-parse` llevan `--` donde corresponde.
**R6.** `_git` no aplica universal newlines: un `\r` en un nombre de archivo se preserva. Decodificación UTF-8 con `errors="replace"` (sin cambio).
**R7.** Los callers en `ds_guard.py` (status, validate, archive, init, notebook-diff) convierten el fallo de Git en hallazgo/mensaje y exit 3 (error de entorno/git) en vez de traceback; `resolve_git_commit` conserva su contrato «nunca lanza» (`(None, None)` = desconocido).
**R8.** `verificador.md` y su plantilla documentan `ALCANCE-GIT-ILEGIBLE` incluyendo los nuevos orígenes.
**R9.** Tests: fallo de comando, Git no disponible, Unicode, espacios, rename autorizado→no autorizado y viceversa, copy, salida malformada, regresión ASCII, ref con `-`, `\r` en nombre (si el FS lo permite).
**R10.** Sin cambios de comportamiento ante Git sano; la suite existente de scope/repo sigue verde (tests que fijaban fail-open se actualizan y se documentan).

## Criterios de aceptación
- [ ] R1–R3 R7 verificados por tests.
- [ ] R4–R6 verificados por tests.
- [ ] R8 docs. R10 regresión relevante verde.
