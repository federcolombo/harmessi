"""Tests estructurales de neutralidad del core de v0.6 (Change 0,
`20260918-reporting-core`). Mismo patrón `ast` que
`tools/tests/test_v05_core_neutrality.py`, pero escaneando TODOS los imports
del archivo (`ast.walk`, incluidos los anidados en funciones), no solo los de
nivel de módulo.

Verifica (R1/R14):
- `tools/reporting/core.py` importa únicamente de la stdlib permitida y no
  usa identificadores de librerías gráficas/tabulares ni de `dsguard`.
- `tools/reporting/__init__.py` no tiene cuerpo (salvo docstring): no acopla la
  instalación de `core.py` a módulos futuros.
- Dirección inversa de la regla 6 de ARCHITECTURE.md: ningún módulo de
  `dsguard`, `ds_profile`, `dsimpact`, `providers`, `routing`, `fallback` ni
  `harmessi_bench` importa `reporting` (con cualquier estilo de import).
- `MODULOS_CORE` de `test_architecture_boundaries.py` incluye el core.
"""
from __future__ import annotations

import ast
import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]

CORE_REPORTING = "tools/reporting/core.py"
INIT_REPORTING = "tools/reporting/__init__.py"

IMPORTS_PERMITIDOS = {"__future__", "dataclasses", "hashlib", "json", "math", "re", "copy", "typing"}

# Fragmentos que ningún identificador de `core.py` puede contener.
FRAGMENTOS_PROHIBIDOS = ("plotly", "pandas", "numpy", "html", "dsguard")

PAQUETES_SIN_REPORTING = (
    "tools/dsguard",
    "tools/ds_profile",
    "tools/dsimpact",
    "tools/providers",
    "tools/routing",
    "tools/fallback",
    "tools/harmessi_bench",
)


def _parsear(ruta_absoluta: Path) -> ast.AST:
    return ast.parse(ruta_absoluta.read_text(encoding="utf-8"), filename=str(ruta_absoluta))


def _todos_los_imports(ruta_absoluta: Path) -> list:
    """Lista de `(modulo_raiz, nombre_completo)` de TODOS los imports del
    archivo (`ast.walk`). Un import relativo se reporta con raíz `.` (nunca
    permitido en `core.py`)."""
    resultado = []
    for nodo in ast.walk(_parsear(ruta_absoluta)):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                resultado.append((alias.name.split(".")[0], alias.name))
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level and nodo.level > 0:
                resultado.append((".", "." * nodo.level + (nodo.module or "")))
            else:
                resultado.append((nodo.module.split(".")[0], nodo.module))
    return resultado


def _violaciones_whitelist(ruta_absoluta: Path) -> list:
    """Nombres importados (en cualquier parte del archivo) fuera del set permitido."""
    return [
        nombre
        for raiz, nombre in _todos_los_imports(ruta_absoluta)
        if raiz not in IMPORTS_PERMITIDOS
    ]


def _identificadores(ruta_absoluta: Path) -> list:
    """Todos los identificadores del archivo: nombres, atributos, defs/clases,
    argumentos, keywords y nombres importados (no incluye string literals)."""
    ids = []
    for nodo in ast.walk(_parsear(ruta_absoluta)):
        if isinstance(nodo, ast.Name):
            ids.append(nodo.id)
        elif isinstance(nodo, ast.Attribute):
            ids.append(nodo.attr)
        elif isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            ids.append(nodo.name)
        elif isinstance(nodo, ast.arg):
            ids.append(nodo.arg)
        elif isinstance(nodo, ast.keyword) and nodo.arg:
            ids.append(nodo.arg)
        elif isinstance(nodo, ast.alias):
            ids.append(nodo.name)
            if nodo.asname:
                ids.append(nodo.asname)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            ids.append(nodo.module)
    return ids


def _referencias_a_reporting(ruta_absoluta: Path) -> list:
    """Imports del archivo que apuntan a `reporting` con cualquier estilo:
    `import tools.reporting[.x]`, `import reporting`, `from tools.reporting[.x]
    import y`, `from reporting import y`, `from tools import reporting`,
    `from . import reporting`, `from .reporting import y`."""
    encontradas = []
    for nodo in ast.walk(_parsear(ruta_absoluta)):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                partes = alias.name.split(".")
                if partes[0] == "reporting" or partes[:2] == ["tools", "reporting"]:
                    encontradas.append(f"import {alias.name}")
        elif isinstance(nodo, ast.ImportFrom):
            partes = nodo.module.split(".") if nodo.module else []
            if partes and (partes[0] == "reporting" or partes[:2] == ["tools", "reporting"]):
                encontradas.append(f"from {'.' * nodo.level}{nodo.module} import ...")
            for alias in nodo.names:
                if alias.name == "reporting" and (not nodo.module or nodo.module == "tools"):
                    encontradas.append(f"from {'.' * nodo.level}{nodo.module or ''} import reporting")
    return encontradas


