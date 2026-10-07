"""Tests de `tools.cards.datacard` (Change `20261002-data-cards`, R5-R20, R33-R36).

Usan OBJETOS REALES de v0.8 (`datasources`), v0.6/v0.7 (`datacontracts`,
`qualityevidence`) construidos en directorios temporales; sin mocks.
"""
from __future__ import annotations

import ast
import copy
import dataclasses
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.cards import assess, core, datacard, resolvers
from tools.datacontracts import core as dc
from tools.datasources import core as ds
from tools.qualityevidence import core as qe_core
from tools.qualityevidence import evidence as qe_evidence

try:  # solo para documentar el comportamiento del runtime real de v0.8
    from tools.datasources import runtime as ds_runtime
except ImportError:  # pragma: no cover
    ds_runtime = None

T0 = "2026-10-01T10:00:00Z"
T1 = "2026-10-01T10:00:00Z"
T2 = "2026-10-02T10:00:00Z"
T3 = "2026-10-03T10:00:00Z"
NOW = "2026-10-04T00:00:00Z"
H0 = "0" * 64


# ---------------------------------------------------------------------------
# Fixtures con objetos reales
# ---------------------------------------------------------------------------


def codigo_de(funcion, *args, **kwargs):
    try:
        funcion(*args, **kwargs)
    except core.CardError as exc:
        return exc.code
    raise AssertionError("no lanzó CardError")


def hacer_obs(source_id="ventas", filas=10, generated_at=T1):
    """SourceObservation real mínima y válida."""
    prov = ds.SourceProvenance(
        source_id=source_id,
        observer_id="tests.observer:observar",
        observer_code_sha256=None,
        access_mode="read",
        source_kind=None,
        generated_at=generated_at,
    )
    return ds.SourceObservation(
        source_id=source_id,
        provenance=prov,
        dataset={"row_count": {"value": filas, "exactness": "exact"}},
        fields=(ds.FieldObservation("monto", "float", None),),
    )


