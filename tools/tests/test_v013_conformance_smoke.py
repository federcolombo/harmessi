"""Smoke del Change `20261021-v013-provider-adapter-conformance` (R3, R5, R6, R11).

Evidencia REAL de este Change:
- `detect()` real de `claude`: solo con `HARMESSI_SMOKE_LOCAL=1` y la CLI en
  PATH (skip explicito si no).
- `FileObserver` real sobre un CSV sintetico temporal (skip explicito si falta
  `ds_profile` o `pandas`; nunca un falso OK).

Evidencia FIXTURE: conformance de contrato de los 4 providers (dobles).
Live NO se ejecuta: solo se prueba que sin `HARMESSI_LIVE_PROVIDER` la CLI da
exit 2 y no invoca nada.
"""
from __future__ import annotations

import contextlib
import csv
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

from tools.datasources import conformance as conformance_fuentes
from tools.datasources import file_observer
from tools.providers import PROVIDER_REGISTRY
from tools.providers import conformance as conformance_providers


class TestProvidersContratoReal(unittest.TestCase):
    def test_los_4_providers_alcanzan_contract_tested(self):
        self.assertEqual(set(PROVIDER_REGISTRY), {"claude_code", "codex", "gemini", "grok"})
        for provider_id, adapter in PROVIDER_REGISTRY.items():
            with self.subTest(provider=provider_id):
                reporte = conformance_providers.verificar_conformidad(adapter)
                self.assertEqual(reporte.nivel_alcanzado, "contract-tested", reporte.to_json())

    @unittest.skipUnless(os.environ.get("HARMESSI_SMOKE_LOCAL") == "1", "smoke local opt-in: HARMESSI_SMOKE_LOCAL=1")
    @unittest.skipIf(shutil.which("claude") is None, "CLI 'claude' no disponible en este host")
    def test_smoke_local_real_de_claude_code(self):
        reporte = conformance_providers.verificar_conformidad(PROVIDER_REGISTRY["claude_code"], smoke=True)
        self.assertEqual(reporte.nivel_alcanzado, "locally-smoke-tested", reporte.to_json())

    def test_live_sin_variable_exit_2_y_no_invoca(self):
        entorno = {k: v for k, v in os.environ.items() if k != conformance_providers.VARIABLE_LIVE}
        run = mock.MagicMock()
        with mock.patch.dict(os.environ, entorno, clear=True), mock.patch("subprocess.run", run):
            with contextlib.redirect_stderr(io.StringIO()):
                codigo = conformance_providers.main(["--live"])
        self.assertEqual(codigo, 2)
        run.assert_not_called()


def _crear_csv(ruta: Path) -> None:
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "nombre", "monto"])
        w.writerow(["1", "ana", "10.5"])
        w.writerow(["2", "ñandú", "20.0"])
        w.writerow(["3", "", "30.25"])


def test_file_observer_real_sobre_csv_sintetico():
    pytest.importorskip("ds_profile", reason="ds_profile no instalado: sin evidencia real de FileObserver")
    pytest.importorskip("pandas", reason="pandas no instalado: sin evidencia real de FileObserver")
    with tempfile.TemporaryDirectory(prefix="repo sintético ñ ") as tmp:
        repo = Path(tmp)
        (repo / "datos de prueba").mkdir()
        _crear_csv(repo / "datos de prueba" / "archivo ñandú.csv")
        reporte = conformance_fuentes.verificar_observer(
            file_observer.factory_with_repo_root(repo),
            source_id="fuente-csv-sintetica",
            options={"path": "datos de prueba/archivo ñandú.csv"},
            request={"source_id": "fuente-csv-sintetica"},
            evidencia="real",
            options_error={"path": "datos de prueba/no_existe.csv"},
        )
    assert reporte.evidencia == "real"
    assert reporte.completo
    assert reporte.ok, reporte.to_json()


if __name__ == "__main__":
    unittest.main()
