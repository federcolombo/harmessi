"""Búsqueda de consumidores en texto Python (archivo `.py` completo, o
`source` de una celda de código de notebook) -- R5/R6.

Vía `ast` (para ubicar rangos de línea de imports/asserts) y `tokenize` (para
encontrar tokens `NAME` reales, nunca substring dentro de otro identificador).
No resuelve aliasing (`import x as y`), reflection ni imports dinámicos --
deuda aceptada (ver `spec.md` R5, `design.md` §8).
"""
from __future__ import annotations

import ast
import io
import tokenize


def _rangos_de_lineas(arbol, tipos_nodo) -> set:
    lineas = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, tipos_nodo):
            fin = getattr(nodo, "end_lineno", None) or nodo.lineno
            lineas.update(range(nodo.lineno, fin + 1))
    return lineas


def buscar_en_texto_python(texto: str, targets_simbolos: set, targets_strings: set) -> list:
    """[{"changed_item": str, "tipo_base": "ASSERT_REFERENCE"|"IMPORT_REFERENCE"|
    "SYMBOL_REFERENCE"|"STRING_CONTRACT_REFERENCE", "linea": int, "fragmento": str}, ...].
    Si `texto` no parsea (`SyntaxError`), devuelve `[]` -- el consumidor se
    omite, no bloquea el scan (límite documentado: un consumidor con error de
    sintaxis no se analiza)."""
    try:
        arbol = ast.parse(texto)
    except SyntaxError:
        return []

    lineas_import = _rangos_de_lineas(arbol, (ast.Import, ast.ImportFrom))
    lineas_assert = _rangos_de_lineas(arbol, (ast.Assert,))
    lineas_texto = texto.splitlines()

    def _fragmento(linea: int) -> str:
        return lineas_texto[linea - 1].strip()[:120] if 0 < linea <= len(lineas_texto) else ""

    def _tipo_base(linea: int, es_string: bool) -> str:
        if linea in lineas_assert:
            return "ASSERT_REFERENCE"
        if not es_string and linea in lineas_import:
            return "IMPORT_REFERENCE"
        return "STRING_CONTRACT_REFERENCE" if es_string else "SYMBOL_REFERENCE"

    resultados = []
    if targets_simbolos:
        try:
            for tok in tokenize.generate_tokens(io.StringIO(texto).readline):
                if tok.type == tokenize.NAME and tok.string in targets_simbolos:
                    linea = tok.start[0]
                    resultados.append({
                        "changed_item": tok.string, "tipo_base": _tipo_base(linea, False),
                        "linea": linea, "fragmento": _fragmento(linea),
                    })
        except (tokenize.TokenizeError, IndentationError, SyntaxError):
            # Casos borde raros donde `ast.parse` acepta pero `tokenize` no --
            # no se rompe todo el finding, se conserva lo ya encontrado vía
            # `ast.walk` para strings más abajo.
            pass

    if targets_strings:
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and nodo.value in targets_strings:
                linea = nodo.lineno
                resultados.append({
                    "changed_item": nodo.value, "tipo_base": _tipo_base(linea, True),
                    "linea": linea, "fragmento": _fragmento(linea),
                })
    return resultados
