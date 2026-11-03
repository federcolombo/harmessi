"""Paquete `ds_init`: inicializador del harness de agentes/tooling para proyectos
de ciencia de datos (Python + Jupyter). Solo biblioteca estándar (ver `spec.md`
requisito R13 del cambio `20260909-inicializador-harness-datos`).

Uso: `python -m tools.ds_init --destino <ruta> --nombre <proyecto> [--dry-run|--execute]`.
"""
from .version import HARNESS_VERSION

__all__ = ["HARNESS_VERSION"]
