"""`tools.datasources` -- acceso neutral a fuentes de datos (v0.8 Change 1).

Este `__init__.py` no importa nada por defecto (evita acoplar el import del
paquete a `runtime`/`file_observer`, que traen I/O e `importlib`/imports
perezosos de `ds_profile`): cada módulo (`core`, `scan`, `registry`) se
importa explícitamente por quien lo necesita, siguiendo el patrón de
`tools/datacontracts` y `tools/autonomy`.
"""
from __future__ import annotations
