"""Tests de la guarda técnica `core.validar_usuario_sin_email` cableada en los
5 command handlers de `tools/ds_guard.py` que persisten un campo `usuario`
(`openspec/changes/20260917-remove-personal-email/`): `cmd_approve`,
`cmd_remediation_extend`, `cmd_decision_add`, `cmd_decision_supersede`,
`cmd_decision_revoke`.

Dos niveles de cobertura, a propósito asimétricos (más simple es más
confiable que fabricar mocks frágiles para los 5 por igual):

- Integración real (con `argparse.Namespace` fabricado a mano, sobre un repo
  git temporal) para `cmd_approve` y `cmd_decision_add`: los dos casos donde
  el hallazgo original (email persistido) ocurrió/podía ocurrir de verdad.
  Confirma exit code 2, mensaje en stderr, y que no se escribe nada.
- Chequeo estructural liviano para los 5 handlers (incluidos los dos ya
  cubiertos arriba): la llamada a `core.validar_usuario_sin_email` aparece en
  el código fuente de la función, y aparece antes que cualquier escritura
  (`escribir_control`/`_escribir_entradas`/`sdd.remediation_extend`/
  `decision.decision_*`) dentro de esa misma función.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

import ds_guard  # noqa: E402
from dsguard import core, decision  # noqa: E402


def _crear_repo_git_temporal(prefix: str = "usuario_guard_test_") -> Path:
    repo = Path(tempfile.mkdtemp(prefix=prefix))
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    return repo


def _scaffold_change(repo: Path, change_id: str) -> Path:
    change_dir = repo / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True, exist_ok=True)
    (change_dir / "tasks.md").write_text("estado: propuesta_pendiente\n", encoding="utf-8")
    (change_dir / "proposal.md").write_text("contenido\n", encoding="utf-8")
    control = {
        "schema_version": 1,
        "change_id": change_id,
        "modo": "abreviado",
        "origen": "test",
        "creado_utc": core.ahora_utc(),
        "baseline": {"commit": "0" * 40, "rama": "main", "capturado_utc": core.ahora_utc()},
        "alcance": {"rutas_autorizadas": []},
        "aprobaciones": [],
        "transiciones": [],
        "sesiones": [],
    }
    core.escribir_control(change_dir / "control.json", control)
    return change_dir


@contextlib.contextmanager
def _cwd(path: Path):
    anterior = Path.cwd()
    try:
        import os

        os.chdir(path)
        yield
    finally:
        import os

        os.chdir(anterior)


class TestCmdApproveRechazaEmail(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        self.change_id = "20260917-test-usuario-guard"
        self.change_dir = _scaffold_change(self.repo, self.change_id)
        self.control_path = self.change_dir / "control.json"
        self.control_antes = core.capturar_bytes(self.control_path)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_approve_con_email_devuelve_2_y_no_escribe_nada(self):
        args = argparse.Namespace(
            change_id=self.change_id,
            artefacto=["proposal.md"],
            usuario="alguien@ejemplo.com",
            fecha="2026-09-17",
            alcance="todo",
            cita="cita literal",
        )
        stderr = io.StringIO()
        with _cwd(self.repo):
            with contextlib.redirect_stderr(stderr):
                resultado = ds_guard.cmd_approve(args)

        self.assertEqual(resultado, 2)
        self.assertIn("alguien@ejemplo.com", stderr.getvalue())
        self.assertEqual(core.capturar_bytes(self.control_path), self.control_antes)


class TestCmdDecisionAddRechazaEmail(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        self.ledger_path = decision.ledger_path(self.repo)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_decision_add_con_email_devuelve_2_y_no_escribe_ledger(self):
        args = argparse.Namespace(
            decision_id="20260917-decision-x",
            tipo="target",
            resumen="resumen",
            rationale="rationale",
            usuario="alguien@ejemplo.com",
            fecha="2026-09-17",
            cita="cita literal",
            change_id=None,
            kdd_etapa=None,
            evidencia=None,
            json=False,
        )
        stderr = io.StringIO()
        with _cwd(self.repo):
            with contextlib.redirect_stderr(stderr):
                resultado = ds_guard.cmd_decision_add(args)

        self.assertEqual(resultado, 2)
        self.assertIn("alguien@ejemplo.com", stderr.getvalue())
        self.assertFalse(self.ledger_path.exists())


class TestGuardaCableadaEnLos5Handlers(unittest.TestCase):
    """Chequeo estructural liviano: confirma, por inspección del código fuente,
    que cada uno de los 5 handlers llama a `core.validar_usuario_sin_email`
    antes de su primera escritura persistente."""

    def _codigo_fuente(self, nombre_funcion: str) -> str:
        import inspect

        funcion = getattr(ds_guard, nombre_funcion)
        return inspect.getsource(funcion)

    def _asegurar_guarda_antes_de_escritura(self, nombre_funcion: str, marcador_escritura: str):
        codigo = self._codigo_fuente(nombre_funcion)
        pos_guarda = codigo.find("core.validar_usuario_sin_email")
        pos_escritura = codigo.find(marcador_escritura)
        self.assertNotEqual(pos_guarda, -1, f"{nombre_funcion} no llama a validar_usuario_sin_email")
        self.assertNotEqual(pos_escritura, -1, f"{nombre_funcion} no contiene el marcador de escritura esperado")
        self.assertLess(
            pos_guarda,
            pos_escritura,
            f"{nombre_funcion}: la guarda debe aparecer antes de la escritura",
        )

    def test_cmd_approve(self):
        self._asegurar_guarda_antes_de_escritura("cmd_approve", "core.escribir_control")

    def test_cmd_remediation_extend(self):
        self._asegurar_guarda_antes_de_escritura("cmd_remediation_extend", "sdd.remediation_extend")

    def test_cmd_decision_add(self):
        self._asegurar_guarda_antes_de_escritura("cmd_decision_add", "decision.decision_add")

    def test_cmd_decision_supersede(self):
        self._asegurar_guarda_antes_de_escritura("cmd_decision_supersede", "decision.decision_supersede")

    def test_cmd_decision_revoke(self):
        self._asegurar_guarda_antes_de_escritura("cmd_decision_revoke", "decision.decision_revoke")


if __name__ == "__main__":
    unittest.main()
