"""Tests de `tools.datasources.file_observer` (R28)."""
from __future__ import annotations

import ast
import csv
import json
import os
import tempfile
from pathlib import Path

import pytest

ds_profile = pytest.importorskip("ds_profile", reason="ds_profile no instalado en este entorno de tests")

from tools.datasources import file_observer
from tools.datasources import profile_bridge as pb
from ds_profile import report as ds_report


def _crear_csv(ruta: Path) -> None:
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "nombre", "monto"])
        w.writerow(["1", "ana", "10.5"])
        w.writerow(["2", "beto", "20.0"])
        w.writerow(["3", "", "30.25"])


def _crear_repo(tmp_path: Path, subdir: str = "data") -> Path:
    (tmp_path / subdir).mkdir(parents=True, exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# R1/R28 -- import perezoso: 'ds_profile' no aparece a nivel de módulo.
# ---------------------------------------------------------------------------


def test_ds_profile_no_se_importa_a_nivel_de_modulo():
    ruta = os.path.join(os.path.dirname(__file__), "..", "file_observer.py")
    with open(ruta, "r", encoding="utf-8") as f:
        arbol = ast.parse(f.read(), filename="file_observer.py")

    nombres_top_level = set()
    for nodo in arbol.body:  # solo nivel de módulo, no dentro de funciones
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                nombres_top_level.add(alias.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module is not None:
                nombres_top_level.add(nodo.module.split(".")[0])

    assert "ds_profile" not in nombres_top_level


def test_ds_profile_si_se_importa_dentro_de_alguna_funcion():
    ruta = os.path.join(os.path.dirname(__file__), "..", "file_observer.py")
    with open(ruta, "r", encoding="utf-8") as f:
        arbol = ast.parse(f.read(), filename="file_observer.py")

    encontrado = False
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            if isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.module.split(".")[0] == "ds_profile":
                encontrado = True
            if isinstance(nodo, ast.Import) and any(a.name.split(".")[0] == "ds_profile" for a in nodo.names):
                encontrado = True
    assert encontrado


# ---------------------------------------------------------------------------
# capabilities()
# ---------------------------------------------------------------------------


def test_capabilities_no_incluye_snapshot():
    obs = file_observer.factory("customers", {"path": "data/x.csv"})
    caps = obs.capabilities()
    assert "snapshot" not in caps["facets"]
    assert set(caps["facets"]) == {
        "schema", "row_count", "fingerprint",
        "null_count", "distinct_count", "value_distribution", "value_range", "time_range",
    }
    assert caps["operations"] == ["read"]


# ---------------------------------------------------------------------------
# observe() -- coincide con profile_bridge sobre el mismo archivo
# ---------------------------------------------------------------------------


def test_observe_coincide_con_profile_bridge_directo(tmp_path):
    repo_root = _crear_repo(tmp_path)
    ruta_csv_relativa = "data/customers.csv"
    _crear_csv(repo_root / ruta_csv_relativa)

    obs = file_observer.factory_with_repo_root(repo_root)("customers", {"path": ruta_csv_relativa, "seed": 1})
    resultado = obs.observe({"facets": ["schema", "row_count"], "exactness": "any"})

    with tempfile.TemporaryDirectory() as out_dir:
        directo = ds_report.generar_perfil(
            ruta_input=repo_root / ruta_csv_relativa,
            output_dir=Path(out_dir),
            incluir_markdown=False,
            seed=1,
        )
    esperado = pb.profile_to_observation(directo["perfil"], "customers").to_dict()

    # provenance difiere a propósito (el observer la sobreescribe con datos
    # reales); se compara todo lo demás.
    resultado_sin_prov = dict(resultado)
    esperado_sin_prov = dict(esperado)
    resultado_sin_prov.pop("provenance")
    esperado_sin_prov.pop("provenance")
    assert resultado_sin_prov == esperado_sin_prov

    assert resultado["provenance"]["observer_id"] == "tools.datasources.file_observer:factory"
    assert resultado["provenance"]["source_kind"] == "file"


def test_ruta_nunca_aparece_en_el_resultado(tmp_path):
    repo_root = _crear_repo(tmp_path)
    ruta_csv_relativa = "data/customers.csv"
    _crear_csv(repo_root / ruta_csv_relativa)

    obs = file_observer.factory_with_repo_root(repo_root)("customers", {"path": ruta_csv_relativa})
    resultado = obs.observe({})

    texto = json.dumps(resultado)
    assert ruta_csv_relativa not in texto
    assert str(repo_root) not in texto
    assert str(repo_root / ruta_csv_relativa) not in texto


# ---------------------------------------------------------------------------
# guard de holdout
# ---------------------------------------------------------------------------


def test_ruta_bajo_holdout_declarado_lanza_excepcion(tmp_path):
    repo_root = _crear_repo(tmp_path)
    ruta_csv_relativa = "data/holdout/secreto.csv"
    (repo_root / "data" / "holdout").mkdir(parents=True, exist_ok=True)
    _crear_csv(repo_root / ruta_csv_relativa)

    (repo_root / ".claude").mkdir(parents=True, exist_ok=True)
    guardrails = {"version": 1, "holdouts": ["data/holdout/**"]}
    (repo_root / ".claude" / "guardrails.json").write_text(json.dumps(guardrails), encoding="utf-8")

    obs = file_observer.factory_with_repo_root(repo_root)("customers", {"path": ruta_csv_relativa})
    with pytest.raises(RuntimeError) as exc_info:
        obs.observe({})

    mensaje = str(exc_info.value)
    assert str(repo_root) not in mensaje
    assert ruta_csv_relativa in mensaje


def test_factory_sin_repo_root_lanza_runtimeerror_claro(tmp_path):
    ruta_csv_relativa = "data/customers.csv"
    _crear_csv(_crear_repo(tmp_path) / ruta_csv_relativa)

    obs = file_observer.factory("customers", {"path": ruta_csv_relativa})
    with pytest.raises(RuntimeError, match="repo_root"):
        obs.observe({})


def test_factory_con_repo_root_en_options(tmp_path):
    repo_root = _crear_repo(tmp_path)
    ruta_csv_relativa = "data/customers.csv"
    _crear_csv(repo_root / ruta_csv_relativa)

    obs = file_observer.factory("customers", {"path": ruta_csv_relativa, "_repo_root": str(repo_root)})
    resultado = obs.observe({})
    assert resultado["source_id"] == "customers"
