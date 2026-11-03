"""v0.13 R8: las CLIs no lanzan UnicodeEncodeError con consola no UTF-8."""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ORIGEN = Path(__file__).resolve().parents[3]
if str(REPO_ORIGEN) not in sys.path:
    sys.path.insert(0, str(REPO_ORIGEN))

from tools.harmessi_bench import cli as bench_cli  # noqa: E402
from tools.providers import conformance  # noqa: E402


def _stream_cp1252() -> io.TextIOWrapper:
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict", newline="")


class TestConsolaSegura(unittest.TestCase):
    def _verificar(self, funcion):
        out, err = _stream_cp1252(), _stream_cp1252()
        with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            funcion()
            print("flecha → y tilde á")  # → no existe en cp1252
            print("error →", file=sys.stderr)
            out.flush()
            err.flush()
            crudo = out.buffer.getvalue()
        self.assertIn(b"flecha ? y tilde \xe1", crudo)

    def test_bench_cli(self):
        self._verificar(bench_cli._consola_segura)

    def test_providers_conformance(self):
        self._verificar(conformance._consola_segura)

    def test_main_invoca_consola_segura(self):
        with mock.patch.object(bench_cli, "_consola_segura") as espia:
            with self.assertRaises(SystemExit):  # sin argumentos argparse sale; ya se llamó antes
                bench_cli.main([])
        espia.assert_called_once()
        with mock.patch.object(conformance, "_consola_segura") as espia:
            with self.assertRaises(SystemExit):
                conformance.main(["--opcion-inexistente"])
        espia.assert_called_once()

    def test_stream_sin_reconfigure_no_falla(self):
        class Plano:
            def write(self, _):
                return 0

        with mock.patch.object(sys, "stdout", Plano()), mock.patch.object(sys, "stderr", Plano()):
            bench_cli._consola_segura()
            conformance._consola_segura()

    def test_reconfigure_con_error_no_falla(self):
        class Rota:
            def reconfigure(self, **_):
                raise ValueError("no se puede")

        with mock.patch.object(sys, "stdout", Rota()), mock.patch.object(sys, "stderr", Rota()):
            bench_cli._consola_segura()
            conformance._consola_segura()


if __name__ == "__main__":
    unittest.main()
