"""Tests de Doctor para upgrade/migración (v0.11 Change 5, R6): `HARMESSI-VERSION`
con remedio literal, `HARMESSI-MIGRACION` (staging/journal/lock residuales) y
mensaje explícito de archivo administrado ausente. Doctor es solo lectura."""
from __future__ import annotations

import unittest

from tools.harmessi import doctor as doctor_mod
from tools.ds_init.tests.test_upgrade import (
    RUTA_NUEVA,
    VERSION_PREVIA,
    _BaseUpgrade,
    _commit_todo,
    _escribir_control,
    _hashes_arbol,
    _leer_control,
)


def _hashes_sin_cache(repo) -> dict:
    return {k: v for k, v in _hashes_arbol(repo).items() if "__pycache__" not in k}


def _por_codigo(resultados, codigo: str) -> list:
    return [r for r in resultados if r.codigo == codigo]


def _no_ok(resultados) -> set:
    return {
        (r.nivel, r.codigo, r.ubicacion)
        for r in resultados
        if r.nivel in (doctor_mod.NIVEL_WARN, doctor_mod.NIVEL_ERROR)
    }


class TestDoctorMigracion(_BaseUpgrade):
    def doctor(self):
        resultados, _codigo = doctor_mod.ejecutar(self.repo)
        return resultados

    def test_version_igual_ok(self):
        r = _por_codigo(self.doctor(), "HARMESSI-VERSION")
        self.assertEqual([x.nivel for x in r], [doctor_mod.NIVEL_OK])

    def test_version_distinta_warn_con_comando(self):
        control = _leer_control(self.repo)
        control["harness_version"] = VERSION_PREVIA
        _escribir_control(self.repo, control)
        r = _por_codigo(self.doctor(), "HARMESSI-VERSION")
        self.assertEqual([x.nivel for x in r], [doctor_mod.NIVEL_WARN])
        self.assertIn("python -m tools.ds_init upgrade --destino", r[0].mensaje)
        self.assertIn("--execute", r[0].mensaje)

    def test_limpio_ok(self):
        r = _por_codigo(self.doctor(), "HARMESSI-MIGRACION")
        self.assertEqual([x.nivel for x in r], [doctor_mod.NIVEL_OK])

    def _crear_journal(self, fase_json: str) -> None:
        d = self.repo / ".ds_init" / "journal" / "20260101T000000000000Z"
        d.mkdir(parents=True)
        (d / "journal.json").write_text(fase_json, encoding="utf-8")

    def test_journal_parcial_error_con_recover(self):
        self._crear_journal('{"fase": "aplicando", "entradas": []}\n')
        r = _por_codigo(self.doctor(), "HARMESSI-MIGRACION")
        self.assertEqual([x.nivel for x in r], [doctor_mod.NIVEL_ERROR])
        self.assertIn("python -m tools.ds_init recover --destino", r[0].mensaje)
        self.assertIn("--execute", r[0].mensaje)

    def test_journal_ilegible_error(self):
        self._crear_journal("{ no es json")
        r = _por_codigo(self.doctor(), "HARMESSI-MIGRACION")
        self.assertEqual([x.nivel for x in r], [doctor_mod.NIVEL_ERROR])

    def test_staging_huerfano_error(self):
        (self.repo / ".ds_init_staging_20260101T000000000000Z").mkdir()
        r = _por_codigo(self.doctor(), "HARMESSI-MIGRACION")
        self.assertEqual([x.nivel for x in r], [doctor_mod.NIVEL_ERROR])
        self.assertIn("recover", r[0].mensaje)

    def test_lock_huerfano_warn(self):
        (self.repo / ".ds_init" / "lock").write_text("{}", encoding="utf-8")
        r = _por_codigo(self.doctor(), "HARMESSI-MIGRACION")
        self.assertEqual([x.nivel for x in r], [doctor_mod.NIVEL_WARN])
        self.assertIn("lock", r[0].mensaje)

    def test_journal_completo_sin_limpiar_warn(self):
        self._crear_journal('{"fase": "completo", "entradas": []}\n')
        r = _por_codigo(self.doctor(), "HARMESSI-MIGRACION")
        self.assertEqual([x.nivel for x in r], [doctor_mod.NIVEL_WARN])
        self.assertIn("recover", r[0].mensaje)

    def test_archivo_ausente_se_distingue_de_drift(self):
        (self.repo / RUTA_NUEVA).unlink()
        r = _por_codigo(self.doctor(), "HARMESSI-DRIFT-FALTANTE")
        self.assertTrue(r)
        self.assertIn("instalación incompleta", r[0].mensaje)

    def test_tras_upgrade_sin_hallazgos_nuevos(self):
        base = _no_ok(self.doctor())
        self.simular_v010()
        # Antes del upgrade aparece el WARN de versión.
        versiones = _por_codigo(self.doctor(), "HARMESSI-VERSION")
        self.assertEqual([x.nivel for x in versiones], [doctor_mod.NIVEL_WARN])
        codigo, _out, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0, err)
        _commit_todo(self.repo, "post upgrade")
        self.assertEqual(base, _no_ok(self.doctor()))

    def test_doctor_no_modifica_el_arbol(self):
        self._crear_journal('{"fase": "aplicando", "entradas": []}\n')
        antes = _hashes_sin_cache(self.repo)
        self.doctor()
        self.assertEqual(antes, _hashes_sin_cache(self.repo))


if __name__ == "__main__":
    unittest.main()
