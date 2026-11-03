"""Doctor y hash managed cross-platform (R14-R19, R41, R42): `_check_hashes_drift` con
`managed_hash.verificar_entrada`. Directorios temporales y bytes explícitos (sin depender
de `core.autocrlf`)."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.ds_init import managed_hash as mh
from tools.ds_init import manifest as manifest_mod
from tools.dsguard import checks
from tools.harmessi import doctor as doctor_mod

RUTA_GUARDRAILS = ".claude/guardrails.json"
COMANDO_MIGRACION = "python -m tools.ds_init migrate-hashes --execute"


class _Base(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="doctor_managed_hash_"))
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)

    def escribir(self, ruta: str, datos: bytes) -> Path:
        p = self.repo / ruta
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(datos)
        return p

    def entrada_actual(self, ruta: str, bytes_baseline: bytes) -> dict:
        """Entrada con `hash_alg` vigente calculada con la primitive oficial sobre `bytes_baseline`."""
        aux = self.escribir("_baseline_aux/" + ruta.replace("/", "_"), bytes_baseline)
        return {
            "ruta": ruta,
            "sha256": mh.hash_managed_file(aux, mh.ALG_TEXTO),
            "hash_alg": mh.ALG_TEXTO,
        }

    @staticmethod
    def entrada_legacy(ruta: str, bytes_baseline: bytes) -> dict:
        return {"ruta": ruta, "sha256": hashlib.sha256(bytes_baseline).hexdigest()}

    def drift(self, *entradas):
        return doctor_mod._check_hashes_drift(self.repo, {"archivos": list(entradas)})


def _status(resultados):
    return [r.status for r in resultados]


class TestAlgoritmoActual(_Base):
    def test_lf_y_crlf_sin_drift(self):
        entrada = self.entrada_actual("tools/x.py", b"hello\nworld\n")
        for contenido in (b"hello\nworld\n", b"hello\r\nworld\r\n"):
            with self.subTest(contenido=contenido):
                self.escribir("tools/x.py", contenido)
                r = self.drift(entrada)
                self.assertEqual(_status(r), [checks.STATUS_PASS])
                self.assertNotIn(COMANDO_MIGRACION, r[0].message)

    def test_cambios_reales_son_warn(self):
        entrada = self.entrada_actual("tools/x.py", b"hello\nworld\n")
        casos = {
            "mayuscula": b"hello\nWORLD\n",
            "trailing_space": b"hello \nworld\n",
            "tab": b"hello\n\tworld\n",
        }
        for nombre, contenido in casos.items():
            with self.subTest(caso=nombre):
                self.escribir("tools/x.py", contenido)
                r = self.drift(entrada)
                self.assertEqual(_status(r), [checks.STATUS_WARN])
                self.assertEqual(r[0].code, "HARMESSI-DRIFT")
                self.assertIn("Modificado desde la instalación: tools/x.py", r[0].message)

    def test_algoritmo_desconocido_es_fail(self):
        self.escribir("tools/x.py", b"hello\n")
        entrada = {"ruta": "tools/x.py", "sha256": "0" * 64, "hash_alg": "sha256/futuro/v9"}
        r = self.drift(entrada)
        self.assertEqual(_status(r), [checks.STATUS_FAIL])
        self.assertEqual(r[0].code, "HARMESSI-DRIFT")
        self.assertIn("tools/x.py", r[0].message)
        self.assertIn("sha256/futuro/v9", r[0].message)

    def test_faltante_se_mantiene(self):
        entrada = self.entrada_actual("tools/x.py", b"a\n")
        r = self.drift(entrada)
        self.assertEqual([x.code for x in r], ["HARMESSI-DRIFT-FALTANTE"])
        self.assertEqual(_status(r), [checks.STATUS_FAIL])


class TestLegacy(_Base):
    def test_legacy_lf_con_checkout_crlf_es_informativo(self):
        self.escribir("tools/x.py", b"hello\r\nworld\r\n")
        r = self.drift(self.entrada_legacy("tools/x.py", b"hello\nworld\n"))
        self.assertEqual(_status(r), [checks.STATUS_PASS])
        self.assertEqual(r[0].code, "HARMESSI-DRIFT")
        self.assertIn(COMANDO_MIGRACION, r[0].message)
        self.assertIn("1 archivo", r[0].message)

    def test_legacy_crudo_identico_tambien_es_informativo(self):
        self.escribir("tools/x.py", b"hello\n")
        r = self.drift(self.entrada_legacy("tools/x.py", b"hello\n"))
        self.assertEqual(_status(r), [checks.STATUS_PASS])
        self.assertIn(COMANDO_MIGRACION, r[0].message)

    def test_legacy_modificado_es_warn(self):
        self.escribir("tools/x.py", b"hello\r\nWORLD\r\n")
        r = self.drift(self.entrada_legacy("tools/x.py", b"hello\nworld\n"))
        self.assertEqual(_status(r), [checks.STATUS_WARN])
        self.assertNotIn(COMANDO_MIGRACION, r[0].message)

    def test_legacy_binario_con_eol_alterado_es_warn(self):
        # En binario el legacy solo acepta el hash crudo: una diferencia de EOL es drift real.
        self.escribir("assets/x.bin", b"ab\r\ncd\r\n")
        entrada = self.entrada_legacy("assets/x.bin", b"ab\ncd\n")
        with patch.object(
            doctor_mod.manifest_mod, "contenido_de", return_value=mh.CONTENIDO_BINARIO
        ):
            r = self.drift(entrada)
        self.assertEqual(_status(r), [checks.STATUS_WARN])
        self.assertNotIn(COMANDO_MIGRACION, r[0].message)

    def test_legacy_se_agrega_aparte_si_hay_otros_warn(self):
        self.escribir("tools/a.py", b"hello\r\n")
        self.escribir("tools/b.py", b"cambiado\n")
        r = self.drift(
            self.entrada_legacy("tools/a.py", b"hello\n"),
            self.entrada_legacy("tools/b.py", b"original\n"),
        )
        self.assertEqual(sorted(_status(r)), sorted([checks.STATUS_WARN, checks.STATUS_PASS]))
        informativos = [x for x in r if x.status == checks.STATUS_PASS]
        self.assertEqual(len(informativos), 1)
        self.assertIn(COMANDO_MIGRACION, informativos[0].message)


class TestGuardrailsEol(_Base):
    def setUp(self):
        super().setUp()
        plantilla = manifest_mod.raiz_repo_origen() / RUTA_GUARDRAILS
        # Baseline canónico en LF, independiente del checkout del host.
        self.base_lf = plantilla.read_bytes().replace(b"\r\n", b"\n")
        self.entrada = self.entrada_actual(RUTA_GUARDRAILS, self.base_lf)

    def test_solo_eol_no_agrega_drift(self):
        for contenido in (self.base_lf, self.base_lf.replace(b"\n", b"\r\n")):
            with self.subTest(crlf=b"\r\n" in contenido):
                self.escribir(RUTA_GUARDRAILS, contenido)
                r = self.drift(self.entrada)
                self.assertEqual(_status(r), [checks.STATUS_PASS])

    def test_customizacion_no_soportada_sigue_siendo_drift(self):
        datos = json.loads(self.base_lf.decode("utf-8"))
        datos["campo_no_soportado_xyz"] = {"a": 1}
        self.escribir(RUTA_GUARDRAILS, json.dumps(datos, indent=2).encode("utf-8"))
        r = self.drift(self.entrada)
        self.assertEqual(_status(r), [checks.STATUS_WARN])
        self.assertIn(RUTA_GUARDRAILS, r[0].message)

    def test_customizacion_soportada_no_es_drift(self):
        datos = json.loads(self.base_lf.decode("utf-8"))
        datos["version"] = 2
        datos["autonomy"] = {"mode": "autonomous", "budgets": {"aggregate_minutes": 120, "max_sessions": 3}}
        self.escribir(RUTA_GUARDRAILS, json.dumps(datos, indent=2).encode("utf-8"))
        r = self.drift(self.entrada)
        self.assertNotIn(checks.STATUS_WARN, _status(r))
        self.assertNotIn(checks.STATUS_FAIL, _status(r))


if __name__ == "__main__":
    unittest.main()
