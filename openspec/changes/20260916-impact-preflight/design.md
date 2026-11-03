# Design — 20260916-impact-preflight

## 1. Por qué `tools/dsimpact/` reusa `dsguard.repo._git` directamente (en vez de replicarlo)

Auditoría: `tools/dsguard/repo.py` ya tiene un wrapper de subprocess genérico (`_git`, con su
propio allowlist de subcomandos: `rev-parse`/`status`/`diff`/`show`/`log`/`ls-files`/`mv`) usado
intra-paquete por `kdd.py`/`sdd.py`/`notebooks.py` (`notebooks.py` lo importa como
`from . import repo as repo_mod` y llama `repo_mod._git(...)` directamente pese a ser privado).
A diferencia de `pathguard._matchea_patrones`/`_excepcion_vigente` (domain logic con riesgo real de
drift semántico si se replica mal, por eso Change 0 los replicó localmente en vez de importarlos),
`_git` es un wrapper de subprocess genérico sin lógica de dominio -- replicarlo sería duplicar
exactamente el tipo de "utilidad de Git" que el brief pide reusar, no una decisión de negocio.
`dsimpact` importa `from dsguard import repo as repo_mod` (mismo patrón de dependencia
unidireccional que `ds_profile -> dsguard`) y llama `repo_mod._git(...)` con los subcomandos ya
permitidos (`diff`, `show`, `rev-parse`, `ls-files`) -- cero cambios en `repo.py`.

## 2. Por qué no hay un segundo motor de "changed items" para Python vs. notebooks

Una celda de código de notebook se trata como texto Python normal para R5/R6 (mismo `ast`/
`tokenize` sobre el `source` de la celda) -- la única diferencia real es de dónde viene el texto
(`.py` completo vs. `source` de una celda) y qué ubicación se reporta (línea vs. índice de celda).
No se escribe una segunda implementación de detección de referencias para notebooks.

## 3. Por qué la extracción de string contracts es asimétrica (estructural del lado del cambio,
   libre del lado del consumidor)

Del lado del CAMBIO, exigir posición estructural (lista/dict/assert/comparación/asignación) es lo
que evita que cualquier palabra de un diff se convierta en "contrato" (brief §5C, explícito: "NO
considerar cualquier palabra de texto como contrato"). Del lado del CONSUMIDOR, una vez que ya se
decidió que un string específico es un contrato real (superó el filtro estructural + el filtro de
tokens genéricos), buscarlo en cualquier posición del archivo consumidor es razonable y no relaja
el criterio de falsos positivos -- el string ya pasó el filtro fuerte antes de convertirse en
target de búsqueda.

## 4. Por qué `import dsimpact` en `ds_guard.py` debe ser perezoso

`tools/dsimpact/` se instala desde `stage_minimo="experiment"` (preferencia explícita del brief:
"el valor principal aparece durante desarrollo/modelado", y "discovery debe seguir sin componentes
innecesarios"). `ds_guard.py` se instala siempre desde discovery. Si `ds_guard.py` importara
`dsimpact` a nivel de módulo (como hace con el resto de `dsguard.*`), cualquier instalación en
discovery rompería `ds_guard.py` COMPLETO con `ImportError` al primer uso -- exactamente la clase
de regresión que ya cubre `test_manifest_dsguard_parity.py` (hallazgo B1 de la auditoría de release
v0.2.0, `decision.py` sin entrada de manifest). Se usa el patrón ya establecido en
`tools/dsguard/status.py` (`_importar_doctor`/`_importar_legacy`, import perezoso opcional, nunca a
nivel de archivo) -- primer `import dsimpact` real recién dentro de `cmd_impact_scan`, con
`ImportError` traducido a un mensaje claro + exit 3, nunca un traceback crudo.

## 5. Por qué `python -m tools.dsimpact scan` es la implementación canónica, no `ds_guard.py`

`tools/dsimpact/cli.py` contiene el parser/lógica completa (`argparse`, subcomando `scan`).
`ds_guard.py` (`impact scan`) es un wrapper de una función: arma el mismo `argparse.Namespace`
(o llama directamente a la función interna que ya recibe argumentos ya parseados,
`dsimpact.cli.ejecutar_scan(repo_root, since, staged, como_json) -> (payload, exit_code)`) y
imprime/retorna lo mismo. Ningún camino reimplementa la extracción de changed items ni la búsqueda
de consumidores dos veces.

## 6. Por qué no hay parser real de YAML/TOML

`tomllib` es stdlib recién desde Python 3.11; el proyecto soporta desde 3.9 (`CORE-PYTHON-VERSION`
de `harmessi doctor`). No hay parser YAML en stdlib bajo ninguna versión. Agregar PyYAML o
`tomli`/`tomllib`-backport sería una dependencia externa nueva, prohibida explícitamente para v1.
Se tratan como texto plano con matching conservador (mismo filtro de tokens genéricos que el resto)
-- documentado como límite conocido, no como intento fallido de ser exhaustivo.

## 7. Por qué el filtro de tokens genéricos es una denylist fija, no un umbral estadístico

Un umbral basado en frecuencia (p. ej. "aparece en más de N archivos, descartar") requeriría un
primer pase de conteo global sobre todo el repo antes de poder filtrar nada -- más costoso y menos
predecible que una lista fija y corta, explícita, documentada, ajustable a mano. Coherente con
"preferir stdlib, preferir simple" y con que v1 es deliberadamente conservador, no exhaustivo.

## 8. Riesgos aceptados / límites conocidos (además de los ya declarados en `proposal.md`)

- No se resuelve aliasing de import (`import x as y`), reflection, imports dinámicos, ni
  monkeypatching -- si `ast`/`tokenize` no puede probar la relación, no se reporta (falso negativo
  aceptado, preferido sobre inventar certeza).
- Un símbolo/string cuyo nombre coincide por casualidad con algo no relacionado en otro archivo
  genera un falso positivo -- aceptado explícitamente por el brief ("preferir algunos falsos
  positivos razonables antes que inventar certeza"), mitigado por el filtro de tokens genéricos
  (§7) y por reportar SIEMPRE "potentially affected", nunca una afirmación de ruptura real.
- Copias (`C` de `git diff --name-status`) se tratan como archivo nuevo sin rastrear su origen --
  caso raro, documentado, no se resuelve en v1.
- `dsimpact` no sabe nada de `openspec/changes/<id>/control.json`/SDD todavía (puede leerse a mano
  si el Lead lo necesita, pero no hay integración automática -- eso es Change 2, Scope & Change
  Isolation).
