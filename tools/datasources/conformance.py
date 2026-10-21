"""Conformance de observers de fuente (v0.13 Change 3,
`20261021-v013-provider-adapter-conformance`, R7-R11).

Suite reutilizable para que el autor de un observer (Harmessi o un proyecto)
sepa si cumple el contrato `factory(source_id, options)` ->
`.capabilities()` / `.observe(request)`. Se instala en los proyectos.

Solo stdlib (`ast`, `copy`, `inspect`, `json`, `dataclasses`, `typing`) +
`core` y `scan` relativos. No importa `subprocess`, red ni providers, y no
instala nada. Las excepciones del observer se capturan por chequeo (un
chequeo fallido, nunca un traceback); los detalles del reporte no reproducen
valores ni rutas del observer, solo el tipo/codigo del error.

`evidencia` ("fixture" | "real") la declara quien llama y el reporte la
propaga: la suite no puede saber si el observer corre sobre datos reales.

Limites honestos: el chequeo de secretos/rutas es heuristico (`scan`); el
chequeo "no instala nada" es estatico (AST del archivo del factory: imports en
cualquier nivel salvo bajo `TYPE_CHECKING`, `__import__`/`import_module` con
constante prohibida, `os.system`/`os.popen`/`os.spawn*`/`os.exec*`) y NO es
exhaustivo: no sigue modulos hermanos ni nombres construidos dinamicamente.

Un chequeo no evaluado (p. ej. `error_acotado` sin `options_error`) hace que
`ok` sea False y `completo` False, salvo `permitir_no_evaluados=True`.

Errores acotados (E/I): `SourceError`, `RuntimeError`, `ValueError`,
`FileNotFoundError`, `OSError`. Cualquier otra clase (`KeyError`, `TypeError`,
`AttributeError`, `AssertionError`, ...) es un chequeo fallido que nombra el
tipo.

Uso tipico:

    from tools.datasources import conformance
    reporte = conformance.verificar_observer(
        mi_factory, source_id="mi-fuente", options={...},
        request={"source_id": "mi-fuente"}, evidencia="real",
        options_error={...},  # opcional: options que deben provocar un error
    )
    print(reporte.to_json())
"""
from __future__ import annotations

import ast
import copy
import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from . import core
from . import scan

EVIDENCIAS = ("fixture", "real")

# Raices de import que indican instalacion/ejecucion de procesos.
IMPORTS_PROHIBIDOS = (
    "subprocess", "pip", "ensurepip", "pipx", "conda", "uv", "poetry", "setuptools", "runpy", "ctypes",
)

# Excepciones documentadas como "errores acotados" de un observer.
ERRORES_ACOTADOS = (core.SourceError, RuntimeError, ValueError, FileNotFoundError, OSError)

_SOURCE_ID_INVALIDO = "ID invalido con espacios"


@dataclass
class CheckResult:
    nombre: str
    ok: bool
    detalle: str

    def to_dict(self) -> dict:
        return {"nombre": self.nombre, "ok": bool(self.ok), "detalle": self.detalle}


@dataclass
class ConformanceReport:
    source_id: str
    evidencia: str
    chequeos: List[CheckResult] = field(default_factory=list)
    no_evaluados: List[str] = field(default_factory=list)
    permitir_no_evaluados: bool = False

    @property
    def completo(self) -> bool:
        """True si no quedo ningun chequeo sin evaluar."""
        return not self.no_evaluados

    @property
    def ok(self) -> bool:
        if not self.chequeos or not all(c.ok for c in self.chequeos):
            return False
        return self.completo or self.permitir_no_evaluados

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "evidencia": self.evidencia,
            "ok": self.ok,
            "completo": self.completo,
            "chequeos": [c.to_dict() for c in self.chequeos],
            "no_evaluados": list(self.no_evaluados),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, indent=2)


