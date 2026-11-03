"""Tests de inercia de las Data Cards (v0.9 Change 1, `20261002-data-cards`,
R1, R2, R29, R32, R37, R38 de `spec.md`).

- `resolvers.py` y `datacard.py` solo importan stdlib y hermanos `core`/`assess`
  (+ `resolvers` de forma perezosa desde `datacard`): nunca `datasources`,
  `qualityevidence`, `datacontracts`, `modelquality`, `autonomy`, `leadrun`,
  `reporting`, `ds_init` ni `ds_guard` (R1).
- `STOP_CATALOG`, `MANIFEST`, `CAPABILITIES_CONOCIDAS`, `EXCLUSIONES_PERMANENTES`
  y `.ds_init/control.json` quedan intactos (R2, R38).
- Ningún módulo de producción fuera de `tools/cards` importa `cards`.
- Una Card escrita con `write_data_card` es project-owned: no altera
  `control.json['archivos']` ni produce drift de Doctor (R29).

El snapshot de `STOP_CATALOG` replica el de `test_v09_cards_inert.py`: si se
cambia un STOP, ese cambio debe ser deliberado y editar ambos snapshots.
"""
from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

from tools.autonomy import core as autonomy_core
from tools.cards import core, datacard
from tools.ds_init import control as control_mod
from tools.ds_init.manifest import (
    CAPABILITIES_CONOCIDAS,
    CAPABILITIES_OPT_IN,
    EXCLUSIONES_PERMANENTES,
    MANIFEST,
)

REPO_ORIGEN = Path(__file__).resolve().parents[2]
DIR_CARDS = REPO_ORIGEN / "tools" / "cards"

STOP_CATALOG_SNAPSHOT = (
    (1, "AUTONOMY-STOP-01", "sealed_access"),
    (2, "AUTONOMY-STOP-02", "unlisted_methodological_decision"),
    (3, "AUTONOMY-STOP-03", "leakage_doubt"),
    (4, "AUTONOMY-STOP-04", "new_dependency"),
    (5, "AUTONOMY-STOP-05", "write_outside_scope"),
    (6, "AUTONOMY-STOP-06", "secret_required"),
    (7, "AUTONOMY-STOP-07", "data_loss_risk"),
    (8, "AUTONOMY-STOP-08", "remediation_exhausted"),
    (9, "AUTONOMY-STOP-09", "approach_refuted"),
    (10, "AUTONOMY-STOP-10", "requirement_contradiction"),
    (11, "AUTONOMY-STOP-11", "scope_expansion"),
    (12, "AUTONOMY-STOP-12", "bypass_needed"),
)

PAQUETES_PROHIBIDOS = (
    "datasources",
    "qualityevidence",
    "datacontracts",
    "modelquality",
    "autonomy",
    "leadrun",
    "reporting",
    "ds_init",
    "ds_guard",
    "dsguard",
    "harmessi",
    "nbrunner",
)

# Hermanos permitidos por módulo (import dual relativo / suelto).
HERMANOS_PERMITIDOS = {
    "resolvers.py": {"core", "assess"},
    "datacard.py": {"core", "assess", "resolvers"},
    "modelcard.py": {"core", "assess", "resolvers"},
    "govpolicy.py": {"core"},
    "modelgov.py": {"core", "assess", "govpolicy", "resolvers"},
}

_STDLIB_RESPALDO = {
    "__future__", "ast", "collections", "dataclasses", "datetime", "functools", "hashlib", "json",
    "os", "pathlib", "re", "sys", "tempfile", "typing", "unicodedata",
}

