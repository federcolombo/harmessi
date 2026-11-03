# Proceso de release (runbook)

Runbook paso a paso para publicar una versión `X.Y.Z` de Harmessi desde un checkout. Está derivado de lo
hecho en los releases anteriores (`docs/releases/v0.14.0.md`, `docs/roadmap/v0.15.md` §C7) y del código
actual. No es una automatización: no hay un script de release; cada paso lo ejecuta una persona.

Convenciones de este documento: `X.Y.Z` es la versión a publicar; `<tag_anterior>` es el tag publicado
previo (por ejemplo `v0.14.0` para publicar `v0.15.0`); `<proyecto>` es un proyecto instalado o el propio
checkout, según el paso.

## 1. Precondiciones

- Estás en la rama de desarrollo del release (por ejemplo `v0.15-dev`), no en `main`.
- Working tree limpio: `git status` sin cambios sin commitear. Los archivos no versionados que no
  forman parte del release deben quedar fuera del commit o descartarse a propósito.
- Todos los Changes del release están cerrados según su `tasks.md`/`control.json` (el cierre lo decide el
  Lead y el usuario; este runbook no lo altera).
- Python y `pytest` disponibles en el entorno del checkout (`.venv`).
- Hay un tag anterior publicado contra el que se compara (`git tag --list`).

## 2. Subir `HARNESS_VERSION`

- Editar `tools/ds_init/version.py` (`HARNESS_VERSION`) a `X.Y.Z`.
- Los releases anteriores también actualizaron `CITATION.cff` (ver `docs/roadmap/v0.10.md`); si el archivo
  existe, verificar que su versión coincide. Verificarlo antes de asumirlo.
- Revisar `docs/versioning.md` por si cambia algún schema o ventana de compatibilidad.

## 3. Notas de release

- Crear `docs/releases/vX.Y.Z.md` (en inglés, como las anteriores). Estructura observada en
  `docs/releases/v0.14.0.md`:
  1. Título y párrafo introductorio (qué es la versión, qué no hace, qué se validó y qué no).
  2. `What's included`, con subsecciones por capacidad.
  3. `What vX.Y does NOT do`.
  4. `Compatibility and upgrading`, con el origen de upgrade soportado (el tag anterior) y los pasos
     `python -m tools.ds_init upgrade --destino <project>` (dry run), luego `--execute`, y `recover` si
     se interrumpe.
  5. `Known limitations`: cada límite debe ser algo observado; lo inferido se declara como inferido.
  6. `Deferred`: dirección sin contrato.
- No incluir rutas personales, emails ni números que no salgan de una corrida.

## 4. Regresión completa SERIAL

- Ejecutar `python -m pytest -q tools` (todos los tests bajo `tools`) en un único proceso a la vez, nunca en
  paralelo entre sí.
- La suite completa es larga (decenas de minutos). Por presión de memoria se corre en lotes en background
  (por ejemplo por subdirectorio o por archivo de test), uno tras otro, y se guarda la salida de cada lote.
- Registrar en el ledger del release, por lote: comando, resultado (pasados/fallidos/omitidos) y fecha. Los
  números de las notas salen de esa salida, nunca de memoria.
- Cualquier fallo se resuelve (o se clasifica con aprobación explícita) antes de seguir. No se continúa el
  release con un fallo no explicado.

## 5. Fixtures de compatibilidad (solo si cambió un schema)

Solo si el release cambia un contrato versionado o el baseline. Los generadores son solo-checkout (no se
instalan en proyectos ni los corre la suite normal) y generan con el código del tag, no con el checkout
actual:

1. Exportar el árbol del tag anterior a un directorio nuevo y vacío **fuera del repo**:
   `git archive <tag_anterior> --prefix=tree/ -o <tar_fuera_del_repo>` y extraer con
   `--strip-components=1` en `<dir_tree>` (o `git archive <tag_anterior> | tar -x -C <dir_tree>`).
2. Contratos `harmessi_improve`:
   `python tools/tests/fixtures/compat/generate_v014.py --tree <dir_tree> --out tools/tests/fixtures/compat/v0_14`
3. Data Card v1: `python tools/tests/fixtures/compat/generate_datacard_v014.py --tree <dir_tree> --out tools/tests/fixtures/compat/v0_14`
   (`--tree` y `--out` son ambos obligatorios; el generador está escrito para `v0.14.0`, para otro tag
   usar el directorio de salida que corresponda; ver el
   docstring del script para su destino y para el chequeo de `HARNESS_VERSION` del árbol).
4. Los scripts actuales están escritos para `v0.14.0`; para otro tag se necesita un generador nuevo
   (o adaptar el existente) y se aborta si el árbol importado no corresponde al tag. Los sha256 del
   `MANIFEST.json` son específicos de la corrida que los generó.
5. Los fixtures baseline de `.ds_init/control.json` de tags anteriores se obtienen con
   `git show <tag>:.ds_init/control.json` (ver `docs/versioning.md`).
6. Revisar el diff de los fixtures y correr los tests de compatibilidad que los consumen.

## 6. Doctor

- `python -m tools.harmessi doctor --destino <proyecto>` sobre un proyecto instalado con la versión nueva
  (y sobre el checkout, si corresponde). Debe terminar con **0 ERROR** (exit 0). Preferible 0 WARN;
  cada WARN se explica en la evidencia del release.
- Doctor solo diagnostica: no escribe ni repara.

## 7. Baseline de hashes managed (una sola vez)

- El baseline es `.ds_init/control.json` (hashes de los archivos administrados). Se actualiza **una vez** por
  release, al final, cuando el contenido administrado ya no cambia; regenerarlo en medio del release
  obliga a repetirlo.
