"""Consumidores de rutas Git con Unicode (change 20261009-unicode-git-paths-corrective):
`dsguard.scope` y `dsimpact.git_source` deben ver rutas Unicode/con espacios intactas tanto con
`core.quotepath=true` como con `false` (parseo `-z`), y una salida de git ilegible debe ser
fail-closed (`ALCANCE-GIT-ILEGIBLE`), nunca «sin archivos».

Repos git temporales reales; nunca usa este repositorio como fixture.
"""
from __future__ import annotations

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

from tools.dsguard import repo as repo_mod  # noqa: E402
from tools.dsguard import scope  # noqa: E402

# `dsimpact.git_source` importa `dsguard.repo` (sin prefijo `tools.`): es otro objeto módulo y otras
# clases de excepción que `tools.dsguard.repo`. Por eso, en los tests de git_source se parchea y se
# lanza SIEMPRE vía `git_source.repo_mod`; en los de scope, vía `tools.dsguard.repo` (el mismo objeto
# que scope importa con `from . import repo`).
from dsimpact import git_source  # noqa: E402

QUOTEPATH = ("true", "false")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), check=True, capture_output=True,
        text=True, encoding="utf-8",
    )


def _crear_repo(quotepath: str) -> Path:
    repo = Path(tempfile.mkdtemp(prefix="dsguard_unicode_test_"))
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "tag.gpgsign", "false")
    _git(repo, "config", "core.quotepath", quotepath)
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
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _control(baseline, rutas) -> dict:
    control = {"schema_version": 1, "alcance": {"rutas_autorizadas": rutas}}
    if baseline is not None:
        control["baseline"] = {"commit": baseline}
    return control


def _codigos_ubic(findings) -> set:
    return {(f.codigo, f.ubicacion) for f in findings}


