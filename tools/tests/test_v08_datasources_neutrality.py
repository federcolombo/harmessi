"""Tests estructurales de neutralidad de `tools/datasources` (v0.8 Change 1,
`20260928-source-neutral-data-access`). Mismo patrón `ast` que
`test_v08_autonomy_neutrality.py`, escaneando TODOS los imports (`ast.walk`,
incluidos los anidados en funciones) salvo donde se indique explícitamente
"solo nivel de módulo".

Verifica (R1, R2 de `spec.md`):
- `core.py` importa solo stdlib (`dataclasses`, `typing`, `re`, `json`,
  `hashlib`, `unicodedata`, `__future__`); sin `os`/`pathlib`/`sys`/
  `importlib`, sin hermanos ni `tools.*`.
- `scan.py` importa solo stdlib + `.core` relativo.
- `registry.py` importa solo stdlib + `.core`/`.scan` relativos.
- `runtime.py` importa stdlib (`os`, `pathlib`, `importlib`, `hashlib`,
  `json`, `datetime`, `sys`, `typing`) + `dsguard.checks` (vía
  `sys.path.insert`) + `.core`/`.registry`/`.scan` relativos.
- `profile_bridge.py` es puro: solo stdlib + `.core`.
- `file_observer.py`: `ds_profile` NO aparece como import a nivel de módulo
  (`ast.Module.body`), solo dentro de funciones (import perezoso).
- Dirección inversa: ninguno de `dsguard`, `ds_profile`, `dsimpact`,
  `reporting`, `providers`, `routing`, `fallback`, `harmessi_bench`,
  `autonomy`, `modelquality`, `qualityevidence` importa `datasources`. Única
  excepción documentada: `tools.datacontracts.validation`/`legacy_wording.py`.
- `MODULOS_CORE` de `test_architecture_boundaries.py` incluye los 6 módulos
  de `tools/datasources`.
"""
from __future__ import annotations

import ast
import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]

CORE = "tools/datasources/core.py"
SCAN = "tools/datasources/scan.py"
REGISTRY = "tools/datasources/registry.py"
RUNTIME = "tools/datasources/runtime.py"
PROFILE_BRIDGE = "tools/datasources/profile_bridge.py"
FILE_OBSERVER = "tools/datasources/file_observer.py"

IMPORTS_CORE = {"__future__", "dataclasses", "typing", "re", "json", "hashlib", "unicodedata"}
IMPORTS_SCAN = {"__future__", "re", "typing"}
IMPORTS_REGISTRY = {"__future__", "re", "typing"}
IMPORTS_RUNTIME = {
    "__future__", "hashlib", "importlib", "json", "os", "sys", "typing",
    "datetime", "pathlib", "dsguard",
}
IMPORTS_PROFILE_BRIDGE = {"__future__", "datetime", "typing"}
IMPORTS_FILE_OBSERVER_MODULO = {"__future__", "tempfile", "pathlib", "typing"}

PROHIBIDOS = {"os", "pathlib", "sys", "importlib"}

# Paquetes que NO deben importar `datasources` en ninguna dirección (R2),
# salvo la excepción documentada de `tools.datacontracts` (verificada aparte).
PAQUETES_SIN_DATASOURCES = (
    "tools/dsguard",
    "tools/ds_profile",
    "tools/dsimpact",
    "tools/reporting",
    "tools/providers",
    "tools/routing",
    "tools/fallback",
    "tools/harmessi_bench",
    "tools/autonomy",
    "tools/modelquality",
    "tools/qualityevidence",
)

# Excepción documentada de R2: estos archivos de `tools/datacontracts` SÍ
# importan `datasources` (evaluador único sobre observación neutral, M1 del
# roadmap de v0.8).
EXCEPCION_DATACONTRACTS = (
    "tools/datacontracts/validation.py",
    "tools/datacontracts/legacy_wording.py",
)


def _requerir(ruta_relativa: str) -> Path:
    ruta = REPO_ORIGEN / ruta_relativa
    if not ruta.is_file():
        raise AssertionError(f"falta {ruta_relativa}: el archivo debe existir para verificar su neutralidad")
    return ruta


def _parsear(ruta: Path) -> ast.AST:
    return ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))


