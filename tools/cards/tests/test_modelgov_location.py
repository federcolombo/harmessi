"""Tests de ubicación y escritura de assessments de governance (`card_path`,
`write_governance_assessment`; Change `20261005-model-risk-responsible-ai`, R60-R62)."""
from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.cards import assess, core, govpolicy, modelcard, modelgov, resolvers  # noqa: F401

T0 = "2026-10-01T10:00:00Z"
NOW = "2026-10-04T00:00:00Z"
REPO = Path(__file__).resolve().parents[3]


def codigo_de(funcion, *args, **kwargs):
    try:
        funcion(*args, **kwargs)
    except core.CardError as exc:
        return exc.code
    raise AssertionError("no lanzó CardError")


def hacer_assessment(model_id="clasificador", version="1.0.0", notes=None, **kw):
    cid = modelcard.model_card_id(model_id, version)
    h = "a" * 64
    pin = core.EvidenceRef(
        "ev-mc", "model_card", f"{cid}__{h[:12]}", h, T0, locator=f"governance/cards/model/{cid}.json"
    )
    body = {
        "model_card_ref": {"evidence_id": "ev-mc"},
        "policy_ref": {
            "base_policy_id": govpolicy.BASE_POLICY.policy_id,
            "base_version": govpolicy.BASE_POLICY.version,
            "base_sha256": govpolicy.BASE_POLICY_SHA256,
            "effective_sha256": govpolicy.merge(govpolicy.BASE_POLICY).effective_sha256(),
        },
    }
    if notes is not None:
        body["notes"] = notes
    base = dict(
        schema_version=1,
        card_kind="governance_assessment",
        kind_schema_version=1,
        card_id=cid,
        title="Assessment de prueba",
        subject=model_id,
        created_at=T0,
        generated_at=T0,
        evidence=(pin,),
        claims=(core.Claim("c-mc", "Respaldo", supports=("ev-mc",), requirement_id="model_card_pin"),),
        body=body,
    )
    base.update(kw)
    return core.CardEnvelope(**base)


class BaseTmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name).resolve()

    @property
    def governance(self):
        return self.raiz / "governance"

    def destino(self, card_id="clasificador__1_0_0"):
        return self.raiz / "governance" / "model-risk" / f"{card_id}.json"

    def escribir_ajeno(self, contenido: bytes, card_id="clasificador__1_0_0"):
        ruta = self.destino(card_id)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)
        return ruta

    def escribir(self, card=None, **kw):
        return modelgov.write_governance_assessment(self.raiz, card or hacer_assessment(), clock=lambda: NOW, **kw)


