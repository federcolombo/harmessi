"""Tests de la primitive de hash managed (`tools/ds_init/managed_hash.py`).

Todos los archivos se arman con bytes explícitos en un directorio temporal:
no dependen de `core.autocrlf` ni del host.
"""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.ds_init import managed_hash as mh


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self._n = 0

    def _escribir(self, datos: bytes) -> Path:
        self._n += 1
        ruta = self.dir / f"f{self._n}.txt"
        ruta.write_bytes(datos)
        return ruta

    def _h(self, datos: bytes, bloque: int = 65536) -> str:
        return mh.hash_managed_file(self._escribir(datos), mh.ALG_TEXTO, bloque)


class TestHashTexto(_Base):
    def test_lf_crlf_cr_iguales(self):
        h_lf = self._h(b"hello\nworld\n")
        self.assertEqual(h_lf, self._h(b"hello\r\nworld\r\n"))
        self.assertEqual(h_lf, self._h(b"hello\rworld\r"))

    def test_cambio_real_distinto(self):
        self.assertNotEqual(self._h(b"hello\nworld\n"), self._h(b"hello\nWORLD\n"))

    def test_whitespace_distinto(self):
        base = self._h(b"a b\n")
        self.assertNotEqual(base, self._h(b"a b \n"))
        self.assertNotEqual(base, self._h(b"a\tb\n"))
        self.assertNotEqual(base, self._h(b"a  b\n"))

    def test_eol_mixto(self):
        self.assertEqual(self._h(b"a\r\nb\nc\rd"), self._h(b"a\nb\nc\nd"))

    def test_archivo_vacio(self):
        self.assertEqual(self._h(b""), hashlib.sha256(b"").hexdigest())

    def test_sin_newline_final(self):
        self.assertEqual(self._h(b"abc"), hashlib.sha256(b"abc").hexdigest())
        self.assertNotEqual(self._h(b"abc"), self._h(b"abc\n"))

    def test_crlf_partido_entre_bloques(self):
        esperado = hashlib.sha256(b"a\nb\nc\n").hexdigest()
        for bloque in (1, 2, 3):
            with self.subTest(bloque=bloque):
                self.assertEqual(self._h(b"a\r\nb\r\nc\r\n", bloque), esperado)

    def test_crlf_cruzando_limite_65536(self):
        # el \r queda como último byte del primer bloque y el \n abre el segundo
        datos = b"x" * 65535 + b"\r\n" + b"y" * 10
        esperado = hashlib.sha256(b"x" * 65535 + b"\n" + b"y" * 10).hexdigest()
        self.assertEqual(self._h(datos), esperado)

    def test_independiente_del_bloque(self):
        datos = b"\xef\xbb\xbfl1\r\nl2\rl3\n\r\n\r\r\nfin\r"
        ref = self._h(datos)
        for bloque in (1, 2, 3, 4, 5, 7, 64, 65536):
            with self.subTest(bloque=bloque):
                self.assertEqual(self._h(datos, bloque), ref)

    def test_cr_doble_y_cr_lf_consecutivos(self):
        # \r\r\n -> \n\n ; \r\n\r\n -> \n\n
        self.assertEqual(self._h(b"a\r\r\nb", 1), hashlib.sha256(b"a\n\nb").hexdigest())
        self.assertEqual(self._h(b"a\r\n\r\nb", 1), hashlib.sha256(b"a\n\nb").hexdigest())

    def test_bom_se_conserva(self):
        self.assertNotEqual(self._h(b"\xef\xbb\xbfhola\n"), self._h(b"hola\n"))

    def test_algoritmo_desconocido_valueerror(self):
        ruta = self._escribir(b"x")
        with self.assertRaises(ValueError):
            mh.hash_managed_file(ruta, "sha256/otro/v9")

    def test_hash_crudo(self):
        ruta = self._escribir(b"a\r\nb")
        self.assertEqual(mh.hash_crudo_file(ruta), hashlib.sha256(b"a\r\nb").hexdigest())


class TestHashBinario(_Base):
    def test_bytes_exactos(self):
        ruta = self._escribir(b"a\r\nb")
        self.assertEqual(
            mh.hash_managed_file(ruta, mh.ALG_BINARIO),
            hashlib.sha256(b"a\r\nb").hexdigest(),
        )

    def test_crlf_distinto_de_lf(self):
        h1 = mh.hash_managed_file(self._escribir(b"a\r\nb"), mh.ALG_BINARIO)
        h2 = mh.hash_managed_file(self._escribir(b"a\nb"), mh.ALG_BINARIO)
        self.assertNotEqual(h1, h2)

    def test_independiente_del_bloque(self):
        ruta = self._escribir(b"\x00\r\n\xff\r" * 50)
        self.assertEqual(
            mh.hash_managed_file(ruta, mh.ALG_BINARIO, 1),
            mh.hash_managed_file(ruta, mh.ALG_BINARIO),
        )


