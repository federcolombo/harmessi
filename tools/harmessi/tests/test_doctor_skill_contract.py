"""Check de Doctor `HARMESSI-SKILL-CONTRATO` (validación estructural de
`.claude/skills/lead-data-scientist/skills/*.md`) y plantilla `templates/skill.md`."""
from __future__ import annotations

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools.dsguard import skill_contract
from tools.harmessi import doctor as doctor_mod
from tools.harmessi.tests.test_doctor import (
    _crear_interprete_falso,
    _crear_repo_git_temporal,
    _mock_solo_interprete,
)

RAIZ = Path(__file__).resolve().parents[3]
PLANTILLA = RAIZ / ".claude" / "skills" / "lead-data-scientist" / "templates" / "skill.md"
DIR_SKILLS = ".claude/skills/lead-data-scientist/skills"

SKILL_VALIDA = (
    "---\n"
    "name: mi-skill\n"
    "purpose: Guiar algo\n"
    "when_to_load: Cuando aplica\n"
    "roles: [lead-data-scientist]\n"
    "---\n\n# mi-skill\n"
)
SKILL_INVALIDA = (
    "---\n"
    "name: mala-skill\n"
    "purpose: Guiar algo\n"
    "when_to_load: Cuando aplica\n"
    "roles: [lead-data-scientist]\n"
    "tools: [Bash]\n"
    "---\n\n# mala-skill\n"
)


class TestCheckDirecto(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="doctor_skill_contrato_"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def _skill(self, nombre: str, texto: str):
        carpeta = self.dir / DIR_SKILLS
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / f"{nombre}.md").write_text(texto, encoding="utf-8")

    def test_sin_directorio_skills_es_ok(self):
        resultados = doctor_mod._ejecutar_check(
            doctor_mod.SECCION_HARMESSI, "HARMESSI-SKILL-CONTRATO", doctor_mod._check_skill_contrato, self.dir
        )
        self.assertEqual([(r.nivel, r.codigo) for r in resultados], [(doctor_mod.NIVEL_OK, "HARMESSI-SKILL-CONTRATO")])

    def test_modulo_no_disponible_es_warn_nunca_fail(self):
        with patch.object(doctor_mod, "skill_contract", None):
            resultados = doctor_mod._ejecutar_check(
                doctor_mod.SECCION_HARMESSI, "HARMESSI-SKILL-CONTRATO", doctor_mod._check_skill_contrato, self.dir
            )
        self.assertEqual([(r.nivel, r.codigo) for r in resultados], [(doctor_mod.NIVEL_WARN, "HARMESSI-SKILL-CONTRATO")])
        self.assertIn("no disponible", resultados[0].mensaje)

    def test_skill_valida_es_ok(self):
        self._skill("mi-skill", SKILL_VALIDA)
        resultados = doctor_mod._ejecutar_check(
            doctor_mod.SECCION_HARMESSI, "HARMESSI-SKILL-CONTRATO", doctor_mod._check_skill_contrato, self.dir
        )
        self.assertEqual([r.nivel for r in resultados], [doctor_mod.NIVEL_OK])

    def test_skill_invalida_reporta_contrato_como_warn(self):
        # WARN y no ERROR: una skill es guidance y no desactiva ningún guardrail.
        self._skill("mala-skill", SKILL_INVALIDA)
        resultados = doctor_mod._ejecutar_check(
            doctor_mod.SECCION_HARMESSI, "HARMESSI-SKILL-CONTRATO", doctor_mod._check_skill_contrato, self.dir
        )
        self.assertTrue(resultados)
        for r in resultados:
            self.assertEqual(r.codigo, "HARMESSI-SKILL-CONTRATO")
            self.assertEqual(r.nivel, doctor_mod.NIVEL_WARN)
        self.assertIn("SKILL-CAMPO-NO-PERMITIDO", resultados[0].mensaje)
        self.assertIn("mala-skill.md", resultados[0].ubicacion)


    def test_artifact_protegido_es_warn_nunca_fail(self):
        self._skill("mi-skill", SKILL_VALIDA.replace("---\n\n#", "artifacts: [tools/x.py]\n---\n\n#"))
        resultados = doctor_mod._ejecutar_check(
            doctor_mod.SECCION_HARMESSI, "HARMESSI-SKILL-CONTRATO", doctor_mod._check_skill_contrato, self.dir
        )
        self.assertEqual([r.nivel for r in resultados], [doctor_mod.NIVEL_WARN])
        self.assertIn("SKILL-ARTIFACT-SUPERFICIE-PROTEGIDA", resultados[0].mensaje)


