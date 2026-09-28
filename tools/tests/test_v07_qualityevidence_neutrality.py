"""Tests estructurales de neutralidad de `tools/qualityevidence` (v0.7 Change 3,
`20260922-quality-evidence-and-drift`). Mismo patrón `ast` que
`tools/tests/test_v07_modelquality_neutrality.py`/`test_v07_validation_neutrality.py`,
cubriendo AMBOS módulos de este Change en un solo archivo (`core.py` y
`evidence.py` por separado), escaneando TODOS los imports (`ast.walk`,
incluidos los anidados en funciones).

Verifica (R1/R21 de `spec.md`):
- `tools/qualityevidence/core.py` importa únicamente de la stdlib permitida
  (`__future__, dataclasses, datetime, hashlib, json, re, secrets, typing`) y
  no referencia `tools.datacontracts`, `tools.modelquality`, `tools.reporting`,
  `ds_profile`, `dsguard`, pandas, numpy.
- `tools/qualityevidence/evidence.py` importa: esa misma stdlib permitida (más
  `os`, `sys`, `tempfile`, `pathlib`) + `dsguard` (para `dsguard.checks`) +
  EXACTAMENTE `ds_profile.holdout_guard.verificar_permitido` (ningún otro
  símbolo de `ds_profile`, nunca `ds_profile.fingerprint`) + el sibling
  `tools.qualityevidence.core` (import relativo `.core`); nunca
  `tools.datacontracts`, `tools.modelquality`, `tools.reporting`, pandas,
  numpy, ni ningún otro paquete de `tools/`.
- `tools/qualityevidence/__init__.py` no tiene cuerpo (salvo docstring).
- Dirección inversa de la regla 9 de ARCHITECTURE.md: ningún módulo de
  `dsguard`, `ds_profile`, `dsimpact`, `reporting`, `tools.datacontracts`,
  `tools.modelquality`, `providers`, `routing`, `fallback` ni `harmessi_bench`
  importa `tools.qualityevidence` (ningún estilo de import).
- `MODULOS_CORE` de `test_architecture_boundaries.py` incluye ambos módulos.
"""
from __future__ import annotations

import ast
import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]

CORE_QUALITYEVIDENCE = "tools/qualityevidence/core.py"
EVIDENCE_QUALITYEVIDENCE = "tools/qualityevidence/evidence.py"
INIT_QUALITYEVIDENCE = "tools/qualityevidence/__init__.py"

# --- core.py: solo stdlib -------------------------------------------------------

CORE_IMPORTS_PERMITIDOS = {"__future__", "dataclasses", "datetime", "hashlib", "json", "re", "secrets", "typing"}
CORE_FRAGMENTOS_PROHIBIDOS = ("pandas", "numpy", "ds_profile", "dsguard", "reporting", "datacontracts", "modelquality")

# --- evidence.py: stdlib + dsguard.checks + ds_profile.holdout_guard.verificar_permitido + sibling .core --

EVIDENCE_STDLIB_PERMITIDOS = {
    "__future__",
    "dataclasses",
    "datetime",
    "hashlib",
    "json",
    "os",
    "re",
    "secrets",
    "sys",
    "tempfile",
    "typing",
    "pathlib",
}
EVIDENCE_RAIZ_PERMITIDOS = EVIDENCE_STDLIB_PERMITIDOS | {"dsguard", "."}
EVIDENCE_RELATIVO_PERMITIDO = ".core"

# Único símbolo de `ds_profile` que `evidence.py` puede importar.
_DS_PROFILE_PERMITIDO = ("ds_profile.holdout_guard", "verificar_permitido")

