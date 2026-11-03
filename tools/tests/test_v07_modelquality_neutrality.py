"""Tests estructurales de neutralidad de `tools/modelquality` (v0.7 Change 2,
`20260922-model-quality-policies`). Mismo patrón `ast` que
`tools/tests/test_v07_core_neutrality.py`/`test_v07_validation_neutrality.py`
(Changes 0-1 de `tools/datacontracts`), cubriendo AMBOS módulos de este Change
en un solo archivo (`core.py` y `validation.py` por separado), escaneando
TODOS los imports (`ast.walk`, incluidos los anidados en funciones).

Verifica (R1/R18 de `spec.md`):
- `tools/modelquality/core.py` importa únicamente de la stdlib permitida
  (`__future__, dataclasses, hashlib, json, re, typing`) y no referencia
  `tools.datacontracts`, `ds_profile`, `dsguard`, pandas, numpy, `reporting`.
- `tools/modelquality/validation.py` importa: esa misma stdlib permitida (más
  `sys`/`pathlib`, usados solo para resolver `sys.path` hacia `tools/`, mismo
  patrón que `tools/datacontracts/validation.py`) + `dsguard` (para
  `dsguard.checks`) + el sibling `tools.modelquality.core` (import relativo
  `.core`); nunca `tools.datacontracts`, `ds_profile`, pandas, numpy, ni ningún
  otro paquete de `tools/`.
- `tools/modelquality/__init__.py` no tiene cuerpo (salvo docstring).
- Dirección inversa de la regla 8 de ARCHITECTURE.md: ningún módulo de
  `dsguard`, `ds_profile`, `dsimpact`, `reporting`, `tools.datacontracts`,
  `providers`, `routing`, `fallback` ni `harmessi_bench` importa
  `tools.modelquality` (ningún estilo de import).
- `MODULOS_CORE` de `test_architecture_boundaries.py` incluye ambos módulos.
"""
from __future__ import annotations

import ast
import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]

CORE_MODELQUALITY = "tools/modelquality/core.py"
VALIDATION_MODELQUALITY = "tools/modelquality/validation.py"
INIT_MODELQUALITY = "tools/modelquality/__init__.py"

# --- core.py: solo stdlib (idéntico set que tools/datacontracts/core.py) -----

CORE_IMPORTS_PERMITIDOS = {"__future__", "dataclasses", "hashlib", "json", "re", "typing"}
CORE_FRAGMENTOS_PROHIBIDOS = ("pandas", "numpy", "ds_profile", "dsguard", "reporting", "datacontracts")

# --- validation.py: stdlib + dsguard.checks + sibling .core -----------------

VALIDATION_STDLIB_PERMITIDOS = {"__future__", "sys", "pathlib", "typing", "json"}
VALIDATION_RAIZ_PERMITIDOS = VALIDATION_STDLIB_PERMITIDOS | {"dsguard", "."}
VALIDATION_RELATIVO_PERMITIDO = ".core"

PAQUETES_SIN_MODELQUALITY = (
    "tools/dsguard",
    "tools/ds_profile",
    "tools/dsimpact",
    "tools/reporting",
    "tools/datacontracts",
    "tools/providers",
    "tools/routing",
    "tools/fallback",
    "tools/harmessi_bench",
)


def _parsear(ruta_absoluta: Path) -> ast.AST:
    return ast.parse(ruta_absoluta.read_text(encoding="utf-8"), filename=str(ruta_absoluta))


def _todos_los_imports(ruta_absoluta: Path) -> list:
    """Lista de `(modulo_raiz, nombre_completo)` de TODOS los imports del
    archivo (`ast.walk`). Un import relativo se reporta con raíz `.`."""
    resultado = []
    for nodo in ast.walk(_parsear(ruta_absoluta)):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                resultado.append((alias.name.split(".")[0], alias.name))
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level and nodo.level > 0:
                if nodo.module:
                    resultado.append((".", "." * nodo.level + nodo.module))
                else:
                    for alias in nodo.names:
                        resultado.append((".", "." * nodo.level + alias.name))
            else:
                resultado.append((nodo.module.split(".")[0], nodo.module))
    return resultado


def _identificadores(ruta_absoluta: Path) -> list:
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


