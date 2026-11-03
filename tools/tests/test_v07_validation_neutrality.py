"""Tests estructurales de neutralidad de `tools/datacontracts/validation.py` (v0.7
Change 1, `20260922-data-contract-validation`). Mismo patrón `ast` que
`tools/tests/test_v07_core_neutrality.py` (Change 0), escaneando TODOS los imports del
archivo (`ast.walk`, incluidos los anidados en funciones), no solo los de nivel de
módulo.

Verifica (R1 de `spec.md`):
- `tools/datacontracts/validation.py` importa únicamente: stdlib permitida + `dsguard`
  (para `dsguard.checks`) + `datasources` (paquete completo, SIN restricción de
  símbolo -- excepción de dependencia de v0.8 Change 1 / M1, ver regla 11 de
  `ARCHITECTURE.md` y R2 de
  `openspec/changes/20260928-source-neutral-data-access/spec.md`: el evaluador único
  evalúa sobre `SourceObservation`) + imports relativos sibling `from . import core` y
  `from . import legacy_wording` (este último también parte de la excepción de M1) +
  `ds_profile.holdout_guard.verificar_permitido` (EXACTAMENTE ese único símbolo, de ese
  único módulo -- nunca `ds_profile.report`/`.column_stats`/`.fingerprint`/`.sampling`/
  `.quality_flags`/`.schema`/`.io_readers`, ni el paquete completo `ds_profile` sin
  calificar; a diferencia de `datasources`, que sí queda permitido sin calificar).
  Esta ampliación es puntual (la única excepción de dependencia aprobada por M1), no
  una relajación general de la frontera: cualquier otro paquete de `tools/` sigue
  prohibido.
- Ningún import de pandas, numpy, ni ningún otro paquete de `tools/`.
- Regresión: `tools/datacontracts/core.py` (Change 0) sigue solo-stdlib.
- Sanity: los detectores detectan violaciones reales de prueba (no pasan en vacío).
"""
from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]

VALIDATION_DATACONTRACTS = "tools/datacontracts/validation.py"
CORE_DATACONTRACTS = "tools/datacontracts/core.py"

# stdlib + `dsguard` (solo se usa `dsguard.checks`) permitidos a nivel de raíz de import;
# el import relativo (`.`) y `ds_profile` se validan aparte, con reglas más estrictas
# (ver `_violaciones_frontera_validation`).
IMPORTS_STDLIB_PERMITIDOS = {"__future__", "json", "pathlib", "typing", "sys", "datetime"}
# `datasources` se agrega por la excepción de dependencia de v0.8 Change 1 / M1 (paquete
# completo permitido, sin restricción de símbolo -- ver ARCHITECTURE.md regla 11).
IMPORTS_RAIZ_PERMITIDOS = IMPORTS_STDLIB_PERMITIDOS | {"dsguard", "ds_profile", "datasources", "."}

# Único símbolo de `ds_profile` que `validation.py` puede importar (design.md, decisión 3).
_DS_PROFILE_PERMITIDO = ("ds_profile.holdout_guard", "verificar_permitido")

# Imports relativos permitidos: el sibling `core` de `tools/datacontracts`, y desde v0.8
# Change 1 / M1 también `.legacy_wording` (misma excepción de dependencia).
_RELATIVOS_PERMITIDOS = {".core", ".legacy_wording"}

CORE_IMPORTS_PERMITIDOS = {"__future__", "dataclasses", "hashlib", "json", "re", "typing"}


def _parsear(ruta_absoluta: Path) -> ast.AST:
    return ast.parse(ruta_absoluta.read_text(encoding="utf-8"), filename=str(ruta_absoluta))


def _todos_los_imports(ruta_absoluta: Path) -> list:
    """Lista de `(modulo_raiz, nombre_completo)` de TODOS los imports del archivo
    (`ast.walk`). Un import relativo se reporta con raíz `.` y nombre
    `"." * nivel + modulo`."""
    resultado = []
    for nodo in ast.walk(_parsear(ruta_absoluta)):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                resultado.append((alias.name.split(".")[0], alias.name))
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level and nodo.level > 0:
                if nodo.module:
                    # `from .core import X` / `from ..pkg.core import X`
                    resultado.append((".", "." * nodo.level + nodo.module))
                else:
                    # `from . import core[, otro]` -- el módulo real está en `names`.
                    for alias in nodo.names:
                        resultado.append((".", "." * nodo.level + alias.name))
            else:
                resultado.append((nodo.module.split(".")[0], nodo.module))
    return resultado


