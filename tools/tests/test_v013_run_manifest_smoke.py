"""Smoke del Change `20261021-v013-reproducible-harness-runs`: baseline y
candidate manual (skills distintas en un directorio temporal inyectado)
=> identity_hash distintos, comparación con `config_diff` y resume
incompatible rechazado. Adapter falso, sin red ni CLIs reales."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from tools.harmessi_bench import cli as cli_mod
from tools.harmessi_bench import storage
from tools.harmessi_bench.cli import main
from tools.providers.core import InvocationResult, ProviderCapabilities, ProviderInfo

_EJEMPLOS = str(Path(__file__).resolve().parents[1] / "harmessi_bench" / "scenarios" / "examples.json")
_DIR_SKILLS = (".claude", "skills", "lead-data-scientist", "skills")


class _AdapterFalso:
    provider_id = "fake"
    cli_command = "fake"
    display_name = "Fake"

    def __init__(self):
        self.llamadas = 0

    def detect(self):
        return ProviderInfo(provider_id="fake", display_name="Fake", cli_command="fake", available=True,
                            authenticated=True, version="0", capabilities=ProviderCapabilities(), detail="ok")

    def invoke(self, request):
        self.llamadas += 1
        texto = "OK" if "OK" in request.prompt else ("4" if "2+2" in request.prompt else "rojo\nazul")
        return InvocationResult(provider_id="fake", exit_code=0, stdout=texto, stderr="", ok=True,
                                availability_error=None, duration_s=0.0)


def _crear_skills(base: Path, contenido: str) -> Path:
    raiz = base / "repo ñ con espacios"
    directorio = raiz.joinpath(*_DIR_SKILLS)
    directorio.mkdir(parents=True)
    (directorio / "demo.md").write_text(contenido, encoding="utf-8")
    return raiz


class TestSmokeRunManifest(unittest.TestCase):
    def test_baseline_candidate_comparacion_y_resume_incompatible(self):
        import tools.providers as providers_mod

        adapter = _AdapterFalso()
        with TemporaryDirectory(prefix="smoke ñ ") as tmp, \
                mock.patch.dict(providers_mod.PROVIDER_REGISTRY, {"fake": adapter}):
            base = Path(tmp)
            (base / "a").mkdir()
            (base / "b").mkdir()
            raiz_a = _crear_skills(base / "a", "version A\n")
            raiz_b = _crear_skills(base / "b", "version B\n")
            evals = base / "evals ñ"

            def correr(run_id, raiz_repo, *extra):
                with mock.patch.object(cli_mod, "_REPO_ROOT_MANIFEST", raiz_repo):
                    return main(["run", "--scenarios", _EJEMPLOS, "--provider", "fake",
                                 "--run-id", run_id, "--root", str(evals), *extra])

            self.assertEqual(correr("baseline", raiz_a), 0)
            self.assertEqual(correr("candidate", raiz_b), 0)
            base_run = storage.load_run("baseline", root=evals)
            cand_run = storage.load_run("candidate", root=evals)
            self.assertNotEqual(base_run["run_manifest"]["identity_hash"],
                                cand_run["run_manifest"]["identity_hash"])
            self.assertNotIn(str(base), json.dumps(base_run["run_manifest"]))

            from tools.harmessi_bench.compare import compare_runs

            reporte = compare_runs(base_run, cand_run)
            self.assertIn("skills", reporte.config_diff)
            self.assertNotEqual(reporte.verdict, "inconclusive", reporte.verdict_reason)

            # Resume del baseline con las skills del candidate: incompatible, sin tocar nada.
            antes = (evals / "baseline" / "result.json").read_bytes()
            llamadas = adapter.llamadas
            self.assertEqual(correr("baseline", raiz_b, "--resume"), 1)
            self.assertEqual((evals / "baseline" / "result.json").read_bytes(), antes)
            self.assertEqual(adapter.llamadas, llamadas)


if __name__ == "__main__":
    unittest.main()