PAQUETES_SIN_QUALITYEVIDENCE = (
    "tools/dsguard",
    "tools/ds_profile",
    "tools/dsimpact",
    "tools/reporting",
    "tools/datacontracts",
    "tools/modelquality",
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
    return [nombre for raiz, nombre in _todos_los_imports(ruta_absoluta) if raiz not in CORE_IMPORTS_PERMITIDOS]


def _nombres_importados_de_ds_profile(ruta_absoluta: Path) -> list:
    """Lista de `(modulo, alias_importado)` para cada import cuyo módulo (o,
    en `import x`, el propio `x`) empieza con `ds_profile`. `alias_importado`
    es `None` para `import ds_profile[.x]`."""
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


def _violaciones_frontera_evidence(ruta_absoluta: Path) -> list:
    """Nombres/símbolos importados por `evidence.py` fuera de su frontera
    permitida: stdlib autorizada + `dsguard` + el sibling `.core`, y
    cualquier símbolo de `ds_profile` que no sea exactamente
    `ds_profile.holdout_guard.verificar_permitido`."""
    violaciones: list = []
    for raiz, nombre in _todos_los_imports(ruta_absoluta):
        if raiz == ".":
            if nombre != EVIDENCE_RELATIVO_PERMITIDO:
                violaciones.append(nombre)
            continue
        if raiz == "ds_profile":
            continue  # reportado aparte, símbolo por símbolo, abajo
        if raiz not in EVIDENCE_RAIZ_PERMITIDOS:
            violaciones.append(nombre)
    for tupla in _nombres_importados_de_ds_profile(ruta_absoluta):
        if tupla != _DS_PROFILE_PERMITIDO:
            modulo, alias = tupla
            violaciones.append(f"{modulo}.{alias}" if alias else modulo)
    return violaciones


def _referencias_a_qualityevidence(ruta_absoluta: Path) -> list:
    """Imports del archivo que apuntan a `qualityevidence` con cualquier
    estilo: `import tools.qualityevidence[.x]`, `import qualityevidence`,
    `from tools.qualityevidence[.x] import y`, `from qualityevidence import y`,
    `from tools import qualityevidence`, `from . import qualityevidence`,
    `from .qualityevidence import y`."""
    encontradas = []
    for nodo in ast.walk(_parsear(ruta_absoluta)):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                partes = alias.name.split(".")
                if partes[0] == "qualityevidence" or partes[:2] == ["tools", "qualityevidence"]:
                    encontradas.append(f"import {alias.name}")
        elif isinstance(nodo, ast.ImportFrom):
            partes = nodo.module.split(".") if nodo.module else []
            if partes and (partes[0] == "qualityevidence" or partes[:2] == ["tools", "qualityevidence"]):
                encontradas.append(f"from {'.' * nodo.level}{nodo.module} import ...")
            for alias in nodo.names:
                if alias.name == "qualityevidence" and (not nodo.module or nodo.module == "tools"):
                    encontradas.append(f"from {'.' * nodo.level}{nodo.module or ''} import qualityevidence")
    return encontradas


class TestCoreQualityEvidenceSoloStdlib(unittest.TestCase):
    def test_core_existe(self):
        self.assertTrue((REPO_ORIGEN / CORE_QUALITYEVIDENCE).is_file())

    def test_imports_de_core_pertenecen_al_set_permitido(self):
        violaciones = _violaciones_whitelist_core(REPO_ORIGEN / CORE_QUALITYEVIDENCE)
        self.assertEqual(
            violaciones,
            [],
            f"tools/qualityevidence/core.py importa fuera de la stdlib permitida "
            f"{sorted(CORE_IMPORTS_PERMITIDOS)}: {violaciones}",
        )

    def test_core_no_referencia_librerias_ni_hermanos_prohibidos(self):
        prohibidos = {"pandas", "numpy", "dsguard", "ds_profile", "reporting", "tools", "datacontracts", "modelquality"}
        for raiz, nombre in _todos_los_imports(REPO_ORIGEN / CORE_QUALITYEVIDENCE):
            partes = set(nombre.split("."))
            self.assertFalse(prohibidos & partes, f"import prohibido en core.py: {nombre}")

    def test_identificadores_de_core_no_referencian_librerias_prohibidas(self):
        violaciones = [
            identificador
            for identificador in _identificadores(REPO_ORIGEN / CORE_QUALITYEVIDENCE)
            if any(f in identificador.lower() for f in CORE_FRAGMENTOS_PROHIBIDOS)
        ]
        self.assertEqual(violaciones, [], f"identificadores prohibidos en core.py: {violaciones}")

    def test_init_de_qualityevidence_esta_vacio(self):
        arbol = _parsear(REPO_ORIGEN / INIT_QUALITYEVIDENCE)
        cuerpo = list(arbol.body)
        if (
            cuerpo
            and isinstance(cuerpo[0], ast.Expr)
            and isinstance(cuerpo[0].value, ast.Constant)
            and isinstance(cuerpo[0].value.value, str)
        ):
            cuerpo = cuerpo[1:]
        self.assertEqual(cuerpo, [], "tools/qualityevidence/__init__.py no debe tener lógica ni imports")
        self.assertEqual(_todos_los_imports(REPO_ORIGEN / INIT_QUALITYEVIDENCE), [])


class TestEvidenceQualityEvidenceFrontera(unittest.TestCase):
    def test_evidence_existe(self):
        self.assertTrue((REPO_ORIGEN / EVIDENCE_QUALITYEVIDENCE).is_file())

    def test_imports_de_evidence_pertenecen_al_set_permitido(self):
        violaciones = _violaciones_frontera_evidence(REPO_ORIGEN / EVIDENCE_QUALITYEVIDENCE)
        self.assertEqual(
            violaciones,
            [],
            f"tools/qualityevidence/evidence.py importa fuera de la frontera permitida por R1 "
            f"(stdlib {sorted(EVIDENCE_STDLIB_PERMITIDOS)} + dsguard.checks + "
            f"ds_profile.holdout_guard.verificar_permitido + sibling .core): {violaciones}",
        )

    def test_evidence_no_importa_pandas_numpy_ni_otros_paquetes_de_tools(self):
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
            "datacontracts",
            "modelquality",
        }
        for raiz, nombre in _todos_los_imports(REPO_ORIGEN / EVIDENCE_QUALITYEVIDENCE):
            self.assertNotIn(raiz, prohibidos_raiz, f"import prohibido en evidence.py: {nombre}")

    def test_evidence_no_importa_datacontracts_ni_modelquality_ni_reporting(self):
        for raiz, nombre in _todos_los_imports(REPO_ORIGEN / EVIDENCE_QUALITYEVIDENCE):
            partes = set(nombre.split("."))
            self.assertFalse(
                {"datacontracts", "modelquality", "reporting"} & partes, f"import prohibido en evidence.py: {nombre}"
            )

    def test_evidence_solo_importa_verificar_permitido_de_ds_profile_holdout_guard(self):
        importados = _nombres_importados_de_ds_profile(REPO_ORIGEN / EVIDENCE_QUALITYEVIDENCE)
        self.assertEqual(
            importados,
            [_DS_PROFILE_PERMITIDO],
            f"evidence.py debe importar EXACTAMENTE ds_profile.holdout_guard.verificar_permitido "
            f"(un solo símbolo, un solo módulo), se encontró: {importados}",
        )


