"""Tests de inercia de las Model Cards (v0.9 Change 2, `20261005-model-cards`,
R1, R2, R32, R37, R38 de `spec.md`).

- `modelcard.py` y `resolvers.py` solo importan stdlib y hermanos
  `core`/`assess` (+ `resolvers` de forma perezosa desde `modelcard`): nunca
  `modelquality`, `qualityevidence`, `datasources`, `datacontracts`, `autonomy`,
  `leadrun`, `reporting`, `ds_init` ni `ds_guard` (R1).
- `STOP_CATALOG`, `MANIFEST`, `CAPABILITIES_CONOCIDAS` quedan intactos (R2, R38).
- `model_governance` / `data_cards` / `modelcard` no aparecen en `ds_init`,
  `autonomy`, `harmessi`, `ds_guard` ni Doctor (R38).
- `modelquality`, `qualityevidence`, `datasources` y `datacontracts` no importan
  `cards`.
- `OBSERVED_KINDS` conserva el orden de los 10 originales como prefijo (R3).
- Una Model Card escrita con `write_model_card` es project-owned: no altera
  `control.json['archivos']` ni produce drift de Doctor (R32).

El snapshot de `STOP_CATALOG` replica el de `test_v09_cards_inert.py`: si se
cambia un STOP, ese cambio debe ser deliberado y editar todos los snapshots.
"""
from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

from tools.autonomy import core as autonomy_core
from tools.cards import core, modelcard
from tools.ds_init import control as control_mod
from tools.ds_init.manifest import CAPABILITIES_CONOCIDAS, EXCLUSIONES_PERMANENTES, MANIFEST

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

OBSERVED_KINDS_ORIGINALES = (
    "source_observation",
    "source_provenance",
    "data_contract_result",
    "quality_evidence",
    "observed_metric",
    "baseline_reference",
    "drift_evidence",
    "execution_record",
    "report_artifact",
    "harmessi_contract",
)
OBSERVED_KINDS_AGREGADOS_MODEL_CARDS = ("data_card", "model_quality_result", "model_quality_policy")
OBSERVED_KINDS_AGREGADOS_GOBERNANZA = ("model_card", "governance_policy", "evidence_document")

PAQUETES_PROHIBIDOS = (
    "modelquality",
    "qualityevidence",
    "datasources",
    "datacontracts",
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
    "modelcard.py": {"core", "assess", "resolvers"},
    "govpolicy.py": {"core"},
    "modelgov.py": {"core", "assess", "govpolicy", "resolvers"},
}

_STDLIB_RESPALDO = {
    "__future__", "ast", "collections", "dataclasses", "datetime", "functools", "hashlib", "json",
    "os", "pathlib", "re", "sys", "tempfile", "typing", "unicodedata",
}

DIRECTORIOS_SIN_NOMBRES_FUTUROS = ("tools/ds_init", "tools/autonomy", "tools/harmessi")
NOMBRES_FUTUROS = ("model_governance", "data_cards", "modelcard")
PAQUETES_QUE_NO_IMPORTAN_CARDS = ("modelquality", "qualityevidence", "datasources", "datacontracts")

T0 = "2026-10-01T10:00:00Z"
NOW = "2026-10-02T00:00:00Z"
H = "a" * 64


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


def _importa_cards(importados: list) -> list:
    ofensores = []
    for nivel, modulo, nombres in importados:
        segmentos = modulo.split(".") if modulo else []
        if nivel == 0 and ("cards" in segmentos or (segmentos[-1:] == ["tools"] and "cards" in nombres)):
            ofensores.append(f"{modulo} {nombres}")
        elif nivel > 0 and ("cards" in segmentos or (modulo == "" and "cards" in nombres)):
            ofensores.append(f"{'.' * nivel}{modulo} {nombres}")
    return ofensores


