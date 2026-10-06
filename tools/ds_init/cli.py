"""Interfaz de línea de comandos de `ds_init` (R3).

`accion` (`install`/`sync`, R7/R8/R11 de `spec.md` de Change 7 v0.3:
`20260915-progressive-capability-installation-and-scaffold`) es un
positional opcional, `default="install"` — preserva 100% la invocación plana
existente (`python -m tools.ds_init --destino X --nombre Y ...`, sin
`accion`), invariante dura de backward compatibility (R14).

`--dry-run` es el comportamiento por defecto: corre preflight + planner e
imprime el plan, sin tocar el disco del destino. `--execute` corre lo mismo y
además ejecuta la escritura real (`writer.py`: staging + journal + rollback,
R11) tras el preflight y la construcción del plan.

`install` instala un destino nuevo (`--stage discovery|experiment`, default
`experiment`). `sync` amplía un destino YA instalado hasta un `--stage`
objetivo (cualquiera de los 4), reconstruyendo placeholders desde
`.ds_init/control.json` en vez de pedir `--nombre`/etc. de nuevo.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import control as control_mod
from . import legacy as legacy_mod
from . import writer
from .manifest import (
    CAPABILITIES_CONOCIDAS,
    CAPABILITIES_VALIDAS,
    ORDEN_STAGES,
    capabilities_efectivas_sync,
    manifest_para_perfil_y_stage,
    raiz_repo_origen,
    validar_capabilities,
)
from .planner import construir_plan, formatear_plan
from .preflight import DestinoInvalidoError, validar_destino
from .version import HARNESS_VERSION

# Identificador público de CLI (R2). El mapeo a su directorio real bajo
# `profiles/` (con guion bajo, no se renombra) vive únicamente en
# `manifest.PERFILES` / `manifest.resolver_dir_perfil` — no se duplica acá.
PERFIL_MVP = "python-jupyter-data"

# Stages válidos para una instalación NUEVA (`install`): rechaza
# explícitamente `production_candidate`/`production` (R7 — evita bypass de
# madurez, un `init` nuevo nunca puede declararse "listo para producción").
STAGES_INSTALL_PERMITIDOS = ("discovery", "experiment")

STAGE_INSTALL_DEFAULT = "experiment"


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.ds_init",
        description="Inicializador/sincronizador del harness de agentes/tooling para proyectos "
        "de ciencia de datos (perfil python-jupyter-data).",
    )
    parser.add_argument(
        "accion",
        nargs="?",
        default="install",
        choices=["install", "sync"],
        help="Operación a realizar: 'install' (default, instala un destino nuevo) o 'sync' "
        "(amplía un destino ya instalado hasta un --stage objetivo mayor).",
    )
    parser.add_argument("--destino", required=True, help="Repo local destino (debe existir, ser Git, working tree limpio).")
    parser.add_argument(
        "--nombre",
        required=False,
        help="Nombre del proyecto, usado en placeholders de plantillas. Obligatorio para "
        "'install'; ignorado (se reconstruye desde control.json) para 'sync'.",
    )
    parser.add_argument("--notebooks-dir", default="notebooks", help="Directorio de notebooks del proyecto destino (default: notebooks, solo 'install').")
    parser.add_argument("--venv-dir", default=".venv", help="Directorio del entorno virtual del proyecto destino (default: .venv, solo 'install').")
    parser.add_argument("--integrar-claude", action="store_true", help="Integra un bloque delimitado en un CLAUDE.md ya existente (R9, solo 'install').")
    parser.add_argument(
        "--disable-capability",
        action="append",
        choices=list(CAPABILITIES_VALIDAS),
        default=None,
        metavar="CAPABILITY",
        help="Deshabilita una capability (M8, repetible) -- ninguna entrada del manifiesto "
        "declarada bajo esa capability se provisiona. Default: todas las capabilities "
        f"conocidas ({CAPABILITIES_CONOCIDAS}) habilitadas, comportamiento idéntico a no pasar "
        "este flag. Válido para 'install' y 'sync'. Nunca borra archivos ya instalados.",
    )
    parser.add_argument(
        "--enable-capability",
        action="append",
        choices=list(CAPABILITIES_VALIDAS),
        default=None,
        metavar="CAPABILITY",
        help="Habilita una capability (repetible). Las opt-in (data_cards, model_governance) "
        "están deshabilitadas por default; 'model_governance' requiere 'predictive_modeling'. "
        "Acepta también las históricas para re-habilitarlas de forma explícita. Válido para "
        "'install' y 'sync'.",
    )
    parser.add_argument(
        "--stage",
        choices=list(ORDEN_STAGES),
        default=None,
        help="Bundle de instalación progresiva objetivo. Para 'install': solo "
        f"{STAGES_INSTALL_PERMITIDOS} (default {STAGE_INSTALL_DEFAULT!r}). Para 'sync': "
        f"cualquiera de {ORDEN_STAGES} (obligatorio).",
    )

    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--dry-run", action="store_true", help="Informa el plan, no escribe nada (comportamiento por defecto).")
    modo.add_argument("--execute", action="store_true", help="Ejecuta la escritura real, tras preflight exitoso.")

    return parser


def _contexto_placeholders(nombre, notebooks_dir, venv_dir) -> dict:
    return {
        "NOMBRE_PROYECTO": nombre,
        "NOTEBOOKS_DIR": notebooks_dir,
        "VENV_DIR": venv_dir,
        "FECHA_INSTALACION": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "HARNESS_VERSION": HARNESS_VERSION,
        # Lista dura de rutas siempre-prohibidas de tools/nbrunner/manifest.py
        # en el proyecto destino (R6/§3 de design.md): vacía por defecto, cada
        # proyecto la completa a mano según sus propios datasets sensibles.
        "RUTAS_PROHIBIDAS_JSON": "[]",
    }


def _imprimir_omitidos(omitidos, perfil: str, stage: str) -> None:
    """Mensaje de colisión enriquecido (R20 de B5): para cada destino omitido
    por colisión con un archivo ya existente en el destino, informa además
    tipo de conflicto (tratamiento que Harmessi quería aplicar), el asset
    (descripción de la `EntradaManifiesto`) y las alternativas soportadas.
    Nunca mueve/renombra nada -- solo imprime más información sobre una
    decisión (no sobrescribir) que `writer.py` ya tomó."""
    entradas_por_destino = {
        e.destino: e for e in manifest_para_perfil_y_stage(perfil, stage)
    }
    print("Omitidos (ya existían en el destino, sin sobrescribir):")
    for ruta_relativa in omitidos:
        entrada = entradas_por_destino.get(ruta_relativa)
        print(f"  {ruta_relativa}")
        if entrada is not None:
            print(
                f"    tipo de conflicto: archivo ya existe (Harmessi quería aplicar "
                f"tratamiento {entrada.tratamiento!r})"
            )
            if entrada.descripcion:
                print(f"    asset que Harmessi quería instalar: {entrada.descripcion}")
            print(
                "    alternativas: si es intencional, el archivo del usuario queda intacto "
                "(nunca se sobrescribe); para customizar en vez de reemplazar, usá project "
                "config/local override (M10, .harmessi/project-config.json / "
                ".harmessi/local-overrides.json) si esa entrada lo soporta; resolución manual "
                "si hace falta reconciliar a mano."
            )


def _rechazar_flags_contradictorios(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Una misma capability en `--enable-capability` y `--disable-capability`
    es ambigua (install y sync resolverían distinto): se rechaza (exit 2)."""
    contradictorias = sorted(set(args.enable_capability or []) & set(args.disable_capability or []))
    if contradictorias:
        parser.error(
            "capability(s) en --enable-capability y --disable-capability a la vez: "
            + ", ".join(contradictorias)
        )


