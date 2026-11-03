"""Tests de `tools.dsguard.ownership` (Change 20261014-composable-skills-writer-
semantics, R10-R13): parser y validador de la sección `## Ownership de
writers`. Funciones puras: no requieren repo git ni I/O."""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import ownership  # noqa: E402
from dsguard.ownership import (  # noqa: E402
    Instancia,
    entrada_cubierta,
    entradas_solapan,
    evaluar_ownership,
    parsear_ownership,
    validar_ownership,
)

ROL = "python-data-engineer"
ALCANCE = ["tools/dsguard/**", "tools/tests/**"]


def _tasks(*bloques: str, historial: str = "") -> str:
    """Arma un tasks.md mínimo con la sección de ownership."""
    texto = "# Tareas\n\nestado: en_implementacion\n\n## Ownership de writers\n"
    texto += "\n".join(bloques) + "\n"
    if historial:
        texto += "\n## Historial de ownership\n" + historial + "\n"
    texto += "\n## Tareas\n- [ ] T1\n"
    return texto


def _bloque(id_: str, rol: str, *entradas: str, tareas: str = "T1") -> str:
    lineas = [f"### {id_} — {rol} — {tareas}"]
    lineas += [f"- {e}" for e in entradas]
    return "\n".join(lineas)


def _codigos(hallazgos) -> list:
    return sorted(h.codigo for h in hallazgos)


class TestEjemplosDelPedido(unittest.TestCase):
    def test_valido_sin_hallazgos(self):
        texto = _tasks(
            _bloque("A", ROL, "tools/dsguard/foo.py", "tools/tests/test_foo.py"),
            _bloque("B", ROL, "tools/dsguard/bar.py", "tools/tests/test_bar.py"),
        )
        self.assertEqual(evaluar_ownership(texto, ALCANCE), [])

    def test_invalido_directorio_en_ambas(self):
        texto = _tasks(
            _bloque("A", ROL, "tools/dsguard/**"),
            _bloque("B", ROL, "tools/dsguard/**"),
        )
        hallazgos = evaluar_ownership(texto, ALCANCE)
        self.assertEqual(_codigos(hallazgos), ["OWNERSHIP-SOLAPADO"])
        msg = hallazgos[0].mensaje
        self.assertIn("'A'", msg)
        self.assertIn("'B'", msg)
        self.assertIn("tools/dsguard/**", msg)
        self.assertEqual(hallazgos[0].ubicacion, "tasks.md#Ownership de writers")


class TestParser(unittest.TestCase):
    def test_sin_seccion(self):
        self.assertEqual(parsear_ownership("# Tareas\n\n## Tareas\n- x\n"), ([], []))
        self.assertEqual(evaluar_ownership("# Tareas\n", ALCANCE), [])
        self.assertEqual(evaluar_ownership("", []), [])

    def test_instancia_parseada(self):
        texto = _tasks(_bloque("W1", ROL, "tools/a.py", "tools/b/**", tareas="T1, T2"))
        instancias, hallazgos = parsear_ownership(texto)
        self.assertEqual(hallazgos, [])
        self.assertEqual(len(instancias), 1)
        inst = instancias[0]
        self.assertEqual((inst.id, inst.rol, inst.tareas), ("W1", ROL, "T1, T2"))
        self.assertEqual(inst.entradas, ["tools/a.py", "tools/b/**"])

    def test_separador_guion_y_tareas_opcionales(self):
        texto = _tasks(
            f"### A - {ROL} - T1\n- tools/a.py",
            f"### B — {ROL}\n- tools/b.py",
            f"### C — {ROL} — texto libre de tareas\n- tools/c.py",
        )
        instancias, hallazgos = parsear_ownership(texto)
        self.assertEqual(hallazgos, [])
        self.assertEqual([i.id for i in instancias], ["A", "B", "C"])
        self.assertEqual([i.rol for i in instancias], [ROL] * 3)
        self.assertEqual(instancias[1].tareas, "")
        self.assertEqual(instancias[2].tareas, "texto libre de tareas")

    def test_comentarios_y_prosa_ignorados(self):
        texto = (
            "## Ownership de writers\n"
            "Plan propuesto, prosa libre.\n"
            "<!-- - un/bullet/comentado.py -->\n"
            f"### A — {ROL} — T1\n"
            "Nota en prosa.\n"
            "- tools/a.py\n"
        )
        instancias, hallazgos = parsear_ownership(texto)
        self.assertEqual(hallazgos, [])
        self.assertEqual(instancias[0].entradas, ["tools/a.py"])

    def test_historial_no_se_interpreta(self):
        texto = _tasks(
            _bloque("A", ROL, "tools/dsguard/a.py"),
            historial=f"### X — rol-raro — T9\n- tools/dsguard/a.py\n- *.py\n- suelto",
        )
        instancias, hallazgos = parsear_ownership(texto)
        self.assertEqual([i.id for i in instancias], ["A"])
        self.assertEqual(hallazgos, [])
        self.assertEqual(evaluar_ownership(texto, ALCANCE), [])

    def test_encabezado_malformado(self):
        for encabezado in (
            "### solo-id",
            f"### id con espacios — {ROL} — T1",
            f"### a!b — {ROL} — T1",
            "###",
        ):
            with self.subTest(encabezado=encabezado):
                texto = _tasks(encabezado + "\n- tools/dsguard/a.py")
                instancias, hallazgos = parsear_ownership(texto)
                self.assertEqual(instancias, [])
                self.assertEqual(_codigos(hallazgos), ["OWNERSHIP-SECCION-ILEGIBLE"])

    def test_bullet_fuera_de_encabezado(self):
        texto = _tasks("- tools/dsguard/a.py", _bloque("A", ROL, "tools/dsguard/b.py"))
        instancias, hallazgos = parsear_ownership(texto)
        self.assertEqual(_codigos(hallazgos), ["OWNERSHIP-SECCION-ILEGIBLE"])
        self.assertEqual([i.id for i in instancias], ["A"])

    def test_entradas_repetidas_en_la_misma_instancia_se_unifican(self):
        texto = _tasks(_bloque("A", ROL, "tools/a.py", "./tools/a.py", "tools\\a.py"))
        instancias, hallazgos = parsear_ownership(texto)
        self.assertEqual(hallazgos, [])
        self.assertEqual(instancias[0].entradas, ["tools/a.py"])


