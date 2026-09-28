"""Tests de `tools/autonomy/core.py` (v0.8 Change 0, `20260928-project-autonomy-contract`).

Cobertura de `spec.md` R1 (parte core), R2-R7, R9, R11 (tipos), R16-R19.
Sin I/O, sin red, sin aleatoriedad. `json` se importa solo aqui (el core no lo usa).
"""
from __future__ import annotations

import dataclasses
import json
import re
import unittest
from unittest import mock

from tools.autonomy import core

HASH = "a" * 64
CHANGE_ID = "20260928-project-autonomy-contract"

# Tabla esperada de spec R3: clase -> (autonomous, supervised) con (executor, approval, outcome, stop_nn)
_ESPERADA = {
    "diagnostic_read": (("lead", "none", "proceed", None), ("lead", "none", "proceed", None)),
    "execute_project_code": (("lead", "none", "proceed", None), ("lead_or_human", "human", "proceed", None)),
    "approve_run_manifest": (("lead", "policy", "proceed", None), ("human", "human", "proceed", None)),
    "approve_proposal": (("human", "human", "proceed", None), ("human", "human", "proceed", None)),
    "continue_preapproved_decision": (("lead", "policy", "proceed", None), ("lead", "human", "proceed", None)),
    "decide_unlisted_methodological": (("human", "human", "stop_human", 2), ("human", "human", "stop_human", 2)),
    "sdd_transition_post_approval": (("lead", "none", "proceed", None), ("lead", "human_conditional", "proceed", None)),
    "corrective_reinvocation_in_window": (("lead", "none", "proceed", None), ("lead", "none", "proceed", None)),
    "remediation_extend": (("human", "human", "stop_human", 8), ("human", "human", "stop_human", 8)),
    "session_open_close": (("lead", "policy", "proceed", None), ("lead", "human_conditional", "proceed", None)),
    "access_sealed": (("human", "human", "stop_human", 1), ("human", "human", "stop_human", 1)),
    "provide_secret": (("human", "human", "stop_human", 6), ("human", "human", "stop_human", 6)),
    "install_dependency": (("human", "human", "stop_human", 4), ("human", "human", "stop_human", 4)),
    "write_outside_scope_or_source_or_raw": (("human", "human", "stop_human", 5), ("human", "human", "stop_human", 5)),
    "commit_tag_publish": (("human", "human", "proceed", None), ("human", "human", "proceed", None)),
}


def _ref_dict(**overrides) -> dict:
    base = {"change_id": CHANGE_ID, "artefacto": "proposal.md", "hash": HASH}
    base.update(overrides)
    return base


def _pa_dict(**overrides) -> dict:
    base = {
        "approved_by": "policy:autonomous",
        "action_class": "approve_run_manifest",
        "human_approval_ref": _ref_dict(),
    }
    base.update(overrides)
    return base


def _pre_dict(**overrides) -> dict:
    base = {
        "decision_type": "tipo_a",
        "summary": "resumen",
        "scope": ["docs/x.md", "src/*.py"],
        "approval_ref": _ref_dict(),
    }
    base.update(overrides)
    return base


