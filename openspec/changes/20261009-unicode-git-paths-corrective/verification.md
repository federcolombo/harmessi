# Verificación — 20261009-unicode-git-paths-corrective

## Resumen
Corrective intermedio de v0.10 (entre Change 1 y Change 2, sin renumerar), severidad alta. SDD abreviado aprobado por hash (proposal `a94ecf3bfc45c4701e23d94f2b3c61af476fc86be5f851d7d0286cf28418c7b1`; alcance materializado: 12 rutas) bajo la autorización anticipada del usuario en el pedido del Corrective (flujo autónomo). Implementado por 3 instancias de `python-data-engineer` con ownership disjunto (A: `tools/dsguard/repo.py` + `test_git_name_status_z.py`; B: `scope.py`, `dsimpact/git_source.py` + `test_git_paths_unicode_consumers.py`; C: `docs/roadmap/v0.10.md`). El Lead no escribió código; transiciones solo con `ds_guard transition`.

## Root cause (reproducido)
Con `core.quotepath=true` (default), `git diff --name-status -M` entrega rutas con comillas y escapes octales. `scope.py::archivos_tocados_desde_baseline` las parseaba con `split("\n")`/`split("\t")` sin `-z` y comparaba el texto escapado contra `alcance.rutas_autorizadas`, generando `ALCANCE-RUTA` falso (quotepath=true: falso positivo; false: 0). Mismo patrón en `dsimpact/git_source.py::listar_cambios`.

## Callers auditados
- Ya `-z`: `repo.list_dirty_files`, `git_source` `ls-files -z`.
- Solo display/truthiness: `repo.diff_check`, `ds_guard.py` `ls-files --`, `ds_init/preflight.py` y `harmessi/doctor.py` `status --porcelain`; `dsguard/notebooks.py` pasa la ruta como argumento.
- Vulnerables (corregidos): `scope.py` y `dsimpact/git_source.py`.
- Sin otros consumidores.

## Qué entrega
- Primitive en `tools/dsguard/repo.py`: `GitOutputError(ValueError)`, `GitCommandError(GitOutputError)` (returncode != 0), `parse_name_status_z` y `diff_name_status(repo_root, *args)`.
- `parse_name_status_z`: función pura sobre `git diff --name-status -z -M`. A/M/D/T/U/X/B un campo; R<nn>/C<nn> tres campos (origen→destino). Valida el código de estado completo con `fullmatch([AMDTUXB]|[RC]\d{1,3})`. Ante estado inválido, registro truncado o ruta vacía lanza `GitOutputError`, nunca resultado parcial.
- `scope.py` usa `diff_name_status`: baseline vacío, `GitCommandError` y excepciones de ejecución → `[]` (degradación silenciosa existente, no ampliada); salida ilegible → `GitIlegibleError` → `Finding` fail-closed `ALCANCE-GIT-ILEGIBLE`. El matching de alcance no cambió.
- `git_source.listar_cambios` mapea `GitOutputError` a `GitSourceError` y conserva R→renamed(old_path), C→added, A/M/D, otros→modified.
- Encoding: salida `-z` UTF-8 decodificada con `_git` (`errors="replace"`: byte inválido→U+FFFD, no coincide con alcance de ruta exacta); sin normalización NFC/NFD. No se toca `core.quotepath`, pathguard ni allowlist.

## Evidencia obtenida
- Tests dirigidos iniciales: 62 OK.
- Tras fixes del reviewer, lote scope/Unicode/boundaries/smoke roadmap/SDD (`test_git_name_status_z`, `test_git_paths_unicode_consumers`, `test_scope`, `test_operational_scope`, `test_architecture_boundaries`, `test_v09_release_hardening_smoke`, `test_autonomy_sdd`, `test_checks`): 177 OK.
- `tools/dsimpact/tests` completo: 68 OK.
- Cobertura: quotepath forzado true y false, `tamaño.txt`, `información.md`, `datos_área/ficha.txt`, `mi archivo.txt`, rename Unicode→Unicode, A/M/D, ASCII, parseo puro con tab/newline, malformados, ref inválida, U+FFFD.
- Reproducción end-to-end sin mocks tras el fix (repo temporal; `referencias/tamaño_iqr/f.txt` autorizada y `otra_área.txt` no autorizada): resultado idéntico con quotepath true y false (solo la no autorizada da `ALCANCE-RUTA`).
- Sin full regression, sin Cards/governance/ds_profile (pedido del usuario).
- Reviewer: 1 de 2 ciclos usados. 0 blockers/altos. 3 medios corregidos (M1 parser aceptaba cualquier campo que empezara con letra de estado → ahora fullmatch; M2 `scope.py` duplicaba el comando git → ahora usa `diff_name_status` con `GitCommandError`; M3 `\r` en nombres POSIX alterado por `text=True` → documentado como limitación preexistente). Bajos corregidos: docstring de `evaluar_alcance`, mensaje redundante en `git_source`, tests de U+FFFD/rc≠0/`gpgsign`. No se corrió un segundo ciclo (fixes mecánicos cubiertos por tests y por la reproducción end-to-end).

## Archivos modificados
`tools/dsguard/repo.py`, `tools/dsguard/scope.py`, `tools/dsimpact/git_source.py`, `docs/roadmap/v0.10.md`; tests nuevos `tools/tests/test_git_name_status_z.py`, `tools/tests/test_git_paths_unicode_consumers.py`.

## Fingerprint de dataset/artefacto
No aplica (sin datasets).

## Diferencias contra la spec
Ninguna registrada.

## Limitaciones
- `list_dirty_files` no verifica returncode.
- `scope` traga toda `Exception` como degradación silenciosa.
- Para R/C, scope evalúa solo el lado nuevo.
- `_git` usa `text=True`: un `\r` en nombres POSIX se altera.
- Refs que empiezan con `-` sin `--`.
- `dsimpact.git_source` importa `dsguard.repo` (objeto de módulo distinto de `tools.dsguard.repo`); sus tests parchean vía `git_source.repo_mod`.
- Sin full regression.

## Pendientes derivados
- Documentar `ALCANCE-GIT-ILEGIBLE` en `verificador.md` y su plantilla (fuera del alcance de este corrective).
- Deuda de las Limitaciones registrada en el roadmap, sin implementar.
- Fuera de alcance mantenido: pathguard (f2), recovery/allowlist (h), default de sesión (m), ledger (l/f4), turn limits, config de Git.
- Cierre, transiciones y commit local pendientes del Lead (sin push).

## Resultado final
Corrective verificado con las pruebas relevantes indicadas; sin hallazgos abiertos del reviewer. Cierre pendiente del Lead.
