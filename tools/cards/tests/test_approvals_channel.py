"""Tests de canal/trust tier en `approvals` (Change 20261009, R31-R38)."""
from __future__ import annotations

import dataclasses
import types
import unittest

from tools.cards import approvals, core
from tools.cards.tests.test_approvals import ART, CID, Mundo, hash_lf


class Canal(Mundo):
    def con_canal(self, h, utc, **extra):
        e = self.entrada(h, utc)
        e.update(extra)
        return e

    def sembrar(self, **extra):
        self.crear_change(aprobaciones=[self.con_canal(self.hash, "2026-10-06T10:00:00Z", **extra)])


class TestTier(Canal):
    def test_sin_canal_t0_declared(self):
        r = self.resolver()
        self.assertEqual((r.state, r.approval_channel, r.trust_tier), ("verified", "declared", "T0"))

    def test_console_confirmed_t1(self):
        self.sembrar(approval_channel="console_confirmed", channel_version="console/v1")
        r = self.resolver()
        self.assertEqual((r.state, r.approval_channel, r.trust_tier), ("verified", "console_confirmed", "T1"))

    def test_desconocidos_o_malformados_t0(self):
        casos = [
            {"approval_channel": "tty_confirmed", "channel_version": "console/v1"},
            {"approval_channel": "CONSOLE_CONFIRMED", "channel_version": "console/v1"},
            {"approval_channel": 123, "channel_version": "console/v1"},
            {"approval_channel": ["console_confirmed"], "channel_version": "console/v1"},
            {"approval_channel": None, "channel_version": "console/v1"},
            {"approval_channel": "console_confirmed", "channel_version": "console/v2"},
            {"approval_channel": "console_confirmed", "channel_version": "CONSOLE/V1"},
            {"approval_channel": "console_confirmed", "channel_version": 1},
            {"approval_channel": "console_confirmed"},
            {"channel_version": "console/v1"},
        ]
        for extra in casos:
            with self.subTest(extra=extra):
                self.sembrar(**extra)
                r = self.resolver()
                self.assertEqual((r.state, r.approval_channel, r.trust_tier), ("verified", "declared", "T0"))

    def test_estados_sin_cambio_por_el_canal(self):
        for extra in ({}, {"approval_channel": "console_confirmed", "channel_version": "console/v1"}):
            with self.subTest(extra=extra):
                self.sembrar(**extra)
                self.assertEqual(self.resolver().state, "verified")
                self.assertEqual(self.resolver(self.ref(hash="a" * 64)).state, "missing")
                self.assertEqual(self.resolver(self.ref(change_id="20261005-otro")).state, "unresolvable")
                (self.carpeta() / ART).write_text("# cambiado\n", encoding="utf-8")
                self.assertEqual(self.resolver().state, "stale")
                (self.carpeta() / ART).write_text(self.texto, encoding="utf-8")

    def test_missing_y_unresolvable_sin_canal(self):
        self.sembrar(approval_channel="console_confirmed", channel_version="console/v1")
        for ref in (self.ref(hash="a" * 64), self.ref(change_id="20261005-otro"), {"change_id": CID}):
            with self.subTest(ref=ref):
                r = self.resolver(ref)
                self.assertIn(r.state, ("missing", "unresolvable"))
                self.assertIsNone(r.approval_channel)
                self.assertIsNone(r.trust_tier)
        (self.carpeta() / ART).unlink()  # entrada existe pero artefacto ausente -> missing
        r = self.resolver()
        self.assertEqual((r.state, r.approval_channel, r.trust_tier), ("missing", None, None))

    def test_usa_la_entrada_mas_reciente(self):
        nuevo = hash_lf("# Spec\nversion 2\n")
        self.crear_change(aprobaciones=[
            self.con_canal(self.hash, "2026-10-06T10:00:00Z",
                           approval_channel="console_confirmed", channel_version="console/v1"),
            self.con_canal(nuevo, "2026-10-06T11:00:00Z"),
        ], texto="# Spec\nversion 2\n")
        viejo = self.resolver()  # ref al hash viejo (T1) reemplazado por uno T0 posterior
        self.assertEqual(viejo.state, "stale")
        self.assertEqual((viejo.approval_channel, viejo.trust_tier), (None, None))
        vigente = self.resolver(self.ref(hash=nuevo))
        self.assertEqual((vigente.state, vigente.trust_tier), ("verified", "T0"))

    def test_t0_reemplazada_por_t1_posterior(self):
        nuevo = hash_lf("# Spec\nversion 2\n")
        self.crear_change(aprobaciones=[
            self.con_canal(self.hash, "2026-10-06T10:00:00Z"),
            self.con_canal(nuevo, "2026-10-06T11:00:00Z",
                           approval_channel="console_confirmed", channel_version="console/v1"),
        ], texto="# Spec\nversion 2\n")
        self.assertEqual(self.resolver(self.ref(hash=nuevo)).trust_tier, "T1")
        viejo = self.resolver()
        self.assertEqual((viejo.state, viejo.approval_channel, viejo.trust_tier), ("stale", None, None))

    def test_stale_por_archivo_cambiado_sin_canal(self):
        self.sembrar(approval_channel="console_confirmed", channel_version="console/v1")
        (self.carpeta() / ART).write_text("# cambiado\n", encoding="utf-8")
        r = self.resolver()
        self.assertEqual((r.state, r.approval_channel, r.trust_tier), ("stale", None, None))

    def test_ref_con_claves_de_tier_se_rechaza(self):
        self.sembrar()
        for extra in ({"trust_tier": "T1"}, {"approval_channel": "console_confirmed"}):
            with self.subTest(extra=extra):
                r = self.resolver(self.ref(**extra))
                self.assertEqual(r.state, "unresolvable")
                self.assertIsNone(r.trust_tier)

    def test_canal_de_aprobacion(self):
        self.sembrar(approval_channel="console_confirmed", channel_version="console/v1")
        self.assertEqual(approvals.canal_de_aprobacion(self.raiz, self.ref()),
                         ("verified", "console_confirmed", "T1"))
        self.assertEqual(approvals.canal_de_aprobacion(self.raiz, self.ref(hash="a" * 64)),
                         ("missing", None, None))
        self.assertEqual(approvals.canal_de_aprobacion(object(), self.ref())[0], "unresolvable")

    def test_solo_lectura(self):
        self.sembrar(approval_channel="console_confirmed", channel_version="console/v1")
        antes = {p: p.read_bytes() for p in self.raiz.rglob("*") if p.is_file()}
        self.resolver()
        approvals.canal_de_aprobacion(self.raiz, self.ref())
        self.assertEqual(antes, {p: p.read_bytes() for p in self.raiz.rglob("*") if p.is_file()})