def _imports_todos(ruta: Path) -> list:
    """Lista de `(nivel, modulo, nombres)` de TODOS los imports del archivo
    (`ast.walk`, incluye los anidados en funciones)."""
    resultado = []
    for nodo in ast.walk(_parsear(ruta)):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                resultado.append((0, alias.name, (alias.name,)))
        elif isinstance(nodo, ast.ImportFrom):
            resultado.append((nodo.level or 0, nodo.module or "", tuple(a.name for a in nodo.names)))
    return resultado


def _imports_nivel_modulo(ruta: Path) -> list:
    """Como `_imports_todos`, pero SOLO de nivel superior (`ast.Module.body`,
    no anidados en funciones/métodos)."""
    resultado = []
    for nodo in _parsear(ruta).body:
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                resultado.append((0, alias.name, (alias.name,)))
        elif isinstance(nodo, ast.ImportFrom):
            resultado.append((nodo.level or 0, nodo.module or "", tuple(a.name for a in nodo.names)))
    return resultado


def _violaciones(imports: list, permitidos: set, relativos_permitidos: set) -> list:
    """Imports fuera del set permitido. Un import relativo (`nivel == 1`) solo
    es válido si es `from . import <nombre>` con `<nombre>` en
    `relativos_permitidos`, o `from .<modulo> import ...` con `<modulo>` en
    `relativos_permitidos`."""
    violaciones = []
    for nivel, modulo, nombres in imports:
        if nivel:
            if nivel == 1 and not modulo and set(nombres) <= relativos_permitidos:
                continue
            if nivel == 1 and modulo in relativos_permitidos:
                continue
            violaciones.append("." * nivel + modulo + " import " + ",".join(nombres))
        elif modulo.split(".")[0] not in permitidos:
            violaciones.append(modulo)
    return violaciones


def _referencias_a_datasources(ruta: Path) -> list:
    encontradas = []
    for nodo in ast.walk(_parsear(ruta)):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                partes = alias.name.split(".")
                if partes[0] == "datasources" or partes[:2] == ["tools", "datasources"]:
                    encontradas.append(f"import {alias.name}")
        elif isinstance(nodo, ast.ImportFrom):
            partes = nodo.module.split(".") if nodo.module else []
            if partes and (partes[0] == "datasources" or partes[:2] == ["tools", "datasources"]):
                encontradas.append(f"from {'.' * nodo.level}{nodo.module} import ...")
            for alias in nodo.names:
                if alias.name == "datasources" and (not nodo.module or nodo.module == "tools"):
                    encontradas.append(f"from {'.' * nodo.level}{nodo.module or ''} import datasources")
    return encontradas


class TestCoreDatasourcesSoloStdlib(unittest.TestCase):
    def test_imports_de_core_pertenecen_al_set_permitido(self):
        imports = _imports_todos(_requerir(CORE))
        violaciones = _violaciones(imports, IMPORTS_CORE, set())
        self.assertEqual(violaciones, [], f"core.py importa fuera de {sorted(IMPORTS_CORE)}: {violaciones}")

    def test_core_no_importa_prohibidos_ni_hermanos(self):
        for nivel, modulo, nombres in _imports_todos(_requerir(CORE)):
            self.assertEqual(nivel, 0, f"import relativo en core.py: {modulo} {nombres}")
            self.assertFalse(
                PROHIBIDOS & set(modulo.split(".")), f"import prohibido en core.py: {modulo}"
            )


class TestScanSoloStdlibYCore(unittest.TestCase):
    def test_imports_de_scan_pertenecen_al_set_permitido(self):
        imports = _imports_todos(_requerir(SCAN))
        violaciones = _violaciones(imports, IMPORTS_SCAN, {"core"})
        self.assertEqual(
            violaciones, [], f"scan.py importa fuera de {sorted(IMPORTS_SCAN)} y `.core`: {violaciones}"
        )


class TestRegistrySoloStdlibYPuros(unittest.TestCase):
    def test_imports_de_registry_pertenecen_al_set_permitido(self):
        imports = _imports_todos(_requerir(REGISTRY))
        violaciones = _violaciones(imports, IMPORTS_REGISTRY, {"core", "scan"})
        self.assertEqual(
            violaciones, [], f"registry.py importa fuera de {sorted(IMPORTS_REGISTRY)} y `.core`/`.scan`: {violaciones}"
        )


