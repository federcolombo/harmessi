# Spec — 20260916-impact-preflight

## Requisitos

### R1 — Fuente del cambio (Git)
`tools/dsimpact/git_source.py` reusa `dsguard.repo._git` (helper genérico de subprocess ya
existente, con su propio allowlist de subcomandos que ya cubre `diff`/`show`/`rev-parse`/
`ls-files`) — NO se reimplementa un segundo wrapper de subprocess para Git (evitar la duplicación
que el brief prohíbe explícitamente). Nunca muta el repo (ningún subcomando de escritura).

- `validar_ref(repo_root, ref) -> bool`: `git rev-parse --verify <ref>` (mismo patrón que
  `dsguard.notebooks.obtener_revision`). Ref inválida → error técnico claro (nunca traceback
  crudo), exit code 1.
- `--since REF`: `git diff --name-status -M <REF>` — compara `REF` contra el working tree actual
  (incluye cambios staged y unstaged, semántica nativa de `git diff <commit>`). Contenido "after"
  se lee del filesystem real (no del índice), contenido "before" vía `git show <REF>:<path>`.
- `--staged`: `git diff --staged --name-status -M` — compara HEAD contra el índice. Contenido
  "after" vía `git show :<path>` (stage 0), contenido "before" vía `git show HEAD:<path>`.
- Parsing de `--name-status`: `A`/`M`/`D`/`Rxxx`/`Cxxx`/`T`. Renombres (`R`) llevan `old_path` y
  `new_path`; copias (`C`) se tratan como archivo nuevo en `new_path` (se documenta como límite:
  no se busca el origen de una copia). `T` (cambio de tipo) se trata como `M`.
- Universo de "consumidores candidatos": `git ls-files -z --cached --others --exclude-standard`
  (tracked + untracked-no-ignorados — respeta `.gitignore` automáticamente, sin mantener una lista
  de exclusiones propia por directorio). Filtrado después por extensión
  (`.py`,`.ipynb`,`.json`,`.yaml`,`.yml`,`.toml`,`.md`).

### R2 — Changed items: Python
`tools/dsimpact/py_changes.py`, vía `ast` (stdlib, `ast.unparse` — disponible desde Python 3.9,
igual al mínimo soportado del proyecto).

- Por archivo `.py` `A`/`M`/`D`/renombrado: parsear `before`/`after` (el lado ausente, `None`, para
  `A`/`D`).
- Símbolos de nivel módulo: `FunctionDef`/`AsyncFunctionDef`/`ClassDef` (por nombre) y asignaciones
  simples de nivel módulo (`Assign`/`AnnAssign` con target `Name`, por nombre). Comparar
  `ast.unparse(nodo)` entre `before`/`after`: agregado (solo en after), eliminado (solo en before),
  modificado (en ambos, unparse distinto). Los tres tipos son "changed items" válidos para buscar
  consumidores (un símbolo eliminado sigue siendo relevante: alguien puede seguir importándolo).
- Errores de parseo (`SyntaxError`) en `before`/`after`: no bloquean el scan completo — se reporta
  el archivo como "changed" sin símbolos extraídos, con una nota (`parse_error`), y se sigue con el
  resto del diff.

### R3 — Changed items: strings contractuales
Dentro de las MISMAS regiones ya identificadas como cambiadas en R2 (cuerpo de un símbolo
agregado/modificado, o valor de una asignación de nivel módulo agregada/modificada — nunca todo el
archivo), extraer `ast.Constant` de tipo `str` que aparezcan en posición estructural:
- elemento directo de `List`/`Tuple`/`Set`;
- key o value directo de `Dict`;
- RHS directo de una asignación (`Assign`/`AnnAssign`, nivel módulo o de clase);
- dentro del `test` de un `Assert`;
- operando de un `Compare` con `==`/`!=`/`in`/`not in`.

Nunca se extraen strings de docstrings, f-strings, argumentos de logging, ni literales sueltos
fuera de esas posiciones. Aplicar el filtro de tokens genéricos (R7) antes de convertir un string
en target de búsqueda.

### R4 — Changed items: archivos eliminados/renombrados
Para cada archivo eliminado o el `old_path` de un renombrado: el "changed item" es el path mismo
más el nombre de módulo Python derivado (`tools/features.py` → `tools.features`, solo para `.py`
bajo un prefijo importable simple — sin resolver `sys.path` real). Se busca por referencia al path
literal o al nombre de módulo derivado (ver R6, `PATH_REFERENCE`).

### R5 — Consumidores: Python (`.py`, y celdas de código de `.ipynb`)
`tools/dsimpact/consumers_py.py`, vía `ast`/`tokenize` sobre el archivo consumidor completo
(archivo entero, no solo un diff — un consumidor no tiene por qué estar en el mismo diff).

- Import: `ast.Import`/`ast.ImportFrom` que referencian el módulo derivado del changed file, o un
  changed symbol vía `from modulo import simbolo`.
