"""Chequeo read-only, dev-only: compara `manifest.py` contra las rutas
canónicas de este mismo repositorio (Harmessi) para detectar drift.

No es una prueba de instalación (R14, excepción explícita): no escribe nada,
no corre contra un destino, y no se instala en ningún destino. Se corre
manualmente desde la raíz de este repositorio:

    python -m tools.ds_init.check_manifest_parity

Es la única lectura de este repositorio fuera de una prueba de instalación
que `design.md` §4 autoriza explícitamente.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .manifest import EXCLUSIONES_PERMANENTES, MANIFEST, PLANTILLA, VERBATIM, raiz_repo_origen


def verificar_rutas_verbatim() -> list:
    """(a) del chequeo de paridad: cada ruta VERBATIM del manifiesto debe
    seguir existiendo en el árbol real de este repositorio."""
    raiz = raiz_repo_origen()
    faltantes = []
    for entrada in MANIFEST:
        if entrada.tratamiento != VERBATIM:
            continue
        ruta_real = raiz / entrada.fuente
        if not ruta_real.exists():
            faltantes.append(entrada.fuente)
    return faltantes


def listar_plantillas() -> list:
    """(b) del chequeo de paridad: lista las entradas PLANTILLA para que
    quien corre el chequeo revise a mano si el `.tmpl` correspondiente sigue
    reflejando la mecánica genérica del archivo fuente real (no hay
    sincronización automática — ver `design.md` §4)."""
    return [entrada.destino for entrada in MANIFEST if entrada.tratamiento == PLANTILLA]


# Allowlist «solo checkout» (R1 de Change 5 v0.11): código que vive únicamente en
# este repositorio y no se instala. Misma lista que `test_manifest_completitud`.
SOLO_CHECKOUT = (
    "tools/ds_init/",
    "tools/harmessi/",
    "tools/fallback/",
    "tools/providers/",
    "tools/routing/",
    "tools/harmessi_bench/",
    "tools/tests/",
)


def _es_runtime(ruta: str) -> bool:
    partes = ruta.split("/")
    return (
        "__pycache__" not in partes
        and "tests" not in partes
        and not any(ruta.startswith(p) for p in SOLO_CHECKOUT)
    )


def verificar_modulos_runtime_en_manifest(destinos=None) -> list:
    """(c) dirección inversa de R1: módulos `.py` runtime de este checkout bajo
    `tools/` (fuera de la allowlist solo-checkout, de los tests y de las
    exclusiones permanentes) que NO figuran como destino en el MANIFEST.
    `destinos` permite inyectar un conjunto (tests)."""
    raiz = raiz_repo_origen()
    if destinos is None:
        destinos = {e.destino for e in MANIFEST}
    destinos = set(destinos)
    ausentes = []
    for ruta in sorted((raiz / "tools").rglob("*.py")):
        rel = ruta.relative_to(raiz).as_posix()
        if not _es_runtime(rel):
            continue
        if any(rel == x or rel.startswith(x) for x in EXCLUSIONES_PERMANENTES):
            continue
        if rel not in destinos:
            ausentes.append(rel)
    return ausentes


def main() -> int:
    faltantes = verificar_rutas_verbatim()
    plantillas = listar_plantillas()
    ausentes = verificar_modulos_runtime_en_manifest()

    print("--- check_manifest_parity (read-only, dev-only) ---")
    if faltantes:
        print(f"[FALTAN] {len(faltantes)} ruta(s) VERBATIM del manifiesto ya no existen:")
        for ruta in faltantes:
            print(f"  - {ruta}")
    else:
        print("[OK] Todas las rutas VERBATIM del manifiesto existen en este repositorio.")

    print(f"\n[INFO] {len(plantillas)} entrada(s) PLANTILLA — revisar a mano que su .tmpl "
          "siga reflejando la mecánica genérica del archivo fuente real:")
    for destino in plantillas:
        print(f"  - {destino}")

    if ausentes:
        print(f"\n[AUSENTES] {len(ausentes)} módulo(s) runtime del checkout no están en el MANIFEST "
              "(agregarlos o incluirlos en la allowlist solo-checkout):")
        for ruta in ausentes:
            print(f"  - {ruta}")
    else:
        print("\n[OK] Todo módulo runtime de tools/ figura en el MANIFEST (o es solo-checkout).")

    return 1 if (faltantes or ausentes) else 0


if __name__ == "__main__":
    sys.exit(main())
