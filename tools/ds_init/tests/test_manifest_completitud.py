"""R1 (Change 5 v0.11): completitud del MANIFEST por análisis AST.

Parte de los `.py` de `tools/` que SÍ están en `MANIFEST` (entrypoints
instalados), sigue sus imports (relativos y absolutos, sin importar los
módulos) hacia otros `.py` bajo `tools/` y falla, con el nombre del módulo, si
alguno alcanzable no está en el MANIFEST ni en la allowlist «solo checkout».
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from tools.ds_init import manifest as manifest_mod

RAIZ = manifest_mod.raiz_repo_origen()

# Allowlist explícita «solo checkout»: código que vive únicamente en este
# repositorio y NO se instala en el destino. Prefijos relativos a la raíz.
SOLO_CHECKOUT = (
    "tools/ds_init/",
    "tools/harmessi/",
    "tools/fallback/",
    "tools/providers/",
    "tools/routing/",
    "tools/harmessi_bench/",
    "tools/tests/",
)


def _es_solo_checkout(ruta: str) -> bool:
    return "__pycache__" in ruta or any(ruta.startswith(p) for p in SOLO_CHECKOUT)


def _candidatos_modulo(partes: list) -> list:
    """Rutas .py posibles para el módulo `partes` (más los __init__ de sus
    paquetes padre), relativas a la raíz, que existan en disco."""
    encontrados = []
    for i in range(1, len(partes) + 1):
        base = "/".join(partes[:i])
        for cand in (f"{base}.py", f"{base}/__init__.py"):
            if (RAIZ / cand).is_file():
                encontrados.append(cand)
    return encontrados


def _imports_de(ruta: str) -> set:
    """Rutas .py (bajo tools/) importadas por el archivo `ruta`."""
    arbol = ast.parse((RAIZ / ruta).read_text(encoding="utf-8"), filename=ruta)
    paquete = ruta.split("/")[:-1]
    hallados = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                hallados.update(_candidatos_modulo(alias.name.split(".")))
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level:
                base = paquete[: len(paquete) - (nodo.level - 1)]
            else:
                base = []
            modulo = nodo.module.split(".") if nodo.module else []
            partes = base + modulo
            if partes:
                hallados.update(_candidatos_modulo(partes))
            for alias in nodo.names:
                if alias.name != "*" and partes:
                    hallados.update(_candidatos_modulo(partes + [alias.name]))
    return {h for h in hallados if h.startswith("tools/")}


def calcular_faltantes(destinos_manifest) -> list:
    """Módulos `.py` runtime alcanzables desde los entrypoints del manifest
    que no están en `destinos_manifest` ni en la allowlist solo-checkout."""
    destinos = set(destinos_manifest)
    raices = sorted(
        d for d in destinos
        if d.startswith("tools/") and d.endswith(".py") and not _es_solo_checkout(d)
        and (RAIZ / d).is_file()
    )
    vistos = set(raices)
    pendientes = list(raices)
    faltantes = set()
    while pendientes:
        actual = pendientes.pop()
        for dep in _imports_de(actual):
            if dep in vistos or _es_solo_checkout(dep):
                continue
            vistos.add(dep)
            if dep not in destinos:
                faltantes.add(dep)
            pendientes.append(dep)
    return sorted(faltantes)


class TestManifestCompletitud(unittest.TestCase):
    def test_todo_modulo_alcanzable_esta_en_manifest(self):
        destinos = [e.destino for e in manifest_mod.MANIFEST]
        faltantes = calcular_faltantes(destinos)
        self.assertEqual(
            faltantes, [],
            f"Módulos runtime alcanzables ausentes del MANIFEST: {faltantes}",
        )

    def test_detecta_modulo_removido_del_manifest(self):
        destinos = [e.destino for e in manifest_mod.MANIFEST]
        self.assertIn("tools/dsguard/scope.py", destinos)
        sin_scope = [d for d in destinos if d != "tools/dsguard/scope.py"]
        faltantes = calcular_faltantes(sin_scope)
        self.assertIn("tools/dsguard/scope.py", faltantes)


if __name__ == "__main__":
    unittest.main()
