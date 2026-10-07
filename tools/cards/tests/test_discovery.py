"""Tests de `tools/cards/discovery.py` (Change `20261005-cards-governance-integration`,
R17-R21, R44-R49; contrato D). Repos 100% sintéticos en directorios temporales."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tools.cards import core, datacard, discovery, govpolicy, modelcard, modelgov

T0 = "2026-10-01T10:00:00Z"
NOW = "2026-10-04T00:00:00Z"
H1 = "a" * 64


def hacer_data_card(card_id="producto-a"):
    pin = core.EvidenceRef("ev-src-a", "source_observation", "ventas__aaaaaaaaaaaa", H1, T0)
    return core.CardEnvelope(
        schema_version=1, card_kind="data_card", kind_schema_version=1, card_id=card_id,
        title="Data Card de prueba", subject=card_id, created_at=T0, generated_at=T0,
        evidence=(pin,),
        claims=(core.Claim("c-src-a", "Observada", supports=("ev-src-a",), requirement_id="source_src-a"),),
        body={
            "description": "Producto de prueba",
            "source_refs": [{"source_ref_id": "src-a", "source_id": "ventas", "observation_evidence_id": "ev-src-a"}],
        },
    )


def hacer_model_card(model_id="clasificador", version="1.0.0"):
    return core.CardEnvelope(
        schema_version=1, card_kind="model_card", kind_schema_version=1,
        card_id=modelcard.model_card_id(model_id, version), title="Model Card de prueba", subject=model_id,
        created_at=T0, generated_at=T0,
        body={"model_id": model_id, "model_version": version, "description": "Modelo de prueba"},
    )


def hacer_assessment(model_id="clasificador", version="1.0.0"):
    cid = modelcard.model_card_id(model_id, version)
    pin = core.EvidenceRef(
        "ev-mc", "model_card", f"{cid}__{H1[:12]}", H1, T0, locator=f"governance/cards/model/{cid}.json"
    )
    return core.CardEnvelope(
        schema_version=1, card_kind="governance_assessment", kind_schema_version=1, card_id=cid,
        title="Assessment de prueba", subject=model_id, created_at=T0, generated_at=T0,
        evidence=(pin,),
        claims=(core.Claim("c-mc", "Respaldo", supports=("ev-mc",), requirement_id="model_card_pin"),),
        body={
            "model_card_ref": {"evidence_id": "ev-mc"},
            "policy_ref": {
                "base_policy_id": govpolicy.BASE_POLICY.policy_id,
                "base_version": govpolicy.BASE_POLICY.version,
                "base_sha256": govpolicy.BASE_POLICY_SHA256,
                "effective_sha256": govpolicy.merge(govpolicy.BASE_POLICY).effective_sha256(),
            },
        },
    )


class BaseTmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name).resolve()

    def escribir_texto(self, rel: str, texto: str) -> Path:
        ruta = self.raiz.joinpath(*rel.split("/"))
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto, encoding="utf-8")
        return ruta


class TestDescubrir(BaseTmp):
    def test_repo_vacio(self):
        self.assertEqual(discovery.descubrir(self.raiz), [])

    def test_rutas_conocidas_y_orden(self):
        for rel in (
            "governance/model-risk/b.json", "governance/cards/model/z.json", "governance/cards/data/b.json",
            "governance/cards/data/a.json", "governance/cards/data/leeme.txt",
        ):
            self.escribir_texto(rel, "{}")
        encontrados = [(d.kind, d.rel_path) for d in discovery.descubrir(self.raiz)]
        self.assertEqual(
            encontrados,
            [
                ("data", "governance/cards/data/a.json"),
                ("data", "governance/cards/data/b.json"),
                ("model", "governance/cards/model/z.json"),
                ("governance", "governance/model-risk/b.json"),
            ],
        )

    def test_no_recursivo_ni_otras_rutas(self):
        self.escribir_texto("governance/cards/data/sub/x.json", "{}")
        self.escribir_texto("governance/otros/y.json", "{}")
        self.escribir_texto("src/z.json", "{}")
        (self.raiz / "governance" / "cards" / "data" / "carpeta.json").mkdir()
        self.assertEqual(discovery.descubrir(self.raiz), [])

    def test_symlink_se_lista(self):
        destino = self.escribir_texto("fuera.json", "{}")
        enlace = self.raiz / "governance" / "cards" / "data" / "enlace.json"
        enlace.parent.mkdir(parents=True)
        try:
            os.symlink(destino, enlace)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks no disponibles")
        self.assertEqual([d.rel_path for d in discovery.descubrir(self.raiz)], ["governance/cards/data/enlace.json"])
        pv = discovery.validar_proyecto(self.raiz)
        self.assertEqual(pv.reports[0].status, "invalid")


class TestValidarProyecto(BaseTmp):
    def test_data_card_sin_modelgov(self):
        datacard.write_data_card(self.raiz, hacer_data_card(), clock=lambda: NOW)
        pv = discovery.validar_proyecto(self.raiz)
        self.assertEqual(len(pv.reports), 1)
        r = pv.reports[0]
        self.assertEqual((r.kind, r.card_id, r.rel_path), ("data", "producto-a", "governance/cards/data/producto-a.json"))
        self.assertIn(r.status, ("complete", "incomplete", "stale"))
        self.assertTrue(r.revision_id.startswith("producto-a__"))
        self.assertIsNone(pv.governance)
        self.assertTrue(r.check_results)

    def test_model_card_y_assessment(self):
        modelcard.write_model_card(self.raiz, hacer_model_card(), clock=lambda: NOW)
        modelgov.write_governance_assessment(self.raiz, hacer_assessment(), clock=lambda: NOW)
        pv = discovery.validar_proyecto(self.raiz)
        self.assertEqual([r.kind for r in pv.reports], ["model", "governance"])
        gov = pv.reports[1]
        self.assertIsNotNone(gov.policy)
        self.assertIn("effective_level", gov.policy)
        self.assertIsNotNone(pv.governance)

    def test_filtro_kinds(self):
        datacard.write_data_card(self.raiz, hacer_data_card(), clock=lambda: NOW)
        modelcard.write_model_card(self.raiz, hacer_model_card(), clock=lambda: NOW)
        pv = discovery.validar_proyecto(self.raiz, kinds=["model"])
        self.assertEqual([r.kind for r in pv.reports], ["model"])

    def test_archivo_malformado_es_invalid(self):
        self.escribir_texto("governance/cards/data/roto.json", "{no es json")
        self.escribir_texto("governance/cards/model/lista.json", "[]")
        pv = discovery.validar_proyecto(self.raiz)
        self.assertEqual([r.status for r in pv.reports], ["invalid", "invalid"])
        for r in pv.reports:
            self.assertTrue(any(c.status == "FAIL" for c in r.check_results))

    def test_nombre_distinto_de_card_id(self):
        ruta = datacard.write_data_card(self.raiz, hacer_data_card(), clock=lambda: NOW)
        ruta.rename(ruta.with_name("otro.json"))
        r = discovery.validar_proyecto(self.raiz).reports[0]
        self.assertEqual(r.status, "invalid")
        self.assertEqual(r.findings[0]["code"], "DATACARD-IDENTITY-MISMATCH")

    def test_kind_distinto_al_directorio(self):
        ruta = modelcard.write_model_card(self.raiz, hacer_model_card(), clock=lambda: NOW)
        destino = self.raiz / "governance" / "cards" / "data" / ruta.name
        destino.parent.mkdir(parents=True)
        destino.write_bytes(ruta.read_bytes())
        r = discovery.validar_proyecto(self.raiz, kinds=["data"]).reports[0]
        self.assertEqual(r.status, "invalid")
        self.assertEqual(r.findings[0]["code"], "DATACARD-KIND-INVALID")

    def test_path_explicito_fuera_de_rutas_conocidas(self):
        ruta = datacard.write_data_card(self.raiz, hacer_data_card(), clock=lambda: NOW)
        copia = self.raiz / "otra" / "x.json"
        copia.parent.mkdir()
        copia.write_bytes(ruta.read_bytes())
        pv = discovery.validar_proyecto(self.raiz, paths=["otra/x.json"])
        self.assertEqual(pv.reports[0].kind, "data")
        self.assertNotEqual(pv.reports[0].status, "invalid")
        self.assertTrue(any("fuera de las rutas conocidas" in n for n in pv.notes))

    def test_path_fuera_del_repo(self):
        pv = discovery.validar_proyecto(self.raiz, paths=[str(self.raiz.parent / "ajeno.json")])
        self.assertEqual(pv.reports[0].status, "invalid")
        self.assertNotIn(str(self.raiz.parent), json.dumps(discovery.report_a_dict(pv.reports[0])))

    def test_report_a_dict_json_safe_y_sin_absolutos(self):
        datacard.write_data_card(self.raiz, hacer_data_card(), clock=lambda: NOW)
        self.escribir_texto("governance/cards/data/roto.json", "{" + str(self.raiz))
        for r in discovery.validar_proyecto(self.raiz).reports:
            texto = json.dumps(discovery.report_a_dict(r), ensure_ascii=False)
            self.assertNotIn(str(self.raiz), texto)

    def test_validar_no_escribe(self):
        datacard.write_data_card(self.raiz, hacer_data_card(), clock=lambda: NOW)
        antes = sorted(p.relative_to(self.raiz).as_posix() for p in self.raiz.rglob("*"))
        discovery.validar_proyecto(self.raiz)
        despues = sorted(p.relative_to(self.raiz).as_posix() for p in self.raiz.rglob("*"))
        self.assertEqual(antes, despues)


class TestLimpiarTexto(unittest.TestCase):
    def test_control_y_truncado(self):
        t = discovery.limpiar_texto("a\x1b[31mb\nc" + "x" * 500)
        self.assertNotIn("\x1b", t)
        self.assertNotIn("\n", t)
        self.assertLessEqual(len(t), discovery.MAX_TEXTO)

    def test_oculta_ruta_del_repo(self):
        self.assertNotIn("/tmp/repo", discovery.limpiar_texto("falla en /tmp/repo/x", "/tmp/repo"))


class TestEstadoCapabilities(unittest.TestCase):
    def test_legacy_sin_lista(self):
        for control in (None, {}, {"otra": 1}):
            e = discovery.estado_capabilities(control)
            self.assertTrue(e["legacy"])
            self.assertTrue(e["predictive_modeling"])
            self.assertFalse(e["data_cards"])
            self.assertFalse(e["model_governance"])
            self.assertEqual(e["invalida"], [])

    def test_lista_literal(self):
        e = discovery.estado_capabilities({"capabilities_habilitadas": ["data_cards"]})
        self.assertFalse(e["legacy"])
        self.assertTrue(e["data_cards"])
        self.assertFalse(e["predictive_modeling"])
        self.assertEqual(e["habilitadas"], frozenset({"data_cards"}))

    def test_model_governance_sin_predictive_es_invalida(self):
        e = discovery.estado_capabilities({"capabilities_habilitadas": ["model_governance"]})
        self.assertTrue(e["invalida"])

    def test_lista_malformada(self):
        e = discovery.estado_capabilities({"capabilities_habilitadas": "data_cards"})
        self.assertTrue(e["invalida"])


def _romper_imports(*nombres):
    """Parche de `discovery._importar` que falla (ImportError) para los módulos dados."""
    original = discovery._importar

    def falso(nombre):
        if nombre in nombres:
            raise ImportError(f"simulado: {nombre}")
        return original(nombre)

    return mock.patch.object(discovery, "_importar", side_effect=falso)


class TestFailClosed(BaseTmp):
    def test_govconfig_roto_gobierno_unresolvable(self):
        modelcard.write_model_card(self.raiz, hacer_model_card(), clock=lambda: NOW)
        modelgov.write_governance_assessment(self.raiz, hacer_assessment(), clock=lambda: NOW)
        with _romper_imports("govconfig"):
            pv = discovery.validar_proyecto(self.raiz, kinds=["governance"])
        self.assertIsNotNone(pv.governance)
        self.assertEqual(pv.governance.state, "unresolvable")
        self.assertEqual([h.code for h in pv.governance.findings], ["GOVCFG-UNRESOLVABLE"])
        self.assertNotEqual(pv.reports[0].status, "complete")
        self.assertTrue(any("no disponible" in n for n in pv.notes))

    def test_approvals_roto_verificador_sintetico_unresolvable(self):
        notas: list = []
        with _romper_imports("approvals"):
            verificador = discovery._verificador_ancla(self.raiz, notas)
        self.assertIsNotNone(verificador)
        self.assertEqual(verificador(object()).state, "unresolvable")
        att = SimpleNamespace(attestation_id="at-1", attestation_kind="anchored")
        card = SimpleNamespace(attestations=(att,))
        filas = discovery._anclas(card, verificador, self.raiz)
        self.assertEqual(filas[0]["state"], "unresolvable")
        self.assertNotIn("usuario", filas[0])

    def test_approvals_roto_no_omite_el_verificador_en_validar(self):
        datacard.write_data_card(self.raiz, hacer_data_card(), clock=lambda: NOW)
        with _romper_imports("approvals"):
            pv = discovery.validar_proyecto(self.raiz)
        self.assertEqual(len(pv.reports), 1)
        self.assertTrue(any("anchored quedan unresolvable" in n for n in pv.notes))


class TestEnlaces(BaseTmp):
    def _enlazar(self, origen: Path, destino: Path):
        origen.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(destino, origen, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks no disponibles")

    def test_directorio_de_cards_symlink_es_hallazgo(self):
        real = self.raiz / "otro"
        real.mkdir()
        self._enlazar(self.raiz / "governance" / "cards" / "data", real)
        self.assertEqual([d.rel_path for d in discovery.descubrir(self.raiz)], ["governance/cards/data"])
        r = discovery.validar_proyecto(self.raiz).reports[0]
        self.assertEqual(r.status, "invalid")
        self.assertEqual(r.findings[0]["code"], "CARD-PATH-NOT-REGULAR")

    def test_padre_governance_symlink_es_hallazgo_por_directorio(self):
        real = self.raiz / "real"
        (real / "cards" / "data").mkdir(parents=True)
        self._enlazar(self.raiz / "governance", real)
        reportes = discovery.validar_proyecto(self.raiz).reports
        self.assertTrue(reportes)
        self.assertTrue(all(r.status == "invalid" for r in reportes))

    def test_policy_symlink_es_hallazgo(self):
        real = self.raiz / "otro"
        real.mkdir()
        self._enlazar(self.raiz / "governance" / "policy", real)
        self.assertIn("governance/policy", [d.rel_path for d in discovery.descubrir(self.raiz)])

    def test_path_con_componente_intermedio_enlace_es_invalid(self):
        real = self.raiz / "real"
        real.mkdir()
        self.escribir_texto("real/x.json", "{}")
        self._enlazar(self.raiz / "atajo", real)
        r = discovery.validar_proyecto(self.raiz, paths=["atajo/x.json"]).reports[0]
        self.assertEqual(r.status, "invalid")
        self.assertEqual(r.findings[0]["code"], "CARD-PATH-NOT-REGULAR")


class TestKindDesconocido(BaseTmp):
    def test_card_kind_desconocido_invalid_sin_evaluar(self):
        ruta = datacard.write_data_card(self.raiz, hacer_data_card(), clock=lambda: NOW)
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["card_kind"] = "otra_cosa"
        datos.pop("revision_id", None)
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        with mock.patch.object(discovery, "_evaluar_card", side_effect=AssertionError("no debe evaluarse")):
            r = discovery.validar_proyecto(self.raiz).reports[0]
        self.assertEqual(r.status, "invalid")


class TestSaneoDeChecks(BaseTmp):
    def test_check_results_sin_controles_ni_rutas_absolutas(self):
        ruta = datacard.write_data_card(self.raiz, hacer_data_card(), clock=lambda: NOW)
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["body"]["x\x1b[31m" + str(self.raiz)] = 1  # clave desconocida con control y ruta
        datos.pop("revision_id", None)
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        r = discovery.validar_proyecto(self.raiz).reports[0]
        for c in r.check_results:
            blob = c.message + (c.detail or "") + (c.subject or "")
            self.assertNotIn("\x1b", blob)
            self.assertNotIn(str(self.raiz), blob)


class TestLimpiarTextoRutasAbsolutas(unittest.TestCase):
    """Cierre de revisión ciclo 2 (N-7): sin rutas absolutas de otro origen (R49/R71)."""

    def test_redacta_rutas_absolutas_de_usuario_y_conserva_urls(self):
        t = discovery.limpiar_texto(
            "ver C:\\Users\\pepe\\datos.csv, D:/proyectos/x y /home/pepe/y.txt o http://ejemplo.com/a"
        )
        self.assertNotIn("pepe", t)
        self.assertNotIn("proyectos", t)
        self.assertIn("<ruta>", t)
        self.assertIn("http://ejemplo.com/a", t)

    def test_texto_sin_rutas_no_cambia(self):
        self.assertEqual(discovery.limpiar_texto("tabla de clientes 12:30"), "tabla de clientes 12:30")


if __name__ == "__main__":
    unittest.main()
