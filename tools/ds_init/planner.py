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

from .manifest import (
    GENERADO,
    MERGE,
    ORDEN_STAGES,
    PLANTILLA,
    VERBATIM,
    manifest_para_perfil,
    manifest_para_perfil_stage_y_capabilities,
    manifest_para_perfil_y_stage,
)
from .managed_hash import ESTADO_ALG_DESCONOCIDO, ESTADO_DRIFT, ESTADO_OK, ESTADO_OK_LEGACY
from .preflight import detectar_colisiones

ACCION_CREAR = "crear"
ACCION_OMITIR_EXISTENTE = "omitir-por-existente"
ACCION_MERGE = "merge"
ACCION_PLANTILLA = "plantilla"
ACCION_ACTUALIZAR_MANAGED = "actualizar-managed"


@dataclass(frozen=True)
class AccionPlan:
    """Una fila del plan mostrado por `--dry-run` (R10): ruta destino y
    acción a aplicar."""

    destino: str
    accion: str
    descripcion: str = ""
    # M1/R27d: existente sin baseline previo; el writer solo lo registra si el
    # contenido distribuido es idéntico (nunca sobrescribe un archivo del usuario).
    solo_si_identico: bool = False


DESCRIPCION_DRIFT_PRESERVADO = (
    "DRIFT preservado: modificado respecto del baseline; sync no lo reescribe ni lo adopta"
)


def _accion_para_entrada(entrada, colisiones: set, integrar_claude_md: bool, clasificacion=None) -> str:
    """Decide la acción de una entrada del manifiesto, dado el conjunto de
    destinos que ya existen en el repo destino (`colisiones`).

    `clasificacion` (opcional, salida de `control.clasificar_baseline`): solo
    la usa `sync` (M-A, R27). Con `None` el comportamiento es el de siempre."""
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
        if clasificacion is not None:
            info = clasificacion.get(entrada.destino)
            if info is not None and info.get("estado") in (ESTADO_OK, ESTADO_OK_LEGACY):
                # R27/R27b: pristine (o legacy verificable) -> reconciliar con
                # el asset distribuido.
                return ACCION_ACTUALIZAR_MANAGED
            if info is None and entrada.destino != ".ds_init/control.json":
                # R27d: existente sin baseline -> el writer lo registra solo si
                # es idéntico al distribuido.
                return ACCION_ACTUALIZAR_MANAGED
        # R10: por defecto un archivo ya existente se omite, nunca se
        # sobrescribe (fuera de los casos MERGE/CLAUDE.md ya cubiertos).
        # Drift / algoritmo desconocido (R27c) y existente sin entrada
        # previa (R27d) caen acá: no se reescriben ni se adoptan.
        return ACCION_OMITIR_EXISTENTE

    if entrada.tratamiento == PLANTILLA:
        return ACCION_PLANTILLA
    if entrada.tratamiento in (VERBATIM, GENERADO):
        return ACCION_CREAR

    raise ValueError(f"tratamiento sin acción definida: {entrada.tratamiento!r}")