def _bytes(d: dict) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class TestVocabularioYTabla(unittest.TestCase):
    def test_constantes(self):
        self.assertEqual(core.MODES, ("autonomous", "supervised"))
        self.assertEqual(core.DEFAULT_MODE, "supervised")
        self.assertEqual(core.EXECUTORS, ("lead", "human", "lead_or_human"))
        self.assertEqual(core.APPROVALS, ("none", "policy", "human", "human_conditional"))
        self.assertEqual(core.OUTCOMES, ("proceed", "stop_human"))

    def test_policy_decision_frozen(self):
        d = core.resolve_action("diagnostic_read", "supervised")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            d.mode = "autonomous"  # type: ignore[misc]

    def test_tabla_una_asercion_por_fila_y_modo(self):
        self.assertEqual(len(_ESPERADA), 15)
        for clase, (auto, sup) in _ESPERADA.items():
            for modo, esperado in (("autonomous", auto), ("supervised", sup)):
                with self.subTest(clase=clase, modo=modo):
                    d = core.resolve_action(clase, modo)
                    ejecutor, aprobacion, resultado, stop_n = esperado
                    stop = None if stop_n is None else "AUTONOMY-STOP-%02d" % stop_n
                    self.assertEqual(
                        d,
                        core.PolicyDecision(clase, modo, ejecutor, aprobacion, resultado, stop),
                    )

    def test_exhaustividad(self):
        esperadas = {(c, m) for c in core.ACTION_CLASSES for m in core.MODES}
        self.assertEqual(set(core.POLICY_TABLE), esperadas)
        self.assertEqual(len(core.ACTION_CLASSES), 15)
        self.assertEqual(set(core.ACTION_CLASSES), set(_ESPERADA))

    def test_stop_code_solo_en_filas_stop_human(self):
        for (clase, modo), d in core.POLICY_TABLE.items():
            with self.subTest(clase=clase, modo=modo):
                if d.outcome == "stop_human":
                    self.assertIsNotNone(d.stop_code)
                    self.assertEqual(d.approval, "human")
                else:
                    self.assertIsNone(d.stop_code)

    def test_stop_igual_en_ambos_modos(self):
        for clase in core.ACTION_CLASSES:
            a = core.resolve_action(clase, "autonomous")
            s = core.resolve_action(clase, "supervised")
            if a.outcome == "stop_human" or s.outcome == "stop_human":
                with self.subTest(clase=clase):
                    self.assertEqual(a.outcome, "stop_human")
                    self.assertEqual(s.outcome, "stop_human")
                    self.assertEqual(a.stop_code, s.stop_code)

    def test_approve_proposal_human_en_ambos_modos(self):
        for modo in core.MODES:
            d = core.resolve_action("approve_proposal", modo)
            self.assertEqual((d.executor, d.approval), ("human", "human"))

    def test_desconocidos_lanzan_autonomy_error(self):
        with self.assertRaises(core.AutonomyError) as c1:
            core.resolve_action("no_existe", "supervised")
        self.assertEqual(c1.exception.code, core.CODE_UNKNOWN_ACTION_CLASS)
        with self.assertRaises(core.AutonomyError) as c2:
            core.resolve_action("diagnostic_read", "otro")
        self.assertEqual(c2.exception.code, core.CODE_UNKNOWN_MODE)
        with self.assertRaises(core.AutonomyError) as c3:
            core.resolve_action(None, "supervised")  # type: ignore[arg-type]
        self.assertEqual(c3.exception.code, core.CODE_UNKNOWN_ACTION_CLASS)
        self.assertTrue(issubclass(core.AutonomyError, ValueError))
        with self.assertRaises(core.AutonomyError) as c4:
            core.role_capabilities("nadie")
        self.assertEqual(c4.exception.code, core.CODE_UNKNOWN_ROLE)


