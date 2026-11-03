"""Tests estructurales de neutralidad de `tools/datacontracts/evolution.py`
(v0.7 Change 4, `20260922-quality-integration-and-cli`). Mismo patrón `ast`
que `tools/tests/test_v07_validation_neutrality.py`/
`test_v07_modelquality_neutrality.py`/`test_v07_qualityevidence_neutrality.py`,
escaneando TODOS los imports del archivo (`ast.walk`, incluidos los anidados
en funciones), no solo los de nivel de módulo.

Verifica (R6/R21 de `spec.md`):
- `tools/datacontracts/evolution.py` importa únicamente: stdlib permitida
  (`__future__`, `sys`, `pathlib`, `typing`) + `dsguard` (para
  `dsguard.checks`) + import relativo sibling `from . import core`.
- Ningún import de `ds_profile`, `dsimpact`, `tools.modelquality`,
  `tools.qualityevidence`, `tools.reporting`, pandas, numpy, ni ningún otro
  paquete de `tools/`.
- Ningún módulo existente (Changes 0-3, `dsguard`, `ds_profile`, `dsimpact`,
  `reporting`, `providers`, `routing`, `fallback`, `harmessi_bench`) importa
  `tools.datacontracts.evolution` (dirección inversa).
- Regresión: `tools/datacontracts/core.py` (Change 0) sigue solo-stdlib.
"""
from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]

EVOLUTION_DATACONTRACTS = "tools/datacontracts/evolution.py"
CORE_DATACONTRACTS = "tools/datacontracts/core.py"

IMPORTS_STDLIB_PERMITIDOS = {"__future__", "sys", "pathlib", "typing", "json"}
IMPORTS_RAIZ_PERMITIDOS = IMPORTS_STDLIB_PERMITIDOS | {"dsguard", "."}

_RELATIVO_PERMITIDO = ".core"

# `evolution.py` no importa NADA de `ds_profile` (a diferencia de
# `validation.py`/`evidence.py`, que sí tienen un único símbolo permitido):
# cualquier import de `ds_profile` es violación. Se detecta por separado
# (mismo patrón que `test_v07_qualityevidence_neutrality.py`) para reportar
# el nombre completo `modulo.alias`, no solo la raíz `ds_profile`.

CORE_IMPORTS_PERMITIDOS = {"__future__", "dataclasses", "hashlib", "json", "re", "typing"}

PAQUETES_A_ESCANEAR_DIRECCION_INVERSA = (
    "tools/dsguard",
    "tools/ds_profile",
    "tools/dsimpact",
    "tools/reporting",
    "tools/datacontracts",
    "tools/modelquality",
    "tools/qualityevidence",
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


def _nombres_importados_de_ds_profile(ruta_absoluta: Path) -> list:
    """Lista de `(modulo, alias_importado)` para cada import cuyo módulo (o,
    en `import x`, el propio `x`) empieza con `ds_profile`. `alias_importado`
    es `None` para `import ds_profile[.x]` -- mismo patrón que
    `test_v07_qualityevidence_neutrality.py`."""
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


def _violaciones_frontera_evolution(ruta_absoluta: Path) -> list:
    violaciones: list = []
    for raiz, nombre in _todos_los_imports(ruta_absoluta):
        if raiz == ".":
            if nombre != _RELATIVO_PERMITIDO:
                violaciones.append(nombre)
            continue
        if raiz == "ds_profile":
            continue  # reportado aparte, símbolo por símbolo, abajo
        if raiz not in IMPORTS_RAIZ_PERMITIDOS:
            violaciones.append(nombre)
    for modulo, alias in _nombres_importados_de_ds_profile(ruta_absoluta):
        violaciones.append(f"{modulo}.{alias}" if alias else modulo)
    return violaciones


def _referencias_a_evolution(ruta_absoluta: Path) -> list:
    """Imports del archivo que apuntan a `tools.datacontracts.evolution` con
    cualquier estilo."""
    encontradas = []
    for nodo in ast.walk(_parsear(ruta_absoluta)):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                partes = alias.name.split(".")
                if partes[-1] == "evolution" and (
                    "datacontracts" in partes or partes[0] == "evolution"
                ):
                    encontradas.append(f"import {alias.name}")
        elif isinstance(nodo, ast.ImportFrom):
            partes = nodo.module.split(".") if nodo.module else []
            if partes and partes[-1] == "evolution" and "datacontracts" in partes:
                encontradas.append(f"from {'.' * nodo.level}{nodo.module} import ...")
            for alias in nodo.names:
                if alias.name == "evolution" and partes and partes[-1] == "datacontracts":
                    encontradas.append(f"from {'.' * nodo.level}{nodo.module} import evolution")
    return encontradas


class TestEvolutionExiste(unittest.TestCase):
    def test_evolution_es_un_archivo(self):
        self.assertTrue((REPO_ORIGEN / EVOLUTION_DATACONTRACTS).is_file())


class TestEvolutionFronteraDeImports(unittest.TestCase):
    def test_imports_de_evolution_pertenecen_al_set_permitido(self):
        violaciones = _violaciones_frontera_evolution(REPO_ORIGEN / EVOLUTION_DATACONTRACTS)
        self.assertEqual(
            violaciones,
            [],
            f"tools/datacontracts/evolution.py importa fuera de la frontera permitida por R6 "
            f"(stdlib {sorted(IMPORTS_STDLIB_PERMITIDOS)} + dsguard.checks + sibling .core): {violaciones}",
        )

    def test_evolution_no_importa_pandas_numpy_ni_otros_paquetes_de_tools(self):
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
            "modelquality",
            "qualityevidence",
        }
        for raiz, nombre in _todos_los_imports(REPO_ORIGEN / EVOLUTION_DATACONTRACTS):
            self.assertNotIn(raiz, prohibidos_raiz, f"import prohibido en evolution.py: {nombre}")