def construir_plan(
    perfil: str,
    destino: Path,
    config: dict,
    stage: str = None,
    capabilities_habilitadas=None,
    clasificacion=None,
) -> list:
    """Combina `manifest_para_perfil(perfil)` (o `manifest_para_perfil_y_stage`
    si se pasa `stage`, o `manifest_para_perfil_stage_y_capabilities` si
    además se pasa `capabilities_habilitadas`) + `detectar_colisiones` y arma
    la lista de `AccionPlan` (R3, R10, R4 de Change 7 v0.3; M8 de Change 4).

    `config` acepta la clave opcional `integrar_claude` (bool, default
    `False`) — corresponde al flag `--integrar-claude` de la CLI.

    `stage` (opcional, uno de `manifest.ORDEN_STAGES`): si es `None`
    (default), usa `manifest_para_perfil(perfil)` — comportamiento actual,
    sin cambios, para cualquier caller que no pase este parámetro. Si se
    pasa, usa `manifest_para_perfil_y_stage(perfil, stage)` en su lugar.

    `capabilities_habilitadas` (opcional, M8 -- hallazgo de hardening de
    Change 5: `manifest_para_perfil_stage_y_capabilities` ya existía desde
    Change 4 pero ningún llamador real la invocaba, dejando el filtro de
    capabilities inalcanzable desde la CLI real pese a estar completamente
    implementado y testeado a nivel unitario). `None` (default) preserva
    exactamente el comportamiento de arriba -- cero cambio para cualquier
    llamador que no lo pase. Si se pasa (iterable de strings), se usa
    SIEMPRE `manifest_para_perfil_stage_y_capabilities`, con `stage` resuelto
    al máximo de `ORDEN_STAGES` si no se pasó un `stage` explícito (el filtro
    de capabilities no tiene sentido sin alguna noción de stage, aunque sea
    el máximo -- nunca se intenta aplicar capabilities sobre
    `manifest_para_perfil` sin stage).

    `clasificacion` (opcional, R48; salida de `control.clasificar_baseline`,
    calculada por `sync` ANTES de escribir): `None` (default) deja el plan
    idéntico al histórico. Si se pasa, un destino existente (no MERGE ni
    CLAUDE.md) en estado `ok`/`ok_legacy` pasa a `ACCION_ACTUALIZAR_MANAGED`;
    en `drift`/`algoritmo_desconocido` se omite con una descripción que marca
    el drift preservado; sin entrada previa se omite como siempre."""
    if capabilities_habilitadas is not None:
        stage_efectivo = stage if stage is not None else ORDEN_STAGES[-1]
        entradas = manifest_para_perfil_stage_y_capabilities(perfil, stage_efectivo, capabilities_habilitadas)
    elif stage is None:
        entradas = manifest_para_perfil(perfil)
    else:
        entradas = manifest_para_perfil_y_stage(perfil, stage)
    destinos = [entrada.destino for entrada in entradas]
    colisiones = set(detectar_colisiones(destinos, Path(destino)))
    integrar_claude_md = bool(config.get("integrar_claude", False))

    plan = []
    for entrada in entradas:
        accion = _accion_para_entrada(entrada, colisiones, integrar_claude_md, clasificacion)
        descripcion = entrada.descripcion
        solo_si_identico = False
        if clasificacion is not None:
            info = clasificacion.get(entrada.destino)
            if info is not None and info.get("estado") in (ESTADO_DRIFT, ESTADO_ALG_DESCONOCIDO):
                if accion == ACCION_OMITIR_EXISTENTE:
                    descripcion = f"{DESCRIPCION_DRIFT_PRESERVADO} ({entrada.descripcion})".replace(" ()", "")
                elif accion == ACCION_MERGE:
                    descripcion = (
                        f"DRIFT preservado en baseline (el merge se aplica, la entrada no se adopta) "
                        f"({entrada.descripcion})"
                    ).replace(" ()", "")
            solo_si_identico = accion == ACCION_ACTUALIZAR_MANAGED and info is None
            if solo_si_identico:
                descripcion = (
                    f"{descripcion} (solo se registra si es idéntico al distribuido; no se sobrescribe)"
                )
        plan.append(
            AccionPlan(
                destino=entrada.destino,
                accion=accion,
                descripcion=descripcion,
                solo_si_identico=solo_si_identico,
            )
        )
    return plan


def formatear_plan(plan: list) -> str:
    """Representación de texto plano del plan, para `--dry-run` y para el
    reporte final de `--execute`."""
    lineas = [f"Plan de instalación ({len(plan)} entradas):"]
    for accion in plan:
        detalle = f" — {accion.descripcion}" if accion.descripcion else ""
        lineas.append(f"  [{accion.accion:22s}] {accion.destino}{detalle}")
    return "\n".join(lineas)
