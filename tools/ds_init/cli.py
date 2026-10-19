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
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import control as control_mod
from . import legacy as legacy_mod
from . import lock as lock_mod
from . import recover as recover_mod
from . import writer
from .manifest import (
    CAPABILITIES_CONOCIDAS,
    CAPABILITIES_VALIDAS,
    EXCLUSIONES_PERMANENTES,
    MERGE,
    ORDEN_STAGES,
    PLANTILLA,
    capabilities_efectivas_sync,
    manifest_para_perfil_stage_y_capabilities,
    manifest_para_perfil_y_stage,
    raiz_repo_origen,
    validar_capabilities,
)
from .managed_hash import ESTADO_ALG_DESCONOCIDO, ESTADO_DRIFT, ESTADO_OK, ESTADO_OK_LEGACY
from .planner import (
    ACCION_ACTUALIZAR_MANAGED,
    ACCION_CREAR,
    ACCION_MERGE,
    ACCION_PLANTILLA,
    AccionPlan,
    construir_plan,
    formatear_plan,
)
from .preflight import DestinoInvalidoError, _detectar_staging_huerfano, validar_destino
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

# Estados de clasificación de baseline que `sync` trata como drift preservado.
_ESTADOS_DRIFT = (ESTADO_DRIFT, ESTADO_ALG_DESCONOCIDO)


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
        choices=["install", "sync", "migrate-hashes", "upgrade", "recover"],
        help="Operación a realizar: 'install' (default, instala un destino nuevo), 'recover' "
        "(revierte una operación interrumpida desde su journal; dry-run por defecto), 'upgrade' "
        "(actualiza los archivos managed pristine a la versión actual del harness; dry-run por "
        "defecto, --execute para aplicar), 'sync' "
        "(amplía un destino ya instalado hasta un --stage objetivo mayor) o 'migrate-hashes' "
        "(migra al algoritmo de hash vigente las entradas legacy que verifican; dry-run por "
        "defecto, --execute para aplicar).",
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
            with lock_mod.lock_instalacion(destino, "install"):
                resultado = writer.instalar(plan, destino, config)
        except (writer.InstalacionAbortadaError, lock_mod.LockOcupadoError) as exc:
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
        # R27f: el instalador recibe el baseline previo para no perderlo.
        "entradas_conservadas": list(control_previo.get("archivos") or []),
    }

    # M-A (R27): se clasifica contra el baseline ANTERIOR, antes de escribir.
    clasificacion = control_mod.clasificar_baseline(destino, control_previo)

    # A1: rutas con drift (o algoritmo desconocido): el instalador no las hashea.
    rutas_drift = {
        ruta for ruta, info in clasificacion.items() if (info or {}).get("estado") in _ESTADOS_DRIFT
    }
    config["rutas_drift"] = sorted(rutas_drift)

    plan = construir_plan(
        perfil,
        destino,
        config,
        stage=target,
        capabilities_habilitadas=capabilities_habilitadas,
        clasificacion=clasificacion,
    )
    # Rutas MERGE sobre archivo existente sin baseline utilizable: no son
    # drift (no se informan como tal) pero tampoco se hashean/adoptan en el
    # control intermedio del instalador.
    merge_sin_baseline = {
        a.destino for a in plan if a.accion == ACCION_MERGE and clasificacion.get(a.destino) is None
    }
    config["rutas_drift"] = sorted(rutas_drift | merge_sin_baseline)
    # Rutas que ya existían en disco ANTES de la corrida (para que
    # `regenerar_control` no adopte un MERGE sobre archivo sin baseline).
    preexistentes = {a.destino for a in plan if (destino / a.destino).exists()}
    print(formatear_plan(plan))

    if not args.execute:
        print("\n[DRY-RUN] No se escribió ni modificó ningún archivo del destino.")
        return 0

    # `regenerar_control` (design.md §5) completa el control con el set
    # ACUMULADO hasta `target`. Desde v0.11 (Change 5) corre DENTRO de la
    # transacción de `writer.instalar` (hook `post_aplicar`, fase journal
    # "control_pendiente"): si falla, se revierte todo (archivos y control) en
    # vez de dejar un estado parcial.
    def _regenerar(resultado_tx):
        # Modo conservador (R28): se pasa el control PREVIO original y la
        # clasificación calculada antes de escribir; el drift se conserva tal cual.
        control_mod.regenerar_control(
            destino,
            control_previo,
            perfil=perfil,
            stage=target,
            installation_stage=target,
            capabilities_habilitadas=capabilities_habilitadas,
            clasificacion=clasificacion,
            resultado=resultado_tx,
            preexistentes=preexistentes,
        )

    config["post_aplicar"] = _regenerar
    try:
        with lock_mod.lock_instalacion(destino, "sync"):
            resultado = writer.instalar(plan, destino, config)
    except (writer.InstalacionAbortadaError, lock_mod.LockOcupadoError) as exc:
        print(f"[ABORTADO] {exc}", file=sys.stderr)
        return 1

    print(
        f"\n[EXECUTE] Sync completo ({stage_base!r} -> {target!r}): {len(resultado.aplicados)} "
        f"archivo(s) aplicado(s), {len(resultado.omitidos)} omitido(s) por colisión existente, "
        f"{len(resultado.actualizados)} actualizado(s), {len(resultado.sin_cambios)} sin cambios."
    )
    # M5: drift preservado para TODA ruta del plan, incluidas las MERGE que sí se mergearon.
    drift_preservado = [a.destino for a in plan if a.destino in rutas_drift]
    for ruta in drift_preservado:
        if ruta in resultado.omitidos:
            print(
                f"DRIFT preservado: {ruta} — modificado respecto del baseline; sync no lo reescribió "
                "ni lo adoptó; revisá el cambio o reinstalá el asset explícitamente"
            )
        else:
            print(
                f"DRIFT preservado: {ruta} — modificado respecto del baseline; se aplicó el merge "
                "funcional pero sync no adoptó el archivo (la entrada previa del baseline se "
                "conserva); revisá el cambio o reinstalá el asset explícitamente"
            )
    if resultado.actualizados:
        print("Actualizados (pristine con nueva versión distribuida):")
        for ruta in resultado.actualizados:
            print(f"  {ruta}")
    if resultado.sin_cambios:
        print(f"Sin cambios (contenido distribuido idéntico al actual): {len(resultado.sin_cambios)} archivo(s)")
    omitidos_otros = [r for r in resultado.omitidos if r not in drift_preservado]
    if omitidos_otros:
        _imprimir_omitidos(omitidos_otros, perfil, target)
    print(f"Archivo de control: {resultado.control_path}")
    return 0


