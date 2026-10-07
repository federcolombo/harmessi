"""Corrective C (`ds-profile-bounded-memory`): memoria acotada por diseño.

Las pruebas verifican invariantes DETERMINISTAS (decisión previa, tope de
retención, batch_size, determinismo, metadata, errores); nunca RSS ni
`tracemalloc`.
"""
from __future__ import annotations

import io
import json
import os
import random
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from tools.ds_profile import column_stats, io_readers, report, sampling
from tools.ds_profile.cli import main

try:
    import pyarrow  # noqa: F401

    _PYARROW = True
except ImportError:
    _PYARROW = False


class _LectorSintetico:
    """Lector falso, perezoso: genera filas sin materializarlas. Registra
    cuántas filas se consumieron (para probar que la decisión es previa)."""

    def __init__(self, filas, columnas, bytes_=1000, falla_en=None, filas_meta=None):
        self._filas = filas
        self._columnas = [f"c{i}" for i in range(columnas)]
        self._bytes = bytes_
        self._falla_en = falla_en
        self._filas_meta = filas if filas_meta is None else filas_meta
        self.consumidas = 0

    def schema(self):
        return {c: "str" for c in self._columnas}

    def filas_exactas(self):
        return self._filas_meta

    def tamano_bytes(self):
        return self._bytes

    def iter_filas(self):
        rnd = random.Random(1)
        for i in range(self._filas):
            if self._falla_en is not None and i == self._falla_en:
                raise RuntimeError("reader roto")
            self.consumidas += 1
            yield {
                c: (None if (i + j) % 17 == 0 else (i * (j + 1)) % 997 if j % 3 else f"t{rnd.randint(0, 50)}")
                for j, c in enumerate(self._columnas)
            }


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name).resolve()
        self.ruta = self.dir / "datos.csv"
        self.ruta.write_text("x\n1\n", encoding="utf-8")  # existe; el lector es falso
        self.out = self.dir / "out"

    def perfil(self, lector, **kw):
        with patch.object(io_readers, "abrir_lector", return_value=lector):
            return report.generar_perfil(self.ruta, self.out, **kw)["perfil"]


class TestPlanPrevio(unittest.TestCase):
    def test_pequeno_es_exacto(self):
        plan = sampling.decidir_plan(1000, 100, 5, 500, 2_000_000)
        self.assertFalse(plan["muestreado"])
        self.assertIsNone(plan["motivo"])
        self.assertEqual(plan["tamano_muestra"], 0)

    def test_caso_real_620570x27_con_defaults_es_muestreado_por_memoria(self):
        # 20 MB comprimidos, 620.570 filas, 27 columnas, defaults de la CLI.
        plan = sampling.decidir_plan(20 * 1024 * 1024, 620_570, 27, 500, 2_000_000)
        self.assertTrue(plan["muestreado"])
        self.assertEqual(plan["motivo"], "memoria_estimada")
        self.assertGreater(plan["estimado_bytes"], plan["presupuesto_bytes"])
        # La muestra cabe en el presupuesto.
        self.assertLessEqual(plan["tamano_muestra"] * 27 * sampling.BYTES_POR_CELDA, plan["presupuesto_bytes"])

    def test_motivos_legacy_se_conservan(self):
        self.assertEqual(sampling.decidir_plan(600 * 1024 * 1024, 10, 2, 500, 2_000_000)["motivo"], "tamano_archivo")
        self.assertEqual(sampling.decidir_plan(10, 50, 2, 500, 10)["motivo"], "filas")

    def test_transicion_exacta_en_el_umbral_de_memoria(self):
        # presupuesto 1 MiB, 1 columna => 1048576 // 96 = 10922 filas caben.
        limite = (1 * 1024 * 1024) // sampling.BYTES_POR_CELDA
        self.assertFalse(sampling.decidir_plan(10, limite, 1, 1, 2_000_000)["muestreado"])
        self.assertTrue(sampling.decidir_plan(10, limite + 1, 1, 1, 2_000_000)["muestreado"])

    def test_filas_desconocidas_no_estima(self):
        plan = sampling.decidir_plan(10, None, 3, 500, 2_000_000)
        self.assertIsNone(plan["estimado_bytes"])
        self.assertFalse(plan["muestreado"])

    def test_tamano_muestra_acotado_por_presupuesto_y_maximo(self):
        plan = sampling.decidir_plan(10, 10_000_000, 27, 500, 50_000_000)
        self.assertLessEqual(plan["tamano_muestra"], sampling.TAMANO_MUESTRA_MAXIMO)
        plan_bajo = sampling.decidir_plan(10, 10_000_000, 27, 1, 50_000_000)
        self.assertEqual(plan_bajo["tamano_muestra"], sampling.TAMANO_MUESTRA_MINIMO)

    def test_tamano_muestra_respeta_max_filas_exactas(self):
        self.assertEqual(sampling.decidir_plan(10, 100, 2, 500, 5)["tamano_muestra"], 5)

    def test_fuente_demasiado_ancha_falla_controlado(self):
        with self.assertRaises(sampling.PresupuestoInsuficienteError) as ctx:
            sampling.decidir_plan(10, 10**9, 25_000, 1, 2_000_000)
        self.assertIn("columnas", str(ctx.exception))

    def test_decidir_modo_legacy_intacto(self):
        self.assertTrue(sampling.decidir_modo(tamano_bytes=1, filas_exactas=10, max_mb_exactos=500, max_filas_exactas=5))
        self.assertFalse(sampling.decidir_modo(tamano_bytes=1000, filas_exactas=100, max_mb_exactos=500, max_filas_exactas=2_000_000))