class TestAlgoritmoParaContenido(unittest.TestCase):
    def test_mapeo(self):
        self.assertEqual(mh.algoritmo_para_contenido(mh.CONTENIDO_TEXTO), mh.ALG_TEXTO)
        self.assertEqual(mh.algoritmo_para_contenido(mh.CONTENIDO_BINARIO), mh.ALG_BINARIO)

    def test_desconocido(self):
        with self.assertRaises(ValueError):
            mh.algoritmo_para_contenido("raro")

    def test_conocidos(self):
        self.assertEqual(set(mh.ALGORITMOS_CONOCIDOS), {mh.ALG_TEXTO, mh.ALG_BINARIO})


class TestVerificarEntrada(_Base):
    def _sha(self, datos: bytes) -> str:
        return hashlib.sha256(datos).hexdigest()

    def test_ok_con_hash_alg(self):
        ruta = self._escribir(b"hello\r\nworld\r\n")
        entrada = {"ruta": "f", "sha256": self._sha(b"hello\nworld\n"), "hash_alg": mh.ALG_TEXTO}
        self.assertEqual(mh.verificar_entrada(ruta, entrada)[0], mh.ESTADO_OK)

    def test_ok_hex_mayusculas(self):
        ruta = self._escribir(b"abc\n")
        entrada = {"ruta": "f", "sha256": self._sha(b"abc\n").upper(), "hash_alg": mh.ALG_TEXTO}
        self.assertEqual(mh.verificar_entrada(ruta, entrada)[0], mh.ESTADO_OK)

    def test_drift_con_hash_alg(self):
        ruta = self._escribir(b"hello\nWORLD\n")
        entrada = {"ruta": "f", "sha256": self._sha(b"hello\nworld\n"), "hash_alg": mh.ALG_TEXTO}
        self.assertEqual(mh.verificar_entrada(ruta, entrada)[0], mh.ESTADO_DRIFT)

    def test_binario_ok_y_drift(self):
        ruta = self._escribir(b"a\r\nb")
        ok = {"ruta": "f", "sha256": self._sha(b"a\r\nb"), "hash_alg": mh.ALG_BINARIO}
        mal = {"ruta": "f", "sha256": self._sha(b"a\nb"), "hash_alg": mh.ALG_BINARIO}
        self.assertEqual(mh.verificar_entrada(ruta, ok)[0], mh.ESTADO_OK)
        self.assertEqual(mh.verificar_entrada(ruta, mal)[0], mh.ESTADO_DRIFT)

    def test_algoritmo_desconocido(self):
        ruta = self._escribir(b"x")
        for alg in ("sha256/futuro/v9", 7, None):
            with self.subTest(alg=alg):
                entrada = {"ruta": "f", "sha256": self._sha(b"x"), "hash_alg": alg}
                self.assertEqual(
                    mh.verificar_entrada(ruta, entrada)[0], mh.ESTADO_ALG_DESCONOCIDO
                )

    def test_algoritmo_desconocido_no_lee_archivo(self):
        # no calcula nada: ni siquiera falla si el archivo no existe
        entrada = {"ruta": "f", "sha256": "0" * 64, "hash_alg": "sha256/futuro/v9"}
        estado, _ = mh.verificar_entrada(self.dir / "no_existe", entrada)
        self.assertEqual(estado, mh.ESTADO_ALG_DESCONOCIDO)

    def test_legacy_crudo(self):
        datos = b"a\r\nb\r\n"
        ruta = self._escribir(datos)
        entrada = {"ruta": "f", "sha256": self._sha(datos)}
        self.assertEqual(mh.verificar_entrada(ruta, entrada)[0], mh.ESTADO_OK_LEGACY)

    def test_legacy_forma_lf(self):
        ruta = self._escribir(b"a\r\nb\r\n")
        entrada = {"ruta": "f", "sha256": self._sha(b"a\nb\n")}
        self.assertEqual(mh.verificar_entrada(ruta, entrada)[0], mh.ESTADO_OK_LEGACY)

    def test_legacy_forma_crlf(self):
        ruta = self._escribir(b"a\nb\n")
        entrada = {"ruta": "f", "sha256": self._sha(b"a\r\nb\r\n")}
        self.assertEqual(mh.verificar_entrada(ruta, entrada)[0], mh.ESTADO_OK_LEGACY)

    def test_legacy_bloque_chico(self):
        ruta = self._escribir(b"a\nb\n")
        entrada = {"ruta": "f", "sha256": self._sha(b"a\r\nb\r\n")}
        self.assertEqual(mh.verificar_entrada(ruta, entrada, bloque=1)[0], mh.ESTADO_OK_LEGACY)
        ruta2 = self._escribir(b"a\r\nb\r\n")
        entrada2 = {"ruta": "f", "sha256": self._sha(b"a\nb\n")}
        self.assertEqual(mh.verificar_entrada(ruta2, entrada2, bloque=1)[0], mh.ESTADO_OK_LEGACY)

    def test_legacy_modificado_drift(self):
        ruta = self._escribir(b"a\nB\n")
        entrada = {"ruta": "f", "sha256": self._sha(b"a\nb\n")}
        self.assertEqual(mh.verificar_entrada(ruta, entrada)[0], mh.ESTADO_DRIFT)

    def test_legacy_eol_mixto_no_verificable(self):
        # baseline histórico de EOL mixto; el archivo actual quedó en LF puro
        baseline = self._sha(b"a\r\nb\nc\r\n")
        ruta = self._escribir(b"a\nb\nc\n")
        entrada = {"ruta": "f", "sha256": baseline}
        self.assertEqual(mh.verificar_entrada(ruta, entrada)[0], mh.ESTADO_DRIFT)

    def test_sha256_no_str_drift(self):
        ruta = self._escribir(b"x")
        for esperado in (None, 123, b"abc"):
            for extra in ({}, {"hash_alg": mh.ALG_TEXTO}):
                with self.subTest(esperado=esperado, extra=extra):
                    entrada = {"ruta": "f", "sha256": esperado, **extra}
                    self.assertEqual(mh.verificar_entrada(ruta, entrada)[0], mh.ESTADO_DRIFT)
        self.assertEqual(mh.verificar_entrada(ruta, {"ruta": "f"})[0], mh.ESTADO_DRIFT)

    def test_legacy_binario_crudo_ok_legacy(self):
        datos = b"\x00a\r\nb\xff"
        ruta = self._escribir(datos)
        entrada = {"ruta": "f", "sha256": self._sha(datos)}
        self.assertEqual(
            mh.verificar_entrada(ruta, entrada, contenido=mh.CONTENIDO_BINARIO)[0],
            mh.ESTADO_OK_LEGACY,
        )

    def test_legacy_binario_eol_alterado_drift(self):
        ruta = self._escribir(b"a\nb\n")
        for baseline in (b"a\r\nb\r\n", b"a\nb\r\n"):
            with self.subTest(baseline=baseline):
                entrada = {"ruta": "f", "sha256": self._sha(baseline)}
                self.assertEqual(
                    mh.verificar_entrada(ruta, entrada, contenido=mh.CONTENIDO_BINARIO)[0],
                    mh.ESTADO_DRIFT,
                )
        # el mismo caso en texto sí verifica
        entrada = {"ruta": "f", "sha256": self._sha(b"a\r\nb\r\n")}
        self.assertEqual(
            mh.verificar_entrada(ruta, entrada, contenido=mh.CONTENIDO_TEXTO)[0],
            mh.ESTADO_OK_LEGACY,
        )

    def test_contenido_invalido_valueerror(self):
        ruta = self._escribir(b"x")
        entrada = {"ruta": "f", "sha256": self._sha(b"x")}
        with self.assertRaises(ValueError):
            mh.verificar_entrada(ruta, entrada, contenido="raro")

    def test_contenido_no_afecta_con_hash_alg(self):
        ruta = self._escribir(b"a\r\nb")
        entrada = {"ruta": "f", "sha256": self._sha(b"a\nb"), "hash_alg": mh.ALG_TEXTO}
        self.assertEqual(
            mh.verificar_entrada(ruta, entrada, contenido=mh.CONTENIDO_BINARIO)[0],
            mh.ESTADO_OK,
        )

    def test_error_io_se_propaga(self):
        entrada = {"ruta": "f", "sha256": "0" * 64, "hash_alg": mh.ALG_TEXTO}
        with self.assertRaises(OSError):
            mh.verificar_entrada(self.dir / "no_existe", entrada)
        with self.assertRaises(OSError):
            mh.verificar_entrada(self.dir / "no_existe", {"ruta": "f", "sha256": "0" * 64})


if __name__ == "__main__":
    unittest.main()
