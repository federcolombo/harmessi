"""Tests de `tools.ds_profile.column_stats`."""
from __future__ import annotations

import unittest
from datetime import datetime

from tools.ds_profile.column_stats import (
    AcumuladorColumna,
    clasificar_dtype,
    construir_metricas_columna,
    es_binario_numerico,
)


class TestClasificarDtype(unittest.TestCase):
    def test_lista_vacia_es_texto(self):
        self.assertEqual(clasificar_dtype([]), "texto")

    def test_booleano_true_false(self):
        self.assertEqual(clasificar_dtype(["true", "False", "TRUE", "false"]), "booleano")

    def test_0_1_clasifica_entero_no_booleano(self):
        # Corrección: {"0","1"} numérico YA NO clasifica como booleano --
        # queda como "entero" (y `construir_metricas_columna` agrega el
        # flag "binary_numeric", ver TestConstruirMetricasColumna).
        self.assertEqual(clasificar_dtype(["0", "1", "1", "0"]), "entero")

    def test_no_booleano_si_hay_un_valor_fuera_del_conjunto(self):
        self.assertNotEqual(clasificar_dtype(["true", "false", "maybe"]), "booleano")

    def test_entero_100_por_ciento(self):
        self.assertEqual(clasificar_dtype(["1", "2", "-3", "+4", "0"]), "entero")

    def test_entero_con_95_por_ciento(self):
        valores = ["1"] * 19 + ["abc"]  # 19/20 = 0.95
        self.assertEqual(clasificar_dtype(valores), "entero")

    def test_entero_por_debajo_del_umbral_cae_a_flotante_o_texto(self):
        valores = ["1"] * 9 + ["abc"] * 2  # 9/11 < 0.95
        self.assertNotEqual(clasificar_dtype(valores), "entero")

    def test_flotante(self):
        self.assertEqual(clasificar_dtype(["1.5", "2.25", "-3.0", "4"]), "flotante")

    def test_flotante_excluye_nan_e_infinity(self):
        # "nan"/"inf" parsean con float() de stdlib pero se excluyen a
        # propósito para no clasificar una columna de texto como flotante.
        self.assertEqual(clasificar_dtype(["nan", "inf", "-inf", "hola"]), "texto")

    def test_fecha_formato_fecha_simple(self):
        self.assertEqual(clasificar_dtype(["2024-01-01", "2024-02-15", "2024-03-30"]), "fecha")

    def test_fecha_formato_con_hora_t(self):
        self.assertEqual(clasificar_dtype(["2024-01-01T10:00:00", "2024-01-02T11:30:00"]), "fecha")

    def test_fecha_formato_con_espacio(self):
        self.assertEqual(clasificar_dtype(["2024-01-01 10:00:00", "2024-01-02 11:30:00"]), "fecha")

    def test_fecha_formato_con_z(self):
        self.assertEqual(clasificar_dtype(["2024-01-01T10:00:00Z", "2024-01-02T11:30:00Z"]), "fecha")

    def test_fecha_formato_con_microsegundos_t(self):
        # `datetime.datetime` nativo de Parquet con microsegundos (columnas
        # `timestamp`) -- hallazgo de `data-science-reviewer`.
        self.assertEqual(
            clasificar_dtype(["2026-01-15T10:30:00.123456", "2026-01-16T11:00:00.000001"]),
            "fecha",
        )

    def test_fecha_formato_con_microsegundos_espacio(self):
        self.assertEqual(
            clasificar_dtype(["2026-01-15 10:30:00.123456", "2026-01-16 11:00:00.000001"]),
            "fecha",
        )

    def test_texto_default(self):
        self.assertEqual(clasificar_dtype(["hola", "mundo", "che"]), "texto")

    def test_tipos_nativos_no_string_bool_parquet(self):
        # Simula valores nativos de Parquet (bool real, no "true"/"false").
        self.assertEqual(clasificar_dtype([True, False, True]), "booleano")

    def test_tipos_nativos_no_string_int_parquet(self):
        self.assertEqual(clasificar_dtype([1, 2, 3, 4]), "entero")

    def test_tipos_nativos_no_string_float_parquet(self):
        self.assertEqual(clasificar_dtype([1.5, 2.5, 3.5]), "flotante")


