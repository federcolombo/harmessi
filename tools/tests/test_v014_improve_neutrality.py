"""Neutralidad de `tools/harmessi_improve` (v0.14 Change 1, R13).

Verifica por AST (todos los imports, incluidos los anidados en funciones) que:
- el paquete importa solo stdlib, sí mismo, `tools.harmessi_bench`, `tools.dsguard`,
  `tools.ds_init.version` y `tools.providers.core`;
- no usa subprocess ni red (ni telemetría);
- ningún provider concreto aparece en los imports;
- ningún módulo (no test) de `tools/dsguard` ni `tools/harmessi_bench` lo importa.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DIR_IMPROVE = RAIZ / "tools" / "harmessi_improve"

PREFIJOS_PERMITIDOS = (
    "tools.harmessi_improve",
    "tools.harmessi_bench",
    "tools.dsguard",
)
PROHIBIDOS = frozenset({
    "subprocess", "socket", "urllib", "http", "requests", "ftplib", "smtplib", "webbrowser",
    "importlib",
})
PROVIDERS_CONCRETOS = ("claude_code", "codex", "gemini", "grok")


def _modulos_fuente(directorio: Path):
    return sorted(p for p in directorio.rglob("*.py") if "tests" not in p.relative_to(directorio).parts)


def _imports(ruta: Path):
    """Lista de `(modulo, nivel, nombres)` de todo import del archivo."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    salida = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                salida.append((alias.name, 0, ()))
        elif isinstance(nodo, ast.ImportFrom):
            salida.append((nodo.module or "", nodo.level, tuple(a.name for a in nodo.names)))
    return salida


def _es_permitido(modulo: str, archivo: str = "") -> bool:
    raiz = modulo.split(".")[0]
    if raiz in sys.stdlib_module_names or raiz == "__future__":
        return True
    if modulo == "tools.ds_init.version":
        return True
    # v0.14 Change 2 (R11): el contrato neutral de invocación solo para probe.py.
    if modulo == "tools.providers.core":
        return archivo == "probe.py"
    # v0.14 Change 5 (R10): la CLI resuelve el provider con import diferido de PROVIDER_REGISTRY.
    if modulo == "tools.providers":
        return archivo == "cli.py"
    return any(modulo == p or modulo.startswith(p + ".") for p in PREFIJOS_PERMITIDOS)


