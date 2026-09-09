"""Escritura real de la instalación (`--execute`, R11): staging temporal
dentro del destino, validación, journal con backups, aplicación atómica y
rollback en reversa ante cualquier fallo.

Flujo de `instalar()` (`design.md` §5):

1. Crea `<destino>/.ds_init_staging_<timestamp>/` y arma ahí el árbol
   completo (verbatim + plantillas renderizadas + settings.json fusionado +
   CLAUDE.md resuelto), sin tocar `.ds_init/control.json` (se genera aparte,
   después de aplicar, vía `control.generar_control`).
2. Valida el staging completo: JSON parseable, sin placeholders `{{...}}`
   pendientes, ninguna ruta de exclusión permanente (R7), ninguna cadena
   prohibida (R17). Si algo falla: borra el staging, no toca el destino.
3. Si la validación pasa: arma un journal (orden de aplicación + backups de
   todo lo que se va a reemplazar/fusionar) y aplica cada entrada con
   `os.replace`.
4. Si una excepción interrumpe la aplicación: revierte en orden inverso lo ya
   aplicado (borra lo creado, restaura los backups) y borra el staging — el
   destino queda igual que antes de `--execute`.
5. Si todo aplica sin excepciones: borra el staging y genera
   `.ds_init/control.json`.
"""
from __future__ import annotations

import json
import os
import shutil
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import control as control_mod
from .manifest import (
    EXCLUSIONES_PERMANENTES,
    GENERADO,
    MERGE,
    PLANTILLA,
    VERBATIM,
    manifest_para_perfil,
    raiz_repo_origen,
)
from .planner import ACCION_MERGE, ACCION_OMITIR_EXISTENTE
from .settings_merge import fusionar
from .templating import (
    insertar_bloque_claude_md,
    renderizar,
    verificar_sin_placeholders_pendientes,
)

# Cadenas cuya sola presencia en cualquier archivo de staging aborta la
# instalación completa antes de mover nada (R17) — red de seguridad final,
# independiente de que la clasificación VERBATIM/PLANTILLA de cada entrada
# del manifiesto haya sido correcta.
#
# Vacía por defecto: Harmessi no embebe nombres de organizaciones ni datasets
# propios. Quien mantenga un fork puede agregar aquí las cadenas propias
# (nombres internos, datasets sellados, rutas locales) que nunca deban
# terminar en un proyecto instalado.
CADENAS_PROHIBIDAS: tuple = ()

# Esta entrada del manifiesto es GENERADO pero no tiene archivo fuente ni se
# arma en el staging junto al resto: se produce aparte, después de que la
# aplicación del journal terminó sin errores (`control.generar_control`).
DESTINO_CONTROL_JSON = ".ds_init/control.json"

NOMBRE_JOURNAL = "journal.json"
NOMBRE_DIR_BACKUP = ".backup"

ACCION_JOURNAL_CREAR = "crear"
ACCION_JOURNAL_REEMPLAZAR_MERGE = "reemplazar-merge"


class InstalacionAbortadaError(Exception):
    """La instalación se abortó (validación de staging fallida, conflicto de
    merge, o fallo durante la aplicación del journal con rollback ya
    completado). El destino queda intacto o restaurado a su estado previo."""


@dataclass
class ResultadoInstalacion:
    """Resultado de una corrida exitosa de `instalar()`."""

    aplicados: list = field(default_factory=list)
    omitidos: list = field(default_factory=list)
    control_path: Optional[str] = None
    advertencias: list = field(default_factory=list)


def _rmtree_seguro(staging: Path) -> Optional[str]:
    """Intenta borrar `staging` por completo. A diferencia de
    `shutil.rmtree(..., ignore_errors=True)` a secas, no silencia un fallo:
    si el directorio sigue existiendo después del intento, devuelve su ruta
    (como string) para que quien llama deje constancia (mensaje de excepción
    o `ResultadoInstalacion.advertencias`); si se borró bien, devuelve
    `None`."""
    shutil.rmtree(staging, ignore_errors=True)
    if staging.exists():
        return str(staging)
    return None


