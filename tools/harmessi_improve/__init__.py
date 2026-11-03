"""harmessi_improve (v0.14): mejora gobernada del harness.

Change 1: modelo de candidate aislada y presupuestos. Una candidate es una propuesta de
reemplazo de una superficie Optimizable del harness que vive SIEMPRE bajo
`.harmessi/improvement/` y nunca modifica el archivo activo. Solo stdlib, sin red.
"""
from __future__ import annotations
