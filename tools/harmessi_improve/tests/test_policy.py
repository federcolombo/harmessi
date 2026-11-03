"""Tests de ProbePolicy (v0.14 Change 2, R1-R2)."""
from __future__ import annotations

import dataclasses
import unittest

from tools.harmessi_improve.policy import POLICY_VERSION, PolicyInvalida, ProbePolicy, hash_policy


class TestPolicy(unittest.TestCase):
    def test_defaults_validos(self):
        p = ProbePolicy()
        self.assertEqual(POLICY_VERSION, 1)
        self.assertEqual((p.primary, p.repeats, p.tie_policy), ("passed", 1, "equivalent"))

    def test_invalidos(self):
        casos = [
            dict(primary="otro"), dict(secondary=("nada",)), dict(secondary="mean_score"),
            dict(secondary=("mean_score", "mean_score")), dict(tie_policy="x"),
            dict(repeats=0), dict(repeats=4), dict(repeats=True), dict(repeats=1.5),
            dict(min_stable_ratio=0), dict(min_stable_ratio=1.1), dict(min_stable_ratio=True),
            dict(secondary=("duration_s",)), dict(tie_policy="secondary", secondary=("mean_score",), min_delta=0),
            dict(min_scenarios=0), dict(min_scenarios=True), dict(min_scenarios=1.5),
            dict(min_delta=10 ** 400), dict(min_stable_ratio=10 ** 400), dict(min_delta=-0.1), dict(min_delta=float("nan")), dict(min_delta="1"),
        ]
        for kw in casos:
            with self.subTest(**kw):
                with self.assertRaises(PolicyInvalida):
                    ProbePolicy(**kw)

    def test_validos_limites(self):
        ProbePolicy(repeats=3, min_stable_ratio=1, min_delta=0.01, secondary=("mean_score",),
                    tie_policy="secondary", min_scenarios=1)
        ProbePolicy(min_stable_ratio=0.01, tie_policy="inconclusive")

    def test_inmutable(self):
        p = ProbePolicy()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            p.repeats = 2  # type: ignore[misc]

    def test_hash_determinista_y_sensible(self):
        a = ProbePolicy(secondary=["mean_score"])
        b = ProbePolicy(secondary=("mean_score",))
        self.assertEqual(hash_policy(a), hash_policy(b))
        self.assertEqual(len(hash_policy(a)), 64)
        otra = ProbePolicy(secondary=("mean_score",), tie_policy="secondary", min_delta=0.5)
        self.assertNotEqual(hash_policy(a), hash_policy(otra))
        self.assertNotEqual(hash_policy(ProbePolicy()), hash_policy(a))
        self.assertNotEqual(hash_policy(ProbePolicy()), hash_policy(ProbePolicy(repeats=2)))

    def test_roundtrip_dict(self):
        p = ProbePolicy(repeats=2, secondary=("mean_score",), tie_policy="secondary", min_delta=0.5)
        self.assertEqual(ProbePolicy.desde_dict(p.a_dict()), p)
        self.assertEqual(hash_policy(ProbePolicy.desde_dict(p.a_dict())), hash_policy(p))

    def test_desde_dict_estricto(self):
        d = ProbePolicy().a_dict()
        for malo in ({**d, "extra": 1}, {k: v for k, v in d.items() if k != "repeats"},
                     {**d, "policy_version": 2}, [], None):
            with self.subTest(malo=str(malo)[:30]):
                with self.assertRaises(PolicyInvalida):
                    ProbePolicy.desde_dict(malo)


if __name__ == "__main__":
    unittest.main()
