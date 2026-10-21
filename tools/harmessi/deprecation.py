"""Convención mínima de deprecación (v0.13 Change 5, solo-checkout).

Sin framework: una dataclass congelada, un registro (hoy vacío), un validador
puro y una función que emite `DeprecationWarning` con formato fijo. Sin
decoradores globales, sin telemetría y sin escritura a disco. Solo stdlib.
Ver `docs/deprecation.md`.
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass

TIPOS_VALIDOS = frozenset({"cli", "flag", "schema-field", "skill-key", "api"})

_RE_SEMVER = re.compile(r"([0-9]|[1-9][0-9]*)\.([0-9]|[1-9][0-9]*)\.([0-9]|[1-9][0-9]*)")


@dataclass(frozen=True)
class Deprecation:
    """Una deprecación declarada. `desde` y `remocion_minima` son versiones
    `X.Y.Z`; `remocion_minima` es la versión más temprana en que se podría
    remover (no una promesa de remoción)."""

    nombre: str
    tipo: str
    desde: str
    reemplazo: str
    remocion_minima: str


# Registro v0.13: vacío (no hay deprecaciones vigentes).
DEPRECATIONS: tuple = ()


def _parsear_semver(texto):
    """`(major, minor, patch)` o `None` si no es `X.Y.Z` estricto (sin
    espacios ni saltos de línea, sin ceros a la izquierda)."""
    if not isinstance(texto, str):
        return None
    coincidencia = _RE_SEMVER.fullmatch(texto)
    if coincidencia is None:
        return None
    return tuple(int(parte) for parte in coincidencia.groups())


def _problemas_de_entrada(entrada, indice: int, vistos: set) -> list:
    """Problemas de una entrada; `vistos` acumula nombres normalizados."""
    if not isinstance(entrada, Deprecation):
        return [f"entrada {indice}: se esperaba Deprecation, se recibió {type(entrada).__name__}"]
    problemas: list = []
    nombre = entrada.nombre
    if isinstance(nombre, str) and nombre.strip():
        normalizado = nombre.strip()
        etiqueta = repr(normalizado)
        if normalizado in vistos:
            problemas.append(f"{etiqueta}: nombre duplicado")
        else:
            vistos.add(normalizado)
    else:
        etiqueta = f"entrada {indice}"
        problemas.append(f"entrada {indice}: nombre vacío o no es texto")
    if not isinstance(entrada.tipo, str) or entrada.tipo not in TIPOS_VALIDOS:
        problemas.append(f"{etiqueta}: tipo {entrada.tipo!r} fuera de {sorted(TIPOS_VALIDOS)}")
    if not isinstance(entrada.reemplazo, str) or not entrada.reemplazo.strip():
        problemas.append(f"{etiqueta}: reemplazo vacío o no es texto")
    desde = _parsear_semver(entrada.desde)
    remocion = _parsear_semver(entrada.remocion_minima)
    if desde is None:
        problemas.append(f"{etiqueta}: desde {entrada.desde!r} no es una versión X.Y.Z")
    if remocion is None:
        problemas.append(f"{etiqueta}: remocion_minima {entrada.remocion_minima!r} no es una versión X.Y.Z")
    if desde is None or remocion is None:
        return problemas
    if remocion <= desde:
        problemas.append(f"{etiqueta}: remocion_minima debe ser estrictamente posterior a desde")
    elif desde[0] == 0 and not (remocion[0] > 0 or remocion[1] > desde[1]):
        problemas.append(
            f"{etiqueta}: en 0.x la remocion_minima debe ser al menos una versión menor posterior a desde"
        )
    elif desde[0] >= 1 and remocion[0] < desde[0] + 1:
        problemas.append(
            f"{etiqueta}: en 1.x la remocion_minima debe ser al menos la siguiente mayor ({desde[0] + 1}.0.0)"
        )
    return problemas


def validar_registro(entradas) -> list:
    """Devuelve la lista de problemas (str) del registro; vacía si es válido.
    Reglas: versiones `X.Y.Z` estrictas; `remocion_minima` estrictamente
    posterior a `desde`; en 0.x, al menos una versión menor posterior; en
    1.x o más, al menos la siguiente mayor; `reemplazo` no vacío; `tipo`
    válido; nombres únicos (comparados sin espacios en los bordes). Nunca
    lanza: un valor inesperado se reporta como problema."""
    try:
        elementos = list(entradas)
    except TypeError:
        return [f"el registro no es iterable: {type(entradas).__name__}"]
    problemas: list = []
    vistos: set = set()
    for indice, entrada in enumerate(elementos):
        try:
            problemas.extend(_problemas_de_entrada(entrada, indice, vistos))
        except Exception as exc:  # defensivo: el validador nunca lanza
            problemas.append(f"entrada {indice}: no se pudo validar ({type(exc).__name__})")
    return problemas


def advertir(nombre: str, registro=DEPRECATIONS, stacklevel: int = 2) -> None:
    """Emite `DeprecationWarning` con formato fijo para `nombre`. Lanza
    `KeyError` si no está registrado y `ValueError` si la entrada registrada
    es inválida (no se emite un aviso con datos corruptos). Nota: Python
    silencia `DeprecationWarning` por defecto fuera de `__main__` y de los
    tests; ver `docs/deprecation.md`."""
    for entrada in registro:
        if getattr(entrada, "nombre", None) == nombre:
            problemas = validar_registro([entrada])
            if problemas:
                raise ValueError(f"deprecación inválida para {nombre!r}: {'; '.join(problemas)}")
            mensaje = (
                f"{entrada.nombre} está deprecado desde {entrada.desde}; usar {entrada.reemplazo}; "
                f"se removerá no antes de {entrada.remocion_minima}"
            )
            warnings.warn(mensaje, DeprecationWarning, stacklevel=stacklevel)
            return
    raise KeyError(nombre)