class TestCatalogos(unittest.TestCase):
    def test_doce_stop(self):
        self.assertEqual(len(core.STOP_CATALOG), 12)
        self.assertEqual([e.number for e in core.STOP_CATALOG], list(range(1, 13)))
        for e in core.STOP_CATALOG:
            self.assertEqual(e.code, "AUTONOMY-STOP-%02d" % e.number)
        claves = [e.key for e in core.STOP_CATALOG]
        self.assertEqual(
            claves,
            ["sealed_access", "unlisted_methodological_decision", "leakage_doubt",
             "new_dependency", "write_outside_scope", "secret_required", "data_loss_risk",
             "remediation_exhausted", "approach_refuted", "requirement_contradiction",
             "scope_expansion", "bypass_needed"],
        )
        self.assertEqual(len(set(claves)), 12)

    def test_limit(self):
        self.assertEqual(
            [(e.code, e.key, e.result) for e in core.LIMIT_CATALOG],
            [("AUTONOMY-LIMIT-SESSION-BUDGET", "session_budget", "checkpoint_resumable"),
             ("AUTONOMY-LIMIT-AGGREGATE-BUDGET", "aggregate_budget", "checkpoint_resumable")],
        )

    def test_limit_disjunto_de_stop(self):
        self.assertFalse({e.code for e in core.LIMIT_CATALOG} & {e.code for e in core.STOP_CATALOG})
        self.assertFalse({e.key for e in core.LIMIT_CATALOG} & {e.key for e in core.STOP_CATALOG})

    def test_ningun_approval_derivado_de_limit(self):
        origenes = {e.code for e in core.LIMIT_CATALOG} | {e.key for e in core.LIMIT_CATALOG}
        for d in core.POLICY_TABLE.values():
            self.assertNotIn(d.approval, origenes)
            self.assertNotIn(d.executor, origenes)
            self.assertNotIn(d.stop_code, origenes)

    def test_all_codes(self):
        self.assertEqual(len(core.ALL_CODES), len(set(core.ALL_CODES)))
        for c in core.ALL_CODES:
            self.assertRegex(c, r"^AUTONOMY-[A-Z0-9-]+$")
        self.assertEqual(core.TECHNICAL_ERROR_CODE, "AUTONOMY-TECHNICAL-ERROR")
        for c in (
            "AUTONOMY-POLICY-UNSUPPORTED", "AUTONOMY-POLICY-INVALID", "AUTONOMY-POLICY-VERSION",
            "AUTONOMY-POLICY-LIMITS", "AUTONOMY-POLICY-UNKNOWN-KEY",
            "AUTONOMY-SEALED-UNSEALED-HOLDOUT", "AUTONOMY-SEALED-PATH-MISMATCH",
            "AUTONOMY-APPROVAL-REF-INVALID", "AUTONOMY-APPROVAL-INVALID",
            "AUTONOMY-IDENTITY-INVALID", "AUTONOMY-IDENTITY-RESERVED",
        ):
            self.assertIn(c, core.ALL_CODES)

    def test_todo_codigo_usado_esta_registrado(self):
        # Todo codigo de hallazgo/tabla producido en estos tests pertenece al registro.
        for d in core.POLICY_TABLE.values():
            if d.stop_code:
                self.assertIn(d.stop_code, core.ALL_CODES)
        publicos = [v for k, v in vars(core).items() if k.startswith("CODE_")]
        for v in publicos:
            self.assertIn(v, core.ALL_CODES)

    def test_stop_de_cada_fila_existe(self):
        codigos = {e.code for e in core.STOP_CATALOG}
        for d in core.POLICY_TABLE.values():
            if d.stop_code:
                self.assertIn(d.stop_code, codigos)

    def test_constantes_str_sin_prosa(self):
        vistos = 0
        for nombre, valor in vars(core).items():
            if nombre.startswith("_") or not isinstance(valor, str):
                continue
            if nombre == "SOURCE_ID_PATTERN":
                continue  # es una regex documentada, no un codigo/clave
            vistos += 1
            with self.subTest(nombre=nombre):
                self.assertRegex(valor, r"^[A-Za-z0-9_.:-]+$")
        self.assertGreater(vistos, 5)

    def test_sin_constante_rol_modo_extra(self):
        roles, modos = set(core.ROLES), set(core.MODES)
        fuentes = {"ROLE_CAPABILITIES", "POLICY_TABLE"}
        for nombre, valor in vars(core).items():
            if nombre.startswith("_") or nombre in fuentes or not isinstance(valor, dict):
                continue
            with self.subTest(nombre=nombre):
                claves = list(valor)
                self.assertFalse(claves and all(k in roles for k in claves))
                self.assertFalse(claves and all(k in modos for k in claves))
                for k in claves:
                    if isinstance(k, tuple):
                        # clave-tupla que mezcle rol y modo, en cualquier orden
                        self.assertFalse(set(k) & roles and set(k) & modos)
                for v in valor.values():
                    if isinstance(v, dict) and v:
                        self.assertFalse(all(k in roles for k in v))
                        self.assertFalse(all(k in modos for k in v))
        # las dos fuentes no son mapas rol x modo
        for k in core.POLICY_TABLE:
            self.assertFalse(set(k) & roles)
        self.assertFalse(set(core.ROLE_CAPABILITIES) & modos)
        for caps in core.ROLE_CAPABILITIES.values():
            self.assertFalse(set(caps) & modos)


