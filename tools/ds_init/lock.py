"""Lock de instalación (`<destino>/.ds_init/lock`, v0.11 Change 5 R3).

Impide dos escrituras simultáneas de `ds_init` sobre el mismo destino. El lock
se crea de forma atómica (`O_CREAT | O_EXCL`) con contenido JSON
`{pid, utc, accion}`. Si ya existe NO se ignora ni se roba: se levanta
`LockOcupadoError` con instrucciones accionables para que lo resuelva una
persona.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DIR_CONTROL = ".ds_init"
NOMBRE_LOCK = "lock"


class LockOcupadoError(Exception):
    """Ya existe `.ds_init/lock`: otra corrida de `ds_init` está en curso o
    quedó un lock huérfano. El mensaje indica cómo resolverlo."""


def ruta_lock(destino) -> Path:
    return Path(destino) / DIR_CONTROL / NOMBRE_LOCK


def _describir_lock_existente(ruta: Path) -> str:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        return (
            f"pid={datos.get('pid')}, accion={datos.get('accion')}, "
            f"utc={datos.get('utc')}"
        )
    except (OSError, ValueError):
        return "contenido ilegible"


def adquirir_lock(destino, accion: str = "install") -> Path:
    """Crea `.ds_init/lock` con O_EXCL. Devuelve la ruta del lock. Si ya
    existe levanta `LockOcupadoError` (nunca lo pisa ni lo ignora)."""
    ruta = ruta_lock(destino)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(ruta), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise LockOcupadoError(
            f"Ya existe el lock de instalación {ruta} ({_describir_lock_existente(ruta)}). "
            f"Verificar que no haya otro proceso de ds_init en ejecución sobre este "
            f"destino y, si no lo hay, borrar el archivo {ruta} y reintentar."
        ) from None
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            json.dump(
                {
                    "pid": os.getpid(),
                    "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "accion": accion,
                },
                f,
            )
    except Exception:
        liberar_lock(destino)
        raise
    return ruta


def liberar_lock(destino) -> None:
    """Borra `.ds_init/lock` si existe (idempotente). Quita `.ds_init/` solo si
    quedó vacío."""
    ruta = ruta_lock(destino)
    try:
        ruta.unlink()
    except FileNotFoundError:
        pass
    try:
        ruta.parent.rmdir()
    except OSError:
        pass


@contextmanager
def lock_instalacion(destino, accion: str = "install"):
    """Adquiere el lock y lo libera siempre (también ante excepción)."""
    adquirir_lock(destino, accion)
    try:
        yield
    finally:
        liberar_lock(destino)
