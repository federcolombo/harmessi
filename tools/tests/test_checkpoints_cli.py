"""Tests CLI de checkpoints con `@approved` (T3 de 20261006-sdd-parsers-and-guardrail-ownership):
`approve` materializa el hash real de `proposal.md` y `status` verifica los checkpoints.

Subprocess contra un repo git temporal (patrón de test_operational_scope.py).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import core  # noqa: E402

DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"
_TEMPLATES_ORIGEN = REPO_ORIGEN / ".claude" / "skills" / "lead-data-scientist" / "templates"
_ID = "20261006-test-checkpoints"
_ID_OTRO = "20261006-test-otro-change"
_CEROS = "0" * 64


def _crear_repo() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="chk_cli_"))
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)
    (repo / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    shutil.copytree(_TEMPLATES_ORIGEN, repo / ".claude" / "skills" / "lead-data-scientist" / "templates")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=str(repo), check=True)
    return repo


def _cli(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DS_GUARD), *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8"
    )


def _propuesta(bullet: str) -> str:
    return f"# Propuesta\n\n## Alcance\n- x\n\n## Checkpoints de negocio\n{bullet}\n\n## Motivo de rechazo\n"


def _bullet(change_id: str, ref: str, cp_id: str = "cp1") -> str:
    return f"- **{cp_id}**: decisión de prueba — alcance: tools/x.py — aprobacion: {change_id}/proposal.md@{ref}"


class _Base(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo()
        r = _cli(["init", "--change-id", _ID, "--modo", "completo", "--approval-mode", "checkpoints"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _dir(self, change_id: str = _ID) -> Path:
        return self.repo / "openspec" / "changes" / change_id

    def _control(self, change_id: str = _ID) -> dict:
        return json.loads((self._dir(change_id) / "control.json").read_text(encoding="utf-8"))

    def _proposal(self, texto: str, change_id: str = _ID) -> None:
        (self._dir(change_id) / "proposal.md").write_text(texto, encoding="utf-8")

    def _aprobar(self, change_id: str = _ID) -> subprocess.CompletedProcess:
        return _cli(
            ["approve", "--change-id", change_id, "--artefacto", "proposal.md", "--usuario", "Tester",
             "--fecha", "2026-10-06", "--alcance", "test", "--cita", "ok"],
            self.repo,
        )

    def _status_json(self) -> dict:
        r = _cli(["status", "--change-id", _ID, "--json"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def _hash_aprobado(self, change_id: str = _ID) -> str:
        return self._control(change_id)["aprobaciones"][-1]["hash"]

    def _crear_otro(self, aprobar: bool) -> None:
        r = _cli(["init", "--change-id", _ID_OTRO, "--modo", "completo"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self._proposal("# Otro\n\n## Alcance\n- y\n", _ID_OTRO)
        if aprobar:
            self.assertEqual(self._aprobar(_ID_OTRO).returncode, 0)


class TestApproved(_Base):
    def test_approved_propio_materializa_hash_real(self):
        self._proposal(_propuesta(_bullet(_ID, "approved")))
        r = self._aprobar()
        self.assertEqual(r.returncode, 0, r.stderr)
        real = core.hash_lf_v1(self._dir() / "proposal.md")
        control = self._control()
        self.assertEqual(self._hash_aprobado(), real)
        refs = [d["approval_ref"]["hash"] for d in control["decisiones_preaprobadas"]]
        self.assertEqual(refs, [real])
        self.assertNotIn("approved", json.dumps(control["decisiones_preaprobadas"]))

    def test_approved_otro_change_sin_aprobacion_rechaza(self):
        self._crear_otro(aprobar=False)
        self._proposal(_propuesta(_bullet(_ID_OTRO, "approved")))
        antes = (self._dir() / "control.json").read_text(encoding="utf-8")
        r = self._aprobar()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual((self._dir() / "control.json").read_text(encoding="utf-8"), antes)

    def test_approved_otro_change_con_aprobacion_vigente(self):
        self._crear_otro(aprobar=True)
        self._proposal(_propuesta(_bullet(_ID_OTRO, "approved")))
        r = self._aprobar()
        self.assertEqual(r.returncode, 0, r.stderr)
        esperado = self._hash_aprobado(_ID_OTRO)
        self.assertEqual(self._control()["decisiones_preaprobadas"][0]["approval_ref"]["hash"], esperado)

    def test_legacy_hash_real_aceptado(self):
        real = "ab" * 32
        self._proposal(_propuesta(_bullet(_ID, real)))
        r = self._aprobar()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._control()["decisiones_preaprobadas"][0]["approval_ref"]["hash"], real)

    def test_ceros_aceptado_con_deprecated_y_status_placeholder(self):
        self._proposal(_propuesta(_bullet(_ID, _CEROS)))
        r = self._aprobar()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("deprecated", r.stderr)
        self.assertIn("cp1", r.stderr)
        cps = self._status_json()["checkpoints"]
        self.assertEqual(len(cps), 1)
        self.assertEqual(cps[0]["estado"], "placeholder")
        self.assertNotEqual(cps[0]["estado"], "verified")

    def test_status_verified_y_stale_tras_modificar(self):
        self._proposal(_propuesta(_bullet(_ID, "approved")))
        self.assertEqual(self._aprobar().returncode, 0)
        self.assertEqual([c["estado"] for c in self._status_json()["checkpoints"]], ["verified"])
        texto = (self._dir() / "proposal.md").read_text(encoding="utf-8")
        self._proposal(texto + "\nmodificado después de aprobar\n")
        self.assertEqual([c["estado"] for c in self._status_json()["checkpoints"]], ["stale"])
        r = _cli(["status", "--change-id", _ID], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Checkpoints", r.stdout)
        self.assertIn("stale", r.stdout)

    def test_reaprobar_rehace(self):
        self._proposal(_propuesta(_bullet(_ID, "approved")))
        self.assertEqual(self._aprobar().returncode, 0)
        texto = (self._dir() / "proposal.md").read_text(encoding="utf-8")
        self._proposal(texto + "\ncambio\n")
        self.assertEqual(self._aprobar().returncode, 0)
        real = core.hash_lf_v1(self._dir() / "proposal.md")
        self.assertEqual(self._control()["decisiones_preaprobadas"][0]["approval_ref"]["hash"], real)
        self.assertEqual([c["estado"] for c in self._status_json()["checkpoints"]], ["verified"])


class TestRevision(_Base):
    def test_crlf_hash_materializado_igual_hash_lf_v1(self):
        texto = _propuesta(_bullet(_ID, "approved")).replace("\n", "\r\n")
        (self._dir() / "proposal.md").write_bytes(texto.encode("utf-8"))
        r = self._aprobar()
        self.assertEqual(r.returncode, 0, r.stderr)
        real = core.hash_lf_v1(self._dir() / "proposal.md")
        self.assertEqual(self._control()["decisiones_preaprobadas"][0]["approval_ref"]["hash"], real)
        self.assertEqual(self._hash_aprobado(), real)

    def test_approved_otro_change_stale_rechaza(self):
        self._crear_otro(aprobar=True)
        self._proposal("# Otro\n\n## Alcance\n- y\n\nmodificado\n", _ID_OTRO)
        self._proposal(_propuesta(_bullet(_ID_OTRO, "approved")))
        antes = (self._dir() / "control.json").read_text(encoding="utf-8")
        r = self._aprobar()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual((self._dir() / "control.json").read_text(encoding="utf-8"), antes)

    def test_entrada_con_hash_ceros_nunca_verified(self):
        self._proposal(_propuesta(_bullet(_ID, "approved")))
        self.assertEqual(self._aprobar().returncode, 0)
        ruta = self._dir() / "control.json"
        control = self._control()
        control["decisiones_preaprobadas"][0]["approval_ref"]["hash"] = _CEROS
        ruta.write_text(json.dumps(control, indent=2), encoding="utf-8")
        estados = [c["estado"] for c in self._status_json()["checkpoints"]]
        self.assertEqual(len(estados), 1)
        self.assertNotEqual(estados[0], "verified")


class TestSinCheckpoints(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo()
        r = _cli(["init", "--change-id", _ID, "--modo", "completo"], self.repo)  # per_change
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_per_change_no_materializa_y_status_json_checkpoints_vacio(self):
        base = self.repo / "openspec" / "changes" / _ID
        (base / "proposal.md").write_text(_propuesta(_bullet(_ID, "approved")), encoding="utf-8")
        r = _cli(["approve", "--change-id", _ID, "--artefacto", "proposal.md", "--usuario", "Tester",
                  "--fecha", "2026-10-06", "--alcance", "test", "--cita", "ok"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        control = json.loads((base / "control.json").read_text(encoding="utf-8"))
        self.assertFalse(control.get("decisiones_preaprobadas"))
        s = _cli(["status", "--change-id", _ID, "--json"], self.repo)
        self.assertEqual(s.returncode, 0, s.stderr)
        self.assertEqual(json.loads(s.stdout)["checkpoints"], [])

    def test_checkpoints_sin_seccion(self):
        _cli(["init", "--change-id", "20261006-test-sin-seccion", "--modo", "completo",
              "--approval-mode", "checkpoints"], self.repo)
        base = self.repo / "openspec" / "changes" / "20261006-test-sin-seccion"
        (base / "proposal.md").write_text("# P\n\n## Alcance\n- x\n", encoding="utf-8")
        r = _cli(["approve", "--change-id", "20261006-test-sin-seccion", "--artefacto", "proposal.md",
                  "--usuario", "Tester", "--fecha", "2026-10-06", "--alcance", "test", "--cita", "ok"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        control = json.loads((base / "control.json").read_text(encoding="utf-8"))
        self.assertEqual(control.get("decisiones_preaprobadas"), [])


if __name__ == "__main__":
    unittest.main()
