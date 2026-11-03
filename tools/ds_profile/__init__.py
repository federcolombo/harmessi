"""`ds_profile`: profiling determinista de datasets CSV/Parquet (Bloque 6,
`20260911-ds-profile-project-eda`).

Paquete standalone: no importa `tools/ds_guard.py` ni `tools/nbrunner`.
Invocación: `python -m tools.ds_profile run --input <ruta> --output <dir>`.

Solo biblioteca estándar para CSV. Parquet requiere `pyarrow`, importado de
forma perezosa (ver `io_readers.py`) -- si falta, termina con exit code 3 y
un mensaje claro, sin generar ningún archivo de salida parcial.

`holdout_guard.py` es la única excepción a "sin dependencias externas al
paquete": reusa `dsguard.pathguard`/`dsguard.repo` de forma explícita, mismo
patrón `sys.path.insert` que `tools/nbrunner/execute.py`.
"""
