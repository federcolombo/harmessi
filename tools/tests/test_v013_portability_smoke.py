"""v0.13 R11: smoke de portabilidad ejercitado en el host real.

Solo prueba lo que se ejecuta aquí; no afirma nada sobre otras plataformas
(ver `docs/portability.md`). Todo sintético: repos y directorios temporales.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
for _p in (str(RAIZ), str(RAIZ / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dsguard import repo as repo_mod  # noqa: E402
from dsimpact import scan as scan_mod  # noqa: E402
from tools.harmessi_bench import runmanifest  # noqa: E402
from tools.harmessi_bench.suite import load_suite_y_casos  # noqa: E402

NOMBRE_UNICODE = "pruéba ñandú con espacios"  # tilde y ñ, espacios


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


def _repo_temporal(base: Path) -> Path:
    repo = base / NOMBRE_UNICODE
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Usuario Sintetico")
    _git(repo, "config", "user.email", "sintetico@example.com")
    _git(repo, "config", "commit.gpgsign", "false")
    return repo


def _commit_todo(repo: Path, mensaje: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", mensaje)


class TestDirectoriosEspaciosUnicode(unittest.TestCase):
    def test_roundtrip_con_espacios_y_unicode(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / NOMBRE_UNICODE
            d.mkdir()
            f = d / "archivo áñ.txt"
            f.write_text("contenido ñ\n", encoding="utf-8")
            self.assertEqual(f.read_text(encoding="utf-8"), "contenido ñ\n")
            self.assertIn(f.name, [p.name for p in d.iterdir()])

    def test_normalizacion_nfc_nfd_cada_nombre_funciona(self):
        nfc = unicodedata.normalize("NFC", "cañón")
        nfd = unicodedata.normalize("NFD", nfc)
        self.assertNotEqual(nfc, nfd)
        with tempfile.TemporaryDirectory() as tmp:
            contenidos = {}
            for etiqueta, nombre in (("nfc", nfc), ("nfd", nfd)):
                d = Path(tmp) / etiqueta / nombre
                d.mkdir(parents=True)
                (d / "x.txt").write_text("igual\n", encoding="utf-8")
                contenidos[etiqueta] = (d / "x.txt").read_text(encoding="utf-8")
            self.assertEqual(contenidos["nfc"], contenidos["nfd"])


class TestFinalesDeLinea(unittest.TestCase):
    CASOS = [
        {"scenario_id": "a", "prompt": "uno\ndos ñ", "category": "c",
         "expected": {"tipo": "exact", "valor": "x"}},
        {"scenario_id": "b", "prompt": "otro", "category": "c",
         "expected": {"tipo": "exact", "valor": "y"}},
    ]

    def _escribir_suite(self, directorio: Path, eol: str) -> Path:
        directorio.mkdir(parents=True)
        casos = json.dumps({"case_contract_version": 1, "escenarios": self.CASOS}, indent=2, ensure_ascii=False)
        manifest = json.dumps(
            {"suite_contract_version": 1, "suite_id": "s", "suite_version": 1,
             "cases_file": "casos.json", "case_ids": ["a", "b"]}, indent=2)
        # Bytes explícitos: el modo texto traduciría los finales de línea según el SO.
        (directorio / "casos.json").write_bytes(casos.replace("\n", eol).encode("utf-8"))
        ruta = directorio / "x.suite.json"
        ruta.write_bytes(manifest.replace("\n", eol).encode("utf-8"))
        return ruta

    def test_suite_hash_invariante_crlf_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            suite_lf, _ = load_suite_y_casos(self._escribir_suite(raiz / "lf", "\n"))
            suite_crlf, _ = load_suite_y_casos(self._escribir_suite(raiz / "crlf", "\r\n"))
        self.assertEqual(suite_lf.suite_hash, suite_crlf.suite_hash)

    def test_hashes_de_identidad_invariantes_crlf_lf(self):
        ruta_skill = Path(*runmanifest.DIR_SKILLS.split("/")) if hasattr(runmanifest, "DIR_SKILLS") else None
        if ruta_skill is None:
            self.skipTest("runmanifest no expone DIR_SKILLS")
        with tempfile.TemporaryDirectory() as tmp:
            hashes = []
            for etiqueta, eol in (("lf", "\n"), ("crlf", "\r\n")):
                raiz = Path(tmp) / etiqueta
                destino = raiz / ruta_skill
                destino.mkdir(parents=True)
                (destino / "alfa.md").write_bytes(f"---\nname: alfa\n---\ncuerpo{eol}linea{eol}".encode("utf-8"))
                hashes.append((runmanifest.hash_skills(raiz), runmanifest.hash_superficies(raiz)))
        self.assertEqual(hashes[0], hashes[1])
        self.assertIn("alfa", hashes[0][0])


class TestTempYSubprocess(unittest.TestCase):
    def test_tempdir_existe_y_es_escribible(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "t.bin"
            p.write_bytes(b"\x00\x01")
            self.assertEqual(p.read_bytes(), b"\x00\x01")
        self.assertFalse(Path(tmp).exists())

    def test_subprocess_salida_unicode_como_bytes(self):
        codigo = "import sys; sys.stdout.buffer.write('ca\\u00f1\\u00f3n'.encode('utf-8'))"
        r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, check=True)
        self.assertEqual(r.stdout.decode("utf-8"), "cañón")

    def test_subprocess_con_argumento_con_espacios(self):
        r = subprocess.run(
            [sys.executable, "-c", "import sys; print(sys.argv[1])", "dos palabras ñ"],
            capture_output=True, check=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(r.stdout.decode("utf-8").strip(), "dos palabras ñ")


class TestGitRepoTemporal(unittest.TestCase):
    def test_commit_head_limpio_y_lectura(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo_temporal(Path(tmp))
            nombre = "canción ñ.py"
            (repo / nombre).write_text("x = 1\n", encoding="utf-8")
            _commit_todo(repo, "inicial")
            commit, _rama = repo_mod.get_head(repo)
            self.assertEqual(len(commit), 40)
            self.assertTrue(repo_mod.is_tree_clean(repo))
            self.assertEqual(repo_mod.leer_en_commit(repo, commit, nombre), b"x = 1\n")
            (repo / nombre).write_text("x = 2\n", encoding="utf-8")
            self.assertFalse(repo_mod.is_tree_clean(repo))

    def test_dsimpact_sobre_cambio_real_con_ruta_unicode(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo_temporal(Path(tmp))
            (repo / "modulo ñ.py").write_text("def calcular(x):\n    return x\n", encoding="utf-8")
            (repo / "consumidor.py").write_text(
                "from modulo import calcular\ncalcular(1)\n", encoding="utf-8")
            _commit_todo(repo, "inicial")
            (repo / "modulo ñ.py").write_text(
                "def calcular(x, y):\n    return x + y\n", encoding="utf-8")
            resultado = scan_mod.ejecutar_scan(repo, "HEAD", False)
            self.assertEqual([c["path"] for c in resultado["changed"]], ["modulo ñ.py"])
            self.assertEqual(resultado["changed"][0]["status"], "modified")


class TestSymlink(unittest.TestCase):
    def test_symlink_a_directorio_si_el_so_lo_permite(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "destino con espacios"
            destino.mkdir()
            (destino / "a.txt").write_text("a\n", encoding="utf-8")
            enlace = Path(tmp) / "enlace"
            try:
                os.symlink(str(destino), str(enlace), target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink no disponible en este host/privilegios: {type(exc).__name__}")
            self.assertEqual((enlace / "a.txt").read_text(encoding="utf-8"), "a\n")
            self.assertTrue(enlace.is_symlink())


if __name__ == "__main__":
    unittest.main()
