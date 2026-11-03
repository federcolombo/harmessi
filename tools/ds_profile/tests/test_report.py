"""Tests de `tools.ds_profile.report` (orquestación end-to-end sobre CSV
sintético). Parquet se cubre en `test_cli.py`/`test_io_readers.py` bajo
`skipUnless pyarrow`."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.ds_profile import report
from tools.ds_profile.io_readers import FormatoNoSoportadoError

_CSV_CONTENIDO = (
    "id,nombre,edad,activo,fecha_registro\n"
    "1,ana,30,true,2024-01-01\n"
    "2,beto,25,false,2024-01-02\n"
    "3,cami,,true,2024-01-03\n"
    "1,ana,30,true,2024-01-01\n"
)


class TestGenerarPerfilCSV(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.ruta_csv = self.dir / "clientes.csv"
        self.ruta_csv.write_text(_CSV_CONTENIDO, encoding="utf-8")
        self.output_dir = self.dir / "salida"

    def test_estructura_general_del_perfil(self):
        resultado = report.generar_perfil(self.ruta_csv, self.output_dir)
        perfil = resultado["perfil"]
        self.assertEqual(perfil["schema_version"], 1)
        self.assertEqual(perfil["tool"], "ds_profile")
        self.assertEqual(perfil["formato_detectado"], "csv")
        self.assertEqual(perfil["filas"], 4)
        self.assertEqual(perfil["columnas"], 5)
        self.assertEqual(perfil["tamano_bytes"], self.ruta_csv.stat().st_size)
        self.assertEqual(perfil["fingerprint"]["algoritmo"], "sha256/bin/v1")
        self.assertEqual(set(perfil["schema"].keys()), {"id", "nombre", "edad", "activo", "fecha_registro"})

    def test_escribe_profile_json_en_output_profile_id(self):
        resultado = report.generar_perfil(self.ruta_csv, self.output_dir)
        ruta_json = resultado["ruta_profile_json"]
        self.assertTrue(ruta_json.exists())
        self.assertEqual(ruta_json.parent.parent, self.output_dir)
        self.assertEqual(ruta_json.name, "profile.json")
        contenido = json.loads(ruta_json.read_text(encoding="utf-8"))
        self.assertEqual(contenido["profile_id"], resultado["perfil"]["profile_id"])

    def test_profile_id_explicito_se_respeta(self):
        resultado = report.generar_perfil(self.ruta_csv, self.output_dir, profile_id="mi-perfil")
        self.assertEqual(resultado["perfil"]["profile_id"], "mi-perfil")
        self.assertEqual(resultado["ruta_profile_json"], self.output_dir / "mi-perfil" / "profile.json")

    def test_dtype_por_columna(self):
        perfil = report.generar_perfil(self.ruta_csv, self.output_dir)["perfil"]
        schema = perfil["schema"]
        self.assertEqual(schema["id"], "entero")
        self.assertEqual(schema["nombre"], "texto")
        self.assertEqual(schema["edad"], "entero")
        self.assertEqual(schema["activo"], "booleano")
        self.assertEqual(schema["fecha_registro"], "fecha")

    def test_nulls_de_columna_con_vacios(self):
        perfil = report.generar_perfil(self.ruta_csv, self.output_dir)["perfil"]
        self.assertEqual(perfil["columnas_detalle"]["edad"]["nulls"]["count"], 1)

    def test_fecha_min_max(self):
        perfil = report.generar_perfil(self.ruta_csv, self.output_dir)["perfil"]
        detalle = perfil["columnas_detalle"]["fecha_registro"]
        self.assertEqual(detalle["fecha_min"], "2024-01-01T00:00:00")
        self.assertEqual(detalle["fecha_max"], "2024-01-03T00:00:00")

    def test_columna_id_marcada_posible_id(self):
        perfil = report.generar_perfil(self.ruta_csv, self.output_dir)["perfil"]
        self.assertIn("posible_id", perfil["columnas_detalle"]["id"]["flags"])

    def test_duplicados_de_fila(self):
        perfil = report.generar_perfil(self.ruta_csv, self.output_dir)["perfil"]
        # Fila 4 es copia exacta de la fila 1 -> 4 filas totales, 3 distintas.
        self.assertEqual(perfil["calidad"]["duplicados_fila"], {"valor": 1, "exactitud": "exacta"})

    def test_sampling_inactivo_por_defecto(self):
        perfil = report.generar_perfil(self.ruta_csv, self.output_dir)["perfil"]
        self.assertFalse(perfil["sampling"]["activo"])
        self.assertIsNone(perfil["sampling"]["tamano_muestra"])
        self.assertEqual(perfil["sampling"]["metodo"], "reservoir_v1")
        self.assertEqual(perfil["sampling"]["semilla"], 42)
        for detalle in perfil["columnas_detalle"].values():
            self.assertEqual(detalle["exactitud_estadisticos"], "exacta")

    def test_sampling_activo_via_max_mb_exactos_cero(self):
        # max_mb_exactos=0 -> cualquier archivo con bytes > 0 dispara modo
        # muestreado, forma determinista de probarlo sin necesitar un
        # dataset real de cientos de MB.
        perfil = report.generar_perfil(self.ruta_csv, self.output_dir, max_mb_exactos=0, seed=7)["perfil"]
        self.assertTrue(perfil["sampling"]["activo"])
        self.assertEqual(perfil["sampling"]["semilla"], 7)
        self.assertIsNotNone(perfil["sampling"]["tamano_muestra"])
        for detalle in perfil["columnas_detalle"].values():
            self.assertEqual(detalle["exactitud_estadisticos"], "muestreada")
        # Metadata sigue siendo siempre exacta, sin importar el modo.
        self.assertEqual(perfil["columnas_detalle"]["edad"]["nulls"]["exactitud"], "exacta")

    def test_fingerprint_estable_entre_corridas(self):
        perfil_1 = report.generar_perfil(self.ruta_csv, self.output_dir / "a")["perfil"]
        perfil_2 = report.generar_perfil(self.ruta_csv, self.output_dir / "b")["perfil"]
        self.assertEqual(perfil_1["fingerprint"], perfil_2["fingerprint"])

    def test_json_estable_salvo_created_utc(self):
        perfil_1 = dict(report.generar_perfil(self.ruta_csv, self.output_dir / "a")["perfil"])
        perfil_2 = dict(report.generar_perfil(self.ruta_csv, self.output_dir / "b")["perfil"])
        del perfil_1["created_utc"]
        del perfil_2["created_utc"]
        self.assertEqual(perfil_1, perfil_2)

    def test_markdown_opcional(self):
        resultado_sin = report.generar_perfil(self.ruta_csv, self.output_dir / "sin_md")
        self.assertIsNone(resultado_sin["ruta_profile_md"])

        resultado_con = report.generar_perfil(self.ruta_csv, self.output_dir / "con_md", incluir_markdown=True)
        ruta_md = resultado_con["ruta_profile_md"]
        self.assertIsNotNone(ruta_md)
        self.assertTrue(ruta_md.exists())
        texto = ruta_md.read_text(encoding="utf-8")
        self.assertIn("# Perfil de datos", texto)
        self.assertIn("id", texto)
        self.assertNotIn("<html", texto.lower())

    def test_archivo_inexistente_levanta_archivo_invalido_error(self):
        with self.assertRaises(report.ArchivoInvalidoError):
            report.generar_perfil(self.dir / "no_existe.csv", self.output_dir)
        self.assertFalse(self.output_dir.exists())

    def test_extension_no_soportada_no_escribe_nada(self):
        ruta_txt = self.dir / "no_es_dataset.txt"
        ruta_txt.write_text("hola\n", encoding="utf-8")
        with self.assertRaises(FormatoNoSoportadoError):
            report.generar_perfil(ruta_txt, self.output_dir)
        self.assertFalse(self.output_dir.exists())


def _csv_20_filas() -> str:
    lineas = ["id,valor\n"]
    for i in range(20):
        lineas.append(f"{i},{i % 5}\n")
    return "".join(lineas)


class TestGenerarPerfilCSVUmbralFilas(unittest.TestCase):
    """Corrección 2 de `20260911-ds-profile-fix-clasificacion-sampling`:
    `--max-filas-exactas` ahora también dispara modo muestreado en CSV
    (antes solo aplicaba a Parquet vía metadata, porque `LectorCSV.
    filas_exactas()` devolvía `None` siempre)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.ruta_csv = self.dir / "veinte_filas.csv"
        self.ruta_csv.write_text(_csv_20_filas(), encoding="utf-8")
        self.output_dir = self.dir / "salida"

    def test_modo_exacto_bajo_ambos_umbrales(self):
        perfil = report.generar_perfil(
            self.ruta_csv,
            self.output_dir / "exacto",
            max_filas_exactas=100,
            max_mb_exactos=500,
        )["perfil"]
        self.assertFalse(perfil["sampling"]["activo"])
        self.assertIsNone(perfil["sampling"]["tamano_muestra"])
        for detalle in perfil["columnas_detalle"].values():
            self.assertEqual(detalle["exactitud_estadisticos"], "exacta")
            self.assertEqual(detalle["unique"]["exactitud"], "exacta")

    def test_modo_muestreado_disparado_por_umbral_de_filas(self):
        # max_filas_exactas=5 (chico a propósito) sobre un CSV de 20 filas,
        # con max_mb_exactos alto -- el modo muestreado se dispara
        # específicamente por el umbral de filas, no por MB.
        perfil = report.generar_perfil(
            self.ruta_csv,
            self.output_dir / "por_filas",
            max_filas_exactas=5,
            max_mb_exactos=500,
        )["perfil"]
        self.assertTrue(perfil["sampling"]["activo"])
        self.assertIsNotNone(perfil["sampling"]["tamano_muestra"])
        self.assertLessEqual(perfil["sampling"]["tamano_muestra"], 5)
        for detalle in perfil["columnas_detalle"].values():
            self.assertEqual(detalle["exactitud_estadisticos"], "muestreada")
            self.assertEqual(detalle["unique"]["exactitud"], "muestreada")

    def test_modo_muestreado_disparado_por_umbral_de_mb(self):
        # Confirma que el umbral de MB sigue disparando modo muestreado en
        # CSV (ya cubierto por test_sampling_activo_via_max_mb_exactos_cero
        # en TestGenerarPerfilCSV; se repite acá sobre este dataset de 20
        # filas, que queda bajo max_filas_exactas por defecto).
        perfil = report.generar_perfil(
            self.ruta_csv,
            self.output_dir / "por_mb",
            max_filas_exactas=1_000_000,
            max_mb_exactos=0,
        )["perfil"]
        self.assertTrue(perfil["sampling"]["activo"])

    def test_metadata_siempre_exacta_sin_importar_el_modo(self):
        perfil = report.generar_perfil(
            self.ruta_csv,
            self.output_dir / "metadata",
            max_filas_exactas=5,
            max_mb_exactos=500,
        )["perfil"]
        self.assertEqual(perfil["filas"], 20)
        self.assertEqual(perfil["tamano_bytes"], self.ruta_csv.stat().st_size)
        self.assertEqual(set(perfil["schema"].keys()), {"id", "valor"})
        self.assertEqual(perfil["fingerprint"]["algoritmo"], "sha256/bin/v1")
        for detalle in perfil["columnas_detalle"].values():
            self.assertEqual(detalle["nulls"]["exactitud"], "exacta")

    def test_reproducibilidad_misma_semilla_mismo_csv_misma_muestra(self):
        perfil_1 = report.generar_perfil(
            self.ruta_csv,
            self.output_dir / "rep_a",
            max_filas_exactas=5,
            max_mb_exactos=500,
            seed=123,
        )["perfil"]
        perfil_2 = report.generar_perfil(
            self.ruta_csv,
            self.output_dir / "rep_b",
            max_filas_exactas=5,
            max_mb_exactos=500,
            seed=123,
        )["perfil"]
        del perfil_1["created_utc"]
        del perfil_2["created_utc"]
        self.assertEqual(perfil_1, perfil_2)


if __name__ == "__main__":
    unittest.main()
