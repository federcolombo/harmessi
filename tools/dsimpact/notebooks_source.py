"""Lectura de notebooks para Impact Preflight (R8).

Reusa `dsguard.notebooks.parsear_notebook_texto` (JSON parse con manejo de
error ya resuelto) -- nunca ejecuta el notebook, nunca analiza `outputs`.
Markdown de celdas se ignora en v1 (documentado, ver `spec.md` R8).
"""
from __future__ import annotations

from dsguard import notebooks as dsguard_notebooks


def _fuente_a_texto(source) -> str:
    if isinstance(source, list):
        return "".join(source)
    return source or ""


def celdas_codigo(texto_notebook: str, ubicacion: str):
    """(list[(indice: int, texto: str)], error: bool). `error=True` si el
    JSON del notebook es inválido -- en ese caso la lista es vacía y el
    notebook se excluye del scan (como consumidor Y como changed item si
    corresponde) sin abortar el resto (mismo criterio que R2 para `.py` con
    `SyntaxError`)."""
    notebook, finding = dsguard_notebooks.parsear_notebook_texto(texto_notebook, ubicacion)
    if finding is not None:
        return [], True
    celdas = notebook.get("cells", []) if isinstance(notebook, dict) else []
    resultado = []
    for i, celda in enumerate(celdas):
        if celda.get("cell_type") == "code":
            resultado.append((i, _fuente_a_texto(celda.get("source", ""))))
    return resultado, False
