"""Tests de dependencias pre-aprobadas con el subset PEP 440 (R16-R20 de
`20261006-sdd-parsers-and-guardrail-ownership`) vía la API pública de
`dsguard.sdd`. Archivo nuevo."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from autonomy import core as autonomy_core  # noqa: E402
from dsguard import sdd  # noqa: E402

_STOP = next(e.code for e in autonomy_core.STOP_CATALOG if e.key == "new_dependency")


def _deps(*bullets):
    texto = "## Dependencias pre-aprobadas\n\n" + "\n".join(f"- {b}" for b in bullets) + "\n"
    return sdd.parsear_dependencias_preaprobadas(texto)


class TestDependenciasSubset(unittest.TestCase):
    def _clasificar(self, rango, version):
        validas, hallazgos = _deps(f"pkg: {rango}")
        self.assertEqual(hallazgos, [], rango)
        return sdd.clasificar_dependencia("pkg", version, validas)

    def test_exacta_normal(self):
        self.assertEqual(self._clasificar("==2.9.0", "2.9.0"), "no_stop")
        self.assertEqual(self._clasificar("==2.9.0", "2.9.1"), _STOP)

    def test_post0(self):
        self.assertEqual(self._clasificar("==2.9.0.post0", "2.9.0.post0"), "no_stop")
        self.assertEqual(self._clasificar("==2.9.0.post0", "2.9.0.post0+cu118"), "no_stop")
        self.assertEqual(self._clasificar("==2.9.0.post0", "2.9.0"), _STOP)

    def test_pre_y_dev(self):
        self.assertEqual(self._clasificar("==1.0rc1", "1.0rc1"), "no_stop")
        self.assertEqual(self._clasificar("==1.0a1", "1.0a1"), "no_stop")
        self.assertEqual(self._clasificar("==1.0b2", "1.0b2"), "no_stop")
        self.assertEqual(self._clasificar("==1.0.dev3", "1.0.dev3"), "no_stop")
        self.assertEqual(self._clasificar(">=1.0", "1.0rc1"), _STOP)

    def test_rangos(self):
        self.assertEqual(self._clasificar(">=1.2,<2", "1.5"), "no_stop")
        self.assertEqual(self._clasificar(">=1.2,<2", "2.0"), _STOP)
        self.assertEqual(self._clasificar(">=1.2,<2", "1.5.post1"), "no_stop")

    def test_limite_exclusivo_prerelease_misma_release(self):
        self.assertEqual(self._clasificar(">=1.2,<2", "2.0rc1"), _STOP)
        self.assertEqual(self._clasificar(">=1.2,<2", "2.0.dev1"), _STOP)
        self.assertEqual(self._clasificar(">=1.2,<2", "1.5rc1"), "no_stop")
        self.assertEqual(self._clasificar(">1", "1.0.post1"), _STOP)

    def test_malformado_emite_hallazgo(self):
        for rango in ["~=1.0", "==1.*", "===1.0", ">=1!2", ">=1.0alpha1", ">=1.0+local", "1.0", ">=1..2"]:
            validas, hallazgos = _deps(f"pkg: {rango}")
            self.assertEqual(validas, [], rango)
            self.assertEqual(len(hallazgos), 1, rango)
            self.assertEqual(hallazgos[0].codigo, sdd.CODE_DEPENDENCY_PREAPPROVAL_INVALID)
            self.assertIn("no parseable", hallazgos[0].mensaje)

    def test_version_solicitada_fuera_del_subset_es_stop(self):
        validas, _ = _deps("pkg: >=1.0")
        for v in ["", "x", "1.0alpha1", "1!2.0", "1.*"]:
            self.assertEqual(sdd.clasificar_dependencia("pkg", v, validas), _STOP, v)

    def test_nombre_no_listado_es_stop(self):
        validas, _ = _deps("pkg: >=1.0")
        self.assertEqual(sdd.clasificar_dependencia("otro", "1.5", validas), _STOP)


if __name__ == "__main__":
    unittest.main()
