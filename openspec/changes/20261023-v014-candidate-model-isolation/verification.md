# Verificación — 20261023-v014-candidate-model-isolation

## Resumen
Contrato `Candidate`, almacenamiento aislado bajo `.harmessi/improvement/` y budgets de mejora con techos duros (`tools/harmessi_improve/{candidate,budget}.py`).

## Evidencia obtenida
- `python -m unittest discover -s tools/harmessi_improve/tests -t .`: 71 tests OK (3 skips: creación de symlinks no disponible).
- `test_v014_improve_neutrality`, `test_architecture_boundaries`, `test_manifest_completitud`: 26 OK.
- Reviewer (1 ciclo): 0 BLOCKER, 1 HIGH (lost update sin lock en budget), 8 MED, 8 LOW. Corregidos: lock de archivo con test de threads, symlinks/junctions en base y raíz, revalidación completa al cargar (estado, historial, evidencia, superficie), formato estricto de ids/evidencia, canonicalización de ruta en id, rollback ante fallo de escritura, fechas naive como UTC, fsync, ids con fullmatch, NUL en ruta, imports dentro de la allowlist del spec (R13).
- No se hizo segundo ciclo: los fixes están cubiertos por tests nuevos (`test_hardening.py`).

## Limitaciones
`desde_dict` rechaza bases con mayúsculas en FS case-sensitive por canonicalización con casefold (aceptable: las superficies Optimizable son minúsculas). Mensajes de `PresupuestoInvalido` por OSError del JSON pueden incluir texto del sistema. Sin CLI (Change 5).

## Divergencias respecto del SDD
R6: rutas no-str/absolutas/`..` devuelven `RUTA_INVALIDA` (rechazo equivalente a Protected por fail-safe). La API ganó parámetros opcionales (`ahora`, `presupuesto`) para tests deterministas.

## Resultado final
Change 1 cerrado; R1–R13 verificados por tests.