def _main_migrate_hashes(args: argparse.Namespace, destino: Path) -> int:
    """`migrate-hashes` (R20-R26): migra al algoritmo vigente SOLO las entradas
    legacy que verifican. Dry-run por defecto. No es re-adopción: no pide
    `--usuario` ni aprobación y el drift persiste."""
    ruta_control = destino / control_mod.DIR_CONTROL / control_mod.NOMBRE_ARCHIVO_CONTROL
    if not ruta_control.exists():
        print(f"[ABORTADO] No existe {ruta_control}: nada que migrar.", file=sys.stderr)
        return 1

    try:
        informe = control_mod.migrar_hashes(destino, ejecutar=bool(args.execute))
    except (OSError, ValueError) as exc:
        print(f"[ABORTADO] No se pudo migrar los hashes: {exc}", file=sys.stderr)
        return 1

    def _etiqueta(item) -> str:
        if isinstance(item, dict):
            ruta = item.get("ruta", "")
            detalle = item.get("detalle")
            return f"{ruta} — {detalle}" if detalle else str(ruta)
        if isinstance(item, (tuple, list)) and len(item) == 2:
            return f"{item[0]} — {item[1]}"
        return str(item)

    modo = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"[{modo}] migrate-hashes")
    secciones = (
        ("Migradas" if args.execute else "Migrables", informe.migradas),
        ("Ya actuales", informe.ya_actuales),
        ("No verificables (drift persiste, no se tocan)", informe.no_verificables),
        ("Desconocidas (algoritmo desconocido, fail-closed)", informe.desconocidas),
    )
    for titulo, items in secciones:
        print(f"{titulo}: {len(items)}")
        for item in items:
            print(f"  {_etiqueta(item)}")
    if not args.execute:
        print("\n[DRY-RUN] No se escribió control.json. Usá --execute para aplicar la migración.")
    return 0


