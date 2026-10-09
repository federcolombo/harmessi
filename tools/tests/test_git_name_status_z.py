"""Tests de `repo.parse_name_status_z` y `repo.diff_name_status`.

Los tests con git real fuerzan `core.quotepath` en true y en false: el
resultado no debe depender de esa configuración.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from unittest import mock  # noqa: E402

from tools.dsguard import repo as repo_mod  # noqa: E402
from tools.dsguard.repo import (  # noqa: E402
    GitCommandError,
    GitOutputError,
    diff_name_status,
    parse_name_status_z,
)


class ParseNameStatusZTests(unittest.TestCase):
    def test_vacia(self):
        self.assertEqual(parse_name_status_z(""), [])

    def test_a_m_d(self):
        salida = "A\0a.txt\0M\0b.txt\0D\0c.txt\0"
        self.assertEqual(
            parse_name_status_z(salida),
            [("A", "a.txt", None), ("M", "b.txt", None), ("D", "c.txt", None)],
        )

    def test_rename_tres_campos(self):
        self.assertEqual(
            parse_name_status_z("R100\0vieja.txt\0nueva.txt\0"),
            [("R100", "nueva.txt", "vieja.txt")],
        )

    def test_copia(self):
        self.assertEqual(
            parse_name_status_z("C075\0origen.txt\0destino.txt\0"),
            [("C075", "destino.txt", "origen.txt")],
        )

    def test_mezcla_rename_y_otros(self):
        salida = "M\0x.txt\0R090\0a\0b\0D\0y.txt\0"
        self.assertEqual(
            parse_name_status_z(salida),
            [("M", "x.txt", None), ("R090", "b", "a"), ("D", "y.txt", None)],
        )

    def test_espacios(self):
        self.assertEqual(
            parse_name_status_z("A\0mi archivo.txt\0"),
            [("A", "mi archivo.txt", None)],
        )

    def test_tab_y_salto_de_linea_en_nombre(self):
        self.assertEqual(
            parse_name_status_z("A\0a\tb.txt\0M\0c\nd.txt\0"),
            [("A", "a\tb.txt", None), ("M", "c\nd.txt", None)],
        )

    def test_unicode(self):
        self.assertEqual(
            parse_name_status_z("R100\0datos_área/a.txt\0tamaño.txt\0"),
            [("R100", "tamaño.txt", "datos_área/a.txt")],
        )

    def test_cero_final_ausente_y_presente(self):
        con = parse_name_status_z("M\0a.txt\0")
        sin = parse_name_status_z("M\0a.txt")
        self.assertEqual(con, sin)
        self.assertEqual(con, [("M", "a.txt", None)])
        self.assertEqual(
            parse_name_status_z("R100\0a\0b"), [("R100", "b", "a")]
        )

    def test_estado_desconocido(self):
        with self.assertRaises(GitOutputError):
            parse_name_status_z("Z\0a.txt\0")

    def test_estado_vacio(self):
        with self.assertRaises(GitOutputError):
            parse_name_status_z("\0a.txt\0")

    def test_truncado(self):
        with self.assertRaises(GitOutputError):
            parse_name_status_z("M\0")
        with self.assertRaises(GitOutputError):
            parse_name_status_z("M")
        with self.assertRaises(GitOutputError):
            parse_name_status_z("A\0a.txt\0M\0")

    def test_rename_con_un_solo_campo(self):
        with self.assertRaises(GitOutputError):
            parse_name_status_z("R100\0solo.txt\0")
        with self.assertRaises(GitOutputError):
            parse_name_status_z("C100\0solo.txt")

    def test_ruta_vacia(self):
        with self.assertRaises(GitOutputError):
            parse_name_status_z("M\0\0")
        with self.assertRaises(GitOutputError):
            parse_name_status_z("R100\0a\0\0")

    def test_estado_validado_completo(self):
        for malo in ("Makefile\0x\0", "Rx\0a\0b\0", "README.md\0x\0", "R\0a\0b\0"):
            with self.subTest(salida=malo):
                with self.assertRaises(GitOutputError):
                    parse_name_status_z(malo)
        self.assertEqual(
            parse_name_status_z("R100\0a\0b\0"), [("R100", "b", "a")]
        )
        self.assertEqual(
            parse_name_status_z("C75\0a\0b\0"), [("C75", "b", "a")]
        )

    def test_comando_fallido_vs_salida_malformada(self):
        class _Res:
            returncode = 0
            stderr = ""
            stdout = "Z\0a.txt\0"

        with mock.patch.object(repo_mod, "_git", return_value=_Res()):
            with self.assertRaises(GitOutputError) as ctx:
                diff_name_status(Path("."))
        self.assertNotIsInstance(ctx.exception, GitCommandError)

    def test_sin_resultados_parciales(self):
        # Un registro válido seguido de uno malformado: error, no lista parcial.
        with self.assertRaises(GitOutputError):
            parse_name_status_z("A\0ok.txt\0Z\0mal.txt\0")


def _run(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=str(repo), check=True, capture_output=True
    )


def _escribir(repo: Path, rel: str, contenido: str) -> None:
    destino = repo / rel
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8", newline="\n")


def _contenido_largo(semilla: str) -> str:
    return "".join(f"{semilla} linea {n} con contenido suficiente\n" for n in range(40))


class DiffNameStatusGitRealTests(unittest.TestCase):
    QUOTEPATH = ("true", "false")

    def _repo(self, quotepath: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name)
        _run(repo, "init", "-q")
        _run(repo, "config", "user.email", "t@example.com")
        _run(repo, "config", "user.name", "Test")
        _run(repo, "config", "core.quotepath", quotepath)
        _run(repo, "config", "commit.gpgsign", "false")
        return repo

    def _commit_base(self, repo: Path) -> None:
        _escribir(repo, "base.txt", "base\n")
        _run(repo, "add", "-A")
        _run(repo, "commit", "-q", "-m", "base")

    def test_altas_unicode_y_espacios(self):
        rutas = [
            "tamaño.txt",
            "información.md",
            "datos_área/ficha.txt",
            "mi archivo.txt",
            "plain.txt",
        ]
        for qp in self.QUOTEPATH:
            with self.subTest(quotepath=qp):
                repo = self._repo(qp)
                self._commit_base(repo)
                for r in rutas:
                    _escribir(repo, r, f"contenido de {r}\n")
                _run(repo, "add", "-A")
                res = diff_name_status(repo, "--staged")
                self.assertEqual(
                    sorted(res), sorted((("A", r, None) for r in rutas))
                )

    def test_rename_unicode_a_unicode(self):
        for qp in self.QUOTEPATH:
            with self.subTest(quotepath=qp):
                repo = self._repo(qp)
                _escribir(repo, "datos_área/información.txt", _contenido_largo("x"))
                _run(repo, "add", "-A")
                _run(repo, "commit", "-q", "-m", "base")
                (repo / "datos_área" / "información.txt").rename(
                    repo / "datos_área" / "tamaño.txt"
                )
                _run(repo, "add", "-A")
                res = diff_name_status(repo, "--staged")
                self.assertEqual(
                    res,
                    [("R100", "datos_área/tamaño.txt", "datos_área/información.txt")],
                )

    def test_modificado_y_borrado(self):
        for qp in self.QUOTEPATH:
            with self.subTest(quotepath=qp):
                repo = self._repo(qp)
                _escribir(repo, "tamaño.txt", "uno\n")
                _escribir(repo, "información.md", "dos\n")
                _escribir(repo, "ascii.txt", "tres\n")
                _run(repo, "add", "-A")
                _run(repo, "commit", "-q", "-m", "base")
                _escribir(repo, "tamaño.txt", "uno modificado\n")
                (repo / "información.md").unlink()
                _escribir(repo, "ascii.txt", "tres modificado\n")
                _run(repo, "add", "-A")
                res = diff_name_status(repo, "--staged")
                self.assertEqual(
                    sorted(res),
                    sorted(
                        [
                            ("M", "tamaño.txt", None),
                            ("D", "información.md", None),
                            ("M", "ascii.txt", None),
                        ]
                    ),
                )

    def test_regresion_ascii(self):
        for qp in self.QUOTEPATH:
            with self.subTest(quotepath=qp):
                repo = self._repo(qp)
                self._commit_base(repo)
                _escribir(repo, "src/nuevo.py", "x = 1\n")
                _run(repo, "add", "-A")
                self.assertEqual(
                    diff_name_status(repo, "--staged"),
                    [("A", "src/nuevo.py", None)],
                )

    def test_contra_ref_head(self):
        for qp in self.QUOTEPATH:
            with self.subTest(quotepath=qp):
                repo = self._repo(qp)
                self._commit_base(repo)
                _escribir(repo, "tamaño.txt", "x\n")
                _run(repo, "add", "-A")
                self.assertEqual(
                    diff_name_status(repo, "HEAD"), [("A", "tamaño.txt", None)]
                )

    def test_ref_invalida(self):
        for qp in self.QUOTEPATH:
            with self.subTest(quotepath=qp):
                repo = self._repo(qp)
                self._commit_base(repo)
                with self.assertRaises(GitCommandError) as ctx:
                    diff_name_status(repo, "ref_que_no_existe_xyz")
                self.assertIsInstance(ctx.exception, GitOutputError)

    def test_sin_cambios(self):
        for qp in self.QUOTEPATH:
            with self.subTest(quotepath=qp):
                repo = self._repo(qp)
                self._commit_base(repo)
                self.assertEqual(diff_name_status(repo, "--staged"), [])


if __name__ == "__main__":
    unittest.main()
