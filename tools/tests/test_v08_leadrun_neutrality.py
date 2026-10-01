"""Tests estructurales de neutralidad de `tools/leadrun` (v0.8 Change 2,
`20260929-lead-execution-runtime`). Mismo patrón `ast` que
`test_v08_datasources_neutrality.py`, escaneando TODOS los imports (`ast.walk`,
incluidos los anidados en funciones) salvo donde se indique explícitamente
"solo nivel de módulo".

Verifica (R1-R3, R6, R15 de `spec.md`):
- `core.py` importa solo stdlib (`__future__`, `hashlib`, `json`, `re`,
  `dataclasses`, `typing`); sin `os`/`pathlib`/`sys`/`subprocess`/
  `importlib`, sin imports relativos, sin hermanos ni `tools.*`.
- `allowlist.py` importa stdlib (`__future__`, `os` -- vía `os.path`, `re`,
  `typing`) + `.core` (relativo).
- `scripts.py` importa stdlib (`__future__`, `subprocess`, `time`,
  `pathlib`, `typing`) + `.core` (relativo).
- `notebooks.py`: a nivel de módulo importa stdlib (`__future__`, `sys`,
  `pathlib`, `typing`) + `nbrunner` (bare, hermano de `tools/`) +
  `launcher_common` (bare) + `.core` (relativo); `from nbrunner import
  execute` NO aparece a nivel de módulo, solo dentro de una función
  (import perezoso).
- `runtime.py` importa stdlib (`__future__`, `json`, `os`, `re`, `sys`,
  `pathlib`, `typing`) + `dsguard`/`datasources` (bare) + `.allowlist`/
  `.core`/`.notebooks`/`.scripts` (relativos); NO importa `autonomy` ni
  `pathguard` en ninguna forma.
- `tools/notebook_runner.py` importa stdlib (`__future__`, `argparse`,
  `sys`, `pathlib`) + `dsguard` (bare) + `tools.leadrun.notebooks`
  (calificado, único caso permitido en todo el paquete).
- Dirección inversa (R2): ninguno de `dsguard`, `ds_profile`, `dsimpact`,
  `reporting`, `providers`, `routing`, `fallback`, `harmessi_bench`,
  `autonomy`, `modelquality`, `qualityevidence`, `datasources`,
  `datacontracts`, `nbrunner` importa `tools.leadrun`/`leadrun` -- SIN
  excepción documentada (a diferencia de la regla 11/`datasources`).
- Catálogo único de códigos `EXEC-*` (R6): ningún literal `EXEC-[A-Z-]+`
  fuera de `core.CODES` en `tools/leadrun/*.py` (incluidos sus tests) ni en
  `tools/notebook_runner.py`.
"""
from __future__ import annotations

import ast
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
_TOOLS_DIR = REPO_ORIGEN / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

CORE = "tools/leadrun/core.py"
ALLOWLIST = "tools/leadrun/allowlist.py"
SCRIPTS = "tools/leadrun/scripts.py"
NOTEBOOKS = "tools/leadrun/notebooks.py"
RUNTIME = "tools/leadrun/runtime.py"
NOTEBOOK_RUNNER = "tools/notebook_runner.py"

IMPORTS_CORE = {"__future__", "hashlib", "json", "re", "dataclasses", "typing"}
IMPORTS_ALLOWLIST = {"__future__", "os", "re", "typing"}
IMPORTS_SCRIPTS = {"__future__", "subprocess", "time", "pathlib", "typing"}
IMPORTS_NOTEBOOKS_MODULO = {"__future__", "sys", "pathlib", "typing", "nbrunner", "launcher_common"}
IMPORTS_RUNTIME = {"__future__", "json", "os", "re", "sys", "pathlib", "typing", "dsguard", "datasources"}
IMPORTS_NOTEBOOK_RUNNER = {"__future__", "argparse", "sys", "pathlib", "dsguard", "tools"}

PROHIBIDOS_CORE = {"os", "pathlib", "sys", "subprocess", "importlib"}

