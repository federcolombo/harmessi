"""Tests de `tools.providers.conformance` (v0.13 Change 3, R1-R6, R13).

Todo contra dobles (`unittest.mock`): sin red, sin credenciales, sin invocar
ninguna CLI real salvo el `detect()` de `claude` (skip si no esta en PATH).
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from tools.providers import PROVIDER_REGISTRY
from tools.providers import conformance
from shutil import which as _which_importado
from subprocess import run as _run_importado

from tools.providers.codex import CodexAdapter
from tools.providers.core import (
    InvocationRequest,
    InvocationResult,
    ProviderCapabilities,
    ProviderInfo,
    classify_availability_error,
)

_CLAVE_ENTORNO = "HARMESSI_CONFORMIDAD_CLAVE"


class FalsoConforme(CodexAdapter):
    """Provider falso conformante (hereda el comportamiento estandar)."""

    provider_id = "falso_conforme"
    cli_command = "falsocli"
    display_name = "Falso Conforme"


class FalsoSinDisplay(FalsoConforme):
    provider_id = "falso_sin_display"
    display_name = ""


class FalsoDetectLanza(FalsoConforme):
    provider_id = "falso_detect_lanza"

    def detect(self) -> ProviderInfo:
        if shutil.which(self.cli_command) is None:
            raise RuntimeError("detect no tolera CLI ausente")
        return super().detect()


class FalsoFiltraBase(FalsoConforme):
    """Base de fixtures que filtran un secreto del entorno por una via."""

    provider_id = "falso_filtra_base"

    def _extra_cmd(self) -> list:
        return []

    def _extra_kwargs(self) -> dict:
        return {}

    def invoke(self, request: InvocationRequest) -> InvocationResult:
        try:
            resultado = subprocess.run(
                [self.cli_command, request.prompt, *self._extra_cmd()],
                capture_output=True, text=True, **self._extra_kwargs(),
            )
        except (OSError, subprocess.TimeoutExpired):
            return InvocationResult(self.provider_id, -1, "", "", False, "unavailable", 0.0)
        return InvocationResult(
            self.provider_id, resultado.returncode, resultado.stdout, resultado.stderr,
            resultado.returncode == 0, None, 0.0,
        )


class FalsoInterpolaSecreto(FalsoFiltraBase):
    provider_id = "falso_interpola_secreto"

    def _extra_cmd(self) -> list:
        return [os.environ.get(_CLAVE_ENTORNO, "")]


class FalsoFiltraCmdOpenai(FalsoFiltraBase):
    provider_id = "falso_filtra_cmd_openai"

    def _extra_cmd(self) -> list:
        return ["--key=" + os.environ.get("OPENAI_API_KEY", "")]


class FalsoFiltraEnv(FalsoFiltraBase):
    provider_id = "falso_filtra_env"

    def _extra_kwargs(self) -> dict:
        return {"env": dict(os.environ)}


class FalsoFiltraInput(FalsoFiltraBase):
    provider_id = "falso_filtra_input"

    def _extra_kwargs(self) -> dict:
        return {"input": os.environ.get("ANTHROPIC_API_KEY", "")}


class FalsoPopen(FalsoConforme):
    """Conformante que invoca con `subprocess.Popen` (debe redirigirse al doble)."""

    provider_id = "falso_popen"
    cli_command = "falsocli-popen"

    def invoke(self, request: InvocationRequest) -> InvocationResult:
        try:
            proceso = subprocess.Popen(
                [self.cli_command, request.prompt], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            salida, error = proceso.communicate(timeout=request.timeout_s)
        except (OSError, subprocess.TimeoutExpired):
            return InvocationResult(self.provider_id, -1, "", "", False, "unavailable", 0.0)
        codigo = proceso.returncode
        return InvocationResult(
            self.provider_id, codigo, salida, error, codigo == 0,
            classify_availability_error(codigo, error) if codigo != 0 else None, 0.0,
        )


class FalsoFromImport(FalsoConforme):
    """Conformante que usa `from subprocess import run` / `from shutil import which`."""

    provider_id = "falso_from_import"
    cli_command = "falsocli-fi"

    def detect(self) -> ProviderInfo:
        capacidades = ProviderCapabilities()
        if _which_importado(self.cli_command) is None:
            return ProviderInfo(
                self.provider_id, self.display_name, self.cli_command, False, None, None, capacidades, "CLI ausente"
            )
        resultado = _run_importado([self.cli_command, "--version"], capture_output=True, text=True, timeout=10)
        lineas = resultado.stdout.strip().splitlines()
        return ProviderInfo(
            self.provider_id, self.display_name, self.cli_command, resultado.returncode == 0, None,
            lineas[0].strip() if lineas else None, capacidades, "detectado",
        )

    def invoke(self, request: InvocationRequest) -> InvocationResult:
        if _which_importado(self.cli_command) is None:
            return InvocationResult(self.provider_id, 127, "", "CLI ausente", False, "unavailable", 0.0)
        try:
            resultado = _run_importado(
                [self.cli_command, request.prompt], capture_output=True, text=True, timeout=request.timeout_s
            )
        except (OSError, subprocess.TimeoutExpired):
            return InvocationResult(self.provider_id, -1, "", "", False, "unavailable", 0.0)
        codigo = resultado.returncode
        return InvocationResult(
            self.provider_id, codigo, resultado.stdout, resultado.stderr, codigo == 0,
            classify_availability_error(codigo, resultado.stderr) if codigo != 0 else None, 0.0,
        )


class FalsoInvokeLanza(FalsoConforme):
    provider_id = "falso_invoke_lanza"

    def invoke(self, request: InvocationRequest) -> InvocationResult:
        resultado = subprocess.run([self.cli_command, request.prompt], capture_output=True, text=True)
        return InvocationResult(
            self.provider_id, resultado.returncode, resultado.stdout, resultado.stderr,
            resultado.returncode == 0, None, 0.0,
        )


class FalsoCapacidadNone(FalsoConforme):
    provider_id = "falso_capacidad_none"

    def detect(self) -> ProviderInfo:
        info = super().detect()
        info.capabilities = ProviderCapabilities(streaming=None)  # type: ignore[arg-type]
        return info


def _nombres_fallidos(reporte) -> list:
    return [c["nombre"] for c in reporte.chequeos if not c["ok"]]


class TestNivelesYReporte(unittest.TestCase):
    def test_niveles_en_orden(self):
        self.assertEqual(
            conformance.NIVELES_SOPORTE, ("contract-tested", "locally-smoke-tested", "live-validated")
        )

    def test_reporte_serializable_y_determinista(self):
        reporte = conformance.verificar_conformidad(FalsoConforme())
        self.assertEqual(reporte.to_json(), conformance.verificar_conformidad(FalsoConforme()).to_json())
        datos = json.loads(reporte.to_json())
        self.assertEqual(set(datos), {"provider_id", "nivel_alcanzado", "chequeos", "advertencias"})
        for chequeo in datos["chequeos"]:
            self.assertEqual(set(chequeo), {"nombre", "ok", "detalle", "evidencia"})


class TestProviderFalsoConformante(unittest.TestCase):
    def test_conformante_alcanza_contract_tested(self):
        reporte = conformance.verificar_conformidad(FalsoConforme())
        self.assertEqual(_nombres_fallidos(reporte), [])
        self.assertEqual(reporte.nivel_alcanzado, "contract-tested")
        self.assertTrue(all(c["evidencia"] == "fixture" for c in reporte.chequeos))

    def test_los_4_providers_reales_alcanzan_contract_tested(self):
        for provider_id, adapter in PROVIDER_REGISTRY.items():
            with self.subTest(provider=provider_id):
                reporte = conformance.verificar_conformidad(adapter)
                self.assertEqual(_nombres_fallidos(reporte), [])
                self.assertEqual(reporte.nivel_alcanzado, "contract-tested")


class TestDoblesCubrenOtrasViasDeProceso(unittest.TestCase):
    def test_adapter_con_popen_se_redirige_al_doble(self):
        reporte = conformance.verificar_conformidad(FalsoPopen())
        self.assertEqual(_nombres_fallidos(reporte), [])
        self.assertEqual(reporte.nivel_alcanzado, "contract-tested")

    def test_adapter_con_from_import_se_redirige_al_doble(self):
        reporte = conformance.verificar_conformidad(FalsoFromImport())
        self.assertEqual(_nombres_fallidos(reporte), [])
        self.assertEqual(reporte.nivel_alcanzado, "contract-tested")

    def test_popen_filtrando_secreto_se_detecta(self):
        class FalsoPopenFiltra(FalsoPopen):
            provider_id = "falso_popen_filtra"

            def invoke(self, request):
                proceso = subprocess.Popen(
                    [self.cli_command, request.prompt], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, env=dict(os.environ),
                )
                salida, error = proceso.communicate()
                return InvocationResult(self.provider_id, proceso.returncode, salida, error, True, None, 0.0)

        reporte = conformance.verificar_conformidad(FalsoPopenFiltra())
        self.assertIn("invoke_contrato_comando", _nombres_fallidos(reporte))


class TestAdvertencias(unittest.TestCase):
    def test_codex_ignora_model_y_effort_como_advertencia_no_falla(self):
        reporte = conformance.verificar_conformidad(PROVIDER_REGISTRY["codex"])
        self.assertEqual(reporte.nivel_alcanzado, "contract-tested")
        self.assertIn("codex: ignora model", reporte.advertencias)
        self.assertIn("codex: ignora effort", reporte.advertencias)
        self.assertIn("advertencias", json.loads(reporte.to_json()))

    def test_claude_code_respeta_model_y_effort(self):
        reporte = conformance.verificar_conformidad(PROVIDER_REGISTRY["claude_code"])
        self.assertEqual(reporte.advertencias, [])

    def test_los_providers_reales_no_fallan_por_advertencias(self):
        for adapter in PROVIDER_REGISTRY.values():
            self.assertEqual(conformance.verificar_conformidad(adapter).nivel_alcanzado, "contract-tested")


class TestProvidersNoConformantes(unittest.TestCase):
    def _verificar(self, clase, esperado):
        reporte = conformance.verificar_conformidad(clase())
        self.assertIn(esperado, _nombres_fallidos(reporte))
        self.assertIsNone(reporte.nivel_alcanzado)

    def test_sin_display_name(self):
        self._verificar(FalsoSinDisplay, "forma_adapter")

    def test_detect_con_cli_ausente_lanza(self):
        self._verificar(FalsoDetectLanza, "detect_cli_ausente")

    def test_filtra_secreto_por_cada_via(self):
        for clase in (FalsoInterpolaSecreto, FalsoFiltraCmdOpenai, FalsoFiltraEnv, FalsoFiltraInput):
            with self.subTest(clase=clase.__name__):
                reporte = conformance.verificar_conformidad(clase())
                self.assertIn("invoke_contrato_comando", _nombres_fallidos(reporte))
                self.assertIsNone(reporte.nivel_alcanzado)
                detalle = [c["detalle"] for c in reporte.chequeos if c["nombre"] == "invoke_contrato_comando"][0]
                self.assertIn("secretos", detalle)
                # El detalle nombra variables, nunca reproduce el valor sintetico.
                self.assertNotIn("sk-sintetico", detalle)

    def test_invoke_no_captura_oserror(self):
        self._verificar(FalsoInvokeLanza, "fallas_clasificadas")

    def test_capacidad_none(self):
        self._verificar(FalsoCapacidadNone, "forma_info_capacidades")


class TestSmokeYLive(unittest.TestCase):
    def test_smoke_con_cli_ausente_no_sube_de_nivel(self):
        with mock.patch("shutil.which", return_value=None):
            reporte = conformance.verificar_conformidad(FalsoConforme(), smoke=True)
        self.assertEqual(reporte.nivel_alcanzado, "contract-tested")
        smoke = [c for c in reporte.chequeos if c["nombre"] == conformance.NOMBRE_SMOKE][0]
        self.assertFalse(smoke["ok"])
        self.assertEqual(smoke["evidencia"], "real")

    def test_smoke_con_detect_disponible_sube_a_locally_smoke_tested(self):
        falso = SimpleNamespace(returncode=0, stdout="falsocli 1.0.0\n", stderr="")
        with mock.patch("shutil.which", return_value="/ruta/sintetica/falsocli"), mock.patch(
            "subprocess.run", return_value=falso
        ):
            reporte = conformance.verificar_conformidad(FalsoConforme(), smoke=True)
        self.assertEqual(reporte.nivel_alcanzado, "locally-smoke-tested")

    def test_sin_flag_smoke_no_se_ejecuta_el_chequeo(self):
        reporte = conformance.verificar_conformidad(FalsoConforme())
        self.assertNotIn(conformance.NOMBRE_SMOKE, [c["nombre"] for c in reporte.chequeos])

    def test_live_sin_variable_no_invoca_ni_sube(self):
        entorno = {k: v for k, v in os.environ.items() if k != conformance.VARIABLE_LIVE}
        with mock.patch.dict(os.environ, entorno, clear=True):
            reporte = conformance.verificar_conformidad(FalsoConforme(), live=True)
        self.assertEqual(reporte.nivel_alcanzado, "contract-tested")
        live = [c for c in reporte.chequeos if c["nombre"] == conformance.NOMBRE_LIVE][0]
        self.assertFalse(live["ok"])
        self.assertEqual(live["evidencia"], "none")  # L4: no hubo ejecucion real

    def test_chequeo_que_sale_con_systemexit_es_chequeo_fallido(self):
        class FalsoSalida(FalsoConforme):
            provider_id = "falso_salida"

            def detect(self):
                raise SystemExit(3)

        reporte = conformance.verificar_conformidad(FalsoSalida())
        self.assertIn("detect_cli_ausente", _nombres_fallidos(reporte))

    def test_detalle_no_copia_el_mensaje_de_la_excepcion(self):
        class FalsoMensaje(FalsoConforme):
            provider_id = "falso_mensaje"

            def detect(self):
                raise RuntimeError("MENSAJE-PRIVADO-123")

        self.assertNotIn("MENSAJE-PRIVADO-123", conformance.verificar_conformidad(FalsoMensaje()).to_json())

    def test_live_con_variable_y_doble_alcanza_live_validated(self):
        falso = SimpleNamespace(returncode=0, stdout="falsocli 1.0.0\nok", stderr="")
        with mock.patch.dict(os.environ, {conformance.VARIABLE_LIVE: "1"}), mock.patch(
            "shutil.which", return_value="/ruta/sintetica/falsocli"
        ), mock.patch("subprocess.run", return_value=falso):
            reporte = conformance.verificar_conformidad(FalsoConforme(), live=True)
        self.assertEqual(reporte.nivel_alcanzado, "live-validated")

    def test_contrato_fallido_anula_el_nivel_aunque_se_pida_live(self):
        with mock.patch.dict(os.environ, {conformance.VARIABLE_LIVE: "1"}):
            reporte = conformance.verificar_conformidad(FalsoSinDisplay(), smoke=True, live=True)
        self.assertIsNone(reporte.nivel_alcanzado)
        nombres = [c["nombre"] for c in reporte.chequeos]
        self.assertNotIn(conformance.NOMBRE_LIVE, nombres)


class TestSoporteDeclarado(unittest.TestCase):
    def test_todo_provider_del_registro_esta_declarado(self):
        self.assertEqual(set(conformance.SOPORTE_DECLARADO), set(PROVIDER_REGISTRY))

    def test_niveles_validos_y_evidencia_no_vacia(self):
        for provider_id, entrada in conformance.SOPORTE_DECLARADO.items():
            with self.subTest(provider=provider_id):
                self.assertIn(entrada["nivel_declarado"], conformance.NIVELES_SOPORTE)
                self.assertTrue(entrada["evidencia"].strip())

    def test_todos_declarados_contract_tested_ninguno_smoke_ni_live(self):
        for provider_id, entrada in conformance.SOPORTE_DECLARADO.items():
            self.assertEqual(entrada["nivel_declarado"], "contract-tested", provider_id)

    def test_declarado_no_excede_lo_probable_sin_live(self):
        for provider_id, entrada in conformance.SOPORTE_DECLARADO.items():
            reporte = conformance.verificar_conformidad(PROVIDER_REGISTRY[provider_id])
            self.assertEqual(reporte.nivel_alcanzado, entrada["nivel_declarado"], provider_id)

    @unittest.skipUnless(os.environ.get("HARMESSI_SMOKE_LOCAL") == "1", "smoke local opt-in: HARMESSI_SMOKE_LOCAL=1")
    @unittest.skipIf(shutil.which("claude") is None, "CLI 'claude' no disponible en este host")
    def test_smoke_real_de_claude_code_solo_opt_in(self):
        reporte = conformance.verificar_conformidad(PROVIDER_REGISTRY["claude_code"], smoke=True)
        self.assertEqual(reporte.nivel_alcanzado, "locally-smoke-tested")


class TestCli(unittest.TestCase):
    def _correr(self, argv):
        salida, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
            codigo = conformance.main(argv)
        return codigo, salida.getvalue(), error.getvalue()

    def test_live_sin_variable_da_exit_2_y_no_invoca(self):
        entorno = {k: v for k, v in os.environ.items() if k != conformance.VARIABLE_LIVE}
        run = mock.MagicMock()
        with mock.patch.dict(os.environ, entorno, clear=True), mock.patch("subprocess.run", run):
            codigo, _salida, error = self._correr(["--live"])
        self.assertEqual(codigo, 2)
        self.assertIn(conformance.VARIABLE_LIVE, error)
        run.assert_not_called()

    def test_json_de_un_provider_da_exit_0(self):
        codigo, salida, _error = self._correr(["--provider", "codex", "--json"])
        self.assertEqual(codigo, 0)
        datos = json.loads(salida)
        self.assertEqual(datos[0]["provider_id"], "codex")
        self.assertEqual(datos[0]["nivel_alcanzado"], "contract-tested")

    def test_todos_los_providers_texto_exit_0(self):
        codigo, salida, _error = self._correr([])
        self.assertEqual(codigo, 0)
        for provider_id in PROVIDER_REGISTRY:
            self.assertIn(provider_id, salida)

    def test_provider_desconocido_exit_2(self):
        codigo, _salida, _error = self._correr(["--provider", "no_existe"])
        self.assertEqual(codigo, 2)


if __name__ == "__main__":
    unittest.main()