class TestCoreReportingSoloStdlib(unittest.TestCase):
    def test_core_existe(self):
        self.assertTrue((REPO_ORIGEN / CORE_REPORTING).is_file())

    def test_imports_de_core_pertenecen_al_set_permitido(self):
        violaciones = _violaciones_whitelist(REPO_ORIGEN / CORE_REPORTING)
        self.assertEqual(
            violaciones,
            [],
            f"tools/reporting/core.py importa fuera de la stdlib permitida {sorted(IMPORTS_PERMITIDOS)}: "
            f"{violaciones}",
        )

    def test_core_no_referencia_librerias_ni_hermanos_prohibidos(self):
        prohibidos = {"plotly", "pandas", "numpy", "html", "dsguard", "ds_profile", "tools", "reporting"}
        for raiz, nombre in _todos_los_imports(REPO_ORIGEN / CORE_REPORTING):
            partes = set(nombre.split("."))
            self.assertFalse(prohibidos & partes, f"import prohibido en core.py: {nombre}")

    def test_identificadores_de_core_no_referencian_librerias_ni_dsguard(self):
        violaciones = [
            identificador
            for identificador in _identificadores(REPO_ORIGEN / CORE_REPORTING)
            if any(f in identificador.lower() for f in FRAGMENTOS_PROHIBIDOS)
        ]
        self.assertEqual(violaciones, [], f"identificadores prohibidos en core.py: {violaciones}")

    def test_init_de_reporting_esta_vacio(self):
        arbol = _parsear(REPO_ORIGEN / INIT_REPORTING)
        cuerpo = list(arbol.body)
        if (
            cuerpo
            and isinstance(cuerpo[0], ast.Expr)
            and isinstance(cuerpo[0].value, ast.Constant)
            and isinstance(cuerpo[0].value.value, str)
        ):
            cuerpo = cuerpo[1:]
        self.assertEqual(cuerpo, [], "tools/reporting/__init__.py no debe tener lógica ni imports")
        self.assertEqual(_todos_los_imports(REPO_ORIGEN / INIT_REPORTING), [])


class TestCoreEnModulosCore(unittest.TestCase):
    def test_modulos_core_de_architecture_boundaries_incluye_reporting_core(self):
        ruta = REPO_ORIGEN / "tools" / "tests" / "test_architecture_boundaries.py"
        especificacion = importlib.util.spec_from_file_location("_arch_boundaries_v06", ruta)
        modulo = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(modulo)
        self.assertIn(CORE_REPORTING, modulo.MODULOS_CORE)


class TestNingunPaqueteImportaReporting(unittest.TestCase):
    def test_ningun_modulo_de_los_paquetes_previos_importa_reporting(self):
        violaciones = []
        for paquete in PAQUETES_SIN_REPORTING:
            directorio = REPO_ORIGEN / paquete
            self.assertTrue(directorio.is_dir(), f"no existe el paquete {paquete}")
            for ruta in sorted(directorio.rglob("*.py")):
                if "__pycache__" in ruta.parts or "tests" in ruta.relative_to(directorio).parts:
                    continue
                for referencia in _referencias_a_reporting(ruta):
                    violaciones.append(f"{ruta.relative_to(REPO_ORIGEN).as_posix()}: {referencia}")
        self.assertEqual(
            violaciones,
            [],
            "Módulo(s) que importan `reporting` -- prohibido por la regla 6 de ARCHITECTURE.md "
            f"(la dependencia es solo reporting -> dsguard/ds_profile): {violaciones}",
        )


# Change 5 (F5): el "core" de validación/profiles no conoce la capa de presentación ni el CLI.
MODULOS_DE_PRESENTACION = {"style", "render_html", "plotly_backend", "publish", "cli"}


def _importa_presentacion(ruta_absoluta: Path) -> list:
    """Imports (`ast.walk`, incluidos los anidados) que apuntan a style, render_html,
    plotly_backend, publish o cli, con cualquier estilo (`from . import style`,
    `from .style import x`, `from tools.reporting import cli`, `import tools.reporting.publish`)."""
    encontrados = []
    for nodo in ast.walk(_parsear(ruta_absoluta)):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                if MODULOS_DE_PRESENTACION & set(alias.name.split(".")):
                    encontrados.append(f"import {alias.name}")
        elif isinstance(nodo, ast.ImportFrom):
            partes = set(nodo.module.split(".")) if nodo.module else set()
            nombres = {alias.name for alias in nodo.names}
            if MODULOS_DE_PRESENTACION & (partes | nombres):
                encontrados.append(f"from {'.' * nodo.level}{nodo.module or ''} import {', '.join(sorted(nombres))}")
    return encontrados