def persistir_obs(raiz, obs):
    """Mismo layout y bytes que `tools/datasources/runtime.py::_persistir_observacion`
    (sin pasar por el runtime, que no es necesario): `.harmessi/observations/<id>__<hash12>/observation.json`."""
    h = obs.content_sha256()
    directorio = Path(raiz) / ".harmessi" / "observations" / f"{obs.source_id}__{h[:12]}"
    directorio.mkdir(parents=True, exist_ok=True)
    archivo = directorio / "observation.json"
    texto = json.dumps(obs.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    archivo.write_bytes(texto.encode("utf-8"))
    return archivo


def pin_de(obs, evidence_id):
    h = obs.content_sha256()
    return core.EvidenceRef(evidence_id, "source_observation", f"{obs.source_id}__{h[:12]}", h, T0)


def pin_provenance(obs, evidence_id):
    h = obs.content_sha256()
    return core.EvidenceRef(
        evidence_id,
        "source_provenance",
        f"{obs.source_id}__{h[:12]}",
        resolvers.hash_provenance(obs.to_dict()),
        T0,
        member="provenance",
    )


def fuente(sref, obs, eid=None, pin=None):
    eid = eid or "ev-" + sref
    return {"sref": sref, "source_id": obs.source_id, "pin": pin if pin is not None else pin_de(obs, eid)}


def armar_card(fuentes, con_claims=True, body_extra=None, evidence_extra=(), claims_extra=(), attestations=(), **kw):
    """Data Card con una `source_ref` por fuente y, opcionalmente, el claim
    `source_<sref>` que la soporta por su pin."""
    refs = [
        {
            "source_ref_id": f["sref"],
            "source_id": f["source_id"],
            "observation_evidence_id": f["pin"].evidence_id,
        }
        for f in fuentes
    ]
    body = {"description": "Producto de datos de prueba", "source_refs": refs}
    body.update(body_extra or {})
    claims = []
    if con_claims:
        claims = [
            core.Claim(
                "c-" + f["sref"],
                "La fuente fue observada",
                supports=(f["pin"].evidence_id,),
                requirement_id=datacard.requirement_id_for_source(f["sref"]),
            )
            for f in fuentes
        ]
    base = dict(
        schema_version=1,
        card_kind="data_card",
        kind_schema_version=1,
        card_id="producto-a",
        title="Data Card de prueba",
        subject="producto-a",
        created_at=T0,
        generated_at=T0,
        evidence=tuple(f["pin"] for f in fuentes) + tuple(evidence_extra),
        attestations=tuple(attestations),
        claims=tuple(claims) + tuple(claims_extra),
        body=body,
    )
    base.update(kw)
    return core.CardEnvelope(**base)


def hacer_att(**kw):
    base = dict(
        attestation_id="at-own",
        claim="El dueño del producto es el equipo de datos",
        actor="ana",
        authority="owner",
        attested_at=T0,
        scope="Propiedad del producto de datos",
        attestation_kind="declared",
    )
    base.update(kw)
    return core.HumanAttestation(**base)


def claim_ownership(supports=("at-own",)):
    return core.Claim("c-own", "Ownership declarado", supports=supports, requirement_id=datacard.REQ_OWNERSHIP)


def con_body(card, **cambios):
    body = copy.deepcopy(card.body)
    body.update(cambios)
    return dataclasses.replace(card, body=body)


def con_source_ref(card, **cambios):
    body = copy.deepcopy(card.body)
    body["source_refs"][0].update(cambios)
    return dataclasses.replace(card, body=body)


def codigos(card):
    return {h.code for h in datacard.validate_data_card(card)}


def estado_req(assessment, rid):
    for r in assessment.requisitos:
        if r[0] == rid:
            return r[2]
    raise AssertionError(f"requisito {rid} ausente")


def estado_ev(assessment, eid):
    return dict(assessment.evidencias)[eid]


def crear_contrato(raiz, descripcion="v1", version="1.0.0"):
    contrato = dc.DataContract(
        contract_id="mi-contrato",
        version=dc.ContractVersion(version=version),
        dataset_role="raw_table",
        fields=(dc.ContractField(name="monto", type_family="float"),),
        description=descripcion,
    )
    locator = "contratos/mi-contrato.json"
    ruta = Path(raiz) / locator
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(contrato.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return contrato, locator


def pin_contrato(contrato, locator, evidence_id="ev-ct"):
    return core.EvidenceRef(
        evidence_id,
        "harmessi_contract",
        f"{contrato.contract_id}@{contrato.version.version}",
        contrato.content_sha256(),
        T0,
        locator=locator,
    )


def card_con_contrato(contrato, locator, **kw):
    obs_f = fuente("src-a", hacer_obs())
    pin_ct = pin_contrato(contrato, locator)
    return armar_card(
        [obs_f],
        body_extra={
            "contract_refs": [
                {
                    "contract_id": contrato.contract_id,
                    "version": contrato.version.version,
                    "declaration_evidence_id": "ev-ct",
                }
            ]
        },
        evidence_extra=(pin_ct,),
        claims_extra=(
            core.Claim(
                "c-ct",
                "Contrato citado",
                supports=("ev-ct",),
                requirement_id=datacard.requirement_id_for_contract(contrato.contract_id),
            ),
        ),
        **kw,
    )


def crear_manifest(raiz, subject_kind="data_contract_evaluation", declaration_kind="data_contract", sufijo="abc123"):
    fuente_q = qe_evidence.describe_source_generated("conteo sintetico", {"n": 3})
    decl = qe_core.DeclarationRef(declaration_kind, "mi-contrato", "1.0.0", "a" * 64)
    manifest = qe_core.QualityEvidenceManifest(
        evidence_id=f"qe-20261001T100000Z-{sufijo}",
        subject_kind=subject_kind,
        declaration=decl,
        source=fuente_q,
        generated_at=T0,
    )
    ruta = qe_evidence.write_manifest(raiz, manifest)
    return manifest, Path(ruta)


def pin_manifest(manifest, kind="data_contract_result", evidence_id="ev-qe"):
    return core.EvidenceRef(evidence_id, kind, manifest.evidence_id, manifest.content_sha256(), T0)


class BaseTmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name).resolve()

    def evaluar(self, card):
        return datacard.evaluate_data_card(card, self.raiz)


# ---------------------------------------------------------------------------
# R1 -- frontera de imports de producción
# ---------------------------------------------------------------------------


class TestImportsProduccion(unittest.TestCase):
    PROHIBIDOS = {
        "datasources", "qualityevidence", "datacontracts", "modelquality",
        "autonomy", "leadrun", "reporting", "ds_init", "dsguard",
    }

    def _nombres(self, nombre_archivo):
        ruta = os.path.join(os.path.dirname(__file__), "..", nombre_archivo)
        with open(ruta, "r", encoding="utf-8") as f:
            arbol = ast.parse(f.read(), filename=nombre_archivo)
        nombres = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                nombres.update(a.name for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom):
                nombres.add(nodo.module or "")
                nombres.update(a.name for a in nodo.names)
        return {parte for n in nombres for parte in n.split(".")}

    def test_datacard_y_resolvers_no_importan_paquetes_hermanos(self):
        for archivo in ("datacard.py", "resolvers.py"):
            with self.subTest(archivo=archivo):
                self.assertFalse(self._nombres(archivo) & self.PROHIBIDOS)


# ---------------------------------------------------------------------------
# Paridad de hashes con los objetos reales (R18, R21, R22, R23)
# ---------------------------------------------------------------------------


class TestParidadHashes(BaseTmp):
    def test_hash_observation_y_provenance(self):
        obs = hacer_obs()
        self.assertEqual(resolvers.hash_observation(obs.to_dict()), obs.content_sha256())
        # no depende de generated_at
        otra = hacer_obs(generated_at=T3)
        self.assertEqual(resolvers.hash_observation(otra.to_dict()), obs.content_sha256())
        self.assertEqual(resolvers.hash_provenance(obs.to_dict()), resolvers.hash_provenance(otra.to_dict()))

    def test_hash_contract(self):
        contrato, _ = crear_contrato(self.raiz)
        self.assertEqual(resolvers.hash_contract(contrato.to_dict()), contrato.content_sha256())

    def test_hash_quality_manifest(self):
        manifest, _ = crear_manifest(self.raiz)
        self.assertEqual(resolvers.hash_quality_manifest(manifest.to_dict()), manifest.content_sha256())


# ---------------------------------------------------------------------------
# Completitud con fuentes reales (R15, R16, R19, R20, R36)
# ---------------------------------------------------------------------------


class TestCompletitudFuentes(BaseTmp):
    def test_una_fuente_observada_es_complete_y_ownership_ausente_es_warn(self):
        obs = hacer_obs()
        persistir_obs(self.raiz, obs)
        card = armar_card([fuente("src-a", obs)])
        self.assertEqual(datacard.validate_data_card(card), [])
        ev = self.evaluar(card)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)
        self.assertEqual(estado_req(ev, "source_src-a"), assess.REQ_SATISFIED)
        self.assertEqual(estado_req(ev, datacard.REQ_OWNERSHIP), assess.REQ_MISSING)
        self.assertEqual(estado_ev(ev, "ev-src-a"), assess.EV_FRESH)
        res = assess.a_check_results(ev)
        advertencias = [r for r in res if r.status == "WARN" and datacard.REQ_OWNERSHIP in r.message]
        self.assertEqual(len(advertencias), 1)
        self.assertEqual(advertencias[0].code, core.CODE_REQUIREMENT_MISSING)
        self.assertNotIn("FAIL", [r.status for r in res])
        self.assertIn("PASS", [r.status for r in res])

    def test_tres_fuentes_una_sin_observacion_es_incomplete(self):
        oa, ob, oc = hacer_obs("ventas"), hacer_obs("clientes"), hacer_obs("pagos")
        persistir_obs(self.raiz, oa)
        persistir_obs(self.raiz, ob)  # oc NO se persiste
        card = armar_card([fuente("src-a", oa), fuente("src-b", ob), fuente("src-c", oc)])
        ev = self.evaluar(card)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)
        self.assertEqual(estado_req(ev, "source_src-a"), assess.REQ_SATISFIED)
        self.assertEqual(estado_req(ev, "source_src-b"), assess.REQ_SATISFIED)
        self.assertEqual(estado_req(ev, "source_src-c"), assess.REQ_UNRESOLVABLE)
        self.assertEqual(estado_ev(ev, "ev-src-c"), assess.EV_UNRESOLVABLE)
        fallos = [r for r in assess.a_check_results(ev) if r.status == "FAIL"]
        self.assertEqual([r.code for r in fallos], [core.CODE_REQUIREMENT_UNRESOLVABLE])
        self.assertIn("source_src-c", fallos[0].message)

    def test_observacion_inexistente_sin_directorio_es_missing_e_incomplete(self):
        obs = hacer_obs()  # nunca persistida; ni siquiera existe .harmessi/
        ev = self.evaluar(armar_card([fuente("src-a", obs)]))
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)
        self.assertEqual(estado_ev(ev, "ev-src-a"), assess.EV_UNRESOLVABLE)

    def test_mismo_source_id_dos_veces_con_source_ref_id_distinto(self):
        obs = hacer_obs()
        persistir_obs(self.raiz, obs)
        f1 = fuente("ventas-2025", obs, "ev-v25")
        f2 = fuente("ventas-2026", obs, "ev-v26")
        card = armar_card([f1, f2])
        card = dataclasses.replace(
            card,
            body={
                **card.body,
                "source_refs": [
                    {**card.body["source_refs"][0], "time_scope": {"period_start": "2025-01-01", "period_end": "2025-12-31"}},
                    {**card.body["source_refs"][1], "time_scope": {"period_start": "2026-01-01"}},
                ],
            },
        )
        self.assertEqual(datacard.validate_data_card(card), [])
        ev = self.evaluar(card)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)
        self.assertEqual(estado_req(ev, "source_ventas-2025"), assess.REQ_SATISFIED)
        self.assertEqual(estado_req(ev, "source_ventas-2026"), assess.REQ_SATISFIED)

    def test_source_ref_id_duplicado_es_inconsistente(self):
        obs = hacer_obs()
        card = armar_card([fuente("src-a", obs, "ev-1"), fuente("src-a", obs, "ev-2")], con_claims=False)
        self.assertIn(datacard.CODE_SOURCE_REF_INCONSISTENT, codigos(card))

    def test_reobservacion_con_contenido_distinto_deja_stale_la_fuente_y_la_card(self):
        v1, v2 = hacer_obs("ventas", 10, T1), hacer_obs("ventas", 11, T2)
        otra = hacer_obs("clientes")
        persistir_obs(self.raiz, v1)
        persistir_obs(self.raiz, otra)
        card = armar_card([fuente("src-a", v1), fuente("src-b", otra)])
        self.assertEqual(self.evaluar(card).card_status, assess.CARD_COMPLETE)
        persistir_obs(self.raiz, v2)  # re-observación con contenido distinto
        self.assertNotEqual(v1.content_sha256(), v2.content_sha256())
        ev = self.evaluar(card)
        self.assertEqual(estado_ev(ev, "ev-src-a"), assess.EV_STALE)
        self.assertEqual(estado_ev(ev, "ev-src-b"), assess.EV_FRESH)
        self.assertEqual(estado_req(ev, "source_src-a"), assess.REQ_STALE)
        self.assertEqual(estado_req(ev, "source_src-b"), assess.REQ_SATISFIED)
        self.assertEqual(ev.card_status, assess.CARD_STALE)
        codigos_chk = [(r.status, r.code) for r in assess.a_check_results(ev)]
        self.assertIn(("FAIL", core.CODE_REQUIREMENT_STALE), codigos_chk)
        self.assertIn(("WARN", core.CODE_EVIDENCE_STALE), codigos_chk)

    def test_reobservacion_identica_sigue_fresh(self):
        v1 = hacer_obs("ventas", 10, T1)
        persistir_obs(self.raiz, v1)
        card = armar_card([fuente("src-a", v1)])
        v1b = hacer_obs("ventas", 10, T3)  # mismo contenido, otro generated_at
        self.assertEqual(v1.content_sha256(), v1b.content_sha256())
        persistir_obs(self.raiz, v1b)  # mismo id/directorio
        ev = self.evaluar(card)
        self.assertEqual(estado_ev(ev, "ev-src-a"), assess.EV_FRESH)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_pin_con_hash_distinto_al_vigente_es_stale(self):
        # Pin COHERENTE (ref_id = <source_id>__<hash[:12]>) de una observación vieja
        # real; la vigente (más reciente) tiene otro contenido -> stale, no inconsistente.
        vieja = hacer_obs("ventas", 10, T1)
        vigente = hacer_obs("ventas", 11, T2)
        persistir_obs(self.raiz, vieja)
        persistir_obs(self.raiz, vigente)
        pin = pin_de(vieja, "ev-src-a")
        self.assertEqual(pin.ref_id, f"ventas__{pin.content_sha256[:12]}")
        card = armar_card([fuente("src-a", vieja, pin=pin)])
        self.assertEqual(datacard.validate_data_card(card), [])
        ev = self.evaluar(card)
        self.assertEqual(estado_ev(ev, "ev-src-a"), assess.EV_STALE)
        self.assertEqual(ev.card_status, assess.CARD_STALE)

    def test_observacion_adulterada_no_es_fresh(self):
        obs = hacer_obs()
        archivo = persistir_obs(self.raiz, obs)
        card = armar_card([fuente("src-a", obs)])
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        datos["dataset"]["row_count"]["value"] = 999
        archivo.write_text(json.dumps(datos), encoding="utf-8")
        ev = self.evaluar(card)
        self.assertIn(estado_ev(ev, "ev-src-a"), (assess.EV_STALE, assess.EV_UNVERIFIABLE))
        self.assertNotEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_observacion_ilegible_o_con_source_id_interno_distinto_es_unverifiable(self):
        obs = hacer_obs()
        archivo = persistir_obs(self.raiz, obs)
        card = armar_card([fuente("src-a", obs)])
        # source_id interno distinto del directorio
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        datos["source_id"] = "otra"
        archivo.write_text(json.dumps(datos), encoding="utf-8")
        self.assertEqual(estado_ev(self.evaluar(card), "ev-src-a"), assess.EV_UNVERIFIABLE)
        # JSON roto
        archivo.write_text("{no es json", encoding="utf-8")
        self.assertEqual(estado_ev(self.evaluar(card), "ev-src-a"), assess.EV_UNVERIFIABLE)
        # directorio sin observation.json
        archivo.unlink()
        self.assertEqual(estado_ev(self.evaluar(card), "ev-src-a"), assess.EV_UNVERIFIABLE)

    def test_pin_de_provenance_fresh_y_sin_member_unverifiable(self):
        obs = hacer_obs()
        persistir_obs(self.raiz, obs)
        pin_p = pin_provenance(obs, "ev-prov")
        card = armar_card([fuente("src-a", obs)], evidence_extra=(pin_p,))
        card = con_source_ref(card, provenance_evidence_id="ev-prov")
        self.assertEqual(datacard.validate_data_card(card), [])
        self.assertEqual(estado_ev(self.evaluar(card), "ev-prov"), assess.EV_FRESH)
        sin_member = dataclasses.replace(pin_p, member=None)
        card2 = armar_card([fuente("src-a", obs)], evidence_extra=(sin_member,))
        card2 = con_source_ref(card2, provenance_evidence_id="ev-prov")
        self.assertEqual(estado_ev(self.evaluar(card2), "ev-prov"), assess.EV_UNVERIFIABLE)

    def test_resolvers_nunca_lanzan_y_rechazan_ids_con_componentes_de_ruta(self):
        mapa = resolvers.default_resolvers(self.raiz)
        # Conjunto vigente: todos los kinds observados salvo report_artifact (sin resolver)
        self.assertEqual(set(mapa), set(core.OBSERVED_KINDS) - {"report_artifact"})
        for kind, resolver in mapa.items():
            with self.subTest(kind=kind, basura="None"):
                self.assertEqual(resolver(None).state, assess.RES_UNVERIFIABLE)
        ref = core.EvidenceRef("ev-x", "source_observation", "..__aaaaaaaaaaaa", H0, T0)
        self.assertEqual(mapa["source_observation"](ref).state, assess.RES_UNVERIFIABLE)


