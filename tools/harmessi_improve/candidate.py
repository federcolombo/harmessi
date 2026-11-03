"""Modelo de candidate aislada (v0.14 Change 1, R1-R9).

Por qué existe: para mejorar el harness hace falta poder PROPONER un reemplazo de una
superficie Optimizable sin tocar nunca el archivo activo. Una candidate vive en
`.harmessi/improvement/candidates/<id>/` (`candidate.json` + `content.md`); el archivo
activo, el managed baseline y el resto del árbol quedan byte a byte iguales.

Principios:
- Fail-closed y en orden fijo: tipo/ruta -> superficie -> base legible -> contenido y
  privacidad -> idempotencia -> budget -> escritura. Nada se escribe si algo falla antes.
- No hay clasificación de superficies propia: se reutiliza `superficie_de_ruta`.
- Privacidad: si `redactar_texto` modificaría el texto, se rechaza (no se redacta en
  silencio). Conocimiento del proyecto (términos del GLOSSARY) tampoco entra.
- El id es reproducible (hash de base + contenido), así que crear dos veces la misma
  candidate es idempotente y no consume budget dos veces.
- Sin chain-of-thought ni secretos: la provenance es un dict cerrado.
Solo stdlib; sin red ni subprocess.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tools.dsguard import glossary as _glossary
from tools.dsguard.skill_contract import (
    SUPERFICIE_OPTIMIZABLE,
    SUPERFICIE_PROTEGIDA,
    SUPERFICIE_PROYECTO,
    superficie_de_ruta,
)
from tools.harmessi_bench.redact import redactar_texto
from tools.harmessi_bench.runmanifest import HARNESS_VERSION, hash_contenido
from tools.harmessi_improve import budget as _budget
from tools.harmessi_improve.budget import (
    BUDGET_VERSION,
    ImprovementBudget,
    bloqueo,
    es_enlace,
    escribir_atomico,
    raiz_improvement,
    verificar_dentro_de_improvement,
)

CANDIDATE_CONTRACT_VERSION = 1

ESTADO_PROPOSED = "proposed"
ESTADO_EVALUATED = "evaluated"
ESTADO_PROMOTABLE = "promotable"
ESTADO_REJECTED = "rejected"
ESTADO_INCONCLUSIVE = "inconclusive"
ESTADOS = (ESTADO_PROPOSED, ESTADO_EVALUATED, ESTADO_PROMOTABLE, ESTADO_REJECTED, ESTADO_INCONCLUSIVE)

TRANSICIONES = {
    ESTADO_PROPOSED: (ESTADO_EVALUATED,),
    ESTADO_EVALUATED: (ESTADO_PROMOTABLE, ESTADO_REJECTED, ESTADO_INCONCLUSIVE),
    ESTADO_INCONCLUSIVE: (ESTADO_EVALUATED,),
    ESTADO_PROMOTABLE: (),
    ESTADO_REJECTED: (),
}

# Códigos de rechazo
RUTA_INVALIDA = "RUTA_INVALIDA"
SUPERFICIE_PROTEGIDA_COD = "SUPERFICIE_PROTEGIDA"
SUPERFICIE_PROYECTO_COD = "SUPERFICIE_PROYECTO"
BASE_ILEGIBLE = "BASE_ILEGIBLE"
CONTENIDO_INVALIDO = "CONTENIDO_INVALIDO"
CONTENIDO_SENSIBLE = "CONTENIDO_SENSIBLE"
CONOCIMIENTO_DEL_PROYECTO = "CONOCIMIENTO_DEL_PROYECTO"
SIN_CAMBIO = "SIN_CAMBIO"
PROVENANCE_INVALIDA = "PROVENANCE_INVALIDA"
TRANSICION_INVALIDA = "TRANSICION_INVALIDA"
EVIDENCIA_REQUERIDA = "EVIDENCIA_REQUERIDA"

MAX_CONTENIDO_BYTES = 200 * 1024
MAX_HIPOTESIS = 1000
MAX_ETIQUETA = 80
PROPOSER_KINDS = ("llm", "human", "script")

DIR_CANDIDATES = "candidates"
NOMBRE_JSON = "candidate.json"
NOMBRE_CONTENIDO = "content.md"
_RE_ID = re.compile(r"cand-[0-9a-f]{12}")
_RE_ID_TEXTO = re.compile(r"[A-Za-z0-9._-]{1,80}")   # suite_ids y probe_id
_RE_HASH_DECISION = re.compile(r"[A-Za-z0-9]{1,128}")  # decision_hash


def _id_valido(valor) -> bool:
    return isinstance(valor, str) and _RE_ID.fullmatch(valor) is not None


def _texto_acotado_valido(valor, patron) -> bool:
    """str que cumple `patron` completo y que `redactar_texto` no modificaría."""
    return (isinstance(valor, str) and patron.fullmatch(valor) is not None
            and redactar_texto(valor) == valor)


def _evidencia_valida(ev) -> bool:
    return (isinstance(ev, dict) and set(ev) == {"probe_id", "decision_hash"}
            and _texto_acotado_valido(ev["probe_id"], _RE_ID_TEXTO)
            and _texto_acotado_valido(ev["decision_hash"], _RE_HASH_DECISION))

_CLAVES_JSON = (
    "contract_version", "candidate_id", "base_surface", "base_hash", "content_hash",
    "hypothesis", "provenance", "created_utc", "status", "status_history", "suite_ids",
    "budget_version",
)


class CandidateRechazada(Exception):
    """La candidate no cumple una regla; `codigo` identifica cuál."""

    def __init__(self, codigo: str, mensaje: str = "") -> None:
        self.codigo = codigo
        self.mensaje = mensaje
        super().__init__(f"{codigo}: {mensaje}" if mensaje else codigo)


class CandidateCorrupta(Exception):
    """El contenido persistido de una candidate no es íntegro o no existe."""


@dataclass
class Candidate:
    candidate_id: str
    base_surface: str
    base_hash: str
    content_hash: str
    hypothesis: str
    provenance: dict
    created_utc: str
    status: str = ESTADO_PROPOSED
    status_history: list = field(default_factory=list)
    suite_ids: list = field(default_factory=list)
    budget_version: int = BUDGET_VERSION
    contract_version: int = CANDIDATE_CONTRACT_VERSION

    def a_dict(self) -> dict:
        return {
            "contract_version": self.contract_version,
            "candidate_id": self.candidate_id,
            "base_surface": self.base_surface,
            "base_hash": self.base_hash,
            "content_hash": self.content_hash,
            "hypothesis": self.hypothesis,
            "provenance": dict(self.provenance),
            "created_utc": self.created_utc,
            "status": self.status,
            "status_history": [dict(h) for h in self.status_history],
            "suite_ids": list(self.suite_ids),
            "budget_version": self.budget_version,
        }

    @classmethod
    def desde_dict(cls, datos: dict) -> "Candidate":
        """Valida forma y tipos; lanza `CandidateCorrupta` si no cuadra."""
        if not isinstance(datos, dict) or set(datos) != set(_CLAVES_JSON):
            raise CandidateCorrupta("candidate.json: claves inesperadas")
        if datos["contract_version"] != CANDIDATE_CONTRACT_VERSION or isinstance(datos["contract_version"], bool):
            raise CandidateCorrupta("candidate.json: contract_version no soportada")
        for clave in ("candidate_id", "base_surface", "base_hash", "content_hash",
                      "hypothesis", "created_utc", "status"):
            if not isinstance(datos[clave], str) or not datos[clave]:
                raise CandidateCorrupta(f"candidate.json: {clave} inválido")
        if not _id_valido(datos["candidate_id"]):
            raise CandidateCorrupta("candidate.json: candidate_id inválido")
        base = datos["base_surface"]
        if _normalizar_ruta(base) != base or superficie_de_ruta(base) != SUPERFICIE_OPTIMIZABLE:
            raise CandidateCorrupta("candidate.json: base_surface no canónica u no Optimizable")
        if datos["status"] not in ESTADOS:
            raise CandidateCorrupta("candidate.json: status inválido")
        prov = datos["provenance"]
        if (not isinstance(prov, dict)
                or set(prov) != {"proposer_kind", "proposer_label", "harness_version"}
                or prov["proposer_kind"] not in PROPOSER_KINDS
                or not isinstance(prov["proposer_label"], str)
                or not isinstance(prov["harness_version"], str)):
            raise CandidateCorrupta("candidate.json: provenance inválida")
        hist = datos["status_history"]
        if not isinstance(hist, list) or not hist or not all(
                isinstance(h, dict) and h.get("status") in ESTADOS
                and isinstance(h.get("utc"), str) for h in hist):
            raise CandidateCorrupta("candidate.json: status_history inválido")
        if hist[-1]["status"] != datos["status"]:
            raise CandidateCorrupta("candidate.json: status_history no coincide con status")
        if hist[0]["status"] != ESTADO_PROPOSED or "evidence" in hist[0]:
            raise CandidateCorrupta("candidate.json: history[0] debe ser proposed")
        for previo, actual in zip(hist, hist[1:]):
            if actual["status"] not in TRANSICIONES[previo["status"]]:
                raise CandidateCorrupta("candidate.json: transición inválida en status_history")
            if not _evidencia_valida(actual.get("evidence")):
                raise CandidateCorrupta("candidate.json: evidencia ausente o inválida")
        suites = datos["suite_ids"]
        if not isinstance(suites, list) or not all(_texto_acotado_valido(s, _RE_ID_TEXTO) for s in suites):
            raise CandidateCorrupta("candidate.json: suite_ids inválido")
        if isinstance(datos["budget_version"], bool) or not isinstance(datos["budget_version"], int):
            raise CandidateCorrupta("candidate.json: budget_version inválido")
        return cls(
            candidate_id=datos["candidate_id"], base_surface=datos["base_surface"],
            base_hash=datos["base_hash"], content_hash=datos["content_hash"],
            hypothesis=datos["hypothesis"], provenance=dict(prov),
            created_utc=datos["created_utc"], status=datos["status"],
            status_history=[dict(h) for h in hist], suite_ids=list(suites),
            budget_version=datos["budget_version"], contract_version=datos["contract_version"],
        )


# --- Utilidades --------------------------------------------------------------------

def calcular_candidate_id(base_surface: str, base_hash: str, content_hash: str) -> str:
    base = f"{base_surface}\n{base_hash}\n{content_hash}"
    return "cand-" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:12]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json_bytes(datos: dict) -> bytes:
    return (json.dumps(datos, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _dir_candidate(repo_root, candidate_id: str) -> Path:
    if not _id_valido(candidate_id):
        raise CandidateCorrupta(f"candidate_id inválido: {candidate_id!r}")
    ruta = raiz_improvement(repo_root) / DIR_CANDIDATES / candidate_id
    try:
        return verificar_dentro_de_improvement(repo_root, ruta)
    except _budget.PresupuestoInvalido:
        raise CandidateCorrupta("ruta de candidate fuera de .harmessi/improvement") from None


def _normalizar_ruta(base_surface: str) -> str:
    partes = [p for p in base_surface.strip().replace("\\", "/").casefold().split("/") if p not in ("", ".")]
    return "/".join(partes)


def _validar_ruta(base_surface) -> str:
    """Condiciones triviales de ruta (RUTA_INVALIDA) y normalización."""
    if not isinstance(base_surface, str) or not base_surface.strip():
        raise CandidateRechazada(RUTA_INVALIDA, "base_surface debe ser un str no vacío")
    texto = base_surface.strip()
    if "\x00" in texto:
        raise CandidateRechazada(RUTA_INVALIDA, "base_surface con NUL")
    if texto[0] in "/\\" or ":" in texto:
        raise CandidateRechazada(RUTA_INVALIDA, "base_surface no puede ser absoluta")
    if ".." in texto.replace("\\", "/").split("/"):
        raise CandidateRechazada(RUTA_INVALIDA, "base_surface no puede contener '..'")
    normal = _normalizar_ruta(texto)
    if not normal:
        raise CandidateRechazada(RUTA_INVALIDA, "base_surface vacía tras normalizar")
    return normal


def _leer_base(repo_root, ruta_normal: str) -> bytes:
    raiz_lex = Path(repo_root)
    actual = raiz_lex
    for parte in ruta_normal.split("/"):
        actual = actual / parte
        if es_enlace(actual):
            raise CandidateRechazada(BASE_ILEGIBLE, "un componente de la ruta es symlink/junction")
    try:
        raiz = raiz_lex.resolve()
        destino = (raiz_lex / ruta_normal).resolve()
        rel = destino.relative_to(raiz).as_posix()
        if superficie_de_ruta(rel) != SUPERFICIE_OPTIMIZABLE:
            raise CandidateRechazada(BASE_ILEGIBLE, "la ruta real ya no es Optimizable")
        if not destino.is_file():
            raise CandidateRechazada(BASE_ILEGIBLE, "la base no existe o no es archivo")
        return destino.read_bytes()
    except ValueError:
        raise CandidateRechazada(BASE_ILEGIBLE, "la base resuelve fuera del repo o ruta inválida") from None
    except OSError as exc:
        raise CandidateRechazada(BASE_ILEGIBLE, f"base ilegible: {type(exc).__name__}") from None


def _validar_provenance(provenance) -> dict:
    if (not isinstance(provenance, dict)
            or set(provenance) != {"proposer_kind", "proposer_label"}):
        raise CandidateRechazada(PROVENANCE_INVALIDA, "provenance debe tener proposer_kind y proposer_label")
    kind, label = provenance["proposer_kind"], provenance["proposer_label"]
    if kind not in PROPOSER_KINDS or isinstance(kind, bool):
        raise CandidateRechazada(PROVENANCE_INVALIDA, "proposer_kind inválido")
    if not isinstance(label, str) or not label.strip() or len(label) > MAX_ETIQUETA:
        raise CandidateRechazada(PROVENANCE_INVALIDA, "proposer_label inválido")
    if redactar_texto(label) != label:
        raise CandidateRechazada(CONTENIDO_SENSIBLE, "proposer_label contiene datos sensibles")
    return {"proposer_kind": kind, "proposer_label": label, "harness_version": HARNESS_VERSION}


def normalizar_para_glosario(texto: str) -> str:
    """Normalización común (candidate y lessons) de términos y textos: NFC, casefold, `-` y `_` como
    espacio y espacios/saltos colapsados (`glossary.clave_termino` + separadores)."""
    plano = _glossary.clave_termino(texto)
    plano = re.sub(r"[-_]", " ", plano)
    return re.sub(r"\s+", " ", plano).strip()


def terminos_glossary_normalizados(repo_root) -> list:
    """Términos del GLOSSARY normalizados (lista vacía si no hay GLOSSARY). Lanza si es ilegible."""
    ruta = Path(repo_root) / _glossary.RUTA_GLOSSARY
    if not ruta.exists():
        return []
    entradas, _hallazgos = _glossary.parsear_glossary(ruta.read_text(encoding="utf-8"))
    terminos = [normalizar_para_glosario(e.termino) for e in entradas
                if isinstance(e.termino, str) and e.termino.strip()]
    return [t for t in terminos if t]


def contiene_termino_normalizado(texto: str, terminos: list) -> Optional[str]:
    """Primer término (ya normalizado) presente en `texto` por límites de palabra, o None."""
    plano = normalizar_para_glosario(texto)
    for t in terminos:
        if re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", plano):
            return t
    return None


def _terminos_glossary(repo_root) -> list:
    try:
        return terminos_glossary_normalizados(repo_root)
    except Exception as exc:  # noqa: BLE001 - fail-closed: glossary ilegible => se rechaza
        raise CandidateRechazada(CONOCIMIENTO_DEL_PROYECTO, f"GLOSSARY ilegible: {exc}") from None


def _contiene_termino(texto: str, terminos: list) -> Optional[str]:
    return contiene_termino_normalizado(texto, terminos)


# --- API ---------------------------------------------------------------------------

def crear_candidate(repo_root, base_surface, content, hypothesis, provenance,
                    suite_ids=(), budget: Optional[ImprovementBudget] = None,
                    ahora: Optional[datetime] = None) -> Candidate:
    """Crea (o devuelve, si ya existe y es válida) una candidate. Solo escribe bajo
    `.harmessi/improvement/candidates/<id>/`. Ver orden fail-closed en el docstring del módulo."""
    # 1. tipo/ruta
    ruta_normal = _validar_ruta(base_surface)
    # 2. superficie
    superficie = superficie_de_ruta(ruta_normal)
    if superficie == SUPERFICIE_PROTEGIDA:
        raise CandidateRechazada(SUPERFICIE_PROTEGIDA_COD, f"superficie protegida: {ruta_normal}")
    if superficie == SUPERFICIE_PROYECTO:
        raise CandidateRechazada(SUPERFICIE_PROYECTO_COD, f"superficie del proyecto: {ruta_normal}")
    if superficie != SUPERFICIE_OPTIMIZABLE:
        raise CandidateRechazada(SUPERFICIE_PROTEGIDA_COD, "superficie desconocida (fail-safe)")
    # 3. base legible
    base_bytes = _leer_base(repo_root, ruta_normal)
    base_hash = hash_contenido(base_bytes)
    # 4. contenido, hipótesis, provenance y privacidad
    if not isinstance(content, str) or not content.strip() or "\x00" in content:
        raise CandidateRechazada(CONTENIDO_INVALIDO, "contenido vacío, no-str o con NUL")
    try:
        content_bytes = content.encode("utf-8")
    except UnicodeEncodeError:
        raise CandidateRechazada(CONTENIDO_INVALIDO, "contenido no codificable en UTF-8") from None
    if len(content_bytes) > MAX_CONTENIDO_BYTES:
        raise CandidateRechazada(CONTENIDO_INVALIDO, "contenido supera 200 KB")
    if not isinstance(hypothesis, str) or not hypothesis.strip() or len(hypothesis) > MAX_HIPOTESIS:
        raise CandidateRechazada(CONTENIDO_INVALIDO, f"hipótesis vacía, no-str o > {MAX_HIPOTESIS}")
    if isinstance(suite_ids, (str, bytes)) or not all(
            _texto_acotado_valido(s, _RE_ID_TEXTO) for s in suite_ids):
        raise CandidateRechazada(CONTENIDO_INVALIDO, "suite_ids inválido")
    prov = _validar_provenance(provenance)
    if redactar_texto(content) != content or redactar_texto(hypothesis) != hypothesis:
        raise CandidateRechazada(CONTENIDO_SENSIBLE, "contenido o hipótesis con datos sensibles")
    terminos = _terminos_glossary(repo_root)
    if _contiene_termino(content, terminos) or _contiene_termino(hypothesis, terminos):
        raise CandidateRechazada(CONOCIMIENTO_DEL_PROYECTO, "contiene un término del GLOSSARY del proyecto")
    content_hash = hash_contenido(content_bytes)
    if content_hash == base_hash:
        raise CandidateRechazada(SIN_CAMBIO, "el contenido es idéntico a la base")
    # 5. idempotencia
    candidate_id = calcular_candidate_id(ruta_normal, base_hash, content_hash)
    directorio = _dir_candidate(repo_root, candidate_id)
    ahora = ahora or datetime.now(timezone.utc)
    with bloqueo(repo_root):  # serializa idempotencia + budget + escritura
        if (directorio / NOMBRE_JSON).exists():
            return cargar_candidate(repo_root, candidate_id)
        # 6. budget (verifica antes de incrementar)
        _budget.consumir_sin_lock(repo_root, "candidates", ahora=ahora, presupuesto=budget)
        # 7. escritura atómica con rollback del budget y limpieza si falla
        try:
            return _escribir_candidate(repo_root, directorio, candidate_id, ruta_normal, base_hash,
                                       content_hash, hypothesis, prov, ahora, suite_ids, content_bytes)
        except BaseException:
            for nombre in (NOMBRE_JSON, NOMBRE_CONTENIDO):
                try:
                    (directorio / nombre).unlink()
                except OSError:
                    pass
            try:
                directorio.rmdir()
            except OSError:
                pass
            _budget.devolver_candidate(repo_root)
            raise


def _escribir_candidate(repo_root, directorio, candidate_id, ruta_normal, base_hash, content_hash,
                        hypothesis, prov, ahora, suite_ids, content_bytes) -> Candidate:
    """content.md primero, candidate.json al final (sin json => directorio huérfano ignorable)."""
    candidato = Candidate(
        candidate_id=candidate_id, base_surface=ruta_normal, base_hash=base_hash,
        content_hash=content_hash, hypothesis=hypothesis, provenance=prov,
        created_utc=_iso(ahora), status=ESTADO_PROPOSED,
        status_history=[{"status": ESTADO_PROPOSED, "utc": _iso(ahora)}],
        suite_ids=list(suite_ids),
    )
    escribir_atomico(verificar_dentro_de_improvement(repo_root, directorio / NOMBRE_CONTENIDO), content_bytes)
    escribir_atomico(verificar_dentro_de_improvement(repo_root, directorio / NOMBRE_JSON),
                     _json_bytes(candidato.a_dict()))
    return candidato


def cargar_candidate(repo_root, candidate_id: str) -> Candidate:
    """Carga y verifica contrato, id e integridad de `content.md`. `CandidateCorrupta` si falla."""
    directorio = _dir_candidate(repo_root, candidate_id)
    try:
        datos = json.loads((directorio / NOMBRE_JSON).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CandidateCorrupta(f"candidate inexistente: {candidate_id}") from None
    except (OSError, ValueError) as exc:
        raise CandidateCorrupta(f"candidate.json ilegible: {exc}") from None
    candidato = Candidate.desde_dict(datos)
    esperado = calcular_candidate_id(candidato.base_surface, candidato.base_hash, candidato.content_hash)
    if candidato.candidate_id != candidate_id or esperado != candidate_id:
        raise CandidateCorrupta("candidate_id no coincide con su contenido")
    try:
        contenido = (directorio / NOMBRE_CONTENIDO).read_bytes()
    except OSError as exc:
        raise CandidateCorrupta(f"content.md ilegible: {exc}") from None
    if hash_contenido(contenido) != candidato.content_hash:
        raise CandidateCorrupta("content.md fue manipulado (content_hash no coincide)")
    return candidato


def listar_candidates(repo_root) -> list:
    """Candidates existentes ordenadas por id. Una corrupta propaga `CandidateCorrupta`."""
    raiz = raiz_improvement(repo_root) / DIR_CANDIDATES
    if not raiz.is_dir():
        return []
    # Directorios sin candidate.json (huérfanos de una escritura fallida) se ignoran.
    ids = sorted(p.name for p in raiz.iterdir()
                 if p.is_dir() and _id_valido(p.name) and (p / NOMBRE_JSON).exists())
    return [cargar_candidate(repo_root, i) for i in ids]


def leer_contenido(repo_root, candidate_id: str) -> str:
    """Contenido propuesto (verificado por hash)."""
    cargar_candidate(repo_root, candidate_id)
    return (_dir_candidate(repo_root, candidate_id) / NOMBRE_CONTENIDO).read_bytes().decode("utf-8")


def base_vigente(repo_root, candidate: Candidate) -> bool:
    """True si el archivo activo sigue teniendo `base_hash`. Ilegible => False."""
    try:
        actual = _leer_base(repo_root, candidate.base_surface)
    except CandidateRechazada:
        return False
    return hash_contenido(actual) == candidate.base_hash


def transicionar(repo_root, candidate_id: str, nuevo_estado: str, evidencia: Optional[dict] = None,
                 ahora: Optional[datetime] = None) -> Candidate:
    """Cambia el estado según `TRANSICIONES`. Todo estado distinto de `proposed` exige
    `evidencia = {"probe_id": str, "decision_hash": str}` (no vacíos)."""
    with bloqueo(repo_root):
        return transicionar_sin_lock(repo_root, candidate_id, nuevo_estado, evidencia, ahora)


def transicionar_sin_lock(repo_root, candidate_id: str, nuevo_estado: str, evidencia: Optional[dict] = None,
                          ahora: Optional[datetime] = None) -> Candidate:
    """Igual que `transicionar` pero SIN tomar el lock: el llamador ya lo tiene (`budget.bloqueo`)."""
    if not isinstance(nuevo_estado, str):
        raise CandidateRechazada(TRANSICION_INVALIDA, "nuevo_estado debe ser str")
    candidato = cargar_candidate(repo_root, candidate_id)
    if nuevo_estado not in TRANSICIONES.get(candidato.status, ()):
        raise CandidateRechazada(
            TRANSICION_INVALIDA, f"{candidato.status} -> {nuevo_estado!r} no permitida")
    if not _evidencia_valida(evidencia):
        raise CandidateRechazada(
            EVIDENCIA_REQUERIDA,
            "se requiere evidencia {probe_id: [A-Za-z0-9._-]{1,80}, decision_hash: alnum <=128}")
    ahora = ahora or datetime.now(timezone.utc)
    candidato.status = nuevo_estado
    candidato.status_history.append({
        "status": nuevo_estado,
        "utc": _iso(ahora),
        "evidence": {"probe_id": evidencia["probe_id"], "decision_hash": evidencia["decision_hash"]},
    })
    directorio = _dir_candidate(repo_root, candidate_id)
    escribir_atomico(verificar_dentro_de_improvement(repo_root, directorio / NOMBRE_JSON),
                     _json_bytes(candidato.a_dict()))
    return candidato
