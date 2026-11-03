"""v0.13 R10: auditoría estática de portabilidad de los módulos nuevos de v0.13.

Análisis AST (no regex sobre texto) para no confundir docstrings/mensajes con
llamadas reales. Alcance acotado a una lista explícita; el resto de `tools/**`
(heredado) se registra en `docs/portability.md` como deuda.
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
TOOLS = RAIZ / "tools"


def _modulos_v013() -> list:
    modulos = sorted(p for p in (TOOLS / "harmessi_bench").glob("*.py"))
    modulos += [
        TOOLS / "providers" / "conformance.py",
        TOOLS / "datasources" / "conformance.py",
        TOOLS / "dsimpact" / "git_source.py",
    ]
    return modulos


def _nombre_llamada(nodo: ast.Call) -> str:
    f = nodo.func
    if isinstance(f, ast.Attribute):
        base = f.value.id if isinstance(f.value, ast.Name) else ""
        return f"{base}.{f.attr}" if base else f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


def _kw(nodo: ast.Call, nombre: str):
    for k in nodo.keywords:
        if k.arg == nombre:
            return k.value
    return None


def _es_modo_binario(nodo: ast.Call, posicion: int) -> bool:
    modo = nodo.args[posicion] if len(nodo.args) > posicion else _kw(nodo, "mode")
    return isinstance(modo, ast.Constant) and isinstance(modo.value, str) and "b" in modo.value


def _docstrings(arbol: ast.AST) -> set:
    ids = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            cuerpo = nodo.body
            if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(cuerpo[0].value, ast.Constant):
                ids.add(id(cuerpo[0].value))
    return ids


def auditar_fuente(texto: str) -> list:
    """Devuelve la lista de violaciones (strings) de un fuente Python."""
    arbol = ast.parse(texto)
    docs = _docstrings(arbol)
    problemas = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call):
            nombre = _nombre_llamada(nodo)
            hoja = nombre.rsplit(".", 1)[-1]
            if hoja == "open" and nombre in ("open", "io.open", "codecs.open"):
                if not _es_modo_binario(nodo, 1) and _kw(nodo, "encoding") is None:
                    problemas.append(f"L{nodo.lineno}: open() de texto sin encoding=")
            if hoja in ("read_text", "write_text") and _kw(nodo, "encoding") is None:
                # `write_text(datos, encoding=...)`: encoding posicional solo en read_text(arg0)
                posicional = hoja == "read_text" and len(nodo.args) >= 1
                posicional = posicional or (hoja == "write_text" and len(nodo.args) >= 2)
                if not posicional:
                    problemas.append(f"L{nodo.lineno}: {hoja}() sin encoding=")
            if nombre == "os.system":
                problemas.append(f"L{nodo.lineno}: os.system")
            sh = _kw(nodo, "shell")
            if isinstance(sh, ast.Constant) and sh.value is True:
                problemas.append(f"L{nodo.lineno}: shell=True")
            if hoja in ("Path", "PurePath", "joinpath", "open", "read_text", "write_text", "mkdir"):
                for arg in nodo.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and "\\" in arg.value:
                        problemas.append(f"L{nodo.lineno}: separador '\\' hardcodeado en literal de ruta")
        elif isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and id(nodo) not in docs:
            if "/tmp" in nodo.value:
                problemas.append(f"L{nodo.lineno}: ruta '/tmp' hardcodeada")
            if re.search(r"[A-Za-z]:\\", nodo.value):
                problemas.append(f"L{nodo.lineno}: ruta de unidad Windows hardcodeada")
        elif isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Div):
            for lado in (nodo.left, nodo.right):
                if isinstance(lado, ast.Constant) and isinstance(lado.value, str) and "\\" in lado.value:
                    problemas.append(f"L{nodo.lineno}: separador '\\' hardcodeado en join de ruta")
    return problemas


class TestAuditoriaDetector(unittest.TestCase):
    """El detector detecta lo que dice detectar (evita un test vacuo)."""

    def test_detecta_violaciones(self):
        casos = {
            "open('x.txt')": "open()",
            "open('x.txt', 'w')": "open()",
            "from pathlib import Path\nPath('a').read_text()": "read_text()",
            "from pathlib import Path\nPath('a').write_text('x')": "write_text()",
            "import os\nos.system('ls')": "os.system",
            "import subprocess\nsubprocess.run(['a'], shell=True)": "shell=True",
            "x = '/tmp/algo'": "/tmp",
            "x = 'C:\\\\Users\\\\x'": "Windows",
            "from pathlib import Path\nPath('a\\\\b')": "separador",
        }
        for fuente, esperado in casos.items():
            with self.subTest(fuente=fuente):
                problemas = auditar_fuente(fuente)
                self.assertTrue(any(esperado in p for p in problemas), (fuente, problemas))

    def test_acepta_codigo_correcto(self):
        fuente = (
            "'''docstring con /tmp y shell=True'''\n"
            "from pathlib import Path\n"
            "open('x', 'rb')\n"
            "open('x', encoding='utf-8')\n"
            "Path('a').read_text(encoding='utf-8')\n"
            "Path('a').write_text('x', encoding='utf-8')\n"
        )
        self.assertEqual(auditar_fuente(fuente), [])


class TestModulosV013(unittest.TestCase):
    def test_lista_de_modulos_existe(self):
        modulos = _modulos_v013()
        self.assertGreaterEqual(len(modulos), 5)
        for m in modulos:
            self.assertTrue(m.is_file(), m)

    def test_modulos_v013_sin_patrones_no_portables(self):
        for modulo in _modulos_v013():
            with self.subTest(modulo=modulo.relative_to(RAIZ).as_posix()):
                problemas = auditar_fuente(modulo.read_text(encoding="utf-8"))
                self.assertEqual(problemas, [])


if __name__ == "__main__":
    unittest.main()