# ---------------------------------------------------------------------------
# Contratos y evidencia de calidad reales (R22, R23)
# ---------------------------------------------------------------------------


class TestContratoYCalidad(BaseTmp):
    def setUp(self):
        super().setUp()
        self.obs = hacer_obs()
        persistir_obs(self.raiz, self.obs)

    def test_contrato_real_fresh(self):
        contrato, locator = crear_contrato(self.raiz)
        card = card_con_contrato(contrato, locator)
        self.assertEqual(datacard.validate_data_card(card), [])
        ev = self.evaluar(card)
        rid = datacard.requirement_id_for_contract("mi-contrato")
        self.assertEqual(estado_ev(ev, "ev-ct"), assess.EV_FRESH)
        self.assertEqual(estado_req(ev, rid), assess.REQ_SATISFIED)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_contrato_modificado_es_stale(self):
        contrato, locator = crear_contrato(self.raiz)
        card = card_con_contrato(contrato, locator)
        crear_contrato(self.raiz, descripcion="v1 editado")
        ev = self.evaluar(card)
        rid = datacard.requirement_id_for_contract("mi-contrato")
        self.assertEqual(estado_ev(ev, "ev-ct"), assess.EV_STALE)
        self.assertEqual(estado_req(ev, rid), assess.REQ_STALE)
        # el requisito de contrato es recommended: no bloquea ni vuelve stale la Card
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)
        self.assertIn(("WARN", core.CODE_EVIDENCE_STALE), [(r.status, r.code) for r in assess.a_check_results(ev)])

    def test_contrato_ausente_es_unresolvable(self):
        contrato, locator = crear_contrato(self.raiz)
        card = card_con_contrato(contrato, locator)
        (self.raiz / locator).unlink()
        self.assertEqual(estado_ev(self.evaluar(card), "ev-ct"), assess.EV_UNRESOLVABLE)

    def test_contrato_cuyo_contenido_no_coincide_con_ref_id_es_unverifiable(self):
        contrato, locator = crear_contrato(self.raiz)
        card = card_con_contrato(contrato, locator)
        crear_contrato(self.raiz, version="2.0.0")  # el archivo ahora declara 2.0.0
        self.assertEqual(estado_ev(self.evaluar(card), "ev-ct"), assess.EV_UNVERIFIABLE)

    def test_contract_ref_con_declaracion_inconsistente(self):
        contrato, locator = crear_contrato(self.raiz)
        card = card_con_contrato(contrato, locator)
        malo = dataclasses.replace(
            card,
            evidence=tuple(
                dataclasses.replace(e, ref_id="mi-contrato@2.0.0") if e.evidence_id == "ev-ct" else e
                for e in card.evidence
            ),
        )
        self.assertIn(datacard.CODE_CONTRACT_REF_INCONSISTENT, codigos(malo))
        self.assertEqual(self.evaluar(malo).card_status, assess.CARD_INVALID)

    def test_manifest_real_fresh(self):
        manifest, _ = crear_manifest(self.raiz)
        contrato, locator = crear_contrato(self.raiz)
        card = card_con_contrato(contrato, locator)
        card = dataclasses.replace(
            card,
            evidence=card.evidence + (pin_manifest(manifest),),
            body={
                **card.body,
                "contract_refs": [{**card.body["contract_refs"][0], "result_evidence_ids": ["ev-qe"]}],
            },
        )
        self.assertEqual(datacard.validate_data_card(card), [])
        ev = self.evaluar(card)
        self.assertEqual(estado_ev(ev, "ev-qe"), assess.EV_FRESH)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_manifest_inexistente_es_unresolvable(self):
        manifest, ruta = crear_manifest(self.raiz)
        pin = pin_manifest(manifest)
        ruta.unlink()
        ev = self.evaluar(self._card_manifest_simple(pin))
        self.assertEqual(estado_ev(ev, "ev-qe"), assess.EV_UNRESOLVABLE)

    def _card_manifest_simple(self, pin):
        """Card que solo cita el manifest como `quality_evidence_ids`/claim de contrato."""
        body_extra = {}
        con_claim = pin.kind != "quality_evidence"
        if pin.kind == "quality_evidence":
            body_extra["quality_evidence_ids"] = [pin.evidence_id]
        contrato, locator = crear_contrato(self.raiz)
        pin_ct = pin_contrato(contrato, locator)
        if pin.kind == "data_contract_result":
            body_extra["contract_refs"] = [
                {"contract_id": "mi-contrato", "version": "1.0.0", "declaration_evidence_id": "ev-ct", "result_evidence_ids": [pin.evidence_id]}
            ]
        else:
            body_extra["contract_refs"] = [
                {"contract_id": "mi-contrato", "version": "1.0.0", "declaration_evidence_id": "ev-ct"}
            ]
        # Un claim `contract_<id>` solo puede apoyarse en la declaración y los
        # resultados de sus contract_refs (B1): un `quality_evidence_ids` suelto
        # NO puede ser soporte de ese claim, así que en ese caso no se arma claim
        # (el estado por evidencia se evalúa igual: `assess` evalúa todo card.evidence).
        claims_extra = ()
        if con_claim:
            claims_extra = (
                core.Claim(
                    "c-qe",
                    "Resultado de calidad",
                    supports=(pin.evidence_id,),
                    requirement_id=datacard.requirement_id_for_contract("mi-contrato"),
                ),
            )
        return armar_card(
            [fuente("src-a", self.obs)],
            body_extra=body_extra,
            evidence_extra=(pin_ct, pin),
            claims_extra=claims_extra,
        )

    def test_manifest_adulterado_es_unverifiable(self):
        manifest, ruta = crear_manifest(self.raiz)
        pin = pin_manifest(manifest)
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["scope"]["population"] = "poblacion adulterada"  # content_sha256 persistido queda viejo
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        ev = self.evaluar(self._card_manifest_simple(pin))
        self.assertEqual(estado_ev(ev, "ev-qe"), assess.EV_UNVERIFIABLE)
        self.assertEqual(
            estado_req(ev, datacard.requirement_id_for_contract("mi-contrato")), assess.REQ_UNVERIFIABLE
        )

    def test_subject_kind_incorrecto_para_data_contract_result_es_unverifiable(self):
        manifest, _ = crear_manifest(
            self.raiz, subject_kind="model_quality_evaluation", declaration_kind="model_quality_policy", sufijo="def456"
        )
        # como data_contract_result: exige subject data_contract_evaluation
        pin_dcr = pin_manifest(manifest, kind="data_contract_result")
        ev = self.evaluar(self._card_manifest_simple(pin_dcr))
        self.assertEqual(estado_ev(ev, "ev-qe"), assess.EV_UNVERIFIABLE)
        # como quality_evidence genérico el mismo manifest es válido
        pin_qe = pin_manifest(manifest, kind="quality_evidence")
        ev = self.evaluar(self._card_manifest_simple(pin_qe))
        self.assertEqual(estado_ev(ev, "ev-qe"), assess.EV_FRESH)

    def test_quality_evidence_ids_con_kind_incorrecto_es_invalido(self):
        manifest, _ = crear_manifest(self.raiz)
        pin = pin_manifest(manifest, kind="data_contract_result")
        card = armar_card([fuente("src-a", self.obs)], body_extra={"quality_evidence_ids": ["ev-qe"]}, evidence_extra=(pin,))
        self.assertIn(datacard.CODE_BODY_INVALID, codigos(card))


