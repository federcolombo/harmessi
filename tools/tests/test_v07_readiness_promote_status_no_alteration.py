"""Test de no-alteración (v0.7 Change 4, `20260922-quality-integration-and-cli`,
R16-R17 de `spec.md`, `design.md` decisión 6): garantiza que
`tools/dsguard/status.py::evaluar_status`, `ds_guard.py project readiness` y
`ds_guard.py project promote` mantienen EXACTAMENTE su comportamiento previo a
este Change, con y sin evidencia de calidad (`.harmessi/quality/`) presente.

Los 3 escenarios EXACTOS de `design.md` decisión 6:
1. `dsguard.status.evaluar_status()` idéntico con/sin `.harmessi/quality/`
   presente (manifest sintético escrito a mano, sin pasar por
   `tools.qualityevidence`).
2. `ds_guard.py project readiness --target <t> --json`: stdout + exit code
   idénticos con/sin evidencia.
3. `ds_guard.py project promote <stage> --json` en DOS directorios de fixture
   independientes: stdout + exit code + contenido final de `project.json`
   idénticos con/sin evidencia presente.

Nunca usa este repositorio real como fixture; nunca importa
`tools.qualityevidence` para escribir el manifest sintético del escenario 1
(bytes fijos a mano, mismo criterio que `design.md`)."""
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

from dsguard import lifecycle, maturity, status  # noqa: E402

DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"


def _crear_repo_git_temporal(prefix: str = "no_alteracion_") -> Path:
    repo = Path(tempfile.mkdtemp(prefix=prefix))
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)
    (repo / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=str(repo), check=True)
    return repo


def _correr_ds_guard(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DS_GUARD), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


# Manifest sintético escrito A MANO (bytes fijos, sin pasar por
# `tools.qualityevidence.evidence.build_manifest`/`write_manifest`) -- mismo
# criterio que `design.md` decisión 6, escenario 1: aísla el test de que ese
# paquete esté instalado o no en el stage actual.
_MANIFEST_SINTETICO = {
    "evidence_id": "qe-20260101T000000Z-abc123",
    "subject_kind": "data_contract_evaluation",
    "declaration": {
        "declaration_kind": "data_contract",
        "declaration_id": "c1",
        "version": "1.0.0",
        "content_sha256": "0" * 64,
    },
    "source": {
        "kind": "file",
        "role": "profile",
        "path": "profile.json",
        "sha256": "1" * 64,
        "algorithm": "sha256/bin/v1",
        "description": None,
        "params": None,
    },
    "generated_at": "2026-01-01T00:00:00Z",
    "scope": {"population": "", "time_start": None, "time_end": None},
    "check_results": [],
    "technical_errors": [],
    "schema_version": 1,
}


def _escribir_manifest_sintetico(repo: Path) -> None:
    directorio = repo / ".harmessi" / "quality" / _MANIFEST_SINTETICO["evidence_id"]
    directorio.mkdir(parents=True, exist_ok=True)
    # `content_sha256` no se calcula ni se verifica en este test (el manifest
    # nunca se lee vía `qualityevidence.evidence.read_manifest` en el
    # escenario 1 -- `evaluar_status` no lo toca en absoluto, ver R16).
    datos = dict(_MANIFEST_SINTETICO)
    datos["content_sha256"] = "2" * 64
    (directorio / "manifest.json").write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Comitear el archivo nuevo: sin esto, el working tree queda "sucio" y
    # `doctor.check_reproducibilidad` (CORE-WORKING-TREE, agregado por la
    # sección "harness" de `evaluar_status`) cambia de PASS a WARN -- una
    # variable AJENA a la presencia de `.harmessi/quality/` que rompería el
    # aislamiento de esta comparación (única variable real: con/sin
    # evidencia). Comitear deja el working tree limpio en ambas mediciones.
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "evidencia de calidad sintetica"], cwd=str(repo), check=True)


def _es_clave_utc(clave: str) -> bool:
    return clave == "utc" or clave.endswith("_utc")


def _normalizar_utc(valor):
    """Copia recursiva de `valor` con cualquier clave `"utc"` o que termine en
    `"_utc"` (p. ej. `"creado_utc"`, `tools/dsguard/maturity.py:72`)
    reemplazada por un placeholder fijo -- aísla la comparación de
    `project.json` de timestamps reales distintos entre dos corridas de
    subprocess (Escenario 3), sin relajar ninguna otra clave."""
    if isinstance(valor, dict):
        return {
            clave: ("UTC_NORMALIZADO" if _es_clave_utc(clave) else _normalizar_utc(sub_valor))
            for clave, sub_valor in valor.items()
        }
    if isinstance(valor, list):
        return [_normalizar_utc(item) for item in valor]
    return valor