def _describir_excepcion(exc: BaseException) -> str:
    """Solo tipo (y codigo si es `SourceError`): nunca el mensaje, que puede
    contener rutas o valores del observer."""
    codigo = getattr(exc, "code", None)
    if isinstance(exc, core.SourceError) and isinstance(codigo, str):
        return f"{type(exc).__name__}({codigo})"
    return type(exc).__name__


def _pedido_como_dict(request: Any, source_id: str) -> dict:
    if request is None:
        base = {"source_id": source_id}
    elif hasattr(request, "to_dict"):
        base = request.to_dict()
    else:
        base = dict(request)
    base.setdefault("source_id", source_id)
    return core.ObservationRequest.from_dict(base).to_dict()


def _a_dict(resultado: Any) -> Optional[dict]:
    if isinstance(resultado, core.SourceObservation):
        return resultado.to_dict()
    if isinstance(resultado, dict):
        return resultado
    return None


def _es_type_checking(prueba: ast.AST) -> bool:
    return (isinstance(prueba, ast.Name) and prueba.id == "TYPE_CHECKING") or (
        isinstance(prueba, ast.Attribute) and prueba.attr == "TYPE_CHECKING"
    )


def _hallazgos_instalacion(arbol: ast.AST) -> List[str]:
    """Hallazgos de instalacion/ejecucion de procesos en TODO el archivo
    (cualquier nivel, incluidas funciones y `try`), salvo bajo
    `if TYPE_CHECKING:`. No exhaustivo: no sigue modulos hermanos."""
    hallazgos: set = set()

    def prohibido(nombre: Any) -> bool:
        return isinstance(nombre, str) and nombre.split(".")[0] in IMPORTS_PROHIBIDOS

    def visitar(nodo: ast.AST) -> None:
        if isinstance(nodo, ast.If) and _es_type_checking(nodo.test):
            for hijo in nodo.orelse:
                visitar(hijo)
            return
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                if prohibido(alias.name):
                    hallazgos.add(f"import {alias.name}")
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module and not nodo.level and prohibido(nodo.module):
                hallazgos.add(f"from {nodo.module} import ...")
        elif isinstance(nodo, ast.Call):
            funcion = nodo.func
            nombre = funcion.id if isinstance(funcion, ast.Name) else getattr(funcion, "attr", None)
            if nombre in ("__import__", "import_module") and nodo.args:
                primero = nodo.args[0]
                if isinstance(primero, ast.Constant) and prohibido(primero.value):
                    hallazgos.add(f"{nombre}({primero.value})")
            if (
                isinstance(funcion, ast.Attribute)
                and isinstance(funcion.value, ast.Name)
                and funcion.value.id == "os"
                and (funcion.attr in ("system", "popen") or funcion.attr.startswith(("spawn", "exec")))
            ):
                hallazgos.add(f"os.{funcion.attr}")
        for hijo in ast.iter_child_nodes(nodo):
            visitar(hijo)

    visitar(arbol)
    return sorted(hallazgos)


def _archivo_fuente(factory: Callable) -> Optional[str]:
    try:
        ruta = inspect.getsourcefile(factory)
        if ruta:
            return ruta
    except TypeError:
        pass
    codigo = getattr(factory, "__code__", None)
    return getattr(codigo, "co_filename", None)


class _Contexto:
    """Estado compartido entre chequeos (observer construido, observaciones)."""

    def __init__(self) -> None:
        self.observer: Any = None
        self.capacidades: Optional[dict] = None
        self.obs_dict: Optional[dict] = None
        self.observacion: Optional[core.SourceObservation] = None