class TestSeccion(unittest.TestCase):
    def test_encabezado_con_sufijo(self):
        texto = (
            "## Ownership de writers (borrador)\n"
            f"### A — {ROL} — T1\n- tools/dsguard/a.py\n"
        )
        instancias, hallazgos = parsear_ownership(texto)
        self.assertEqual(_codigos(hallazgos), ["OWNERSHIP-SECCION-ILEGIBLE"])
        self.assertIn("sufijo", hallazgos[0].mensaje)
        self.assertEqual(_codigos(evaluar_ownership(texto, ALCANCE)), ["OWNERSHIP-SECCION-ILEGIBLE"])

    def test_seccion_duplicada_no_valida_el_resto(self):
        texto = (
            "## Ownership de writers\n"
            f"### A — {ROL} — T1\n- tools/dsguard/a.py\n"
            "## Ownership de writers\n"
            f"### B — {ROL} — T2\n- tools/dsguard/a.py\n"
        )
        instancias, hallazgos = parsear_ownership(texto)
        self.assertEqual(instancias, [])
        self.assertEqual(_codigos(hallazgos), ["OWNERSHIP-SECCION-ILEGIBLE"])
        self.assertIn("duplicada", hallazgos[0].mensaje)
        self.assertEqual(_codigos(evaluar_ownership(texto, ALCANCE)), ["OWNERSHIP-SECCION-ILEGIBLE"])

    def test_encabezado_no_canonico(self):
        for encabezado in ("## Ownership de Writers", "## Ownership de writer", "## ownership de writers"):
            with self.subTest(encabezado=encabezado):
                texto = f"# T\n\n{encabezado}\n### A — {ROL} — T1\n- tools/dsguard/a.py\n"
                instancias, hallazgos = parsear_ownership(texto)
                self.assertEqual(instancias, [])
                self.assertEqual(_codigos(hallazgos), ["OWNERSHIP-SECCION-ILEGIBLE"])
                self.assertIn("no canónico", hallazgos[0].mensaje)

    def test_fence_sin_cerrar_con_encabezado_tragado(self):
        texto = f"# T\n\n```\n## Ownership de writers\n### A — {ROL} — T1\n- tools/dsguard/a.py\n"
        instancias, hallazgos = parsear_ownership(texto)
        self.assertEqual(instancias, [])
        self.assertEqual(_codigos(hallazgos), ["OWNERSHIP-SECCION-ILEGIBLE"])
        self.assertIn("sin cerrar", hallazgos[0].mensaje)

    def test_fence_sin_cerrar_sin_encabezado_se_ignora(self):
        texto = "# T\n\n```\ncodigo cualquiera\n## Otra\n"
        self.assertEqual(parsear_ownership(texto), ([], []))

    def test_encabezado_al_final_sin_newline(self):
        self.assertEqual(parsear_ownership("# T\n\n## Ownership de writers"), ([], []))
        _, hallazgos = parsear_ownership("# T\n\n## Ownership de writers (x)")
        self.assertEqual(_codigos(hallazgos), ["OWNERSHIP-SECCION-ILEGIBLE"])

    def test_encabezado_citado_en_bloque_de_codigo_se_ignora(self):
        texto = (
            "# Tareas\n\n```\n## Ownership de writers\n"
            f"### Z — {ROL} — T9\n- docs/x.py\n```\n\n"
            + _tasks(_bloque("A", ROL, "tools/dsguard/a.py")).split("# Tareas\n", 1)[1]
        )
        instancias, hallazgos = parsear_ownership(texto)
        self.assertEqual(hallazgos, [])
        self.assertEqual([i.id for i in instancias], ["A"])
        self.assertEqual(evaluar_ownership(texto, ALCANCE), [])

    def test_bullets_en_bloque_de_codigo_dentro_de_la_seccion_no_cuentan(self):
        texto = _tasks(_bloque("A", ROL, "tools/dsguard/a.py") + "\n```\n- docs/x.py\n```")
        instancias, hallazgos = parsear_ownership(texto)
        self.assertEqual(hallazgos, [])
        self.assertEqual(instancias[0].entradas, ["tools/dsguard/a.py"])

    def test_comentario_html_con_ejemplo_se_ignora(self):
        texto = (
            "<!-- ejemplo:\n## Ownership de writers\n### Z — rol-raro\n- *.py\n-->\n"
            + _tasks(_bloque("A", ROL, "tools/dsguard/a.py")).split("# Tareas\n", 1)[1]
        )
        instancias, hallazgos = parsear_ownership(texto)
        self.assertEqual(hallazgos, [])
        self.assertEqual([i.id for i in instancias], ["A"])