class TestNeutralidadImprove(unittest.TestCase):
    def test_hay_modulos(self):
        nombres = {p.name for p in _modulos_fuente(DIR_IMPROVE)}
        self.assertTrue({"__init__.py", "candidate.py", "budget.py", "policy.py", "probe.py", "decision.py", "promotion.py",
                          "lessons.py", "cycle.py", "cli.py", "__main__.py"} <= nombres)

    def test_cycle_no_importa_promotion_ni_lessons_y_solo_lessons_importa_promotion(self):
        """v0.14 Change 5: el ciclo no promueve ni escribe lessons; `promotion` solo lo usan `lessons`
        y la CLI (`cli.py`, que además es el único que importa `lessons`)."""
        for ruta in _modulos_fuente(DIR_IMPROVE):
            for modulo, _nivel, nombres in _imports(ruta):
                textos = (modulo,) + tuple(nombres)
                importa_promotion = any(t.endswith("promotion") or ".promotion" in t for t in textos)
                importa_lessons = any(t.endswith("lessons") or ".lessons" in t for t in textos)
                with self.subTest(archivo=ruta.name, modulo=modulo):
                    if ruta.name == "cycle.py":
                        self.assertFalse(importa_promotion or importa_lessons)
                    if importa_promotion:
                        self.assertIn(ruta.name, ("lessons.py", "cli.py"))
                    if importa_lessons:
                        self.assertEqual(ruta.name, "cli.py", "solo la CLI importa lessons")

    def test_imports_permitidos(self):
        for ruta in _modulos_fuente(DIR_IMPROVE):
            for modulo, nivel, nombres in _imports(ruta):
                with self.subTest(archivo=ruta.name, modulo=modulo):
                    self.assertEqual(nivel, 0, "imports relativos no permitidos")
                    self.assertTrue(_es_permitido(modulo, ruta.name), f"import no permitido: {modulo}")
                    if modulo == "tools":
                        self.fail(f"import desde 'tools' directo: {nombres}")

    def test_providers_core_solo_invocation_request(self):
        """R11: de `tools.providers.core` solo se importa `InvocationRequest` (y solo en probe.py).
        R10 (Change 5): de `tools.providers` solo `PROVIDER_REGISTRY`, y solo en cli.py (import diferido)."""
        for ruta in _modulos_fuente(DIR_IMPROVE):
            for modulo, _nivel, nombres in _imports(ruta):
                if modulo == "tools.providers" or modulo.startswith("tools.providers."):
                    with self.subTest(archivo=ruta.name, modulo=modulo):
                        if modulo == "tools.providers":
                            self.assertEqual(ruta.name, "cli.py")
                            self.assertEqual(nombres, ("PROVIDER_REGISTRY",))
                        else:
                            self.assertEqual(ruta.name, "probe.py")
                            self.assertEqual(modulo, "tools.providers.core")
                            self.assertEqual(nombres, ("InvocationRequest",))

    def test_import_de_providers_en_cli_es_diferido(self):
        """El import de `tools.providers` en cli.py está dentro de una función, no a nivel de módulo."""
        arbol = ast.parse((DIR_IMPROVE / "cli.py").read_text(encoding="utf-8"))
        for nodo in arbol.body:
            if isinstance(nodo, ast.ImportFrom):
                self.assertFalse((nodo.module or "").startswith("tools.providers"))

    def test_sin_red_ni_subprocess(self):
        for ruta in _modulos_fuente(DIR_IMPROVE):
            for modulo, _nivel, nombres in _imports(ruta):
                with self.subTest(archivo=ruta.name, modulo=modulo):
                    self.assertNotIn(modulo.split(".")[0], PROHIBIDOS)
                    for nombre in nombres:
                        self.assertNotIn(nombre.split(".")[0], PROHIBIDOS)

    def test_sin_ejecucion_dinamica_ni_os_system(self):
        for ruta in _modulos_fuente(DIR_IMPROVE):
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.Name):
                    with self.subTest(archivo=ruta.name, nombre=nodo.id):
                        self.assertNotIn(nodo.id, ("__import__", "exec", "eval"))
                if isinstance(nodo, ast.Attribute) and isinstance(nodo.value, ast.Name) and nodo.value.id == "os":
                    with self.subTest(archivo=ruta.name, atributo=nodo.attr):
                        self.assertFalse(
                            nodo.attr in ("system", "popen") or nodo.attr.startswith(("spawn", "exec")),
                            f"os.{nodo.attr} prohibido")

    def test_sin_providers_concretos(self):
        for ruta in _modulos_fuente(DIR_IMPROVE):
            for modulo, _nivel, nombres in _imports(ruta):
                for texto in (modulo,) + tuple(nombres):
                    with self.subTest(archivo=ruta.name, texto=texto):
                        for provider in PROVIDERS_CONCRETOS:
                            self.assertNotIn(provider, texto)

    def test_nadie_en_dsguard_ni_bench_lo_importa(self):
        for paquete in ("dsguard", "harmessi_bench"):
            for ruta in _modulos_fuente(RAIZ / "tools" / paquete):
                for modulo, _nivel, nombres in _imports(ruta):
                    with self.subTest(archivo=str(ruta.relative_to(RAIZ)), modulo=modulo):
                        self.assertNotIn("harmessi_improve", modulo)
                        for nombre in nombres:
                            self.assertNotIn("harmessi_improve", nombre)


if __name__ == "__main__":
    unittest.main()
