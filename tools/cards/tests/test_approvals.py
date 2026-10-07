"""Tests de `approvals.resolve_approval_ref` (Change 4, R35-R41)."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.cards import approvals

CID = "20261005-demo-change"
ART = "spec.md"


def hash_lf(texto: str) -> str:
    return hashlib.sha256(texto.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")).hexdigest()


class Mundo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name).resolve()
        self.texto = "# Spec\ncontenido\n"
        self.hash = hash_lf(self.texto)
        self.crear_change(padre="changes")

    def carpeta(self, padre="changes"):
        return self.raiz / "openspec" / padre / CID

    def crear_change(self, padre="changes", aprobaciones=None, texto=None):
        c = self.carpeta(padre)
        c.mkdir(parents=True, exist_ok=True)
        (c / ART).write_bytes((texto if texto is not None else self.texto).encode("utf-8"))
        if aprobaciones is None:
            aprobaciones = [self.entrada(self.hash, "2026-10-06T10:00:00Z")]
        self.escribir_control(padre, aprobaciones)

    def entrada(self, h, utc, artefacto=ART):
        return {"artefacto": artefacto, "algoritmo": "sha256/lf/v1", "hash": h, "registrado_utc": utc,
                "usuario": "Ana", "fecha_declarada": "2026-10-06"}

    def escribir_control(self, padre, aprobaciones):
        (self.carpeta(padre) / "control.json").write_text(
            json.dumps({"schema_version": 1, "change_id": CID, "aprobaciones": aprobaciones}), encoding="utf-8")

    def ref(self, **cambios):
        r = {"change_id": CID, "artefacto": ART, "hash": self.hash}
        r.update(cambios)
        return r

    def resolver(self, ref=None):
        return approvals.resolve_approval_ref(self.raiz, ref if ref is not None else self.ref())


class TestResolucion(Mundo):
    def test_verified_con_metadatos_informativos(self):
        r = self.resolver()
        self.assertEqual(r.state, "verified")
        self.assertEqual((r.change_id, r.artefacto, r.usuario, r.fecha_declarada), (CID, ART, "Ana", "2026-10-06"))

    def test_entrada_ausente_missing(self):
        self.assertEqual(self.resolver(self.ref(hash="a" * 64)).state, "missing")

    def test_artefacto_equivocado_missing(self):
        self.assertEqual(self.resolver(self.ref(artefacto="design.md")).state, "missing")

    def test_change_equivocado_unresolvable(self):
        self.assertEqual(self.resolver(self.ref(change_id="20261005-otro")).state, "unresolvable")

    def test_forma_invalida_unresolvable(self):
        for ref in ({"change_id": CID}, {**self.ref(), "extra": 1}, self.ref(hash="zz"), self.ref(artefacto="../x"), "no-dict", None):
            with self.subTest(ref=ref):
                self.assertEqual(approvals.resolve_approval_ref(self.raiz, ref).state, "unresolvable")

    def test_artefacto_no_portable_unresolvable(self):
        for art in ("C:foo", "spec.md:ads", "NUL", "con.md", "COM1.txt", "spec.md.", "spec.md "):
            with self.subTest(art=art):
                self.assertEqual(self.resolver(self.ref(artefacto=art)).state, "unresolvable")

    def test_reemplazada_stale(self):
        nuevo = hash_lf("# Spec\nversion 2\n")
        self.crear_change(aprobaciones=[
            self.entrada(self.hash, "2026-10-06T10:00:00Z"), self.entrada(nuevo, "2026-10-06T11:00:00Z")],
            texto="# Spec\nversion 2\n")
        self.assertEqual(self.resolver().state, "stale")  # ref al hash viejo
        self.assertEqual(self.resolver(self.ref(hash=nuevo)).state, "verified")

    def test_archivo_modificado_stale(self):
        (self.carpeta() / ART).write_text("# Spec\ncambiado\n", encoding="utf-8")
        self.assertEqual(self.resolver().state, "stale")

    def test_crlf_equivale_a_lf(self):
        (self.carpeta() / ART).write_bytes(self.texto.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(self.resolver().state, "verified")

    def test_artefacto_ausente_missing(self):
        (self.carpeta() / ART).unlink()
        self.assertEqual(self.resolver().state, "missing")

    def test_change_archivado(self):
        import shutil
        (self.raiz / "openspec" / "archive").mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.carpeta("changes")), str(self.carpeta("archive")))
        self.assertEqual(self.resolver().state, "verified")

    def test_control_ilegible_unresolvable(self):
        (self.carpeta() / "control.json").write_text("{{{", encoding="utf-8")
        self.assertEqual(self.resolver().state, "unresolvable")
        (self.carpeta() / "control.json").write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
        self.assertEqual(self.resolver().state, "unresolvable")
        (self.carpeta() / "control.json").unlink()
        self.assertEqual(self.resolver().state, "unresolvable")

    def test_solo_lectura(self):
        antes = {p: p.read_bytes() for p in self.raiz.rglob("*") if p.is_file()}
        self.resolver()
        self.resolver(self.ref(hash="a" * 64))
        despues = {p: p.read_bytes() for p in self.raiz.rglob("*") if p.is_file()}
        self.assertEqual(antes, despues)

    def test_nunca_lanza(self):
        self.assertEqual(approvals.resolve_approval_ref(object(), self.ref()).state, "unresolvable")

    def test_nota_anchor(self):
        self.assertIn("trust model", approvals.NOTA_ANCHOR)


if __name__ == "__main__":
    unittest.main()