class TestCompatibilidad(Canal):
    def test_campos_previos_en_orden_y_nuevos_al_final_con_default(self):
        campos = dataclasses.fields(approvals.AnchorResolution)
        self.assertEqual(
            [f.name for f in campos],
            ["state", "detail", "change_id", "artefacto", "usuario", "fecha_declarada",
             "approval_channel", "trust_tier"])
        for f in campos[-2:]:
            self.assertIsNone(f.default)
        # construcción posicional previa (6 argumentos) sigue válida
        r = approvals.AnchorResolution("verified", "d", "c", "a", "u", "f")
        self.assertEqual((r.approval_channel, r.trust_tier), (None, None))

    def test_human_attestation_sin_campos_de_tier(self):
        nombres = {f.name for f in dataclasses.fields(core.HumanAttestation)}
        self.assertFalse({"trust_tier", "approval_channel", "channel_version"} & nombres)

    def test_verificador_anchored_no_cambia_estado_por_canal(self):
        for extra in ({}, {"approval_channel": "console_confirmed", "channel_version": "console/v1"}):
            with self.subTest(extra=extra):
                self.sembrar(**extra)
                att = types.SimpleNamespace(attestation_kind="anchored", approval_ref=self.ref())
                r = approvals.make_anchor_verifier(self.raiz)(att)
                self.assertEqual(r.state, "verified")
                self.assertEqual((r.change_id, r.artefacto, r.usuario), (CID, ART, "Ana"))

    def test_nota_anchor(self):
        self.assertIn("trust model", approvals.NOTA_ANCHOR)
        self.assertIn("does not prove the identity or authorship", approvals.NOTA_ANCHOR)
        self.assertIn("deliberately synthesized local console input", approvals.NOTA_ANCHOR)


if __name__ == "__main__":
    unittest.main()
