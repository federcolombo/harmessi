"""Presupuestos del ciclo de mejora (v0.14 Change 1, R10-R12).

Por qué existe: un proceso de mejora automática sin tope puede gastar candidates, ciclos
de probe y corridas sin límite. Los límites son explícitos, validados con techos duros
y SE AGOTAN de forma determinista (`PresupuestoAgotado`), nunca se recortan en silencio
(un valor sobre el techo es `PresupuestoInvalido`, no se "clampea").

El estado se persiste en `.harmessi/improvement/budget_state.json` con escritura atómica
(tmp + `os.replace`). Un estado corrupto es fail-closed: no reinicia contadores.
Solo stdlib; sin red ni subprocess.
"""
from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BUDGET_VERSION = 1

CLAVES_PRESUPUESTO = (
    "max_candidates",
    "max_probe_cycles",
    "max_runs_per_candidate",
    "max_retries",
    "max_wall_clock_s",
)

DEFAULTS = {
    "max_candidates": 3,
    "max_probe_cycles": 2,
    "max_runs_per_candidate": 6,
    "max_retries": 1,
    "max_wall_clock_s": 1800,
}

HARD_CEILING = {
    "max_candidates": 10,
    "max_probe_cycles": 5,
    "max_runs_per_candidate": 20,
    "max_retries": 3,
    "max_wall_clock_s": 7200,
}

DIR_IMPROVEMENT = (".harmessi", "improvement")
NOMBRE_BUDGET = "budget.json"
NOMBRE_ESTADO = "budget_state.json"
NOMBRE_LOCK = ".lock"

RECURSOS = ("candidates", "probe_cycles", "runs", "retries")
_RECURSOS_POR_CANDIDATE = ("runs", "retries")


class PresupuestoInvalido(ValueError):
    """Configuración o estado de presupuesto inválido (fail-closed)."""


class PresupuestoAgotado(RuntimeError):
    """Se superaría el límite de un recurso."""

    def __init__(self, recurso: str, limite) -> None:
        self.recurso = recurso
        self.limite = limite
        super().__init__(f"presupuesto agotado: {recurso} (limite {limite})")


@dataclass(frozen=True)
class ImprovementBudget:
    max_candidates: int = DEFAULTS["max_candidates"]
    max_probe_cycles: int = DEFAULTS["max_probe_cycles"]
    max_runs_per_candidate: int = DEFAULTS["max_runs_per_candidate"]
    max_retries: int = DEFAULTS["max_retries"]
    max_wall_clock_s: int = DEFAULTS["max_wall_clock_s"]

    def validar(self) -> "ImprovementBudget":
        """Devuelve self si es válido; si no lanza `PresupuestoInvalido`."""
        for campo in fields(self):
            valor = getattr(self, campo.name)
            if isinstance(valor, bool) or not isinstance(valor, int):
                raise PresupuestoInvalido(f"{campo.name}: debe ser entero (no bool)")
            if valor < 1:
                raise PresupuestoInvalido(f"{campo.name}: debe ser >= 1")
            if valor > HARD_CEILING[campo.name]:
                raise PresupuestoInvalido(
                    f"{campo.name}: {valor} supera el techo duro {HARD_CEILING[campo.name]}")
        return self


# --- Rutas y escritura -------------------------------------------------------------

def raiz_improvement(repo_root) -> Path:
    return Path(repo_root).joinpath(*DIR_IMPROVEMENT)


def es_enlace(ruta) -> bool:
    """True si `ruta` es symlink o junction (no se siguen enlaces)."""
    ruta = Path(ruta)
    try:
        if ruta.is_symlink():
            return True
        isjunction = getattr(os.path, "isjunction", None)
        return bool(isjunction and isjunction(str(ruta)))
    except (OSError, ValueError):
        return True


def verificar_dentro_de_improvement(repo_root, ruta) -> Path:
    """Exige que `ruta` quede (léxicamente) dentro de `repo_root/.harmessi/improvement`,
    que `.harmessi` e `improvement` no sean enlaces, que ningún componente existente
    intermedio lo sea y que la raíz resuelta quede dentro de `repo_root`. No resuelve el
    sufijo (el destino puede no existir todavía)."""
    raiz = raiz_improvement(repo_root)
    destino = Path(ruta)
    try:
        relativa = destino.relative_to(raiz)
    except ValueError:
        raise PresupuestoInvalido("ruta fuera de .harmessi/improvement") from None
    if ".." in relativa.parts:
        raise PresupuestoInvalido("ruta con '..' no permitida")
    repo = Path(repo_root)
    for tramo in (repo / DIR_IMPROVEMENT[0], raiz):
        if es_enlace(tramo):
            raise PresupuestoInvalido(f"{tramo.name} es un enlace: no permitido")
    actual = raiz
    for parte in relativa.parts[:-1]:
        actual = actual / parte
        if es_enlace(actual):
            raise PresupuestoInvalido("componente intermedio es un enlace")
    if raiz.exists():
        try:
            raiz.resolve().relative_to(repo.resolve())
        except ValueError:
            raise PresupuestoInvalido("la raíz de mejora resuelve fuera del repo") from None
    return destino


