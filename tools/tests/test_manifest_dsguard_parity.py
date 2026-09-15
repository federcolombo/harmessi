"""Test acotado del hallazgo B1 de la auditoría de release v0.2.0
(`openspec/changes/20260911-release-v0-2-0-blockers/proposal.md`):
`tools/dsguard/decision.py` no tenía entrada en `MANIFEST`, por lo que
`ds_guard.py` fallaba con `ImportError` al primer uso en cualquier proyecto
instalado desde `main` (`tools/ds_guard.py:34`:
`from dsguard import core, decision, kdd, notebooks, repo, sdd`).

Verifica que cada nombre importado a nivel de módulo en esa línea tenga una
`EntradaManifiesto` VERBATIM en `tools.ds_init.manifest.MANIFEST` con
`destino == f"tools/dsguard/{nombre}.py"`. Deliberadamente NO es un scanner
genérico de imports de todo el repo (eso queda como deuda futura explícita,
ver "Fuera de alcance" del cambio arriba) -- se limita a los nombres que
`ds_guard.py` importa desde `dsguard` a nivel de módulo.

Lee el `tools/ds_guard.py` real de este repositorio con `ast` (en vez de una
regex de texto sobre la línea) para no depender de que el import se
mantenga en un formato exacto (reordenamiento alfabético, salto de línea,
etc.), siempre que siga siendo un `from dsguard import ...` a nivel de
módulo (no anidado en una función o condicional) -- mismo criterio de
lectura read-only, dev-only de este repositorio que ya usan
`check_manifest_parity.py` y los demás tests de `tools/tests/` (p. ej.
`test_kdd.py`/`test_decision.py`, que corren `tools/ds_guard.py` real como
subproceso).
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from tools.ds_init.manifest import MANIFEST, VERBATIM

REPO_ORIGEN = Path(__file__).resolve().parents[2]
DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"


def _nombres_importados_de_dsguard() -> list:
    """Nombres importados a nivel de módulo desde `dsguard` en
    `tools/ds_guard.py` (ej. `decision` en
    `from dsguard import core, decision, kdd, notebooks, repo, sdd`).

    Solo mira el body de nivel superior del módulo (`arbol.body`): un import
    anidado dentro de una función o condicional no cuenta, porque no rompe
    la carga del script al primer uso del mismo modo que uno a nivel de
    módulo."""
    codigo = DS_GUARD.read_text(encoding="utf-8")
    arbol = ast.parse(codigo, filename=str(DS_GUARD))
    nombres: list = []
    for nodo in arbol.body:
        if isinstance(nodo, ast.ImportFrom) and nodo.module == "dsguard" and nodo.level == 0:
            nombres.extend(alias.name for alias in nodo.names)
    return nombres


class TestParidadImportsDsguardVsManifest(unittest.TestCase):
    def test_ds_guard_importa_al_menos_un_modulo_de_dsguard(self):
        # Si esto falla, `ds_guard.py` cambió de forma tal que el parseo ya
        # no encuentra el `from dsguard import ...` esperado a nivel de
        # módulo -- revisar `_nombres_importados_de_dsguard`, no vaciar el
        # test.
        self.assertTrue(_nombres_importados_de_dsguard())

    def test_cada_modulo_importado_tiene_entrada_verbatim_en_manifest(self):
        destinos_verbatim = {
            entrada.destino for entrada in MANIFEST if entrada.tratamiento == VERBATIM
        }
        faltantes = [
            nombre
            for nombre in _nombres_importados_de_dsguard()
            if f"tools/dsguard/{nombre}.py" not in destinos_verbatim
        ]
        self.assertEqual(
            faltantes,
            [],
            "Módulo(s) de dsguard importados por ds_guard.py sin entrada VERBATIM en "
            f"MANIFEST: {faltantes} -- agregar una EntradaManifiesto en "
            "tools/ds_init/manifest.py, mismo patrón que sus hermanos "
            "(core.py/repo.py/sdd.py/kdd.py/notebooks.py).",
        )


class TestParidadManifestLifecycleYKddCompatExplicita(unittest.TestCase):
    """Regresión de `20260914-lifecycle-migration-and-kdd-repoint`: a
    diferencia de `TestParidadImportsDsguardVsManifest` (que depende de qué
    importe `ds_guard.py` a nivel de módulo), este test hardcodea los nombres
    para que siga cubriendo el caso aunque `ds_guard.py` deje de importarlos
    algún día -- `lifecycle.py` y `kdd_compat.py` deben tener entrada VERBATIM
    en MANIFEST de todos modos (los usa `kdd_compat.migrar_desde_legacy` vía
    `cmd_lifecycle_migrate`, y el storage vivo del proyecto instalado depende
    de ambos)."""

    def test_lifecycle_py_tiene_entrada_verbatim_en_manifest(self):
        destinos_verbatim = {
            entrada.destino for entrada in MANIFEST if entrada.tratamiento == VERBATIM
        }
        self.assertIn("tools/dsguard/lifecycle.py", destinos_verbatim)

    def test_kdd_compat_py_tiene_entrada_verbatim_en_manifest(self):
        destinos_verbatim = {
            entrada.destino for entrada in MANIFEST if entrada.tratamiento == VERBATIM
        }
        self.assertIn("tools/dsguard/kdd_compat.py", destinos_verbatim)


class TestParidadManifestMaturityExplicita(unittest.TestCase):
    """Regresión de `20260915-project-maturity-state-and-calibration`: mismo
    criterio que `TestParidadManifestLifecycleYKddCompatExplicita` -- nombre
    hardcodeado, no dependiente de qué importe `ds_guard.py` a nivel de
    módulo, para que `maturity.py` siga cubierto aunque el import cambie
    algún día."""

    def test_maturity_py_tiene_entrada_verbatim_en_manifest(self):
        destinos_verbatim = {
            entrada.destino for entrada in MANIFEST if entrada.tratamiento == VERBATIM
        }
        self.assertIn("tools/dsguard/maturity.py", destinos_verbatim)


class TestParidadManifestChecksExplicita(unittest.TestCase):
    """Regresión de `20260915-checks-engine-foundation`: mismo criterio que
    `TestParidadManifestLifecycleYKddCompatExplicita`/`TestParidadManifestMaturityExplicita`
    -- nombre hardcodeado, no dependiente de qué importe `ds_guard.py` a
    nivel de módulo (`checks.py` no se wirea en `ds_guard.py` en este
    change), para que `checks.py` siga cubierto por el manifiesto de todos
    modos (lo usa `harmessi doctor` vía `tools.dsguard.checks`)."""

    def test_checks_py_tiene_entrada_verbatim_en_manifest(self):
        destinos_verbatim = {
            entrada.destino for entrada in MANIFEST if entrada.tratamiento == VERBATIM
        }
        self.assertIn("tools/dsguard/checks.py", destinos_verbatim)


class TestParidadManifestMlopsFoundationsExplicita(unittest.TestCase):
    """Regresión de `20260915-mlops-foundations-experiment`: mismo criterio
    que `TestParidadManifestLifecycleYKddCompatExplicita`/
    `TestParidadManifestMaturityExplicita`/`TestParidadManifestChecksExplicita`
    -- nombre hardcodeado, no dependiente de qué importe `ds_guard.py` a
    nivel de módulo, para que `mlops_foundations.py` siga cubierto por el
    manifiesto de todos modos."""

    def test_mlops_foundations_py_tiene_entrada_verbatim_en_manifest(self):
        destinos_verbatim = {
            entrada.destino for entrada in MANIFEST if entrada.tratamiento == VERBATIM
        }
        self.assertIn("tools/dsguard/mlops_foundations.py", destinos_verbatim)


if __name__ == "__main__":
    unittest.main()