# ---------------------------------------------------------------------------
# upgrade (v0.11 Change 5, R2/R3/R7)
# ---------------------------------------------------------------------------

ACCION_REPORTAR_DRIFT = "reportar-drift"
_RUTA_CONTROL_MANIFEST = ".ds_init/control.json"
# Rutas del proyecto que, si ya existen, upgrade nunca sobrescribe aunque el
# manifest las distribuya (R10 del manifest: guardrails.json customizable).
_RUTAS_NUNCA_SOBRESCRIBIR = ("CLAUDE.md", ".claude/guardrails.json")


@dataclass
class _PlanUpgrade:
    """Resultado de calcular un upgrade (sin mutar el destino)."""

    plan: list = field(default_factory=list)  # AccionPlan que va a writer.instalar
    actualizar: list = field(default_factory=list)
    crear: list = field(default_factory=list)
    drift: list = field(default_factory=list)
    preservados: list = field(default_factory=list)  # (ruta, motivo)
    bloqueantes: list = field(default_factory=list)
    clasificacion: dict = field(default_factory=dict)
    version_distinta: bool = False

    @property
    def hay_cambios(self) -> bool:
        return bool(self.plan) or self.version_distinta


def _calcular_plan_upgrade(
    destino: Path, control_previo: dict, perfil: str, stage: str, capabilities, placeholders: dict
) -> _PlanUpgrade:
    """Calcula (sin escribir en el destino) qué haría `upgrade`. Reusa
    `writer._armar_staging` sobre un directorio temporal EXTERNO al destino,
    de modo que dry-run y execute decidan exactamente igual qué cambia."""
    resultado = _PlanUpgrade()
    resultado.version_distinta = control_previo.get("harness_version") != HARNESS_VERSION
    resultado.clasificacion = control_mod.clasificar_baseline(destino, control_previo)
    rutas_baseline = {
        e["ruta"]
        for e in (control_previo.get("archivos") or [])
        if isinstance(e, dict) and isinstance(e.get("ruta"), str)
    }

    entradas = manifest_para_perfil_stage_y_capabilities(perfil, stage, capabilities)
    entradas_por_destino = {e.destino: e for e in entradas}
    candidatos = []
    for entrada in entradas:
        rel = entrada.destino
        if rel == _RUTA_CONTROL_MANIFEST:
            continue
        if any(rel == x or rel.startswith(x) for x in EXCLUSIONES_PERMANENTES):
            continue  # nunca (project-owned / exclusiones permanentes)
        existe = (destino / rel).exists()
        info = resultado.clasificacion.get(rel)
        estado = info.get("estado") if info else None

        if entrada.tratamiento == MERGE:
            # settings.json: solo merge (si no existe se crea).
            accion = ACCION_MERGE if existe else ACCION_CREAR
            candidatos.append(AccionPlan(rel, accion, entrada.descripcion))
        elif rel in _RUTAS_NUNCA_SOBRESCRIBIR:
            if existe:
                resultado.preservados.append((rel, "archivo del proyecto, nunca se sobrescribe"))
            elif rel in rutas_baseline:
                resultado.preservados.append((rel, "ausente del disco pero en el baseline; no se recrea"))
            else:
                candidatos.append(AccionPlan(rel, ACCION_CREAR, entrada.descripcion))
        elif existe:
            if estado in (ESTADO_OK, ESTADO_OK_LEGACY):
                candidatos.append(AccionPlan(rel, ACCION_ACTUALIZAR_MANAGED, entrada.descripcion))
            elif estado in _ESTADOS_DRIFT:
                resultado.drift.append(rel)
            else:
                resultado.preservados.append((rel, "existente sin baseline; no se toca ni se adopta"))
        elif rel in rutas_baseline:
            resultado.preservados.append((rel, "ausente del disco pero en el baseline; no se recrea"))
        else:
            accion = ACCION_PLANTILLA if entrada.tratamiento == PLANTILLA else ACCION_CREAR
            candidatos.append(AccionPlan(rel, accion, entrada.descripcion))

    tmp = Path(tempfile.mkdtemp(prefix="ds_init_upgrade_calc_"))
    try:
        try:
            journal, _omitidos, actualizados, _sin_cambios = writer._armar_staging(
                candidatos, entradas_por_destino, destino, tmp, placeholders
            )
            writer._validar_staging(tmp)
        except Exception as exc:  # staging inválido, merge incompatible, E/S
            resultado.bloqueantes.append(f"{type(exc).__name__}: {exc}")
            return resultado
        reales = set(actualizados)
        merges_cambiados = []
        for entrada_j in journal:
            rel = entrada_j["destino"]
            if rel in actualizados:
                continue
            if entrada_j["accion"] == writer.ACCION_JOURNAL_CREAR:
                reales.add(rel)
                resultado.crear.append(rel)
            else:  # merge (settings.json): solo si cambia el contenido
                if (tmp / rel).read_bytes() != (destino / rel).read_bytes():
                    reales.add(rel)
                    merges_cambiados.append(rel)
        resultado.actualizar = sorted(actualizados) + merges_cambiados
        resultado.plan = [a for a in candidatos if a.destino in reales]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return resultado