class TestImportsDeModelcardYResolvers(unittest.TestCase):
    def test_los_modulos_existen(self):
        for nombre in HERMANOS_PERMITIDOS:
            self.assertTrue((DIR_CARDS / nombre).is_file(), nombre)

    def test_solo_stdlib_y_hermanos_permitidos(self):
        for nombre, permitidos in HERMANOS_PERMITIDOS.items():
            for nivel, modulo, nombres in _imports(DIR_CARDS / nombre):
                with self.subTest(archivo=nombre, nivel=nivel, modulo=modulo, nombres=nombres):
                    if nivel > 0:
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

    def test_resolvers_no_importa_modelcard_ni_datacard(self):
        for nivel, modulo, nombres in _imports(DIR_CARDS / "resolvers.py"):
            segmentos = set(modulo.split(".")) | set(nombres)
            self.assertFalse(segmentos & {"modelcard", "datacard"}, f"resolvers importa una Card: {modulo} {nombres}")

    def test_modelcard_importa_resolvers_solo_de_forma_perezosa(self):
        arbol = ast.parse((DIR_CARDS / "modelcard.py").read_text(encoding="utf-8"))
        a_nivel_modulo = []
        for nodo in arbol.body:  # solo sentencias top-level (sin bajar a funciones)
            if isinstance(nodo, ast.ImportFrom):
                a_nivel_modulo.append((nodo.module or "", tuple(a.name for a in nodo.names)))
            elif isinstance(nodo, ast.Import):
                a_nivel_modulo.extend((a.name, ()) for a in nodo.names)
        for modulo, nombres in a_nivel_modulo:
            self.assertNotIn("resolvers", set(modulo.split(".")) | set(nombres))

    def test_sin_manipulacion_dinamica_de_imports(self):
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
        for ruta in _py_de(DIR_CARDS, recursivo=False):
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

    def test_manifest_sin_cards_ni_governance(self):
        destinos = [e.destino.replace("\\", "/") for e in MANIFEST]
        self.assertTrue(destinos, "MANIFEST vacío: el test sería vacuo")
        segmentos_prohibidos = {"cards", "governance"}
        self.assertEqual([d for d in destinos if segmentos_prohibidos & set(d.split("/"))], [])
        self.assertEqual([d for d in destinos if d.startswith(("tools/cards", "governance"))], [])

    def test_capabilities_conocidas_sin_cambios(self):
        self.assertEqual(CAPABILITIES_CONOCIDAS, ("predictive_modeling",))

    def test_exclusiones_permanentes_sin_governance(self):
        exclusiones = [e.replace("\\", "/") for e in EXCLUSIONES_PERMANENTES]
        self.assertEqual([e for e in exclusiones if e.startswith("governance") or "governance/cards" in e], [])

    def test_nombres_futuros_no_aparecen_en_ds_init_autonomy_harmessi(self):
        encontrados = []
        for directorio in DIRECTORIOS_SIN_NOMBRES_FUTUROS:
            modulos = _py_de(REPO_ORIGEN / directorio)
            self.assertTrue(modulos, f"{directorio} sin módulos: el test sería vacuo")
            for ruta in modulos:
                texto = ruta.read_text(encoding="utf-8")
                for nombre in NOMBRES_FUTUROS:
                    if nombre in texto:
                        encontrados.append(f"{ruta.relative_to(REPO_ORIGEN).as_posix()}: {nombre}")
        self.assertEqual(encontrados, [])

    def test_nombres_futuros_no_aparecen_en_ds_guard_ni_doctor(self):
        archivos = [REPO_ORIGEN / "tools" / "ds_guard.py", REPO_ORIGEN / "tools" / "harmessi" / "doctor.py"]
        for ruta in archivos:
            self.assertTrue(ruta.is_file(), ruta)
            texto = ruta.read_text(encoding="utf-8")
            for nombre in NOMBRES_FUTUROS:
                with self.subTest(archivo=ruta.name, nombre=nombre):
                    self.assertNotIn(nombre, texto)
            with self.subTest(archivo=ruta.name, nombre="tools.cards"):
                self.assertNotIn("tools.cards", texto)

    def test_ningun_stop_menciona_cards(self):
        for entrada in autonomy_core.STOP_CATALOG:
            with self.subTest(codigo=entrada.code):
                self.assertNotIn("card", entrada.key.lower())
                self.assertNotIn("card", entrada.code.lower())


class TestObservedKindsExtensionAditiva(unittest.TestCase):
    def test_los_diez_originales_son_prefijo_y_en_el_mismo_orden(self):
        self.assertEqual(core.OBSERVED_KINDS[:10], OBSERVED_KINDS_ORIGINALES)

    def test_los_agregados_de_model_cards_estan_presentes_al_final_del_prefijo_de_trece(self):
        self.assertEqual(len(core.OBSERVED_KINDS), 16)
        self.assertEqual(core.OBSERVED_KINDS[10:13], OBSERVED_KINDS_AGREGADOS_MODEL_CARDS)
        self.assertEqual(core.OBSERVED_KINDS[13:16], OBSERVED_KINDS_AGREGADOS_GOBERNANZA)

    def test_sin_duplicados(self):
        self.assertEqual(len(set(core.OBSERVED_KINDS)), len(core.OBSERVED_KINDS))

    def test_cards_serializadas_con_kinds_originales_siguen_siendo_validas(self):
        for kind in OBSERVED_KINDS_ORIGINALES:
            with self.subTest(kind=kind):
                ref = core.EvidenceRef("ev1", kind, "x-1", H, T0)
                self.assertEqual(core.EvidenceRef.from_dict(ref.to_dict()), ref)