# ---------------------------------------------------------------------------
# Atestaciones (R11, R17, R39)
# ---------------------------------------------------------------------------


class TestAtestaciones(BaseTmp):
    def setUp(self):
        super().setUp()
        self.obs = hacer_obs()
        persistir_obs(self.raiz, self.obs)

    def test_solo_atestacion_no_satisface_requisito_de_fuente(self):
        f = fuente("src-a", self.obs)
        claim = core.Claim(
            "c-src-a", "Afirmo que la fuente existe", supports=("at-own",),
            requirement_id=datacard.requirement_id_for_source("src-a"),
        )
        card = armar_card([f], con_claims=False, attestations=(hacer_att(),), claims_extra=(claim,))
        # Foundation sola (sin el hook de body de datacard): una atestación no
        # satisface un requisito empírico (observed-only). El camino datacard,
        # donde este mismo claim es inválido por B1, se fija en
        # `test_claim_source_solo_con_atestacion_es_invalido_por_datacard`.
        ev = assess.evaluate(
            card, datacard.requirements_for(card), resolvers.default_resolvers(self.raiz), lambda: NOW,
            validate_body=lambda body: [],  # hook permisivo: aísla la regla de Foundation
        )
        self.assertEqual(estado_req(ev, "source_src-a"), assess.REQ_UNTRUSTED_TYPE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)
        self.assertEqual(
            [r.code for r in assess.a_check_results(ev) if r.status == "FAIL"],
            [core.CODE_REQUIREMENT_UNTRUSTED_TYPE],
        )

    def test_solo_atestacion_no_satisface_requisito_de_contrato(self):
        contrato, locator = crear_contrato(self.raiz)
        card = card_con_contrato(contrato, locator)
        rid = datacard.requirement_id_for_contract("mi-contrato")
        claims = tuple(c for c in card.claims if c.requirement_id != rid) + (
            core.Claim("c-ct", "Afirmo el contrato", supports=("at-own",), requirement_id=rid),
        )
        card = dataclasses.replace(card, claims=claims, attestations=(hacer_att(),))
        # Foundation sola (sin el hook de body): la atestación no satisface un
        # requisito empírico. El camino datacard se fija en
        # `test_claim_contract_solo_con_atestacion_es_invalido_por_datacard`.
        ev = assess.evaluate(
            card, datacard.requirements_for(card), resolvers.default_resolvers(self.raiz), lambda: NOW,
            validate_body=lambda body: [],  # hook permisivo: aísla la regla de Foundation
        )
        self.assertEqual(estado_req(ev, rid), assess.REQ_UNTRUSTED_TYPE)

    def test_claim_source_solo_con_atestacion_es_invalido_por_datacard(self):
        f = fuente("src-a", self.obs)
        claim = core.Claim(
            "c-src-a", "Afirmo que la fuente existe", supports=("at-own",),
            requirement_id=datacard.requirement_id_for_source("src-a"),
        )
        card = armar_card([f], con_claims=False, attestations=(hacer_att(),), claims_extra=(claim,))
        self.assertIn(datacard.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(card))
        ev = self.evaluar(card)
        self.assertEqual(ev.card_status, assess.CARD_INVALID)
        self.assertIn(datacard.CODE_CLAIM_SUPPORT_INCONSISTENT, {h.code for h in ev.hallazgos})

    def test_claim_contract_solo_con_atestacion_es_invalido_por_datacard(self):
        contrato, locator = crear_contrato(self.raiz)
        card = card_con_contrato(contrato, locator)
        rid = datacard.requirement_id_for_contract("mi-contrato")
        claims = tuple(c for c in card.claims if c.requirement_id != rid) + (
            core.Claim("c-ct", "Afirmo el contrato", supports=("at-own",), requirement_id=rid),
        )
        card = dataclasses.replace(card, claims=claims, attestations=(hacer_att(),))
        self.assertIn(datacard.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(card))
        ev = self.evaluar(card)
        self.assertEqual(ev.card_status, assess.CARD_INVALID)
        self.assertIn(datacard.CODE_CLAIM_SUPPORT_INCONSISTENT, {h.code for h in ev.hallazgos})

    def test_ownership_con_atestacion_declared_satisface(self):
        card = armar_card(
            [fuente("src-a", self.obs)], attestations=(hacer_att(),), claims_extra=(claim_ownership(),)
        )
        ev = self.evaluar(card)
        self.assertEqual(estado_req(ev, datacard.REQ_OWNERSHIP), assess.REQ_SATISFIED)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)
        res = assess.a_check_results(ev)
        self.assertFalse([r for r in res if r.status in ("WARN", "FAIL")])

    def test_ownership_con_atestacion_anchored_estructural_satisface_sin_afirmar_verificacion(self):
        anclada = hacer_att(
            attestation_kind="anchored",
            approval_ref={"change_id": "20261002-data-cards", "artefacto": "spec.md", "hash": "a" * 64},
        )
        card = armar_card([fuente("src-a", self.obs)], attestations=(anclada,), claims_extra=(claim_ownership(),))
        ev = self.evaluar(card)
        self.assertEqual(estado_req(ev, datacard.REQ_OWNERSHIP), assess.REQ_SATISFIED)
        for r in assess.a_check_results(ev):
            texto = f"{r.message} {r.detail or ''}".lower()
            self.assertNotIn("verified", texto)
            self.assertNotIn("verificad", texto)

    def test_evidencia_observada_no_satisface_ownership(self):
        f = fuente("src-a", self.obs)
        claim = core.Claim("c-own", "Ownership por observación", supports=("ev-src-a",), requirement_id=datacard.REQ_OWNERSHIP)
        ev = self.evaluar(armar_card([f], claims_extra=(claim,)))
        self.assertEqual(estado_req(ev, datacard.REQ_OWNERSHIP), assess.REQ_UNTRUSTED_TYPE)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)  # recommended no bloquea


# ---------------------------------------------------------------------------
# Revisión de la Card (R5, R31)
# ---------------------------------------------------------------------------


class TestRevision(BaseTmp):
    def test_dos_revisiones_mismo_pin_distinto_revision_id(self):
        obs = hacer_obs()
        persistir_obs(self.raiz, obs)
        a = armar_card([fuente("src-a", obs)])
        b = con_body(a, description="Descripción revisada del producto")
        self.assertEqual(a.card_id, b.card_id)
        self.assertEqual(a.evidence, b.evidence)
        self.assertNotEqual(a.revision_id(), b.revision_id())
        self.assertTrue(a.revision_id().startswith("producto-a__"))
        self.assertEqual(self.evaluar(a).card_status, assess.CARD_COMPLETE)
        self.assertEqual(self.evaluar(b).card_status, assess.CARD_COMPLETE)


# ---------------------------------------------------------------------------
# Validación del body (R6-R14, R35)
# ---------------------------------------------------------------------------