class TestNarrowMode(unittest.TestCase):
    def test_cuatro_pares(self):
        self.assertEqual(core.narrow_mode("autonomous", "autonomous"), "autonomous")
        self.assertEqual(core.narrow_mode("autonomous", "supervised"), "supervised")
        self.assertEqual(core.narrow_mode("supervised", "autonomous"), "supervised")
        self.assertEqual(core.narrow_mode("supervised", "supervised"), "supervised")

    def test_nunca_amplia(self):
        rango = {"supervised": 0, "autonomous": 1}
        for a in core.MODES:
            for b in core.MODES:
                r = core.narrow_mode(a, b)
                self.assertLessEqual(rango[r], rango[a])
                self.assertLessEqual(rango[r], rango[b])

    def test_desconocido_es_supervised(self):
        for raro in ("otro", None, 3, "", "AUTONOMOUS"):
            self.assertEqual(core.narrow_mode("autonomous", raro), "supervised")
            self.assertEqual(core.narrow_mode(raro, "autonomous"), "supervised")
            self.assertEqual(core.narrow_mode(raro, raro), "supervised")


class TestRoles(unittest.TestCase):
    def test_roles(self):
        self.assertEqual(core.ROLES, ("lead", "writer", "reviewer", "metodologo", "runner", "human"))
        self.assertEqual(set(core.ROLE_CAPABILITIES), set(core.ROLES))

    def test_invariantes(self):
        for rol in core.ROLES:
            caps = core.role_capabilities(rol)
            self.assertEqual(set(caps), {"write_files", "execute", "read_only"})
            self.assertEqual(caps["write_files"], rol == "writer")
        self.assertIs(core.role_capabilities("writer")["execute"], False)
        self.assertIs(core.role_capabilities("reviewer")["read_only"], True)
        self.assertIs(core.role_capabilities("metodologo")["read_only"], True)
        self.assertIs(core.role_capabilities("lead")["write_files"], False)

    def test_role_capabilities_devuelve_copia(self):
        caps = core.role_capabilities("lead")
        caps["write_files"] = True
        self.assertIs(core.role_capabilities("lead")["write_files"], False)

    def test_rol_desconocido(self):
        with self.assertRaises(core.AutonomyError) as c:
            core.role_capabilities("intruso")
        self.assertEqual(c.exception.code, "AUTONOMY-UNKNOWN-ROLE")


class TestRoleResponsibilities(unittest.TestCase):
    def test_exhaustivo_rol_modo_clase(self):
        for rol in core.ROLES:
            for modo in core.MODES:
                vista = core.role_responsibilities(rol, modo)
                self.assertEqual(vista["capabilities"], core.role_capabilities(rol))
                if rol not in ("lead", "human"):
                    self.assertEqual(vista["actions"], {})
                    continue
                self.assertEqual(list(vista["actions"]), list(core.ACTION_CLASSES))
                for clase, impl in vista["actions"].items():
                    d = core.resolve_action(clase, modo)
                    with self.subTest(rol=rol, modo=modo, clase=clase):
                        self.assertEqual(list(impl), [i for i in core.IMPLICATIONS if i in impl])
                        ejecuta = d.executor in (rol, "lead_or_human")
                        self.assertEqual("executes" in impl, ejecuta)
                        self.assertEqual(
                            "approves" in impl,
                            rol == "human" and d.approval in ("human", "human_conditional"),
                        )
                        self.assertEqual(
                            "registers_policy" in impl, rol == "lead" and d.approval == "policy"
                        )
                        self.assertEqual(
                            "stops" in impl, rol == "human" and d.outcome == "stop_human"
                        )

    def test_solo_lead_y_human_ejecutan_y_stops_solo_human(self):
        for rol in core.ROLES:
            for modo in core.MODES:
                vista = core.role_responsibilities(rol, modo)
                if rol not in ("lead", "human"):
                    self.assertIs(vista["capabilities"]["write_files"], rol == "writer")
                    self.assertNotIn("executes", vista["actions"])
                if rol == "writer":
                    self.assertIs(vista["capabilities"]["execute"], False)
                if rol != "human":
                    for impl in vista["actions"].values():
                        self.assertNotIn("stops", impl)

    def test_ejemplos_concretos(self):
        a = core.role_responsibilities("lead", "autonomous")["actions"]
        self.assertEqual(a["approve_run_manifest"], ("executes", "registers_policy"))
        h = core.role_responsibilities("human", "supervised")["actions"]
        self.assertEqual(h["execute_project_code"], ("executes", "approves"))
        self.assertEqual(h["access_sealed"], ("executes", "approves", "stops"))
        self.assertEqual(h["diagnostic_read"], ())

    def test_desconocidos(self):
        with self.assertRaises(core.AutonomyError):
            core.role_responsibilities("x", "supervised")
        with self.assertRaises(core.AutonomyError):
            core.role_responsibilities("lead", "x")

    def test_lee_las_dos_fuentes_en_cada_llamada(self):
        tabla = dict(core.POLICY_TABLE)
        tabla[("diagnostic_read", "supervised")] = core.PolicyDecision(
            "diagnostic_read", "supervised", "human", "policy", "proceed", None
        )
        caps = {k: dict(v) for k, v in core.ROLE_CAPABILITIES.items()}
        caps["reviewer"]["execute"] = True
        with mock.patch.object(core, "POLICY_TABLE", tabla), \
                mock.patch.object(core, "ROLE_CAPABILITIES", caps):
            self.assertEqual(
                core.role_responsibilities("human", "supervised")["actions"]["diagnostic_read"],
                ("executes",),
            )
            self.assertEqual(
                core.role_responsibilities("lead", "supervised")["actions"]["diagnostic_read"],
                ("registers_policy",),
            )
            self.assertIs(
                core.role_responsibilities("reviewer", "supervised")["capabilities"]["execute"], True
            )
        self.assertEqual(
            core.role_responsibilities("lead", "supervised")["actions"]["diagnostic_read"],
            ("executes",),
        )
        self.assertIs(core.role_capabilities("reviewer")["execute"], False)

    def test_patch_dict_sobre_tabla(self):
        fila = core.PolicyDecision("diagnostic_read", "autonomous", "human", "none", "proceed", None)
        with mock.patch.dict(core.POLICY_TABLE, {("diagnostic_read", "autonomous"): fila}):
            self.assertEqual(
                core.role_responsibilities("human", "autonomous")["actions"]["diagnostic_read"],
                ("executes",),
            )