def _imprimir_plan_upgrade(plan_up: _PlanUpgrade, version_instalada) -> None:
    print(f"[UPGRADE] Versión instalada: {version_instalada!r} | versión disponible: {HARNESS_VERSION!r}")
    print(
        f"Resumen: a actualizar {len(plan_up.actualizar)}, a crear {len(plan_up.crear)}, "
        f"drift {len(plan_up.drift)}, preservados {len(plan_up.preservados)}, "
        f"bloqueantes {len(plan_up.bloqueantes)}"
    )
    for ruta in plan_up.actualizar:
        print(f"  [{ACCION_ACTUALIZAR_MANAGED:18s}] {ruta}")
    for ruta in plan_up.crear:
        print(f"  [{ACCION_CREAR:18s}] {ruta}")
    for ruta in plan_up.drift:
        print(f"  [{ACCION_REPORTAR_DRIFT:18s}] {ruta} — modificado respecto del baseline; upgrade no lo toca ni lo adopta")
    for ruta, motivo in plan_up.preservados:
        print(f"  [preservado        ] {ruta} — {motivo}")
    for bloqueante in plan_up.bloqueantes:
        print(f"  [BLOQUEANTE] {bloqueante}")


def _main_upgrade(parser: argparse.ArgumentParser, args: argparse.Namespace, destino: Path) -> int:
    if args.stage or args.enable_capability or args.disable_capability:
        parser.error(
            "'upgrade' no acepta --stage/--enable-capability/--disable-capability: usa el "
            "stage y las capabilities persistidos en control.json (para ampliarlos, 'sync')"
        )

    ruta_control = destino / control_mod.DIR_CONTROL / control_mod.NOMBRE_ARCHIVO_CONTROL
    if not ruta_control.exists():
        print(f"[ABORTADO] No existe {ruta_control}: nada que actualizar (correr 'install' primero).", file=sys.stderr)
        return 1
    try:
        control_previo = json.loads(ruta_control.read_text(encoding="utf-8"))
        if not isinstance(control_previo, dict) or not isinstance(control_previo.get("configuracion"), dict):
            raise ValueError("estructura inesperada (se esperaba un objeto con 'configuracion')")
    except (OSError, ValueError) as exc:
        print(f"[ABORTADO] control.json ilegible o inválido ({ruta_control}): {exc}", file=sys.stderr)
        return 2

    # Staging / journal huérfano: la transacción anterior quedó a medias.
    huerfanos = _detectar_staging_huerfano(destino)
    if huerfanos:
        print(
            f"[ABORTADO] Hay staging/journal huérfano ({', '.join(huerfanos)}): una operación "
            f"anterior quedó interrumpida. Ejecutar primero: python -m tools.ds_init recover "
            f"--destino {destino}",
            file=sys.stderr,
        )
        return 1

    perfil = control_previo.get("perfil") or PERFIL_MVP
    stage = control_previo.get("installation_stage")
    if stage is None:
        stage = legacy_mod.inferir_installation_stage(destino, perfil)
    if stage not in ORDEN_STAGES:
        print(f"[ABORTADO] installation_stage inválido en control.json: {stage!r}", file=sys.stderr)
        return 2

    persistidas = control_previo.get("capabilities_habilitadas")
    if persistidas is not None:
        if not isinstance(persistidas, list) or not all(isinstance(c, str) for c in persistidas):
            print("[ABORTADO] control.json inválido: capabilities_habilitadas debe ser lista de strings", file=sys.stderr)
            return 2
        errores = validar_capabilities(persistidas)
        if errores:
            print("[ABORTADO] control.json inválido: " + "; ".join(errores), file=sys.stderr)
            return 2
    capabilities = frozenset(persistidas) if persistidas is not None else frozenset(CAPABILITIES_CONOCIDAS)

    try:
        validar_destino(destino)
    except DestinoInvalidoError as exc:
        print(f"[ABORTADO] {exc}", file=sys.stderr)
        return 1

    conf = control_previo["configuracion"]
    nombre, notebooks_dir, venv_dir = conf.get("nombre"), conf.get("notebooks_dir"), conf.get("venv_dir")
    placeholders = _contexto_placeholders(nombre, notebooks_dir, venv_dir)
    # La fecha de instalación original se conserva: si no, toda plantilla que
    # la use cambiaría en cada corrida (rompe idempotencia, R7).
    if control_previo.get("fecha_utc"):
        placeholders["FECHA_INSTALACION"] = control_previo["fecha_utc"]
    version_instalada = control_previo.get("harness_version")

    def _calcular() -> _PlanUpgrade:
        return _calcular_plan_upgrade(destino, control_previo, perfil, stage, capabilities, placeholders)

    try:
        plan_up = _calcular()
    except ValueError as exc:  # p. ej. perfil desconocido
        print(f"[ABORTADO] {exc}", file=sys.stderr)
        return 1
    _imprimir_plan_upgrade(plan_up, version_instalada)

    if plan_up.bloqueantes:
        print("[ABORTADO] Hay bloqueantes; no se aplica nada.", file=sys.stderr)
        return 1
    if not plan_up.hay_cambios:
        print("\n[UPGRADE] Nada que hacer: el destino ya está al día.")
        return 0
    if not args.execute:
        print("\n[DRY-RUN] No se escribió ni modificó ningún archivo del destino. Usá --execute para aplicar.")
        return 0

    try:
        with lock_mod.lock_instalacion(destino, "upgrade"):
            # Se recalcula con el lock tomado, antes de mutar.
            plan_up = _calcular()
            if plan_up.bloqueantes:
                print("[ABORTADO] Hay bloqueantes tras recalcular: " + "; ".join(plan_up.bloqueantes), file=sys.stderr)
                return 1
            if not plan_up.hay_cambios:
                print("\n[UPGRADE] Nada que hacer: el destino ya está al día.")
                return 0

            plan = plan_up.plan
            clasificacion = plan_up.clasificacion
            rutas_drift = {
                r for r, info in clasificacion.items() if (info or {}).get("estado") in _ESTADOS_DRIFT
            }
            merge_sin_baseline = {
                a.destino for a in plan if a.accion == ACCION_MERGE and clasificacion.get(a.destino) is None
            }
            preexistentes = {a.destino for a in plan if (destino / a.destino).exists()}
            config = {
                "perfil": perfil,
                "nombre": nombre,
                "notebooks_dir": notebooks_dir,
                "venv_dir": venv_dir,
                "destino": args.destino,
                "integrar_claude": False,
                "stage": stage,
                "placeholders": placeholders,
                "capabilities_habilitadas": sorted(persistidas) if persistidas is not None else None,
                "entradas_conservadas": list(control_previo.get("archivos") or []),
                "rutas_drift": sorted(rutas_drift | merge_sin_baseline),
            }

            def _regenerar(resultado_tx):
                # Dentro de la transacción: harness_version queda actualizada.
                control_mod.regenerar_control(
                    destino,
                    control_previo,
                    perfil=perfil,
                    stage=stage,
                    installation_stage=stage,
                    capabilities_habilitadas=persistidas,
                    clasificacion=clasificacion,
                    resultado=resultado_tx,
                    preexistentes=preexistentes,
                )

            config["post_aplicar"] = _regenerar
            resultado = writer.instalar(plan, destino, config)
    except (writer.InstalacionAbortadaError, lock_mod.LockOcupadoError) as exc:
        print(f"[ABORTADO] {exc}", file=sys.stderr)
        return 1

    print(
        f"\n[EXECUTE] Upgrade completo ({version_instalada!r} -> {HARNESS_VERSION!r}): "
        f"{len(resultado.actualizados)} actualizado(s), "
        f"{len(resultado.aplicados) - len(resultado.actualizados)} creado(s)/mergeado(s), "
        f"{len(plan_up.drift)} con drift preservado."
    )
    print(f"Archivo de control: {resultado.control_path}")
    return 0


