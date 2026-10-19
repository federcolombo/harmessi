"""`ds_init recover` (v0.11 Change 5, R4): revierte al estado previo consistente
una transacción de `writer.instalar` interrumpida.

Política (solo rollback, nunca roll-forward):
- Journal en `.ds_init/journal/<ts>/` en fase `preparado`: no se aplicó nada, se
  limpia sin revertir (los backups pueden estar incompletos y no hacen falta).
- Fases `aplicando` / `control_pendiente`: se revierte con
  `writer._revertir_journal` (borra lo creado, restaura backups, incluido el
  control.json previo). Para los `reemplazar-merge` se restaura SIEMPRE el
  backup (idempotente, cubre un corte entre `os.replace` y la marca `aplicado`).
  Para los `crear` no marcados se infiere que se aplicaron si el staging
  hermano existe y ya no contiene el archivo.
- Fase `completo`: la transacción quedó confirmada; solo faltó limpiar. Se
  considera limpia y `--execute` borra journal/staging como housekeeping, sin
  revertir.
- Si algún journal es ilegible o falta un backup necesario, se aborta ANTES de
  tocar nada (el CLI sale con 2 y da la instrucción manual).
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import writer
from .preflight import PREFIJO_STAGING_HUERFANO

FASES_VALIDAS = (
    writer.FASE_PREPARADO,
    writer.FASE_APLICANDO,
    writer.FASE_CONTROL_PENDIENTE,
    writer.FASE_COMPLETO,
)
ACCIONES_VALIDAS = (writer.ACCION_JOURNAL_CREAR, writer.ACCION_JOURNAL_REEMPLAZAR_MERGE)


@dataclass
class InfoJournal:
    nombre: str
    ruta: Path
    fase: str = None
    entradas: list = field(default_factory=list)
    problemas: list = field(default_factory=list)


@dataclass
class EstadoRecover:
    journals: list = field(default_factory=list)  # InfoJournal, más reciente primero
    staging: list = field(default_factory=list)  # Path de .ds_init_staging_*

    @property
    def vacio(self) -> bool:
        return not self.journals and not self.staging

    @property
    def problemas(self) -> list:
        return [p for j in self.journals for p in j.problemas]


def _ruta_relativa_segura(rel) -> bool:
    if not isinstance(rel, str) or not rel:
        return False
    p = PurePosixPath(rel.replace("\\", "/"))
    return bool(p.parts) and not p.is_absolute() and ".." not in p.parts and ":" not in p.parts[0]


def analizar_journal(ruta: Path) -> InfoJournal:
    info = InfoJournal(nombre=ruta.name, ruta=ruta)
    ruta_journal = ruta / writer.NOMBRE_JOURNAL
    try:
        datos = json.loads(ruta_journal.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        info.problemas.append(f"{ruta_journal}: journal ilegible ({exc})")
        return info
    if (
        not isinstance(datos, dict)
        or datos.get("fase") not in FASES_VALIDAS
        or not isinstance(datos.get("entradas"), list)
    ):
        info.problemas.append(f"{ruta_journal}: estructura inválida (fase/entradas)")
        return info
    info.fase = datos["fase"]
    for e in datos["entradas"]:
        if (
            not isinstance(e, dict)
            or not _ruta_relativa_segura(e.get("destino"))
            or e.get("accion") not in ACCIONES_VALIDAS
        ):
            info.problemas.append(f"{ruta_journal}: entrada inválida {e!r}")
            return info
    info.entradas = datos["entradas"]
    if info.fase in (writer.FASE_APLICANDO, writer.FASE_CONTROL_PENDIENTE):
        for e in info.entradas:
            if e["accion"] == writer.ACCION_JOURNAL_REEMPLAZAR_MERGE:
                backup = ruta / writer.NOMBRE_DIR_BACKUP / e["destino"]
                if not backup.is_file():
                    info.problemas.append(f"falta el backup {backup} (necesario para restaurar {e['destino']})")
    return info


def detectar(destino: Path) -> EstadoRecover:
    destino = Path(destino)
    estado = EstadoRecover()
    dir_journal = destino / writer.DIR_JOURNAL
    if dir_journal.is_dir():
        for p in sorted((q for q in dir_journal.iterdir() if q.is_dir()), key=lambda q: q.name, reverse=True):
            estado.journals.append(analizar_journal(p))
    estado.staging = sorted(
        p for p in destino.iterdir() if p.is_dir() and p.name.startswith(PREFIJO_STAGING_HUERFANO)
    ) if destino.is_dir() else []
    return estado


def _entradas_a_revertir(info: InfoJournal, destino: Path) -> list:
    if info.fase in (writer.FASE_PREPARADO, writer.FASE_COMPLETO):
        return []
    staging = destino / (PREFIJO_STAGING_HUERFANO + info.nombre)
    resultado = []
    for e in info.entradas:
        copia = dict(e)
        if e["accion"] == writer.ACCION_JOURNAL_REEMPLAZAR_MERGE:
            copia["aplicado"] = True
        elif not e.get("aplicado"):
            copia["aplicado"] = staging.is_dir() and not (staging / e["destino"]).exists()
        resultado.append(copia)
    return resultado


def describir(info: InfoJournal, destino: Path) -> list:
    """Líneas de texto del dry-run para un journal."""
    lineas = [f"Journal {info.ruta} — fase: {info.fase}"]
    if info.problemas:
        return lineas
    aplicadas = [e["destino"] for e in info.entradas if e.get("aplicado")]
    lineas.append(f"  entradas: {len(info.entradas)}, marcadas como aplicadas: {len(aplicadas)}")
    if info.fase == writer.FASE_COMPLETO:
        lineas.append("  transacción confirmada: solo se eliminará el journal (sin revertir)")
    elif info.fase == writer.FASE_PREPARADO:
        lineas.append("  no se aplicó nada: solo se eliminará el journal")
    else:
        for e in _entradas_a_revertir(info, destino):
            if not e.get("aplicado"):
                continue
            if e["accion"] == writer.ACCION_JOURNAL_CREAR:
                lineas.append(f"  borrar archivo creado: {e['destino']}")
            else:
                lineas.append(f"  restaurar desde backup: {e['destino']}")
        lineas.append("  luego se eliminará el journal")
    return lineas


def instruccion_manual(estado: EstadoRecover) -> str:
    """Instrucción exacta cuando recover no puede proceder solo."""
    lineas = ["No se modificó nada. Resolución manual:"]
    for j in estado.journals:
        if j.problemas:
            lineas.append(f"  - Revisar {j.ruta / writer.NOMBRE_JOURNAL} y la carpeta de backups {j.ruta / writer.NOMBRE_DIR_BACKUP}")
            lineas.extend(f"      {p}" for p in j.problemas)
    lineas.append(
        "  Restaurar a mano cada archivo de backups/ sobre la misma ruta relativa del destino, borrar "
        "los archivos que la operación hubiera creado (ver 'git status'), y luego borrar "
        f"{writer.DIR_JOURNAL}/ y los directorios {PREFIJO_STAGING_HUERFANO}*. "
        "Con el árbol limpio (git checkout / git status) reintentar la operación."
    )
    return "\n".join(lineas)


def ejecutar(destino: Path, estado: EstadoRecover) -> list:
    """Aplica el recover (se asume lock tomado y estado sin problemas).
    Devuelve la lista de fallos de reversión (vacía si todo OK)."""
    destino = Path(destino)
    fallos = []
    for info in estado.journals:  # más reciente primero
        entradas = _entradas_a_revertir(info, destino)
        fallos_j = writer._revertir_journal(entradas, destino, info.ruta) if entradas else []
        if fallos_j:
            fallos.extend({"journal": info.nombre, **f} for f in fallos_j)
            continue  # se conserva el journal como insumo
        shutil.rmtree(info.ruta, ignore_errors=True)
    if not fallos:
        for staging in estado.staging:
            shutil.rmtree(staging, ignore_errors=True)
        dir_control = destino / ".ds_init"
        if dir_control.is_dir():
            for tmp in dir_control.glob("control.json.tmp-*"):
                try:
                    tmp.unlink()
                except OSError:
                    pass
        writer._limpiar_dirs_journal_vacios(destino)
    return fallos
