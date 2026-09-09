"""Tests de `tools.ds_init.manifest`. Valida SOLO la forma del manifiesto
(clasificación VERBATIM/PLANTILLA/GENERADO/MERGE consistente, sin overlap de
destinos) — corre contra los datos fijos del propio paquete, no lee el
repositorio del harness a nivel de contenido de archivos (R14)."""
from __future__ import annotations

import unittest

from tools.ds_init.manifest import (
    EXCLUSIONES_PERMANENTES,
    GENERADO,
    MERGE,
    MANIFEST,
    PERFILES,
    PLANTILLA,
    TRATAMIENTOS_VALIDOS,
    VERBATIM,
    EntradaManifiesto,
    PerfilDesconocidoError,
    manifest_para_perfil,
    resolver_dir_perfil,
)


class TestFormaManifiesto(unittest.TestCase):
    def test_manifest_no_vacio(self):
        self.assertGreater(len(MANIFEST), 0)

    def test_todos_los_tratamientos_son_validos(self):
        for entrada in MANIFEST:
            self.assertIn(entrada.tratamiento, TRATAMIENTOS_VALIDOS)

    def test_destinos_sin_overlap(self):
        destinos = [entrada.destino for entrada in MANIFEST]
        self.assertEqual(len(destinos), len(set(destinos)), "Hay destinos duplicados en MANIFEST")

    def test_entradas_no_generado_tienen_fuente(self):
        for entrada in MANIFEST:
            if entrada.tratamiento != GENERADO:
                self.assertTrue(
                    entrada.fuente,
                    f"Entrada {entrada.destino!r} ({entrada.tratamiento}) sin fuente",
                )

    def test_entrada_invalida_levanta_value_error(self):
        with self.assertRaises(ValueError):
            EntradaManifiesto(fuente="algo.py", tratamiento="NO_EXISTE", destino="algo.py")

    def test_entrada_no_generado_sin_fuente_levanta(self):
        with self.assertRaises(ValueError):
            EntradaManifiesto(fuente=None, tratamiento=VERBATIM, destino="algo.py")

    def test_ningun_destino_dentro_de_exclusion_permanente(self):
        for entrada in MANIFEST:
            for exclusion in EXCLUSIONES_PERMANENTES:
                self.assertFalse(
                    entrada.destino.startswith(exclusion),
                    f"Destino {entrada.destino!r} cae dentro de la exclusión permanente {exclusion!r}",
                )

    def test_control_json_es_generado(self):
        entradas_control = [e for e in MANIFEST if e.destino == ".ds_init/control.json"]
        self.assertEqual(len(entradas_control), 1)
        self.assertEqual(entradas_control[0].tratamiento, GENERADO)

    def test_settings_json_es_merge(self):
        entradas_settings = [e for e in MANIFEST if e.destino == ".claude/settings.json"]
        self.assertEqual(len(entradas_settings), 1)
        self.assertEqual(entradas_settings[0].tratamiento, MERGE)

    def test_nbrunner_manifest_es_plantilla(self):
        entradas = [e for e in MANIFEST if e.destino == "tools/nbrunner/manifest.py"]
        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0].tratamiento, PLANTILLA)

    def test_suite_tests_desarrollo_no_se_instala(self):
        for entrada in MANIFEST:
            self.assertFalse(
                entrada.destino.startswith("tools/tests/test_ds_guard")
                or entrada.destino.startswith("tools/tests/test_hook_presupuesto")
                or entrada.destino.startswith("tools/tests/test_nbrunner"),
            )

    def test_smoke_test_generico_si_se_instala(self):
        destinos = [entrada.destino for entrada in MANIFEST]
        self.assertIn("tools/tests/test_harness_smoke.py", destinos)


class TestManifestParaPerfil(unittest.TestCase):
    def test_perfil_mvp_incluye_todo(self):
        # El identificador público de CLI usa guiones (R2); el directorio
        # real del perfil (`python_jupyter_data`, guion bajo) no se pasa acá
        # directamente — lo resuelve `manifest.resolver_dir_perfil`.
        entradas = manifest_para_perfil("python-jupyter-data")
        self.assertEqual(len(entradas), len(MANIFEST))

    def test_perfil_desconocido_levanta_error_claro(self):
        with self.assertRaises(PerfilDesconocidoError):
            manifest_para_perfil("perfil-inexistente")


class TestResolverDirPerfil(unittest.TestCase):
    def test_mapea_identificador_publico_a_directorio_real(self):
        self.assertEqual(resolver_dir_perfil("python-jupyter-data"), "python_jupyter_data")

    def test_perfiles_mapeo_contiene_el_perfil_mvp(self):
        self.assertIn("python-jupyter-data", PERFILES)
        self.assertEqual(PERFILES["python-jupyter-data"], "python_jupyter_data")

    def test_perfil_desconocido_levanta_error_claro_no_file_not_found(self):
        with self.assertRaises(PerfilDesconocidoError) as ctx:
            resolver_dir_perfil("perfil-inexistente")
        # El mensaje debe ser explícito, no un FileNotFoundError críptico.
        self.assertIn("perfil-inexistente", str(ctx.exception))
        self.assertNotIsInstance(ctx.exception, FileNotFoundError)


if __name__ == "__main__":
    unittest.main()