class TestScopeUnicode(unittest.TestCase):
    def _con_repo(self, quotepath):
        repo = _crear_repo(quotepath)
        self.addCleanup(shutil.rmtree, repo, True)
        return repo

    def test_unicode_autorizado_por_glob(self):
        for qp in QUOTEPATH:
            with self.subTest(quotepath=qp):
                repo = self._con_repo(qp)
                base = _head(repo)
                _escribir(repo, "referencias/tamaño_iqr/f.txt")
                _commit(repo)
                hall = scope.evaluar_alcance(
                    repo, _control(base, ["referencias/tamaño_iqr/**"]))
                self.assertEqual(hall, [])

    def test_unicode_no_autorizado(self):
        for qp in QUOTEPATH:
            with self.subTest(quotepath=qp):
                repo = self._con_repo(qp)
                base = _head(repo)
                _escribir(repo, "referencias/tamaño_iqr/f.txt")
                _commit(repo)
                hall = scope.evaluar_alcance(repo, _control(base, ["otra/**"]))
                self.assertEqual(
                    _codigos_ubic(hall),
                    {("ALCANCE-RUTA", "referencias/tamaño_iqr/f.txt")},
                )

    def test_nombres_variados_en_archivos_tocados(self):
        nombres = ["información.md", "datos_área/ficha.txt", "mi archivo.txt"]
        for qp in QUOTEPATH:
            with self.subTest(quotepath=qp):
                repo = self._con_repo(qp)
                base = _head(repo)
                for n in nombres:
                    _escribir(repo, n)
                _commit(repo)
                self.assertEqual(
                    sorted(scope.archivos_tocados_desde_baseline(repo, base)),
                    sorted(nombres),
                )
                hall = scope.evaluar_alcance(repo, _control(base, ["nada/**"]))
                self.assertEqual(
                    _codigos_ubic(hall), {("ALCANCE-RUTA", n) for n in nombres})
                hall_ok = scope.evaluar_alcance(
                    repo, _control(base, ["información.md", "datos_área/*", "mi archivo.txt"]))
                self.assertEqual(hall_ok, [])

    def test_rename_unicode_a_unicode_reporta_lado_nuevo(self):
        for qp in QUOTEPATH:
            with self.subTest(quotepath=qp):
                repo = self._con_repo(qp)
                _escribir(repo, "datos_área/viejo_ñandú.txt", "mismo contenido largo\n" * 5)
                _commit(repo)
                base = _head(repo)
                (repo / "datos_área" / "viejo_ñandú.txt").rename(
                    repo / "datos_área" / "nuevo_información.txt")
                _commit(repo)
                # v0.11 (git-scope-fail-closed): rename -> ambas rutas (nueva y vieja).
                self.assertEqual(
                    scope.archivos_tocados_desde_baseline(repo, base),
                    ["datos_área/nuevo_información.txt", "datos_área/viejo_ñandú.txt"],
                )

    def test_salida_malformada_es_fail_closed(self):
        original = repo_mod._git

        def falso(repo_root, *args):
            if args and args[0] == "diff":
                return SimpleNamespace(returncode=0, stdout="M\0", stderr="")
            return original(repo_root, *args)

        for qp in QUOTEPATH:
            with self.subTest(quotepath=qp):
                repo = self._con_repo(qp)
                base = _head(repo)
                _escribir(repo, "información.md")
                _commit(repo)
                with mock.patch.object(repo_mod, "_git", side_effect=falso):
                    hall = scope.evaluar_alcance(
                        repo, _control(base, ["información.md"]))
                    codigos = [f.codigo for f in hall]
                    self.assertIn("ALCANCE-GIT-ILEGIBLE", codigos)
                    with self.assertRaises(scope.GitIlegibleError):
                        scope.archivos_tocados_desde_baseline(repo, base)

    def test_parser_que_lanza_git_output_error_es_fail_closed(self):
        repo = self._con_repo("true")
        base = _head(repo)
        with mock.patch.object(
            repo_mod, "parse_name_status_z",
            side_effect=repo_mod.GitOutputError("basura"),
        ):
            hall = scope.evaluar_alcance(repo, _control(base, ["**"]))
        self.assertEqual([f.codigo for f in hall], ["ALCANCE-GIT-ILEGIBLE"])

    def test_ruta_con_u_fffd_no_coincide_con_alcance_exacto(self):
        # Contrato: `_git` decodifica UTF-8 con errors="replace"; un byte inválido produce U+FFFD y la
        # ruta resultante NO coincide con ningún alcance de ruta exacta (falla cerrado: se informa
        # como fuera de alcance, nunca se adivina el nombre original).
        original = repo_mod._git
        ruta_rota = "datos_�/ficha.txt"

        def falso(repo_root, *args):
            if args and args[0] == "diff":
                return SimpleNamespace(returncode=0, stdout=f"M\0{ruta_rota}\0", stderr="")
            return original(repo_root, *args)

        repo = self._con_repo("true")
        base = _head(repo)
        with mock.patch.object(repo_mod, "_git", side_effect=falso):
            hall = scope.evaluar_alcance(repo, _control(base, ["datos_á/ficha.txt"]))
        self.assertEqual(_codigos_ubic(hall), {("ALCANCE-RUTA", ruta_rota)})

    # v0.11 (git-scope-fail-closed): antes estos casos degradaban a [] (fail-open); ahora propagan.
    def test_returncode_distinto_de_cero_con_stdout_basura_propaga(self):
        repo = self._con_repo("true")
        base = _head(repo)
        falso = SimpleNamespace(returncode=128, stdout="basura\0\0M", stderr="fatal")
        with mock.patch.object(repo_mod, "_git", return_value=falso):
            with self.assertRaises(repo_mod.GitCommandError):
                scope.archivos_tocados_desde_baseline(repo, base)

    def test_excepcion_de_ejecucion_propaga_y_evaluar_alcance_la_traduce(self):
        repo = self._con_repo("true")
        base = _head(repo)
        with mock.patch.object(repo_mod, "_git", side_effect=RuntimeError("git no disponible")):
            with self.assertRaises(RuntimeError):
                scope.archivos_tocados_desde_baseline(repo, base)
            hall = scope.evaluar_alcance(repo, _control(base, ["**"]))
        self.assertEqual([f.codigo for f in hall], ["ALCANCE-GIT-ILEGIBLE"])

    def test_scope_usa_diff_name_status(self):
        repo = self._con_repo("true")
        with mock.patch.object(
            repo_mod, "diff_name_status",
            return_value=[("R100", "a/nuevo_ñ.txt", "a/viejo.txt"), ("M", "b.txt", None)],
        ) as m:
            resultado = scope.archivos_tocados_desde_baseline(repo, "abc123")
        m.assert_called_once_with(repo, "abc123")
        self.assertEqual(resultado, ["a/nuevo_ñ.txt", "a/viejo.txt", "b.txt"])

    def test_ref_invalida_es_fail_closed(self):
        # v0.11: antes degradaba a [] (fail-open); ahora ALCANCE-GIT-ILEGIBLE.
        repo = self._con_repo("true")
        with self.assertRaises(repo_mod.GitCommandError):
            scope.archivos_tocados_desde_baseline(repo, "0" * 40)
        hall = scope.evaluar_alcance(repo, _control("0" * 40, ["**"]))
        self.assertEqual([f.codigo for f in hall], ["ALCANCE-GIT-ILEGIBLE"])

    def test_baseline_none_sin_hallazgos(self):
        for qp in QUOTEPATH:
            with self.subTest(quotepath=qp):
                repo = self._con_repo(qp)
                self.assertEqual(scope.archivos_tocados_desde_baseline(repo, None), [])
                self.assertEqual(scope.evaluar_alcance(repo, _control(None, ["**"])), [])

    def test_ascii_sin_regresion(self):
        for qp in QUOTEPATH:
            with self.subTest(quotepath=qp):
                repo = self._con_repo(qp)
                base = _head(repo)
                _escribir(repo, "src/a.py")
                _escribir(repo, "fuera.py")
                _commit(repo)
                hall = scope.evaluar_alcance(repo, _control(base, ["src/*"]))
                self.assertEqual(_codigos_ubic(hall), {("ALCANCE-RUTA", "fuera.py")})


