"""Tests de `tools.dsguard.mlops_evidence` (Change 6, v0.3:
20260915-readiness-and-promotion) -- mecanismo genérico de evidencia de
artifact para los tiers `production_readiness`/`operations`.

Sigue el mismo patrón de `test_pathguard.py` (`_escribir_config`) y de
`test_mlops_foundations.py` (`_crear_repo_git_temporal`, aunque acá no
hace falta git real -- `mlops_evidence` no llama `repo.get_head`, solo
`repo.path_matches_any`, que es pura). Nunca usa este repositorio real
como fixture.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.dsguard import lifecycle, mlops_evidence


def _crear_dir_temporal(prefix: str = "mlops_evidence_test_") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def _escribir_config(repo: Path, datos: dict) -> Path:
    dir_claude = repo / ".claude"
    dir_claude.mkdir(parents=True, exist_ok=True)
    ruta = dir_claude / "guardrails.json"
    ruta.write_text(json.dumps(datos, indent=2), encoding="utf-8")
    return ruta


def _fecha(delta_horas: float) -> str:
    momento = datetime.now(timezone.utc) + timedelta(hours=delta_horas)
    return momento.strftime("%Y-%m-%dT%H:%M:%SZ")


class _BaseConLifecycle(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()
        lifecycle.lifecycle_init(self.repo)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _crear_artifact(self, nombre: str = "evidencia.txt", contenido: bytes = b"contenido") -> Path:
        ruta = self.repo / nombre
        ruta.write_bytes(contenido)
        return ruta


# --- agregar_evidencia: caso exitoso --------------------------------------

class TestAgregarEvidenciaExitoso(_BaseConLifecycle):
    def test_artifact_valido_agrega_entrada(self):
        self._crear_artifact()
        resultado = mlops_evidence.agregar_evidencia(
            self.repo, "production_readiness", "packaging", "evidencia.txt", "empaquetado ok"
        )
        self.assertTrue(resultado["agregado"])
        self.assertFalse(resultado["duplicado"])
        entrada = resultado["entrada"]
        self.assertEqual(entrada["tipo"], "artifact_evidence")
        self.assertEqual(entrada["path"], "evidencia.txt")
        self.assertEqual(entrada["reason"], "empaquetado ok")
        self.assertIn("sha256", entrada)
        self.assertIn("utc", entrada)

        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        evidencia = estado["mlops"]["production_readiness"]["packaging"]["evidencia"]
        self.assertEqual(len(evidencia), 1)
        self.assertEqual(evidencia[0]["path"], "evidencia.txt")

    def test_artifact_en_subdirectorio_ruta_relativa_posix(self):
        (self.repo / "artifacts").mkdir()
        (self.repo / "artifacts" / "a.txt").write_bytes(b"x")
        resultado = mlops_evidence.agregar_evidencia(
            self.repo, "operations", "monitoring", "artifacts/a.txt", "monitoreo documentado"
        )
        self.assertEqual(resultado["entrada"]["path"], "artifacts/a.txt")


# --- agregar_evidencia: rechazos de dominio -------------------------------

class TestAgregarEvidenciaRechazos(_BaseConLifecycle):
    def test_artifact_fuera_del_repo_absoluta(self):
        otro = _crear_dir_temporal("mlops_evidence_test_otro_")
        try:
            fuera = otro / "x.txt"
            fuera.write_bytes(b"x")
            with self.assertRaises(mlops_evidence.EvidenciaError):
                mlops_evidence.agregar_evidencia(
                    self.repo, "production_readiness", "packaging", str(fuera), "motivo"
                )
        finally:
            shutil.rmtree(otro, ignore_errors=True)

    def test_artifact_fuera_del_repo_traversal(self):
        with self.assertRaises(mlops_evidence.EvidenciaError):
            mlops_evidence.agregar_evidencia(
                self.repo, "production_readiness", "packaging", "../fuera.txt", "motivo"
            )

    def test_artifact_inexistente(self):
        with self.assertRaises(mlops_evidence.EvidenciaError):
            mlops_evidence.agregar_evidencia(
                self.repo, "production_readiness", "packaging", "no_existe.txt", "motivo"
            )

    def test_artifact_es_directorio(self):
        (self.repo / "un_dir").mkdir()
        with self.assertRaises(mlops_evidence.EvidenciaError):
            mlops_evidence.agregar_evidencia(
                self.repo, "production_readiness", "packaging", "un_dir", "motivo"
            )

    def test_tier_invalido(self):
        self._crear_artifact()
        with self.assertRaises(mlops_evidence.EvidenciaError):
            mlops_evidence.agregar_evidencia(self.repo, "inventado", "packaging", "evidencia.txt", "motivo")

    def test_tier_foundations_rechazado(self):
        self._crear_artifact()
        with self.assertRaises(mlops_evidence.EvidenciaError):
            mlops_evidence.agregar_evidencia(self.repo, "foundations", "reproducibilidad", "evidencia.txt", "motivo")

    def test_capability_no_pertenece_al_tier(self):
        self._crear_artifact()
        with self.assertRaises(mlops_evidence.EvidenciaError):
            mlops_evidence.agregar_evidencia(
                self.repo, "production_readiness", "monitoring", "evidencia.txt", "motivo"
            )

    def test_reason_vacio(self):
        self._crear_artifact()
        with self.assertRaises(mlops_evidence.EvidenciaError):
            mlops_evidence.agregar_evidencia(self.repo, "production_readiness", "packaging", "evidencia.txt", "")

    def test_reason_ausente_none(self):
        self._crear_artifact()
        with self.assertRaises(mlops_evidence.EvidenciaError):
            mlops_evidence.agregar_evidencia(self.repo, "production_readiness", "packaging", "evidencia.txt", None)

    def test_holdout_sin_excepcion_de_lectura(self):
        _escribir_config(self.repo, {"holdouts": ["data/holdout/**"]})
        (self.repo / "data" / "holdout").mkdir(parents=True)
        (self.repo / "data" / "holdout" / "x.txt").write_bytes(b"secreto")
        with self.assertRaises(mlops_evidence.EvidenciaError):
            mlops_evidence.agregar_evidencia(
                self.repo, "production_readiness", "packaging", "data/holdout/x.txt", "motivo"
            )

    def test_holdout_con_excepcion_de_lectura_vigente_permite(self):
        _escribir_config(
            self.repo,
            {
                "holdouts": ["data/holdout/**"],
                "excepciones": [
                    {"ruta": "data/holdout/x.txt", "accion": "read", "vence_utc": _fecha(24)}
                ],
            },
        )
        (self.repo / "data" / "holdout").mkdir(parents=True)
        (self.repo / "data" / "holdout" / "x.txt").write_bytes(b"secreto")
        resultado = mlops_evidence.agregar_evidencia(
            self.repo, "production_readiness", "packaging", "data/holdout/x.txt", "motivo"
        )
        self.assertTrue(resultado["agregado"])

    def test_holdout_con_excepcion_vencida_rechaza(self):
        _escribir_config(
            self.repo,
            {
                "holdouts": ["data/holdout/**"],
                "excepciones": [
                    {"ruta": "data/holdout/x.txt", "accion": "read", "vence_utc": _fecha(-24)}
                ],
            },
        )
        (self.repo / "data" / "holdout").mkdir(parents=True)
        (self.repo / "data" / "holdout" / "x.txt").write_bytes(b"secreto")
        with self.assertRaises(mlops_evidence.EvidenciaError):
            mlops_evidence.agregar_evidencia(
                self.repo, "production_readiness", "packaging", "data/holdout/x.txt", "motivo"
            )

    def test_secreto_hardcodeado_rechaza(self):
        (self.repo / ".env").write_text("SECRET=1\n", encoding="utf-8")
        with self.assertRaises(mlops_evidence.EvidenciaError):
            mlops_evidence.agregar_evidencia(self.repo, "production_readiness", "packaging", ".env", "motivo")

    def test_secreto_extra_declarado_rechaza(self):
        _escribir_config(self.repo, {"secretos_extra": ["config/interno.json"]})
        (self.repo / "config").mkdir()
        (self.repo / "config" / "interno.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(mlops_evidence.EvidenciaError):
            mlops_evidence.agregar_evidencia(
                self.repo, "production_readiness", "packaging", "config/interno.json", "motivo"
            )

    def test_guardrails_corrupto_fail_closed(self):
        dir_claude = self.repo / ".claude"
        dir_claude.mkdir(parents=True, exist_ok=True)
        (dir_claude / "guardrails.json").write_text("esto no es json", encoding="utf-8")
        self._crear_artifact()
        with self.assertRaises(mlops_evidence.EvidenciaError):
            mlops_evidence.agregar_evidencia(
                self.repo, "production_readiness", "packaging", "evidencia.txt", "motivo"
            )

    def test_lifecycle_ausente_propaga_filenotfound_no_lo_crea(self):
        otro_repo = _crear_dir_temporal()
        try:
            (otro_repo / "evidencia.txt").write_bytes(b"x")
            with self.assertRaises(FileNotFoundError):
                mlops_evidence.agregar_evidencia(
                    otro_repo, "production_readiness", "packaging", "evidencia.txt", "motivo"
                )
            self.assertFalse(lifecycle.state_path(otro_repo).exists())
        finally:
            shutil.rmtree(otro_repo, ignore_errors=True)


# --- dedup / hash-cambia -----------------------------------------------------

class TestDedupYHashCambia(_BaseConLifecycle):
    def test_registrar_dos_veces_mismo_path_y_hash_no_duplica(self):
        self._crear_artifact()
        r1 = mlops_evidence.agregar_evidencia(
            self.repo, "production_readiness", "packaging", "evidencia.txt", "primera vez"
        )
        r2 = mlops_evidence.agregar_evidencia(
            self.repo, "production_readiness", "packaging", "evidencia.txt", "segunda vez, mismo archivo"
        )
        self.assertTrue(r1["agregado"])
        self.assertFalse(r2["agregado"])
        self.assertTrue(r2["duplicado"])
        self.assertEqual(r2["entrada"], r1["entrada"])

        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        self.assertEqual(len(estado["mlops"]["production_readiness"]["packaging"]["evidencia"]), 1)

    def test_mismo_path_contenido_distinto_agrega_segunda_entrada(self):
        self._crear_artifact(contenido=b"version 1")
        mlops_evidence.agregar_evidencia(
            self.repo, "production_readiness", "packaging", "evidencia.txt", "v1"
        )
        (self.repo / "evidencia.txt").write_bytes(b"version 2, contenido distinto")
        resultado = mlops_evidence.agregar_evidencia(
            self.repo, "production_readiness", "packaging", "evidencia.txt", "v2"
        )
        self.assertTrue(resultado["agregado"])
        self.assertFalse(resultado["duplicado"])

        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        self.assertEqual(len(estado["mlops"]["production_readiness"]["packaging"]["evidencia"]), 2)


# --- evidencia_valida ---------------------------------------------------------

class TestEvidenciaValida(_BaseConLifecycle):
    def test_sin_evidencia_false_detalle_sin_evidencia(self):
        valido, detalle = mlops_evidence.evidencia_valida(self.repo, "production_readiness", "packaging")
        self.assertFalse(valido)
        self.assertIn("sin evidencia", detalle)

    def test_archivo_presente_hash_coincide_true(self):
        self._crear_artifact()
        mlops_evidence.agregar_evidencia(
            self.repo, "production_readiness", "packaging", "evidencia.txt", "motivo"
        )
        valido, detalle = mlops_evidence.evidencia_valida(self.repo, "production_readiness", "packaging")
        self.assertTrue(valido)

    def test_archivo_borrado_despues_false_obsoleta(self):
        self._crear_artifact()
        mlops_evidence.agregar_evidencia(
            self.repo, "production_readiness", "packaging", "evidencia.txt", "motivo"
        )
        (self.repo / "evidencia.txt").unlink()
        valido, detalle = mlops_evidence.evidencia_valida(self.repo, "production_readiness", "packaging")
        self.assertFalse(valido)
        self.assertIn("obsoleta", detalle)

    def test_archivo_modificado_despues_false_hash_no_coincide(self):
        self._crear_artifact(contenido=b"original")
        mlops_evidence.agregar_evidencia(
            self.repo, "production_readiness", "packaging", "evidencia.txt", "motivo"
        )
        (self.repo / "evidencia.txt").write_bytes(b"modificado despues de registrar")
        valido, detalle = mlops_evidence.evidencia_valida(self.repo, "production_readiness", "packaging")
        self.assertFalse(valido)
        self.assertIn("obsoleta", detalle)


if __name__ == "__main__":
    unittest.main()
