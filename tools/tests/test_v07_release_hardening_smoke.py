"""Smokes nuevos de release hardening de v0.7 (Change 5,
`20260925-v07-release-hardening`), spec R12 y "smoke de neutralidad agregada"
(`design.md` decisión 1).

1. `TestSmokeReportingConsumption`: construye un `QualityEvidenceManifest`
   sintético 100% (Change 3), lo persiste con
   `tools.qualityevidence.evidence.write_manifest` bajo un directorio temporal
   (`tempfile`), y llama `tools.reporting.evidence.describe_source` sobre ese
   archivo -- confirma que el hash reportado coincide con el hash real del
   archivo persistido, que el `dict` resultante tiene la forma esperada
   (`kind="file"`, `role`, `path`, `sha256`, `algorithm`, `size_bytes`) y que
   ningún módulo de producción de `tools/reporting` ni de
   `tools/qualityevidence` importa al otro (mismo patrón `ast` que
   `tools/tests/test_v07_qualityevidence_neutrality.py`; NO se duplica el
   resto de esa suite, que ya cubre la frontera completa de
   `tools/qualityevidence/{core,evidence}.py`).

2. `TestSmokeNeutralidadAgregada`: en una sola pasada, escanea los 7 módulos
   nuevos de v0.7 (`tools/datacontracts/{core,validation,evolution}.py`,
   `tools/modelquality/{core,validation}.py`,
   `tools/qualityevidence/{core,evidence}.py`) contra el universo COMPLETO de
   paquetes preexistentes (`dsguard`, `ds_profile`, `dsimpact`, `reporting`,
   `providers`, `routing`, `fallback`, `harmessi_bench`), confirmando que
   ninguno de esos paquetes preexistentes importa ninguno de los 7 módulos
   nuevos -- una verificación consolidada de alto nivel, no una repetición de
   los 5 tests de neutralidad ya existentes (`test_v07_core_neutrality.py`,
   `test_v07_validation_neutrality.py`, `test_v07_modelquality_neutrality.py`,
   `test_v07_qualityevidence_neutrality.py`, `test_v07_evolution_neutrality.py`),
   que verifican cada familia por separado.

Deterministas, sin datos reales, sin red; no escriben nada fuera de un
directorio temporal (`tempfile.TemporaryDirectory`).
"""
from __future__ import annotations

import ast
import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.qualityevidence import core as qe_core
from tools.qualityevidence import evidence as qe_evidence
from tools.reporting import evidence as reporting_evidence

REPO_ORIGEN = Path(__file__).resolve().parents[2]

# `generated_at` fijo: mismo criterio que los tests de `content_sha256()` ya
# existentes en Change 3 -- determinismo sin depender del reloj real.
_GENERATED_AT_FIJO = "2026-09-25T00:00:00Z"


def _manifest_sintetico() -> qe_core.QualityEvidenceManifest:
    """`QualityEvidenceManifest` 100% sintético y genérico (sin datos reales,
    dominios ni organizaciones particulares): un único `check_result` PASS
    contra una declaración/fuente inventadas."""
    declaracion = qe_core.DeclarationRef(
        declaration_kind="data_contract",
        declaration_id="contrato_sintetico_smoke",
        version="1",
        content_sha256="a" * 64,
    )
    fuente = qe_core.EvidenceSource(
        kind="generated",
        role="input",
        description="fuente sintética de smoke de release hardening",
        params={"filas": 10},
        sha256="b" * 64,
    )
    return qe_core.QualityEvidenceManifest(
        evidence_id="qe-20260925T000000Z-abc123",
        subject_kind="data_contract_evaluation",
        declaration=declaracion,
        source=fuente,
        generated_at=_GENERATED_AT_FIJO,
        check_results=(
            {"status": "PASS", "code": "SMOKE-CHECK", "message": "check sintético de smoke"},
        ),
    )


# ---------------------------------------------------------------------------
# Helpers AST (mismo patrón que los 5 tests de neutralidad existentes de v0.7)
# ---------------------------------------------------------------------------


def _parsear(ruta_absoluta: Path) -> ast.AST:
    return ast.parse(ruta_absoluta.read_text(encoding="utf-8"), filename=str(ruta_absoluta))


def _referencias_a(ruta_absoluta: Path, paquete: str) -> list:
    """Imports del archivo que apuntan a `paquete` (`tools.<paquete>` o
    `<paquete>`) con cualquier estilo: `import`, `import x.y`, `from x import
    y`, `from . import x`, incluidos los anidados en funciones (`ast.walk`)."""
    encontradas: list = []
    for nodo in ast.walk(_parsear(ruta_absoluta)):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                partes = alias.name.split(".")
                if partes[0] == paquete or partes[:2] == ["tools", paquete]:
                    encontradas.append(f"import {alias.name}")
        elif isinstance(nodo, ast.ImportFrom):
            partes = nodo.module.split(".") if nodo.module else []
            if partes and (partes[0] == paquete or partes[:2] == ["tools", paquete]):
                encontradas.append(f"from {'.' * nodo.level}{nodo.module} import ...")
            for alias in nodo.names:
                if alias.name == paquete and (not nodo.module or nodo.module == "tools"):
                    encontradas.append(f"from {'.' * nodo.level}{nodo.module or ''} import {paquete}")
    return encontradas


# ---------------------------------------------------------------------------
# 1. Smoke de "reporting consumption" (R12)
# ---------------------------------------------------------------------------