class TestRuntimeIOEImportlib(unittest.TestCase):
    def test_imports_de_runtime_pertenecen_al_set_permitido(self):
        imports = _imports_todos(_requerir(RUNTIME))
        violaciones = _violaciones(imports, IMPORTS_RUNTIME, {"core", "registry", "scan"})
        self.assertEqual(
            violaciones,
            [],
            f"runtime.py importa fuera de {sorted(IMPORTS_RUNTIME)} y `.core`/`.registry`/`.scan`: {violaciones}",
        )

    def test_runtime_no_importa_autonomy_ni_pathguard(self):
        for nivel, modulo, nombres in _imports_todos(_requerir(RUNTIME)):
            partes = modulo.split(".") if modulo else list(nombres)
            self.assertFalse(
                "autonomy" in partes or "pathguard" in partes,
                f"runtime.py no debe importar autonomy/pathguard (D8, R25): {modulo or nombres}",
            )


class TestProfileBridgePuro(unittest.TestCase):
    def test_imports_de_profile_bridge_pertenecen_al_set_permitido(self):
        imports = _imports_todos(_requerir(PROFILE_BRIDGE))
        violaciones = _violaciones(imports, IMPORTS_PROFILE_BRIDGE, {"core"})
        self.assertEqual(
            violaciones,
            [],
            f"profile_bridge.py importa fuera de {sorted(IMPORTS_PROFILE_BRIDGE)} y `.core`: {violaciones}",
        )

    def test_profile_bridge_no_importa_ds_profile(self):
        for nivel, modulo, nombres in _imports_todos(_requerir(PROFILE_BRIDGE)):
            partes = modulo.split(".") if modulo else list(nombres)
            self.assertNotIn("ds_profile", partes, "profile_bridge.py no debe importar ds_profile (R27)")


