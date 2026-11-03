"""Tests de `tools/dsguard/pep440_subset.py` (R15-R20 de
`20261006-sdd-parsers-and-guardrail-ownership`). Archivo nuevo."""
from __future__ import annotations

import itertools
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from dsguard import pep440_subset as p  # noqa: E402

# Orden estrictamente creciente (R17).
ORDEN = [
    "1.0.dev1", "1.0a1", "1.0b1", "1.0rc1.dev1", "1.0rc1", "1.0", "1.0.post1.dev1",
    "1.0.post1", "1.0.post2", "2.9.0", "2.9.0.post0", "2.9.1.dev0", "2.9.1", "10.0",
]


class TestParse(unittest.TestCase):
    def test_validas(self):
        for t in ["1", "1.0", "1.0a1", "1.0b2", "1.0rc1", "1.0.post1", "1.0.dev1",
                  "1.0rc1.dev2", "1.0.post1.dev3", "  1.0RC1 ", "1.0a1.post2.dev3"]:
            p.parse_version(t)

    def test_invalidas(self):
        for t in ["", "  ", "1!2.0", "1.*", "1.0.*", "~=1.0", "===1.0", "1.0alpha1", "1.0beta1",
                  "1.0c1", "1.0pre1", "1.0preview1", "1.0rev1", "1.0r1", "1.0-1", "1.0_post1",
                  "1.0-rc1", "1..2", ".1", "1.", "1.0a", "1.0.post", "1.0.dev", "x", "1.0.dev1.post1",
                  "1.0.post1a1", "name @ http://x", "1.0+local"]:
            with self.assertRaises(ValueError, msg=t):
                p.parse_version(t)

    def test_local_solo_si_se_permite(self):
        self.assertEqual(p.parse_version("2.9.0+cu118.x-y_z", permitir_local=True), p.parse_version("2.9.0"))
        with self.assertRaises(ValueError):
            p.parse_version("2.9.0+local")
        with self.assertRaises(ValueError):
            p.parse_version("1.0+", permitir_local=True)

    def test_mensaje_claro(self):
        with self.assertRaises(ValueError) as c:
            p.parse_version("1!2.0")
        self.assertIn("epoch", str(c.exception))
        with self.assertRaises(ValueError) as c:
            p.parse_version("1.*")
        self.assertIn("wildcard", str(c.exception))


class TestOrdering(unittest.TestCase):
    def test_orden_completo(self):
        for (i, a), (j, b) in itertools.product(enumerate(ORDEN), repeat=2):
            esperado = (i > j) - (i < j)
            self.assertEqual(p.compare(p.parse_version(a), p.parse_version(b)), esperado, (a, b))

    def test_transitividad(self):
        vs = [p.parse_version(t) for t in ORDEN]
        for a, b, c in itertools.product(vs, repeat=3):
            if a < b and b < c:
                self.assertTrue(a < c)

    def test_igualdades(self):
        self.assertEqual(p.compare(p.parse_version("1.0"), p.parse_version("1.0.0")), 0)
        self.assertEqual(p.parse_version("1.0"), p.parse_version("1.0.0"))
        self.assertGreater(p.parse_version("2.9.0.post0"), p.parse_version("2.9.0"))
        self.assertLess(p.parse_version("2.9.0.post0"), p.parse_version("2.9.1.dev0"))
        self.assertGreater(p.parse_version("10.0"), p.parse_version("9.0"))  # no lexicográfico


class TestRangos(unittest.TestCase):
    def test_compat_rangos_existentes(self):
        casos = [
            (">=1.2,<2", "1.5", True), (">=1.2,<2", "2.0", False), (">=1.2,<2", "1.1", False),
            (">=1.2,<2", "1.2", True), (">=1.2,<2", "1.2.0", True), ("==1.0", "1.0.0", True),
            ("!=1.5", "1.5", False), ("!=1.5", "1.6", True), (">1", "1.0.1", True), (">1", "1", False),
            ("<=3", "3.0", True), (">= 1.2 , < 2", "1.9", True),
        ]
        for rango, v, esperado in casos:
            self.assertEqual(p.satisfies(v, rango), esperado, (rango, v))

    def test_exacta_post_y_local(self):
        self.assertTrue(p.satisfies("2.9.0.post0", "==2.9.0.post0"))
        self.assertTrue(p.satisfies("2.9.0.post0+local", "==2.9.0.post0"))
        self.assertFalse(p.satisfies("2.9.0", "==2.9.0.post0"))

    def test_pre_dev(self):
        self.assertTrue(p.satisfies("1.0rc1", "==1.0rc1"))
        self.assertFalse(p.satisfies("1.0rc1", ">=1.0"))
        self.assertTrue(p.satisfies("1.0rc1", "<=1.0"))  # `<` lo excluye (PEP 440), `<=` no
        self.assertTrue(p.satisfies("1.0.dev1", "<1.0a1"))
        self.assertTrue(p.satisfies("1.0.post1", ">=1.0"))

    def test_parse_range(self):
        r = p.parse_range(">=1.2,<2")
        self.assertEqual([op for op, _ in r], [">=", "<"])

    def test_rangos_invalidos(self):
        for r in ["", ",", ">=1.0,", "~=1.0", "===1.0", "1.0", "==1.*", ">=1.0+local", ">=1!1", "=>1.0", "@1.0"]:
            with self.assertRaises(ValueError, msg=r):
                p.parse_range(r)

    def test_limite_exclusivo_menor_excluye_prerelease_misma_release(self):
        for v in ["2.0rc1", "2.0.dev1", "2.0a1", "2.0b1", "2rc1"]:
            self.assertFalse(p.satisfies(v, "<2"), v)
        for v in ["1.9.9", "1.5rc1", "1.0.dev1"]:
            self.assertTrue(p.satisfies(v, "<2"), v)
        self.assertTrue(p.satisfies("2rc1.dev1", "<2rc1"))
        self.assertTrue(p.satisfies("2a1", "<2rc1"))

    def test_limite_exclusivo_mayor_excluye_postrelease_misma_release(self):
        self.assertFalse(p.satisfies("1.0.post1", ">1"))
        for v in ["1.0.1", "2.0", "1.1.post1"]:
            self.assertTrue(p.satisfies(v, ">1"), v)
        self.assertTrue(p.satisfies("1.post2", ">1.post1"))

    def test_digitos_no_ascii(self):
        for t in ["1.²", "١.٠", "１.０", "1.0a²", "1.0.post١"]:
            with self.assertRaises(ValueError, msg=t):
                p.parse_version(t)
            self.assertFalse(p.satisfies(t, ">=0"), t)
        with self.assertRaises(ValueError):
            p.parse_range(">=１.０")

    def test_fail_closed(self):
        self.assertFalse(p.satisfies("x", ">=1"))
        self.assertFalse(p.satisfies("1.0", "~=1.0"))
        self.assertFalse(p.satisfies("1.0", ""))
        self.assertFalse(p.satisfies(None, ">=1"))
        self.assertFalse(p.satisfies("1.0", None))


if __name__ == "__main__":
    unittest.main()