def _limpiar_padres_vacios(ruta: Path, destino: Path) -> None:
    """Sube desde el padre de `ruta` borrando directorios que hayan quedado
    vacíos (p. ej. tras revertir un `crear` bajo un subdirectorio que
    `_aplicar_journal` creó con `mkdir(parents=True)`), sin pasar nunca de
    `destino` ni tocarlo a él mismo."""
    actual = ruta.parent
    while actual != destino and destino in actual.parents:
        try:
            actual.rmdir()
        except OSError:
            break
        actual = actual.parent


def _leer_texto(ruta: Path) -> str:
    with open(ruta, "r", encoding="utf-8") as f:
        return f.read()


def _escribir_texto(ruta: Path, contenido: str) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # newline="" preserva literalmente los "\n" del contenido (plantillas y
    # JSON generados acá usan LF); evita que el modo texto de Windows los
    # traduzca a CRLF de forma implícita.
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        f.write(contenido)


def _armar_staging(plan: list, entradas_por_destino: dict, destino: Path, staging: Path, placeholders: dict):
    """Arma el árbol completo dentro de `staging` a partir de `plan`
    (lista de `AccionPlan` de `planner.construir_plan`). Devuelve
    `(entradas_journal, omitidos)`.

    `entradas_journal` es una lista de dicts `{"destino": ruta_relativa,
    "accion": "crear"|"reemplazar-merge", "aplicado": False}`, en el orden en
    que aparecen en `plan` (ese es también el orden de aplicación)."""
    entradas_journal = []
    omitidos = []

    for accion in plan:
        rel = accion.destino

        if rel == DESTINO_CONTROL_JSON:
            # Se genera aparte, después de aplicar (control.generar_control).
            continue

        if accion.accion == ACCION_OMITIR_EXISTENTE:
            omitidos.append(rel)
            continue

        entrada = entradas_por_destino[rel]
        staging_path = staging / rel

        if entrada.tratamiento == VERBATIM:
            fuente_path = raiz_repo_origen() / entrada.fuente
            staging_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(fuente_path, staging_path)
            accion_journal = ACCION_JOURNAL_CREAR

        elif entrada.tratamiento == PLANTILLA:
            fuente_path = raiz_repo_origen() / entrada.fuente
            renderizado = renderizar(_leer_texto(fuente_path), placeholders)
            _escribir_texto(staging_path, renderizado)
            accion_journal = ACCION_JOURNAL_CREAR

        elif entrada.tratamiento == MERGE:
            fuente_path = raiz_repo_origen() / entrada.fuente
            nuevo = json.loads(_leer_texto(fuente_path))
            if accion.accion == ACCION_MERGE:
                existente = json.loads(_leer_texto(destino / rel))
                fusionado = fusionar(existente, nuevo)
                _escribir_texto(staging_path, json.dumps(fusionado, indent=2, ensure_ascii=False) + "\n")
                accion_journal = ACCION_JOURNAL_REEMPLAZAR_MERGE
            else:
                _escribir_texto(staging_path, json.dumps(nuevo, indent=2, ensure_ascii=False) + "\n")
                accion_journal = ACCION_JOURNAL_CREAR

        elif entrada.tratamiento == GENERADO:
            fuente_path = raiz_repo_origen() / entrada.fuente
            renderizado = renderizar(_leer_texto(fuente_path), placeholders)
            if rel == "CLAUDE.md" and accion.accion == ACCION_MERGE:
                existente = _leer_texto(destino / rel)
                version = placeholders.get("HARNESS_VERSION", "")
                resultado = insertar_bloque_claude_md(existente, renderizado, version)
                _escribir_texto(staging_path, resultado)
                accion_journal = ACCION_JOURNAL_REEMPLAZAR_MERGE
            else:
                _escribir_texto(staging_path, renderizado)
                accion_journal = ACCION_JOURNAL_CREAR

        else:
            raise ValueError(f"tratamiento sin manejo en writer: {entrada.tratamiento!r}")

        entradas_journal.append({"destino": rel, "accion": accion_journal, "aplicado": False})

    return entradas_journal, omitidos


