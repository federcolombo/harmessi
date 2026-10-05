"""Tests estructurales de neutralidad de `tools/cards` (v0.9 Change 0,
`20261002-card-and-evidence-foundation`, R1 de `spec.md`). Mismo patrón `ast`
que `test_v08_datasources_neutrality.py`, escaneando TODOS los imports
(`ast.walk`, incluidos los anidados en funciones) salvo donde se indique
"solo nivel de módulo".

Verifica:
- `core.py` importa solo stdlib (`__future__`, `dataclasses`, `datetime`,
  `hashlib`, `json`, `re`, `unicodedata`, `typing`); sin imports relativos, sin
  `tools.*`, sin hermanos y sin ninguno de los paquetes prohibidos
  (`autonomy`, `datasources`, `qualityevidence`, `modelquality`,
  `datacontracts`, `leadrun`, `reporting`, `ds_init`, `ds_guard`, `harmessi`,
  `doctor`).
- `assess.py` a nivel de módulo importa solo stdlib + `core` (relativo, o
  `import core` como fallback de ejecución sin paquete padre); `dsguard`
  aparece SOLO de forma perezosa dentro de una función.
- Dirección inversa: ningún módulo de producción de `tools/` fuera de
  `tools/cards` importa `cards`.
- Ningún módulo de `tools/cards` (salvo el `dsguard` perezoso de `assess.py`)
  importa algo fuera de stdlib.
"""
from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]

CORE = "tools/cards/core.py"
ASSESS = "tools/cards/assess.py"
DIRECTORIO_CARDS = "tools/cards"

IMPORTS_CORE = {
    "__future__", "dataclasses", "datetime", "hashlib", "json", "re", "unicodedata", "typing",
}

# Paquetes/módulos que ni `core.py` ni `assess.py` pueden importar (a ningún nivel).
PROHIBIDOS = {
    "tools", "autonomy", "datasources", "qualityevidence", "modelquality", "datacontracts",
    "leadrun", "reporting", "ds_init", "ds_guard", "harmessi", "doctor",
}
# Además, `core.py` no puede importar a su hermano `assess` (ni a `cards`).
PROHIBIDOS_CORE = PROHIBIDOS | {"assess", "cards", "dsguard"}
# `assess.py` puede usar `dsguard`, pero solo de forma perezosa (se verifica aparte).
PROHIBIDOS_ASSESS = PROHIBIDOS

# Respaldo para Python < 3.10 (sin `sys.stdlib_module_names`): módulos stdlib
# plausibles en un paquete como éste.
_STDLIB_RESPALDO = frozenset({
    "__future__", "abc", "argparse", "ast", "base64", "collections", "contextlib", "copy",
    "dataclasses", "datetime", "enum", "errno", "functools", "hashlib", "io", "itertools",
    "json", "math", "os", "pathlib", "re", "shutil", "stat", "string", "sys", "tempfile",
    "textwrap", "types", "typing", "unicodedata", "uuid", "warnings",
})
STDLIB = frozenset(getattr(sys, "stdlib_module_names", ())) or _STDLIB_RESPALDO


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


def _recorrer_nivel_modulo(sentencias: list, acumulado: list) -> None:
    """Imports que se ejecutan al cargar el módulo: top-level y los dentro de
    `try`/`if` de nivel superior (p. ej. el import dual `try: from . import core
    / except ImportError: import core`). NO baja a funciones ni clases."""
    for nodo in sentencias:
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                acumulado.append((0, alias.name, (alias.name,)))
        elif isinstance(nodo, ast.ImportFrom):
            acumulado.append((nodo.level or 0, nodo.module or "", tuple(a.name for a in nodo.names)))
        elif isinstance(nodo, ast.Try):
            _recorrer_nivel_modulo(nodo.body, acumulado)
            for manejador in nodo.handlers:
                _recorrer_nivel_modulo(manejador.body, acumulado)
            _recorrer_nivel_modulo(nodo.orelse, acumulado)
            _recorrer_nivel_modulo(nodo.finalbody, acumulado)
        elif isinstance(nodo, ast.If):
            _recorrer_nivel_modulo(nodo.body, acumulado)
            _recorrer_nivel_modulo(nodo.orelse, acumulado)