class TestListarCambiosUnicode(unittest.TestCase):
    def _con_repo(self, quotepath):
        repo = _crear_repo(quotepath)
        self.addCleanup(shutil.rmtree, repo, True)
        return repo

    def test_estados_y_rutas_unicode(self):
        for qp in QUOTEPATH:
            with self.subTest(quotepath=qp):
                repo = self._con_repo(qp)
                _escribir(repo, "datos_área/viejo_ñandú.txt", "contenido repetido\n" * 8)
                _escribir(repo, "tamaño.txt", "uno\n")
                _escribir(repo, "borrar_información.txt", "adiós\n")
                _commit(repo)
                base = _head(repo)
                (repo / "datos_área" / "viejo_ñandú.txt").rename(
                    repo / "datos_área" / "nuevo_ñandú.txt")
                _escribir(repo, "tamaño.txt", "dos\n")
                (repo / "borrar_información.txt").unlink()
                _escribir(repo, "mi archivo nuevo.txt")
                _git(repo, "add", "-A")

                for kwargs in ({"since": base, "staged": False},
                               {"since": None, "staged": True}):
                    cambios = {c.path: c for c in git_source.listar_cambios(repo, **kwargs)}
                    self.assertEqual(
                        set(cambios),
                        {"datos_área/nuevo_ñandú.txt", "tamaño.txt",
                         "borrar_información.txt", "mi archivo nuevo.txt"},
                    )
                    ren = cambios["datos_área/nuevo_ñandú.txt"]
                    self.assertEqual(ren.status, git_source.STATUS_RENAMED)
                    self.assertEqual(ren.old_path, "datos_área/viejo_ñandú.txt")
                    self.assertEqual(cambios["tamaño.txt"].status, git_source.STATUS_MODIFIED)
                    self.assertEqual(
                        cambios["borrar_información.txt"].status, git_source.STATUS_DELETED)
                    self.assertEqual(
                        cambios["mi archivo nuevo.txt"].status, git_source.STATUS_ADDED)

    def test_git_output_error_se_traduce_a_git_source_error(self):
        repo = self._con_repo("true")
        rm = git_source.repo_mod
        with mock.patch.object(
            rm, "diff_name_status", side_effect=rm.GitOutputError("falló feo"),
        ):
            with self.assertRaises(git_source.GitSourceError) as ctx:
                git_source.listar_cambios(repo, since="HEAD", staged=False)
        self.assertIn("falló feo", str(ctx.exception))

    def test_git_command_error_mensaje_limpio_sin_prefijo(self):
        repo = self._con_repo("true")
        rm = git_source.repo_mod
        with mock.patch.object(
            rm, "diff_name_status", side_effect=rm.GitCommandError("stderr de git"),
        ):
            with self.assertRaises(git_source.GitSourceError) as ctx:
                git_source.listar_cambios(repo, since="HEAD", staged=False)
        self.assertEqual(str(ctx.exception), "stderr de git")

    def test_ref_invalida_lanza_git_source_error(self):
        repo = self._con_repo("true")
        with self.assertRaises(git_source.GitSourceError):
            git_source.listar_cambios(repo, since="no-existe-ref", staged=False)


if __name__ == "__main__":
    unittest.main()
