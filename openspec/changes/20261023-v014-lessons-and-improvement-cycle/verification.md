# Verificación — 20261023-v014-lessons-and-improvement-cycle

## Resumen
`lessons.py` (contrato estructurado, privacidad, aplicabilidad, vigencia, creación gobernada), `cycle.py` (ciclo acotado, sin anidamiento) y `cli.py` / `__main__.py` (`python -m tools.harmessi_improve`).

## Evidencia obtenida
- `unittest discover tools/harmessi_improve/tests`: 268 tests OK (5 skips: symlinks no disponibles). Neutralidad, arquitectura y completitud del manifest: 29 OK. CLI: 21 tests OK (incluidos en los 268).
- Reviewer (1 ciclo, parte A): 0 BLOCKER, 2 HIGH, 6 MED, 6 LOW. Corregidos: normalización común del GLOSSARY (NFC, espacios, `-`/`_`) para texto, tags e ids (H1/H2, compartida con candidate); lock del ciclo con token propio y retiro atómico de stale (M1); `PresupuestoAgotado` y errores de datos en todas las etapas preservan el resultado parcial (M2); rutas relativas con extensión o `~/` rechazadas (M3); escaneo de `probe_id`/`suite_id`/`deprecated_reason` (M4); `detenido_por` con nombres de `budget` (M6); validación previa de `2*repeats` y suite (L1); coherencia de estado y fechas al cargar (L2); veredictos opuestos → `hypothesis` (L4).
- Deuda barata auditada: dsimpact fail-open y `## Skills cargados` duplicada ya cerradas en v0.13; H1 (atribución de runtime) sigue UNCONFIRMED y no se toca. Acciones de Node en CI: se decide en Change 6.

## Limitaciones
El escaneo de privacidad es heurístico: texto libre de hasta 500 caracteres puede contener un prompt o una fila que `redactar_texto` no detecta (la defensa es el límite de longitud y que la creación exige un Change abierto). Restauración del lock stale de mejor esfuerzo. Rechazo de symlink final de lesson sin test (Windows sin permisos). Un candidate `inconclusive` no se reintenta desde el ciclo (probe_id determinista).

## Divergencias respecto del SDD
`detenido_por` incluye `"rechazo"` para fallos de arranque del ciclo (`CICLO_INVALIDO`, `SUITE_INVALIDA`). `cycle` terminado por presupuesto sale con exit 0 (fin determinista esperado).

## Resultado final
Change 5 cerrado; R1–R10 verificados por tests.
