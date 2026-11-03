"""Ciclo de mejora acotado (v0.14 Change 5, R7-R9).

Por qué existe: orquesta, para una lista corta de propuestas, el camino ya gobernado
`crear_candidate -> ejecutar_probe -> decidir/aplicar_decision`, con la MISMA política y suite para todas,
y se detiene de forma determinista cuando se agota un presupuesto. No selecciona ni promueve nada:
devuelve la lista de candidates con su estado. Nunca importa `promotion` ni `lessons`.

Principios:
- Profundidad 1: cada candidate se basa en el archivo activo (lo garantiza `crear_candidate`); las
  superficies Protected (incluido el engine, `tools/...`) se rechazan estructuralmente.
- Sin recursión: un lock de archivo `.harmessi/improvement/.cycle.lock` (`O_EXCL`) con token único
  (pid+uuid) impide anidar ciclos (`CicloAnidado`). Solo se libera si el contenido sigue siendo el
  propio token; un lock stale (mtime más viejo que el techo duro de reloj) se retira con rename atómico
  a un nombre único. El mtime se refresca entre propuestas.
- Techos duros (R9): el presupuesto se carga y valida antes de empezar (`PresupuestoInvalido` si alguna
  clave supera `HARD_CEILING`); el ciclo no acepta más propuestas que `HARD_CEILING["max_candidates"]`;
  se exige `2 * repeats <= max_runs_per_candidate` y una suite cargable ANTES de crear candidates (si no,
  rechazo global con `detenido_por == "rechazo"`, sin consumir presupuesto ni tomar el lock).
- `detenido_por` usa los nombres de recurso del presupuesto: `candidates`, `probe_cycles`, `runs`,
  `retries`, `lock`, `wall_clock` (o `None`; `"rechazo"` solo para el rechazo global previo).
- En TODAS las etapas: `PresupuestoAgotado` detiene el ciclo; rechazos de reglas y evidencia/estado
  corruptos (`CandidateRechazada`, `ProbeRechazado`, `CandidateCorrupta`, `ProbeCorrupto`,
  `PolicyInvalida`, `EvidenciaInvalida`) se registran como rechazo y el ciclo sigue con la siguiente.
  Los resultados y rechazos acumulados se preservan siempre.
Solo stdlib y paquetes permitidos; sin red ni subprocess.
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from tools.harmessi_bench.redact import redactar_texto
from tools.harmessi_bench.suite import load_suite_y_casos
from tools.harmessi_improve import candidate as _candidate
from tools.harmessi_improve import decision as _decision
from tools.harmessi_improve import probe as _probe
from tools.harmessi_improve.budget import (
    HARD_CEILING,
    PresupuestoAgotado,
    PresupuestoInvalido,
    cargar_presupuesto,
    raiz_improvement,
    verificar_dentro_de_improvement,
)
from tools.harmessi_improve.policy import PolicyInvalida, ProbePolicy

NOMBRE_CYCLE_LOCK = ".cycle.lock"
CLAVES_PROPUESTA = ("base_surface", "content", "hypothesis", "provenance")
PROPUESTA_INVALIDA = "PROPUESTA_INVALIDA"
CICLO_INVALIDO = "CICLO_INVALIDO"
ETAPA_CICLO = "ciclo"
ETAPA_CANDIDATE = "candidate"
ETAPA_PROBE = "probe"
ETAPA_DECISION = "decision"

_RECURSO_POR_CLAVE = {
    "max_candidates": "candidates",
    "max_probe_cycles": "probe_cycles",
    "max_runs_per_candidate": "runs",
    "max_retries": "retries",
    "max_wall_clock_s": "wall_clock",
}
_ERRORES_DE_RECHAZO = (
    _candidate.CandidateRechazada, _probe.ProbeRechazado, _candidate.CandidateCorrupta,
    _probe.ProbeCorrupto, PolicyInvalida, _decision.EvidenciaInvalida,
)


class CicloAnidado(Exception):
    """Ya hay un ciclo en ejecución (lock presente y vigente): no se admite anidar ciclos."""


def probe_id_de(candidate_id: str) -> str:
    """`probe_id` determinista derivado del `candidate_id` (`cand-<12hex>` -> `p-<12hex>`)."""
    return "p-" + candidate_id[len("cand-"):]


def _recurso(exc: PresupuestoAgotado) -> str:
    return _RECURSO_POR_CLAVE.get(exc.recurso, exc.recurso)


# --- Lock de anidamiento (M1) ------------------------------------------------------

def _ruta_lock(repo_root) -> Path:
    return verificar_dentro_de_improvement(repo_root, raiz_improvement(repo_root) / NOMBRE_CYCLE_LOCK)


def _es_stale(ruta: Path) -> Optional[bool]:
    """True si el lock es más viejo que el techo duro de reloj; None si desapareció."""
    try:
        return time.time() - ruta.stat().st_mtime > HARD_CEILING["max_wall_clock_s"]
    except OSError:
        return None


def _tomar_lock(repo_root) -> tuple:
    """`(ruta, token)`. Lanza `CicloAnidado` si hay un lock vigente."""
    ruta = _ruta_lock(repo_root)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    token = f"pid={os.getpid()} id={uuid.uuid4().hex}\n"
    for _intento in range(3):
        try:
            fd = os.open(str(ruta), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            stale = _es_stale(ruta)
            if stale is None:
                continue  # desapareció entre medio: reintenta
            if not stale:
                raise CicloAnidado("ya hay un ciclo en ejecución (.cycle.lock vigente)") from None
            retirado = ruta.with_name(f"{NOMBRE_CYCLE_LOCK}.stale-{uuid.uuid4().hex}")
            try:
                os.replace(str(ruta), str(retirado))  # rename atómico: solo uno gana
            except OSError:
                continue
            if _es_stale(retirado) is False:  # carrera: se retiró un lock recién creado por otro
                try:
                    os.rename(str(retirado), str(ruta))
                except OSError:
                    pass
                raise CicloAnidado("ya hay un ciclo en ejecución (.cycle.lock vigente)") from None
            try:
                retirado.unlink()
            except OSError:
                pass
            continue
        try:
            try:
                os.write(fd, token.encode("ascii"))
            finally:
                os.close(fd)
        except BaseException:
            try:
                ruta.unlink()
            except OSError:
                pass
            raise
        return ruta, token
    raise CicloAnidado("no se pudo obtener .cycle.lock")


def _refrescar_lock(ruta: Path, token: str) -> None:
    try:
        if ruta.read_text(encoding="ascii") == token:
            os.utime(str(ruta), None)
    except (OSError, ValueError):
        pass


def _liberar_lock(ruta: Path, token: str) -> None:
    """Borra el lock solo si sigue siendo el propio (token coincide)."""
    try:
        if ruta.read_text(encoding="ascii") == token:
            ruta.unlink()
    except (OSError, ValueError):
        pass


# --- Ciclo -------------------------------------------------------------------------

def _rechazo(indice, etapa: str, codigo: str, mensaje: str, candidate_id: Optional[str] = None) -> dict:
    return {"indice": indice, "etapa": etapa, "codigo": codigo,
            "mensaje": redactar_texto(mensaje or ""), "candidate_id": candidate_id}


def _propuesta_valida(propuesta) -> bool:
    return isinstance(propuesta, dict) and set(propuesta) == set(CLAVES_PROPUESTA)


def _codigo_de(exc: Exception) -> tuple:
    codigo = getattr(exc, "codigo", None)
    if not isinstance(codigo, str):
        codigo = "EVIDENCIA_INVALIDA" if isinstance(exc, _decision.EvidenciaInvalida) else type(exc).__name__
    return codigo, (getattr(exc, "mensaje", None) or str(exc))


def ejecutar_ciclo(repo_root, propuestas, suite_path, adapter, target, policy: ProbePolicy,
                   seed: Optional[int] = None, evals_root=None,
                   ahora: Optional[datetime] = None) -> dict:
    """Procesa `propuestas` en orden y devuelve
    `{"resultados": [{candidate_id, probe_id, verdict, candidate_status}], "detenido_por": None|recurso,
    "rechazos": [...]}`. `detenido_por` es el recurso agotado (`candidates`, `probe_cycles`, `runs`,
    `retries`, `lock`, `wall_clock`), `"rechazo"` si el ciclo no pudo arrancar (política/suite
    incompatibles) o None. Las propuestas rechazadas van a `rechazos` y NO detienen el ciclo.
    No promueve ni escribe lessons."""
    raiz = Path(repo_root)
    if not isinstance(policy, ProbePolicy):
        raise PolicyInvalida("policy debe ser una ProbePolicy")
    if isinstance(propuestas, (str, bytes, dict)) or not isinstance(propuestas, (list, tuple)):
        raise PresupuestoInvalido("propuestas debe ser una lista")
    if len(propuestas) > HARD_CEILING["max_candidates"]:
        raise PresupuestoInvalido(
            f"{len(propuestas)} propuestas superan el techo duro {HARD_CEILING['max_candidates']}")
    presupuesto = cargar_presupuesto(raiz)  # valida claves y techos duros antes de empezar (R9)

    # L1: precondiciones globales antes de crear candidates
    if 2 * policy.repeats > presupuesto.max_runs_per_candidate:
        return {"resultados": [], "detenido_por": "rechazo", "rechazos": [_rechazo(
            None, ETAPA_CICLO, CICLO_INVALIDO,
            f"2*repeats ({2 * policy.repeats}) supera max_runs_per_candidate ({presupuesto.max_runs_per_candidate})")]}
    try:
        load_suite_y_casos(Path(suite_path))
    except (OSError, ValueError) as exc:
        return {"resultados": [], "detenido_por": "rechazo", "rechazos": [_rechazo(
            None, ETAPA_CICLO, _probe.SUITE_INVALIDA, f"suite ilegible o inválida ({type(exc).__name__})")]}

    lock, token = _tomar_lock(raiz)
    resultados: list = []
    rechazos: list = []
    detenido_por: Optional[str] = None
    try:
        for indice, propuesta in enumerate(propuestas):
            _refrescar_lock(lock, token)
            if not _propuesta_valida(propuesta):
                rechazos.append(_rechazo(indice, ETAPA_CANDIDATE, PROPUESTA_INVALIDA,
                                         "la propuesta exige base_surface, content, hypothesis y provenance"))
                continue
            etapa = ETAPA_CANDIDATE
            candidate_id = None
            probe_id = None
            try:
                cand = _candidate.crear_candidate(
                    raiz, propuesta["base_surface"], propuesta["content"], propuesta["hypothesis"],
                    propuesta["provenance"], budget=presupuesto, ahora=ahora)
                candidate_id = cand.candidate_id
                probe_id = probe_id_de(candidate_id)
                etapa = ETAPA_PROBE
                _probe.ejecutar_probe(raiz, candidate_id, suite_path, adapter, target, policy, probe_id,
                                      seed=seed, evals_root=evals_root, ahora=ahora)
                etapa = ETAPA_DECISION
                final = _decision.aplicar_decision(raiz, probe_id, evals_root=evals_root, ahora=ahora)
                veredicto = _decision.cargar_decision(raiz, probe_id)["verdict"]
            except PresupuestoAgotado as exc:
                detenido_por = _recurso(exc)
                if candidate_id is not None:  # resultado parcial: la candidate existe
                    try:
                        estado = _candidate.cargar_candidate(raiz, candidate_id).status
                    except _candidate.CandidateCorrupta:
                        estado = None
                    resultados.append({"candidate_id": candidate_id,
                                       "probe_id": probe_id if etapa == ETAPA_DECISION else None,
                                       "verdict": None,
                                       "candidate_status": estado})
                break
            except _ERRORES_DE_RECHAZO as exc:
                codigo, mensaje = _codigo_de(exc)
                rechazos.append(_rechazo(indice, etapa, codigo, mensaje, candidate_id))
                continue
            resultados.append({"candidate_id": candidate_id, "probe_id": probe_id,
                               "verdict": veredicto, "candidate_status": final.status})
    finally:
        _liberar_lock(lock, token)
    return {"resultados": resultados, "detenido_por": detenido_por, "rechazos": rechazos}
