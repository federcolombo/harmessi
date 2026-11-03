"""Paridad de hashes y layout entre `tools/cards/resolvers.py` y los paquetes
reales `datasources`, `datacontracts` y `qualityevidence` (Change
`20261002-data-cards`, R18, R21, R22, R23, D8).

`resolvers.py` no puede importar esos paquetes (R1): recomputa los hashes a
nivel de dict JSON con el mismo JSON canónico. Este test fija que la
duplicación sigue siendo exacta. Solo los tests importan ambos lados.
"""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.cards import resolvers
from tools.datacontracts import core as dc_core
from tools.datasources import core as ds_core
from tools.datasources import runtime as ds_runtime
from tools.qualityevidence import core as qe_core
from tools.qualityevidence import evidence as qe_evidence

REPO_ORIGEN = Path(__file__).resolve().parents[2]


def _observacion(source_id="clientes", generated_at="2026-10-01T10:00:00Z", rica=False):
    prov = ds_core.SourceProvenance(
        source_id=source_id,
        observer_id="obs:file",
        observer_code_sha256="f" * 64,
        access_mode="read",
        source_kind="file",
        generated_at=generated_at,
        tool_versions={"harmessi": "0.9"},
        requested_facets=("row_count", "schema"),
        unsupported_facets=("fingerprint",),
    )
    dataset = {"row_count": {"value": 1234, "exactness": "exact"}}
    campos = ()
    omitidos = ()
    if rica:
        dataset = {
            "row_count": {"value": 1234, "exactness": "approximate"},
            "fingerprint": {"algorithm": "sha256/bin/v1", "value": "a" * 64},
            "snapshot": {"as_of": "2026-09-30", "cutoff": None},
            "sampling": {"active": True, "method": "head", "sample_size": 100, "seed": 7},
        }
        campos = (
            ds_core.FieldObservation(
                "nombre_ñandú",
                "string",
                "VARCHAR(10)",
                {
                    "null_count": {"value": 3, "exactness": "exact"},
                    "value_distribution": {
                        "value": [{"value": "á", "frequency": 2}, {"value": "b", "frequency": 1}],
                        "exactness": "exact",
                        "complete": True,
                    },
                },
            ),
            ds_core.FieldObservation(
                "monto",
                "float",
                None,
                {"value_range": {"value": {"min": 0.1, "max": 1e22}, "exactness": "exact"}},
            ),
        )
        omitidos = ({"field": "monto", "facet": "distinct_count", "reason": "no soportada"},)
    return ds_core.SourceObservation(
        source_id=source_id, provenance=prov, dataset=dataset, fields=campos, omitted_facets=omitidos
    )


def _contrato(rica=False):
    campos = (dc_core.ContractField("id", "integer", required=True, nullable=False), dc_core.ContractField("monto", "float"))
    return dc_core.DataContract(
        contract_id="contrato-clientes",
        version=dc_core.ContractVersion("1.2.0", summary="resumen ñ", previous_version="1.1.0"),
        dataset_role="raw_table",
        fields=campos,
        keys=("id",) if rica else (),
        description="descripción con acentos" if rica else "",
        extensions={"x_nota": {"k": [1, 2.5, None]}} if rica else {},
    )


def _manifest(subject="data_contract_evaluation", declaration_kind="data_contract"):
    declaracion = qe_core.DeclarationRef(declaration_kind, "contrato-clientes", "1.0.0", "c" * 64)
    fuente = qe_core.EvidenceSource(
        kind="generated", role="input", sha256="b" * 64, description="conteo", params={"n": 1, "z": [1.5, "ñ"]}
    )
    return qe_evidence.build_manifest(
        subject_kind=subject,
        declaration=declaracion,
        source=fuente,
        results=[],
        scope=qe_core.ScopeWindow(population="todos", time_start="2026-01-01T00:00:00Z"),
        clock=lambda: datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc),
    )


