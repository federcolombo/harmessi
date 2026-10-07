"""Tests de inercia de la governance de modelos (v0.9 Change 3,
`20261005-model-risk-responsible-ai`, R1, R2, R3, R5, R6, R20, R65-R68, R8).

- `govpolicy.py` importa solo stdlib + `core`; `modelgov.py` solo stdlib + `core`,
  `assess`, `govpolicy` y (perezoso) `resolvers`. Ningún paquete prohibido a nivel de
  módulo; `dsguard` solo llega de forma perezosa vía `assess` (R1).
- Sin `importlib`, `__import__`, red ni subprocesos.
- `STOP_CATALOG`, `MANIFEST`, `CAPABILITIES_CONOCIDAS` intactos; los nombres de
  governance no aparecen en `ds_init`, `autonomy`, `harmessi`, `ds_guard`, Doctor (R66).
- `guardrails.json` no se lee (está protegido): se verifica por texto que los módulos no
  lo mencionan.
- Vocabularios `CARD_KINDS` / `OBSERVED_KINDS` con extensión aditiva (R3).
- `ModelCard` v1 y `DataCard` no cambian (R5, R6).
- Un assessment escrito con `write_governance_assessment` es project-owned: no altera
  `control.json['archivos']` ni produce drift de Doctor.
- Textos sin lenguaje de cumplimiento normativo (R20).

El snapshot de `STOP_CATALOG` replica el de `test_v09_modelcards_inert.py`: si se
cambia un STOP, ese cambio debe ser deliberado y editar todos los snapshots.
"""
from __future__ import annotations

import ast
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

from tools.autonomy import core as autonomy_core
from tools.cards import assess, core, govpolicy, modelcard, modelgov
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
    "modelcard",
    "datacard",
    "harmessi",
    "nbrunner",
)

# Paquetes externos a `cards` (los módulos hermanos de cards se verifican aparte).
PAQUETES_EXTERNOS = tuple(p for p in PAQUETES_PROHIBIDOS if p not in ("modelcard", "datacard"))

# Hermanos permitidos por módulo (import dual relativo / suelto).
HERMANOS_PERMITIDOS = {
    "govpolicy.py": {"core"},
    "modelgov.py": {"core", "assess", "govpolicy", "resolvers"},
}
# Hermanos permitidos a NIVEL DE MÓDULO (`resolvers` es perezoso en modelgov).
HERMANOS_A_NIVEL_DE_MODULO = {
    "govpolicy.py": {"core"},
    "modelgov.py": {"core", "assess", "govpolicy"},
}

_STDLIB_RESPALDO = {
    "__future__", "ast", "collections", "dataclasses", "datetime", "functools", "hashlib", "json",
    "os", "pathlib", "re", "sys", "tempfile", "typing", "unicodedata",
}

DIRECTORIOS_SIN_NOMBRES_FUTUROS = ("tools/ds_init", "tools/autonomy", "tools/harmessi")
# Enmiendas R75/R76 (Change 4, `20261005-cards-governance-integration`).
ARCHIVOS_NOMBRES_PERMITIDOS = (
    "tools/ds_init/manifest.py",
    "tools/ds_init/cli.py",
    "tools/harmessi/doctor.py",
    "tools/ds_guard.py",
)
PREFIJOS_NOMBRES_PERMITIDOS = ("tools/ds_init/tests/", "tools/harmessi/tests/")
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
NOMBRES_FUTUROS = ("model_governance", "data_cards", "modelgov", "govpolicy")
PAQUETES_QUE_NO_IMPORTAN_CARDS = ("modelquality", "qualityevidence", "datasources", "datacontracts")
NOMBRES_DE_MODULOS_GOV = ("govpolicy", "modelgov")

T0 = "2026-10-01T10:00:00Z"
NOW = "2026-10-02T00:00:00Z"
H = "a" * 64