class TestSmokeReportingConsumption(unittest.TestCase):
    def test_describe_source_hashea_manifest_sintetico_de_qualityevidence(self):
        manifest = _manifest_sintetico()
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            ruta_persistida = qe_evidence.write_manifest(repo_root, manifest)

            # (a) hash real del archivo persistido, calculado de forma
            # independiente con hashlib.sha256.
            hash_real = hashlib.sha256(ruta_persistida.read_bytes()).hexdigest()

            ruta_relativa = ruta_persistida.relative_to(repo_root).as_posix()
            resultado = reporting_evidence.describe_source(
                repo_root, ruta_relativa, role="quality_evidence"
            )

            self.assertEqual(resultado["sha256"], hash_real)

            # (b) forma esperada del dict.
            self.assertEqual(resultado["kind"], "file")
            self.assertEqual(resultado["role"], "quality_evidence")
            self.assertEqual(resultado["path"], ruta_relativa)
            self.assertIn("sha256", resultado)
            self.assertIn("algorithm", resultado)
            self.assertIn("size_bytes", resultado)
            self.assertEqual(resultado["size_bytes"], ruta_persistida.stat().st_size)

    def test_ni_reporting_evidence_ni_qualityevidence_se_importan_entre_si(self):
        """Confirmación puntual sobre los módulos concretos usados en este
        test (R12/`design.md`): no se duplica la cobertura ya exhaustiva de
        `test_v07_qualityevidence_neutrality.py` (que verifica TODA la
        frontera de `tools/qualityevidence/{core,evidence}.py`), solo se
        confirma el par de archivos que este smoke usa efectivamente."""
        reporting_evidence_py = REPO_ORIGEN / "tools" / "reporting" / "evidence.py"
        qe_core_py = REPO_ORIGEN / "tools" / "qualityevidence" / "core.py"
        qe_evidence_py = REPO_ORIGEN / "tools" / "qualityevidence" / "evidence.py"

        self.assertEqual(_referencias_a(reporting_evidence_py, "qualityevidence"), [])
        self.assertEqual(_referencias_a(qe_core_py, "reporting"), [])
        self.assertEqual(_referencias_a(qe_evidence_py, "reporting"), [])


# ---------------------------------------------------------------------------
# 2. Smoke de neutralidad agregada
# ---------------------------------------------------------------------------

MODULOS_NUEVOS_V07 = (
    "tools/datacontracts/core.py",
    "tools/datacontracts/validation.py",
    "tools/datacontracts/evolution.py",
    "tools/modelquality/core.py",
    "tools/modelquality/validation.py",
    "tools/qualityevidence/core.py",
    "tools/qualityevidence/evidence.py",
)

FAMILIAS_NUEVAS_V07 = ("datacontracts", "modelquality", "qualityevidence")

PAQUETES_PREEXISTENTES = (
    "tools/dsguard",
    "tools/ds_profile",
    "tools/dsimpact",
    "tools/reporting",
    "tools/providers",
    "tools/routing",
    "tools/fallback",
    "tools/harmessi_bench",
)


class TestSmokeNeutralidadAgregada(unittest.TestCase):
    def test_los_7_modulos_nuevos_de_v07_existen(self):
        for modulo in MODULOS_NUEVOS_V07:
            self.assertTrue((REPO_ORIGEN / modulo).is_file(), f"no existe {modulo}")

    def test_ningun_paquete_preexistente_importa_ninguna_de_las_3_familias_nuevas(self):
        """Pasada única y consolidada (spec R12/`design.md` decisión 1):
        ninguno de los 8 paquetes preexistentes importa `tools.datacontracts`,
        `tools.modelquality` ni `tools.qualityevidence`, en ningún estilo de
        import, incluidos los anidados en funciones. No repite símbolo por
        símbolo lo que ya hace cada test individual de neutralidad; da
        confianza extra de que no se coló ninguna dependencia cruzada entre
        familias al escanear el universo completo en un solo test."""
        violaciones = []
        for paquete in PAQUETES_PREEXISTENTES:
            directorio = REPO_ORIGEN / paquete
            self.assertTrue(directorio.is_dir(), f"no existe el paquete {paquete}")
            for ruta in sorted(directorio.rglob("*.py")):
                if "__pycache__" in ruta.parts or "tests" in ruta.relative_to(directorio).parts:
                    continue
                for familia in FAMILIAS_NUEVAS_V07:
                    for referencia in _referencias_a(ruta, familia):
                        violaciones.append(
                            f"{ruta.relative_to(REPO_ORIGEN).as_posix()}: {referencia}"
                        )
        self.assertEqual(
            violaciones,
            [],
            "Módulo(s) preexistente(s) que importan alguna de las 3 familias nuevas de v0.7 -- "
            f"prohibido por la regla 7-9 de ARCHITECTURE.md: {violaciones}",
        )

    def test_el_escaner_detecta_una_violacion_real_incluso_anidada(self):
        """Sanity del detector agregado (mismo criterio que
        `TestSanityDeLosDetectores` de los tests de neutralidad individuales):
        confirma que `_referencias_a` no pasa en vacío."""
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "modulo_de_prueba.py"
            ruta.write_text(
                "import json\n\ndef f():\n    from tools.datacontracts import core\n",
                encoding="utf-8",
            )
            self.assertTrue(_referencias_a(ruta, "datacontracts"))
            limpio = Path(tmp) / "modulo_limpio.py"
            limpio.write_text("import json\nfrom tools.dsguard import core\n", encoding="utf-8")
            self.assertEqual(_referencias_a(limpio, "datacontracts"), [])


if __name__ == "__main__":
    unittest.main()
