"""Tests de CLI de `ds_guard source *` y `contract validate --observation`
(v0.8 Change 1 T6, `20260928-source-neutral-data-access`).

Mismo patrón que `test_ds_guard_contract_quality_cli.py`: corre
`tools/ds_guard.py` real como subproceso contra un repo git temporal
sintético. El observer de prueba se escribe como archivo real bajo el repo
temporal y se agrega a `PYTHONPATH` (subprocess, no in-process: no se puede
compartir un observer en memoria como hace `test_runtime.py`)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"


def _crear_repo_git_temporal(prefix: str = "cli_source_") -> Path:
    repo = Path(tempfile.mkdtemp(prefix=prefix))
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)
    (repo / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=str(repo), check=True)
    return repo


def _correr_ds_guard(args: list, cwd: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(cwd) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, str(DS_GUARD), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def _escribir_json(repo: Path, nombre: str, datos) -> Path:
    ruta = repo / nombre
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


# --- Observer de prueba (archivo real, importable vía PYTHONPATH=repo) ------

_OBSERVER_OK_CODIGO = (
    "def factory(source_id, options):\n"
    "    class _Obs:\n"
    "        def capabilities(self):\n"
    "            return {'facets': {'row_count': ['exact']}, 'operations': []}\n"
    "        def observe(self, request):\n"
    "            return {\n"
    "                'dataset': {'row_count': {'value': 3, 'exactness': 'exact'}},\n"
    "                'fields': [],\n"
    "            }\n"
    "    return _Obs()\n"
)

_OBSERVER_DECOY_CODIGO = (
    "import pathlib\n"
    "pathlib.Path(__file__).with_name('importado.marker').write_text('importado', encoding='utf-8')\n"
    "\n"
    "def factory(source_id, options):\n"
    "    class _Obs:\n"
    "        def capabilities(self):\n"
    "            return {'facets': {}, 'operations': []}\n"
    "        def observe(self, request):\n"
    "            return {'dataset': {}, 'fields': []}\n"
    "    return _Obs()\n"
)


def _escribir_registro(repo: Path, *fuentes) -> None:
    directorio = repo / ".harmessi"
    directorio.mkdir(parents=True, exist_ok=True)
    (directorio / "sources.json").write_text(
        json.dumps({"schema_version": 1, "sources": list(fuentes)}, ensure_ascii=False), encoding="utf-8"
    )


def _fuente_customers(**overrides) -> dict:
    base = {
        "source_id": "customers",
        "role": "raw_table",
        "observer": "observer_ok:factory",
        "access_mode": "read",
        "sensitivity": "internal",
    }
    base.update(overrides)
    return base


def _escribir_guardrails(repo: Path, datos) -> Path:
    directorio = repo / ".claude"
    directorio.mkdir(parents=True, exist_ok=True)
    ruta = directorio / "guardrails.json"
    if isinstance(datos, str):
        ruta.write_text(datos, encoding="utf-8")
    else:
        ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return ruta


_GUARDRAILS_SELLADA = {
    "version": 2,
    "autonomy": {
        "version": 2,
        "mode": "supervised",
        "sealed_sources": ["customers"],
    },
}


class _BaseRepoGit(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)


# --- source list --------------------------------------------------------------

class TestSourceList(_BaseRepoGit):
    def test_sin_registro_es_informativo_exit_0(self):
        r = _correr_ds_guard(["source", "list", "--json"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertIn("resultados", payload)
        codigos = [x["code"] for x in payload["resultados"]]
        self.assertIn("SOURCE-REGISTRY-MISSING", codigos)

    def test_con_registro_lista_fuentes(self):
        _escribir_registro(self.repo, _fuente_customers())
        r = _correr_ds_guard(["source", "list", "--json"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(len(payload["fuentes"]), 1)
        self.assertEqual(payload["fuentes"][0]["source_id"], "customers")


# --- source check ---------------------------------------------------------------

class TestSourceCheck(_BaseRepoGit):
    def test_registro_valido(self):
        _escribir_registro(self.repo, _fuente_customers())
        r = _correr_ds_guard(["source", "check", "--json"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)


# --- source observe --------------------------------------------------------------

class TestSourceObserve(_BaseRepoGit):
    def test_observe_de_punta_a_punta_exito(self):
        (self.repo / "observer_ok.py").write_text(_OBSERVER_OK_CODIGO, encoding="utf-8")
        _escribir_registro(self.repo, _fuente_customers())
        r = _correr_ds_guard(
            ["source", "observe", "--source-id", "customers", "--json"], self.repo
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertIn("observation_id", payload)
        self.assertTrue(payload["observation_id"].startswith("customers__"))
        # Persistido en disco.
        directorio_obs = self.repo / ".harmessi" / "observations" / payload["observation_id"]
        self.assertTrue((directorio_obs / "observation.json").exists())

    def test_fuente_sellada_no_importa_observer(self):
        (self.repo / "observer_decoy.py").write_text(_OBSERVER_DECOY_CODIGO, encoding="utf-8")
        _escribir_registro(self.repo, _fuente_customers(observer="observer_decoy:factory"))
        _escribir_guardrails(self.repo, _GUARDRAILS_SELLADA)

        r = _correr_ds_guard(
            ["source", "observe", "--source-id", "customers", "--json"], self.repo
        )
        self.assertNotEqual(r.returncode, 0)
        payload = json.loads(r.stdout)
        codigos = [x["code"] for x in payload["resultados"]]
        self.assertIn("SOURCE-SEALED", codigos)
        # El observer señuelo no se importó: no dejó su marcador en disco.
        self.assertFalse((self.repo / "importado.marker").exists())

    def test_guardrails_corrupto_deniega(self):
        (self.repo / "observer_decoy.py").write_text(_OBSERVER_DECOY_CODIGO, encoding="utf-8")
        _escribir_registro(self.repo, _fuente_customers(observer="observer_decoy:factory"))
        _escribir_guardrails(self.repo, "{ esto no es json valido")

        r = _correr_ds_guard(
            ["source", "observe", "--source-id", "customers", "--json"], self.repo
        )
        self.assertNotEqual(r.returncode, 0)
        payload = json.loads(r.stdout)
        codigos = [x["code"] for x in payload["resultados"]]
        self.assertIn("SOURCE-ACCESS-DENIED", codigos)
        self.assertFalse((self.repo / "importado.marker").exists())


# --- source check-stale ----------------------------------------------------------

class TestSourceCheckStale(_BaseRepoGit):
    def test_ruta_invalida_exit_2(self):
        r = _correr_ds_guard(
            ["source", "check-stale", "--observation", "../fuera/x.json"], self.repo
        )
        self.assertEqual(r.returncode, 2)


# --- contract validate --observation --------------------------------------------

_CONTRATO_V1 = {
    "contract_id": "c1",
    "version": {"version": "1.0.0"},
    "dataset_role": "raw_table",
    "fields": [{"name": "id", "type_family": "integer", "required": True, "nullable": False}],
    "constraints": [],
    "business_rules": [],
    "keys": [],
    "compatibility_policy": None,
    "description": "",
    "extensions": {},
    "schema_version": 1,
}

_PROFILE = {
    "schema": {"id": {}},
    "columnas_detalle": {
        "id": {"dtype": "entero", "nulls": {"count": 0}, "unique": {"count": 3, "exactitud": "exacta"}}
    },
    "sampling": {"activo": False},
    "filas": 3,
}


def _observacion_valida() -> dict:
    return {
        "schema_version": 1,
        "source_id": "customers",
        "provenance": {
            "source_id": "customers",
            "observer_id": "observer_ok:factory",
            "observer_code_sha256": None,
            "access_mode": "read",
            "source_kind": None,
            "generated_at": "2026-01-01T00:00:00Z",
            "tool_versions": {},
            "requested_facets": [],
            "unsupported_facets": [],
        },
        "dataset": {},
        "fields": [
            {
                "name": "id",
                "type_family": "integer",
                "native_type": "int64",
                "facets": {"null_count": {"value": 0, "exactness": "exact"}},
            }
        ],
        "omitted_facets": [],
    }


class TestContractValidateObservation(_BaseRepoGit):
    def test_sin_profile_ni_observation_exit_2(self):
        contrato = _escribir_json(self.repo, "contract.json", _CONTRATO_V1)
        r = _correr_ds_guard(["contract", "validate", "--contract", str(contrato)], self.repo)
        self.assertEqual(r.returncode, 2)

    def test_con_ambos_exit_2(self):
        contrato = _escribir_json(self.repo, "contract.json", _CONTRATO_V1)
        profile = _escribir_json(self.repo, "profile.json", _PROFILE)
        obs = _escribir_json(self.repo, "observation.json", _observacion_valida())
        r = _correr_ds_guard(
            [
                "contract",
                "validate",
                "--contract",
                str(contrato),
                "--profile",
                str(profile),
                "--observation",
                str(obs),
            ],
            self.repo,
        )
        self.assertEqual(r.returncode, 2)

    def test_profile_solo_sigue_funcionando(self):
        contrato = _escribir_json(self.repo, "contract.json", _CONTRATO_V1)
        profile = _escribir_json(self.repo, "profile.json", _PROFILE)
        r = _correr_ds_guard(
            ["contract", "validate", "--contract", str(contrato), "--profile", str(profile), "--json"],
            self.repo,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertTrue(len(payload["resultados"]) > 0)

    def test_observation_da_resultado_del_mismo_tipo_que_profile(self):
        contrato = _escribir_json(self.repo, "contract.json", _CONTRATO_V1)
        obs = _escribir_json(self.repo, "observation.json", _observacion_valida())
        r = _correr_ds_guard(
            ["contract", "validate", "--contract", str(contrato), "--observation", str(obs), "--json"],
            self.repo,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertTrue(len(payload["resultados"]) > 0)
        for entrada in payload["resultados"]:
            self.assertIn("status", entrada)
            self.assertIn("code", entrada)


if __name__ == "__main__":
    unittest.main()
