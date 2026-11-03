# Tareas — 20260916-portable-core

estado: en_progreso

## Invocaciones planificadas
- Lead: `ARCHITECTURE.md` (ya escrito directamente, documentación).
- `python-data-engineer` (1 sesión chica): `tools/tests/test_architecture_boundaries.py`.
- Lead: corre el test, verifica que realmente protege algo (criterio de aceptación 2), regresión,
  manifest parity, doctor, commit local. Sin reviewer dedicado — el "review" real es que el test
  mismo debe fallar ante un acoplamiento inyectado a propósito, verificado por el Lead.

## Tareas
- [x] `ARCHITECTURE.md`.
- [ ] `tools/tests/test_architecture_boundaries.py`.
- [ ] Verificación de que el test falla ante un acoplamiento inyectado (prueba, no se commitea).
- [ ] Regresión + manifest parity + doctor.

## Dependencias
Ninguna. No se toca ningún archivo de producción existente.

## Próximo paso exacto
N/A.