class TestDirectorioSinComodin(unittest.TestCase):
    def test_literal_directorio_no_es_el_directorio(self):
        # Usar `dir/**` para poseer un directorio: `tools/dsguard` es un
        # archivo con ese nombre exacto, no el directorio.
        self.assertFalse(entradas_solapan("tools/dsguard", "tools/dsguard/**"))
        self.assertFalse(entradas_solapan("tools/dsguard/**", "tools/dsguard"))
        self.assertFalse(entrada_cubierta("tools/dsguard/a.py", ["tools/dsguard"]))
        texto = _tasks(
            _bloque("A", ROL, "tools/dsguard"),
            _bloque("B", ROL, "tools/dsguard/**"),
        )
        self.assertNotIn("OWNERSHIP-SOLAPADO", _codigos(evaluar_ownership(texto, ALCANCE)))


class TestSolape(unittest.TestCase):
    def test_archivo_igual_archivo(self):
        self.assertTrue(entradas_solapan("tools/a.py", "tools/a.py"))
        self.assertFalse(entradas_solapan("tools/a.py", "tools/b.py"))

    def test_directorio_vs_archivo_dentro(self):
        self.assertTrue(entradas_solapan("tools/**", "tools/a.py"))
        self.assertTrue(entradas_solapan("tools/a/b.py", "tools/**"))
        self.assertTrue(entradas_solapan("tools/**", "tools/a/b/c.py"))

    def test_directorio_vs_subdirectorio(self):
        self.assertTrue(entradas_solapan("a/**", "a/b/**"))
        self.assertTrue(entradas_solapan("a/b/**", "a/**"))

    def test_dos_directorios_anidados_e_iguales(self):
        self.assertTrue(entradas_solapan("tools/dsguard/**", "tools/dsguard/**"))
        self.assertTrue(entradas_solapan("tools/**", "tools/dsguard/x/**"))

    def test_equivalentes_tras_normalizacion(self):
        texto = _tasks(
            _bloque("A", ROL, "./tools/dsguard/x.py"),
            _bloque("B", ROL, "tools/dsguard/x.py"),
        )
        self.assertEqual(_codigos(evaluar_ownership(texto, ALCANCE)), ["OWNERSHIP-SOLAPADO"])

    def test_equivalentes_barra_invertida_y_mayusculas(self):
        texto = _tasks(
            _bloque("A", ROL, "Tools\\DSGuard\\X.py"),
            _bloque("B", ROL, "tools/dsguard/x.py"),
        )
        self.assertEqual(_codigos(evaluar_ownership(texto, ALCANCE)), ["OWNERSHIP-SOLAPADO"])
        self.assertTrue(entradas_solapan("Tools/A.py", "tools/a.PY"))
        self.assertTrue(entradas_solapan("TOOLS/**", "tools/a.py"))

    def test_no_solapan(self):
        self.assertFalse(entradas_solapan("tools/foo/**", "tools/foobar.py"))
        self.assertFalse(entradas_solapan("a/**", "ab/**"))
        self.assertFalse(entradas_solapan("ab/**", "a/**"))
        self.assertFalse(entradas_solapan("a/**", "a.py"))
        self.assertFalse(entradas_solapan("a/b/**", "a/c/**"))

    def test_misma_instancia_no_es_error(self):
        texto = _tasks(_bloque("A", ROL, "tools/dsguard/**", "tools/dsguard/a.py"))
        self.assertEqual(evaluar_ownership(texto, ALCANCE), [])


