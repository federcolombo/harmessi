"""Tests estructurales de neutralidad del core de v0.5 (Change 4,
`20260917-cross-provider-hardening`). Mismo patrón que
`tools/tests/test_architecture_boundaries.py` (v0.4 Change 3): escaneo de
imports vía `ast`, no un analizador semántico completo -- límite deliberado,
documentado, no sobreingeniería (ver `design.md` de este Change, "Riesgos").

Objetivo: que el core de v0.5 (`tools/providers/core.py`,
`tools/routing/core.py`, `tools/fallback/core.py`,
`tools/harmessi_bench/core.py`) nunca dependa, ni por import ni por literal
de código, de un proveedor de IA concreto (p. ej. Claude Code) ni de
`subprocess` (que vive únicamente en los 4 adapters concretos:
`tools/providers/claude_code.py`, `codex.py`, `gemini.py`, `grok.py`), ni de
`tools.harmessi_bench` en el caso de `routing`/`fallback` (separación
"decidir/reintentar" vs "medir calidad").
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]

CORE_FILES = (
    "tools/providers/core.py",
    "tools/routing/core.py",
    "tools/fallback/core.py",
    "tools/harmessi_bench/core.py",
)

# Módulos de adapter de proveedor concreto (Change 0) -- ninguno de los 4
# `core.py` de arriba debe importarlos, sin importar el estilo del import.
MODULOS_ADAPTER_PROVEEDOR = ("claude_code", "codex", "gemini", "grok")

# Archivos que, además de no importar adapters de proveedor, tampoco deben
# importar `tools.harmessi_bench` (separación "decidir/reintentar" del motor
# de routing/fallback vs "medir calidad" de harmessi_bench).
ARCHIVOS_SIN_HARMESSI_BENCH = (
    "tools/routing/core.py",
    "tools/fallback/core.py",
)


def _imports_nivel_modulo(ruta_absoluta: Path) -> list:
    """Todos los `import x`/`from x import y` de nivel superior (arbol.body,
    no anidados), devuelve una lista de strings con el nombre completo
    referenciado por cada import. Mismo criterio que
    `test_architecture_boundaries.py::_imports_nivel_modulo`."""
    codigo = ruta_absoluta.read_text(encoding="utf-8")
    arbol = ast.parse(codigo, filename=str(ruta_absoluta))
    imports: list = []
    for nodo in arbol.body:
        if isinstance(nodo, ast.Import):
            imports.extend(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module:
                imports.extend(f"{nodo.module}.{alias.name}" for alias in nodo.names)
            else:
                imports.extend(alias.name for alias in nodo.names)
    return imports


def _nodos_docstring(arbol: ast.AST) -> set:
    """IDs de objeto (`id(nodo)`) de los nodos `ast.Constant` que funcionan
    como docstring (primer statement de un `Module`/`ClassDef`/`FunctionDef`/
    `AsyncFunctionDef` cuyo valor es un string) -- se excluyen del escaneo de
    literales `"claude"` para no marcar prosa de documentación como
    violación (ver `design.md`, R1: "sin falsos positivos de docstrings")."""
    ids = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            cuerpo = nodo.body
            if (
                cuerpo
                and isinstance(cuerpo[0], ast.Expr)
                and isinstance(cuerpo[0].value, ast.Constant)
                and isinstance(cuerpo[0].value.value, str)
            ):
                ids.add(id(cuerpo[0].value))
    return ids


def _literales_claude(ruta_absoluta: Path) -> list:
    """Strings literales (`ast.Constant`) que contienen 'claude'
    (case-insensitive), EXCLUYENDO los que son docstrings -- son los únicos
    literales que representarían un acoplamiento real de la lógica (una
    comparación, un argumento de llamada, un valor por default) a un
    proveedor concreto, no prosa documental."""
    codigo = ruta_absoluta.read_text(encoding="utf-8")
    arbol = ast.parse(codigo, filename=str(ruta_absoluta))
    ids_docstring = _nodos_docstring(arbol)

    violaciones = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            if id(nodo) in ids_docstring:
                continue
            if "claude" in nodo.value.lower():
                violaciones.append(nodo.value)
    return violaciones


class TestCoreNoImportaAdapterDeProveedor(unittest.TestCase):
    def test_ningun_core_importa_un_adapter_de_proveedor_concreto(self):
        violaciones = []
        for ruta_relativa in CORE_FILES:
            ruta_absoluta = REPO_ORIGEN / ruta_relativa
            for nombre_importado in _imports_nivel_modulo(ruta_absoluta):
                componente_final = nombre_importado.rsplit(".", 1)[-1]
                if componente_final in MODULOS_ADAPTER_PROVEEDOR:
                    violaciones.append(
                        f"{ruta_relativa} importa '{nombre_importado}' "
                        f"(adapter de proveedor concreto '{componente_final}')"
                    )
        self.assertEqual(
            violaciones,
            [],
            "Módulo(s) core de v0.5 importando un adapter de proveedor concreto -- "
            f"prohibido por docs/roadmap/v0.5.md Change 4: {violaciones}",
        )


class TestCoreNoImportaSubprocess(unittest.TestCase):
    def test_ningun_core_importa_subprocess(self):
        violaciones = []
        for ruta_relativa in CORE_FILES:
            ruta_absoluta = REPO_ORIGEN / ruta_relativa
            for nombre_importado in _imports_nivel_modulo(ruta_absoluta):
                componente_final = nombre_importado.rsplit(".", 1)[-1]
                if componente_final == "subprocess" or nombre_importado == "subprocess":
                    violaciones.append(f"{ruta_relativa} importa '{nombre_importado}'")
        self.assertEqual(
            violaciones,
            [],
            "Módulo(s) core de v0.5 importando 'subprocess' -- eso vive únicamente en los "
            f"4 adapters concretos (claude_code.py/codex.py/gemini.py/grok.py): {violaciones}",
        )


class TestRoutingYFallbackNoImportanHarmessiBench(unittest.TestCase):
    def test_routing_y_fallback_no_importan_harmessi_bench(self):
        violaciones = []
        for ruta_relativa in ARCHIVOS_SIN_HARMESSI_BENCH:
            ruta_absoluta = REPO_ORIGEN / ruta_relativa
            for nombre_importado in _imports_nivel_modulo(ruta_absoluta):
                if nombre_importado.startswith("tools.harmessi_bench") or nombre_importado.startswith(
                    "harmessi_bench"
                ):
                    violaciones.append(f"{ruta_relativa} importa '{nombre_importado}'")
        self.assertEqual(
            violaciones,
            [],
            "routing/core.py o fallback/core.py importando tools.harmessi_bench -- "
            "prohibido: 'decidir/reintentar' (routing/fallback) debe permanecer separado de "
            f"'medir calidad' (harmessi_bench), ver design.md de Change 3: {violaciones}",
        )


class TestCoreNoContieneLiteralClaude(unittest.TestCase):
    def test_ningun_core_contiene_el_literal_claude_fuera_de_docstrings(self):
        violaciones = {}
        for ruta_relativa in CORE_FILES:
            ruta_absoluta = REPO_ORIGEN / ruta_relativa
            encontrados = _literales_claude(ruta_absoluta)
            if encontrados:
                violaciones[ruta_relativa] = encontrados
        self.assertEqual(
            violaciones,
            {},
            "Módulo(s) core de v0.5 con el literal 'claude' en código real (no docstring) -- "
            f"el core no puede reconocer proveedores por nombre: {violaciones}",
        )


if __name__ == "__main__":
    unittest.main()