class TestCoreSigueSoloStdlib(unittest.TestCase):
    """Regresión: `core.py` (Change 0) no se modifica ni gana dependencias nuevas."""

    def test_core_sigue_solo_stdlib(self):
        violaciones = [
            nombre
            for raiz, nombre in _todos_los_imports(REPO_ORIGEN / CORE_DATACONTRACTS)
            if raiz not in CORE_IMPORTS_PERMITIDOS
        ]
        self.assertEqual(
            violaciones,
            [],
            f"tools/datacontracts/core.py debe seguir solo-stdlib {sorted(CORE_IMPORTS_PERMITIDOS)}: "
            f"{violaciones}",
        )


class TestNingunPaqueteImportaEvolution(unittest.TestCase):
    def test_ningun_modulo_previo_importa_evolution(self):
        violaciones = []
        for paquete in PAQUETES_A_ESCANEAR_DIRECCION_INVERSA:
            directorio = REPO_ORIGEN / paquete
            self.assertTrue(directorio.is_dir(), f"no existe el paquete {paquete}")
            for ruta in sorted(directorio.rglob("*.py")):
                if "__pycache__" in ruta.parts or "tests" in ruta.relative_to(directorio).parts:
                    continue
                if ruta == REPO_ORIGEN / EVOLUTION_DATACONTRACTS:
                    continue
                for referencia in _referencias_a_evolution(ruta):
                    violaciones.append(f"{ruta.relative_to(REPO_ORIGEN).as_posix()}: {referencia}")
        self.assertEqual(
            violaciones,
            [],
            "Módulo(s) que importan `tools.datacontracts.evolution` fuera de `ds_guard.py` -- "
            f"solo el adapter top-level puede consumirlo (ver design.md decisión 1): {violaciones}",
        )


class TestSanityDeLosDetectores(unittest.TestCase):
    def _escribir(self, directorio: str, nombre: str, codigo: str) -> Path:
        ruta = Path(directorio) / nombre
        ruta.write_text(codigo, encoding="utf-8")
        return ruta

    def test_archivo_limpio_no_produce_violaciones(self):
        with tempfile.TemporaryDirectory() as tmp:
            limpio = self._escribir(
                tmp,
                "limpio.py",
                "from __future__ import annotations\n"
                "import sys\n"
                "from pathlib import Path\n"
                "from typing import Optional\n"
                "from dsguard import checks\n"
                "from . import core as datacontracts_core\n",
            )
            self.assertEqual(_violaciones_frontera_evolution(limpio), [])

    def test_detecta_import_pandas(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "a.py", "import json\nimport pandas\n")
            self.assertEqual(_violaciones_frontera_evolution(ruta), ["pandas"])

    def test_detecta_import_ds_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "b.py", "from ds_profile import report\n")
            self.assertEqual(_violaciones_frontera_evolution(ruta), ["ds_profile.report"])

    def test_detecta_import_relativo_prohibido(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "c.py", "from . import hermano\n")
            self.assertEqual(_violaciones_frontera_evolution(ruta), [".hermano"])

    def test_detecta_referencia_a_evolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "d.py", "from tools.datacontracts import evolution\n")
            self.assertTrue(_referencias_a_evolution(ruta))
            limpio = self._escribir(tmp, "e.py", "from tools.datacontracts import core\n")
            self.assertEqual(_referencias_a_evolution(limpio), [])


if __name__ == "__main__":
    unittest.main()
