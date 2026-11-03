"""B-11 (`v015-ds-core-debt`): lectura columnar de dos pases en `ds_profile`.

Invariantes DETERMINISTAS: el perfil columnar es idéntico al del camino por
filas (salvo `sampling.modo_lectura` y `created_utc`); los fallbacks a filas
(lector sin `iter_columna`, schema anidado, modo muestreado, CSV); errores
de lectura -> `LecturaFallidaError`. Los tests con pyarrow real van con
`skipUnless`; el camino de dos pases se cubre sin pyarrow con un lector sintético.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.ds_profile import io_readers, report, sampling

try:
    import pyarrow  # noqa: F401

    _PYARROW = True
except ImportError:
    _PYARROW = False


FILAS = [
    {"id": i, "grupo": ("a" if i % 3 else "b"), "valor": (None if i % 7 == 0 else float(i % 5)), "texto": ("" if i % 11 == 0 else f"t{i % 4}")}
    for i in range(200)
] + [
    # filas duplicadas exactas y NaN, para digests y estadísticos
    {"id": 1, "grupo": "a", "valor": 1.0, "texto": "t1"},
    {"id": 1, "grupo": "a", "valor": 1.0, "texto": "t1"},
    {"id": 999, "grupo": "z", "valor": float("nan"), "texto": "t9"},
]
SCHEMA = {"id": "int64", "grupo": "string", "valor": "double", "texto": "string"}


class _LectorBase:
    def __init__(self, filas=FILAS, schema=SCHEMA, falla_columna=None, falla_filas_en=None):
        self._filas = filas
        self._schema = dict(schema)
        self._falla_columna = falla_columna
        self._falla_filas_en = falla_filas_en
        self.llamadas_iter_filas = 0
        self.columnas_leidas = []

    def schema(self):
        return dict(self._schema)

    def filas_exactas(self):
        return len(self._filas)

    def tamano_bytes(self):
        return 1000

    def iter_filas(self):
        self.llamadas_iter_filas += 1
        for i, fila in enumerate(self._filas):
            if self._falla_filas_en is not None and i == self._falla_filas_en:
                raise RuntimeError("reader roto")
            yield dict(fila)


class _LectorColumnar(_LectorBase):
    """Expone `iter_columna` (proyección por columna)."""

    def iter_columna(self, nombre):
        self.columnas_leidas.append(nombre)
        for i, fila in enumerate(self._filas):
            if self._falla_columna == nombre and i == 5:
                raise RuntimeError("columna rota")
            yield fila.get(nombre)


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name).resolve()
        self.ruta = self.dir / "datos.parquet"
        self.ruta.write_bytes(b"x")  # existe; el lector es falso
        self.out = self.dir / "out"

    def perfil(self, lector, **kw):
        with patch.object(io_readers, "abrir_lector", return_value=lector):
            return report.generar_perfil(self.ruta, self.out, **kw)["perfil"]


def _normalizado(perfil: dict) -> str:
    p = json.loads(json.dumps(perfil))
    p.pop("created_utc")
    p["sampling"].pop("modo_lectura")
    return json.dumps(p, sort_keys=True)


class TestCaminoDeDosPases(_Base):
    def test_lector_con_iter_columna_usa_columnar(self):
        lector = _LectorColumnar()
        perfil = self.perfil(lector)
        self.assertEqual(perfil["sampling"]["modo_lectura"], "columnar_v1")
        self.assertEqual(lector.columnas_leidas, list(SCHEMA))
        self.assertEqual(lector.llamadas_iter_filas, 1)  # pase 1 (digests)

    def test_perfil_identico_al_camino_por_filas(self):
        columnar = self.perfil(_LectorColumnar())
        filas = self.perfil(_LectorBase())
        self.assertEqual(filas["sampling"]["modo_lectura"], "filas")
        self.assertEqual(_normalizado(columnar), _normalizado(filas))
        # Filas base 0..199 son únicas por `id`. La fila id=1 es (1, "a", 1.0, "t1");
        # las dos filas extra la repiten => 3 copias = 2 duplicados. (None y "" colapsan
        # igual en el digest por `fila_a_tupla`, comportamiento preexistente, pero acá
        # no generan filas iguales porque `id` las distingue.)
        self.assertEqual(columnar["calidad"]["duplicados_fila"]["valor"], 2)
        self.assertEqual(columnar["filas"], len(FILAS))

    def test_top_valores_conserva_orden_de_aparicion(self):
        columnar = self.perfil(_LectorColumnar())
        filas = self.perfil(_LectorBase())
        self.assertEqual(
            json.dumps(columnar["columnas_detalle"]["texto"], sort_keys=True),
            json.dumps(filas["columnas_detalle"]["texto"], sort_keys=True),
        )

    def test_estimacion_por_dtype_en_el_perfil(self):
        perfil = self.perfil(_LectorColumnar())
        self.assertEqual(perfil["sampling"]["estimacion"], "dtype_v1")
        esperado = sampling.decidir_plan(1000, len(FILAS), len(SCHEMA), 500, 2_000_000, schema=SCHEMA)
        self.assertEqual(perfil["sampling"]["estimado_bytes_exactos"], esperado["estimado_bytes"])
        self.assertEqual(perfil["sampling"]["version_algoritmo"], "bounded_v1")


class TestFallbackAFilas(_Base):
    def test_lector_sin_iter_columna(self):
        self.assertEqual(self.perfil(_LectorBase())["sampling"]["modo_lectura"], "filas")

    def test_schema_anidado_cae_a_filas(self):
        schema = dict(SCHEMA, texto="list<item: string>")
        filas = [dict(f, texto=[f["texto"]]) for f in FILAS]
        lector = _LectorColumnar(filas=filas, schema=schema)
        perfil = self.perfil(lector)
        self.assertEqual(perfil["sampling"]["modo_lectura"], "filas")
        self.assertEqual(lector.columnas_leidas, [])

    def test_modo_muestreado_cae_a_filas(self):
        lector = _LectorColumnar()
        perfil = self.perfil(lector, max_mb_exactos=0, max_filas_exactas=50)
        self.assertTrue(perfil["sampling"]["activo"])
        self.assertEqual(perfil["sampling"]["modo_lectura"], "filas")
        self.assertEqual(lector.columnas_leidas, [])

    def test_nombres_de_columna_repetidos_caen_a_filas(self):
        class _Repetidos(_LectorColumnar):
            def nombres_unicos(self):
                return False

        lector = _Repetidos()
        perfil = self.perfil(lector)
        self.assertEqual(perfil["sampling"]["modo_lectura"], "filas")
        self.assertEqual(lector.columnas_leidas, [])

    def test_nombre_de_columna_con_punto_cae_a_filas(self):
        schema = {"a.b": "int64", "c": "string"}
        filas = [{"a.b": i, "c": f"t{i}"} for i in range(5)]
        lector = _LectorColumnar(filas=filas, schema=schema)
        perfil = self.perfil(lector)
        self.assertEqual(perfil["sampling"]["modo_lectura"], "filas")
        self.assertEqual(lector.columnas_leidas, [])

    def test_csv_cae_a_filas(self):
        ruta = self.dir / "d.csv"
        ruta.write_text("a,b\n1,x\n2,y\n", encoding="utf-8")
        perfil = report.generar_perfil(ruta, self.dir / "o")["perfil"]
        self.assertEqual(perfil["sampling"]["modo_lectura"], "filas")
        self.assertEqual(perfil["sampling"]["estimacion"], "global_v1")


class TestErroresColumnar(_Base):
    def test_error_en_columna_es_lectura_fallida(self):
        with self.assertRaises(report.LecturaFallidaError) as ctx:
            self.perfil(_LectorColumnar(falla_columna="grupo"))
        self.assertIn("grupo", str(ctx.exception))
        self.assertIn("corrupto", str(ctx.exception))
        self.assertFalse(self.out.exists())

    def test_error_en_pase_de_digests_es_lectura_fallida(self):
        with self.assertRaises(report.LecturaFallidaError) as ctx:
            self.perfil(_LectorColumnar(falla_filas_en=10))
        self.assertIn("10 filas", str(ctx.exception))
        self.assertFalse(self.out.exists())

    def test_memoria_en_columna_sugiere_bajar_presupuesto(self):
        lector = _LectorColumnar()
        with patch.object(_LectorColumnar, "iter_columna", side_effect=MemoryError()):
            with self.assertRaises(report.LecturaFallidaError) as ctx:
                self.perfil(lector)
        self.assertIn("--max-mb-exactos", str(ctx.exception))


@unittest.skipUnless(_PYARROW, "pyarrow no instalado")
class TestParquetReal(unittest.TestCase):
    def setUp(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name).resolve()
        self.ruta = self.dir / "datos.parquet"
        tabla = pa.table({c: [f.get(c) for f in FILAS] for c in SCHEMA})
        pq.write_table(tabla, self.ruta, row_group_size=64)

    def test_iter_columna_proyecta_una_columna(self):
        lector = io_readers.LectorParquet(self.ruta)
        self.addCleanup(lector.close)  # libera el handle (Windows no borra archivos abiertos)
        self.assertTrue(lector.nombres_unicos())
        valores = list(lector.iter_columna("id"))
        self.assertEqual(valores, [f["id"] for f in FILAS])

    def test_equivalencia_columnar_vs_filas(self):
        columnar = report.generar_perfil(self.ruta, self.dir / "o1")["perfil"]
        self.assertEqual(columnar["sampling"]["modo_lectura"], "columnar_v1")
        with patch.object(report, "_puede_columnar", return_value=False):
            filas = report.generar_perfil(self.ruta, self.dir / "o2")["perfil"]
        self.assertEqual(filas["sampling"]["modo_lectura"], "filas")
        self.assertEqual(_normalizado(columnar), _normalizado(filas))

    def test_iter_columna_error_de_lectura_es_controlado(self):
        malo = self.dir / "roto.parquet"
        malo.write_bytes(self.ruta.read_bytes()[:200])
        with self.assertRaises(report.LecturaFallidaError):
            report.generar_perfil(malo, self.dir / "o3")


if __name__ == "__main__":
    unittest.main()
