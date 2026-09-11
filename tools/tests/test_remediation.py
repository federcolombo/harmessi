"""Tests de bounded remediation (Bloque 5, `20260910-decision-ledger-bounded-
remediation`): `control["remediaciones"]` (`tools/dsguard/sdd.py`), su
integración con `session_note`, y la extensión de `hook_presupuesto.py`.

La mayoría de los tests llaman directamente a `tools.dsguard.sdd` sobre un
`control` dict en memoria, sin necesidad de git ni de CLI (mismo criterio que
`test_kdd.py` para las funciones que no lo requieren). Se agrega al menos un
test de integración CLI real (`subprocess.run` contra `tools/ds_guard.py`)
para `remediation resolve`/`extend`, y un test directo de
`dsguard.hook_presupuesto.evaluar()` para el chequeo de límite de reintentos.
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

from dsguard import core, hook_presupuesto, sdd  # noqa: E402

DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"


def _crear_dir_temporal(prefix: str = "remediation_test_") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def _control_con_sesion(max_reintentos: int = 2) -> dict:
    control = {
        "schema_version": 1,
        "change_id": "20260910-x",
        "modo": "completo",
        "sesiones": [],
    }
    sdd.session_start(control, minutos=90, max_reintentos=max_reintentos)
    return control


class TestRemediationNoteVentanaUno(unittest.TestCase):
    def setUp(self):
        self.control = _control_con_sesion(max_reintentos=10)

    def test_intentos_1_a_n_permitidos_y_n_mas_1_denegado(self):
        max_intentos = 2
        for i in range(max_intentos):
            ok, findings, remediation_id = sdd.remediation_note(
                self.control,
                "bug",
                causa=f"causa {i}",
                cambio_aplicado="fix",
                resultado="parcial",
                session_id="s1",
                finding_id="F1",
                max_intentos_default=max_intentos,
            )
            self.assertTrue(ok, findings)
            self.assertEqual(remediation_id, "r1")

        ok, findings, remediation_id = sdd.remediation_note(
            self.control,
            "bug",
            causa="causa 3",
            cambio_aplicado="fix",
            resultado="parcial",
            session_id="s1",
            finding_id="F1",
            max_intentos_default=max_intentos,
        )
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "REMEDIACION-LIMITE")
        self.assertIsNone(remediation_id)
        remediacion = self.control["remediaciones"][0]
        self.assertEqual(len(remediacion["ventanas"][0]["intentos"]), max_intentos)

    def test_bug_sin_finding_id_se_rehusa(self):
        ok, findings, _ = sdd.remediation_note(
            self.control, "bug", "c", "ca", "r", "s1", finding_id=None
        )
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "REMEDIACION-FINDING-REQUERIDO")
        self.assertEqual(self.control.get("remediaciones", []), [])

    def test_metodologica_sin_finding_id_se_rehusa(self):
        ok, findings, _ = sdd.remediation_note(
            self.control, "metodologica", "c", "ca", "r", "s1", finding_id=""
        )
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "REMEDIACION-FINDING-REQUERIDO")

    def test_retry_tecnico_sin_finding_id_permitido(self):
        ok, findings, remediation_id = sdd.remediation_note(
            self.control, "retry_tecnico", "c", "ca", "r", "s1", finding_id=None
        )
        self.assertTrue(ok, findings)
        self.assertEqual(remediation_id, "r1")
        self.assertIsNone(self.control["remediaciones"][0]["finding_id"])

    def test_tipo_invalido_se_rehusa(self):
        ok, findings, _ = sdd.remediation_note(
            self.control, "cambio_de_enfoque", "c", "ca", "r", "s1", finding_id="F1"
        )
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "REMEDIACION-TIPO-INVALIDO")

    def test_tipo_inconsistente_se_rehusa(self):
        sdd.remediation_note(self.control, "bug", "c", "ca", "r", "s1", finding_id="F1")
        ok, findings, _ = sdd.remediation_note(
            self.control, "metodologica", "c2", "ca2", "r2", "s1", finding_id="F1"
        )
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "REMEDIACION-TIPO-INCONSISTENTE")

    def test_retry_tecnico_sin_finding_id_no_acumula_entre_llamadas(self):
        """`_hallar_remediacion` devuelve siempre `None` si `finding_id` es
        `None` (ver `sdd.py`): cada llamada sucesiva a `remediation_note` con
        `remediation_tipo="retry_tecnico"` y sin `finding_id` crea una
        remediación nueva e independiente (`r1`, `r2`, `r3`, cada una con su
        propia ventana 1 desde cero), nunca reutiliza ni bloquea por límite.
        El único freno real para esta secuencia es el agregado
        `sesiones[].reintentos`, no `remediaciones[]`."""
        remediation_ids = []
        for i in range(3):
            ok, findings, remediation_id = sdd.remediation_note(
                self.control,
                "retry_tecnico",
                causa=f"causa {i}",
                cambio_aplicado="reintentar",
                resultado="parcial",
                session_id="s1",
                finding_id=None,
                max_intentos_default=1,
            )
            self.assertTrue(ok, findings)
            remediation_ids.append(remediation_id)
            self.assertEqual(len(self.control["remediaciones"]), i + 1)

        # Cada llamada creó una remediación distinta (r1, r2, r3), nunca
        # reutilizó la anterior pese a que cada una agotó su ventana 1
        # (max_intentos_default=1) en el mismo intento que la creó.
        self.assertEqual(remediation_ids, ["r1", "r2", "r3"])
        for remediacion in self.control["remediaciones"]:
            self.assertIsNone(remediacion["finding_id"])
            self.assertEqual(len(remediacion["ventanas"]), 1)
            self.assertEqual(len(remediacion["ventanas"][0]["intentos"]), 1)


class TestRemediationResolve(unittest.TestCase):
    def setUp(self):
        self.control = _control_con_sesion(max_reintentos=10)
        sdd.remediation_note(self.control, "bug", "c", "ca", "r", "s1", finding_id="F1")

    def test_resolve_valido_conserva_intentos(self):
        remediation_id = self.control["remediaciones"][0]["remediation_id"]
        ok, findings = sdd.remediation_resolve(self.control, remediation_id, "arreglado")
        self.assertTrue(ok)
        self.assertEqual(findings, [])
        remediacion = self.control["remediaciones"][0]
        self.assertEqual(remediacion["estado"], "resuelta")
        self.assertEqual(remediacion["resultado_final"], "arreglado")
        self.assertEqual(len(remediacion["ventanas"][0]["intentos"]), 1)

    def test_segundo_resolve_denegado(self):
        remediation_id = self.control["remediaciones"][0]["remediation_id"]
        sdd.remediation_resolve(self.control, remediation_id, "arreglado")
        ok, findings = sdd.remediation_resolve(self.control, remediation_id, "otra vez")
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "REMEDIACION-YA-RESUELTA")
        self.assertEqual(self.control["remediaciones"][0]["resultado_final"], "arreglado")

    def test_intento_tras_resolve_denegado(self):
        remediation_id = self.control["remediaciones"][0]["remediation_id"]
        sdd.remediation_resolve(self.control, remediation_id, "arreglado")
        ok, findings, _ = sdd.remediation_note(
            self.control, "bug", "c2", "ca2", "r2", "s1", finding_id="F1"
        )
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "REMEDIACION-RESUELTA")

    def test_resolve_inexistente(self):
        ok, findings = sdd.remediation_resolve(self.control, "r999", "x")
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "REMEDIACION-INEXISTENTE")


class TestRemediationExtend(unittest.TestCase):
    def setUp(self):
        self.control = _control_con_sesion(max_reintentos=10)
        sdd.remediation_note(self.control, "bug", "c", "ca", "r", "s1", finding_id="F1", max_intentos_default=1)
        # Agotar la ventana 1 (max_intentos=1 en la creación).
        sdd.remediation_note(self.control, "bug", "c2", "ca2", "r2", "s1", finding_id="F1")

    def test_extend_agrega_ventana_sin_tocar_la_anterior(self):
        remediation_id = self.control["remediaciones"][0]["remediation_id"]
        ventana_1_antes = json.dumps(self.control["remediaciones"][0]["ventanas"][0], sort_keys=True)

        ok, findings, ventana = sdd.remediation_extend(
            self.control, remediation_id, "federico", "2026-09-10", "más margen", max_intentos=2
        )
        self.assertTrue(ok, findings)
        self.assertEqual(ventana, 2)

        ventana_1_despues = json.dumps(self.control["remediaciones"][0]["ventanas"][0], sort_keys=True)
        self.assertEqual(ventana_1_antes, ventana_1_despues)
        self.assertEqual(len(self.control["remediaciones"][0]["ventanas"]), 2)

    def test_tras_extend_intento_nuevo_se_agrega_a_ventana_2_hasta_su_maximo(self):
        remediation_id = self.control["remediaciones"][0]["remediation_id"]
        sdd.remediation_extend(self.control, remediation_id, "federico", "2026-09-10", "más margen", max_intentos=2)

        ok, findings, _ = sdd.remediation_note(
            self.control, "bug", "c3", "ca3", "r3", "s1", finding_id="F1"
        )
        self.assertTrue(ok, findings)
        remediacion = self.control["remediaciones"][0]
        self.assertEqual(len(remediacion["ventanas"][1]["intentos"]), 1)
        self.assertEqual(len(remediacion["ventanas"][0]["intentos"]), 1)  # ventana 1 intacta

        ok2, findings2, _ = sdd.remediation_note(
            self.control, "bug", "c4", "ca4", "r4", "s1", finding_id="F1"
        )
        self.assertTrue(ok2, findings2)
        self.assertEqual(len(remediacion["ventanas"][1]["intentos"]), 2)

        # Ventana 2 agotada (max_intentos=2): un tercer intento se rehúsa.
        ok3, findings3, _ = sdd.remediation_note(
            self.control, "bug", "c5", "ca5", "r5", "s1", finding_id="F1"
        )
        self.assertFalse(ok3)
        self.assertEqual(findings3[0].codigo, "REMEDIACION-LIMITE")

    def test_ventana_3_requiere_nuevo_extend_con_autorizacion(self):
        remediation_id = self.control["remediaciones"][0]["remediation_id"]
        sdd.remediation_extend(self.control, remediation_id, "federico", "2026-09-10", "más margen", max_intentos=1)
        sdd.remediation_note(self.control, "bug", "c3", "ca3", "r3", "s1", finding_id="F1")
        # Ventana 2 agotada (max_intentos=1).
        ok, findings, _ = sdd.remediation_note(
            self.control, "bug", "c4", "ca4", "r4", "s1", finding_id="F1"
        )
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "REMEDIACION-LIMITE")

        ok_extend, findings_extend, ventana = sdd.remediation_extend(
            self.control, remediation_id, "federico", "2026-09-11", "tercera ventana", max_intentos=1
        )
        self.assertTrue(ok_extend, findings_extend)
        self.assertEqual(ventana, 3)

        ok2, findings2, _ = sdd.remediation_note(
            self.control, "bug", "c5", "ca5", "r5", "s1", finding_id="F1"
        )
        self.assertTrue(ok2, findings2)

    def test_extend_sobre_remediacion_resuelta_se_rehusa(self):
        remediation_id = self.control["remediaciones"][0]["remediation_id"]
        sdd.remediation_resolve(self.control, remediation_id, "cerrado")
        ok, findings, ventana = sdd.remediation_extend(
            self.control, remediation_id, "federico", "2026-09-10", "motivo", max_intentos=2
        )
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "REMEDIACION-RESUELTA")
        self.assertIsNone(ventana)

    def test_extend_con_campo_vacio_se_rehusa(self):
        remediation_id = self.control["remediaciones"][0]["remediation_id"]
        ok, findings, ventana = sdd.remediation_extend(
            self.control, remediation_id, "", "2026-09-10", "motivo", max_intentos=2
        )
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "REMEDIACION-CAMPO-VACIO")

    def test_extend_inexistente(self):
        ok, findings, ventana = sdd.remediation_extend(
            self.control, "r999", "federico", "2026-09-10", "motivo"
        )
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "REMEDIACION-INEXISTENTE")


class TestSessionNoteIntegracion(unittest.TestCase):
    """Integración de `remediation_note` dentro de `session_note` (R18):
    el agregado `sesiones[].reintentos` solo avanza si la remediación
    también avanzó."""

    def setUp(self):
        self.control = _control_con_sesion(max_reintentos=10)

    def test_reintento_con_remediation_tipo_incrementa_ambos_contadores(self):
        sdd.session_note(
            self.control,
            rol="python-data-engineer",
            tipo="reintento",
            finding_id="F1",
            remediation_tipo="bug",
            causa="c",
            cambio_aplicado="ca",
            resultado="r",
        )
        activa = sdd._sesion_activa(self.control)
        self.assertEqual(activa["reintentos"], 1)
        self.assertEqual(len(self.control["remediaciones"]), 1)

    def test_limite_agotado_no_incrementa_reintentos_ni_escribe_intento(self):
        sdd.session_note(
            self.control,
            rol=None,
            tipo="reintento",
            finding_id="F1",
            remediation_tipo="bug",
            causa="c1",
            cambio_aplicado="ca1",
            resultado="r1",
            max_intentos_remediacion=1,
        )
        activa = sdd._sesion_activa(self.control)
        self.assertEqual(activa["reintentos"], 1)

        with self.assertRaises(sdd.RemediacionLimiteError) as ctx:
            sdd.session_note(
                self.control,
                rol=None,
                tipo="reintento",
                finding_id="F1",
                remediation_tipo="bug",
                causa="c2",
                cambio_aplicado="ca2",
                resultado="r2",
                max_intentos_remediacion=1,
            )
        self.assertEqual(ctx.exception.findings[0].codigo, "REMEDIACION-LIMITE")
        # No se incrementó el agregado de sesión pese al intento denegado.
        self.assertEqual(activa["reintentos"], 1)
        self.assertEqual(len(self.control["remediaciones"][0]["ventanas"][0]["intentos"]), 1)

    def test_regresion_session_note_sin_flags_nuevos_se_comporta_igual_que_antes(self):
        """Mismo comportamiento que antes de este cambio cuando no se usan
        `finding_id`/`remediation_tipo`."""
        control = _control_con_sesion(max_reintentos=10)
        activa = sdd.session_note(control, "python-data-engineer", "reintento", tarea="t1")
        self.assertEqual(activa["reintentos"], 1)
        self.assertEqual(activa["tareas"], ["t1"])
        self.assertEqual(activa["roles"], ["python-data-engineer"])
        self.assertNotIn("remediaciones", control)

        activa2 = sdd.session_note(control, None, "planificada")
        self.assertEqual(activa2["reintentos"], 1)  # no cambia por "planificada"

        activa3 = sdd.session_note(control, None, "ronda")
        self.assertEqual(activa3["rondas_revision"], 1)


class TestHookPresupuestoLimiteReintentos(unittest.TestCase):
    """Extensión de `hook_presupuesto.evaluar()` (R19): deniega `Agent`
    nuevo si `reintentos >= max_reintentos` de la sesión activa."""

    def _payload_agent(self):
        return {"tool_name": "Agent", "tool_input": {"agent_id": "sub1"}}

    def test_reintentos_agotados_deniega_agent_nuevo(self):
        control = _control_con_sesion(max_reintentos=2)
        sesion = sdd._sesion_activa(control)
        sesion["reintentos"] = 2
        permitido, motivo, modificado = hook_presupuesto.evaluar(self._payload_agent(), sesion, None)
        self.assertFalse(permitido)
        self.assertIn("LÍMITE DE REINTENTOS", motivo)
        self.assertFalse(modificado)

    def test_reintentos_dentro_de_presupuesto_permite(self):
        control = _control_con_sesion(max_reintentos=2)
        sesion = sdd._sesion_activa(control)
        sesion["reintentos"] = 1
        permitido, motivo, modificado = hook_presupuesto.evaluar(self._payload_agent(), sesion, None)
        self.assertTrue(permitido)

    def test_sin_sesion_activa_permite_siempre(self):
        permitido, motivo, modificado = hook_presupuesto.evaluar(self._payload_agent(), None, None)
        self.assertTrue(permitido)


def _crear_dir_temporal_change(repo: Path, change_id: str, max_reintentos: int = 10) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    change_dir = repo / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True, exist_ok=True)
    control = {
        "schema_version": 1,
        "change_id": change_id,
        "modo": "completo",
        "creado_utc": core.ahora_utc(),
        "baseline": {"commit": "0" * 40, "rama": "main", "capturado_utc": core.ahora_utc()},
        "alcance": {"rutas_autorizadas": [f"openspec/changes/{change_id}/*"]},
        "aprobaciones": [],
        "transiciones": [],
        "sesiones": [],
    }
    sdd.session_start(control, minutos=90, max_reintentos=max_reintentos)
    core.escribir_control(change_dir / "control.json", control)
    (change_dir / "tasks.md").write_text(
        f"# Tareas — {change_id}\n\nestado: en_implementacion\n\n## Tareas\n- [ ] x\n",
        encoding="utf-8",
    )
    return change_dir


def _correr_ds_guard(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DS_GUARD), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class TestCliRemediationResolveExtend(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal("remediation_cli_test_")
        self.change_id = "20260910-remediation-cli"
        _crear_dir_temporal_change(self.repo, self.change_id)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_note_luego_resolve_luego_extend_via_cli(self):
        resultado_note = _correr_ds_guard(
            [
                "session", "note", "--change-id", self.change_id, "--tipo", "reintento",
                "--finding-id", "F1", "--remediation-tipo", "bug",
                "--causa", "c", "--cambio-aplicado", "ca", "--resultado", "r",
            ],
            self.repo,
        )
        self.assertEqual(resultado_note.returncode, 0, resultado_note.stderr)

        control_path = self.repo / "openspec" / "changes" / self.change_id / "control.json"
        control = core.leer_control(control_path)
        remediation_id = control["remediaciones"][0]["remediation_id"]

        resultado_resolve = _correr_ds_guard(
            [
                "remediation", "resolve", "--change-id", self.change_id,
                "--remediation-id", remediation_id, "--resultado", "arreglado", "--json",
            ],
            self.repo,
        )
        self.assertEqual(resultado_resolve.returncode, 0, resultado_resolve.stderr)
        control_tras_resolve = core.leer_control(control_path)
        self.assertEqual(control_tras_resolve["remediaciones"][0]["estado"], "resuelta")

        resultado_extend = _correr_ds_guard(
            [
                "remediation", "extend", "--change-id", self.change_id,
                "--remediation-id", remediation_id, "--usuario", "federico",
                "--fecha", "2026-09-10", "--motivo", "reabrir", "--json",
            ],
            self.repo,
        )
        # La remediación ya está resuelta: extend se rehúsa (exit 1).
        self.assertEqual(resultado_extend.returncode, 1, resultado_extend.stderr)

    def test_remediation_tipo_sin_tipo_reintento_es_error_de_uso(self):
        resultado = _correr_ds_guard(
            [
                "session", "note", "--change-id", self.change_id, "--tipo", "planificada",
                "--remediation-tipo", "bug",
            ],
            self.repo,
        )
        self.assertEqual(resultado.returncode, 2)


if __name__ == "__main__":
    unittest.main()
