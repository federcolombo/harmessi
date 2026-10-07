"""Tests de N1 (R43-R46, `20261005-operational-autonomy-hardening`):
`pathguard` ignora redirecciones sin efecto en Bash/PowerShell, sigue
bloqueando escrituras reales sobre `guardrails.json`, y los tools
estructurados mantienen su política (Read/Grep permitidos; Write/Edit/
NotebookEdit bloqueados)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import pathguard  # noqa: E402

GUARDRAILS = ".claude/guardrails.json"


def _evaluar(tool_name: str, tool_input: dict):
    return pathguard.evaluar_tool_call(
        {"tool_name": tool_name, "tool_input": tool_input}, pathguard.ConfigGuardrails(), REPO_ORIGEN
    )


def _bash(comando: str):
    return _evaluar("Bash", {"command": comando})


class TestToolsEstructuradosGuardrails(unittest.TestCase):
    def test_read_permitido(self):
        self.assertTrue(_evaluar("Read", {"file_path": GUARDRAILS})[0])

    def test_grep_permitido(self):
        self.assertTrue(_evaluar("Grep", {"path": GUARDRAILS, "pattern": "x"})[0])

    def test_write_edit_notebookedit_bloqueados(self):
        self.assertFalse(_evaluar("Write", {"file_path": GUARDRAILS})[0])
        self.assertFalse(_evaluar("Edit", {"file_path": GUARDRAILS})[0])
        self.assertFalse(_evaluar("NotebookEdit", {"notebook_path": GUARDRAILS})[0])


class TestBashRedireccionesInocuas(unittest.TestCase):
    def test_redirecciones_sin_efecto_permitidas(self):
        casos = (
            f"grep -n x {GUARDRAILS} 2>/dev/null | head",
            f"cat {GUARDRAILS} 2>&1",
            f"cat {GUARDRAILS} >/dev/null",
            f"cat {GUARDRAILS} &>/dev/null",
            f"cat {GUARDRAILS} 2>>/dev/null",
            f"findstr x {GUARDRAILS} >nul",
            f"findstr x {GUARDRAILS} 2>NUL",
            f"Select-String x {GUARDRAILS} 2>$null",
            f"Select-String x {GUARDRAILS} >$NULL",
        )
        for comando in casos:
            with self.subTest(comando=comando):
                self.assertTrue(_bash(comando)[0], comando)

    def test_redireccion_real_bloqueada(self):
        casos = (
            f"echo x >> {GUARDRAILS}",
            f"cat a > {GUARDRAILS} 2>/dev/null",
            f"cat a > {GUARDRAILS} 2>&1",
            f"cat {GUARDRAILS} > salida.txt 2>&1",
            f"echo x > {GUARDRAILS}",
        )
        for comando in casos:
            with self.subTest(comando=comando):
                self.assertFalse(_bash(comando)[0], comando)

    def test_sumidero_con_sufijo_no_se_neutraliza(self):
        self.assertFalse(_bash(f"cat {GUARDRAILS} >nul.txt")[0])
        self.assertFalse(_bash(f"cat {GUARDRAILS} >/dev/null/x")[0])

    def test_duplicacion_de_descriptor_con_sufijo_de_ruta_no_se_neutraliza(self):
        for comando in (
            "echo x >&1/../.claude/guardrails.json",
            "echo x >&1\\..\\.claude\\guardrails.json",
        ):
            with self.subTest(comando=comando):
                self.assertFalse(_bash(comando)[0], comando)

    def test_patrones_de_escritura_siguen_bloqueando(self):
        casos = (
            f"echo x | tee {GUARDRAILS}",
            f"sed -i s/a/b/ {GUARDRAILS}",
            f"rm {GUARDRAILS} 2>/dev/null",
            f"cp a {GUARDRAILS} 2>&1",
        )
        for comando in casos:
            with self.subTest(comando=comando):
                self.assertFalse(_bash(comando)[0], comando)

    def test_secretos_y_data_raw_sin_cambios(self):
        self.assertFalse(_bash("cat .env 2>/dev/null")[0])
        self.assertFalse(_bash("rm data/raw/x.csv 2>/dev/null")[0])
        self.assertFalse(_bash("echo x > data/raw/x.csv 2>/dev/null")[0])


if __name__ == "__main__":
    unittest.main()