class TestNingunModuloDeProduccionImportaCards(unittest.TestCase):
    def test_paquetes_de_evidencia_de_v06_a_v08_no_importan_cards(self):
        ofensores = []
        revisados = 0
        for paquete in PAQUETES_QUE_NO_IMPORTAN_CARDS:
            directorio = REPO_ORIGEN / "tools" / paquete
            modulos = [
                r
                for r in _py_de(directorio)
                if "tests" not in r.relative_to(directorio).parts and not r.name.startswith("test_")
            ]
            self.assertTrue(modulos, f"{paquete} sin módulos: el test sería vacuo")
            for ruta in modulos:
                revisados += 1
                for ofensor in _importa_cards(_imports(ruta)):
                    ofensores.append(f"{paquete}/{ruta.name}: {ofensor}")
        self.assertGreater(revisados, 4)
        self.assertEqual(ofensores, [])

    def test_solo_tools_cards_importa_cards(self):
        ofensores = []
        revisados = 0
        for ruta in _py_de(REPO_ORIGEN / "tools"):
            relativa = ruta.relative_to(REPO_ORIGEN / "tools")
            if relativa.parts[0] == "cards":
                continue
            if "tests" in relativa.parts or ruta.name.startswith("test_"):
                continue
            revisados += 1
            try:
                importados = _imports(ruta)
            except SyntaxError:
                continue
            for ofensor in _importa_cards(importados):
                ofensores.append(f"{relativa.as_posix()}: {ofensor}")
            for nivel, modulo, nombres in importados:
                if nivel == 0 and modulo == "tools" and "cards" in nombres:
                    ofensores.append(f"{relativa.as_posix()}: from tools import cards")
        self.assertGreater(revisados, 20, "el test sería vacuo")
        self.assertEqual(ofensores, [])


# ---------------------------------------------------------------------------
# R32: la Model Card es project-owned y no produce drift
# ---------------------------------------------------------------------------


def _card(model_id="clasificador", version="1.0", titulo="Clasificador"):
    return core.CardEnvelope(
        schema_version=1,
        card_kind="model_card",
        kind_schema_version=1,
        card_id=modelcard.model_card_id(model_id, version),
        title=titulo,
        subject=model_id,
        created_at=T0,
        generated_at=T0,
        body={"model_id": model_id, "model_version": version, "description": "Clasificador de prueba"},
    )


def _reloj():
    return NOW


class TestModelCardProjectOwned(unittest.TestCase):
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

    def test_write_model_card_no_altera_control_json(self):
        antes = self.ruta_control.read_bytes()
        control_antes = json.loads(antes.decode("utf-8"))
        ruta = modelcard.write_model_card(self.proyecto, _card(), clock=_reloj)
        self.assertTrue(Path(ruta).is_file())
        self.assertEqual(
            Path(ruta).relative_to(self.proyecto).as_posix(), "governance/cards/model/clasificador__1_0.json"
        )
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
        ruta = modelcard.write_model_card(self.proyecto, _card(), clock=_reloj)
        _assert_sin_drift("card creada")
        modelcard.write_model_card(self.proyecto, _card(titulo="Clasificador v1 revisado"), replace=True, clock=_reloj)
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
        malo = core.CardEnvelope(
            schema_version=1,
            card_kind="model_card",
            kind_schema_version=1,
            card_id="clasificador__1_0",
            title="t",
            subject="clasificador",
            created_at=T0,
            generated_at=T0,
            body={},  # model_id / model_version / description obligatorios ausentes
        )
        with self.assertRaises(core.CardError):
            modelcard.write_model_card(self.proyecto, malo, clock=_reloj)
        self.assertFalse((self.proyecto / "governance").exists())

    def test_importar_y_validar_no_crea_governance(self):
        self.assertEqual(modelcard.validate_model_card(_card()), [])
        modelcard.evaluate_model_card(_card(), self.proyecto, clock=_reloj)
        self.assertFalse((self.proyecto / "governance").exists())
        self.assertFalse((self.proyecto / ".harmessi").exists())


if __name__ == "__main__":
    unittest.main()
