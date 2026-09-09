"""Diff determinista de notebooks `.ipynb`, sin ejecutar nada.

Responsabilidades:
- Validar que el contenido de un `.ipynb` sea JSON válido (`NB-JSON-INVALIDO`,
  con línea/columna del `JSONDecodeError`).
- Comparar el notebook del working tree contra una revisión de git
  (`git show <rev>:<path>`, vía `repo._git`) **por posición + hash de
  contenido de `source`**, nunca por `id` de celda: la mayoría de los
  notebooks reales de este proyecto no tienen `id` en sus celdas. Limitación
  deliberada: esta comparación posicional NO detecta movimientos de celdas —
  un bloque desplazado (insertado/borrado en el medio) aparece como un tramo
  "eliminado" seguido de un tramo "agregado", en vez de reconocerse como el
  mismo contenido reubicado.

Este módulo nunca ejecuta el notebook: solo lee texto y lo parsea como JSON.
"""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
from typing import Optional

from . import repo as repo_mod
from .core import Finding


# --- Parseo de JSON ------------------------------------------------------------

def parsear_notebook_texto(texto: str, ubicacion: str):
    """(notebook: dict|None, finding: Finding|None). Si el JSON es inválido,
    `notebook` es `None` y `finding` trae código `NB-JSON-INVALIDO` con línea y
    columna del `json.JSONDecodeError`."""
    try:
        return json.loads(texto), None
    except json.JSONDecodeError as e:
        return None, Finding(
            "NB-JSON-INVALIDO",
            f"JSON inválido en {ubicacion}: línea {e.lineno}, columna {e.colno}: {e.msg}",
            ubicacion,
        )


# --- Obtención de una revisión anterior vía git -------------------------------

def obtener_revision(repo_root: Path, rev: str, ruta_posix: str):
    """(existe_en_esa_revision: bool, texto: str|None, rev_valida: bool).

    Si `rev` no resuelve a ningún commit, `rev_valida` es `False` (error de
    uso: revisión desconocida). Si `rev` resuelve pero el archivo no existía
    ahí (notebook nuevo), `existe_en_esa_revision` es `False` con
    `rev_valida=True` y `texto=None`."""
    resultado = repo_mod._git(repo_root, "show", f"{rev}:{ruta_posix}")
    if resultado.returncode == 0:
        return True, resultado.stdout, True
    verificacion = repo_mod._git(repo_root, "rev-parse", "--verify", rev)
    if verificacion.returncode != 0:
        return False, None, False
    return False, None, True


# --- Hash y resumen de celdas ---------------------------------------------------

def _fuente_a_texto(source) -> str:
    if isinstance(source, list):
        return "".join(source)
    return source or ""


def _hash_source(celda: dict) -> str:
    texto = _fuente_a_texto(celda.get("source", ""))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _primeros_60(celda: dict) -> str:
    texto = _fuente_a_texto(celda.get("source", ""))
    lineas = texto.splitlines()
    primera = lineas[0] if lineas else ""
    return primera[:60]


def _execution_count(celda: Optional[dict]):
    if celda is None:
        return None
    return celda.get("execution_count")


def _cantidad_outputs(celda: Optional[dict]):
    if celda is None:
        return None
    return len(celda.get("outputs", []) or [])


def _outputs_o_exec_distintos(ca: dict, cd: dict) -> bool:
    return ca.get("execution_count") != cd.get("execution_count") or (
        ca.get("outputs", []) != cd.get("outputs", [])
    )


def _resumen_celda(ruta: str, indice: int, tipo: str, ca: Optional[dict], cd: Optional[dict]) -> dict:
    referencia = cd if cd is not None else ca
    return {
        "archivo": ruta,
        "indice": indice,
        "tipo": tipo,
        "cell_type": referencia.get("cell_type") if referencia else None,
        "primera_linea": _primeros_60(referencia) if referencia else "",
        "execution_count_antes": _execution_count(ca),
        "execution_count_despues": _execution_count(cd),
        "outputs_antes": _cantidad_outputs(ca),
        "outputs_despues": _cantidad_outputs(cd),
    }


# --- Ids: ausentes/duplicados ---------------------------------------------------

