"""Enmiendas gobernadas del scope de un Change (Change 3 de v0.10).

Historial encadenado `openspec/changes/<id>/amendments.jsonl` (append-only, una
entrada JSON por línea). El scope efectivo sale SIEMPRE de la cadena; la caché
`control["alcance"]["rutas_autorizadas"]` es solo compatibilidad y nunca la
supera. Detecta edición ingenua (hashes encadenados); NO es criptografía.

Módulo de datos: solo stdlib + `Finding`. No pide T1 (lo hace el CLI): acá solo
se valida que los campos T1 recibidos sean de canal `console_confirmed`. No
persiste challenge ni respuesta.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .core import Finding

SCHEMA_VERSION = 1
NOMBRE_ARCHIVO = "amendments.jsonl"
COD_ENMIENDA_INVALIDA = "ALCANCE-ENMIENDA-INVALIDA"
COD_CACHE_DIVERGENTE = "ALCANCE-CACHE-DIVERGENTE"

CANAL_REQUERIDO = "console_confirmed"
CAMPOS_T1 = ("approval_channel", "confirmed_at", "channel_version")
CLAVES_ENTRADA = frozenset({
    "schema_version", "seq", "utc", "operacion", "add", "remove",
    "rutas_despues", "scope_hash_before", "scope_hash_after", "prev_hash",
    "motivo", "usuario", "fecha_declarada", "approval_channel",
    "confirmed_at", "channel_version", "entry_hash",
})


# --- Hashes canónicos --------------------------------------------------------

def _json_canonico(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(texto: str) -> str:
    # surrogatepass: un surrogate suelto no debe romper la validación (se rechaza por contenido).
    return hashlib.sha256(texto.encode("utf-8", "surrogatepass")).hexdigest()


def _ordenadas(rutas) -> list:
    return sorted(set(rutas))


def hash_alcance(rutas) -> str:
    """sha256 del JSON canónico de la lista ordenada y sin duplicados."""
    return _sha256(_json_canonico(_ordenadas(rutas)))


def hash_entrada(entrada: dict) -> str:
    """sha256 del JSON canónico de la entrada SIN `entry_hash`."""
    sin_hash = {k: v for k, v in entrada.items() if k != "entry_hash"}
    return _sha256(_json_canonico(sin_hash))


def ruta_archivo(change_dir) -> Path:
    return Path(change_dir) / NOMBRE_ARCHIVO


# --- Validación de la cadena -------------------------------------------------

def _es_lista_str(valor) -> bool:
    return isinstance(valor, list) and all(isinstance(x, str) for x in valor)


FORMATO_UTC = "%Y-%m-%dT%H:%M:%SZ"
MAX_MOTIVO = 500
MAX_USUARIO = 200
_CATEGORIAS_PROHIBIDAS = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp", "Co", "Cn"})


def texto_con_caracteres_de_control(texto) -> bool:
    """True si `texto` contiene algún carácter de categoría Cc, Cf, Cs, Zl, Zp,
    Co o Cn (control, formato, surrogate, separadores de línea/párrafo, uso
    privado, no asignado). Reutilizable por el CLI para motivo/usuario/rutas."""
    return any(unicodedata.category(c) in _CATEGORIAS_PROHIBIDAS for c in str(texto))


def _fecha_valida(valor) -> bool:
    if not isinstance(valor, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", valor):
        return False
    try:
        datetime.strptime(valor, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _utc_valido(valor) -> bool:
    if not isinstance(valor, str):
        return False
    try:
        datetime.strptime(valor, FORMATO_UTC)
    except ValueError:
        return False
    return True


def motivo_ruta_invalida(ruta) -> Optional[str]:
    """Validador estructural mínimo (sin importar sdd) de una ruta del historial.
    Devuelve el motivo de rechazo o None si es aceptable."""
    if not isinstance(ruta, str) or not ruta.strip():
        return "ruta vacía"
    if texto_con_caracteres_de_control(ruta):
        return "ruta con NUL o caracteres de control/formato/no asignados"
    if "\\" in ruta:
        return "ruta con backslash"
    if ":" in ruta:
        return "ruta con ':' (unidad o esquema)"
    if ruta.startswith(("/", "~")):
        return "ruta absoluta o con '~'"
    segmentos = ruta.split("/")
    if any(s in ("..", ".") for s in segmentos):
        return "ruta con segmento '.' o '..'"
    if "*" in segmentos[0]:
        return "comodín repo-wide en el primer segmento"
    bajo = ruta.lower()
    if bajo == "data/raw" or bajo.startswith("data/raw/"):
        return "ruta bajo data/raw"
    if segmentos[0].lower() in (".git", ".harmessi"):
        return "ruta protegida (.git/.harmessi)"
    if bajo == ".claude/guardrails.json" or fnmatch.fnmatchcase(bajo, ".claude/settings*.json"):
        return "ruta protegida (.claude)"
    return None


def _validar_cadena(texto: str, hash_ancla: Optional[str]) -> tuple:
    """Valida el contenido completo. Devuelve (entradas, errores).

    Para seq 1 la base previa se deriva de la propia entrada
    ((despues - add) | remove) y su hash debe ser `scope_hash_before`; así no
    depende de la caché (que el CLI refresca). `hash_ancla` (hash de
    aprobación, si existe) debe coincidir con `scope_hash_before` de seq 1."""
    errores: list = []
    entradas: list = []
    lineas = texto.split("\n")
    if lineas and lineas[-1] == "":
        lineas.pop()
    prev_hash = ""
    base: Optional[list] = None
    for idx, linea in enumerate(lineas, start=1):
        pre = f"línea {idx}: "
        try:
            e = json.loads(linea)
        except (ValueError, RecursionError):
            errores.append(pre + "JSON inválido")
            break
        if not isinstance(e, dict):
            errores.append(pre + "la entrada no es un objeto JSON")
            break
        if set(e.keys()) != CLAVES_ENTRADA:
            errores.append(pre + "claves inesperadas o faltantes")
            break
        problema = _validar_entrada(e, idx, prev_hash, base, hash_ancla)
        if problema:
            errores.append(pre + problema)
            break
        entradas.append(e)
        prev_hash = e["entry_hash"]
        base = e["rutas_despues"]
    return entradas, errores


def _validar_entrada(e: dict, idx: int, prev_hash: str, base: Optional[list],
                     hash_ancla: Optional[str]) -> Optional[str]:
    """Devuelve el motivo de invalidez o None."""
    if isinstance(e["schema_version"], bool) or e["schema_version"] != SCHEMA_VERSION:
        return "schema_version no soportada"
    if not isinstance(e["seq"], int) or isinstance(e["seq"], bool) or e["seq"] != idx:
        return f"seq fuera de orden o con huecos (esperado {idx})"
    if e["prev_hash"] != prev_hash:
        return "prev_hash no coincide con la entrada anterior"
    for clave, maximo in (("motivo", MAX_MOTIVO), ("usuario", MAX_USUARIO)):
        if not isinstance(e[clave], str) or not e[clave].strip():
            return f"{clave} ausente o vacío"
        if len(e[clave]) > maximo:
            return f"{clave} excede {maximo} caracteres"
        if texto_con_caracteres_de_control(e[clave]):
            return f"{clave} con caracteres de control/formato"
    if not _fecha_valida(e["fecha_declarada"]):
        return "fecha_declarada inválida (se espera AAAA-MM-DD)"
    for clave in ("scope_hash_before", "scope_hash_after", "entry_hash", "operacion"):
        if not isinstance(e[clave], str):
            return f"{clave} no es string"
    for clave in ("utc", "confirmed_at"):
        if not _utc_valido(e[clave]):
            return f"{clave} con formato inválido (se espera %Y-%m-%dT%H:%M:%SZ)"
    if e["entry_hash"] != hash_entrada(e):
        return "entry_hash incorrecto (entrada alterada)"
    if e["approval_channel"] != CANAL_REQUERIDO:
        return "approval_channel distinto de console_confirmed"
    if not isinstance(e["channel_version"], str) or not e["channel_version"]:
        return "channel_version ausente"
    for clave in ("add", "remove", "rutas_despues"):
        if not _es_lista_str(e[clave]):
            return f"{clave} no es lista de strings"
    for clave in ("add", "rutas_despues"):
        for ruta in e[clave]:
            motivo_r = motivo_ruta_invalida(ruta)
            if motivo_r:
                return f"{clave}: ruta {ruta!r} inválida ({motivo_r})"
    despues = e["rutas_despues"]
    if despues != _ordenadas(despues):
        return "rutas_despues no está ordenada y sin duplicados"
    add, remove = set(e["add"]), set(e["remove"])
    if add & remove:
        return "add y remove comparten rutas"
    if not add and not remove:
        return "entrada sin cambios"
    esperada = "mixta" if add and remove else ("add" if add else "remove")
    if e["operacion"] != esperada:
        return "operacion inconsistente con add/remove"
    if e["scope_hash_after"] != hash_alcance(despues):
        return "scope_hash_after no coincide con rutas_despues"
    if base is None:
        base_calc = _ordenadas((set(despues) - add) | remove)
        if e["scope_hash_before"] != hash_alcance(base_calc):
            return "scope_hash_before no coincide con el estado previo derivado"
        if hash_ancla is not None and e["scope_hash_before"] != hash_ancla:
            return "scope_hash_before no coincide con el scope aprobado"
        base = base_calc
    elif e["scope_hash_before"] != hash_alcance(base):
        return "scope_hash_before no coincide con rutas_despues de la entrada anterior"
    if despues != _ordenadas((set(base) | add) - remove):
        return "rutas_despues no equivale a anteriores + add - remove"
    return None


# --- Estado ------------------------------------------------------------------

@dataclass(frozen=True)
class EstadoAlcance:
    rutas: tuple
    revision: int
    scope_hash: str
    valido: bool
    desde_cadena: bool
    hallazgos: tuple


def _rutas_cache(control) -> Optional[list]:
    alcance = control.get("alcance") if isinstance(control, dict) else None
    rutas = alcance.get("rutas_autorizadas") if isinstance(alcance, dict) else None
    if isinstance(rutas, list) and all(isinstance(x, str) for x in rutas):
        return _ordenadas(rutas)
    return None


def _hash_aprobado(control) -> Optional[str]:
    alcance = control.get("alcance") if isinstance(control, dict) else None
    h = alcance.get("scope_hash") if isinstance(alcance, dict) else None
    return h if isinstance(h, str) and h else None


def _invalido(errores: list, ubicacion: str) -> EstadoAlcance:
    hallazgos = tuple(
        Finding(COD_ENMIENDA_INVALIDA, f"Historial de enmiendas inválido: {m}", ubicacion)
        for m in errores
    )
    return EstadoAlcance((), 0, "", False, True, hallazgos)


def estado_alcance(change_dir, control) -> EstadoAlcance:
    """Scope efectivo: la cadena manda; sin archivo, la caché de aprobación."""
    path = ruta_archivo(change_dir)
    cache = _rutas_cache(control)
    ubic = str(path)

    def _sin_cadena() -> EstadoAlcance:
        rutas = cache if cache is not None else []
        ancla = _hash_aprobado(control)
        if ancla is not None and hash_alcance(rutas) != ancla:
            return _invalido(["la caché de control.json diverge de la ancla de aprobación "
                              "y no hay cadena de enmiendas que lo respalde (edición "
                              "manual o archivo de enmiendas borrado)"], ubic)
        return EstadoAlcance(tuple(rutas), 0, hash_alcance(rutas), True, False, ())

    if not path.exists():
        return _sin_cadena()
    try:
        texto = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return _invalido([f"archivo ilegible ({type(exc).__name__})"], ubic)
    entradas, errores = _validar_cadena(texto, _hash_aprobado(control))
    if errores:
        return _invalido(errores, ubic)
    if not entradas:
        return _sin_cadena()
    ultima = entradas[-1]
    hallazgos = ()
    if cache is None or hash_alcance(cache) != ultima["scope_hash_after"]:
        hallazgos = (Finding(
            COD_CACHE_DIVERGENTE,
            "La caché control.alcance.rutas_autorizadas difiere del historial de "
            "enmiendas; el scope efectivo se toma de la cadena. Ejecutá "
            "`ds_guard scope show --reparar-cache` para realinear la caché.",
            ubic,
        ),)
    return EstadoAlcance(tuple(ultima["rutas_despues"]), ultima["seq"],
                         ultima["scope_hash_after"], True, True, hallazgos)


# --- Plan --------------------------------------------------------------------

@dataclass(frozen=True)
class PlanEnmienda:
    add: tuple
    remove: tuple
    noop_add: tuple
    noop_remove: tuple
    rutas_antes: tuple
    rutas_despues: tuple
    hash_antes: str
    hash_despues: str
    errores: tuple
    es_noop: bool
    operacion: str


def planificar_enmienda(estado: EstadoAlcance, add_crudo, remove_crudo,
                        rutas_defecto, normalizar: Callable) -> PlanEnmienda:
    """Función pura: calcula el efecto de add/remove sobre `estado`."""
    antes = tuple(_ordenadas(estado.rutas))
    errores: list = []
    if not estado.valido:
        errores.append("el historial de enmiendas es inválido; no se puede enmendar")
    add_crudo = list(add_crudo or [])
    remove_crudo = list(remove_crudo or [])
    if not add_crudo and not remove_crudo:
        errores.append("debe indicarse al menos un --add o un --remove")

    def _norm(lista: list, rol: str) -> list:
        salida = []
        for crudo in lista:
            ruta, motivo = normalizar(crudo)
            if ruta is None:
                errores.append(f"{rol} {crudo!r} inválida: {motivo}")
            elif ruta not in salida:
                salida.append(ruta)
        return salida

    add_n = _norm(add_crudo, "add")
    rem_n = _norm(remove_crudo, "remove")

    defecto = set()
    for r in rutas_defecto or ():
        defecto.add(r)
        ruta, _m = normalizar(r)
        if ruta is not None:
            defecto.add(ruta)
    for r in rem_n:
        if r in defecto:
            errores.append(f"remove {r!r}: es una ruta por defecto del Change y no se puede quitar")
    for r in sorted(set(add_n) & set(rem_n)):
        errores.append(f"{r!r} aparece en add y en remove de la misma operación")

    h_antes = hash_alcance(antes)
    if errores:
        return PlanEnmienda((), (), (), (), antes, antes, h_antes, h_antes,
                            tuple(errores), False, "")
    presentes = set(antes)
    add_ef = tuple(sorted(r for r in add_n if r not in presentes))
    noop_add = tuple(sorted(r for r in add_n if r in presentes))
    rem_ef = tuple(sorted(r for r in rem_n if r in presentes))
    noop_rem = tuple(sorted(r for r in rem_n if r not in presentes))
    despues = tuple(_ordenadas((presentes | set(add_ef)) - set(rem_ef)))
    es_noop = not add_ef and not rem_ef
    if es_noop:
        operacion = ""
    elif add_ef and rem_ef:
        operacion = "mixta"
    else:
        operacion = "add" if add_ef else "remove"
    return PlanEnmienda(add_ef, rem_ef, noop_add, noop_rem, antes, despues,
                        h_antes, hash_alcance(despues), (), es_noop, operacion)


def diff_canonico(change_id: str, plan: PlanEnmienda) -> dict:
    return {
        "operacion": plan.operacion,
        "target": "scope-amendment",
        "change_id": change_id,
        "hash_antes": plan.hash_antes,
        "add": list(plan.add),
        "remove": list(plan.remove),
        "hash_despues": plan.hash_despues,
    }


def hash_diff(change_id: str, plan: PlanEnmienda) -> str:
    return _sha256(_json_canonico(diff_canonico(change_id, plan)))


# --- Aplicación atómica ------------------------------------------------------

def _hash_cache_en_disco(change_dir: Path) -> Optional[str]:
    """Hash de la caché de `<change_dir>/control.json` si es legible; si no, None."""
    try:
        control = json.loads((change_dir / "control.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    cache = _rutas_cache(control)
    return hash_alcance(cache) if cache is not None else None


def aplicar_enmienda(change_dir, plan: PlanEnmienda, *, motivo: str, usuario: str,
                     fecha, campos_t1: dict, esperado_hash_antes: str,
                     utc: Optional[str] = None, change_id: Optional[str] = None) -> dict:
    """Agrega la entrada al historial de forma atómica. ValueError si algo no
    cuadra (nada se escribe). `change_id` se acepta por contrato del CLI y no
    se persiste (el directorio identifica al Change)."""
    change_dir = Path(change_dir)
    if plan.errores or plan.es_noop or not plan.operacion:
        raise ValueError("el plan no es aplicable (con errores o sin cambios efectivos)")
    if not isinstance(campos_t1, dict) or set(campos_t1.keys()) != set(CAMPOS_T1):
        raise ValueError("campos_t1 debe tener exactamente approval_channel, confirmed_at y channel_version")
    if campos_t1["approval_channel"] != CANAL_REQUERIDO:
        raise ValueError("approval_channel debe ser console_confirmed")
    for k in ("confirmed_at", "channel_version"):
        if not isinstance(campos_t1[k], str) or not campos_t1[k]:
            raise ValueError("campos_t1 incompletos")
    if plan.hash_antes != hash_alcance(plan.rutas_antes) \
            or plan.hash_despues != hash_alcance(plan.rutas_despues):
        raise ValueError("el plan es incoherente con sus hashes")
    if plan.hash_antes != esperado_hash_antes:
        raise ValueError("el plan no corresponde al hash esperado (scope cambiado)")

    path = ruta_archivo(change_dir)
    previo, entradas = "", []
    bytes_iniciales: Optional[bytes] = None
    if path.exists():
        try:
            bytes_iniciales = path.read_bytes()
            previo = bytes_iniciales.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError(f"historial ilegible ({type(exc).__name__})") from exc
        entradas, errores = _validar_cadena(previo, None)
        if errores:
            raise ValueError("historial de enmiendas inválido: " + "; ".join(errores))
    if entradas:
        actual = entradas[-1]["scope_hash_after"]
    else:
        actual = _hash_cache_en_disco(change_dir)
    if actual is not None and actual != esperado_hash_antes:
        raise ValueError("el scope cambió desde que se calculó el plan (hash actual distinto del esperado)")

    entrada = {
        "schema_version": SCHEMA_VERSION,
        "seq": len(entradas) + 1,
        "utc": utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "operacion": plan.operacion,
        "add": list(plan.add),
        "remove": list(plan.remove),
        "rutas_despues": list(plan.rutas_despues),
        "scope_hash_before": plan.hash_antes,
        "scope_hash_after": plan.hash_despues,
        "prev_hash": entradas[-1]["entry_hash"] if entradas else "",
        "motivo": motivo,
        "usuario": usuario,
        "fecha_declarada": fecha,
        "approval_channel": campos_t1["approval_channel"],
        "confirmed_at": campos_t1["confirmed_at"],
        "channel_version": campos_t1["channel_version"],
    }
    entrada["entry_hash"] = hash_entrada(entrada)

    if previo and not previo.endswith("\n"):
        previo += "\n"
    nuevo = previo + json.dumps(entrada, sort_keys=True, ensure_ascii=False) + "\n"

    change_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_nombre = tempfile.mkstemp(dir=str(change_dir), prefix=".amendments-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(nuevo.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        with open(tmp_nombre, "rb") as fh:
            _ents, errs = _validar_cadena(fh.read().decode("utf-8"), None)
        if errs:
            raise ValueError("la cadena resultante es inválida: " + "; ".join(errs))
        # Carrera: el registro no debe haber cambiado desde la lectura inicial.
        try:
            actuales = path.read_bytes() if path.exists() else None
        except OSError as exc:
            raise ValueError(f"no se pudo releer el historial ({type(exc).__name__})") from exc
        if actuales != bytes_iniciales:
            raise ValueError("el historial de enmiendas cambió durante la operación; se aborta sin escribir")
        os.replace(tmp_nombre, path)
    except BaseException:
        try:
            os.unlink(tmp_nombre)
        except OSError:
            pass
        raise
    return entrada