class TestEsBinarioNumerico(unittest.TestCase):
    def test_entero_0_1_es_binario_numerico(self):
        self.assertTrue(es_binario_numerico(["0", "1", "1", "0"], "entero"))

    def test_flotante_0_0_1_0_es_binario_numerico(self):
        self.assertTrue(es_binario_numerico(["0.0", "1.0", "1.0"], "flotante"))

    def test_un_solo_valor_no_es_binario_numerico(self):
        self.assertFalse(es_binario_numerico(["0", "0", "0"], "entero"))

    def test_dtype_no_numerico_nunca_es_binario_numerico(self):
        self.assertFalse(es_binario_numerico(["true", "false"], "booleano"))
        self.assertFalse(es_binario_numerico(["hola", "che"], "texto"))

    def test_valores_fuera_de_0_1_no_es_binario_numerico(self):
        self.assertFalse(es_binario_numerico(["0", "1", "2"], "entero"))


class TestAcumuladorColumna(unittest.TestCase):
    def test_cuenta_nulos_string_vacio_y_none(self):
        acumulador = AcumuladorColumna("col")
        for v in ["a", "", None, "b"]:
            acumulador.observar(v)
        self.assertEqual(acumulador.total, 4)
        self.assertEqual(acumulador.nulos, 2)
        self.assertEqual(acumulador.filas_no_nulas, 2)

    def test_min_max_numerico(self):
        acumulador = AcumuladorColumna("col")
        for v in ["5", "1", "9", "3"]:
            acumulador.observar(v)
        self.assertEqual(acumulador.min_numerico, 1.0)
        self.assertEqual(acumulador.max_numerico, 9.0)

    def test_media_y_std_welford(self):
        acumulador = AcumuladorColumna("col")
        for v in ["1", "2", "3", "4", "5"]:
            acumulador.observar(v)
        self.assertAlmostEqual(acumulador.media, 3.0)
        # Desviación estándar poblacional de [1,2,3,4,5] = sqrt(2)
        self.assertAlmostEqual(acumulador.desviacion_estandar(), 2 ** 0.5)

    def test_std_con_un_solo_valor_es_cero(self):
        acumulador = AcumuladorColumna("col")
        acumulador.observar("42")
        self.assertEqual(acumulador.desviacion_estandar(), 0.0)

    def test_std_sin_valores_numericos_es_none(self):
        acumulador = AcumuladorColumna("col")
        acumulador.observar("hola")
        self.assertIsNone(acumulador.desviacion_estandar())

    def test_min_max_fecha(self):
        acumulador = AcumuladorColumna("col")
        for v in ["2024-01-05", "2024-01-01", "2024-01-03"]:
            acumulador.observar(v)
        self.assertEqual(acumulador.min_fecha.isoformat(), "2024-01-01T00:00:00")
        self.assertEqual(acumulador.max_fecha.isoformat(), "2024-01-05T00:00:00")


