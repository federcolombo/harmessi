"""Búsqueda de consumidores en JSON/YAML/TOML/MD (R6).

JSON se recorre estructuralmente (`json.loads`, nunca regex sobre texto
crudo). YAML/TOML/MD no tienen parser stdlib universal para el rango de
Python soportado (ver `design.md` §6) -- se tratan como texto plano con
matching de palabra completa por línea (word-boundary real, no substring).
"""
from __future__ import annotations

import json
import re


def buscar_en_json(texto: str, targets: set) -> list:
    """[{"changed_item": str, "fragmento": str}, ...] -- el `evidence_type`
    `CONFIG_REFERENCE` lo agrega el orquestador."""
    try:
        datos = json.loads(texto)
    except (json.JSONDecodeError, ValueError):
        return []
    encontrados = set()

    def _recorrer(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, str) and k in targets:
                    encontrados.add(k)
                _recorrer(v)
        elif isinstance(obj, list):
            for v in obj:
                _recorrer(v)
        elif isinstance(obj, str) and obj in targets:
            encontrados.add(obj)

    _recorrer(datos)
    return [{"changed_item": item, "fragmento": item} for item in sorted(encontrados)]


_PATRON_CACHE: dict = {}


def _patron_palabra(target: str):
    if target not in _PATRON_CACHE:
        _PATRON_CACHE[target] = re.compile(r"(?<![\w.]){}(?![\w])".format(re.escape(target)))
    return _PATRON_CACHE[target]


def buscar_en_texto_plano(texto: str, targets: set) -> list:
    """Para `.yaml`/`.yml`/`.toml`/`.md`: matching de palabra completa por
    línea (word-boundary real, no substring) -- ver `design.md` §6.
    [{"changed_item": str, "linea": int, "fragmento": str}, ...]."""
    resultados = []
    for i, linea in enumerate(texto.splitlines(), start=1):
        for target in targets:
            if _patron_palabra(target).search(linea):
                resultados.append({"changed_item": target, "linea": i, "fragmento": linea.strip()[:120]})
    return resultados