class TestApprovalRef(unittest.TestCase):
    def test_valida(self):
        self.assertEqual(core.validate_approval_ref(_ref_dict()), [])
        ref = core.ApprovalRef.from_dict(_ref_dict())
        self.assertEqual(ref.change_id, CHANGE_ID)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ref.hash = "x"  # type: ignore[misc]

    def test_invalidas(self):
        casos = {
            "hash_corto": _ref_dict(hash="a" * 63),
            "hash_mayusculas": _ref_dict(hash="A" * 64),
            "hash_no_str": _ref_dict(hash=123),
            "artefacto_dotdot": _ref_dict(artefacto="../x.md"),
            "artefacto_slash": _ref_dict(artefacto="a/b.md"),
            "artefacto_backslash": _ref_dict(artefacto="a\\b.md"),
            "artefacto_vacio": _ref_dict(artefacto=""),
            "artefacto_solo_espacios": _ref_dict(artefacto="   "),
            "artefacto_espacio_lateral": _ref_dict(artefacto="proposal.md "),
            "artefacto_espacio_inicial": _ref_dict(artefacto=" proposal.md"),
            "artefacto_punto": _ref_dict(artefacto="."),
            "change_id_invalido": _ref_dict(change_id="mi-change"),
            "change_id_mayus": _ref_dict(change_id="20260928-Foo"),
            "change_id_no_str": _ref_dict(change_id=None),
        }
        for nombre, data in casos.items():
            with self.subTest(caso=nombre):
                hall = core.validate_approval_ref(data)
                self.assertTrue(hall)
                for f in hall:
                    self.assertEqual(f.code, "AUTONOMY-APPROVAL-REF-INVALID")
                with self.assertRaises(core.AutonomyError) as c:
                    core.ApprovalRef.from_dict(data)
                self.assertEqual(c.exception.code, "AUTONOMY-APPROVAL-REF-INVALID")

    def test_incompleta_y_no_dict_no_lanzan(self):
        self.assertTrue(core.validate_approval_ref({"change_id": CHANGE_ID}))
        for raro in (None, [], "x", 3):
            self.assertTrue(core.validate_approval_ref(raro))
            with self.assertRaises(core.AutonomyError):
                core.ApprovalRef.from_dict(raro)

    def test_roundtrip_bytes(self):
        ref = core.ApprovalRef.from_dict(_ref_dict())
        s1 = _bytes(ref.to_dict())
        ref2 = core.ApprovalRef.from_dict(json.loads(s1))
        self.assertEqual(ref, ref2)
        self.assertEqual(_bytes(ref2.to_dict()), s1)
        self.assertEqual(list(ref.to_dict()), sorted(ref.to_dict()))

    def test_mismo_tipo_en_todos_lados(self):
        pa = core.PolicyApproval.from_dict(_pa_dict())
        pre = core.PreApprovedDecision.from_dict(_pre_dict())
        self.assertIsInstance(pa.human_approval_ref, core.ApprovalRef)
        self.assertIsInstance(pre.approval_ref, core.ApprovalRef)
        campos_pa = {f.name: f.type for f in dataclasses.fields(core.PolicyApproval)}
        campos_pre = {f.name: f.type for f in dataclasses.fields(core.PreApprovedDecision)}
        self.assertEqual(campos_pa["human_approval_ref"], "ApprovalRef")
        self.assertEqual(campos_pre["approval_ref"], "ApprovalRef")