class TestQualityEvidenceEnModulosCore(unittest.TestCase):
    def test_modulos_core_incluye_core_y_evidence(self):
        ruta = REPO_ORIGEN / "tools" / "tests" / "test_architecture_boundaries.py"
        especificacion = importlib.util.spec_from_file_location("_arch_boundaries_qe", ruta)
        modulo = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(modulo)
        self.assertIn(CORE_QUALITYEVIDENCE, modulo.MODULOS_CORE)
        self.assertIn(EVIDENCE_QUALITYEVIDENCE, modulo.MODULOS_CORE)


class TestNingunPaqueteImportaQualityEvidence(unittest.TestCase):
    def test_ningun_modulo_de_los_paquetes_previos_importa_qualityevidence(self):
        violaciones = []
        for paquete in PAQUETES_SIN_QUALITYEVIDENCE:
            directorio = REPO_ORIGEN / paquete
            self.assertTrue(directorio.is_dir(), f"no existe el paquete {paquete}")
            for ruta in sorted(directorio.rglob("*.py")):
                if "__pycache__" in ruta.parts or "tests" in ruta.relative_to(directorio).parts:
                    continue
                for referencia in _referencias_a_qualityevidence(ruta):
                    violaciones.append(f"{ruta.relative_to(REPO_ORIGEN).as_posix()}: {referencia}")
        self.assertEqual(
            violaciones,
            [],
            "Módulo(s) que importan `qualityevidence` -- prohibido por la regla 9 de ARCHITECTURE.md "
            f"(la dependencia es solo qualityevidence -> dsguard/ds_profile, nunca al revés): {violaciones}",
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

    def test_frontera_evidence_archivo_limpio(self):
        with tempfile.TemporaryDirectory() as tmp:
            limpio = self._escribir(
                tmp,
                "limpio.py",
                "from __future__ import annotations\n"
                "import os\n"
                "import tempfile\n"
                "from pathlib import Path\n"
                "from dsguard import checks\n"
                "from ds_profile.holdout_guard import verificar_permitido\n"
                "from . import core as qe_core\n",
            )
            self.assertEqual(_violaciones_frontera_evidence(limpio), [])

    def test_frontera_evidence_detecta_pandas(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "a.py", "import json\nimport pandas\n")
            self.assertEqual(_violaciones_frontera_evidence(ruta), ["pandas"])

    def test_frontera_evidence_detecta_ds_profile_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "b.py", "from ds_profile import fingerprint\n")
            self.assertEqual(_violaciones_frontera_evidence(ruta), ["ds_profile.fingerprint"])

    def test_frontera_evidence_detecta_import_relativo_prohibido(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "c.py", "from . import hermano\n")
            self.assertEqual(_violaciones_frontera_evidence(ruta), [".hermano"])

    def test_frontera_evidence_permite_solo_verificar_permitido(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(
                tmp, "d.py", "from ds_profile.holdout_guard import verificar_permitido, verificar_salida_permitida\n"
            )
            self.assertEqual(_violaciones_frontera_evidence(ruta), ["ds_profile.holdout_guard.verificar_salida_permitida"])

    def test_detecta_todos_los_estilos_de_import_de_qualityevidence(self):
        estilos = (
            "import tools.qualityevidence\n",
            "import tools.qualityevidence.core as c\n",
            "import qualityevidence\n",
            "from tools.qualityevidence import core\n",
            "from tools.qualityevidence.core import QualityEvidenceManifest\n",
            "from qualityevidence import core\n",
            "from tools import qualityevidence\n",
            "from . import qualityevidence\n",
            "from .qualityevidence import core\n",
            "from .. import qualityevidence\n",
            "def f():\n    from tools.qualityevidence import core\n",
        )
        with tempfile.TemporaryDirectory() as tmp:
            for i, codigo in enumerate(estilos):
                ruta = self._escribir(tmp, f"m{i}.py", codigo)
                self.assertTrue(_referencias_a_qualityevidence(ruta), f"no detectó: {codigo!r}")
            limpio = self._escribir(
                tmp, "limpio.py", "import json\nfrom tools.dsguard import core\nfrom . import otro\n"
            )
            self.assertEqual(_referencias_a_qualityevidence(limpio), [])


if __name__ == "__main__":
    unittest.main()