def _validar_staging(staging: Path) -> None:
    """Valida el staging completo antes de mover nada a su ubicación final:
    JSON parseable donde corresponda, sin placeholders `{{...}}` sin resolver,
    ninguna ruta de exclusión permanente (R7), ninguna cadena prohibida
    (R17). Levanta `InstalacionAbortadaError` con detalle ante la primera
    violación encontrada."""
    for path in sorted(staging.rglob("*")):
        if path.is_dir():
            continue

        rel = path.relative_to(staging).as_posix()

        for exclusion in EXCLUSIONES_PERMANENTES:
            if rel == exclusion or rel.startswith(exclusion):
                raise InstalacionAbortadaError(
                    f"Archivo en staging viola una exclusión permanente (R7): {rel}"
                )

        contenido_bytes = path.read_bytes()

        for cadena in CADENAS_PROHIBIDAS:
            if cadena.encode("utf-8") in contenido_bytes:
                raise InstalacionAbortadaError(
                    f"Cadena prohibida {cadena!r} encontrada en {rel} (R17)"
                )

        try:
            texto = contenido_bytes.decode("utf-8")
        except UnicodeDecodeError:
            # Archivo binario: ya se comprobaron las cadenas prohibidas a
            # nivel de bytes arriba; no hay placeholders ni JSON que validar.
            continue

        if not verificar_sin_placeholders_pendientes(texto):
            raise InstalacionAbortadaError(f"Placeholder sin resolver en {rel}")

        if rel.endswith(".json"):
            try:
                json.loads(texto)
            except json.JSONDecodeError as exc:
                raise InstalacionAbortadaError(f"JSON inválido en {rel}: {exc}") from exc


def _preparar_backups(entradas_journal: list, destino: Path, staging: Path) -> None:
    """Para cada entrada `reemplazar-merge` del journal, copia el archivo
    original del destino a `<staging>/.backup/<ruta-relativa>` antes de tocar
    nada — se ejecuta antes de empezar a aplicar el journal (§5 paso 1)."""
    for entrada in entradas_journal:
        if entrada["accion"] != ACCION_JOURNAL_REEMPLAZAR_MERGE:
            continue
        origen = destino / entrada["destino"]
        backup_path = staging / NOMBRE_DIR_BACKUP / entrada["destino"]
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, backup_path)


def _escribir_journal(journal_path: Path, entradas_journal: list) -> None:
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    with open(journal_path, "w", encoding="utf-8", newline="") as f:
        json.dump(entradas_journal, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _aplicar_journal(entradas_journal: list, journal_path: Path, destino: Path, staging: Path) -> None:
    """Aplica cada entrada del journal, en orden, con `os.replace`. Marca
    cada entrada como aplicada de forma incremental (se reescribe el journal
    después de cada movimiento exitoso)."""
    for entrada in entradas_journal:
        rel = entrada["destino"]
        origen_staging = staging / rel
        destino_final = destino / rel
        destino_final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(origen_staging, destino_final)
        entrada["aplicado"] = True
        _escribir_journal(journal_path, entradas_journal)


def _revertir_journal(entradas_journal: list, destino: Path, staging: Path) -> None:
    """Revierte, en orden inverso, todo lo que llegó a aplicarse: borra los
    `crear`, restaura desde `.backup/` los `reemplazar-merge`."""
    for entrada in reversed(entradas_journal):
        if not entrada.get("aplicado"):
            continue
        rel = entrada["destino"]
        destino_final = destino / rel

        if entrada["accion"] == ACCION_JOURNAL_CREAR:
            if destino_final.exists():
                destino_final.unlink()
            _limpiar_padres_vacios(destino_final, destino)
        elif entrada["accion"] == ACCION_JOURNAL_REEMPLAZAR_MERGE:
            backup_path = staging / NOMBRE_DIR_BACKUP / rel
            if backup_path.exists():
                destino_final.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_path, destino_final)