class TestCardPath(BaseTmp):
    def test_ruta_bajo_governance_model_risk(self):
        ruta = modelgov.card_path(self.raiz, "clasificador__1_0_0")
        self.assertEqual(ruta.relative_to(self.raiz).as_posix(), "governance/model-risk/clasificador__1_0_0.json")
        self.assertEqual(modelgov.CARD_DIR_PARTES, ("governance", "model-risk"))

    def test_acepta_project_root_str(self):
        self.assertEqual(modelgov.card_path(str(self.raiz), "m1").name, "m1.json")

    def test_no_crea_ni_escanea_nada(self):
        modelgov.card_path(self.raiz, "m1")
        self.assertFalse(self.governance.exists())

    def test_card_id_invalido_o_con_escape(self):
        invalidos = (
            "", "../x", "..", "a/b", "a\\b", "A", "C:\\x", "/abs", "x.json", "con espacio",
            "a" * 65, "none", "null", "default", "status", None, 5, ["a"],
        )
        for card_id in invalidos:
            with self.subTest(card_id=card_id):
                self.assertEqual(codigo_de(modelgov.card_path, self.raiz, card_id), core.CODE_ID_INVALID)
        self.assertFalse(self.governance.exists())

    def test_project_root_invalido(self):
        self.assertEqual(codigo_de(modelgov.card_path, None, "m1"), modelgov.CODE_PATH_INVALID)

    def test_symlink_que_escapa_de_project_root(self):
        with tempfile.TemporaryDirectory() as afuera:
            try:
                os.symlink(afuera, self.governance, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks no disponibles en este entorno")
            self.assertEqual(codigo_de(modelgov.card_path, self.raiz, "m1"), modelgov.CODE_PATH_INVALID)


class TestWriteGovernanceAssessment(BaseTmp):
    def test_crea_directorios_y_escribe(self):
        self.assertFalse(self.governance.exists())
        ruta = self.escribir()
        self.assertEqual(ruta, modelgov.card_path(self.raiz, "clasificador__1_0_0"))
        self.assertTrue(ruta.is_file())
        self.assertEqual(assess.read_card(ruta).to_dict(), hacer_assessment().to_dict())
        self.assertEqual(os.listdir(ruta.parent), ["clasificador__1_0_0.json"])

    def test_no_toca_otros_directorios(self):
        self.escribir()
        self.assertEqual(os.listdir(self.governance), ["model-risk"])
        self.assertEqual(os.listdir(self.raiz), ["governance"])

    def test_segundo_write_sin_replace_falla_y_no_toca_el_original(self):
        ruta = self.escribir()
        antes = ruta.read_bytes()
        codigo = codigo_de(
            modelgov.write_governance_assessment, self.raiz, hacer_assessment(notes="Otra"), clock=lambda: NOW
        )
        self.assertIn(codigo, (modelgov.CODE_EXISTS, core.CODE_IO_ERROR))
        self.assertEqual(ruta.read_bytes(), antes)
        self.assertEqual(os.listdir(ruta.parent), ["clasificador__1_0_0.json"])

    def test_misma_card_dos_veces_tambien_falla(self):
        self.escribir()
        self.assertIn(
            codigo_de(modelgov.write_governance_assessment, self.raiz, hacer_assessment(), clock=lambda: NOW),
            (modelgov.CODE_EXISTS, core.CODE_IO_ERROR),
        )

    def test_replace_misma_identidad_crea_nueva_revision(self):
        ruta = self.escribir()
        antes = assess.read_card(ruta)
        self.escribir(hacer_assessment(notes="Notas revisadas"), replace=True)
        despues = assess.read_card(ruta)
        self.assertEqual(despues.card_id, antes.card_id)
        self.assertNotEqual(despues.revision_id(), antes.revision_id())
        self.assertEqual(despues.body["notes"], "Notas revisadas")

    def test_replace_sin_archivo_es_not_found_y_no_crea_governance(self):
        self.assertEqual(
            codigo_de(modelgov.write_governance_assessment, self.raiz, hacer_assessment(), replace=True,
                      clock=lambda: NOW),
            modelgov.CODE_NOT_FOUND,
        )
        self.assertFalse(self.governance.exists())

    def test_replace_de_otra_version_no_pisa_el_assessment_existente(self):
        ruta = self.escribir(hacer_assessment(version="1.0.0"))
        antes = ruta.read_bytes()
        v2 = hacer_assessment(version="2.0.0")
        codigo = codigo_de(modelgov.write_governance_assessment, self.raiz, v2, replace=True, clock=lambda: NOW)
        self.assertIn(codigo, (modelgov.CODE_NOT_FOUND, modelgov.CODE_IDENTITY_MISMATCH))
        self.assertEqual(ruta.read_bytes(), antes)
        self.assertEqual(os.listdir(ruta.parent), ["clasificador__1_0_0.json"])

    def test_nueva_version_sin_replace_es_otro_assessment_otro_archivo(self):
        self.escribir(hacer_assessment(version="1.0.0"))
        self.escribir(hacer_assessment(version="1.0.1"))
        self.assertEqual(
            sorted(os.listdir(self.destino().parent)), ["clasificador__1_0_0.json", "clasificador__1_0_1.json"]
        )

    def test_replace_con_otra_identidad_en_la_ruta_es_identity_mismatch(self):
        ajena = core.CardEnvelope(
            schema_version=1, card_kind="governance_assessment", kind_schema_version=1,
            card_id="clasificador__1_0_0", title="Ajena", subject="otro", created_at=T0, generated_at=T0,
        )
        ruta = self.destino()
        ruta.parent.mkdir(parents=True)
        assess.write_card(ruta, ajena, lambda: NOW)  # body {} sin validador
        antes = ruta.read_bytes()
        self.assertEqual(
            codigo_de(modelgov.write_governance_assessment, self.raiz, hacer_assessment(), replace=True,
                      clock=lambda: NOW),
            modelgov.CODE_IDENTITY_MISMATCH,
        )
        self.assertEqual(ruta.read_bytes(), antes)

    def test_replace_sobre_card_de_otro_kind_es_identity_mismatch(self):
        otra = core.CardEnvelope(
            schema_version=1, card_kind="model_card", kind_schema_version=1, card_id="clasificador__1_0_0",
            title="Model", subject="clasificador", created_at=T0, generated_at=T0,
        )
        ruta = self.destino()
        ruta.parent.mkdir(parents=True)
        assess.write_card(ruta, otra, lambda: NOW)
        antes = ruta.read_bytes()
        self.assertEqual(
            codigo_de(modelgov.write_governance_assessment, self.raiz, hacer_assessment(), replace=True,
                      clock=lambda: NOW),
            modelgov.CODE_IDENTITY_MISMATCH,
        )
        self.assertEqual(ruta.read_bytes(), antes)

    def test_archivo_ajeno_no_se_sobrescribe(self):
        for contenido in (b"hola, esto no es una Card\n", b'{"a": 1}\n', b"", b"\xff\xfe\x00"):
            with self.subTest(contenido=contenido):
                ruta = self.escribir_ajeno(contenido)
                for replace in (False, True):
                    with self.assertRaises(core.CardError):
                        modelgov.write_governance_assessment(
                            self.raiz, hacer_assessment(), replace=replace, clock=lambda: NOW
                        )
                    self.assertEqual(ruta.read_bytes(), contenido)
                self.assertEqual(
                    codigo_de(modelgov.write_governance_assessment, self.raiz, hacer_assessment(), replace=True,
                              clock=lambda: NOW),
                    modelgov.CODE_IDENTITY_MISMATCH,
                )
                self.assertIn(
                    codigo_de(modelgov.write_governance_assessment, self.raiz, hacer_assessment(), clock=lambda: NOW),
                    (modelgov.CODE_EXISTS, core.CODE_IO_ERROR),
                )
                ruta.unlink()

    def test_directorio_en_la_ruta_no_se_sobrescribe(self):
        ruta = self.destino()
        ruta.mkdir(parents=True)
        for replace in (False, True):
            with self.assertRaises(core.CardError):
                modelgov.write_governance_assessment(self.raiz, hacer_assessment(), replace=replace, clock=lambda: NOW)
        self.assertTrue(ruta.is_dir())

    def test_card_invalida_no_crea_governance(self):
        base = hacer_assessment()
        att_a = core.HumanAttestation("at-a", "risk_level=low", "ana", "owner", T0, "scope", "declared")
        att_b = core.HumanAttestation("at-b", "risk_level=high", "ana", "owner", T0, "scope", "declared")
        invalidas = {
            "clave desconocida": dataclasses.replace(base, body={**base.body, "inventada": 1}),
            "status": dataclasses.replace(base, body={**base.body, "status": "complete"}),
            "governance_completeness": dataclasses.replace(base, body={**base.body, "governance_completeness": "complete"}),
            "fair": dataclasses.replace(base, body={**base.body, "fair": True}),
            "schema ajeno": dataclasses.replace(base, kind_schema_version=2),
            "kind ajeno": dataclasses.replace(base, card_kind="data_card"),
            "card_id distinto": dataclasses.replace(base, card_id="otro__1_0_0"),
            "subject distinto": dataclasses.replace(base, subject="otro"),
            "colgante": dataclasses.replace(
                base, body={**base.body, "model_card_ref": {"evidence_id": "no-existe"}}
            ),
            "sin policy_ref": dataclasses.replace(
                base, body={k: v for k, v in base.body.items() if k != "policy_ref"}
            ),
            "riesgo contradictorio": dataclasses.replace(base, attestations=(att_a, att_b)),
            "ruta absoluta": dataclasses.replace(base, body={**base.body, "notes": "/etc/passwd"}),
            "dsn en x_": dataclasses.replace(base, body={**base.body, "x_dsn": "postgres://u:p@h/db"}),
        }
        for nombre, card in invalidas.items():
            for replace in (False, True):
                with self.subTest(caso=nombre, replace=replace):
                    with self.assertRaises(core.CardError):
                        modelgov.write_governance_assessment(self.raiz, card, replace=replace, clock=lambda: NOW)
                    self.assertFalse(self.governance.exists())

    def test_atestacion_futura_no_crea_governance(self):
        futura = core.HumanAttestation("at-f", "risk_level=low", "ana", "owner", "2030-01-01T00:00:00Z", "s", "declared")
        card = dataclasses.replace(hacer_assessment(), attestations=(futura,))
        with self.assertRaises(core.CardError):
            modelgov.write_governance_assessment(self.raiz, card, clock=lambda: NOW)
        self.assertFalse(self.governance.exists())

    def test_argumento_que_no_es_card_no_crea_governance(self):
        for valor in (None, {}, "x", 5):
            with self.subTest(valor=valor):
                self.assertEqual(
                    codigo_de(modelgov.write_governance_assessment, self.raiz, valor, clock=lambda: NOW),
                    core.CODE_FIELD_INVALID,
                )
        self.assertFalse(self.governance.exists())

    def test_model_card_no_se_escribe_como_assessment(self):
        mc = core.CardEnvelope(
            schema_version=1, card_kind="model_card", kind_schema_version=1, card_id="clasificador__1_0_0",
            title="Model", subject="clasificador", created_at=T0, generated_at=T0,
            body={"model_id": "clasificador", "model_version": "1.0.0", "description": "x"},
        )
        with self.assertRaises(core.CardError):
            modelgov.write_governance_assessment(self.raiz, mc, clock=lambda: NOW)
        self.assertFalse(self.governance.exists())

    def test_cada_model_id_tiene_su_archivo(self):
        self.escribir(hacer_assessment("modelo-a"))
        self.escribir(hacer_assessment("modelo-b"))
        self.assertEqual(
            sorted(os.listdir(self.destino().parent)), ["modelo-a__1_0_0.json", "modelo-b__1_0_0.json"]
        )

    def test_escritura_determinista(self):
        a = self.escribir()
        with tempfile.TemporaryDirectory() as otra:
            b = modelgov.write_governance_assessment(otra, hacer_assessment(), clock=lambda: NOW)
            self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_el_archivo_no_contiene_estado(self):
        texto = self.escribir().read_text(encoding="utf-8")
        for palabra in ("governance_completeness", '"status"', '"score"', '"fair"', '"passed"'):
            self.assertNotIn(palabra, texto)


class TestImportarNoCreaGovernance(BaseTmp):
    def test_importar_los_modulos_no_crea_governance(self):
        existia = (REPO / "governance").exists()
        entorno = dict(os.environ)
        entorno["PYTHONPATH"] = str(REPO) + os.pathsep + entorno.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-c", "import tools.cards.modelgov, tools.cards.govpolicy, tools.cards.resolvers"],
            cwd=str(self.raiz), env=entorno, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(self.governance.exists())
        self.assertEqual((REPO / "governance").exists(), existia)

    def test_card_path_validar_y_evaluar_no_crean_governance(self):
        modelgov.card_path(self.raiz, "m1")
        card = hacer_assessment()
        modelgov.validate_governance_assessment(card)
        modelgov.body_validator_for(card)(card.body)
        a = modelgov.evaluate_governance_assessment(card, self.raiz)
        modelgov.a_check_results(a)
        modelgov.evaluate_governance_assessment(self.raiz / "no-existe.json", self.raiz)
        self.assertFalse(self.governance.exists())
        self.assertEqual(os.listdir(self.raiz), [])


if __name__ == "__main__":
    unittest.main()
