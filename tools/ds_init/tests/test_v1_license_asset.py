"""Asset HARMESSI-LICENSE.txt en el manifest y su ciclo install/upgrade (v1.0,
Change 20261102-v1-release-hardening, R2). Reusa la base y los helpers de
`test_upgrade` (repositorios Git temporales propios)."""
from __future__ import annotations

import unittest

from tools.ds_init import managed_hash
from tools.ds_init.manifest import MANIFEST, VERBATIM, contenido_de, raiz_repo_origen
from tools.ds_init.tests.test_upgrade import (
    _BaseUpgrade,
    _commit_todo,
    _escribir_control,
    _hashes_arbol,
    _leer_control,
)

ASSET = "HARMESSI-LICENSE.txt"


class TestAssetEnManifest(unittest.TestCase):
    def test_entrada_verbatim_discovery_y_fuente_existe(self):
        entradas = [e for e in MANIFEST if e.destino == ASSET]
        self.assertEqual(len(entradas), 1)
        entrada = entradas[0]
        self.assertEqual(entrada.tratamiento, VERBATIM)
        self.assertEqual(entrada.stage_minimo, "discovery")
        self.assertEqual(entrada.fuente, ASSET)
        self.assertTrue((raiz_repo_origen() / entrada.fuente).is_file())


class TestAssetInstallUpgrade(_BaseUpgrade):
    def _entrada_control(self):
        return {e["ruta"]: e for e in _leer_control(self.repo)["archivos"]}.get(ASSET)

    def _simular_baseline_sin_asset(self):
        """Baseline previo a la entrada del asset: sin archivo y sin entrada en el control."""
        (self.repo / ASSET).unlink()
        control = _leer_control(self.repo)
        control["archivos"] = [e for e in control["archivos"] if e["ruta"] != ASSET]
        _escribir_control(self.repo, control)
        _commit_todo(self.repo, "baseline sin asset de licencia")

    def test_install_crea_asset_y_lo_registra_con_hash(self):
        self.assertTrue((self.repo / ASSET).is_file())
        entrada = self._entrada_control()
        self.assertIsNotNone(entrada, "el asset debe figurar en `archivos` del control")
        algoritmo = managed_hash.algoritmo_para_contenido(contenido_de(ASSET))
        self.assertEqual(entrada["sha256"], managed_hash.hash_managed_file(self.repo / ASSET, algoritmo))
        self.assertEqual(
            entrada["sha256"],
            managed_hash.hash_managed_file(raiz_repo_origen() / ASSET, algoritmo))

    def test_upgrade_crea_asset_como_managed_nuevo_sin_drift(self):
        self._simular_baseline_sin_asset()
        codigo, salida, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0, err)
        self.assertTrue((self.repo / ASSET).is_file())
        entrada = self._entrada_control()
        self.assertIsNotNone(entrada)
        algoritmo = managed_hash.algoritmo_para_contenido(contenido_de(ASSET))
        self.assertEqual(entrada["sha256"], managed_hash.hash_managed_file(self.repo / ASSET, algoritmo))
        # Sin drift: el resumen lo declara y el asset no figura como reportado.
        self.assertIn("drift 0", salida)
        self.assertNotIn("reportar-drift", salida)

    def test_segunda_corrida_es_idempotente(self):
        self._simular_baseline_sin_asset()
        codigo, _out, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0, err)
        _commit_todo(self.repo, "post upgrade")
        tras_primera = _hashes_arbol(self.repo)
        codigo, salida, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0, err)
        self.assertIn("Nada que hacer", salida)
        self.assertEqual(tras_primera, _hashes_arbol(self.repo))

    def test_asset_borrado_por_el_usuario_no_se_recrea(self):
        # Comportamiento real (cli.py, plan de upgrade): ausente del disco pero
        # presente en el baseline -> "no se recrea".
        (self.repo / ASSET).unlink()
        _commit_todo(self.repo, "usuario borra el asset")
        codigo, _out, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0, err)
        self.assertFalse((self.repo / ASSET).exists())


if __name__ == "__main__":
    unittest.main()