class TestPlantilla(unittest.TestCase):
    def test_plantilla_en_archivos_esperados(self):
        self.assertIn(
            ".claude/skills/lead-data-scientist/templates/skill.md", doctor_mod._ARCHIVOS_SKILL_ESPERADOS
        )

    def test_plantilla_copiada_pasa_validar_skill(self):
        with tempfile.TemporaryDirectory(prefix="plantilla_skill_") as tmp:
            destino = Path(tmp) / "nombre-de-skill.md"
            shutil.copyfile(PLANTILLA, destino)
            hallazgos = skill_contract.validar_skill(destino, {"lead-data-scientist"})
        self.assertEqual(hallazgos, [])


class TestDoctorInstalado(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal(prefix="doctor_skill_contrato_inst_")
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        from tools.ds_init.cli import main

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            codigo = main(["install", "--destino", str(self.repo), "--nombre", "p", "--execute"])
        self.assertEqual(codigo, 0)

    def _doctor(self):
        _crear_interprete_falso(self.repo)
        with patch("tools.harmessi.doctor.subprocess.run", side_effect=_mock_solo_interprete(0, "")):
            resultados, _exit = doctor_mod.ejecutar(self.repo)
        return resultados

    def test_instalacion_limpia_check_ok_y_plantilla_instalada(self):
        self.assertTrue((self.repo / ".claude/skills/lead-data-scientist/templates/skill.md").is_file())
        self.assertTrue((self.repo / "tools/dsguard/skill_contract.py").is_file())
        self.assertTrue((self.repo / "tools/dsguard/ownership.py").is_file())
        # La instalación ahora trae la skill domain-modeling (y no crea GLOSSARY.md).
        self.assertTrue((self.repo / DIR_SKILLS / "domain-modeling.md").is_file())
        self.assertFalse((self.repo / "GLOSSARY.md").exists())
        # Y problem-framing, esperada por Doctor.
        self.assertTrue((self.repo / DIR_SKILLS / "problem-framing.md").is_file())
        self.assertIn(
            ".claude/skills/lead-data-scientist/skills/problem-framing.md",
            doctor_mod._ARCHIVOS_SKILL_ESPERADOS,
        )
        resultados = self._doctor()
        contrato = [r for r in resultados if r.codigo == "HARMESSI-SKILL-CONTRATO"]
        self.assertEqual([r.nivel for r in contrato], [doctor_mod.NIVEL_OK])

    def test_diagnosing_bugs_instalada_y_esperada_por_doctor(self):
        self.assertTrue((self.repo / DIR_SKILLS / "diagnosing-bugs.md").is_file())
        self.assertIn(
            ".claude/skills/lead-data-scientist/skills/diagnosing-bugs.md",
            doctor_mod._ARCHIVOS_SKILL_ESPERADOS,
        )

    def test_diagnosing_bugs_borrada_reporta_skill_faltante(self):
        (self.repo / DIR_SKILLS / "diagnosing-bugs.md").unlink()
        resultados = self._doctor()
        faltantes = [r for r in resultados if r.codigo == "HARMESSI-SKILL-FALTANTE"]
        self.assertTrue(any("diagnosing-bugs.md" in r.mensaje for r in faltantes), faltantes)

    def test_problem_framing_borrada_reporta_skill_faltante(self):
        (self.repo / DIR_SKILLS / "problem-framing.md").unlink()
        resultados = self._doctor()
        faltantes = [r for r in resultados if r.codigo == "HARMESSI-SKILL-FALTANTE"]
        self.assertTrue(any("problem-framing.md" in r.mensaje for r in faltantes), faltantes)

    def test_skill_de_proyecto_valida_no_genera_drift(self):
        carpeta = self.repo / DIR_SKILLS
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "mi-skill.md").write_text(SKILL_VALIDA, encoding="utf-8")
        resultados = self._doctor()
        drift = [r for r in resultados if r.codigo.startswith("HARMESSI-DRIFT") and "skills/" in r.mensaje]
        self.assertEqual(drift, [])
        contrato = [r for r in resultados if r.codigo == "HARMESSI-SKILL-CONTRATO"]
        self.assertEqual([r.nivel for r in contrato], [doctor_mod.NIVEL_OK])

    def test_skill_de_proyecto_invalida_reporta_contrato_sin_drift(self):
        carpeta = self.repo / DIR_SKILLS
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "mala-skill.md").write_text(SKILL_INVALIDA, encoding="utf-8")
        resultados = self._doctor()
        contrato = [r for r in resultados if r.codigo == "HARMESSI-SKILL-CONTRATO"]
        self.assertTrue(contrato)
        self.assertTrue(all(r.nivel == doctor_mod.NIVEL_WARN for r in contrato))
        drift = [r for r in resultados if r.codigo.startswith("HARMESSI-DRIFT") and "skills/" in r.mensaje]
        self.assertEqual(drift, [])


if __name__ == "__main__":
    unittest.main()