class TestDecisionAntesDeAcumular(_Base):
    def test_muestreado_se_decide_antes_de_consumir_filas(self):
        lector = _LectorSintetico(filas=3000, columnas=4)
        orden = []
        real = sampling.decidir_plan

        def espia(*a, **k):
            orden.append(("plan", lector.consumidas))
            return real(*a, **k)

        with patch.object(sampling, "decidir_plan", side_effect=espia):
            perfil = self.perfil(lector, max_mb_exactos=0, max_filas_exactas=500)
        self.assertEqual(orden, [("plan", 0)])
        self.assertTrue(perfil["sampling"]["activo"])

    def test_memoria_estimada_activa_muestreo_sin_flags_de_filas(self):
        lector = _LectorSintetico(filas=3_000, columnas=27)
        perfil = self.perfil(lector, max_mb_exactos=1)
        s = perfil["sampling"]
        self.assertTrue(s["activo"])
        self.assertEqual(s["motivo"], "memoria_estimada")
        self.assertEqual(s["filas_observadas"], 3_000)
        self.assertEqual(s["version_algoritmo"], "bounded_v1")
        self.assertEqual(s["presupuesto_bytes"], 1 * 1024 * 1024)
        self.assertGreater(s["estimado_bytes_exactos"], s["presupuesto_bytes"])
        self.assertLessEqual(s["tamano_muestra"], sampling.decidir_plan(1000, 3_000, 27, 1, 2_000_000)["tamano_muestra"])


class TestRetencionAcotada(_Base):
    def test_reservoir_nunca_supera_el_tope(self):
        maximos = []
        original = sampling.ReservoirSampler.observar

        def espia(self_, fila):
            original(self_, fila)
            maximos.append(len(self_._muestra))

        lector = _LectorSintetico(filas=8000, columnas=6)
        with patch.object(sampling.ReservoirSampler, "observar", espia):
            perfil = self.perfil(lector, max_mb_exactos=1, max_filas_exactas=1500)
        self.assertEqual(max(maximos), 1500)
        self.assertEqual(perfil["sampling"]["tamano_muestra"], 1500)
        self.assertEqual(perfil["filas"], 8000)

    def test_modo_muestreado_no_retiene_listas_de_valores_ni_digests(self):
        capturado = {}
        original = report._procesar_fila

        def espia(fila, acumuladores, orden, valores_completos, reservoir, digests):
            capturado["valores"] = valores_completos
            capturado["digests"] = digests
            return original(fila, acumuladores, orden, valores_completos, reservoir, digests)

        with patch.object(report, "_procesar_fila", espia):
            self.perfil(_LectorSintetico(filas=2000, columnas=3), max_mb_exactos=0, max_filas_exactas=100)
        self.assertIsNone(capturado["valores"])
        self.assertIsNone(capturado["digests"])

    def test_modo_exacto_retiene_digests_no_tuplas(self):
        capturado = {}
        original = report._procesar_fila

        def espia(fila, acumuladores, orden, valores_completos, reservoir, digests):
            capturado["digests"] = digests
            return original(fila, acumuladores, orden, valores_completos, reservoir, digests)

        with patch.object(report, "_procesar_fila", espia):
            self.perfil(_LectorSintetico(filas=300, columnas=3))
        self.assertTrue(all(isinstance(d, bytes) and len(d) == 16 for d in capturado["digests"]))

    def test_acumulador_no_retiene_valores(self):
        acum = column_stats.AcumuladorColumna("c")
        for i in range(5000):
            acum.observar(str(i))
        retenidos = [v for v in vars(acum).values() if isinstance(v, (list, dict, set))]
        self.assertTrue(all(len(v) <= 2 for v in retenidos))