@contextlib.contextmanager
def bloqueo(repo_root, espera_s: float = 5.0):
    """Lock de archivo (`O_CREAT|O_EXCL`) con espera acotada. Si no se obtiene =>
    `PresupuestoAgotado("lock", espera_s)` (fail-closed). Se limpia al salir."""
    raiz = raiz_improvement(repo_root)
    verificar_dentro_de_improvement(repo_root, raiz / NOMBRE_LOCK)
    raiz.mkdir(parents=True, exist_ok=True)
    ruta = raiz / NOMBRE_LOCK
    limite = time.monotonic() + espera_s
    while True:
        try:
            fd = os.open(str(ruta), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() >= limite:
                raise PresupuestoAgotado("lock", espera_s) from None
            time.sleep(0.01)
    try:
        yield
    finally:
        try:
            os.close(fd)
        finally:
            try:
                os.unlink(str(ruta))
            except OSError:
                pass


def escribir_atomico(ruta: Path, datos: bytes) -> None:
    """Escribe `datos` en `ruta` vía archivo temporal + fsync + `os.replace`."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(ruta.parent), prefix=ruta.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(datos)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ruta)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _como_utc(dt: datetime) -> datetime:
    """Una fecha naive se trata como UTC (consistente en todo el módulo)."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _a_iso(dt: datetime) -> str:
    return _como_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parsear_iso(texto) -> datetime:
    if not isinstance(texto, str):
        raise PresupuestoInvalido("started_utc inválido")
    try:
        return datetime.strptime(texto, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise PresupuestoInvalido("started_utc inválido") from None


# --- Carga de configuración --------------------------------------------------------

def cargar_presupuesto(repo_root) -> ImprovementBudget:
    """Lee `.harmessi/improvement/budget.json` (opcional). Ausente => defaults.
    Claves desconocidas, valores inválidos o sobre el techo => `PresupuestoInvalido`."""
    ruta = raiz_improvement(repo_root) / NOMBRE_BUDGET
    if not ruta.exists():
        return ImprovementBudget().validar()
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PresupuestoInvalido(f"budget.json ilegible: {exc}") from None
    if not isinstance(datos, dict):
        raise PresupuestoInvalido("budget.json debe ser un objeto")
    desconocidas = set(datos) - set(CLAVES_PRESUPUESTO) - {"budget_version"}
    if desconocidas:
        raise PresupuestoInvalido(f"claves desconocidas: {sorted(desconocidas)}")
    if "budget_version" in datos and (
            isinstance(datos["budget_version"], bool) or datos["budget_version"] != BUDGET_VERSION):
        raise PresupuestoInvalido("budget_version no soportada")
    valores = dict(DEFAULTS)
    valores.update({k: datos[k] for k in CLAVES_PRESUPUESTO if k in datos})
    return ImprovementBudget(**valores).validar()


# --- Estado persistido -------------------------------------------------------------

def _estado_inicial(ahora: datetime) -> dict:
    return {
        "budget_version": BUDGET_VERSION,
        "started_utc": _a_iso(ahora),
        "candidates": 0,
        "probe_cycles": 0,
        "runs_by_candidate": {},
        "retries_by_candidate": {},
    }


def _entero_no_negativo(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0


def _validar_estado(datos) -> dict:
    if not isinstance(datos, dict):
        raise PresupuestoInvalido("budget_state.json corrupto: no es objeto")
    esperadas = {"budget_version", "started_utc", "candidates", "probe_cycles",
                 "runs_by_candidate", "retries_by_candidate"}
    if set(datos) != esperadas:
        raise PresupuestoInvalido("budget_state.json corrupto: claves inesperadas")
    if datos["budget_version"] != BUDGET_VERSION or isinstance(datos["budget_version"], bool):
        raise PresupuestoInvalido("budget_state.json: budget_version no soportada")
    _parsear_iso(datos["started_utc"])
    for clave in ("candidates", "probe_cycles"):
        if not _entero_no_negativo(datos[clave]):
            raise PresupuestoInvalido(f"budget_state.json corrupto: {clave}")
    for clave in ("runs_by_candidate", "retries_by_candidate"):
        mapa = datos[clave]
        if not isinstance(mapa, dict) or not all(
                isinstance(k, str) and _entero_no_negativo(v) for k, v in mapa.items()):
            raise PresupuestoInvalido(f"budget_state.json corrupto: {clave}")
    return datos


def _leer_estado(repo_root) -> Optional[dict]:
    ruta = raiz_improvement(repo_root) / NOMBRE_ESTADO
    if not ruta.exists():
        return None
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PresupuestoInvalido(f"budget_state.json corrupto: {exc}") from None
    return _validar_estado(datos)


def estado(repo_root) -> dict:
    """Estado actual de contadores (copia). Sin archivo => estado inicial sin persistir."""
    leido = _leer_estado(repo_root)
    if leido is None:
        return _estado_inicial(_ahora_utc())
    return json.loads(json.dumps(leido))


def _guardar_estado(repo_root, datos: dict) -> None:
    ruta = verificar_dentro_de_improvement(repo_root, raiz_improvement(repo_root) / NOMBRE_ESTADO)
    escribir_atomico(ruta, (json.dumps(datos, indent=2, sort_keys=True) + "\n").encode("utf-8"))


# --- Wall clock --------------------------------------------------------------------

def verificar_wall_clock(started_utc, ahora, limite_s: int) -> None:
    """Pura. Lanza `PresupuestoAgotado("max_wall_clock_s", limite_s)` si transcurrió
    más de `limite_s` segundos entre `started_utc` y `ahora` (str ISO o datetime)."""
    inicio = _parsear_iso(started_utc) if isinstance(started_utc, str) else started_utc
    if not isinstance(inicio, datetime) or not isinstance(ahora, datetime):
        raise PresupuestoInvalido("wall clock: fechas inválidas")
    inicio, ahora = _como_utc(inicio), _como_utc(ahora)
    if (ahora - inicio).total_seconds() > limite_s:
        raise PresupuestoAgotado("max_wall_clock_s", limite_s)


# --- Consumo -----------------------------------------------------------------------

def consumir(repo_root, recurso: str, candidate_id: Optional[str] = None, n: int = 1,
             ahora: Optional[datetime] = None,
             presupuesto: Optional[ImprovementBudget] = None) -> dict:
    """Consume `n` unidades de `recurso` bajo lock (lectura-modificación-escritura
    serializada). Ver `consumir_sin_lock`."""
    with bloqueo(repo_root):
        return consumir_sin_lock(repo_root, recurso, candidate_id, n, ahora, presupuesto)


def devolver_candidate(repo_root) -> None:
    """Revierte un consumo de `candidates` (rollback tras fallo de escritura). Sin lock:
    el llamador ya lo tiene."""
    datos = _leer_estado(repo_root)
    if datos is not None and datos["candidates"] > 0:
        datos["candidates"] -= 1
        _guardar_estado(repo_root, datos)


def consumir_sin_lock(repo_root, recurso: str, candidate_id: Optional[str] = None, n: int = 1,
                      ahora: Optional[datetime] = None,
                      presupuesto: Optional[ImprovementBudget] = None) -> dict:
    """Consume `n` unidades de `recurso`. Verifica ANTES de incrementar; si superaría el
    límite lanza `PresupuestoAgotado` sin modificar el estado. Persiste de forma atómica
    y devuelve el estado resultante. El llamador debe tener el lock."""
    if recurso not in RECURSOS:
        raise PresupuestoInvalido(f"recurso desconocido: {recurso!r}")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise PresupuestoInvalido("n debe ser entero >= 1")
    if recurso in _RECURSOS_POR_CANDIDATE:
        if not isinstance(candidate_id, str) or not candidate_id:
            raise PresupuestoInvalido(f"{recurso} requiere candidate_id")
    ppto = (presupuesto or cargar_presupuesto(repo_root)).validar()
    ahora = ahora or _ahora_utc()
    datos = _leer_estado(repo_root)
    if datos is None:
        datos = _estado_inicial(ahora)

    verificar_wall_clock(datos["started_utc"], ahora, ppto.max_wall_clock_s)

    if recurso == "candidates":
        actual, limite, clave = datos["candidates"], ppto.max_candidates, "max_candidates"
    elif recurso == "probe_cycles":
        actual, limite, clave = datos["probe_cycles"], ppto.max_probe_cycles, "max_probe_cycles"
    elif recurso == "runs":
        actual = datos["runs_by_candidate"].get(candidate_id, 0)
        limite, clave = ppto.max_runs_per_candidate, "max_runs_per_candidate"
    else:
        actual = datos["retries_by_candidate"].get(candidate_id, 0)
        limite, clave = ppto.max_retries, "max_retries"
    if actual + n > limite:
        raise PresupuestoAgotado(clave, limite)

    if recurso == "candidates":
        datos["candidates"] = actual + n
    elif recurso == "probe_cycles":
        datos["probe_cycles"] = actual + n
    elif recurso == "runs":
        datos["runs_by_candidate"][candidate_id] = actual + n
    else:
        datos["retries_by_candidate"][candidate_id] = actual + n
    _guardar_estado(repo_root, datos)
    return datos