class TestVacioIdRol(unittest.TestCase):
    def test_vacio(self):
        texto = _tasks(f"### A — {ROL} — T1", _bloque("B", ROL, "tools/dsguard/b.py"))
        hallazgos = evaluar_ownership(texto, ALCANCE)
        self.assertEqual(_codigos(hallazgos), ["OWNERSHIP-VACIO"])
        self.assertIn("'A'", hallazgos[0].mensaje)

    def test_id_duplicado(self):
        texto = _tasks(
            _bloque("A", ROL, "tools/dsguard/a.py"),
            _bloque("A", ROL, "tools/dsguard/b.py"),
        )
        self.assertEqual(_codigos(evaluar_ownership(texto, ALCANCE)), ["OWNERSHIP-ID-DUPLICADO"])

    def test_rol_invalido(self):
        for rol in ("ml-engineer", "data-science-reviewer", "metodologo", "lead-data-scientist"):
            with self.subTest(rol=rol):
                texto = _tasks(_bloque("A", rol, "tools/dsguard/a.py"))
                self.assertEqual(
                    _codigos(evaluar_ownership(texto, ALCANCE)), ["OWNERSHIP-ROL-INVALIDO"]
                )


class TestPatronInvalido(unittest.TestCase):
    def test_patrones_invalidos(self):
        invalidos = (
            "*",
            "**",
            "*.py",
            "tools/*.py",
            "tools/dsguard/?.py",
            "tools/dsguard/[a].py",
            "a/*/b",
            "a/**/b",
            "a/b**",
            "/etc/passwd",
            "C:/Users/x.py",
            "~/x.py",
            "a/../b.py",
            "../x.py",
            ".claude/settings.json",
            ".claude/guardrails.json",
            ".claude/**",
            ".git/config",
            "data/raw/x.csv",
        )
        for entrada in invalidos:
            with self.subTest(entrada=entrada):
                texto = _tasks(_bloque("A", ROL, entrada))
                instancias, hallazgos = parsear_ownership(texto)
                self.assertIn("OWNERSHIP-PATRON-INVALIDO", _codigos(hallazgos))
                self.assertEqual(instancias[0].entradas, [])

    def test_patron_invalido_no_oculta_entradas_validas(self):
        texto = _tasks(_bloque("A", ROL, "tools/dsguard/a.py", "a/*/b"))
        instancias, hallazgos = parsear_ownership(texto)
        self.assertEqual(_codigos(hallazgos), ["OWNERSHIP-PATRON-INVALIDO"])
        self.assertEqual(instancias[0].entradas, ["tools/dsguard/a.py"])

    def test_patrones_validos(self):
        for entrada in ("tools/a.py", "tools/**", "tools/dsguard/", "./tools/a.py", "`tools/a.py`"):
            with self.subTest(entrada=entrada):
                _, hallazgos = parsear_ownership(_tasks(_bloque("A", ROL, entrada)))
                self.assertEqual(hallazgos, [])