def _violaciones_whitelist_core(ruta_absoluta: Path) -> list:
    return [
        nombre
        for raiz, nombre in _todos_los_imports(ruta_absoluta)
        if raiz not in CORE_IMPORTS_PERMITIDOS
    ]


def _nombres_importados_de_ds_profile(ruta_absoluta: Path) -> list:
    """Lista de `(modulo, alias_importado)` para cada import cuyo módulo (o, en
    `import x`, el propio `x`) empieza con `ds_profile`. `alias_importado` es
    `None` para `import ds_profile[.x]` (no importa un símbolo puntual). Mismo
    patrón que `tools/tests/test_v07_validation_neutrality.py`, para que la
    violación reportada incluya el submódulo/símbolo concreto (p. ej.
    `ds_profile.report`) en vez de solo la raíz -- `validation.py` no permite
    NINGÚN símbolo de `ds_profile` (a diferencia de
    `tools/datacontracts/validation.py`, que sí permite uno solo), así que acá
    no hace falta comparar contra un símbolo permitido: cualquier import
    rooted en `ds_profile` es, sin excepción, una violación."""
    resultado = []
    for nodo in ast.walk(_parsear(ruta_absoluta)):
        if isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.module.split(".")[0] == "ds_profile":
            for alias in nodo.names:
                resultado.append((nodo.module, alias.name))
        elif isinstance(nodo, ast.Import):
            for alias in nodo.names:
                if alias.name.split(".")[0] == "ds_profile":
                    resultado.append((alias.name, None))
    return resultado


def _violaciones_frontera_validation(ruta_absoluta: Path) -> list:
    """Nombres/símbolos importados por `validation.py` fuera de su frontera
    permitida: stdlib autorizada + `dsguard` + el sibling `.core`. Cualquier
    import rooted en `ds_profile` se reporta aparte, con el submódulo/símbolo
    concreto (`_nombres_importados_de_ds_profile`), ya que `validation.py` no
    permite ninguno."""
    violaciones: list = []
    for raiz, nombre in _todos_los_imports(ruta_absoluta):
        if raiz == ".":
            if nombre != VALIDATION_RELATIVO_PERMITIDO:
                violaciones.append(nombre)
            continue
        if raiz == "ds_profile":
            continue  # reportado aparte, con submódulo/alias, abajo
        if raiz not in VALIDATION_RAIZ_PERMITIDOS:
            violaciones.append(nombre)
    for modulo, alias in _nombres_importados_de_ds_profile(ruta_absoluta):
        violaciones.append(f"{modulo}.{alias}" if alias else modulo)
    return violaciones


def _referencias_a_modelquality(ruta_absoluta: Path) -> list:
    """Imports del archivo que apuntan a `modelquality` con cualquier estilo:
    `import tools.modelquality[.x]`, `import modelquality`, `from
    tools.modelquality[.x] import y`, `from modelquality import y`, `from
    tools import modelquality`, `from . import modelquality`, `from
    .modelquality import y`."""
    encontradas = []
    for nodo in ast.walk(_parsear(ruta_absoluta)):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                partes = alias.name.split(".")
                if partes[0] == "modelquality" or partes[:2] == ["tools", "modelquality"]:
                    encontradas.append(f"import {alias.name}")
        elif isinstance(nodo, ast.ImportFrom):
            partes = nodo.module.split(".") if nodo.module else []
            if partes and (partes[0] == "modelquality" or partes[:2] == ["tools", "modelquality"]):
                encontradas.append(f"from {'.' * nodo.level}{nodo.module} import ...")
            for alias in nodo.names:
                if alias.name == "modelquality" and (not nodo.module or nodo.module == "tools"):
                    encontradas.append(f"from {'.' * nodo.level}{nodo.module or ''} import modelquality")
    return encontradas


