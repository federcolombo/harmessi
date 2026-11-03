"""Tests deterministas de las docs públicas (v0.15 C6, B-26..B-30, B-34).

Verifican existencia, enlaces relativos, cobertura de subcomandos de ds_guard,
identidad de la suite pública, `.gitattributes` y frases de límite que no deben
quitarse sin observación real.
"""

import ast
import json
import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

DOCS_REQUERIDOS = [
    "installation",
    "concepts",
    "cli-reference",
    "evaluation",
    "security-and-trust",
    "release-process",
]
RUTAS_DOCS = [RAIZ / "docs" / f"{nombre}.md" for nombre in DOCS_REQUERIDOS]
SUITE_JSON = RAIZ / "tools" / "harmessi_bench" / "suites" / "harmessi-core-synthetic.suite.json"
DS_GUARD = RAIZ / "tools" / "ds_guard.py"

_RE_ENLACE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _leer(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8")


def _sin_bloques_codigo(texto: str) -> str:
    """Quita los bloques cercados con ``` (o ~~~)."""
    salida = []
    dentro = False
    for linea in texto.splitlines():
        if linea.lstrip().startswith(("```", "~~~")):
            dentro = not dentro
            continue
        if not dentro:
            salida.append(linea)
    return "\n".join(salida)


def _enlaces_relativos(ruta: Path):
    texto = _sin_bloques_codigo(_leer(ruta))
    for destino in _RE_ENLACE.findall(texto):
        destino = destino.strip().strip("<>")
        if not destino or destino.startswith("#"):
            continue
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", destino):  # http:, https:, mailto:, etc.
            continue
        destino = destino.split("#", 1)[0]
        if destino:
            yield destino


def _subcomandos_ds_guard():
    """Subcomandos top-level: `subparsers.add_parser("x")` en `construir_parser`."""
    arbol = ast.parse(_leer(DS_GUARD))
    nombres = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.FunctionDef) and nodo.name == "construir_parser":
            for sub in ast.walk(nodo):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "add_parser"
                    and isinstance(sub.func.value, ast.Name)
                    and sub.func.value.id == "subparsers"
                    and sub.args
                    and isinstance(sub.args[0], ast.Constant)
                    and isinstance(sub.args[0].value, str)
                ):
                    nombres.append(sub.args[0].value)
    return nombres


class TestDocsPublicas(unittest.TestCase):
    def test_docs_existen_y_no_vacios(self):
        for ruta in RUTAS_DOCS:
            with self.subTest(doc=ruta.name):
                self.assertTrue(ruta.is_file(), f"falta {ruta.name}")
                self.assertTrue(_leer(ruta).strip(), f"{ruta.name} está vacío")

    def test_enlaces_relativos_existen(self):
        for ruta in [RAIZ / "README.md", *RUTAS_DOCS]:
            self.assertTrue(ruta.is_file(), f"falta {ruta.name}")
            for destino in _enlaces_relativos(ruta):
                with self.subTest(archivo=ruta.name, enlace=destino):
                    objetivo = (ruta.parent / destino).resolve()
                    self.assertTrue(
                        objetivo.exists(),
                        f"{ruta.name}: enlace roto -> {destino}",
                    )

    def test_cli_reference_menciona_cada_subcomando(self):
        subcomandos = _subcomandos_ds_guard()
        self.assertGreater(len(subcomandos), 10, "no se extrajeron subcomandos de ds_guard")
        texto = _leer(RAIZ / "docs" / "cli-reference.md")
        for nombre in subcomandos:
            with self.subTest(subcomando=nombre):
                self.assertIn(nombre, texto)

    def test_evaluation_contiene_identidad_de_suite(self):
        from tools.harmessi_bench.suite import load_suite_y_casos

        manifest = json.loads(SUITE_JSON.read_text(encoding="utf-8-sig"))
        suite, _escenarios = load_suite_y_casos(SUITE_JSON)
        texto = _leer(RAIZ / "docs" / "evaluation.md")
        for campo in ("suite_id", "suite_version", "suite_hash"):
            self.assertIn(campo, texto)
        self.assertIn(manifest["suite_id"], texto)
        self.assertIn(suite.suite_hash, texto)
        for case_id in manifest["case_ids"]:
            with self.subTest(case_id=case_id):
                self.assertIn(case_id, texto)

    def test_gitattributes_patrones_lf(self):
        ruta = RAIZ / ".gitattributes"
        self.assertTrue(ruta.is_file(), "falta .gitattributes")
        lineas = [l.strip() for l in _leer(ruta).splitlines() if l.strip() and not l.strip().startswith("#")]
        for patron in ("tools/tests/fixtures/compat/**", "golden_*.json", "templates/**"):
            with self.subTest(patron=patron):
                self.assertTrue(
                    any(patron in l and "eol=lf" in l for l in lineas),
                    f"patrón {patron} sin eol=lf",
                )

    def test_release_process_pending_observation(self):
        # CI remoto no observado: no quitar la frase sin observar de verdad (B-30).
        self.assertIn("pending observation", _leer(RAIZ / "docs" / "release-process.md"))

    def test_evaluation_declara_limite_de_baseline(self):
        texto = _leer(RAIZ / "docs" / "evaluation.md")
        self.assertIn("baseline numérico", texto)
        self.assertIn("no", texto)
        self.assertIn("publica", texto)


if __name__ == "__main__":
    unittest.main()
