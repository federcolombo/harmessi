"""Ejecución gobernada de un probe baseline-vs-candidate (v0.14 Change 2, R3-R10).

Por qué existe: para saber si una candidate mejora una superficie hay que medirla en las
MISMAS condiciones que la base. Un probe corre la misma suite, con el mismo target,
evaluador, seed y adapter, `repeats` veces para cada lado; lo único que cambia es la guía
inyectada (`GuidanceAdapter` antepone al prompt el contenido de la superficie: el activo
para baseline, `content.md` para candidate). El archivo activo NUNCA se modifica: el
manifest del lado candidate se calcula con `runmanifest.sustituir_superficie`.

Orden (fail-closed): id -> candidate/estado -> base vigente -> suite -> tamaño de guía ->
identidad (preflight) -> [bajo lock: existencia/resume -> compatibilidad -> consumo de budget
-> probe.json `running` con la política congelada] -> repeticiones -> clasificación ->
probe.json `completed`. Todo el consumo de budget ocurre ANTES de ejecutar (salvo los
reintentos, que consumen `retries`).

Identidad: el `identity_hash` de cada lado se fija en el preflight y se exige idéntico antes
y después de CADA corrida; si el archivo activo (u otra superficie) cambia, el probe termina
`inconclusive` y esa corrida no se guarda.

Reintentos: ante `ok=False` (con o sin `availability_error`) se reintenta la corrida mientras
queden `retries`. Un fallo SIN `availability_error` solo se atribuye a un lado
(`fallo_propio`) si un reintento lo repitió; si no pudo confirmarse es `fallo_no_confirmado`
y el probe es `inconclusive` (nunca se culpa a la candidate por un fallo no confirmado).

No transiciona la candidate (eso es de la decisión, Change 3) ni escribe fuera de
`.harmessi/improvement/probes/` y `.harmessi/evals/`. Sin LLM-as-judge: los scorers son los
deterministas de `harmessi_bench`. `probe.json` no guarda prompts, salidas ni rutas absolutas.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tools.ds_init.version import HARNESS_VERSION
from tools.harmessi_bench import storage
from tools.harmessi_bench.redact import redactar_texto
from tools.harmessi_bench.runmanifest import (
    campos_faltantes,
    construir_manifest,
    finalizar_manifest,
    hash_contenido,
    sustituir_superficie,
)
from tools.harmessi_bench.runner import run_scenario_set
from tools.harmessi_bench.suite import bloque_suite, load_suite_y_casos
from tools.harmessi_improve import budget as _budget
from tools.harmessi_improve.budget import (
    PresupuestoAgotado,
    PresupuestoInvalido,
    bloqueo,
    cargar_presupuesto,
    es_enlace,
    escribir_atomico,
    raiz_improvement,
    verificar_dentro_de_improvement,
)
from tools.harmessi_improve.candidate import (
    ESTADO_INCONCLUSIVE,
    ESTADO_PROPOSED,
    base_vigente,
    cargar_candidate,
    leer_contenido,
)
from tools.harmessi_improve.policy import PolicyInvalida, ProbePolicy, hash_policy
from tools.providers.core import InvocationRequest

PROBE_CONTRACT_VERSION = 1

DIR_PROBES = "probes"
NOMBRE_PROBE = "probe.json"
_RE_PROBE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")

# Tope de guía + prompt más largo (bytes UTF-8).
MAX_GUIA_BYTES = 100_000

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS = (STATUS_RUNNING, STATUS_COMPLETED)

OUTCOME_SUCCESS = "success"
OUTCOME_CANDIDATE_FAILURE = "candidate_failure"
OUTCOME_BASELINE_FAILURE = "baseline_failure"
OUTCOME_ENVIRONMENT_FAILURE = "environment_failure"
OUTCOME_INCONCLUSIVE = "inconclusive"
OUTCOMES = (OUTCOME_SUCCESS, OUTCOME_CANDIDATE_FAILURE, OUTCOME_BASELINE_FAILURE,
            OUTCOME_ENVIRONMENT_FAILURE, OUTCOME_INCONCLUSIVE)

ROL_BASELINE = "baseline"
ROL_CANDIDATE = "candidate"
_SUFIJO_ROL = {ROL_BASELINE: "base", ROL_CANDIDATE: "cand"}

RUN_OK = "ok"
RUN_FALLO_ENTORNO = "fallo_entorno"
RUN_FALLO_PROPIO = "fallo_propio"
RUN_FALLO_NO_CONFIRMADO = "fallo_no_confirmado"
_ESTADOS_RUN = (RUN_OK, RUN_FALLO_ENTORNO, RUN_FALLO_PROPIO, RUN_FALLO_NO_CONFIRMADO)
# Una repetición con estos estados en ambos lados se considera completa (se reutiliza).
_ESTADOS_REUTILIZABLES = (RUN_OK, RUN_FALLO_PROPIO)

MOTIVO_WALL_CLOCK = "wall_clock"
MOTIVO_IDENTIDAD_CAMBIO = "identidad_cambio_durante_corrida"
MOTIVO_FALLO_NO_CONFIRMADO = "fallo_no_confirmado"
# Un probe `completed` solo es reanudable si quedó inconclusive por alguno de estos motivos.
_MOTIVOS_REANUDABLES = (MOTIVO_WALL_CLOCK, MOTIVO_IDENTIDAD_CAMBIO)

# Códigos de rechazo
ESTADO_NO_PROBABLE = "ESTADO_NO_PROBABLE"
BASE_OBSOLETA = "BASE_OBSOLETA"
SUITE_INCOMPATIBLE = "SUITE_INCOMPATIBLE"
SUITE_INVALIDA = "SUITE_INVALIDA"
IDENTIDAD_INVALIDA = "IDENTIDAD_INVALIDA"
PROBE_EXISTENTE = "PROBE_EXISTENTE"
PROBE_ID_INVALIDO = "PROBE_ID_INVALIDO"
PROBE_COMPLETADO = "PROBE_COMPLETADO"
GUIA_DEMASIADO_GRANDE = "GUIA_DEMASIADO_GRANDE"
RUTA_INVALIDA = "RUTA_INVALIDA"
PROBE_PENDIENTE_DE_DECISION = "PROBE_PENDIENTE_DE_DECISION"
CRITERIOS_CAMBIADOS = "CRITERIOS_CAMBIADOS"

_CLAVES_PROBE = (
    "contract_version", "probe_id", "candidate_id", "base_surface", "baseline_surface_hash",
    "candidate_hash", "budget_version", "policy", "policy_hash", "suite", "cases_hash", "target",
    "seed", "runs", "status", "outcome", "motivos", "started_utc", "finished_utc", "sessions_utc",
    "harmessi_version",
)
_CLAVES_RUN = (
    "run_id", "role", "repetition", "identity_hash", "sha256", "estado", "attempts", "total",
    "passed", "mean_score", "mean_duration_s",
)


class ProbeRechazado(Exception):
    """Una precondición del probe no se cumple; `codigo` identifica cuál."""

    def __init__(self, codigo: str, mensaje: str = "") -> None:
        self.codigo = codigo
        self.mensaje = mensaje
        super().__init__(f"{codigo}: {mensaje}" if mensaje else codigo)


class ProbeIncompatible(Exception):
    """Un resume no es compatible con el probe persistido."""


class ProbeCorrupto(Exception):
    """`probe.json` no existe, no es íntegro o tiene un contrato no soportado."""


class GuidanceAdapter:
    """Envuelve un adapter real y antepone `guidance` al prompt de cada invocación.
    Es la ÚNICA diferencia entre baseline y candidate (R3)."""

    def __init__(self, adapter, guidance: str) -> None:
        self._adapter = adapter
        self._guidance = guidance
        self.provider_id = getattr(adapter, "provider_id", None)
        self.display_name = getattr(adapter, "display_name", None)
        self.cli_command = getattr(adapter, "cli_command", None)

    def invoke(self, request: InvocationRequest):
        prompt = f"[GUIDANCE]\n{self._guidance}\n[/GUIDANCE]\n\n{request.prompt}"
        return self._adapter.invoke(dataclasses.replace(request, prompt=prompt))

    def detect(self):
        return self._adapter.detect()


# --- Utilidades --------------------------------------------------------------------

def _reloj(ahora):
    """`ahora` puede ser None (reloj real), un datetime fijo o un callable sin args."""
    if callable(ahora):
        return ahora
    if isinstance(ahora, datetime):
        return lambda: ahora
    return lambda: datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json_bytes(datos: dict) -> bytes:
    return (json.dumps(datos, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _ruta_probe(repo_root, probe_id: str) -> Path:
    ruta = raiz_improvement(repo_root) / DIR_PROBES / probe_id / NOMBRE_PROBE
    return verificar_dentro_de_improvement(repo_root, ruta)


def _run_id(probe_id: str, rol: str, repeticion: int) -> str:
    return f"{probe_id}-{_SUFIJO_ROL[rol]}-r{repeticion}"


def _datos_target(target) -> dict:
    return {
        "provider_id": getattr(target, "provider_id", None),
        "model": redactar_texto(getattr(target, "model", None)),
        "effort": redactar_texto(getattr(target, "effort", None)),
    }


def _sha256_archivo(ruta: Path) -> Optional[str]:
    try:
        return hashlib.sha256(ruta.read_bytes()).hexdigest()
    except OSError:
        return None


def _es_entorno(resultado) -> bool:
    return bool(resultado.availability_error)


def _estado_de(resultados, intentos: int) -> str:
    """Entorno si hay `availability_error`; `fallo_propio` si hay ok=False repetido por al
    menos un reintento; `fallo_no_confirmado` si hubo ok=False sin reintento que lo confirme."""
    if any(_es_entorno(r) for r in resultados):
        return RUN_FALLO_ENTORNO
    if any(not r.ok for r in resultados):
        return RUN_FALLO_PROPIO if intentos > 1 else RUN_FALLO_NO_CONFIRMADO
    return RUN_OK


def _promedio(valores) -> float:
    valores = list(valores)
    return round(sum(valores) / len(valores), 6) if valores else 0.0


def _clasificar(runs: list):
    """`(outcome, motivos)` de R7 sobre las corridas completadas. Ambigüedad => entorno."""
    estados = {(r["role"], r["estado"]) for r in runs}
    entorno = any(e == RUN_FALLO_ENTORNO for _r, e in estados)
    base = (ROL_BASELINE, RUN_FALLO_PROPIO) in estados
    cand = (ROL_CANDIDATE, RUN_FALLO_PROPIO) in estados
    if entorno or (base and cand):
        return OUTCOME_ENVIRONMENT_FAILURE, sorted(f"{r}:{e}" for r, e in estados if e != RUN_OK)
    if any(e == RUN_FALLO_NO_CONFIRMADO for _r, e in estados):
        return OUTCOME_INCONCLUSIVE, [MOTIVO_FALLO_NO_CONFIRMADO]
    if cand:
        return OUTCOME_CANDIDATE_FAILURE, [f"{ROL_CANDIDATE}:{RUN_FALLO_PROPIO}"]
    if base:
        return OUTCOME_BASELINE_FAILURE, [f"{ROL_BASELINE}:{RUN_FALLO_PROPIO}"]
    return OUTCOME_SUCCESS, []


# --- Carga -------------------------------------------------------------------------

def _validar_probe(datos, probe_id: str) -> dict:
    if not isinstance(datos, dict) or set(datos) != set(_CLAVES_PROBE):
        raise ProbeCorrupto("probe.json: claves inesperadas")
    v = datos["contract_version"]
    if isinstance(v, bool) or v != PROBE_CONTRACT_VERSION:
        raise ProbeCorrupto("probe.json: contract_version no soportada")
    if datos["probe_id"] != probe_id:
        raise ProbeCorrupto("probe.json: probe_id no coincide")
    if datos["status"] not in STATUS:
        raise ProbeCorrupto("probe.json: status inválido")
    if datos["status"] == STATUS_COMPLETED and datos["outcome"] not in OUTCOMES:
        raise ProbeCorrupto("probe.json: outcome inválido")
    if datos["status"] == STATUS_RUNNING and datos["outcome"] is not None:
        raise ProbeCorrupto("probe.json: outcome presente en un probe running")
    for clave in ("candidate_id", "base_surface", "baseline_surface_hash", "candidate_hash",
                  "policy_hash", "cases_hash", "started_utc", "harmessi_version"):
        if not isinstance(datos[clave], str) or not datos[clave]:
            raise ProbeCorrupto(f"probe.json: {clave} inválido")
    try:
        politica = ProbePolicy.desde_dict(datos["policy"])
    except PolicyInvalida as exc:
        raise ProbeCorrupto(f"probe.json: policy inválida ({exc})") from None
    if hash_policy(politica) != datos["policy_hash"]:
        raise ProbeCorrupto("probe.json: policy_hash no coincide con la política")
    suite = datos["suite"]
    if not isinstance(suite, dict) or set(suite) != {"suite_id", "suite_version", "suite_hash"}:
        raise ProbeCorrupto("probe.json: suite inválida")
    if not isinstance(datos["target"], dict) or set(datos["target"]) != {"provider_id", "model", "effort"}:
        raise ProbeCorrupto("probe.json: target inválido")
    if isinstance(datos["budget_version"], bool) or not isinstance(datos["budget_version"], int):
        raise ProbeCorrupto("probe.json: budget_version inválido")
    if not isinstance(datos["motivos"], list) or not all(isinstance(m, str) for m in datos["motivos"]):
        raise ProbeCorrupto("probe.json: motivos inválido")
    if not isinstance(datos["sessions_utc"], list):
        raise ProbeCorrupto("probe.json: sessions_utc inválido")
    runs = datos["runs"]
    if not isinstance(runs, list):
        raise ProbeCorrupto("probe.json: runs inválido")
    for r in runs:
        if not isinstance(r, dict) or set(r) != set(_CLAVES_RUN):
            raise ProbeCorrupto("probe.json: entrada de run inválida")
        if r["role"] not in _SUFIJO_ROL or r["estado"] not in _ESTADOS_RUN:
            raise ProbeCorrupto("probe.json: rol o estado de run inválido")
        if isinstance(r["repetition"], bool) or not isinstance(r["repetition"], int) or r["repetition"] < 1:
            raise ProbeCorrupto("probe.json: repetición inválida")
        if r["run_id"] != _run_id(probe_id, r["role"], r["repetition"]):
            raise ProbeCorrupto("probe.json: run_id no coincide con rol/repetición")
    return datos


def cargar_probe(repo_root, probe_id: str) -> dict:
    """Carga `probe.json` y valida versión y estructura. `ProbeCorrupto` si falla."""
    if not isinstance(probe_id, str) or _RE_PROBE_ID.fullmatch(probe_id) is None:
        raise ProbeCorrupto(f"probe_id inválido: {probe_id!r}")
    try:
        ruta = _ruta_probe(repo_root, probe_id)
    except PresupuestoInvalido as exc:
        raise ProbeCorrupto(f"ruta de probe inválida: {exc}") from None
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ProbeCorrupto(f"probe inexistente: {probe_id}") from None
    except (OSError, ValueError) as exc:
        raise ProbeCorrupto(f"probe.json ilegible: {type(exc).__name__}") from None
    return _validar_probe(datos, probe_id)


def probes_de_candidate(repo_root, candidate_id: str, excepto: Optional[str] = None) -> list:
    """`probe.json` (dicts) de todos los probes legibles de la candidate, del más viejo al más
    reciente (por fin/inicio, luego mtime del archivo, luego id). Los ilegibles se ignoran."""
    carpeta = raiz_improvement(repo_root) / DIR_PROBES
    if not carpeta.is_dir():
        return []
    salida = []
    for p in carpeta.iterdir():
        if not p.is_dir() or p.name == excepto or _RE_PROBE_ID.fullmatch(p.name) is None:
            continue
        try:
            datos = cargar_probe(repo_root, p.name)
            mtime = (p / NOMBRE_PROBE).stat().st_mtime_ns
        except (ProbeCorrupto, OSError):
            continue
        if datos["candidate_id"] == candidate_id:
            salida.append(((datos["finished_utc"] or datos["started_utc"], mtime, p.name), datos))
    return [d for _k, d in sorted(salida, key=lambda t: t[0])]


def _tiene_decision(repo_root, probe_id: str) -> bool:
    return (raiz_improvement(repo_root) / "decisions" / probe_id / "decision.json").exists()


def _escribir_probe(repo_root, probe_id: str, datos: dict) -> None:
    escribir_atomico(_ruta_probe(repo_root, probe_id), _json_bytes(datos))


def _crear_exclusivo(ruta: Path, datos: bytes) -> None:
    """Crea `probe.json` con `O_EXCL` (nunca pisa uno existente)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(ruta), os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0))
    except FileExistsError:
        raise ProbeRechazado(PROBE_EXISTENTE, "el probe ya existe") from None
    with os.fdopen(fd, "wb") as f:
        f.write(datos)
        f.flush()
        os.fsync(f.fileno())


