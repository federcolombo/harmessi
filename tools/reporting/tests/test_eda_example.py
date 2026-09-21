"""Tests del ejemplo genérico de EDA (v0.6 Change 2, R19/R23).

Sin red y sin pandas: el ejemplo debe pasar el validador sin FAIL, ser
determinista, mantener figura <-> tabla íntegras, no importar pandas y no
contener datos privados.
"""
from __future__ import annotations

import ast
import json
import re
import unittest
from pathlib import Path
from unittest import mock

from tools.reporting import core
from tools.reporting.examples import eda_generic
from tools.reporting.profiles import eda

from dsguard import checks  # noqa: E402

RUTA_EJEMPLO = Path(eda_generic.__file__).resolve()

BLOQUES_REALES = (
    "data_quality",
    "univariate",
    "bivariate_target",
    "temporal",
    "concentration",
    "population_and_unit",
)
BLOQUES_OMITIDOS = ("segmentation", "multivariate", "leakage_review")
BLOQUES_NO_APLICABLES = ("entity_relations", "process_cycles")

# Patrones típicos de datos privados: rutas de Windows/POSIX de usuario, correos y URLs.
PATRONES_PRIVADOS = (
    re.compile(r"[A-Za-z]:\\"),
    re.compile(r"/(?:home|Users|mnt)/"),
    re.compile(r"@"),
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"\.env\b"),
)


