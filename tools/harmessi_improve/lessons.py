"""Biblioteca de lessons verificables (v0.14 Change 5, R1-R6).

Por qué existe: lo aprendido en un ciclo de mejora solo es reutilizable si es (a) genérico, sin
conocimiento del proyecto ni datos sensibles, (b) respaldado por evidencia que se puede recomputar y
(c) acotado a los contextos donde se observó. Este módulo guarda esas lessons y decide cuáles aplican.

Principios:
- El estado lo calcula el módulo, nunca el llamador: `evidence-backed` solo si la decisión recomputada
  (`decision.decidir`) coincide con `decision_hash`/`suite_id`, su veredicto es `candidate_better` o
  `baseline_better` y la política tiene `repeats >= 2`; si no, `hypothesis` (R2).
- Creación gobernada: exige un Change abierto (`promotion.verificar_change_abierto`) (R4). Ninguna otra
  función del paquete (probe/decision/promotion/cycle) escribe lessons.
- Privacidad (R3): texto invariante bajo `redactar_texto`, sin rutas, emails, tokens ni términos del
  GLOSSARY. Se re-escanea al aplicar.
- `lessons_aplicables` (R5) no globaliza: sin intersección de contextos la lesson no aplica.
- Escritura atómica en `.harmessi/improvement/lessons/<id>.json`, sin enlaces (R6).
Solo stdlib y paquetes permitidos; sin red ni subprocess.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tools.dsguard import glossary as _glossary
from tools.harmessi_bench.redact import redactar_texto
from tools.harmessi_improve import candidate as _candidate
from tools.harmessi_improve import decision as _decision
from tools.harmessi_improve.budget import (
    PresupuestoInvalido,
    bloqueo,
    es_enlace,
    escribir_atomico,
    raiz_improvement,
    verificar_dentro_de_improvement,
)
from tools.harmessi_improve.policy import ProbePolicy
from tools.harmessi_improve.promotion import verificar_change_abierto

LESSON_CONTRACT_VERSION = 1
DIR_LESSONS = "lessons"
MAX_PATTERN = 200
MAX_RECOMMENDATION = 500
MAX_CONTEXTOS = 5

ESTADO_EVIDENCE_BACKED = "evidence-backed"
ESTADO_HYPOTHESIS = "hypothesis"
ESTADO_DEPRECATED = "deprecated"
ESTADOS = (ESTADO_EVIDENCE_BACKED, ESTADO_HYPOTHESIS, ESTADO_DEPRECATED)

# Códigos de rechazo
CONTENIDO_SENSIBLE = "CONTENIDO_SENSIBLE"
CONOCIMIENTO_DEL_PROYECTO = "CONOCIMIENTO_DEL_PROYECTO"
EVIDENCIA_NO_VERIFICABLE = "EVIDENCIA_NO_VERIFICABLE"
SIN_CHANGE = "SIN_CHANGE"
CAMPO_INVALIDO = "CAMPO_INVALIDO"
ESTADO_INVALIDO = "ESTADO_INVALIDO"
LESSON_CORRUPTA = "LESSON_CORRUPTA"

_RE_TAG = re.compile(r"[a-z0-9][a-z0-9-]{1,39}")
_RE_LESSON_ID = re.compile(r"les-[0-9a-f]{12}")
_RE_ID_TEXTO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
_RE_UNIDAD = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]")  # solo unidad real: letra + ':' + separador
_EXTENSIONES = r"(?:py|ipynb|yaml|yml|json|csv|sql|md|txt)"
_RE_RUTA_POSIX = re.compile(
    r"(?<![\w/])/[\w.~-]+/"                                  # /palabra/...
    r"|(?<![\w/.-])[\w.-]+/[\w.-]+/[\w.-]+"                 # relativa con 2+ barras
    r"|(?<![\w/.-])[\w.-]+/[\w.-]+\.\w{1,5}(?!\w)"          # 2 segmentos con extension
    r"|(?<![\w.-])[\w-]+\." + _EXTENSIONES + r"(?!\w)"       # nombre de archivo conocido
    r"|~/"                                                    # home
    r"|(?<![\w.])\.\.(?:/|$)|/\.\.",                          # relativos con '..'
    re.IGNORECASE)
_CLAVES_BASE = (
    "contract_version", "lesson_id", "pattern", "recommendation", "applicability", "evidence_refs",
    "status", "created_utc", "lesson_hash",
)
_CLAVES_DEPRECADA = _CLAVES_BASE + ("deprecated_reason", "deprecated_utc")
_CLAVES_REF = ("probe_id", "decision_hash", "suite_id")
_VEREDICTOS_RESPALDAN = (_decision.VER_CANDIDATE_MEJOR, _decision.VER_BASELINE_MEJOR)


class LessonRechazada(Exception):
    """La lesson no cumple una regla; `codigo` identifica cuál."""

    def __init__(self, codigo: str, mensaje: str = "") -> None:
        self.codigo = codigo
        self.mensaje = mensaje
        super().__init__(f"{codigo}: {mensaje}" if mensaje else codigo)


# --- Utilidades --------------------------------------------------------------------

def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json_bytes(datos: dict) -> bytes:
    return (json.dumps(datos, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _hash_lesson(lesson: dict) -> str:
    """sha256 del JSON canónico del contenido SIN el campo `lesson_hash`."""
    sin_hash = {k: v for k, v in lesson.items() if k != "lesson_hash"}
    return hashlib.sha256(_canon(sin_hash).encode("utf-8")).hexdigest()


def _id_de_contenido(pattern: str, recommendation: str, contextos: list, refs: list) -> str:
    contenido = {"contract_version": LESSON_CONTRACT_VERSION, "pattern": pattern,
                 "recommendation": recommendation, "contexts": contextos, "evidence_refs": refs}
    return "les-" + hashlib.sha256(_canon(contenido).encode("utf-8")).hexdigest()[:12]


def _ruta_lesson(repo_root, lesson_id: str) -> Path:
    if not isinstance(lesson_id, str) or _RE_LESSON_ID.fullmatch(lesson_id) is None:
        raise LessonRechazada(CAMPO_INVALIDO, f"lesson_id inválido: {lesson_id!r}")
    ruta = raiz_improvement(repo_root) / DIR_LESSONS / f"{lesson_id}.json"
    try:
        return verificar_dentro_de_improvement(repo_root, ruta)
    except PresupuestoInvalido:
        raise LessonRechazada(CAMPO_INVALIDO, "ruta de lesson fuera de .harmessi/improvement") from None


# --- Privacidad (R3) ---------------------------------------------------------------

def _terminos_glossary(repo_root) -> list:
    """Términos normalizados con la misma función que usa `candidate` (un solo lugar)."""
    try:
        return _candidate.terminos_glossary_normalizados(repo_root)
    except Exception as exc:  # noqa: BLE001 - fail-closed
        raise LessonRechazada(CONOCIMIENTO_DEL_PROYECTO, f"GLOSSARY ilegible: {type(exc).__name__}") from None


def _escanear_texto(texto: str, terminos: list, campo: str) -> None:
    """Lanza `LessonRechazada` si `texto` tiene datos sensibles o conocimiento del proyecto."""
    if redactar_texto(texto) != texto:
        raise LessonRechazada(CONTENIDO_SENSIBLE, f"{campo}: contiene datos sensibles (email/token)")
    if "\\" in texto or "://" in texto or _RE_UNIDAD.search(texto) or _RE_RUTA_POSIX.search(texto):
        raise LessonRechazada(CONTENIDO_SENSIBLE, f"{campo}: contiene una ruta o URL")
    if _candidate.contiene_termino_normalizado(texto, terminos):
        raise LessonRechazada(CONOCIMIENTO_DEL_PROYECTO, f"{campo}: contiene un término del GLOSSARY")


def _escanear_lesson(terminos: list, pattern: str, recommendation: str, contextos: list, refs: list) -> None:
    """Privacidad + GLOSSARY sobre pattern, recommendation, tags y probe_id/suite_id de las refs."""
    _escanear_texto(pattern, terminos, "pattern")
    _escanear_texto(recommendation, terminos, "recommendation")
    for tag in contextos:
        _escanear_texto(tag, terminos, "contexts")
    for ref in refs:
        _escanear_texto(ref["probe_id"], terminos, "evidence_refs.probe_id")
        _escanear_texto(ref["suite_id"], terminos, "evidence_refs.suite_id")


# --- Validación de campos ----------------------------------------------------------

def _texto(valor, campo: str, maximo: int) -> str:
    if not isinstance(valor, str) or not valor.strip() or "\x00" in valor:
        raise LessonRechazada(CAMPO_INVALIDO, f"{campo}: debe ser un texto no vacío")
    if len(valor) > maximo:
        raise LessonRechazada(CAMPO_INVALIDO, f"{campo}: supera {maximo} caracteres")
    return valor


def _validar_contextos(contexts) -> list:
    if isinstance(contexts, (str, bytes)) or not isinstance(contexts, (list, tuple)):
        raise LessonRechazada(CAMPO_INVALIDO, "contexts: debe ser una lista de tags")
    tags = sorted(set(contexts)) if all(isinstance(t, str) for t in contexts) else None
    if not tags or len(tags) > MAX_CONTEXTOS or any(_RE_TAG.fullmatch(t) is None for t in tags):
        raise LessonRechazada(CAMPO_INVALIDO, f"contexts: 1-{MAX_CONTEXTOS} tags ^[a-z0-9][a-z0-9-]{{1,39}}$")
    return tags


def _validar_refs(evidence_refs) -> list:
    if isinstance(evidence_refs, (str, bytes)) or not isinstance(evidence_refs, (list, tuple)) or not evidence_refs:
        raise LessonRechazada(CAMPO_INVALIDO, "evidence_refs: se requiere al menos una referencia")
    refs = []
    for ref in evidence_refs:
        if not isinstance(ref, dict) or set(ref) != set(_CLAVES_REF) or any(
                not isinstance(ref[k], str) or _RE_ID_TEXTO.fullmatch(ref[k]) is None for k in _CLAVES_REF):
            raise LessonRechazada(CAMPO_INVALIDO, "evidence_refs: cada referencia exige probe_id, decision_hash y suite_id")
        refs.append({k: ref[k] for k in _CLAVES_REF})
    refs.sort(key=lambda r: (r["probe_id"], r["decision_hash"], r["suite_id"]))
    vistos = {_canon(r) for r in refs}
    return [json.loads(c) for c in sorted(vistos)]


# --- Evidencia (R2) ----------------------------------------------------------------

def _estado_por_evidencia(repo_root, refs: list, evals_root=None) -> str:
    """`evidence-backed` o `hypothesis`. Lanza `LessonRechazada(EVIDENCIA_NO_VERIFICABLE)` si alguna
    referencia no se puede recomputar o no coincide."""
    respaldada = True
    veredictos = set()
    for ref in refs:
        try:
            d = _decision.decidir(repo_root, ref["probe_id"], evals_root=evals_root)
            repeats = ProbePolicy.desde_dict(d["policy"]).repeats
        except Exception as exc:  # noqa: BLE001 - fail-closed
            raise LessonRechazada(EVIDENCIA_NO_VERIFICABLE,
                                  f"no se pudo recomputar {ref['probe_id']} ({type(exc).__name__})") from None
        suite = d.get("suite")
        suite_id = suite.get("suite_id") if isinstance(suite, dict) else None
        if d["decision_hash"] != ref["decision_hash"] or suite_id != ref["suite_id"]:
            raise LessonRechazada(EVIDENCIA_NO_VERIFICABLE,
                                  f"la decisión recomputada de {ref['probe_id']} no coincide con la referencia")
        if d["verdict"] not in _VEREDICTOS_RESPALDAN or repeats < 2:
            respaldada = False
        veredictos.add(d["verdict"])
    if len(veredictos) > 1:  # L4: referencias de veredicto opuesto (o mixto) no respaldan nada
        respaldada = False
    return ESTADO_EVIDENCE_BACKED if respaldada else ESTADO_HYPOTHESIS


# --- Carga -------------------------------------------------------------------------

def cargar_lesson(repo_root, lesson_id: str) -> dict:
    """Carga y valida una lesson (forma, `lesson_id` y `lesson_hash` recomputados)."""
    ruta = _ruta_lesson(repo_root, lesson_id)
    if es_enlace(ruta):
        raise LessonRechazada(LESSON_CORRUPTA, "la lesson es un enlace: no permitido")
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise LessonRechazada(LESSON_CORRUPTA, f"lesson inexistente ({lesson_id})") from None
    except (OSError, ValueError) as exc:
        raise LessonRechazada(LESSON_CORRUPTA, f"lesson ilegible ({type(exc).__name__})") from None
    if not isinstance(datos, dict) or set(datos) not in (set(_CLAVES_BASE), set(_CLAVES_DEPRECADA)):
        raise LessonRechazada(LESSON_CORRUPTA, "claves inesperadas")
    v = datos["contract_version"]
    if isinstance(v, bool) or v != LESSON_CONTRACT_VERSION:
        raise LessonRechazada(LESSON_CORRUPTA, "contract_version no soportada")
    if datos["lesson_id"] != lesson_id or datos["status"] not in ESTADOS:
        raise LessonRechazada(LESSON_CORRUPTA, "lesson_id o status inválido")
    es_deprecada = datos["status"] == ESTADO_DEPRECATED
    if es_deprecada != ("deprecated_reason" in datos):
        raise LessonRechazada(LESSON_CORRUPTA, "status y claves de deprecación incoherentes")
    for campo in ("created_utc", "deprecated_utc"):
        if campo in datos:
            try:
                datetime.strptime(datos[campo], "%Y-%m-%dT%H:%M:%SZ")
            except (TypeError, ValueError):
                raise LessonRechazada(LESSON_CORRUPTA, f"{campo} inválido") from None
    if es_deprecada and (not isinstance(datos["deprecated_reason"], str) or not datos["deprecated_reason"].strip()):
        raise LessonRechazada(LESSON_CORRUPTA, "deprecated_reason inválido")
    if not isinstance(datos["lesson_hash"], str) or _hash_lesson(datos) != datos["lesson_hash"]:
        raise LessonRechazada(LESSON_CORRUPTA, "lesson_hash no coincide (manipulada)")
    try:
        contextos = _validar_contextos(datos["applicability"]["contexts"])
        refs = _validar_refs(datos["evidence_refs"])
        _texto(datos["pattern"], "pattern", MAX_PATTERN)
        _texto(datos["recommendation"], "recommendation", MAX_RECOMMENDATION)
    except (LessonRechazada, KeyError, TypeError):
        raise LessonRechazada(LESSON_CORRUPTA, "campos inválidos") from None
    if _id_de_contenido(datos["pattern"], datos["recommendation"], contextos, refs) != lesson_id:
        raise LessonRechazada(LESSON_CORRUPTA, "lesson_id no corresponde al contenido")
    return datos


def _ids_en_disco(repo_root) -> list:
    directorio = raiz_improvement(repo_root) / DIR_LESSONS
    if not directorio.is_dir():
        return []
    return sorted(p.stem for p in directorio.iterdir()
                  if p.is_file() and p.suffix == ".json" and _RE_LESSON_ID.fullmatch(p.stem))


def listar_lessons(repo_root) -> list:
    """Todas las lessons íntegras, ordenadas por `lesson_id`. Una corrupta lanza `LESSON_CORRUPTA`."""
    return [cargar_lesson(repo_root, i) for i in _ids_en_disco(repo_root)]


# --- API ---------------------------------------------------------------------------

def crear_lesson(repo_root, change_id: str, pattern: str, recommendation: str, contexts,
                 evidence_refs, evals_root=None, ahora: Optional[datetime] = None) -> dict:
    """Crea (o devuelve, si ya existe) una lesson. Exige un Change `en_implementacion` (R4), valida
    campos y privacidad (R3), recomputa la evidencia y calcula el estado (R2). Idempotente por id."""
    raiz = Path(repo_root)
    pattern = _texto(pattern, "pattern", MAX_PATTERN)
    recommendation = _texto(recommendation, "recommendation", MAX_RECOMMENDATION)
    contextos = _validar_contextos(contexts)
    refs = _validar_refs(evidence_refs)
    _escanear_lesson(_terminos_glossary(raiz), pattern, recommendation, contextos, refs)
    if verificar_change_abierto(raiz, change_id):
        raise LessonRechazada(SIN_CHANGE, "se requiere un Change existente en en_implementacion")
    estado = _estado_por_evidencia(raiz, refs, evals_root)
    lesson_id = _id_de_contenido(pattern, recommendation, contextos, refs)
    ruta = _ruta_lesson(raiz, lesson_id)
    with bloqueo(raiz):
        if ruta.exists():
            return cargar_lesson(raiz, lesson_id)
        lesson = {
            "contract_version": LESSON_CONTRACT_VERSION,
            "lesson_id": lesson_id,
            "pattern": pattern,
            "recommendation": recommendation,
            "applicability": {"contexts": contextos},
            "evidence_refs": refs,
            "status": estado,
            "created_utc": _iso(ahora or datetime.now(timezone.utc)),
        }
        lesson["lesson_hash"] = _hash_lesson(lesson)
        escribir_atomico(ruta, _json_bytes(lesson))
        return lesson


def deprecar(repo_root, change_id: str, lesson_id: str, motivo: str,
             ahora: Optional[datetime] = None) -> dict:
    """Marca una lesson como `deprecated` (único camino). Gobernado por un Change abierto."""
    raiz = Path(repo_root)
    motivo = _texto(motivo, "motivo", MAX_RECOMMENDATION)
    _escanear_texto(motivo, _terminos_glossary(raiz), "motivo")
    if verificar_change_abierto(raiz, change_id):
        raise LessonRechazada(SIN_CHANGE, "se requiere un Change existente en en_implementacion")
    ruta = _ruta_lesson(raiz, lesson_id)
    with bloqueo(raiz):
        lesson = cargar_lesson(raiz, lesson_id)
        if lesson["status"] == ESTADO_DEPRECATED:
            return lesson
        lesson = dict(lesson, status=ESTADO_DEPRECATED, deprecated_reason=motivo,
                      deprecated_utc=_iso(ahora or datetime.now(timezone.utc)))
        lesson["lesson_hash"] = _hash_lesson(lesson)
        escribir_atomico(ruta, _json_bytes(lesson))
        return lesson


def lessons_aplicables(repo_root, contexts, evals_root=None) -> dict:
    """`{"aplicables": [lesson...], "descartadas": [{"lesson_id", "motivo"}...]}` (R5). Solo lectura."""
    raiz = Path(repo_root)
    pedidos = set(_validar_contextos(contexts))
    aplicables, descartadas = [], []
    try:
        terminos = _terminos_glossary(raiz)
    except LessonRechazada:
        terminos = None
    for lesson_id in _ids_en_disco(raiz):
        try:
            lesson = cargar_lesson(raiz, lesson_id)
        except LessonRechazada:
            descartadas.append({"lesson_id": lesson_id, "motivo": "lesson_corrupta"})
            continue
        if lesson["status"] == ESTADO_DEPRECATED:
            descartadas.append({"lesson_id": lesson_id, "motivo": "deprecated"})
            continue
        if not pedidos & set(lesson["applicability"]["contexts"]):
            descartadas.append({"lesson_id": lesson_id, "motivo": "sin_contexto_en_comun"})
            continue
        try:
            if terminos is None:
                raise LessonRechazada(CONOCIMIENTO_DEL_PROYECTO, "GLOSSARY ilegible")
            _escanear_lesson(terminos, lesson["pattern"], lesson["recommendation"],
                             lesson["applicability"]["contexts"], lesson["evidence_refs"])
            if lesson.get("deprecated_reason"):
                _escanear_texto(lesson["deprecated_reason"], terminos, "deprecated_reason")
        except LessonRechazada:
            descartadas.append({"lesson_id": lesson_id, "motivo": "privacidad_no_superada"})
            continue
        try:
            recomputado = _estado_por_evidencia(raiz, lesson["evidence_refs"], evals_root)
        except LessonRechazada:
            descartadas.append({"lesson_id": lesson_id, "motivo": "evidencia_no_verificable"})
            continue
        if lesson["status"] == ESTADO_EVIDENCE_BACKED and recomputado != ESTADO_EVIDENCE_BACKED:
            descartadas.append({"lesson_id": lesson_id, "motivo": "evidencia_no_respalda_el_estado"})
            continue
        aplicables.append(lesson)
    return {"aplicables": aplicables, "descartadas": descartadas}
