"""B-13 (`v015-ds-core-debt`): Data Card `temporality` current/as_of.

Objetos reales (`datasources.core.SourceObservation` persistida con el layout
`.harmessi/observations/<source_id>__<hash12>/observation.json`). Invariantes:
la Card `as_of` NO queda stale solo porque aparezca una observación más nueva
(se informa `DATACARD-AS-OF-HISTORICAL`), pero SÍ si la observación pinneada
cambia o desaparece; las Cards v1 se siguen leyendo como `current`.
"""
from __future__ import annotations

import dataclasses
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.cards import assess, core, datacard, resolvers
from tools.datasources import core as ds_core

T0 = "2026-10-01T10:00:00Z"
NOW = "2026-10-04T00:00:00Z"


def _observacion(generated_at, filas, source_id="clientes"):
    prov = ds_core.SourceProvenance(
        source_id=source_id, observer_id="obs:file", observer_code_sha256=None,
        access_mode="read", source_kind=None, generated_at=generated_at,
    )
    return ds_core.SourceObservation(
        source_id=source_id, provenance=prov, dataset={"row_count": {"value": filas, "exactness": "exact"}}
    )


def _guardar(raiz, obs):
    directorio = Path(raiz) / ".harmessi" / "observations" / f"{obs.source_id}__{obs.content_sha256()[:12]}"
    directorio.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(obs.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    (directorio / "observation.json").write_bytes(texto.encode("utf-8"))
    return directorio


def _card(obs, ksv=2, temporality=None, time_scope=None, **cuerpo):
    pin = core.EvidenceRef("ev-src-a", "source_observation", f"clientes__{obs.content_sha256()[:12]}", obs.content_sha256(), T0)
    body = {
        "description": "Clientes",
        "source_refs": [{"source_ref_id": "src-a", "source_id": "clientes", "observation_evidence_id": "ev-src-a"}],
    }
    if temporality is not None:
        body["temporality"] = temporality
    if time_scope is not None:
        body["time_scope"] = time_scope
    body.update(cuerpo)
    return core.CardEnvelope(
        schema_version=1, card_kind="data_card", kind_schema_version=ksv, card_id="clientes-card",
        title="Data Card", subject="clientes-card", created_at=T0, generated_at=T0,
        evidence=(pin,),
        claims=(core.Claim("c-src-a", "Observada", supports=("ev-src-a",), requirement_id="source_src-a"),),
        body=body,
    )


def _codigos(card):
    return [h.code for h in datacard.validate_data_card(card)]


class TestValidacionTemporality(unittest.TestCase):
    def setUp(self):
        self.obs = _observacion(T0, 1)

    def test_v2_as_of_valida(self):
        card = _card(self.obs, temporality={"mode": "as_of"}, time_scope={"as_of": "2026-09-30"})
        self.assertEqual(_codigos(card), [])
        self.assertEqual(datacard.temporality_mode(card), "as_of")

    def test_v2_current_valida(self):
        card = _card(self.obs, temporality={"mode": "current"})
        self.assertEqual(_codigos(card), [])
        self.assertEqual(datacard.temporality_mode(card), "current")

    def test_v1_sin_temporality_es_current(self):
        card = _card(self.obs, ksv=1)
        self.assertEqual(_codigos(card), [])
        self.assertEqual(datacard.temporality_mode(card), "current")

    def test_v1_con_temporality_se_rechaza(self):
        card = _card(self.obs, ksv=1, temporality={"mode": "current"})
        self.assertIn(datacard.CODE_BODY_INVALID, _codigos(card))

    def test_v2_exige_temporality(self):
        self.assertIn(datacard.CODE_BODY_INVALID, _codigos(_card(self.obs)))

    def test_as_of_exige_time_scope_as_of(self):
        card = _card(self.obs, temporality={"mode": "as_of"})
        self.assertIn(datacard.CODE_BODY_INVALID, _codigos(card))
        card = _card(self.obs, temporality={"mode": "as_of"}, time_scope={"cutoff": "2026-09-30"})
        self.assertIn(datacard.CODE_BODY_INVALID, _codigos(card))

    def test_mode_invalido_y_clave_desconocida(self):
        self.assertIn(datacard.CODE_BODY_INVALID, _codigos(_card(self.obs, temporality={"mode": "historico"})))
        self.assertIn(datacard.CODE_UNKNOWN_KEY, _codigos(_card(self.obs, temporality={"mode": "current", "x": 1})))

    def test_version_futura_no_soportada(self):
        card = dataclasses.replace(_card(self.obs, temporality={"mode": "current"}), kind_schema_version=3)
        self.assertEqual(_codigos(card), [datacard.CODE_SCHEMA_UNSUPPORTED])


class TestEvaluacionAsOf(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name).resolve()
        self.vieja = _observacion("2026-09-01T00:00:00Z", 1)
        self.nueva = _observacion("2026-10-01T00:00:00Z", 2)
        self.dir_vieja = _guardar(self.repo, self.vieja)
        _guardar(self.repo, self.nueva)

    def evaluar(self, card):
        return datacard.evaluate_data_card(card, self.repo, clock=lambda: NOW)

    def _as_of(self, obs):
        return _card(obs, temporality={"mode": "as_of"}, time_scope={"as_of": "2026-09-15"})

    def test_current_pinneada_a_la_vieja_sigue_stale(self):
        ev = self.evaluar(_card(self.vieja, ksv=1))
        self.assertEqual(ev.card_status, assess.CARD_STALE)

    def test_as_of_pinneada_a_la_vieja_no_es_stale_e_informa_historica(self):
        ev = self.evaluar(self._as_of(self.vieja))
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)
        self.assertIn(datacard.CODE_AS_OF_HISTORICAL, [h.code for h in ev.hallazgos])

    def test_v2_current_pinneada_a_la_vieja_es_stale(self):
        card = _card(self.vieja, temporality={"mode": "current"})
        self.assertEqual(self.evaluar(card).card_status, assess.CARD_STALE)

    def test_as_of_es_declarativo_no_se_compara_con_la_fecha_de_la_observacion(self):
        # La observación pinneada se generó el 2026-09-01; un as_of ANTERIOR (2020-01-01)
        # no se rechaza ni se marca: as_of no se verifica contra generated_at (documentado).
        card = _card(self.vieja, temporality={"mode": "as_of"}, time_scope={"as_of": "2020-01-01"})
        self.assertEqual(_codigos(card), [])
        self.assertEqual(self.evaluar(card).card_status, assess.CARD_COMPLETE)

    def test_as_of_pinneada_a_la_vigente_no_informa_historica(self):
        ev = self.evaluar(self._as_of(self.nueva))
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)
        self.assertNotIn(datacard.CODE_AS_OF_HISTORICAL, [h.code for h in ev.hallazgos])

    def test_as_of_con_observacion_pinneada_alterada_es_stale(self):
        archivo = self.dir_vieja / "observation.json"
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        datos["dataset"]["row_count"]["value"] = 999
        archivo.write_text(json.dumps(datos), encoding="utf-8")
        ev = self.evaluar(self._as_of(self.vieja))
        self.assertEqual(ev.card_status, assess.CARD_STALE)

    def test_as_of_con_observacion_pinneada_desaparecida_no_es_complete(self):
        shutil.rmtree(self.dir_vieja)
        ev = self.evaluar(self._as_of(self.vieja))
        self.assertNotEqual(ev.card_status, assess.CARD_COMPLETE)
        self.assertNotEqual(ev.card_status, assess.CARD_INVALID)
        self.assertIn(assess.EV_UNRESOLVABLE, [estado for _eid, estado in ev.evidencias])

    def test_card_invalida_as_of_no_agrega_hallazgo_historico(self):
        card = _card(self.vieja, temporality={"mode": "as_of"})  # sin time_scope.as_of
        ev = self.evaluar(card)
        self.assertEqual(ev.card_status, assess.CARD_INVALID)
        self.assertNotIn(datacard.CODE_AS_OF_HISTORICAL, [h.code for h in ev.hallazgos])


