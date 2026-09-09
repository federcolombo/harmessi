"""Núcleo determinista y sin dependencia de SDD ni de Git.

Contiene:
- `hash_lf_v1`: hash reproducible de un archivo de texto, normalizado a LF.
- Lectura/escritura atómica de `control.json`.
- `Finding`: hallazgo de validación, con serialización a texto y a JSON.
- Utilidad para capturar bytes exactos de un archivo (usada por los tests de
  atomicidad: nada se escribe si un gate falla).

Nada en este módulo ejecuta `git` ni conoce el vocabulario de estados SDD — eso
vive en `repo.py` y `sdd.py` respectivamente.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


# --- Hash reproducible -------------------------------------------------------

def hash_lf_v1(path: Path) -> str:
    """sha256 de un archivo de texto, normalizado a LF, algoritmo "sha256/lf/v1".

    Pasos: leer en binario, decodificar como utf-8-sig (descarta un BOM si
    existe), normalizar `\\r\\n` -> `\\n` y luego `\\r` -> `\\n`, volver a
    codificar a UTF-8 y hashear esos bytes. Reproduce exactamente el algoritmo
    ya usado a mano para los hashes de aprobación existentes en `control.json`.
    """
    crudo = Path(path).read_bytes()
    texto = crudo.decode("utf-8-sig")
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# --- Fecha/hora ---------------------------------------------------------------

def ahora_utc() -> str:
    """Timestamp UTC en formato `YYYY-MM-DDTHH:MM:SSZ` (sin microsegundos)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parsear_utc(valor: str) -> datetime:
    return datetime.strptime(valor, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def minutos_restantes(sesion: dict) -> float:
    """Minutos restantes hasta el deadline de la sesión (negativo si ya venció).

    Compara contra el momento real (`datetime.now(timezone.utc)`), nunca contra
    un valor estimado o pasado por el llamador. Única función reusada tanto por
    `chequear_limites` como por `session_close` y por el hook de presupuesto —
    no se recalcula el mismo cociente en más de un lugar.

    Compatibilidad hacia atrás: si `deadline_utc` está ausente/`None`/vacío
    (sesión activa de esquema viejo, previo a esta clave), se deriva como
    `inicio_utc + presupuesto.minutos` (default 90 si `presupuesto.minutos`
    también falta) en vez de levantar `KeyError`. Las sesiones ya cerradas no
    se tocan ni se migran en disco -- este fallback es solo para el cálculo en
    caliente. Si `deadline_utc` está presente, se usa tal cual. Puede levantar
    `ValueError`/`TypeError` si `inicio_utc`/`deadline_utc` están mal
    formados: la decisión de qué hacer ante eso (fail-safe hacia permitir,
    finding informativo, etc.) es del llamador, no de esta función."""
    deadline_utc = sesion.get("deadline_utc")
    if deadline_utc:
        deadline = parsear_utc(deadline_utc)
    else:
        minutos_presupuesto = sesion.get("presupuesto", {}).get("minutos", 90)
        deadline = parsear_utc(sesion.get("inicio_utc")) + timedelta(minutes=minutos_presupuesto)
    ahora = datetime.now(timezone.utc)
    return (deadline - ahora).total_seconds() / 60.0


# --- Escritura atómica genérica ------------------------------------------------

def _escribir_atomico(path: Path, contenido_bytes: bytes) -> None:
    path = Path(path)
    tmp = path.parent / (path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(contenido_bytes)
    os.replace(tmp, path)


def escribir_texto_atomico(path: Path, texto: str) -> None:
    """Escritura atómica de texto UTF-8: a un `.tmp` en el mismo directorio y
    `os.replace`. Usada tanto por `escribir_control` como por `ds_guard init`
    para no duplicar el patrón `open(tmp, "wb") -> os.replace`."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    _escribir_atomico(Path(path), texto.encode("utf-8"))


def capturar_bytes(path: Path) -> Optional[bytes]:
    """Bytes exactos de un archivo, o `None` si no existe.

    Pensada para los tests de atomicidad: capturar antes de una operación que
    puede fallar, comparar después, confirmar que no cambió nada.
    """
    path = Path(path)
    if not path.exists():
        return None
    return path.read_bytes()


# --- control.json ---------------------------------------------------------------

SCHEMA_VERSION_SOPORTADA = 1


class ControlJsonError(Exception):
    """Error controlado al leer/escribir `control.json`.

    En particular: `schema_version` desconocida. Nunca se recupera con datos
    por defecto — el error se propaga para que el llamador decida (típicamente
    exit code 2, error de uso/configuración).
    """


def leer_control(path: Path) -> dict:
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        try:
            datos = json.load(f)
        except json.JSONDecodeError as e:
            raise ControlJsonError(f"control.json inválido: {e}")
    version = datos.get("schema_version")
    if version != SCHEMA_VERSION_SOPORTADA:
        raise ControlJsonError(
            f"schema_version desconocida en {path}: {version!r} "
            f"(se esperaba {SCHEMA_VERSION_SOPORTADA})"
        )
    return datos


def escribir_control(path: Path, control: dict) -> None:
    """Escritura atómica: json.dump con indent=2, sin escape de no-ASCII, salto
    de línea final, a un `.tmp` en el mismo directorio y `os.replace`. Crea el
    directorio padre si no existe (vía `escribir_texto_atomico`)."""
    texto = json.dumps(control, indent=2, ensure_ascii=False) + "\n"
    escribir_texto_atomico(path, texto)


# --- Finding -----------------------------------------------------------------

@dataclass
class Finding:
    """Un hallazgo de validación. `codigo` es uno de los strings fijos de la
    spec (ALCANCE-RUTA, SDD-ESTADO-ILEGIBLE, SESION-AUSENTE, etc.)."""

    codigo: str
    mensaje: str
    ubicacion: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"codigo": self.codigo, "mensaje": self.mensaje}
        if self.ubicacion:
            d["ubicacion"] = self.ubicacion
        return d


def formatear_findings_texto(findings: list) -> str:
    if not findings:
        return "Sin hallazgos."
    lineas = []
    for h in findings:
        if h.ubicacion:
            lineas.append(f"[{h.codigo}] {h.mensaje} ({h.ubicacion})")
        else:
            lineas.append(f"[{h.codigo}] {h.mensaje}")
    return "\n".join(lineas)


def formatear_findings_json(findings: list, exit_code: int) -> str:
    payload = {
        "findings": [h.to_dict() for h in findings],
        "exit_code": exit_code,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
