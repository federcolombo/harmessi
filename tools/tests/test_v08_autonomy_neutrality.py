"""Tests estructurales de neutralidad de `tools/autonomy` (v0.8 Change 0). Mismo
patrón `ast` que `test_v07_core_neutrality.py`, escaneando TODOS los imports
(`ast.walk`, incluidos los anidados en funciones).

Verifica:
- `core.py` importa solo `dataclasses`, `typing`, `re`, `unicodedata`,
  `__future__`; ni `json`/`os`/`pathlib`/`sys`, ni `tools.*`, ni hermanos.
- `policy.py` importa solo stdlib acotada (`dataclasses`, `typing`, `types`,
  `re`, `collections.abc`, `__future__`) y `from . import core`; sin
  `json`/`os`/`pathlib`/`sys` ni `tools.*` (recibe `guard_policy_version_max`
  del llamador, no importa pathguard).
- Dirección inversa: ningún paquete previo importa `tools.autonomy`/`autonomy`,
  **con una única excepción documentada** (regla 10 de `ARCHITECTURE.md`,
  enmendada por v0.8 Change 3, `20260930-autonomous-sdd-and-remediation`):
  `tools/dsguard/sdd.py` importa `autonomy.core` (bare) para reutilizar
  `PreApprovedDecision`/`validate_pre_approved` al implementar checkpoints de
  negocio (R3 de ese Change) — el propio docstring de Change 0 en
  `tools/autonomy/core.py` ya anticipaba este consumidor ("Este modulo NO
  consulta control.json ni ningun archivo (eso es del Change 3)"). Ningún
  otro archivo de `tools/dsguard` ni de ningún otro paquete de
  `PAQUETES_SIN_AUTONOMY` importa `autonomy` — la excepción es puntual a un
  solo archivo, no relaja la regla general.
- `MODULOS_CORE` incluye `core.py` y `policy.py`.
"""
from __future__ import annotations

import ast
import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]

CORE = "tools/autonomy/core.py"
POLICY = "tools/autonomy/policy.py"

IMPORTS_CORE = {"__future__", "dataclasses", "typing", "re", "unicodedata"}
IMPORTS_POLICY = {"__future__", "dataclasses", "typing", "types", "re", "collections.abc"}
PROHIBIDOS = {"json", "os", "pathlib", "sys", "tools", "autonomy", "dsguard"}

PAQUETES_SIN_AUTONOMY = (
    "tools/dsguard",
    "tools/ds_profile",
    "tools/dsimpact",
    "tools/reporting",
    "tools/providers",
    "tools/routing",
    "tools/fallback",
    "tools/harmessi_bench",
    "tools/datacontracts",
    "tools/modelquality",
    "tools/qualityevidence",
)


def _requerir(ruta_relativa: str) -> Path:
    ruta = REPO_ORIGEN / ruta_relativa
    if not ruta.is_file():
        raise AssertionError(f"falta {ruta_relativa}: el archivo debe existir para verificar su neutralidad")
    return ruta


def _parsear(ruta: Path) -> ast.AST:
    return ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))


def _imports(ruta: Path) -> list:
    """Lista de `(nivel, modulo, nombres)` de TODOS los imports del archivo."""
    resultado = []
    for nodo in ast.walk(_parsear(ruta)):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                resultado.append((0, alias.name, (alias.name,)))
        elif isinstance(nodo, ast.ImportFrom):
            resultado.append((nodo.level or 0, nodo.module or "", tuple(a.name for a in nodo.names)))
    return resultado


def _violaciones(ruta: Path, permitidos: set, relativos_permitidos: set) -> list:
    """Imports fuera del set permitido. Un import relativo solo es válido si es
    `from . import <nombre>` con `<nombre>` en `relativos_permitidos`."""
    violaciones = []
    for nivel, modulo, nombres in _imports(ruta):
        if nivel:
            if nivel == 1 and not modulo and set(nombres) <= relativos_permitidos:
                continue
            violaciones.append("." * nivel + modulo + " import " + ",".join(nombres))
        elif modulo not in permitidos:
            violaciones.append(modulo)
    return violaciones


def _referencias_a_autonomy(ruta: Path) -> list:
    encontradas = []
    for nodo in ast.walk(_parsear(ruta)):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                partes = alias.name.split(".")
                if partes[0] == "autonomy" or partes[:2] == ["tools", "autonomy"]:
                    encontradas.append(f"import {alias.name}")
        elif isinstance(nodo, ast.ImportFrom):
            partes = nodo.module.split(".") if nodo.module else []
            if partes and (partes[0] == "autonomy" or partes[:2] == ["tools", "autonomy"]):
                encontradas.append(f"from {'.' * nodo.level}{nodo.module} import ...")
            for alias in nodo.names:
                if alias.name == "autonomy" and (not nodo.module or nodo.module == "tools"):
                    encontradas.append(f"from {'.' * nodo.level}{nodo.module or ''} import autonomy")
    return encontradas


class TestCoreAutonomySoloStdlib(unittest.TestCase):
    def test_imports_de_core_pertenecen_al_set_permitido(self):
        violaciones = _violaciones(_requerir(CORE), IMPORTS_CORE, set())
        self.assertEqual(violaciones, [], f"core.py importa fuera de {sorted(IMPORTS_CORE)}: {violaciones}")

    def test_core_no_importa_prohibidos(self):
        for nivel, modulo, nombres in _imports(_requerir(CORE)):
            self.assertEqual(nivel, 0, f"import relativo en core.py: {modulo} {nombres}")
            self.assertFalse(PROHIBIDOS & set(modulo.split(".")), f"import prohibido en core.py: {modulo}")