def _main_install(parser: argparse.ArgumentParser, args: argparse.Namespace, destino: Path) -> int:
    _rechazar_flags_contradictorios(parser, args)

    # Set de install: (históricas - disable) | enable. Sin flags: idéntico a v0.8.
    capabilities_habilitadas = (
        frozenset(CAPABILITIES_CONOCIDAS) - frozenset(args.disable_capability or [])
    ) | frozenset(args.enable_capability or [])
    errores_capabilities = validar_capabilities(capabilities_habilitadas)
    if errores_capabilities:
        # Antes de cualquier escritura (R4): exit 2.
        parser.error("; ".join(errores_capabilities))

    if not args.nombre:
        parser.error("--nombre es obligatorio para 'install'")

    stage = args.stage or STAGE_INSTALL_DEFAULT
    if stage not in STAGES_INSTALL_PERMITIDOS:
        parser.error(
            f"--stage {stage!r} no es válido para una instalación nueva (solo "
            f"{STAGES_INSTALL_PERMITIDOS}) — 'production_candidate'/'production' requieren "
            "capacidades ya sincronizadas sobre un destino existente, ver 'sync'."
        )

    try:
        validar_destino(destino)
    except DestinoInvalidoError as exc:
        print(f"[ABORTADO] {exc}", file=sys.stderr)
        return 1

    config = {
        "perfil": PERFIL_MVP,
        "nombre": args.nombre,
        "notebooks_dir": args.notebooks_dir,
        "venv_dir": args.venv_dir,
        "destino": args.destino,
        "integrar_claude": args.integrar_claude,
        "stage": stage,
        "placeholders": _contexto_placeholders(args.nombre, args.notebooks_dir, args.venv_dir),
        "capabilities_habilitadas": sorted(capabilities_habilitadas),
    }

    plan = construir_plan(PERFIL_MVP, destino, config, stage=stage, capabilities_habilitadas=capabilities_habilitadas)
    print(formatear_plan(plan))

    if args.execute:
        try:
            resultado = writer.instalar(plan, destino, config)
        except writer.InstalacionAbortadaError as exc:
            print(f"[ABORTADO] {exc}", file=sys.stderr)
            return 1
        print(
            f"\n[EXECUTE] Instalación completa ({stage}): {len(resultado.aplicados)} archivo(s) "
            f"aplicado(s), {len(resultado.omitidos)} omitido(s) por colisión existente."
        )
        if resultado.omitidos:
            _imprimir_omitidos(resultado.omitidos, PERFIL_MVP, stage)
        print(f"Archivo de control: {resultado.control_path}")
        return 0

    print("\n[DRY-RUN] No se escribió ni modificó ningún archivo del destino.")
    return 0