def _chequear_ids(cells_despues: list, indices_tocados: set, ruta: str):
    """(bloqueantes, informativos). `NB-ID-AUSENTE` siempre es warning
    (informativo, nunca bloquea). `NB-ID-DUPLICADO` es bloqueante solo si
    alguna de las celdas con ese id repetido está en `indices_tocados`
    (nueva o modificada en este diff); si el duplicado ya existía sin
    tocarse, queda como warning."""
    bloqueantes = []
    informativos = []
    ids_vistos: dict = {}
    for i, celda in enumerate(cells_despues):
        cid = celda.get("id")
        if cid is None:
            informativos.append(
                Finding("NB-ID-AUSENTE", f"Celda {i} de {ruta} sin id", f"{ruta}#{i}")
            )
            continue
        ids_vistos.setdefault(cid, []).append(i)

    for cid, indices in ids_vistos.items():
        if len(indices) <= 1:
            continue
        mensaje = f"id duplicado '{cid}' en celdas {indices} de {ruta}"
        if any(i in indices_tocados for i in indices):
            bloqueantes.append(Finding("NB-ID-DUPLICADO", mensaje, ruta))
        else:
            informativos.append(Finding("NB-ID-DUPLICADO", mensaje, ruta))

    return bloqueantes, informativos


# --- Diff por celdas -------------------------------------------------------------

def _procesar_par_alineado(
    ruta: str,
    indice_despues: int,
    ca: dict,
    cd: dict,
    estado_sdd: Optional[str],
    resumen: list,
    conteos: dict,
    bloqueantes: list,
    informativos: list,
    indices_tocados: set,
) -> None:
    """Clasifica un par de celdas ya alineadas por `SequenceMatcher` (misma
    posición relativa en un bloque `equal`/`replace`): `modificada` si el
    hash de `source` difiere, `solo_ejecucion` si el `source` es igual pero
    `outputs`/`execution_count` cambiaron, o nada si son idénticas."""
    if _hash_source(ca) != _hash_source(cd):
        indices_tocados.add(indice_despues)
        conteos["modificadas"] += 1
        resumen.append(_resumen_celda(ruta, indice_despues, "modificada", ca, cd))
    elif _outputs_o_exec_distintos(ca, cd):
        conteos["solo_ejecucion"] += 1
        resumen.append(_resumen_celda(ruta, indice_despues, "solo_ejecucion", ca, cd))
        mensaje = (
            f"Celda {indice_despues} de {ruta}: outputs/execution_count "
            "cambiaron sin cambiar el source"
        )
        codigo_finding = Finding(
            "NB-OUTPUTS-FUERA-DE-FASE", mensaje, f"{ruta}#{indice_despues}"
        )
        if estado_sdd == "en_implementacion":
            bloqueantes.append(codigo_finding)
        else:
            informativos.append(codigo_finding)