class TestAcumuladoresExactos(unittest.TestCase):
    CASOS = [
        [],
        ["true", "False", "TRUE"],
        ["0", "1", "1", "0"],
        ["0", "1", "2"],
        ["0.0", "1.0"],
        ["1", "2", "-3", "+4", "0"],
        ["1"] * 19 + ["abc"],
        ["1"] * 9 + ["abc"] * 2,
        ["1.5", "2.25", "x"] * 10,
        ["2024-01-01", "2024-02-01"],
        ["2024-01-01", "2024-01-02 10:00:00", "hola"],
        ["nan", "inf", "Infinity"],
        ["a", "b", "c"],
        ["7"] * 30,
        ["1", " 1 ", "01"],
        [1, 2, 3, 4.5],
        [True, False, True],
    ]

    def test_equivalencia_con_funciones_de_referencia(self):
        for valores in self.CASOS:
            with self.subTest(valores=valores[:4]):
                acum = column_stats.AcumuladorColumna("c")
                for v in valores:
                    acum.observar(v)
                dtype = column_stats.clasificar_dtype(valores)
                self.assertEqual(acum.clasificar_dtype(), dtype)
                self.assertEqual(acum.es_binario_numerico(dtype), column_stats.es_binario_numerico(valores, dtype))
                self.assertAlmostEqual(
                    acum.fraccion_numero_o_fecha(), column_stats._fraccion_numero_o_fecha(valores)
                )

    def test_equivalencia_aleatoria(self):
        rnd = random.Random(7)
        pool = ["0", "1", "2", "3.5", "abc", "true", "false", "2024-01-01", "-7", " ", "1e3"]
        for _ in range(200):
            valores = [rnd.choice(pool) for _ in range(rnd.randint(0, 40))]
            no_nulos = [v for v in valores if v.strip() != ""]
            acum = column_stats.AcumuladorColumna("c")
            for v in valores:
                acum.observar(v)
            dtype = column_stats.clasificar_dtype(no_nulos)
            self.assertEqual(acum.clasificar_dtype(), dtype, valores)
            self.assertEqual(acum.es_binario_numerico(dtype), column_stats.es_binario_numerico(no_nulos, dtype), valores)

    def test_dtype_exacto_en_modo_muestreado(self):
        # 3% de basura textual: el dtype sale de TODAS las filas aun con muestra chica.
        filas = ["id,v"] + [f"{i},{'x' if i % 33 == 0 else i}" for i in range(1, 3001)]
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "d.csv"
            ruta.write_text("\n".join(filas) + "\n", encoding="utf-8")
            exacto = report.generar_perfil(ruta, Path(tmp) / "o1")["perfil"]
            muestreado = report.generar_perfil(ruta, Path(tmp) / "o2", max_filas_exactas=200)["perfil"]
        self.assertFalse(exacto["sampling"]["activo"])
        self.assertTrue(muestreado["sampling"]["activo"])
        for col in ("id", "v"):
            self.assertEqual(muestreado["columnas_detalle"][col]["dtype"], exacto["columnas_detalle"][col]["dtype"])
            self.assertEqual(muestreado["columnas_detalle"][col]["nulls"], exacto["columnas_detalle"][col]["nulls"])
        self.assertEqual(muestreado["columnas_detalle"]["id"]["min"], exacto["columnas_detalle"]["id"]["min"])
        self.assertEqual(muestreado["columnas_detalle"]["id"]["unique"]["exactitud"], "muestreada")
        self.assertEqual(exacto["columnas_detalle"]["id"]["unique"]["exactitud"], "exacta")


class TestFlagsCardinalidadMuestreado(unittest.TestCase):
    def test_denominador_es_la_muestra(self):
        acum = column_stats.AcumuladorColumna("user")
        valores = [str(i) for i in range(10_000)]
        for v in valores:
            acum.observar(v)
        muestra = valores[:500]
        detalle = column_stats.construir_metricas_columna("user", acum, muestra, "muestreada", 5)
        self.assertIn("alta_cardinalidad", detalle["flags"])
        self.assertNotIn("casi_constante", detalle["flags"])

    def test_error_de_programacion_no_se_disfraza_de_archivo_corrupto(self):
        with patch.object(report, "_procesar_fila", side_effect=KeyError("bug")):
            with self.assertRaises(KeyError):
                _Base.perfil(self._base(), _LectorSintetico(filas=5, columnas=2))

    def _base(self):
        b = _Base("perfil")
        b.setUp()
        self.addCleanup(b._tmp.cleanup)
        return b


