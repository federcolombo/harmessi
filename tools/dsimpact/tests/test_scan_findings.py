"""Tests end-to-end de `tools.dsimpact.scan.ejecutar_scan` sobre repos Git
temporales reales -- cobertura de los criterios de aceptación de `spec.md`."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsimpact import scan as scan_mod  # noqa: E402
from dsimpact.git_source import GitSourceError  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, text=True)


def _crear_repo() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="dsimpact_scan_test_"))
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "inicial")
    return repo


def _commit_todo(repo: Path, mensaje: str) -> None:
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", mensaje)


def _notebook(celdas_code: list) -> str:
    cells = [{"cell_type": "code", "source": [c], "outputs": [], "execution_count": None} for c in celdas_code]
    return json.dumps({"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5})


class TestFuncionModificadaConsumidaEnTest(unittest.TestCase):
    def test_finding_test_o_assert_reference(self):
        repo = _crear_repo()
        (repo / "features.py").write_text(
            "def build_features(df):\n    return df\n", encoding="utf-8"
        )
        (repo / "tests").mkdir()
        (repo / "tests" / "test_features.py").write_text(
            "from features import build_features\n\n"
            "def test_build_features():\n    assert build_features(1) == 1\n",
            encoding="utf-8",
        )
        _commit_todo(repo, "base")

        (repo / "features.py").write_text(
            "def build_features(df):\n    return df.copy()\n", encoding="utf-8"
        )
        _commit_todo(repo, "cambio")

        resultado = scan_mod.ejecutar_scan(repo, "HEAD~1", False)
        self.assertEqual(len(resultado["changed"]), 1)
        self.assertEqual(resultado["changed"][0]["path"], "features.py")
        symbols = resultado["changed"][0]["symbols"]
        self.assertEqual(symbols[0]["name"], "build_features")
        self.assertEqual(symbols[0]["change"], "modificado")

        consumers = {f["consumer"] for f in resultado["findings"]}
        self.assertIn("tests/test_features.py", consumers)
        evidence_types = {f["evidence_type"] for f in resultado["findings"] if f["consumer"] == "tests/test_features.py"}
        self.assertTrue(evidence_types & {"ASSERT_REFERENCE", "TEST_REFERENCE", "IMPORT_REFERENCE"})


class TestConstanteConsumidaEnNotebook(unittest.TestCase):
    def test_finding_con_cell_index(self):
        repo = _crear_repo()
        (repo / "config.py").write_text("COLUMNAS = ['a']\n", encoding="utf-8")
        (repo / "analisis.ipynb").write_text(
            _notebook(["# celda 0\n", "from config import COLUMNAS\nprint(COLUMNAS)\n"]),
            encoding="utf-8",
        )
        _commit_todo(repo, "base")

        (repo / "config.py").write_text("COLUMNAS = ['a', 'b']\n", encoding="utf-8")
        _commit_todo(repo, "cambio")

        resultado = scan_mod.ejecutar_scan(repo, "HEAD~1", False)
        findings_nb = [f for f in resultado["findings"] if f["consumer"] == "analisis.ipynb"]
        self.assertTrue(findings_nb)
        self.assertIn("#cell:1", findings_nb[0]["location"])


class TestStringContractPyYJson(unittest.TestCase):
    def test_dos_findings_string_contract_y_config(self):
        repo = _crear_repo()
        (repo / "schema.py").write_text("COLUMNAS = ['id']\n", encoding="utf-8")
        (repo / "consumidor.py").write_text("columna = 'monto_total'\n", encoding="utf-8")
        (repo / "config.json").write_text(json.dumps({"target": "otra_cosa"}), encoding="utf-8")
        _commit_todo(repo, "base")

        (repo / "schema.py").write_text("COLUMNAS = ['id', 'monto_total']\n", encoding="utf-8")
        (repo / "config.json").write_text(json.dumps({"target": "monto_total"}), encoding="utf-8")
        _commit_todo(repo, "cambio")

        resultado = scan_mod.ejecutar_scan(repo, "HEAD~1", False)
        tipos = {(f["consumer"], f["evidence_type"]) for f in resultado["findings"]}
        self.assertIn(("consumidor.py", "STRING_CONTRACT_REFERENCE"), tipos)
        self.assertIn(("config.json", "CONFIG_REFERENCE"), tipos)


class TestTokenGenerico(unittest.TestCase):
    def test_token_generico_no_dispara_busqueda(self):
        repo = _crear_repo()
        (repo / "modulo.py").write_text("id = 1\n", encoding="utf-8")
        (repo / "consumidor.py").write_text("id = 99\n", encoding="utf-8")
        _commit_todo(repo, "base")

        (repo / "modulo.py").write_text("id = 2\n", encoding="utf-8")
        _commit_todo(repo, "cambio")

        resultado = scan_mod.ejecutar_scan(repo, "HEAD~1", False)
        self.assertEqual(resultado["changed"][0]["symbols"][0]["name"], "id")
        self.assertEqual(resultado["findings"], [])


class TestArchivoEliminado(unittest.TestCase):
    def test_path_reference(self):
        repo = _crear_repo()
        (repo / "viejo_modulo.py").write_text("VALOR = 1\n", encoding="utf-8")
        (repo / "consumidor.py").write_text("ruta = 'viejo_modulo.py'\n", encoding="utf-8")
        _commit_todo(repo, "base")

        (repo / "viejo_modulo.py").unlink()
        _commit_todo(repo, "elimina")

        resultado = scan_mod.ejecutar_scan(repo, "HEAD~1", False)
        deleted_entries = [c for c in resultado["changed"] if c["status"] == "deleted"]
        self.assertEqual(len(deleted_entries), 1)
        path_findings = [f for f in resultado["findings"] if f["evidence_type"] == "PATH_REFERENCE"]
        self.assertTrue(path_findings)
        self.assertEqual(path_findings[0]["consumer"], "consumidor.py")

    def test_nombre_de_modulo_generico_no_genera_findings_ruidosos(self):
        # R7 aplica también a los path-reference targets de R4: "data.py"
        # deriva el nombre de módulo "data", que ES un token genérico
        # (`generic_filter.es_generico("data")` es True) -- no debe disparar
        # búsqueda global (evitaría cientos de matches de la palabra "data"
        # en cualquier .py/.json/.md del repo).
        from dsimpact import generic_filter

        self.assertTrue(generic_filter.es_generico("data"))

        repo = _crear_repo()
        (repo / "data.py").write_text("VALOR = 1\n", encoding="utf-8")
        (repo / "consumidor.py").write_text(
            "data = {'nada_que_ver': 1}\n"
            "def procesar_data():\n"
            "    return data\n",
            encoding="utf-8",
        )
        _commit_todo(repo, "base")

        (repo / "data.py").unlink()
        _commit_todo(repo, "elimina")

        resultado = scan_mod.ejecutar_scan(repo, "HEAD~1", False)
        deleted_entries = [c for c in resultado["changed"] if c["status"] == "deleted"]
        self.assertEqual(len(deleted_entries), 1)
        self.assertEqual(deleted_entries[0]["path"], "data.py")
        # El único path-reference target no filtrado es el path literal
        # completo "data.py" (tiene "/" -- no, en este caso es raíz, pero
        # conserva extensión y no es un token de la denylist); el nombre de
        # módulo derivado "data" SÍ está filtrado -- no debe aparecer ningún
        # finding disparado por la palabra suelta "data".
        self.assertEqual(resultado["findings"], [])


class TestRefInvalida(unittest.TestCase):
    def test_lanza_git_source_error(self):
        repo = _crear_repo()
        with self.assertRaises(GitSourceError):
            scan_mod.ejecutar_scan(repo, "no-existe-esta-ref", False)


class TestContenidoIlegibleFailClosed(unittest.TestCase):
    """v0.13 R3: un contenido ilegible no se convierte en «0 consumidores»."""

    def test_modified_con_working_tree_ilegible_lanza(self):
        from unittest import mock

        repo = _crear_repo()
        (repo / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        _commit_todo(repo, "agrega a.py")
        (repo / "a.py").write_text("def f():\n    return 2\n", encoding="utf-8")
        with mock.patch.object(Path, "read_text", side_effect=PermissionError("denegado")):
            with self.assertRaises(GitSourceError):
                scan_mod.ejecutar_scan(repo, "HEAD", False)

    def test_git_no_disponible_lanza_en_scan(self):
        from unittest import mock

        repo = _crear_repo()
        with mock.patch("dsguard.repo.subprocess.run", side_effect=FileNotFoundError("git")):
            with self.assertRaises(GitSourceError):
                scan_mod.ejecutar_scan(repo, None, True)


class TestNoAnalizados(unittest.TestCase):
    """Fix HIGH-1/HIGH-2: nada queda invisible."""

    def _repo_con_modulo(self) -> Path:
        repo = _crear_repo()
        (repo / "m.py").write_text("def calcular_puntaje_sintetico():\n    return 1\n", encoding="utf-8")
        (repo / "ok.py").write_text(
            "from m import calcular_puntaje_sintetico\ncalcular_puntaje_sintetico()\n", encoding="utf-8"
        )
        (repo / "roto.py").write_text("def (:\n", encoding="utf-8")
        (repo / "roto.json").write_text("{no es json", encoding="utf-8")
        (repo / "borrado.py").write_text("from m import calcular_puntaje_sintetico\n", encoding="utf-8")
        _commit_todo(repo, "base")
        (repo / "borrado.py").unlink()  # tracked borrado del working tree
        (repo / "m.py").write_text("def calcular_puntaje_sintetico(x):\n    return x\n", encoding="utf-8")
        return repo

    def test_consumidores_no_analizados_listados_y_findings_parciales(self):
        resultado = scan_mod.ejecutar_scan(self._repo_con_modulo(), "HEAD", False)
        lista = resultado["summary"]["consumidores_no_analizados"]
        motivos = {e["path"]: e["motivo"] for e in lista}
        self.assertEqual(motivos.get("roto.py"), "SyntaxError")
        self.assertIn("roto.json", motivos)
        self.assertEqual([e["path"] for e in lista], sorted(motivos))
        for e in lista:
            self.assertEqual(set(e), {"path", "motivo"})
            self.assertNotIn(":\\", e["path"])
        self.assertIn("ok.py", {f["consumer"] for f in resultado["findings"]})  # parciales conservados

    def test_cli_texto_no_concluyente_sin_findings(self):
        from dsimpact import cli as cli_mod

        resultado = {
            "since": "HEAD", "staged": False, "changed": [], "findings": [],
            "summary": {"consumers": 0, "findings": 0, "changed_files": 1, "changed_items": 1,
                        "consumidores_no_analizados": [{"path": "x.py", "motivo": "SyntaxError"}],
                        "cambios_no_analizados": []},
        }
        texto = cli_mod.formatear_texto(resultado)
        self.assertNotIn("(ningún consumidor potencial detectado)", texto)
        self.assertIn("resultado no concluyente: 1 consumidor(es) no analizado(s)", texto)
        self.assertIn("x.py (SyntaxError)", texto)

    def test_cli_texto_sin_no_analizados_conserva_mensaje(self):
        from dsimpact import cli as cli_mod

        resultado = {"since": "HEAD", "staged": False, "changed": [], "findings": [], "summary": {}}
        self.assertIn("(ningún consumidor potencial detectado)", cli_mod.formatear_texto(resultado))

    def test_excepcion_inesperada_en_fuente_marca_parse_error(self):
        from unittest import mock

        repo = _crear_repo()
        (repo / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        _commit_todo(repo, "base")
        (repo / "m.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
        with mock.patch("dsimpact.py_changes.diff_simbolos", side_effect=ValueError("boom")):
            resultado = scan_mod.ejecutar_scan(repo, "HEAD", False)
        self.assertTrue(resultado["changed"][0]["parse_error"])
        self.assertEqual(resultado["summary"]["cambios_no_analizados"], [{"path": "m.py", "motivo": "ValueError"}])

    def test_since_con_git_ausente_lanza_git_source_error(self):
        from unittest import mock

        repo = _crear_repo()
        with mock.patch("dsguard.repo.subprocess.run", side_effect=FileNotFoundError("git")):
            with self.assertRaises(GitSourceError):
                scan_mod.ejecutar_scan(repo, "HEAD", False)

    def test_staged_status_u_modified_con_blob_ausente_es_fail_closed(self):
        from dsimpact import git_source

        repo = _crear_repo()
        with self.assertRaises(GitSourceError):
            git_source.contenido_before(repo, None, True, "no_esta.py", status=git_source.STATUS_MODIFIED)

    def test_mensaje_de_git_sin_ruta_absoluta_del_repo(self):
        from dsimpact import git_source

        repo = _crear_repo()
        with self.assertRaises(GitSourceError) as ctx:
            git_source.contenido_before(repo, "HEAD", False, "no_esta.py", status=git_source.STATUS_MODIFIED)
        self.assertNotIn(str(repo), str(ctx.exception))
        self.assertNotIn(str(repo).replace("\\", "/"), str(ctx.exception))


class TestSinDiff(unittest.TestCase):
    def test_since_head_vacio(self):
        repo = _crear_repo()
        resultado = scan_mod.ejecutar_scan(repo, "HEAD", False)
        self.assertEqual(resultado["changed"], [])
        self.assertEqual(resultado["findings"], [])

    def test_staged_indice_vacio(self):
        repo = _crear_repo()
        resultado = scan_mod.ejecutar_scan(repo, None, True)
        self.assertEqual(resultado["changed"], [])
        self.assertEqual(resultado["findings"], [])


class TestDeterminismoYOrden(unittest.TestCase):
    def test_dos_corridas_mismo_resultado(self):
        repo = _crear_repo()
        (repo / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        (repo / "c1.py").write_text("from m import f\nf()\n", encoding="utf-8")
        (repo / "c2.py").write_text("from m import f\nf()\n", encoding="utf-8")
        _commit_todo(repo, "base")
        (repo / "m.py").write_text("def f():\n    return 2\n", encoding="utf-8")
        _commit_todo(repo, "cambio")

        r1 = scan_mod.ejecutar_scan(repo, "HEAD~1", False)
        r2 = scan_mod.ejecutar_scan(repo, "HEAD~1", False)
        self.assertEqual(r1, r2)

        consumers_orden = [f["consumer"] for f in r1["findings"]]
        self.assertEqual(consumers_orden, sorted(consumers_orden))


if __name__ == "__main__":
    unittest.main()