class Escenario1EvaluarStatusDirecto(unittest.TestCase):
    """`dsguard.status.evaluar_status(repo_root)` idéntico con/sin
    `.harmessi/quality/` presente."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_resultado_identico_con_y_sin_evidencia(self):
        resultado_sin = status.evaluar_status(self.repo)

        _escribir_manifest_sintetico(self.repo)
        resultado_con = status.evaluar_status(self.repo)

        self.assertEqual(resultado_sin, resultado_con)
        # Las 8 claves documentadas por R16, sin ninguna clave nueva.
        self.assertEqual(
            set(resultado_con.keys()),
            {"project", "installation", "alignment", "lifecycle", "mlops", "readiness", "science", "harness"},
        )

    def test_formatear_texto_identico(self):
        resultado_sin = status.evaluar_status(self.repo)
        texto_sin = status.formatear_texto(resultado_sin)

        _escribir_manifest_sintetico(self.repo)
        resultado_con = status.evaluar_status(self.repo)
        texto_con = status.formatear_texto(resultado_con)

        self.assertEqual(texto_sin, texto_con)


class Escenario2ProjectReadinessCLI(unittest.TestCase):
    """`ds_guard.py project readiness --target <t> --json`: stdout + exit
    code idénticos con/sin evidencia de calidad presente (mismo directorio,
    readiness es de solo lectura -- nunca muta el fixture)."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        subprocess.run(["git", "add", "-A"], cwd=str(self.repo), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "fixture readiness"], cwd=str(self.repo), check=True)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_stdout_y_exit_code_identicos(self):
        r_sin = _correr_ds_guard(["project", "readiness", "--target", "experiment", "--json"], self.repo)

        _escribir_manifest_sintetico(self.repo)
        r_con = _correr_ds_guard(["project", "readiness", "--target", "experiment", "--json"], self.repo)

        self.assertEqual(r_sin.returncode, r_con.returncode)
        self.assertEqual(r_sin.stdout, r_con.stdout)


class Escenario3ProjectPromoteCLI(unittest.TestCase):
    """`ds_guard.py project promote <stage> --json`: stdout + exit code +
    contenido final de `.harmessi/project.json` idénticos con/sin evidencia,
    en DOS directorios de fixture INDEPENDIENTES (promote muta el estado, no
    puede reusarse el mismo directorio para las dos corridas)."""

    def _fixture(self) -> Path:
        repo = _crear_repo_git_temporal()
        maturity.project_init(repo, stage="discovery")
        lifecycle.lifecycle_init(repo)
        subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "fixture promote"], cwd=str(repo), check=True)
        return repo

    def test_stdout_exit_code_y_project_json_identicos(self):
        repo_sin = self._fixture()
        repo_con = self._fixture()
        try:
            r_sin = _correr_ds_guard(
                ["project", "promote", "experiment", "--reason", "avance de prueba", "--json"], repo_sin
            )
            _escribir_manifest_sintetico(repo_con)
            r_con = _correr_ds_guard(
                ["project", "promote", "experiment", "--reason", "avance de prueba", "--json"], repo_con
            )

            self.assertEqual(r_sin.returncode, r_con.returncode)
            self.assertEqual(r_sin.stdout, r_con.stdout)

            project_sin = json.loads((repo_sin / ".harmessi" / "project.json").read_text(encoding="utf-8"))
            project_con = json.loads((repo_con / ".harmessi" / "project.json").read_text(encoding="utf-8"))
            # Cada corrida real de `promote`/`project init` genera sus propios
            # timestamps ("utc", en cada entrada de "stage_history") -- una
            # diferencia esperable entre dos invocaciones de subprocess
            # separadas por segundos reales, no relacionada con la presencia
            # de evidencia de calidad. Se normalizan ANTES de comparar (única
            # clave tocada; el resto del dict se compara sin relajar nada).
            self.assertEqual(_normalizar_utc(project_sin), _normalizar_utc(project_con))
        finally:
            shutil.rmtree(repo_sin, ignore_errors=True)
            shutil.rmtree(repo_con, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