class TestPolicyApproval(unittest.TestCase):
    def test_valida_y_roundtrip(self):
        self.assertEqual(core.validate_policy_approval(_pa_dict()), [])
        pa = core.PolicyApproval.from_dict(_pa_dict())
        self.assertEqual(pa.approved_by, "policy:autonomous")
        s1 = _bytes(pa.to_dict())
        pa2 = core.PolicyApproval.from_dict(json.loads(s1))
        self.assertEqual(pa, pa2)
        self.assertEqual(_bytes(pa2.to_dict()), s1)
        self.assertNotIn("usuario", pa.to_dict())
        self.assertEqual(list(pa.to_dict()), sorted(pa.to_dict()))

    def test_invalidas(self):
        casos = {
            "sin_prefijo": _pa_dict(approved_by="autonomous"),
            "mayusculas": _pa_dict(approved_by="policy:Autonomous"),
            "espacios": _pa_dict(approved_by="policy:auto nomous"),
            "espacio_inicial": _pa_dict(approved_by=" policy:x"),
            "slug_vacio": _pa_dict(approved_by="policy:"),
            "no_str": _pa_dict(approved_by=None),
            "clase_desconocida": _pa_dict(action_class="nope"),
            "clase_no_str": _pa_dict(action_class=None),
            "usuario_presente": _pa_dict(usuario="Federico"),
            "hash_malo": _pa_dict(human_approval_ref=_ref_dict(hash="zz")),
            "ref_incompleta": _pa_dict(human_approval_ref={"change_id": CHANGE_ID}),
            "ref_no_dict": _pa_dict(human_approval_ref="x"),
        }
        for nombre, data in casos.items():
            with self.subTest(caso=nombre):
                self.assertTrue(core.validate_policy_approval(data))
                with self.assertRaises(core.AutonomyError):
                    core.PolicyApproval.from_dict(data)

    def test_faltantes(self):
        for clave in ("approved_by", "action_class", "human_approval_ref"):
            data = _pa_dict()
            del data[clave]
            with self.subTest(clave=clave):
                self.assertTrue(core.validate_policy_approval(data))

    def test_entrada_humana_no_valida_como_policy(self):
        humana = {"usuario": "Federico", "action_class": "approve_run_manifest",
                  "human_approval_ref": _ref_dict()}
        self.assertTrue(core.validate_policy_approval(humana))
        for raro in (None, [], "x"):
            self.assertTrue(core.validate_policy_approval(raro))

    def test_clases_permitidas_calculadas_desde_tabla(self):
        esperadas = {
            c for c in core.ACTION_CLASSES
            if any(core.POLICY_TABLE[(c, m)].approval == "policy" for m in core.MODES)
        }
        self.assertEqual(set(core.policy_approval_classes()), esperadas)
        self.assertEqual(
            set(esperadas),
            {"approve_run_manifest", "continue_preapproved_decision", "session_open_close"},
        )
        for clase in core.ACTION_CLASSES:
            with self.subTest(clase=clase):
                hall = core.validate_policy_approval(_pa_dict(action_class=clase))
                self.assertEqual(hall == [], clase in esperadas)

    def test_approve_proposal_y_stop_invalidas(self):
        self.assertTrue(core.validate_policy_approval(_pa_dict(action_class="approve_proposal")))
        for clase in core.ACTION_CLASSES:
            if core.resolve_action(clase, "supervised").outcome == "stop_human":
                self.assertTrue(core.validate_policy_approval(_pa_dict(action_class=clase)))

    def test_clases_permitidas_siguen_la_tabla(self):
        fila = core.PolicyDecision("diagnostic_read", "autonomous", "lead", "policy", "proceed", None)
        with mock.patch.dict(core.POLICY_TABLE, {("diagnostic_read", "autonomous"): fila}):
            self.assertIn("diagnostic_read", core.policy_approval_classes())
            self.assertEqual(
                core.validate_policy_approval(_pa_dict(action_class="diagnostic_read")), []
            )

    def test_is_policy_actor(self):
        self.assertTrue(core.is_policy_actor("policy:autonomous"))
        self.assertFalse(core.is_policy_actor("Federico"))
        self.assertFalse(core.is_policy_actor("policy:Bad"))
        self.assertFalse(core.is_policy_actor(None))


