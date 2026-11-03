"""Tests de `tools/cards/resolvers.py` (Change `20261002-data-cards`, R18-R27).

Usan OBJETOS REALES en directorios temporales: `datasources.core.SourceObservation`
(persistida con el layout `.harmessi/observations/<source_id>__<hash12>/observation.json`),
`datacontracts.core.DataContract` (escrito como `to_dict()`) y manifests reales de
`qualityevidence` (`write_manifest`). Solo los tests importan esos paquetes (R1).
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tools.cards import assess, core, resolvers
from tools.datacontracts import core as dc_core
from tools.datasources import core as ds_core
from tools.qualityevidence import core as qe_core
from tools.qualityevidence import evidence as qe_evidence

H = "a" * 64
T0 = "2026-10-01T10:00:00Z"
HASH12_CERO = "0" * 12


# ---------------------------------------------------------------------------
# Constructores de objetos reales
# ---------------------------------------------------------------------------


def _observacion(source_id="clientes", generated_at="2026-10-01T10:00:00Z", filas=10, observer_id="obs:file"):
    prov = ds_core.SourceProvenance(
        source_id=source_id,
        observer_id=observer_id,
        observer_code_sha256=None,
        access_mode="read",
        source_kind=None,
        generated_at=generated_at,
    )
    return ds_core.SourceObservation(
        source_id=source_id,
        provenance=prov,
        dataset={"row_count": {"value": filas, "exactness": "exact"}},
    )


def _guardar_observacion(raiz, obs):
    """Persiste con el layout real de `datasources.runtime`. Devuelve el directorio."""
    directorio = Path(raiz) / ".harmessi" / "observations" / f"{obs.source_id}__{obs.content_sha256()[:12]}"
    directorio.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(obs.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    (directorio / "observation.json").write_bytes(texto.encode("utf-8"))
    return directorio


def _contrato(contract_id="contrato-clientes", version="1.0.0", descripcion=""):
    return dc_core.DataContract(
        contract_id=contract_id,
        version=dc_core.ContractVersion(version),
        dataset_role="raw_table",
        fields=(dc_core.ContractField("id", "integer"), dc_core.ContractField("monto", "float")),
        description=descripcion,
    )


def _guardar_contrato(raiz, contrato, rel="contracts/contrato.json"):
    ruta = Path(raiz) / rel
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(contrato.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return ruta


def _manifest(subject="data_contract_evaluation", declaration_kind="data_contract"):
    declaracion = qe_core.DeclarationRef(declaration_kind, "contrato-clientes", "1.0.0", "c" * 64)
    fuente = qe_core.EvidenceSource(
        kind="generated", role="input", sha256="b" * 64, description="conteo sintetico", params={"n": 1}
    )
    return qe_evidence.build_manifest(
        subject_kind=subject,
        declaration=declaracion,
        source=fuente,
        results=[],
        clock=lambda: datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc),
    )


def _guardar_manifest(raiz, manifest):
    return qe_evidence.write_manifest(raiz, manifest)


def _ref(kind, ref_id, locator=None, member=None):
    return core.EvidenceRef("ev1", kind, ref_id, H, T0, member=member, locator=locator)


def _ref_obs(source_id="clientes", kind="source_observation", member=None):
    return _ref(kind, f"{source_id}__{HASH12_CERO}", member=member)


def _falso(ref_id=None, locator=None, member=None, kind="x"):
    """Ref hostil que `EvidenceRef` real rechazaría en construcción."""
    return SimpleNamespace(ref_id=ref_id, locator=locator, member=member, kind=kind, content_sha256=H)


def _symlink(destino, origen, directorio=True):
    try:
        os.symlink(str(origen), str(destino), target_is_directory=directorio)
    except (OSError, NotImplementedError, AttributeError):
        raise unittest.SkipTest("el SO no permite crear symlinks")


def _arbol(raiz):
    """Snapshot (ruta relativa, es_dir, tamaño, mtime_ns) de todo el árbol."""
    salida = []
    for base, dirs, archivos in os.walk(raiz):
        for nombre in sorted(dirs) + sorted(archivos):
            ruta = Path(base) / nombre
            st = ruta.lstat()
            salida.append((ruta.relative_to(raiz).as_posix(), ruta.is_dir(), st.st_size, st.st_mtime_ns))
    return sorted(salida)


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name).resolve()
        self.repo = self.raiz / "repo"
        self.repo.mkdir()
        self.fuera = self.raiz / "fuera"
        self.fuera.mkdir()

    def assertEstado(self, resolucion, estado):
        self.assertIsInstance(resolucion, assess.Resolution)
        self.assertEqual(resolucion.state, estado, resolucion.detail)
        if estado != assess.RES_FOUND:
            self.assertIsNone(resolucion.current_sha256)


# ---------------------------------------------------------------------------
# source_observation (R18-R20) y source_provenance (R21), D6
# ---------------------------------------------------------------------------


class TestSourceObservation(_Base):
    def _resolver(self):
        return resolvers.source_observation_resolver(self.repo)

    def test_found_con_hash_de_la_observacion_real(self):
        obs = _observacion()
        _guardar_observacion(self.repo, obs)
        res = self._resolver()(_ref_obs())
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, obs.content_sha256())

    def test_missing_sin_directorio_de_observaciones(self):
        self.assertEstado(self._resolver()(_ref_obs()), assess.RES_MISSING)

    def test_missing_si_solo_hay_otros_source_ids(self):
        _guardar_observacion(self.repo, _observacion("otra-fuente"))
        self.assertEstado(self._resolver()(_ref_obs("clientes")), assess.RES_MISSING)

    def test_hash12_del_ref_no_se_compara_solo_el_contenido(self):
        obs = _observacion()
        _guardar_observacion(self.repo, obs)
        ref = _ref("source_observation", "clientes__ffffffffffff")
        res = self._resolver()(ref)
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, obs.content_sha256())

    def test_unverifiable_json_corrupto(self):
        directorio = _guardar_observacion(self.repo, _observacion())
        (directorio / "observation.json").write_text("{", encoding="utf-8")
        self.assertEstado(self._resolver()(_ref_obs()), assess.RES_UNVERIFIABLE)

    def test_unverifiable_json_no_objeto_nan_o_utf8_invalido(self):
        directorio = _guardar_observacion(self.repo, _observacion())
        for contenido in (b"[]", b"5", b'{"a": NaN}', b"\xff\xfe"):
            with self.subTest(contenido=contenido):
                (directorio / "observation.json").write_bytes(contenido)
                self.assertEstado(self._resolver()(_ref_obs()), assess.RES_UNVERIFIABLE)

    def test_unverifiable_directorio_sin_observation_json(self):
        directorio = _guardar_observacion(self.repo, _observacion())
        (directorio / "observation.json").unlink()
        self.assertEstado(self._resolver()(_ref_obs()), assess.RES_UNVERIFIABLE)

    def test_unverifiable_entrada_que_no_es_directorio(self):
        base = self.repo / ".harmessi" / "observations"
        base.mkdir(parents=True)
        (base / f"clientes__{HASH12_CERO}").write_text("x", encoding="utf-8")
        self.assertEstado(self._resolver()(_ref_obs()), assess.RES_UNVERIFIABLE)

    def test_unverifiable_source_id_interno_distinto_al_del_directorio(self):
        obs_otra = _observacion("otra-fuente")
        directorio = _guardar_observacion(self.repo, obs_otra)
        destino = self.repo / ".harmessi" / "observations" / f"clientes__{HASH12_CERO}"
        directorio.rename(destino)
        self.assertEstado(self._resolver()(_ref_obs("clientes")), assess.RES_UNVERIFIABLE)

    def test_unverifiable_provenance_ausente_o_fecha_invalida(self):
        directorio = _guardar_observacion(self.repo, _observacion())
        archivo = directorio / "observation.json"
        base = json.loads(archivo.read_text(encoding="utf-8"))
        casos = {
            "sin_provenance": {k: v for k, v in base.items() if k != "provenance"},
            "provenance_no_dict": dict(base, provenance="x"),
            "sin_generated_at": dict(base, provenance={k: v for k, v in base["provenance"].items() if k != "generated_at"}),
            "fecha_basura": dict(base, provenance=dict(base["provenance"], generated_at="ayer")),
            "fecha_no_str": dict(base, provenance=dict(base["provenance"], generated_at=5)),
        }
        for nombre, datos in casos.items():
            with self.subTest(caso=nombre):
                archivo.write_text(json.dumps(datos), encoding="utf-8")
                self.assertEstado(self._resolver()(_ref_obs()), assess.RES_UNVERIFIABLE)

    def test_unverifiable_archivo_excede_tamano_maximo(self):
        _guardar_observacion(self.repo, _observacion())
        with mock.patch.object(resolvers, "MAX_BYTES_LECTURA", 10):
            self.assertEstado(self._resolver()(_ref_obs()), assess.RES_UNVERIFIABLE)

    def test_un_directorio_corrupto_de_otro_source_id_no_afecta(self):
        obs = _observacion()
        _guardar_observacion(self.repo, obs)
        otro = _guardar_observacion(self.repo, _observacion("otra-fuente"))
        (otro / "observation.json").write_text("{", encoding="utf-8")
        res = self._resolver()(_ref_obs())
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, obs.content_sha256())

    def test_un_directorio_corrupto_del_mismo_source_id_es_unverifiable(self):
        _guardar_observacion(self.repo, _observacion(filas=1))
        malo = _guardar_observacion(self.repo, _observacion(filas=2))
        (malo / "observation.json").write_text("{", encoding="utf-8")
        self.assertEstado(self._resolver()(_ref_obs()), assess.RES_UNVERIFIABLE)

    def test_ref_id_malformado_es_unverifiable(self):
        _guardar_observacion(self.repo, _observacion())
        for ref_id in (
            "clientes",
            "clientes__",
            "Clientes__0123456789ab",
            "clientes__XYZ",
            "clientes__0123456789abc",
            "clientes__0123456789a",
            "clientes_0123456789ab",
            "clientes__0123456789AB",
            "",
        ):
            with self.subTest(ref_id=ref_id):
                self.assertEstado(self._resolver()(_falso(ref_id)), assess.RES_UNVERIFIABLE)

    def test_ref_id_con_rutas_o_separadores_es_unverifiable(self):
        _guardar_observacion(self.repo, _observacion())
        for ref_id in (
            "../clientes__0123456789ab",
            "..__0123456789ab",
            "a/b__0123456789ab",
            "a\\b__0123456789ab",
            "/abs__0123456789ab",
            "C:\\x__0123456789ab",
            "C:/x__0123456789ab",
            "~x__0123456789ab",
            ".x__0123456789ab",
            "clientes__0123456789ab/",
            "clientes/../clientes__0123456789ab",
            None,
            5,
            b"clientes__0123456789ab",
        ):
            with self.subTest(ref_id=ref_id):
                self.assertEstado(self._resolver()(_falso(ref_id)), assess.RES_UNVERIFIABLE)

    def test_ruta_absoluta_como_ref_id_real_tampoco_resuelve(self):
        # Una EvidenceRef real ya rechaza rutas absolutas; si colara una, igual no resuelve.
        absoluta = str(self.fuera).replace("\\", "/")
        self.assertEstado(self._resolver()(_falso(absoluta + "__0123456789ab")), assess.RES_UNVERIFIABLE)

    # -- D6: varias observaciones del mismo source_id -------------------------

    def test_elige_la_de_mayor_generated_at(self):
        for vieja_filas, nueva_filas in ((1, 2), (2, 1)):
            with self.subTest(vieja=vieja_filas):
                with tempfile.TemporaryDirectory() as tmp:
                    repo = Path(tmp)
                    vieja = _observacion(generated_at="2026-09-01T00:00:00Z", filas=vieja_filas)
                    nueva = _observacion(generated_at="2026-10-01T00:00:00Z", filas=nueva_filas)
                    _guardar_observacion(repo, vieja)
                    _guardar_observacion(repo, nueva)
                    res = resolvers.source_observation_resolver(repo)(_ref_obs())
                    self.assertEstado(res, assess.RES_FOUND)
                    self.assertEqual(res.current_sha256, nueva.content_sha256())
                    self.assertNotEqual(res.current_sha256, vieja.content_sha256())

    def test_generated_at_se_compara_como_fecha_no_como_texto(self):
        # "+02:00" en texto es mayor, pero como instante UTC es MÁS VIEJO.
        con_offset = _observacion(generated_at="2026-10-01T10:00:00+02:00", filas=1)  # 08:00Z
        utc = _observacion(generated_at="2026-10-01T09:00:00Z", filas=2)  # 09:00Z
        _guardar_observacion(self.repo, con_offset)
        _guardar_observacion(self.repo, utc)
        res = self._resolver()(_ref_obs())
        self.assertEqual(res.current_sha256, utc.content_sha256())

    def test_parsear_fecha_formatos_validos(self):
        base = datetime(2026, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
        casos = {
            "2026-01-02": base,
            "2026-01-02T00:00:00Z": base,
            "2026-01-02T00:00:00.5Z": base.replace(microsecond=500000),
            "2026-01-02T00:00:00.123Z": base.replace(microsecond=123000),
            "2026-01-02T00:00:00.123456Z": base.replace(microsecond=123456),
            "2026-01-02T00:00:00.123456789Z": base.replace(microsecond=123456),
            "2026-01-02T02:00:00+02:00": base,
            "2026-01-01T19:00:00-05:00": base,
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(resolvers._parsear_fecha(texto), esperado)

    def test_la_mas_reciente_por_instante_con_formatos_mixtos(self):
        fechas = [
            "2026-01-02",                       # 00:00Z
            "2026-01-02T00:00:00.1Z",           # +100 ms
            "2026-01-02T00:00:00.123Z",         # +123 ms
            "2026-01-02T00:00:00.123456Z",
            "2026-01-02T00:00:00.123456789Z",   # truncada a 6 dígitos = igual a la anterior
            "2026-01-02T05:00:00+02:00",        # 03:00Z  <- la más reciente
            "2026-01-02T00:30:00Z",
        ]
        ordenadas = sorted(fechas, key=resolvers._parsear_fecha)
        self.assertEqual(ordenadas[0], "2026-01-02")
        self.assertEqual(ordenadas[-1], "2026-01-02T05:00:00+02:00")
        # y el resolver elige esa observación
        for i, f in enumerate(fechas):
            _guardar_observacion(self.repo, _observacion(generated_at=f, filas=i + 1))
        res = self._resolver()(_ref_obs())
        self.assertEqual(res.current_sha256, _observacion(generated_at=fechas[5], filas=6).content_sha256())

    def test_desempate_por_nombre_de_directorio(self):
        a = _observacion(generated_at=T0, filas=1)
        b = _observacion(generated_at=T0, filas=2)
        _guardar_observacion(self.repo, a)
        _guardar_observacion(self.repo, b)
        nombre_a = f"clientes__{a.content_sha256()[:12]}"
        nombre_b = f"clientes__{b.content_sha256()[:12]}"
        esperado = a if nombre_a > nombre_b else b
        res = self._resolver()(_ref_obs())
        self.assertEqual(res.current_sha256, esperado.content_sha256())

    def test_reobservacion_con_contenido_identico_queda_fresh(self):
        primera = _observacion(generated_at="2026-09-01T00:00:00Z")
        segunda = _observacion(generated_at="2026-10-01T00:00:00Z")
        self.assertEqual(primera.content_sha256(), segunda.content_sha256())
        _guardar_observacion(self.repo, primera)
        _guardar_observacion(self.repo, segunda)
        pin = core.EvidenceRef(
            "ev1", "source_observation", f"clientes__{primera.content_sha256()[:12]}", primera.content_sha256(), T0
        )
        self.assertEqual(assess.evaluar_evidencia(pin, resolvers.default_resolvers(self.repo)), assess.EV_FRESH)

    def test_observacion_cambiada_deja_el_pin_stale(self):
        vieja = _observacion(generated_at="2026-09-01T00:00:00Z", filas=1)
        nueva = _observacion(generated_at="2026-10-01T00:00:00Z", filas=2)
        _guardar_observacion(self.repo, vieja)
        _guardar_observacion(self.repo, nueva)
        pin = core.EvidenceRef(
            "ev1", "source_observation", f"clientes__{vieja.content_sha256()[:12]}", vieja.content_sha256(), T0
        )
        self.assertEqual(assess.evaluar_evidencia(pin, resolvers.default_resolvers(self.repo)), assess.EV_STALE)

    def test_hash_pinneado_alterado_nunca_es_fresh(self):
        obs = _observacion()
        _guardar_observacion(self.repo, obs)
        pin = core.EvidenceRef("ev1", "source_observation", f"clientes__{HASH12_CERO}", "d" * 64, T0)
        estado = assess.evaluar_evidencia(pin, resolvers.default_resolvers(self.repo))
        self.assertIn(estado, (assess.EV_STALE, assess.EV_UNVERIFIABLE))

    def test_archivo_de_observacion_adulterado_cambia_el_hash(self):
        obs = _observacion()
        directorio = _guardar_observacion(self.repo, obs)
        archivo = directorio / "observation.json"
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        datos["dataset"]["row_count"]["value"] = 999
        archivo.write_text(json.dumps(datos), encoding="utf-8")
        res = self._resolver()(_ref_obs())
        self.assertEstado(res, assess.RES_FOUND)
        self.assertNotEqual(res.current_sha256, obs.content_sha256())

    def test_source_ids_que_contienen_doble_guion_bajo_se_distinguen(self):
        simple = _observacion("a", filas=1)
        con_doble = _observacion("a__b", filas=2)
        con_hex = _observacion("a__abcdef012345", filas=3)  # parece <id>__<hash12>
        for obs in (simple, con_doble, con_hex):
            _guardar_observacion(self.repo, obs)
        resolver = self._resolver()
        casos = (("a", simple), ("a__b", con_doble), ("a__abcdef012345", con_hex))
        for source_id, esperado in casos:
            with self.subTest(source_id=source_id):
                res = resolver(_ref("source_observation", f"{source_id}__{HASH12_CERO}"))
                self.assertEstado(res, assess.RES_FOUND)
                self.assertEqual(res.current_sha256, esperado.content_sha256())

    def test_source_id_prefijo_no_confunde_con_otro_mas_largo(self):
        _guardar_observacion(self.repo, _observacion("clientes-historico"))
        self.assertEstado(self._resolver()(_ref_obs("clientes")), assess.RES_MISSING)

    def test_symlink_del_directorio_de_observaciones_que_escapa(self):
        _guardar_observacion(self.fuera, _observacion())
        (self.repo / ".harmessi").mkdir()
        _symlink(self.repo / ".harmessi" / "observations", self.fuera / ".harmessi" / "observations")
        self.assertEstado(self._resolver()(_ref_obs()), assess.RES_UNVERIFIABLE)

    def test_symlink_del_directorio_de_una_observacion_que_escapa(self):
        obs = _observacion()
        directorio_fuera = _guardar_observacion(self.fuera, obs)
        base = self.repo / ".harmessi" / "observations"
        base.mkdir(parents=True)
        _symlink(base / directorio_fuera.name, directorio_fuera)
        self.assertEstado(self._resolver()(_ref_obs()), assess.RES_UNVERIFIABLE)

    def test_symlink_del_archivo_observation_json_que_escapa(self):
        obs = _observacion()
        directorio_fuera = _guardar_observacion(self.fuera, obs)
        directorio = self.repo / ".harmessi" / "observations" / directorio_fuera.name
        directorio.mkdir(parents=True)
        _symlink(directorio / "observation.json", directorio_fuera / "observation.json", directorio=False)
        self.assertEstado(self._resolver()(_ref_obs()), assess.RES_UNVERIFIABLE)


class TestSourceProvenance(_Base):
    def _resolver(self):
        return resolvers.source_provenance_resolver(self.repo)

    def test_found_con_hash_de_provenance_sin_generated_at(self):
        obs = _observacion()
        _guardar_observacion(self.repo, obs)
        res = self._resolver()(_ref_obs(kind="source_provenance", member="provenance"))
        self.assertEstado(res, assess.RES_FOUND)
        prov = obs.provenance.to_dict()
        prov.pop("generated_at")
        self.assertEqual(res.current_sha256, ds_core.content_sha256(prov))

    def test_exige_member_provenance(self):
        _guardar_observacion(self.repo, _observacion())
        for member in (None, "otro", "Provenance", ""):
            with self.subTest(member=member):
                ref = _falso(f"clientes__{HASH12_CERO}", member=member, kind="source_provenance")
                self.assertEstado(self._resolver()(ref), assess.RES_UNVERIFIABLE)

    def test_missing_sin_observaciones(self):
        res = self._resolver()(_ref_obs(kind="source_provenance", member="provenance"))
        self.assertEstado(res, assess.RES_MISSING)

    def test_cambio_solo_en_generated_at_no_cambia_el_hash(self):
        _guardar_observacion(self.repo, _observacion(generated_at="2026-09-01T00:00:00Z"))
        ref = _ref_obs(kind="source_provenance", member="provenance")
        antes = self._resolver()(ref).current_sha256
        _guardar_observacion(self.repo, _observacion(generated_at="2026-10-01T00:00:00Z"))
        self.assertEqual(self._resolver()(ref).current_sha256, antes)

    def test_cambio_de_observer_cambia_el_hash(self):
        _guardar_observacion(self.repo, _observacion(generated_at="2026-09-01T00:00:00Z", observer_id="obs:a"))
        ref = _ref_obs(kind="source_provenance", member="provenance")
        antes = self._resolver()(ref).current_sha256
        _guardar_observacion(self.repo, _observacion(generated_at="2026-10-01T00:00:00Z", observer_id="obs:b"))
        self.assertNotEqual(self._resolver()(ref).current_sha256, antes)

    def test_ref_id_con_rutas_es_unverifiable(self):
        for ref_id in ("../x__0123456789ab", "a/b__0123456789ab", "/abs__0123456789ab", "a\\b__0123456789ab"):
            with self.subTest(ref_id=ref_id):
                ref = _falso(ref_id, member="provenance", kind="source_provenance")
                self.assertEstado(self._resolver()(ref), assess.RES_UNVERIFIABLE)


# ---------------------------------------------------------------------------
# harmessi_contract (R22)
# ---------------------------------------------------------------------------


class TestHarmessiContract(_Base):
    def _resolver(self):
        return resolvers.harmessi_contract_resolver(self.repo)

    def _ref(self, ref_id="contrato-clientes@1.0.0", locator="contracts/contrato.json"):
        return _ref("harmessi_contract", ref_id, locator=locator)

    def test_found_con_hash_del_contrato_real(self):
        contrato = _contrato()
        _guardar_contrato(self.repo, contrato)
        res = self._resolver()(self._ref())
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, contrato.content_sha256())

    def test_contrato_modificado_queda_stale(self):
        original = _contrato()
        _guardar_contrato(self.repo, original)
        pin = core.EvidenceRef(
            "ev1", "harmessi_contract", "contrato-clientes@1.0.0", original.content_sha256(), T0,
            locator="contracts/contrato.json",
        )
        defaults = resolvers.default_resolvers(self.repo)
        self.assertEqual(assess.evaluar_evidencia(pin, defaults), assess.EV_FRESH)
        _guardar_contrato(self.repo, _contrato(descripcion="cambio"))
        self.assertEqual(assess.evaluar_evidencia(pin, defaults), assess.EV_STALE)

    def test_missing_si_el_archivo_no_existe(self):
        self.assertEstado(self._resolver()(self._ref()), assess.RES_MISSING)

    def test_unverifiable_sin_locator(self):
        _guardar_contrato(self.repo, _contrato())
        self.assertEstado(self._resolver()(self._ref(locator=None)), assess.RES_UNVERIFIABLE)

    def test_unverifiable_locator_no_portable_o_que_escapa(self):
        _guardar_contrato(self.repo, _contrato())
        (self.raiz / "ajeno.json").write_text(json.dumps(_contrato().to_dict()), encoding="utf-8")
        for locator in (
            "/abs/contrato.json",
            "C:/x/contrato.json",
            "C:contrato.json",
            "a:b.json",
            "..\\ajeno.json",
            "contracts\\contrato.json",
            "../ajeno.json",
            "contracts/../../ajeno.json",
            "~/contrato.json",
            "https://host/contrato.json",
            "",
            5,
            None,
        ):
            with self.subTest(locator=locator):
                self.assertEstado(self._resolver()(_falso("contrato-clientes@1.0.0", locator=locator)), assess.RES_UNVERIFIABLE)

    def test_unverifiable_ref_id_malformado(self):
        _guardar_contrato(self.repo, _contrato())
        for ref_id in ("contrato-clientes", "contrato-clientes@1.0", "contrato-clientes@v1", "@1.0.0", "Contrato@1.0.0", "", None):
            with self.subTest(ref_id=ref_id):
                self.assertEstado(self._resolver()(_falso(ref_id, locator="contracts/contrato.json")), assess.RES_UNVERIFIABLE)

    def test_unverifiable_si_id_o_version_no_coinciden_con_el_contenido(self):
        _guardar_contrato(self.repo, _contrato())
        for ref_id in ("otro-contrato@1.0.0", "contrato-clientes@2.0.0"):
            with self.subTest(ref_id=ref_id):
                self.assertEstado(self._resolver()(self._ref(ref_id)), assess.RES_UNVERIFIABLE)

    def test_unverifiable_json_invalido_o_forma_inesperada(self):
        ruta = _guardar_contrato(self.repo, _contrato())
        base = _contrato().to_dict()
        for nombre, contenido in (
            ("roto", "{"),
            ("lista", "[]"),
            ("version_str", json.dumps(dict(base, version="1.0.0"))),
            ("sin_version", json.dumps({k: v for k, v in base.items() if k != "version"})),
        ):
            with self.subTest(caso=nombre):
                ruta.write_text(contenido, encoding="utf-8")
                self.assertEstado(self._resolver()(self._ref()), assess.RES_UNVERIFIABLE)

    def test_unverifiable_si_el_locator_es_un_directorio(self):
        (self.repo / "contracts" / "contrato.json").mkdir(parents=True)
        self.assertEstado(self._resolver()(self._ref()), assess.RES_UNVERIFIABLE)

    def test_symlink_que_escapa_de_repo_root(self):
        _guardar_contrato(self.fuera, _contrato(), rel="contrato.json")
        (self.repo / "contracts").mkdir()
        _symlink(self.repo / "contracts" / "contrato.json", self.fuera / "contrato.json", directorio=False)
        self.assertEstado(self._resolver()(self._ref()), assess.RES_UNVERIFIABLE)

    def test_symlink_de_directorio_que_escapa_de_repo_root(self):
        _guardar_contrato(self.fuera, _contrato(), rel="contrato.json")
        _symlink(self.repo / "contracts", self.fuera)
        self.assertEstado(self._resolver()(self._ref()), assess.RES_UNVERIFIABLE)


# ---------------------------------------------------------------------------
# quality_evidence / data_contract_result (R23)
# ---------------------------------------------------------------------------


class TestQualityEvidence(_Base):
    def _ref(self, evidence_id, kind="quality_evidence"):
        return _ref(kind, evidence_id)

    def _manifest_persistido(self, **kwargs):
        manifest = _manifest(**kwargs)
        ruta = _guardar_manifest(self.repo, manifest)
        return manifest, Path(ruta)

    def test_quality_evidence_found_con_hash_persistido_y_recomputado(self):
        manifest, ruta = self._manifest_persistido()
        res = resolvers.quality_evidence_resolver(self.repo)(self._ref(manifest.evidence_id))
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, manifest.content_sha256())
        self.assertEqual(res.current_sha256, json.loads(ruta.read_text(encoding="utf-8"))["content_sha256"])

    def test_quality_evidence_acepta_cualquier_subject_kind(self):
        manifest, _ = self._manifest_persistido(subject="model_quality_evaluation", declaration_kind="model_quality_policy")
        res = resolvers.quality_evidence_resolver(self.repo)(self._ref(manifest.evidence_id))
        self.assertEstado(res, assess.RES_FOUND)

    def test_data_contract_result_found_para_data_contract_evaluation(self):
        manifest, _ = self._manifest_persistido()
        res = resolvers.data_contract_result_resolver(self.repo)(self._ref(manifest.evidence_id, "data_contract_result"))
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, manifest.content_sha256())

    def test_data_contract_result_con_subject_kind_erroneo_es_unverifiable(self):
        manifest, _ = self._manifest_persistido(subject="model_quality_evaluation", declaration_kind="model_quality_policy")
        res = resolvers.data_contract_result_resolver(self.repo)(self._ref(manifest.evidence_id, "data_contract_result"))
        self.assertEstado(res, assess.RES_UNVERIFIABLE)

    def test_missing_si_el_manifest_no_existe(self):
        for resolver in (
            resolvers.quality_evidence_resolver(self.repo),
            resolvers.data_contract_result_resolver(self.repo),
        ):
            self.assertEstado(resolver(self._ref("qe-20261001T100000Z-abcdef")), assess.RES_MISSING)

    def test_ref_id_malformado_o_con_rutas_es_unverifiable(self):
        self._manifest_persistido()
        resolver = resolvers.quality_evidence_resolver(self.repo)
        for ref_id in (
            "qe-1",
            "QE-20261001T100000Z-abcdef",
            "qe-20261001T100000Z-ABCDEF",
            "qe-20261001T100000Z-abcde",
            "../qe-20261001T100000Z-abcdef",
            "qe-20261001T100000Z-abcdef/..",
            "a/qe-20261001T100000Z-abcdef",
            "a\\qe-20261001T100000Z-abcdef",
            "/qe-20261001T100000Z-abcdef",
            "C:\\qe-20261001T100000Z-abcdef",
            "",
            None,
            7,
        ):
            with self.subTest(ref_id=ref_id):
                self.assertEstado(resolver(_falso(ref_id)), assess.RES_UNVERIFIABLE)

    def test_manifest_adulterado_con_hash_persistido_viejo_es_unverifiable(self):
        manifest, ruta = self._manifest_persistido()
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["scope"]["population"] = "otra poblacion"  # content_sha256 persistido queda viejo
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        res = resolvers.quality_evidence_resolver(self.repo)(self._ref(manifest.evidence_id))
        self.assertEstado(res, assess.RES_UNVERIFIABLE)

    def test_hash_persistido_ausente_o_invalido_es_unverifiable(self):
        manifest, ruta = self._manifest_persistido()
        original = json.loads(ruta.read_text(encoding="utf-8"))
        resolver = resolvers.quality_evidence_resolver(self.repo)
        for nombre, valor in (("faltante", None), ("corto", "abc"), ("mayusculas", "A" * 64), ("no_str", 5)):
            with self.subTest(caso=nombre):
                datos = {k: v for k, v in original.items() if k != "content_sha256"}
                if nombre != "faltante":
                    datos["content_sha256"] = valor
                ruta.write_text(json.dumps(datos), encoding="utf-8")
                self.assertEstado(resolver(self._ref(manifest.evidence_id)), assess.RES_UNVERIFIABLE)

    def test_evidence_id_interno_distinto_al_directorio_es_unverifiable(self):
        manifest, ruta = self._manifest_persistido()
        otro_id = "qe-20261001T100000Z-ffffff"
        self.assertNotEqual(otro_id, manifest.evidence_id)
        destino = self.repo / ".harmessi" / "quality" / otro_id
        destino.mkdir(parents=True)
        (destino / "manifest.json").write_bytes(ruta.read_bytes())
        res = resolvers.quality_evidence_resolver(self.repo)(self._ref(otro_id))
        self.assertEstado(res, assess.RES_UNVERIFIABLE)

    def test_cambio_solo_en_generated_at_no_rompe_la_integridad(self):
        manifest, ruta = self._manifest_persistido()
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["generated_at"] = "2030-01-01T00:00:00Z"
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        res = resolvers.quality_evidence_resolver(self.repo)(self._ref(manifest.evidence_id))
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, manifest.content_sha256())

    def test_json_corrupto_o_no_objeto_es_unverifiable(self):
        manifest, ruta = self._manifest_persistido()
        resolver = resolvers.quality_evidence_resolver(self.repo)
        for contenido in ("{", "[]", "null"):
            with self.subTest(contenido=contenido):
                ruta.write_text(contenido, encoding="utf-8")
                self.assertEstado(resolver(self._ref(manifest.evidence_id)), assess.RES_UNVERIFIABLE)

    def test_symlink_del_directorio_del_manifest_que_escapa(self):
        manifest = _manifest()
        _guardar_manifest(self.fuera, manifest)
        base = self.repo / ".harmessi" / "quality"
        base.mkdir(parents=True)
        _symlink(base / manifest.evidence_id, self.fuera / ".harmessi" / "quality" / manifest.evidence_id)
        res = resolvers.quality_evidence_resolver(self.repo)(self._ref(manifest.evidence_id))
        self.assertEstado(res, assess.RES_UNVERIFIABLE)

    def test_symlink_del_directorio_quality_que_escapa(self):
        manifest = _manifest()
        _guardar_manifest(self.fuera, manifest)
        (self.repo / ".harmessi").mkdir()
        _symlink(self.repo / ".harmessi" / "quality", self.fuera / ".harmessi" / "quality")
        res = resolvers.quality_evidence_resolver(self.repo)(self._ref(manifest.evidence_id))
        self.assertEstado(res, assess.RES_UNVERIFIABLE)

    def test_symlink_del_archivo_manifest_que_escapa(self):
        manifest = _manifest()
        ruta_fuera = Path(_guardar_manifest(self.fuera, manifest))
        directorio = self.repo / ".harmessi" / "quality" / manifest.evidence_id
        directorio.mkdir(parents=True)
        _symlink(directorio / "manifest.json", ruta_fuera, directorio=False)
        res = resolvers.quality_evidence_resolver(self.repo)(self._ref(manifest.evidence_id))
        self.assertEstado(res, assess.RES_UNVERIFIABLE)

    def test_evaluar_evidencia_fresh_y_stale(self):
        manifest, _ = self._manifest_persistido()
        defaults = resolvers.default_resolvers(self.repo)
        fresco = core.EvidenceRef("ev1", "quality_evidence", manifest.evidence_id, manifest.content_sha256(), T0)
        viejo = core.EvidenceRef("ev1", "quality_evidence", manifest.evidence_id, "e" * 64, T0)
        self.assertEqual(assess.evaluar_evidencia(fresco, defaults), assess.EV_FRESH)
        self.assertEqual(assess.evaluar_evidencia(viejo, defaults), assess.EV_STALE)


# ---------------------------------------------------------------------------
# default_resolvers (R24), robustez (nunca lanza) y solo lectura (R25)
# ---------------------------------------------------------------------------

CINCO_KINDS = {
    "source_observation",
    "source_provenance",
    "harmessi_contract",
    "quality_evidence",
    "data_contract_result",
}


class TestDefaultResolvers(_Base):
    def test_exactamente_los_quince_kinds(self):
        mapa = resolvers.default_resolvers(self.repo)
        self.assertEqual(set(mapa), set(core.OBSERVED_KINDS) - {"report_artifact"})
        self.assertTrue(CINCO_KINDS <= set(mapa))
        self.assertEqual(len(mapa), 15)
        for kind, resolver in mapa.items():
            with self.subTest(kind=kind):
                self.assertTrue(callable(resolver))
                self.assertIn(kind, core.OBSERVED_KINDS)

    def test_constantes_de_kind_coinciden_con_core(self):
        self.assertEqual(
            {
                resolvers.KIND_SOURCE_OBSERVATION,
                resolvers.KIND_SOURCE_PROVENANCE,
                resolvers.KIND_HARMESSI_CONTRACT,
                resolvers.KIND_QUALITY_EVIDENCE,
                resolvers.KIND_DATA_CONTRACT_RESULT,
            },
            CINCO_KINDS,
        )

    def test_los_demas_kinds_quedan_unverifiable(self):
        mapa = resolvers.default_resolvers(self.repo)
        for kind in set(core.OBSERVED_KINDS) - set(mapa):
            self.assertEqual(kind, "report_artifact")
            with self.subTest(kind=kind):
                ref = core.EvidenceRef("ev1", kind, "x-1", H, T0)
                self.assertEqual(assess.evaluar_evidencia(ref, mapa), assess.EV_UNVERIFIABLE)

    def test_repo_root_invalido_lanza_card_error(self):
        with self.assertRaises(core.CardError):
            resolvers.default_resolvers(None)


class TestNuncaLanzan(_Base):
    def _todos(self, repo):
        return resolvers.default_resolvers(repo)

    def _basura(self):
        return (
            None,
            5,
            "texto",
            b"bytes",
            object(),
            SimpleNamespace(),
            SimpleNamespace(ref_id=b"x", locator=5, member=[], kind=None),
            SimpleNamespace(ref_id="a" * 10000, locator="b" * 10000, member="provenance"),
            SimpleNamespace(ref_id="\x00", locator="\x00", member="\x00"),
            SimpleNamespace(ref_id="a__0123456789ab\x00", locator="a/\x00b.json", member="provenance"),
            _falso("qe-20261001T100000Z-abcdef", locator="contracts/c.json", member="provenance"),
        )

    def test_basura_nunca_lanza_y_nunca_es_found(self):
        _guardar_observacion(self.repo, _observacion())
        for kind, resolver in self._todos(self.repo).items():
            for i, basura in enumerate(self._basura()):
                with self.subTest(kind=kind, caso=i):
                    res = resolver(basura)
                    self.assertIsInstance(res, assess.Resolution)
                    self.assertNotEqual(res.state, assess.RES_FOUND)

    def test_repo_inexistente_no_lanza(self):
        inexistente = self.raiz / "no_existe"
        for kind, resolver in self._todos(inexistente).items():
            with self.subTest(kind=kind):
                ref = _falso("clientes__0123456789ab", locator="c.json", member="provenance")
                res = resolver(ref)
                self.assertIn(res.state, (assess.RES_MISSING, assess.RES_UNVERIFIABLE))

    def test_error_inesperado_de_io_se_convierte_en_unverifiable(self):
        _guardar_observacion(self.repo, _observacion())
        resolver = resolvers.source_observation_resolver(self.repo)
        with mock.patch.object(Path, "iterdir", side_effect=PermissionError("denegado")):
            res = resolver(_ref_obs())
        self.assertEstado(res, assess.RES_UNVERIFIABLE)

    def test_evaluar_evidencia_con_resolvers_reales_ante_basura_es_unverifiable(self):
        mapa = self._todos(self.repo)
        self.assertEqual(assess.evaluar_evidencia(_falso("../x"), mapa), assess.EV_UNVERIFIABLE)


class TestSinEscrituraEnDisco(_Base):
    def test_ningun_resolver_modifica_el_arbol(self):
        obs = _observacion()
        _guardar_observacion(self.repo, obs)
        _guardar_observacion(self.repo, _observacion(filas=99, generated_at="2026-10-02T00:00:00Z"))
        _guardar_contrato(self.repo, _contrato())
        manifest = _manifest()
        _guardar_manifest(self.repo, manifest)
        roto = self.repo / ".harmessi" / "observations" / f"roto__{HASH12_CERO}"
        roto.mkdir()
        (roto / "observation.json").write_text("{", encoding="utf-8")

        antes = _arbol(self.raiz)
        mapa = resolvers.default_resolvers(self.repo)
        refs = (
            _ref_obs(),
            _ref_obs("roto"),
            _ref_obs("inexistente"),
            _ref_obs(kind="source_provenance", member="provenance"),
            _ref("harmessi_contract", "contrato-clientes@1.0.0", locator="contracts/contrato.json"),
            _ref("harmessi_contract", "contrato-clientes@1.0.0", locator="contracts/no_esta.json"),
            _ref("quality_evidence", manifest.evidence_id),
            _ref("data_contract_result", manifest.evidence_id),
            _ref("quality_evidence", "qe-20261001T100000Z-abcdef"),
            _falso("../../x"),
        )
        for ref in refs:
            for resolver in mapa.values():
                resolver(ref)
        despues = _arbol(self.raiz)
        self.assertEqual(antes, despues)

    def test_no_crea_directorios_en_repo_vacio(self):
        antes = _arbol(self.raiz)
        for resolver in resolvers.default_resolvers(self.repo).values():
            resolver(_ref_obs())
            resolver(_falso("qe-20261001T100000Z-abcdef", locator="c.json"))
        self.assertEqual(_arbol(self.raiz), antes)
        self.assertFalse((self.repo / ".harmessi").exists())


if __name__ == "__main__":
    unittest.main()
