"""Tests de v0.8 Change 3 (`20260930-autonomous-sdd-and-remediation`), T1+T2:
`resolver_approval_mode`, `parsear_checkpoints_de_propuesta`,
`presupuesto_agregado`, `chequear_limite_agregado` (`tools/dsguard/sdd.py`).
No edita ningún test preexistente (R18 de `spec.md`): archivo nuevo.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from autonomy import core as autonomy_core  # noqa: E402
from dsguard import sdd  # noqa: E402

_HASH_RELLENO = "0123456789abcdef" * 4  # 64 hex chars, no es un hash real del repo.
_CHANGE_ID = "20260930-autonomous-sdd-and-remediation"


def _bullet_checkpoint(id_="budget-sprint3", resumen="Aprobar el tope de presupuesto"):
    return (
        f"- **{id_}**: {resumen} — alcance: tools/dsguard/sdd.py, "
        f"tools/tests/test_lifecycle.py — aprobacion: {_CHANGE_ID}/proposal.md@{_HASH_RELLENO}"
    )


# --- Entregable 1: approval_mode + checkpoints --------------------------------


class TestResolverApprovalMode(unittest.TestCase):
    def test_ausente_resuelve_per_change(self):
        control = {"schema_version": 1}
        self.assertEqual(sdd.resolver_approval_mode(control), "per_change")

    def test_checkpoints_explicito_se_respeta(self):
        control = {"schema_version": 1, "aprobacion_modo": "checkpoints"}
        self.assertEqual(sdd.resolver_approval_mode(control), "checkpoints")

    def test_valor_desconocido_resuelve_per_change(self):
        control = {"schema_version": 1, "aprobacion_modo": "algo_no_declarado"}
        self.assertEqual(sdd.resolver_approval_mode(control), "per_change")


class TestParsearCheckpointsDePropuesta(unittest.TestCase):
    def test_checkpoint_bien_formado_valida_sin_hallazgos(self):
        texto = f"## Checkpoints de negocio\n\n{_bullet_checkpoint()}\n\n## Otra sección\nignorar\n"
        checkpoints, hallazgos = sdd.parsear_checkpoints_de_propuesta(texto)
        self.assertEqual(hallazgos, [])
        self.assertEqual(len(checkpoints), 1)
        cp = checkpoints[0]
        self.assertEqual(cp["decision_type"], "business_checkpoint")
        self.assertEqual(cp["approval_ref"]["artefacto"], "proposal.md")
        # Válido según la misma validación que usa `PreApprovedDecision` (R3).
        self.assertEqual(
            autonomy_core.validate_pre_approved(cp, known_types=("business_checkpoint",)),
            [],
        )
        # Round-trip: `PreApprovedDecision.from_dict` no debe lanzar.
        decision = autonomy_core.PreApprovedDecision.from_dict(cp)
        self.assertEqual(decision.decision_type, "business_checkpoint")

    def test_bullet_ambiguo_produce_hallazgo_sin_checkpoint_fantasma(self):
        texto = (
            "## Checkpoints de negocio\n\n"
            "- **checkpoint-incompleto**: falta el resto del formato\n"
        )
        checkpoints, hallazgos = sdd.parsear_checkpoints_de_propuesta(texto)
        self.assertEqual(checkpoints, [])
        self.assertEqual(len(hallazgos), 1)
        self.assertEqual(hallazgos[0].codigo, autonomy_core.CODE_PREAPPROVED_INVALID)

    def test_seccion_ausente_da_listas_vacias(self):
        texto = "## Otra sección\nsin checkpoints acá\n"
        checkpoints, hallazgos = sdd.parsear_checkpoints_de_propuesta(texto)
        self.assertEqual(checkpoints, [])
        self.assertEqual(hallazgos, [])

    def test_bullet_con_alcance_vacio_produce_hallazgo_sin_checkpoint_fantasma(self):
        """Bullet con `alcance` vacío: sea porque no matchea el regex (formato
        ambiguo) o porque matchea pero `validate_pre_approved` lo rechaza
        (`scope_empty`), en ningún caso se acepta un checkpoint fantasma --
        siempre termina en un hallazgo con el código ya registrado."""
        texto = (
            "## Checkpoints de negocio\n\n"
            f"- **cp2**: resumen — alcance:  — aprobacion: {_CHANGE_ID}/proposal.md@{_HASH_RELLENO}\n"
        )
        checkpoints, hallazgos = sdd.parsear_checkpoints_de_propuesta(texto)
        self.assertEqual(checkpoints, [])
        self.assertEqual(len(hallazgos), 1)
        self.assertEqual(hallazgos[0].codigo, autonomy_core.CODE_PREAPPROVED_INVALID)


# --- Entregable 2: presupuesto agregado ---------------------------------------


def _control_vacio(change_id: str = _CHANGE_ID) -> dict:
    return {
        "schema_version": 1,
        "change_id": change_id,
        "modo": "completo",
        "sesiones": [],
        "transiciones": [],
    }


class TestPresupuestoAgregado(unittest.TestCase):
    def test_suma_sobre_sesiones_cerradas(self):
        control = _control_vacio()
        control["sesiones"] = [
            {"estado_final": "completada", "minutos_consumidos": 40.0},
            {"estado_final": "completada", "minutos_consumidos": 30.0},
            {"estado_final": "pausada", "minutos_consumidos": 25.0},
        ]
        agregado = sdd.presupuesto_agregado(control)
        self.assertEqual(agregado["minutos_consumidos_totales"], 95.0)
        self.assertEqual(agregado["sesiones_totales"], 3)
        self.assertEqual(agregado["sesiones_abiertas"], 0)

    def test_consulta_no_consume_sesion(self):
        control = _control_vacio()
        control["sesiones"] = [{"estado_final": "completada", "minutos_consumidos": 10.0}]
        antes = len(control["sesiones"])
        sdd.presupuesto_agregado(control)
        sdd.session_status(control)
        self.assertEqual(len(control["sesiones"]), antes)

    def test_session_close_no_agrega_otra_entrada(self):
        control = _control_vacio()
        sdd.session_start(control, minutos=90)
        antes = len(control["sesiones"])
        sdd.session_close(control, "completada")
        self.assertEqual(len(control["sesiones"]), antes)


class TestChequearLimiteAgregado(unittest.TestCase):
    def test_sin_config_budgets_no_produce_findings(self):
        control = _control_vacio()
        control["sesiones"] = [{"estado_final": "completada", "minutos_consumidos": 999.0}]
        self.assertEqual(sdd.chequear_limite_agregado(control, None), [])
        self.assertEqual(sdd.chequear_limite_agregado(control, {}), [])

    def test_limite_de_minutos_excedido_produce_finding(self):
        control = _control_vacio()
        control["sesiones"] = [{"estado_final": "completada", "minutos_consumidos": 100.0}]
        findings = sdd.chequear_limite_agregado(control, {"aggregate_minutes": 60})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].codigo, autonomy_core.CODE_LIMIT_AGGREGATE_BUDGET)


class TestNoEvasionR12a(unittest.TestCase):
    """Secuencia de 7 pasos EXACTA de R12a de `spec.md` (aprobación humana
    congelada 2026-09-30): reapertura tras `pausada_bloqueada` consume una
    nueva unidad de `max_sessions`, sin evasión posible encadenando sesiones.

    Decisión de implementación de esta invocación (T2): el paso "la sesión
    pasa a `pausada_bloqueada`" se resuelve con la transición SDD real ya
    existente (`sdd.transition(..., hacia="pausada_bloqueada")`, que exige
    tener `tasks.md`/`control.json` reales en disco -- por eso este test usa
    un directorio temporal real, no solo un dict en memoria como el resto de
    este archivo). No se transiciona de vuelta a `en_implementacion` entre
    ventanas porque `session_start` no depende del estado de `tasks.md` (es
    una función pura sobre `control`, sin tocar su mecanismo) y R12a no lo
    exige -- solo importa que `control["sesiones"]` crezca por cada reapertura
    real, que es lo que esta secuencia demuestra.
    """

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="agregado_no_evasion_"))
        self.change_id = "20260930-no-evasion-test"
        self.change_dir = self.repo / "openspec" / "changes" / self.change_id
        self.change_dir.mkdir(parents=True)
        self.tasks_path = self.change_dir / "tasks.md"
        self.control_path = self.change_dir / "control.json"
        self.tasks_path.write_text(
            "# Tareas\n\nestado: en_implementacion\n\n"
            "## Próximo paso exacto\nRetomar la ventana pausada.\n",
            encoding="utf-8",
        )
        self.control = _control_vacio(self.change_id)

    def _agotar_y_pausar(self):
        # 1) Abrir con presupuesto de tiempo = 0 -> agotamiento REAL, casi
        #    instantáneo (no un flag simulado): `minutos_restantes` compara
        #    contra el reloj real, y el deadline queda en el mismo instante
        #    de apertura.
        sdd.session_start(self.control, minutos=0, max_reintentos=10)
        sesion = sdd._sesion_activa(self.control)
        findings_limite = sdd.chequear_limites(sesion)
        self.assertTrue(
            any(f.codigo == "SESION-LIMITE-TIEMPO" for f in findings_limite), findings_limite
        )
        # 2) La sesión pasa a `pausada_bloqueada`: cerrar la sesión (mecanismo
        #    ya existente `session_close`) y transicionar el Change SDD al
        #    estado `pausada_bloqueada` (mecanismo ya existente `transition`,
        #    sin cambios).
        sdd.session_close(self.control, "pausada")
        ok, findings_transicion = sdd.transition(
            self.control,
            self.tasks_path,
            self.control_path,
            self.repo,
            hacia="pausada_bloqueada",
            sesion_activa=None,
        )
        self.assertTrue(ok, findings_transicion)

    def test_secuencia_completa_de_no_evasion(self):
        # (1)-(2): ventana 1, agotar y pasar a pausada_bloqueada.
        self._agotar_y_pausar()
        self.assertEqual(sdd.presupuesto_agregado(self.control)["sesiones_totales"], 1)

        # (3): reabrir -- nueva `session_start` sobre el mismo Change.
        # (4): confirmar que `sesiones_totales` pasó de 1 a 2 (no quedó en 1
        #      por "ser la misma continuación conceptual").
        # (5): repetir agotar->pausar->reabrir hasta llegar EXACTAMENTE al
        #      máximo configurado (2, en este test).
        self._agotar_y_pausar()
        agregado = sdd.presupuesto_agregado(self.control)
        self.assertEqual(agregado["sesiones_totales"], 2)

        # (6): el límite ya está agotado -- `chequear_limite_agregado`
        #      (función pura de `sdd.py`, sin conocer política de CLI) lo
        #      detecta correctamente con `max_sessions=2`. Esta función NO
        #      es quien bloquea el `session start` en sí (por diseño, D5: la
        #      composición de budgets vive en `ds_guard.py`, no en `sdd.py`
        #      -- `sdd.session_start` no conoce `max_sessions`) -- la prueba
        #      real de "no se abre una sesión nueva" (R12, hallazgo de
        #      revisión T8, corregido) está a nivel CLI en
        #      `tools/tests/test_ds_guard_budgets_cli.py::
        #      test_max_sessions_excedido_rechaza_una_session_start_adicional`,
        #      que sí ejercita `ds_guard session start` de punta a punta y
        #      confirma `returncode == 2` y que `control["sesiones"]` no
        #      creció. Acá solo se prueba que la detección de la que depende
        #      ese rechazo es correcta.
        findings = sdd.chequear_limite_agregado(self.control, {"max_sessions": 2})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].codigo, autonomy_core.CODE_LIMIT_AGGREGATE_BUDGET)

        # (7): ese bloqueo es un LIMIT (`checkpoint_resumable`), nunca un
        #      STOP del catálogo, y la función no lanzó ninguna excepción ni
        #      tiene forma de pedir aprobación humana (sin parámetro
        #      "usuario"/"aprobado_por" en su firma).
        codigos_stop = {e.code for e in autonomy_core.STOP_CATALOG}
        self.assertNotIn(findings[0].codigo, codigos_stop)
        limit_entry = next(
            e for e in autonomy_core.LIMIT_CATALOG if e.code == findings[0].codigo
        )
        self.assertEqual(limit_entry.result, autonomy_core.CHECKPOINT_RESUMABLE)


# --- T4: subagentes concurrentes (límite honesto, best-effort) ----------------


class TestSubagentesConcurrentes(unittest.TestCase):
    def setUp(self):
        self.control = _control_vacio()
        sdd.session_start(self.control, minutos=90)

    def test_abrir_incrementa_conteo(self):
        sdd.session_note(self.control, "lead", "subagente", evento="abrir")
        self.assertEqual(sdd.session_status(self.control)["subagentes"], 1)

    def test_dos_aperturas_seguidas_conteo_en_2(self):
        sdd.session_note(self.control, "lead", "subagente", evento="abrir")
        sdd.session_note(self.control, "lead", "subagente", evento="abrir")
        self.assertEqual(sdd.session_status(self.control)["subagentes"], 2)

    def test_abrir_y_cerrar_vuelve_a_0(self):
        sdd.session_note(self.control, "lead", "subagente", evento="abrir")
        sdd.session_note(self.control, "lead", "subagente", evento="cerrar")
        self.assertEqual(sdd.session_status(self.control)["subagentes"], 0)

    def test_cerrar_sin_apertura_previa_lanza_value_error(self):
        with self.assertRaises(ValueError):
            sdd.session_note(self.control, "lead", "subagente", evento="cerrar")

    def test_evento_invalido_lanza_value_error(self):
        with self.assertRaises(ValueError):
            sdd.session_note(self.control, "lead", "subagente", evento="lo-que-sea")
        with self.assertRaises(ValueError):
            sdd.session_note(self.control, "lead", "subagente", evento=None)

    def test_subagente_no_toca_reintentos_ni_rondas(self):
        sdd.session_note(self.control, "lead", "subagente", evento="abrir")
        sesion = sdd._sesion_activa(self.control)
        self.assertEqual(sesion.get("reintentos", 0), 0)
        self.assertEqual(sesion.get("rondas_revision", 0), 0)


class TestLimiteSubagentesAlcanzado(unittest.TestCase):
    def setUp(self):
        self.control = _control_vacio()
        sdd.session_start(self.control, minutos=90)

    def test_sin_sesion_activa_da_false(self):
        control_sin_sesion = _control_vacio()
        self.assertFalse(sdd.limite_subagentes_alcanzado(control_sin_sesion, 2))

    def test_max_concurrentes_none_da_false(self):
        sdd.session_note(self.control, "lead", "subagente", evento="abrir")
        self.assertFalse(sdd.limite_subagentes_alcanzado(self.control, None))

    def test_por_debajo_del_maximo_da_false(self):
        sdd.session_note(self.control, "lead", "subagente", evento="abrir")
        self.assertFalse(sdd.limite_subagentes_alcanzado(self.control, 2))

    def test_en_el_maximo_da_true(self):
        sdd.session_note(self.control, "lead", "subagente", evento="abrir")
        sdd.session_note(self.control, "lead", "subagente", evento="abrir")
        self.assertTrue(sdd.limite_subagentes_alcanzado(self.control, 2))


if __name__ == "__main__":
    unittest.main()