def _via_archivo_json(obj):
    """Ida y vuelta por disco con el mismo formato que los persistidores reales."""
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / "x.json"
        ruta.write_bytes((json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)


class TestParidadObservacion(unittest.TestCase):
    def test_hash_observation_igual_a_content_sha256_real(self):
        for rica in (False, True):
            obs = _observacion(rica=rica)
            with self.subTest(rica=rica, via="dict"):
                self.assertEqual(resolvers.hash_observation(obs.to_dict()), obs.content_sha256())
            with self.subTest(rica=rica, via="archivo"):
                self.assertEqual(resolvers.hash_observation(_via_archivo_json(obs.to_dict())), obs.content_sha256())

    def test_hash_observation_ignora_generated_at(self):
        a = _observacion(generated_at="2026-09-01T00:00:00Z", rica=True)
        b = _observacion(generated_at="2026-10-01T00:00:00Z", rica=True)
        self.assertNotEqual(a.to_dict(), b.to_dict())
        self.assertEqual(resolvers.hash_observation(a.to_dict()), resolvers.hash_observation(b.to_dict()))

    def test_hash_observation_no_muta_la_entrada(self):
        datos = _observacion().to_dict()
        copia = json.loads(json.dumps(datos))
        resolvers.hash_observation(datos)
        self.assertEqual(datos, copia)
        self.assertIn("generated_at", datos["provenance"])

    def test_hash_observation_cambia_con_el_contenido(self):
        base = _observacion().to_dict()
        otra = json.loads(json.dumps(base))
        otra["dataset"]["row_count"]["value"] += 1
        self.assertNotEqual(resolvers.hash_observation(base), resolvers.hash_observation(otra))

    def test_hash_observation_rechaza_formas_invalidas(self):
        for malo in (None, [], "x", {}, {"provenance": None}, {"provenance": []}):
            with self.subTest(malo=malo):
                with self.assertRaises(resolvers.CardError):
                    resolvers.hash_observation(malo)

    def test_hash_provenance_igual_al_canonico_de_provenance_sin_generated_at(self):
        for rica in (False, True):
            obs = _observacion(rica=rica)
            prov = obs.provenance.to_dict()
            prov.pop("generated_at")
            esperado = ds_core.content_sha256(prov)
            with self.subTest(rica=rica):
                self.assertEqual(resolvers.hash_provenance(obs.to_dict()), esperado)
                self.assertEqual(resolvers.hash_provenance(obs.provenance.to_dict()), esperado)
                self.assertEqual(resolvers.hash_provenance(_via_archivo_json(obs.to_dict())), esperado)

    def test_hash_provenance_ignora_generated_at_y_difiere_del_de_observacion(self):
        a = _observacion(generated_at="2026-09-01T00:00:00Z")
        b = _observacion(generated_at="2026-10-01T00:00:00Z")
        self.assertEqual(resolvers.hash_provenance(a.to_dict()), resolvers.hash_provenance(b.to_dict()))
        self.assertNotEqual(resolvers.hash_provenance(a.to_dict()), resolvers.hash_observation(a.to_dict()))

    def test_hash_provenance_rechaza_no_dict(self):
        for malo in (None, [], "x", 5):
            with self.subTest(malo=malo):
                with self.assertRaises(resolvers.CardError):
                    resolvers.hash_provenance(malo)

    def test_resolver_sobre_persistencia_real_de_datasources(self):
        """Usa `runtime._persistir_observacion` (el escritor real): fija el layout."""
        obs = _observacion(rica=True)
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self.assertIsNone(ds_runtime._persistir_observacion(repo, obs))
            ref = type("R", (), {"ref_id": f"clientes__{obs.content_sha256()[:12]}", "member": None})()
            res = resolvers.source_observation_resolver(repo)(ref)
            self.assertEqual(res.state, "found", res.detail)
            self.assertEqual(res.current_sha256, obs.content_sha256())
            ref_prov = type("R", (), {"ref_id": ref.ref_id, "member": "provenance"})()
            res_prov = resolvers.source_provenance_resolver(repo)(ref_prov)
            self.assertEqual(res_prov.state, "found", res_prov.detail)
            self.assertEqual(res_prov.current_sha256, resolvers.hash_provenance(obs.to_dict()))


class TestParidadContrato(unittest.TestCase):
    def test_hash_contract_igual_a_content_sha256_real(self):
        for rica in (False, True):
            contrato = _contrato(rica=rica)
            with self.subTest(rica=rica, via="dict"):
                self.assertEqual(resolvers.hash_contract(contrato.to_dict()), contrato.content_sha256())
            with self.subTest(rica=rica, via="archivo"):
                self.assertEqual(resolvers.hash_contract(_via_archivo_json(contrato.to_dict())), contrato.content_sha256())

    def test_resolver_sobre_contrato_escrito_como_to_dict(self):
        contrato = _contrato(rica=True)
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "contracts").mkdir()
            (repo / "contracts" / "c.json").write_text(json.dumps(contrato.to_dict()), encoding="utf-8")
            ref = type("R", (), {"ref_id": "contrato-clientes@1.2.0", "locator": "contracts/c.json"})()
            res = resolvers.harmessi_contract_resolver(repo)(ref)
            self.assertEqual(res.state, "found", res.detail)
            self.assertEqual(res.current_sha256, contrato.content_sha256())

    def test_limitacion_conocida_contrato_a_mano_con_defaults_omitidos_no_coincide(self):
        """LIMITACIÓN CONOCIDA: `hash_contract` hashea el dict TAL CUAL está en el
        archivo. Un contrato escrito a mano que omite campos con default (que
        `DataContract.from_dict` rellena) es el MISMO contrato lógico pero NO
        produce el hash de `DataContract.content_sha256()`. Para pinnear, el autor
        debe escribir el archivo en forma `to_dict()` (o pinnear `hash_contract`)."""
        contrato = _contrato()
        a_mano = {
            "contract_id": "contrato-clientes",
            "version": {"version": "1.2.0", "summary": "resumen ñ", "previous_version": "1.1.0"},
            "dataset_role": "raw_table",
            "fields": [{"name": "id", "type_family": "integer", "required": True, "nullable": False},
                       {"name": "monto", "type_family": "float"}],
            "schema_version": 1,
        }
        reconstruido = dc_core.DataContract.from_dict(a_mano)
        self.assertEqual(reconstruido.contract_id, contrato.contract_id)
        self.assertNotEqual(resolvers.hash_contract(a_mano), reconstruido.content_sha256())
        # En cambio, el hash de su forma normalizada sí coincide.
        self.assertEqual(resolvers.hash_contract(reconstruido.to_dict()), reconstruido.content_sha256())

    def test_hash_contract_rechaza_no_dict(self):
        for malo in (None, [], "x", 5):
            with self.subTest(malo=malo):
                with self.assertRaises(resolvers.CardError):
                    resolvers.hash_contract(malo)


