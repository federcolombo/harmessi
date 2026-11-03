"""Test dirigido de neutralidad de `tools/leadrun` frente a Change 4
(`20260930-project-extension-and-installer-integration`, T3/R24, R45): verifica
por DIFF real contra `git show HEAD:...` (no por inspección genérica) que
`tools/leadrun/` (Change 2, cerrado) solo cambió en los 3 puntos exactos
documentados en `spec.md` R24 -- ninguna otra línea de las 4 formas
existentes, ningún archivo fuera de esos 3.

Corre como test de repo (no de paquete instalado): asume que este archivo
vive dentro de un checkout git real de Harmessi (mismo criterio que
`test_v08_leadrun_neutrality.py`, que ya asume la estructura del repo
fuente)."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _diff_unified0(ruta_relativa: str) -> str:
    """`git diff --unified=0 HEAD -- <ruta>` contra la raíz de este repo.
    Devuelve el texto completo del diff (vacío si no hay cambios respecto de
    `HEAD`)."""
    resultado = subprocess.run(
        ["git", "diff", "--unified=0", "HEAD", "--", ruta_relativa],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return resultado.stdout


def _lineas_agregadas(diff_texto: str) -> list:
    """Líneas que empiezan con `+` en el diff, excluyendo la cabecera
    `+++`."""
    return [
        linea[1:]
        for linea in diff_texto.splitlines()
        if linea.startswith("+") and not linea.startswith("+++")
    ]


def _lineas_quitadas(diff_texto: str) -> list:
    """Líneas que empiezan con `-` en el diff, excluyendo la cabecera
    `---`."""
    return [
        linea[1:]
        for linea in diff_texto.splitlines()
        if linea.startswith("-") and not linea.startswith("---")
    ]


class TestDiffDirigidoLeadrunChange4(unittest.TestCase):
    """R45: `tools/leadrun` (Change 2, cerrado) SOLO cambió en los 3 puntos
    exactos de R24 -- `EXECUTION_FORMS`, la función nueva de `allowlist.py`,
    la rama de despacho de `runtime.py` -- verificado por diff dirigido."""

    @classmethod
    def setUpClass(cls):
        # `git diff` contra HEAD asume que este Change todavía no fue
        # commiteado (estado real de la sesión al momento de escribir este
        # test). Si algún día se commitea Change 4 y este test se corre
        # después, `HEAD` ya incluiría estos cambios y los diffs saldrían
        # vacíos -- documentado como limitación conocida de un test "dirigido
        # por diff de working tree", no un bug: en ese caso el test pasa
        # trivialmente (ningún diff nuevo que romper), no falla.
        cls.diff_core = _diff_unified0("tools/leadrun/core.py")
        cls.diff_allowlist = _diff_unified0("tools/leadrun/allowlist.py")
        cls.diff_runtime = _diff_unified0("tools/leadrun/runtime.py")

    def test_los_4_suites_de_tests_de_change_2_sin_ningun_cambio(self):
        # R24 (hallazgo bloqueante del reviewer T8, corregido): los tests
        # NUEVOS de `dependency_install` viven en
        # `tools/leadrun/tests/test_dependency_install_form.py` (archivo
        # propio de Change 4) -- los 4 suites de Change 2 quedan sin editar
        # una sola línea, letra exacta de R24 ("pasan SIN editar ninguno").
        for ruta in (
            "tools/leadrun/tests/test_core.py",
            "tools/leadrun/tests/test_allowlist.py",
            "tools/leadrun/tests/test_scripts.py",
            "tools/leadrun/tests/test_runtime.py",
        ):
            with self.subTest(ruta=ruta):
                self.assertEqual(_diff_unified0(ruta), "", f"{ruta} no debería tener ningún cambio (R24)")

    def test_scripts_py_notebooks_py_init_py_sin_cambios(self):
        for ruta in ("tools/leadrun/scripts.py", "tools/leadrun/notebooks.py", "tools/leadrun/__init__.py"):
            with self.subTest(ruta=ruta):
                self.assertEqual(_diff_unified0(ruta), "", f"{ruta} no debería tener ningún cambio")

    def test_core_py_solo_la_linea_de_execution_forms(self):
        if not self.diff_core:
            self.skipTest("sin diff contra HEAD (working tree ya coincide, ver setUpClass)")
        agregadas = _lineas_agregadas(self.diff_core)
        quitadas = _lineas_quitadas(self.diff_core)
        self.assertEqual(len(agregadas), 1, f"se esperaba 1 línea agregada, hubo {len(agregadas)}: {agregadas}")
        self.assertEqual(len(quitadas), 1, f"se esperaba 1 línea quitada, hubo {len(quitadas)}: {quitadas}")
        self.assertIn('EXECUTION_FORMS = ("script", "pytest", "notebook", "cli_diagnostic")', quitadas[0])
        self.assertIn("dependency_install", agregadas[0])
        self.assertIn("cli_diagnostic", agregadas[0])

    def test_allowlist_py_sin_lineas_quitadas_de_codigo_de_las_4_formas_existentes(self):
        if not self.diff_allowlist:
            self.skipTest("sin diff contra HEAD (working tree ya coincide, ver setUpClass)")
        quitadas = _lineas_quitadas(self.diff_allowlist)
        # Las únicas líneas quitadas permitidas son las de comentario/
        # docstring que reflejan "4 formas" -> "5 formas" (texto, no código)
        # -- ninguna línea de CÓDIGO de `_evaluar_forma_script/pytest/
        # notebook/cli_diagnostic` fue tocada. Chequeo estructural (no
        # dependiente de una wording exacta): ninguna línea quitada empieza
        # (tras strip) con una palabra clave de código Python.
        _PALABRAS_CLAVE_CODIGO = ("if ", "return", "def ", "for ", "while ", "raise ", "elif ", "else:")
        for linea in quitadas:
            contenido = linea.strip()
            self.assertFalse(
                contenido.startswith(_PALABRAS_CLAVE_CODIGO),
                f"línea quitada parece código, no comentario/docstring: {linea!r}",
            )
        self.assertLessEqual(len(quitadas), 3, f"más líneas quitadas de las esperadas: {quitadas}")

    def test_allowlist_py_agrega_funcion_aislada_sin_tocar_las_4_existentes(self):
        if not self.diff_allowlist:
            self.skipTest("sin diff contra HEAD (working tree ya coincide, ver setUpClass)")
        agregadas = "\n".join(_lineas_agregadas(self.diff_allowlist))
        self.assertIn("_evaluar_forma_dependency_install", agregadas)
        self.assertIn("dependency_install", agregadas)
        # Ninguna de las 4 funciones de forma existentes aparece REDEFINIDA
        # (el diff solo debe AGREGAR código nuevo, nunca reabrir el cuerpo de
        # `_evaluar_forma_script`/`_evaluar_forma_pytest`/
        # `_evaluar_forma_notebook`/`_evaluar_forma_cli_diagnostic`).
        for nombre_forma in (
            "def _evaluar_forma_script(",
            "def _evaluar_forma_pytest(",
            "def _evaluar_forma_notebook(",
            "def _evaluar_forma_cli_diagnostic(",
        ):
            self.assertNotIn(nombre_forma, agregadas)

    def test_runtime_py_solo_agrega_la_rama_de_despacho_sin_quitar_nada(self):
        if not self.diff_runtime:
            self.skipTest("sin diff contra HEAD (working tree ya coincide, ver setUpClass)")
        quitadas = _lineas_quitadas(self.diff_runtime)
        self.assertEqual(quitadas, [], f"runtime.py no debería tener ninguna línea quitada: {quitadas}")
        agregadas = "\n".join(_lineas_agregadas(self.diff_runtime))
        self.assertIn('elif request.command_form == "dependency_install":', agregadas)
        self.assertIn("scripts.ejecutar_script(request, repo_root)", agregadas)


if __name__ == "__main__":
    unittest.main()