class TestFileObserverImportPerezosoDeDsProfile(unittest.TestCase):
    def test_imports_de_nivel_modulo_pertenecen_al_set_permitido(self):
        imports = _imports_nivel_modulo(_requerir(FILE_OBSERVER))
        violaciones = _violaciones(imports, IMPORTS_FILE_OBSERVER_MODULO, {"profile_bridge"})
        self.assertEqual(
            violaciones,
            [],
            f"file_observer.py importa a nivel de módulo fuera de {sorted(IMPORTS_FILE_OBSERVER_MODULO)} "
            f"y `.profile_bridge`: {violaciones}",
        )

    def test_ds_profile_no_aparece_a_nivel_de_modulo(self):
        for nivel, modulo, nombres in _imports_nivel_modulo(_requerir(FILE_OBSERVER)):
            partes = modulo.split(".") if modulo else list(nombres)
            self.assertNotIn(
                "ds_profile", partes,
                "ds_profile debe importarse de forma perezosa (dentro de funciones), nunca a nivel de módulo",
            )

    def test_ds_profile_si_aparece_dentro_de_una_funcion(self):
        """Import perezoso esperado (R1/R28): dentro de funciones, `ds_profile`
        SÍ debe aparecer -- si no aparece en ningún lado, el observer no
        podría funcionar."""
        arbol = _parsear(_requerir(FILE_OBSERVER))
        encontrado = False
        for nodo_top in ast.walk(arbol):
            if isinstance(nodo_top, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for sub in ast.walk(nodo_top):
                    if isinstance(sub, ast.ImportFrom) and sub.module and sub.module.split(".")[0] == "ds_profile":
                        encontrado = True
                    if isinstance(sub, ast.Import):
                        for alias in sub.names:
                            if alias.name.split(".")[0] == "ds_profile":
                                encontrado = True
        self.assertTrue(encontrado, "ds_profile debe importarse de forma perezosa dentro de alguna función")


class TestDireccionInversaDeDatasources(unittest.TestCase):
    def test_ningun_paquete_previo_importa_datasources(self):
        violaciones = []
        for paquete in PAQUETES_SIN_DATASOURCES:
            directorio = REPO_ORIGEN / paquete
            self.assertTrue(directorio.is_dir(), f"no existe el paquete {paquete}")
            for ruta in sorted(directorio.rglob("*.py")):
                if "__pycache__" in ruta.parts or "tests" in ruta.relative_to(directorio).parts:
                    continue
                for referencia in _referencias_a_datasources(ruta):
                    violaciones.append(f"{ruta.relative_to(REPO_ORIGEN).as_posix()}: {referencia}")
        self.assertEqual(
            violaciones,
            [],
            f"Módulo(s) que importan `datasources` fuera de la excepción de `tools.datacontracts` "
            f"(R2 de spec.md, regla 11 de ARCHITECTURE.md): {violaciones}",
        )

    def test_excepcion_documentada_de_datacontracts_si_importa_datasources(self):
        """La excepción es real (no un olvido): `validation.py` importa
        `datasources` (`legacy_wording.py` no, hoy)."""
        referencias_validation = _referencias_a_datasources(_requerir("tools/datacontracts/validation.py"))
        self.assertTrue(
            referencias_validation,
            "tools/datacontracts/validation.py debería importar datasources (excepción documentada de R2)",
        )

    def test_datacontracts_no_importa_datasources_fuera_de_la_excepcion(self):
        directorio = REPO_ORIGEN / "tools/datacontracts"
        for ruta in sorted(directorio.rglob("*.py")):
            if "__pycache__" in ruta.parts or "tests" in ruta.relative_to(directorio).parts:
                continue
            rel = ruta.relative_to(REPO_ORIGEN).as_posix()
            if rel in EXCEPCION_DATACONTRACTS:
                continue
            referencias = _referencias_a_datasources(ruta)
            self.assertEqual(
                referencias, [], f"{rel} importa datasources fuera de la excepción documentada: {referencias}"
            )


class TestDatasourcesEnModulosCore(unittest.TestCase):
    def test_modulos_core_incluye_los_6_modulos_de_datasources(self):
        ruta = REPO_ORIGEN / "tools" / "tests" / "test_architecture_boundaries.py"
        especificacion = importlib.util.spec_from_file_location("_arch_boundaries_v08_ds", ruta)
        modulo = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(modulo)
        for ruta_relativa in (CORE, SCAN, REGISTRY, RUNTIME, PROFILE_BRIDGE, FILE_OBSERVER):
            self.assertIn(ruta_relativa, modulo.MODULOS_CORE)


class TestSanityDeLosDetectores(unittest.TestCase):
    def _escribir(self, directorio: str, nombre: str, codigo: str) -> Path:
        ruta = Path(directorio) / nombre
        ruta.write_text(codigo, encoding="utf-8")
        return ruta

    def test_violaciones_detecta_imports_prohibidos_y_relativos(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self._escribir(tmp, "a.py", "import os\n")
            b = self._escribir(tmp, "b.py", "def f():\n    import os\n")
            c = self._escribir(tmp, "c.py", "from . import hermano\n")
            d = self._escribir(tmp, "d.py", "from . import core\nimport re\n")
            self.assertEqual(_violaciones(_imports_todos(a), IMPORTS_CORE, set()), ["os"])
            self.assertEqual(_violaciones(_imports_todos(b), IMPORTS_CORE, set()), ["os"])
            self.assertEqual(len(_violaciones(_imports_todos(c), IMPORTS_SCAN, {"core"})), 1)
            self.assertEqual(_violaciones(_imports_todos(d), IMPORTS_SCAN, {"core"}), [])

    def test_detecta_estilos_de_import_de_datasources(self):
        estilos = (
            "import tools.datasources\n",
            "import datasources\n",
            "from tools.datasources import core\n",
            "from tools import datasources\n",
            "from . import datasources\n",
            "def f():\n    from tools.datasources import runtime\n",
        )
        with tempfile.TemporaryDirectory() as tmp:
            for i, codigo in enumerate(estilos):
                self.assertTrue(_referencias_a_datasources(self._escribir(tmp, f"m{i}.py", codigo)), codigo)
            self.assertEqual(_referencias_a_datasources(self._escribir(tmp, "l.py", "import json\n")), [])


if __name__ == "__main__":
    unittest.main()