# Paquetes que NO deben importar `leadrun` en ninguna dirección (R2) -- sin
# excepción documentada (a diferencia de la regla 11/`datasources`, R2 de
# `spec.md` de este Change es explícita: "sin ninguna excepción").
PAQUETES_SIN_LEADRUN = (
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
    "tools/datasources",
    "tools/datacontracts",
    "tools/nbrunner",
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


def _referencias_a_leadrun(ruta: Path) -> list:
    """Detecta CUALQUIER estilo de referencia a `leadrun`/`tools.leadrun`
    (`ast.walk`, incluidos imports perezosos dentro de funciones):
    `import leadrun`, `import tools.leadrun`, `from leadrun import x`,
    `from tools.leadrun import x`, `from tools import leadrun`,
    `from . import leadrun`."""
    encontradas = []
    for nodo in ast.walk(_parsear(ruta)):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                partes = alias.name.split(".")
                if partes[0] == "leadrun" or partes[:2] == ["tools", "leadrun"]:
                    encontradas.append(f"import {alias.name}")
        elif isinstance(nodo, ast.ImportFrom):
            partes = nodo.module.split(".") if nodo.module else []
            if partes and (partes[0] == "leadrun" or partes[:2] == ["tools", "leadrun"]):
                encontradas.append(f"from {'.' * nodo.level}{nodo.module} import ...")
            for alias in nodo.names:
                if alias.name == "leadrun" and (not nodo.module or nodo.module == "tools"):
                    encontradas.append(f"from {'.' * nodo.level}{nodo.module or ''} import leadrun")
    return encontradas


_RE_CODIGO_EXEC = re.compile(r"^EXEC-[A-Z-]+$")


def _literales_exec(ruta: Path) -> list:
    """`[(codigo, lineno), ...]` de todos los literales string que matchean
    `^EXEC-[A-Z-]+$` en `ruta` (constantes de módulo, argumentos de llamada,
    literales en tests, etc. -- cualquier `ast.Constant`/`ast.Str`)."""
    encontrados = []
    for nodo in ast.walk(_parsear(ruta)):
        valor = None
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            valor = nodo.value
        elif hasattr(ast, "Str") and isinstance(nodo, getattr(ast, "Str")):
            valor = nodo.s
        if valor is not None and _RE_CODIGO_EXEC.match(valor):
            encontrados.append((valor, getattr(nodo, "lineno", -1)))
    return encontrados


class TestCoreLeadrunSoloStdlib(unittest.TestCase):
    def test_imports_de_core_pertenecen_al_set_permitido(self):
        imports = _imports_todos(_requerir(CORE))
        violaciones = _violaciones(imports, IMPORTS_CORE, set())
        self.assertEqual(violaciones, [], f"core.py importa fuera de {sorted(IMPORTS_CORE)}: {violaciones}")

    def test_core_no_importa_prohibidos_ni_hermanos(self):
        for nivel, modulo, nombres in _imports_todos(_requerir(CORE)):
            self.assertEqual(nivel, 0, f"import relativo en core.py: {modulo} {nombres}")
            self.assertFalse(
                PROHIBIDOS_CORE & set(modulo.split(".")), f"import prohibido en core.py: {modulo}"
            )


class TestAllowlistSoloStdlibYCore(unittest.TestCase):
    def test_imports_de_allowlist_pertenecen_al_set_permitido(self):
        imports = _imports_todos(_requerir(ALLOWLIST))
        violaciones = _violaciones(imports, IMPORTS_ALLOWLIST, {"core"})
        self.assertEqual(
            violaciones, [], f"allowlist.py importa fuera de {sorted(IMPORTS_ALLOWLIST)} y `.core`: {violaciones}"
        )


class TestScriptsIO(unittest.TestCase):
    def test_imports_de_scripts_pertenecen_al_set_permitido(self):
        imports = _imports_todos(_requerir(SCRIPTS))
        # `scripts.py` importa `core` (relativo), NO `allowlist` (D del
        # encargo: no se agrega `allowlist` como si fuera importado).
        violaciones = _violaciones(imports, IMPORTS_SCRIPTS, {"core"})
        self.assertEqual(
            violaciones, [], f"scripts.py importa fuera de {sorted(IMPORTS_SCRIPTS)} y `.core`: {violaciones}"
        )


class TestNotebooksImportPerezosoDeNbexecute(unittest.TestCase):
    def test_imports_de_nivel_modulo_pertenecen_al_set_permitido(self):
        imports = _imports_nivel_modulo(_requerir(NOTEBOOKS))
        violaciones = _violaciones(imports, IMPORTS_NOTEBOOKS_MODULO, {"core"})
        self.assertEqual(
            violaciones,
            [],
            f"notebooks.py importa a nivel de módulo fuera de {sorted(IMPORTS_NOTEBOOKS_MODULO)} "
            f"y `.core`: {violaciones}",
        )

    def test_nbexecute_no_aparece_a_nivel_de_modulo(self):
        for nivel, modulo, nombres in _imports_nivel_modulo(_requerir(NOTEBOOKS)):
            if modulo == "nbrunner":
                self.assertNotIn(
                    "execute", nombres,
                    "nbrunner.execute debe importarse de forma perezosa (dentro de una función), "
                    "nunca a nivel de módulo",
                )

    def test_nbexecute_si_aparece_dentro_de_una_funcion(self):
        arbol = _parsear(_requerir(NOTEBOOKS))
        encontrado = False
        for nodo_top in ast.walk(arbol):
            if isinstance(nodo_top, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for sub in ast.walk(nodo_top):
                    if isinstance(sub, ast.ImportFrom) and sub.module == "nbrunner":
                        if any(alias.name == "execute" for alias in sub.names):
                            encontrado = True
        self.assertTrue(
            encontrado, "nbrunner.execute debe importarse de forma perezosa dentro de alguna función"
        )


class TestRuntimeIO(unittest.TestCase):
    def test_imports_de_runtime_pertenecen_al_set_permitido(self):
        imports = _imports_todos(_requerir(RUNTIME))
        violaciones = _violaciones(imports, IMPORTS_RUNTIME, {"allowlist", "core", "notebooks", "scripts"})
        self.assertEqual(
            violaciones,
            [],
            f"runtime.py importa fuera de {sorted(IMPORTS_RUNTIME)} y "
            f"`.allowlist`/`.core`/`.notebooks`/`.scripts`: {violaciones}",
        )

    def test_runtime_no_importa_autonomy_ni_pathguard(self):
        for nivel, modulo, nombres in _imports_todos(_requerir(RUNTIME)):
            partes = modulo.split(".") if modulo else list(nombres)
            self.assertFalse(
                "autonomy" in partes or "pathguard" in partes,
                f"runtime.py no debe importar autonomy/pathguard (R1, spec.md): {modulo or nombres}",
            )


class TestNotebookRunnerCLI(unittest.TestCase):
    def test_imports_de_notebook_runner_pertenecen_al_set_permitido(self):
        imports = _imports_todos(_requerir(NOTEBOOK_RUNNER))
        # Sin imports relativos (nivel 0 en todos): `tools.leadrun.notebooks`
        # es el único calificado `tools.*`, ya incluido en `IMPORTS_NOTEBOOK_RUNNER`
        # vía el módulo top-level `tools`.
        violaciones = _violaciones(imports, IMPORTS_NOTEBOOK_RUNNER, set())
        self.assertEqual(
            violaciones,
            [],
            f"notebook_runner.py importa fuera de {sorted(IMPORTS_NOTEBOOK_RUNNER)}: {violaciones}",
        )

    def test_notebook_runner_importa_tools_leadrun_notebooks(self):
        encontrado = False
        for nivel, modulo, nombres in _imports_todos(_requerir(NOTEBOOK_RUNNER)):
            if modulo == "tools.leadrun" and "notebooks" in nombres:
                encontrado = True
        self.assertTrue(
            encontrado,
            "notebook_runner.py debe componer tools.leadrun.notebooks (único import calificado tools.* del paquete)",
        )


class TestDireccionInversaDeLeadrun(unittest.TestCase):
    def test_ningun_paquete_previo_importa_leadrun(self):
        violaciones = []
        for paquete in PAQUETES_SIN_LEADRUN:
            directorio = REPO_ORIGEN / paquete
            self.assertTrue(directorio.is_dir(), f"no existe el paquete {paquete}")
            for ruta in sorted(directorio.rglob("*.py")):
                if "__pycache__" in ruta.parts or "tests" in ruta.relative_to(directorio).parts:
                    continue
                for referencia in _referencias_a_leadrun(ruta):
                    violaciones.append(f"{ruta.relative_to(REPO_ORIGEN).as_posix()}: {referencia}")
        self.assertEqual(
            violaciones,
            [],
            f"Módulo(s) que importan `leadrun` (R2 de spec.md, regla 12 de ARCHITECTURE.md, "
            f"sin excepción documentada): {violaciones}",
        )


class TestCatalogoUnicoDeCodigosExec(unittest.TestCase):
    def test_ningun_codigo_exec_fuera_del_catalogo(self):
        from leadrun import core as leadrun_core  # solo-stdlib, import directo (R6)

        catalogo = set(leadrun_core.CODES)
        self.assertEqual(len(catalogo), 8, f"se esperaban 8 códigos EXEC-*, se encontraron {len(catalogo)}: {catalogo}")

        archivos = sorted((REPO_ORIGEN / "tools" / "leadrun").rglob("*.py"))
        archivos = [a for a in archivos if "__pycache__" not in a.parts]
        archivos.append(REPO_ORIGEN / "tools" / "notebook_runner.py")

        sobrantes = []
        for archivo in archivos:
            for codigo, lineno in _literales_exec(archivo):
                if codigo not in catalogo:
                    sobrantes.append(f"{archivo.relative_to(REPO_ORIGEN).as_posix()}:{lineno}: {codigo!r}")

        self.assertEqual(
            sobrantes,
            [],
            f"Código(s) EXEC-* fuera del catálogo único de core.CODES (R6 de spec.md): {sobrantes}",
        )


class TestSanityDeLosDetectoresNuevos(unittest.TestCase):
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
            self.assertEqual(len(_violaciones(_imports_todos(c), IMPORTS_ALLOWLIST, {"core"})), 1)
            self.assertEqual(_violaciones(_imports_todos(d), IMPORTS_ALLOWLIST, {"core"}), [])

    def test_detecta_estilos_de_import_de_leadrun(self):
        estilos = (
            "import tools.leadrun\n",
            "import leadrun\n",
            "from tools.leadrun import core\n",
            "from tools import leadrun\n",
            "from . import leadrun\n",
            "def f():\n    from leadrun import runtime\n",
        )
        with tempfile.TemporaryDirectory() as tmp:
            for i, codigo in enumerate(estilos):
                self.assertTrue(_referencias_a_leadrun(self._escribir(tmp, f"m{i}.py", codigo)), codigo)
            self.assertEqual(_referencias_a_leadrun(self._escribir(tmp, "l.py", "import json\n")), [])

    def test_literales_exec_detecta_codigo_sintetico_fuera_de_catalogo(self):
        with tempfile.TemporaryDirectory() as tmp:
            sintetico = self._escribir(tmp, "s.py", 'X = "EXEC-NO-EXISTE"\n')
            encontrados = _literales_exec(sintetico)
            self.assertEqual([codigo for codigo, _lineno in encontrados], ["EXEC-NO-EXISTE"])

            inocuo = self._escribir(tmp, "n.py", 'X = "algo-distinto"\n')
            self.assertEqual(_literales_exec(inocuo), [])


if __name__ == "__main__":
    unittest.main()
