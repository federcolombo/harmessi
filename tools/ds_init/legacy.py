"""Inferencia de `installation_stage` para instalaciones anteriores a
Change 7 v0.3 (`20260915-progressive-capability-installation-and-scaffold`),
que no tenían noción de stage y siempre instalaban el 100% del manifiesto de
su época (`incluye_todo: true`).

Módulo pequeño de `tools/ds_init/` (el instalador), no de `tools/dsguard/`
(la inferencia opera sobre archivos del instalador, no sobre estado de
madurez, ver `design.md` §7 del change). No se instala en ningún destino —
como el resto de `tools/ds_init/`, es tooling del propio repo Harmessi.

`inferir_installation_stage` es una función PURA: nunca escribe nada, nunca
se invoca automáticamente en una lectura simple. Solo la usan `cli.py` (como
base antes de calcular el delta de `sync`) y `tools/harmessi/doctor.py`
(solo para mostrar en `HARMESSI-INSTALLATION-STAGE`, nunca para persistir).
"""
from __future__ import annotations

from pathlib import Path

from .manifest import manifest_para_perfil


def inferir_installation_stage(destino, perfil: str) -> str:
    """`"production"` si TODOS los archivos con `stage_minimo="experiment"`
    del manifiesto vigente del `perfil` están presentes en `destino` (única
    señal confiable disponible para instalaciones anteriores a este change —
    ver R6 de `spec.md`); `"discovery"` en cualquier otro caso.

    Nunca distingue `experiment`/`production_candidate`/`production` entre sí
    a partir de archivos legacy — no hay señal para eso, se asume el máximo
    compatible con lo pedido por el usuario (piso conservador: `"discovery"`
    si ni siquiera los archivos de `experiment` están completos)."""
    destino = Path(destino)
    entradas_experiment = [
        entrada for entrada in manifest_para_perfil(perfil) if entrada.stage_minimo == "experiment"
    ]
    if entradas_experiment and all((destino / entrada.destino).exists() for entrada in entradas_experiment):
        return "production"
    return "discovery"
