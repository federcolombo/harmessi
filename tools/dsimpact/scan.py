"""Orquestador de Impact Preflight (R9/R10/R11, v0.4 Change 1): junta
`git_source`/`py_changes`/`consumers_py`/`consumers_text`/`notebooks_source`/
`generic_filter`, dedup/ordena, y arma el resultado final -- SIEMPRE de solo
lectura, SIEMPRE vocabulario "potentially affected" (nunca "roto").

Nota de diseño (decisión de implementación, documentada acá porque no está
100% explícita en `spec.md`): para consumidores `.py`/`.ipynb`, los
path-reference targets (path literal y, si aplica, nombre de módulo derivado
de un archivo eliminado/renombrado) se buscan como parte del conjunto de
STRINGS de ese source (no como símbolos sueltos vía `tokenize` -- un nombre de
módulo con puntos, p. ej. `tools.features`, no tokeniza como un único NAME).
Esto es consistente con R6 paso 2 (override a `PATH_REFERENCE` cuando el
`changed_item` matcheado es un path-reference target), y con el criterio
general de R5 de no inventar resolución de imports que `ast`/`tokenize` no
puedan probar directamente.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import consumers_py, consumers_text, generic_filter, git_source, notebooks_source, py_changes
from .git_source import GitSourceError

EXTENSIONES_JSON = (".json",)
EXTENSIONES_TEXTO_CONFIG = (".yaml", ".yml", ".toml")
EXTENSIONES_MD = (".md",)


# --- Helpers de clasificación -------------------------------------------------

def _es_archivo_test(path: str) -> bool:
    """`test_*.py`, `*_test.py`, o bajo un directorio `tests/`/`test/` (R6
    paso 3)."""
    partes = path.split("/")
    nombre = partes[-1]
    if nombre.startswith("test_") and nombre.endswith(".py"):
        return True
    if nombre.endswith("_test.py"):
        return True
    if any(p in ("tests", "test") for p in partes[:-1]):
        return True
    return False


def _evidence_type(tipo_base: str, changed_item: str, targets_path: set, consumer_path: str) -> str:
    """Regla de 3 pasos EXACTA de `spec.md` R6."""
    tipo = tipo_base
    if changed_item in targets_path and tipo_base not in ("ASSERT_REFERENCE", "IMPORT_REFERENCE"):
        tipo = "PATH_REFERENCE"
    if _es_archivo_test(consumer_path) and tipo not in ("ASSERT_REFERENCE", "IMPORT_REFERENCE", "PATH_REFERENCE"):
        tipo = "TEST_REFERENCE"
    return tipo


# --- Extracción de changed items por archivo ----------------------------------

def _procesar_py(repo_root: Path, since: Optional[str], staged: bool, cambio) -> dict:
    """Devuelve un dict "fuente" con `changed_entry`, `targets_simbolos`,
    `targets_strings`, `targets_path` (siempre vacío acá -- solo
    deleted/renamed generan path-reference targets)."""
    texto_antes = None if cambio.status == git_source.STATUS_ADDED else git_source.contenido_before(
        repo_root, since, staged, cambio.path
    )
    texto_despues = git_source.contenido_after(repo_root, staged, cambio.path)

    simbolos, parse_error = py_changes.diff_simbolos(texto_antes, texto_despues)
    strings = set() if parse_error else py_changes.strings_contractuales(texto_despues, simbolos)

    targets_simbolos = {s.nombre for s in simbolos if not generic_filter.es_generico(s.nombre)}
    targets_strings = {s for s in strings if not generic_filter.es_generico(s)}

    return {
        "path": cambio.path,
        "status": cambio.status,
        "old_path": cambio.old_path,
        "changed_entry": {
            "path": cambio.path,
            "status": cambio.status,
            "old_path": cambio.old_path,
            "symbols": [{"name": s.nombre, "kind": s.tipo, "change": s.cambio} for s in simbolos],
            "string_contracts": sorted(strings),
            "parse_error": parse_error,
        },
        "targets_simbolos": targets_simbolos,
        "targets_strings": targets_strings,
        "targets_path": set(),
    }


def _simbolos_celda_cambiada(texto_celda: str, cambio_celda: str) -> list:
    """Trata el código de una celda de notebook como mini-módulo Python:
    símbolos/constantes de nivel superior de ESA celda, envuelto en
    try/except `SyntaxError` (celdas con código no parseable como módulo
    completo -- `!pip install`, magics de IPython -- se saltan sin error)."""
    import ast

    try:
        arbol = ast.parse(texto_celda)
    except SyntaxError:
        return []
    simbolos_dict = py_changes._simbolos_nivel_modulo(arbol)
    return [
        py_changes.SimboloCambiado(nombre, tipo, cambio_celda)
        for nombre, (tipo, _nodo) in simbolos_dict.items()
    ]


def _procesar_notebook(repo_root: Path, since: Optional[str], staged: bool, cambio) -> dict:
    texto_antes = None if cambio.status == git_source.STATUS_ADDED else git_source.contenido_before(
        repo_root, since, staged, cambio.path
    )
    texto_despues = git_source.contenido_after(repo_root, staged, cambio.path)

    parse_error = False
    celdas_antes: list = []
    celdas_despues: list = []

    if texto_antes is not None:
        celdas_antes, error_antes = notebooks_source.celdas_codigo(texto_antes, f"antes:{cambio.path}")
        parse_error = parse_error or error_antes
    if texto_despues is not None:
        celdas_despues, error_despues = notebooks_source.celdas_codigo(texto_despues, cambio.path)
        parse_error = parse_error or error_despues
    else:
        parse_error = True

    simbolos_totales: list = []
    if not parse_error:
        indice_antes = dict(celdas_antes)
        for indice, texto_celda in celdas_despues:
            texto_previo = indice_antes.get(indice)
            if texto_previo == texto_celda:
                continue
            cambio_celda = "agregado" if texto_previo is None else "modificado"
            simbolos_totales.extend(_simbolos_celda_cambiada(texto_celda, cambio_celda))

    targets_simbolos = {s.nombre for s in simbolos_totales if not generic_filter.es_generico(s.nombre)}

    return {
        "path": cambio.path,
        "status": cambio.status,
        "old_path": cambio.old_path,
        "changed_entry": {
            "path": cambio.path,
            "status": cambio.status,
            "old_path": cambio.old_path,
            "symbols": [{"name": s.nombre, "kind": s.tipo, "change": s.cambio} for s in simbolos_totales],
            "string_contracts": [],
            "parse_error": parse_error,
        },
        "targets_simbolos": targets_simbolos,
        "targets_strings": set(),
        "targets_path": set(),
    }


def _procesar_eliminado_o_renombrado(cambio) -> dict:
    origen = cambio.path if cambio.status == git_source.STATUS_DELETED else cambio.old_path
    targets_path_crudos = {origen}
    if origen and origen.endswith(".py"):
        modulo = py_changes.derivar_nombre_modulo(origen)
        if modulo:
            targets_path_crudos.add(modulo)
    # R7 aplica también a los path-reference targets de R4 -- el path literal
    # completo (con "/" y extensión) rara vez es genérico, pero el nombre de
    # módulo derivado corto (p. ej. "data.py" -> "data") sí puede coincidir
    # con la denylist.
    targets_path = {t for t in targets_path_crudos if not generic_filter.es_generico(t)}
    return {
        "path": cambio.path,
        "status": cambio.status,
        "old_path": cambio.old_path,
        "changed_entry": {
            "path": cambio.path,
            "status": cambio.status,
            "old_path": cambio.old_path,
            "symbols": [],
            "string_contracts": [],
            "parse_error": False,
        },
        "targets_simbolos": set(),
        "targets_strings": set(),
        "targets_path": targets_path,
    }


def _procesar_otro(cambio) -> dict:
    """Cualquier archivo agregado/modificado que no sea `.py`/`.ipynb` --
    fuera de alcance de R2/R3, se reporta en `changed` sin targets."""
    return {
        "path": cambio.path,
        "status": cambio.status,
        "old_path": cambio.old_path,
        "changed_entry": {
            "path": cambio.path,
            "status": cambio.status,
            "old_path": cambio.old_path,
            "symbols": [],
            "string_contracts": [],
            "parse_error": False,
        },
        "targets_simbolos": set(),
        "targets_strings": set(),
        "targets_path": set(),
    }


def _construir_fuente(repo_root: Path, since: Optional[str], staged: bool, cambio) -> dict:
    """Nunca lanza -- un error de parseo puntual se degrada con gracia
    (`_procesar_otro` como último resguardo)."""
    try:
        if cambio.status in (git_source.STATUS_DELETED, git_source.STATUS_RENAMED):
            return _procesar_eliminado_o_renombrado(cambio)
        if cambio.path.endswith(".py"):
            return _procesar_py(repo_root, since, staged, cambio)
        if cambio.path.endswith(".ipynb"):
            return _procesar_notebook(repo_root, since, staged, cambio)
        return _procesar_otro(cambio)
    except Exception:  # noqa: BLE001 - degradación con gracia, nunca aborta el scan
        return _procesar_otro(cambio)


# --- Búsqueda de consumidores --------------------------------------------------

def _buscar_en_candidato_py(texto: str, fuente: dict) -> list:
    targets_simbolos = fuente["targets_simbolos"]
    targets_strings = fuente["targets_strings"] | fuente["targets_path"]
    if not targets_simbolos and not targets_strings:
        return []
    return consumers_py.buscar_en_texto_python(texto, targets_simbolos, targets_strings)


def _buscar_en_candidato_notebook(repo_root: Path, candidato: str, fuente: dict) -> list:
    ruta_abs = repo_root / candidato
    if not ruta_abs.exists():
        return []
    texto = ruta_abs.read_text(encoding="utf-8", errors="replace")
    celdas, error = notebooks_source.celdas_codigo(texto, candidato)
    if error:
        return []
    resultados = []
    for indice, texto_celda in celdas:
        matches = _buscar_en_candidato_py(texto_celda, fuente)
        for m in matches:
            m = dict(m)
            m["cell_index"] = indice
            resultados.append(m)
    return resultados


def _buscar_en_candidato_json(texto: str, fuente: dict) -> list:
    targets = fuente["targets_simbolos"] | fuente["targets_strings"] | fuente["targets_path"]
    if not targets:
        return []
    return consumers_text.buscar_en_json(texto, targets)


def _buscar_en_candidato_texto_plano_config(texto: str, fuente: dict) -> list:
    targets = fuente["targets_simbolos"] | fuente["targets_strings"] | fuente["targets_path"]
    if not targets:
        return []
    return consumers_text.buscar_en_texto_plano(texto, targets)


def _buscar_en_candidato_md(texto: str, fuente: dict) -> list:
    targets = fuente["targets_strings"] | fuente["targets_path"]
    if not targets:
        return []
    return consumers_text.buscar_en_texto_plano(texto, targets)


def _location_py(consumer: str, linea: int) -> str:
    return f"{consumer}:{linea}"


def _location_notebook(consumer: str, cell_index: int, linea: Optional[int] = None) -> str:
    if linea is not None:
        return f"{consumer}#cell:{cell_index}:{linea}"
    return f"{consumer}#cell:{cell_index}"


def _mensaje(changed_item: str, evidence_type: str, consumer: str) -> str:
    return f"'{changed_item}' referenciada en {consumer} ({evidence_type.lower()})"


def _findings_para_candidato(repo_root: Path, candidato: str, fuente: dict) -> list:
    """Nunca lanza -- un archivo consumidor con error de parseo/lectura se
    omite sin abortar el resto del scan."""
    if candidato == fuente["path"]:
        return []

    ext = candidato.lower()
    findings: list = []
    try:
        if ext.endswith(".py"):
            ruta_abs = repo_root / candidato
            if not ruta_abs.exists():
                return []
            texto = ruta_abs.read_text(encoding="utf-8", errors="replace")
            for m in _buscar_en_candidato_py(texto, fuente):
                evidence_type = _evidence_type(m["tipo_base"], m["changed_item"], fuente["targets_path"], candidato)
                findings.append({
                    "source_changed": fuente["path"],
                    "changed_item": m["changed_item"],
                    "consumer": candidato,
                    "evidence_type": evidence_type,
                    "location": _location_py(candidato, m["linea"]),
                    "evidence": m["fragmento"],
                    "message": _mensaje(m["changed_item"], evidence_type, candidato),
                })
        elif ext.endswith(".ipynb"):
            for m in _buscar_en_candidato_notebook(repo_root, candidato, fuente):
                evidence_type = _evidence_type(m["tipo_base"], m["changed_item"], fuente["targets_path"], candidato)
                findings.append({
                    "source_changed": fuente["path"],
                    "changed_item": m["changed_item"],
                    "consumer": candidato,
                    "evidence_type": evidence_type,
                    "location": _location_notebook(candidato, m["cell_index"], m["linea"]),
                    "evidence": m["fragmento"],
                    "message": _mensaje(m["changed_item"], evidence_type, candidato),
                })
        elif ext.endswith(".json"):
            ruta_abs = repo_root / candidato
            if not ruta_abs.exists():
                return []
            texto = ruta_abs.read_text(encoding="utf-8", errors="replace")
            for m in _buscar_en_candidato_json(texto, fuente):
                evidence_type = _evidence_type("CONFIG_REFERENCE", m["changed_item"], fuente["targets_path"], candidato)
                findings.append({
                    "source_changed": fuente["path"],
                    "changed_item": m["changed_item"],
                    "consumer": candidato,
                    "evidence_type": evidence_type,
                    "location": candidato,
                    "evidence": m["fragmento"],
                    "message": _mensaje(m["changed_item"], evidence_type, candidato),
                })
        elif ext.endswith((".yaml", ".yml", ".toml")):
            ruta_abs = repo_root / candidato
            if not ruta_abs.exists():
                return []
            texto = ruta_abs.read_text(encoding="utf-8", errors="replace")
            for m in _buscar_en_candidato_texto_plano_config(texto, fuente):
                evidence_type = _evidence_type("CONFIG_REFERENCE", m["changed_item"], fuente["targets_path"], candidato)
                findings.append({
                    "source_changed": fuente["path"],
                    "changed_item": m["changed_item"],
                    "consumer": candidato,
                    "evidence_type": evidence_type,
                    "location": f"{candidato}:{m['linea']}",
                    "evidence": m["fragmento"],
                    "message": _mensaje(m["changed_item"], evidence_type, candidato),
                })
        elif ext.endswith(".md"):
            ruta_abs = repo_root / candidato
            if not ruta_abs.exists():
                return []
            texto = ruta_abs.read_text(encoding="utf-8", errors="replace")
            for m in _buscar_en_candidato_md(texto, fuente):
                evidence_type = _evidence_type("STRING_CONTRACT_REFERENCE", m["changed_item"], fuente["targets_path"], candidato)
                findings.append({
                    "source_changed": fuente["path"],
                    "changed_item": m["changed_item"],
                    "consumer": candidato,
                    "evidence_type": evidence_type,
                    "location": f"{candidato}:{m['linea']}",
                    "evidence": m["fragmento"],
                    "message": _mensaje(m["changed_item"], evidence_type, candidato),
                })
    except Exception:  # noqa: BLE001 - un consumidor con error se omite, nunca aborta el scan
        return []
    return findings


# --- Orquestador público --------------------------------------------------------

def ejecutar_scan(repo_root, since: Optional[str], staged: bool) -> dict:
    """Lanza `git_source.GitSourceError` si la ref es inválida. Nunca lanza
    otra excepción no controlada -- un error de parseo puntual de un archivo
    (Python o notebook) se degrada con gracia (se documenta en la entrada
    correspondiente), nunca aborta el scan completo. Nunca escribe nada en
    disco (R11) -- ni siquiera un archivo temporal."""
    repo_root = Path(repo_root)

    if since is not None:
        if not git_source.validar_ref(repo_root, since):
            raise GitSourceError(f"Referencia Git inválida: {since!r}")

    cambios = git_source.listar_cambios(repo_root, since, staged)

    fuentes = [_construir_fuente(repo_root, since, staged, cambio) for cambio in cambios]

    candidatos = git_source.listar_consumidores_candidatos(repo_root)

    findings: list = []
    for fuente in fuentes:
        tiene_targets = fuente["targets_simbolos"] or fuente["targets_strings"] or fuente["targets_path"]
        if not tiene_targets:
            continue
        for candidato in candidatos:
            findings.extend(_findings_para_candidato(repo_root, candidato, fuente))

    # Dedup por (source_changed, changed_item, consumer, location).
    vistos: dict = {}
    for f in findings:
        clave = (f["source_changed"], f["changed_item"], f["consumer"], f["location"])
        vistos.setdefault(clave, f)
    findings_dedup = list(vistos.values())
    findings_dedup.sort(key=lambda f: (f["source_changed"], f["changed_item"], f["consumer"], f["location"]))

    changed_entries = [f["changed_entry"] for f in fuentes]
    changed_items_count = sum(
        len(f["targets_simbolos"]) + len(f["targets_strings"]) + len(f["targets_path"]) for f in fuentes
    )
    consumers_unicos = {f["consumer"] for f in findings_dedup}

    return {
        "since": since,
        "staged": staged,
        "changed": changed_entries,
        "findings": findings_dedup,
        "summary": {
            "changed_files": len(cambios),
            "changed_items": changed_items_count,
            "findings": len(findings_dedup),
            "consumers": len(consumers_unicos),
        },
    }
