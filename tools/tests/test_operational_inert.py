"""Inercia del Corrective A (`20261005-operational-autonomy-hardening`, R47-R49).

Fija que el endurecimiento operativo NO toca la decisión de autonomía ni los
matchers compartidos: `STOP_CATALOG` y `POLICY_TABLE` intactos, `path_matches_any`
con su semántica previa y `tools/autonomy` sin imports nuevos.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from autonomy import core as autonomy_core  # noqa: E402
from dsguard import repo as repo_mod  # noqa: E402

_STOP_CLAVES_ESPERADAS = (
    "sealed_access",
    "unlisted_methodological_decision",
    "leakage_doubt",
    "new_dependency",
    "write_outside_scope",
    "secret_required",
    "data_loss_risk",
    "remediation_exhausted",
    "approach_refuted",
    "requirement_contradiction",
    "scope_expansion",
    "bypass_needed",
)


class TestAutonomiaIntacta(unittest.TestCase):
    def test_stop_catalog_sin_cambios(self):
        self.assertEqual(len(autonomy_core.STOP_CATALOG), 12)
        claves = tuple(getattr(e, "key", None) or e[0] for e in autonomy_core.STOP_CATALOG)
        self.assertEqual(claves, _STOP_CLAVES_ESPERADAS)

    def test_ningun_stop_nuevo_de_limites_o_alcance(self):
        for e in autonomy_core.STOP_CATALOG:
            texto = repr(e).lower()
            self.assertNotIn("budget", texto)
            self.assertNotIn("alcance_autorizado", texto)

    def test_policy_no_importa_nada_nuevo(self):
        arbol = ast.parse((REPO / "tools" / "autonomy" / "policy.py").read_text(encoding="utf-8"))
        modulos = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                modulos.update(a.name.split(".")[0] for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                modulos.add(nodo.module.split(".")[0])
        self.assertLessEqual(
            modulos,
            {"__future__", "typing", "types", "dataclasses", "re", "datetime", "collections", "autonomy", "core"},
        )


class TestMatcherCompartidoIntacto(unittest.TestCase):
    def test_path_matches_any_semantica_previa(self):
        self.assertTrue(repo_mod.path_matches_any("tools/a.py", ["tools/a.py"]))
        self.assertTrue(repo_mod.path_matches_any("tools/x/y.py", ["tools/**"]))
        self.assertFalse(repo_mod.path_matches_any("tools_old/y.py", ["tools/**"]))
        # Entrada de directorio plano: sigue siendo exacta en validate (legacy).
        self.assertFalse(repo_mod.path_matches_any("tools/a.py", ["tools"]))


if __name__ == "__main__":
    unittest.main()
