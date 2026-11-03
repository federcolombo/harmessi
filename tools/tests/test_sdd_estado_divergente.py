"""Tests de `sdd.chequear_estado_divergente` (R15 de
`20261014-composable-skills-writer-semantics`). Archivo nuevo."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "tools"))

from dsguard import core, sdd  # noqa: E402

CODIGO = "SDD-ESTADO-DIVERGENTE"


def _tasks(estado):
    lineas = ["# Tasks", ""]
    if estado is not None:
        lineas.append(f"estado: {estado}")
    return "\n".join(lineas) + "\n"


def _trans(*destinos):
    return {
        "schema_version": core.SCHEMA_VERSION_SOPORTADA,
        "transiciones": [{"utc": "2026-10-14T10:00:00Z", "desde": "x", "hacia": h} for h in destinos],
    }


class TestEstadoDivergente(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name) / "20261014-temporal"
        self.dir.mkdir()
        self.tasks = self.dir / "tasks.md"

    def escribir(self, estado):
        self.tasks.write_text(_tasks(estado), encoding="utf-8", newline="")

    def test_sin_transiciones_propuesta_pendiente(self):
        self.escribir("propuesta_pendiente")
        self.assertEqual(sdd.chequear_estado_divergente({}, self.tasks), [])
        self.assertEqual(sdd.chequear_estado_divergente({"transiciones": []}, self.tasks), [])

    def test_consistente_tras_transiciones(self):
        self.escribir("aprobada_implementacion")
        c = _trans("aprobada_diseño", "aprobada_implementacion")
        self.assertEqual(sdd.chequear_estado_divergente(c, self.tasks), [])

    def test_estado_adelantado_a_mano(self):
        self.escribir("aprobada_implementacion")
        hallazgos = sdd.chequear_estado_divergente({}, self.tasks)
        self.assertEqual(len(hallazgos), 1)
        h = hallazgos[0]
        self.assertEqual(h.codigo, CODIGO)
        self.assertEqual(h.ubicacion, str(self.tasks))
        self.assertIn("propuesta_pendiente", h.mensaje)
        self.assertIn("aprobada_implementacion", h.mensaje)
        self.assertIn("ds_guard transition --change-id 20261014-temporal --a aprobada_implementacion", h.mensaje)
        self.assertIn("git", h.mensaje)

    def test_mensaje_salto_ilegitimo_no_sugiere_reconciliar(self):
        self.escribir("en_verificacion")
        (h,) = sdd.chequear_estado_divergente({}, self.tasks)
        self.assertEqual(h.codigo, CODIGO)
        self.assertNotIn("--a en_verificacion", h.mensaje)
        self.assertIn("NO es válida", h.mensaje)
        self.assertIn("Restaurar 'estado:' a 'propuesta_pendiente' desde git", h.mensaje)

    def test_mensaje_paso_valido_sugiere_transition(self):
        self.escribir("aprobada_diseño")
        (h,) = sdd.chequear_estado_divergente({}, self.tasks)
        self.assertIn("es válida", h.mensaje)
        self.assertNotIn("NO es válida", h.mensaje)
        self.assertIn("--a aprobada_diseño", h.mensaje)

    def test_estado_atrasado(self):
        self.escribir("propuesta_pendiente")
        hallazgos = sdd.chequear_estado_divergente(_trans("aprobada_implementacion"), self.tasks)
        self.assertEqual([h.codigo for h in hallazgos], [CODIGO])

    def test_sin_linea_estado_devuelve_vacio(self):
        self.escribir(None)
        self.assertEqual(sdd.chequear_estado_divergente({}, self.tasks), [])

    def test_estado_duplicado_devuelve_vacio(self):
        self.tasks.write_text("estado: cerrada\nestado: cerrada\n", encoding="utf-8")
        self.assertEqual(sdd.chequear_estado_divergente({}, self.tasks), [])

    def test_ventana_de_reconciliacion_resuelta_por_transition(self):
        # estado ya escrito = destino (en_verificacion), transición faltante.
        self.escribir("en_verificacion")
        control_path = self.dir / "control.json"
        control = _trans("en_implementacion")
        core.escribir_control(control_path, control)
        self.assertEqual(len(sdd.chequear_estado_divergente(control, self.tasks)), 1)

        # El gate de en_verificacion solo exige sesión activa.
        ok, findings = sdd.transition(
            control, self.tasks, control_path, self.dir, "en_verificacion", {"id": "s1"}
        )
        self.assertTrue(ok, findings)
        self.assertEqual(sdd.chequear_estado_divergente(control, self.tasks), [])
        recargado = core.leer_control(control_path)
        self.assertEqual(recargado["transiciones"][-1]["hacia"], "en_verificacion")
        self.assertTrue(recargado["transiciones"][-1].get("reconciliado"))
        self.assertEqual(sdd.chequear_estado_divergente(recargado, self.tasks), [])


class TestCensoRepoReal(unittest.TestCase):
    def test_changes_y_archive_sin_divergencia(self):
        revisados = 0
        for padre in ("changes", "archive"):
            base = RAIZ / "openspec" / padre
            if not base.is_dir():
                continue
            for carpeta in sorted(p for p in base.iterdir() if p.is_dir()):
                tasks = carpeta / "tasks.md"
                control_path = carpeta / "control.json"
                if not (tasks.is_file() and control_path.is_file()):
                    continue
                with self.subTest(change=f"{padre}/{carpeta.name}"):
                    control = core.leer_control(control_path)
                    self.assertEqual(sdd.chequear_estado_divergente(control, tasks), [])
                revisados += 1
        if revisados == 0:
            self.skipTest("sin Changes con tasks.md y control.json")


if __name__ == "__main__":
    unittest.main()
