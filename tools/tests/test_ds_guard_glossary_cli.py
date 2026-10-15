"""Tests de CLI de `ds_guard glossary check|hash` y su integración en `validate`
(Change 20261014-domain-modeling, R4-R6).

Mismo patrón que `test_ds_guard_ownership_cli.py`: corre `tools/ds_guard.py` real como
subproceso contra un repo git temporal sintético.

La aprobación T1 de `test_approved_valida` es un FAKE de test del contrato: se escribe a
mano en `control.json`. El tier T1 real solo lo produce la consola y no se ejercita acá.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"
_TEMPLATES_ORIGEN = REPO_ORIGEN / ".claude" / "skills" / "lead-data-scientist" / "templates"
_CHANGE_ID = "20261014-test-glossary-cli"
_ARTEFACTO = "domain-approval.md"

_HYPOTHESIS = (
    "# Glosario\n\n"
    "## cliente activo\n"
    "- estado: hypothesis\n"
    "- definicion: cliente con al menos una compra en los últimos 90 días\n"
)
_HYPOTHESIS_AMBIGUA = _HYPOTHESIS + "- ambiguedad: material\n"
_ESTADO_DESCONOCIDO = (
    "## cliente activo\n"
    "- estado: inventado\n"
    "- definicion: algo\n"
)
_DEFINICION = "cliente con al menos una compra en los últimos 90 días"


def _crear_repo_git_temporal() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="cli_glossary_"))
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)
    (repo / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    shutil.copytree(_TEMPLATES_ORIGEN, repo / ".claude" / "skills" / "lead-data-scientist" / "templates")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=str(repo), check=True)
    return repo


def _correr(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DS_GUARD), *args],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
    )


class _Base(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        self.glossary = self.repo / "GLOSSARY.md"

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _escribir(self, texto: str) -> None:
        self.glossary.write_bytes(texto.encode("utf-8"))

    def _check(self, *extra) -> subprocess.CompletedProcess:
        return _correr(["glossary", "check", *extra], self.repo)

    def _hash(self, termino: str = "cliente activo") -> subprocess.CompletedProcess:
        return _correr(["glossary", "hash", "--term", termino], self.repo)

    def _codigos_json(self, r: subprocess.CompletedProcess) -> list:
        return [f["codigo"] for f in json.loads(r.stdout)["findings"]]


class TestGlossaryCheck(_Base):
    def test_sin_glossary_exit_0(self):
        r = self._check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("sin GLOSSARY.md", r.stdout)

    def test_hypothesis_valida_exit_0(self):
        self._escribir(_HYPOTHESIS)
        r = self._check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_estado_desconocido_exit_1(self):
        self._escribir(_ESTADO_DESCONOCIDO)
        r = self._check("--json")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("GLOSSARY-ESTADO-INVALIDO", self._codigos_json(r))

    def test_ambiguedad_material_pendiente_no_falla(self):
        self._escribir(_HYPOTHESIS_AMBIGUA)
        r = self._check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PENDIENTE (ambigüedad material): cliente activo", r.stdout)
        rj = self._check("--json")
        self.assertEqual(rj.returncode, 0, rj.stdout + rj.stderr)
        self.assertIn("cliente activo", json.loads(rj.stdout)["pendientes"])

    def test_ambiguedad_material_strict_exit_1(self):
        self._escribir(_HYPOTHESIS_AMBIGUA)
        r = self._check("--strict")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


class TestGlossaryHash(_Base):
    def test_hash_correcto(self):
        self._escribir(_HYPOTHESIS)
        r = self._hash()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        h = r.stdout.strip()
        self.assertRegex(h, r"^[0-9a-f]{64}$")
        # Mismo valor que el módulo puro (casefold del término en la búsqueda).
        sys.path.insert(0, str(REPO_ORIGEN / "tools"))
        try:
            from dsguard import glossary as g
        finally:
            sys.path.pop(0)
        self.assertEqual(h, g.definition_hash("cliente activo", _DEFINICION))
        self.assertEqual(self._hash("CLIENTE ACTIVO").stdout.strip(), h)

    def test_termino_inexistente_exit_2(self):
        self._escribir(_HYPOTHESIS)
        r = self._hash("no existe")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), "")
        self.assertTrue(r.stderr.strip())

    def test_sin_glossary_exit_2(self):
        self.assertEqual(self._hash().returncode, 2)

    def test_hash_con_bom(self):
        self._escribir(_HYPOTHESIS)
        sin_bom = self._hash().stdout.strip()
        self.glossary.write_bytes(b"\xef\xbb\xbf" + _HYPOTHESIS.encode("utf-8"))
        r = self._hash()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), sin_bom)

    def test_entrada_sin_definicion_exit_2(self):
        self._escribir("## cliente activo\n- estado: hypothesis\n")
        r = self._hash()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_termino_con_espacios_colapsados(self):
        self._escribir(_HYPOTHESIS)
        esperado = self._hash().stdout.strip()
        r = self._hash("cliente  activo")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), esperado)


class TestGlossaryIlegible(_Base):
    def test_no_utf8_exit_2(self):
        self.glossary.write_bytes(b"## t\n- estado: hypothesis\n- definicion: \xff\xfe\xfa\n")
        r = self._check()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertTrue(r.stderr.strip())

    def test_directorio_exit_2(self):
        self.glossary.mkdir()
        r = self._check()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


class TestGlossaryApproved(_Base):
    def setUp(self):
        super().setUp()
        r = _correr(["init", "--change-id", _CHANGE_ID, "--modo", "completo"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.dir_change = self.repo / "openspec" / "changes" / _CHANGE_ID

    def _armar_approved(self, canal: str, version: str, con_aprobacion: bool = True) -> None:
        # 1. hypothesis -> hash de la definición.
        self._escribir(_HYPOTHESIS)
        h_def = self._hash().stdout.strip()
        # 2. artefacto del Change que contiene el hash.
        contenido = f"# Aprobación de dominio\r\n\r\n- cliente activo: {h_def}\r\n"
        (self.dir_change / _ARTEFACTO).write_bytes(contenido.encode("utf-8"))
        h_art = hashlib.sha256(contenido.replace("\r\n", "\n").encode("utf-8")).hexdigest()
        # 3. entrada de aprobación escrita a mano (FAKE de test del contrato).
        if con_aprobacion:
            ruta_control = self.dir_change / "control.json"
            control = json.loads(ruta_control.read_text(encoding="utf-8"))
            control.setdefault("aprobaciones", []).append({
                "artefacto": _ARTEFACTO,
                "algoritmo": "sha256/lf/v1",
                "hash": h_art,
                "registrado_utc": "2026-10-14T12:00:00Z",
                "usuario": "Test User",
                "fecha_declarada": "2026-10-14",
                "alcance_aprobado": "x",
                "cita": "x",
                "approval_channel": canal,
                "confirmed_at": "2026-10-14T12:00:00Z",
                "channel_version": version,
            })
            ruta_control.write_text(json.dumps(control, indent=2), encoding="utf-8")
        # 4. entrada approved.
        self._escribir(
            "# Glosario\n\n## cliente activo\n- estado: approved\n"
            f"- definicion: {_DEFINICION}\n"
            f"- approval_ref: {_CHANGE_ID}/{_ARTEFACTO}@{h_art}\n"
            f"- definition_hash: {h_def}\n"
        )

    def test_approved_sin_aprobacion_real_exit_1(self):
        self._armar_approved("console_confirmed", "console/v1", con_aprobacion=False)
        r = self._check("--json")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("GLOSSARY-APROBACION-INVALIDA", self._codigos_json(r))

    def test_approved_valida_exit_0(self):
        self._armar_approved("console_confirmed", "console/v1")
        r = self._check("--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_approved_declared_sin_t1(self):
        self._armar_approved("declared", "declared/v1")
        r = self._check("--json")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("GLOSSARY-APROBACION-SIN-T1", self._codigos_json(r))


class TestGlossaryValidate(_Base):
    def _validate(self) -> subprocess.CompletedProcess:
        return _correr(["validate", "--change-id", _CHANGE_ID, "--json"], self.repo)

    def setUp(self):
        super().setUp()
        r = _correr(["init", "--change-id", _CHANGE_ID, "--modo", "completo"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_validate_sin_glossary_sin_hallazgos_glossary(self):
        codigos = self._codigos_json(self._validate())
        self.assertFalse([c for c in codigos if c.startswith("GLOSSARY-")])

    def test_validate_glossary_invalido_reporta(self):
        self._escribir(_ESTADO_DESCONOCIDO)
        r = self._validate()
        self.assertIn("GLOSSARY-ESTADO-INVALIDO", self._codigos_json(r))

    def test_validate_hypothesis_valida_sin_hallazgos_glossary(self):
        self._escribir(_HYPOTHESIS)
        codigos = self._codigos_json(self._validate())
        self.assertFalse([c for c in codigos if c.startswith("GLOSSARY-")])


if __name__ == "__main__":
    unittest.main()
