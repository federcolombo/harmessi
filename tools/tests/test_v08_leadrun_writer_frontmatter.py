"""R18 (v0.8 Change 2, `20260929-lead-execution-runtime`): el frontmatter del
writer (`agent_python_data_engineer.md.tmpl`) NO cambia con este Change -- el
writer no gana ninguna herramienta de ejecución (decisión 1 del roadmap,
`docs/roadmap/v0.8.md:450-451`).

La verificación GENERAL de "conjunto exacto de tools, sin Bash/PowerShell/
Agent" ya existe y no se reabre acá: `tools/tests/test_v08_writer_no_execution.py`
(Change 0, `TestWriterNoEjecuta`). Este test es un COMPLEMENTO puntual de ese
(no un duplicado): fija un snapshot exacto del bloque de frontmatter completo
(no solo el conjunto de `tools:`) contra el que se compara el contenido
ACTUAL de la plantilla, como evidencia de que específicamente este Change no
lo tocó. Se usa un snapshot de texto completo en vez de un hash precalculado
porque este test se produce sin poder ejecutar código (entorno de solo
lectura/escritura, sin `Bash`); el snapshot de texto es tan verificable por
inspección como un hash, y se corre igual en la próxima ejecución real de la
suite (`pytest`), sin que nadie haya "inventado" un hash no verificado.
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

# Snapshot EXACTO del frontmatter (entre las dos líneas '---'), tal como está
# hoy en el repo -- ver `tools/tests/test_v08_writer_no_execution.py` para la
# verificación semántica (conjunto de tools). Este snapshot es la evidencia
# puntual de R18 de este Change: byte a byte, sin cambios.
FRONTMATTER_ESPERADO = """---
name: python-data-engineer
description: Único subagente autorizado a leer y editar código/notebooks (ETL, debugging, pipelines, QA). No ejecuta código ni notebooks en esta versión.
tools: Read, Edit, Write, NotebookEdit, Grep, Glob
model: sonnet
effort: medium
maxTurns: 12
---"""


def _extraer_frontmatter(texto: str) -> str:
    lineas = texto.splitlines()
    if not lineas or lineas[0].strip() != "---":
        raise AssertionError("la plantilla no abre con frontmatter '---'")
    fin = None
    for i, linea in enumerate(lineas[1:], start=1):
        if linea.strip() == "---":
            fin = i
            break
    if fin is None:
        raise AssertionError("no se encontró el cierre '---' del frontmatter")
    return "\n".join(lineas[: fin + 1])


class TestFrontmatterWriterSinCambios(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PLANTILLA.is_file(), f"no existe {PLANTILLA}")
        self.frontmatter_actual = _extraer_frontmatter(PLANTILLA.read_text(encoding="utf-8"))

    def test_frontmatter_identico_al_snapshot_pre_change_2(self):
        self.assertEqual(
            self.frontmatter_actual,
            FRONTMATTER_ESPERADO,
            "El frontmatter de agent_python_data_engineer.md.tmpl cambió respecto del snapshot "
            "fijado para v0.8 Change 2 (R18): el writer no debe ganar ninguna capacidad de "
            "ejecución con este Change.",
        )

    def test_tools_no_incluye_ejecucion(self):
        # Evidencia puntual y redundante (a propósito) con
        # `test_v08_writer_no_execution.py`: ninguna herramienta de
        # ejecución/delegación en el snapshot fijado acá.
        for prohibida in ("Bash", "PowerShell", "Agent", "Execute"):
            self.assertNotIn(prohibida, FRONTMATTER_ESPERADO)


if __name__ == "__main__":
    unittest.main()