- Referencia de símbolo: token `NAME` (vía `tokenize`, límites de palabra reales, nunca substring)
  igual al changed item, fuera de un import y fuera de un `assert`.
- Referencia dentro de `assert`: mismo match, pero el nodo más cercano en el AST es un `Assert`.
- String contract: literal de string (`ast.Constant` str, en cualquier posición del archivo
  consumidor — acá sí se busca en todo el archivo, no solo en posiciones estructurales, porque la
  posición estructural ya se exigió del lado del CAMBIO, no hace falta exigirla también del lado
  del consumo) que coincide exactamente con un string contract del diff.
- No se intenta resolver aliasing (`import x as y`), reflection, imports dinámicos, monkeypatching
  — si no se puede probar la relación con `ast`/`tokenize`, no se reporta (documentado como deuda
  aceptable).

### R6 — Categorías de evidencia (evidence_type)
Regla en 3 pasos (determinista, sin ambigüedad de prioridad):

**Paso 1 — tipo base, según cómo se parseó el archivo consumidor:**
- `.py`/celda de código `.ipynb`: `ASSERT_REFERENCE` si el match cae dentro de un `assert`;
  `IMPORT_REFERENCE` si cae dentro de una declaración de import; si no, `STRING_CONTRACT_REFERENCE`
  (match de string contract) o `SYMBOL_REFERENCE` (match de nombre) según corresponda.
- `.json`/`.yaml`/`.yml`/`.toml`: `CONFIG_REFERENCE` (JSON verificado estructuralmente vía
  `json.loads`; YAML/TOML por texto plano línea a línea, límite documentado en `design.md` §6).
- `.md`: `STRING_CONTRACT_REFERENCE` (solo se buscan strings contractuales y path-references en
  `.md` — nunca símbolos sueltos, demasiado ruidoso en prosa).

**Paso 2 — override por identidad del target:** si el changed item matcheado es específicamente un
path-reference (R4, path/nombre de módulo de un archivo eliminado/renombrado) y el tipo base del
paso 1 no es `ASSERT_REFERENCE`/`IMPORT_REFERENCE`, el `evidence_type` final es `PATH_REFERENCE`.

**Paso 3 — override por tipo de consumidor:** si el archivo consumidor es reconocible como test
(`test_*.py`, `*_test.py`, o bajo un directorio `tests/`/`test/`) y el `evidence_type` resultante de
los pasos 1-2 no es `ASSERT_REFERENCE`/`IMPORT_REFERENCE`/`PATH_REFERENCE`, el `evidence_type` final
es `TEST_REFERENCE`.

Para notebooks, la ubicación agrega el índice de celda (`archivo#cell:N` o campo `cell_index` en
JSON) — el tipo de evidencia sigue exactamente la misma regla de 3 pasos que un `.py`.

Para notebooks, el `evidence_type` sigue esta misma prioridad (una celda de código se trata como
código Python para R5/R6); la ubicación agrega el índice de celda (`archivo#cell:N` o campo
`cell_index` en JSON).

### R7 — Filtro de tokens genéricos
Denylist fija, corta, case-insensitive, de nombres/strings demasiado genéricos para disparar
búsqueda global (`id`, `name`, `date`, `value`, `data`, `index`, `key`, `type`, `path`, `file`,
`config`, `result`, `item`, `items`, `self`, `args`, `kwargs`, `true`, `false`, `none`) más un
mínimo de longitud (2 caracteres). Un changed item filtrado sigue apareciendo en la sección
`changed` del output (fue modificado), pero NUNCA dispara búsqueda de consumidores. Documentado
como limitación explícita (no exhaustivo, ajustable a futuro).

### R8 — Notebooks
`tools/dsimpact/notebooks_source.py` reusa `dsguard.notebooks.parsear_notebook_texto` (JSON parse
con manejo de error ya resuelto) para leer `.ipynb` — nunca ejecuta el notebook, nunca analiza
`outputs`. Extrae `source` de celdas `cell_type == "code"` (unidas en un único texto por celda,
mismo criterio que `_fuente_a_texto` de `dsguard.notebooks` — sin reimportar esa función privada,
replicar la lógica de una línea localmente). Markdown de celdas se ignora en v1 (documentado, no
aporta valor claro para v1 vs. el costo de otro camino de parseo). Notebook con JSON inválido: se
excluye del scan como consumidor con una nota, sin abortar el scan completo (mismo criterio de
`R2` para `.py` con `SyntaxError`).

### R9 — CLI
- `python -m tools.dsimpact scan --since REF [--json]`
- `python -m tools.dsimpact scan --staged [--json]`
- `--since`/`--staged` mutuamente excluyentes, exactamente uno requerido.
- Wrapper fino `python -m tools.ds_guard impact scan --since REF [--json]` /
  `... --staged [--json]`, delegando a la MISMA función de `tools.dsimpact` (import directo, sin
  reimplementar el CLI). Único punto de implementación canónica: `tools/dsimpact/`.
