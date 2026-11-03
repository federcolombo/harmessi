"""Tests estructurales de neutralidad del core de v0.7 (Change 0,
`20260922-data-contracts-core`). Mismo patrón `ast` que
`tools/tests/test_v06_core_neutrality.py`, escaneando TODOS los imports del
archivo (`ast.walk`, incluidos los anidados en funciones), no solo los de
nivel de módulo.

Verifica (R1/R14):
- `tools/datacontracts/core.py` importa únicamente de la stdlib permitida y no
  usa identificadores de `ds_profile`/`dsguard`/pandas/numpy/reporting.
- `tools/datacontracts/__init__.py` no tiene cuerpo (salvo docstring): no
  acopla la instalación de `core.py` a módulos futuros.
- Dirección inversa de la regla 7 de ARCHITECTURE.md: ningún módulo de
  `dsguard`, `ds_profile`, `dsimpact`, `reporting`, `providers`, `routing`,
  `fallback` ni `harmessi_bench` importa `datacontracts` (con cualquier estilo
  de import).
- `MODULOS_CORE` de `test_architecture_boundaries.py` incluye el core.
"""
from __future__ import annotations

import ast
import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]

CORE_DATACONTRACTS = "tools/datacontracts/core.py"
INIT_DATACONTRACTS = "tools/datacontracts/__init__.py"

IMPORTS_PERMITIDOS = {"__future__", "dataclasses", "hashlib", "json", "re", "typing"}

# Fragmentos que ningún identificador de `core.py` puede contener.
FRAGMENTOS_PROHIBIDOS = ("pandas", "numpy", "ds_profile", "dsguard", "reporting")

