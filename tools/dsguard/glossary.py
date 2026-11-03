"""Parser y validador determinista de `GLOSSARY.md` (Change 20261014-domain-modeling).

Solo stdlib y `.core`. No importa cards, decision, datacontracts ni proveedores:
el verificador de aprobaciones se inyecta como `resolver` (fail-closed si falta).
Funciones puras salvo `evaluar_glossary` (lee el archivo) y la verificacion del
artefacto aprobado (lectura).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .core import Finding

RUTA_GLOSSARY = "GLOSSARY.md"
ESTADOS = ("hypothesis", "approved")
AMBIGUEDADES = ("none", "material")
CAMPOS_PERMITIDOS = ("estado", "definicion", "ambiguedad", "approval_ref", "definition_hash")

COD_CAMPO_DESCONOCIDO = "GLOSSARY-CAMPO-DESCONOCIDO"
COD_MALFORMADO = "GLOSSARY-MALFORMADO"
COD_TERMINO_DUPLICADO = "GLOSSARY-TERMINO-DUPLICADO"
COD_ESTADO_INVALIDO = "GLOSSARY-ESTADO-INVALIDO"
COD_DEFINICION_AUSENTE = "GLOSSARY-DEFINICION-AUSENTE"
COD_AMBIGUEDAD_INVALIDA = "GLOSSARY-AMBIGUEDAD-INVALIDA"
COD_CAMPO_INESPERADO = "GLOSSARY-CAMPO-INESPERADO"
COD_APROBACION_AUSENTE = "GLOSSARY-APROBACION-AUSENTE"
COD_APROBACION_OBSOLETA = "GLOSSARY-APROBACION-OBSOLETA"
COD_AMBIGUEDAD_EN_APPROVED = "GLOSSARY-AMBIGUEDAD-EN-APPROVED"
COD_APROBACION_INVALIDA = "GLOSSARY-APROBACION-INVALIDA"
COD_APROBACION_SIN_T1 = "GLOSSARY-APROBACION-SIN-T1"
COD_APROBACION_NO_VINCULA = "GLOSSARY-APROBACION-NO-VINCULA"


@dataclass
class Entrada:
    termino: Optional[str] = None
    estado: Optional[str] = None
    definicion: Optional[str] = None
    ambiguedad: Optional[str] = "none"
    approval_ref: Optional[str] = None
    definition_hash: Optional[str] = None
    linea: Optional[int] = None


# --- Hash y approval_ref --------------------------------------------------------

def _normalizar(texto: str) -> str:
    """Colapsa todo whitespace (incluye EOL) a un espacio y recorta."""
    return " ".join(texto.split())


def clave_termino(termino: str) -> str:
    """Clave canonica de un termino: NFC + whitespace colapsado + strip + casefold."""
    t = _normalizar(unicodedata.normalize("NFC", termino)).casefold()
    return unicodedata.normalize("NFC", t)


def definition_hash(termino: str, definicion: str) -> str:
    base = clave_termino(termino) + "\n" + _normalizar(definicion)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


_RE_HASH = re.compile(r"[0-9a-f]{64}")


def parsear_approval_ref(valor: str) -> Optional[dict]:
    if not isinstance(valor, str):
        return None
    valor = valor.strip()
    if "/" not in valor or "@" not in valor:
        return None
    change_id, resto = valor.split("/", 1)
    if "@" not in resto:
        return None
    artefacto, hash_ = resto.rsplit("@", 1)
    if not change_id or not artefacto or not _RE_HASH.fullmatch(hash_):
        return None
    return {"change_id": change_id, "artefacto": artefacto, "hash": hash_}


# --- Parser ---------------------------------------------------------------------

_RE_COMENTARIO = re.compile(r"<!--.*?-->", re.DOTALL)
_RE_ENCABEZADO = re.compile(r"^##(?!#)\s*(.*?)\s*$")
_RE_BULLET = re.compile(r"^[-*]\s+([^:]*?)\s*:\s*(.*?)\s*$")


def _quitar_comentarios(texto: str) -> str:
    """Quita comentarios HTML conservando los saltos de linea (numeracion estable)."""
    return _RE_COMENTARIO.sub(lambda m: "\n" * m.group(0).count("\n"), texto)


def _blanquear_cercas(texto: str) -> tuple[str, Optional[int], list[int]]:
    """Reemplaza por lineas vacias los bloques cercados (``` o ~~~, marcadores
    incluidos). Devuelve (texto, linea_de_apertura_sin_cerrar | None,
    lineas_de_apertura_dentro_de_una_entrada).

    Cercas en el preambulo (antes del primer `## termino`) se permiten. Dentro de
    una entrada se reportan (su texto queda fuera de la definicion y del hash).
    Los comentarios HTML dentro de una entrada si se permiten: son anotaciones y
    quedan fuera de la definicion y del definition_hash."""
    salida: list[str] = []
    marca: Optional[str] = None
    apertura = 0
    en_entrada = False
    dentro: list[int] = []
    for n, linea in enumerate(texto.split("\n"), start=1):
        s = linea.lstrip()
        if marca is None:
            if s.startswith("```") or s.startswith("~~~"):
                marca = s[:3]
                apertura = n
                if en_entrada:
                    dentro.append(n)
                salida.append("")
                continue
            if _RE_ENCABEZADO.match(linea):
                en_entrada = True
            salida.append(linea)
        else:
            if s.startswith(marca):
                marca = None
            salida.append("")
    return "\n".join(salida), (apertura if marca is not None else None), dentro


def _ubic(termino: Optional[str]) -> str:
    return f"{RUTA_GLOSSARY}#{termino}" if termino else RUTA_GLOSSARY


def parsear_glossary(texto: str) -> tuple[list[Entrada], list[Finding]]:
    entradas: list[Entrada] = []
    hallazgos: list[Finding] = []
    vistos: set[str] = set()

    actual: Optional[Entrada] = None
    campos_vistos: set[str] = set()
    ultimo: Optional[str] = None  # campo almacenado que admite continuacion

    # Primero cercas (un `<!--` dentro de una cerca no debe consumir contenido real),
    # despues comentarios HTML.
    texto, sin_cerrar, cercas_dentro = _blanquear_cercas(texto.replace("\r\n", "\n").replace("\r", "\n"))
    for n_cerca in cercas_dentro:
        hallazgos.append(Finding(
            COD_MALFORMADO,
            f"linea {n_cerca}: bloque de codigo dentro de entrada: no forma parte de la definicion",
            RUTA_GLOSSARY))
    if sin_cerrar is not None:
        hallazgos.append(Finding(COD_MALFORMADO, f"linea {sin_cerrar}: bloque de codigo sin cerrar", RUTA_GLOSSARY))
    texto = _quitar_comentarios(texto)
    for n, linea in enumerate(texto.split("\n"), start=1):
        if not linea.strip():
            continue

        if linea.startswith("#"):
            m = _RE_ENCABEZADO.match(linea)
            if m is None:  # titulo de nivel 1 o 3+: no abre entrada
                if actual is not None:
                    hallazgos.append(Finding(COD_MALFORMADO, f"linea {n}: encabezado dentro de entrada", _ubic(actual.termino)))
                actual = None
                ultimo = None
                continue
            termino = m.group(1)
            ultimo = None
            campos_vistos = set()
            if not termino:
                hallazgos.append(Finding(COD_MALFORMADO, f"linea {n}: encabezado '##' sin termino", RUTA_GLOSSARY))
                actual = None
                continue
            actual = Entrada(termino=termino, linea=n)
            clave = clave_termino(termino)
            if clave in vistos:
                hallazgos.append(Finding(COD_TERMINO_DUPLICADO, f"termino duplicado: {termino!r}", _ubic(termino)))
            vistos.add(clave)
            entradas.append(actual)
            continue

        if actual is None:
            continue  # prosa fuera de entradas

        if linea[:2] == "  " or linea[:1] == "\t":
            if ultimo is None:
                hallazgos.append(Finding(COD_MALFORMADO, f"linea {n}: continuacion sin campo previo", _ubic(actual.termino)))
                continue
            previo = getattr(actual, ultimo) or ""
            setattr(actual, ultimo, (previo + " " + linea.strip()).strip())
            continue

        m = _RE_BULLET.match(linea)
        if m is None:
            hallazgos.append(Finding(COD_MALFORMADO, f"linea {n}: no es un bullet '- campo: valor'", _ubic(actual.termino)))
            ultimo = None
            continue
        campo, valor = m.group(1), m.group(2)
        if campo in campos_vistos:
            hallazgos.append(Finding(COD_MALFORMADO, f"linea {n}: campo repetido {campo!r}", _ubic(actual.termino)))
            ultimo = None
            continue
        campos_vistos.add(campo)
        if campo not in CAMPOS_PERMITIDOS:
            hallazgos.append(Finding(COD_CAMPO_DESCONOCIDO, f"linea {n}: campo desconocido {campo!r}", _ubic(actual.termino)))
            ultimo = None
            continue
        setattr(actual, campo, valor)
        ultimo = campo

    return entradas, hallazgos


# --- Validador ------------------------------------------------------------------

def _ruta_segura(base: Path, partes: str) -> Optional[Path]:
    if not partes or "\\" in partes or partes.startswith("/") or re.match(r"^[A-Za-z]:", partes):
        return None
    segmentos = partes.split("/")
    # Rechaza segmentos vacios, `.`, `..` y letras de unidad (`C:`) en cualquier segmento.
    if any(s in ("", ".", "..") or re.match(r"^[A-Za-z]:", s) for s in segmentos):
        return None
    return base.joinpath(*segmentos)


def _vincula(repo_root, ref: dict, hash_entrada: str) -> bool:
    """Vinculo artefacto<->hash. LIMITE INHERENTE: es textual; un hash citado en
    cualquier otro contexto del artefacto aprobado (fuera de comentarios HTML y
    como token hex completo) lo satisface. No prueba autoria ni intencion."""
    if repo_root is None:
        return False
    change_id = ref["change_id"]
    if _ruta_segura(Path(repo_root), change_id) is None or "/" in change_id:
        return False
    raiz = Path(repo_root) / "openspec"
    for sub in ("changes", "archive"):
        cambio = raiz / sub / change_id
        ruta = _ruta_segura(cambio, ref["artefacto"])
        if ruta is None:
            return False
        if ruta.is_file():
            try:
                # Un symlink que sale del directorio del Change no vale.
                if not ruta.resolve().is_relative_to(cambio.resolve()):
                    return False
                contenido = ruta.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError, ValueError):
                return False
            contenido = _RE_COMENTARIO.sub("", contenido)
            patron = r"(?<![0-9a-fA-F])" + re.escape(hash_entrada) + r"(?![0-9a-fA-F])"
            return re.search(patron, contenido, re.IGNORECASE) is not None
    return False


def _validar_aprobacion(e: Entrada, repo_root, resolver) -> Optional[Finding]:
    ub = _ubic(e.termino)
    if not e.approval_ref or not e.definition_hash:
        return Finding(COD_APROBACION_AUSENTE, f"{e.termino!r}: approved requiere approval_ref y definition_hash", ub)
    if e.definicion and e.definition_hash.lower() != definition_hash(e.termino, e.definicion):
        return Finding(COD_APROBACION_OBSOLETA, f"{e.termino!r}: la definicion cambio despues de aprobarse", ub)
    ref = parsear_approval_ref(e.approval_ref)
    if ref is None:
        return Finding(COD_APROBACION_INVALIDA, f"{e.termino!r}: approval_ref con formato invalido", ub)
    if resolver is None:
        return Finding(COD_APROBACION_INVALIDA, f"{e.termino!r}: sin resolver de aprobaciones (fail-closed)", ub)
    try:
        res = resolver(ref)
    except Exception as exc:  # fail-closed
        return Finding(COD_APROBACION_INVALIDA, f"{e.termino!r}: el resolver fallo ({type(exc).__name__})", ub)
    if getattr(res, "state", None) != "verified":
        return Finding(COD_APROBACION_INVALIDA, f"{e.termino!r}: aprobacion no verificada", ub)
    if getattr(res, "trust_tier", None) != "T1":
        return Finding(COD_APROBACION_SIN_T1, f"{e.termino!r}: la aprobacion no es T1 (presencia humana)", ub)
    if not _vincula(repo_root, ref, e.definition_hash):
        return Finding(COD_APROBACION_NO_VINCULA, f"{e.termino!r}: el artefacto aprobado no contiene el definition_hash", ub)
    return None


def validar_glossary(
    entradas: list[Entrada],
    repo_root=None,
    resolver: Optional[Callable] = None,
) -> tuple[list[Finding], list[str]]:
    hallazgos: list[Finding] = []
    pendientes: list[str] = []
    for e in entradas:
        ub = _ubic(e.termino)
        estado_ok = e.estado in ESTADOS
        if not estado_ok:
            hallazgos.append(Finding(COD_ESTADO_INVALIDO, f"{e.termino!r}: estado ausente o desconocido ({e.estado!r})", ub))
        definicion_ok = bool(e.definicion and e.definicion.strip())
        if not definicion_ok:
            hallazgos.append(Finding(COD_DEFINICION_AUSENTE, f"{e.termino!r}: definicion vacia o ausente", ub))
        amb = e.ambiguedad
        if amb not in AMBIGUEDADES:
            hallazgos.append(Finding(COD_AMBIGUEDAD_INVALIDA, f"{e.termino!r}: ambiguedad invalida ({amb!r})", ub))

        if e.estado == "hypothesis":
            if e.approval_ref is not None or e.definition_hash is not None:
                hallazgos.append(Finding(COD_CAMPO_INESPERADO, f"{e.termino!r}: hypothesis no admite approval_ref/definition_hash", ub))
            if amb == "material":
                pendientes.append(e.termino)
        elif e.estado == "approved":
            if amb == "material":
                hallazgos.append(Finding(COD_AMBIGUEDAD_EN_APPROVED, f"{e.termino!r}: ambiguedad material en approved", ub))
            if definicion_ok:
                h = _validar_aprobacion(e, repo_root, resolver)
                if h is not None:
                    hallazgos.append(h)
    return hallazgos, pendientes


def evaluar_glossary(repo_root, resolver: Optional[Callable] = None) -> tuple[list[Finding], list[str]]:
    ruta = Path(repo_root) / RUTA_GLOSSARY
    if not ruta.exists():
        return [], []
    try:
        texto = ruta.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return [Finding(COD_MALFORMADO, f"GLOSSARY.md ilegible: {type(exc).__name__}", RUTA_GLOSSARY)], []
    entradas, h_parseo = parsear_glossary(texto)
    h_val, pendientes = validar_glossary(entradas, repo_root, resolver)
    return h_parseo + h_val, pendientes