class TestResolverPinneado(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name).resolve()

    def _ref(self, ref_id, obs):
        return core.EvidenceRef("ev1", "source_observation", ref_id, obs.content_sha256(), T0)

    def test_resuelve_el_directorio_exacto_aunque_haya_una_vigente_mas_nueva(self):
        vieja, nueva = _observacion("2026-09-01T00:00:00Z", 1), _observacion("2026-10-01T00:00:00Z", 2)
        _guardar(self.repo, vieja)
        _guardar(self.repo, nueva)
        ref = self._ref(f"clientes__{vieja.content_sha256()[:12]}", vieja)
        res = resolvers.source_observation_pinned_resolver(self.repo)(ref)
        self.assertEqual(res.state, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, vieja.content_sha256())
        self.assertEqual(resolvers.hash_observacion_vigente(self.repo, "clientes"), nueva.content_sha256())

    def test_provenance_pinneada_resuelve_el_directorio_exacto(self):
        vieja, nueva = _observacion("2026-09-01T00:00:00Z", 1), _observacion("2026-10-01T00:00:00Z", 2)
        _guardar(self.repo, vieja)
        _guardar(self.repo, nueva)
        hash_prov = resolvers.hash_provenance(vieja.to_dict())
        ref = core.EvidenceRef(
            "ev1", "source_provenance", f"clientes__{vieja.content_sha256()[:12]}", hash_prov, T0, member="provenance"
        )
        resolver = resolvers.source_provenance_pinned_resolver(self.repo)
        res = resolver(ref)
        self.assertEqual(res.state, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, hash_prov)
        # sin member='provenance' no es verificable (mismo contrato que el resolver vigente)
        sin_member = core.EvidenceRef("ev1", "source_provenance", ref.ref_id, hash_prov, T0)
        self.assertEqual(resolver(sin_member).state, assess.RES_UNVERIFIABLE)

    def test_ausente_es_missing_y_ref_hostil_no_es_verificable(self):
        obs = _observacion(T0, 1)
        res = resolvers.source_observation_pinned_resolver(self.repo)(self._ref(f"clientes__{'0' * 12}", obs))
        self.assertEqual(res.state, assess.RES_MISSING)
        res = resolvers.source_observation_pinned_resolver(self.repo)(self._ref("clientes__zz", obs))
        self.assertEqual(res.state, assess.RES_UNVERIFIABLE)

    def test_vigente_sin_observaciones_es_none(self):
        self.assertIsNone(resolvers.hash_observacion_vigente(self.repo, "clientes"))

    def test_default_resolvers_sigue_con_quince_kinds(self):
        self.assertEqual(set(resolvers.default_resolvers(self.repo)), set(core.OBSERVED_KINDS) - {"report_artifact"})


if __name__ == "__main__":
    unittest.main()
