"""Suites de evaluación (v0.13 Change 1, `eval-benchmark-foundation`).

Una suite es un manifest JSON (`suite_contract_version` = 1) que apunta a un
archivo de casos y declara la lista exacta de `case_ids`. El `suite_hash` es el
sha256 del contenido canónico de los casos: reproducible entre sistemas
operativos (no depende de finales de línea, orden de archivo ni rutas).

Puro stdlib salvo `scenarios`/`core`: sin providers, `subprocess` ni red.
No hay leaderboard ni servicio: solo un resumen determinista por corrida.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Tuple

from tools.harmessi_bench.core import CASE_CONTRACT_VERSION, Scenario
from tools.harmessi_bench.scenarios import load_scenarios_con_version

SUITE_CONTRACT_VERSION = 1

_CAMPOS_REQUERIDOS = ("suite_contract_version", "suite_id", "suite_version", "cases_file", "case_ids")


@dataclass
class Suite:
    """Identidad de una suite ya validada. `suite_hash` lo calcula el código
    a partir del contenido de los casos (nunca se declara en el manifest)."""

    suite_id: str
    suite_version: int
    case_ids: List[str]
    suite_hash: str
    case_contract_version: int
    description: str = ""


def _es_entero_puro(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def calcular_suite_hash(
    escenarios: List[Scenario], case_contract_version: int = CASE_CONTRACT_VERSION
) -> str:
    """sha256 hex de la serialización JSON canónica (claves ordenadas,
    `ensure_ascii`) de la lista, ordenada por id, de
    `{scenario_id, prompt, expected, case_contract_version, fixtures,
    surface_under_test}`. Independiente del orden de los casos en el archivo."""
    ordenados = sorted(escenarios, key=lambda escenario: escenario.scenario_id)
    canonico = [
        {
            "scenario_id": escenario.scenario_id,
            "prompt": escenario.prompt,
            "expected": escenario.expected,
            "case_contract_version": case_contract_version,
            "fixtures": escenario.fixtures,
            "surface_under_test": escenario.surface_under_test,
        }
        for escenario in ordenados
    ]
    texto = json.dumps(canonico, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def calcular_cases_hash(
    escenarios: List[Scenario], case_contract_version: int = CASE_CONTRACT_VERSION
) -> str:
    """Hash canónico de los escenarios cargados (mismo cálculo que
    `suite_hash`). Se persiste siempre en `result.json` como `cases_hash`,
    también para corridas con `--scenarios` sin suite."""
    return calcular_suite_hash(escenarios, case_contract_version)


def _resolver_cases_file(manifest_dir: Path, cases_file) -> Path:
    """Valida `cases_file` (relativo, sin `..`, sin separadores de Windows que
    escapen, dentro del directorio del manifest) y devuelve la ruta resuelta."""
    if not isinstance(cases_file, str) or not cases_file.strip():
        raise ValueError("cases_file debe ser un string no vacío")
    normalizado = cases_file.replace("\\", "/")
    if normalizado.startswith("/") or ":" in normalizado:
        raise ValueError(f"cases_file debe ser relativo al manifest, no absoluto: {cases_file!r}")
    partes = PurePosixPath(normalizado).parts
    if ".." in partes:
        raise ValueError(f"cases_file no puede contener '..': {cases_file!r}")
    base = manifest_dir.resolve()
    destino = (base / normalizado).resolve()
    try:
        destino.relative_to(base)
    except ValueError:
        raise ValueError(
            f"cases_file escapa del directorio de la suite: {cases_file!r}"
        ) from None
    if not destino.is_file():
        raise ValueError(f"cases_file no existe dentro del directorio de la suite: {cases_file!r}")
    return destino


def load_suite_y_casos(path: Path) -> Tuple[Suite, List[Scenario]]:
    """Valida el manifest y devuelve `(Suite, escenarios)`. Fail-closed:
    `ValueError` ante campo faltante, versión desconocida, `case_ids`
    vacío/duplicado, `cases_file` fuera del directorio o `case_ids` distinto
    de los ids del archivo de casos. `FileNotFoundError` si el manifest no
    existe."""
    ruta = Path(path)
    contenido = json.loads(ruta.read_text(encoding="utf-8-sig"))
    if not isinstance(contenido, dict):
        raise ValueError(f"{ruta.name}: el manifest de suite debe ser un objeto JSON")

    faltantes = [campo for campo in _CAMPOS_REQUERIDOS if campo not in contenido]
    if faltantes:
        raise ValueError(f"{ruta.name}: faltan campos requeridos en el manifest: {faltantes!r}")

    desconocidas = sorted(set(contenido) - set(_CAMPOS_REQUERIDOS) - {"description"})
    if desconocidas:
        raise ValueError(
            f"{ruta.name}: claves desconocidas en el manifest: {desconocidas!r} "
            "(el suite_hash lo calcula el código, no se declara)"
        )

    version_contrato = contenido["suite_contract_version"]
    if not _es_entero_puro(version_contrato) or version_contrato != SUITE_CONTRACT_VERSION:
        raise ValueError(
            f"{ruta.name}: suite_contract_version={version_contrato!r} desconocida "
            f"(soportada: {SUITE_CONTRACT_VERSION})"
        )

    suite_id = contenido["suite_id"]
    if not isinstance(suite_id, str) or not suite_id.strip():
        raise ValueError(f"{ruta.name}: suite_id debe ser un string no vacío")

    suite_version = contenido["suite_version"]
    if not _es_entero_puro(suite_version) or suite_version < 1:
        raise ValueError(f"{ruta.name}: suite_version debe ser un entero >= 1, no {suite_version!r}")

    descripcion = contenido.get("description", "")
    if not isinstance(descripcion, str):
        raise ValueError(f"{ruta.name}: description debe ser un string")

    case_ids = contenido["case_ids"]
    if not isinstance(case_ids, list) or not case_ids:
        raise ValueError(f"{ruta.name}: case_ids debe ser una lista no vacía")
    if not all(isinstance(identificador, str) and identificador for identificador in case_ids):
        raise ValueError(f"{ruta.name}: case_ids debe contener solo strings no vacíos")
    duplicados = sorted({i for i in case_ids if case_ids.count(i) > 1})
    if duplicados:
        raise ValueError(f"{ruta.name}: case_ids con duplicados: {duplicados!r}")

    ruta_casos = _resolver_cases_file(ruta.parent, contenido["cases_file"])
    version_casos, escenarios = load_scenarios_con_version(ruta_casos)

    ids_archivo = {escenario.scenario_id for escenario in escenarios}
    ids_manifest = set(case_ids)
    if ids_archivo != ids_manifest:
        faltan_en_archivo = sorted(ids_manifest - ids_archivo)
        sobran_en_archivo = sorted(ids_archivo - ids_manifest)
        raise ValueError(
            f"{ruta.name}: case_ids no coincide con el archivo de casos "
            f"(en el manifest y no en el archivo: {faltan_en_archivo!r}; "
            f"en el archivo y no en el manifest: {sobran_en_archivo!r})"
        )

    suite = Suite(
        suite_id=suite_id,
        suite_version=suite_version,
        case_ids=list(case_ids),
        suite_hash=calcular_suite_hash(escenarios, version_casos),
        case_contract_version=version_casos,
        description=descripcion,
    )
    return suite, escenarios


def load_suite(path: Path) -> Suite:
    """Valida el manifest de suite y devuelve su `Suite` (ver
    `load_suite_y_casos`)."""
    return load_suite_y_casos(path)[0]


def bloque_suite(suite) -> Optional[dict]:
    """Bloque `suite` que se persiste en `result.json`:
    `{suite_id, suite_version, suite_hash}`. Acepta `Suite`, un dict con esas
    claves o `None`."""
    if suite is None:
        return None
    if isinstance(suite, dict):
        return {
            "suite_id": suite.get("suite_id"),
            "suite_version": suite.get("suite_version"),
            "suite_hash": suite.get("suite_hash"),
        }
    return {
        "suite_id": suite.suite_id,
        "suite_version": suite.suite_version,
        "suite_hash": suite.suite_hash,
    }


def _campo(resultado, nombre, default=None):
    """Lee un campo de un `EvalResult` o de un dict cargado con `load_run`."""
    if isinstance(resultado, dict):
        return resultado.get(nombre, default)
    return getattr(resultado, nombre, default)


def _clasificar(resultado) -> str:
    """`no_disponible` si la invocación no fue ok o hay `availability_error`;
    si no, `paso`/`fallo` según `score.passed`."""
    ok = _campo(resultado, "ok", True)
    if ok is False or _campo(resultado, "availability_error"):
        return "no_disponible"
    score = _campo(resultado, "score")
    passed = score.get("passed") if isinstance(score, dict) else getattr(score, "passed", False)
    return "paso" if passed else "fallo"


def resumir(resultados: list, suite=None, categorias: Optional[Dict[str, str]] = None) -> dict:
    """Resumen determinista de una corrida. `resultados` son `EvalResult` o
    dicts de `load_run`; `categorias` (opcional) mapea `scenario_id` a su
    categoría (`EvalResult` no la guarda). Los no disponibles no cuentan como
    fallos de calidad. Sin leaderboard."""
    categorias = categorias or {}
    resumen = {
        "total": 0,
        "pasaron": 0,
        "fallaron": 0,
        "no_disponibles": 0,
        "por_categoria": {},
        "suite": bloque_suite(suite),
    }
    claves = {"paso": "pasaron", "fallo": "fallaron", "no_disponible": "no_disponibles"}
    por_categoria: Dict[str, Dict[str, int]] = {}
    for resultado in resultados:
        clave = claves[_clasificar(resultado)]
        categoria = categorias.get(_campo(resultado, "scenario_id"), "") or "sin-categoria"
        cuenta = por_categoria.setdefault(
            categoria, {"total": 0, "pasaron": 0, "fallaron": 0, "no_disponibles": 0}
        )
        cuenta["total"] += 1
        cuenta[clave] += 1
        resumen["total"] += 1
        resumen[clave] += 1
    resumen["por_categoria"] = {categoria: por_categoria[categoria] for categoria in sorted(por_categoria)}
    return resumen


def render_resumen(resumen: dict) -> str:
    """Texto humano estable (mismas entradas => mismo texto) del dict de
    `resumir`."""
    lineas = []
    suite = resumen.get("suite")
    if suite:
        lineas.append(f"suite: {suite['suite_id']} v{suite['suite_version']} ({suite['suite_hash']})")
    else:
        lineas.append("suite: (sin suite declarada)")
    lineas.append(
        f"total={resumen['total']} pasaron={resumen['pasaron']} "
        f"fallaron={resumen['fallaron']} no_disponibles={resumen['no_disponibles']}"
    )
    for categoria, cuenta in resumen.get("por_categoria", {}).items():
        lineas.append(
            f"  {categoria}: {cuenta['pasaron']}/{cuenta['total']} pasaron "
            f"(fallaron={cuenta['fallaron']}, no_disponibles={cuenta['no_disponibles']})"
        )
    return "\n".join(lineas)
