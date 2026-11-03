"""Tests de `sdd.resolver_aprobacion_registrada`, checkpoints `@approved` y
`sdd.verificar_checkpoints` (R1, R5-R12 de
`20261006-sdd-parsers-and-guardrail-ownership`). Archivo nuevo."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from autonomy import core as autonomy_core  # noqa: E402
from dsguard import core, sdd  # noqa: E402

_CID = "20261006-sdd-parsers-and-guardrail-ownership"
_OTRO = "20261001-otro-change"
_CERO = "0" * 64


def _bullet(hash_texto, cid=_CID, id_="cp-1"):
    return (
        f"- **{id_}**: Aprobar el tope — alcance: tools/dsguard/sdd.py, tools/tests/test_x.py "
        f"— aprobacion: {cid}/proposal.md@{hash_texto}"
    )


def _seccion(*bullets):
    return "# Proposal\n\n## Checkpoints de negocio\n\n" + "\n".join(bullets) + "\n"


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def crear_change(self, cid, texto="contenido\n", aprobar=True, archivo=False):
        padre = "archive" if archivo else "changes"
        carpeta = self.root / "openspec" / padre / cid
        carpeta.mkdir(parents=True)
        (carpeta / "proposal.md").write_text(texto, encoding="utf-8")
        control = {"schema_version": core.SCHEMA_VERSION_SOPORTADA, "aprobaciones": []}
        h = core.hash_lf_v1(carpeta / "proposal.md")
        if aprobar:
            control["aprobaciones"].append(self.entrada("proposal.md", h, "2026-10-06T10:00:00Z"))
        (carpeta / "control.json").write_text(json.dumps(control), encoding="utf-8")
        return carpeta, h

    @staticmethod
    def entrada(art, h, ts):
        return {"artefacto": art, "hash": h, "algoritmo": "sha256/lf/v1", "registrado_utc": ts}

    def agregar(self, carpeta, entrada):
        p = carpeta / "control.json"
        c = json.loads(p.read_text(encoding="utf-8"))
        c["aprobaciones"].append(entrada)
        p.write_text(json.dumps(c), encoding="utf-8")


class TestPrimitiva(_Base):
    def test_verified(self):
        _, h = self.crear_change(_CID)
        r = sdd.resolver_aprobacion_registrada(self.root, _CID, "proposal.md", h)
        self.assertEqual(r["estado"], "verified")
        self.assertEqual(r["hash_vigente"], h)
        self.assertIsNotNone(r["entrada"])

    def test_verified_sin_hash_esperado(self):
        _, h = self.crear_change(_CID)
        r = sdd.resolver_aprobacion_registrada(self.root, _CID, "proposal.md")
        self.assertEqual((r["estado"], r["hash_vigente"]), ("verified", h))

    def test_archive(self):
        _, h = self.crear_change(_CID, archivo=True)
        self.assertEqual(sdd.resolver_aprobacion_registrada(self.root, _CID, "proposal.md", h)["estado"], "verified")

    def test_stale_por_reemplazo(self):
        carpeta, h = self.crear_change(_CID)
        self.agregar(carpeta, self.entrada("proposal.md", "a" * 64, "2026-10-06T11:00:00Z"))
        r = sdd.resolver_aprobacion_registrada(self.root, _CID, "proposal.md", h)
        self.assertEqual(r["estado"], "stale")
        self.assertIsNone(r["hash_vigente"])

    def test_stale_por_archivo_cambiado(self):
        carpeta, h = self.crear_change(_CID)
        (carpeta / "proposal.md").write_text("cambiado\n", encoding="utf-8")
        self.assertEqual(sdd.resolver_aprobacion_registrada(self.root, _CID, "proposal.md", h)["estado"], "stale")
        self.assertEqual(sdd.resolver_aprobacion_registrada(self.root, _CID, "proposal.md")["estado"], "stale")

    def test_missing(self):
        self.crear_change(_CID, aprobar=False)
        self.assertEqual(sdd.resolver_aprobacion_registrada(self.root, _CID, "proposal.md")["estado"], "missing")
        _, h = self.crear_change(_OTRO)
        self.assertEqual(
            sdd.resolver_aprobacion_registrada(self.root, _OTRO, "proposal.md", "b" * 64)["estado"], "missing"
        )

    def test_unresolvable_change_inexistente(self):
        r = sdd.resolver_aprobacion_registrada(self.root, _OTRO, "proposal.md", "b" * 64)
        self.assertEqual(r["estado"], "unresolvable")

    def test_unresolvable_formas(self):
        self.crear_change(_CID)
        for cid, art in [
            ("../x", "proposal.md"), ("BAD", "proposal.md"), (None, "proposal.md"),
            (_CID, "../proposal.md"), (_CID, "a/b.md"), (_CID, "a\\b.md"), (_CID, "c:proposal.md"),
            (_CID, "proposal.md:ads"), (_CID, "con"), (_CID, "NUL.md"), (_CID, "proposal.md."),
            (_CID, "proposal.md "), (_CID, ""), (_CID, None),
        ]:
            r = sdd.resolver_aprobacion_registrada(self.root, cid, art)
            self.assertEqual(r["estado"], "unresolvable", (cid, art))

    def test_control_ilegible(self):
        carpeta, _ = self.crear_change(_CID)
        (carpeta / "control.json").write_text("{no json", encoding="utf-8")
        self.assertEqual(sdd.resolver_aprobacion_registrada(self.root, _CID, "proposal.md")["estado"], "unresolvable")

    def test_entrada_con_hash_invalido(self):
        carpeta, _ = self.crear_change(_CID, aprobar=False)
        self.agregar(carpeta, self.entrada("proposal.md", "no-es-hex", "2026-10-06T10:00:00Z"))
        r = sdd.resolver_aprobacion_registrada(self.root, _CID, "proposal.md")
        self.assertEqual(r["estado"], "unresolvable")
        self.assertIsNone(r["hash_vigente"])

    def test_algoritmo_distinto(self):
        carpeta, h = self.crear_change(_CID, aprobar=False)
        e = self.entrada("proposal.md", h, "2026-10-06T10:00:00Z")
        e["algoritmo"] = "md5/raw/v0"
        self.agregar(carpeta, e)
        for esperado in (None, h):
            r = sdd.resolver_aprobacion_registrada(self.root, _CID, "proposal.md", esperado)
            self.assertEqual(r["estado"], "unresolvable")

    def test_symlink_que_escapa_del_change(self):
        carpeta, _ = self.crear_change(_CID, aprobar=False)
        fuera = self.root / "fuera.md"
        fuera.write_text("secreto\n", encoding="utf-8")
        (carpeta / "proposal.md").unlink()
        try:
            (carpeta / "proposal.md").symlink_to(fuera)
        except (OSError, NotImplementedError):
            self.skipTest("el SO no permite symlinks")
        h = core.hash_lf_v1(fuera)
        self.agregar(carpeta, self.entrada("proposal.md", h, "2026-10-06T10:00:00Z"))
        r = sdd.resolver_aprobacion_registrada(self.root, _CID, "proposal.md", h)
        self.assertEqual(r["estado"], "unresolvable")
        self.assertNotEqual(r["estado"], "verified")

    def test_hash_cero_nunca_verified(self):
        carpeta, _ = self.crear_change(_CID, aprobar=False)
        self.agregar(carpeta, self.entrada("proposal.md", _CERO, "2026-10-06T10:00:00Z"))
        for esperado in (None, _CERO):
            r = sdd.resolver_aprobacion_registrada(self.root, _CID, "proposal.md", esperado)
            self.assertNotEqual(r["estado"], "verified", esperado)
            self.assertIsNone(r["hash_vigente"])

    def test_hash_esperado_invalido(self):
        self.crear_change(_CID)
        self.assertEqual(
            sdd.resolver_aprobacion_registrada(self.root, _CID, "proposal.md", "xyz")["estado"], "unresolvable"
        )


class TestParseoCheckpoints(_Base):
    def test_approved_con_resolver(self):
        vistos = []

        def resolver(cid):
            vistos.append(cid)
            return "c" * 64, "ok"

        cps, hall = sdd.parsear_checkpoints_de_propuesta(
            _seccion(_bullet("approved")), change_id=_CID, resolver_approved=resolver
        )
        self.assertEqual(hall, [])
        self.assertEqual(vistos, [_CID])
        self.assertEqual(len(cps), 1)
        self.assertEqual(cps[0]["approval_ref"], {"artefacto": "proposal.md", "change_id": _CID, "hash": "c" * 64})
        self.assertEqual(cps[0]["decision_type"], "business_checkpoint")
        self.assertEqual(set(cps[0]), {"approval_ref", "decision_type", "scope", "summary"})

    def test_approved_sin_resolver_es_hallazgo(self):
        cps, hall = sdd.parsear_checkpoints_de_propuesta(_seccion(_bullet("approved")), change_id=_CID)
        self.assertEqual(cps, [])
        self.assertEqual([h.codigo for h in hall], [autonomy_core.CODE_PREAPPROVED_INVALID])

    def test_approved_resolver_sin_hash_o_con_error(self):
        for resolver in (lambda c: (None, "missing"), lambda c: (_CERO, "x"), lambda c: ("zz", "x"),
                         lambda c: 1 / 0):
            cps, hall = sdd.parsear_checkpoints_de_propuesta(
                _seccion(_bullet("approved")), change_id=_CID, resolver_approved=resolver
            )
            self.assertEqual(cps, [])
            self.assertEqual(len(hall), 1)
            self.assertEqual(hall[0].codigo, autonomy_core.CODE_PREAPPROVED_INVALID)

    def test_legacy_hash_real(self):
        cps, hall = sdd.parsear_checkpoints_de_propuesta(_seccion(_bullet("d" * 64)))
        self.assertEqual(hall, [])
        self.assertEqual(cps[0]["approval_ref"]["hash"], "d" * 64)

    def test_legacy_ceros_aceptado_sintacticamente(self):
        texto = _seccion(_bullet(_CERO, id_="viejo"), _bullet("approved", id_="nuevo"))
        cps, hall = sdd.parsear_checkpoints_de_propuesta(texto, resolver_approved=lambda c: ("e" * 64, "ok"))
        self.assertEqual(len(cps), 2)
        self.assertEqual(hall, [])
        self.assertEqual(sdd.checkpoints_con_placeholder_cero(texto), ["viejo"])
        self.assertEqual(sdd.checkpoints_con_placeholder_cero("sin seccion"), [])


class TestVerificarCheckpoints(_Base):
    @staticmethod
    def _control(cid, h, resumen="cp-1: Aprobar"):
        return {"decisiones_preaprobadas": [{
            "approval_ref": {"artefacto": "proposal.md", "change_id": cid, "hash": h},
            "decision_type": "business_checkpoint", "scope": ["a"], "summary": resumen,
        }]}

    def test_verified(self):
        _, h = self.crear_change(_CID)
        r = sdd.verificar_checkpoints(self.root, self._control(_CID, h))
        self.assertEqual([x["estado"] for x in r], ["verified"])
        self.assertEqual(r[0]["summary"], "cp-1: Aprobar")

    def test_verified_archivado(self):
        _, h = self.crear_change(_OTRO, archivo=True)
        self.assertEqual(sdd.verificar_checkpoints(self.root, self._control(_OTRO, h))[0]["estado"], "verified")

    def test_stale_proposal_cambiado(self):
        carpeta, h = self.crear_change(_CID)
        (carpeta / "proposal.md").write_text("otro texto\n", encoding="utf-8")
        self.assertEqual(sdd.verificar_checkpoints(self.root, self._control(_CID, h))[0]["estado"], "stale")

    def test_missing_otro_change_sin_aprobacion(self):
        self.crear_change(_OTRO, aprobar=False)
        self.assertEqual(sdd.verificar_checkpoints(self.root, self._control(_OTRO, "f" * 64))[0]["estado"], "missing")

    def test_placeholder(self):
        self.crear_change(_CID)
        self.assertEqual(sdd.verificar_checkpoints(self.root, self._control(_CID, _CERO))[0]["estado"], "placeholder")

    def test_unresolvable_change_inexistente(self):
        self.assertEqual(
            sdd.verificar_checkpoints(self.root, self._control(_OTRO, "f" * 64))[0]["estado"], "unresolvable"
        )

    def test_sin_decisiones(self):
        self.assertEqual(sdd.verificar_checkpoints(self.root, {}), [])
        self.assertEqual(sdd.verificar_checkpoints(self.root, {"decisiones_preaprobadas": "x"}), [])

    def test_hash_cero_registrado_en_control_nunca_verified(self):
        carpeta, _ = self.crear_change(_CID, aprobar=False)
        self.agregar(carpeta, self.entrada("proposal.md", _CERO, "2026-10-06T10:00:00Z"))
        r = sdd.verificar_checkpoints(self.root, self._control(_CID, _CERO))
        self.assertEqual([x["estado"] for x in r], ["placeholder"])

    def test_extremo_a_extremo_approved_materializado(self):
        carpeta, h = self.crear_change(_CID)

        def resolver_real(cid):  # resolver como el de la CLI: usa la primitiva, sin mocks
            r = sdd.resolver_aprobacion_registrada(self.root, cid, "proposal.md")
            return (r["hash_vigente"] if r["estado"] == "verified" else None), r["detalle"]

        cps, hall = sdd.parsear_checkpoints_de_propuesta(
            _seccion(_bullet("approved")), change_id=_CID, resolver_approved=resolver_real
        )
        self.assertEqual(cps[0]["approval_ref"]["hash"], h)
        self.assertEqual(hall, [])
        control = {"decisiones_preaprobadas": cps}
        self.assertEqual(sdd.verificar_checkpoints(self.root, control)[0]["estado"], "verified")
        (carpeta / "proposal.md").write_text("cambio posterior\n", encoding="utf-8")
        self.assertEqual(sdd.verificar_checkpoints(self.root, control)[0]["estado"], "stale")


if __name__ == "__main__":
    unittest.main()