class TestParidadManifestDeCalidad(unittest.TestCase):
    def test_hash_quality_manifest_igual_al_real_y_al_persistido(self):
        for subject, kind in (
            ("data_contract_evaluation", "data_contract"),
            ("model_quality_evaluation", "model_quality_policy"),
        ):
            manifest = _manifest(subject, kind)
            datos = manifest.to_dict()
            with self.subTest(subject=subject, via="dict"):
                self.assertEqual(resolvers.hash_quality_manifest(datos), manifest.content_sha256())
                self.assertEqual(resolvers.hash_quality_manifest(datos), datos["content_sha256"])
            with self.subTest(subject=subject, via="write_manifest"):
                with tempfile.TemporaryDirectory() as tmp:
                    ruta = qe_evidence.write_manifest(tmp, manifest)
                    persistido = json.loads(Path(ruta).read_text(encoding="utf-8"))
                    self.assertEqual(resolvers.hash_quality_manifest(persistido), manifest.content_sha256())
                    self.assertEqual(resolvers.hash_quality_manifest(persistido), persistido["content_sha256"])

    def test_hash_quality_manifest_excluye_generated_at_y_content_sha256(self):
        datos = _manifest().to_dict()
        base = resolvers.hash_quality_manifest(datos)
        self.assertEqual(resolvers.hash_quality_manifest(dict(datos, generated_at="2031-01-01T00:00:00Z")), base)
        self.assertEqual(resolvers.hash_quality_manifest(dict(datos, content_sha256="0" * 64)), base)
        sin_hash = {k: v for k, v in datos.items() if k != "content_sha256"}
        self.assertEqual(resolvers.hash_quality_manifest(sin_hash), base)

    def test_hash_quality_manifest_cambia_con_el_contenido(self):
        datos = _manifest().to_dict()
        otro = json.loads(json.dumps(datos))
        otro["scope"]["population"] = "otra"
        self.assertNotEqual(resolvers.hash_quality_manifest(datos), resolvers.hash_quality_manifest(otro))

    def test_hash_quality_manifest_rechaza_no_dict(self):
        for malo in (None, [], "x", 5):
            with self.subTest(malo=malo):
                with self.assertRaises(resolvers.CardError):
                    resolvers.hash_quality_manifest(malo)

    def test_resolver_sobre_write_manifest_real(self):
        manifest = _manifest()
        with tempfile.TemporaryDirectory() as tmp:
            qe_evidence.write_manifest(tmp, manifest)
            ref = type("R", (), {"ref_id": manifest.evidence_id})()
            res = resolvers.quality_evidence_resolver(tmp)(ref)
            self.assertEqual(res.state, "found", res.detail)
            self.assertEqual(res.current_sha256, manifest.content_sha256())
            res2 = resolvers.data_contract_result_resolver(tmp)(ref)
            self.assertEqual(res2.state, "found", res2.detail)


