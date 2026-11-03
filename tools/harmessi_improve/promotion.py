"""Promoción gobernada de una candidate `promotable` (v0.14 Change 4, R1-R7).

Por qué existe: una candidate con evidencia a favor NO se aplica sola. Este módulo arma una
propuesta revisable (`proposal.json` + `change.diff`), define un gate de solo lectura que exige un
Change SDD normal con aprobaciones humanas T1 (`approval_channel == "console_confirmed"`) y, solo si
el gate pasa, reemplaza UNA superficie Optimizable de forma atómica.

Principios:
- `proponer_promocion` recomputa la evidencia (`decision.verificar_promotable`) y la base vigente;
  escribe solo `.harmessi/improvement/proposals/<candidate_id>/`.
- `evaluar_gate` es una función pura de lectura que devuelve motivos (códigos estables) y nunca
  lanza: cualquier excepción es un motivo (fail-closed).
- `aplicar_promocion` es la única que escribe fuera de `.harmessi/`: ejecuta el gate bajo
  `budget.bloqueo` y escribe exclusivamente la superficie de la candidate (sin seguir enlaces) más
  `applied.json`. No toca `main`, el managed baseline ni ninguna otra ruta.
- Una promoción no sustituye tests, reviewer ni verificación de release (R6/R7).
Solo stdlib y paquetes permitidos; sin red ni subprocess.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import functools
import sys
from types import SimpleNamespace

from tools.dsguard.skill_contract import SUPERFICIE_OPTIMIZABLE, superficie_de_ruta
from tools.harmessi_bench.redact import redactar_texto
from tools.harmessi_bench.runmanifest import hash_contenido
from tools.harmessi_improve.budget import (
    PresupuestoInvalido,
    bloqueo,
    es_enlace,
    escribir_atomico,
    raiz_improvement,
    verificar_dentro_de_improvement,
)
from tools.harmessi_improve.candidate import (
    CandidateCorrupta,
    base_vigente,
    cargar_candidate,
    leer_contenido,
)
from tools.harmessi_improve.decision import PromocionNoRespaldada, verificar_promotable

PROPOSAL_CONTRACT_VERSION = 1
DIR_PROPOSALS = "proposals"
NOMBRE_PROPUESTA = "proposal.json"
NOMBRE_DIFF = "change.diff"
NOMBRE_APLICADA = "applied.json"
CANAL_REQUERIDO = "console_confirmed"
VERSION_CANAL_REQUERIDA = "console/v1"  # T1 canónico: canal + versión (ver tools/cards/approvals.py)
ESTADO_PENDING = "pending"
ESTADO_APPLIED = "applied"
ESTADO_REQUERIDO = "en_implementacion"
ARTEFACTOS_APROBADOS = ("proposal.md", "spec.md", "design.md")
PREFIJO_DISTRIBUIDO = ".claude/skills/lead-data-scientist/"

# Códigos de motivo de bloqueo del gate
PROPUESTA_INVALIDA = "PROPUESTA_INVALIDA"
NO_PROMOTABLE = "NO_PROMOTABLE"
BASE_CAMBIADA = "BASE_CAMBIADA"
CHANGE_INEXISTENTE = "CHANGE_INEXISTENTE"
CHANGE_NO_EN_IMPLEMENTACION = "CHANGE_NO_EN_IMPLEMENTACION"
CONTROL_ILEGIBLE = "CONTROL_ILEGIBLE"
FUERA_DE_ALCANCE = "FUERA_DE_ALCANCE"
PROPUESTA_NO_CITADA = "PROPUESTA_NO_CITADA"
SUPERFICIE_NO_OPTIMIZABLE = "SUPERFICIE_NO_OPTIMIZABLE"
DIFF_SENSIBLE = "DIFF_SENSIBLE"

_RE_CANDIDATE_ID = re.compile(r"cand-[0-9a-f]{12}")
_RE_CHANGE_ID = re.compile(r"[0-9]{8}-[a-z0-9][a-z0-9-]*")
_CLAVES_PROPUESTA = (
    "contract_version", "proposal_id", "candidate_id", "base_surface", "base_hash", "content_hash",
    "probe_id", "decision_hash", "verdict", "evidencia", "diff_sha256", "governance",
    "ledger_text", "proposal_hash",
)


class PromocionBloqueada(Exception):
    """El gate no pasa (o la promoción no puede proponerse). `motivos` son códigos estables."""

    def __init__(self, motivos) -> None:
        self.motivos = list(motivos)
        super().__init__("promoción bloqueada: " + ", ".join(self.motivos))


class PropuestaInvalida(Exception):
    """`proposal.json`/`change.diff` inexistente, manipulado o con forma inválida."""


# --- Utilidades --------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _sdd() -> SimpleNamespace:
    """Import diferido de `tools.dsguard.{core,repo,scope,sdd}`. `sdd.py` hace `from autonomy import
    core` (top-level), que requiere `tools/` en `sys.path` (patrón de `ds_guard.py` y
    `datasources/runtime.py`). Solo si `autonomy` no se resuelve se agrega `tools/` a `sys.path`. Si
    el import falla, la excepción llega al gate, que la convierte en motivo (fail-closed)."""
    try:
        from tools.dsguard import sdd as _modulo_sdd  # noqa: F401
    except ModuleNotFoundError as exc:
        if exc.name != "autonomy":
            raise
        tools_dir = str(Path(__file__).resolve().parents[1])
        if tools_dir not in sys.path:
            sys.path.append(tools_dir)  # append: no desplaza módulos ya resolubles
    from tools.dsguard.core import leer_control
    from tools.dsguard.repo import path_matches_any
    from tools.dsguard.scope import alcance_efectivo
    from tools.dsguard.sdd import read_estado, resolver_aprobacion_registrada
    return SimpleNamespace(
        leer_control=leer_control, path_matches_any=path_matches_any,
        alcance_efectivo=alcance_efectivo, read_estado=read_estado,
        resolver_aprobacion_registrada=resolver_aprobacion_registrada)


def _hash_propuesta(propuesta: dict) -> str:
    """sha256 del JSON canónico del contenido SIN el campo `proposal_hash`."""
    sin_hash = {k: v for k, v in propuesta.items() if k != "proposal_hash"}
    texto = json.dumps(sin_hash, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _json_bytes(datos: dict) -> bytes:
    return (json.dumps(datos, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lf(texto: str) -> str:
    return texto.replace("\r\n", "\n").replace("\r", "\n")


def _dir_propuesta(repo_root, candidate_id: str) -> Path:
    if not isinstance(candidate_id, str) or _RE_CANDIDATE_ID.fullmatch(candidate_id) is None:
        raise PropuestaInvalida(f"candidate_id inválido: {candidate_id!r}")
    ruta = raiz_improvement(repo_root) / DIR_PROPOSALS / candidate_id
    try:
        return verificar_dentro_de_improvement(repo_root, ruta)
    except PresupuestoInvalido:
        raise PropuestaInvalida("ruta de propuesta fuera de .harmessi/improvement") from None


def _ruta_superficie(repo_root, base_surface: str) -> Path:
    """Ruta de la superficie sin seguir enlaces: ningún componente puede ser symlink/junction."""
    if superficie_de_ruta(base_surface) != SUPERFICIE_OPTIMIZABLE:
        raise PromocionBloqueada([SUPERFICIE_NO_OPTIMIZABLE])
    actual = Path(repo_root)
    for parte in base_surface.split("/"):
        actual = actual / parte
        if es_enlace(actual):
            raise PromocionBloqueada([BASE_CAMBIADA])
    return actual


def _diff(base_surface: str, activo: str, propuesto: str) -> str:
    """Diff fiel: SIN normalizar EOL (`splitlines(keepends=True)`); una línea sin salto final lleva
    el marcador `\\ No newline at end of file`. Un diff vacío con contenido distinto es inválido."""
    salida = []
    lineas = difflib.unified_diff(
        activo.splitlines(keepends=True), propuesto.splitlines(keepends=True),
        fromfile=f"a/{base_surface}", tofile=f"b/{base_surface}", lineterm="\n")
    for i, linea in enumerate(lineas):
        salida.append(linea)
        if i >= 2 and not linea.endswith("\n"):
            salida.append("\n\\ No newline at end of file\n")
    if not salida:
        raise PromocionBloqueada([PROPUESTA_INVALIDA])
    return "".join(salida)


def _texto_activo(repo_root, base_surface: str) -> str:
    try:
        return _ruta_superficie(repo_root, base_surface).read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise PropuestaInvalida("la superficie activa no es UTF-8") from None


def _construir(repo_root, candidate_id: str, evals_root=None) -> tuple:
    """`(propuesta, diff_texto)` recomputados desde disco. Lanza `PromocionNoRespaldada` o
    `PromocionBloqueada`."""
    raiz = Path(repo_root)
    decision = verificar_promotable(raiz, candidate_id, evals_root=evals_root)
    try:
        cand = cargar_candidate(raiz, candidate_id)
    except CandidateCorrupta as exc:
        raise PromocionNoRespaldada(f"candidate no íntegra: {exc}") from None
    if superficie_de_ruta(cand.base_surface) != SUPERFICIE_OPTIMIZABLE:  # R5
        raise PromocionBloqueada([SUPERFICIE_NO_OPTIMIZABLE])
    if not base_vigente(raiz, cand):
        raise PromocionBloqueada([BASE_CAMBIADA])
    texto_diff = _diff(cand.base_surface, _texto_activo(raiz, cand.base_surface),
                       leer_contenido(raiz, candidate_id))
    if redactar_texto(texto_diff) != texto_diff:
        raise PromocionBloqueada([DIFF_SENSIBLE])
    ledger = (
        f"Promoción propuesta de {cand.base_surface} (candidate {cand.candidate_id}).\n"
        f"Evidencia: probe {decision['probe_id']}, decision_hash {decision['decision_hash']}, "
        f"veredicto {decision['verdict']}.\n"
        f"Requiere Change SDD con aprobaciones T1; la verificación de release sigue siendo obligatoria."
    )
    propuesta = {
        "contract_version": PROPOSAL_CONTRACT_VERSION,
        "proposal_id": cand.candidate_id,
        "candidate_id": cand.candidate_id,
        "base_surface": cand.base_surface,
        "base_hash": cand.base_hash,
        "content_hash": cand.content_hash,
        "probe_id": decision["probe_id"],
        "decision_hash": decision["decision_hash"],
        "verdict": decision["verdict"],
        "evidencia": {
            "suite": decision["suite"],
            "n_escenarios": decision["n_escenarios"],
            "runs": [{"run_id": e["run_id"], "role": e["role"], "repetition": e["repetition"],
                      "sha256": e["sha256"]} for e in decision["evidencia"]],
        },
        "diff_sha256": hashlib.sha256(texto_diff.encode("utf-8")).hexdigest(),
        "governance": {
            "requires": CANAL_REQUERIDO,
            "surface_class": SUPERFICIE_OPTIMIZABLE,
            "distributed": cand.base_surface.startswith(PREFIJO_DISTRIBUIDO),
            "steps": [
                "Citar proposal_hash en el proposal.md del Change y aprobar proposal/spec/design (T1).",
                "Implementar dentro del scope del Change y aplicar con aplicar_promocion.",
                "Correr tests, reviewer y verificación de release: la promoción no los sustituye.",
            ],
            "release_verification_required": True,
            "managed_baseline_note": "Actualizar el managed baseline es tarea del release/Change, "
                                     "no de esta API.",
        },
        "ledger_text": ledger,
    }
    propuesta["proposal_hash"] = _hash_propuesta(propuesta)
    return propuesta, texto_diff


# --- API ---------------------------------------------------------------------------

def proponer_promocion(repo_root, candidate_id: str, evals_root=None) -> dict:
    """Arma y escribe la propuesta de una candidate `promotable` (R1-R2). Solo escribe bajo
    `.harmessi/improvement/proposals/<candidate_id>/`. Devuelve el dict de `proposal.json`."""
    raiz = Path(repo_root)
    propuesta, texto_diff = _construir(raiz, candidate_id, evals_root)
    directorio = _dir_propuesta(raiz, candidate_id)
    with bloqueo(raiz):
        escribir_atomico(verificar_dentro_de_improvement(raiz, directorio / NOMBRE_DIFF),
                         texto_diff.encode("utf-8"))
        escribir_atomico(verificar_dentro_de_improvement(raiz, directorio / NOMBRE_PROPUESTA),
                         _json_bytes(propuesta))
    return propuesta


def cargar_propuesta(repo_root, candidate_id: str) -> dict:
    """Carga `proposal.json`; valida forma, `proposal_hash` y `diff_sha256` del `change.diff`."""
    directorio = _dir_propuesta(repo_root, candidate_id)
    try:
        datos = json.loads((directorio / NOMBRE_PROPUESTA).read_text(encoding="utf-8"))
        diff = (directorio / NOMBRE_DIFF).read_bytes()
    except FileNotFoundError:
        raise PropuestaInvalida(f"propuesta inexistente ({candidate_id})") from None
    except (OSError, ValueError) as exc:
        raise PropuestaInvalida(f"propuesta ilegible ({type(exc).__name__})") from None
    if not isinstance(datos, dict) or set(datos) != set(_CLAVES_PROPUESTA):
        raise PropuestaInvalida("proposal.json: claves inesperadas")
    v = datos["contract_version"]
    if isinstance(v, bool) or v != PROPOSAL_CONTRACT_VERSION:
        raise PropuestaInvalida("proposal.json: contract_version no soportada")
    if datos["candidate_id"] != candidate_id or datos["proposal_id"] != candidate_id:
        raise PropuestaInvalida("proposal.json: candidate_id no coincide")
    if not isinstance(datos["base_surface"], str) or not isinstance(datos["proposal_hash"], str) \
            or _hash_propuesta(datos) != datos["proposal_hash"]:
        raise PropuestaInvalida("proposal.json: proposal_hash no coincide (manipulado)")
    if hashlib.sha256(diff).hexdigest() != datos["diff_sha256"]:
        raise PropuestaInvalida("change.diff manipulado (diff_sha256 no coincide)")
    return datos


def _sigla(artefacto: str) -> str:
    return artefacto.split(".")[0].upper()


def evaluar_gate(repo_root, candidate_id: str, change_id: str, evals_root=None) -> list:
    """Lista de motivos de bloqueo (vacía = el gate pasa). Solo lectura; nunca lanza."""
    try:
        return _evaluar_gate(Path(repo_root), candidate_id, change_id, evals_root)
    except Exception as exc:  # noqa: BLE001 - fail-closed
        return [f"{PROPUESTA_INVALIDA}: gate falló ({type(exc).__name__})"]


def _evaluar_gate(raiz: Path, candidate_id: str, change_id: str, evals_root) -> list:
    # 1. Propuesta íntegra
    try:
        guardada = cargar_propuesta(raiz, candidate_id)
    except PropuestaInvalida:
        return [PROPUESTA_INVALIDA]
    if superficie_de_ruta(guardada["base_surface"]) != SUPERFICIE_OPTIMIZABLE:  # R5
        return [SUPERFICIE_NO_OPTIMIZABLE]
    # 2. Candidate promotable con evidencia vigente y base vigente
    try:
        verificar_promotable(raiz, candidate_id, evals_root=evals_root)
    except PromocionNoRespaldada as exc:
        return [BASE_CAMBIADA] if "archivo activo cambió" in str(exc) else [NO_PROMOTABLE]
    try:
        recomputada, _diff_txt = _construir(raiz, candidate_id, evals_root)
    except PromocionBloqueada as exc:
        return list(exc.motivos)
    except PromocionNoRespaldada:
        return [NO_PROMOTABLE]
    if recomputada != guardada:
        return [PROPUESTA_INVALIDA]
    motivos: list = []
    # 3. Change (import diferido de dsguard: si falla, la excepción llega a evaluar_gate => motivo)
    bloqueos, change_dir, control = _cargar_change_abierto(raiz, change_id)
    if bloqueos:
        return bloqueos
    ds = _sdd()
    # 4. Aprobaciones T1 de los tres artefactos
    for artefacto in ARTEFACTOS_APROBADOS:
        r = ds.resolver_aprobacion_registrada(raiz, change_id, artefacto)
        entrada = r.get("entrada")
        if r.get("estado") != "verified":
            motivos.append(f"APROBACION_{_sigla(artefacto)}_NO_VERIFICADA")
        elif not _es_t1(entrada):
            motivos.append(f"APROBACION_{_sigla(artefacto)}_NO_T1")
    # 5. Scope efectivo
    rutas, _hall = ds.alcance_efectivo(change_dir, control)
    if not ds.path_matches_any(guardada["base_surface"], rutas):
        motivos.append(FUERA_DE_ALCANCE)
    # 6. proposal.md cita el proposal_hash
    try:
        texto = (change_dir / "proposal.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        texto = ""
    if not _cita_ancla(texto, guardada["proposal_hash"]):
        motivos.append(PROPUESTA_NO_CITADA)
    return motivos


def _cargar_change_abierto(raiz: Path, change_id: str) -> tuple:
    """`(motivos, change_dir, control)`: motivos vacío = Change existente, `en_implementacion` y con
    `control.json` legible cuyo `change_id` coincide. Puede lanzar si `dsguard` no se importa."""
    if not isinstance(change_id, str) or _RE_CHANGE_ID.fullmatch(change_id) is None:
        return [CHANGE_INEXISTENTE], None, None
    ds = _sdd()
    change_dir = raiz / "openspec" / "changes" / change_id
    if not change_dir.is_dir():
        return [CHANGE_INEXISTENTE], None, None
    try:
        estado, _hallazgos = ds.read_estado(change_dir / "tasks.md")
    except OSError:
        estado = None
    if estado != ESTADO_REQUERIDO:
        return [CHANGE_NO_EN_IMPLEMENTACION], None, None
    try:
        control = ds.leer_control(change_dir / "control.json")
    except Exception:  # noqa: BLE001
        return [CONTROL_ILEGIBLE], None, None
    if not isinstance(control, dict) or control.get("change_id") != change_id:
        return [CONTROL_ILEGIBLE], None, None
    return [], change_dir, control


def verificar_change_abierto(repo_root, change_id: str) -> list:
    """Motivos (códigos estables) por los que `change_id` no es un Change abierto válido; lista vacía
    si existe, está `en_implementacion` y su `control.json` lleva ese `change_id`. Solo lectura;
    nunca lanza (fail-closed)."""
    try:
        return _cargar_change_abierto(Path(repo_root), change_id)[0]
    except Exception as exc:  # noqa: BLE001
        return [f"{CONTROL_ILEGIBLE}: {type(exc).__name__}"]


def _es_t1(entrada) -> bool:
    """T1 canónico: `approval_channel == console_confirmed` Y `channel_version == console/v1`."""
    return (isinstance(entrada, dict)
            and type(entrada.get("approval_channel")) is str
            and entrada.get("approval_channel") == CANAL_REQUERIDO
            and type(entrada.get("channel_version")) is str
            and entrada.get("channel_version") == VERSION_CANAL_REQUERIDA)


def _cita_ancla(texto: str, proposal_hash: str) -> bool:
    """Línea ancla `proposal_hash: <hash>` (opcional viñeta) fuera de comentarios HTML."""
    sin_comentarios = re.sub(r"<!--.*?-->", "", texto, flags=re.S)
    patron = r"^[ \t]*(?:[-*][ \t]+)?proposal_hash:[ \t]*" + re.escape(proposal_hash) + r"[ \t]*\r?$"
    return re.search(patron, sin_comentarios, flags=re.M) is not None


def aplicar_promocion(repo_root, candidate_id: str, change_id: str, evals_root=None,
                      ahora: Optional[datetime] = None) -> dict:
    """Ejecuta el gate y, si pasa, reemplaza SOLO la superficie de la candidate (atómico) y escribe
    `applied.json`. Con cualquier motivo => `PromocionBloqueada` sin escribir. Idempotente: si la
    superficie ya tiene `content_hash` y existe un `applied.json` coherente, no reescribe nada."""
    raiz = Path(repo_root)
    ahora = ahora or datetime.now(timezone.utc)
    with bloqueo(raiz):
        previo = _recuperar_o_idempotente(raiz, candidate_id, change_id, ahora)
        if previo is not None:
            return previo
        motivos = evaluar_gate(raiz, candidate_id, change_id, evals_root)
        if motivos:
            raise PromocionBloqueada(motivos)
        cand = cargar_candidate(raiz, candidate_id)
        propuesta = cargar_propuesta(raiz, candidate_id)
        contenido = leer_contenido(raiz, candidate_id).encode("utf-8")  # content.md se lee UNA vez
        if hash_contenido(contenido) != cand.content_hash:
            raise PromocionBloqueada([PROPUESTA_INVALIDA])
        destino = _ruta_superficie(raiz, cand.base_surface)
        base_bytes = destino.read_bytes()
        if hash_contenido(base_bytes) != cand.base_hash:
            raise PromocionBloqueada([BASE_CAMBIADA])
        registro = {"state": ESTADO_PENDING, "candidate_id": candidate_id,
                    "base_surface": cand.base_surface, "change_id": change_id,
                    "proposal_hash": propuesta["proposal_hash"],
                    "decision_hash": propuesta["decision_hash"], "probe_id": propuesta["probe_id"],
                    "base_hash": cand.base_hash, "content_hash": cand.content_hash,
                    "pending_utc": _iso(ahora)}
        _escribir_registro(raiz, candidate_id, registro)  # write-ahead
        if hash_contenido(destino.read_bytes()) != cand.base_hash:  # re-verificación final
            raise PromocionBloqueada([BASE_CAMBIADA])
        try:
            escribir_atomico(destino, contenido)
            if hash_contenido(destino.read_bytes()) != cand.content_hash:
                raise PromocionBloqueada([PROPUESTA_INVALIDA])
        except BaseException:
            _restaurar_base(destino, base_bytes, cand.base_hash)
            raise
        # La superficie ya tiene el contenido: si falla lo que sigue, `pending` permite recuperar.
        final = dict(registro, state=ESTADO_APPLIED, applied_utc=_iso(ahora))
        _escribir_registro(raiz, candidate_id, final)
        return dict(final, already_applied=False)


def _escribir_registro(raiz: Path, candidate_id: str, registro: dict) -> None:
    directorio = _dir_propuesta(raiz, candidate_id)
    escribir_atomico(verificar_dentro_de_improvement(raiz, directorio / NOMBRE_APLICADA),
                     _json_bytes(registro))


def _restaurar_base(destino: Path, base_bytes: bytes, base_hash: str) -> None:
    """Si la escritura de la superficie falló a medias, vuelve a la base original (mejor esfuerzo)."""
    try:
        if hash_contenido(destino.read_bytes()) != base_hash:
            escribir_atomico(destino, base_bytes)
    except OSError:
        pass


def _recuperar_o_idempotente(raiz: Path, candidate_id: str, change_id: str, ahora: datetime):
    """Resultado si la promoción ya está aplicada (idempotente) o quedó `pending` con la superficie
    ya reemplazada (se completa a `applied`, sin gate, solo con el mismo change_id). Si no, None."""
    try:
        cand = cargar_candidate(raiz, candidate_id)
        propuesta = cargar_propuesta(raiz, candidate_id)
        ruta = _dir_propuesta(raiz, candidate_id) / NOMBRE_APLICADA
        registro = json.loads(ruta.read_text(encoding="utf-8"))
        actual = _ruta_superficie(raiz, cand.base_surface).read_bytes()
    except (CandidateCorrupta, PropuestaInvalida, PromocionBloqueada, OSError, ValueError):
        return None
    if not (isinstance(registro, dict) and registro.get("candidate_id") == candidate_id
            and registro.get("change_id") == change_id
            and registro.get("proposal_hash") == propuesta["proposal_hash"]
            and registro.get("content_hash") == cand.content_hash
            and hash_contenido(actual) == cand.content_hash):
        return None
    if registro.get("state") == ESTADO_APPLIED:
        return dict(registro, already_applied=True)
    if registro.get("state") == ESTADO_PENDING:
        final = dict(registro, state=ESTADO_APPLIED, applied_utc=_iso(ahora))
        _escribir_registro(raiz, candidate_id, final)
        return dict(final, already_applied=False)
    return None