DIRECTORIOS_SIN_CAPABILITIES_FUTURAS = ("tools/ds_init", "tools/autonomy", "tools/harmessi")
# Enmiendas R75/R76 (Change 4, `20261005-cards-governance-integration`).
ARCHIVOS_CAPABILITIES_PERMITIDOS = (
    "tools/ds_init/manifest.py",
    "tools/ds_init/cli.py",
    "tools/harmessi/doctor.py",
    "tools/ds_guard.py",
)
PREFIJOS_CAPABILITIES_PERMITIDOS = ("tools/ds_init/tests/", "tools/harmessi/tests/")
IMPORTADORES_CARDS_PERMITIDOS = ("harmessi/doctor.py", "ds_guard.py")  # relativos a tools/
ADAPTADORES_NUEVOS = ("approvals.py", "discovery.py", "report.py", "govconfig.py")
PROHIBIDOS_ADAPTADORES = {
    "autonomy", "leadrun", "modelquality", "qualityevidence", "datasources", "datacontracts",
}
DESTINOS_CARDS = tuple(
    f"tools/cards/{n}.py"
    for n in (
        "__init__", "core", "assess", "resolvers", "approvals", "discovery",
        "report", "datacard", "modelcard", "govpolicy", "modelgov", "govconfig",
    )
)
CAPABILITIES_FUTURAS = ("data_cards", "model_governance")

H = "a" * 64
T0 = "2026-10-01T10:00:00Z"
NOW = "2026-10-02T00:00:00Z"


def _es_stdlib(nombre_raiz: str) -> bool:
    nombres = getattr(sys, "stdlib_module_names", None)
    if nombres is not None:
        return nombre_raiz in nombres
    return nombre_raiz in _STDLIB_RESPALDO


