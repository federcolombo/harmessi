"""Tests de inercia de `tools/cards` (v0.9 Change 0,
`20261002-card-and-evidence-foundation`, R3, R41, R42 y D1 de `spec.md`).

El paquete `tools/cards` no se cablea a nada en este change:
- `autonomy.core.STOP_CATALOG` queda idéntico a un snapshot literal (R3, D1:
  Cards/evidencia no son un STOP ni tocan autonomía).
- `tools/ds_init/manifest.MANIFEST` no tiene ningún destino bajo `tools/cards`
  (R42: se instala recién en Change 4 con capabilities) y
  `CAPABILITIES_CONOCIDAS` sigue siendo `("predictive_modeling",)`.
- `tools/ds_guard.py`, `tools/harmessi/doctor.py` y `tools/autonomy/*.py` no
  mencionan `cards` (R3, R41: un proyecto v0.8 se comporta idéntico).
- `data_cards` / `model_governance` (capabilities futuras) no aparecen en
  `tools/ds_init`, `tools/autonomy` ni `tools/harmessi`.

El snapshot de `STOP_CATALOG` se tomó del código actual de
`tools/autonomy/core.py` (`_STOP_CLAVES`, código `AUTONOMY-STOP-NN`). Si se
agrega o cambia un STOP, ese cambio debe ser deliberado y editar este snapshot
a propósito.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from tools.autonomy import core as autonomy_core
from tools.ds_init.manifest import CAPABILITIES_CONOCIDAS, MANIFEST

REPO_ORIGEN = Path(__file__).resolve().parents[2]

# (number, code, key) de cada entrada de `STOP_CATALOG`, en orden.
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

# Archivos/directorios que NO deben mencionar `cards` (subcadena, sin distinguir mayúsculas).
ARCHIVOS_SIN_CARDS = (
    "tools/ds_guard.py",
    "tools/harmessi/doctor.py",
)
DIRECTORIO_AUTONOMY = "tools/autonomy"

# Directorios donde no deben aparecer los nombres de capabilities futuras.
DIRECTORIOS_SIN_CAPABILITIES_FUTURAS = (
    "tools/ds_init",
    "tools/autonomy",
    "tools/harmessi",
)
CAPABILITIES_FUTURAS = ("data_cards", "model_governance")


def _leer(ruta_relativa: str) -> str:
    ruta = REPO_ORIGEN / ruta_relativa
    if not ruta.is_file():
        raise AssertionError(f"falta {ruta_relativa}")
    return ruta.read_text(encoding="utf-8")


def _py_de(directorio_relativo: str, recursivo: bool) -> list:
    directorio = REPO_ORIGEN / directorio_relativo
    if not directorio.is_dir():
        raise AssertionError(f"no existe el directorio {directorio_relativo}")
    candidatos = directorio.rglob("*.py") if recursivo else directorio.glob("*.py")
    return [ruta for ruta in sorted(candidatos) if "__pycache__" not in ruta.parts]


class TestStopCatalogInmutable(unittest.TestCase):
    def test_stop_catalog_igual_al_snapshot_literal(self):
        actual = tuple((e.number, e.code, e.key) for e in autonomy_core.STOP_CATALOG)
        self.assertEqual(actual, STOP_CATALOG_SNAPSHOT)

    def test_stop_catalog_tiene_12_entradas(self):
        self.assertEqual(len(autonomy_core.STOP_CATALOG), 12)
        self.assertEqual(len(STOP_CATALOG_SNAPSHOT), 12)

    def test_ningun_stop_menciona_cards(self):
        """D1: Cards/evidencia no introducen STOP (R3, R33)."""
        for entrada in autonomy_core.STOP_CATALOG:
            with self.subTest(codigo=entrada.code):
                self.assertNotIn("card", entrada.key.lower())
                self.assertNotIn("card", entrada.code.lower())

    def test_all_codes_no_contiene_codigos_card(self):
        for codigo in autonomy_core.ALL_CODES:
            self.assertFalse(codigo.startswith("CARD-"), codigo)


class TestManifestYCapabilitiesInertes(unittest.TestCase):
    def test_manifest_sin_destinos_bajo_tools_cards(self):
        destinos = [e.destino.replace("\\", "/") for e in MANIFEST]
        self.assertTrue(destinos, "MANIFEST vacío: el test sería vacuo")
        bajo_cards = [d for d in destinos if d.startswith("tools/cards")]
        self.assertEqual(
            bajo_cards,
            [],
            f"tools/cards no debe estar en MANIFEST en v0.9 Change 0 (R42; se instala en Change 4): {bajo_cards}",
        )

    def test_manifest_sin_destinos_que_mencionen_cards(self):
        """Más estricto que lo anterior: ningún destino contiene un segmento `cards`."""
        con_segmento = [
            e.destino
            for e in MANIFEST
            if "cards" in e.destino.replace("\\", "/").split("/")
        ]
        self.assertEqual(con_segmento, [])

    def test_capabilities_conocidas_sin_cambios(self):
        self.assertEqual(CAPABILITIES_CONOCIDAS, ("predictive_modeling",))


class TestArchivosExistentesNoMencionanCards(unittest.TestCase):
    def test_ds_guard_y_doctor_no_contienen_cards(self):
        for ruta in ARCHIVOS_SIN_CARDS:
            with self.subTest(archivo=ruta):
                self.assertNotIn("cards", _leer(ruta).lower())

    def test_autonomy_no_contiene_cards(self):
        modulos = _py_de(DIRECTORIO_AUTONOMY, recursivo=False)
        self.assertTrue(modulos, "tools/autonomy sin módulos: el test sería vacuo")
        for ruta in modulos:
            with self.subTest(archivo=ruta.name):
                self.assertNotIn("cards", ruta.read_text(encoding="utf-8").lower())


class TestCapabilitiesFuturasAusentes(unittest.TestCase):
    def test_data_cards_y_model_governance_no_aparecen(self):
        encontrados = []
        for directorio in DIRECTORIOS_SIN_CAPABILITIES_FUTURAS:
            modulos = _py_de(directorio, recursivo=True)
            self.assertTrue(modulos, f"{directorio} sin módulos: el test sería vacuo")
            for ruta in modulos:
                texto = ruta.read_text(encoding="utf-8")
                for nombre in CAPABILITIES_FUTURAS:
                    if nombre in texto:
                        encontrados.append(f"{ruta.relative_to(REPO_ORIGEN).as_posix()}: {nombre}")
        self.assertEqual(
            encontrados,
            [],
            f"capabilities futuras (data_cards/model_governance) no deben aparecer todavía: {encontrados}",
        )


if __name__ == "__main__":
    unittest.main()
