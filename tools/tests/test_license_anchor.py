"""Ancla de licencia v1.0 (Change 20261102-v1-release-hardening, R1/R5).

Verifica: LICENSE == golden PolyForm Shield 1.0.0 (normalizando CRLF), NOTICE con
`Required Notice:`, barrido de terminos de licencia obsoletos con allowlist
explicita por patron, y el asset HARMESSI-LICENSE.txt (que no es un LICENSE)."""
import re
import unittest
from pathlib import Path

from tools.ds_init.manifest import MANIFEST

RAIZ = Path(__file__).resolve().parents[2]
GOLDEN = RAIZ / "tools" / "tests" / "fixtures" / "license" / "polyform-shield-1.0.0.md"

# Terminos que no deben aparecer en la documentacion de licencia de v1.x.
RE_PROHIBIDOS = re.compile(r"apache|open source", re.IGNORECASE)

# Allowlist MINIMA por patron de linea (no por archivo). Una linea con un termino
# prohibido solo se acepta si cumple alguno de estos patrones.
ALLOWLIST_LINEA = (
    re.compile(r"v0\.x", re.IGNORECASE),                        # marcador historico
    re.compile(r"versiones anteriores", re.IGNORECASE),         # marcador historico
    re.compile(r"\b(?:no|not) open source\b", re.IGNORECASE),   # negacion explicita
    re.compile(r"source available", re.IGNORECASE),             # posicionamiento correcto
)


def lineas_prohibidas(texto):
    """Devuelve las lineas con 'Apache'/'open source' que no cumplen la allowlist."""
    return [
        linea for linea in texto.splitlines()
        if RE_PROHIBIDOS.search(linea) and not any(p.search(linea) for p in ALLOWLIST_LINEA)
    ]


def _archivos_barrido():
    fijos = ["LICENSE", "NOTICE", "CITATION.cff", "README.md",
             "HARMESSI-LICENSE.txt", "COMMERCIAL-LICENSE.md"]
    rutas = [RAIZ / f for f in fijos]
    rutas += sorted((RAIZ / "docs").glob("*.md"))  # no recursivo: excluye roadmap/ y releases/
    return [p for p in rutas if p.is_file()]


def _leer(ruta):
    return Path(ruta).read_bytes().decode("utf-8").replace("\r\n", "\n")


class TestLicenciaAncla(unittest.TestCase):
    def test_license_igual_al_golden(self):
        self.assertEqual(_leer(RAIZ / "LICENSE"), _leer(GOLDEN))

    def test_notice_tiene_required_notice(self):
        self.assertIn("Required Notice:", _leer(RAIZ / "NOTICE"))

    def test_barrido_sin_terminos_obsoletos(self):
        archivos = _archivos_barrido()
        self.assertIn("LICENSE", {p.name for p in archivos})
        for ruta in archivos:
            with self.subTest(archivo=ruta.relative_to(RAIZ).as_posix()):
                self.assertEqual(lineas_prohibidas(_leer(ruta)), [])


class TestAllowlist(unittest.TestCase):
    def test_apache_sin_marcador_historico_falla(self):
        self.assertEqual(
            lineas_prohibidas("Distribuido bajo Apache License 2.0."),
            ["Distribuido bajo Apache License 2.0."])

    def test_open_source_sin_negacion_falla(self):
        self.assertTrue(lineas_prohibidas("Harmessi es open source."))

    def test_lineas_permitidas(self):
        for linea in ("Las v0.x se publicaron bajo Apache License 2.0.",
                      "Ver versiones anteriores (Apache License 2.0).",
                      "Es source available, no open source.",
                      "It is not open source."):
            with self.subTest(linea):
                self.assertEqual(lineas_prohibidas(linea), [])


class TestAssetLicencia(unittest.TestCase):
    def setUp(self):
        self.texto = _leer(RAIZ / "HARMESSI-LICENSE.txt")

    def test_contenido_minimo(self):
        self.assertIn("PolyForm Shield", self.texto)
        self.assertIn("Required Notice:", self.texto)
        self.assertIn("polyformproject.org/licenses/shield/1.0.0", self.texto)
        self.assertIn("COMMERCIAL-LICENSE.md", self.texto)
        self.assertIn("no relicencia", self.texto.lower())
        self.assertIn("does not relicense", self.texto.lower())

    def test_sin_crlf(self):
        self.assertNotIn(b"\r", (RAIZ / "HARMESSI-LICENSE.txt").read_bytes())

    def test_ningun_destino_license_en_manifest(self):
        destinos = [e.destino for e in MANIFEST]
        self.assertNotIn("LICENSE", destinos)
        self.assertIn("HARMESSI-LICENSE.txt", destinos)


if __name__ == "__main__":
    unittest.main()