def _nombres_importados_de_ds_profile(ruta_absoluta: Path) -> list:
    """Lista de `(modulo, alias_importado)` para cada import cuyo módulo (o, en
    `import x`, el propio `x`) empieza con `ds_profile`. `alias_importado` es `None`
    para `import ds_profile[.x]` (no importa un símbolo puntual)."""
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
    """Nombres/símbolos importados por `ruta_absoluta` que violan la frontera de
    imports de `validation.py` (R1): fuera del set de raíces permitidas, un import
    relativo que no sea alguno de los siblings `core`/`legacy_wording`, o cualquier
    símbolo de `ds_profile` que no sea exactamente
    `ds_profile.holdout_guard.verificar_permitido`."""
    violaciones: list = []
    for raiz, nombre in _todos_los_imports(ruta_absoluta):
        if raiz == ".":
            if nombre not in _RELATIVOS_PERMITIDOS:
                violaciones.append(nombre)
            continue
        if raiz == "ds_profile":
            continue  # validado aparte, símbolo por símbolo, abajo
        if raiz not in IMPORTS_RAIZ_PERMITIDOS:
            violaciones.append(nombre)
    for tupla in _nombres_importados_de_ds_profile(ruta_absoluta):
        if tupla != _DS_PROFILE_PERMITIDO:
            modulo, alias = tupla
            violaciones.append(f"{modulo}.{alias}" if alias else modulo)
    return violaciones


class TestValidationExiste(unittest.TestCase):
    def test_validation_es_un_archivo(self):
        self.assertTrue((REPO_ORIGEN / VALIDATION_DATACONTRACTS).is_file())


class TestValidationFronteraDeImports(unittest.TestCase):
    def test_imports_de_validation_pertenecen_al_set_permitido(self):
        violaciones = _violaciones_frontera_validation(REPO_ORIGEN / VALIDATION_DATACONTRACTS)
        self.assertEqual(
            violaciones,
            [],
            f"tools/datacontracts/validation.py importa fuera de la frontera permitida por R1 "
            f"(stdlib {sorted(IMPORTS_STDLIB_PERMITIDOS)} + dsguard.checks + "
            f"datasources (paquete completo, excepción M1) + "
            f"ds_profile.holdout_guard.verificar_permitido + siblings .core/.legacy_wording): "
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
        }
        for raiz, nombre in _todos_los_imports(REPO_ORIGEN / VALIDATION_DATACONTRACTS):
            self.assertNotIn(raiz, prohibidos_raiz, f"import prohibido en validation.py: {nombre}")

    def test_validation_solo_importa_verificar_permitido_de_ds_profile_holdout_guard(self):
        importados = _nombres_importados_de_ds_profile(REPO_ORIGEN / VALIDATION_DATACONTRACTS)
        self.assertEqual(
            importados,
            [_DS_PROFILE_PERMITIDO],
            f"validation.py debe importar EXACTAMENTE ds_profile.holdout_guard.verificar_permitido "
            f"(un solo símbolo, un solo módulo), se encontró: {importados}",
        )


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


class TestSanityDeLosDetectores(unittest.TestCase):
    """Los escáneres detectan violaciones reales, no pasan en vacío."""

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
                "import json\n"
                "import sys\n"
                "from pathlib import Path\n"
                "from dsguard import checks\n"
                "from ds_profile.holdout_guard import verificar_permitido\n"
                "from datasources import core as datasources_core\n"
                "from . import core as datacontracts_core\n"
                "from . import legacy_wording\n",
            )
            self.assertEqual(_violaciones_frontera_validation(limpio), [])

    def test_detecta_import_pandas(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "a.py", "import json\nimport pandas\n")
            self.assertEqual(_violaciones_frontera_validation(ruta), ["pandas"])

    def test_detecta_import_de_paquete_no_autorizado_pese_a_excepcion_datasources(self):
        """La excepción de M1 (`datasources` permitido) es puntual: cualquier otro
        paquete no autorizado (p. ej. `modelquality`) sigue detectándose como
        violación."""
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "h.py", "import json\nimport modelquality\n")
            self.assertEqual(_violaciones_frontera_validation(ruta), ["modelquality"])

    def test_detecta_import_pandas_anidado_en_funcion(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "b.py", "import json\n\ndef f():\n    import pandas as pd\n")
            self.assertEqual(_violaciones_frontera_validation(ruta), ["pandas"])

    def test_detecta_from_ds_profile_import_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "c.py", "from ds_profile import report\n")
            violaciones = _violaciones_frontera_validation(ruta)
            self.assertEqual(violaciones, ["ds_profile.report"])

    def test_detecta_from_ds_profile_column_stats_import_clasificar_dtype(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "d.py", "from ds_profile.column_stats import clasificar_dtype\n")
            violaciones = _violaciones_frontera_validation(ruta)
            self.assertEqual(violaciones, ["ds_profile.column_stats.clasificar_dtype"])

    def test_detecta_import_ds_profile_completo(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "e.py", "import ds_profile\n")
            violaciones = _violaciones_frontera_validation(ruta)
            self.assertEqual(violaciones, ["ds_profile"])

    def test_detecta_import_relativo_prohibido(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(tmp, "f.py", "from . import hermano\n")
            violaciones = _violaciones_frontera_validation(ruta)
            self.assertEqual(violaciones, [".hermano"])

    def test_permite_solo_verificar_permitido_de_holdout_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._escribir(
                tmp, "g.py", "from ds_profile.holdout_guard import verificar_permitido, verificar_salida_permitida\n"
            )
            violaciones = _violaciones_frontera_validation(ruta)
            self.assertEqual(violaciones, ["ds_profile.holdout_guard.verificar_salida_permitida"])


if __name__ == "__main__":
    unittest.main()