class TestValidacionYProfilesNoConocenPresentacion(unittest.TestCase):
    def _archivos(self) -> list:
        archivos = [REPO_ORIGEN / "tools/reporting/validation.py"]
        archivos += sorted((REPO_ORIGEN / "tools/reporting/profiles").glob("*.py"))
        return archivos

    def test_hay_archivos_que_escanear(self):
        archivos = self._archivos()
        self.assertGreaterEqual(len(archivos), 3)  # validation + __init__ + eda
        for ruta in archivos:
            self.assertTrue(ruta.is_file(), ruta)

    def test_validation_y_profiles_no_importan_style_render_backend_publish_ni_cli(self):
        violaciones = []
        for ruta in self._archivos():
            for referencia in _importa_presentacion(ruta):
                violaciones.append(f"{ruta.relative_to(REPO_ORIGEN).as_posix()}: {referencia}")
        self.assertEqual(
            violaciones,
            [],
            "validation/profiles no deben conocer style, render_html, plotly_backend, publish ni cli "
            f"(ARCHITECTURE.md regla 6): {violaciones}",
        )

    def test_el_detector_encuentra_una_violacion_real(self):
        estilos = (
            "from . import style\n",
            "from .style import default_style\n",
            "from .render_html import render_report_html\n",
            "from tools.reporting import cli\n",
            "import tools.reporting.publish\n",
            "def f():\n    from .. import plotly_backend\n",
        )
        with tempfile.TemporaryDirectory() as tmp:
            for i, codigo in enumerate(estilos):
                ruta = Path(tmp) / f"v{i}.py"
                ruta.write_text(codigo, encoding="utf-8")
                self.assertTrue(_importa_presentacion(ruta), f"no detectó: {codigo!r}")
            limpio = Path(tmp) / "limpio.py"
            limpio.write_text(
                "import json\nfrom . import core as reporting_core\nfrom . import evidence\n"
                "from .profiles import eda\n",
                encoding="utf-8",
            )
            self.assertEqual(_importa_presentacion(limpio), [])


class TestSanityDeLosDetectores(unittest.TestCase):
    """Los escáneres detectan violaciones reales (no pasan en vacío)."""

    def _escribir(self, directorio: str, nombre: str, codigo: str) -> Path:
        ruta = Path(directorio) / nombre
        ruta.write_text(codigo, encoding="utf-8")
        return ruta

    def test_whitelist_detecta_imports_prohibidos_incluso_anidados(self):
        with tempfile.TemporaryDirectory() as tmp:
            nivel_modulo = self._escribir(tmp, "a.py", "import json\nimport pandas\n")
            anidado = self._escribir(tmp, "b.py", "import json\n\ndef f():\n    import numpy as np\n")
            desde = self._escribir(tmp, "c.py", "from tools.dsguard import core\n")
            relativo = self._escribir(tmp, "d.py", "from . import hermano\n")
            limpio = self._escribir(tmp, "e.py", "from __future__ import annotations\nimport re\n")
            self.assertEqual(_violaciones_whitelist(nivel_modulo), ["pandas"])
            self.assertEqual(_violaciones_whitelist(anidado), ["numpy"])
            self.assertEqual(_violaciones_whitelist(desde), ["tools.dsguard"])
            self.assertEqual(len(_violaciones_whitelist(relativo)), 1)
            self.assertEqual(_violaciones_whitelist(limpio), [])

    def test_detector_de_identificadores(self):
        with tempfile.TemporaryDirectory() as tmp:
            sucio = self._escribir(tmp, "s.py", "def usar_pandas(x):\n    return x.numpy_dato\n")
            limpio = self._escribir(tmp, "l.py", 'RUTA = "report.html"\n')
            ids_sucio = [
                i for i in _identificadores(sucio) if any(f in i.lower() for f in FRAGMENTOS_PROHIBIDOS)
            ]
            ids_limpio = [
                i for i in _identificadores(limpio) if any(f in i.lower() for f in FRAGMENTOS_PROHIBIDOS)
            ]
            self.assertEqual(sorted(ids_sucio), ["numpy_dato", "usar_pandas"])
            self.assertEqual(ids_limpio, [])

    def test_detecta_todos_los_estilos_de_import_de_reporting(self):
        estilos = (
            "import tools.reporting\n",
            "import tools.reporting.core as c\n",
            "import reporting\n",
            "from tools.reporting import core\n",
            "from tools.reporting.core import Report\n",
            "from reporting import core\n",
            "from tools import reporting\n",
            "from . import reporting\n",
            "from .reporting import core\n",
            "from .. import reporting\n",
            "def f():\n    from tools.reporting import core\n",
        )
        with tempfile.TemporaryDirectory() as tmp:
            for i, codigo in enumerate(estilos):
                ruta = self._escribir(tmp, f"m{i}.py", codigo)
                self.assertTrue(_referencias_a_reporting(ruta), f"no detectó: {codigo!r}")
            limpio = self._escribir(
                tmp, "limpio.py", "import json\nfrom tools.dsguard import core\nfrom . import otro\n"
            )
            self.assertEqual(_referencias_a_reporting(limpio), [])


if __name__ == "__main__":
    unittest.main()