class TestDeterminismo(_Base):
    def _normalizado(self, perfil):
        p = json.loads(json.dumps(perfil))
        p.pop("created_utc")
        return p

    def test_misma_entrada_y_config_mismo_perfil(self):
        a = self.perfil(_LectorSintetico(filas=5000, columnas=5), max_mb_exactos=0, max_filas_exactas=700, seed=3)
        b = self.perfil(_LectorSintetico(filas=5000, columnas=5), max_mb_exactos=0, max_filas_exactas=700, seed=3)
        self.assertEqual(self._normalizado(a), self._normalizado(b))

    def test_semilla_distinta_cambia_la_muestra(self):
        a = self.perfil(_LectorSintetico(filas=5000, columnas=5), max_mb_exactos=0, max_filas_exactas=700, seed=3)
        b = self.perfil(_LectorSintetico(filas=5000, columnas=5), max_mb_exactos=0, max_filas_exactas=700, seed=4)
        self.assertEqual(a["sampling"]["semilla"], 3)
        self.assertNotEqual(a["columnas_detalle"], b["columnas_detalle"])


class TestCompatibilidadPequena(_Base):
    def test_pequeno_exacto_conserva_schema_y_agrega_metadata(self):
        perfil = self.perfil(_LectorSintetico(filas=50, columnas=3))
        s = perfil["sampling"]
        self.assertFalse(s["activo"])
        self.assertEqual(s["metodo"], "reservoir_v1")
        self.assertIsNone(s["tamano_muestra"])
        self.assertIsNone(s["motivo"])
        self.assertEqual(s["filas_observadas"], 50)
        for detalle in perfil["columnas_detalle"].values():
            self.assertEqual(detalle["exactitud_estadisticos"], "exacta")
        self.assertEqual(perfil["calidad"]["duplicados_fila"]["exactitud"], "exacta")

    def test_duplicados_exactos(self):
        filas = ["a,b"] + ["1,x"] * 5 + ["2,y", "3,z"]
        ruta = self.dir / "dup.csv"
        ruta.write_text("\n".join(filas) + "\n", encoding="utf-8")
        perfil = report.generar_perfil(ruta, self.out)["perfil"]
        self.assertEqual(perfil["calidad"]["duplicados_fila"]["valor"], 4)

    def test_markdown_muestra_motivo(self):
        perfil = self.perfil(_LectorSintetico(filas=2000, columnas=3), max_mb_exactos=0, max_filas_exactas=100)
        self.assertIn("motivo=", report.generar_markdown(perfil))


class TestErrores(_Base):
    def test_reader_error_a_mitad_es_controlado_y_no_escribe(self):
        with self.assertRaises(report.LecturaFallidaError) as ctx:
            self.perfil(_LectorSintetico(filas=100, columnas=2, falla_en=40))
        msg = str(ctx.exception)
        self.assertIn("40 filas", msg)
        self.assertIn("corrupto", msg)
        self.assertFalse(self.out.exists())

    def test_memoria_insuficiente_sugiere_bajar_presupuesto(self):
        lector = _LectorSintetico(filas=100, columnas=2)
        with patch.object(_LectorSintetico, "iter_filas", side_effect=MemoryError()):
            with self.assertRaises(report.LecturaFallidaError) as ctx:
                self.perfil(lector)
        self.assertIn("--max-mb-exactos", str(ctx.exception))

    def test_cli_csv_malformado_exit_4(self):
        ruta = self.dir / "malo.csv"
        ruta.write_bytes(b"a,b\n1,\xff\xfe\n")
        err = io.StringIO()
        cwd = os.getcwd()
        os.chdir(self.dir)
        try:
            with redirect_stderr(err):
                codigo = main(["run", "--input", str(ruta), "--output", str(self.out)])
        finally:
            os.chdir(cwd)
        self.assertEqual(codigo, 4)
        self.assertIn("malo.csv", err.getvalue())
        self.assertFalse(self.out.exists())

    def test_cli_fuente_ancha_exit_4(self):
        lector = _LectorSintetico(filas=10, columnas=25_000, bytes_=10**9)
        err = io.StringIO()
        cwd = os.getcwd()
        os.chdir(self.dir)
        try:
            with patch.object(io_readers, "abrir_lector", return_value=lector), redirect_stderr(err):
                codigo = main(["run", "--input", str(self.ruta), "--output", str(self.out)])
        finally:
            os.chdir(cwd)
        self.assertEqual(codigo, 4)
        self.assertIn("columnas", err.getvalue())

    def test_limite_extremadamente_bajo_sigue_acotado(self):
        perfil = self.perfil(_LectorSintetico(filas=4000, columnas=3), max_mb_exactos=0, max_filas_exactas=2_000_000)
        self.assertTrue(perfil["sampling"]["activo"])
        self.assertLessEqual(perfil["sampling"]["tamano_muestra"], sampling.TAMANO_MUESTRA_MINIMO)