def diff_notebooks(nb_antes: Optional[dict], nb_despues: dict, estado_sdd: Optional[str], ruta: str) -> dict:
    """Diff entre `nb_antes` (puede ser `None` si el notebook es nuevo) y
    `nb_despues`, alineado con `difflib.SequenceMatcher` sobre la secuencia de
    hashes de `source` de cada celda (no sobre las celdas completas) —
    detecta inserciones/eliminaciones en cualquier posición del notebook, no
    solo al final.

    Limitación deliberada, ya declarada a nivel de módulo: sin `id` de celda,
    un tramo `replace` de igual longitud en ambos lados (p. ej. una celda que
    cambia de contenido sin ninguna celda-ancla de contenido igual alrededor
    que permita separar "se borró esto" de "se agregó aquello") se clasifica
    como "modificada" — es la mejor respuesta honesta que un diff por
    contenido puede dar ante esa ambigüedad, no una falla del algoritmo.

    Devuelve un dict con `resumen` (lista de dicts por celda cambiada, nunca
    con `source` completo ni `outputs`), `conteos`
    (agregadas/eliminadas/modificadas/solo_ejecucion), `bloqueantes` e
    `informativos` (listas de `Finding`).
    """
    cells_antes = (nb_antes or {}).get("cells", []) or []
    cells_despues = (nb_despues or {}).get("cells", []) or []

    resumen = []
    conteos = {"agregadas": 0, "eliminadas": 0, "modificadas": 0, "solo_ejecucion": 0}
    bloqueantes = []
    informativos = []
    indices_tocados = set()

    hashes_antes = [_hash_source(c) for c in cells_antes]
    hashes_despues = [_hash_source(c) for c in cells_despues]
    matcher = difflib.SequenceMatcher(None, hashes_antes, hashes_despues, autojunk=False)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                _procesar_par_alineado(
                    ruta, j1 + k, cells_antes[i1 + k], cells_despues[j1 + k],
                    estado_sdd, resumen, conteos, bloqueantes, informativos, indices_tocados,
                )
        elif tag == "replace":
            largo_comun = min(i2 - i1, j2 - j1)
            for k in range(largo_comun):
                _procesar_par_alineado(
                    ruta, j1 + k, cells_antes[i1 + k], cells_despues[j1 + k],
                    estado_sdd, resumen, conteos, bloqueantes, informativos, indices_tocados,
                )
            for k in range(largo_comun, i2 - i1):
                indice = i1 + k
                conteos["eliminadas"] += 1
                resumen.append(_resumen_celda(ruta, indice, "eliminada", cells_antes[indice], None))
            for k in range(largo_comun, j2 - j1):
                indice = j1 + k
                indices_tocados.add(indice)
                conteos["agregadas"] += 1
                resumen.append(_resumen_celda(ruta, indice, "agregada", None, cells_despues[indice]))
        elif tag == "delete":
            for indice in range(i1, i2):
                conteos["eliminadas"] += 1
                resumen.append(_resumen_celda(ruta, indice, "eliminada", cells_antes[indice], None))
        elif tag == "insert":
            for indice in range(j1, j2):
                indices_tocados.add(indice)
                conteos["agregadas"] += 1
                resumen.append(_resumen_celda(ruta, indice, "agregada", None, cells_despues[indice]))

    ids_bloq, ids_inf = _chequear_ids(cells_despues, indices_tocados, ruta)
    bloqueantes += ids_bloq
    informativos += ids_inf

    return {
        "resumen": resumen,
        "conteos": conteos,
        "bloqueantes": bloqueantes,
        "informativos": informativos,
    }


# --- Orquestación por archivo ---------------------------------------------------

def diff_archivo(repo_root: Path, ruta_relativa: str, rev: str, estado_sdd: Optional[str]) -> dict:
    """Diff de un `.ipynb` del working tree contra `rev`. Devuelve un dict con
    `error_uso` (Finding|None — revisión desconocida o archivo ausente en el
    working tree, errores de uso/entorno) y, si no hay error de uso,
    `resumen`/`conteos`/`bloqueantes`/`informativos` (`NB-JSON-INVALIDO`
    cuenta como hallazgo bloqueante normal, no como error de uso)."""
    ruta_posix = Path(ruta_relativa).as_posix()
    ruta_abs = repo_root / ruta_relativa
    if not ruta_abs.exists():
        return {
            "error_uso": Finding(
                "NB-ARCHIVO-AUSENTE",
                f"No existe en el working tree: {ruta_relativa}",
                ruta_relativa,
            )
        }

    texto_despues = ruta_abs.read_text(encoding="utf-8", errors="replace")
    nb_despues, finding_json = parsear_notebook_texto(texto_despues, ruta_relativa)
    if finding_json:
        return {
            "error_uso": None,
            "resumen": [],
            "conteos": {"agregadas": 0, "eliminadas": 0, "modificadas": 0, "solo_ejecucion": 0},
            "bloqueantes": [finding_json],
            "informativos": [],
        }

    existe, texto_antes, rev_valida = obtener_revision(repo_root, rev, ruta_posix)
    if not rev_valida:
        return {
            "error_uso": Finding("NB-REVISION-INVALIDA", f"Revisión desconocida: {rev}", rev)
        }

    nb_antes = None
    if existe:
        nb_antes, finding_json_antes = parsear_notebook_texto(texto_antes, f"{rev}:{ruta_relativa}")
        if finding_json_antes:
            return {
                "error_uso": None,
                "resumen": [],
                "conteos": {"agregadas": 0, "eliminadas": 0, "modificadas": 0, "solo_ejecucion": 0},
                "bloqueantes": [finding_json_antes],
                "informativos": [],
            }

    resultado = diff_notebooks(nb_antes, nb_despues, estado_sdd, ruta_relativa)
    resultado["error_uso"] = None
    return resultado
