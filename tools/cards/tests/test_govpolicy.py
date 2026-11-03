"""Tests de `tools.cards.govpolicy` (Change `20261005-model-risk-responsible-ai`,
R13-R31, R64).

Cubren tipos estrictos, vocabularios cerrados, la matriz BASE congelada (R21-R22b),
el orden de fuerza (R17), la monotonicidad (R18), el merge fail-closed todo-o-nada
(R25-R29), `requirements_at`, `max_level` y la ausencia de lenguaje de
cumplimiento (R20). Sin mocks; todo con objetos reales en memoria.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import itertools
import json
import re
import unittest
from pathlib import Path

from tools.cards import core, govpolicy

# Vector literal CONGELADO (R21/R22b/R64). NO ajustar si falla: la matriz fue
# aprobada y congelada; cambiarla implica nueva version de policy.
BASE_SHA256_CONGELADO = "ee6b6188a1db05fbc51b12709e1f4dba4211040d11e3ac8e1ed164ee58ccdb53"

EXT = tuple(sorted(govpolicy.EXTERNAL_EVIDENCE_KINDS))
OBS_ATT = ("observed", "attestation")
FUENTE = Path(govpolicy.__file__).resolve()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def ls(severity="required", accepts=OBS_ATT, kinds=None, minimo="declared"):
    return govpolicy.LevelSpec(severity, accepts, kinds, minimo)


def att(minimo="declared", severity="required"):
    return ls(severity, ("attestation",), None, minimo)


def mixto(severity, minimo):
    return ls(severity, OBS_ATT, EXT, minimo)


def codigo(funcion, *args, **kwargs):
    """Código del `GovPolicyError` lanzado; falla si no lanza ese error."""
    try:
        funcion(*args, **kwargs)
    except govpolicy.GovPolicyError as exc:
        return exc.code
    raise AssertionError("no lanzó GovPolicyError")


def hard(floor=None, overrides=(), additional=(), policy_id="harmessi-base", base_version=1):
    return govpolicy.HardeningDocument(
        policy_id=policy_id,
        base_version=base_version,
        risk_floor=floor,
        overrides=tuple(overrides),
        additional=tuple(additional),
    )


def ov(rid, levels):
    return govpolicy.RequirementOverride(rid, levels)


def requisito(rid, dimension="security", levels=None, description=""):
    return govpolicy.PolicyRequirement(rid, dimension, levels or {"high": ls()}, description)


def req_de(policy, rid):
    for r in policy.requirements:
        if r.requirement_id == rid:
            return r
    raise AssertionError(f"requisito {rid!r} ausente")


def merge_base(documento=None):
    return govpolicy.merge(govpolicy.BASE_POLICY, documento)


# Matriz R22 esperada: rid -> (dimension, {nivel: (severity, accepts, kinds, minimo)}).
ATT_ONLY = ("attestation",)
MATRIZ = {
    "accountability_risk_declaration": (
        "accountability",
        {
            "low": ("required", ATT_ONLY, None, "declared"),
            "medium": ("required", ATT_ONLY, None, "declared"),
            "high": ("required", ATT_ONLY, None, "anchored"),
        },
    ),
    "accountability_owner": (
        "accountability",
        {
            "low": ("required", ATT_ONLY, None, "declared"),
            "medium": ("required", ATT_ONLY, None, "declared"),
            "high": ("required", ATT_ONLY, None, "anchored"),
        },
    ),
    "human_oversight_process": (
        "human_oversight",
        {
            "medium": ("recommended", OBS_ATT, EXT, "declared"),
            "high": ("required", OBS_ATT, EXT, "anchored"),
        },
    ),
    "fairness_evidence": (
        "fairness",
        {
            "medium": ("required", OBS_ATT, EXT, "declared"),
            "high": ("required", ("observed",), EXT, "declared"),
        },
    ),
    "explainability_evidence": (
        "explainability",
        {
            "medium": ("recommended", OBS_ATT, EXT, "declared"),
            "high": ("required", OBS_ATT, EXT, "anchored"),
        },
    ),
    "privacy_evidence": (
        "privacy",
        {
            "low": ("recommended", OBS_ATT, EXT, "declared"),
            "medium": ("required", OBS_ATT, EXT, "declared"),
            "high": ("required", OBS_ATT, EXT, "anchored"),
        },
    ),
    "security_evidence": (
        "security",
        {
            "low": ("recommended", OBS_ATT, EXT, "declared"),
            "medium": ("required", OBS_ATT, EXT, "declared"),
            "high": ("required", OBS_ATT, EXT, "anchored"),
        },
    ),
}


# ---------------------------------------------------------------------------
# Vocabularios (R13)
# ---------------------------------------------------------------------------


class TestVocabularios(unittest.TestCase):
    def test_levels_exactos(self):
        self.assertEqual(govpolicy.LEVELS, ("low", "medium", "high"))
        for prohibido in ("unassessed", "critical", "none"):
            self.assertNotIn(prohibido, govpolicy.LEVELS)

    def test_dimensions_exactas(self):
        self.assertEqual(
            govpolicy.DIMENSIONS,
            ("fairness", "explainability", "privacy", "security", "accountability", "human_oversight"),
        )

    def test_kinds_externos_r19(self):
        self.assertEqual(
            set(govpolicy.EXTERNAL_EVIDENCE_KINDS),
            {
                "evidence_document",
                "execution_record",
                "observed_metric",
                "baseline_reference",
                "model_quality_result",
                "drift_evidence",
            },
        )
        self.assertNotIn("report_artifact", govpolicy.EXTERNAL_EVIDENCE_KINDS)

    def test_codigos(self):
        self.assertEqual(
            set(govpolicy.CODES),
            {
                "GOVPOLICY-INVALID",
                "GOVPOLICY-NOT-MONOTONIC",
                "GOVPOLICY-RELAXATION",
                "GOVPOLICY-BASE-MISMATCH",
                "GOVPOLICY-UNKNOWN-KEY",
                "GOVPOLICY-SCHEMA-UNSUPPORTED",
            },
        )


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------


class TestLevelSpec(unittest.TestCase):
    def test_normalizacion_canonica(self):
        s = govpolicy.LevelSpec("required", ["attestation", "observed", "observed"], ["observed_metric", "drift_evidence", "observed_metric"])
        self.assertEqual(s.accepts, ("observed", "attestation"))
        self.assertEqual(s.accepted_kinds, ("drift_evidence", "observed_metric"))
        self.assertEqual(s.min_attestation_kind, "declared")

    def test_accepts_orden_independiente_igualdad(self):
        a = govpolicy.LevelSpec("required", ("attestation", "observed"))
        b = govpolicy.LevelSpec("required", ("observed", "attestation"))
        self.assertEqual(a, b)

    def test_invalidos(self):
        casos = [
            lambda: govpolicy.LevelSpec("critical", ("observed",)),
            lambda: govpolicy.LevelSpec(1, ("observed",)),
            lambda: govpolicy.LevelSpec(True, ("observed",)),
            lambda: govpolicy.LevelSpec("required", ()),
            lambda: govpolicy.LevelSpec("required", "observed"),
            lambda: govpolicy.LevelSpec("required", None),
            lambda: govpolicy.LevelSpec("required", ("other",)),
            lambda: govpolicy.LevelSpec("required", (1,)),
            lambda: govpolicy.LevelSpec("required", ("observed",), ()),
            lambda: govpolicy.LevelSpec("required", ("observed",), "evidence_document"),
            lambda: govpolicy.LevelSpec("required", ("observed",), ("source_observation",)),
            lambda: govpolicy.LevelSpec("required", ("observed",), ("report_artifact",)),
            lambda: govpolicy.LevelSpec("required", ("observed",), ("model_card",)),
            lambda: govpolicy.LevelSpec("required", ("observed",), (3,)),
            lambda: govpolicy.LevelSpec("required", ("attestation",), None, "other"),
            lambda: govpolicy.LevelSpec("required", ("attestation",), None, None),
            lambda: govpolicy.LevelSpec("required", ("attestation",), None, 1),
        ]
        for i, caso in enumerate(casos):
            with self.subTest(i=i):
                self.assertEqual(codigo(caso), govpolicy.CODE_INVALID)

    def test_inmutable(self):
        s = ls()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            s.severity = "recommended"

    def test_round_trip(self):
        for s in (ls(), att("anchored"), mixto("recommended", "anchored"), ls(kinds=("drift_evidence",))):
            with self.subTest(s=s):
                self.assertEqual(govpolicy.LevelSpec.from_dict(s.to_dict()), s)
                self.assertEqual(govpolicy.LevelSpec.from_dict(json.loads(json.dumps(s.to_dict()))), s)

    def test_from_dict_estricto(self):
        base = ls().to_dict()
        extra = dict(base, extra=1)
        self.assertEqual(codigo(govpolicy.LevelSpec.from_dict, extra), govpolicy.CODE_UNKNOWN_KEY)
        for clave in ("severity", "accepts"):
            d = dict(base)
            del d[clave]
            with self.subTest(clave=clave):
                self.assertEqual(codigo(govpolicy.LevelSpec.from_dict, d), govpolicy.CODE_INVALID)
        for malo in (None, [], "x", 3):
            with self.subTest(malo=malo):
                self.assertEqual(codigo(govpolicy.LevelSpec.from_dict, malo), govpolicy.CODE_INVALID)
        self.assertEqual(
            codigo(govpolicy.LevelSpec.from_dict, {"severity": "required", "accepts": ["x"]}),
            govpolicy.CODE_INVALID,
        )

    def test_from_dict_opcionales_por_defecto(self):
        s = govpolicy.LevelSpec.from_dict({"severity": "required", "accepts": ["attestation"]})
        self.assertIsNone(s.accepted_kinds)
        self.assertEqual(s.min_attestation_kind, "declared")


class TestPolicyRequirement(unittest.TestCase):
    def test_valido_y_normaliza_orden_niveles(self):
        r = govpolicy.PolicyRequirement("r1", "privacy", {"high": ls(), "low": ls("recommended")}, "desc")
        self.assertEqual(tuple(r.levels), ("low", "high"))

    def test_ids_invalidos(self):
        for rid in ("", "BAD", "con espacio", "a" * 65, "-x", 5, None, True):
            with self.subTest(rid=rid):
                self.assertEqual(
                    codigo(govpolicy.PolicyRequirement, rid, "privacy", {"low": ls()}),
                    govpolicy.CODE_INVALID,
                )

    def test_id_limite_64_valido(self):
        self.assertEqual(requisito("a" * 64).requirement_id, "a" * 64)

    def test_ids_reservados_y_estructurales(self):
        for rid in tuple(core.RESERVED_CARD_IDS) + tuple(govpolicy.STRUCTURAL_REQUIREMENT_IDS):
            with self.subTest(rid=rid):
                self.assertEqual(
                    codigo(govpolicy.PolicyRequirement, rid, "privacy", {"low": ls()}),
                    govpolicy.CODE_INVALID,
                )
                self.assertEqual(codigo(govpolicy.RequirementOverride, rid, {"low": ls()}), govpolicy.CODE_INVALID)

    def test_estructurales_exactos(self):
        self.assertEqual(govpolicy.STRUCTURAL_REQUIREMENT_IDS, ("model_card_pin", "policy_hardening_pin"))

    def test_dimension_invalida(self):
        for dim in ("otra", "", None, 1, "Privacy"):
            with self.subTest(dim=dim):
                self.assertEqual(codigo(govpolicy.PolicyRequirement, "r1", dim, {"low": ls()}), govpolicy.CODE_INVALID)

    def test_levels_invalidos(self):
        casos = [
            {},
            None,
            [],
            {"critical": ls()},
            {"unassessed": ls()},
            {"low": {"severity": "required"}},
            {"low": None},
            {1: ls()},
        ]
        for i, lv in enumerate(casos):
            with self.subTest(i=i):
                self.assertEqual(codigo(govpolicy.PolicyRequirement, "r1", "privacy", lv), govpolicy.CODE_INVALID)

    def test_description_invalida(self):
        self.assertEqual(
            codigo(govpolicy.PolicyRequirement, "r1", "privacy", {"low": ls()}, 5), govpolicy.CODE_INVALID
        )

    def test_round_trip_y_estricto(self):
        r = govpolicy.BASE_POLICY.requirements[0]
        self.assertEqual(govpolicy.PolicyRequirement.from_dict(r.to_dict()), r)
        d = r.to_dict()
        d["otra"] = 1
        self.assertEqual(codigo(govpolicy.PolicyRequirement.from_dict, d), govpolicy.CODE_UNKNOWN_KEY)
        d = r.to_dict()
        del d["levels"]
        self.assertEqual(codigo(govpolicy.PolicyRequirement.from_dict, d), govpolicy.CODE_INVALID)
        d = r.to_dict()
        d["levels"]["low"]["extra"] = 1
        self.assertEqual(codigo(govpolicy.PolicyRequirement.from_dict, d), govpolicy.CODE_UNKNOWN_KEY)
        d = r.to_dict()
        d["levels"]["critical"] = d["levels"]["low"]
        self.assertEqual(codigo(govpolicy.PolicyRequirement.from_dict, d), govpolicy.CODE_INVALID)


class TestGovernancePolicy(unittest.TestCase):
    def test_version_estricta(self):
        for v in (True, False, 0, -1, 1.0, "1", None):
            with self.subTest(v=v):
                self.assertEqual(codigo(govpolicy.GovernancePolicy, "p1", v, ()), govpolicy.CODE_INVALID)

    def test_policy_id_invalido(self):
        for pid in ("", "BAD", 3, None, "a" * 65):
            with self.subTest(pid=pid):
                self.assertEqual(codigo(govpolicy.GovernancePolicy, pid, 1, ()), govpolicy.CODE_INVALID)

    def test_requisitos_duplicados(self):
        self.assertEqual(
            codigo(govpolicy.GovernancePolicy, "p1", 1, (requisito("a"), requisito("a"))), govpolicy.CODE_INVALID
        )

    def test_requisitos_tipo(self):
        self.assertEqual(codigo(govpolicy.GovernancePolicy, "p1", 1, "x"), govpolicy.CODE_INVALID)
        self.assertEqual(codigo(govpolicy.GovernancePolicy, "p1", 1, None), govpolicy.CODE_INVALID)
        self.assertEqual(codigo(govpolicy.GovernancePolicy, "p1", 1, ({"requirement_id": "a"},)), govpolicy.CODE_INVALID)

    def test_schema_version(self):
        self.assertEqual(
            codigo(govpolicy.GovernancePolicy, "p1", 1, (), 2), govpolicy.CODE_SCHEMA_UNSUPPORTED
        )
        self.assertEqual(codigo(govpolicy.GovernancePolicy, "p1", 1, (), True), govpolicy.CODE_INVALID)
        self.assertEqual(codigo(govpolicy.GovernancePolicy, "p1", 1, (), "1"), govpolicy.CODE_INVALID)

    def test_requisitos_ordenados_por_id(self):
        p = govpolicy.GovernancePolicy("p1", 1, (requisito("b"), requisito("a")))
        self.assertEqual([r.requirement_id for r in p.requirements], ["a", "b"])

    def test_hash_independiente_del_orden(self):
        reqs = [requisito("a"), requisito("b"), requisito("c", "privacy")]
        hashes = {
            govpolicy.GovernancePolicy("p1", 1, perm).content_sha256() for perm in itertools.permutations(reqs)
        }
        self.assertEqual(len(hashes), 1)

    def test_round_trip(self):
        p = govpolicy.BASE_POLICY
        d = p.to_dict()
        self.assertEqual(d["schema_version"], 1)
        self.assertEqual(govpolicy.GovernancePolicy.from_dict(d), p)
        self.assertEqual(govpolicy.GovernancePolicy.from_dict(json.loads(json.dumps(d))), p)
        self.assertEqual(govpolicy.GovernancePolicy.from_dict(d).content_sha256(), p.content_sha256())

    def test_from_dict_schema_ajeno(self):
        d = govpolicy.BASE_POLICY.to_dict()
        d["schema_version"] = 2
        self.assertEqual(codigo(govpolicy.GovernancePolicy.from_dict, d), govpolicy.CODE_SCHEMA_UNSUPPORTED)
        d["schema_version"] = True
        self.assertEqual(codigo(govpolicy.GovernancePolicy.from_dict, d), govpolicy.CODE_INVALID)

    def test_from_dict_sin_schema_version_ok(self):
        d = govpolicy.BASE_POLICY.to_dict()
        del d["schema_version"]
        self.assertEqual(govpolicy.GovernancePolicy.from_dict(d), govpolicy.BASE_POLICY)

    def test_from_dict_estricto(self):
        d = govpolicy.BASE_POLICY.to_dict()
        d["otra"] = 1
        self.assertEqual(codigo(govpolicy.GovernancePolicy.from_dict, d), govpolicy.CODE_UNKNOWN_KEY)
        for clave in ("policy_id", "version", "requirements"):
            d = govpolicy.BASE_POLICY.to_dict()
            del d[clave]
            with self.subTest(clave=clave):
                self.assertEqual(codigo(govpolicy.GovernancePolicy.from_dict, d), govpolicy.CODE_INVALID)
        d = govpolicy.BASE_POLICY.to_dict()
        d["version"] = True
        self.assertEqual(codigo(govpolicy.GovernancePolicy.from_dict, d), govpolicy.CODE_INVALID)
        d = govpolicy.BASE_POLICY.to_dict()
        d["requirements"] = "x"
        self.assertEqual(codigo(govpolicy.GovernancePolicy.from_dict, d), govpolicy.CODE_INVALID)
        d = govpolicy.BASE_POLICY.to_dict()
        d["requirements"].append(copy.deepcopy(d["requirements"][0]))
        self.assertEqual(codigo(govpolicy.GovernancePolicy.from_dict, d), govpolicy.CODE_INVALID)
        for malo in (None, [], "x"):
            self.assertEqual(codigo(govpolicy.GovernancePolicy.from_dict, malo), govpolicy.CODE_INVALID)

    def test_hash_es_sha256_del_json_canonico(self):
        esperado = hashlib.sha256(core.canonical_json(govpolicy.BASE_POLICY.to_dict()).encode("utf-8")).hexdigest()
        self.assertEqual(govpolicy.BASE_POLICY.content_sha256(), esperado)


class TestHardeningDocument(unittest.TestCase):
    def test_valido_defaults(self):
        h = hard()
        self.assertIsNone(h.risk_floor)
        self.assertEqual((h.overrides, h.additional), ((), ()))

    def test_campos_invalidos(self):
        casos = [
            lambda: govpolicy.HardeningDocument("BAD", 1),
            lambda: govpolicy.HardeningDocument("harmessi-base", True),
            lambda: govpolicy.HardeningDocument("harmessi-base", 0),
            lambda: govpolicy.HardeningDocument("harmessi-base", "1"),
            lambda: govpolicy.HardeningDocument("harmessi-base", 1, risk_floor="critical"),
            lambda: govpolicy.HardeningDocument("harmessi-base", 1, risk_floor="unassessed"),
            lambda: govpolicy.HardeningDocument("harmessi-base", 1, risk_floor=1),
            lambda: govpolicy.HardeningDocument("harmessi-base", 1, overrides="x"),
            lambda: govpolicy.HardeningDocument("harmessi-base", 1, overrides=({"requirement_id": "a"},)),
            lambda: govpolicy.HardeningDocument("harmessi-base", 1, additional=({"requirement_id": "a"},)),
            lambda: govpolicy.HardeningDocument(
                "harmessi-base", 1, overrides=(ov("privacy_evidence", {"high": ls()}), ov("privacy_evidence", {"low": ls()}))
            ),
            lambda: govpolicy.HardeningDocument("harmessi-base", 1, additional=(requisito("x"), requisito("x"))),
            lambda: govpolicy.RequirementOverride("privacy_evidence", {}),
            lambda: govpolicy.RequirementOverride("privacy_evidence", {"low": "x"}),
        ]
        for i, caso in enumerate(casos):
            with self.subTest(i=i):
                self.assertEqual(codigo(caso), govpolicy.CODE_INVALID)

    def test_orden_normalizado(self):
        h = hard(
            overrides=(ov("security_evidence", {"high": ls()}), ov("privacy_evidence", {"high": ls()})),
            additional=(requisito("zeta"), requisito("alfa")),
        )
        self.assertEqual([o.requirement_id for o in h.overrides], ["privacy_evidence", "security_evidence"])
        self.assertEqual([r.requirement_id for r in h.additional], ["alfa", "zeta"])

    def test_round_trip(self):
        h = hard(
            "medium",
            overrides=(ov("privacy_evidence", {"high": mixto("required", "anchored")}),),
            additional=(requisito("extra_check"),),
        )
        d = h.to_dict()
        self.assertEqual(d["schema_version"], 1)
        self.assertEqual(govpolicy.HardeningDocument.from_dict(d), h)
        self.assertEqual(govpolicy.HardeningDocument.from_dict(json.loads(json.dumps(d))), h)
        self.assertEqual(govpolicy.HardeningDocument.from_dict(d).content_sha256(), h.content_sha256())

    def test_from_dict_minimo(self):
        h = govpolicy.HardeningDocument.from_dict({"policy_id": "harmessi-base", "base_version": 1})
        self.assertEqual(h, hard())

    def test_from_dict_estricto(self):
        valido = hard("low").to_dict()
        self.assertEqual(codigo(govpolicy.HardeningDocument.from_dict, dict(valido, otra=1)), govpolicy.CODE_UNKNOWN_KEY)
        self.assertEqual(
            codigo(govpolicy.HardeningDocument.from_dict, dict(valido, schema_version=2)),
            govpolicy.CODE_SCHEMA_UNSUPPORTED,
        )
        self.assertEqual(
            codigo(govpolicy.HardeningDocument.from_dict, dict(valido, schema_version=True)), govpolicy.CODE_INVALID
        )
        self.assertEqual(codigo(govpolicy.HardeningDocument.from_dict, dict(valido, base_version=True)), govpolicy.CODE_INVALID)
        self.assertEqual(codigo(govpolicy.HardeningDocument.from_dict, dict(valido, overrides="x")), govpolicy.CODE_INVALID)
        self.assertEqual(codigo(govpolicy.HardeningDocument.from_dict, dict(valido, additional=3)), govpolicy.CODE_INVALID)
        self.assertEqual(
            codigo(govpolicy.HardeningDocument.from_dict, dict(valido, overrides=[{"requirement_id": "a", "levels": {}, "x": 1}])),
            govpolicy.CODE_UNKNOWN_KEY,
        )
        for clave in ("policy_id", "base_version"):
            d = dict(valido)
            del d[clave]
            with self.subTest(clave=clave):
                self.assertEqual(codigo(govpolicy.HardeningDocument.from_dict, d), govpolicy.CODE_INVALID)
        self.assertEqual(codigo(govpolicy.HardeningDocument.from_dict, None), govpolicy.CODE_INVALID)


class TestEffectivePolicyTipos(unittest.TestCase):
    def _kw(self, **cambios):
        kw = dict(
            policy_id="harmessi-base",
            base_version=1,
            base_sha256="a" * 64,
            hardening_sha256=None,
            risk_floor=None,
            requirements=(),
        )
        kw.update(cambios)
        return kw

    def test_valida(self):
        e = govpolicy.EffectivePolicy(**self._kw())
        self.assertEqual(len(e.effective_sha256()), 64)

    def test_invalidos(self):
        for cambio in (
            {"policy_id": "BAD"},
            {"base_version": True},
            {"base_version": 0},
            {"base_sha256": "xyz"},
            {"base_sha256": "A" * 64},
            {"base_sha256": 5},
            {"hardening_sha256": "xyz"},
            {"hardening_sha256": 5},
            {"risk_floor": "critical"},
            {"requirements": (requisito("a"), requisito("a"))},
            {"requirements": ("x",)},
        ):
            with self.subTest(cambio=cambio):
                self.assertEqual(codigo(govpolicy.EffectivePolicy, **self._kw(**cambio)), govpolicy.CODE_INVALID)


# ---------------------------------------------------------------------------
# BASE_POLICY (R21-R22b, R64)
# ---------------------------------------------------------------------------


class TestBasePolicy(unittest.TestCase):
    def test_identidad(self):
        self.assertEqual(govpolicy.BASE_POLICY.policy_id, "harmessi-base")
        self.assertEqual(govpolicy.BASE_POLICY.version, 1)
        self.assertEqual(govpolicy.BASE_POLICY.schema_version, 1)

    def test_hash_congelado_literal(self):
        # Si falla: NO ajustar el literal (matriz aprobada y congelada); reportar.
        self.assertEqual(govpolicy.BASE_POLICY_SHA256, BASE_SHA256_CONGELADO)
        self.assertEqual(govpolicy.BASE_POLICY.content_sha256(), BASE_SHA256_CONGELADO)

    def test_es_monotonica(self):
        self.assertEqual(govpolicy.validate_monotonic(govpolicy.BASE_POLICY), [])

    def test_matriz_exacta_r22(self):
        self.assertEqual({r.requirement_id for r in govpolicy.BASE_POLICY.requirements}, set(MATRIZ))
        for rid, (dimension, niveles) in MATRIZ.items():
            r = req_de(govpolicy.BASE_POLICY, rid)
            with self.subTest(rid=rid):
                self.assertEqual(r.dimension, dimension)
                self.assertEqual(set(r.levels), set(niveles))
            for nivel in govpolicy.LEVELS:
                with self.subTest(rid=rid, nivel=nivel):
                    if nivel not in niveles:
                        self.assertNotIn(nivel, r.levels)
                        continue
                    sev, accepts, kinds, minimo = niveles[nivel]
                    s = r.levels[nivel]
                    self.assertEqual(s.severity, sev)
                    self.assertEqual(s.accepts, accepts)
                    self.assertEqual(s.accepted_kinds, kinds)
                    self.assertEqual(s.min_attestation_kind, minimo)

    def test_ausentes_explicitos(self):
        for rid in ("human_oversight_process", "fairness_evidence", "explainability_evidence"):
            self.assertNotIn("low", req_de(govpolicy.BASE_POLICY, rid).levels)
        for rid in ("accountability_risk_declaration", "accountability_owner", "privacy_evidence", "security_evidence"):
            self.assertEqual(set(req_de(govpolicy.BASE_POLICY, rid).levels), set(govpolicy.LEVELS))

    def test_fairness_high_no_acepta_atestacion(self):
        s = req_de(govpolicy.BASE_POLICY, "fairness_evidence").levels["high"]
        self.assertEqual(s.accepts, ("observed",))
        self.assertEqual(s.severity, "required")
        self.assertNotIn(govpolicy.ATOM_ATT_DECLARED, govpolicy.atoms(s))
        self.assertNotIn(govpolicy.ATOM_ATT_ANCHORED, govpolicy.atoms(s))

    def test_progresividad_presencia(self):
        def ids(nivel):
            return {r.requirement_id for r, _ in govpolicy.requirements_at(govpolicy.BASE_POLICY, nivel)}

        self.assertLessEqual(ids("low"), ids("medium"))
        self.assertLessEqual(ids("medium"), ids("high"))
        self.assertLess(ids("low"), ids("high"))

    def test_progresividad_fuerza(self):
        for r in govpolicy.BASE_POLICY.requirements:
            for inf, sup in zip(govpolicy.LEVELS, govpolicy.LEVELS[1:]):
                with self.subTest(rid=r.requirement_id, inf=inf, sup=sup):
                    self.assertTrue(govpolicy.at_least_as_strong(r.levels.get(sup), r.levels.get(inf)))

    def test_conteo_por_nivel(self):
        self.assertEqual(
            [len(govpolicy.requirements_at(govpolicy.BASE_POLICY, n)) for n in govpolicy.LEVELS], [4, 7, 7]
        )

    def test_round_trip_conserva_hash(self):
        rt = govpolicy.GovernancePolicy.from_dict(json.loads(json.dumps(govpolicy.BASE_POLICY.to_dict())))
        self.assertEqual(rt.content_sha256(), BASE_SHA256_CONGELADO)


# ---------------------------------------------------------------------------
# Orden de fuerza (R17)
# ---------------------------------------------------------------------------


class TestOrdenDeFuerza(unittest.TestCase):
    def test_atoms(self):
        self.assertEqual(
            govpolicy.atoms(ls(accepts=("observed",), kinds=("drift_evidence",))), frozenset({"drift_evidence"})
        )
        self.assertEqual(
            govpolicy.atoms(att("declared")), frozenset({"att_declared", "att_anchored"})
        )
        self.assertEqual(govpolicy.atoms(att("anchored")), frozenset({"att_anchored"}))
        self.assertEqual(
            govpolicy.atoms(ls(accepts=("observed",), kinds=None)),
            frozenset(govpolicy.EXTERNAL_EVIDENCE_KINDS) | {"model_card", "governance_policy"},
        )
        self.assertEqual(
            govpolicy.atoms(mixto("required", "anchored")), frozenset(EXT) | {"att_anchored"}
        )
        self.assertEqual(codigo(govpolicy.atoms, "x"), govpolicy.CODE_INVALID)
        self.assertEqual(codigo(govpolicy.atoms, None), govpolicy.CODE_INVALID)

    def test_tabla_de_pares(self):
        k2 = ("drift_evidence", "evidence_document")
        k3 = ("drift_evidence", "evidence_document", "observed_metric")
        base = ls("required", OBS_ATT, None, "declared")
        # (nombre, b, a, esperado)  -> at_least_as_strong(b, a)
        tabla = [
            ("identico", base, base, True),
            # severidad
            ("required>=recommended", ls("required"), ls("recommended"), True),
            ("recommended<required", ls("recommended"), ls("required"), False),
            ("recommended==recommended", ls("recommended"), ls("recommended"), True),
            # accepts
            ("accepts restringido a observed", ls(accepts=("observed",)), base, True),
            ("accepts restringido a attestation", ls(accepts=("attestation",)), base, True),
            ("accepts ampliado desde observed", base, ls(accepts=("observed",)), False),
            ("accepts ampliado desde attestation", base, ls(accepts=("attestation",)), False),
            ("observed vs attestation disjuntos 1", ls(accepts=("observed",)), ls(accepts=("attestation",)), False),
            ("observed vs attestation disjuntos 2", ls(accepts=("attestation",)), ls(accepts=("observed",)), False),
            # accepted_kinds
            ("kinds restringido vs None", ls(kinds=k2), base, True),
            ("None vs kinds (ampliado)", base, ls(kinds=k2), False),
            ("kinds subconjunto", ls(kinds=k2), ls(kinds=k3), True),
            ("kinds superconjunto", ls(kinds=k3), ls(kinds=k2), False),
            ("kinds iguales", ls(kinds=k2), ls(kinds=k2), True),
            ("kinds disjuntos", ls(kinds=("drift_evidence",)), ls(kinds=("evidence_document",)), False),
            ("kinds EXT vs None (estructurales fuera)", ls(kinds=EXT), ls(kinds=None), True),
            ("None vs kinds EXT", ls(kinds=None), ls(kinds=EXT), False),
            # min_attestation_kind
            ("anchored vs declared", att("anchored"), att("declared"), True),
            ("declared vs anchored", att("declared"), att("anchored"), False),
            ("anchored igual", att("anchored"), att("anchored"), True),
            ("min irrelevante sin attestation", ls(accepts=("observed",), minimo="anchored"), ls(accepts=("observed",), minimo="declared"), True),
            ("min irrelevante sin attestation (inverso)", ls(accepts=("observed",), minimo="declared"), ls(accepts=("observed",), minimo="anchored"), True),
            # combinaciones: más severo pero ampliado => no
            ("severo pero ampliado", ls("required", OBS_ATT), ls("recommended", ("observed",)), False),
            ("débil pero restringido", ls("recommended", ("observed",)), ls("required", OBS_ATT), False),
            ("severo y restringido", ls("required", ("observed",), k2), ls("recommended", OBS_ATT, k3), True),
            # ausente
            ("presente vs ausente", base, None, True),
            ("ausente vs presente", None, base, False),
            ("ausente vs ausente", None, None, True),
        ]
        for nombre, b, a, esperado in tabla:
            with self.subTest(nombre):
                self.assertIs(govpolicy.at_least_as_strong(b, a), esperado)

    def test_tipos_invalidos(self):
        for b, a in (("x", ls()), (ls(), "x"), ({}, None), (None, 3)):
            with self.subTest(b=b, a=a):
                self.assertEqual(codigo(govpolicy.at_least_as_strong, b, a), govpolicy.CODE_INVALID)

    def test_reflexiva_y_transitiva_en_base(self):
        specs = [s for r in govpolicy.BASE_POLICY.requirements for s in r.levels.values()]
        for s in specs:
            self.assertTrue(govpolicy.at_least_as_strong(s, s))
        for a, b, c in itertools.product(specs, repeat=3):
            if govpolicy.at_least_as_strong(a, b) and govpolicy.at_least_as_strong(b, c):
                self.assertTrue(govpolicy.at_least_as_strong(a, c))


# ---------------------------------------------------------------------------
# Monotonicidad (R18)
# ---------------------------------------------------------------------------


class TestValidateMonotonic(unittest.TestCase):
    def test_policy_no_monotonica_por_fuerza(self):
        p = govpolicy.GovernancePolicy(
            "p1",
            1,
            (
                govpolicy.PolicyRequirement(
                    "r1", "privacy", {"low": att("anchored"), "medium": att("declared"), "high": att("anchored")}
                ),
            ),
        )
        # low->medium falla (declared amplía); medium->high es válido (anchored restringe).
        h = govpolicy.validate_monotonic(p)
        self.assertEqual(len(h), 1)
        self.assertIsInstance(h[0], core.Hallazgo)
        self.assertEqual(h[0].code, govpolicy.CODE_NOT_MONOTONIC)
        self.assertEqual(h[0].path, "r1.low->medium")

    def test_policy_no_monotonica_por_severidad(self):
        p = govpolicy.GovernancePolicy(
            "p1", 1, (govpolicy.PolicyRequirement("r1", "privacy", {"medium": ls("required"), "high": ls("recommended")}),)
        )
        self.assertEqual([x.path for x in govpolicy.validate_monotonic(p)], ["r1.medium->high"])

    def test_presencia_desaparece_al_subir(self):
        p = govpolicy.GovernancePolicy(
            "p1", 1, (govpolicy.PolicyRequirement("r1", "privacy", {"low": ls(), "high": ls()}),)
        )
        paths = [x.path for x in govpolicy.validate_monotonic(p)]
        self.assertEqual(paths, ["r1.low->medium"])

    def test_presencia_aparece_al_subir_es_monotona(self):
        p = govpolicy.GovernancePolicy(
            "p1", 1, (govpolicy.PolicyRequirement("r1", "privacy", {"high": ls()}),)
        )
        self.assertEqual(govpolicy.validate_monotonic(p), [])

    def test_varios_hallazgos(self):
        p = govpolicy.GovernancePolicy(
            "p1",
            1,
            (
                # r1: solo falla low->medium (severidad); medium->high es válido.
                govpolicy.PolicyRequirement(
                    "r1", "privacy", {"low": ls(), "medium": ls("recommended"), "high": ls("recommended")}
                ),
                govpolicy.PolicyRequirement("r2", "security", {"medium": ls(), "high": ls("recommended")}),
            ),
        )
        self.assertEqual({x.path for x in govpolicy.validate_monotonic(p)}, {"r1.low->medium", "r2.medium->high"})

    def test_acepta_effective_policy(self):
        self.assertEqual(govpolicy.validate_monotonic(merge_base()), [])

    def test_tipo_invalido(self):
        for malo in ("x", None, {}, 3):
            with self.subTest(malo=malo):
                self.assertEqual(codigo(govpolicy.validate_monotonic, malo), govpolicy.CODE_INVALID)


# ---------------------------------------------------------------------------
# merge (R25-R29)
# ---------------------------------------------------------------------------


class TestMergeSinHardening(unittest.TestCase):
    def test_equivalente_a_la_base(self):
        e = merge_base(None)
        self.assertIsInstance(e, govpolicy.EffectivePolicy)
        self.assertEqual(e.policy_id, "harmessi-base")
        self.assertEqual(e.base_version, 1)
        self.assertEqual(e.base_sha256, BASE_SHA256_CONGELADO)
        self.assertIsNone(e.hardening_sha256)
        self.assertIsNone(e.risk_floor)
        self.assertEqual(e.requirements, govpolicy.BASE_POLICY.requirements)

    def test_hash_determinista(self):
        self.assertEqual(merge_base().effective_sha256(), merge_base().effective_sha256())
        self.assertEqual(merge_base(), merge_base())

    def test_hash_es_sha256_canonico_de_to_dict(self):
        e = merge_base()
        esperado = hashlib.sha256(core.canonical_json(e.to_dict()).encode("utf-8")).hexdigest()
        self.assertEqual(e.effective_sha256(), esperado)
        self.assertEqual(
            set(e.to_dict()),
            {"policy_id", "base_version", "base_sha256", "hardening_sha256", "risk_floor", "requirements"},
        )

    def test_hardening_vacio_difiere_en_hash(self):
        # Un documento vacío (sin cambios) deja los requisitos pero registra su hash.
        vacio = merge_base(hard())
        self.assertEqual(vacio.requirements, govpolicy.BASE_POLICY.requirements)
        self.assertEqual(vacio.hardening_sha256, hard().content_sha256())
        self.assertNotEqual(vacio.effective_sha256(), merge_base().effective_sha256())

    def test_tipos_invalidos(self):
        self.assertEqual(codigo(govpolicy.merge, "x"), govpolicy.CODE_INVALID)
        self.assertEqual(codigo(govpolicy.merge, None), govpolicy.CODE_INVALID)
        self.assertEqual(codigo(govpolicy.merge, govpolicy.BASE_POLICY, {}), govpolicy.CODE_INVALID)
        self.assertEqual(codigo(govpolicy.merge, govpolicy.BASE_POLICY, "x"), govpolicy.CODE_INVALID)
        # Una EffectivePolicy es base válida (capas apiladas); merge(e, None) la devuelve.
        e = merge_base()
        self.assertIs(govpolicy.merge(e, None), e)


class TestMergeEndurecimientosValidos(unittest.TestCase):
    def test_subir_risk_floor(self):
        for piso in govpolicy.LEVELS:
            with self.subTest(piso=piso):
                e = merge_base(hard(piso))
                self.assertEqual(e.risk_floor, piso)
                self.assertEqual(e.requirements, govpolicy.BASE_POLICY.requirements)
                self.assertEqual(e.hardening_sha256, hard(piso).content_sha256())

    def test_required_sobre_recommended(self):
        h = hard(overrides=(ov("human_oversight_process", {"medium": mixto("required", "declared")}),))
        e = merge_base(h)
        r = req_de(e, "human_oversight_process")
        self.assertEqual(r.levels["medium"].severity, "required")
        self.assertEqual(r.levels["high"], req_de(govpolicy.BASE_POLICY, "human_oversight_process").levels["high"])
        self.assertNotIn("low", r.levels)

    def test_restringir_accepted_kinds(self):
        kinds = ("evidence_document", "execution_record")
        h = hard(
            overrides=(
                ov(
                    "privacy_evidence",
                    {
                        "low": ls("recommended", OBS_ATT, kinds, "declared"),
                        "medium": ls("required", OBS_ATT, kinds, "declared"),
                        "high": ls("required", OBS_ATT, kinds, "anchored"),
                    },
                ),
            )
        )
        e = merge_base(h)
        self.assertEqual(req_de(e, "privacy_evidence").levels["medium"].accepted_kinds, kinds)
        self.assertEqual(req_de(e, "security_evidence"), req_de(govpolicy.BASE_POLICY, "security_evidence"))

    def test_restringir_None_a_kinds_en_base_personalizada(self):
        # Base monótona (presente en los tres niveles, specs iguales).
        base = govpolicy.GovernancePolicy(
            "p1", 1, (govpolicy.PolicyRequirement("r1", "privacy", {n: ls() for n in govpolicy.LEVELS}),)
        )
        restringido = ls(kinds=("drift_evidence",))
        e = govpolicy.merge(
            base, hard(policy_id="p1", overrides=(ov("r1", {n: restringido for n in govpolicy.LEVELS}),))
        )
        for nivel in govpolicy.LEVELS:
            self.assertEqual(req_de(e, "r1").levels[nivel].accepted_kinds, ("drift_evidence",))

    def test_exigir_anchored_donde_alcanzaba_declared(self):
        h = hard(
            overrides=(ov("accountability_owner", {"low": att("anchored"), "medium": att("anchored"), "high": att("anchored")}),)
        )
        e = merge_base(h)
        for nivel in govpolicy.LEVELS:
            self.assertEqual(req_de(e, "accountability_owner").levels[nivel].min_attestation_kind, "anchored")

    def test_quitar_aceptacion_de_atestacion(self):
        solo_obs = ls("required", ("observed",), EXT, "declared")
        h = hard(overrides=(ov("security_evidence", {n: solo_obs for n in govpolicy.LEVELS}),))
        e = merge_base(h)
        for nivel in govpolicy.LEVELS:
            self.assertEqual(req_de(e, "security_evidence").levels[nivel].accepts, ("observed",))

    def test_requisito_adicional(self):
        extra = govpolicy.PolicyRequirement("extra_security_review", "security", {"high": ls("required", ("observed",), EXT)})
        e = merge_base(hard(additional=(extra,)))
        self.assertEqual(len(e.requirements), len(govpolicy.BASE_POLICY.requirements) + 1)
        self.assertEqual(req_de(e, "extra_security_review"), extra)
        # Los de la base quedan intactos.
        for r in govpolicy.BASE_POLICY.requirements:
            self.assertEqual(req_de(e, r.requirement_id), r)

    def test_agregar_nivel_donde_la_base_estaba_ausente(self):
        debil = ls("recommended", OBS_ATT, None, "declared")
        h = hard(overrides=(ov("fairness_evidence", {"low": debil}),))
        e = merge_base(h)
        r = req_de(e, "fairness_evidence")
        self.assertEqual(r.levels["low"], debil)
        self.assertEqual(set(r.levels), {"low", "medium", "high"})
        self.assertEqual(len(govpolicy.requirements_at(e, "low")), 5)

    def test_override_parcial_conserva_otros_niveles(self):
        # Un override solo toca los niveles indicados: no puede "quitar" niveles.
        e = merge_base(hard(overrides=(ov("privacy_evidence", {"high": ls("required", ("observed",), EXT, "declared")}),)))
        base_r = req_de(govpolicy.BASE_POLICY, "privacy_evidence")
        r = req_de(e, "privacy_evidence")
        self.assertEqual(r.levels["low"], base_r.levels["low"])
        self.assertEqual(r.levels["medium"], base_r.levels["medium"])
        self.assertEqual(r.dimension, base_r.dimension)
        self.assertEqual(r.description, base_r.description)

    def test_override_no_modifica_la_base(self):
        merge_base(hard("high", overrides=(ov("privacy_evidence", {"high": ls("required", ("observed",), EXT)}),)))
        self.assertEqual(govpolicy.BASE_POLICY.content_sha256(), BASE_SHA256_CONGELADO)

    def test_combinacion_de_endurecimientos(self):
        h = hard(
            "medium",
            overrides=(ov("human_oversight_process", {"medium": mixto("required", "declared")}),),
            additional=(requisito("extra_check", "privacy", {"medium": ls("recommended"), "high": ls("recommended")}),),
        )
        e = merge_base(h)
        self.assertEqual(e.risk_floor, "medium")
        self.assertEqual(req_de(e, "human_oversight_process").levels["medium"].severity, "required")
        self.assertIn("extra_check", [r.requirement_id for r in e.requirements])


class TestMergeRelajaciones(unittest.TestCase):
    def assert_relajacion(self, documento, base=None):
        self.assertEqual(codigo(govpolicy.merge, base or govpolicy.BASE_POLICY, documento), govpolicy.CODE_RELAXATION)

    def test_required_a_recommended(self):
        self.assert_relajacion(hard(overrides=(ov("accountability_owner", {"low": att("declared", "recommended")}),)))
        self.assert_relajacion(hard(overrides=(ov("privacy_evidence", {"medium": mixto("recommended", "declared")}),)))

    def test_ampliar_accepted_kinds_None_donde_la_base_lista(self):
        self.assert_relajacion(hard(overrides=(ov("privacy_evidence", {"medium": ls("required", OBS_ATT, None, "declared")}),)))

    def test_ampliar_accepted_kinds_extra(self):
        # Base monótona: presente en los tres niveles con kinds restringidos.
        base = govpolicy.GovernancePolicy(
            "p1",
            1,
            (govpolicy.PolicyRequirement("r1", "privacy", {n: ls(kinds=("drift_evidence",)) for n in govpolicy.LEVELS}),),
        )
        self.assert_relajacion(
            hard(policy_id="p1", overrides=(ov("r1", {"low": ls(kinds=("drift_evidence", "evidence_document"))}),)), base
        )
        # Control: repetir el spec de la base (no relaja) es válido y monótono.
        govpolicy.merge(base, hard(policy_id="p1", overrides=(ov("r1", {"low": ls(kinds=("drift_evidence",))}),)))

    def test_ampliar_accepts(self):
        self.assert_relajacion(hard(overrides=(ov("fairness_evidence", {"high": mixto("required", "declared")}),)))
        self.assert_relajacion(hard(overrides=(ov("fairness_evidence", {"high": ls("required", ("attestation",), EXT)}),)))
        base = govpolicy.GovernancePolicy("p1", 1, (govpolicy.PolicyRequirement("r1", "privacy", {"low": att()}),))
        self.assert_relajacion(hard(policy_id="p1", overrides=(ov("r1", {"low": ls("required", OBS_ATT)}),)), base)

    def test_bajar_min_attestation_kind(self):
        self.assert_relajacion(hard(overrides=(ov("accountability_owner", {"high": att("declared")}),)))
        self.assert_relajacion(hard(overrides=(ov("privacy_evidence", {"high": mixto("required", "declared")}),)))

    def test_override_de_requisito_inexistente(self):
        self.assert_relajacion(hard(overrides=(ov("no_existe", {"high": ls()}),)))

    def test_reusar_id_base_en_additional(self):
        self.assert_relajacion(hard(additional=(requisito("privacy_evidence", "privacy", {"high": ls()}),)))
        # Aunque la versión reusada sea más fuerte.
        self.assert_relajacion(
            hard(additional=(requisito("fairness_evidence", "fairness", {"high": ls("required", ("observed",), ("evidence_document",))}),))
        )

    def test_ids_reservados_no_pueden_construirse(self):
        for rid in ("none", "null", "default", "status", "model_card_pin", "policy_hardening_pin"):
            with self.subTest(rid=rid):
                self.assertEqual(codigo(requisito, rid), govpolicy.CODE_INVALID)
                self.assertEqual(codigo(ov, rid, {"high": ls()}), govpolicy.CODE_INVALID)

    def test_no_existe_forma_de_bajar_risk_floor(self):
        # El piso solo puede ser un nivel válido o None; valores de "bajada" no existen.
        for malo in ("critical", "unassessed", "", "LOW", -1, 0):
            with self.subTest(malo=malo):
                self.assertEqual(codigo(hard, malo), govpolicy.CODE_INVALID)
        # Un piso "low" sobre una base sin piso no es relajación.
        self.assertEqual(merge_base(hard("low")).risk_floor, "low")
        # La base (sin piso) no puede ser debilitada por un documento sin piso.
        self.assertIsNone(merge_base(hard(None)).risk_floor)

    def test_override_sin_niveles_es_invalido_no_elimina(self):
        self.assertEqual(codigo(ov, "privacy_evidence", {}), govpolicy.CODE_INVALID)
        self.assertEqual(codigo(govpolicy.RequirementOverride.from_dict, {"requirement_id": "privacy_evidence", "levels": {}}), govpolicy.CODE_INVALID)

    def test_todo_el_documento_rechazado_parte_valida_mas_invalida(self):
        valido = dict(
            floor="high",
            overrides=[ov("human_oversight_process", {"medium": mixto("required", "declared")})],
            additional=[requisito("extra_check", "privacy", {"medium": ls("recommended"), "high": ls("recommended")})],
        )
        # Control: la parte válida sola se aplica.
        e_ok = merge_base(hard(valido["floor"], valido["overrides"], valido["additional"]))
        self.assertEqual(e_ok.risk_floor, "high")
        # Parte válida + una relajación: nada se aplica, ni parcialmente.
        invalido = ov("accountability_owner", {"low": att("declared", "recommended")})
        doc = hard(valido["floor"], valido["overrides"] + [invalido], valido["additional"])
        with self.assertRaises(govpolicy.GovPolicyError) as cm:
            merge_base(doc)
        self.assertEqual(cm.exception.code, govpolicy.CODE_RELAXATION)
        self.assertIn("accountability_owner", cm.exception.message)
        self.assertEqual(govpolicy.BASE_POLICY.content_sha256(), BASE_SHA256_CONGELADO)
        # Tras el rechazo, la base sin hardening sigue produciendo la policy original.
        self.assertEqual(merge_base().requirements, govpolicy.BASE_POLICY.requirements)

    def test_relajacion_junto_a_additional_valido_y_reuso(self):
        doc = hard(
            additional=(requisito("extra_ok"), requisito("privacy_evidence", "privacy", {"high": ls()})),
        )
        self.assert_relajacion(doc)

    def test_reporta_todas_las_violaciones(self):
        doc = hard(
            overrides=(
                ov("accountability_owner", {"low": att("declared", "recommended")}),
                ov("no_existe", {"high": ls()}),
            ),
            additional=(requisito("security_evidence", "security", {"high": ls()}),),
        )
        with self.assertRaises(govpolicy.GovPolicyError) as cm:
            merge_base(doc)
        self.assertEqual(cm.exception.code, govpolicy.CODE_RELAXATION)
        for texto in ("accountability_owner", "no_existe", "security_evidence"):
            self.assertIn(texto, cm.exception.message)


class TestMergeBaseMismatch(unittest.TestCase):
    def test_policy_id_distinto(self):
        self.assertEqual(codigo(govpolicy.merge, govpolicy.BASE_POLICY, hard(policy_id="otra-base")), govpolicy.CODE_BASE_MISMATCH)

    def test_base_version_distinta(self):
        self.assertEqual(codigo(govpolicy.merge, govpolicy.BASE_POLICY, hard(base_version=2)), govpolicy.CODE_BASE_MISMATCH)

    def test_mismatch_gana_a_contenido_invalido(self):
        doc = hard(base_version=2, overrides=(ov("no_existe", {"high": ls()}),))
        self.assertEqual(codigo(govpolicy.merge, govpolicy.BASE_POLICY, doc), govpolicy.CODE_BASE_MISMATCH)


class TestMergeNoMonotonico(unittest.TestCase):
    def test_override_que_rompe_monotonicidad_entre_niveles(self):
        # Sube `low` (más fuerte que la base) pero deja `medium` sin ser al menos tan fuerte.
        h = hard(overrides=(ov("privacy_evidence", {"low": ls("required", ("attestation",), None, "anchored")}),))
        self.assertEqual(codigo(govpolicy.merge, govpolicy.BASE_POLICY, h), govpolicy.CODE_NOT_MONOTONIC)

    def test_nivel_alto_con_requisito_y_medio_ausente(self):
        # Agregar `low` a un requisito que en `medium` es más débil.
        h = hard(overrides=(ov("human_oversight_process", {"low": mixto("required", "declared")}),))
        self.assertEqual(codigo(govpolicy.merge, govpolicy.BASE_POLICY, h), govpolicy.CODE_NOT_MONOTONIC)

    def test_adicional_no_monotono(self):
        r = govpolicy.PolicyRequirement("extra_check", "privacy", {"low": ls("required"), "medium": ls("recommended")})
        self.assertEqual(codigo(govpolicy.merge, govpolicy.BASE_POLICY, hard(additional=(r,))), govpolicy.CODE_NOT_MONOTONIC)

    def test_el_mensaje_nombra_el_tramo(self):
        h = hard(overrides=(ov("privacy_evidence", {"low": ls("required", ("attestation",), None, "anchored")}),))
        with self.assertRaises(govpolicy.GovPolicyError) as cm:
            merge_base(h)
        self.assertIn("privacy_evidence.low->medium", cm.exception.message)

    def test_no_se_aplica_nada_parcial(self):
        h = hard(
            "high",
            overrides=(
                ov("human_oversight_process", {"medium": mixto("required", "declared")}),
                ov("privacy_evidence", {"low": ls("required", ("attestation",), None, "anchored")}),
            ),
        )
        self.assertEqual(codigo(govpolicy.merge, govpolicy.BASE_POLICY, h), govpolicy.CODE_NOT_MONOTONIC)


# ---------------------------------------------------------------------------
# effective_sha256 (R29/R64)
# ---------------------------------------------------------------------------


class TestEffectiveSha256(unittest.TestCase):
    def _doc(self, orden_ov=0, orden_add=0):
        ovs = [
            ov("human_oversight_process", {"medium": mixto("required", "declared")}),
            ov("security_evidence", {"high": ls("required", OBS_ATT, EXT, "anchored")}),
            ov("privacy_evidence", {"high": ls("required", ("observed",), EXT, "anchored")}),
        ]
        adds = [requisito("extra_a", "privacy", {"high": ls()}), requisito("extra_b", "security", {"medium": ls("recommended"), "high": ls("recommended")})]
        ovs = list(itertools.permutations(ovs))[orden_ov % 6]
        adds = list(itertools.permutations(adds))[orden_add % 2]
        return hard("medium", ovs, adds)

    def test_independiente_del_orden(self):
        hashes = {merge_base(self._doc(i, j)).effective_sha256() for i in range(6) for j in range(2)}
        self.assertEqual(len(hashes), 1)
        a, b = merge_base(self._doc(0, 0)), merge_base(self._doc(5, 1))
        self.assertEqual(a, b)
        self.assertEqual([r.requirement_id for r in a.requirements], sorted(r.requirement_id for r in a.requirements))

    def test_independiente_del_orden_de_requisitos_de_la_base(self):
        reqs = list(govpolicy.BASE_POLICY.requirements)
        invertida = govpolicy.GovernancePolicy("harmessi-base", 1, tuple(reversed(reqs)))
        self.assertEqual(govpolicy.merge(invertida).effective_sha256(), merge_base().effective_sha256())

    def test_sensible_a_cambios(self):
        referencia = merge_base(self._doc()).effective_sha256()
        variantes = {
            "piso": hard("high", self._doc().overrides, self._doc().additional),
            "sin_piso": hard(None, self._doc().overrides, self._doc().additional),
            "sin_adicional": hard("medium", self._doc().overrides, ()),
            "adicional_distinto": hard(
                "medium", self._doc().overrides, (requisito("extra_a", "privacy", {"high": ls("required", ("observed",), EXT)}), requisito("extra_b", "security", {"medium": ls("recommended"), "high": ls("recommended")}))
            ),
            "descripcion": hard(
                "medium", self._doc().overrides, (requisito("extra_a", "privacy", {"high": ls()}, "otra"), requisito("extra_b", "security", {"medium": ls("recommended"), "high": ls("recommended")}))
            ),
            "override_distinto": hard(
                "medium",
                (ov("human_oversight_process", {"medium": mixto("required", "anchored")}),) + self._doc().overrides[1:],
                self._doc().additional,
            ),
        }
        vistos = {referencia}
        for nombre, doc in variantes.items():
            with self.subTest(nombre):
                h = merge_base(doc).effective_sha256()
                self.assertNotIn(h, vistos)
                vistos.add(h)

    def test_sensible_a_la_base(self):
        otra = govpolicy.GovernancePolicy(
            "harmessi-base", 1, govpolicy.BASE_POLICY.requirements + (requisito("extra_base", "privacy"),)
        )
        self.assertNotEqual(govpolicy.merge(otra).effective_sha256(), merge_base().effective_sha256())
        self.assertNotEqual(govpolicy.merge(otra).base_sha256, BASE_SHA256_CONGELADO)

    def test_sensible_a_cada_campo_del_efectivo(self):
        e = merge_base(hard("low"))
        h0 = e.effective_sha256()
        for cambio in (
            {"risk_floor": "high"},
            {"base_version": 2},
            {"base_sha256": "b" * 64},
            {"hardening_sha256": "c" * 64},
            {"policy_id": "otra"},
            {"requirements": e.requirements[:-1]},
        ):
            with self.subTest(cambio=cambio):
                self.assertNotEqual(dataclasses.replace(e, **cambio).effective_sha256(), h0)


# ---------------------------------------------------------------------------
# requirements_at / max_level
# ---------------------------------------------------------------------------


class TestRequirementsAt(unittest.TestCase):
    def test_por_nivel_en_base(self):
        esperado = {
            "low": [
                "accountability_owner",
                "accountability_risk_declaration",
                "privacy_evidence",
                "security_evidence",
            ],
            "medium": sorted(MATRIZ),
            "high": sorted(MATRIZ),
        }
        for nivel, ids in esperado.items():
            with self.subTest(nivel=nivel):
                pares = govpolicy.requirements_at(govpolicy.BASE_POLICY, nivel)
                self.assertEqual([r.requirement_id for r, _ in pares], ids)
                for r, s in pares:
                    self.assertIs(s, r.levels[nivel])

    def test_acepta_effective_policy(self):
        e = merge_base(hard(additional=(requisito("extra_h", "privacy", {"high": ls()}),)))
        self.assertIn("extra_h", [r.requirement_id for r, _ in govpolicy.requirements_at(e, "high")])
        self.assertNotIn("extra_h", [r.requirement_id for r, _ in govpolicy.requirements_at(e, "low")])

    def test_invalidos(self):
        for nivel in ("critical", "unassessed", None, 1, "LOW"):
            with self.subTest(nivel=nivel):
                self.assertEqual(codigo(govpolicy.requirements_at, govpolicy.BASE_POLICY, nivel), govpolicy.CODE_INVALID)
        self.assertEqual(codigo(govpolicy.requirements_at, "x", "low"), govpolicy.CODE_INVALID)


class TestMaxLevel(unittest.TestCase):
    def test_tabla(self):
        niveles = govpolicy.LEVELS
        for a in niveles:
            for b in niveles:
                esperado = niveles[max(niveles.index(a), niveles.index(b))]
                with self.subTest(a=a, b=b):
                    self.assertEqual(govpolicy.max_level(a, b), esperado)

    def test_none(self):
        self.assertIsNone(govpolicy.max_level(None, None))
        for n in govpolicy.LEVELS:
            self.assertEqual(govpolicy.max_level(None, n), n)
            self.assertEqual(govpolicy.max_level(n, None), n)

    def test_invalidos(self):
        for malo in ("critical", "unassessed", "", 1, True):
            with self.subTest(malo=malo):
                self.assertEqual(codigo(govpolicy.max_level, malo, "low"), govpolicy.CODE_INVALID)
                self.assertEqual(codigo(govpolicy.max_level, "low", malo), govpolicy.CODE_INVALID)
                self.assertEqual(codigo(govpolicy.max_level, None, malo), govpolicy.CODE_INVALID)


# ---------------------------------------------------------------------------
# Texto (R20) y alcance
# ---------------------------------------------------------------------------


class TestSinLenguajeDeCumplimiento(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texto = FUENTE.read_text(encoding="utf-8")

    def test_no_menciona_leyes_ni_marcos(self):
        prohibidos = [
            r"EU\s+AI\s+Act",
            r"\bNIST\b",
            r"\bISO\b",
            r"\bIEC\b",
            r"\bGDPR\b",
            r"\bRGPD\b",
            r"\bHIPAA\b",
            r"\bSOC\s?2\b",
            r"\bCCPA\b",
        ]
        for patron in prohibidos:
            with self.subTest(patron=patron):
                self.assertIsNone(re.search(patron, self.texto, flags=re.IGNORECASE if patron.startswith("EU") else 0))

    def test_no_afirma_compliance(self):
        self.assertIsNone(re.search(r"compliance|compliant|conforme\s+a|certific", self.texto, flags=re.IGNORECASE))

    def test_cumplimiento_solo_en_negacion(self):
        lineas = [l for l in self.texto.splitlines() if re.search(r"cumplimiento", l, flags=re.IGNORECASE)]
        for linea in lineas:
            with self.subTest(linea=linea):
                self.assertIn("NO", linea)

    def test_declara_alcance_documental(self):
        self.assertIn("DOCUMENTACION/EVIDENCIA", self.texto)

    def test_textos_de_base_sin_lenguaje_normativo(self):
        for r in govpolicy.BASE_POLICY.requirements:
            with self.subTest(rid=r.requirement_id):
                self.assertIsNone(re.search(r"\b(ley|norma|regulaci|compliance|GDPR|NIST|ISO)\b", r.description, flags=re.IGNORECASE))


# ---------------------------------------------------------------------------
# Capas apiladas (merge sobre EffectivePolicy) y paridad de vocabulario
# ---------------------------------------------------------------------------


class TestCapasApiladas(unittest.TestCase):
    def capa1(self, piso="medium"):
        return merge_base(
            hard(
                piso,
                overrides=(ov("human_oversight_process", {"medium": mixto("required", "declared")}),),
                additional=(requisito("extra_l1", "privacy", {"high": ls()}),),
            )
        )

    def test_piso_menor_es_relajacion(self):
        self.assertEqual(codigo(govpolicy.merge, self.capa1("medium"), hard("low")), govpolicy.CODE_RELAXATION)
        self.assertEqual(codigo(govpolicy.merge, self.capa1("high"), hard("medium")), govpolicy.CODE_RELAXATION)
        self.assertEqual(codigo(govpolicy.merge, self.capa1("high"), hard("low")), govpolicy.CODE_RELAXATION)

    def test_piso_menor_rechaza_todo_el_documento(self):
        c1 = self.capa1("medium")
        doc = hard(
            "low",
            overrides=(ov("security_evidence", {"high": ls("required", ("observed",), EXT, "anchored")}),),
            additional=(requisito("extra_l2", "security", {"high": ls()}),),
        )
        with self.assertRaises(govpolicy.GovPolicyError) as cm:
            govpolicy.merge(c1, doc)
        self.assertEqual(cm.exception.code, govpolicy.CODE_RELAXATION)
        self.assertIn("risk_floor", cm.exception.message)
        # Control: sin el piso menor, el resto del documento es válido.
        ok = govpolicy.merge(c1, hard(None, doc.overrides, doc.additional))
        self.assertIn("extra_l2", [r.requirement_id for r in ok.requirements])

    def test_piso_igual_valido(self):
        c1 = self.capa1("medium")
        c2 = govpolicy.merge(c1, hard("medium"))
        self.assertEqual(c2.risk_floor, "medium")

    def test_piso_mayor_es_el_maximo(self):
        self.assertEqual(govpolicy.merge(self.capa1("medium"), hard("high")).risk_floor, "high")
        self.assertEqual(govpolicy.merge(self.capa1("low"), hard("medium")).risk_floor, "medium")

    def test_piso_none_hereda(self):
        self.assertEqual(govpolicy.merge(self.capa1("medium"), hard(None)).risk_floor, "medium")
        self.assertEqual(govpolicy.merge(self.capa1("high"), hard(None)).risk_floor, "high")
        self.assertIsNone(govpolicy.merge(merge_base(), hard(None)).risk_floor)

    def test_relajar_override_de_la_capa_1(self):
        c1 = self.capa1()
        # La capa 1 hizo required lo que la base tenía recommended; la capa 2 lo vuelve recommended.
        doc = hard(overrides=(ov("human_oversight_process", {"medium": mixto("recommended", "declared")}),))
        self.assertEqual(codigo(govpolicy.merge, c1, doc), govpolicy.CODE_RELAXATION)
        # Contra la BASE sola ese mismo documento sería válido (igual a la base): el
        # criterio es el spec EFECTIVO de la capa previa.
        govpolicy.merge(govpolicy.BASE_POLICY, doc)

    def test_capa_2_endurece_mas(self):
        c1 = self.capa1()
        doc = hard(
            "high",
            overrides=(
                ov("human_oversight_process", {"medium": mixto("required", "anchored")}),
                ov("extra_l1", {"high": ls("required", ("observed",), EXT)}),
            ),
            additional=(requisito("extra_l2", "security", {"high": ls()}),),
        )
        c2 = govpolicy.merge(c1, doc)
        self.assertEqual(req_de(c2, "human_oversight_process").levels["medium"].min_attestation_kind, "anchored")
        self.assertEqual(req_de(c2, "extra_l1").levels["high"].accepts, ("observed",))
        self.assertIn("extra_l2", [r.requirement_id for r in c2.requirements])
        self.assertEqual(c2.risk_floor, "high")
        self.assertEqual(govpolicy.validate_monotonic(c2), [])

    def test_reusar_id_agregado_por_capa_1(self):
        c1 = self.capa1()
        self.assertEqual(
            codigo(govpolicy.merge, c1, hard(additional=(requisito("extra_l1", "privacy", {"high": ls()}),))),
            govpolicy.CODE_RELAXATION,
        )
        self.assertEqual(
            codigo(govpolicy.merge, c1, hard(additional=(requisito("privacy_evidence", "privacy", {"high": ls()}),))),
            govpolicy.CODE_RELAXATION,
        )

    def test_override_de_inexistente_en_capa_2(self):
        self.assertEqual(
            codigo(govpolicy.merge, self.capa1(), hard(overrides=(ov("no_existe", {"high": ls()}),))),
            govpolicy.CODE_RELAXATION,
        )

    def test_base_mismatch_entre_capas(self):
        c1 = self.capa1()
        self.assertEqual(codigo(govpolicy.merge, c1, hard(policy_id="otra-base")), govpolicy.CODE_BASE_MISMATCH)
        self.assertEqual(codigo(govpolicy.merge, c1, hard(base_version=2)), govpolicy.CODE_BASE_MISMATCH)

    def test_no_monotonica_en_capa_2(self):
        doc = hard(overrides=(ov("privacy_evidence", {"low": ls("required", ("attestation",), None, "anchored")}),))
        self.assertEqual(codigo(govpolicy.merge, self.capa1(), doc), govpolicy.CODE_NOT_MONOTONIC)

    def test_metadatos_de_la_capa_apilada(self):
        c1 = self.capa1()
        doc = hard("high")
        c2 = govpolicy.merge(c1, doc)
        self.assertEqual(c2.parent_effective_sha256, c1.effective_sha256())
        self.assertEqual(c2.base_sha256, BASE_SHA256_CONGELADO)
        self.assertEqual(c2.base_version, 1)
        self.assertEqual(c2.policy_id, "harmessi-base")
        self.assertEqual(c2.hardening_sha256, doc.content_sha256())
        self.assertIsNone(c1.parent_effective_sha256)

    def test_merge_con_none_devuelve_la_misma_capa(self):
        c1 = self.capa1()
        self.assertIs(govpolicy.merge(c1, None), c1)
        self.assertIs(govpolicy.merge(c1), c1)

    def test_hash_determinista_con_padre(self):
        doc = hard("high", overrides=(ov("extra_l1", {"high": ls("required", ("observed",), EXT)}),))
        a = govpolicy.merge(self.capa1(), doc)
        b = govpolicy.merge(self.capa1(), doc)
        self.assertEqual(a, b)
        self.assertEqual(a.effective_sha256(), b.effective_sha256())

    def test_hash_distinto_de_una_sola_capa(self):
        doc = hard("high")
        c2 = govpolicy.merge(self.capa1(), doc)
        una_capa = dataclasses.replace(c2, parent_effective_sha256=None)
        self.assertNotEqual(c2.effective_sha256(), una_capa.effective_sha256())
        self.assertIn("parent_effective_sha256", c2.to_dict())

    def test_hash_depende_de_la_capa_padre(self):
        doc = hard("high")
        h_a = govpolicy.merge(self.capa1("medium"), doc).effective_sha256()
        h_b = govpolicy.merge(self.capa1("low"), doc).effective_sha256()
        self.assertNotEqual(h_a, h_b)

    def test_hash_independiente_del_orden_en_capa_2(self):
        o1 = ov("human_oversight_process", {"medium": mixto("required", "anchored")})
        o2 = ov("security_evidence", {"high": ls("required", ("observed",), EXT)})
        a = govpolicy.merge(self.capa1(), hard("high", (o1, o2)))
        b = govpolicy.merge(self.capa1(), hard("high", (o2, o1)))
        self.assertEqual(a.effective_sha256(), b.effective_sha256())

    def test_base_only_conserva_hash(self):
        # Sin padre, el hash es el de siempre: la clave `parent_effective_sha256` no entra.
        for doc in (None, hard("low"), hard("high", additional=(requisito("extra_h", "privacy", {"high": ls()}),))):
            with self.subTest(doc=doc):
                e = merge_base(doc)
                self.assertIsNone(e.parent_effective_sha256)
                d = e.to_dict()
                self.assertNotIn("parent_effective_sha256", d)
                self.assertEqual(
                    set(d),
                    {"policy_id", "base_version", "base_sha256", "hardening_sha256", "risk_floor", "requirements"},
                )
                esperado = hashlib.sha256(core.canonical_json(d).encode("utf-8")).hexdigest()
                self.assertEqual(e.effective_sha256(), esperado)
                reconstruida = govpolicy.EffectivePolicy(
                    policy_id=e.policy_id,
                    base_version=e.base_version,
                    base_sha256=e.base_sha256,
                    hardening_sha256=e.hardening_sha256,
                    risk_floor=e.risk_floor,
                    requirements=e.requirements,
                    parent_effective_sha256=None,
                )
                self.assertEqual(reconstruida.effective_sha256(), e.effective_sha256())

    def test_parent_sha_invalido(self):
        e = merge_base()
        for malo in ("xyz", "A" * 64, 5):
            with self.subTest(malo=malo):
                self.assertEqual(
                    codigo(dataclasses.replace, e, parent_effective_sha256=malo), govpolicy.CODE_INVALID
                )

    def test_tres_capas(self):
        c1 = self.capa1("low")
        c2 = govpolicy.merge(c1, hard("medium"))
        c3 = govpolicy.merge(c2, hard(None))
        self.assertEqual(c3.risk_floor, "medium")
        self.assertEqual(c3.parent_effective_sha256, c2.effective_sha256())
        self.assertEqual(codigo(govpolicy.merge, c3, hard("low")), govpolicy.CODE_RELAXATION)


class TestNivelesInmutables(unittest.TestCase):
    """Fix M1: `levels` de PolicyRequirement/RequirementOverride es de solo lectura."""

    def setUp(self):
        self.req = govpolicy.PolicyRequirement(
            "r1", "privacy", {"low": ls("recommended"), "medium": ls(), "high": ls("required", ("observed",), EXT)}, "d"
        )
        self.ovr = govpolicy.RequirementOverride("r1", {"high": ls()})

    def test_asignar_nivel_lanza_typeerror(self):
        for objeto in (self.req, self.ovr):
            with self.subTest(tipo=type(objeto).__name__):
                with self.assertRaises(TypeError):
                    objeto.levels["low"] = ls()
                with self.assertRaises(TypeError):
                    objeto.levels["high"] = ls("recommended")
                with self.assertRaises(TypeError):
                    objeto.levels["inexistente"] = ls()

    def test_borrar_nivel_lanza_typeerror(self):
        for objeto in (self.req, self.ovr):
            with self.subTest(tipo=type(objeto).__name__):
                with self.assertRaises(TypeError):
                    del objeto.levels["high"]

    def test_atributos_internos_no_se_pueden_tocar(self):
        with self.assertRaises(TypeError):
            self.req.levels._datos = {}
        with self.assertRaises(TypeError):
            del self.req.levels._datos

    def test_intentos_no_alteran_el_objeto(self):
        antes = copy.deepcopy(self.req.to_dict())
        for intento in (
            lambda: self.req.levels.__setitem__("low", ls()),
            lambda: self.req.levels.__delitem__("high"),
        ):
            with self.assertRaises((TypeError, AttributeError)):
                intento()
        self.assertEqual(self.req.to_dict(), antes)
        self.assertEqual(tuple(self.req.levels), govpolicy.LEVELS)

    def test_base_policy_no_se_puede_mutar(self):
        for r in govpolicy.BASE_POLICY.requirements:
            nivel = next(iter(r.levels))
            with self.subTest(rid=r.requirement_id):
                with self.assertRaises(TypeError):
                    r.levels[nivel] = ls("recommended", ("observed",))
                with self.assertRaises(TypeError):
                    del r.levels[nivel]
                with self.assertRaises(TypeError):
                    r.levels["low"] = ls()
        self.assertEqual(govpolicy.BASE_POLICY_SHA256, BASE_SHA256_CONGELADO)
        self.assertEqual(govpolicy.BASE_POLICY.content_sha256(), BASE_SHA256_CONGELADO)
        self.assertEqual(merge_base().base_sha256, BASE_SHA256_CONGELADO)

    def test_el_dict_de_entrada_no_queda_enlazado(self):
        entrada = {"low": ls(), "high": ls()}
        r = govpolicy.PolicyRequirement("r1", "privacy", entrada)
        entrada["medium"] = ls("recommended")
        del entrada["low"]
        self.assertEqual(tuple(r.levels), ("low", "high"))

    def test_copy_deepcopy_pickle_preservan_igualdad_y_hash(self):
        import pickle

        for original in (self.req, govpolicy.BASE_POLICY.requirements[0], self.ovr):
            copias = {
                "copy": copy.copy(original),
                "deepcopy": copy.deepcopy(original),
                "pickle": pickle.loads(pickle.dumps(original)),
            }
            for nombre, copia in copias.items():
                with self.subTest(tipo=type(original).__name__, via=nombre):
                    self.assertEqual(copia, original)
                    self.assertEqual(copia.levels, original.levels)
                    self.assertEqual(copia.to_dict(), original.to_dict())
                    with self.assertRaises(TypeError):
                        copia.levels["low"] = ls()
        # Hash de contenido de policies completas tras roundtrip.
        for via in (copy.copy, copy.deepcopy, lambda o: pickle.loads(pickle.dumps(o))):
            copia = via(govpolicy.BASE_POLICY)
            self.assertEqual(copia, govpolicy.BASE_POLICY)
            self.assertEqual(copia.content_sha256(), BASE_SHA256_CONGELADO)
        efectiva = merge_base(hard("high"))
        for via in (copy.copy, copy.deepcopy, lambda o: pickle.loads(pickle.dumps(o))):
            copia = via(efectiva)
            self.assertEqual(copia, efectiva)
            self.assertEqual(copia.effective_sha256(), efectiva.effective_sha256())

    def test_dataclasses_replace(self):
        r2 = dataclasses.replace(self.req, levels=self.req.levels)
        self.assertEqual(r2, self.req)
        self.assertEqual(r2.to_dict(), self.req.to_dict())
        o2 = dataclasses.replace(self.ovr, levels=self.ovr.levels)
        self.assertEqual(o2, self.ovr)
        # replace con un dict nuevo también normaliza.
        r3 = dataclasses.replace(self.req, levels={"high": ls()})
        self.assertEqual(tuple(r3.levels), ("high",))
        with self.assertRaises(TypeError):
            r3.levels["low"] = ls()
        # replace sin tocar levels conserva los niveles.
        r4 = dataclasses.replace(self.req, description="otra")
        self.assertEqual(r4.levels, self.req.levels)

    def test_igualdad_con_dict_y_entre_instancias(self):
        esperado = {"low": ls("recommended"), "medium": ls(), "high": ls("required", ("observed",), EXT)}
        self.assertEqual(self.req.levels, esperado)
        self.assertEqual(esperado, self.req.levels)
        self.assertEqual(dict(self.req.levels), esperado)
        self.assertNotEqual(self.req.levels, {"low": ls("recommended")})
        self.assertNotEqual(self.req.levels, {**esperado, "high": ls("recommended")})
        otro = govpolicy.PolicyRequirement("otro", "security", dict(esperado))
        self.assertEqual(self.req.levels, otro.levels)
        self.assertNotEqual(self.req.levels, self.ovr.levels)
        self.assertEqual(self.ovr.levels, {"high": ls()})
        # Requisitos construidos desde dicts con distinto orden de claves son iguales.
        a = govpolicy.PolicyRequirement("r1", "privacy", {"high": ls(), "low": ls()})
        b = govpolicy.PolicyRequirement("r1", "privacy", {"low": ls(), "high": ls()})
        self.assertEqual(a, b)
        self.assertEqual(a.content_sha256() if hasattr(a, "content_sha256") else a.to_dict(),
                         b.content_sha256() if hasattr(b, "content_sha256") else b.to_dict())

    def test_interfaz_de_lectura_de_mapping(self):
        lv = self.req.levels
        self.assertEqual(len(lv), 3)
        self.assertIn("low", lv)
        self.assertNotIn("critical", lv)
        self.assertEqual(list(lv.keys()), ["low", "medium", "high"])
        self.assertEqual(lv.get("inexistente"), None)
        with self.assertRaises(KeyError):
            lv["inexistente"]
        self.assertIsInstance(lv["low"], govpolicy.LevelSpec)

    def test_to_dict_devuelve_dicts_mutables_independientes(self):
        for objeto in (self.req, self.ovr, govpolicy.BASE_POLICY):
            with self.subTest(tipo=type(objeto).__name__):
                d1 = objeto.to_dict()
                d2 = objeto.to_dict()
                self.assertEqual(d1, d2)
                self.assertIsNot(d1, d2)
        d = self.req.to_dict()
        self.assertIs(type(d["levels"]), dict)
        antes = self.req.to_dict()
        d["levels"]["low"]["severity"] = "required"
        d["levels"]["low"]["accepts"].append("basura")
        d["levels"]["extra"] = {}
        del d["levels"]["high"]
        d["description"] = "mutada"
        self.assertEqual(self.req.to_dict(), antes)
        self.assertEqual(self.req.levels["low"].severity, "recommended")
        self.assertEqual(self.req.levels["low"].accepts, ("observed", "attestation"))
        self.assertEqual(tuple(self.req.levels), govpolicy.LEVELS)
        # Mutar el to_dict de la policy base no afecta su hash.
        db = govpolicy.BASE_POLICY.to_dict()
        db["requirements"][0]["levels"]["low"]["severity"] = "recommended"
        db["requirements"].pop()
        self.assertEqual(govpolicy.BASE_POLICY.content_sha256(), BASE_SHA256_CONGELADO)
        # LevelSpec.to_dict también es independiente.
        s = ls()
        ds = s.to_dict()
        ds["accepts"].append("x")
        self.assertEqual(s.accepts, ("observed", "attestation"))

    def test_from_dict_to_dict_round_trip_con_levels_inmutables(self):
        rt = govpolicy.PolicyRequirement.from_dict(self.req.to_dict())
        self.assertEqual(rt, self.req)
        with self.assertRaises(TypeError):
            rt.levels["low"] = ls()
        rt_o = govpolicy.RequirementOverride.from_dict(self.ovr.to_dict())
        self.assertEqual(rt_o, self.ovr)
        with self.assertRaises(TypeError):
            rt_o.levels["high"] = ls()


class TestParidadVocabulario(unittest.TestCase):
    def test_levels_igual_a_risk_levels_de_dsguard(self):
        from tools.dsguard import maturity

        self.assertEqual(tuple(govpolicy.LEVELS), tuple(maturity.RISK_LEVELS))


if __name__ == "__main__":
    unittest.main()