@unittest.skipUnless(_PYARROW, "pyarrow no instalado")
class TestParquetAcotado(_Base):
    def setUp(self):
        super().setUp()
        import pyarrow as pa
        import pyarrow.parquet as pq

        n = 30_000
        self.ruta = self.dir / "grande.parquet"
        tabla = pa.table(
            {
                "id": list(range(n)),
                "valor": [float(i % 101) for i in range(n)],
                "cat": [f"k{i % 13}" for i in range(n)],
            }
        )
        pq.write_table(tabla, self.ruta, row_group_size=30_000)

    def test_lee_por_batches_acotados_sin_read_table(self):
        import pyarrow.parquet as pq

        lector = io_readers.LectorParquet(self.ruta)
        tamanos = []
        original = lector._parquet_file.iter_batches

        def espia(*a, **k):
            self.assertEqual(k.get("batch_size"), io_readers.tamano_batch(3))
            for batch in original(*a, **k):
                tamanos.append(batch.num_rows)
                yield batch

        with patch.object(pq, "read_table", side_effect=AssertionError("read_table prohibido")), patch.object(
            lector._parquet_file, "iter_batches", espia
        ):
            filas = sum(1 for _ in lector.iter_filas())
        self.assertEqual(filas, 30_000)
        self.assertLessEqual(max(tamanos), io_readers.BATCH_SIZE)
        self.assertGreater(len(tamanos), 1)

    def test_batch_se_achica_en_fuentes_anchas(self):
        self.assertEqual(io_readers.tamano_batch(3), io_readers.BATCH_SIZE)
        self.assertLessEqual(io_readers.tamano_batch(5000) * 5000, io_readers.MAX_CELDAS_POR_BATCH)
        self.assertGreaterEqual(io_readers.tamano_batch(10**6), 256)

    def test_perfil_parquet_muestreado_por_presupuesto_es_acotado_y_reproducible(self):
        kw = dict(max_mb_exactos=1, max_filas_exactas=2_000_000, seed=5)
        a = report.generar_perfil(self.ruta, self.dir / "o1", **kw)["perfil"]
        b = report.generar_perfil(self.ruta, self.dir / "o2", **kw)["perfil"]
        self.assertTrue(a["sampling"]["activo"])
        self.assertEqual(a["sampling"]["motivo"], "memoria_estimada")
        self.assertEqual(a["filas"], 30_000)
        self.assertLessEqual(a["sampling"]["tamano_muestra"], 3641)
        self.assertEqual(a["columnas_detalle"], b["columnas_detalle"])
        self.assertEqual(a["columnas_detalle"]["id"]["min"], 0)
        self.assertEqual(a["columnas_detalle"]["id"]["max"], 29_999)
        self.assertEqual(a["columnas_detalle"]["id"]["nulls"]["exactitud"], "exacta")

    def test_perfil_parquet_pequeno_sigue_exacto(self):
        perfil = report.generar_perfil(self.ruta, self.dir / "o3")["perfil"]
        # 30000 x 3 x 96 = 8.6 MB < 500 MiB => exacto.
        self.assertFalse(perfil["sampling"]["activo"])
        self.assertEqual(perfil["columnas_detalle"]["cat"]["unique"]["count"], 13)

    def test_parquet_truncado_exit_4(self):
        malo = self.dir / "roto.parquet"
        malo.write_bytes(self.ruta.read_bytes()[:200])
        err = io.StringIO()
        cwd = os.getcwd()
        os.chdir(self.dir)
        try:
            with redirect_stderr(err):
                codigo = main(["run", "--input", str(malo), "--output", str(self.out)])
        finally:
            os.chdir(cwd)
        self.assertEqual(codigo, 4)
        self.assertIn("roto.parquet", err.getvalue())


if __name__ == "__main__":
    unittest.main()