PAQUETES_SIN_DATACONTRACTS = (
    "tools/dsguard",
    "tools/ds_profile",
    "tools/dsimpact",
    "tools/reporting",
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


def _referencias_a_datacontracts(ruta_absoluta: Path) -> list:
    """Imports del archivo que apuntan a `datacontracts` con cualquier estilo:
    `import tools.datacontracts[.x]`, `import datacontracts`, `from
    tools.datacontracts[.x] import y`, `from datacontracts import y`, `from
    tools import datacontracts`, `from . import datacontracts`, `from
    .datacontracts import y`."""
    encontradas = []
    for nodo in ast.walk(_parsear(ruta_absoluta)):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                partes = alias.name.split(".")
                if partes[0] == "datacontracts" or partes[:2] == ["tools", "datacontracts"]:
                    encontradas.append(f"import {alias.name}")
        elif isinstance(nodo, ast.ImportFrom):
            partes = nodo.module.split(".") if nodo.module else []
            if partes and (partes[0] == "datacontracts" or partes[:2] == ["tools", "datacontracts"]):
                encontradas.append(f"from {'.' * nodo.level}{nodo.module} import ...")
            for alias in nodo.names:
                if alias.name == "datacontracts" and (not nodo.module or nodo.module == "tools"):
                    encontradas.append(f"from {'.' * nodo.level}{nodo.module or ''} import datacontracts")
    return encontradas


class TestCoreDataContractsSoloStdlib(unittest.TestCase):
    def test_core_existe(self):
        self.assertTrue((REPO_ORIGEN / CORE_DATACONTRACTS).is_file())

    def test_imports_de_core_pertenecen_al_set_permitido(self):
        violaciones = _violaciones_whitelist(REPO_ORIGEN / CORE_DATACONTRACTS)
        self.assertEqual(
            violaciones,
            [],
            f"tools/datacontracts/core.py importa fuera de la stdlib permitida "
            f"{sorted(IMPORTS_PERMITIDOS)}: {violaciones}",
        )

    def test_core_no_referencia_librerias_ni_hermanos_prohibidos(self):
        prohibidos = {"pandas", "numpy", "dsguard", "ds_profile", "reporting", "tools"}
        for raiz, nombre in _todos_los_imports(REPO_ORIGEN / CORE_DATACONTRACTS):
            partes = set(nombre.split("."))
            self.assertFalse(prohibidos & partes, f"import prohibido en core.py: {nombre}")

    def test_identificadores_de_core_no_referencian_librerias_ni_dsguard(self):
        violaciones = [
            identificador
            for identificador in _identificadores(REPO_ORIGEN / CORE_DATACONTRACTS)
            if any(f in identificador.lower() for f in FRAGMENTOS_PROHIBIDOS)
        ]
        self.assertEqual(violaciones, [], f"identificadores prohibidos en core.py: {violaciones}")

    def test_init_de_datacontracts_esta_vacio(self):
        arbol = _parsear(REPO_ORIGEN / INIT_DATACONTRACTS)
        cuerpo = list(arbol.body)
        if (
            cuerpo
            and isinstance(cuerpo[0], ast.Expr)
            and isinstance(cuerpo[0].value, ast.Constant)
            and isinstance(cuerpo[0].value.value, str)
        ):
            cuerpo = cuerpo[1:]
        self.assertEqual(cuerpo, [], "tools/datacontracts/__init__.py no debe tener lógica ni imports")
        self.assertEqual(_todos_los_imports(REPO_ORIGEN / INIT_DATACONTRACTS), [])


class TestCoreEnModulosCore(unittest.TestCase):
    def test_modulos_core_de_architecture_boundaries_incluye_datacontracts_core(self):
        ruta = REPO_ORIGEN / "tools" / "tests" / "test_architecture_boundaries.py"
        especificacion = importlib.util.spec_from_file_location("_arch_boundaries_v07", ruta)
        modulo = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(modulo)
        self.assertIn(CORE_DATACONTRACTS, modulo.MODULOS_CORE)


class TestNingunPaqueteImportaDataContracts(unittest.TestCase):
    def test_ningun_modulo_de_los_paquetes_previos_importa_datacontracts(self):
        violaciones = []
        for paquete in PAQUETES_SIN_DATACONTRACTS:
            directorio = REPO_ORIGEN / paquete
            self.assertTrue(directorio.is_dir(), f"no existe el paquete {paquete}")
            for ruta in sorted(directorio.rglob("*.py")):
                if "__pycache__" in ruta.parts or "tests" in ruta.relative_to(directorio).parts:
                    continue
                for referencia in _referencias_a_datacontracts(ruta):
                    violaciones.append(f"{ruta.relative_to(REPO_ORIGEN).as_posix()}: {referencia}")
        self.assertEqual(
            violaciones,
            [],
            "Módulo(s) que importan `datacontracts` -- prohibido por la regla 7 de "
            f"ARCHITECTURE.md (la dependencia es solo datacontracts -> dsguard/ds_profile "
            f"en Changes posteriores, nunca al revés): {violaciones}",
        )


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
            limpio = self._escribir(tmp, "l.py", 'RUTA = "contrato.json"\n')
            ids_sucio = [
                i for i in _identificadores(sucio) if any(f in i.lower() for f in FRAGMENTOS_PROHIBIDOS)
            ]
            ids_limpio = [
                i for i in _identificadores(limpio) if any(f in i.lower() for f in FRAGMENTOS_PROHIBIDOS)
            ]
            self.assertEqual(sorted(ids_sucio), ["numpy_dato", "usar_pandas"])
            self.assertEqual(ids_limpio, [])

    def test_detecta_todos_los_estilos_de_import_de_datacontracts(self):
        estilos = (
            "import tools.datacontracts\n",
            "import tools.datacontracts.core as c\n",
            "import datacontracts\n",
            "from tools.datacontracts import core\n",
            "from tools.datacontracts.core import DataContract\n",
            "from datacontracts import core\n",
            "from tools import datacontracts\n",
            "from . import datacontracts\n",
            "from .datacontracts import core\n",
            "from .. import datacontracts\n",
            "def f():\n    from tools.datacontracts import core\n",
        )
        with tempfile.TemporaryDirectory() as tmp:
            for i, codigo in enumerate(estilos):
                ruta = self._escribir(tmp, f"m{i}.py", codigo)
                self.assertTrue(_referencias_a_datacontracts(ruta), f"no detectó: {codigo!r}")
            limpio = self._escribir(
                tmp, "limpio.py", "import json\nfrom tools.dsguard import core\nfrom . import otro\n"
            )
            self.assertEqual(_referencias_a_datacontracts(limpio), [])


if __name__ == "__main__":
    unittest.main()
