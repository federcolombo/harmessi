"""Arma el plan de instalación combinando `manifest.py` +
`preflight.detectar_colisiones` (R3, R10). Es lo que imprime `--dry-run` y lo
que valida `--execute` antes de escribir nada.

Este módulo no toca el contenido de los archivos (eso es `templating.py` /
`writer.py`, Sesión 2): solo decide, por entrada del manifiesto, qué acción le
corresponde.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .manifest import GENERADO, MERGE, PLANTILLA, VERBATIM, manifest_para_perfil
from .preflight import detectar_colisiones

ACCION_CREAR = "crear"
ACCION_OMITIR_EXISTENTE = "omitir-por-existente"
ACCION_MERGE = "merge"
ACCION_PLANTILLA = "plantilla"


@dataclass(frozen=True)
class AccionPlan:
    """Una fila del plan mostrado por `--dry-run` (R10): ruta destino y
    acción a aplicar."""

    destino: str
    accion: str
    descripcion: str = ""


def _accion_para_entrada(entrada, colisiones: set, integrar_claude_md: bool) -> str:
    """Decide la acción de una entrada del manifiesto, dado el conjunto de
    destinos que ya existen en el repo destino (`colisiones`)."""
    ya_existe = entrada.destino in colisiones

    if entrada.tratamiento == MERGE:
        # settings.json: si no existe se crea, si existe se fusiona (R8).
        return ACCION_MERGE if ya_existe else ACCION_CREAR

    if entrada.destino == "CLAUDE.md":
        # R9: si no existe, se crea; si existe, solo se toca con
        # --integrar-claude (bloque delimitado idempotente).
        if not ya_existe:
            return ACCION_CREAR
        return ACCION_MERGE if integrar_claude_md else ACCION_OMITIR_EXISTENTE

    if ya_existe:
        # R10: por defecto un archivo ya existente se omite, nunca se
        # sobrescribe (fuera de los casos MERGE/CLAUDE.md ya cubiertos).
        return ACCION_OMITIR_EXISTENTE

    if entrada.tratamiento == PLANTILLA:
        return ACCION_PLANTILLA
    if entrada.tratamiento in (VERBATIM, GENERADO):
        return ACCION_CREAR

    raise ValueError(f"tratamiento sin acción definida: {entrada.tratamiento!r}")


def construir_plan(perfil: str, destino: Path, config: dict) -> list:
    """Combina `manifest_para_perfil(perfil)` + `detectar_colisiones` y arma
    la lista de `AccionPlan` (R3, R10).

    `config` acepta la clave opcional `integrar_claude` (bool, default
    `False`) — corresponde al flag `--integrar-claude` de la CLI.
    """
    entradas = manifest_para_perfil(perfil)
    destinos = [entrada.destino for entrada in entradas]
    colisiones = set(detectar_colisiones(destinos, Path(destino)))
    integrar_claude_md = bool(config.get("integrar_claude", False))

    plan = []
    for entrada in entradas:
        accion = _accion_para_entrada(entrada, colisiones, integrar_claude_md)
        plan.append(AccionPlan(destino=entrada.destino, accion=accion, descripcion=entrada.descripcion))
    return plan


def formatear_plan(plan: list) -> str:
    """Representación de texto plano del plan, para `--dry-run` y para el
    reporte final de `--execute`."""
    lineas = [f"Plan de instalación ({len(plan)} entradas):"]
    for accion in plan:
        detalle = f" — {accion.descripcion}" if accion.descripcion else ""
        lineas.append(f"  [{accion.accion:22s}] {accion.destino}{detalle}")
    return "\n".join(lineas)