def _imports_nivel_modulo(ruta: Path) -> list:
    resultado: list = []
    _recorrer_nivel_modulo(_parsear(ruta).body, resultado)
    return resultado


def _imports_perezosos(ruta: Path) -> list:
    """Imports que viven DENTRO de funciones/métodos (los perezosos)."""
    resultado = []
    for nodo in ast.walk(_parsear(ruta)):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(nodo):
                if isinstance(sub, ast.Import):
                    for alias in sub.names:
                        resultado.append((0, alias.name, (alias.name,)))
                elif isinstance(sub, ast.ImportFrom):
                    resultado.append((sub.level or 0, sub.module or "", tuple(a.name for a in sub.names)))
    return resultado


def _tokens(modulo: str, nombres: tuple) -> set:
    return set(modulo.split(".")) | set(nombres) if modulo else set(nombres)


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


def _prohibidos_presentes(imports: list, prohibidos: set) -> list:
    encontrados = []
    for nivel, modulo, nombres in imports:
        interseccion = _tokens(modulo, nombres) & prohibidos
        if interseccion:
            encontrados.append(f"{'.' * nivel}{modulo} import {','.join(nombres)} -> {sorted(interseccion)}")
    return encontrados


def _referencias_a_cards(ruta: Path) -> list:
    encontradas = []
    for nodo in ast.walk(_parsear(ruta)):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                partes = alias.name.split(".")
                if partes[0] == "cards" or partes[:2] == ["tools", "cards"]:
                    encontradas.append(f"import {alias.name}")
        elif isinstance(nodo, ast.ImportFrom):
            partes = nodo.module.split(".") if nodo.module else []
            if partes and (partes[0] == "cards" or partes[:2] == ["tools", "cards"]):
                encontradas.append(f"from {'.' * nodo.level}{nodo.module} import ...")
            for alias in nodo.names:
                if alias.name == "cards" and (not nodo.module or nodo.module == "tools"):
                    encontradas.append(f"from {'.' * nodo.level}{nodo.module or ''} import cards")
    return encontradas


def _modulos_cards() -> list:
    directorio = REPO_ORIGEN / DIRECTORIO_CARDS
    if not directorio.is_dir():
        raise AssertionError(f"no existe el paquete {DIRECTORIO_CARDS}")
    return [
        ruta
        for ruta in sorted(directorio.rglob("*.py"))
        if "__pycache__" not in ruta.parts and "tests" not in ruta.relative_to(directorio).parts
    ]


class TestCoreCardsSoloStdlib(unittest.TestCase):
    def test_imports_de_core_pertenecen_al_set_permitido(self):
        violaciones = _violaciones(_imports_todos(_requerir(CORE)), IMPORTS_CORE, set())
        self.assertEqual(violaciones, [], f"core.py importa fuera de {sorted(IMPORTS_CORE)}: {violaciones}")

    def test_core_sin_imports_relativos(self):
        for nivel, modulo, nombres in _imports_todos(_requerir(CORE)):
            self.assertEqual(nivel, 0, f"import relativo en core.py (hermano): {modulo} {nombres}")

    def test_core_no_importa_paquetes_prohibidos_ni_hermanos(self):
        encontrados = _prohibidos_presentes(_imports_todos(_requerir(CORE)), PROHIBIDOS_CORE)
        self.assertEqual(encontrados, [], f"core.py importa paquetes prohibidos (R1): {encontrados}")

    def test_core_no_importa_tools(self):
        for _nivel, modulo, nombres in _imports_todos(_requerir(CORE)):
            self.assertNotIn("tools", _tokens(modulo, nombres), f"core.py no debe importar tools.*: {modulo}")


