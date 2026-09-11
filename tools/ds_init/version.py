"""Versión semver del harness instalable por `ds_init`.

Se usa para: (a) el bloque delimitado idempotente que se inserta en `CLAUDE.md`
del destino (`<!-- ds_init:inicio v<version> -->`), y (b) el campo `version` de
`.ds_init/control.json` que se escribe en el destino tras una instalación
exitosa (implementado en la Sesión 2, `control.py`).

No se implementan comandos de actualización/desinstalación en este MVP (R15);
este archivo solo deja el número fijo para que una fase futura pueda diffear
contra la lista de hashes instalados.
"""

HARNESS_VERSION = "0.2.0"
