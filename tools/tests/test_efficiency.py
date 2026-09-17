"""Tests de `tools.dsguard.efficiency` (v0.4 Change 4:
20260916-agent-efficiency-and-token-governance) -- observabilidad de
eficiencia de agentes, de solo lectura, sobre `control.json` de un Change.

Sigue el mismo patrón de `test_scientific_validity.py`: funciones puras se
prueban sobre un `control.json` armado a mano en un directorio temporal
plano (sin `git init`); la integración CLI real (subprocess) sí usa un repo
git temporal, mismo criterio que `test_scientific_validity.py`/
`test_mlops_foundations.py`.
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

from dsguard import checks, core, efficiency  # noqa: E402

DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"


# --- Fixtures compartidas -----------------------------------------------------

def _sesion_base(**overrides) -> dict:
    base = {
        "id": "s1",
        "inicio_utc": "2026-01-01T00:00:00Z",
        "cierre_utc": None,
        "modo": "estandar",
        "presupuesto": {
            "minutos": 90,
            "max_tareas": 3,
            "max_roles": 2,
            "max_reintentos": 2,
            "max_rondas_revision": 2,
        },
        "deadline_utc": "2099-01-01T01:30:00Z",
        "minutos_consumidos": 10.0,
        "resultado": "dentro_de_presupuesto",
        "subagentes": {},
        "tareas": ["t1"],
        "roles": ["python-data-engineer"],
        "reintentos": 0,
        "rondas_revision": 0,
        "estado_final": "completada",
    }
    base.update(overrides)
    return base


def _remediacion_base(**overrides) -> dict:
    base = {
        "remediation_id": "r1",
        "finding_id": "f1",
        "origen": "python-data-engineer",
        "tipo": "bug",
        "estado": "abierta",
        "creado_utc": "2026-01-01T00:00:00Z",
        "ventanas": [
            {
                "ventana": 1,
                "max_intentos": 2,
                "autorizado_por": None,
                "fecha_autorizacion": None,
                "motivo": None,
                "intentos": [],
            }
        ],
        "resuelto_utc": None,
        "resultado_final": None,
    }
    base.update(overrides)
    return base


def _control_base(**overrides) -> dict:
    base = {"schema_version": 1, "sesiones": [], "remediaciones": []}
    base.update(overrides)
    return base


def _crear_repo_temporal(prefix: str = "efficiency_test_") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def _crear_repo_git_temporal(prefix: str = "efficiency_cli_test_") -> Path:
    repo = Path(tempfile.mkdtemp(prefix=prefix))
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)
    (repo / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=str(repo), check=True)
    return repo


def _correr_ds_guard(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DS_GUARD), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _escribir_control(change_dir: Path, control: dict) -> Path:
    change_dir.mkdir(parents=True, exist_ok=True)
    ruta = change_dir / "control.json"
    ruta.write_text(json.dumps(control, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


class _BaseRepo(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)


# --- evaluar_sesion --------------------------------------------------------

class TestEvaluarSesion(unittest.TestCase):
    def test_dentro_de_limites_pass(self):
        sesion = _sesion_base()
        resultados = efficiency.evaluar_sesion(sesion)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)
        self.assertEqual(resultados[0].code, efficiency.CODIGO_SESION_LIMITE)

    def test_excede_max_reintentos_warn_reusa_mensaje_de_chequear_limites(self):
        sesion = _sesion_base(reintentos=5)
        resultados = efficiency.evaluar_sesion(sesion)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].status, checks.STATUS_WARN)
        self.assertEqual(resultados[0].code, efficiency.CODIGO_SESION_LIMITE)
        self.assertIn("Reintentos (5) supera el máximo de la sesión (2)", resultados[0].message)

    def test_excede_varios_limites_un_warn_por_finding(self):
        sesion = _sesion_base(reintentos=5, rondas_revision=5, roles=["a", "b", "c"])
        resultados = efficiency.evaluar_sesion(sesion)
        self.assertEqual(len(resultados), 3)
        for r in resultados:
            self.assertEqual(r.status, checks.STATUS_WARN)

    def test_funciona_igual_para_sesion_activa(self):
        sesion = _sesion_base(estado_final="activa", cierre_utc=None)
        resultados = efficiency.evaluar_sesion(sesion)
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)


# --- evaluar_delegaciones_sesion --------------------------------------------

class TestEvaluarDelegacionesSesion(unittest.TestCase):
    def test_sin_max_roles_na(self):
        sesion = _sesion_base(presupuesto={"minutos": 90})
        r = efficiency.evaluar_delegaciones_sesion(sesion)[0]
        self.assertEqual(r.status, checks.STATUS_NA)
        self.assertEqual(r.code, efficiency.CODIGO_SESION_DELEGACIONES)

    def test_roles_bajo_el_maximo_pass(self):
        sesion = _sesion_base(roles=["a"])
        r = efficiency.evaluar_delegaciones_sesion(sesion)[0]
        self.assertEqual(r.status, checks.STATUS_PASS)

    def test_roles_en_o_sobre_el_maximo_warn(self):
        sesion = _sesion_base(roles=["a", "b"])
        r = efficiency.evaluar_delegaciones_sesion(sesion)[0]
        self.assertEqual(r.status, checks.STATUS_WARN)
        self.assertEqual(r.code, efficiency.CODIGO_SESION_DELEGACIONES)


# --- evaluar_remediacion -----------------------------------------------------

class TestEvaluarRemediacion(unittest.TestCase):
    def test_sin_ventanas_na(self):
        remediacion = _remediacion_base(ventanas=[])
        r = efficiency.evaluar_remediacion(remediacion)[0]
        self.assertEqual(r.status, checks.STATUS_NA)

    def test_ventana_agotada_warn_intentos(self):
        remediacion = _remediacion_base(
            ventanas=[{
                "ventana": 1,
                "max_intentos": 2,
                "intentos": [
                    {"attempt": 1, "causa": "a", "cambio_aplicado": "x", "resultado": "fallo", "session_id": "s1", "utc": "t1"},
                    {"attempt": 2, "causa": "b", "cambio_aplicado": "y", "resultado": "fallo", "session_id": "s1", "utc": "t2"},
                ],
            }]
        )
        resultados = efficiency.evaluar_remediacion(remediacion)
        codigos = [r.code for r in resultados]
        self.assertIn(efficiency.CODIGO_REMEDIACION_INTENTOS, codigos)
        for r in resultados:
            if r.code == efficiency.CODIGO_REMEDIACION_INTENTOS:
                self.assertEqual(r.status, checks.STATUS_WARN)

    def test_causas_repetidas_warn_adicional(self):
        remediacion = _remediacion_base(
            ventanas=[{
                "ventana": 1,
                "max_intentos": 5,
                "intentos": [
                    {"attempt": 1, "causa": "misma causa", "cambio_aplicado": "x", "resultado": "fallo", "session_id": "s1", "utc": "t1"},
                    {"attempt": 2, "causa": "misma causa", "cambio_aplicado": "y", "resultado": "fallo", "session_id": "s1", "utc": "t2"},
                ],
            }]
        )
        resultados = efficiency.evaluar_remediacion(remediacion)
        codigos = [r.code for r in resultados]
        self.assertIn(efficiency.CODIGO_REMEDIACION_REPETIDA, codigos)

    def test_causas_distintas_sin_warn_repetida(self):
        remediacion = _remediacion_base(
            ventanas=[{
                "ventana": 1,
                "max_intentos": 5,
                "intentos": [
                    {"attempt": 1, "causa": "causa a", "cambio_aplicado": "x", "resultado": "fallo", "session_id": "s1", "utc": "t1"},
                    {"attempt": 2, "causa": "causa b", "cambio_aplicado": "y", "resultado": "fallo", "session_id": "s1", "utc": "t2"},
                ],
            }]
        )
        resultados = efficiency.evaluar_remediacion(remediacion)
        codigos = [r.code for r in resultados]
        self.assertNotIn(efficiency.CODIGO_REMEDIACION_REPETIDA, codigos)

    def test_sin_senales_pass_unico(self):
        remediacion = _remediacion_base()
        resultados = efficiency.evaluar_remediacion(remediacion)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)


# --- evaluar_eficiencia_change ------------------------------------------------

class TestEvaluarEficienciaChange(_BaseRepo):
    def test_control_ausente_fail_technical_error_menciona_change(self):
        resultados = efficiency.evaluar_eficiencia_change(self.repo, "no-existe")
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].status, checks.STATUS_FAIL)
        self.assertEqual(resultados[0].kind, checks.KIND_TECHNICAL_ERROR)
        self.assertIn("no-existe", resultados[0].message)

    def test_control_corrupto_fail_technical_error(self):
        change_dir = self.repo / "openspec" / "changes" / "c1"
        change_dir.mkdir(parents=True, exist_ok=True)
        (change_dir / "control.json").write_text("esto no es json", encoding="utf-8")
        resultados = efficiency.evaluar_eficiencia_change(self.repo, "c1")
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].status, checks.STATUS_FAIL)
        self.assertEqual(resultados[0].kind, checks.KIND_TECHNICAL_ERROR)

    def test_change_archivado_tambien_reportable(self):
        change_dir = self.repo / "openspec" / "archive" / "c1"
        control = _control_base(sesiones=[_sesion_base()])
        _escribir_control(change_dir, control)
        resultados = efficiency.evaluar_eficiencia_change(self.repo, "c1")
        self.assertTrue(any(r.code == efficiency.CODIGO_SESION_LIMITE for r in resultados))

    def test_sin_sesiones_ni_remediaciones_listas_vacias(self):
        change_dir = self.repo / "openspec" / "changes" / "c1"
        _escribir_control(change_dir, _control_base())
        resultados = efficiency.evaluar_eficiencia_change(self.repo, "c1")
        self.assertEqual(resultados, [])

    def test_sesiones_y_remediaciones_combinadas(self):
        change_dir = self.repo / "openspec" / "changes" / "c1"
        control = _control_base(
            sesiones=[_sesion_base()],
            remediaciones=[_remediacion_base()],
        )
        _escribir_control(change_dir, control)
        resultados = efficiency.evaluar_eficiencia_change(self.repo, "c1")
        codigos = {r.code for r in resultados}
        self.assertIn(efficiency.CODIGO_SESION_LIMITE, codigos)
        self.assertIn(efficiency.CODIGO_SESION_DELEGACIONES, codigos)
        self.assertIn(efficiency.CODIGO_REMEDIACION_INTENTOS, codigos)

    def test_determinismo(self):
        change_dir = self.repo / "openspec" / "changes" / "c1"
        control = _control_base(
            sesiones=[_sesion_base()],
            remediaciones=[_remediacion_base()],
        )
        _escribir_control(change_dir, control)
        r1 = [r.to_dict() for r in efficiency.evaluar_eficiencia_change(self.repo, "c1")]
        r2 = [r.to_dict() for r in efficiency.evaluar_eficiencia_change(self.repo, "c1")]
        self.assertEqual(r1, r2)


# --- Read-only ---------------------------------------------------------------

class TestReadOnly(_BaseRepo):
    def test_no_modifica_control_json(self):
        change_dir = self.repo / "openspec" / "changes" / "c1"
        control = _control_base(
            sesiones=[_sesion_base(reintentos=5)],
            remediaciones=[_remediacion_base(
                ventanas=[{
                    "ventana": 1,
                    "max_intentos": 2,
                    "intentos": [
                        {"attempt": 1, "causa": "misma", "cambio_aplicado": "x", "resultado": "fallo", "session_id": "s1", "utc": "t1"},
                        {"attempt": 2, "causa": "misma", "cambio_aplicado": "y", "resultado": "fallo", "session_id": "s1", "utc": "t2"},
                    ],
                }]
            )],
        )
        ruta = _escribir_control(change_dir, control)
        antes = core.capturar_bytes(ruta)
        efficiency.evaluar_eficiencia_change(self.repo, "c1")
        despues = core.capturar_bytes(ruta)
        self.assertEqual(antes, despues)

    def test_efficiency_py_nunca_llama_funciones_de_escritura(self):
        codigo = (REPO_ORIGEN / "tools" / "dsguard" / "efficiency.py").read_text(encoding="utf-8")
        for prohibido in (
            "escribir_control(",
            "session_note(",
            "remediation_note(",
            "remediation_resolve(",
            "remediation_extend(",
            "session_start(",
            "session_close(",
            '"w")',
            "'w')",
        ):
            self.assertNotIn(prohibido, codigo, f"efficiency.py no debe contener {prohibido!r}")


class TestReadOnlyCli(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_cli_no_modifica_control_json(self):
        change_dir = self.repo / "openspec" / "changes" / "c1"
        control = _control_base(sesiones=[_sesion_base(reintentos=5)])
        ruta = _escribir_control(change_dir, control)
        antes = core.capturar_bytes(ruta)
        _correr_ds_guard(["efficiency", "report", "--change-id", "c1", "--json"], self.repo)
        despues = core.capturar_bytes(ruta)
        self.assertEqual(antes, despues)


# --- CLI -----------------------------------------------------------------------

class TestCli(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        change_dir = self.repo / "openspec" / "changes" / "c1"
        control = _control_base(sesiones=[_sesion_base(reintentos=5)])
        _escribir_control(change_dir, control)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_json_valido_con_resultados(self):
        resultado = _correr_ds_guard(
            ["efficiency", "report", "--change-id", "c1", "--json"], self.repo
        )
        payload = json.loads(resultado.stdout)
        self.assertIn("resultados", payload)
        self.assertTrue(any(r["status"] == checks.STATUS_WARN for r in payload["resultados"]))

    def test_texto_muestra_el_change_id(self):
        resultado = _correr_ds_guard(
            ["efficiency", "report", "--change-id", "c1"], self.repo
        )
        self.assertIn("c1", resultado.stdout)

    def test_exit_code_0_sin_fail(self):
        resultado = _correr_ds_guard(
            ["efficiency", "report", "--change-id", "c1", "--json"], self.repo
        )
        self.assertEqual(resultado.returncode, 0)

    def test_exit_code_1_con_control_ausente(self):
        resultado = _correr_ds_guard(
            ["efficiency", "report", "--change-id", "no-existe", "--json"], self.repo
        )
        self.assertEqual(resultado.returncode, 1)
        payload = json.loads(resultado.stdout)
        self.assertEqual(payload["resultados"][0]["kind"], checks.KIND_TECHNICAL_ERROR)


if __name__ == "__main__":
    unittest.main()