- Exit codes: `0` scan exitoso (con o sin findings), `1` error técnico (repo inválido, ref
  inválida, uso incorrecto de flags). Findings nunca cambian el exit code.
- Output humano: compacto, agrupado por `Changed:` (archivo → símbolos/strings) y
  `Potentially affected:` (consumidor → evidence_type → changed_item, con ubicación), cerrando con
  `Summary: N potentially affected consumers` (nunca "N broken consumers").
- `--json`: `{"since": str|null, "staged": bool, "changed": [...], "findings": [...], "summary":
  {...}}`, determinista, serializable, sin timestamps, paths repo-relative siempre.

### R10 — Determinismo / dedup
Mismo diff + mismo estado de repo → mismo output byte a byte (salvo que el propio repo cambie
entre corridas, lo cual es inherente a cualquier scan de filesystem). Orden estable:
`source_changed` → `changed_item` → `consumer` → `location`. Dedup de findings equivalentes
(mismos 4 campos clave). Sin timestamps en el JSON.

### R11 — Read-only
`dsimpact scan` (ambos CLI, `dsimpact` y el wrapper de `ds_guard`) nunca escribe: working tree,
SDD, lifecycle, `project.json`, `control.json`, notebooks, decision ledger, evidence,
`scientific-policy.json`. Verificado byte a byte en tests (mismo patrón que Change 0,
`dsguard.core.capturar_bytes`).

### R12 — Manifest / install
`tools/dsimpact/*` (VERBATIM, `stage_minimo="experiment"` — el valor principal aparece durante
desarrollo/modelado activo, no en discovery liviano de viabilidad). `ds_guard.py` en sí mismo es
`stage_minimo="discovery"` y se instala siempre — por eso el import de `tools.dsimpact` desde
`ds_guard.py` NO puede ser incondicional a nivel de módulo (rompería `ds_guard.py` entero con
`ImportError` en cualquier instalación todavía en discovery, el mismo bug de la clase de regresión
que ya cubre `test_manifest_dsguard_parity.py`). Resolución: el subcomando `impact scan` usa
**import perezoso opcional**, mismo patrón ya establecido en `tools/dsguard/status.py`
(`_importar_doctor`/`_importar_legacy`: probar `from dsimpact import cli as dsimpact_cli` y
`from tools.dsimpact import cli as dsimpact_cli` como fallback, nunca un import a nivel de módulo).
Si no está disponible, `cmd_impact_scan` imprime un mensaje claro ("impact preflight no está
instalado en este stage -- correr 'ds_init sync --stage experiment --execute'") y devuelve exit
code `3` (error de entorno/herramienta, mismo vocabulario que el resto de `ds_guard.py`). El
subparser `impact` en sí SIEMPRE existe en el árbol de argparse (no depende de si el paquete está
instalado) -- solo la ejecución real depende de la disponibilidad del paquete.

## Criterios de aceptación
- [ ] `scan --since HEAD~1` sobre un repo temporal con un commit que modifica una función y un
      commit siguiente que la consume en un test → 1 finding `TEST_REFERENCE` (o `ASSERT_REFERENCE`
      si hay un `assert` con esa función).
- [ ] Constante/lista modificada consumida por una celda de notebook → finding con `cell_index`.
- [ ] String contract modificado (ej. nombre de columna en una lista) consumido por un `.py` y un
      `.json` → 2 findings, uno `STRING_CONTRACT_REFERENCE`, uno `CONFIG_REFERENCE`.
- [ ] Token genérico (`id`, `name`) modificado → aparece en `changed`, cero findings de consumidor.
- [ ] Archivo eliminado → `PATH_REFERENCE` en cualquier consumidor que lo importe/mencione.
- [ ] Ref inválida → exit 1, mensaje claro, sin traceback.
- [ ] Repo sin diff (`--since HEAD`) → `changed: []`, `findings: []`, exit 0.
- [ ] `--staged` con índice vacío → mismo comportamiento, exit 0.
- [ ] Read-only: `git status`/bytes de archivos de estado idénticos antes/después.
- [ ] Determinismo: dos corridas seguidas sobre el mismo estado → mismo JSON.
- [ ] `ds_guard impact scan` produce exactamente el mismo resultado que `python -m tools.dsimpact
      scan` con los mismos flags (delegación real, no reimplementación).
- [ ] Suite completa (`tools/tests`, `tools/dsimpact/tests`, `tools/ds_init/tests`,
      `tools/harmessi/tests`) pasa; `check_manifest_parity` y `harmessi doctor` sin errores nuevos.

## Cutoff / information boundary
No aplica (no hay dataset propio de este cambio).

## Baseline (condicional — modeling)
No aplica (no hay modelo involucrado).
