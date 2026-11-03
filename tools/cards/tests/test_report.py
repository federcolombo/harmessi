"""Tests de `tools/cards/report.py` (Change `20261005-cards-governance-integration`,
R63-R72; contrato E). Repos sintéticos en directorios temporales."""
from __future__ import annotations

import dataclasses
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.cards import datacard, discovery, modelcard, modelgov, report
from tools.cards.tests.test_discovery import (
    NOW, T0, BaseTmp, hacer_assessment, hacer_data_card, hacer_model_card,
)
from tools.reporting import core as rcore

MARCA_PAYLOAD = "PAYLOAD-SECRETO-7f3a91"


def _repo_con_git(raiz: Path) -> None:
    for cmd in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t@example.com"],
        ["git", "config", "user.name", "T"],
    ):
        subprocess.run(cmd, cwd=str(raiz), check=True)


class TestConstruirReport(BaseTmp):
    def _reporte(self, kind_escribe):
        if kind_escribe == "data":
            datacard.write_data_card(self.raiz, hacer_data_card(), clock=lambda: NOW)
        elif kind_escribe == "model":
            modelcard.write_model_card(self.raiz, hacer_model_card(), clock=lambda: NOW)
        else:
            modelgov.write_governance_assessment(self.raiz, hacer_assessment(), clock=lambda: NOW)
        cr = discovery.validar_proyecto(self.raiz).reports[0]
        return report.construir_report(cr, repo_root=self.raiz), cr

    def test_vocabulario_y_estructura_para_las_tres_cards(self):
        for kind in ("data", "model", "governance"):
            with self.subTest(kind=kind):
                with tempfile.TemporaryDirectory() as tmp:
                    self.raiz = Path(tmp).resolve()
                    rep, cr = self._reporte(kind)
                    self.assertEqual(rep.report_kind, "governance")
                    self.assertEqual(rep.decision_scope, "exploratory")
                    self.assertEqual(list(rep.iter_figures()), [])
                    self.assertEqual(list(rep.iter_insights()), [])
                    self.assertTrue(list(rep.iter_tables()))
                    nota = report.nota_completeness()
                    self.assertIn(nota, rep.summary)
                    self.assertIn(nota, rep.conclusion)
                    for cap in rep.chapters:
                        self.assertIn(nota, cap.method_note)

    def test_tablas_de_evidencia_sin_contenido(self):
        rep, cr = self._reporte("data")
        tabla = rep.get_table("estado-evidencia")
        self.assertEqual(tabla.columns, ("evidence_id", "kind", "ref_id", "hash12", "estado"))
        self.assertEqual(tabla.rows[0][0], "ev-src-a")
        self.assertEqual(tabla.rows[0][3], "a" * 12)

    def test_assessment_incluye_riesgo_y_policy(self):
        rep, cr = self._reporte("governance")
        tabla = rep.get_table("riesgo-y-policy")
        campos = {fila[0] for fila in tabla.rows}
        self.assertIn("risk_level_efectivo", campos)
        self.assertIn("governance_completeness", campos)

    def test_r68_en_cada_capitulo_de_model_card_y_assessment(self):
        nota = report.nota_completeness()
        for kind in ("model", "governance"):
            with self.subTest(kind=kind):
                with tempfile.TemporaryDirectory() as tmp:
                    self.raiz = Path(tmp).resolve()
                    rep, cr = self._reporte(kind)
                    self.assertGreaterEqual(len(rep.chapters), 3)
                    for cap in rep.chapters:
                        self.assertIn(nota, cap.method_note, cap.chapter_id)

    def test_assessment_incluye_nota_anchor_y_estado_de_configuracion(self):
        rep, cr = self._reporte("governance")
        cap = next(c for c in rep.chapters if c.chapter_id == "assessment")
        na = report.nota_anchor()
        if na:
            self.assertIn(na, cap.method_note)
        campos = {fila[0] for fila in rep.get_table("riesgo-y-policy").rows}
        self.assertIn("estado_configuracion", campos)

    def test_sin_rutas_absolutas(self):
        rep, cr = self._reporte("data")
        self.assertNotIn(str(self.raiz), json.dumps(rep.to_dict(), ensure_ascii=False))

    def test_card_invalida_se_reporta_sin_conclusiones(self):
        self.escribir_texto("governance/cards/data/roto.json", "{roto")
        cr = discovery.validar_proyecto(self.raiz).reports[0]
        rep = report.construir_report(cr, repo_root=self.raiz)
        self.assertEqual(rep.report_kind, "governance")
        self.assertIn("invalid", rep.summary)
        self.assertNotIn("aprobad", rep.summary.lower())