class TestCoreModelQualitySoloStdlib(unittest.TestCase):
    def test_core_existe(self):
        self.assertTrue((REPO_ORIGEN / CORE_MODELQUALITY).is_file())

    def test_imports_de_core_pertenecen_al_set_permitido(self):
        violaciones = _violaciones_whitelist_core(REPO_ORIGEN / CORE_MODELQUALITY)
        self.assertEqual(
            violaciones,
            [],
            f"tools/modelquality/core.py importa fuera de la stdlib permitida "
            f"{sorted(CORE_IMPORTS_PERMITIDOS)}: {violaciones}",
        )

    def test_core_no_referencia_librerias_ni_hermanos_prohibidos(self):
        prohibidos = {"pandas", "numpy", "dsguard", "ds_profile", "reporting", "tools", "datacontracts"}
        for raiz, nombre in _todos_los_imports(REPO_ORIGEN / CORE_MODELQUALITY):
            partes = set(nombre.split("."))
            self.assertFalse(prohibidos & partes, f"import prohibido en core.py: {nombre}")

    def test_identificadores_de_core_no_referencian_librerias_prohibidas(self):
        violaciones = [
            identificador
            for identificador in _identificadores(REPO_ORIGEN / CORE_MODELQUALITY)
            if any(f in identificador.lower() for f in CORE_FRAGMENTOS_PROHIBIDOS)
        ]
        self.assertEqual(violaciones, [], f"identificadores prohibidos en core.py: {violaciones}")

    def test_init_de_modelquality_esta_vacio(self):
        arbol = _parsear(REPO_ORIGEN / INIT_MODELQUALITY)
        cuerpo = list(arbol.body)
        if (
            cuerpo
            and isinstance(cuerpo[0], ast.Expr)
            and isinstance(cuerpo[0].value, ast.Constant)
            and isinstance(cuerpo[0].value.value, str)
        ):
            cuerpo = cuerpo[1:]
        self.assertEqual(cuerpo, [], "tools/modelquality/__init__.py no debe tener lógica ni imports")
        self.assertEqual(_todos_los_imports(REPO_ORIGEN / INIT_MODELQUALITY), [])


class TestValidationModelQualityFrontera(unittest.TestCase):
    def test_validation_existe(self):
        self.assertTrue((REPO_ORIGEN / VALIDATION_MODELQUALITY).is_file())

    def test_imports_de_validation_pertenecen_al_set_permitido(self):
        violaciones = _violaciones_frontera_validation(REPO_ORIGEN / VALIDATION_MODELQUALITY)
        self.assertEqual(
            violaciones,
            [],
            f"tools/modelquality/validation.py importa fuera de la frontera permitida por R1 "
            f"(stdlib {sorted(VALIDATION_STDLIB_PERMITIDOS)} + dsguard.checks + sibling .core): "
            f"{violaciones}",
        )

    def test_validation_no_importa_pandas_numpy_ni_otros_paquetes_de_tools(self):
        prohibidos_raiz = {
            "pandas",
            "numpy",
            "reporting",
            "dsimpact",
            "providers",
            "routing",
            "fallback",
            "harmessi_bench",
            "nbrunner",
            "ds_guard",
            "harmessi",
            "launcher_common",
            "ds_profile",
            "datacontracts",
        }
        for raiz, nombre in _todos_los_imports(REPO_ORIGEN / VALIDATION_MODELQUALITY):
            self.assertNotIn(raiz, prohibidos_raiz, f"import prohibido en validation.py: {nombre}")

    def test_validation_no_importa_datacontracts_ni_ds_profile(self):
        for raiz, nombre in _todos_los_imports(REPO_ORIGEN / VALIDATION_MODELQUALITY):
            partes = set(nombre.split("."))
            self.assertFalse(
                {"datacontracts", "ds_profile"} & partes, f"import prohibido en validation.py: {nombre}"
            )


class TestModelQualityEnModulosCore(unittest.TestCase):
    def test_modulos_core_incluye_core_y_validation(self):
        ruta = REPO_ORIGEN / "tools" / "tests" / "test_architecture_boundaries.py"
        especificacion = importlib.util.spec_from_file_location("_arch_boundaries_mq", ruta)
        modulo = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(modulo)
        self.assertIn(CORE_MODELQUALITY, modulo.MODULOS_CORE)
        self.assertIn(VALIDATION_MODELQUALITY, modulo.MODULOS_CORE)


