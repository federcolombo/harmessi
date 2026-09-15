"""Tests del motor neutral de checks (`tools.dsguard.checks`, Change 4 v0.3).

Cubre los criterios de `spec.md` de
`openspec/changes/20260915-checks-engine-foundation/`: preservación de
PASS/WARN/FAIL/N-A, validación de `message`/`status`/`kind`, orden
preservado, no-short-circuit ante excepción, conteos/bloqueo/exit code,
filtrado por status, serialización y la distinción `kind` "check" vs
"technical_error"."""
from __future__ import annotations

import unittest

from tools.dsguard import checks


def _check_pass():
    return [checks.CheckResult(checks.STATUS_PASS, "X-PASS", "todo ok")]


def _check_warn():
    return [checks.CheckResult(checks.STATUS_WARN, "X-WARN", "atención")]


def _check_fail():
    return [checks.CheckResult(checks.STATUS_FAIL, "X-FAIL", "falló")]


def _check_na():
    return [checks.CheckResult(checks.STATUS_NA, "X-NA", "no aplica")]


def _check_explota():
    raise RuntimeError("boom inesperado")


class TestCheckResult(unittest.TestCase):
    def test_status_valido_se_construye_sin_error(self):
        for status in (checks.STATUS_PASS, checks.STATUS_WARN, checks.STATUS_FAIL, checks.STATUS_NA):
            r = checks.CheckResult(status, "COD", "mensaje")
            self.assertEqual(r.status, status)

    def test_status_invalido_lanza_value_error(self):
        with self.assertRaises(ValueError):
            checks.CheckResult("NO-EXISTE", "COD", "mensaje")

    def test_message_vacio_lanza_value_error(self):
        with self.assertRaises(ValueError):
            checks.CheckResult(checks.STATUS_NA, "COD", "")

    def test_message_vacio_lanza_value_error_incluso_en_pass(self):
        # Regla universal (no solo para N/A) -- design.md punto 4.
        with self.assertRaises(ValueError):
            checks.CheckResult(checks.STATUS_PASS, "COD", "")

    def test_kind_default_es_check(self):
        r = checks.CheckResult(checks.STATUS_FAIL, "COD", "falló normalmente")
        self.assertEqual(r.kind, checks.KIND_CHECK)

    def test_kind_invalido_lanza_value_error(self):
        with self.assertRaises(ValueError):
            checks.CheckResult(checks.STATUS_PASS, "COD", "mensaje", kind="algo-raro")

    def test_to_dict_incluye_status_code_message_kind(self):
        r = checks.CheckResult(checks.STATUS_WARN, "COD", "mensaje")
        d = r.to_dict()
        self.assertEqual(d["status"], checks.STATUS_WARN)
        self.assertEqual(d["code"], "COD")
        self.assertEqual(d["message"], "mensaje")
        self.assertEqual(d["kind"], checks.KIND_CHECK)

    def test_to_dict_omite_detail_y_subject_si_no_estan(self):
        r = checks.CheckResult(checks.STATUS_PASS, "COD", "mensaje")
        d = r.to_dict()
        self.assertNotIn("detail", d)
        self.assertNotIn("subject", d)

    def test_to_dict_incluye_detail_y_subject_si_estan(self):
        r = checks.CheckResult(checks.STATUS_PASS, "COD", "mensaje", detail="d", subject="s")
        d = r.to_dict()
        self.assertEqual(d["detail"], "d")
        self.assertEqual(d["subject"], "s")