class TestNamespaceReservado(unittest.TestCase):
    def test_reservados(self):
        for v in ("policy:autonomous", " Policy:x", "POLICY:x", "policy\uff1ax", "\tpolicy:x"):
            with self.subTest(valor=v):
                self.assertTrue(core.is_reserved_policy_namespace(v))
                hall = core.validate_human_identity(v)
                self.assertEqual([f.code for f in hall], ["AUTONOMY-IDENTITY-RESERVED"])

    def test_aceptados(self):
        for v in ("policyx", "mypolicy:x", "Federico"):
            with self.subTest(valor=v):
                self.assertFalse(core.is_reserved_policy_namespace(v))
                self.assertEqual(core.validate_human_identity(v), [])

    def test_caracteres_invisibles(self):
        for v in ("​policy:x", "poli­cy:x", "policy​:x", "⁠policy:x",
                  "﻿policy:x"):
            with self.subTest(valor=v):
                self.assertTrue(core.is_reserved_policy_namespace(v))
                hall = core.validate_human_identity(v)
                self.assertEqual([f.code for f in hall], ["AUTONOMY-IDENTITY-RESERVED"])

    def test_identidad_no_imprimible(self):
        for v in ("​", "\t", "​\t ", "Fede​rico", "Fede\trico"):
            with self.subTest(valor=v):
                hall = core.validate_human_identity(v)
                self.assertEqual([f.code for f in hall], ["AUTONOMY-IDENTITY-INVALID"])

    def test_no_str_y_vacio(self):
        for v in (None, 3, [], b"policy:x"):
            self.assertFalse(core.is_reserved_policy_namespace(v))
        for v in (None, "", "   ", 3):
            hall = core.validate_human_identity(v)
            self.assertEqual([f.code for f in hall], ["AUTONOMY-IDENTITY-INVALID"])

    def test_entrada_humana(self):
        self.assertEqual(core.validate_human_approval_entry({"usuario": "Federico"}), [])
        hall = core.validate_human_approval_entry({"usuario": "Federico", "approved_by": "policy:x"})
        self.assertEqual([f.code for f in hall], ["AUTONOMY-APPROVAL-INVALID"])
        hall = core.validate_human_approval_entry({"usuario": "policy:x"})
        self.assertEqual([f.code for f in hall], ["AUTONOMY-IDENTITY-RESERVED"])
        self.assertTrue(core.validate_human_approval_entry({}))
        self.assertTrue(core.validate_human_approval_entry(None))

    def test_policy_approval_con_usuario_es_hallazgo(self):
        self.assertTrue(core.validate_policy_approval(_pa_dict(usuario="Federico")))