def _main_recover(destino: Path, execute: bool) -> int:
    """`recover` (R4): revierte una transacción interrumpida al estado previo.
    Dry-run por defecto. Exit 2 (sin tocar nada) si un journal es ilegible o
    falta un backup necesario."""
    if not destino.is_dir():
        print(f"[ABORTADO] El destino no existe o no es un directorio: {destino}", file=sys.stderr)
        return 1
    estado = recover_mod.detectar(destino)
    if estado.vacio:
        print("[RECOVER] Nada que recuperar: no hay journal ni staging huérfano.")
        return 0

    print(f"[RECOVER] {len(estado.journals)} journal(s), {len(estado.staging)} staging(s) huérfano(s):")
    for info in estado.journals:
        for linea in recover_mod.describir(info, destino):
            print(linea)
    for staging in estado.staging:
        print(f"Staging {staging}: se eliminará")
    if lock_mod.ruta_lock(destino).exists():
        print(
            f"AVISO: existe {lock_mod.ruta_lock(destino)}. Si ningún proceso de ds_init está en "
            "ejecución, borrarlo a mano antes de --execute."
        )

    if estado.problemas:
        for p in estado.problemas:
            print(f"[PROBLEMA] {p}", file=sys.stderr)
        print("[ABORTADO] " + recover_mod.instruccion_manual(estado), file=sys.stderr)
        return 2

    if not execute:
        print("\n[DRY-RUN] No se escribió ni modificó nada. Usá --execute para aplicar el recover.")
        return 0

    try:
        with lock_mod.lock_instalacion(destino, "recover"):
            fallos = recover_mod.ejecutar(destino, estado)
    except lock_mod.LockOcupadoError as exc:
        print(f"[ABORTADO] {exc}", file=sys.stderr)
        return 1
    if fallos:
        detalle = "; ".join(f"{f['destino']} ({f['error']})" for f in fallos)
        print(
            f"[ABORTADO] No se pudo revertir por completo: {detalle}. El journal se conservó; "
            "resolver a mano esas rutas desde su carpeta backups/ y reintentar.",
            file=sys.stderr,
        )
        return 1
    print("\n[EXECUTE] Recover completo: destino restaurado y journal/staging eliminados.")
    return 0


def main(argv: list = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)

    destino = Path(args.destino)

    if args.accion == "install":
        return _main_install(parser, args, destino)
    if args.accion == "sync":
        return _main_sync(parser, args, destino)
    if args.accion == "migrate-hashes":
        return _main_migrate_hashes(args, destino)
    if args.accion == "upgrade":
        return _main_upgrade(parser, args, destino)
    if args.accion == "recover":
        return _main_recover(destino, bool(args.execute))

    parser.error(f"acción desconocida: {args.accion!r}")
    return 2  # inalcanzable: parser.error() ya hizo sys.exit(2)


if __name__ == "__main__":
    sys.exit(main())