class TestEjecutarChecks(unittest.TestCase):
    def test_check_pass_se_preserva_tal_cual(self):
        resultados = checks.ejecutar_checks([("X-PASS", _check_pass, ())])
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)

    def test_check_warn_se_preserva_no_bloquea(self):
        resultados = checks.ejecutar_checks([("X-WARN", _check_warn, ())])
        self.assertEqual(resultados[0].status, checks.STATUS_WARN)
        self.assertFalse(checks.hay_bloqueo(resultados))

    def test_check_fail_se_preserva_y_bloquea(self):
        resultados = checks.ejecutar_checks([("X-FAIL", _check_fail, ())])
        self.assertEqual(resultados[0].status, checks.STATUS_FAIL)
        self.assertTrue(checks.hay_bloqueo(resultados))
        self.assertEqual(checks.exit_code(resultados), 1)

    def test_check_na_se_preserva_no_bloquea_no_es_pass_ni_fail(self):
        resultados = checks.ejecutar_checks([("X-NA", _check_na, ())])
        self.assertEqual(resultados[0].status, checks.STATUS_NA)
        self.assertFalse(checks.hay_bloqueo(resultados))
        conteos = checks.contar_por_status(resultados)
        self.assertEqual(conteos[checks.STATUS_PASS], 0)
        self.assertEqual(conteos[checks.STATUS_FAIL], 0)
        self.assertEqual(conteos[checks.STATUS_NA], 1)

    def test_orden_de_registros_se_preserva(self):
        registros = [
            ("X-PASS", _check_pass, ()),
            ("X-FAIL", _check_fail, ()),
            ("X-WARN", _check_warn, ()),
        ]
        resultados = checks.ejecutar_checks(registros)
        self.assertEqual(
            [r.code for r in resultados], ["X-PASS", "X-FAIL", "X-WARN"]
        )

    def test_orden_interno_de_cada_lista_se_preserva(self):
        def _check_multiple():
            return [
                checks.CheckResult(checks.STATUS_PASS, "A", "uno"),
                checks.CheckResult(checks.STATUS_WARN, "B", "dos"),
            ]

        resultados = checks.ejecutar_checks([("X", _check_multiple, ())])
        self.assertEqual([r.code for r in resultados], ["A", "B"])

    def test_excepcion_no_detiene_los_checks_siguientes(self):
        registros = [
            ("X-EXPLOTA", _check_explota, ()),
            ("X-PASS", _check_pass, ()),
        ]
        resultados = checks.ejecutar_checks(registros)
        self.assertEqual(len(resultados), 2)
        self.assertEqual(resultados[1].status, checks.STATUS_PASS)

    def test_excepcion_produce_fail_con_codigo_y_mensaje_esperado(self):
        resultados = checks.ejecutar_checks([("X-EXPLOTA", _check_explota, ())])
        r = resultados[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)
        self.assertEqual(r.code, "X-EXPLOTA-EXCEPCION")
        self.assertIn("Fallo inesperado ejecutando el check:", r.message)
        self.assertIn("boom inesperado", r.message)

    def test_excepcion_tiene_kind_technical_error(self):
        resultados = checks.ejecutar_checks([("X-EXPLOTA", _check_explota, ())])
        self.assertEqual(resultados[0].kind, checks.KIND_TECHNICAL_ERROR)

    def test_fail_funcional_tiene_kind_check(self):
        resultados = checks.ejecutar_checks([("X-FAIL", _check_fail, ())])
        self.assertEqual(resultados[0].kind, checks.KIND_CHECK)

    def test_ambos_kinds_bloquean_igual(self):
        resultados_check = checks.ejecutar_checks([("X-FAIL", _check_fail, ())])
        resultados_tecnico = checks.ejecutar_checks([("X-EXPLOTA", _check_explota, ())])
        self.assertTrue(checks.hay_bloqueo(resultados_check))
        self.assertTrue(checks.hay_bloqueo(resultados_tecnico))
        self.assertEqual(checks.exit_code(resultados_check), 1)
        self.assertEqual(checks.exit_code(resultados_tecnico), 1)

    def test_serializacion_conserva_kind(self):
        resultados = checks.ejecutar_checks([("X-EXPLOTA", _check_explota, ())])
        d = resultados[0].to_dict()
        self.assertEqual(d["kind"], checks.KIND_TECHNICAL_ERROR)


class TestResultadoDeExcepcion(unittest.TestCase):
    def test_formato_de_mensaje(self):
        exc = ValueError("mal dato")
        r = checks.resultado_de_excepcion("COD-BASE", exc)
        self.assertEqual(r.status, checks.STATUS_FAIL)
        self.assertEqual(r.code, "COD-BASE-EXCEPCION")
        self.assertEqual(r.kind, checks.KIND_TECHNICAL_ERROR)
        self.assertIn(repr(exc), r.message)


class TestContarPorStatus(unittest.TestCase):
    def test_conteo_correcto_por_cada_status(self):
        resultados = [
            checks.CheckResult(checks.STATUS_PASS, "A", "a"),
            checks.CheckResult(checks.STATUS_PASS, "B", "b"),
            checks.CheckResult(checks.STATUS_WARN, "C", "c"),
            checks.CheckResult(checks.STATUS_FAIL, "D", "d"),
            checks.CheckResult(checks.STATUS_NA, "E", "e"),
        ]
        conteos = checks.contar_por_status(resultados)
        self.assertEqual(conteos, {"PASS": 2, "WARN": 1, "FAIL": 1, "N/A": 1})


class TestHayBloqueoYExitCode(unittest.TestCase):
    def test_solo_pass_warn_na_no_bloquea(self):
        resultados = [
            checks.CheckResult(checks.STATUS_PASS, "A", "a"),
            checks.CheckResult(checks.STATUS_WARN, "B", "b"),
            checks.CheckResult(checks.STATUS_NA, "C", "c"),
        ]
        self.assertFalse(checks.hay_bloqueo(resultados))
        self.assertEqual(checks.exit_code(resultados), 0)

    def test_con_al_menos_un_fail_bloquea(self):
        resultados = [
            checks.CheckResult(checks.STATUS_PASS, "A", "a"),
            checks.CheckResult(checks.STATUS_FAIL, "B", "b"),
        ]
        self.assertTrue(checks.hay_bloqueo(resultados))
        self.assertEqual(checks.exit_code(resultados), 1)

    def test_lista_vacia_no_bloquea(self):
        self.assertFalse(checks.hay_bloqueo([]))
        self.assertEqual(checks.exit_code([]), 0)


class TestFiltrarPorStatus(unittest.TestCase):
    def test_filtra_preservando_orden(self):
        resultados = [
            checks.CheckResult(checks.STATUS_WARN, "A", "a"),
            checks.CheckResult(checks.STATUS_PASS, "B", "b"),
            checks.CheckResult(checks.STATUS_WARN, "C", "c"),
        ]
        filtrados = checks.filtrar_por_status(resultados, checks.STATUS_WARN)
        self.assertEqual([r.code for r in filtrados], ["A", "C"])

    def test_filtra_sin_coincidencias_devuelve_lista_vacia(self):
        resultados = [checks.CheckResult(checks.STATUS_PASS, "A", "a")]
        self.assertEqual(checks.filtrar_por_status(resultados, checks.STATUS_FAIL), [])


if __name__ == "__main__":
    unittest.main()
