"""Test end-to-end de `tools.ds_profile.cli`. Repos sintéticos en
`tempfile.TemporaryDirectory()`: cada test hace `os.chdir` a ese directorio
(el CLI resuelve `repo_root = Path.cwd()` para `holdout_guard`) y restaura
el directorio original al terminar."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools.ds_profile.cli import main

try:
    import pyarrow  # noqa: F401

    _PYARROW_DISPONIBLE = True
except ImportError:
    _PYARROW_DISPONIBLE = False

_CSV_CONTENIDO = "id,nombre\n1,ana\n2,beto\n"


class _CliTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name).resolve()
        self._cwd_original = Path.cwd()
        self.addCleanup(os.chdir, str(self._cwd_original))
        os.chdir(self.dir)


class TestCliRunCSV(_CliTestCase):
    def setUp(self):
        super().setUp()
        self.ruta_csv = self.dir / "dataset.csv"
        self.ruta_csv.write_text(_CSV_CONTENIDO, encoding="utf-8")
        self.output_dir = self.dir / "salida"

    def test_corrida_exitosa_devuelve_0(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            codigo = main(["run", "--input", str(self.ruta_csv), "--output", str(self.output_dir)])
        self.assertEqual(codigo, 0)
        self.assertIn("profile.json escrito en", stdout.getvalue())
        archivos = list(self.output_dir.glob("*/profile.json"))
        self.assertEqual(len(archivos), 1)
        contenido = json.loads(archivos[0].read_text(encoding="utf-8"))
        self.assertEqual(contenido["formato_detectado"], "csv")

    def test_markdown_flag_genera_profile_md(self):
        codigo = main(["run", "--input", str(self.ruta_csv), "--output", str(self.output_dir), "--markdown"])
        self.assertEqual(codigo, 0)
        archivos_md = list(self.output_dir.glob("*/profile.md"))
        self.assertEqual(len(archivos_md), 1)

    def test_input_inexistente_devuelve_1(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            codigo = main(
                ["run", "--input", str(self.dir / "no_existe.csv"), "--output", str(self.output_dir)]
            )
        self.assertEqual(codigo, 1)
        self.assertNotEqual(stderr.getvalue().strip(), "")

    def test_extension_no_soportada_devuelve_1(self):
        ruta_txt = self.dir / "no_es_dataset.txt"
        ruta_txt.write_text("hola\n", encoding="utf-8")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            codigo = main(["run", "--input", str(ruta_txt), "--output", str(self.output_dir)])
        self.assertEqual(codigo, 1)

    def test_sin_subcomando_no_crashea_y_sale_con_codigo_no_cero(self):
        with self.assertRaises(SystemExit) as cm:
            main([])
        self.assertNotEqual(cm.exception.code, 0)

    def test_limites_personalizados_quedan_en_el_perfil(self):
        codigo = main(
            [
                "run",
                "--input",
                str(self.ruta_csv),
                "--output",
                str(self.output_dir),
                "--top-n",
                "3",
                "--seed",
                "99",
            ]
        )
        self.assertEqual(codigo, 0)
        archivos = list(self.output_dir.glob("*/profile.json"))
        contenido = json.loads(archivos[0].read_text(encoding="utf-8"))
        self.assertEqual(contenido["limites_aplicados"]["top_n"], 3)
        self.assertEqual(contenido["limites_aplicados"]["seed"], 99)


class TestCliParquetSinPyarrow(_CliTestCase):
    def test_dependencia_faltante_devuelve_3(self):
        ruta_parquet = self.dir / "dataset.parquet"
        ruta_parquet.write_bytes(b"contenido irrelevante")
        output_dir = self.dir / "salida"
        stderr = io.StringIO()
        with patch.dict(sys.modules, {"pyarrow": None, "pyarrow.parquet": None}):
            with redirect_stderr(stderr):
                codigo = main(["run", "--input", str(ruta_parquet), "--output", str(output_dir)])
        self.assertEqual(codigo, 3)
        self.assertIn("pyarrow", stderr.getvalue())
        self.assertFalse(output_dir.exists())


@unittest.skipUnless(_PYARROW_DISPONIBLE, "pyarrow no instalado")
class TestCliParquetConPyarrow(_CliTestCase):
    def test_corrida_exitosa_sobre_parquet_devuelve_0(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        ruta_parquet = self.dir / "dataset.parquet"
        tabla = pa.table({"id": [1, 2, 3], "valor": [1.5, 2.5, 3.5]})
        pq.write_table(tabla, ruta_parquet)
        output_dir = self.dir / "salida"

        codigo = main(["run", "--input", str(ruta_parquet), "--output", str(output_dir)])
        self.assertEqual(codigo, 0)
        archivos = list(output_dir.glob("*/profile.json"))
        self.assertEqual(len(archivos), 1)
        contenido = json.loads(archivos[0].read_text(encoding="utf-8"))
        self.assertEqual(contenido["formato_detectado"], "parquet")


class TestCliHoldout(_CliTestCase):
    def test_input_dentro_de_holdout_devuelve_2(self):
        (self.dir / ".claude").mkdir(parents=True, exist_ok=True)
        (self.dir / ".claude" / "guardrails.json").write_text(
            json.dumps({"version": 1, "holdouts": ["sealed/**"], "data_raw": ["data/raw/**"],
                        "secretos_extra": [], "write_scopes": {}, "excepciones": []}),
            encoding="utf-8",
        )
        (self.dir / "sealed").mkdir(parents=True, exist_ok=True)
        ruta_holdout = self.dir / "sealed" / "secreto.csv"
        ruta_holdout.write_text(_CSV_CONTENIDO, encoding="utf-8")
        output_dir = self.dir / "salida"

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            codigo = main(["run", "--input", str(ruta_holdout), "--output", str(output_dir)])
        self.assertEqual(codigo, 2)
        self.assertIn("holdout", stderr.getvalue().lower())
        self.assertFalse(output_dir.exists())

    def test_output_dentro_de_data_raw_devuelve_2(self):
        ruta_csv = self.dir / "dataset.csv"
        ruta_csv.write_text(_CSV_CONTENIDO, encoding="utf-8")
        output_dir = self.dir / "data" / "raw" / "salida"

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            codigo = main(["run", "--input", str(ruta_csv), "--output", str(output_dir)])
        self.assertEqual(codigo, 2)
        self.assertIn("data/raw", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
