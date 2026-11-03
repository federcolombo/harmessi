"""Extraccion determinista de la superficie de una CLI `argparse` (v1 Change 20261030-v1-contract-stabilization, T1).

`extraer_superficie(parser)` recorre el parser por introspeccion (sin ejecutar ningun comando) y devuelve:

    {"<ruta de subcomando separada por espacio; '' = raiz>":
        {"flags": {"--flag": {"required": bool, "choices": [str, ...] | None, "nargs": str | None}},
         "posicionales": {"nombre": {"required": bool, "choices": [str, ...] | None, "nargs": str | None}}}}

Reglas:
- `-h/--help` se excluyen. Cada option string (`-x`, `--xx`) es una clave de `flags`.
- Los subparsers se recorren recursivamente; cada nombre registrado (alias incluidos) es una ruta.
- Un posicional con `choices` (p. ej. `ds_init accion`) se trata ademas como conjunto de subcomandos: cada
  choice agrega una ruta `<ruta> <choice>` con flags/posicionales vacios (los flags quedan en la ruta padre).
- `choices` se serializa como lista de `str` ordenada; `nargs` como `str` (store_true -> "0") o None.
- `posicionales` es un dict ordenado por aparicion (el orden de los posicionales importa en argparse).

FUENTE UNICA: `tools/tests/fixtures/compat/generate_v015.py` importa este modulo por ruta (no lo duplica) y
`test_v1_stable_contracts.py` lo verifica. Solo stdlib.
"""
from __future__ import annotations

import argparse


def _info_accion(accion: argparse.Action) -> dict:
    choices = None if accion.choices is None else sorted(str(c) for c in accion.choices)
    nargs = None if accion.nargs is None else str(accion.nargs)
    return {"required": bool(accion.required), "choices": choices, "nargs": nargs}


def _recorrer(parser: argparse.ArgumentParser, ruta: list, salida: dict) -> None:
    flags: dict = {}
    posicionales: dict = {}
    hijos: list = []
    choices_posicionales: list = []
    for accion in parser._actions:
        if isinstance(accion, argparse._HelpAction):
            continue
        if isinstance(accion, argparse._SubParsersAction):
            hijos.extend(accion.choices.items())
            continue
        if accion.option_strings:
            for opcion in accion.option_strings:
                if opcion in ("-h", "--help"):
                    continue
                flags[opcion] = _info_accion(accion)
        else:
            posicionales[accion.dest] = _info_accion(accion)
            if accion.choices is not None:
                choices_posicionales.extend(str(c) for c in accion.choices)
    salida[" ".join(ruta)] = {"flags": flags, "posicionales": posicionales}
    for nombre, sub in hijos:
        _recorrer(sub, ruta + [str(nombre)], salida)
    for choice in choices_posicionales:
        salida.setdefault(" ".join(ruta + [choice]), {"flags": {}, "posicionales": {}})


def extraer_superficie(parser: argparse.ArgumentParser) -> dict:
    """Superficie (subcomandos, flags, posicionales) de `parser`. Ver docstring del modulo."""
    salida: dict = {}
    _recorrer(parser, [], salida)
    return salida