# R20: nunca aparecen (ni siquiera negados).
_RE_MARCOS_PROHIBIDOS = re.compile(
    r"EU AI Act|\bAI Act\b|\bNIST\b|\bGDPR\b|\bRGPD\b|\bHIPAA\b|\bCCPA\b|\bSOC ?2\b|ISO[ /-]?\d|ISO/IEC",
    re.IGNORECASE,
)
# R20: solo con negación explícita en la misma línea o en la anterior/siguiente.
_RE_CLAIM_BLANDO = re.compile(r"compliance|compliant|conformidad|cumplimiento|certific|garantiz", re.IGNORECASE)
_RE_NEGACION = re.compile(r"\b(no|ni|nunca|sin|ning[uú]n[a]?|not)\b", re.IGNORECASE)


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


def _imports_a_nivel_de_modulo(ruta: Path) -> list:
    """Imports ejecutados al importar el módulo: recorre todo el árbol SIN bajar a
    funciones/lambdas/clases-método (sí a `try`/`if` de nivel módulo)."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    salida = []
    pendientes = list(arbol.body)
    while pendientes:
        nodo = pendientes.pop()
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                salida.append((0, alias.name, ()))
        elif isinstance(nodo, ast.ImportFrom):
            salida.append((nodo.level, nodo.module or "", tuple(a.name for a in nodo.names)))
        pendientes.extend(ast.iter_child_nodes(nodo))
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


def _es_produccion(ruta: Path, base: Path) -> bool:
    relativa = ruta.relative_to(base)
    return "tests" not in relativa.parts and not ruta.name.startswith("test_")


class TestImportsDeGovpolicyYModelgov(unittest.TestCase):
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

    def test_hermanos_a_nivel_de_modulo(self):
        """`resolvers` solo puede importarse de forma perezosa (dentro de funciones)."""
        for nombre, permitidos in HERMANOS_A_NIVEL_DE_MODULO.items():
            for nivel, modulo, nombres in _imports_a_nivel_de_modulo(DIR_CARDS / nombre):
                with self.subTest(archivo=nombre, nivel=nivel, modulo=modulo, nombres=nombres):
                    if nivel > 0:
                        candidatos = set(nombres) if modulo == "" else {modulo.split(".")[0]}
                        self.assertTrue(candidatos <= permitidos, f"hermanos no permitidos a nivel de módulo: {candidatos - permitidos}")
                    else:
                        raiz = modulo.split(".")[0]
                        if raiz in permitidos:
                            continue
                        self.assertTrue(_es_stdlib(raiz), f"no es stdlib ni hermano permitido: {modulo}")

    def test_modelgov_importa_resolvers_solo_de_forma_perezosa_y_existe_el_import(self):
        a_nivel = _imports_a_nivel_de_modulo(DIR_CARDS / "modelgov.py")
        for nivel, modulo, nombres in a_nivel:
            self.assertNotIn("resolvers", set(modulo.split(".")) | set(nombres))
        todos = _imports(DIR_CARDS / "modelgov.py")
        self.assertTrue(
            any("resolvers" in (set(modulo.split(".")) | set(nombres)) for _n, modulo, nombres in todos),
            "modelgov ya no importa resolvers: revisar R1",
        )

    def test_govpolicy_solo_importa_core_como_hermano(self):
        hermanos = set()
        for nivel, modulo, nombres in _imports(DIR_CARDS / "govpolicy.py"):
            if nivel > 0:
                hermanos |= set(nombres) if modulo == "" else {modulo.split(".")[0]}
            elif modulo.split(".")[0] in {"core", "assess", "resolvers", "modelgov", "modelcard", "datacard"}:
                hermanos.add(modulo.split(".")[0])
        self.assertEqual(hermanos, {"core"})

    def test_ningun_paquete_prohibido_a_nivel_de_modulo(self):
        for nombre in HERMANOS_PERMITIDOS:
            for nivel, modulo, nombres in _imports_a_nivel_de_modulo(DIR_CARDS / nombre):
                segmentos = set(modulo.split(".")) | set(nombres)
                with self.subTest(archivo=nombre, modulo=modulo):
                    self.assertFalse(segmentos & set(PAQUETES_PROHIBIDOS), f"import prohibido: {modulo} {nombres}")

    def test_ningun_paquete_prohibido_tampoco_de_forma_perezosa(self):
        """Ni siquiera perezoso: `dsguard` solo se alcanza vía `assess`."""
        for nombre in HERMANOS_PERMITIDOS:
            for nivel, modulo, nombres in _imports(DIR_CARDS / nombre):
                segmentos = set(modulo.split(".")) | set(nombres)
                with self.subTest(archivo=nombre, modulo=modulo):
                    self.assertFalse(segmentos & set(PAQUETES_PROHIBIDOS), f"import prohibido: {modulo} {nombres}")

    def test_govpolicy_y_modelgov_no_se_importan_entre_las_cards_previas(self):
        for nombre in ("core.py", "assess.py", "resolvers.py", "modelcard.py", "datacard.py"):
            ruta = DIR_CARDS / nombre
            if not ruta.is_file():
                continue
            for nivel, modulo, nombres in _imports(ruta):
                segmentos = set(modulo.split(".")) | set(nombres)
                with self.subTest(archivo=nombre, modulo=modulo):
                    self.assertFalse(segmentos & set(NOMBRES_DE_MODULOS_GOV), f"{nombre} importa governance: {modulo}")

    def test_sin_manipulacion_dinamica_de_imports(self):
        for nombre in HERMANOS_PERMITIDOS:
            arbol = ast.parse((DIR_CARDS / nombre).read_text(encoding="utf-8"))
            for nodo in ast.walk(arbol):
                with self.subTest(archivo=nombre, linea=getattr(nodo, "lineno", 0)):
                    if isinstance(nodo, ast.Name):
                        self.assertNotIn(nodo.id, ("importlib", "__import__"))
                    elif isinstance(nodo, ast.Attribute):
                        self.assertNotIn(nodo.attr, ("import_module", "__import__"))
                    elif isinstance(nodo, (ast.Import, ast.ImportFrom)):
                        nombres = [a.name for a in nodo.names] + [getattr(nodo, "module", None) or ""]
                        self.assertFalse(any("importlib" in n for n in nombres))

    def test_sin_red_ni_subprocesos(self):
        prohibidos = {"socket", "urllib", "http", "requests", "subprocess", "ftplib", "smtplib", "ssl", "asyncio"}
        for nombre in HERMANOS_PERMITIDOS:
            raices = {m.split(".")[0] for _n, m, _ in _imports(DIR_CARDS / nombre)}
            with self.subTest(archivo=nombre):
                self.assertFalse(raices & prohibidos)

    def test_sin_llamadas_a_funciones_de_ejecucion_dinamica(self):
        for nombre in HERMANOS_PERMITIDOS:
            arbol = ast.parse((DIR_CARDS / nombre).read_text(encoding="utf-8"))
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name):
                    with self.subTest(archivo=nombre, funcion=nodo.func.id):
                        self.assertNotIn(nodo.func.id, ("eval", "exec", "compile"))

    def test_ningun_modulo_de_cards_importa_paquetes_prohibidos_salvo_assess_perezoso_de_dsguard(self):
        for ruta in _py_de(DIR_CARDS, recursivo=False):
            if ruta.name in ADAPTADORES_NUEVOS:
                # Enmienda R76 (Change 4): adaptadores pueden importar dsguard/
                # reporting/ds_init; siguen prohibidos los demás paquetes.
                for nivel, modulo, nombres in _imports(ruta):
                    segmentos = set(modulo.split(".")) | set(nombres)
                    with self.subTest(archivo=ruta.name, modulo=modulo):
                        self.assertFalse(
                            segmentos & PROHIBIDOS_ADAPTADORES, f"import prohibido: {modulo} {nombres}"
                        )
                continue
            for nivel, modulo, nombres in _imports(ruta):
                segmentos = set(modulo.split(".")) | set(nombres)
                prohibidos = segmentos & set(PAQUETES_EXTERNOS)
                if ruta.name == "assess.py":
                    prohibidos -= {"dsguard"}
                with self.subTest(archivo=ruta.name, modulo=modulo):
                    self.assertFalse(prohibidos, f"import prohibido: {modulo} {nombres}")

    def test_assess_importa_dsguard_solo_de_forma_perezosa(self):
        a_nivel = _imports_a_nivel_de_modulo(DIR_CARDS / "assess.py")
        for nivel, modulo, nombres in a_nivel:
            self.assertNotIn("dsguard", set(modulo.split(".")) | set(nombres))

    def test_cards_no_importa_maturity_y_maturity_no_importa_cards(self):
        for ruta in _py_de(DIR_CARDS, recursivo=False):
            for nivel, modulo, nombres in _imports(ruta):
                with self.subTest(archivo=ruta.name, modulo=modulo):
                    self.assertNotIn("maturity", set(modulo.split(".")) | set(nombres))
        maturity = REPO_ORIGEN / "tools" / "dsguard" / "maturity.py"
        self.assertTrue(maturity.is_file())
        self.assertEqual(_importa_cards(_imports(maturity)), [])

    def test_ningun_nombre_de_guardrails_en_los_modulos(self):
        """`guardrails.json` está protegido y no se lee; se verifica por texto que
        governance no lo referencia."""
        for nombre in HERMANOS_PERMITIDOS:
            texto = (DIR_CARDS / nombre).read_text(encoding="utf-8").lower()
            with self.subTest(archivo=nombre):
                self.assertNotIn("guardrails", texto)


class TestStopCatalogYMetadatosInmutables(unittest.TestCase):
    def test_stop_catalog_igual_al_snapshot_literal(self):
        actual = tuple((e.number, e.code, e.key) for e in autonomy_core.STOP_CATALOG)
        self.assertEqual(actual, STOP_CATALOG_SNAPSHOT)
        self.assertEqual(len(autonomy_core.STOP_CATALOG), 12)

    def test_manifest_cards_exactos_sin_governance(self):
        # Enmienda R75 (Change 4): SOLO estos 12 módulos de tools/cards, sin tests/.
        destinos = [e.destino.replace("\\", "/") for e in MANIFEST]
        self.assertTrue(destinos, "MANIFEST vacío: el test sería vacuo")
        self.assertEqual(sorted(d for d in destinos if d.startswith("tools/cards")), sorted(DESTINOS_CARDS))
        self.assertEqual([d for d in destinos if "governance" in d.split("/")], [])
        self.assertEqual([d for d in destinos if d.startswith("governance")], [])
        self.assertEqual(
            [d for d in destinos if ("govpolicy" in d or "modelgov" in d) and d not in DESTINOS_CARDS], []
        )

    def test_capabilities_conocidas_sin_cambios(self):
        self.assertEqual(CAPABILITIES_CONOCIDAS, ("predictive_modeling",))
        self.assertEqual(CAPABILITIES_OPT_IN, ("data_cards", "model_governance"))

    def test_exclusiones_permanentes_incluyen_governance(self):
        # Enmienda R10 (Change 4): `governance/` es project-owned.
        exclusiones = [e.replace("\\", "/") for e in EXCLUSIONES_PERMANENTES]
        self.assertIn("governance/", exclusiones)

    def test_nombres_futuros_solo_en_lista_cerrada(self):
        # Enmienda R75: permitido solo en manifest/cli/doctor/ds_guard y sus tests;
        # `tools/autonomy/**` sin excepción.
        encontrados = []
        for directorio in DIRECTORIOS_SIN_NOMBRES_FUTUROS:
            modulos = _py_de(REPO_ORIGEN / directorio)
            self.assertTrue(modulos, f"{directorio} sin módulos: el test sería vacuo")
            for ruta in modulos:
                relativa = ruta.relative_to(REPO_ORIGEN).as_posix()
                if relativa in ARCHIVOS_NOMBRES_PERMITIDOS or relativa.startswith(PREFIJOS_NOMBRES_PERMITIDOS):
                    continue
                texto = ruta.read_text(encoding="utf-8")
                for nombre in NOMBRES_FUTUROS:
                    if nombre in texto:
                        encontrados.append(f"{relativa}: {nombre}")
        self.assertEqual(encontrados, [])

    def test_ds_guard_y_doctor_estan_en_la_lista_cerrada(self):
        for relativa in ("tools/ds_guard.py", "tools/harmessi/doctor.py"):
            self.assertIn(relativa, ARCHIVOS_NOMBRES_PERMITIDOS)
            self.assertTrue((REPO_ORIGEN / relativa).is_file(), relativa)

    def test_ningun_stop_menciona_governance_de_modelos(self):
        for entrada in autonomy_core.STOP_CATALOG:
            with self.subTest(codigo=entrada.code):
                for fragmento in ("govern", "gov_", "model_risk", "risk_level"):
                    self.assertNotIn(fragmento, entrada.key.lower())
                    self.assertNotIn(fragmento, entrada.code.lower())


class TestVocabulariosExtensionAditiva(unittest.TestCase):
    def test_card_kinds(self):
        self.assertEqual(core.CARD_KINDS, ("data_card", "model_card", "governance_assessment"))

    def test_los_diez_originales_son_prefijo_y_en_el_mismo_orden(self):
        self.assertEqual(core.OBSERVED_KINDS[:10], OBSERVED_KINDS_ORIGINALES)

    def test_agregados_en_orden_y_total_dieciseis(self):
        self.assertEqual(len(core.OBSERVED_KINDS), 16)
        self.assertEqual(core.OBSERVED_KINDS[10:13], OBSERVED_KINDS_AGREGADOS_MODEL_CARDS)
        self.assertEqual(core.OBSERVED_KINDS[13:16], OBSERVED_KINDS_AGREGADOS_GOBERNANZA)
        self.assertEqual(
            core.OBSERVED_KINDS[13:16], ("model_card", "governance_policy", "evidence_document")
        )

    def test_sin_duplicados(self):
        self.assertEqual(len(set(core.OBSERVED_KINDS)), len(core.OBSERVED_KINDS))

    def test_cards_serializadas_con_kinds_antiguos_siguen_siendo_validas(self):
        for kind in OBSERVED_KINDS_ORIGINALES + OBSERVED_KINDS_AGREGADOS_MODEL_CARDS:
            with self.subTest(kind=kind):
                ref = core.EvidenceRef("ev1", kind, "x-1", H, T0)
                self.assertEqual(core.EvidenceRef.from_dict(ref.to_dict()), ref)

    def test_round_trip_de_los_kinds_nuevos(self):
        for kind in OBSERVED_KINDS_AGREGADOS_GOBERNANZA:
            with self.subTest(kind=kind):
                ref = core.EvidenceRef("ev1", kind, "x-1", H, T0)
                self.assertEqual(core.EvidenceRef.from_dict(ref.to_dict()), ref)

    def test_kind_desconocido_sigue_rechazado(self):
        with self.assertRaises(core.CardError):
            core.EvidenceRef("ev1", "governance_assessment", "x-1", H, T0)


class TestNingunModuloDeProduccionImportaCards(unittest.TestCase):
    def test_paquetes_de_evidencia_de_v06_a_v08_no_importan_cards(self):
        ofensores = []
        revisados = 0
        for paquete in PAQUETES_QUE_NO_IMPORTAN_CARDS:
            directorio = REPO_ORIGEN / "tools" / paquete
            modulos = [r for r in _py_de(directorio) if _es_produccion(r, directorio)]
            self.assertTrue(modulos, f"{paquete} sin módulos: el test sería vacuo")
            for ruta in modulos:
                revisados += 1
                for ofensor in _importa_cards(_imports(ruta)):
                    ofensores.append(f"{paquete}/{ruta.name}: {ofensor}")
        self.assertGreater(revisados, 4)
        self.assertEqual(ofensores, [])

    def test_solo_tools_cards_importa_cards_ni_sus_modulos_de_governance(self):
        ofensores = []
        revisados = 0
        for ruta in _py_de(REPO_ORIGEN / "tools"):
            relativa = ruta.relative_to(REPO_ORIGEN / "tools")
            if relativa.parts[0] == "cards":
                continue
            if not _es_produccion(ruta, REPO_ORIGEN / "tools"):
                continue
            if relativa.as_posix() in IMPORTADORES_CARDS_PERMITIDOS:
                continue  # enmienda R75: lista cerrada (imports perezosos)
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
                if set(modulo.split(".")) & set(NOMBRES_DE_MODULOS_GOV) or set(nombres) & set(NOMBRES_DE_MODULOS_GOV):
                    ofensores.append(f"{relativa.as_posix()}: importa governance {modulo} {nombres}")
        self.assertGreater(revisados, 20, "el test sería vacuo")
        self.assertEqual(ofensores, [])


class TestModelCardYDataCardIntactas(unittest.TestCase):
    def _model_card(self, **body_extra):
        body = {"model_id": "clasificador", "model_version": "1.0", "description": "Clasificador de prueba"}
        body.update(body_extra)
        return core.CardEnvelope(
            schema_version=1,
            card_kind="model_card",
            kind_schema_version=1,
            card_id=modelcard.model_card_id("clasificador", "1.0"),
            title="Clasificador",
            subject="clasificador",
            created_at=T0,
            generated_at=T0,
            body=body,
        )

    def test_model_card_minima_valida(self):
        self.assertEqual(modelcard.validate_model_card(self._model_card()), [])

    def test_model_card_v1_sigue_rechazando_claves_rai_y_risk_level(self):
        for clave in ("risk_level", "fairness", "explainability", "privacy", "security", "accountability",
                      "human_oversight", "governance", "risk_declaration", "model_card_ref", "policy_ref"):
            with self.subTest(clave=clave):
                hallazgos = modelcard.validate_model_card(self._model_card(**{clave: "high"}))
                self.assertIn(modelcard.CODE_UNKNOWN_KEY, [h.code for h in hallazgos])

    def test_model_card_no_acepta_card_kind_de_governance(self):
        card = core.CardEnvelope(
            schema_version=1,
            card_kind="governance_assessment",
            kind_schema_version=1,
            card_id="clasificador__1_0",
            title="t",
            subject="clasificador",
            created_at=T0,
            generated_at=T0,
            body={},
        )
        self.assertNotEqual(modelcard.validate_model_card(card), [])

    def test_modelcard_y_datacard_no_mencionan_governance_de_modelos(self):
        for nombre in ("modelcard.py", "datacard.py"):
            texto = (DIR_CARDS / nombre).read_text(encoding="utf-8")
            for fragmento in ("govpolicy", "modelgov", "governance_assessment", "GOVASSESS", "GOVPOLICY"):
                with self.subTest(archivo=nombre, fragmento=fragmento):
                    self.assertNotIn(fragmento, texto)

    def test_datacard_intacta_en_su_kind(self):
        from tools.cards import datacard

        self.assertEqual(datacard.DATA_CARD_KIND, "data_card")
        self.assertIn("data_card", core.CARD_KINDS)


# ---------------------------------------------------------------------------
# Assessment project-owned: sin drift en Doctor, sin efectos al evaluar/validar
# ---------------------------------------------------------------------------


def _assessment(titulo="Assessment del clasificador"):
    cid = modelcard.model_card_id("clasificador", "1.0")
    pin = core.EvidenceRef(
        "mc-pin",
        "model_card",
        f"{cid}__{H[:12]}",
        H,
        T0,
        locator=f"governance/cards/model/{cid}.json",
    )
    efectiva = govpolicy.merge(govpolicy.BASE_POLICY)
    return core.CardEnvelope(
        schema_version=1,
        card_kind="governance_assessment",
        kind_schema_version=1,
        card_id=cid,
        title=titulo,
        subject="clasificador",
        created_at=T0,
        generated_at=T0,
        evidence=(pin,),
        body={
            "model_card_ref": {"evidence_id": "mc-pin"},
            "policy_ref": {
                "base_policy_id": govpolicy.BASE_POLICY.policy_id,
                "base_version": govpolicy.BASE_POLICY.version,
                "base_sha256": govpolicy.BASE_POLICY_SHA256,
                "effective_sha256": efectiva.effective_sha256(),
            },
        },
    )


def _reloj():
    return NOW


class TestAssessmentProjectOwned(unittest.TestCase):
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

    def test_el_assessment_de_prueba_es_valido(self):
        self.assertEqual(modelgov.validate_governance_assessment(_assessment()), [])
        self.assertEqual(
            core.validate_card(_assessment(), clock=_reloj, validate_body=modelgov.body_validator_for(_assessment())),
            [],
        )

    def test_write_governance_assessment_no_altera_control_json(self):
        antes = self.ruta_control.read_bytes()
        control_antes = json.loads(antes.decode("utf-8"))
        ruta = modelgov.write_governance_assessment(self.proyecto, _assessment(), clock=_reloj)
        self.assertTrue(Path(ruta).is_file())
        self.assertEqual(
            Path(ruta).relative_to(self.proyecto).as_posix(), "governance/model-risk/clasificador__1_0.json"
        )
        self.assertEqual(self.ruta_control.read_bytes(), antes)
        control_despues = json.loads(self.ruta_control.read_text(encoding="utf-8"))
        self.assertEqual(control_despues["archivos"], control_antes["archivos"])
        self.assertEqual([e["ruta"] for e in control_despues["archivos"]], ["tools/x.py"])

    def test_crear_editar_y_borrar_el_assessment_no_produce_drift_en_doctor(self):
        try:
            from tools.harmessi import doctor
        except Exception as exc:  # pragma: no cover - entorno sin dependencias de Doctor
            self.skipTest(f"no se pudo importar Doctor ({type(exc).__name__})")
        control = json.loads(self.ruta_control.read_text(encoding="utf-8"))

        def _assert_sin_drift(etapa):
            resultados = list(doctor._check_hashes_drift(self.proyecto, control))
            self.assertTrue(resultados, etapa)
            for r in resultados:
                self.assertEqual(r.code, "HARMESSI-DRIFT", f"{etapa}: {r.code}")
                self.assertEqual(r.status, "PASS", f"{etapa}: {r.status} {getattr(r, 'message', '')}")

        _assert_sin_drift("sin assessment")
        ruta = modelgov.write_governance_assessment(self.proyecto, _assessment(), clock=_reloj)
        _assert_sin_drift("assessment creado")
        modelgov.write_governance_assessment(
            self.proyecto, _assessment(titulo="Assessment revisado"), replace=True, clock=_reloj
        )
        _assert_sin_drift("assessment editado (replace)")
        Path(ruta).unlink()
        _assert_sin_drift("assessment borrado")

    def test_control_positivo_archivo_administrado_modificado_si_se_detecta(self):
        try:
            from tools.harmessi import doctor
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"no se pudo importar Doctor ({type(exc).__name__})")
        control = json.loads(self.ruta_control.read_text(encoding="utf-8"))
        (self.proyecto / "tools" / "x.py").write_text("print('modificado')\n", encoding="utf-8")
        resultados = doctor._check_hashes_drift(self.proyecto, control)
        self.assertTrue(any(r.status != "PASS" for r in resultados))

    def test_assessment_invalido_no_crea_governance(self):
        malo = core.CardEnvelope(
            schema_version=1,
            card_kind="governance_assessment",
            kind_schema_version=1,
            card_id="clasificador__1_0",
            title="t",
            subject="clasificador",
            created_at=T0,
            generated_at=T0,
            body={},  # model_card_ref / policy_ref obligatorios ausentes
        )
        with self.assertRaises(core.CardError):
            modelgov.write_governance_assessment(self.proyecto, malo, clock=_reloj)
        self.assertFalse((self.proyecto / "governance").exists())

    def test_card_de_otro_kind_no_crea_governance(self):
        otra = core.CardEnvelope(
            schema_version=1,
            card_kind="model_card",
            kind_schema_version=1,
            card_id="clasificador__1_0",
            title="t",
            subject="clasificador",
            created_at=T0,
            generated_at=T0,
            body={"model_id": "clasificador", "model_version": "1.0", "description": "d"},
        )
        with self.assertRaises(core.CardError):
            modelgov.write_governance_assessment(self.proyecto, otra, clock=_reloj)
        self.assertFalse((self.proyecto / "governance").exists())

    def test_validar_y_evaluar_no_crean_governance_ni_harmessi(self):
        self.assertEqual(modelgov.validate_governance_assessment(_assessment()), [])
        resultado = modelgov.evaluate_governance_assessment(_assessment(), self.proyecto, clock=_reloj)
        self.assertIn(resultado.governance_completeness, (assess.CARD_INCOMPLETE, assess.CARD_STALE, assess.CARD_INVALID))
        self.assertNotEqual(resultado.governance_completeness, assess.CARD_COMPLETE)
        self.assertFalse((self.proyecto / "governance").exists())
        self.assertFalse((self.proyecto / ".harmessi").exists())

    def test_evaluar_un_assessment_invalido_tampoco_crea_nada(self):
        malo = core.CardEnvelope(
            schema_version=1,
            card_kind="governance_assessment",
            kind_schema_version=1,
            card_id="clasificador__1_0",
            title="t",
            subject="clasificador",
            created_at=T0,
            generated_at=T0,
            body={},
        )
        resultado = modelgov.evaluate_governance_assessment(malo, self.proyecto, clock=_reloj)
        self.assertEqual(resultado.governance_completeness, assess.CARD_INVALID)
        self.assertFalse((self.proyecto / "governance").exists())
        self.assertFalse((self.proyecto / ".harmessi").exists())

    def test_el_proyecto_solo_tiene_lo_esperado_tras_validar(self):
        modelgov.validate_governance_assessment(_assessment())
        self.assertEqual(sorted(p.name for p in self.proyecto.iterdir()), [".ds_init", "tools"])


# ---------------------------------------------------------------------------
# R20: sin lenguaje de cumplimiento normativo
# ---------------------------------------------------------------------------


class TestSinLenguajeDeCumplimiento(unittest.TestCase):
    def test_marcos_y_leyes_no_aparecen_en_ningun_texto(self):
        for nombre in HERMANOS_PERMITIDOS:
            texto = (DIR_CARDS / nombre).read_text(encoding="utf-8")
            for m in _RE_MARCOS_PROHIBIDOS.finditer(texto):
                with self.subTest(archivo=nombre, termino=m.group(0)):
                    self.fail(f"{nombre} menciona un marco/ley: {m.group(0)!r}")

    def test_claims_de_cumplimiento_solo_con_negacion_explicita(self):
        for nombre in HERMANOS_PERMITIDOS:
            lineas = (DIR_CARDS / nombre).read_text(encoding="utf-8").splitlines()
            encontrados = 0
            for i, linea in enumerate(lineas):
                if not _RE_CLAIM_BLANDO.search(linea):
                    continue
                encontrados += 1
                contexto = " ".join(lineas[max(0, i - 1): i + 2])
                with self.subTest(archivo=nombre, linea=i + 1):
                    self.assertIsNotNone(
                        _RE_NEGACION.search(contexto), f"posible claim de cumplimiento sin negación: {linea.strip()!r}"
                    )
            self.assertGreaterEqual(encontrados, 0)

    def test_textos_de_runtime_sin_marcos_ni_claims(self):
        textos = [modelgov.NOTA_COMPLETENESS]
        textos += [r.description for r in govpolicy.BASE_POLICY.requirements]
        textos += [r.dimension for r in govpolicy.BASE_POLICY.requirements]
        for texto in textos:
            with self.subTest(texto=texto[:50]):
                self.assertIsNone(_RE_MARCOS_PROHIBIDOS.search(texto))
        # Las descripciones de la policy base nunca hablan de cumplimiento/certificación.
        for r in govpolicy.BASE_POLICY.requirements:
            with self.subTest(requisito=r.requirement_id):
                self.assertIsNone(_RE_CLAIM_BLANDO.search(r.description))
        # La nota solo menciona cumplimiento negado.
        self.assertIn("NO equivale", modelgov.NOTA_COMPLETENESS)

    def test_resultado_a_dict_lleva_la_nota_de_completeness(self):
        resultado = modelgov.GovernanceAssessment(governance_completeness=modelgov.GOV_INCOMPLETE)
        self.assertEqual(resultado.a_dict()["nota"], modelgov.NOTA_COMPLETENESS)


if __name__ == "__main__":
    unittest.main()
