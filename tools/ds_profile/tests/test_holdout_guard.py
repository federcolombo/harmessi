"""Tests de `tools.ds_profile.holdout_guard`. Repos sintéticos en
`tempfile.TemporaryDirectory()` -- nunca este repositorio. No requieren un
repo Git real: `verificar_permitido`/`verificar_salida_permitida` solo
tocan filesystem (resolución de rutas + lectura de `.claude/guardrails.json`),
mismo criterio que `dsguard.pathguard`."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from tools.ds_profile import holdout_guard


def _escribir_guardrails(repo_root: Path, **kwargs) -> None:
    config = {
        "version": 1,
        "holdouts": kwargs.get("holdouts", []),
        "data_raw": kwargs.get("data_raw", ["data/raw/**"]),
        "secretos_extra": kwargs.get("secretos_extra", []),
        "write_scopes": kwargs.get("write_scopes", {}),
        "excepciones": kwargs.get("excepciones", []),
    }
    ruta = repo_root / ".claude" / "guardrails.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(config), encoding="utf-8")


class TestVerificarPermitido(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo_root = Path(self._tmp.name)

    def test_sin_guardrails_json_permite(self):
        permitido, motivo = holdout_guard.verificar_permitido(self.repo_root / "cualquier.csv", self.repo_root)
        self.assertTrue(permitido)

    def test_sin_holdouts_declarados_permite(self):
        _escribir_guardrails(self.repo_root, holdouts=[])
        permitido, _ = holdout_guard.verificar_permitido(self.repo_root / "cualquier.csv", self.repo_root)
        self.assertTrue(permitido)

    def test_holdout_declarado_deniega(self):
        _escribir_guardrails(self.repo_root, holdouts=["data/sealed/**"])
        permitido, motivo = holdout_guard.verificar_permitido(
            self.repo_root / "data" / "sealed" / "secreto.csv", self.repo_root
        )
        self.assertFalse(permitido)
        self.assertIn("holdout", motivo.lower())

    def test_ruta_fuera_del_holdout_permite(self):
        _escribir_guardrails(self.repo_root, holdouts=["data/sealed/**"])
        permitido, _ = holdout_guard.verificar_permitido(
            self.repo_root / "data" / "interim" / "libre.csv", self.repo_root
        )
        self.assertTrue(permitido)

    def test_excepcion_de_lectura_vigente_permite(self):
        _escribir_guardrails(
            self.repo_root,
            holdouts=["data/sealed/secreto.csv"],
            excepciones=[{"accion": "read", "ruta": "data/sealed/secreto.csv"}],
        )
        permitido, motivo = holdout_guard.verificar_permitido(
            self.repo_root / "data" / "sealed" / "secreto.csv", self.repo_root
        )
        self.assertTrue(permitido)
        self.assertIn("excepci", motivo.lower())

    def test_excepcion_vencida_no_permite(self):
        vencida = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _escribir_guardrails(
            self.repo_root,
            holdouts=["data/sealed/secreto.csv"],
            excepciones=[{"accion": "read", "ruta": "data/sealed/secreto.csv", "vence_utc": vencida}],
        )
        permitido, _ = holdout_guard.verificar_permitido(
            self.repo_root / "data" / "sealed" / "secreto.csv", self.repo_root
        )
        self.assertFalse(permitido)

    def test_excepcion_de_escritura_no_habilita_lectura_de_holdout(self):
        _escribir_guardrails(
            self.repo_root,
            holdouts=["data/sealed/secreto.csv"],
            excepciones=[{"accion": "write", "ruta": "data/sealed/secreto.csv"}],
        )
        permitido, _ = holdout_guard.verificar_permitido(
            self.repo_root / "data" / "sealed" / "secreto.csv", self.repo_root
        )
        self.assertFalse(permitido)

    def test_excepcion_es_ruta_exacta_no_patron(self):
        # La excepción autoriza SOLO la ruta exacta declarada, no todo
        # `data/sealed/**` -- otra ruta dentro del mismo holdout sigue
        # denegada.
        _escribir_guardrails(
            self.repo_root,
            holdouts=["data/sealed/**"],
            excepciones=[{"accion": "read", "ruta": "data/sealed/secreto.csv"}],
        )
        permitido, _ = holdout_guard.verificar_permitido(
            self.repo_root / "data" / "sealed" / "otro.csv", self.repo_root
        )
        self.assertFalse(permitido)

    def test_ruta_fuera_del_repo_permite(self):
        _escribir_guardrails(self.repo_root, holdouts=["data/sealed/**"])
        with tempfile.TemporaryDirectory() as otro_dir:
            permitido, _ = holdout_guard.verificar_permitido(Path(otro_dir) / "fuera.csv", self.repo_root)
        self.assertTrue(permitido)

    def test_guardrails_json_corrupto_deniega_fail_closed(self):
        ruta = self.repo_root / ".claude" / "guardrails.json"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("{ esto no es json valido", encoding="utf-8")
        permitido, motivo = holdout_guard.verificar_permitido(self.repo_root / "a.csv", self.repo_root)
        self.assertFalse(permitido)
        self.assertIn("guardrails.json", motivo)

    def test_ruta_no_resoluble_deniega_fail_closed(self):
        # Distingue "no se pudo resolver" (error de bajo nivel) de
        # "genuinamente fuera del repo" -- ambos casos devuelven
        # `dentro_del_repo=False` desde `pathguard.resolver_ruta_relativa`,
        # pero solo el primero debe denegar (fail-closed), no permitir.
        with patch("pathlib.Path.resolve", side_effect=OSError("resolución falló")):
            permitido, motivo = holdout_guard.verificar_permitido(
                self.repo_root / "cualquier.csv", self.repo_root
            )
        self.assertFalse(permitido)
        self.assertIn("no resoluble", motivo.lower())


class TestVerificarSalidaPermitida(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo_root = Path(self._tmp.name)

    def test_sin_guardrails_json_data_raw_sigue_protegido_por_default(self):
        permitido, motivo = holdout_guard.verificar_salida_permitida(
            self.repo_root / "data" / "raw" / "salida", self.repo_root
        )
        self.assertFalse(permitido)
        self.assertIn("data/raw", motivo)

    def test_salida_fuera_de_data_raw_permite(self):
        permitido, _ = holdout_guard.verificar_salida_permitida(
            self.repo_root / ".harmessi" / "profiles", self.repo_root
        )
        self.assertTrue(permitido)

    def test_data_raw_configurado_distinto_se_respeta(self):
        _escribir_guardrails(self.repo_root, data_raw=["datos/crudos/**"])
        permitido, _ = holdout_guard.verificar_salida_permitida(
            self.repo_root / "datos" / "crudos" / "salida", self.repo_root
        )
        self.assertFalse(permitido)

    def test_holdout_declarado_en_salida_deniega_aunque_haya_excepcion_de_lectura(self):
        # Mismo criterio que `pathguard.py` (`_evaluar_ruta_estructurada`):
        # la escritura en un holdout nunca está autorizada, sin excepción
        # posible -- una excepción de lectura vigente para esa misma ruta no
        # aplica a escritura.
        _escribir_guardrails(
            self.repo_root,
            holdouts=["data/sealed/secreto.csv"],
            excepciones=[{"accion": "read", "ruta": "data/sealed/secreto.csv"}],
        )
        permitido, motivo = holdout_guard.verificar_salida_permitida(
            self.repo_root / "data" / "sealed" / "secreto.csv", self.repo_root
        )
        self.assertFalse(permitido)
        self.assertIn("holdout", motivo.lower())

    def test_ruta_de_salida_no_resoluble_deniega_fail_closed(self):
        with patch("pathlib.Path.resolve", side_effect=OSError("resolución falló")):
            permitido, motivo = holdout_guard.verificar_salida_permitida(
                self.repo_root / "cualquier.csv", self.repo_root
            )
        self.assertFalse(permitido)
        self.assertIn("no resoluble", motivo.lower())


if __name__ == "__main__":
    unittest.main()