- Estado real del mecanismo: no se encontró en este repo un comando dedicado "regenerar baseline del
  checkout". En los releases anteriores se regeneró con la API `control.regenerar_control(...)`
  (`tools/ds_init/control.py`) sobre el árbol final (ver `docs/roadmap/v0.10.md`: se regeneró sobre el
  árbol ya mergeado en `main`, porque `checkout`/`merge` pueden normalizar fin de línea y cambiar los
  bytes). `python -m tools.ds_init migrate-hashes [--execute]` (dry run por defecto) migra el contrato de
  hash de un baseline, pero no está verificado aquí como sustituto de la regeneración.
  Decidir y registrar el procedimiento exacto antes de ejecutarlo.
- Tras regenerar, correr Doctor (paso 6) y confirmar que no aparece `HARMESSI-DRIFT` sobre archivos
  administrados. Si el merge a `main` (paso 10) cambia bytes (fin de línea), repetir la verificación.

## 8. Barrido de privacidad

- `python -m pytest -q tools/tests/test_privacy_sweep.py`.
- Revisar además a mano las notas nuevas y los docs: sin rutas personales, emails ni identificadores de
  usuario.

## 9. Matriz de readiness v1

- Evaluar los criterios literales de `docs/roadmap/v1.0.md` con estados `PASS` / `PARTIAL` / `FAIL` /
  `ACCEPTED LIMITATION`, cada uno con evidencia (archivo, test o salida de corrida).
- Publicar la matriz junto al release. El release no declara v1.0 salvo decisión explícita del usuario.

## 10. Merge, tag y push

Solo con los pasos 1 a 9 completos y la aprobación explícita del usuario:

1. `git checkout main` y `git merge <rama_de_desarrollo>`.
2. Tag anotado, con mensaje `Harmessi vX.Y.Z`: `git tag -a vX.Y.Z -m "Harmessi vX.Y.Z"` (el nombre del
   tag `vX.Y.Z` es el que usan los generadores de fixtures, p. ej. `v0.14.0`).
3. `git push origin main` y `git push origin vX.Y.Z`.

El push publica el contenido: confirmarlo con el usuario antes de ejecutarlo.

## 11. CI remoto

- El workflow `.github/workflows/portability-smoke.yml` corre en `push`, `pull_request` y
  `workflow_dispatch`, con `actions/checkout@v5`, `actions/setup-python@v6`, `ubuntu-latest`,
  `windows-latest`, `macos-latest` y Python 3.12, sobre una lista acotada de tests (no la suite completa).
- Tras el push, abrir las ejecuciones del workflow para el commit y el tag, y registrar por sistema
  operativo: resultado, fecha y advertencias (por ejemplo de deprecación de acciones).
- Mientras no se haya observado, el estado es **pending observation**. No se afirma que CI pasa.
- La matriz no incluye Python 3.9, aunque el mínimo declarado es 3.9: ese mínimo no está cubierto por CI.

## 12. GitHub Release

- Acción manual del usuario: en el entorno de desarrollo no hay `gh`. Crear el Release desde la interfaz
  web de GitHub sobre el tag `vX.Y.Z`, usando `docs/releases/vX.Y.Z.md` como cuerpo.

## Checklist final

- [ ] Rama correcta, working tree limpio
- [ ] `HARNESS_VERSION` = `X.Y.Z` (y `CITATION.cff` si existe)
- [ ] `docs/releases/vX.Y.Z.md` creado, números tomados de la corrida
- [ ] Regresión completa serial en lotes, sin fallos sin explicar, ledger guardado
- [ ] Fixtures de compat regenerados (solo si cambió un schema) con `git archive` fuera del repo
- [ ] Doctor con 0 ERROR
- [ ] Baseline managed regenerado una sola vez y Doctor sin `HARMESSI-DRIFT`
- [ ] Barrido de privacidad (`tools/tests/test_privacy_sweep.py`) y revisión manual
- [ ] Matriz de readiness v1 publicada
- [ ] Merge a `main`, tag anotado `Harmessi vX.Y.Z`, push (con aprobación)
- [ ] CI remoto observado y registrado (o declarado `pending observation`)
- [ ] GitHub Release creado manualmente por el usuario

## Estado de observación

Estado tras publicar v1.0.0 (actualizado el 2026-11-03): Python 3.12 es el verificado (CI en
ubuntu, windows y macos, lista acotada de tests, observado GREEN sobre `5f4a0ca`) y 3.9 queda como mínimo declarado no ejecutado; el
GitHub Release de v1.0.0 es un paso manual; el baseline se regenera una sola vez, al final, tras
congelar el contenido managed (incluido `HARMESSI-LICENSE.txt`). El resto de la tabla se redactó en
v0.15 (2026-10-26) y no se reobservó:

| Elemento | Estado |
|---|---|
| CI remoto `portability-smoke` (checkout@v5, setup-python@v6) | Observado en success sobre el commit de v0.15.0 (`7e7c681`, 2026-10-30) y, post-release, sobre el push a `main` y el tag `v1.0.0` (commit `5f4a0ca`) |
| Compatibilidad de las acciones checkout@v5 / setup-python@v6 | Observada en esas corridas |
| Linux y macOS | Observados en success (Python 3.12, lista acotada); no la suite completa |
| Python 3.9 (mínimo declarado) | No está en la matriz de CI |
| Procedimiento de regeneración del baseline | Sin comando dedicado verificado (ver paso 7) |
| GitHub Release | Pendiente, acción manual (sin `gh`) |
| Este runbook | Derivado de la lectura del código y de releases previos; no fue ejecutado de punta a punta |
