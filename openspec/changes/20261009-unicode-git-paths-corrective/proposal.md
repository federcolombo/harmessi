# Propuesta — 20261009-unicode-git-paths-corrective

Corrective intermedio de v0.10 entre Change 1 y Change 2 (sin renumerar): «Git paths Unicode independientes de core.quotepath». Severidad: alta.

## Problema
Con `core.quotepath=true` (default de Git), `git diff --name-status -M` entrega rutas con comillas y escapes octales (por ejemplo `"referencias/tama\303\261o_iqr/f.txt"`). `tools/dsguard/scope.py::archivos_tocados_desde_baseline` las parsea con `split("\n")` y `split("\t")` sin `-z`, y `evaluar_alcance` compara el texto escapado contra `alcance.rutas_autorizadas`, lo que produce un `ALCANCE-RUTA` falso. El mismo patrón existe en `tools/dsimpact/git_source.py::listar_cambios`, que usa la ruta parseada para `git show ref:path` y fallaría. Hallazgo de uso real contra Harmessi 0.8; vigente en v0.10-dev.

## Objetivo
Que toda ruta Git interpretada por el harness (scope y dsimpact) se lea de salida `-z` y sea independiente de `core.quotepath`.

## Evidencia
- Reproducido en un repo temporal: `core.quotepath=true` produce 1 hallazgo falso; `core.quotepath=false` produce 0.
- `tools/dsguard/scope.py::archivos_tocados_desde_baseline` (l.33): parseo sin `-z`.
- `tools/dsimpact/git_source.py::listar_cambios` (l.49): usa la ruta parseada para `git show ref:path`.
- Audit de callers de Git que interpretan rutas:
  - A (ya `-z` correcto): `tools/dsguard/repo.py::list_dirty_files` (`status --porcelain=v1 -z`) y `tools/dsimpact/git_source.py` (`ls-files -z`).
  - B (parsea salida humana solo para mostrar o testear vacío): `repo.diff_check` (`diff --check`), `ds_guard.py` ~l.3672 (`ls-files -- <ruta>`, solo truthiness), `ds_init/preflight.py` y `harmessi/doctor.py` (`status --porcelain`, conteo/listado informativo). `dsguard/notebooks.py` pasa la ruta como argumento (`git show rev:ruta`), no la parsea.
  - C (vulnerables): `scope.py` y `dsimpact/git_source.py::listar_cambios`. No hay otros consumidores reales.
- Semántica verificada de `git diff --name-status -z -M`: registros `X\0ruta\0` para A/M/D/T; renombres y copias `R100\0vieja\0nueva\0` / `C100\0origen\0destino\0` (tres campos). La salida es UTF-8, también en Windows. Un tab no es válido en nombres de archivo de Windows: se cubre con la función de parseo pura.

## Supuestos descartados
- Que `core.quotepath` fuera irrelevante para las rutas no ASCII: con el default de Git rompe la comparación de alcance.
- Que todos los callers de Git sufrieran el problema: solo los de categoría C lo sufren; A ya usa `-z` y B no interpreta rutas.

## Alcance
- Primitive de parseo y ejecución de `diff --name-status -z -M` en `tools/dsguard/repo.py`.
- Uso de la primitive en `tools/dsguard/scope.py` y `tools/dsimpact/git_source.py`.
- Tests nuevos y ajustes mínimos a tests existentes de scope y git_source.
- Registro mínimo en `docs/roadmap/v0.10.md` como corrective intermedio entre Change 1 y Change 2 (motivo, severidad alta, bug, estado), sin renumerar ni tocar contenidos congelados.

## Fuera de alcance
pathguard, allowlist, f2 (scratchpad), h (recovery), m (session default), l/f4 (ledger), turn limits, cambios de config de Git, Cards, governance, ds_profile, `docs/feedback/` (no trackeado, no citar). Tampoco los callers B ni la normalización Unicode del filesystem.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Tests en repos temporales que fuerzan `core.quotepath=true` y también `false`, con el mismo resultado funcional:
1. Rutas `tamaño.txt`, `información.md`, directorio Unicode (`datos_área/ficha.txt`), espacios (`mi archivo.txt`), rename Unicode→Unicode, y A/M/D.
2. Parseo puro con tab y saltos de línea en nombres; casos malformados (estado desconocido, registro truncado, rename con un solo campo) lanzan `GitOutputError`.
3. Scope: Unicode autorizado no emite `ALCANCE-RUTA`; Unicode NO autorizado emite `ALCANCE-RUTA`; salida malformada emite `ALCANCE-GIT-ILEGIBLE` (nunca se considera autorizado).
4. dsimpact: `listar_cambios` correcto con `quotepath=true` para Unicode y rename.
5. Regresión ASCII.
6. Siguen verdes los tests existentes de `tools/tests/test_scope.py` y `tools/dsimpact/tests/test_git_source.py`, y `tools/tests/test_architecture_boundaries.py`.
7. Registro del corrective en `docs/roadmap/v0.10.md`.

## Decisión técnica (design-lite — solo SDD abreviado)
1. Primitive pequeña en la capa Git existente `tools/dsguard/repo.py`:
   - `parse_name_status_z(salida: str) -> list[tuple[str, str, Optional[str]]]`: función pura; cada tupla es `(codigo, ruta_nueva, ruta_vieja_o_None)`. Lanza `GitOutputError` ante estado desconocido, campos faltantes o registro truncado.
   - `GitOutputError`: nueva excepción, subclase de `ValueError`, definida en `repo.py`.
   - `diff_name_status(repo_root, *args) -> list`: ejecuta `git diff --name-status -z -M <args>` y devuelve lo anterior; lanza `GitOutputError` ante returncode != 0 con stderr.
   - `_git` conserva su decodificación `utf-8` con `errors="replace"`. Contrato explícito: la salida `-z` de Git es UTF-8; no se normaliza Unicode NFC/NFD; un byte inválido produce U+FFFD y la ruta no coincide con ningún alcance (falla cerrado).
2. `scope.py::archivos_tocados_desde_baseline` usa la primitive. Se conserva la degradación silenciosa EXISTENTE solo para baseline ausente, ref inválida o comando fallido (decisión previa documentada). Un error de PARSEO (`GitOutputError` por salida malformada) NO se trata como «sin archivos»: `evaluar_alcance` emite un `Finding` fail-closed `ALCANCE-GIT-ILEGIBLE` (código nuevo; el scope no se considera satisfecho). El matching de alcance no cambia ni se vuelve permisivo.
3. `dsimpact/git_source.py::listar_cambios` usa la primitive y mapea `GitOutputError` a `GitSourceError`. Conserva el mapeo de estados: R→renamed con old_path, C→added, A/M/D, T y otros→modified.
4. NO se toca `core.quotepath` de ningún usuario ni de install, ni pathguard, ni allowlist, ni los callers B.
5. No se resuelve la normalización Unicode del filesystem.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado
- `tools/dsguard/repo.py`
- `tools/dsguard/scope.py`
- `tools/dsimpact/git_source.py`
- `tools/tests/test_git_name_status_z.py`
- `tools/tests/test_git_paths_unicode_consumers.py`
- `tools/tests/test_scope.py`
- `tools/dsimpact/tests/test_git_source.py`
- `docs/roadmap/v0.10.md`

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
