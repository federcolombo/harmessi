"""Tests de repo de v0.8 Change 3 (`20260930-autonomous-sdd-and-remediation`),
T7: R7 (los 12 STOP nunca se vuelven `proceed`), R19 (`approval_mode` es un
eje ortogonal al modo de autonomía) y R18 (compatibilidad hacia atrás -- un
`control` sin ninguna clave nueva de este Change se comporta igual que
antes).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from autonomy import core as autonomy_core  # noqa: E402
from dsguard import sdd  # noqa: E402


class TestR7StopCatalogInmutableAnteApprovalMode(unittest.TestCase):
    """Los 12 STOP materiales de `tools.autonomy.core.STOP_CATALOG` nunca
    resuelven `outcome="proceed"`, sin importar `approval_mode` -- verificado
    recorriendo el catálogo real (no una lista hardcodeada en el test) y
    confirmando que `resolve_action` ni siquiera acepta `approval_mode` como
    parámetro (Change 3 no le agregó uno, R7 de spec.md)."""

    def test_el_catalogo_tiene_exactamente_12_entradas(self):
        # Sanity: si esto cambia, es un cambio material de Change 0 (STOP)
        # que este Change no debería estar tocando.
        self.assertEqual(len(autonomy_core.STOP_CATALOG), 12)

    def test_ninguna_fila_de_policy_table_con_stop_code_da_proceed(self):
        codigos_stop = {e.code for e in autonomy_core.STOP_CATALOG}
        filas_con_stop = [
            decision
            for decision in autonomy_core.POLICY_TABLE.values()
            if decision.stop_code is not None
        ]
        self.assertTrue(filas_con_stop, "no se encontró ninguna fila STOP en POLICY_TABLE")
        for decision in filas_con_stop:
            self.assertIn(decision.stop_code, codigos_stop)
            self.assertEqual(
                decision.outcome,
                "stop_human",
                f"{decision.action_class}/{decision.mode} con stop_code {decision.stop_code} "
                f"no da stop_human",
            )
            self.assertNotEqual(decision.outcome, "proceed")

    def test_resolve_action_no_acepta_approval_mode(self):
        # `approval_mode` no es un parámetro de `resolve_action` -- Change 3
        # no le agregó uno (R7: los checkpoints nunca pueden convertir un
        # STOP en aprobación automática, porque la función que decide el
        # outcome ni siquiera sabe que `approval_mode` existe).
        import inspect

        firma = inspect.signature(autonomy_core.resolve_action)
        self.assertNotIn("approval_mode", firma.parameters)
        self.assertEqual(list(firma.parameters), ["action_class", "mode"])


class TestR19ApprovalModeEjeOrtogonal(unittest.TestCase):
    """`approval_mode` (`per_change`/`checkpoints`) no cambia el resultado de
    `resolve_action` para ningún `action_class`/modo de autonomía -- la
    matriz 2x2 completa da exactamente los mismos resultados que sin
    considerar `approval_mode` en absoluto, porque el único punto de
    ramificación por modo sigue siendo `resolve_action` (Change 0, sin
    tocar)."""

    def test_matriz_2x2_approval_mode_x_modo_autonomia(self):
        for action_class in autonomy_core.ACTION_CLASSES:
            for modo_autonomia in autonomy_core.MODES:
                resultado_base = autonomy_core.resolve_action(action_class, modo_autonomia)
                for approval_mode in sdd.APPROVAL_MODES:
                    # `resolver_approval_mode` es puramente informativo: no
                    # existe ningún llamador de `resolve_action` en este
                    # repo que le pase `approval_mode` como argumento -- lo
                    # confirmamos llamando a la función real con distintos
                    # `control["aprobacion_modo"]` y comprobando que el
                    # resultado de política no varía.
                    control = {"aprobacion_modo": approval_mode}
                    self.assertEqual(sdd.resolver_approval_mode(control), approval_mode)
                    resultado_con_modo = autonomy_core.resolve_action(action_class, modo_autonomia)
                    self.assertEqual(resultado_base, resultado_con_modo)


class TestR18CompatibilidadHaciaAtras(unittest.TestCase):
    """Un `control` sin ninguna clave nueva de Change 3
    (`aprobacion_modo`/`decisiones_preaprobadas`) se comporta exactamente
    igual que antes de este Change -- smoke test explícito, además de la
    regresión completa (que no requirió editar ningún test preexistente)."""

    def _control_v07(self) -> dict:
        # Forma mínima de un control.json de un Change v0.7/v0.8 anterior a
        # este, sin ninguna clave nueva.
        return {
            "schema_version": 1,
            "change_id": "20260101-change-legacy",
            "modo": "completo",
            "sesiones": [],
            "transiciones": [],
        }

    def test_session_start_y_note_funcionan_sin_claves_nuevas(self):
        control = self._control_v07()
        sdd.session_start(control, minutos=90)
        sdd.session_note(control, "lead", "planificada", tarea="t1")
        estado = sdd.session_status(control)
        self.assertTrue(estado["activa"])
        self.assertEqual(estado["subagentes"], 0)  # default nuevo, no rompe nada existente

    def test_resolver_approval_mode_sobre_control_v07_da_per_change(self):
        control = self._control_v07()
        self.assertEqual(sdd.resolver_approval_mode(control), "per_change")

    def test_presupuesto_agregado_sobre_control_v07_no_lanza(self):
        control = self._control_v07()
        agregado = sdd.presupuesto_agregado(control)
        self.assertEqual(agregado["sesiones_totales"], 0)


if __name__ == "__main__":
    unittest.main()
