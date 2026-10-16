# Diseño — 20261016-v011-git-scope-fail-closed

- **D1.** El chequeo de returncode vive en una sola función (`_git_ok`/check dentro de `repo.py`) que levanta `GitCommandError`; las funciones públicas la usan. No se agrega framework.
- **D2.** `_git` captura bytes y decodifica a mano (`utf-8`, `replace`) construyendo un `CompletedProcess` con `str`: contrato hacia afuera sin cambios, sin traducción de `\r\n`.
- **D3.** Rename → ambas rutas en `list_dirty_files` y en `archivos_tocados_desde_baseline` (lista deduplicada). Copy → solo destino.
- **D4.** Validación de refs: helper `validar_ref(ref)` que rechaza vacío o `-` inicial; `diff <ref> --`, `rev-parse --verify <ref>` (con `--end-of-options` no se usa por compatibilidad con Git viejos).
- **D5.** `evaluar_alcance` captura `GitCommandError`, `GitIlegibleError`, `RuntimeError` y emite un único código `ALCANCE-GIT-ILEGIBLE` con el motivo; no se crea código nuevo.
- **D6.** `ds_guard.py`: los callers directos capturan `repo.GitOutputError`/`RuntimeError` → hallazgo y exit 3.
- **D7.** Evidence de reporting (`resolve_git_commit`) no cambia: `None` ya significa desconocido y no se presenta como limpio.