class TestConstruirMetricasColumna(unittest.TestCase):
    def _acumular(self, valores):
        acumulador = AcumuladorColumna("col")
        for v in valores:
            acumulador.observar(v)
        return acumulador

    def test_columna_entera_incluye_min_max_media_std_mediana_cuantiles(self):
        valores = ["1", "2", "3", "4", "5"]
        acumulador = self._acumular(valores)
        detalle = construir_metricas_columna("col", acumulador, valores, "exacta", top_n=20)
        self.assertEqual(detalle["dtype"], "entero")
        self.assertEqual(detalle["min"], 1)
        self.assertEqual(detalle["max"], 5)
        self.assertIsInstance(detalle["min"], int)
        self.assertAlmostEqual(detalle["media"], 3.0)
        self.assertAlmostEqual(detalle["std"], 2 ** 0.5)
        self.assertAlmostEqual(detalle["mediana"], 3.0)
        self.assertIn("p50", detalle["cuantiles"])
        self.assertLessEqual(detalle["cuantiles"]["p25"], detalle["cuantiles"]["p50"])
        self.assertLessEqual(detalle["cuantiles"]["p50"], detalle["cuantiles"]["p75"])

    def test_columna_fecha_incluye_fecha_min_max_no_min_max_numerico(self):
        valores = ["2024-01-01", "2024-01-05", "2024-01-03"]
        acumulador = self._acumular(valores)
        detalle = construir_metricas_columna("fecha_evento", acumulador, valores, "exacta", top_n=20)
        self.assertEqual(detalle["dtype"], "fecha")
        self.assertEqual(detalle["fecha_min"], "2024-01-01T00:00:00")
        self.assertEqual(detalle["fecha_max"], "2024-01-05T00:00:00")
        self.assertNotIn("min", detalle)

    def test_columna_fecha_con_microsegundos_string_iso_t(self):
        # Hallazgo de `data-science-reviewer`: sin los formatos con `.%f` en
        # `FORMATOS_FECHA`, esto caía a `texto` y perdía `fecha_min`/`fecha_max`.
        valores = ["2026-01-15T10:30:00.123456", "2026-01-16T11:00:00.654321"]
        acumulador = self._acumular(valores)
        detalle = construir_metricas_columna("ts", acumulador, valores, "exacta", top_n=20)
        self.assertEqual(detalle["dtype"], "fecha")
        self.assertEqual(detalle["fecha_min"], "2026-01-15T10:30:00.123456")
        self.assertEqual(detalle["fecha_max"], "2026-01-16T11:00:00.654321")

    def test_columna_fecha_con_microsegundos_datetime_nativo(self):
        # `datetime.datetime` nativo (típico de un lector Parquet), no string.
        valores = [
            datetime(2026, 1, 15, 10, 30, 0, 123456),
            datetime(2026, 1, 16, 11, 0, 0, 1),
            datetime(2026, 1, 14, 9, 0, 0, 0),
        ]
        acumulador = self._acumular(valores)
        detalle = construir_metricas_columna("ts", acumulador, valores, "exacta", top_n=20)
        self.assertEqual(detalle["dtype"], "fecha")
        self.assertEqual(detalle["fecha_min"], "2026-01-14T09:00:00")
        self.assertEqual(detalle["fecha_max"], "2026-01-16T11:00:00.000001")

    def test_flag_constante(self):
        valores = ["a", "a", "a"]
        acumulador = self._acumular(valores)
        detalle = construir_metricas_columna("col", acumulador, valores, "exacta", top_n=20)
        self.assertIn("constante", detalle["flags"])

    def test_flag_casi_constante(self):
        valores = ["a"] * 99 + ["b"]
        acumulador = self._acumular(valores)
        detalle = construir_metricas_columna("col", acumulador, valores, "exacta", top_n=20)
        self.assertIn("casi_constante", detalle["flags"])
        self.assertNotIn("constante", detalle["flags"])

    def test_flag_alta_cardinalidad(self):
        valores = [str(i) for i in range(100)]
        acumulador = self._acumular(valores)
        detalle = construir_metricas_columna("col", acumulador, valores, "exacta", top_n=20)
        self.assertIn("alta_cardinalidad", detalle["flags"])

    def test_flag_posible_id_por_nombre(self):
        valores = ["a", "a", "b"]  # ni siquiera es única
        acumulador = self._acumular(valores)
        for nombre in ("id", "user_id", "uuid", "GUID"):
            with self.subTest(nombre=nombre):
                detalle = construir_metricas_columna(nombre, acumulador, valores, "exacta", top_n=20)
                self.assertIn("posible_id", detalle["flags"])

    def test_flag_posible_id_por_unicidad(self):
        valores = [str(i) for i in range(10)]
        acumulador = self._acumular(valores)
        detalle = construir_metricas_columna("columna_cualquiera", acumulador, valores, "exacta", top_n=20)
        self.assertIn("posible_id", detalle["flags"])

    def test_flag_posible_problema_tipo(self):
        valores = ["1", "2", "3", "4", "abc"]  # 4/5 = 0.8 >= 0.5, pero < 0.95 (no es entero)
        acumulador = self._acumular(valores)
        detalle = construir_metricas_columna("col", acumulador, valores, "exacta", top_n=20)
        self.assertEqual(detalle["dtype"], "texto")
        self.assertIn("posible_problema_tipo", detalle["flags"])

    def test_columna_texto_normal_sin_flags_de_tipo(self):
        valores = ["rojo", "verde", "azul", "rojo"]
        acumulador = self._acumular(valores)
        detalle = construir_metricas_columna("color", acumulador, valores, "exacta", top_n=20)
        self.assertEqual(detalle["dtype"], "texto")
        self.assertNotIn("posible_problema_tipo", detalle["flags"])

    def test_top_valores_respeta_top_n(self):
        valores = [str(i) for i in range(50)]
        acumulador = self._acumular(valores)
        detalle = construir_metricas_columna("col", acumulador, valores, "exacta", top_n=5)
        self.assertLessEqual(len(detalle["top_valores"]), 5)

    def test_unique_exactitud_propagada(self):
        valores = ["a", "b", "a"]
        acumulador = self._acumular(valores)
        detalle = construir_metricas_columna("col", acumulador, valores, "muestreada", top_n=20)
        self.assertEqual(detalle["unique"]["exactitud"], "muestreada")
        self.assertEqual(detalle["exactitud_estadisticos"], "muestreada")
        self.assertEqual(detalle["nulls"]["exactitud"], "exacta")

    def test_binary_numeric_entero_flag_y_estadisticas(self):
        valores = ["0", "0", "1", "1"]
        acumulador = self._acumular(valores)
        detalle = construir_metricas_columna("col", acumulador, valores, "exacta", top_n=20)
        self.assertEqual(detalle["dtype"], "entero")
        self.assertIn("binary_numeric", detalle["flags"])
        self.assertNotIn("constante", detalle["flags"])
        self.assertEqual(detalle["min"], 0)
        self.assertEqual(detalle["max"], 1)
        self.assertIsInstance(detalle["min"], int)
        self.assertIsInstance(detalle["max"], int)
        self.assertAlmostEqual(detalle["media"], 0.5)
        self.assertAlmostEqual(detalle["std"], 0.5)
        self.assertAlmostEqual(detalle["mediana"], 0.5)
        self.assertAlmostEqual(detalle["cuantiles"]["p25"], 0.0)
        self.assertAlmostEqual(detalle["cuantiles"]["p50"], 0.5)
        self.assertAlmostEqual(detalle["cuantiles"]["p75"], 1.0)
        self.assertAlmostEqual(detalle["cuantiles"]["p95"], 1.0)
        self.assertAlmostEqual(detalle["cuantiles"]["p99"], 1.0)

    def test_binary_numeric_flotante_flag_y_estadisticas(self):
        valores = ["0.0", "0.0", "1.0", "1.0"]
        acumulador = self._acumular(valores)
        detalle = construir_metricas_columna("col", acumulador, valores, "exacta", top_n=20)
        self.assertEqual(detalle["dtype"], "flotante")
        self.assertIn("binary_numeric", detalle["flags"])
        self.assertEqual(detalle["min"], 0.0)
        self.assertEqual(detalle["max"], 1.0)
        self.assertAlmostEqual(detalle["media"], 0.5)
        self.assertAlmostEqual(detalle["std"], 0.5)
        self.assertAlmostEqual(detalle["mediana"], 0.5)
        self.assertAlmostEqual(detalle["cuantiles"]["p25"], 0.0)
        self.assertAlmostEqual(detalle["cuantiles"]["p75"], 1.0)

    def test_booleano_true_false_sin_binary_numeric_flag(self):
        valores = ["True", "FALSE", "true", "False"]
        acumulador = self._acumular(valores)
        detalle = construir_metricas_columna("col", acumulador, valores, "exacta", top_n=20)
        self.assertEqual(detalle["dtype"], "booleano")
        self.assertNotIn("binary_numeric", detalle["flags"])

    def test_constante_valor_unico_0_sin_binary_numeric_flag(self):
        valores = ["0", "0", "0"]
        acumulador = self._acumular(valores)
        detalle = construir_metricas_columna("col", acumulador, valores, "exacta", top_n=20)
        self.assertEqual(detalle["dtype"], "entero")
        self.assertIn("constante", detalle["flags"])
        self.assertNotIn("binary_numeric", detalle["flags"])

    def test_columna_vacia_sin_flags_de_cardinalidad(self):
        acumulador = self._acumular([])
        detalle = construir_metricas_columna("col", acumulador, [], "exacta", top_n=20)
        self.assertEqual(detalle["dtype"], "texto")
        self.assertEqual(detalle["flags"], [])
        self.assertEqual(detalle["nulls"]["count"], 0)
        self.assertEqual(detalle["nulls"]["pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