def instalar(plan: list, destino, config: dict) -> ResultadoInstalacion:
    """Ejecuta la escritura real de una instalación (`--execute`, R11),
    dado el `plan` ya calculado por `planner.construir_plan`.

    `config` debe incluir `perfil` (identificador público, p. ej.
    `python-jupyter-data`) y `placeholders` (dict para `templating.renderizar`
    — `NOMBRE_PROYECTO`, `NOTEBOOKS_DIR`, `VENV_DIR`, `FECHA_INSTALACION`,
    `HARNESS_VERSION`, y cualquier placeholder adicional de plantillas
    específicas como `RUTAS_PROHIBIDAS_JSON`); también se leen `nombre`,
    `notebooks_dir`, `venv_dir` y `destino` para el archivo de control (R12).

    Levanta la excepción original (validación de staging, `preflight`,
    `ConflictoIncompatibleError` de `settings_merge`) o
    `InstalacionAbortadaError` (fallo durante la aplicación, ya revertido) —
    en ambos casos el destino queda intacto."""
    destino = Path(destino)
    perfil = config.get("perfil")
    if not perfil:
        raise ValueError("config['perfil'] es obligatorio para writer.instalar()")

    entradas = manifest_para_perfil(perfil)
    entradas_por_destino = {entrada.destino: entrada for entrada in entradas}
    placeholders = dict(config.get("placeholders", {}))

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    staging = destino / f".ds_init_staging_{timestamp}"
    staging.mkdir(parents=False, exist_ok=False)

    try:
        entradas_journal, omitidos = _armar_staging(
            plan, entradas_por_destino, destino, staging, placeholders
        )
        _validar_staging(staging)
    except Exception:
        remanente = _rmtree_seguro(staging)
        if remanente:
            warnings.warn(
                f"No se pudo borrar completamente el staging tras un fallo de "
                f"armado/validación: {remanente}"
            )
        raise

    journal_path = staging / NOMBRE_JOURNAL

    # `_preparar_backups`, `_escribir_journal` y `_aplicar_journal` comparten
    # el mismo try/except: si cualquiera de las dos primeras falla, todavía
    # no se aplicó nada (todas las entradas siguen con "aplicado": False), así
    # que `_revertir_journal` no tiene nada que revertir y el bloque se
    # reduce, en la práctica, a limpiar el staging y abortar — mismo
    # tratamiento que un fallo dentro de `_aplicar_journal` (R11: el destino
    # queda exactamente como estaba).
    try:
        _preparar_backups(entradas_journal, destino, staging)
        _escribir_journal(journal_path, entradas_journal)
        _aplicar_journal(entradas_journal, journal_path, destino, staging)
    except Exception as exc:
        _revertir_journal(entradas_journal, destino, staging)
        remanente = _rmtree_seguro(staging)
        mensaje = (
            f"Fallo durante la aplicación de la instalación; se revirtió todo "
            f"lo ya aplicado y el destino quedó como antes de --execute: {exc}"
        )
        if remanente:
            mensaje += f" (advertencia: no se pudo borrar el staging remanente: {remanente})"
        raise InstalacionAbortadaError(mensaje) from exc

    advertencias = []
    remanente = _rmtree_seguro(staging)
    if remanente:
        advertencias.append(
            f"No se pudo borrar completamente el staging tras una instalación exitosa: {remanente}"
        )

    archivos_aplicados = [entrada["destino"] for entrada in entradas_journal]
    control_mod.generar_control(destino, perfil, config, archivos_aplicados)
    control_path = destino / ".ds_init" / "control.json"

    return ResultadoInstalacion(
        aplicados=archivos_aplicados,
        omitidos=omitidos,
        control_path=str(control_path),
        advertencias=advertencias,
    )
