"""Preservación (v0.11 Change 5, R8): `upgrade` y `recover` dejan byte-idénticos
los archivos del proyecto (guardrails customizado, amendments, aprobaciones,
ledger, adopciones, Cards, Data Contracts, GLOSSARY, notebooks, data) y no
adoptan el drift de un managed modificado por el usuario. Los contenidos son
sintéticos: lo que se verifica son bytes, no la semántica de cada cadena."""
from __future__ import annotations

import hashlib
import json
import unittest
from unittest import mock

from tools.ds_init import writer
from tools.ds_init.tests.test_upgrade import (
    RUTA_DRIFT,
    RUTA_GUARDRAILS,
    _BaseUpgrade,
    _commit_todo,
    _leer_control,
)

_CAMBIO = "20261019-demo"
ARCHIVOS_PROYECTO = {
    "GLOSSARY.md": "# Glosario\n\n- termino: definicion propia\n",
    f"openspec/changes/{_CAMBIO}/amendments.jsonl": '{"seq": 1, "tipo": "scope", "prev": null}\n',
    f"openspec/changes/{_CAMBIO}/control.json": json.dumps(
        {"estado": "implementacion", "aprobaciones": {"proposal": {"canal": "console_confirmed", "hash": "abc"}}},
        indent=2,
    )
    + "\n",
    "openspec/decisions/ledger.jsonl": (
        '{"id": "D-001", "version": 1, "texto": "decision legacy v1"}\n'
        '{"id": "D-002", "version": 2, "prev_hash": "h1", "texto": "decision encadenada v2"}\n'
    ),
    "openspec/decisions/guardrails-adoptions.jsonl": '{"seq": 1, "campo": "holdouts", "valor": "data/holdout.csv"}\n',
    "governance/cards/data_card_demo.json": '{"id": "card-demo", "dataset": "ventas"}\n',
    "governance/contracts/contrato_demo.yaml": "id: contrato-demo\ncolumnas:\n  - nombre: monto\n",
    "notebooks/01_eda.ipynb": '{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}\n',
    "data/ventas.csv": "id,monto\n1,10\n2,20\n",
}


def _sha(repo, ruta) -> str:
    return hashlib.sha256((repo / ruta).read_bytes()).hexdigest()


class TestPreservacion(_BaseUpgrade):
    def preparar_proyecto(self) -> list:
        """Crea los archivos del proyecto, customiza guardrails y simula v0.10
        con un managed en drift. Devuelve las rutas a vigilar."""
        for ruta, contenido in ARCHIVOS_PROYECTO.items():
            p = self.repo / ruta
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(contenido, encoding="utf-8", newline="")
        guardrails = self.repo / RUTA_GUARDRAILS
        datos = json.loads(guardrails.read_text(encoding="utf-8"))
        datos["holdouts"] = ["data/holdout.csv"]
        datos["secretos_extra"] = ["secrets/**"]
        guardrails.write_text(json.dumps(datos, indent=2) + "\n", encoding="utf-8", newline="")
        _commit_todo(self.repo, "archivos del proyecto")
        self.simular_v010(con_drift=True)
        return list(ARCHIVOS_PROYECTO) + [RUTA_GUARDRAILS, RUTA_DRIFT]

    def assert_intactos(self, antes: dict, etapa: str) -> None:
        for ruta, sha in antes.items():
            self.assertEqual(sha, _sha(self.repo, ruta), f"{etapa}: {ruta} cambió")

    def test_upgrade_preserva_archivos_del_proyecto_y_drift(self):
        vigilados = self.preparar_proyecto()
        antes = {r: _sha(self.repo, r) for r in vigilados}
        sha_baseline_drift = {e["ruta"]: e["sha256"] for e in _leer_control(self.repo)["archivos"]}[RUTA_DRIFT]

        codigo, _out, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0, err)
        self.assert_intactos(antes, "upgrade")
        # El drift sigue siendo drift: el baseline no lo adoptó.
        sha_post = {e["ruta"]: e["sha256"] for e in _leer_control(self.repo)["archivos"]}[RUTA_DRIFT]
        self.assertEqual(sha_baseline_drift, sha_post)

        # Segunda corrida (idempotencia) tampoco los toca.
        _commit_todo(self.repo, "post upgrade")
        codigo, _out, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0, err)
        self.assert_intactos(antes, "upgrade idempotente")

    def test_interrupcion_recover_upgrade_preserva(self):
        vigilados = self.preparar_proyecto()
        antes = {r: _sha(self.repo, r) for r in vigilados}

        # Interrupción simulada en control_pendiente, sin rollback automático.
        with mock.patch.object(
            writer, "_revertir_journal", return_value=[{"destino": "x", "error": "proceso muerto"}]
        ), mock.patch("tools.ds_init.control.generar_control", side_effect=OSError("corte")):
            codigo, _out, _err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 1)
        self.assert_intactos(antes, "tras interrupción")

        codigo, _out, err = _correr_recover(self.repo, "--execute")
        self.assertEqual(codigo, 0, err)
        self.assert_intactos(antes, "tras recover")

        codigo, _out, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0, err)
        self.assert_intactos(antes, "upgrade tras recover")


def _correr_recover(repo, *extra):
    from tools.ds_init.tests.test_upgrade import _correr

    return _correr(["recover", "--destino", str(repo), *extra])


if __name__ == "__main__":
    unittest.main()
