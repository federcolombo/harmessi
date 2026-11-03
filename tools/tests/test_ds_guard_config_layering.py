"""Tests del layering de configuración M10 (v0.8 Change 4:
`20260930-project-extension-and-installer-integration`, T2) --
`resolver_project_config`/`resolver_local_override`/`resolver_modo_efectivo`
en `tools/ds_guard.py` (R10-R11 de spec.md, D3 de design.md).

Mismo patrón de import directo (sin subprocess) que
`test_ds_guard_usuario_guard.py`: estas son funciones puras de
lectura/composición, no requieren invocar el CLI completo. Repo git temporal
solo para tener una `repo_root` real con la que construir rutas.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

import ds_guard  # noqa: E402


def _crear_repo_git_temporal(prefix: str = "config_layering_test_") -> Path:
    repo = Path(tempfile.mkdtemp(prefix=prefix))
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    return repo


def _escribir_capa(repo: Path, nombre_archivo: str, contenido: str) -> Path:
    directorio = repo / ".harmessi"
    directorio.mkdir(parents=True, exist_ok=True)
    ruta = directorio / nombre_archivo
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


class _BaseRepoGit(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)


class TestSinNingunaCapaPresente(_BaseRepoGit):
    """Ausencia total de las dos capas: caso normal/esperado (proyecto sin
    M10 configurado), backward compatible con el comportamiento de hoy."""

    def test_resolver_project_config_devuelve_dict_vacio(self):
        self.assertEqual(ds_guard.resolver_project_config(self.repo), {})

    def test_resolver_local_override_devuelve_dict_vacio(self):
        self.assertEqual(ds_guard.resolver_local_override(self.repo), {})

    def test_resolver_modo_efectivo_devuelve_policy_humana_sin_cambios(self):
        self.assertEqual(
            ds_guard.resolver_modo_efectivo("autonomous", {}, {}), "autonomous"
        )
        self.assertEqual(
            ds_guard.resolver_modo_efectivo("supervised", {}, {}), "supervised"
        )


class TestSoloLocalOverridePresente(_BaseRepoGit):
    def test_project_config_ausente_pero_local_supervised_restringe_autonomous(self):
        _escribir_capa(self.repo, "local-overrides.json", json.dumps({"mode": "supervised"}))
        project_config = ds_guard.resolver_project_config(self.repo)
        local_override = ds_guard.resolver_local_override(self.repo)
        self.assertEqual(project_config, {})
        self.assertEqual(local_override, {"mode": "supervised"})
        efectivo = ds_guard.resolver_modo_efectivo("autonomous", project_config, local_override)
        self.assertEqual(efectivo, "supervised")


class TestGivenWhenThenExactoDeR11(_BaseRepoGit):
    """El caso más importante de R11: un override que intenta AMPLIAR
    (`mode: autonomous`) sobre una policy humana `supervised` se ignora --
    el efectivo sigue siendo `supervised`."""

    def test_local_override_autonomous_sobre_policy_supervised_no_amplia(self):
        _escribir_capa(self.repo, "local-overrides.json", json.dumps({"mode": "autonomous"}))
        local_override = ds_guard.resolver_local_override(self.repo)
        efectivo = ds_guard.resolver_modo_efectivo("supervised", {}, local_override)
        self.assertEqual(efectivo, "supervised")


class TestArchivoCorruptoDegradaComoAusente(_BaseRepoGit):
    def test_project_config_json_invalido_no_lanza_y_se_trata_como_ausente(self):
        _escribir_capa(self.repo, "project-config.json", "esto no es json{{{")
        self.assertEqual(ds_guard.resolver_project_config(self.repo), {})

    def test_local_override_json_invalido_no_lanza_y_se_trata_como_ausente(self):
        _escribir_capa(self.repo, "local-overrides.json", "esto no es json{{{")
        self.assertEqual(ds_guard.resolver_local_override(self.repo), {})


class TestRaizNoEsObjetoDegradaComoAusente(_BaseRepoGit):
    def test_project_config_raiz_lista_se_trata_como_ausente(self):
        _escribir_capa(self.repo, "project-config.json", json.dumps(["mode", "supervised"]))
        self.assertEqual(ds_guard.resolver_project_config(self.repo), {})

    def test_local_override_raiz_lista_se_trata_como_ausente(self):
        _escribir_capa(self.repo, "local-overrides.json", json.dumps(["mode", "autonomous"]))
        self.assertEqual(ds_guard.resolver_local_override(self.repo), {})


class TestAmbasCapasPresentesConValoresDistintos(_BaseRepoGit):
    """Documenta y confirma el orden exacto implementado: cualquiera de las
    dos capas que declare `mode: supervised` alcanza para restringir --
    ninguna capa puede "tapar" la restricción declarada por la otra (unión de
    restricciones, no precedencia de "una capa gana sobre la otra"; ver
    docstring de `resolver_modo_efectivo`)."""

    def test_project_config_supervised_local_override_autonomous_gana_supervised(self):
        project_config = {"mode": "supervised"}
        local_override = {"mode": "autonomous"}
        efectivo = ds_guard.resolver_modo_efectivo("autonomous", project_config, local_override)
        self.assertEqual(efectivo, "supervised")

    def test_project_config_autonomous_local_override_supervised_gana_supervised(self):
        project_config = {"mode": "autonomous"}
        local_override = {"mode": "supervised"}
        efectivo = ds_guard.resolver_modo_efectivo("autonomous", project_config, local_override)
        self.assertEqual(efectivo, "supervised")

    def test_ambas_capas_autonomous_no_restringe(self):
        project_config = {"mode": "autonomous"}
        local_override = {"mode": "autonomous"}
        efectivo = ds_guard.resolver_modo_efectivo("autonomous", project_config, local_override)
        self.assertEqual(efectivo, "autonomous")


class TestValoresDesconocidosSeIgnoran(_BaseRepoGit):
    def test_mode_no_string_se_ignora(self):
        efectivo = ds_guard.resolver_modo_efectivo("autonomous", {"mode": 123}, {})
        self.assertEqual(efectivo, "autonomous")

    def test_mode_valor_no_reconocido_se_ignora(self):
        efectivo = ds_guard.resolver_modo_efectivo(
            "autonomous", {}, {"mode": "algo-no-reconocido"}
        )
        self.assertEqual(efectivo, "autonomous")


# --- T3b-1 (Change 4, M11): `dependencias_efectivas` (R26) ------------------


class TestDependenciasEfectivasSinCapas(_BaseRepoGit):
    def test_sin_ninguna_capa_devuelve_control_sin_cambios(self):
        control = {"dependencias_preaprobadas": [{"nombre": "package-a", "rango": ">=1.2,<2"}]}
        self.assertEqual(
            ds_guard.dependencias_efectivas(control, self.repo),
            control["dependencias_preaprobadas"],
        )


class TestDependenciasEfectivasProjectConfigRestringe(_BaseRepoGit):
    def test_project_config_excluye_dependencia_no_declarada(self):
        control = {
            "dependencias_preaprobadas": [
                {"nombre": "package-a", "rango": ">=1.2,<2"},
                {"nombre": "package-b", "rango": ">=1.0"},
            ]
        }
        _escribir_capa(
            self.repo,
            "project-config.json",
            json.dumps({"dependencias_preaprobadas": [{"nombre": "package-a", "rango": ">=1.2,<2"}]}),
        )
        resultado = ds_guard.dependencias_efectivas(control, self.repo)
        self.assertEqual(resultado, [{"nombre": "package-a", "rango": ">=1.2,<2"}])


class TestDependenciasEfectivasLocalOverrideRestringe(_BaseRepoGit):
    def test_local_override_excluye_dependencia_no_declarada(self):
        control = {
            "dependencias_preaprobadas": [
                {"nombre": "package-a", "rango": ">=1.2,<2"},
                {"nombre": "package-b", "rango": ">=1.0"},
            ]
        }
        _escribir_capa(
            self.repo,
            "local-overrides.json",
            json.dumps({"dependencias_preaprobadas": [{"nombre": "package-b", "rango": ">=1.0"}]}),
        )
        resultado = ds_guard.dependencias_efectivas(control, self.repo)
        self.assertEqual(resultado, [{"nombre": "package-b", "rango": ">=1.0"}])


class TestDependenciasEfectivasAmbasCapasIntersectan(_BaseRepoGit):
    def test_ambas_capas_restringen_subconjuntos_distintos_da_interseccion(self):
        control = {
            "dependencias_preaprobadas": [
                {"nombre": "package-a", "rango": ">=1.2,<2"},
                {"nombre": "package-b", "rango": ">=1.0"},
                {"nombre": "package-c", "rango": ">=1.0"},
            ]
        }
        _escribir_capa(
            self.repo,
            "project-config.json",
            json.dumps(
                {
                    "dependencias_preaprobadas": [
                        {"nombre": "package-a", "rango": ">=1.2,<2"},
                        {"nombre": "package-b", "rango": ">=1.0"},
                    ]
                }
            ),
        )
        _escribir_capa(
            self.repo,
            "local-overrides.json",
            json.dumps({"dependencias_preaprobadas": [{"nombre": "package-a", "rango": ">=1.2,<2"}]}),
        )
        resultado = ds_guard.dependencias_efectivas(control, self.repo)
        self.assertEqual(resultado, [{"nombre": "package-a", "rango": ">=1.2,<2"}])


class TestDependenciasEfectivasComparacionCanonicalizada(_BaseRepoGit):
    def test_nombre_con_capitalizacion_y_separador_distinto_sigue_coincidiendo(self):
        control = {"dependencias_preaprobadas": [{"nombre": "My-Package", "rango": ">=1.0"}]}
        _escribir_capa(
            self.repo,
            "project-config.json",
            json.dumps({"dependencias_preaprobadas": [{"nombre": "my_package", "rango": ">=1.0"}]}),
        )
        resultado = ds_guard.dependencias_efectivas(control, self.repo)
        self.assertEqual(resultado, [{"nombre": "My-Package", "rango": ">=1.0"}])


class TestDependenciasEfectivasNuncaAmplia(_BaseRepoGit):
    def test_capa_declara_dependencia_extra_no_aparece_en_resultado(self):
        control = {"dependencias_preaprobadas": [{"nombre": "package-a", "rango": ">=1.0"}]}
        _escribir_capa(
            self.repo,
            "project-config.json",
            json.dumps(
                {
                    "dependencias_preaprobadas": [
                        {"nombre": "package-a", "rango": ">=1.0"},
                        {"nombre": "package-nueva-no-en-control", "rango": ">=1.0"},
                    ]
                }
            ),
        )
        resultado = ds_guard.dependencias_efectivas(control, self.repo)
        nombres = {d["nombre"] for d in resultado}
        self.assertNotIn("package-nueva-no-en-control", nombres)
        # El resultado siempre es subconjunto de control["dependencias_preaprobadas"].
        self.assertTrue(
            all(d in control["dependencias_preaprobadas"] for d in resultado)
        )


if __name__ == "__main__":
    unittest.main()