def _imports(ruta: Path) -> list:
    """Lista de `(nivel, modulo, nombres)` de TODOS los imports del archivo
    (incluidos los perezosos dentro de funciones)."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    salida = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                salida.append((0, alias.name, ()))
        elif isinstance(nodo, ast.ImportFrom):
            salida.append((nodo.level, nodo.module or "", tuple(a.name for a in nodo.names)))
    return salida


def _py_de(directorio: Path, recursivo: bool = True) -> list:
    candidatos = directorio.rglob("*.py") if recursivo else directorio.glob("*.py")
    return [r for r in sorted(candidatos) if "__pycache__" not in r.parts]


class TestImportsDeDatacardYResolvers(unittest.TestCase):
    def test_los_modulos_existen(self):
        for nombre in HERMANOS_PERMITIDOS:
            self.assertTrue((DIR_CARDS / nombre).is_file(), nombre)

    def test_solo_stdlib_y_hermanos_permitidos(self):
        for nombre, permitidos in HERMANOS_PERMITIDOS.items():
            for nivel, modulo, nombres in _imports(DIR_CARDS / nombre):
                with self.subTest(archivo=nombre, nivel=nivel, modulo=modulo, nombres=nombres):
                    if nivel > 0:
                        # `from . import a, b` o `from .mod import x`
                        candidatos = set(nombres) if modulo == "" else {modulo.split(".")[0]}
                        self.assertTrue(candidatos <= permitidos, f"hermanos no permitidos: {candidatos - permitidos}")
                    else:
                        raiz = modulo.split(".")[0]
                        if raiz in permitidos:  # import dual suelto (`import core`)
                            continue
                        self.assertTrue(_es_stdlib(raiz), f"no es stdlib ni hermano permitido: {modulo}")

    def test_ningun_paquete_prohibido_se_importa(self):
        for nombre in HERMANOS_PERMITIDOS:
            for nivel, modulo, nombres in _imports(DIR_CARDS / nombre):
                segmentos = set(modulo.split(".")) | set(nombres)
                with self.subTest(archivo=nombre, modulo=modulo):
                    self.assertFalse(segmentos & set(PAQUETES_PROHIBIDOS), f"import prohibido: {modulo} {nombres}")

    def test_sin_manipulacion_dinamica_de_imports_en_resolvers_y_datacard(self):
        for nombre in HERMANOS_PERMITIDOS:
            texto = (DIR_CARDS / nombre).read_text(encoding="utf-8")
            with self.subTest(archivo=nombre):
                self.assertNotIn("importlib", texto)
                self.assertNotIn("__import__", texto)

    def test_sin_red_ni_subprocesos(self):
        for nombre in HERMANOS_PERMITIDOS:
            raices = {m.split(".")[0] for _n, m, _ in _imports(DIR_CARDS / nombre)}
            with self.subTest(archivo=nombre):
                self.assertFalse(raices & {"socket", "urllib", "http", "requests", "subprocess", "ftplib", "smtplib"})

    def test_ningun_modulo_de_cards_importa_paquetes_prohibidos_salvo_assess_perezoso_de_dsguard(self):
        """Foundation (Change 0): `assess` importa `dsguard.checks` de forma
        perezosa (R1 de Change 0). Los demás módulos de producción de `tools/cards`
        no importan ningún paquete prohibido."""
        for ruta in _py_de(DIR_CARDS, recursivo=False):
            if ruta.name in ADAPTADORES_NUEVOS:
                # Enmienda R76 (Change 4): los 4 adaptadores pueden importar
                # dsguard/reporting/ds_init; siguen prohibidos los demás paquetes.
                for nivel, modulo, nombres in _imports(ruta):
                    segmentos = set(modulo.split(".")) | set(nombres)
                    with self.subTest(archivo=ruta.name, modulo=modulo):
                        self.assertFalse(
                            segmentos & PROHIBIDOS_ADAPTADORES, f"import prohibido: {modulo} {nombres}"
                        )
                continue
            for nivel, modulo, nombres in _imports(ruta):
                segmentos = set(modulo.split(".")) | set(nombres)
                prohibidos = segmentos & set(PAQUETES_PROHIBIDOS)
                if ruta.name == "assess.py":
                    prohibidos -= {"dsguard"}
                with self.subTest(archivo=ruta.name, modulo=modulo):
                    self.assertFalse(prohibidos, f"import prohibido: {modulo} {nombres}")


class TestStopCatalogYMetadatosInmutables(unittest.TestCase):
    def test_stop_catalog_igual_al_snapshot_literal(self):
        actual = tuple((e.number, e.code, e.key) for e in autonomy_core.STOP_CATALOG)
        self.assertEqual(actual, STOP_CATALOG_SNAPSHOT)
        self.assertEqual(len(autonomy_core.STOP_CATALOG), 12)

    def test_ningun_stop_menciona_cards(self):
        for entrada in autonomy_core.STOP_CATALOG:
            with self.subTest(codigo=entrada.code):
                self.assertNotIn("card", entrada.key.lower())
                self.assertNotIn("card", entrada.code.lower())

    def test_manifest_cards_exactos_y_sin_governance(self):
        # Enmienda R75 (Change 4): tools/cards se distribuye, y SOLO estos 12 módulos.
        destinos = [e.destino.replace("\\", "/") for e in MANIFEST]
        self.assertTrue(destinos, "MANIFEST vacío: el test sería vacuo")
        self.assertEqual(sorted(d for d in destinos if d.startswith("tools/cards")), sorted(DESTINOS_CARDS))
        self.assertEqual([d for d in destinos if "governance" in d.split("/")], [])
        self.assertEqual(
            [d for d in destinos if "cards" in d.split("/") and d not in DESTINOS_CARDS], []
        )
        self.assertEqual([d for d in destinos if d.startswith("governance")], [])

    def test_capabilities_conocidas_sin_cambios(self):
        self.assertEqual(CAPABILITIES_CONOCIDAS, ("predictive_modeling",))

    def test_data_cards_y_model_governance_solo_en_lista_cerrada(self):
        # Enmienda R75: permitido solo en la lista cerrada (manifest, cli, doctor,
        # ds_guard y sus tests); `tools/autonomy/**` sin excepción.
        encontrados = []
        for directorio in DIRECTORIOS_SIN_CAPABILITIES_FUTURAS:
            modulos = _py_de(REPO_ORIGEN / directorio)
            self.assertTrue(modulos, f"{directorio} sin módulos: el test sería vacuo")
            for ruta in modulos:
                relativa = ruta.relative_to(REPO_ORIGEN).as_posix()
                if relativa in ARCHIVOS_CAPABILITIES_PERMITIDOS or relativa.startswith(
                    PREFIJOS_CAPABILITIES_PERMITIDOS
                ):
                    continue
                texto = ruta.read_text(encoding="utf-8")
                for nombre in CAPABILITIES_FUTURAS:
                    if nombre in texto:
                        encontrados.append(f"{relativa}: {nombre}")
        self.assertEqual(encontrados, [])

    def test_capabilities_opt_in(self):
        self.assertEqual(CAPABILITIES_OPT_IN, ("data_cards", "model_governance"))

    def test_autonomy_no_menciona_datacard_ni_cards(self):
        # Enmienda R75: ds_guard.py y doctor.py ya pueden mencionar cards/datacard.
        archivos = _py_de(REPO_ORIGEN / "tools" / "autonomy", recursivo=False)
        for ruta in archivos:
            texto = ruta.read_text(encoding="utf-8").lower()
            with self.subTest(archivo=ruta.name):
                self.assertNotIn("datacard", texto)
                self.assertNotIn("tools.cards", texto)


class TestGovernanceAunNoGestionado(unittest.TestCase):
    def test_governance_cards_no_esta_en_control_json(self):
        ruta = REPO_ORIGEN / ".ds_init" / "control.json"
        if not ruta.is_file():
            self.skipTest("el repo de origen no tiene .ds_init/control.json")
        control = json.loads(ruta.read_text(encoding="utf-8"))
        rutas = [str(e.get("ruta", "")).replace("\\", "/") for e in control.get("archivos", []) if isinstance(e, dict)]
        self.assertTrue(rutas, "control.json sin archivos: el test sería vacuo")
        self.assertEqual([r for r in rutas if r.startswith("governance/") or "governance/cards" in r], [])
        self.assertNotIn("governance/cards", ruta.read_text(encoding="utf-8"))

    def test_governance_esta_en_exclusiones_permanentes(self):
        # Enmienda R10 (Change 4): `governance/` es project-owned; el instalador
        # jamás despliega ahí.
        exclusiones = [e.replace("\\", "/") for e in EXCLUSIONES_PERMANENTES]
        self.assertIn("governance/", exclusiones)


class TestNingunModuloDeProduccionImportaCards(unittest.TestCase):
    def test_solo_tools_cards_importa_cards(self):
        ofensores = []
        revisados = 0
        for ruta in _py_de(REPO_ORIGEN / "tools"):
            relativa = ruta.relative_to(REPO_ORIGEN / "tools")
            if relativa.parts[0] == "cards":
                continue
            if "tests" in relativa.parts or ruta.name.startswith("test_"):
                continue
            if relativa.as_posix() in IMPORTADORES_CARDS_PERMITIDOS:
                continue  # enmienda R75: lista cerrada (perezosos)
            revisados += 1
            try:
                importados = _imports(ruta)
            except SyntaxError:
                continue
            for nivel, modulo, nombres in importados:
                segmentos = modulo.split(".") if modulo else []
                if nivel == 0 and ("cards" in segmentos or (segmentos[-1:] == ["tools"] and "cards" in nombres)):
                    ofensores.append(f"{relativa.as_posix()}: {modulo} {nombres}")
                elif nivel > 0 and ("cards" in segmentos or (modulo == "" and "cards" in nombres)):
                    ofensores.append(f"{relativa.as_posix()}: {'.' * nivel}{modulo} {nombres}")
                elif nivel == 0 and modulo in ("tools",) and "cards" in nombres:
                    ofensores.append(f"{relativa.as_posix()}: from tools import cards")
        self.assertGreater(revisados, 20, "el test sería vacuo")
        self.assertEqual(ofensores, [])


# ---------------------------------------------------------------------------
# R29: la Card es project-owned y no produce drift
# ---------------------------------------------------------------------------


def _card(card_id="clientes-card", titulo="Clientes"):
    # Regla I3 de v0.8: ref_id de observación == f"{source_id}__{content_sha256[:12]}".
    evidencia = core.EvidenceRef("obs-clientes", "source_observation", f"clientes__{H[:12]}", H, T0)
    claim = core.Claim("c1", "fuente observada", supports=("obs-clientes",), requirement_id="source_principal")
    return core.CardEnvelope(
        schema_version=1,
        card_kind="data_card",
        kind_schema_version=1,
        card_id=card_id,
        title=titulo,
        subject="clientes",
        created_at=T0,
        generated_at=T0,
        evidence=(evidencia,),
        attestations=(),
        claims=(claim,),
        body={
            "description": "Tabla de clientes",
            "source_refs": [
                {"source_ref_id": "principal", "source_id": "clientes", "observation_evidence_id": "obs-clientes"}
            ],
        },
    )


def _reloj():
    return NOW


class TestCardProjectOwned(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.proyecto = Path(self._tmp.name)
        # Proyecto mínimo con un archivo administrado y control.json real.
        (self.proyecto / "tools").mkdir()
        (self.proyecto / "tools" / "x.py").write_text("print('x')\n", encoding="utf-8")
        control_mod.generar_control(
            self.proyecto,
            "python-jupyter-data",
            {"nombre": "demo", "notebooks_dir": "notebooks", "venv_dir": ".venv"},
            ["tools/x.py"],
            fecha_utc="2026-10-01T00:00:00Z",
        )
        self.ruta_control = self.proyecto / ".ds_init" / "control.json"

    def test_write_data_card_no_altera_control_json(self):
        antes = self.ruta_control.read_bytes()
        control_antes = json.loads(antes.decode("utf-8"))
        ruta = datacard.write_data_card(self.proyecto, _card(), clock=_reloj)
        self.assertTrue(Path(ruta).is_file())
        self.assertEqual(Path(ruta).relative_to(self.proyecto).as_posix(), "governance/cards/data/clientes-card.json")
        self.assertEqual(self.ruta_control.read_bytes(), antes)
        control_despues = json.loads(self.ruta_control.read_text(encoding="utf-8"))
        self.assertEqual(control_despues["archivos"], control_antes["archivos"])
        self.assertEqual([e["ruta"] for e in control_despues["archivos"]], ["tools/x.py"])

    def test_crear_editar_y_borrar_la_card_no_produce_drift_en_doctor(self):
        try:
            from tools.harmessi import doctor
        except Exception as exc:  # pragma: no cover - entorno sin dependencias de Doctor
            self.skipTest(f"no se pudo importar Doctor ({type(exc).__name__})")
        control = json.loads(self.ruta_control.read_text(encoding="utf-8"))

        def _drift():
            return [r for r in doctor._check_hashes_drift(self.proyecto, control)]

        def _assert_sin_drift(etapa):
            resultados = _drift()
            self.assertTrue(resultados, etapa)
            for r in resultados:
                self.assertEqual(r.code, "HARMESSI-DRIFT", f"{etapa}: {r.code}")
                self.assertEqual(r.status, "PASS", f"{etapa}: {r.status} {getattr(r, 'message', '')}")

        _assert_sin_drift("sin card")
        ruta = datacard.write_data_card(self.proyecto, _card(), clock=_reloj)
        _assert_sin_drift("card creada")
        datacard.write_data_card(self.proyecto, _card(titulo="Clientes v2"), replace=True, clock=_reloj)
        _assert_sin_drift("card editada")
        Path(ruta).unlink()
        _assert_sin_drift("card borrada")

    def test_el_archivo_administrado_modificado_si_se_detecta_como_control_positivo(self):
        try:
            from tools.harmessi import doctor
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"no se pudo importar Doctor ({type(exc).__name__})")
        control = json.loads(self.ruta_control.read_text(encoding="utf-8"))
        (self.proyecto / "tools" / "x.py").write_text("print('modificado')\n", encoding="utf-8")
        resultados = doctor._check_hashes_drift(self.proyecto, control)
        self.assertTrue(any(r.status != "PASS" for r in resultados))

    def test_card_invalida_no_crea_governance(self):
        invalida = _card()
        malo = core.CardEnvelope(
            schema_version=1,
            card_kind="data_card",
            kind_schema_version=1,
            card_id="clientes-card",
            title="t",
            subject="clientes",
            created_at=T0,
            generated_at=T0,
            body={},  # source_refs obligatorio ausente
        )
        self.assertNotEqual(invalida.body, malo.body)
        with self.assertRaises(core.CardError):
            datacard.write_data_card(self.proyecto, malo, clock=_reloj)
        self.assertFalse((self.proyecto / "governance").exists())


if __name__ == "__main__":
    unittest.main()
