"""Tests de `tools.leadrun.notebooks` (T3, R11 de
`openspec/changes/20260929-lead-execution-runtime/spec.md`).

Unitarios y aislados: se parchea (`unittest.mock.patch`) la composición hacia
`tools.nbrunner.{manifest,execute,fsdiff}` en el propio namespace del módulo
bajo test, así no se necesita un manifest/notebook real en disco ni un kernel
Jupyter real -- ese motor ya está cubierto por los tests de `tools/nbrunner/`
(no se duplican acá). Cubre los 4 casos Given/When/Then de R11:

1. hash desincronizado no ejecuta.
2. manifest válido + aprobación vigente + execute -> ejecuta y clasifica.
3. manifest válido sin aprobación + execute -> no ejecuta.
4. dry-run nunca ejecuta.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tools.leadrun import notebooks
from tools.nbrunner.core import Finding
from tools.nbrunner.manifest import ManifestInvalidoError

MANIFEST_PATH = Path("openspec/changes/x/runs/r.json")
REPO_ROOT = Path("/repo")

DATOS_MANIFEST = {
    "notebook": {
        "ruta": "notebooks/03_features.ipynb",
        "hash_aprobado": "abc123",
        "algoritmo": "sha256/lf/v1",
    },
    "interprete": "/repo/.venv/bin/python",
    "entradas_permitidas": ["data/interim/algo.parquet"],
    "salidas_permitidas": ["data/processed/algo.parquet"],
    "rutas_prohibidas": [],
    "timeout_segundos": 600,
    "fase": "Fase 6",
    "motivo": "test",
    "criterio_exito": "exit 0",
}


def _resultado_ejecucion_ok() -> SimpleNamespace:
    """Fixture local con exactamente los atributos que `notebooks.py` lee de
    un `ResultadoEjecucion` real (`tools.nbrunner.execute`). Se usa un
    `SimpleNamespace` en vez de la dataclass real para no depender, a nivel
    de módulo, de `nbformat`/`nbclient` (importadas eager por
    `tools.nbrunner.execute`) -- acá alcanza con el duck typing, ya que
    `nbexecute` está mockeado."""
    return SimpleNamespace(
        exit_ok=True,
        duracion_segundos=1.23,
        stdout_resumen="ok",
        stderr_resumen="",
        timeout_alcanzado=False,
        posible_proceso_huerfano=False,
        error_info=None,
    )


class _BaseNotebooksTest(unittest.TestCase):
    """Parchea toda la composición hacia `nbrunner`/`launcher_common` en el
    namespace de `tools.leadrun.notebooks`."""

    def setUp(self) -> None:
        parches = {
            "nbmanifest": mock.patch.object(notebooks, "nbmanifest"),
            # `nbexecute` ya no es un atributo de módulo de `notebooks` (se
            # importa de forma perezosa dentro de `ejecutar_manifest`, fix de
            # eager-import de `nbformat`/`nbclient`): se parchea la fuente
            # real, `nbrunner.execute` (atributo `execute` del paquete
            # `nbrunner`, IMPORT BARE -- mismo gotcha de doble identidad de
            # módulo que en el resto del repo, `tools/` no tiene
            # `__init__.py`: `notebooks.py` hace `sys.path.insert(0,
            # _TOOLS_DIR)` y el lazy import es `from nbrunner import execute
            # as nbexecute`, NO `from tools.nbrunner import execute` -- si acá
            # se parchea `tools.nbrunner.execute` en vez de `nbrunner.execute`,
            # son dos objetos de módulo distintos y el parche no afecta al que
            # `ejecutar_manifest` realmente resuelve), que es lo que ese import
            # perezoso termina resolviendo. `create=True` porque, precisamente
            # por ser perezoso, el submódulo real nunca se importó todavía en
            # este proceso -- sin `create=True`, `mock.patch` exige que el
            # atributo ya exista y falla con `AttributeError` antes de poder
            # simularlo (no requiere `nbformat`/`nbclient` instalados: solo
            # registra el mock como atributo del paquete, sin importar el
            # submódulo real).
            "nbexecute": mock.patch("nbrunner.execute", create=True),
            "nbfsdiff": mock.patch.object(notebooks, "nbfsdiff"),
            "nbcore": mock.patch.object(notebooks, "nbcore"),
            "launcher_common": mock.patch.object(notebooks, "launcher_common"),
        }
        self.mocks = {}
        for nombre, parche in parches.items():
            self.mocks[nombre] = parche.start()
            self.addCleanup(parche.stop)

        # Defaults neutros: cada test ajusta lo que necesite.
        self.mocks["nbmanifest"].cargar_manifest.return_value = dict(DATOS_MANIFEST)
        self.mocks["nbmanifest"].validar_interprete.return_value = []
        self.mocks["nbmanifest"].validar_hash_notebook.return_value = []
        self.mocks["nbmanifest"].validar_rutas_prohibidas.return_value = []
        self.mocks["nbmanifest"].validar_aprobacion.return_value = ([], "vigente")
        self.mocks["nbmanifest"].ManifestInvalidoError = ManifestInvalidoError
        self.mocks["nbcore"].hash_lf_v1.return_value = "hash-del-manifest"
        self.mocks["nbcore"].Finding = Finding
        self.mocks["launcher_common"].resolver_venv_dir.return_value = ".venv"


class TestHashDesincronizadoNoEjecuta(_BaseNotebooksTest):
    def test_hash_desincronizado_no_ejecuta_en_execute(self):
        finding = Finding("NBRUNNER-HASH-DESINCRONIZADO", "no coincide", "notebooks/03_features.ipynb")
        self.mocks["nbmanifest"].validar_hash_notebook.return_value = [finding]

        resultado = notebooks.ejecutar_manifest(MANIFEST_PATH, REPO_ROOT, {"aprobaciones": []}, "execute")

        self.assertFalse(resultado["ok"])
        self.assertFalse(resultado["ejecutado"])
        self.assertIn("NBRUNNER-HASH-DESINCRONIZADO", [f["codigo"] for f in resultado["findings"]])
        self.mocks["nbexecute"].ejecutar_notebook.assert_not_called()

    def test_hash_desincronizado_no_ejecuta_en_dry_run(self):
        finding = Finding("NBRUNNER-HASH-DESINCRONIZADO", "no coincide", "notebooks/03_features.ipynb")
        self.mocks["nbmanifest"].validar_hash_notebook.return_value = [finding]

        resultado = notebooks.ejecutar_manifest(MANIFEST_PATH, REPO_ROOT, {"aprobaciones": []}, "dry_run")

        self.assertFalse(resultado["ok"])
        self.assertFalse(resultado["ejecutado"])
        self.mocks["nbexecute"].ejecutar_notebook.assert_not_called()


class TestManifestValidoAprobacionVigenteExecute(_BaseNotebooksTest):
    def test_ejecuta_y_clasifica(self):
        self.mocks["nbfsdiff"].snapshot.side_effect = [{"antes": (1, 1)}, {"despues": (2, 2)}]
        self.mocks["nbfsdiff"].diferencia.return_value = {
            "agregados": ["data/processed/algo.parquet"],
            "eliminados": [],
            "modificados": [],
        }
        self.mocks["nbfsdiff"].clasificar.return_value = (["data/processed/algo.parquet"], [])
        self.mocks["nbexecute"].ejecutar_notebook.return_value = _resultado_ejecucion_ok()

        resultado = notebooks.ejecutar_manifest(MANIFEST_PATH, REPO_ROOT, {"aprobaciones": []}, "execute")

        self.mocks["nbexecute"].ejecutar_notebook.assert_called_once()
        self.mocks["nbfsdiff"].cuarentena.assert_not_called()
        self.assertTrue(resultado["ejecutado"])
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["estado_aprobacion"], "vigente")
        self.assertEqual(resultado["fsdiff"]["permitidos"], ["data/processed/algo.parquet"])
        self.assertEqual(resultado["fsdiff"]["fuera_de_contrato"], [])

    def test_salida_fuera_de_contrato_va_a_cuarentena_y_ok_false(self):
        self.mocks["nbfsdiff"].snapshot.side_effect = [{}, {}]
        self.mocks["nbfsdiff"].diferencia.return_value = {
            "agregados": ["data/processed/otra_cosa.parquet"],
            "eliminados": [],
            "modificados": [],
        }
        self.mocks["nbfsdiff"].clasificar.return_value = ([], ["data/processed/otra_cosa.parquet"])
        self.mocks["nbfsdiff"].cuarentena.return_value = [
            REPO_ROOT / ".harmessi" / "quarantine" / "r" / "data/processed/otra_cosa.parquet"
        ]
        self.mocks["nbexecute"].ejecutar_notebook.return_value = _resultado_ejecucion_ok()

        resultado = notebooks.ejecutar_manifest(MANIFEST_PATH, REPO_ROOT, {"aprobaciones": []}, "execute")

        self.mocks["nbfsdiff"].cuarentena.assert_called_once()
        self.assertTrue(resultado["ejecutado"])
        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["fsdiff"]["fuera_de_contrato"], ["data/processed/otra_cosa.parquet"])


class TestManifestValidoSinAprobacionExecute(_BaseNotebooksTest):
    def test_no_ejecuta(self):
        finding = Finding("APROB-AUSENTE", "No hay aprobación registrada", "openspec/changes/x/runs/r.json")
        self.mocks["nbmanifest"].validar_aprobacion.return_value = ([finding], "ausente")

        resultado = notebooks.ejecutar_manifest(MANIFEST_PATH, REPO_ROOT, {"aprobaciones": []}, "execute")

        self.assertFalse(resultado["ok"])
        self.assertFalse(resultado["ejecutado"])
        self.assertEqual(resultado["estado_aprobacion"], "ausente")
        self.mocks["nbexecute"].ejecutar_notebook.assert_not_called()


class TestDryRunNuncaEjecuta(_BaseNotebooksTest):
    def test_dry_run_con_todo_valido_no_ejecuta(self):
        self.mocks["nbmanifest"].validar_aprobacion.return_value = ([], "no_verificada")

        resultado = notebooks.ejecutar_manifest(MANIFEST_PATH, REPO_ROOT, {"aprobaciones": []}, "dry_run")

        self.assertTrue(resultado["ok"])
        self.assertFalse(resultado["ejecutado"])
        self.assertEqual(resultado["estado_aprobacion"], "no_verificada")
        self.mocks["nbexecute"].ejecutar_notebook.assert_not_called()
        self.mocks["nbfsdiff"].snapshot.assert_not_called()


class TestManifestInvalido(_BaseNotebooksTest):
    def test_manifest_invalido_corta_sin_seguir_validando(self):
        self.mocks["nbmanifest"].cargar_manifest.side_effect = ManifestInvalidoError(["notebook.ruta"])

        resultado = notebooks.ejecutar_manifest(MANIFEST_PATH, REPO_ROOT, {"aprobaciones": []}, "dry_run")

        self.assertFalse(resultado["ok"])
        self.assertFalse(resultado["ejecutado"])
        self.assertEqual(len(resultado["findings"]), 1)
        self.mocks["nbmanifest"].validar_interprete.assert_not_called()


class TestModoInvalido(_BaseNotebooksTest):
    def test_modo_invalido_lanza_value_error(self):
        with self.assertRaises(ValueError):
            notebooks.ejecutar_manifest(MANIFEST_PATH, REPO_ROOT, {"aprobaciones": []}, "otro")


if __name__ == "__main__":
    unittest.main()
