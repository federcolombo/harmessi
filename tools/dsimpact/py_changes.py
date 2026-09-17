"""Changed items de Python: símbolos de nivel módulo (R2), strings
contractuales (R3), y nombre de módulo derivado de un path (R4).

Vía `ast` (stdlib, `ast.unparse` disponible desde Python 3.9). Nunca ejecuta
nada -- solo parsea texto.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SimboloCambiado:
    nombre: str
    tipo: str   # "funcion" | "clase" | "constante"
    cambio: str  # "agregado" | "eliminado" | "modificado"


def _simbolos_nivel_modulo(arbol: ast.Module) -> dict:
    resultado = {}
    for nodo in arbol.body:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            resultado[nodo.name] = ("funcion", nodo)
        elif isinstance(nodo, ast.ClassDef):
            resultado[nodo.name] = ("clase", nodo)
        elif isinstance(nodo, ast.Assign):
            for t in nodo.targets:
                if isinstance(t, ast.Name):
                    resultado[t.id] = ("constante", nodo)
        elif isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
            resultado[nodo.target.id] = ("constante", nodo)
    return resultado


def diff_simbolos(texto_before: Optional[str], texto_after: Optional[str]):
    """(list[SimboloCambiado], parse_error: bool). `parse_error=True` si
    `before` o `after` existen pero no parsean (`SyntaxError`) -- en ese caso
    la lista es vacía, el archivo se sigue reportando en `changed` (por el
    orquestador) con una nota, sin bloquear el resto del scan."""
    try:
        arbol_before = ast.parse(texto_before) if texto_before is not None else None
        arbol_after = ast.parse(texto_after) if texto_after is not None else None
    except SyntaxError:
        return [], True

    simb_before = _simbolos_nivel_modulo(arbol_before) if arbol_before else {}
    simb_after = _simbolos_nivel_modulo(arbol_after) if arbol_after else {}

    cambiados = []
    for nombre in sorted(set(simb_before) | set(simb_after)):
        en_before, en_after = nombre in simb_before, nombre in simb_after
        if en_before and not en_after:
            cambiados.append(SimboloCambiado(nombre, simb_before[nombre][0], "eliminado"))
        elif en_after and not en_before:
            cambiados.append(SimboloCambiado(nombre, simb_after[nombre][0], "agregado"))
        else:
            tipo, nodo_b = simb_before[nombre]
            _, nodo_a = simb_after[nombre]
            if ast.unparse(nodo_b) != ast.unparse(nodo_a):
                cambiados.append(SimboloCambiado(nombre, tipo, "modificado"))
    return cambiados, False


_COMPARADORES_VALIDOS = (ast.Eq, ast.NotEq, ast.In, ast.NotIn)


def _es_str(nodo) -> bool:
    return isinstance(nodo, ast.Constant) and isinstance(nodo.value, str)


def _strings_estructurales(nodo: ast.AST) -> set:
    """Solo strings en posición estructural (R3): elemento de
    lista/tupla/set, key/value de dict, RHS de una asignación, dentro del
    `test` de un assert, u operando de un `Compare` con `==`/`!=`/`in`/
    `not in`. Nunca docstrings, f-strings, args de logging, ni literales
    sueltos fuera de esas posiciones."""
    encontrados = set()
    for sub in ast.walk(nodo):
        if isinstance(sub, (ast.List, ast.Tuple, ast.Set)):
            encontrados |= {e.value for e in sub.elts if _es_str(e)}
        elif isinstance(sub, ast.Dict):
            for k, v in zip(sub.keys, sub.values):
                if k is not None and _es_str(k):
                    encontrados.add(k.value)
                if _es_str(v):
                    encontrados.add(v.value)
        elif isinstance(sub, (ast.Assign, ast.AnnAssign)):
            if sub.value is not None and _es_str(sub.value):
                encontrados.add(sub.value.value)
        elif isinstance(sub, ast.Assert):
            encontrados |= {s.value for s in ast.walk(sub.test) if _es_str(s)}
        elif isinstance(sub, ast.Compare):
            if _es_str(sub.left) and any(isinstance(o, _COMPARADORES_VALIDOS) for o in sub.ops):
                encontrados.add(sub.left.value)
            for op, comparador in zip(sub.ops, sub.comparators):
                if isinstance(op, _COMPARADORES_VALIDOS) and _es_str(comparador):
                    encontrados.add(comparador.value)
    return encontrados


def strings_contractuales(texto_after: Optional[str], simbolos_cambiados: list) -> set:
    """Solo dentro del cuerpo/valor de símbolos con cambio
    'agregado'/'modificado' (ver `spec.md` R3 -- nunca todo el archivo)."""
    if texto_after is None:
        return set()
    try:
        arbol = ast.parse(texto_after)
    except SyntaxError:
        return set()
    nombres_relevantes = {s.nombre for s in simbolos_cambiados if s.cambio in ("agregado", "modificado")}
    simb_after = _simbolos_nivel_modulo(arbol)
    resultado = set()
    for nombre in nombres_relevantes:
        if nombre in simb_after:
            _, nodo = simb_after[nombre]
            resultado |= _strings_estructurales(nodo)
    return resultado


def derivar_nombre_modulo(path_relativo: str) -> Optional[str]:
    """Solo para `.py`: `'tools/features.py'` -> `'tools.features'`.
    `'tools/pkg/__init__.py'` -> `'tools.pkg'`. `None` si no termina en
    `.py`. Sin resolver `sys.path` real -- derivación textual simple (ver
    `spec.md` R4)."""
    if not path_relativo.endswith(".py"):
        return None
    partes = path_relativo[:-3].split("/")
    if partes and partes[-1] == "__init__":
        partes = partes[:-1]
    if not partes:
        return None
    return ".".join(partes)