class TestPolicyAutonomySoloStdlibYCore(unittest.TestCase):
    def test_imports_de_policy_pertenecen_al_set_permitido(self):
        violaciones = _violaciones(_requerir(POLICY), IMPORTS_POLICY, {"core"})
        self.assertEqual(
            violaciones, [], f"policy.py importa fuera de {sorted(IMPORTS_POLICY)} y `from . import core`: {violaciones}"
        )

    def test_policy_no_importa_prohibidos(self):
        for nivel, modulo, nombres in _imports(_requerir(POLICY)):
            if nivel:
                continue
            self.assertFalse(PROHIBIDOS & set(modulo.split(".")), f"import prohibido en policy.py: {modulo}")


# Excepción documentada (v0.8 Change 3, R3/D1-D3 de
# `20260930-autonomous-sdd-and-remediation`): único archivo de todos los
# paquetes de `PAQUETES_SIN_AUTONOMY` que puede importar `autonomy`.
EXCEPCION_DSGUARD_SDD = "tools/dsguard/sdd.py"


class TestNingunPaqueteImportaAutonomy(unittest.TestCase):
    def test_ningun_modulo_de_los_paquetes_previos_importa_autonomy(self):
        violaciones = []
        for paquete in PAQUETES_SIN_AUTONOMY:
            directorio = REPO_ORIGEN / paquete
            self.assertTrue(directorio.is_dir(), f"no existe el paquete {paquete}")
            for ruta in sorted(directorio.rglob("*.py")):
                if "__pycache__" in ruta.parts or "tests" in ruta.relative_to(directorio).parts:
                    continue
                rel = ruta.relative_to(REPO_ORIGEN).as_posix()
                if rel == EXCEPCION_DSGUARD_SDD:
                    continue
                for referencia in _referencias_a_autonomy(ruta):
                    violaciones.append(f"{rel}: {referencia}")
        self.assertEqual(
            violaciones,
            [],
            f"Módulo(s) que importan `autonomy` fuera de la excepción documentada "
            f"({EXCEPCION_DSGUARD_SDD}, regla 10 de ARCHITECTURE.md): {violaciones}",
        )

    def test_la_excepcion_documentada_si_importa_autonomy_de_forma_bare(self):
        """La excepción es real (no un olvido): `sdd.py` importa `autonomy.core`
        de forma bare (`from autonomy import core`, mismo estilo que el resto
        del repo tras `sys.path.insert(0, tools_dir)`), nunca calificada como
        `tools.autonomy`."""
        referencias = _referencias_a_autonomy(_requerir(EXCEPCION_DSGUARD_SDD))
        self.assertTrue(referencias, f"{EXCEPCION_DSGUARD_SDD} debería importar autonomy (excepción documentada)")
        self.assertTrue(
            any(ref.startswith("from autonomy import") for ref in referencias),
            f"se esperaba un import bare 'from autonomy import ...', se encontró: {referencias}",
        )


class TestAutonomyEnModulosCore(unittest.TestCase):
    def test_modulos_core_incluye_autonomy(self):
        ruta = REPO_ORIGEN / "tools" / "tests" / "test_architecture_boundaries.py"
        especificacion = importlib.util.spec_from_file_location("_arch_boundaries_v08", ruta)
        modulo = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(modulo)
        self.assertIn(CORE, modulo.MODULOS_CORE)
        self.assertIn(POLICY, modulo.MODULOS_CORE)


class TestSanityDeLosDetectores(unittest.TestCase):
    def _escribir(self, directorio: str, nombre: str, codigo: str) -> Path:
        ruta = Path(directorio) / nombre
        ruta.write_text(codigo, encoding="utf-8")
        return ruta

    def test_violaciones_detecta_imports_prohibidos_y_relativos(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self._escribir(tmp, "a.py", "import json\n")
            b = self._escribir(tmp, "b.py", "def f():\n    import os\n")
            c = self._escribir(tmp, "c.py", "from . import hermano\n")
            d = self._escribir(tmp, "d.py", "from . import core\nimport re\n")
            self.assertEqual(_violaciones(a, IMPORTS_CORE, set()), ["json"])
            self.assertEqual(_violaciones(b, IMPORTS_CORE, set()), ["os"])
            self.assertEqual(len(_violaciones(c, IMPORTS_POLICY, {"core"})), 1)
            self.assertEqual(_violaciones(d, IMPORTS_POLICY, {"core"}), [])

    def test_detecta_estilos_de_import_de_autonomy(self):
        estilos = (
            "import tools.autonomy\n",
            "import autonomy\n",
            "from tools.autonomy import core\n",
            "from tools import autonomy\n",
            "from . import autonomy\n",
            "def f():\n    from tools.autonomy import policy\n",
        )
        with tempfile.TemporaryDirectory() as tmp:
            for i, codigo in enumerate(estilos):
                self.assertTrue(_referencias_a_autonomy(self._escribir(tmp, f"m{i}.py", codigo)), codigo)
            self.assertEqual(_referencias_a_autonomy(self._escribir(tmp, "l.py", "import json\n")), [])


if __name__ == "__main__":
    unittest.main()