class TestPreApprovedDecision(unittest.TestCase):
    TIPOS = ("tipo_a", "tipo_b")

    def test_valida_e_instancia(self):
        self.assertEqual(core.validate_pre_approved(_pre_dict(), self.TIPOS), [])
        pre = core.PreApprovedDecision.from_dict(_pre_dict())
        self.assertEqual(pre.scope, ("docs/x.md", "src/*.py"))
        self.assertEqual(core.validate_pre_approved(pre, self.TIPOS), [])
        s1 = _bytes(pre.to_dict())
        self.assertEqual(_bytes(core.PreApprovedDecision.from_dict(json.loads(s1)).to_dict()), s1)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            pre.summary = "x"  # type: ignore[misc]

    def test_sin_ref(self):
        data = _pre_dict()
        del data["approval_ref"]
        hall = core.validate_pre_approved(data, self.TIPOS)
        self.assertEqual([f.code for f in hall], ["AUTONOMY-APPROVAL-REF-INVALID"])
        self.assertTrue(core.validate_pre_approved(_pre_dict(approval_ref=None), self.TIPOS))

    def test_ref_a_otro_artefacto(self):
        data = _pre_dict(approval_ref=_ref_dict(artefacto="design.md"))
        hall = core.validate_pre_approved(data, self.TIPOS)
        self.assertEqual([(f.path, f.detail_key) for f in hall],
                         [("approval_ref.artefacto", "not_proposal")])

    def test_hash_invalido(self):
        data = _pre_dict(approval_ref=_ref_dict(hash="xyz"))
        self.assertTrue(core.validate_pre_approved(data, self.TIPOS))

    def test_scope_invalido(self):
        for scope in (["/abs/x"], ["\\abs"], ["../x"], ["a/../x"], ["C:/x"], ["C:x"],
                      [""], [], "docs/x", None, [3], [" /etc"], ["a "], [" a"],
                      ["a\\b"], ["."], ["ok/x", "."]):
            with self.subTest(scope=scope):
                self.assertTrue(
                    core.validate_pre_approved(_pre_dict(scope=scope), self.TIPOS)
                )

    def test_tipo_desconocido_y_vacios(self):
        self.assertTrue(core.validate_pre_approved(_pre_dict(decision_type="otro"), self.TIPOS))
        self.assertEqual(
            core.validate_pre_approved(_pre_dict(decision_type="otro"), None), []
        )
        self.assertTrue(core.validate_pre_approved(_pre_dict(decision_type=""), self.TIPOS))
        self.assertTrue(core.validate_pre_approved(_pre_dict(summary=""), self.TIPOS))
        for raro in (None, [], "x"):
            self.assertTrue(core.validate_pre_approved(raro, self.TIPOS))

    def test_from_dict_invalido_lanza(self):
        with self.assertRaises(core.AutonomyError):
            core.PreApprovedDecision.from_dict(_pre_dict(scope=[]))

    def test_no_existe_approval_ref_required(self):
        self.assertFalse(hasattr(core, "approval_ref_required"))
        self.assertNotIn(
            "approval_ref_required",
            {f.name for f in dataclasses.fields(core.PreApprovedDecision)},
        )


class TestSourceId(unittest.TestCase):
    def test_validos(self):
        for v in ("customers", "model_features", "a", "a-b_c1", "a" * 64):
            with self.subTest(valor=v):
                self.assertTrue(core.is_valid_source_id(v))

    def test_invalidos(self):
        for v in ("", " a", "A", "a b", "-a", "_a", "a" * 65, "a\n", None, 1, b"a"):
            with self.subTest(valor=v):
                self.assertFalse(core.is_valid_source_id(v))

    def test_patron_publico(self):
        self.assertEqual(core.SOURCE_ID_PATTERN, r"[a-z0-9][a-z0-9_-]{0,63}")


class TestNeutralidadDeImports(unittest.TestCase):
    def test_core_solo_stdlib(self):
        import ast
        from pathlib import Path

        fuente = Path(core.__file__).read_text(encoding="utf-8")
        permitidos = {"__future__", "re", "unicodedata", "dataclasses", "typing"}
        for nodo in ast.walk(ast.parse(fuente)):
            if isinstance(nodo, ast.Import):
                for a in nodo.names:
                    self.assertIn(a.name.split(".")[0], permitidos)
            elif isinstance(nodo, ast.ImportFrom):
                self.assertEqual(nodo.level, 0)
                self.assertIn((nodo.module or "").split(".")[0], permitidos)


if __name__ == "__main__":
    unittest.main()
