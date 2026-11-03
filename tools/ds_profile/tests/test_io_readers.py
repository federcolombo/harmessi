"""Tests de `tools.ds_profile.io_readers`. Datasets sintéticos en
`tempfile.TemporaryDirectory()`."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.ds_profile import io_readers

try:
    import pyarrow  # noqa: F401

    _PYARROW_DISPONIBLE = True
except ImportError:
    _PYARROW_DISPONIBLE = False


class TestAbrirLector(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_extension_no_soportada_levanta_formato_no_soportado(self):
        ruta = self.dir / "dataset.txt"
        ruta.write_text("a,b\n1,2\n", encoding="utf-8")
        with self.assertRaises(io_readers.FormatoNoSoportadoError):
            io_readers.abrir_lector(ruta)

    def test_csv_devuelve_lector_csv(self):
        ruta = self.dir / "dataset.csv"
        ruta.write_text("a,b\n1,2\n", encoding="utf-8")
        lector = io_readers.abrir_lector(ruta)
        self.assertIsInstance(lector, io_readers.LectorCSV)


class TestLectorCSV(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.ruta = self.dir / "dataset.csv"
        self.ruta.write_text("id,nombre,edad\n1,ana,30\n2,beto,25\n3,cami,\n", encoding="utf-8")

    def test_schema_devuelve_columnas_del_encabezado(self):
        lector = io_readers.LectorCSV(self.ruta)
        self.assertEqual(lector.schema(), {"id": "str", "nombre": "str", "edad": "str"})

    def test_filas_exactas_cuenta_filas_de_datos_sin_el_header(self):
        # self.ruta tiene 3 filas de datos (ana, beto, cami) + 1 header.
        lector = io_readers.LectorCSV(self.ruta)
        self.assertEqual(lector.filas_exactas(), 3)
        self.assertIsInstance(lector.filas_exactas(), int)

    def test_filas_exactas_no_se_ve_afectada_por_iter_filas_previo(self):
        # Pasada independiente: llamar `iter_filas()` antes no cambia el
        # resultado de `filas_exactas()` (cada una abre el archivo de nuevo).
        lector = io_readers.LectorCSV(self.ruta)
        list(lector.iter_filas())
        self.assertEqual(lector.filas_exactas(), 3)

    def test_filas_exactas_dataset_grande_cuenta_correctamente(self):
        ruta_grande = self.dir / "grande.csv"
        lineas = ["id,valor\n"] + [f"{i},{i}\n" for i in range(500)]
        ruta_grande.write_text("".join(lineas), encoding="utf-8")
        lector = io_readers.LectorCSV(ruta_grande)
        self.assertEqual(lector.filas_exactas(), 500)

    def test_tamano_bytes_coincide_con_filesystem(self):
        lector = io_readers.LectorCSV(self.ruta)
        self.assertEqual(lector.tamano_bytes(), self.ruta.stat().st_size)

    def test_iter_filas_streamea_dicts_de_strings(self):
        lector = io_readers.LectorCSV(self.ruta)
        filas = list(lector.iter_filas())
        self.assertEqual(len(filas), 3)
        self.assertEqual(filas[0], {"id": "1", "nombre": "ana", "edad": "30"})
        self.assertEqual(filas[2], {"id": "3", "nombre": "cami", "edad": ""})

    def test_iter_filas_es_generador_no_lista_materializada(self):
        lector = io_readers.LectorCSV(self.ruta)
        resultado = lector.iter_filas()
        self.assertTrue(hasattr(resultado, "__next__"))

    def test_encabezado_vacio_no_rompe(self):
        ruta_vacia = self.dir / "vacio.csv"
        ruta_vacia.write_text("", encoding="utf-8")
        lector = io_readers.LectorCSV(ruta_vacia)
        self.assertEqual(lector.schema(), {})
        self.assertEqual(list(lector.iter_filas()), [])
        self.assertEqual(lector.filas_exactas(), 0)

    def test_header_sin_filas_de_datos_filas_exactas_es_0(self):
        ruta_solo_header = self.dir / "solo_header.csv"
        ruta_solo_header.write_text("a,b,c\n", encoding="utf-8")
        lector = io_readers.LectorCSV(ruta_solo_header)
        self.assertEqual(lector.filas_exactas(), 0)

    def test_filas_exactas_consistente_con_iter_filas_con_lineas_en_blanco(self):
        # Líneas en blanco intercaladas en el cuerpo (y una al final): tanto
        # `csv.reader` crudo como `csv.DictReader` las ven al parsear, pero
        # `DictReader` las descarta (`row == []`) antes de yieldear un dict.
        # `filas_exactas()` debe contar lo mismo que `iter_filas()` yieldea,
        # nunca más.
        ruta_con_blancos = self.dir / "con_blancos.csv"
        ruta_con_blancos.write_text(
            "id,nombre\n1,ana\n\n2,beto\n\n\n3,cami\n\n",
            encoding="utf-8",
        )
        lector = io_readers.LectorCSV(ruta_con_blancos)
        filas_yieldeadas = list(lector.iter_filas())
        self.assertEqual(lector.filas_exactas(), len(filas_yieldeadas))
        self.assertEqual(lector.filas_exactas(), 3)


@unittest.skipUnless(_PYARROW_DISPONIBLE, "pyarrow no instalado")
class TestLectorParquet(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.ruta = self.dir / "dataset.parquet"

        import pyarrow as pa
        import pyarrow.parquet as pq

        tabla = pa.table({"id": [1, 2, 3], "valor": [10.5, 20.5, 30.5]})
        pq.write_table(tabla, self.ruta)

    def test_abrir_lector_devuelve_lector_parquet(self):
        lector = io_readers.abrir_lector(self.ruta)
        self.assertIsInstance(lector, io_readers.LectorParquet)

    def test_filas_exactas_viene_de_metadata(self):
        lector = io_readers.LectorParquet(self.ruta)
        self.assertEqual(lector.filas_exactas(), 3)

    def test_schema_incluye_columnas(self):
        lector = io_readers.LectorParquet(self.ruta)
        self.assertEqual(set(lector.schema().keys()), {"id", "valor"})

    def test_iter_filas_streamea_por_row_group(self):
        lector = io_readers.LectorParquet(self.ruta)
        filas = list(lector.iter_filas())
        self.assertEqual(len(filas), 3)
        self.assertEqual(filas[0]["id"], 1)


class TestLectorParquetSinPyarrow(unittest.TestCase):
    """Fuerza el `ImportError` con `unittest.mock.patch` (no depende de que
    el entorno real carezca de `pyarrow`) para ser determinista en
    cualquier entorno -- incluido este, donde `pyarrow` no está instalado."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.ruta = self.dir / "dataset.parquet"
        self.ruta.write_bytes(b"contenido irrelevante: el ImportError ocurre antes de leerlo")

    def test_mensaje_nombra_pyarrow_explicitamente(self):
        with patch.dict(sys.modules, {"pyarrow": None, "pyarrow.parquet": None}):
            with self.assertRaises(io_readers.DependenciaFaltanteError) as ctx:
                io_readers.abrir_lector(self.ruta)
        self.assertIn("pyarrow", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
