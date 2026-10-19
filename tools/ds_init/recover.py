"""`ds_init recover` (v0.11 Change 5, R4): revierte al estado previo consistente
una transacción de `writer.instalar` interrumpida.

Política (solo rollback, nunca roll-forward):
- Journal en `.ds_init/journal/<ts>/` en fase `preparado`: no se aplicó nada, se
  limpia sin revertir (los backups pueden estar incompletos y no hacen falta).
- Fases `aplicando` / `control_pendiente`: se revierte con
  `writer._revertir_journal` (borra lo creado, restaura backups, incluido el
  control.json previo). Para los `reemplazar-merge` se restaura SIEMPRE el
  backup (idempotente, cubre un corte entre `os.replace` y la marca `aplicado`);
  un backup ausente es un fallo, nunca un skip silencioso. Para los `crear` no
  marcados se infiere que se aplicaron si el staging hermano existe y ya no
  contiene el archivo.
- Fase `completo`: la transacción quedó confirmada; solo faltó limpiar. Se
  considera limpia y `--execute` borra journal/staging como housekeeping, sin
  revertir.
- Directorio de journal sin `journal.json` (o solo con su temporal): residuo
  limpiable (el `journal.json` se escribe primero y se borra al final).
- Si algún journal es ilegible, tiene rutas inválidas o falta un backup
  necesario, se aborta ANTES de tocar nada (el CLI sale con 2 y da la
  instrucción manual).
- Si un archivo a revertir fue editado después de la interrupción (su hash no
  es el escrito por la transacción ni el del backup) se aborta con exit 2 salvo
  `--forzar`, que lo revierte conservando la copia como `<ruta>.recover-bak`.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import writer
from .manifest import MANIFEST
from .preflight import PREFIJO_STAGING_HUERFANO

FASES_VALIDAS = (
    writer.FASE_PREPARADO,
    writer.FASE_APLICANDO,
    writer.FASE_CONTROL_PENDIENTE,
    writer.FASE_COMPLETO,
)
ACCIONES_VALIDAS = (writer.ACCION_JOURNAL_CREAR, writer.ACCION_JOURNAL_REEMPLAZAR_MERGE)
SUFIJO_BACKUP_FORZADO = ".recover-bak"


@dataclass
class InfoJournal:
    nombre: str
    ruta: Path
    fase: str = None
    entradas: list = field(default_factory=list)
    problemas: list = field(default_factory=list)
    editados: list = field(default_factory=list)  # rutas editadas tras la interrupción
    residuo: bool = False  # directorio sin journal.json: limpiable


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

    @property
    def editados(self) -> list:
        return [(j.nombre, r) for j in self.journals for r in j.editados]


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def _rutas_permitidas() -> frozenset:
    return frozenset(e.destino for e in MANIFEST)


def validar_ruta_journal(destino: Path, rel, permitidas=None):
    """`None` si `rel` es una ruta aceptable para recover; si no, el motivo.
    Reglas: string relativa, sin barras invertidas ni `..`, sin ':' en ningún
    componente (ADS/unidades), fuera de `.git/`, dentro de `destino` tras
    resolver symlinks del padre, y perteneciente al MANIFEST o a `.ds_init/`."""
    if not isinstance(rel, str) or not rel:
        return "ruta vacía o no es texto"
    if "\\" in rel:
        return "contiene barra invertida"
    p = PurePosixPath(rel)
    if p.is_absolute() or not p.parts:
        return "no es una ruta relativa"
    if ".." in p.parts:
        return "contiene '..'"
    if any(":" in c for c in p.parts):
        return "contiene ':' en algún componente"
    if p.parts[0].lower() == ".git":
        return "apunta dentro de .git/"
    try:
        (Path(destino) / rel).parent.resolve().relative_to(Path(destino).resolve())
    except (ValueError, OSError):
        return "resuelve fuera del destino (symlink)"
    permitidas = _rutas_permitidas() if permitidas is None else permitidas
    if rel not in permitidas and not rel.startswith(".ds_init/"):
        return "no pertenece al MANIFEST ni a .ds_init/"
    return None


def _entradas_a_revertir(info: InfoJournal, destino: Path) -> list:
    if info.fase in (None, writer.FASE_PREPARADO, writer.FASE_COMPLETO):
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


def analizar_journal(ruta: Path, destino: Path = None) -> InfoJournal:
    ruta = Path(ruta)
    destino = Path(destino) if destino is not None else ruta.parents[2]
    info = InfoJournal(nombre=ruta.name, ruta=ruta)
    ruta_journal = ruta / writer.NOMBRE_JOURNAL
    if not ruta_journal.exists():
        info.residuo = True  # residuo de limpieza interrumpida o de corte previo al primer journal
        return info
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
    permitidas = _rutas_permitidas()
    for e in datos["entradas"]:
        if not isinstance(e, dict) or e.get("accion") not in ACCIONES_VALIDAS:
            info.problemas.append(f"{ruta_journal}: entrada inválida {e!r}")
            return info
        motivo = validar_ruta_journal(destino, e.get("destino"), permitidas)
        if motivo:
            info.problemas.append(f"{ruta_journal}: ruta inválida {e.get('destino')!r} ({motivo})")
            return info
    info.fase = datos["fase"]
    info.entradas = datos["entradas"]
    if info.fase in (writer.FASE_APLICANDO, writer.FASE_CONTROL_PENDIENTE):
        for e in info.entradas:
            if e["accion"] == writer.ACCION_JOURNAL_REEMPLAZAR_MERGE:
                backup = ruta / writer.NOMBRE_DIR_BACKUP / e["destino"]
                if not backup.is_file():
                    info.problemas.append(f"falta el backup {backup} (necesario para restaurar {e['destino']})")
        if not info.problemas:
            for e in _entradas_a_revertir(info, destino):
                esperado = e.get("sha256_nuevo")
                actual_ruta = destino / e["destino"]
                if not e.get("aplicado") or not isinstance(esperado, str) or not actual_ruta.is_file():
                    continue
                permitidos = {esperado}
                if e["accion"] == writer.ACCION_JOURNAL_REEMPLAZAR_MERGE:
                    permitidos.add(_sha256(ruta / writer.NOMBRE_DIR_BACKUP / e["destino"]))
                if _sha256(actual_ruta) not in permitidos:
                    info.editados.append(e["destino"])
    return info


def detectar(destino: Path) -> EstadoRecover:
    destino = Path(destino)
    estado = EstadoRecover()
    dir_journal = destino / writer.DIR_JOURNAL
    if dir_journal.is_dir():
        for p in sorted((q for q in dir_journal.iterdir() if q.is_dir()), key=lambda q: q.name, reverse=True):
            estado.journals.append(analizar_journal(p, destino))
    estado.staging = sorted(
        p for p in destino.iterdir() if p.is_dir() and p.name.startswith(PREFIJO_STAGING_HUERFANO)
    ) if destino.is_dir() else []
    return estado


def describir(info: InfoJournal, destino: Path) -> list:
    """Líneas de texto del dry-run para un journal."""
    if info.residuo:
        return [f"Journal {info.ruta} — sin journal.json: residuo limpiable, se eliminará"]
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
    for ruta in info.editados:
        lineas.append(
            f"  AVISO: {ruta} fue editado después de la interrupción (su hash no coincide con lo "
            "escrito por la transacción); execute abortará salvo --forzar"
        )
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


def instruccion_editados(estado: EstadoRecover) -> str:
    lineas = ["Archivos editados después de la interrupción (recover no los pisa sin --forzar):"]
    lineas.extend(f"  - {ruta} (journal {nombre})" for nombre, ruta in estado.editados)
    lineas.append(
        "  Revisar los cambios (git diff) y, si se pueden descartar, reintentar con --forzar "
        f"(la copia actual se conserva como <ruta>{SUFIJO_BACKUP_FORZADO})."
    )
    return "\n".join(lineas)


def ejecutar(destino: Path, estado: EstadoRecover, forzar: bool = False) -> list:
    """Aplica el recover (se asume lock tomado y estado sin problemas).
    Devuelve la lista de fallos de reversión (vacía si todo OK)."""
    destino = Path(destino)
    fallos = []
    for info in estado.journals:  # más reciente primero
        if info.residuo:
            shutil.rmtree(info.ruta, ignore_errors=True)
            continue
        entradas = _entradas_a_revertir(info, destino)
        if forzar:
            for rel in info.editados:
                actual = destino / rel
                if actual.is_file():
                    shutil.copy2(actual, actual.with_name(actual.name + SUFIJO_BACKUP_FORZADO))
        fallos_j = writer._revertir_journal(entradas, destino, info.ruta) if entradas else []
        if fallos_j:
            fallos.extend({"journal": info.nombre, **f} for f in fallos_j)
            continue  # se conserva el journal como insumo
        writer._borrar_journal_seguro(info.ruta)
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
