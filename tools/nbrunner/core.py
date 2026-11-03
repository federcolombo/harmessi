"""Reexporta el núcleo determinista ya existente en `tools/dsguard/core.py`.

No duplica nada: `hash_lf_v1` (hash de texto normalizado a LF, algoritmo
`sha256/lf/v1`), `Finding` (hallazgo de validación) y la lectura/escritura de
`control.json` viven en `dsguard.core` y se reusan tal cual acá.

No se agrega todavía una función de hash binario (análoga a `hash_lf_v1` pero
sobre bytes crudos, sin normalización de línea) — eso es de la Sesión 3
(`spec.md` requisito 5(e), integridad de entradas), no hace falta para el
schema/validaciones previas a ejecución de esta sesión.

Requiere que el directorio `tools/` esté en `sys.path` (mismo patrón que
`tools/tests/test_ds_guard.py`), porque `dsguard` y `nbrunner` son paquetes
hermanos bajo `tools/`, no un paquete anidado uno dentro del otro.
"""
from __future__ import annotations

from dsguard.core import (  # noqa: F401
    ControlJsonError,
    Finding,
    ahora_utc,
    capturar_bytes,
    escribir_control,
    escribir_texto_atomico,
    formatear_findings_json,
    formatear_findings_texto,
    hash_lf_v1,
    leer_control,
    parsear_utc,
)
