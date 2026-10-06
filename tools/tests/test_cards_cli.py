"""Tests del subcomando `ds_guard cards validate|report` (Change
`20261005-cards-governance-integration`, R43-R52; contrato F). Corre `tools/ds_guard.py`
real como subproceso contra un repo git temporal (nunca este repositorio)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.cards import core, datacard, govpolicy, modelcard, modelgov

REPO_ORIGEN = Path(__file__).resolve().parents[2]
DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"
T0 = "2026-10-01T10:00:00Z"
NOW = "2026-10-04T00:00:00Z"
H1 = "a" * 64


def _crear_repo() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="cli_cards_")).resolve()
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(repo), check=True)
    (repo / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=str(repo), check=True)
    return repo


def _correr(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DS_GUARD), *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8"
    )


def _data_card(card_id="producto-a"):
    pin = core.EvidenceRef("ev-src-a", "source_observation", "ventas__aaaaaaaaaaaa", H1, T0)
    return core.CardEnvelope(
        schema_version=1, card_kind="data_card", kind_schema_version=1, card_id=card_id, title="DC",
        subject=card_id, created_at=T0, generated_at=T0, evidence=(pin,),
        claims=(core.Claim("c-src-a", "Observada", supports=("ev-src-a",), requirement_id="source_src-a"),),
        body={
            "description": "Producto de prueba",
            "source_refs": [{"source_ref_id": "src-a", "source_id": "ventas", "observation_evidence_id": "ev-src-a"}],
        },
    )


def _model_card():
    return core.CardEnvelope(
        schema_version=1, card_kind="model_card", kind_schema_version=1,
        card_id=modelcard.model_card_id("clasificador", "1.0.0"), title="MC", subject="clasificador",
        created_at=T0, generated_at=T0,
        body={"model_id": "clasificador", "model_version": "1.0.0", "description": "Modelo de prueba"},
    )


def _assessment():
    cid = modelcard.model_card_id("clasificador", "1.0.0")
    pin = core.EvidenceRef("ev-mc", "model_card", f"{cid}__{H1[:12]}", H1, T0, locator=f"governance/cards/model/{cid}.json")
    return core.CardEnvelope(
        schema_version=1, card_kind="governance_assessment", kind_schema_version=1, card_id=cid, title="GA",
        subject="clasificador", created_at=T0, generated_at=T0, evidence=(pin,),
        claims=(core.Claim("c-mc", "Respaldo", supports=("ev-mc",), requirement_id="model_card_pin"),),
        body={
            "model_card_ref": {"evidence_id": "ev-mc"},
            "policy_ref": {
                "base_policy_id": govpolicy.BASE_POLICY.policy_id,
                "base_version": govpolicy.BASE_POLICY.version,
                "base_sha256": govpolicy.BASE_POLICY_SHA256,
                "effective_sha256": govpolicy.merge(govpolicy.BASE_POLICY).effective_sha256(),
            },
        },
    )


def _foto(repo: Path) -> dict:
    return {p.relative_to(repo).as_posix(): p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts}


class BaseCli(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.repo, ignore_errors=True))

    def escribir_control(self, capacidades):
        ruta = self.repo / ".ds_init" / "control.json"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({"capabilities_habilitadas": capacidades}), encoding="utf-8")


class TestValidate(BaseCli):
    def test_data_card_humano(self):
        datacard.write_data_card(self.repo, _data_card(), clock=lambda: NOW)
        p = _correr(["cards", "validate"], self.repo)
        self.assertIn(p.returncode, (0, 1), p.stderr)
        self.assertIn("producto-a", p.stdout)
        self.assertIn("[data]", p.stdout)
        self.assertIn("NO equivale", p.stdout)  # nota complete != aceptable
        self.assertNotIn(str(self.repo), p.stdout)

    def test_json_una_linea_y_claves(self):
        datacard.write_data_card(self.repo, _data_card(), clock=lambda: NOW)
        modelcard.write_model_card(self.repo, _model_card(), clock=lambda: NOW)
        modelgov.write_governance_assessment(self.repo, _assessment(), clock=lambda: NOW)
        p = _correr(["cards", "validate", "--json"], self.repo)
        self.assertEqual(len(p.stdout.strip().splitlines()), 1, p.stdout)
        datos = json.loads(p.stdout)
        self.assertEqual(set(datos), {"resultados", "cards", "nota"})
        self.assertEqual([c["kind"] for c in datos["cards"]], ["data", "model", "governance"])
        for c in datos["cards"]:
            self.assertTrue(
                {"kind", "card_id", "revision_id", "status", "requirements", "evidence", "anchors", "policy"} <= set(c)
            )
        self.assertNotIn(str(self.repo), p.stdout)
        gov = datos["cards"][2]
        self.assertIn("effective_level", gov["policy"])

    def test_kind_y_path(self):
        datacard.write_data_card(self.repo, _data_card(), clock=lambda: NOW)
        modelcard.write_model_card(self.repo, _model_card(), clock=lambda: NOW)
        p = _correr(["cards", "validate", "--kind", "model", "--json"], self.repo)
        self.assertEqual([c["kind"] for c in json.loads(p.stdout)["cards"]], ["model"])
        p = _correr(["cards", "validate", "--path", "governance/cards/data/producto-a.json", "--json"], self.repo)
        self.assertEqual([c["kind"] for c in json.loads(p.stdout)["cards"]], ["data"])

    def test_malformado_es_fail_exit_1(self):
        ruta = self.repo / "governance" / "cards" / "data" / "roto.json"
        ruta.parent.mkdir(parents=True)
        ruta.write_text("{roto", encoding="utf-8")
        p = _correr(["cards", "validate", "--json"], self.repo)
        self.assertEqual(p.returncode, 1, p.stderr)
        datos = json.loads(p.stdout)
        self.assertEqual(datos["cards"][0]["status"], "invalid")
        self.assertTrue(any(r["status"] == "FAIL" for r in datos["resultados"]))

    def test_sin_cards_exit_0_na(self):
        p = _correr(["cards", "validate", "--json"], self.repo)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["cards"], [])

    def test_kind_invalido_exit_2(self):
        self.assertEqual(_correr(["cards", "validate", "--kind", "otro"], self.repo).returncode, 2)

    def test_validate_no_escribe(self):
        datacard.write_data_card(self.repo, _data_card(), clock=lambda: NOW)
        antes = _foto(self.repo)
        _correr(["cards", "validate"], self.repo)
        _correr(["cards", "validate", "--json"], self.repo)
        self.assertEqual(antes, _foto(self.repo))


class TestGatingCapabilities(BaseCli):
    def test_sin_control_sin_gating(self):
        datacard.write_data_card(self.repo, _data_card(), clock=lambda: NOW)
        p = _correr(["cards", "validate", "--json"], self.repo)
        self.assertEqual(len(json.loads(p.stdout)["cards"]), 1)

    def test_discovery_con_capability_deshabilitada_es_na(self):
        datacard.write_data_card(self.repo, _data_card(), clock=lambda: NOW)
        self.escribir_control(["predictive_modeling"])  # data_cards no habilitada
        p = _correr(["cards", "validate", "--json"], self.repo)
        self.assertEqual(p.returncode, 0, p.stderr)
        datos = json.loads(p.stdout)
        self.assertEqual(datos["cards"], [])
        self.assertTrue(any(r["code"] == "CARDS-CAPABILITY-DISABLED" and r["status"] == "N/A" for r in datos["resultados"]))

    def test_explicito_con_capability_deshabilitada_exit_2(self):
        datacard.write_data_card(self.repo, _data_card(), clock=lambda: NOW)
        self.escribir_control(["predictive_modeling"])
        self.assertEqual(_correr(["cards", "validate", "--kind", "data"], self.repo).returncode, 2)
        p = _correr(["cards", "validate", "--path", "governance/cards/data/producto-a.json"], self.repo)
        self.assertEqual(p.returncode, 2)

    def test_data_cards_habilitada_valida(self):
        datacard.write_data_card(self.repo, _data_card(), clock=lambda: NOW)
        self.escribir_control(["data_cards", "predictive_modeling"])
        p = _correr(["cards", "validate", "--json"], self.repo)
        self.assertEqual([c["kind"] for c in json.loads(p.stdout)["cards"]], ["data"])

    def test_model_governance_sin_predictive_exit_2(self):
        self.escribir_control(["model_governance"])
        self.assertEqual(_correr(["cards", "validate"], self.repo).returncode, 2)

    def test_control_ilegible_falla_cerrado_en_validate_y_en_report(self):
        # Cierre de revisión ciclo 2 (N-3): un control corrupto no desactiva el gating.
        datacard.write_data_card(self.repo, _data_card(), clock=lambda: NOW)
        ruta = self.repo / ".ds_init" / "control.json"
        ruta.parent.mkdir(parents=True)
        ruta.write_text("{{{", encoding="utf-8")
        ruta_card = "governance/cards/data/producto-a.json"
        self.assertEqual(_correr(["cards", "validate"], self.repo).returncode, 2)
        self.assertEqual(_correr(["cards", "validate", "--path", ruta_card], self.repo).returncode, 2)
        p = _correr(["cards", "report", "--path", ruta_card, "--out-dir", "reports/exploratory/x"], self.repo)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertFalse((self.repo / "reports").exists())

    def test_control_legacy_sin_lista_opt_in_deshabilitadas(self):
        datacard.write_data_card(self.repo, _data_card(), clock=lambda: NOW)
        ruta = self.repo / ".ds_init" / "control.json"
        ruta.parent.mkdir(parents=True)
        ruta.write_text("{}", encoding="utf-8")
        p = _correr(["cards", "validate", "--kind", "data"], self.repo)
        self.assertEqual(p.returncode, 2)


class TestReport(BaseCli):
    def test_report_requiere_path(self):
        self.assertEqual(_correr(["cards", "report"], self.repo).returncode, 2)

    def test_report_publica_en_out_dir(self):
        datacard.write_data_card(self.repo, _data_card(), clock=lambda: NOW)
        antes_gov = _foto(self.repo / "governance")
        p = _correr(
            ["cards", "report", "--path", "governance/cards/data/producto-a.json",
             "--out-dir", "reports/exploratory/gov-cli", "--json"],
            self.repo,
        )
        self.assertIn(p.returncode, (0, 1), p.stderr)
        datos = json.loads(p.stdout)
        self.assertIn("out_dir", datos)
        self.assertTrue((self.repo / "reports" / "exploratory" / "gov-cli" / "report.html").is_file(), p.stdout)
        self.assertEqual(antes_gov, _foto(self.repo / "governance"))

    def test_report_con_capability_deshabilitada_no_escribe(self):
        datacard.write_data_card(self.repo, _data_card(), clock=lambda: NOW)
        self.escribir_control(["predictive_modeling"])
        antes = _foto(self.repo)
        p = _correr(
            ["cards", "report", "--path", "governance/cards/data/producto-a.json",
             "--out-dir", "reports/exploratory/gov-cli"],
            self.repo,
        )
        self.assertEqual(p.returncode, 2)
        self.assertEqual(antes, _foto(self.repo))


class TestModelYAssessmentCli(BaseCli):
    def setUp(self):
        super().setUp()
        modelcard.write_model_card(self.repo, _model_card(), clock=lambda: NOW)
        modelgov.write_governance_assessment(self.repo, _assessment(), clock=lambda: NOW)

    def test_model_card_humano(self):
        p = _correr(["cards", "validate", "--kind", "model"], self.repo)
        self.assertIn(p.returncode, (0, 1), p.stderr)
        self.assertIn("[model]", p.stdout)
        self.assertIn("clasificador", p.stdout)

    def test_assessment_humano_muestra_riesgo_y_policy(self):
        p = _correr(["cards", "validate", "--kind", "governance"], self.repo)
        self.assertIn(p.returncode, (0, 1), p.stderr)
        self.assertIn("[governance]", p.stdout)
        self.assertIn("risk_level", p.stdout)
        self.assertIn("policy", p.stdout)
        self.assertIn("NO equivale", p.stdout)

    def test_sin_rutas_absolutas_en_humano_y_json(self):
        for args in (["cards", "validate"], ["cards", "validate", "--json"]):
            p = _correr(args, self.repo)
            self.assertNotIn(str(self.repo), p.stdout)
            self.assertNotIn(str(self.repo).replace("\\", "/"), p.stdout)

    def test_kind_incompatible_con_path_exit_2(self):
        cid = modelcard.model_card_id("clasificador", "1.0.0")
        p = _correr(["cards", "validate", "--kind", "data", "--path", f"governance/cards/model/{cid}.json"], self.repo)
        self.assertEqual(p.returncode, 2)
        self.assertIn("incompatible", p.stderr)

    def test_path_fuera_del_repo_solo_relativo(self):
        with tempfile.TemporaryDirectory() as otro:
            ajeno = Path(otro) / "ajeno.json"
            ajeno.write_text("{}", encoding="utf-8")
            for extra in ([], ["--json"]):
                p = _correr(["cards", "validate", "--path", str(ajeno), *extra], self.repo)
                self.assertEqual(p.returncode, 1, p.stderr)
                self.assertNotIn(otro, p.stdout)
                self.assertIn("<fuera-del-repo>/ajeno.json", p.stdout)

    def test_report_out_dir_bajo_governance_rechazado(self):
        cid = modelcard.model_card_id("clasificador", "1.0.0")
        antes = _foto(self.repo)
        p = _correr(
            ["cards", "report", "--path", f"governance/cards/model/{cid}.json", "--out-dir", "governance/reportes/x"],
            self.repo,
        )
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse((self.repo / "governance" / "reportes").exists())
        self.assertEqual(antes, _foto(self.repo))

    def test_report_assessment_publica(self):
        cid = modelcard.model_card_id("clasificador", "1.0.0")
        p = _correr(
            ["cards", "report", "--path", f"governance/model-risk/{cid}.json",
             "--out-dir", "reports/exploratory/gov-ga", "--json"],
            self.repo,
        )
        self.assertIn(p.returncode, (0, 1), p.stderr)
        self.assertTrue((self.repo / "reports" / "exploratory" / "gov-ga" / "report.html").is_file(), p.stdout)
        self.assertNotIn(str(self.repo), p.stdout)


class TestPaqueteAusente(unittest.TestCase):
    """Exit 3 con `_mensaje_paquete_no_instalado` si el tooling de cards no está instalado."""

    def test_validate_y_report_exit_3(self):
        import argparse
        from io import StringIO
        from unittest import mock

        from tools import ds_guard

        repo = Path(tempfile.mkdtemp(prefix="cli_cards_ausente_"))
        self.addCleanup(lambda: __import__("shutil").rmtree(repo, ignore_errors=True))
        with mock.patch.object(ds_guard, "_repo_root", return_value=repo), mock.patch.object(
            ds_guard, "_importar_perezoso", return_value=None
        ), mock.patch("sys.stderr", new_callable=StringIO) as err:
            self.assertEqual(
                ds_guard.cmd_cards_validate(argparse.Namespace(path=[], kind=None, json=False)), 3
            )
            self.assertEqual(
                ds_guard.cmd_cards_report(argparse.Namespace(path="x.json", out_dir=None, json=False)), 3
            )
        self.assertIn("cards no está instalado", err.getvalue())


if __name__ == "__main__":
    unittest.main()
