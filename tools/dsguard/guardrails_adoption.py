"""Re-adopción de guardrails: closed list aditiva y registro encadenado (R39-R57).

Solo stdlib (más `guardrails_drift`, hermano del paquete); sin imports de `tools.*` ni de
ningún provider, sin consola y sin afirmaciones de autoría. El registro
`openspec/decisions/guardrails-adoptions.jsonl` NO es `ledger.jsonl` ni usa su semántica.

- `planificar_adopcion` es PURA: calcula el diff entre el `guardrails.json` actual y la
  baseline efectiva (plantilla + adopciones válidas) y acepta SOLO adiciones sobre la
  closed list `CLAVES_ELEGIBLES`. Cualquier otra diferencia rechaza TODO el plan (R43).
- `aplicar_adopcion` agrega una línea al registro de forma atómica (temporal + os.replace).
  NO modifica `.claude/guardrails.json` ni `control.json` (R46) ni el hash gestionado (R59).
- La cadena es detección de edición ingenua (hashes), no criptografía ni autoría.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from . import guardrails_drift

# Closed list EXACTA (R41); ampliarla requiere decisión material.
CLAVES_ELEGIBLES = ("holdouts", "data_raw", "secretos_extra", "autonomy.sealed_sources")
RUTA_REGISTRO_RELATIVA = "openspec/decisions/guardrails-adoptions.jsonl"
SCHEMA_VERSION = 1
COD_ADOPCION_INVALIDA = "GUARDRAILS-ADOPCION-INVALIDA"

CANAL_CONSOLE = "console_confirmed"
_MAX_LARGO_ELEMENTO = 512
_CAMPOS_ENTRADA = (
    "schema_version", "seq", "utc", "claves", "adiciones",
    "guardrails_hash_before", "guardrails_hash_after", "prev_hash",
    "motivo", "usuario", "fecha_declarada",
    "approval_channel", "confirmed_at", "channel_version", "entry_hash",
)
_RE_UNIDAD = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class ResultadoAdopciones:
    entradas: tuple
    valida: bool
    hallazgos: tuple


@dataclass(frozen=True)
class PlanAdopcion:
    adiciones: dict
    rechazos: tuple
    es_noop: bool
    hash_antes: str
    hash_despues: str
    # Identidad de la última entrada del registro al planificar (vacíos sin registro).
    ultima_seq: int = 0
    ultimo_entry_hash: str = ""


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def ruta_registro(repo_root) -> Path:
    return Path(repo_root) / Path(*RUTA_REGISTRO_RELATIVA.split("/"))


def _json_canonico(valor) -> str:
    return json.dumps(valor, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8", errors="surrogatepass")).hexdigest()


def _hash_entrada(entrada: dict) -> str:
    return _sha256(_json_canonico({k: v for k, v in entrada.items() if k != "entry_hash"}))


def _ahora_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hallazgo(detail: str, nivel: str = "error") -> dict:
    return {
        "code": COD_ADOPCION_INVALIDA,
        "path": RUTA_REGISTRO_RELATIVA,
        "detail": detail,
        "nivel": nivel,
    }


def _leer_clave(guardrails, clave: str):
    """(presente, valor) de una clave elegible; `autonomy.sealed_sources` es anidada."""
    if not isinstance(guardrails, dict):
        return False, None
    if clave == "autonomy.sealed_sources":
        autonomia = guardrails.get("autonomy")
        if isinstance(autonomia, dict) and "sealed_sources" in autonomia:
            return True, autonomia["sealed_sources"]
        return False, None
    if clave in guardrails:
        return True, guardrails[clave]
    return False, None


def _escribir_clave(guardrails: dict, clave: str, valor) -> None:
    if clave == "autonomy.sealed_sources":
        autonomia = guardrails.get("autonomy")
        if not isinstance(autonomia, dict):
            autonomia = {}
            guardrails["autonomy"] = autonomia
        autonomia["sealed_sources"] = valor
    else:
        guardrails[clave] = valor


def _motivo_elemento_invalido(elemento):
    """Motivo por el que un elemento no es adoptable, o None si es válido."""
    if not isinstance(elemento, str):
        return "no_es_string"
    if not elemento.strip():
        return "vacio"
    if len(elemento) > _MAX_LARGO_ELEMENTO:
        return "demasiado_largo"
    if elemento != elemento.strip():
        return "espacios_en_los_bordes"
    # Cc (control, incluye NUL/saltos/ESC), Cf (formato, bidi/ancho cero), Cs (surrogates),
    # Co (uso privado), Cn (sin asignar), Zl/Zp (separadores de línea/párrafo).
    if any(unicodedata.category(c) in _CATEGORIAS_PROHIBIDAS_ELEMENTO for c in elemento):
        return "caracter_de_control"
    if elemento[0] in ("/", "\\", "~") or _RE_UNIDAD.match(elemento):
        return "ruta_absoluta"
    if any(seg == ".." for seg in re.split(r"[\\/]", elemento)):
        return "traversal"
    return None


_CATEGORIAS_PROHIBIDAS_ELEMENTO = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")
_CATEGORIAS_PROHIBIDAS_TEXTO = ("Cc", "Cf", "Cs", "Zl", "Zp")
_MAX_MOTIVO = 500
_MAX_USUARIO = 200
_RE_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _texto_libre_valido(valor, maximo: int) -> bool:
    """String no vacío, ≤ maximo, sin categorías Cc/Cf/Cs/Zl/Zp."""
    return (
        isinstance(valor, str)
        and bool(valor.strip())
        and len(valor) <= maximo
        and not any(unicodedata.category(c) in _CATEGORIAS_PROHIBIDAS_TEXTO for c in valor)
    )


def _fecha_valida(valor) -> bool:
    """AAAA-MM-DD en dígitos ASCII y fecha calendario real."""
    if not isinstance(valor, str) or not _RE_FECHA.fullmatch(valor):
        return False
    try:
        date(int(valor[0:4]), int(valor[5:7]), int(valor[8:10]))
    except ValueError:
        return False
    return True


def _es_lista_de_strings(valor) -> bool:
    return isinstance(valor, list) and all(isinstance(x, str) for x in valor)


# ---------------------------------------------------------------------------
# Registro: carga y validación de cadena
# ---------------------------------------------------------------------------

def _sumar_adiciones(acum: dict, adiciones: dict) -> dict:
    """Copia de `acum` ({clave: [elementos]}) con `adiciones` agregadas sin duplicar."""
    nuevo = {k: list(v) for k, v in acum.items()}
    for clave in CLAVES_ELEGIBLES:
        for elemento in adiciones.get(clave, ()):
            lista = nuevo.setdefault(clave, [])
            if elemento not in lista:
                lista.append(elemento)
    return nuevo


def hash_acumulado(acum: dict) -> str:
    """sha256 del JSON canónico de las adiciones acumuladas (solo claves elegibles)."""
    return _sha256(_json_canonico({c: list(acum.get(c, ())) for c in CLAVES_ELEGIBLES}))


def _validar_entrada(entrada, indice: int, previa, acum):
    """Motivo de invalidez de la entrada `indice` (0-based) o None."""
    n = indice + 1
    if not isinstance(entrada, dict):
        return "linea_%d:no_es_objeto" % n
    if set(entrada) != set(_CAMPOS_ENTRADA):
        return "linea_%d:campos_inesperados" % n
    if entrada["schema_version"] != SCHEMA_VERSION or isinstance(entrada["schema_version"], bool):
        return "linea_%d:schema_version" % n
    if not isinstance(entrada["seq"], int) or isinstance(entrada["seq"], bool) or entrada["seq"] != n:
        return "linea_%d:seq_fuera_de_orden" % n
    for campo in ("utc", "guardrails_hash_before", "guardrails_hash_after", "motivo", "usuario",
                  "fecha_declarada", "confirmed_at", "channel_version", "entry_hash"):
        if not isinstance(entrada[campo], str) or not entrada[campo].strip():
            return "linea_%d:campo_invalido_%s" % (n, campo)
    if not isinstance(entrada["prev_hash"], str):
        return "linea_%d:campo_invalido_prev_hash" % n
    if not _texto_libre_valido(entrada["motivo"], _MAX_MOTIVO):
        return "linea_%d:motivo_invalido" % n
    if not _texto_libre_valido(entrada["usuario"], _MAX_USUARIO):
        return "linea_%d:usuario_invalido" % n
    if not _fecha_valida(entrada["fecha_declarada"]):
        return "linea_%d:fecha_declarada_invalida" % n
    if entrada["approval_channel"] != CANAL_CONSOLE:
        return "linea_%d:canal_no_console_confirmed" % n
    claves, adiciones = entrada["claves"], entrada["adiciones"]
    if not isinstance(claves, list) or not claves or not isinstance(adiciones, dict):
        return "linea_%d:claves_o_adiciones_invalidas" % n
    if any(c not in CLAVES_ELEGIBLES for c in claves) or any(c not in CLAVES_ELEGIBLES for c in adiciones):
        return "linea_%d:clave_fuera_de_closed_list" % n
    if sorted(set(claves)) != sorted(adiciones) or len(set(claves)) != len(claves):
        return "linea_%d:claves_inconsistentes" % n
    for clave, elementos in adiciones.items():
        if not isinstance(elementos, list) or not elementos or len(set(elementos)) != len(elementos):
            return "linea_%d:adiciones_invalidas_%s" % (n, clave)
        if any(_motivo_elemento_invalido(e) for e in elementos):
            return "linea_%d:elemento_invalido_%s" % (n, clave)
    esperado_prev = previa["entry_hash"] if previa else ""
    if entrada["prev_hash"] != esperado_prev:
        return "linea_%d:prev_hash_roto" % n
    if previa and entrada["guardrails_hash_before"] != previa["guardrails_hash_after"]:
        return "linea_%d:hash_before_no_encadena" % n
    # Los hashes son de las adiciones ACUMULADAS: independientes de la plantilla.
    if entrada["guardrails_hash_before"] != hash_acumulado(acum):
        return "linea_%d:hash_before_no_coincide_con_acumulado" % n
    if entrada["guardrails_hash_after"] != hash_acumulado(_sumar_adiciones(acum, adiciones)):
        return "linea_%d:hash_after_no_coincide_con_acumulado" % n
    if entrada["entry_hash"] != _hash_entrada(entrada):
        return "linea_%d:entry_hash_invalido" % n
    return None


def _validar_texto(texto: str) -> ResultadoAdopciones:
    if texto == "":
        return ResultadoAdopciones((), True, ())
    lineas = texto.split("\n")
    if lineas[-1] == "":
        lineas.pop()
    entradas = []
    acum: dict = {}
    for i, linea in enumerate(lineas):
        try:
            try:
                entrada = json.loads(linea)
            except ValueError:
                return ResultadoAdopciones((), False, (_hallazgo("linea_%d:json_invalido" % (i + 1)),))
            motivo = _validar_entrada(entrada, i, entradas[-1] if entradas else None, acum)
            if motivo:
                return ResultadoAdopciones((), False, (_hallazgo(motivo),))
            acum = _sumar_adiciones(acum, entrada["adiciones"])
        except Exception:  # incluye RecursionError, TypeError por no hashables, etc.
            return ResultadoAdopciones((), False, (_hallazgo("linea_%d:entrada_ilegible" % (i + 1)),))
        entradas.append(entrada)
    return ResultadoAdopciones(tuple(entradas), True, ())


def _leer_registro(ruta: Path):
    """Bytes del registro o None si está ausente. Lanza OSError ante otros fallos."""
    try:
        return ruta.read_bytes()
    except FileNotFoundError:
        return None


def cargar_adopciones(repo_root) -> ResultadoAdopciones:
    """Carga y valida la cadena. Ausente = válida y vacía; cualquier anomalía = ninguna cuenta."""
    ruta = ruta_registro(repo_root)
    try:
        crudo = _leer_registro(ruta)
    except OSError:
        return ResultadoAdopciones((), False, (_hallazgo("registro_ilegible"),))
    if crudo is None:
        return ResultadoAdopciones((), True, ())
    try:
        texto = crudo.decode("utf-8")
    except UnicodeDecodeError:
        return ResultadoAdopciones((), False, (_hallazgo("registro_no_utf8"),))
    return _validar_texto(texto)


# ---------------------------------------------------------------------------
# Baseline y hash de estado
# ---------------------------------------------------------------------------

def _adiciones_acumuladas(adopciones: ResultadoAdopciones) -> dict:
    """{clave: [elementos]} en orden de adopción, sin duplicados; vacío si la cadena no cuenta."""
    acumuladas: dict = {}
    if not adopciones.valida:
        return acumuladas
    for entrada in adopciones.entradas:
        for clave in CLAVES_ELEGIBLES:
            for elemento in entrada["adiciones"].get(clave, ()):
                lista = acumuladas.setdefault(clave, [])
                if elemento not in lista:
                    lista.append(elemento)
    return acumuladas


def baseline_efectivo(plantilla: dict, adopciones: ResultadoAdopciones) -> dict:
    """Copia de la plantilla con cada clave elegible = plantilla + adiciones acumuladas válidas."""
    baseline = copy.deepcopy(plantilla)
    for clave, elementos in _adiciones_acumuladas(adopciones).items():
        presente, valor = _leer_clave(baseline, clave)
        base = list(valor) if presente and isinstance(valor, list) else []
        for elemento in elementos:
            if elemento not in base:
                base.append(elemento)
        _escribir_clave(baseline, clave, base)
    return baseline


def hash_estado(baseline: dict) -> str:
    """sha256 del JSON canónico SOLO del subconjunto de claves elegibles."""
    subconjunto = {}
    for clave in CLAVES_ELEGIBLES:
        presente, valor = _leer_clave(baseline, clave)
        subconjunto[clave] = valor if presente else None
    return _sha256(_json_canonico(subconjunto))


# ---------------------------------------------------------------------------
# Planificación (pura)
# ---------------------------------------------------------------------------

def _rechazar(motivos, hash_antes: str = "", seq: int = 0, ultimo: str = "") -> PlanAdopcion:
    return PlanAdopcion({}, tuple(motivos), False, hash_antes, "", seq, ultimo)


def planificar_adopcion(actual: dict, plantilla: dict, adopciones: ResultadoAdopciones) -> PlanAdopcion:
    """Plan de adopción aditiva sobre la closed list; rechazo TOTAL ante cualquier otra cosa.

    Nunca propaga excepciones: un fallo inesperado (incl. RecursionError) es un rechazo."""
    try:
        return _planificar(actual, plantilla, adopciones)
    except Exception as exc:  # noqa: BLE001 - fail-closed
        return _rechazar(["error_interno:%s" % type(exc).__name__])


def _planificar(actual, plantilla, adopciones) -> PlanAdopcion:
    if not isinstance(actual, dict):
        return _rechazar(["guardrails_actual_malformado"])
    if not isinstance(plantilla, dict):
        return _rechazar(["plantilla_malformada"])
    if not isinstance(adopciones, ResultadoAdopciones) or not adopciones.valida:
        return _rechazar(["cadena_de_adopciones_invalida"])
    base = baseline_efectivo(plantilla, adopciones)
    acum = _adiciones_acumuladas(adopciones)
    # Hash de las adiciones ACUMULADAS: no depende del contenido de la plantilla.
    hash_antes = hash_acumulado(acum)
    ultima = adopciones.entradas[-1] if adopciones.entradas else None
    seq = ultima["seq"] if ultima else 0
    ultimo = ultima["entry_hash"] if ultima else ""
    try:
        rutas = guardrails_drift.comparar(actual, base)
    except ValueError:
        return _rechazar(["guardrails_actual_malformado"], hash_antes, seq, ultimo)

    rechazos = []
    adiciones: dict = {}
    for ruta in rutas:
        if ruta not in CLAVES_ELEGIBLES:
            rechazos.append("clave_no_elegible:%s" % ruta)
            continue
        pres_a, val_a = _leer_clave(actual, ruta)
        pres_b, val_b = _leer_clave(base, ruta)
        if not pres_a:
            rechazos.append("remocion:%s" % ruta)
            continue
        if not _es_lista_de_strings(val_a):
            rechazos.append("tipo_invalido:%s" % ruta)
            continue
        if pres_b and not _es_lista_de_strings(val_b):
            rechazos.append("baseline_tipo_invalido:%s" % ruta)
            continue
        elementos_base = list(val_b) if pres_b else []
        # Duplicados y orden se tratan como conjunto (valores ya validados como str).
        conjunto_base = set(elementos_base)
        if not conjunto_base <= set(val_a):
            rechazos.append("remocion_o_reemplazo:%s" % ruta)
            continue
        nuevos = []
        for e in val_a:
            if e not in conjunto_base and e not in nuevos:
                nuevos.append(e)
        if any(_motivo_elemento_invalido(e) for e in nuevos):
            rechazos.append("elemento_invalido:%s" % ruta)
            continue
        if nuevos:
            adiciones[ruta] = tuple(nuevos)
        # Sin nuevos: solo duplicados/reorden (igualdad de conjuntos); no es adopción.
    if rechazos:
        return _rechazar(rechazos, hash_antes, seq, ultimo)
    if not adiciones:
        return PlanAdopcion({}, (), True, hash_antes, hash_antes, seq, ultimo)
    hash_despues = hash_acumulado(_sumar_adiciones(acum, adiciones))
    return PlanAdopcion(adiciones, (), False, hash_antes, hash_despues, seq, ultimo)


def diff_canonico(plan: PlanAdopcion) -> dict:
    return {
        "operacion": "guardrails-readopt",
        "target": "guardrails.json",
        "hash_antes": plan.hash_antes,
        "adiciones": {clave: list(plan.adiciones[clave]) for clave in sorted(plan.adiciones)},
        "hash_despues": plan.hash_despues,
    }


def hash_diff(plan: PlanAdopcion) -> str:
    return _sha256(_json_canonico(diff_canonico(plan)))


# ---------------------------------------------------------------------------
# Aplicación atómica
# ---------------------------------------------------------------------------

def _texto_no_vacio(valor, nombre: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError("%s requerido (string no vacío)" % nombre)
    return valor


def aplicar_adopcion(repo_root, plan: PlanAdopcion, *, motivo, usuario, fecha, campos_t1,
                     esperado_hash_antes, utc=None) -> dict:
    """Agrega una entrada al registro. Lanza ValueError sin escribir ante cualquier conflicto."""
    if not isinstance(plan, PlanAdopcion):
        raise ValueError("plan inválido")
    if plan.rechazos:
        raise ValueError("el plan tiene rechazos; no se aplica")
    if plan.es_noop or not plan.adiciones:
        raise ValueError("el plan es no-op; no hay nada que registrar")
    if not _texto_libre_valido(motivo, _MAX_MOTIVO):
        raise ValueError("motivo inválido (vacío, > %d o con caracteres de control)" % _MAX_MOTIVO)
    if not _texto_libre_valido(usuario, _MAX_USUARIO):
        raise ValueError("usuario inválido (vacío, > %d o con caracteres de control)" % _MAX_USUARIO)
    if not _fecha_valida(fecha):
        raise ValueError("fecha inválida (se espera AAAA-MM-DD ASCII y válida)")
    if (
        not isinstance(campos_t1, dict)
        or campos_t1.get("approval_channel") != CANAL_CONSOLE
        or not isinstance(campos_t1.get("confirmed_at"), str) or not campos_t1["confirmed_at"].strip()
        or not isinstance(campos_t1.get("channel_version"), str) or not campos_t1["channel_version"].strip()
    ):
        raise ValueError("campos_t1 debe ser una aprobación console_confirmed completa")
    if plan.hash_antes != esperado_hash_antes:
        raise ValueError("conflicto: el hash del estado cambió respecto de lo esperado")
    if any(c not in CLAVES_ELEGIBLES for c in plan.adiciones):
        raise ValueError("clave fuera de la closed list")
    for clave, elementos in plan.adiciones.items():
        if not elementos or any(_motivo_elemento_invalido(e) for e in elementos):
            raise ValueError("adición inválida en %s" % clave)

    ruta = ruta_registro(repo_root)
    # Releer y revalidar inmediatamente antes de escribir.
    try:
        crudo = _leer_registro(ruta)
    except OSError as exc:
        raise ValueError("registro ilegible") from exc
    previo = b"" if crudo is None else crudo
    try:
        actual = _validar_texto(previo.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("registro no es UTF-8") from exc
    if not actual.valida:
        raise ValueError("cadena de adopciones inválida: " + actual.hallazgos[0]["detail"])
    ultima = actual.entradas[-1] if actual.entradas else None
    seq_actual = ultima["seq"] if ultima else 0
    hash_actual = ultima["entry_hash"] if ultima else ""
    if seq_actual != plan.ultima_seq or hash_actual != plan.ultimo_entry_hash:
        raise ValueError("conflicto: el registro cambió desde que se calculó el plan")
    acum = _adiciones_acumuladas(actual)
    if hash_acumulado(acum) != plan.hash_antes:
        raise ValueError("conflicto: las adiciones acumuladas no coinciden con el plan")
    if hash_acumulado(_sumar_adiciones(acum, plan.adiciones)) != plan.hash_despues:
        raise ValueError("plan inconsistente: hash_despues no coincide con las adiciones")

    entrada = {
        "schema_version": SCHEMA_VERSION,
        "seq": len(actual.entradas) + 1,
        "utc": utc if isinstance(utc, str) and utc else _ahora_utc(),
        "claves": sorted(plan.adiciones),
        "adiciones": {c: list(plan.adiciones[c]) for c in sorted(plan.adiciones)},
        "guardrails_hash_before": plan.hash_antes,
        "guardrails_hash_after": plan.hash_despues,
        "prev_hash": ultima["entry_hash"] if ultima else "",
        "motivo": motivo,
        "usuario": usuario,
        "fecha_declarada": fecha,
        "approval_channel": CANAL_CONSOLE,
        "confirmed_at": campos_t1["confirmed_at"],
        "channel_version": campos_t1["channel_version"],
    }
    entrada["entry_hash"] = _hash_entrada(entrada)

    linea = (_json_canonico(entrada) + "\n").encode("utf-8")
    if previo and not previo.endswith(b"\n"):
        previo += b"\n"
    contenido = previo + linea

    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporal = tempfile.mkstemp(dir=str(ruta.parent), prefix=".guardrails-adoptions.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as fh:
            fh.write(contenido)
            fh.flush()
            os.fsync(fh.fileno())
        verificado = _validar_texto(Path(temporal).read_bytes().decode("utf-8"))
        if not verificado.valida or len(verificado.entradas) != len(actual.entradas) + 1:
            raise ValueError("la cadena resultante no es válida; no se escribe")
        # Última comprobación de carrera: el registro no debe haber cambiado desde la lectura.
        if _leer_registro(ruta) != crudo:
            raise ValueError("conflicto: el registro cambió durante la operación")
        os.replace(temporal, str(ruta))
    except BaseException:
        try:
            os.unlink(temporal)
        except OSError:
            pass
        raise
    return entrada


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------

def rutas_cubiertas(actual: dict, plantilla: dict, adopciones: ResultadoAdopciones) -> set:
    """Rutas de drift contra la plantilla cubiertas EXACTAMENTE por adopciones válidas."""
    if not isinstance(actual, dict) or not isinstance(plantilla, dict):
        return set()
    if not isinstance(adopciones, ResultadoAdopciones) or not adopciones.valida:
        return set()
    try:
        rutas = guardrails_drift.comparar(actual, plantilla)
    except ValueError:
        return set()
    acumuladas = _adiciones_acumuladas(adopciones)
    cubiertas = set()
    for ruta in rutas:
        if ruta not in CLAVES_ELEGIBLES:
            continue
        pres_a, val_a = _leer_clave(actual, ruta)
        pres_p, val_p = _leer_clave(plantilla, ruta)
        if not pres_a or not _es_lista_de_strings(val_a):
            continue
        if pres_p and not _es_lista_de_strings(val_p):
            continue
        if not acumuladas.get(ruta):
            continue  # sin adopción para esta ruta, el drift sigue siendo drift
        esperado = set(val_p if pres_p else ()) | set(acumuladas[ruta])
        if set(val_a) == esperado:
            cubiertas.add(ruta)
    return cubiertas