class TestParidadLayoutYPatrones(unittest.TestCase):
    def test_directorio_base_coincide_con_el_de_los_escritores_reales(self):
        texto_runtime = (REPO_ORIGEN / "tools" / "datasources" / "runtime.py").read_text(encoding="utf-8")
        texto_evidence = (REPO_ORIGEN / "tools" / "qualityevidence" / "evidence.py").read_text(encoding="utf-8")
        self.assertEqual(resolvers._DIR_HARMESSI, ".harmessi")
        self.assertIn(f'/ "{resolvers._DIR_HARMESSI}" / "observations"', texto_runtime)
        self.assertIn(f'/ "{resolvers._DIR_HARMESSI}" / "quality"', texto_evidence)
        self.assertIn('"observation.json"', texto_runtime)
        self.assertIn('"manifest.json"', texto_evidence)

    def test_layout_real_de_observacion_es_el_que_lee_el_resolver(self):
        obs = _observacion()
        with tempfile.TemporaryDirectory() as tmp:
            ds_runtime._persistir_observacion(tmp, obs)
            hijos = sorted(p.name for p in (Path(tmp) / ".harmessi" / "observations").iterdir())
            self.assertEqual(hijos, [f"clientes__{obs.content_sha256()[:12]}"])
            self.assertTrue((Path(tmp) / ".harmessi" / "observations" / hijos[0] / "observation.json").is_file())

    def test_layout_real_de_manifest_es_el_que_lee_el_resolver(self):
        manifest = _manifest()
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(qe_evidence.write_manifest(tmp, manifest)).resolve()
            esperada = Path(tmp).resolve() / ".harmessi" / "quality" / manifest.evidence_id / "manifest.json"
            self.assertEqual(ruta, esperada)

    def test_patrones_de_ids_coinciden_con_los_reales(self):
        self.assertEqual(resolvers._RE_SOURCE_ID, ds_core.SOURCE_ID_PATTERN)
        self.assertEqual(resolvers._RE_EVIDENCE_ID.pattern, qe_core._PATRON_EVIDENCE_ID.pattern)
        self.assertEqual(resolvers._RE_SOURCE_ID, dc_core._PATRON_ID.pattern)
        self.assertEqual(r"\d+\.\d+\.\d+", dc_core._PATRON_SEMVER.pattern)
        self.assertTrue(resolvers._RE_CONTRATO_REF.fullmatch("contrato-clientes@1.2.3"))
        self.assertEqual(resolvers._RE_SHA256.pattern, r"[0-9a-f]{64}")
        # Un evidence_id generado por el código real cumple el patrón del resolver.
        self.assertTrue(resolvers._RE_EVIDENCE_ID.fullmatch(qe_evidence.new_evidence_id()))
        self.assertTrue(re.fullmatch(resolvers._RE_SOURCE_ID, "a__b"))

    def test_role_pattern_paridad_con_datasources(self):
        from tools.cards import datacard

        self.assertEqual(datacard.ROLE_PATTERN, ds_core.ROLE_PATTERN)
        validos = ("a", "primary", "raw_table", "a-b_c", "0x", "a" * 64)
        invalidos = ("", "A", "-a", "_a", "a b", "a/b", "a\\b", "a.b", "a" * 65, "ñ", "a\n")
        for caso in validos + invalidos:
            with self.subTest(caso=caso):
                esperado = re.fullmatch(ds_core.ROLE_PATTERN, caso) is not None
                self.assertEqual(re.fullmatch(datacard.ROLE_PATTERN, caso) is not None, esperado)
        for caso in validos:
            self.assertIsNotNone(re.fullmatch(datacard.ROLE_PATTERN, caso), caso)
        for caso in invalidos:
            self.assertIsNone(re.fullmatch(datacard.ROLE_PATTERN, caso), caso)

    def test_semver_pattern_paridad_con_datacontracts(self):
        """datacard es IGUAL o MÁS ESTRICTO que `datacontracts._PATRON_SEMVER`
        (`\\d+\\.\\d+\\.\\d+`): rechaza ceros a la izquierda que datacontracts acepta
        (divergencia conocida, reportada). Nunca acepta algo que datacontracts rechace."""
        from tools.cards import datacard

        validos = ("0.0.0", "1.2.3", "10.20.30", "0.10.0")
        invalidos = ("", "1.2", "1.2.3.4", "v1.2.3", "1.2.x", "1.2.3-rc1", "1..3", " 1.2.3", "1.2.3\n", "-1.2.3")
        con_ceros = ("01.0.0", "1.02.3", "1.2.03")  # dc acepta, datacard rechaza
        for caso in validos + invalidos + con_ceros:
            with self.subTest(caso=caso):
                dc_ok = dc_core._PATRON_SEMVER.fullmatch(caso) is not None
                card_ok = re.fullmatch(datacard.SEMVER_PATTERN, caso) is not None
                if card_ok:
                    self.assertTrue(dc_ok)
        for caso in validos:
            self.assertIsNotNone(dc_core._PATRON_SEMVER.fullmatch(caso), caso)
            self.assertIsNotNone(re.fullmatch(datacard.SEMVER_PATTERN, caso), caso)
        for caso in invalidos:
            self.assertIsNone(dc_core._PATRON_SEMVER.fullmatch(caso), caso)
            self.assertIsNone(re.fullmatch(datacard.SEMVER_PATTERN, caso), caso)
        for caso in con_ceros:
            self.assertIsNotNone(dc_core._PATRON_SEMVER.fullmatch(caso), caso)
            self.assertIsNone(re.fullmatch(datacard.SEMVER_PATTERN, caso), caso)

    def test_subject_kind_de_resolvers_existe_en_qualityevidence(self):
        self.assertIn(resolvers.SUBJECT_DATA_CONTRACT_EVALUATION, qe_core.SUBJECT_KINDS)


if __name__ == "__main__":
    unittest.main()