class TestNingunPaqueteImportaModelQuality(unittest.TestCase):
    def test_ningun_modulo_de_los_paquetes_previos_importa_modelquality(self):
        violaciones = []
        for paquete in PAQUETES_SIN_MODELQUALITY:
            directorio = REPO_ORIGEN / paquete
            self.assertTrue(directorio.is_dir(), f"no existe el paquete {paquete}")
            for ruta in sorted(directorio.rglob("*.py")):
                if "__pycache__" in ruta.parts or "tests" in ruta.relative_to(directorio).parts:
                    continue
                for referencia in _referencias_a_modelquality(ruta):
                    violaciones.append(f"{ruta.relative_to(REPO_ORIGEN).as_posix()}: {referencia}")
        self.assertEqual(
            violaciones,
            [],
            "Módulo(s) que importan `modelquality` -- prohibido por la regla 8 de ARCHITECTURE.md "
            f"(la dependencia es solo modelquality -> dsguard, nunca al revés): {violaciones}",
        )


class TestSanityDeLosDetectores(unittest.TestCase):
    """Los escáneres detectan violaciones reales (no pasan en vacío)."""

    def _escribir(self, directorio: str, nombre: str, codigo: str) -> Path:
        ruta = Path(directorio) / nombre
        ruta.write_text(codigo, encoding="utf-8")
        return ruta

    def test_whitelist_core_detecta_imports_prohibidos_incluso_anidados(self):
        with tempfile.TemporaryDirectory() as tmp:
            nivel_modulo = self._escribir(tmp, "a.py", "import json\nimport pandas\n")
            anidado = self._escribir(tmp, "b.py", "import json\n\ndef f():\n    import numpy as np\n")
            desde = self._escribir(tmp, "c.py", "from tools.dsguard import core\n")
            limpio = self._escribir(tmp, "e.py", "from __future__ import annotations\nimport re\n")
            self.assertEqual(_violaciones_whitelist_core(nivel_modulo), ["pandas"])
            self.assertEqual(_violaciones_whitelist_core(anidado), ["numpy"])
            self.assertEqual(_violaciones_whitelist_core(desde), ["tools.dsguard"])
            self.assertEqual(_violaciones_whitelist_core(limpio), [])

    def test_frontera_validation_archivo_limpio(self):
        with tempfile.TemporaryDirectory() as tmp:
            limpio = self._escribir(
                tmp,
                "limpio.py",
                "from __future__ import annotations\n"
                "import sys\n"
                "from pathlib import Path\n"
                "from dsguard import checks\n"
                "from . import core as modelquality_core\n",
            )
            self.assertEqual(_violaciones_frontera_validation(limpio), [])

    def test_frontera_validation_detecta_pandas(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "a.py", "import json\nimport pandas\n")
            self.assertEqual(_violaciones_frontera_validation(ruta), ["pandas"])

    def test_frontera_validation_detecta_ds_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "b.py", "from ds_profile import report\n")
            self.assertEqual(_violaciones_frontera_validation(ruta), ["ds_profile.report"])

    def test_frontera_validation_detecta_import_relativo_prohibido(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "c.py", "from . import hermano\n")
            self.assertEqual(_violaciones_frontera_validation(ruta), [".hermano"])

    def test_detecta_todos_los_estilos_de_import_de_modelquality(self):
        estilos = (
            "import tools.modelquality\n",
            "import tools.modelquality.core as c\n",
            "import modelquality\n",
            "from tools.modelquality import core\n",
            "from tools.modelquality.core import ModelQualityPolicy\n",
            "from modelquality import core\n",
            "from tools import modelquality\n",
            "from . import modelquality\n",
            "from .modelquality import core\n",
            "from .. import modelquality\n",
            "def f():\n    from tools.modelquality import core\n",
        )
        with tempfile.TemporaryDirectory() as tmp:
            for i, codigo in enumerate(estilos):
                ruta = self._escribir(tmp, f"m{i}.py", codigo)
                self.assertTrue(_referencias_a_modelquality(ruta), f"no detectó: {codigo!r}")
            limpio = self._escribir(
                tmp, "limpio.py", "import json\nfrom tools.dsguard import core\nfrom . import otro\n"
            )
            self.assertEqual(_referencias_a_modelquality(limpio), [])


if __name__ == "__main__":
    unittest.main()