def verificar_observer(
    factory: Callable,
    *,
    source_id: str,
    options: dict,
    request: Any = None,
    evidencia: str = "fixture",
    options_error: Optional[dict] = None,
    permitir_no_evaluados: bool = False,
) -> ConformanceReport:
    """Corre los chequeos R8 (a)-(i) sobre `factory`. Nunca lanza por un
    observer defectuoso: lo registra como chequeo fallido (R9).

    `options_error` (opcional): `options` que deben provocar un error del
    observer (p. ej. una ruta inexistente); sin ellas el chequeo (i) queda en
    `no_evaluados` y el reporte NO es `ok` (ni `completo`) salvo que se pase
    `permitir_no_evaluados=True`.
    """
    if evidencia not in EVIDENCIAS:
        raise ValueError(f"evidencia debe ser una de {EVIDENCIAS}, se recibio {evidencia!r}")

    reporte = ConformanceReport(
        source_id=str(source_id), evidencia=evidencia, permitir_no_evaluados=bool(permitir_no_evaluados)
    )
    ctx = _Contexto()

    try:
        pedido = _pedido_como_dict(request, source_id)
        error_pedido = None
    except Exception as exc:  # noqa: BLE001
        pedido = {"source_id": source_id}
        error_pedido = _describir_excepcion(exc)

    def correr(nombre: str, fn: Callable[[], str]) -> bool:
        try:
            detalle = fn()
            reporte.chequeos.append(CheckResult(nombre, True, detalle))
            return True
        except AssertionError as exc:
            reporte.chequeos.append(CheckResult(nombre, False, str(exc) or "chequeo fallido"))
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - R9/L2: KeyboardInterrupt se propaga
            reporte.chequeos.append(CheckResult(nombre, False, f"excepcion {_describir_excepcion(exc)}"))
        return False

    def requiere(condicion: bool, mensaje: str) -> None:
        if not condicion:
            raise AssertionError(mensaje)

    # (a) forma
    def chequeo_forma() -> str:
        requiere(error_pedido is None, f"el request de prueba es invalido ({error_pedido})")
        ctx.observer = factory(source_id, copy.deepcopy(options))
        requiere(callable(getattr(ctx.observer, "capabilities", None)), "falta capabilities() invocable")
        requiere(callable(getattr(ctx.observer, "observe", None)), "falta observe() invocable")
        return "factory(source_id, options) devuelve objeto con capabilities() y observe()"

    forma_ok = correr("forma_factory", chequeo_forma)

    # (b) capacidades
    def chequeo_capacidades() -> str:
        requiere(forma_ok, "no evaluable: fallo la forma del factory")
        bruto = ctx.observer.capabilities()
        caps = bruto.to_dict() if isinstance(bruto, core.SourceCapabilities) else bruto
        core.validate_capabilities(caps)
        ctx.capacidades = caps
        return "capabilities() valida (validate_capabilities)"

    caps_ok = correr("capacidades_validas", chequeo_capacidades)

    # (c) observacion
    def chequeo_observacion() -> str:
        requiere(forma_ok, "no evaluable: fallo la forma del factory")
        resultado = ctx.observer.observe(copy.deepcopy(pedido))
        obs_dict = _a_dict(resultado)
        requiere(obs_dict is not None, f"observe() devolvio {type(resultado).__name__}, se esperaba dict")
        observacion = core.SourceObservation.from_dict(obs_dict)
        requiere(observacion.source_id == source_id, "source_id de la observacion distinto del pedido")
        requiere(
            observacion.provenance.source_id == source_id, "provenance.source_id distinto del pedido"
        )
        requiere(observacion.schema_version == core.SCHEMA_VERSION, "schema_version inesperado")
        ctx.obs_dict = obs_dict
        ctx.observacion = observacion
        return "observe() devuelve un dict que reconstruye SourceObservation con source_id y schema_version correctos"

    obs_ok = correr("observacion_valida", chequeo_observacion)

    # (d) facetas contenidas en las declaradas
    def chequeo_facetas() -> str:
        requiere(obs_ok and caps_ok, "no evaluable: faltan capacidades u observacion validas")
        declaradas = set(ctx.capacidades.get("facets", {}))
        devueltas = {k for k in ctx.observacion.dataset if k != "sampling"}
        for campo in ctx.observacion.fields:
            devueltas |= set(campo.facets)
        sobrantes = sorted(devueltas - declaradas)
        requiere(not sobrantes, f"facetas devueltas no declaradas: {sobrantes}")
        return "las facetas devueltas estan contenidas en las declaradas"

    correr("facetas_no_fabricadas", chequeo_facetas)

    # (e) source_id invalido rechazado
    def chequeo_id_invalido() -> str:
        requiere(forma_ok, "no evaluable: fallo la forma del factory")
        try:
            observador = factory(_SOURCE_ID_INVALIDO, copy.deepcopy(options))
            resultado = observador.observe({"source_id": _SOURCE_ID_INVALIDO})
        except Exception as exc:  # noqa: BLE001 - se espera un error acotado
            if not isinstance(exc, ERRORES_ACOTADOS):
                raise AssertionError(
                    f"source_id invalido rechazado con excepcion no acotada {_describir_excepcion(exc)}"
                )
            return f"source_id invalido rechazado con {_describir_excepcion(exc)}"
        raise AssertionError(
            f"un source_id invalido no fue rechazado (observe() devolvio {type(resultado).__name__})"
        )

    correr("source_id_invalido_rechazado", chequeo_id_invalido)

    # (f) sin secretos ni rutas absolutas
    def chequeo_fuga() -> str:
        requiere(obs_ok, "no evaluable: no hay observacion valida")
        json.dumps(ctx.obs_dict, sort_keys=True, ensure_ascii=False, allow_nan=False)
        hallazgos = scan.scan_secrets(ctx.obs_dict) + scan.scan_locators(ctx.obs_dict)
        resumen = sorted({f"{codigo}@{puntero}" for codigo, puntero, _motivo in hallazgos})
        requiere(not hallazgos, f"la observacion contiene secretos o localizadores fisicos: {resumen}")
        return "sin patrones de secreto ni rutas absolutas (heuristico)"

    correr("sin_fuga_secretos_rutas", chequeo_fuga)

    # (g) reproducibilidad
    def chequeo_reproducible() -> str:
        requiere(obs_ok, "no evaluable: no hay observacion valida")
        segunda = _a_dict(ctx.observer.observe(copy.deepcopy(pedido)))
        requiere(segunda is not None, "la segunda observe() no devolvio dict")
        hash_1 = ctx.observacion.content_sha256()
        hash_2 = core.SourceObservation.from_dict(segunda).content_sha256()
        requiere(hash_1 == hash_2, "dos observaciones consecutivas difieren en content_sha256")
        return "content_sha256 identico en dos observaciones consecutivas"

    correr("reproducibilidad", chequeo_reproducible)

    # (h) sin instalacion automatica (AST)
    def chequeo_sin_instalacion() -> str:
        ruta = _archivo_fuente(factory)
        requiere(bool(ruta), "no se pudo localizar el codigo fuente del factory")
        with open(ruta, "rb") as fh:
            arbol = ast.parse(fh.read(), filename=str(ruta))
        prohibidos = _hallazgos_instalacion(arbol)
        requiere(not prohibidos, f"el modulo instala o lanza procesos: {prohibidos}")
        return "sin imports de subprocess/instaladores ni os.system/popen/spawn (AST, no exhaustivo)"

    correr("sin_instalacion_automatica", chequeo_sin_instalacion)

    # (i) error acotado, no observacion parcial silenciosa
    if options_error is None:
        reporte.no_evaluados.append("error_acotado")
    else:

        def chequeo_error() -> str:
            try:
                observador = factory(source_id, copy.deepcopy(options_error))
                resultado = observador.observe(copy.deepcopy(pedido))
            except Exception as exc:  # noqa: BLE001 - se espera una excepcion acotada
                if not isinstance(exc, ERRORES_ACOTADOS):
                    raise AssertionError(f"el error se manifiesta como excepcion no acotada {_describir_excepcion(exc)}")
                return f"el error se manifiesta como excepcion acotada {_describir_excepcion(exc)}"
            raise AssertionError(
                f"con options_error el observer devolvio {type(resultado).__name__} en vez de fallar"
            )

        correr("error_acotado", chequeo_error)

    return reporte
