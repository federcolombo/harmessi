"""Tests de `ds_guard dependency install` (M11, T3b-2 de
`20260930-project-extension-and-installer-integration`): instalación
gobernada aditiva de una dependencia pre-aprobada, R24-R41 de `spec.md`.

A diferencia de `test_ds_guard_exec.py` (que corre `ds_guard.py` como
subproceso real), acá se importa `ds_guard` como módulo y se llama
`ds_guard.main([...])` EN PROCESO, con `leadrun.scripts.ejecutar_script`
mockeado: el `argv` final de `dependency install` es
`<intérprete> -m pip install --no-deps <nombre>==<versión>`, que si se
ejecutara de verdad pegaría contra la red real (PyPI) -- inaceptable para un
test hermético. El resto del pipeline (allowlist, `ExecutionRequest`,
`leadrun_runtime.ejecutar`, persistencia de `ExecutionRecord`) corre real, sin
mockear -- el mock es exclusivamente el punto de `subprocess.run` real
(`leadrun.scripts.ejecutar_script`), mismo principio que usa Change 2 para
separar reconocimiento/orquestación de ejecución real."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ORIGEN = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(REPO_ORIGEN / "tools"))

import ds_guard  # noqa: E402
import launcher_common  # noqa: E402
from dsguard import core  # noqa: E402
from leadrun import allowlist as leadrun_allowlist  # noqa: E402
from leadrun import scripts as leadrun_scripts  # noqa: E402

CHANGE_ID = "20260929-lead-execution-runtime"

_GUARDRAILS_AUTONOMOUS = {
    "version": 2,
    "autonomy": {
        "version": 2,
        "mode": "autonomous",
        "limits": {"max_sessions": 1, "max_total_minutes": 60},
    },
}

_GUARDRAILS_SUPERVISED = {
    "version": 2,
    "autonomy": {
        "version": 2,
        "mode": "supervised",
    },
}

_EJECUCION_OK = {
    "exit_code": 0,
    "duration_seconds": 0.01,
    "stdout_summary": "Successfully installed paquete-prueba-1.5\n",
    "stderr_summary": "",
    "timed_out": False,
}

_EJECUCION_FALLIDA = {
    "exit_code": 1,
    "duration_seconds": 0.02,
    "stdout_summary": "",
    "stderr_summary": "ERROR: no se pudo instalar\n",
    "timed_out": False,
}


def _crear_repo_git_temporal(prefix: str = "dep_install_") -> Path:
    repo = Path(tempfile.mkdtemp(prefix=prefix))
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)
    (repo / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=str(repo), check=True)
    return repo


def _escribir_guardrails(repo: Path, datos: dict) -> Path:
    directorio = repo / ".claude"
    directorio.mkdir(parents=True, exist_ok=True)
    ruta = directorio / "guardrails.json"
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return ruta


def _scaffold_change(repo: Path, change_id: str, dependencias_preaprobadas: list) -> Path:
    change_dir = repo / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True, exist_ok=True)
    (change_dir / "tasks.md").write_text("estado: implementacion\n", encoding="utf-8")
    control = {
        "schema_version": 1,
        "change_id": change_id,
        "modo": "abreviado",
        "origen": "test",
        "creado_utc": core.ahora_utc(),
        "baseline": {"commit": "0" * 40, "rama": "main", "capturado_utc": core.ahora_utc()},
        "alcance": {"rutas_autorizadas": []},
        "aprobaciones": [],
        "transiciones": [],
        "sesiones": [],
        "dependencias_preaprobadas": dependencias_preaprobadas,
    }
    core.escribir_control(change_dir / "control.json", control)
    return change_dir


class _BaseRepoGit(unittest.TestCase):
    NOMBRE = "paquete-prueba"
    VERSION = "1.5"
    RANGO = ">=1.2,<2"

    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        self.change_dir = _scaffold_change(
            self.repo, CHANGE_ID, [{"nombre": self.NOMBRE, "rango": self.RANGO}]
        )
        self.control_path = self.change_dir / "control.json"
        self._cwd_previo = Path.cwd()
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self._cwd_previo)
        shutil.rmtree(self.repo, ignore_errors=True)

    def _ejecutar(self, nombre=None, version=None, extra_argv=None, resultado_mock=None):
        argv = [
            "dependency",
            "install",
            "--change-id",
            CHANGE_ID,
            "--nombre",
            nombre if nombre is not None else self.NOMBRE,
            "--version",
            version if version is not None else self.VERSION,
            "--json",
        ]
        if extra_argv:
            argv.extend(extra_argv)
        stdout = io.StringIO()
        stderr = io.StringIO()
        valor_mock = dict(resultado_mock) if resultado_mock is not None else dict(_EJECUCION_OK)
        with mock.patch.object(leadrun_scripts, "ejecutar_script", return_value=valor_mock) as m:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                codigo = ds_guard.main(argv)
        return codigo, stdout.getvalue(), stderr.getvalue(), m

    def _interprete_esperado(self) -> str:
        venv_dir = launcher_common.resolver_venv_dir(self.repo)
        ruta = launcher_common.ruta_interprete_venv(self.repo, venv_dir)
        return leadrun_allowlist.normalizar_interprete(str(ruta))

    def _unico_record(self) -> dict:
        directorio = self.repo / ".harmessi" / "executions"
        registros = list(directorio.iterdir())
        self.assertEqual(len(registros), 1, f"se esperaba exactamente 1 ExecutionRecord, hay {len(registros)}")
        return json.loads((registros[0] / "record.json").read_text(encoding="utf-8"))


class TestDependenciaPreaprobadaDentroDeRango(_BaseRepoGit):
    """Caso 1: dependencia pre-aprobada, versión exacta dentro del rango -> procede."""

    def test_instalacion_procede_en_autonomous(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar()
        self.assertEqual(codigo, 0, stderr)
        self.assertTrue(mock_ejecutar.called)
        record = self._unico_record()
        self.assertEqual(record["command_form"], "dependency_install")
        self.assertEqual(record["exit_code"], 0)
        self.assertEqual(record["mode"], "autonomous")
        self.assertEqual(record["executed_by"], "lead")

    def test_instalacion_procede_en_supervised_sin_aprobacion_por_artefacto_registrada(self):
        # Hallazgo #3 del writer, corregido por el Lead: dependency install
        # NO debe quedar bloqueado en supervised solo por no tener una
        # aprobación por-artefacto registrada -- la clasificación (R25) ya
        # autorizó la acción.
        _escribir_guardrails(self.repo, _GUARDRAILS_SUPERVISED)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar()
        self.assertEqual(codigo, 0, stderr)
        record = self._unico_record()
        self.assertEqual(record["mode"], "supervised")
        self.assertEqual(record["executed_by"], "lead")


class TestDependenciaNoPreaprobada(_BaseRepoGit):
    """Caso 2: dependencia NO pre-aprobada -> rechazada, exit 2, sin ExecutionRequest."""

    def test_nombre_no_listado_rechazado_sin_ejecutar(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar(nombre="otro-paquete-no-aprobado")
        self.assertEqual(codigo, 2, stdout)
        self.assertFalse(mock_ejecutar.called)
        self.assertFalse((self.repo / ".harmessi" / "executions").exists())


class TestVersionFueraDeRango(_BaseRepoGit):
    """Caso 3: versión fuera del rango aprobado -> rechazada, exit 2 (STOP new_dependency)."""

    def test_version_fuera_de_rango_rechazada(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar(version="3.0")
        self.assertEqual(codigo, 2, stdout)
        self.assertFalse(mock_ejecutar.called)
        self.assertFalse((self.repo / ".harmessi" / "executions").exists())


class TestFormaDeNombreNoSoportada(_BaseRepoGit):
    """Caso 4: nombre con forma no soportada (R35) -> rechazado ANTES de clasificar."""

    def test_url_rechazada(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar(nombre="https://example.com/pkg")
        self.assertEqual(codigo, 2, stdout)
        self.assertFalse(mock_ejecutar.called)

    def test_extras_rechazados(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar(nombre="paquete-prueba[extra]")
        self.assertEqual(codigo, 2, stdout)
        self.assertFalse(mock_ejecutar.called)

    def test_multiples_paquetes_rechazados(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar(nombre="paquete-prueba otro-paquete")
        self.assertEqual(codigo, 2, stdout)
        self.assertFalse(mock_ejecutar.called)

    def test_metacaracter_de_shell_rechazado(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar(nombre="paquete-prueba;rm -rf /")
        self.assertEqual(codigo, 2, stdout)
        self.assertFalse(mock_ejecutar.called)


class TestCanonicalizacionNoAutorizaPaqueteDistinto(_BaseRepoGit):
    """Caso 5: nombre canónicamente equivalente al pre-aprobado -> se comporta
    determinísticamente, sin autorizar un paquete distinto."""

    def test_separador_y_mayusculas_distintos_sigue_coincidiendo(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        # Pre-aprobado: "paquete-prueba". Solicitado: "Paquete_Prueba"
        # (misma forma canónica PEP 503) -> debe seguir autorizado.
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar(nombre="Paquete_Prueba")
        self.assertEqual(codigo, 0, stderr)
        self.assertTrue(mock_ejecutar.called)

    def test_nombre_genuinamente_distinto_no_autorizado(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar(nombre="paquete-prueba-2")
        self.assertEqual(codigo, 2, stdout)
        self.assertFalse(mock_ejecutar.called)


class TestInterpreteResueltoPorLauncherCommon(_BaseRepoGit):
    """Caso 6: el intérprete efectivamente usado es el resuelto por
    `launcher_common.ruta_interprete_venv`, nunca uno libre/inventado.

    Nota: el `ExecutionRecord` persistido tiene `argv[0]` REDACTADO
    (`_redactar_argv` de `runtime.py`, Change 2, ya existente y reusado sin
    caso especial por R41: cualquier ruta absoluta en `argv` se trata como
    un localizador físico -- el intérprete resuelto SIEMPRE es una ruta
    absoluta por construcción). Por eso esta prueba verifica el `argv` que
    `leadrun.runtime.ejecutar` recibió ANTES de redactar (capturado por el
    mock de `ejecutar_script`, que corre después de la redacción... en
    realidad ANTES -- `ejecutar_script` recibe `request.argv` sin redactar,
    la redacción ocurre sobre el resultado ya vuelto, ver `runtime.py`), no
    el `record.json` ya redactado."""

    def test_argv_usa_el_interprete_del_venv_del_proyecto(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar()
        self.assertEqual(codigo, 0, stderr)
        request_recibido = mock_ejecutar.call_args[0][0]
        self.assertEqual(request_recibido.argv[0], self._interprete_esperado())
        # El record persistido, en cambio, queda redactado (comportamiento
        # ya existente de Change 2, reusado sin caso especial, R41).
        record = self._unico_record()
        self.assertEqual(record["argv"][0], "[REDACTADO]")


class TestArgvPatronDe6TokensConVersionExacta(_BaseRepoGit):
    """Caso 7: el argv persistido tiene EXACTAMENTE el patrón de 6 tokens con
    la VERSIÓN EXACTA -- el rango aprobado nunca llega a pip tal cual."""

    def test_argv_tiene_6_tokens_con_pin_exacto_no_el_rango(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar(version="1.5")
        self.assertEqual(codigo, 0, stderr)
        record = self._unico_record()
        argv = record["argv"]
        self.assertEqual(len(argv), 6)
        self.assertEqual(tuple(argv[1:5]), ("-m", "pip", "install", "--no-deps"))
        self.assertEqual(argv[5], f"{self.NOMBRE}==1.5")
        # El rango aprobado (">=1.2,<2") NUNCA aparece tal cual en el argv.
        self.assertNotIn(self.RANGO, argv[5])
        self.assertNotIn(">=", argv[5])
        self.assertNotIn("<", argv[5])


class TestApprovalConFormaExactaDeR28(_BaseRepoGit):
    """Caso 8: `ExecutionRecord.approval` tiene exactamente la forma de R28
    en modo supervised (en autonomous, `approval` es `None` por la
    invariante de `ExecutionRecord`, ver docstring de `cmd_dependency_install`)."""

    def test_approval_none_en_autonomous(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar()
        self.assertEqual(codigo, 0, stderr)
        record = self._unico_record()
        self.assertIsNone(record["approval"])

    def test_approval_dependency_preapproval_en_supervised(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_SUPERVISED)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar()
        self.assertEqual(codigo, 0, stderr)
        record = self._unico_record()
        self.assertEqual(
            record["approval"],
            {
                "tipo": "dependency_preapproval",
                "dependencia": {"nombre": self.NOMBRE, "version": self.VERSION},
                "declarado_en": "proposal.md",
            },
        )


class TestNoDepsSiempreObligatorio(_BaseRepoGit):
    """Caso 9: dependencia transitiva faltante NUNCA se autoinstala --
    `--no-deps` está SIEMPRE presente en el argv construido."""

    def test_no_deps_presente_en_todas_las_instalaciones(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar()
        self.assertEqual(codigo, 0, stderr)
        record = self._unico_record()
        self.assertIn("--no-deps", record["argv"])


class TestCodeHashSiempreNone(_BaseRepoGit):
    """`code_hash` de `dependency_install` es siempre `None` (mismo motivo
    que `cli_diagnostic`: no hay un único archivo canónico que hashear)."""

    def test_code_hash_none(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar()
        self.assertEqual(codigo, 0, stderr)
        record = self._unico_record()
        self.assertIsNone(record["code_hash"])


class TestEvidenciaEntornoPersistidaR38(_BaseRepoGit):
    """R38 (hallazgo #2 del reviewer T8, corregido): la evidencia de entorno
    pre/post se persiste de forma trazable junto al `ExecutionRecord`, no
    solo se usa para condicionar warnings efímeros a stderr."""

    def test_dependency_evidence_json_persistido_con_los_campos_de_r38(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar()
        self.assertEqual(codigo, 0, stderr)
        payload = json.loads(stdout)
        execution_id = payload["execution_id"]

        ruta_evidencia = (
            self.repo / ".harmessi" / "executions" / execution_id / "dependency_evidence.json"
        )
        self.assertTrue(ruta_evidencia.exists())
        evidencia = json.loads(ruta_evidencia.read_text(encoding="utf-8"))

        self.assertEqual(evidencia["paquete"], self.NOMBRE)
        self.assertEqual(evidencia["version_solicitada"], self.VERSION)
        self.assertEqual(evidencia["execution_id"], execution_id)
        self.assertIn("version_previa", evidencia)
        self.assertIn("version_posterior", evidencia)
        self.assertIn("resultado", evidencia)
        self.assertIn("referencia_preaprobacion", evidencia)
        self.assertIn("duration_seconds", evidencia)
        self.assertIn("exit_code", evidencia)
        self.assertEqual(
            evidencia["referencia_preaprobacion"],
            {
                "tipo": "dependency_preapproval",
                "dependencia": {"nombre": self.NOMBRE, "version": self.VERSION},
                "declarado_en": "proposal.md",
            },
        )

    def test_evidencia_persistida_tambien_en_supervised(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_SUPERVISED)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar()
        self.assertEqual(codigo, 0, stderr)
        payload = json.loads(stdout)
        execution_id = payload["execution_id"]
        ruta_evidencia = (
            self.repo / ".harmessi" / "executions" / execution_id / "dependency_evidence.json"
        )
        self.assertTrue(ruta_evidencia.exists())


class TestDistribucionesInesperadasR39(_BaseRepoGit):
    """R39 (hallazgo #2 del reviewer T8, corregido): una distribución
    inesperada en el post se reporta como `CheckResult(kind=technical_error)`
    estructurado (no solo texto en stderr), sin STOP nuevo."""

    def test_distribucion_inesperada_produce_check_result_technical_error(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        evidencia_pre = {"version_previa": None, "distribuciones": {"paquete-existente"}}
        evidencia_post = {
            "version_previa": self.VERSION,
            "distribuciones": {"paquete-existente", self.NOMBRE, "paquete-inesperado"},
        }
        with mock.patch.object(
            ds_guard, "_capturar_evidencia_entorno", side_effect=[evidencia_pre, evidencia_post]
        ):
            codigo, stdout, stderr, mock_ejecutar = self._ejecutar()
        self.assertEqual(codigo, 0, stderr)
        self.assertIn("DEPENDENCY-UNEXPECTED-INSTALL", stdout)
        self.assertIn("paquete-inesperado", stdout)
        self.assertIn("technical_error", stdout)

        # La distribución inesperada también queda en la evidencia persistida.
        payload = json.loads(stdout.splitlines()[-1]) if stdout.strip().endswith("}") else None
        # (el stdout mezcla el bloque de R39 impreso aparte + el --json de
        # _ejecutar_exec_comun; buscamos el execution_id en cualquiera de las
        # líneas JSON presentes)
        execution_id = None
        for linea in stdout.splitlines():
            try:
                data = json.loads(linea)
            except ValueError:
                continue
            if "execution_id" in data:
                execution_id = data["execution_id"]
        self.assertIsNotNone(execution_id)
        ruta_evidencia = (
            self.repo / ".harmessi" / "executions" / execution_id / "dependency_evidence.json"
        )
        evidencia = json.loads(ruta_evidencia.read_text(encoding="utf-8"))
        self.assertIn("paquete-inesperado", evidencia["distribuciones_inesperadas"])

    def test_sin_distribucion_inesperada_no_reporta_nada_de_r39(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar()
        self.assertEqual(codigo, 0, stderr)
        self.assertNotIn("DEPENDENCY-UNEXPECTED-INSTALL", stdout)


class TestModoResueltoSinDobleLlamada(_BaseRepoGit):
    """R25/R28 (hallazgo #3 del reviewer T8, corregido): `cmd_dependency_install`
    resuelve `modo` una sola vez y lo pasa explícitamente a
    `_ejecutar_exec_comun` (`modo_resuelto`) -- evita la doble llamada a
    `_resolver_modo_autonomia` y la ventana TOCTOU teórica que eso abría."""

    def test_resolver_modo_autonomia_se_llama_una_sola_vez(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        with mock.patch.object(
            ds_guard, "_resolver_modo_autonomia", wraps=ds_guard._resolver_modo_autonomia
        ) as mock_resolver:
            codigo, stdout, stderr, mock_ejecutar = self._ejecutar()
        self.assertEqual(codigo, 0, stderr)
        self.assertEqual(mock_resolver.call_count, 1)


class TestEvidenciaSePersisteAunConInstalacionFallida(_BaseRepoGit):
    """Hallazgo del reviewer T8 (ciclo 2), corregido: antes, un
    `exit_code != 0` de la instalación saltaba por completo R29/R38/R39 --
    justo el caso donde esa evidencia importa más. Ahora se captura/persiste
    siempre que hubo una ejecución real, y el exit code devuelto sigue
    reflejando el fallo real (nunca se enmascara como éxito)."""

    def test_exit_code_fallido_se_propaga_sin_enmascarar(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar(resultado_mock=_EJECUCION_FALLIDA)
        self.assertNotEqual(codigo, 0)

    def test_evidencia_persistida_aun_cuando_la_instalacion_falla(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar(resultado_mock=_EJECUCION_FALLIDA)
        self.assertNotEqual(codigo, 0)

        directorio = self.repo / ".harmessi" / "executions"
        registros = list(directorio.iterdir())
        self.assertEqual(len(registros), 1)
        execution_id = registros[0].name

        ruta_evidencia = directorio / execution_id / "dependency_evidence.json"
        self.assertTrue(ruta_evidencia.exists(), "la evidencia debe persistirse incluso si la instalación falló")
        evidencia = json.loads(ruta_evidencia.read_text(encoding="utf-8"))
        self.assertEqual(evidencia["resultado"], "instalacion_fallida")
        self.assertEqual(evidencia["exit_code"], 1)
        self.assertEqual(evidencia["execution_id"], execution_id)

    def test_solicitud_rechazada_por_clasificacion_no_persiste_evidencia(self):
        # Caso de control: si la solicitud se rechaza ANTES de ejecutar nada
        # (R25, clasificación), nunca hubo un ExecutionRecord real -- no hay
        # nada que persistir, y el directorio de executions ni se crea.
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        codigo, stdout, stderr, mock_ejecutar = self._ejecutar(nombre="otro-paquete-no-aprobado")
        self.assertEqual(codigo, 2, stdout)
        self.assertFalse(mock_ejecutar.called)
        self.assertFalse((self.repo / ".harmessi" / "executions").exists())


if __name__ == "__main__":
    unittest.main()
