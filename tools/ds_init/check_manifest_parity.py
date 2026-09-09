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

from .manifest import MANIFEST, PLANTILLA, VERBATIM, raiz_repo_origen


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


def main() -> int:
    faltantes = verificar_rutas_verbatim()
    plantillas = listar_plantillas()

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

    return 1 if faltantes else 0


if __name__ == "__main__":
    sys.exit(main())
