"""Merge de `.claude/settings.json` del destino con el `settings.json` del
harness (R8): preserva toda clave existente que no colisione; ante colisión
incompatible, aborta sin escribir nada y detalla el conflicto exacto.
"""
from __future__ import annotations

import copy


class ConflictoIncompatibleError(Exception):
    """Dos hooks con el mismo `matcher` (dentro del mismo evento, p. ej.
    `PreToolUse`) tienen `command` distinto — no se puede fusionar de forma
    segura (R8, AC7 de `spec.md`)."""

    def __init__(self, detalle: str):
        self.detalle = detalle
        super().__init__(detalle)


def _hooks_por_matcher(lista_hooks: list) -> dict:
    """Índice `matcher -> lista de comandos declarados` para un array de
    entradas de hooks estilo `.claude/settings.json` (cada entrada trae
    `matcher` + `hooks: [{type, command}, ...]`)."""
    indice = {}
    for entrada in lista_hooks:
        matcher = entrada.get("matcher")
        comandos = tuple(h.get("command") for h in entrada.get("hooks", []))
        indice.setdefault(matcher, []).append(comandos)
    return indice


def _fusionar_evento_hooks(existente_evento: list, nuevo_evento: list, nombre_evento: str) -> list:
    """Fusiona el array de un evento (p. ej. `PreToolUse`) preservando las
    entradas existentes y agregando las nuevas que no colisionen. Colisión =
    mismo `matcher` con distinta lista de `command`."""
    indice_existente = _hooks_por_matcher(existente_evento)

    resultado = list(existente_evento)
    for entrada_nueva in nuevo_evento:
        matcher = entrada_nueva.get("matcher")
        comandos_nuevos = tuple(h.get("command") for h in entrada_nueva.get("hooks", []))

        if matcher in indice_existente:
            if comandos_nuevos in indice_existente[matcher]:
                # Ya está presente tal cual, no duplicar.
                continue
            raise ConflictoIncompatibleError(
                f"Conflicto en hooks.{nombre_evento}: el matcher {matcher!r} ya existe en "
                f"el destino con command(s) {indice_existente[matcher]!r}, distinto del "
                f"command(s) del harness {comandos_nuevos!r}"
            )
        resultado.append(entrada_nueva)
    return resultado


def fusionar(existente: dict, nuevo: dict) -> dict:
    """Fusiona `nuevo` (settings.json del harness) sobre `existente` (settings
    .json ya presente en el destino), preservando toda clave existente no
    conflictiva. Levanta `ConflictoIncompatibleError` ante colisión
    incompatible (R8). No muta ninguno de los dos dicts de entrada."""
    resultado = copy.deepcopy(existente)

    for clave, valor_nuevo in nuevo.items():
        if clave not in resultado:
            resultado[clave] = copy.deepcopy(valor_nuevo)
            continue

        valor_existente = resultado[clave]

        if clave == "hooks" and isinstance(valor_existente, dict) and isinstance(valor_nuevo, dict):
            hooks_fusionados = copy.deepcopy(valor_existente)
            for nombre_evento, eventos_nuevos in valor_nuevo.items():
                if nombre_evento not in hooks_fusionados:
                    hooks_fusionados[nombre_evento] = copy.deepcopy(eventos_nuevos)
                else:
                    hooks_fusionados[nombre_evento] = _fusionar_evento_hooks(
                        hooks_fusionados[nombre_evento], eventos_nuevos, nombre_evento
                    )
            resultado[clave] = hooks_fusionados
            continue

        if isinstance(valor_existente, dict) and isinstance(valor_nuevo, dict):
            # Merge superficial recursivo para otras claves-objeto (p. ej.
            # "worktree"): mismo criterio, preservar lo existente.
            fusionado = dict(valor_existente)
            for subclave, subvalor in valor_nuevo.items():
                if subclave not in fusionado:
                    fusionado[subclave] = copy.deepcopy(subvalor)
                elif fusionado[subclave] != subvalor:
                    raise ConflictoIncompatibleError(
                        f"Conflicto en {clave}.{subclave}: destino tiene "
                        f"{fusionado[subclave]!r}, harness tiene {subvalor!r}"
                    )
            resultado[clave] = fusionado
            continue

        if valor_existente == valor_nuevo:
            continue

        raise ConflictoIncompatibleError(
            f"Conflicto en clave {clave!r}: destino tiene {valor_existente!r}, "
            f"harness tiene {valor_nuevo!r}"
        )

    return resultado