class TestBodyInvalido(BaseTmp):
    def setUp(self):
        super().setUp()
        self.obs = hacer_obs()
        persistir_obs(self.raiz, self.obs)
        self.card = armar_card([fuente("src-a", self.obs)])

    def _invalida(self, card, codigo):
        self.assertIn(codigo, codigos(card))
        ev = self.evaluar(card)
        self.assertEqual(ev.card_status, assess.CARD_INVALID)
        self.assertIn(codigo, [h.code for h in ev.hallazgos])

    def test_card_base_es_valida(self):
        self.assertEqual(datacard.validate_data_card(self.card), [])

    def test_clave_desconocida(self):
        self._invalida(con_body(self.card, inventada=1), datacard.CODE_UNKNOWN_KEY)

    def test_clave_desconocida_anidada(self):
        self._invalida(con_source_ref(self.card, inventada=1), datacard.CODE_UNKNOWN_KEY)

    def test_extensiones_x_permitidas(self):
        card = con_body(self.card, x_nota="libre")
        card = con_source_ref(card, x_otro={"a": 1})
        self.assertEqual(datacard.validate_data_card(card), [])
        self.assertEqual(self.evaluar(card).card_status, assess.CARD_COMPLETE)

    def test_description_vacia_o_ausente(self):
        self._invalida(con_body(self.card, description=""), datacard.CODE_BODY_INVALID)
        self._invalida(con_body(self.card, description="   "), datacard.CODE_BODY_INVALID)
        body = copy.deepcopy(self.card.body)
        del body["description"]
        self._invalida(dataclasses.replace(self.card, body=body), datacard.CODE_BODY_INVALID)

    def test_source_refs_vacia_o_mal_formada(self):
        self._invalida(con_body(self.card, source_refs=[]), datacard.CODE_BODY_INVALID)
        self._invalida(con_body(self.card, source_refs="x"), datacard.CODE_BODY_INVALID)
        self._invalida(con_body(self.card, source_refs=["x"]), datacard.CODE_BODY_INVALID)

    def test_kind_schema_version_ajeno(self):
        card = dataclasses.replace(self.card, kind_schema_version=2)
        self._invalida(card, datacard.CODE_SCHEMA_UNSUPPORTED)

    def test_card_kind_ajeno(self):
        card = dataclasses.replace(self.card, card_kind="model_card")
        self._invalida(card, datacard.CODE_KIND_INVALID)

    def test_evidencia_colgante(self):
        self._invalida(con_source_ref(self.card, observation_evidence_id="no-existe"), datacard.CODE_DANGLING_EVIDENCE)
        self._invalida(con_source_ref(self.card, provenance_evidence_id="no-existe"), datacard.CODE_DANGLING_EVIDENCE)

    def test_evidencia_de_kind_incorrecto(self):
        manifest, _ = crear_manifest(self.raiz)
        pin = pin_manifest(manifest, kind="quality_evidence")
        card = dataclasses.replace(self.card, evidence=self.card.evidence + (pin,))
        card = con_source_ref(card, observation_evidence_id="ev-qe")
        self._invalida(card, datacard.CODE_SOURCE_REF_INCONSISTENT)

    def test_ref_id_que_no_empieza_con_source_id(self):
        pin = core.EvidenceRef("ev-src-a", "source_observation", "otra__aaaaaaaaaaaa", H0, T0)
        card = armar_card([fuente("src-a", self.obs, pin=pin)])
        self._invalida(card, datacard.CODE_SOURCE_REF_INCONSISTENT)

    def test_stewardship_valido_y_con_arroba_rechazado(self):
        ok = con_body(self.card, stewardship={"owner": "Equipo de Datos", "steward": "Gobierno de Datos"})
        self.assertEqual(datacard.validate_data_card(ok), [])
        for malo in (
            {"owner": "ana@empresa.com"},
            {"owner": "Equipo", "steward": "ana@empresa.com"},
        ):
            with self.subTest(stewardship=malo):
                self._invalida(con_body(self.card, stewardship=malo), datacard.CODE_BODY_INVALID)
        self._invalida(con_body(self.card, stewardship={"steward": "Equipo"}), datacard.CODE_BODY_INVALID)

    def test_rutas_fisicas_en_source_id_y_role(self):
        rutas = ("C:\\datos\\x.csv", "/srv/datos", "a\\b", "postgres://user:clave@host/db", "~/datos", "../x")
        for ruta in rutas:
            with self.subTest(ruta=ruta, campo="source_id"):
                self.assertTrue(datacard.validate_data_card(con_source_ref(self.card, source_id=ruta)))
            with self.subTest(ruta=ruta, campo="role"):
                self.assertTrue(datacard.validate_data_card(con_source_ref(self.card, role=ruta)))
        self.assertEqual(datacard.validate_data_card(con_source_ref(self.card, role="primary")), [])

    def test_rutas_fisicas_en_locator_de_pins(self):
        for locator in ("C:\\datos\\x.csv", "/srv/datos", "a\\b", "postgres://user:clave@host/db", "../x"):
            with self.subTest(locator=locator):
                self.assertEqual(
                    codigo_de(core.EvidenceRef, "ev-x", "report_artifact", "ref", H0, T0, locator=locator),
                    core.CODE_LOCATOR_NOT_PORTABLE,
                )

    def test_rutas_fisicas_en_textos_del_body(self):
        for ruta in ("C:\\datos\\x.csv", "/srv/datos", "\\\\srv\\share", "postgres://user:clave@host/db"):
            with self.subTest(ruta=ruta):
                card = con_body(self.card, description=ruta)
                self.assertEqual(codigos(card), {core.CODE_LOCATOR_NOT_PORTABLE})
                self.assertEqual(self.evaluar(card).card_status, assess.CARD_INVALID)
        # también en listas descriptivas y subject
        self.assertTrue(datacard.validate_data_card(con_body(self.card, known_limitations=["ver C:\\x\\y"])))
        self.assertEqual(
            codigo_de(armar_card, [fuente("src-a", self.obs)], subject="C:\\x"), core.CODE_LOCATOR_NOT_PORTABLE
        )

    def test_time_scope_y_semver(self):
        ok = con_body(self.card, time_scope={"as_of": "2026-01-01", "period_start": "2026-01-01T00:00:00Z"})
        self.assertEqual(datacard.validate_data_card(ok), [])
        self._invalida(con_body(self.card, time_scope={"as_of": "ayer"}), datacard.CODE_BODY_INVALID)
        self._invalida(con_body(self.card, time_scope={"otra": "2026-01-01"}), datacard.CODE_UNKNOWN_KEY)
        malo = con_body(self.card, contract_refs=[{"contract_id": "c", "version": "1.0", "declaration_evidence_id": "ev-src-a"}])
        self.assertIn(datacard.CODE_BODY_INVALID, codigos(malo))

    def test_listas_descriptivas(self):
        ok = con_body(self.card, intended_uses=["reporting"], out_of_scope_uses=["scoring"], known_limitations=["sin 2024"])
        self.assertEqual(datacard.validate_data_card(ok), [])
        self._invalida(con_body(self.card, intended_uses=[""]), datacard.CODE_BODY_INVALID)
        self._invalida(con_body(self.card, known_limitations="texto"), datacard.CODE_BODY_INVALID)

    def test_validate_data_card_con_no_card_no_lanza(self):
        for valor in (None, {}, "x", 5):
            with self.subTest(valor=valor):
                self.assertTrue(datacard.validate_data_card(valor))

    def test_body_validator_for_es_fail_closed(self):
        validador = datacard.body_validator_for(self.card)
        self.assertEqual(validador(self.card.body), [])
        for body in (None, "x", [], 5):
            with self.subTest(body=body):
                self.assertTrue(validador(body))
        self.assertTrue(datacard.body_validator_for(None)({}))


# ---------------------------------------------------------------------------
# Requisitos derivados y no persistidos (R15, R16)
# ---------------------------------------------------------------------------


class TestRequisitosDerivados(BaseTmp):
    def test_requirements_for_deriva_de_las_fuentes_y_contratos(self):
        oa, ob = hacer_obs("ventas"), hacer_obs("clientes")
        contrato, locator = crear_contrato(self.raiz)
        card = card_con_contrato(contrato, locator)
        card = armar_card(
            [fuente("src-a", oa), fuente("src-b", ob)],
            body_extra={"contract_refs": card.body["contract_refs"]},
            evidence_extra=(pin_contrato(contrato, locator),),
        )
        reqs = {r.requirement_id: r for r in datacard.requirements_for(card)}
        self.assertEqual(set(reqs), {"source_src-a", "source_src-b", "ownership", "contract_mi-contrato"})
        for rid in ("source_src-a", "source_src-b"):
            self.assertEqual(reqs[rid].severity, "required")
            self.assertEqual(reqs[rid].accepts, ("observed",))
            self.assertEqual(reqs[rid].accepted_kinds, ("source_observation",))
        self.assertEqual(reqs["ownership"].severity, "recommended")
        self.assertEqual(reqs["ownership"].accepts, ("attestation",))
        self.assertEqual(reqs["ownership"].min_attestation_kind, "declared")
        self.assertEqual(reqs["contract_mi-contrato"].severity, "recommended")
        self.assertEqual(reqs["contract_mi-contrato"].accepts, ("observed",))
        self.assertEqual(
            reqs["contract_mi-contrato"].accepted_kinds,
            ("harmessi_contract", "data_contract_result", "quality_evidence"),
        )

    def test_requirements_for_sin_contratos_no_incluye_contract(self):
        card = armar_card([fuente("src-a", hacer_obs())])
        ids = {r.requirement_id for r in datacard.requirements_for(card)}
        self.assertEqual(ids, {"source_src-a", "ownership"})

    def test_requirements_for_ignora_items_malformados_y_rechaza_no_cards(self):
        card = con_body(armar_card([fuente("src-a", hacer_obs())]), source_refs=["x", {"source_ref_id": 5}, {}])
        self.assertEqual({r.requirement_id for r in datacard.requirements_for(card)}, {"ownership"})
        self.assertEqual(codigo_de(datacard.requirements_for, {"card_id": "x"}), core.CODE_FIELD_INVALID)

    def test_la_card_serializada_no_contiene_requisitos_ni_status(self):
        obs = hacer_obs()
        persistir_obs(self.raiz, obs)
        card = armar_card([fuente("src-a", obs)])
        self.evaluar(card)
        d = card.to_dict(con_revision=True)
        for clave in ("requirements", "requisitos", "status", "card_status"):
            self.assertNotIn(clave, d)
            self.assertNotIn(clave, d["body"])
        texto = json.dumps(d)
        for token in ("severity", "accepted_kinds", "min_attestation_kind", "unresolvable", "satisfied"):
            self.assertNotIn(token, texto)
        # la evaluación no muta la Card
        self.assertEqual(card.to_dict(con_revision=True), d)


