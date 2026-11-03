"""Change 20261016-v011-git-scope-fail-closed: un fallo de Git (comando, ref inválida, Git ausente,
salida malformada) nunca se interpreta como estado limpio ni como «sin archivos tocados».

Repos temporales reales (`git init`); nunca usa este repositorio como fixture.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO_ORIGEN = Path(__file__).resolve().parents[2]
for _p in (REPO_ORIGEN, REPO_ORIGEN / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from tools.dsguard import mlops_foundations  # noqa: E402
from tools.dsguard import notebooks  # noqa: E402
from tools.dsguard import repo as repo_mod  # noqa: E402
from tools.dsguard import scope  # noqa: E402

CONTENIDO_LARGO = "linea de contenido repetido para similitud\n" * 20


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(repo), check=True, capture_output=True,
        text=True, encoding="utf-8",
    ).stdout


def _crear_repo() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="dsguard_failclosed_"))
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "inicial")
    return repo


def _escribir(repo: Path, rel: str, texto: str = "contenido\n") -> None:
    ruta = repo / rel
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")


def _commit(repo: Path, msg: str = "cambio") -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").strip()


def _control(baseline, rutas) -> dict:
    control = {"schema_version": 1, "alcance": {"rutas_autorizadas": rutas}}
    if baseline is not None:
        control["baseline"] = {"commit": baseline}
    return control


def _codigos_ubic(findings) -> set:
    return {(f.codigo, f.ubicacion) for f in findings}


class _BaseRepo(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo()
        self.addCleanup(shutil.rmtree, self.repo, True)

    def _corromper(self):
        # GIT_CEILING_DIRECTORIES evita que git suba a un repo padre y «rescate» el cwd corrupto.
        parche = mock.patch.dict(
            os.environ, {"GIT_CEILING_DIRECTORIES": str(self.repo.parent)}
        )
        parche.start()
        self.addCleanup(parche.stop)
        (self.repo / ".git" / "HEAD").write_text("basura que no es una ref\n", encoding="utf-8")


class TestFalloDeComando(_BaseRepo):
    def test_funciones_publicas_lanzan_git_command_error(self):
        self._corromper()
        for nombre in ("list_dirty_files", "get_head", "diff_check", "is_tree_clean"):
            with self.subTest(funcion=nombre):
                with self.assertRaises(repo_mod.GitCommandError):
                    getattr(repo_mod, nombre)(self.repo)

    def test_files_out_of_scope_hereda_el_error(self):
        self._corromper()
        with self.assertRaises(repo_mod.GitCommandError):
            repo_mod.files_out_of_scope(self.repo, ["**"])

    def test_baseline_con_ref_inexistente_propaga(self):
        with self.assertRaises(repo_mod.GitCommandError):
            scope.archivos_tocados_desde_baseline(self.repo, "0" * 40)

    def test_baseline_vacio_o_none_devuelve_vacio(self):
        self.assertEqual(scope.archivos_tocados_desde_baseline(self.repo, None), [])
        self.assertEqual(scope.archivos_tocados_desde_baseline(self.repo, ""), [])

    def test_evaluar_alcance_un_solo_hallazgo_si_ambos_fallan(self):
        base = _head(self.repo)
        self._corromper()
        hall = scope.evaluar_alcance(self.repo, _control(base, ["**"]))
        self.assertEqual([f.codigo for f in hall], ["ALCANCE-GIT-ILEGIBLE"])

    def test_evaluar_alcance_ref_invalida_sigue_emitiendo_alcance_ruta(self):
        _escribir(self.repo, "fuera.py")
        hall = scope.evaluar_alcance(self.repo, _control("0" * 40, ["base.txt"]))
        self.assertEqual(
            _codigos_ubic(hall),
            {("ALCANCE-GIT-ILEGIBLE", None), ("ALCANCE-RUTA", "fuera.py")},
        )
        self.assertEqual(len([f for f in hall if f.codigo == "ALCANCE-GIT-ILEGIBLE"]), 1)


class TestGitAusente(_BaseRepo):
    def test_git_ausente_es_runtime_error(self):
        with mock.patch.object(subprocess, "run", side_effect=FileNotFoundError("git")):
            with self.assertRaises(RuntimeError):
                repo_mod.list_dirty_files(self.repo)
            with self.assertRaises(RuntimeError):
                repo_mod.get_head(self.repo)

    def test_evaluar_alcance_con_git_ausente_no_lanza(self):
        with mock.patch.object(subprocess, "run", side_effect=FileNotFoundError("git")):
            hall = scope.evaluar_alcance(self.repo, _control("abc123", ["**"]))
        self.assertEqual([f.codigo for f in hall], ["ALCANCE-GIT-ILEGIBLE"])

    def test_mlops_reproducibilidad_no_es_limpio_si_git_falla(self):
        with mock.patch.object(mlops_foundations, "_na_por_stage", return_value=None):
            with mock.patch.object(
                mlops_foundations.repo, "get_head", side_effect=RuntimeError("git no disponible")
            ):
                resultado = mlops_foundations.check_reproducibilidad(self.repo, "experiment")
        self.assertEqual(len(resultado), 1)
        self.assertNotEqual(resultado[0].status, "PASS")


class TestRutasYEstados(_BaseRepo):
    def test_unicode_y_espacios_autorizados_y_no_autorizados(self):
        base = _head(self.repo)
        _escribir(self.repo, "datos ñandú/mi archivo.txt")
        _escribir(self.repo, "otro área/fuera de scope.txt")
        _commit(self.repo)
        hall = scope.evaluar_alcance(self.repo, _control(base, ["datos ñandú/*"]))
        self.assertEqual(_codigos_ubic(hall), {("ALCANCE-RUTA", "otro área/fuera de scope.txt")})

    def test_regresion_ascii(self):
        base = _head(self.repo)
        _escribir(self.repo, "src/a.py")
        _escribir(self.repo, "fuera.py")
        _commit(self.repo)
        hall = scope.evaluar_alcance(self.repo, _control(base, ["src/*"]))
        self.assertEqual(_codigos_ubic(hall), {("ALCANCE-RUTA", "fuera.py")})

    def test_rename_autorizado_a_no_autorizado(self):
        # El destino está autorizado, el origen no: el origen (que desaparece) queda fuera.
        _escribir(self.repo, "src/a.py", CONTENIDO_LARGO)
        _commit(self.repo)
        base = _head(self.repo)
        (self.repo / "dst").mkdir(exist_ok=True)
        _git(self.repo, "mv", "src/a.py", "dst/a.py")
        _commit(self.repo)
        hall = scope.evaluar_alcance(self.repo, _control(base, ["dst/*"]))
        self.assertEqual(_codigos_ubic(hall), {("ALCANCE-RUTA", "src/a.py")})

    def test_rename_no_autorizado_a_autorizado(self):
        # El origen está autorizado, el destino no: el destino queda fuera.
        _escribir(self.repo, "src/a.py", CONTENIDO_LARGO)
        _commit(self.repo)
        base = _head(self.repo)
        (self.repo / "dst").mkdir(exist_ok=True)
        _git(self.repo, "mv", "src/a.py", "dst/a.py")
        _commit(self.repo)
        hall = scope.evaluar_alcance(self.repo, _control(base, ["src/*"]))
        self.assertEqual(_codigos_ubic(hall), {("ALCANCE-RUTA", "dst/a.py")})

    def test_rename_en_working_tree_devuelve_ambas_rutas(self):
        _escribir(self.repo, "src/a.py", CONTENIDO_LARGO)
        _commit(self.repo)
        (self.repo / "dst").mkdir(exist_ok=True)
        _git(self.repo, "mv", "src/a.py", "dst/a.py")
        self.assertEqual(sorted(repo_mod.list_dirty_files(self.repo)), ["dst/a.py", "src/a.py"])

    def _con_status(self, salida: str):
        falso = SimpleNamespace(returncode=0, stdout=salida, stderr="")
        return mock.patch.object(repo_mod, "_git", return_value=falso)

    def test_status_rename_sintetico_ambas_rutas(self):
        with self._con_status("R  nueva.txt\0vieja.txt\0 M otro.txt\0"):
            self.assertEqual(
                repo_mod.list_dirty_files(self.repo), ["vieja.txt", "nueva.txt", "otro.txt"])

    def test_status_copy_solo_destino(self):
        with self._con_status("C  copia.txt\0origen.txt\0"):
            self.assertEqual(repo_mod.list_dirty_files(self.repo), ["copia.txt"])

    def test_diff_copy_solo_destino_y_rename_ambas(self):
        entradas = [("C75", "copia.txt", "origen.txt"), ("R100", "n.txt", "v.txt")]
        with mock.patch.object(repo_mod, "diff_name_status", return_value=entradas):
            self.assertEqual(
                scope.archivos_tocados_desde_baseline(self.repo, "abc"),
                ["copia.txt", "n.txt", "v.txt"],
            )

    def test_salida_malformada_es_ilegible(self):
        base = _head(self.repo)
        original = repo_mod._git

        def falso(repo_root, *args):
            if args and args[0] == "diff":
                return SimpleNamespace(returncode=0, stdout="M\0", stderr="")
            return original(repo_root, *args)

        with mock.patch.object(repo_mod, "_git", side_effect=falso):
            with self.assertRaises(scope.GitIlegibleError):
                scope.archivos_tocados_desde_baseline(self.repo, base)
            hall = scope.evaluar_alcance(self.repo, _control(base, ["**"]))
        self.assertEqual([f.codigo for f in hall], ["ALCANCE-GIT-ILEGIBLE"])

    def test_cr_en_nombre_se_preserva(self):
        nombre = "a\rb.txt"
        try:
            (self.repo / nombre).write_text("x\n", encoding="utf-8")
        except (OSError, ValueError):
            self.skipTest("el sistema de archivos no admite \\r en nombres")
        self.assertIn(nombre, repo_mod.list_dirty_files(self.repo))


class TestBytesYArgs(_BaseRepo):
    def test_git_preserva_cr_en_la_salida(self):
        crudo = SimpleNamespace(args=["git"], returncode=0, stdout=b"a\rb\r\nc\0", stderr=b"")
        with mock.patch.object(repo_mod.subprocess, "run", return_value=crudo):
            resultado = repo_mod._git(self.repo, "status")
        self.assertEqual(resultado.stdout, "a\rb\r\nc\0")
        self.assertIsInstance(resultado.stdout, str)

    def test_oserror_se_traduce_a_runtime_error(self):
        with mock.patch.object(repo_mod.subprocess, "run", side_effect=PermissionError("x")):
            with self.assertRaises(RuntimeError):
                repo_mod._git(self.repo, "status")

    def test_diff_name_status_pasa_separador(self):
        falso = SimpleNamespace(returncode=0, stdout="", stderr="")
        for ref in ("abc123", "--staged"):
            with self.subTest(ref=ref):
                with mock.patch.object(repo_mod, "_git", return_value=falso) as m:
                    repo_mod.diff_name_status(self.repo, ref)
                self.assertEqual(tuple(m.call_args.args[-2:]), (ref, "--"))

    def test_evaluar_alcance_captura_oserror_y_valueerror(self):
        for exc in (OSError("x"), ValueError("y")):
            with self.subTest(exc=type(exc).__name__):
                with mock.patch.object(repo_mod, "list_dirty_files", side_effect=exc):
                    hall = scope.evaluar_alcance(self.repo, _control(None, ["**"]))
                self.assertEqual([f.codigo for f in hall], ["ALCANCE-GIT-ILEGIBLE"])


class TestStatusRCyMalformado(_BaseRepo):
    def _con_status(self, salida: str):
        falso = SimpleNamespace(returncode=0, stdout=salida, stderr="")
        return mock.patch.object(repo_mod, "_git", return_value=falso)

    def test_rename_en_columna_y(self):
        with self._con_status(" R nueva.txt\0vieja.txt\0"):
            self.assertEqual(repo_mod.list_dirty_files(self.repo), ["vieja.txt", "nueva.txt"])

    def test_rename_con_modificacion_en_y(self):
        with self._con_status("RM nueva.txt\0vieja.txt\0"):
            self.assertEqual(repo_mod.list_dirty_files(self.repo), ["vieja.txt", "nueva.txt"])

    def test_copy_en_columna_y_solo_destino(self):
        with self._con_status(" C copia.txt\0origen.txt\0"):
            self.assertEqual(repo_mod.list_dirty_files(self.repo), ["copia.txt"])

    def test_entrada_corta_es_git_output_error(self):
        for salida in ("M\0", "M \0", "??\0"):
            with self.subTest(salida=salida):
                with self._con_status(salida):
                    with self.assertRaises(repo_mod.GitOutputError):
                        repo_mod.list_dirty_files(self.repo)

    def test_rc_truncado_es_git_output_error(self):
        with self._con_status("R  nueva.txt\0"):
            with self.assertRaises(repo_mod.GitOutputError):
                repo_mod.list_dirty_files(self.repo)

    def test_evaluar_alcance_con_status_malformado_es_ilegible(self):
        with self._con_status("M\0"):
            hall = scope.evaluar_alcance(self.repo, _control(None, ["**"]))
        self.assertEqual([f.codigo for f in hall], ["ALCANCE-GIT-ILEGIBLE"])


class TestMlopsGit(_BaseRepo):
    def test_reproducibilidad_con_list_dirty_files_fallando(self):
        with mock.patch.object(mlops_foundations, "_na_por_stage", return_value=None):
            with mock.patch.object(
                mlops_foundations.repo, "list_dirty_files",
                side_effect=repo_mod.GitCommandError("status falló"),
            ):
                resultado = mlops_foundations.check_reproducibilidad(self.repo, "experiment")
        self.assertEqual(len(resultado), 1)
        self.assertNotEqual(resultado[0].status, "PASS")

    def test_versionado_con_get_head_fallando(self):
        with mock.patch.object(mlops_foundations, "_na_por_stage", return_value=None):
            with mock.patch.object(
                mlops_foundations.repo, "get_head",
                side_effect=repo_mod.GitCommandError("rev-parse falló"),
            ):
                resultado = mlops_foundations.check_versionado(self.repo, "experiment")
        self.assertEqual(len(resultado), 1)
        self.assertNotEqual(resultado[0].status, "PASS")


class TestObtenerRevision(_BaseRepo):
    def test_notebook_nuevo(self):
        self.assertEqual(
            notebooks.obtener_revision(self.repo, "HEAD", "nuevo.ipynb"), (False, None, True))

    def test_notebook_existente(self):
        _escribir(self.repo, "nb.ipynb", "{}\n")
        _commit(self.repo)
        self.assertEqual(
            notebooks.obtener_revision(self.repo, "HEAD", "nb.ipynb"), (True, "{}\n", True))

    def test_revision_desconocida(self):
        self.assertEqual(
            notebooks.obtener_revision(self.repo, "no-existe-ref", "nb.ipynb"),
            (False, None, False))

    def test_git_roto_propaga_git_command_error(self):
        self._corromper()
        with self.assertRaises(repo_mod.GitCommandError):
            notebooks.obtener_revision(self.repo, "HEAD", "nb.ipynb")

    def test_git_ausente_propaga_runtime_error(self):
        with mock.patch.object(repo_mod.subprocess, "run", side_effect=FileNotFoundError("git")):
            with self.assertRaises(RuntimeError):
                notebooks.obtener_revision(self.repo, "HEAD", "nb.ipynb")

    def test_show_falla_con_objeto_existente_no_es_nuevo(self):
        def falso(repo_root, *args):
            if args[0] == "show":
                return SimpleNamespace(returncode=128, stdout="", stderr="fatal")
            return SimpleNamespace(returncode=0, stdout="abc\n", stderr="")

        with mock.patch.object(repo_mod, "_git", side_effect=falso):
            with self.assertRaises(repo_mod.GitCommandError):
                notebooks.obtener_revision(self.repo, "HEAD", "nb.ipynb")


class TestRefs(_BaseRepo):
    def test_validar_ref_rechaza_vacia_y_guion(self):
        for ref in ("", "   ", "-x", "--output=/tmp/x", None):
            with self.subTest(ref=ref):
                with self.assertRaises(repo_mod.GitCommandError):
                    repo_mod.validar_ref(ref)
        self.assertEqual(repo_mod.validar_ref("HEAD"), "HEAD")

    def test_diff_name_status_rechaza_ref_con_guion(self):
        with self.assertRaises(repo_mod.GitCommandError):
            repo_mod.diff_name_status(self.repo, "--output=salida.txt")
        self.assertFalse((self.repo / "salida.txt").exists())

    def test_baseline_con_guion_es_ilegible(self):
        hall = scope.evaluar_alcance(self.repo, _control("--output=x", ["**"]))
        self.assertEqual([f.codigo for f in hall], ["ALCANCE-GIT-ILEGIBLE"])

    def test_diff_name_status_usa_separador(self):
        base = _head(self.repo)
        _escribir(self.repo, "nuevo.txt")
        _commit(self.repo)
        self.assertEqual(repo_mod.diff_name_status(self.repo, base), [("A", "nuevo.txt", None)])

    def test_notebooks_obtener_revision_ref_con_guion(self):
        self.assertEqual(
            notebooks.obtener_revision(self.repo, "-x", "a.ipynb"), (False, None, False))


if __name__ == "__main__":
    unittest.main()