class TestAssessSoloStdlibYCore(unittest.TestCase):
    def test_imports_de_nivel_modulo_son_stdlib_o_core(self):
        # `core` aparece como relativo (`from . import core`) y como fallback absoluto
        # (`import core`) en el `except ImportError` del import dual.
        imports = _imports_nivel_modulo(_requerir(ASSESS))
        violaciones = _violaciones(imports, set(STDLIB) | {"core"}, {"core"})
        self.assertEqual(
            violaciones, [], f"assess.py importa a nivel de módulo fuera de stdlib + `core`: {violaciones}"
        )

    def test_assess_importa_core(self):
        """Sanity: si `core` no aparece, la neutralidad de arriba sería vacua."""
        nombres = {
            (modulo, nombres)
            for _n, modulo, nombres in _imports_nivel_modulo(_requerir(ASSESS))
        }
        self.assertTrue(
            ("", ("core",)) in nombres or ("core", ("core",)) in nombres,
            "assess.py debe importar `core` a nivel de módulo",
        )

    def test_assess_no_importa_paquetes_prohibidos(self):
        encontrados = _prohibidos_presentes(_imports_todos(_requerir(ASSESS)), PROHIBIDOS_ASSESS)
        self.assertEqual(encontrados, [], f"assess.py importa paquetes prohibidos (R1): {encontrados}")

    def test_dsguard_no_aparece_a_nivel_de_modulo(self):
        for _nivel, modulo, nombres in _imports_nivel_modulo(_requerir(ASSESS)):
            self.assertNotIn(
                "dsguard", _tokens(modulo, nombres),
                "dsguard.checks debe importarse de forma perezosa (dentro de funciones), nunca a nivel de módulo",
            )

    def test_dsguard_si_aparece_dentro_de_una_funcion(self):
        perezosos = _imports_perezosos(_requerir(ASSESS))
        self.assertTrue(
            any("dsguard" in _tokens(modulo, nombres) for _n, modulo, nombres in perezosos),
            "dsguard.checks debe importarse de forma perezosa dentro de alguna función de assess.py",
        )

    def test_todos_los_imports_de_assess_son_stdlib_core_o_dsguard(self):
        violaciones = _violaciones(
            _imports_todos(_requerir(ASSESS)), set(STDLIB) | {"core", "dsguard"}, {"core"}
        )
        self.assertEqual(violaciones, [], f"assess.py importa fuera de stdlib/core/dsguard: {violaciones}")


class TestCardsSinDependenciasNoStdlib(unittest.TestCase):
    def test_hay_modulos_que_escanear(self):
        nombres = {ruta.name for ruta in _modulos_cards()}
        self.assertTrue({"core.py", "assess.py"} <= nombres, nombres)

    def test_ningun_modulo_de_cards_importa_fuera_de_stdlib(self):
        # Hermanos permitidos por módulo (estrictos, sin comodines): `core` para todos;
        # `assess` solo para datacard/modelcard/resolvers; `resolvers` solo para
        # datacard/modelcard.
        # Cada hermano vale como relativo (`from . import x`) y como fallback absoluto
        # (`import x`) del import dual.
        hermanos_por_modulo = {
            "tools/cards/datacard.py": {"core", "assess", "resolvers"},
            "tools/cards/resolvers.py": {"core", "assess"},
            "tools/cards/modelcard.py": {"core", "assess", "resolvers"},
            "tools/cards/govpolicy.py": {"core"},
            "tools/cards/modelgov.py": {"core", "assess", "govpolicy", "resolvers"},
        }
        violaciones = []
        for ruta in _modulos_cards():
            rel = ruta.relative_to(REPO_ORIGEN).as_posix()
            hermanos = hermanos_por_modulo.get(rel, {"core"})
            permitidos = set(STDLIB) | hermanos
            if rel == ASSESS:
                permitidos |= {"dsguard"}  # perezoso; verificado aparte
            for v in _violaciones(_imports_todos(ruta), permitidos, hermanos):
                violaciones.append(f"{rel}: {v}")
        self.assertEqual(violaciones, [], f"imports no-stdlib en tools/cards: {violaciones}")

    def test_dsguard_solo_en_assess(self):
        for ruta in _modulos_cards():
            rel = ruta.relative_to(REPO_ORIGEN).as_posix()
            if rel == ASSESS:
                continue
            for _n, modulo, nombres in _imports_todos(ruta):
                self.assertNotIn("dsguard", _tokens(modulo, nombres), f"{rel} importa dsguard")