# ---------------------------------------------------------------------------
# Serialización, portabilidad y round-trip (R12, R33, R34, R35)
# ---------------------------------------------------------------------------


class TestSerializacion(BaseTmp):
    def setUp(self):
        super().setUp()
        self.obs = hacer_obs()
        persistir_obs(self.raiz, self.obs)
        contrato, locator = crear_contrato(self.raiz)
        self.card = card_con_contrato(
            contrato, locator, attestations=(hacer_att(),)
        )
        self.card = dataclasses.replace(
            self.card, claims=self.card.claims + (claim_ownership(),)
        )

    def test_card_base_valida_y_complete(self):
        self.assertEqual(datacard.validate_data_card(self.card), [])
        self.assertEqual(self.evaluar(self.card).card_status, assess.CARD_COMPLETE)

    def test_ninguna_ruta_fisica_en_el_json_serializado(self):
        destino_dir = self.raiz / "salida"
        destino_dir.mkdir()
        destino = destino_dir / "card.json"
        assess.write_card(destino, self.card, lambda: NOW, validate_body=datacard.body_validator_for(self.card))
        texto = destino.read_text(encoding="utf-8")
        self.assertNotIn(str(self.raiz), texto)
        self.assertNotIn(str(self.raiz).replace("\\", "/"), texto)
        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", texto))
        self.assertNotIn("\\", texto)
        self.assertNotIn("://", texto)
        for evidencia in json.loads(texto)["evidence"]:
            locator = evidencia.get("locator")
            if locator is not None:
                self.assertTrue(core.es_locator_portable(locator))

    def test_serializacion_determinista(self):
        def serializar(card):
            return json.dumps(card.to_dict(con_revision=True), indent=2, sort_keys=True, ensure_ascii=False)

        self.assertEqual(serializar(self.card), serializar(copy.deepcopy(self.card)))
        a = self.raiz / "a.json"
        b = self.raiz / "b.json"
        validador = datacard.body_validator_for(self.card)
        assess.write_card(a, self.card, lambda: NOW, validate_body=validador)
        assess.write_card(b, self.card, lambda: NOW, validate_body=validador)
        self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_round_trip_y_evaluate_identico(self):
        ruta = datacard.write_data_card(self.raiz, self.card, clock=lambda: NOW)
        leida = assess.read_card(ruta)
        self.assertEqual(leida.to_dict(), self.card.to_dict())
        self.assertEqual(leida.revision_id(), self.card.revision_id())
        directo = self.evaluar(self.card).a_dict()
        desde_archivo = datacard.evaluate_data_card(ruta, self.raiz).a_dict()
        desde_str = datacard.evaluate_data_card(str(ruta), self.raiz).a_dict()
        self.assertEqual(directo, desde_archivo)
        self.assertEqual(directo, desde_str)
        self.assertEqual(directo["card_status"], "complete")
        json.dumps(directo)

    def test_evaluate_data_card_archivo_mal_formado_es_invalid_sin_excepcion(self):
        casos = {
            "basura": b"{esto no es json",
            "vacio": b"",
            "lista": b"[1, 2]",
            "objeto_vacio": b"{}",
            "binario": b"\xff\xfe\x00\x01",
        }
        for nombre, contenido in casos.items():
            with self.subTest(caso=nombre):
                ruta = self.raiz / f"{nombre}.json"
                ruta.write_bytes(contenido)
                ev = datacard.evaluate_data_card(ruta, self.raiz)
                self.assertEqual(ev.card_status, assess.CARD_INVALID)
                self.assertTrue(ev.hallazgos)
        ev = datacard.evaluate_data_card(self.raiz / "no_existe.json", self.raiz)
        self.assertEqual(ev.card_status, assess.CARD_INVALID)

    def test_evaluate_data_card_con_status_persistido_es_invalid(self):
        ruta = datacard.write_data_card(self.raiz, self.card, clock=lambda: NOW)
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["status"] = "complete"
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        self.assertEqual(datacard.evaluate_data_card(ruta, self.raiz).card_status, assess.CARD_INVALID)

    def test_evaluate_data_card_con_kind_schema_ajeno_en_archivo_es_invalid(self):
        ruta = datacard.write_data_card(self.raiz, self.card, clock=lambda: NOW)
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["kind_schema_version"] = 2
        datos.pop("revision_id", None)
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        ev = datacard.evaluate_data_card(ruta, self.raiz)
        self.assertEqual(ev.card_status, assess.CARD_INVALID)
        self.assertIn(datacard.CODE_SCHEMA_UNSUPPORTED, [h.code for h in ev.hallazgos])

    def test_evaluate_data_card_nunca_pass_con_repo_root_sin_evidencia(self):
        with tempfile.TemporaryDirectory() as otro:
            ev = datacard.evaluate_data_card(self.card, otro)
        self.assertNotEqual(ev.card_status, assess.CARD_COMPLETE)
        self.assertNotIn("PASS", [r.status for r in assess.a_check_results(ev)])


# ---------------------------------------------------------------------------
# Hallazgos del reviewer, ciclo 1
# ---------------------------------------------------------------------------

HASH_COHERENTE = "0123456789ab" + "0" * 52  # hash12 == "0123456789ab"