class TestFueraDeAlcance(unittest.TestCase):
    def test_literal_fuera(self):
        texto = _tasks(_bloque("A", ROL, "docs/readme.md"))
        hallazgos = evaluar_ownership(texto, ALCANCE)
        self.assertEqual(_codigos(hallazgos), ["OWNERSHIP-FUERA-DE-ALCANCE"])
        self.assertIn("docs/readme.md", hallazgos[0].mensaje)

    def test_literal_cubierto_por_igualdad_o_patron(self):
        self.assertTrue(entrada_cubierta("tools/a.py", ["tools/a.py"]))
        self.assertTrue(entrada_cubierta("tools/dsguard/a.py", ["tools/**"]))
        self.assertTrue(entrada_cubierta("Tools/A.py", ["tools/a.py"]))
        self.assertFalse(entrada_cubierta("tools/a.py", ["tools/b.py"]))
        self.assertFalse(entrada_cubierta("tools/a.py", []))

    def test_directorio_cubierto_por_directorio_o_ancestro(self):
        self.assertTrue(entrada_cubierta("tools/dsguard/**", ["tools/dsguard/**"]))
        self.assertTrue(entrada_cubierta("tools/dsguard/**", ["tools/**"]))
        self.assertTrue(entrada_cubierta("tools/dsguard/x/**", ["tools/**"]))

    def test_directorio_no_cubierto(self):
        self.assertFalse(entrada_cubierta("tools/**", ["tools/dsguard/**"]))
        self.assertFalse(entrada_cubierta("tools/**", ["tools/a.py"]))
        self.assertFalse(entrada_cubierta("tools/foo/**", ["tools/foobar/**"]))
        self.assertFalse(entrada_cubierta("tools/**", []))

    def test_directorio_fuera_de_alcance_en_validacion(self):
        texto = _tasks(_bloque("A", ROL, "docs/**"))
        self.assertEqual(
            _codigos(evaluar_ownership(texto, ALCANCE)), ["OWNERSHIP-FUERA-DE-ALCANCE"]
        )

    def test_scope_amend_no_asigna_ownership(self):
        # Ampliar el scope (parámetro) no crea ni amplía ownership: una
        # instancia sin entradas sigue vacía aunque el scope crezca.
        ampliado = ALCANCE + ["docs/**"]
        texto_vacio = _tasks(f"### A — {ROL} — T1")
        self.assertEqual(_codigos(evaluar_ownership(texto_vacio, ALCANCE)), ["OWNERSHIP-VACIO"])
        self.assertEqual(_codigos(evaluar_ownership(texto_vacio, ampliado)), ["OWNERSHIP-VACIO"])
        # Una entrada fuera de alcance deja de dar el hallazgo solo cuando el
        # scope pasado como parámetro la cubre.
        texto = _tasks(_bloque("A", ROL, "docs/readme.md"))
        self.assertEqual(
            _codigos(evaluar_ownership(texto, ALCANCE)), ["OWNERSHIP-FUERA-DE-ALCANCE"]
        )
        self.assertEqual(evaluar_ownership(texto, ampliado), [])


class TestValidarDirecto(unittest.TestCase):
    def test_instancias_construidas_a_mano(self):
        instancias = [
            Instancia("A", ROL, "T1", ["tools/dsguard/a.py"]),
            Instancia("B", ROL, "T2", ["tools/dsguard/**"]),
        ]
        hallazgos = validar_ownership(instancias, ALCANCE)
        self.assertEqual(_codigos(hallazgos), ["OWNERSHIP-SOLAPADO"])

    def test_roles_writer(self):
        self.assertEqual(ownership.ROLES_WRITER, frozenset({"python-data-engineer"}))


class TestImportLimpio(unittest.TestCase):
    def test_import_sin_tools_en_sys_path(self):
        codigo = (
            "import sys; sys.path.insert(0, %r); "
            "from tools.dsguard import ownership; "
            "t = '## Ownership de writers\\n### A - python-data-engineer - T1\\n- tools/a.py\\n'; "
            "print(ownership.evaluar_ownership(t, ['tools/**']))"
            % str(REPO_ORIGEN)
        )
        res = subprocess.run(
            [sys.executable, "-c", codigo], cwd=str(REPO_ORIGEN),
            capture_output=True, text=True,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "[]")


class TestNeutralidad(unittest.TestCase):
    def test_modulo_sin_nombres_de_proveedor(self):
        fuente = (REPO_ORIGEN / "tools" / "dsguard" / "ownership.py").read_text(encoding="utf-8")
        self.assertIsNone(
            re.search(r"claude|codex|gemini|anthropic|openai", fuente, re.IGNORECASE)
        )


if __name__ == "__main__":
    unittest.main()
