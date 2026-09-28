"""R13 (v0.8 Change 0): el subagente writer (`python-data-engineer`) no ejecuta.
La plantilla de su agente debe declarar exactamente las herramientas de lectura
y escritura, sin `Bash`, `PowerShell` ni `Agent`. Coherente con
`writer.execute is False` del contrato de autonomía.
"""
from __future__ import annotations

import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
PLANTILLA = (
    REPO_ORIGEN
    / "tools"
    / "ds_init"
    / "profiles"
    / "python_jupyter_data"
    / "templates"
    / "agent_python_data_engineer.md.tmpl"
)
TOOLS_ESPERADAS = {"Read", "Edit", "Write", "NotebookEdit", "Grep", "Glob"}


def _tools_del_frontmatter(texto: str) -> set:
    lineas = texto.splitlines()
    if not lineas or lineas[0].strip() != "---":
        raise AssertionError("la plantilla no abre con frontmatter '---'")
    for linea in lineas[1:]:
        if linea.strip() == "---":
            break
        if linea.startswith("tools:"):
            return {t.strip() for t in linea[len("tools:"):].split(",") if t.strip()}
    raise AssertionError("no se encontró la línea 'tools:' en el frontmatter")


class TestWriterNoEjecuta(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PLANTILLA.is_file(), f"no existe {PLANTILLA}")
        self.tools = _tools_del_frontmatter(PLANTILLA.read_text(encoding="utf-8"))

    def test_conjunto_exacto_de_tools(self):
        self.assertEqual(self.tools, TOOLS_ESPERADAS)

    def test_sin_herramientas_de_ejecucion_ni_delegacion(self):
        for prohibida in ("Bash", "PowerShell", "Agent"):
            self.assertNotIn(prohibida, self.tools)


if __name__ == "__main__":
    unittest.main()