def _main_sync(parser: argparse.ArgumentParser, args: argparse.Namespace, destino: Path) -> int:
    if not args.stage:
        parser.error(f"'sync' requiere --stage <{'|'.join(ORDEN_STAGES)}>")
    target = args.stage

    ruta_control = destino / control_mod.DIR_CONTROL / control_mod.NOMBRE_ARCHIVO_CONTROL
    if not ruta_control.exists():
        print(
            f"[ABORTADO] No existe {ruta_control}: correr una instalación inicial primero "
            "('python -m tools.ds_init install --destino ... --nombre ...').",
            file=sys.stderr,
        )
        return 1

    try:
        control_previo = json.loads(ruta_control.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[ABORTADO] No se pudo leer/parsear {ruta_control}: {exc}", file=sys.stderr)
        return 1

    perfil = control_previo.get("perfil") or PERFIL_MVP

    stage_base = control_previo.get("installation_stage")
    if stage_base is None:
        stage_base = legacy_mod.inferir_installation_stage(destino, perfil)

    _rechazar_flags_contradictorios(parser, args)

    # Set efectivo de sync (R5) y validación ANTES de cualquier escritura (R4).
    persistidas = control_previo.get("capabilities_habilitadas")
    if persistidas is not None:
        if not isinstance(persistidas, list) or not all(isinstance(c, str) for c in persistidas):
            parser.error("control.json persistido inválido: capabilities_habilitadas debe ser una lista de strings")
        errores_persistidos = validar_capabilities(persistidas)
        if errores_persistidos:
            # La dependencia nunca se satisface en silencio, ni siquiera sin flags.
            parser.error(
                "control.json persistido inválido: "
                + "; ".join(errores_persistidos)
                + ". Corregí capabilities_habilitadas en control.json o habilitá las "
                "capabilities requeridas de forma explícita."
            )
    capabilities_habilitadas = capabilities_efectivas_sync(
        persistidas, args.enable_capability, args.disable_capability
    )
    errores_capabilities = validar_capabilities(capabilities_habilitadas)
    if errores_capabilities:
        if "predictive_modeling" in (args.disable_capability or []):
            sugerencia = (
                " Causa: --disable-capability predictive_modeling explícito; no la "
                "deshabilites mientras 'model_governance' esté habilitada."
            )
        else:
            sugerencia = (
                " Si 'predictive_modeling' está deshabilitada en lo persistido, habilitala "
                "de forma explícita: sync --enable-capability predictive_modeling "
                "--enable-capability model_governance"
            )
        parser.error("; ".join(errores_capabilities) + "." + sugerencia)

    # Set persistido tal como se interpreta hoy (R12: sin lista = históricas).
    persistidas_efectivas = (
        frozenset(persistidas) if persistidas is not None else frozenset(CAPABILITIES_CONOCIDAS)
    )
    hay_flags_capability = bool(args.enable_capability or args.disable_capability)
    cambia_capabilities = hay_flags_capability and capabilities_habilitadas != persistidas_efectivas

    # R6: `<` siempre "nada que hacer"; `==` procede solo si flags explícitos
    # cambian el set efectivo respecto del persistido.
    indice_target = ORDEN_STAGES.index(target)
    indice_base = ORDEN_STAGES.index(stage_base)
    if indice_target < indice_base or (indice_target == indice_base and not cambia_capabilities):
        print(
            f"[SYNC] El destino ya está instalado en un stage igual o superior a {target!r} "
            f"(actual: {stage_base!r}) — nada que hacer."
        )
        if hay_flags_capability:
            print(
                "[SYNC] AVISO: los flags de capability se ignoraron: "
                f"enable={sorted(args.enable_capability or [])}, "
                f"disable={sorted(args.disable_capability or [])} (stage objetivo menor, o "
                "igual sin cambio en el set efectivo)."
            )
        return 0

    try:
        validar_destino(destino)
    except DestinoInvalidoError as exc:
        print(f"[ABORTADO] {exc}", file=sys.stderr)
        return 1

    configuracion_previa = control_previo.get("configuracion") or {}
    nombre = configuracion_previa.get("nombre")
    notebooks_dir = configuracion_previa.get("notebooks_dir")
    venv_dir = configuracion_previa.get("venv_dir")

    config = {
        "perfil": perfil,
        "nombre": nombre,
        "notebooks_dir": notebooks_dir,
        "venv_dir": venv_dir,
        "destino": args.destino,
        "integrar_claude": False,
        "stage": target,
        "placeholders": _contexto_placeholders(nombre, notebooks_dir, venv_dir),
        "capabilities_habilitadas": sorted(capabilities_habilitadas),
    }

    plan = construir_plan(perfil, destino, config, stage=target, capabilities_habilitadas=capabilities_habilitadas)
    print(formatear_plan(plan))

    if not args.execute:
        print("\n[DRY-RUN] No se escribió ni modificó ningún archivo del destino.")
        return 0

    try:
        resultado = writer.instalar(plan, destino, config)
    except writer.InstalacionAbortadaError as exc:
        print(f"[ABORTADO] {exc}", file=sys.stderr)
        return 1

    # `writer.instalar` ya generó un control.json consistente con el delta de
    # esta corrida (R5); lo completamos con el set ACUMULADO completo hasta
    # `target` (archivos de corridas anteriores + los recién agregados), vía
    # `regenerar_control` (design.md §5) — nunca reescribe `writer.py`. Este
    # paso corre DESPUÉS de que `writer.instalar` ya aplicó los archivos al
    # destino con éxito (con su propio rollback ya completado si algo hubiera
    # fallado ahí) — un fallo ACÁ no puede revertirse con el mismo mecanismo
    # (los archivos ya están aplicados correctamente), así que se informa de
    # forma explícita y no ambigua en vez de dejar escapar la excepción o
    # imprimir el mensaje de éxito de todas formas.
    try:
        control_recien_escrito = json.loads(ruta_control.read_text(encoding="utf-8"))
        control_mod.regenerar_control(
            destino,
            control_recien_escrito,
            perfil=perfil,
            stage=target,
            installation_stage=target,
            capabilities_habilitadas=capabilities_habilitadas,
        )
    except Exception as exc:  # noqa: BLE001 - fallo real, nunca debe pasar desapercibido
        print(
            f"[ABORTADO-PARCIAL] Los archivos de '{target}' se instalaron correctamente en el "
            f"destino, pero no se pudo completar el registro acumulado en "
            f"{ruta_control}: {exc}. control.json puede haber quedado con 'archivos' "
            f"incompleto (le faltan entradas de corridas anteriores a esta). Revisar "
            f"{ruta_control} a mano, o volver a correr 'sync --stage {target} --execute' "
            f"(idempotente: los archivos ya presentes se omiten, solo se reintenta la "
            f"reconciliación de control.json).",
            file=sys.stderr,
        )
        return 1

    print(
        f"\n[EXECUTE] Sync completo ({stage_base!r} -> {target!r}): {len(resultado.aplicados)} "
        f"archivo(s) aplicado(s), {len(resultado.omitidos)} omitido(s) por colisión existente."
    )
    if resultado.omitidos:
        _imprimir_omitidos(resultado.omitidos, perfil, target)
    print(f"Archivo de control: {resultado.control_path}")
    return 0


def main(argv: list = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)

    destino = Path(args.destino)

    if args.accion == "install":
        return _main_install(parser, args, destino)
    if args.accion == "sync":
        return _main_sync(parser, args, destino)

    parser.error(f"acción desconocida: {args.accion!r}")
    return 2  # inalcanzable: parser.error() ya hizo sys.exit(2)


if __name__ == "__main__":
    sys.exit(main())
