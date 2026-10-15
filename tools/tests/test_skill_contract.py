"""Tests de `tools.dsguard.skill_contract` (Change
20261014-composable-skills-writer-semantics, R2/R3/R6/R7/R27).

Solo repos temporales (tempdirs); sin red ni subprocess.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import skill_contract as sc  # noqa: E402

ROLES = {"lead-data-scientist", "python-data-engineer", "data-science-reviewer", "metodologo"}

SKILL_VALIDA = (
    "---\n"
    "name: domain-modeling\n"
    "purpose: Modelar el dominio\n"
    "when_to_load: Al definir terminos del dominio\n"
    "roles: [lead-data-scientist, python-data-engineer]\n"
    "artifacts: [GLOSSARY.md]\n"
    "---\n"
    "Cuerpo de guidance.\n"
)


def _frontmatter(**campos) -> str:
    base = {
        "name": "mi-skill",
        "purpose": "Un proposito",
        "when_to_load": "Cuando aplique",
        "roles": "[lead-data-scientist]",
    }
    for k, v in campos.items():
        if v is None:
            base.pop(k, None)
        else:
            base[k] = v
    lineas = [f"{k}: {v}" for k, v in base.items()]
    return "---\n" + "\n".join(lineas) + "\n---\ncuerpo\n"


class _Base(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="skill_contract_test_"))
        self.addCleanup(shutil.rmtree, self.repo, True)

    def escribir(self, relativa: str, texto: str, binario: bytes = None) -> Path:
        ruta = self.repo / relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        if binario is not None:
            ruta.write_bytes(binario)
        else:
            ruta.write_text(texto, encoding="utf-8", newline="")
        return ruta

    def skill(self, texto: str, nombre: str = "mi-skill") -> Path:
        return self.escribir(f"{sc.DIR_SKILLS}/{nombre}.md", texto)

    def codigos(self, texto: str, nombre: str = "mi-skill", roles=ROLES) -> list:
        return [f.codigo for f in sc.validar_skill(self.skill(texto, nombre), roles)]


class TestSkillValida(_Base):
    def test_skill_valida_sin_hallazgos(self):
        ruta = self.skill(SKILL_VALIDA, "domain-modeling")
        self.assertEqual(sc.validar_skill(ruta, ROLES), [])

    def test_artifacts_opcional(self):
        self.assertEqual(self.codigos(_frontmatter()), [])

    def test_comillas_en_listas(self):
        texto = _frontmatter(roles="['lead-data-scientist', \"metodologo\"]")
        self.assertEqual(self.codigos(texto), [])


class TestFrontmatter(_Base):
    def test_sin_frontmatter(self):
        self.assertEqual(self.codigos("# solo cuerpo\n"), ["SKILL-FRONTMATTER-AUSENTE"])

    def test_sin_cierre(self):
        self.assertEqual(self.codigos("---\nname: mi-skill\n"), ["SKILL-FRONTMATTER-AUSENTE"])

    def test_parsear_devuelve_none_sin_frontmatter(self):
        datos, hallazgos = sc.parsear_frontmatter("hola")
        self.assertIsNone(datos)
        self.assertEqual(hallazgos[0].codigo, "SKILL-FRONTMATTER-AUSENTE")

    def test_parsear_tipos(self):
        datos, hallazgos = sc.parsear_frontmatter("---\na: x\nb: [1, 'dos', \"t,res\"]\nc: []\n---\n")
        self.assertEqual(hallazgos, [])
        self.assertEqual(datos, {"a": "x", "b": ["1", "dos", "t,res"], "c": []})

    def test_bom(self):
        texto = "\ufeff" + SKILL_VALIDA
        ruta = self.escribir(f"{sc.DIR_SKILLS}/domain-modeling.md", "", binario=texto.encode("utf-8"))
        self.assertEqual(sc.validar_skill(ruta, ROLES), [])

    def test_crlf(self):
        texto = SKILL_VALIDA.replace("\n", "\r\n")
        ruta = self.escribir(f"{sc.DIR_SKILLS}/domain-modeling.md", "", binario=texto.encode("utf-8"))
        self.assertEqual(sc.validar_skill(ruta, ROLES), [])

    def test_bom_y_crlf(self):
        texto = "\ufeff" + SKILL_VALIDA.replace("\n", "\r\n")
        ruta = self.escribir(f"{sc.DIR_SKILLS}/domain-modeling.md", "", binario=texto.encode("utf-8"))
        self.assertEqual(sc.validar_skill(ruta, ROLES), [])

    def test_linea_malformada(self):
        texto = _frontmatter().replace("cuerpo", "cuerpo").replace("---\nname", "---\nlinea sin clave\nname", 1)
        self.assertIn("SKILL-CAMPO-NO-PERMITIDO", self.codigos(texto))

    def test_ubicacion_relativa_en_directorio(self):
        self.skill("sin frontmatter")
        hallazgos = sc.validar_directorio_skills(self.repo)
        self.assertEqual(hallazgos[0].ubicacion, f"{sc.DIR_SKILLS}/mi-skill.md")


class TestCamposObligatorios(_Base):
    def test_cada_campo_faltante(self):
        for campo in sc.CLAVES_OBLIGATORIAS:
            with self.subTest(campo=campo):
                codigos = self.codigos(_frontmatter(**{campo: None}))
                self.assertEqual(codigos, ["SKILL-CAMPO-FALTANTE"])

    def test_campo_vacio(self):
        for campo in ("purpose", "when_to_load"):
            with self.subTest(campo=campo):
                self.assertEqual(self.codigos(_frontmatter(**{campo: ""})), ["SKILL-CAMPO-FALTANTE"])

    def test_purpose_como_lista(self):
        self.assertEqual(self.codigos(_frontmatter(purpose="[a, b]")), ["SKILL-CAMPO-FALTANTE"])

    def test_roles_no_es_lista(self):
        self.assertEqual(self.codigos(_frontmatter(roles="lead-data-scientist")), ["SKILL-CAMPO-FALTANTE"])

    def test_roles_vacia(self):
        self.assertEqual(self.codigos(_frontmatter(roles="[]")), ["SKILL-CAMPO-FALTANTE"])


class TestNombre(_Base):
    def test_nombre_invalido(self):
        for malo in ("Mi_Skill", "1skill", "mi skill", "-x"):
            with self.subTest(nombre=malo):
                self.assertIn("SKILL-NOMBRE-INVALIDO", self.codigos(_frontmatter(name=malo)))

    def test_nombre_distinto_de_archivo(self):
        codigos = self.codigos(_frontmatter(name="otra-skill"))
        self.assertEqual(codigos, ["SKILL-NOMBRE-INVALIDO"])


class TestRoles(_Base):
    def test_rol_desconocido(self):
        self.assertEqual(self.codigos(_frontmatter(roles="[inventado]")), ["SKILL-ROL-DESCONOCIDO"])

    def test_ml_engineer_no_es_rol(self):
        self.assertEqual(
            self.codigos(_frontmatter(roles="[lead-data-scientist, ml-engineer]")),
            ["SKILL-ROL-DESCONOCIDO"],
        )

    def test_roles_conocidos_repo_temporal(self):
        self.escribir(".claude/agents/x.md", "---\nname: x-rol\nmodel: algo\n---\ncuerpo\n")
        self.escribir(".claude/agents/sin-nombre.md", "sin frontmatter")
        roles = sc.roles_conocidos(self.repo)
        self.assertEqual(roles, {"lead-data-scientist", "x-rol"})

    def test_roles_conocidos_sin_directorio(self):
        self.assertEqual(sc.roles_conocidos(self.repo), {"lead-data-scientist"})

    def test_roles_conocidos_del_repo_real(self):
        roles = sc.roles_conocidos(REPO_ORIGEN)
        self.assertIn("lead-data-scientist", roles)
        self.assertIn("python-data-engineer", roles)
        self.assertNotIn("ml-engineer", roles)


class TestClavesNoPermitidas(_Base):
    def test_cada_clave_prohibida(self):
        self.assertEqual(len(sc.CLAVES_PROHIBIDAS), 12)
        for clave in sc.CLAVES_PROHIBIDAS:
            with self.subTest(clave=clave):
                texto = _frontmatter().replace("---\ncuerpo", f"{clave}: x\n---\ncuerpo")
                hallazgos = sc.validar_skill(self.skill(texto), ROLES)
                self.assertEqual([f.codigo for f in hallazgos], ["SKILL-CAMPO-NO-PERMITIDO"])
                self.assertIn("prohibida", hallazgos[0].mensaje)
                self.assertIn(clave, hallazgos[0].mensaje)

    def test_clave_desconocida(self):
        texto = _frontmatter().replace("---\ncuerpo", "version: 1\n---\ncuerpo")
        hallazgos = sc.validar_skill(self.skill(texto), ROLES)
        self.assertEqual([f.codigo for f in hallazgos], ["SKILL-CAMPO-NO-PERMITIDO"])
        self.assertIn("desconocida", hallazgos[0].mensaje)

    def test_clave_duplicada(self):
        texto = _frontmatter().replace("---\ncuerpo", "purpose: otro\n---\ncuerpo")
        self.assertIn("SKILL-CAMPO-NO-PERMITIDO", self.codigos(texto))


class TestArtifacts(_Base):
    def test_validos(self):
        texto = _frontmatter(artifacts="[GLOSSARY.md, docs/a.md, 'tools/x.py']")
        self.assertEqual(self.codigos(texto), [])

    def test_vacio_valido(self):
        self.assertEqual(self.codigos(_frontmatter(artifacts="[]")), [])

    def test_con_punto_punto(self):
        self.assertEqual(self.codigos(_frontmatter(artifacts="[../fuera.md]")), ["SKILL-ARTIFACT-INVALIDO"])

    def test_absoluta(self):
        for ruta in ("/etc/x.md", "C:/x.md"):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.codigos(_frontmatter(artifacts=f"[{ruta}]")), ["SKILL-ARTIFACT-INVALIDO"])

    def test_comodin(self):
        for ruta in ("docs/**", "docs/*.md", "docs/"):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.codigos(_frontmatter(artifacts=f"[{ruta}]")), ["SKILL-ARTIFACT-INVALIDO"])

    def test_ruta_protegida(self):
        self.assertEqual(self.codigos(_frontmatter(artifacts="[.git/config]")), ["SKILL-ARTIFACT-INVALIDO"])

    def test_artifacts_no_lista(self):
        self.assertEqual(self.codigos(_frontmatter(artifacts="GLOSSARY.md")), ["SKILL-CAMPO-NO-PERMITIDO"])


class TestDirectorio(_Base):
    def test_directorio_ausente(self):
        self.assertEqual(sc.validar_directorio_skills(self.repo), [])
        self.assertEqual(sc.skills_existentes(self.repo), set())

    def test_directorio_valida_todo(self):
        self.escribir(".claude/agents/python-data-engineer.md", "---\nname: python-data-engineer\n---\n")
        self.escribir(f"{sc.DIR_SKILLS}/domain-modeling.md", SKILL_VALIDA)
        self.escribir(f"{sc.DIR_SKILLS}/rota.md", "sin frontmatter")
        hallazgos = sc.validar_directorio_skills(self.repo)
        self.assertEqual([f.codigo for f in hallazgos], ["SKILL-FRONTMATTER-AUSENTE"])
        self.assertTrue(hallazgos[0].ubicacion.endswith("rota.md"))
        self.assertEqual(sc.skills_existentes(self.repo), {"domain-modeling", "rota"})

    def test_directorio_usa_roles_del_repo(self):
        self.escribir(".claude/agents/escritor.md", "---\nname: escritor\n---\n")
        self.escribir(f"{sc.DIR_SKILLS}/mi-skill.md", _frontmatter(roles="[escritor]"))
        self.assertEqual(sc.validar_directorio_skills(self.repo), [])


class TestReferencias(unittest.TestCase):
    TASKS = (
        "# Tasks\n\n## Skills cargados\n"
        "<!-- - plantilla — T0 — comentario -->\n"
        "Texto suelto que no es bullet.\n"
        "- domain-modeling — T1 — definir terminos\n"
        "- otra-skill - T2 - motivo\n"
        "- domain-modeling — T3 — repetida\n\n"
        "## Otra seccion\n- no-cuenta — T9 — x\n"
    )

    def test_extraccion(self):
        self.assertEqual(sc.referencias_skills_cargados(self.TASKS), ["domain-modeling", "otra-skill"])

    def test_existente_ok(self):
        self.assertEqual(sc.validar_referencias_skills(self.TASKS, {"domain-modeling", "otra-skill"}), [])

    def test_inexistente_hallazgo(self):
        hallazgos = sc.validar_referencias_skills(self.TASKS, {"domain-modeling"})
        self.assertEqual([f.codigo for f in hallazgos], ["SKILL-REFERENCIA-DESCONOCIDA"])
        self.assertIn("otra-skill", hallazgos[0].mensaje)

    def test_seccion_ausente(self):
        self.assertEqual(sc.validar_referencias_skills("# Tasks\n\n## Otra\n- x — T1 — y\n", set()), [])

    def test_seccion_vacia_o_solo_comentarios(self):
        texto = "## Skills cargados\n<!-- - x — T1 — y -->\n\n## Siguiente\n"
        self.assertEqual(sc.validar_referencias_skills(texto, set()), [])

    def test_bullets_de_prosa_ignorados(self):
        for bullet in ("(ninguna)", "(ninguna por ahora)", "n/a", "N/A", "`ninguna`",
                       "Ninguno", "na", "-", "(n/a) — T1 — x", "Ninguna skill cargada",
                       "n/a – sin skills", "Ninguna, por ahora", "`ninguna` skill"):
            with self.subTest(bullet=bullet):
                texto = f"## Skills cargados\n- {bullet}\n"
                self.assertEqual(sc.referencias_skills_cargados(texto), [])
                self.assertEqual(sc.validar_referencias_skills(texto, set()), [])

    def test_typo_de_skill_sigue_fallando(self):
        for nombre in ("ningunaa", "nada", "domain-modelin"):
            with self.subTest(nombre=nombre):
                texto = f"## Skills cargados\n- {nombre} — T1 — x\n"
                hallazgos = sc.validar_referencias_skills(texto, {"domain-modeling"})
                self.assertEqual([f.codigo for f in hallazgos], ["SKILL-REFERENCIA-DESCONOCIDA"])

    def test_marcador_de_plantilla_ignorado(self):
        texto = "## Skills cargados\n- <skill> — <tarea> — <motivo>\n"
        self.assertEqual(sc.referencias_skills_cargados(texto), [])


class TestImportLimpio(unittest.TestCase):
    def test_import_sin_tools_en_sys_path(self):
        codigo = (
            "import sys; sys.path.insert(0, %r); "
            "from tools.dsguard import skill_contract; "
            "print(skill_contract.parsear_frontmatter('---\\nname: x\\n---\\n')[0]); "
            "print(skill_contract.validar_referencias_skills('## Skills cargados\\n- a - T1 - m\\n', set()))"
            % str(REPO_ORIGEN)
        )
        res = subprocess.run(
            [sys.executable, "-c", codigo], cwd=str(REPO_ORIGEN),
            capture_output=True, text=True,
        )
        self.assertEqual(res.returncode, 0, res.stderr)


class TestNeutralidad(unittest.TestCase):
    def test_modulo_sin_nombres_de_proveedor(self):
        texto = (REPO_ORIGEN / "tools" / "dsguard" / "skill_contract.py").read_text(encoding="utf-8")
        for prohibido in ("Claude", "Codex", "Gemini", "Agent"):
            with self.subTest(nombre=prohibido):
                self.assertNotIn(prohibido, texto)


if __name__ == "__main__":
    unittest.main()
