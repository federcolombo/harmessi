"""Decisión de una candidate a partir de la evidencia de un probe (v0.14 Change 3, R1-R11).

Por qué existe: un probe mide, pero no decide. Este módulo convierte la evidencia en disco
(`probe.json` + `result.json` de cada corrida) en un veredicto reproducible y es el ÚNICO camino
que transiciona una candidate a `promotable`/`rejected`/`inconclusive`.

Principios:
- Ninguna API recibe criterios ni veredictos: la política sale congelada de `probe.json` y los
  datos salen de scorers deterministas ya persistidos (R10). No hay autoevaluación.
- Todo se re-deriva desde disco y se verifica: hash de política, sha256 de cada `result.json`
  (se parsean los MISMOS bytes que se hashean), identidad recomputada de cada manifest, coherencia
  baseline/candidate (solo `skills`/`surfaces_hash` pueden diferir, y la identidad candidate debe ser
  la de sustituir la superficie por el contenido de la candidate), target y seed, y el `outcome`
  declarado por el probe contra los `ok`/`availability_error` reales. Cualquier discrepancia =>
  `EvidenciaInvalida` y no se emite decisión (R1).
- El veredicto base lo da `compare_runs` sobre corridas agregadas por repetición (R3-R4).
- Un escenario inestable solo del lado candidate con baseline estable-pass es una regresión de la
  candidate (no se excluye); inestable del baseline con candidate estable-pass se excluye.
- Muestra mínima (`min_scenarios`) y empate solo por `mean_score` (`duration_s` no es determinista).
- `decision.json` lleva un `decision_hash` canónico; `verificar_promotable` lo recomputa (R9).
- Escrituras: solo `.harmessi/improvement/decisions/` y la transición de la candidate (R11).
Solo stdlib y paquetes permitidos; sin red ni subprocess.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from tools.harmessi_bench import compare as _compare
from tools.harmessi_bench.redact import redactar_texto
from tools.harmessi_bench.runmanifest import (
    calcular_identity_hash,
    diferencias_materiales,
    sustituir_superficie,
)
from tools.harmessi_improve import probe as _probe
from tools.harmessi_improve.budget import (
    PresupuestoInvalido,
    bloqueo,
    es_enlace,
    escribir_atomico,
    raiz_improvement,
    verificar_dentro_de_improvement,
)
from tools.harmessi_improve.candidate import (
    ESTADO_EVALUATED,
    ESTADO_INCONCLUSIVE,
    ESTADO_PROMOTABLE,
    ESTADO_PROPOSED,
    ESTADO_REJECTED,
    Candidate,
    CandidateCorrupta,
    base_vigente,
    cargar_candidate,
    leer_contenido,
    transicionar_sin_lock,
)
from tools.harmessi_improve.policy import PolicyInvalida, ProbePolicy, hash_policy

DECISION_CONTRACT_VERSION = 1
DIR_DECISIONS = "decisions"
NOMBRE_DECISION = "decision.json"
EVIDENCE_KIND = "deterministic_scorers"
DIMENSIONES_SOPORTADAS = ["passed", "mean_score"]

VER_CANDIDATE_MEJOR = _compare.VEREDICTO_CANDIDATE_MEJOR
VER_BASELINE_MEJOR = _compare.VEREDICTO_BASELINE_MEJOR
VER_EQUIVALENTE = _compare.VEREDICTO_EQUIVALENTE
VER_INCONCLUSO = _compare.VEREDICTO_INCONCLUSO

# R6: veredicto -> estado final de la candidate
_ESTADO_POR_VEREDICTO = {
    VER_CANDIDATE_MEJOR: ESTADO_PROMOTABLE,
    VER_BASELINE_MEJOR: ESTADO_REJECTED,
    VER_EQUIVALENTE: ESTADO_REJECTED,
    VER_INCONCLUSO: ESTADO_INCONCLUSIVE,
}

_RE_PROBE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_DIFERENCIAS_ESPERADAS = {"skills", "surfaces_hash"}
_CLAVES_DECISION = (
    "contract_version", "probe_id", "candidate_id", "verdict", "reason", "candidate_status",
    "outcome", "policy", "policy_hash", "evidencia", "inestables", "evidence_kind",
    "dimensiones_soportadas", "n_escenarios", "n_estables", "suite", "target", "seed",
    "decision_hash",
)


class EvidenciaInvalida(Exception):
    """La evidencia en disco no es íntegra o no permite decidir."""


class PromocionNoRespaldada(Exception):
    """La candidate no está respaldada por una decisión `candidate_better` íntegra."""


# --- Utilidades --------------------------------------------------------------------

def _json_bytes(datos: dict) -> bytes:
    return (json.dumps(datos, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _hash_decision(decision: dict) -> str:
    """sha256 del JSON canónico del contenido SIN el campo `decision_hash`."""
    sin_hash = {k: v for k, v in decision.items() if k != "decision_hash"}
    texto = json.dumps(sin_hash, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _validar_probe_id(probe_id) -> str:
    if not isinstance(probe_id, str) or _RE_PROBE_ID.fullmatch(probe_id) is None:
        raise EvidenciaInvalida(f"probe_id inválido: {probe_id!r}")
    return probe_id


def _ruta_decision(repo_root, probe_id: str) -> Path:
    ruta = raiz_improvement(repo_root) / DIR_DECISIONS / probe_id / NOMBRE_DECISION
    try:
        return verificar_dentro_de_improvement(repo_root, ruta)
    except PresupuestoInvalido as exc:
        raise EvidenciaInvalida(f"ruta de decisión inválida: {exc}") from None


def _promedio(valores) -> float:
    valores = list(valores)
    return round(sum(valores) / len(valores), 6) if valores else 0.0


def _numero(valor, defecto: float = 0.0) -> float:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return defecto
    return float(valor)


# --- Verificación de la evidencia (R1, MED-5, MED-6) --------------------------------

def _leer_run(evals: Path, entrada: dict, probe: dict) -> dict:
    """Lee `result.json` UNA vez: hashea y parsea los mismos bytes."""
    ruta = evals / entrada["run_id"] / "result.json"
    try:
        contenido = ruta.read_bytes()
    except OSError:
        raise EvidenciaInvalida(f"result.json inexistente o ilegible ({entrada['run_id']})") from None
    if hashlib.sha256(contenido).hexdigest() != entrada["sha256"]:
        raise EvidenciaInvalida(f"result.json alterado ({entrada['run_id']})")
    try:
        datos = json.loads(contenido.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        raise EvidenciaInvalida(f"result.json no es JSON válido ({entrada['run_id']})") from None
    if not isinstance(datos, dict) or not isinstance(datos.get("resultados"), list):
        raise EvidenciaInvalida(f"result.json con forma inválida ({entrada['run_id']})")
    manifest = datos.get("run_manifest")
    if not isinstance(manifest, dict):
        raise EvidenciaInvalida(f"result.json sin run_manifest ({entrada['run_id']})")
    if not (calcular_identity_hash(manifest) == manifest.get("identity_hash") == entrada["identity_hash"]):
        raise EvidenciaInvalida(f"identity_hash no coincide con el manifest ({entrada['run_id']})")
    if datos.get("cases_hash") != probe["cases_hash"]:
        raise EvidenciaInvalida(f"cases_hash no coincide ({entrada['run_id']})")
    return datos


def _verificar_manifests(raiz: Path, probe: dict, verificados: list) -> None:
    """Coherencia entre corridas: identidad por rol, diferencia material esperada, target y seed."""
    objetivo = probe["target"]
    por_rol = {}
    for entrada, datos in verificados:
        m = datos["run_manifest"]
        t = m.get("target")
        if not isinstance(t, dict) or any(t.get(k) != objetivo.get(k) for k in ("provider_id", "model", "effort")):
            raise EvidenciaInvalida(f"target del manifest no coincide con el probe ({entrada['run_id']})")
        if m.get("seed") != probe["seed"]:
            raise EvidenciaInvalida(f"seed del manifest no coincide con el probe ({entrada['run_id']})")
        if datos.get("target") != verificados[0][1].get("target"):
            raise EvidenciaInvalida("target distinto entre corridas")
        por_rol.setdefault(entrada["role"], []).append(m)
    manifests = {}
    for rol, lista in por_rol.items():
        if len({m["identity_hash"] for m in lista}) != 1:
            raise EvidenciaInvalida(f"las repeticiones de {rol} tienen identidades distintas")
        manifests[rol] = lista[0]
    if _probe.ROL_BASELINE in manifests and _probe.ROL_CANDIDATE in manifests:
        mb, mc = manifests[_probe.ROL_BASELINE], manifests[_probe.ROL_CANDIDATE]
        if mb["identity_hash"] == mc["identity_hash"]:
            raise EvidenciaInvalida("baseline y candidate tienen la misma identidad")
        if not set(diferencias_materiales(mb, mc)) <= _DIFERENCIAS_ESPERADAS:
            raise EvidenciaInvalida("baseline y candidate difieren en más que skills/surfaces_hash")
        try:
            contenido = leer_contenido(raiz, probe["candidate_id"]).encode("utf-8")
            esperada = sustituir_superficie(mb, raiz, probe["base_surface"], contenido)["identity_hash"]
        except (ValueError, OSError, CandidateCorrupta) as exc:
            raise EvidenciaInvalida(f"no se pudo re-derivar la identidad candidate ({type(exc).__name__})") from None
        if esperada != mc["identity_hash"]:
            raise EvidenciaInvalida("la identidad candidate no corresponde a baseline + contenido de la candidate")


def _verificar_candidate(raiz, probe: dict) -> Candidate:
    try:
        cand = cargar_candidate(raiz, probe["candidate_id"])
    except CandidateCorrupta as exc:
        raise EvidenciaInvalida(f"candidate no íntegra: {exc}") from None
    if (cand.content_hash != probe["candidate_hash"] or cand.base_hash != probe["baseline_surface_hash"]
            or cand.base_surface != probe["base_surface"]):
        raise EvidenciaInvalida("la candidate ya no coincide con content_hash/base_hash del probe")
    return cand


def _verificar_outcome(outcome: str, verificados: list) -> None:
    """HIGH-3: el outcome declarado debe concordar con los `ok`/`availability_error` reales."""
    fallo = {_probe.ROL_BASELINE: False, _probe.ROL_CANDIDATE: False}
    avail = False
    for entrada, datos in verificados:
        for r in datos["resultados"]:
            if not isinstance(r, dict):
                raise EvidenciaInvalida("resultado mal formado")
            if r.get("availability_error"):
                avail = True
                fallo[entrada["role"]] = True
            if r.get("ok") is not True:
                fallo[entrada["role"]] = True
    b, c = fallo[_probe.ROL_BASELINE], fallo[_probe.ROL_CANDIDATE]
    coherente = {
        _probe.OUTCOME_SUCCESS: not (b or c),
        _probe.OUTCOME_CANDIDATE_FAILURE: c and not b and not avail,
        _probe.OUTCOME_BASELINE_FAILURE: b and not c and not avail,
        _probe.OUTCOME_ENVIRONMENT_FAILURE: avail or (b and c),
        _probe.OUTCOME_INCONCLUSIVE: True,
    }
    if not coherente.get(outcome, False):
        raise EvidenciaInvalida(f"el outcome declarado ({outcome}) no concuerda con los result.json")


# --- Agregación (R3, MED-7) ---------------------------------------------------------

def _pasa(resultado) -> bool:
    score = resultado.get("score") if isinstance(resultado, dict) else None
    return resultado.get("ok") is True and isinstance(score, dict) and score.get("passed") is True


def _indice(datos: dict) -> dict:
    indice = {}
    for r in datos["resultados"]:
        sid = r.get("scenario_id") if isinstance(r, dict) else None
        if not isinstance(sid, str) or not sid or sid in indice or not isinstance(r.get("score"), dict):
            raise EvidenciaInvalida(f"resultado mal formado o duplicado en {datos.get('run_id')!r}")
        indice[sid] = r
    return indice


def _agregar_rol(corridas: list) -> dict:
    """`{scenario_id: {p, n, ok, availability_error, score, duration_s}}` sobre las repeticiones."""
    indices = [_indice(d) for d in corridas]
    ids = set(indices[0])
    if any(set(i) != ids for i in indices[1:]):
        raise EvidenciaInvalida("las repeticiones de un mismo rol difieren en sus escenarios")
    agregado = {}
    for sid in sorted(ids):
        filas = [i[sid] for i in indices]
        agregado[sid] = {
            "p": sum(1 for f in filas if _pasa(f)),
            "n": len(filas),
            "ok": all(f.get("ok") is True for f in filas),
            "availability_error": next((f["availability_error"] for f in filas if f.get("availability_error")), None),
            "score": _promedio(_numero(f["score"].get("score"), 1.0 if _pasa(f) else 0.0) for f in filas),
            "duration_s": _promedio(_numero(f.get("duration_s")) for f in filas),
        }
    return agregado


def _inestable(a: dict) -> bool:
    return 0 < a["p"] < a["n"]


def _corrida_agregada(rol: str, agregado: dict, incluidos: set, forzar_fallo: set, primera: dict) -> dict:
    return {
        "run_id": f"{rol}-agregado",
        "resultados": [
            {"scenario_id": sid, "ok": a["ok"], "availability_error": a["availability_error"],
             "score": {"passed": a["p"] == a["n"] and sid not in forzar_fallo, "score": a["score"]},
             "duration_s": a["duration_s"]}
            for sid, a in agregado.items() if sid in incluidos
        ],
        "suite": primera.get("suite"),
        "cases_hash": primera.get("cases_hash"),
        "evaluator_version": primera.get("evaluator_version"),
        "run_manifest": primera.get("run_manifest"),
    }


# --- Empate (R5) -------------------------------------------------------------------

def _desempatar(politica: ProbePolicy, res_base: list, res_cand: list):
    """Primer criterio secundario (orden declarado) con diferencia no nula y >= `min_delta`.
    Devuelve `(veredicto, detalle)` o `(None, "")`. Solo `mean_score` (mayor es mejor)."""
    for metrica in politica.secondary:
        if metrica == "mean_score":
            delta = _promedio(r["score"]["score"] for r in res_cand) - _promedio(r["score"]["score"] for r in res_base)
        else:
            continue
        delta = round(delta, 9)
        if delta != 0 and abs(delta) >= politica.min_delta:
            veredicto = VER_CANDIDATE_MEJOR if delta > 0 else VER_BASELINE_MEJOR
            return veredicto, f"desempate por {metrica} (diferencia {abs(delta)} >= min_delta {politica.min_delta})"
    return None, ""


def _comparar(politica: ProbePolicy, verificados: list):
    """`(veredicto, motivo, inestables, n_escenarios, n_comparables)` para outcome success."""
    por_rol = {_probe.ROL_BASELINE: [], _probe.ROL_CANDIDATE: []}
    for entrada, datos in verificados:
        por_rol[entrada["role"]].append((entrada["repetition"], datos))
    esperado = list(range(1, politica.repeats + 1))
    corridas = {}
    for rol, lista in por_rol.items():
        lista.sort(key=lambda t: t[0])
        if [k for k, _ in lista] != esperado:
            raise EvidenciaInvalida(f"repeticiones incompletas o inesperadas para {rol}")
        corridas[rol] = [d for _, d in lista]
    base = _agregar_rol(corridas[_probe.ROL_BASELINE])
    cand = _agregar_rol(corridas[_probe.ROL_CANDIDATE])
    todos = sorted(set(base) | set(cand))
    n_total = len(todos)

    incluidos, forzar_fallo, inestables = set(), set(), []
    for sid in todos:
        b, c = base.get(sid), cand.get(sid)
        ub = b is not None and _inestable(b)
        uc = c is not None and _inestable(c)
        efecto = "incluido"
        if b is None or c is None:
            efecto = "excluido" if (ub or uc) else "incluido"
        elif not ub and not uc:
            efecto = "incluido"
        elif uc and not ub and b["p"] == b["n"]:
            efecto = "regresion_candidate"  # baseline estable-pass, candidate inestable
        else:
            efecto = "excluido"
        if efecto != "excluido":
            incluidos.add(sid)
        if efecto == "regresion_candidate":
            forzar_fallo.add(sid)
        if ub or uc:
            inestables.append({"scenario_id": redactar_texto(sid), "efecto": efecto,
                               "baseline": [b["p"], b["n"]] if b else None,
                               "candidate": [c["p"], c["n"]] if c else None})
    n_comp = len(incluidos)

    for rol, lado in ((_probe.ROL_BASELINE, base), (_probe.ROL_CANDIDATE, cand)):
        total = len(lado)
        estables = sum(1 for a in lado.values() if not _inestable(a))
        if total == 0 or estables / total + 1e-12 < politica.min_stable_ratio:
            return (VER_INCONCLUSO, f"inestable: {estables}/{total} escenarios estables en {rol} "
                    f"(min_stable_ratio {politica.min_stable_ratio})", inestables, n_total, n_comp)
    if n_comp == 0:
        return VER_INCONCLUSO, "inestable: no quedan escenarios comparables", inestables, n_total, n_comp
    if n_comp < politica.min_scenarios:
        return (VER_INCONCLUSO, f"muestra_insuficiente: {n_comp} escenarios comparables "
                f"(min_scenarios {politica.min_scenarios})", inestables, n_total, n_comp)
    agg_base = _corrida_agregada(_probe.ROL_BASELINE, base, incluidos, set(), corridas[_probe.ROL_BASELINE][0])
    agg_cand = _corrida_agregada(_probe.ROL_CANDIDATE, cand, incluidos, forzar_fallo,
                                 corridas[_probe.ROL_CANDIDATE][0])
    try:
        reporte = _compare.compare_runs(agg_base, agg_cand)
    except ValueError as exc:
        raise EvidenciaInvalida(f"corridas no comparables: {exc}") from None
    veredicto, motivo = reporte.verdict, reporte.verdict_reason
    if veredicto == VER_EQUIVALENTE:
        pasan = sum(1 for r in agg_base["resultados"] + agg_cand["resultados"] if r["score"]["passed"])
        if pasan == 0:
            return (VER_INCONCLUSO, "equivalencia no informativa: ningún caso pasa en ninguna corrida",
                    inestables, n_total, n_comp)
        if politica.tie_policy == "inconclusive":
            return VER_INCONCLUSO, f"empate con tie_policy=inconclusive ({motivo})", inestables, n_total, n_comp
        if politica.tie_policy == "secondary":
            v2, detalle = _desempatar(politica, agg_base["resultados"], agg_cand["resultados"])
            if v2 is not None:
                return v2, f"{detalle}; {motivo}", inestables, n_total, n_comp
    return veredicto, motivo, inestables, n_total, n_comp


# --- API ---------------------------------------------------------------------------

def decidir(repo_root, probe_id: str, evals_root=None, registrar: bool = False) -> dict:
    """Decisión (dict con `decision_hash`) de un probe `completed`. No recibe criterios (R1/R10).
    Con `registrar=True` escribe `decision.json` (si ya existe debe ser idéntico)."""
    raiz = Path(repo_root)
    _validar_probe_id(probe_id)
    try:
        probe = _probe.cargar_probe(raiz, probe_id)
        politica = ProbePolicy.desde_dict(probe["policy"])
    except (_probe.ProbeCorrupto, PolicyInvalida) as exc:
        raise EvidenciaInvalida(f"probe no íntegro: {exc}") from None
    if hash_policy(politica) != probe["policy_hash"]:
        raise EvidenciaInvalida("policy_hash no coincide con la política")
    if probe["status"] != _probe.STATUS_COMPLETED:
        raise EvidenciaInvalida("el probe no está completed: no es decidible")
    _verificar_candidate(raiz, probe)
    evals = Path(evals_root) if evals_root is not None else raiz / ".harmessi" / "evals"
    if es_enlace(raiz / ".harmessi") or es_enlace(evals):
        raise EvidenciaInvalida(".harmessi o la raíz de evals es un enlace: no permitido")
    verificados = [(e, _leer_run(evals, e, probe)) for e in probe["runs"]]
    outcome = probe["outcome"]
    _verificar_outcome(outcome, verificados)
    _verificar_manifests(raiz, probe, verificados)

    inestables: list = []
    n_total = n_comp = 0
    if outcome == _probe.OUTCOME_SUCCESS:
        veredicto, motivo, inestables, n_total, n_comp = _comparar(politica, verificados)
    elif outcome == _probe.OUTCOME_CANDIDATE_FAILURE:
        veredicto, motivo = VER_BASELINE_MEJOR, "la candidate falló de forma confirmada (candidate_failure)"
    else:  # environment_failure, baseline_failure, inconclusive: nunca baseline_better
        veredicto, motivo = VER_INCONCLUSO, f"el probe terminó con outcome {outcome}: no hay evidencia comparable"
    decision = {
        "contract_version": DECISION_CONTRACT_VERSION,
        "probe_id": probe_id,
        "candidate_id": probe["candidate_id"],
        "verdict": veredicto,
        "reason": redactar_texto(motivo),
        "candidate_status": _ESTADO_POR_VEREDICTO[veredicto],
        "outcome": outcome,
        "policy": probe["policy"],
        "policy_hash": probe["policy_hash"],
        "evidencia": [{"run_id": e["run_id"], "role": e["role"], "repetition": e["repetition"],
                       "sha256": e["sha256"], "identity_hash": e["identity_hash"]}
                      for e, _d in verificados],
        "inestables": inestables,
        "evidence_kind": EVIDENCE_KIND,
        "dimensiones_soportadas": list(DIMENSIONES_SOPORTADAS),
        "n_escenarios": n_total,
        "n_estables": n_comp,
        "suite": probe["suite"],
        "target": probe["target"],
        "seed": probe["seed"],
    }
    decision["decision_hash"] = _hash_decision(decision)
    if registrar:
        _registrar(raiz, decision)
    return decision


def _registrar(raiz: Path, decision: dict) -> None:
    ruta = _ruta_decision(raiz, decision["probe_id"])
    with bloqueo(raiz):
        if ruta.exists():
            existente = cargar_decision(raiz, decision["probe_id"])
            if existente != decision:
                raise EvidenciaInvalida("decision.json existente difiere de la decisión recomputada")
            return
        escribir_atomico(ruta, _json_bytes(decision))


def cargar_decision(repo_root, probe_id: str) -> dict:
    """Carga `decision.json`, valida estructura y que `decision_hash` == hash recomputado."""
    _validar_probe_id(probe_id)
    ruta = _ruta_decision(repo_root, probe_id)
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise EvidenciaInvalida(f"decision.json inexistente ({probe_id})") from None
    except (OSError, ValueError) as exc:
        raise EvidenciaInvalida(f"decision.json ilegible ({type(exc).__name__})") from None
    if not isinstance(datos, dict) or set(datos) != set(_CLAVES_DECISION):
        raise EvidenciaInvalida("decision.json: claves inesperadas")
    v = datos["contract_version"]
    if isinstance(v, bool) or v != DECISION_CONTRACT_VERSION:
        raise EvidenciaInvalida("decision.json: contract_version no soportada")
    if datos["probe_id"] != probe_id:
        raise EvidenciaInvalida("decision.json: probe_id no coincide")
    if datos["verdict"] not in _ESTADO_POR_VEREDICTO or \
            datos["candidate_status"] != _ESTADO_POR_VEREDICTO[datos["verdict"]]:
        raise EvidenciaInvalida("decision.json: verdict/candidate_status inconsistentes")
    if not isinstance(datos["decision_hash"], str) or _hash_decision(datos) != datos["decision_hash"]:
        raise EvidenciaInvalida("decision.json: decision_hash no coincide (manipulado)")
    return datos


def aplicar_decision(repo_root, probe_id: str, evals_root=None, ahora: Optional[datetime] = None) -> Candidate:
    """Único camino que transiciona la candidate: `proposed|inconclusive -> evaluated -> final`
    con evidencia `{probe_id, decision_hash}`, ambas transiciones bajo un mismo lock. Solo sobre el
    probe `completed` MÁS RECIENTE de la candidate. Idempotente para la misma decisión."""
    raiz = Path(repo_root)
    decision = decidir(raiz, probe_id, evals_root=evals_root, registrar=False)  # una sola vez
    completados = [d for d in _probe.probes_de_candidate(raiz, decision["candidate_id"])
                   if d["status"] == _probe.STATUS_COMPLETED]
    if not completados or completados[-1]["probe_id"] != probe_id:
        raise EvidenciaInvalida("existe un probe completed más reciente de la candidate: decisión obsoleta")
    _registrar(raiz, decision)  # crea decision.json o exige que el existente sea idéntico
    final = decision["candidate_status"]
    evidencia = {"probe_id": probe_id, "decision_hash": decision["decision_hash"]}
    with bloqueo(raiz):
        cand = cargar_candidate(raiz, decision["candidate_id"])

        def _ultima(c: Candidate):
            return c.status_history[-1].get("evidence")

        if cand.status == final and _ultima(cand) == evidencia:
            return cand  # idempotente
        if final == ESTADO_PROMOTABLE and not base_vigente(raiz, cand):
            raise EvidenciaInvalida("el archivo activo cambió: la candidate no puede promoverse")
        if cand.status in (ESTADO_PROPOSED, ESTADO_INCONCLUSIVE):
            cand = transicionar_sin_lock(raiz, cand.candidate_id, ESTADO_EVALUATED, evidencia, ahora)
        elif cand.status == ESTADO_EVALUATED and _ultima(cand) == evidencia:
            pass  # transición a medias de una corrida anterior: se completa
        else:
            raise EvidenciaInvalida(f"la candidate está en {cand.status!r}: no admite esta decisión")
        return transicionar_sin_lock(raiz, cand.candidate_id, final, evidencia, ahora)


def verificar_promotable(repo_root, candidate_id: str, evals_root=None) -> dict:
    """Re-deriva desde disco que la candidate es promotable. Devuelve la decisión o lanza
    `PromocionNoRespaldada`. Un `candidate.json` editado a mano no pasa."""
    raiz = Path(repo_root)
    try:
        cand = cargar_candidate(raiz, candidate_id)
    except CandidateCorrupta as exc:
        raise PromocionNoRespaldada(f"candidate no íntegra: {exc}") from None
    if cand.status != ESTADO_PROMOTABLE:
        raise PromocionNoRespaldada(f"estado {cand.status!r}, no promotable")
    hist = cand.status_history
    ev = hist[-1].get("evidence")
    if len(hist) < 3 or hist[-2]["status"] != ESTADO_EVALUATED or hist[-2].get("evidence") != ev:
        raise PromocionNoRespaldada("historial sin la transición evaluated respaldada")
    try:
        guardada = cargar_decision(raiz, ev["probe_id"])
        recomputada = decidir(raiz, ev["probe_id"], evals_root=evals_root)
    except EvidenciaInvalida as exc:
        raise PromocionNoRespaldada(f"decisión no respaldada: {exc}") from None
    if guardada["decision_hash"] != ev["decision_hash"] or guardada != recomputada:
        raise PromocionNoRespaldada("decision_hash del historial no coincide con la decisión recomputada")
    if guardada["candidate_id"] != candidate_id:
        raise PromocionNoRespaldada("la decisión pertenece a otra candidate")
    if guardada["verdict"] != VER_CANDIDATE_MEJOR:
        raise PromocionNoRespaldada(f"veredicto {guardada['verdict']!r}, no candidate_better")
    if not base_vigente(raiz, cand):
        raise PromocionNoRespaldada("el archivo activo cambió desde la creación de la candidate")
    return guardada