class TestEjemploEda(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reporte = eda_generic.build_example_report()

    def test_constantes_y_tipo(self):
        self.assertEqual(eda_generic.RANDOM_STATE, 42)
        self.assertIsInstance(self.reporte, core.Report)
        self.assertEqual(self.reporte.report_kind, "eda")
        self.assertEqual(self.reporte.decision_scope, "exploratory")

    def test_pasa_validacion_sin_fail(self):
        resultados = eda.validate_eda_report(self.reporte)
        self.assertTrue(resultados)
        fallos = [r for r in resultados if r.status == checks.STATUS_FAIL]
        self.assertEqual(fallos, [], [(r.code, r.subject, r.detail) for r in fallos])
        # El WARN esperado del scope exploratorio con bivariate_target aplicado.
        self.assertIn(
            (checks.STATUS_WARN, eda.CODE_EXPLORATORY_TARGET_USE),
            [(r.status, r.code) for r in resultados],
        )

    def test_hash_determinista(self):
        otro = eda_generic.build_example_report()
        self.assertEqual(self.reporte.content_sha256(), otro.content_sha256())

    def test_datos_calculados_cambian_con_random_state(self):
        # Se compara el contenido calculado (no el hash global, que incluye metadata).
        with mock.patch.object(eda_generic, "RANDOM_STATE", 7):
            distinto = eda_generic.build_example_report()
        for table_id in ("tasa_por_grupo", "calidad_por_columna"):
            with self.subTest(tabla=table_id):
                self.assertNotEqual(
                    self.reporte.get_table(table_id).rows, distinto.get_table(table_id).rows
                )

    def test_round_trip_to_dict_from_dict(self):
        copia = core.Report.from_dict(self.reporte.to_dict())
        self.assertEqual(copia.content_sha256(), self.reporte.content_sha256())

    def test_numeros_citados_coinciden_con_las_tablas(self):
        n_total = eda_generic.N_REGISTROS
        calidad = self.reporte.get_table("calidad_por_columna")
        fila_medida = next(f for f in calidad.rows if f[0] == "medida")
        n_nulos = fila_medida[2]
        self.assertEqual(fila_medida[1], n_total)
        self.assertAlmostEqual(fila_medida[3], n_nulos / n_total, places=3)
        # La proporción está en 0-1 en todas las tablas del ejemplo.
        for fila in calidad.rows:
            self.assertGreaterEqual(fila[3], 0.0)
            self.assertLessEqual(fila[3], 1.0)
        self.assertEqual(calidad.units["prop_nulos"], "proporción (0 a 1)")
        for _g, _n, _p, tasa in self.reporte.get_table("tasa_por_grupo").rows:
            self.assertLessEqual(tasa, 1.0)

        insights = {i.insight_id: i for i in self.reporte.iter_insights()}
        self.assertIn(str(n_nulos), insights["ins-calidad-completitud"].technical_claim)
        self.assertIn(f"{n_nulos / n_total:.2%}", insights["ins-calidad-completitud"].technical_claim)
        self.assertIn(str(n_nulos), self.reporte.conclusion)
        self.assertIn(str(n_total), self.reporte.conclusion)
        self.assertNotIn("completos y utilizables", self.reporte.conclusion)

        # Población: lo que se excluye del resumen de la medida sale de las tablas.
        poblacion = dict(self.reporte.get_table("poblacion_y_unidad").rows)
        excluidos = next(v for k, v in poblacion.items() if k.startswith("Registros sin medida"))
        self.assertEqual(int(excluidos), n_nulos)
        self.assertIn(excluidos, insights["ins-poblacion-unidad"].technical_claim)
        self.assertIn(excluidos, insights["ins-poblacion-unidad"].business_claim)
        self.assertNotIn("ningún registro", insights["ins-poblacion-unidad"].business_claim)

        # Concentración: el n del grupo más chico citado coincide con la tabla.
        ultimo = self.reporte.get_table("concentracion_por_grupo").rows[-1]
        cita = insights["ins-concentracion-grupos"]
        self.assertIn(str(ultimo[1]), cita.uncertainty)
        self.assertIn(ultimo[0], cita.uncertainty)
        self.assertNotIn("menos confiables", cita.business_claim)

    def test_estados_de_los_bloques(self):
        apl = self.reporte.metadata["eda"]["applicability"]
        self.assertEqual(set(apl), {i.block_id for i in eda.BLOCK_CATALOG})
        for bloque in BLOQUES_REALES:
            self.assertEqual(apl[bloque]["state"], "applicable", bloque)
        for bloque in BLOQUES_OMITIDOS:
            self.assertEqual(apl[bloque]["state"], "omitted", bloque)
        for bloque in BLOQUES_NO_APLICABLES:
            self.assertEqual(apl[bloque]["state"], "not_applicable", bloque)
            self.assertFalse(apl[bloque]["auto"], bloque)

    def test_razones_distintas_y_suficientes(self):
        apl = self.reporte.metadata["eda"]["applicability"]
        razones = []
        for bloque in BLOQUES_OMITIDOS + BLOQUES_NO_APLICABLES:
            razon = apl[bloque]["reason"]
            self.assertGreaterEqual(len(razon.split()), 5, bloque)
            razones.append(razon.casefold())
        self.assertEqual(len(set(razones)), len(razones))

    def test_capitulos_reales_con_insight(self):
        por_bloque = {
            c.metadata["eda_block"]: c for c in self.reporte.chapters if "eda_block" in c.metadata
        }
        for bloque in BLOQUES_REALES:
            self.assertIn(bloque, por_bloque)
            self.assertGreaterEqual(len(por_bloque[bloque].insights), 1, bloque)
        for bloque in BLOQUES_OMITIDOS + BLOQUES_NO_APLICABLES:
            self.assertNotIn(bloque, por_bloque)

    def test_evidencia_de_insights_valida(self):
        for insight in self.reporte.iter_insights():
            self.assertTrue(insight.evidence_refs, insight.insight_id)
            for ref in insight.evidence_refs:
                self.assertIsNotNone(self.reporte.get_artifact(ref), (insight.insight_id, ref))
            self.assertTrue(insight.population.strip())
            self.assertTrue(insight.time_scope.strip())
            if insight.claim_type in ("associative", "causal", "recommendation"):
                self.assertTrue(insight.uncertainty.strip(), insight.insight_id)
            self.assertNotIn(insight.claim_type, ("causal", "recommendation"))

    def test_ids_validos(self):
        ids = [self.reporte.report_id]
        for capitulo in self.reporte.chapters:
            ids.append(capitulo.chapter_id)
            ids.extend(t.table_id for t in capitulo.tables)
            ids.extend(f.figure_id for f in capitulo.figures)
            ids.extend(i.insight_id for i in capitulo.insights)
        for identificador in ids:
            self.assertTrue(core.es_id_valido(identificador), identificador)

    def test_integridad_figura_tabla(self):
        figuras = list(self.reporte.iter_figures())
        self.assertTrue(figuras)
        for figura in figuras:
            self.assertIsNotNone(figura.backing_table_id, figura.figure_id)
            tabla = self.reporte.get_table(figura.backing_table_id)
            self.assertIsNotNone(tabla, figura.figure_id)
            for columna in figura.spec.columns_used():
                self.assertIn(columna, tabla.columns, (figura.figure_id, columna))
            if figura.spec.top_n is not None:
                # La tabla de respaldo es completa aunque la figura muestre solo top-N.
                self.assertGreater(len(tabla.rows), figura.spec.top_n, figura.figure_id)

    def test_tasa_por_grupo_con_denominador(self):
        tabla = self.reporte.get_table("tasa_por_grupo")
        self.assertIsNotNone(tabla)
        self.assertEqual(tabla.columns, ("grupo", "n_registros", "n_positivos", "tasa_resultado"))
        self.assertEqual(len(tabla.rows), len(eda_generic.GRUPOS))
        self.assertEqual(sum(fila[1] for fila in tabla.rows), eda_generic.N_REGISTROS)
        for _grupo, n_registros, n_positivos, tasa in tabla.rows:
            self.assertGreater(n_registros, 0)
            self.assertAlmostEqual(tasa, n_positivos / n_registros, places=3)
        figura = self.reporte.get_figure("fig-tasa-por-grupo")
        self.assertEqual(figura.spec.denominator, "n_registros")
        self.assertEqual(figura.spec.top_n, eda_generic.TOP_N_GRUPOS)

    def test_coverage_table_sin_score(self):
        tabla = self.reporte.get_table(eda.COVERAGE_TABLE_ID)
        self.assertEqual(tabla.columns, eda.COVERAGE_COLUMNS)
        self.assertEqual(len(tabla.rows), len(eda.BLOCK_CATALOG))

    def test_sin_importar_pandas(self):
        arbol = ast.parse(RUTA_EJEMPLO.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                nombres = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom):
                nombres = [nodo.module or ""]
            else:
                continue
            for nombre in nombres:
                self.assertNotEqual(nombre.split(".")[0], "pandas", nombre)

    def test_sin_datos_privados(self):
        texto_fuente = RUTA_EJEMPLO.read_text(encoding="utf-8")
        texto_reporte = json.dumps(self.reporte.to_dict(), ensure_ascii=False)
        for patron in PATRONES_PRIVADOS:
            with self.subTest(patron=patron.pattern):
                self.assertIsNone(patron.search(texto_fuente), "fuente")
                self.assertIsNone(patron.search(texto_reporte), "reporte")


if __name__ == "__main__":
    unittest.main()