class TestPublicarCard(BaseTmp):
    def setUp(self):
        super().setUp()
        _repo_con_git(self.raiz)
        self.escribir_texto("data/payload.txt", MARCA_PAYLOAD)
        pin = datacard.core.EvidenceRef(
            "ev-src-a", "source_observation", "ventas__aaaaaaaaaaaa", "a" * 64, T0, locator="data/payload.txt"
        )
        card = dataclasses.replace(hacer_data_card(), evidence=(pin,))
        datacard.write_data_card(self.raiz, card, clock=lambda: NOW)

    def _publicar(self, out="reports/exploratory/gov-test"):
        return report.publicar_card(self.raiz, "governance/cards/data/producto-a.json", out_dir=out)

    def test_publica_html_con_aclaracion_y_sin_payload(self):
        resultado, pv = self._publicar()
        self.assertTrue(resultado.html_written, [r.to_dict() for r in resultado.results])
        destino = self.raiz / resultado.out_dir
        html = (destino / "report.html").read_text(encoding="utf-8")
        self.assertIn("NO equivale a aprobaci", html)  # NOTA_COMPLETENESS renderizada (R68)
        for artefacto in (destino / "artifacts").glob("*.json"):
            self.assertNotIn(MARCA_PAYLOAD, artefacto.read_text(encoding="utf-8"))
        self.assertNotIn(MARCA_PAYLOAD, html)
        manifest = json.loads((destino / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["report_kind"], "governance")
        self.assertEqual(manifest["decision_scope"], "exploratory")

    def test_no_escribe_bajo_governance(self):
        antes = sorted(p.relative_to(self.raiz).as_posix() for p in (self.raiz / "governance").rglob("*"))
        self._publicar()
        despues = sorted(p.relative_to(self.raiz).as_posix() for p in (self.raiz / "governance").rglob("*"))
        self.assertEqual(antes, despues)

    def test_escape_de_texto_de_usuario(self):
        hostil = "Producto <script>alert(1)</script>"
        datacard.write_data_card(self.raiz, hacer_data_card("hostil"), clock=lambda: NOW)
        ruta = self.raiz / "governance" / "cards" / "data" / "hostil.json"
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["body"]["description"] = hostil
        datos.pop("revision_id", None)
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        resultado, _pv = report.publicar_card(
            self.raiz, "governance/cards/data/hostil.json", out_dir="reports/exploratory/gov-hostil"
        )
        html = (self.raiz / resultado.out_dir / "report.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>alert(1)</script>", html)
        # Fuerte: la Card hostil debe haberse evaluado (no invalid por otro motivo) y su texto
        # aparecer ESCAPADO; si no, el assertNotIn de arriba sería vacuo.
        self.assertTrue(html, "el reporte debe haberse publicado")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_publish_que_lanza_devuelve_fail_sin_traceback(self):
        _rc, _ev, rpublish = report._reporting()
        with mock.patch.object(rpublish, "publish", side_effect=RuntimeError("boom")):
            resultado, _pv = self._publicar()
        self.assertFalse(resultado.written)
        self.assertTrue(any(r.status == "FAIL" for r in resultado.results))

    def test_out_dir_bajo_governance_rechazado(self):
        resultado, _pv = report.publicar_card(
            self.raiz, "governance/cards/data/producto-a.json", out_dir="governance/reportes/x"
        )
        self.assertFalse(resultado.html_written)
        self.assertTrue(any(r.status == "FAIL" for r in resultado.results))
        self.assertFalse((self.raiz / "governance" / "reportes").exists())

    def test_path_inexistente_falla_sin_lanzar(self):
        resultado, pv = report.publicar_card(self.raiz, "governance/cards/data/no-existe.json")
        self.assertFalse(resultado.written)
        self.assertTrue(any(r.status == "FAIL" for r in resultado.results))


if __name__ == "__main__":
    unittest.main()