class TestDireccionInversaDeCards(unittest.TestCase):
    def test_ningun_modulo_de_produccion_existente_importa_cards(self):
        directorio_tools = REPO_ORIGEN / "tools"
        directorio_cards = REPO_ORIGEN / DIRECTORIO_CARDS
        violaciones = []
        for ruta in sorted(directorio_tools.rglob("*.py")):
            partes = ruta.relative_to(directorio_tools).parts
            if "__pycache__" in partes or "tests" in partes:
                continue
            if directorio_cards in ruta.parents:
                continue
            for referencia in _referencias_a_cards(ruta):
                violaciones.append(f"{ruta.relative_to(REPO_ORIGEN).as_posix()}: {referencia}")
        self.assertEqual(
            violaciones,
            [],
            f"Módulo(s) de producción que importan `cards` (R1/R3: el paquete es inerte en v0.9 Change 0): {violaciones}",
        )


class TestSanityDeLosDetectores(unittest.TestCase):
    def _escribir(self, directorio: str, nombre: str, codigo: str) -> Path:
        ruta = Path(directorio) / nombre
        ruta.write_text(codigo, encoding="utf-8")
        return ruta

    def test_violaciones_detecta_no_stdlib_y_relativos(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self._escribir(tmp, "a.py", "import pandas\n")
            b = self._escribir(tmp, "b.py", "def f():\n    import numpy\n")
            c = self._escribir(tmp, "c.py", "from . import hermano\n")
            d = self._escribir(tmp, "d.py", "from . import core\nimport re\n")
            self.assertEqual(_violaciones(_imports_todos(a), IMPORTS_CORE, set()), ["pandas"])
            self.assertEqual(_violaciones(_imports_todos(b), IMPORTS_CORE, set()), ["numpy"])
            self.assertEqual(len(_violaciones(_imports_todos(c), IMPORTS_CORE, {"core"})), 1)
            self.assertEqual(_violaciones(_imports_todos(d), IMPORTS_CORE, {"core"}), [])

    def test_nivel_modulo_ve_try_pero_no_funciones(self):
        codigo = (
            "try:\n    from . import core\nexcept ImportError:\n    import core\n"
            "def f():\n    from dsguard import checks\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "m.py", codigo)
            nivel_modulo = {m or n[0] for _l, m, n in _imports_nivel_modulo(ruta)}
            self.assertEqual(nivel_modulo, {"core"})
            self.assertTrue(any("dsguard" in _tokens(m, n) for _l, m, n in _imports_perezosos(ruta)))

    def test_prohibidos_detecta_estilos(self):
        estilos = (
            "import tools.autonomy\n",
            "from tools import datasources\n",
            "from tools.reporting import x\n",
            "def f():\n    import ds_guard\n",
        )
        with tempfile.TemporaryDirectory() as tmp:
            for i, codigo in enumerate(estilos):
                ruta = self._escribir(tmp, f"p{i}.py", codigo)
                self.assertTrue(_prohibidos_presentes(_imports_todos(ruta), PROHIBIDOS), codigo)
            limpio = self._escribir(tmp, "l.py", "import json\nfrom typing import Any\n")
            self.assertEqual(_prohibidos_presentes(_imports_todos(limpio), PROHIBIDOS), [])

    def test_detecta_estilos_de_import_de_cards(self):
        estilos = (
            "import tools.cards\n",
            "import cards\n",
            "from tools.cards import core\n",
            "from tools import cards\n",
            "from . import cards\n",
            "def f():\n    from tools.cards import assess\n",
        )
        with tempfile.TemporaryDirectory() as tmp:
            for i, codigo in enumerate(estilos):
                self.assertTrue(_referencias_a_cards(self._escribir(tmp, f"m{i}.py", codigo)), codigo)
            self.assertEqual(_referencias_a_cards(self._escribir(tmp, "l.py", "import json\n")), [])


if __name__ == "__main__":
    unittest.main()
