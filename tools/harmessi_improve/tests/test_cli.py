"""Tests de la CLI `python -m tools.harmessi_improve` (v0.14 Change 5, R10). main(argv) con repo
temporal (--repo-root) y FakeAdapter inyectado parcheando `cli._resolver_adapter`."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.harmessi_improve import cli
from tools.harmessi_improve.tests._fakes import MARCA_BASE, MARCA_CAND, FakeAdapter, crear_suite
from tools.harmessi_improve.tests._helpers import ACTIVO, crear_repo

TODOS = "tok-1 tok-2 tok-3"
SOLO_1 = "tok-1"


class BaseCli(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._aux = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self._aux.cleanup)
        self.raiz = crear_repo(Path(self._tmp.name))
        (self.raiz / ACTIVO).write_bytes(f"# Skill\n{MARCA_BASE}\n".encode("utf-8"))
        self.aux = Path(self._aux.name)
        self.suite = crear_suite(self.aux)
        self.contenido = self.aux / "nuevo.md"
        self.contenido.write_text(f"# Skill\n{MARCA_CAND}\nvariante\n", encoding="utf-8")
        self.adapter = FakeAdapter(SOLO_1, TODOS)
        parche = mock.patch.object(cli, "_resolver_adapter", lambda provider_id: self.adapter)
        parche.start()
        self.addCleanup(parche.stop)
        self.salidas = []

    def correr(self, *argv, json_out=False):
        """Devuelve (codigo, stdout, stderr); acumula las salidas para el chequeo de rutas."""
        out, err = io.StringIO(), io.StringIO()
        comun = ["--repo-root", str(self.raiz)]
        if json_out:
            comun.append("--json")
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            codigo = cli.main(list(argv) + comun)
        self.salidas.append(out.getvalue() + err.getvalue())
        return codigo, out.getvalue(), err.getvalue()

    def crear_candidate(self, surface=ACTIVO):
        codigo, out, _ = self.correr("candidate", "create", "--base-surface", surface,
                                     "--content-file", str(self.contenido), "--hypothesis", "h1",
                                     json_out=True)
        return codigo, out

    def tearDown(self):
        # Ninguna salida expone la ruta del repo temporal.
        for texto in self.salidas:
            self.assertNotIn(str(self.raiz), texto)
            self.assertNotIn(self.raiz.as_posix(), texto)
            self.assertNotIn("Traceback", texto)


class TestFlujo(BaseCli):
    def test_flujo_completo(self):
        codigo, out = self.crear_candidate()
        self.assertEqual(codigo, 0)
        cid = json.loads(out)["candidate_id"]

        codigo, out, _ = self.correr("candidate", "list", json_out=True)
        self.assertEqual(codigo, 0)
        self.assertEqual([c["candidate_id"] for c in json.loads(out)], [cid])
        self.assertEqual(self.correr("candidate", "show", cid, json_out=True)[0], 0)

        codigo, out, _ = self.correr("probe", "--candidate", cid, "--suite", str(self.suite),
                                     "--provider", "fake", "--probe-id", "p1", json_out=True)
        self.assertEqual(codigo, 0)
        json.loads(out)

        # Sin --apply solo muestra: la candidate no transiciona.
        codigo, out, _ = self.correr("decide", "--probe-id", "p1", json_out=True)
        self.assertEqual(codigo, 0)
        self.assertFalse(json.loads(out)["aplicada"])
        self.assertEqual(json.loads(self.correr("candidate", "show", cid, json_out=True)[1])["status"], "proposed")

        codigo, out, _ = self.correr("decide", "--probe-id", "p1", "--apply", json_out=True)
        self.assertEqual(codigo, 0)
        self.assertEqual(json.loads(out)["candidate_status"], "promotable")

        self.assertEqual(self.correr("promote", "propose", "--candidate", cid, json_out=True)[0], 0)

        # Sin Change abierto el gate bloquea.
        codigo, _, err = self.correr("promote", "gate", "--candidate", cid, "--change-id", "20261023-nope")
        self.assertEqual(codigo, 1)
        self.assertIn("bloqueada", err)
        codigo, _, _ = self.correr("promote", "apply", "--candidate", cid, "--change-id", "20261023-nope")
        self.assertEqual(codigo, 1)

    def test_budget_show(self):
        codigo, out, _ = self.correr("budget", "show", json_out=True)
        self.assertEqual(codigo, 0)
        datos = json.loads(out)
        self.assertIn("presupuesto", datos)
        self.assertIn("estado", datos)
        self.assertEqual(self.correr("budget", "show")[0], 0)

    def test_lesson_add_sin_change(self):
        codigo, _, err = self.correr("lesson", "add", "--change-id", "20261023-nope", "--pattern", "p",
                                     "--recommendation", "r", "--context", "skills",
                                     "--evidence", "p1:abc123:suite-fake")
        self.assertEqual(codigo, 1)
        self.assertTrue(err.strip())

    def test_lesson_list_y_applicable_vacias(self):
        self.assertEqual(self.correr("lesson", "list", json_out=True)[0], 0)
        self.assertEqual(self.correr("lesson", "applicable", "--context", "skills", json_out=True)[0], 0)


class TestRechazosYUso(BaseCli):
    def test_protected_en_candidate_create(self):
        codigo, _ = self.crear_candidate("tools/x.py")
        self.assertEqual(codigo, 1)

    def test_argumentos_invalidos(self):
        for argv in ([], ["probe"], ["candidate"], ["no-existe"]):
            with self.subTest(argv=argv):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(cli.main(argv), 2)

    def test_evidence_mal_formado(self):
        codigo, _, err = self.correr("lesson", "add", "--change-id", "c", "--pattern", "p",
                                     "--recommendation", "r", "--context", "x", "--evidence", "solo-uno")
        self.assertEqual(codigo, 2)

    def test_politica_invalida_es_uso(self):
        self.crear_candidate()
        cid = json.loads(self.correr("candidate", "list", json_out=True)[1])[0]["candidate_id"]
        codigo, _, _ = self.correr("probe", "--candidate", cid, "--suite", str(self.suite), "--provider", "fake",
                                   "--probe-id", "p1", "--tie-policy", "inexistente")
        self.assertEqual(codigo, 2)

    def test_archivo_de_entrada_ilegible(self):
        codigo, _, err = self.correr("candidate", "create", "--base-surface", ACTIVO,
                                     "--content-file", str(self.aux / "no-existe.md"), "--hypothesis", "h")
        self.assertEqual(codigo, 2)
        self.assertNotIn(str(self.aux), err)
        codigo, _, _ = self.correr("cycle", "--proposals-file", str(self.aux / "no.json"),
                                   "--suite", str(self.suite), "--provider", "fake")
        self.assertEqual(codigo, 2)


class TestExitCodesDocumentados(BaseCli):
    """v0.15 Change 1 (T4): un test por exit code documentado de cli-harmessi-improve en inventory:
    0 ok (incluye cycle detenido por presupuesto) / 1 rechazo de regla o gate / 2 uso inválido /
    3 error de entorno inesperado."""

    def test_codigo_0_ok(self):
        self.assertEqual(self.crear_candidate()[0], 0)

    def test_codigo_0_cycle_detenido_por_presupuesto(self):
        dir_imp = self.raiz / ".harmessi" / "improvement"
        dir_imp.mkdir(parents=True, exist_ok=True)
        (dir_imp / "budget.json").write_text(json.dumps({"max_probe_cycles": 1, "max_candidates": 5}),
                                             encoding="utf-8")
        ruta = self.aux / "props.json"
        ruta.write_text(json.dumps([
            {"base_surface": ACTIVO, "content": f"# Skill\n{MARCA_CAND}\nvariante {i}\n", "hypothesis": f"h{i}",
             "provenance": {"proposer_kind": "script", "proposer_label": "t"}} for i in (1, 2, 3)]),
            encoding="utf-8")
        codigo, out, _ = self.correr("cycle", "--proposals-file", str(ruta), "--suite", str(self.suite),
                                     "--provider", "fake", json_out=True)
        self.assertEqual(codigo, 0)
        self.assertIsNotNone(json.loads(out)["detenido_por"])

    def test_codigo_1_rechazo_de_regla(self):
        self.assertEqual(self.crear_candidate("tools/x.py")[0], 1)

    def test_codigo_2_uso_invalido(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["no-existe"]), 2)

    def test_codigo_3_error_de_entorno_inesperado(self):
        with mock.patch.object(cli, "_cmd_budget_show", side_effect=OSError("disco roto"), create=True):
            # El despacho puede resolver el handler al armar el parser; si el parche no alcanza,
            # el test falla y se devuelve al Lead (el código 3 debe estar cubierto).
            codigo, _, err = self.correr("budget", "show")
        self.assertEqual(codigo, 3)
        self.assertNotIn("Traceback", err)


class TestCiclo(BaseCli):
    def propuestas(self, n):
        lista = [{"base_surface": ACTIVO, "content": f"# Skill\n{MARCA_CAND}\nvariante {i}\n",
                  "hypothesis": f"h{i}", "provenance": {"proposer_kind": "script", "proposer_label": "t"}}
                 for i in range(1, n + 1)]
        ruta = self.aux / "props.json"
        ruta.write_text(json.dumps(lista), encoding="utf-8")
        return ruta

    def test_ciclo_completo(self):
        codigo, out, _ = self.correr("cycle", "--proposals-file", str(self.propuestas(2)),
                                     "--suite", str(self.suite), "--provider", "fake", json_out=True)
        self.assertEqual(codigo, 0)
        datos = json.loads(out)
        self.assertIsNone(datos["detenido_por"])
        self.assertEqual(len(datos["resultados"]), 2)

    def test_ciclo_agotado_sale_0_con_detenido_por(self):
        dir_imp = self.raiz / ".harmessi" / "improvement"
        dir_imp.mkdir(parents=True, exist_ok=True)
        (dir_imp / "budget.json").write_text(json.dumps({"max_probe_cycles": 1, "max_candidates": 5}),
                                             encoding="utf-8")
        codigo, out, _ = self.correr("cycle", "--proposals-file", str(self.propuestas(3)),
                                     "--suite", str(self.suite), "--provider", "fake", json_out=True)
        self.assertEqual(codigo, 0)
        self.assertEqual(json.loads(out)["detenido_por"], "probe_cycles")

    def test_ciclo_propuestas_no_lista(self):
        ruta = self.aux / "obj.json"
        ruta.write_text("{}", encoding="utf-8")
        codigo, _, _ = self.correr("cycle", "--proposals-file", str(ruta), "--suite", str(self.suite),
                                   "--provider", "fake")
        self.assertEqual(codigo, 2)


if __name__ == "__main__":
    unittest.main()