class TestClaimsCoherentes(BaseTmp):
    """B1: los claims `source_*` / `contract_*` solo pueden apoyarse en la
    evidencia de SU source_ref / SUS contract_refs (R16)."""

    def setUp(self):
        super().setUp()
        self.oa = hacer_obs("ventas", 10)
        self.ob = hacer_obs("clientes", 20)
        persistir_obs(self.raiz, self.oa)
        persistir_obs(self.raiz, self.ob)
        self.fa = fuente("src-a", self.oa)
        self.fb = fuente("src-b", self.ob)

    def _claim_a(self, supports, requirement_id="source_src-a"):
        return core.Claim("c-a", "afirmación sobre la fuente", supports=tuple(supports), requirement_id=requirement_id)

    def _card(self, claims, **kw):
        return armar_card([self.fa, self.fb], con_claims=False, claims_extra=tuple(claims), **kw)

    def _inconsistente(self, card):
        self.assertIn(datacard.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(card))
        ev = self.evaluar(card)
        self.assertEqual(ev.card_status, assess.CARD_INVALID)
        self.assertNotEqual(ev.card_status, assess.CARD_COMPLETE)
        self.assertIn(datacard.CODE_CLAIM_SUPPORT_INCONSISTENT, [h.code for h in ev.hallazgos])

    def test_claim_de_source_a_apoyado_solo_en_evidencia_de_b_es_inconsistente(self):
        self._inconsistente(self._card([self._claim_a(["ev-src-b"])]))

    def test_claim_de_source_a_con_soportes_de_a_y_de_b_es_inconsistente(self):
        self._inconsistente(self._card([self._claim_a(["ev-src-a", "ev-src-b"])]))

    def test_claim_de_source_sin_su_observation_evidence_es_inconsistente(self):
        pin_p = pin_provenance(self.oa, "ev-prov-a")
        card = self._card([self._claim_a(["ev-prov-a"])], evidence_extra=(pin_p,))
        card = con_source_ref(card, provenance_evidence_id="ev-prov-a")
        self._inconsistente(card)

    def test_claim_con_source_ref_inexistente_es_inconsistente(self):
        self._inconsistente(self._card([self._claim_a(["ev-src-a"], requirement_id="source_fantasma")]))

    def test_claim_valido_con_observation_y_provenance_de_la_misma_source_ref(self):
        pin_p = pin_provenance(self.oa, "ev-prov-a")
        claims = [self._claim_a(["ev-src-a", "ev-prov-a"]), core.Claim("c-b", "fuente b", supports=("ev-src-b",), requirement_id="source_src-b")]
        card = self._card(claims, evidence_extra=(pin_p,))
        card = con_source_ref(card, provenance_evidence_id="ev-prov-a")
        self.assertEqual(datacard.validate_data_card(card), [])
        self.assertEqual(self.evaluar(card).card_status, assess.CARD_COMPLETE)

    def test_claim_de_source_sin_soportes_es_inconsistente(self):
        self._inconsistente(self._card([self._claim_a([])]))

    def test_observacion_stale_con_provenance_fresh_no_enmascara_el_requisito(self):
        pin_p = pin_provenance(self.oa, "ev-prov-a")
        card = self._card([self._claim_a(["ev-src-a", "ev-prov-a"])], evidence_extra=(pin_p,))
        card = con_source_ref(card, provenance_evidence_id="ev-prov-a")
        self.assertEqual(datacard.validate_data_card(card), [])
        persistir_obs(self.raiz, hacer_obs("ventas", 11, T2))  # cambia el contenido, no la provenance
        ev = self.evaluar(card)
        self.assertEqual(estado_ev(ev, "ev-src-a"), assess.EV_STALE)
        self.assertEqual(estado_ev(ev, "ev-prov-a"), assess.EV_FRESH)
        self.assertEqual(estado_req(ev, "source_src-a"), assess.REQ_STALE)
        self.assertEqual(ev.card_status, assess.CARD_STALE)

    def test_claim_de_contrato_apoyado_en_evidencia_de_otro_contrato_es_inconsistente(self):
        contrato, locator = crear_contrato(self.raiz)
        pin_ct = pin_contrato(contrato, locator)
        pin_otro = core.EvidenceRef(
            "ev-ct2", "harmessi_contract", "otro-contrato@1.0.0", H0, T0, locator="contratos/otro.json"
        )
        refs = [
            {"contract_id": "mi-contrato", "version": "1.0.0", "declaration_evidence_id": "ev-ct"},
            {"contract_id": "otro-contrato", "version": "1.0.0", "declaration_evidence_id": "ev-ct2"},
        ]
        base = dict(body_extra={"contract_refs": refs}, evidence_extra=(pin_ct, pin_otro))
        propio = core.Claim("c-ct", "contrato", supports=("ev-ct",), requirement_id="contract_mi-contrato")
        ajeno = core.Claim("c-ct", "contrato", supports=("ev-ct2",), requirement_id="contract_mi-contrato")
        mixto = core.Claim("c-ct", "contrato", supports=("ev-ct", "ev-ct2"), requirement_id="contract_mi-contrato")
        ok = armar_card([self.fa, self.fb], con_claims=False, claims_extra=(propio,), **base)
        self.assertEqual(datacard.validate_data_card(ok), [])
        for malo in (ajeno, mixto):
            with self.subTest(supports=malo.supports):
                self._inconsistente(armar_card([self.fa, self.fb], con_claims=False, claims_extra=(malo,), **base))

    def test_claim_de_contrato_apoyado_en_evidencia_de_fuente_es_inconsistente(self):
        contrato, locator = crear_contrato(self.raiz)
        card = card_con_contrato(contrato, locator)
        rid = datacard.requirement_id_for_contract("mi-contrato")
        claims = tuple(c for c in card.claims if c.requirement_id != rid) + (
            core.Claim("c-ct", "contrato", supports=("ev-src-a",), requirement_id=rid),
        )
        self.assertIn(datacard.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(dataclasses.replace(card, claims=claims)))

    def test_ownership_con_atestacion_sigue_ok(self):
        claims = [
            core.Claim("c-a", "fuente a", supports=("ev-src-a",), requirement_id="source_src-a"),
            core.Claim("c-b", "fuente b", supports=("ev-src-b",), requirement_id="source_src-b"),
            claim_ownership(),
        ]
        card = self._card(claims, attestations=(hacer_att(),))
        self.assertEqual(datacard.validate_data_card(card), [])
        ev = self.evaluar(card)
        self.assertEqual(estado_req(ev, datacard.REQ_OWNERSHIP), assess.REQ_SATISFIED)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_dos_fuentes_una_cambiada_deja_la_card_stale_sin_enmascararla(self):
        claims = [
            core.Claim("c-a", "fuente a", supports=("ev-src-a",), requirement_id="source_src-a"),
            core.Claim("c-b", "fuente b", supports=("ev-src-b",), requirement_id="source_src-b"),
        ]
        card = self._card(claims)
        self.assertEqual(datacard.validate_data_card(card), [])
        self.assertEqual(self.evaluar(card).card_status, assess.CARD_COMPLETE)
        persistir_obs(self.raiz, hacer_obs("ventas", 11, T2))  # la fuente A cambió
        ev = self.evaluar(card)
        self.assertEqual(estado_ev(ev, "ev-src-a"), assess.EV_STALE)
        self.assertEqual(estado_ev(ev, "ev-src-b"), assess.EV_FRESH)
        self.assertEqual(ev.card_status, assess.CARD_STALE)


class TestIdsDeEvidenciaDeFuente(BaseTmp):
    """I2 / I3: el ref_id del pin de la fuente es `<source_id>__<hash12>` y el
    hash12 coincide con `content_sha256[:12]`."""

    def _card_con_pin(self, source_id, ref_id, sha=HASH_COHERENTE):
        pin = core.EvidenceRef("ev-a", "source_observation", ref_id, sha, T0)
        return armar_card([{"sref": "src-a", "source_id": source_id, "pin": pin}])

    def test_pin_coherente_es_valido(self):
        self.assertEqual(datacard.validate_data_card(self._card_con_pin("a", "a__0123456789ab")), [])

    def test_source_id_con_doble_guion_bajo_en_ref_id_ambiguo_es_inconsistente(self):
        # source_id "a" no puede escudarse en un ref_id `a__b__<hash12>` (I2).
        card = self._card_con_pin("a", "a__b__0123456789ab")
        self.assertIn(datacard.CODE_SOURCE_REF_INCONSISTENT, codigos(card))
        self.assertEqual(self.evaluar(card).card_status, assess.CARD_INVALID)

    def test_ref_id_sin_12_hex_es_inconsistente(self):
        for ref_id in ("a__0123456789", "a__0123456789abc", "a__0123456789AB", "a__0123456789zz", "a__", "a"):
            with self.subTest(ref_id=ref_id):
                self.assertIn(datacard.CODE_SOURCE_REF_INCONSISTENT, codigos(self._card_con_pin("a", ref_id)))

    def test_hash12_distinto_de_content_sha256_es_inconsistente(self):
        card = self._card_con_pin("a", "a__0123456789ab", sha="f" * 64)
        self.assertIn(datacard.CODE_SOURCE_REF_INCONSISTENT, codigos(card))
        self.assertEqual(self.evaluar(card).card_status, assess.CARD_INVALID)


class TestPortabilidadDeExtensiones(BaseTmp):
    """I1: las claves `x_*` también se revisan (recursivamente) por rutas/DSN."""

    VALORES = (
        "C:\\datos\\x.csv",
        "/srv/datos",
        "postgres://usuario:clave@host/db",
    )

    def setUp(self):
        super().setUp()
        self.card = armar_card([fuente("src-a", hacer_obs())])

    def _rechazada(self, card):
        self.assertIn(core.CODE_LOCATOR_NOT_PORTABLE, codigos(card))
        self.assertEqual(self.evaluar(card).card_status, assess.CARD_INVALID)

    def test_x_nota_en_el_body(self):
        for valor in self.VALORES:
            with self.subTest(valor=valor):
                self._rechazada(con_body(self.card, x_nota=valor))

    def test_x_nota_anidada_en_lista_y_dict(self):
        for valor in self.VALORES:
            with self.subTest(valor=valor, forma="lista"):
                self._rechazada(con_body(self.card, x_nota=["ok", valor]))
            with self.subTest(valor=valor, forma="dict"):
                self._rechazada(con_body(self.card, x_nota={"a": {"b": ["ok", valor]}}))

    def test_x_nota_en_source_ref(self):
        for valor in self.VALORES:
            with self.subTest(valor=valor):
                self._rechazada(con_source_ref(self.card, x_nota=valor))
                self._rechazada(con_source_ref(self.card, x_nota={"k": [valor]}))

    def test_x_nota_en_stewardship_y_time_scope(self):
        self._rechazada(con_body(self.card, stewardship={"owner": "Equipo", "x_ref": "/srv/datos"}))
        self._rechazada(con_body(self.card, time_scope={"as_of": "2026-01-01", "x_ref": "C:\\x"}))

    def test_x_nota_libre_sigue_permitida(self):
        card = con_body(self.card, x_nota=["texto libre", {"n": 1, "ok": [True, None, 2.5]}])
        self.assertEqual(datacard.validate_data_card(card), [])