def _identidad_viva(construir) -> Optional[str]:
    try:
        return construir()["identity_hash"]
    except ValueError:
        return None


# --- API ---------------------------------------------------------------------------

def ejecutar_probe(repo_root, candidate_id: str, suite_path, adapter, target, policy: ProbePolicy,
                   probe_id: str, seed: Optional[int] = None, resume: bool = False,
                   evals_root=None, ahora=None) -> dict:
    """Ejecuta (o reanuda) un probe y devuelve el `probe.json` final (dict). Ver docstring
    del módulo. `ahora`: None, datetime fijo o callable que devuelve datetime (reloj inyectable)."""
    reloj = _reloj(ahora)
    raiz = Path(repo_root)
    if not isinstance(policy, ProbePolicy):
        raise PolicyInvalida("policy debe ser una ProbePolicy")
    # 1. id y rutas
    if not isinstance(probe_id, str) or _RE_PROBE_ID.fullmatch(probe_id) is None:
        raise ProbeRechazado(PROBE_ID_INVALIDO, "probe_id debe cumplir [A-Za-z0-9][A-Za-z0-9._-]{0,63}")
    evals = Path(evals_root) if evals_root is not None else raiz / ".harmessi" / "evals"
    if es_enlace(raiz / ".harmessi") or es_enlace(evals):
        raise ProbeRechazado(RUTA_INVALIDA, ".harmessi o la raíz de evals es un enlace: no permitido")
    ruta_probe = _ruta_probe(raiz, probe_id)
    # 2. candidate, estado y base vigente
    cand = cargar_candidate(raiz, candidate_id)
    if cand.status not in (ESTADO_PROPOSED, ESTADO_INCONCLUSIVE):
        raise ProbeRechazado(ESTADO_NO_PROBABLE, f"estado {cand.status!r} no admite probe")
    if not base_vigente(raiz, cand):
        raise ProbeRechazado(BASE_OBSOLETA, "el archivo activo cambió desde que se creó la candidate")
    # 3. suite
    try:
        suite, escenarios = load_suite_y_casos(Path(suite_path))
    except (OSError, ValueError) as exc:
        raise ProbeRechazado(SUITE_INVALIDA, f"suite ilegible o inválida ({type(exc).__name__})") from None
    if cand.suite_ids and suite.suite_id not in cand.suite_ids:
        raise ProbeRechazado(SUITE_INCOMPATIBLE, f"la suite {suite.suite_id!r} no está en suite_ids de la candidate")
    cases_hash = suite.suite_hash
    try:
        for rol in _SUFIJO_ROL:
            for k in range(1, policy.repeats + 1):
                storage.validar_run_id(_run_id(probe_id, rol, k))
    except ValueError as exc:
        raise ProbeRechazado(PROBE_ID_INVALIDO, str(exc)) from None
    # 4. guías: bytes leídos una vez, verificados contra los hashes de la candidate
    try:
        bytes_base = (raiz / cand.base_surface).read_bytes()
        guia_base = bytes_base.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise ProbeRechazado(IDENTIDAD_INVALIDA, "la superficie activa no es legible como UTF-8") from None
    if hash_contenido(bytes_base) != cand.base_hash:
        raise ProbeRechazado(BASE_OBSOLETA, "el contenido activo no coincide con base_hash")
    contenido_cand = leer_contenido(raiz, candidate_id)
    bytes_cand = contenido_cand.encode("utf-8")
    if hash_contenido(bytes_cand) != cand.content_hash:
        raise ProbeRechazado(IDENTIDAD_INVALIDA, "el contenido de la candidate no coincide con content_hash")
    max_prompt = max(len(e.prompt.encode("utf-8")) for e in escenarios)
    if max(len(bytes_base), len(bytes_cand)) + max_prompt > MAX_GUIA_BYTES:
        raise ProbeRechazado(GUIA_DEMASIADO_GRANDE, f"guía + prompt supera {MAX_GUIA_BYTES} bytes")
    # 5. identidad del preflight (fija para todo el probe)
    previo = construir_manifest("preflight", target, suite=suite, cases_hash=cases_hash, seed=seed,
                                repo_root=raiz)
    invalidos = campos_faltantes(previo)
    if invalidos:
        raise ProbeRechazado(IDENTIDAD_INVALIDA, f"manifest incompleto: {', '.join(invalidos)}")
    try:
        previo_cand = sustituir_superficie(previo, raiz, cand.base_surface, bytes_cand)
    except ValueError as exc:
        raise ProbeRechazado(IDENTIDAD_INVALIDA, str(exc)) from None
    identidades = {ROL_BASELINE: previo["identity_hash"], ROL_CANDIDATE: previo_cand["identity_hash"]}

    datos_target = _datos_target(target)
    politica_hash = hash_policy(policy)
    ppto = cargar_presupuesto(raiz)

    # 6. bajo lock: existencia / resume, compatibilidad, budget y probe.json `running`
    with bloqueo(raiz):
        existe = ruta_probe.exists()
        runs_previas: list = []
        probe = None
        if not resume:
            if existe:
                raise ProbeRechazado(PROBE_EXISTENTE, f"el probe {probe_id!r} ya existe: usá resume o un id nuevo")
            for rol in _SUFIJO_ROL:
                for k in range(1, policy.repeats + 1):
                    if (evals / _run_id(probe_id, rol, k) / "result.json").exists():
                        raise ProbeRechazado(PROBE_EXISTENTE, "ya existen corridas guardadas con ese probe_id")
            # Criterios congelados por candidate y anti cherry-picking (HIGH-1)
            previos = probes_de_candidate(raiz, cand.candidate_id, excepto=probe_id)
            for d in previos:
                if d["policy_hash"] != politica_hash or d["suite"] != bloque_suite(suite):
                    raise ProbeRechazado(CRITERIOS_CAMBIADOS,
                                         "la política o la suite difieren del primer probe de la candidate")
            for d in previos:
                if (d["status"] == STATUS_COMPLETED
                        and d["outcome"] not in (OUTCOME_INCONCLUSIVE, OUTCOME_ENVIRONMENT_FAILURE)
                        and not _tiene_decision(raiz, d["probe_id"])):
                    raise ProbeRechazado(PROBE_PENDIENTE_DE_DECISION,
                                         f"el probe {d['probe_id']!r} de la candidate no tiene decisión aplicada")
        else:
            if not existe:
                raise ProbeIncompatible(f"no hay un probe {probe_id!r} para reanudar")
            probe = cargar_probe(raiz, probe_id)
            if probe["status"] == STATUS_COMPLETED and not (
                    probe["outcome"] == OUTCOME_INCONCLUSIVE
                    and probe["motivos"] and set(probe["motivos"]) <= set(_MOTIVOS_REANUDABLES)):
                raise ProbeRechazado(PROBE_COMPLETADO, "el probe ya terminó con un resultado definitivo")
            esperado = {
                "candidate_id": cand.candidate_id, "base_surface": cand.base_surface,
                "policy_hash": politica_hash, "candidate_hash": cand.content_hash,
                "baseline_surface_hash": cand.base_hash, "cases_hash": cases_hash,
                "target": datos_target, "budget_version": _budget.BUDGET_VERSION,
                "suite": bloque_suite(suite), "seed": seed,
            }
            diferencias = sorted(k for k, v in esperado.items() if probe[k] != v)
            if diferencias:
                raise ProbeIncompatible(
                    f"resume incompatible para {probe_id!r}: difieren {', '.join(diferencias)}")
            for k in range(1, policy.repeats + 1):
                par = [r for r in probe["runs"] if r["repetition"] == k]
                if len(par) != 2 or not all(r["estado"] in _ESTADOS_REUTILIZABLES for r in par):
                    continue
                if any(r["identity_hash"] != identidades[r["role"]] for r in par):
                    raise ProbeIncompatible(
                        f"resume incompatible: la identidad de la repetición {k} no coincide con la actual")
                shas = [_sha256_archivo(evals / r["run_id"] / "result.json") for r in par]
                if any(s is None for s in shas):
                    continue  # corrida ausente: se re-ejecuta
                if any(s != r["sha256"] for s, r in zip(shas, par)):
                    raise ProbeIncompatible(f"resume incompatible: result.json alterado en la repetición {k}")
                runs_previas.extend(par)
            probe["runs"] = sorted(runs_previas, key=lambda r: (r["repetition"], r["role"]))

        hechas = {r["repetition"] for r in runs_previas}
        pendientes = [k for k in range(1, policy.repeats + 1) if k not in hechas]
        # Consumo de budget (todo ANTES de ejecutar)
        n_runs = 2 * len(pendientes)
        est = _budget.estado(raiz)
        instante = reloj()
        if not resume and est["probe_cycles"] + 1 > ppto.max_probe_cycles:
            raise PresupuestoAgotado("max_probe_cycles", ppto.max_probe_cycles)
        consumidos = est["runs_by_candidate"].get(cand.candidate_id, 0)
        if n_runs and consumidos + n_runs > ppto.max_runs_per_candidate:
            raise PresupuestoAgotado("max_runs_per_candidate", ppto.max_runs_per_candidate)
        if not resume:
            _budget.consumir_sin_lock(raiz, "probe_cycles", ahora=instante, presupuesto=ppto)
        if n_runs:
            _budget.consumir_sin_lock(raiz, "runs", cand.candidate_id, n_runs, instante, ppto)
        inicio_budget = _budget.estado(raiz)["started_utc"]

        # probe.json `running` con la política congelada
        if probe is None:
            probe = {
                "contract_version": PROBE_CONTRACT_VERSION,
                "probe_id": probe_id,
                "candidate_id": cand.candidate_id,
                "base_surface": cand.base_surface,
                "baseline_surface_hash": cand.base_hash,
                "candidate_hash": cand.content_hash,
                "budget_version": _budget.BUDGET_VERSION,
                "policy": policy.a_dict(),
                "policy_hash": politica_hash,
                "suite": bloque_suite(suite),
                "cases_hash": cases_hash,
                "target": datos_target,
                "seed": seed,
                "runs": [],
                "status": STATUS_RUNNING,
                "outcome": None,
                "motivos": [],
                "started_utc": _iso(reloj()),
                "finished_utc": None,
                "sessions_utc": [],
                "harmessi_version": HARNESS_VERSION,
            }
        probe["status"] = STATUS_RUNNING
        probe["outcome"] = None
        probe["motivos"] = []
        probe["finished_utc"] = None
        probe["sessions_utc"] = list(probe["sessions_utc"]) + [_iso(reloj())]
        if resume:
            _escribir_probe(raiz, probe_id, probe)
        else:
            _crear_exclusivo(ruta_probe, _json_bytes(probe))

    # 7. repeticiones
    interrumpido = None

    def ejecutar_run(rol: str, repeticion: int):
        """Devuelve `(entrada | None, motivo | None)`."""
        run_id = _run_id(probe_id, rol, repeticion)
        inicio = _iso(reloj())

        def manifiesto():
            m = construir_manifest(run_id, target, suite=suite, cases_hash=cases_hash, seed=seed,
                                   repo_root=raiz, started_utc=inicio)
            if rol == ROL_CANDIDATE:
                m = sustituir_superficie(m, raiz, cand.base_surface, bytes_cand)
            return m

        manifest_previo = None
        try:
            manifest_previo = manifiesto()
        except ValueError:
            pass
        if manifest_previo is None or manifest_previo["identity_hash"] != identidades[rol]:
            return None, MOTIVO_IDENTIDAD_CAMBIO
        envuelto = GuidanceAdapter(adapter, contenido_cand if rol == ROL_CANDIDATE else guia_base)
        intentos = 0
        motivo = None
        while True:
            intentos += 1
            resultados = run_scenario_set(escenarios, target, envuelto, run_id)
            if all(r.ok for r in resultados):
                break
            if intentos >= 2:
                break  # un solo reintento por corrida basta para confirmar; no agota el budget del otro lado
            try:
                _budget.consumir(raiz, "retries", cand.candidate_id, ahora=reloj(), presupuesto=ppto)
            except PresupuestoAgotado as exc:
                if exc.recurso == "max_wall_clock_s":
                    motivo = MOTIVO_WALL_CLOCK
                break
        if _identidad_viva(manifiesto) != identidades[rol]:
            return None, MOTIVO_IDENTIDAD_CAMBIO
        ruta = storage.save_run(run_id, resultados, target, root=evals, suite=suite,
                                cases_hash=cases_hash, run_manifest=finalizar_manifest(manifest_previo))
        entrada = {
            "run_id": run_id, "role": rol, "repetition": repeticion,
            "identity_hash": identidades[rol], "sha256": _sha256_archivo(ruta),
            "estado": _estado_de(resultados, intentos), "attempts": intentos, "total": len(resultados),
            "passed": sum(1 for r in resultados if r.ok and r.score.passed),
            "mean_score": _promedio(r.score.score for r in resultados),
            "mean_duration_s": _promedio(r.duration_s for r in resultados),
        }
        return entrada, motivo

    for k in pendientes:
        for rol in (ROL_BASELINE, ROL_CANDIDATE):
            try:
                _budget.verificar_wall_clock(inicio_budget, reloj(), ppto.max_wall_clock_s)
            except PresupuestoAgotado:
                interrumpido = MOTIVO_WALL_CLOCK
                break
            entrada, motivo = ejecutar_run(rol, k)
            if entrada is not None:
                probe["runs"].append(entrada)
                probe["runs"].sort(key=lambda r: (r["repetition"], r["role"]))
                _escribir_probe(raiz, probe_id, probe)
            if motivo is not None:
                interrumpido = motivo
                break
        if interrumpido:
            break

    # 8. clasificación y cierre
    if interrumpido:
        probe["outcome"] = OUTCOME_INCONCLUSIVE
        probe["motivos"] = [interrumpido]
    else:
        probe["outcome"], probe["motivos"] = _clasificar(probe["runs"])
    probe["status"] = STATUS_COMPLETED
    probe["finished_utc"] = _iso(reloj())
    _escribir_probe(raiz, probe_id, probe)
    return probe