class TestErroresDeFilesystem(BaseTmp):
    """M1: un OSError al consultar la existencia se convierte en CardError."""

    def setUp(self):
        super().setUp()
        self.card = armar_card([fuente("src-a", hacer_obs())])

    def test_write_data_card_nueva_con_permission_error_es_card_error(self):
        with mock.patch.object(Path, "exists", side_effect=PermissionError("denegado")):
            self.assertEqual(
                codigo_de(datacard.write_data_card, self.raiz, self.card, clock=lambda: NOW), core.CODE_IO_ERROR
            )
        self.assertFalse((self.raiz / "governance").exists())

    def test_write_data_card_replace_con_permission_error_es_card_error(self):
        with mock.patch.object(Path, "exists", side_effect=PermissionError("denegado")):
            self.assertEqual(
                codigo_de(datacard.write_data_card, self.raiz, self.card, replace=True, clock=lambda: NOW),
                core.CODE_IO_ERROR,
            )

    def test_existe_convierte_oserror_en_card_error(self):
        with mock.patch.object(Path, "exists", side_effect=PermissionError("denegado")):
            self.assertEqual(codigo_de(datacard._existe, self.raiz / "x.json"), core.CODE_IO_ERROR)

    def test_es_archivo_convierte_oserror_en_card_error(self):
        with mock.patch.object(Path, "is_file", side_effect=PermissionError("denegado")):
            self.assertEqual(codigo_de(datacard._es_archivo, self.raiz / "x.json"), core.CODE_IO_ERROR)

    def test_replace_con_is_file_permission_error_es_card_error_no_crudo(self):
        datacard.write_data_card(self.raiz, self.card, clock=lambda: NOW)  # el destino existe
        with mock.patch.object(Path, "is_file", side_effect=PermissionError("denegado")):
            self.assertEqual(
                codigo_de(datacard.write_data_card, self.raiz, self.card, replace=True, clock=lambda: NOW),
                core.CODE_IO_ERROR,
            )

    def test_io_error_de_write_card_con_destino_inexistente_no_es_datacard_exists(self):
        falla = core.CardError(core.CODE_IO_ERROR, "sin hard links")
        with mock.patch.object(assess, "write_card", side_effect=falla):
            codigo = codigo_de(datacard.write_data_card, self.raiz, self.card, clock=lambda: NOW)
        self.assertEqual(codigo, core.CODE_IO_ERROR)
        self.assertNotEqual(codigo, datacard.CODE_EXISTS)

    def test_io_error_de_write_card_con_destino_existente_es_datacard_exists(self):
        destino = datacard.card_path(self.raiz, self.card.card_id)
        falla = core.CardError(core.CODE_IO_ERROR, "ya existe")

        def _crea_y_falla(*args, **kwargs):
            destino.write_text("{}", encoding="utf-8")  # carrera: aparece durante la escritura
            raise falla

        with mock.patch.object(assess, "write_card", side_effect=_crea_y_falla):
            self.assertEqual(
                codigo_de(datacard.write_data_card, self.raiz, self.card, clock=lambda: NOW), datacard.CODE_EXISTS
            )

    def test_fallback_de_assess_con_permission_error_es_card_error(self):
        with mock.patch.object(Path, "exists", side_effect=PermissionError("denegado")):
            self.assertEqual(
                codigo_de(assess._publicar_sin_hardlink, "tmp-inexistente", self.raiz / "x.json"), core.CODE_IO_ERROR
            )


class TestLongitudDeIds(BaseTmp):
    """Límite real del código: `requirement_id` (prefijo + id) <= 64 caracteres."""

    def setUp(self):
        super().setUp()
        self.obs = hacer_obs()
        persistir_obs(self.raiz, self.obs)

    def test_limites_segun_el_codigo(self):
        self.assertEqual(datacard._MAX_ID - len(datacard.REQ_PREFIJO_SOURCE), 57)
        self.assertEqual(datacard._MAX_ID - len(datacard.REQ_PREFIJO_CONTRACT), 55)

    def test_source_ref_id_de_57_ok_y_de_58_rechazado(self):
        sref = "s" * 57
        card = armar_card([fuente(sref, self.obs, "ev-1")])
        self.assertEqual(len(datacard.requirement_id_for_source(sref)), 64)
        self.assertEqual(datacard.validate_data_card(card), [])
        self.assertEqual(self.evaluar(card).card_status, assess.CARD_COMPLETE)
        largo = armar_card([fuente("s" * 58, self.obs, "ev-1")], con_claims=False)
        self.assertIn(datacard.CODE_BODY_INVALID, codigos(largo))
        self.assertEqual(self.evaluar(largo).card_status, assess.CARD_INVALID)

    def _card_contrato(self, contract_id):
        pin = core.EvidenceRef(
            "ev-ct", "harmessi_contract", f"{contract_id}@1.0.0", H0, T0, locator="contratos/c.json"
        )
        return armar_card(
            [fuente("src-a", self.obs)],
            body_extra={
                "contract_refs": [
                    {"contract_id": contract_id, "version": "1.0.0", "declaration_evidence_id": "ev-ct"}
                ]
            },
            evidence_extra=(pin,),
        )

    def test_contract_id_de_55_ok_y_de_56_rechazado(self):
        ok = self._card_contrato("c" * 55)
        self.assertEqual(len(datacard.requirement_id_for_contract("c" * 55)), 64)
        self.assertEqual(datacard.validate_data_card(ok), [])
        self.assertIn(datacard.CODE_BODY_INVALID, codigos(self._card_contrato("c" * 56)))


@unittest.skipIf(ds_runtime is None, "datasources.runtime no importable")
class TestReobservacionRuntimeReal(BaseTmp):
    """DOCUMENTACIÓN de comportamiento (no de requisito) del runtime REAL de v0.8
    (`_persistir_observacion`):

    - La re-observación con contenido idéntico pero otro `generated_at` produce
      bytes distintos (generated_at va en el JSON) para el MISMO directorio
      `<source_id>__<hash12>`: el runtime NO actualiza el archivo (lo reporta como
      "colisión de hash") y `generated_at` queda en el de la primera observación.
      El resolver sigue dando `fresh` con el directorio existente.
    - LIMITACIÓN CONOCIDA A -> B -> A: al volver al contenido A el directorio de A
      conserva su `generated_at` viejo, así que la "vigente" (máximo generated_at)
      sigue siendo B y un pin de A queda `stale`.
    """

    def test_reobservacion_identica_no_actualiza_el_archivo_y_sigue_fresh(self):
        v1 = hacer_obs("ventas", 10, T1)
        self.assertIsNone(ds_runtime._persistir_observacion(self.raiz, v1))
        archivo = self.raiz / ".harmessi" / "observations" / f"ventas__{v1.content_sha256()[:12]}" / "observation.json"
        bytes_antes = archivo.read_bytes()
        card = armar_card([fuente("src-a", v1)])

        v1b = hacer_obs("ventas", 10, T3)  # mismo contenido, otro generated_at
        self.assertEqual(v1.content_sha256(), v1b.content_sha256())
        resultado = ds_runtime._persistir_observacion(self.raiz, v1b)
        self.assertIsNotNone(resultado)  # el runtime lo trata como colisión y no escribe
        self.assertEqual(archivo.read_bytes(), bytes_antes)
        self.assertEqual(json.loads(bytes_antes.decode("utf-8"))["provenance"]["generated_at"], T1)

        ev = self.evaluar(card)
        self.assertEqual(estado_ev(ev, "ev-src-a"), assess.EV_FRESH)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_limitacion_a_b_a_deja_el_pin_de_a_stale(self):
        a1 = hacer_obs("ventas", 10, T1)
        b = hacer_obs("ventas", 11, T2)
        a2 = hacer_obs("ventas", 10, T3)  # vuelve al contenido A, más reciente
        ds_runtime._persistir_observacion(self.raiz, a1)
        card = armar_card([fuente("src-a", a1)])
        self.assertEqual(estado_ev(self.evaluar(card), "ev-src-a"), assess.EV_FRESH)
        ds_runtime._persistir_observacion(self.raiz, b)
        ds_runtime._persistir_observacion(self.raiz, a2)  # no actualiza el directorio de A
        ev = self.evaluar(card)
        # Limitación documentada: debería ser fresh (el contenido vigente es A) pero
        # queda stale porque la vigente se decide por generated_at del directorio.
        self.assertEqual(estado_ev(ev, "ev-src-a"), assess.EV_STALE)
        self.assertEqual(ev.card_status, assess.CARD_STALE)
        # Falso fresh documentado (D6): el pin de B figura fresh aunque la fuente
        # haya vuelto al estado A, porque el directorio de B sigue siendo el vigente.
        card_b = armar_card([fuente("src-a", b)])
        self.assertEqual(estado_ev(self.evaluar(card_b), "ev-src-a"), assess.EV_FRESH)


if __name__ == "__main__":
    unittest.main()
