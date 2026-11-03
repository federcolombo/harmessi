# Proposal — 20260916-portable-core

## Contexto

El roadmap (`docs/roadmap/v0.4.md`) pide reducir el acoplamiento entre el core de Harmessi y Claude
Code. Una reestructuración física (mover/renombrar módulos, separar lógica de decisión del I/O de
stdin en `hook_presupuesto.py`/`hook_validar_comando.py`) es un cambio arquitectónico material con
riesgo real de romper el contrato de hooks de instalaciones existentes — decisión explícita del
usuario (tras STOP de esta sesión): **alcance mínimo, sin riesgo**, para este Change.

## Qué se construye

1. `ARCHITECTURE.md` (raíz del repo): inventario explícito core/adapter, reglas de dependencia,
   deuda concreta (incluye el caso especial de `pathguard.py`, el eager-import de `ds_guard.py`, y
   la falta de separación en `hook_presupuesto.py`/`hook_validar_comando.py`).
2. `tools/tests/test_architecture_boundaries.py`: tests estructurales livianos (reusa el patrón ya
   establecido por `test_manifest_dsguard_parity.py`: escaneo de imports vía `ast`) que verifican
   las reglas de dependencia de `ARCHITECTURE.md` §3 no se violen, y fallan si alguien agrega
   silenciosamente un nuevo acoplamiento core→adapter.
3. Registro de deuda para la reestructuración física real, cuando exista necesidad concreta
   (multi-provider, fuera de alcance de v0.4).

## Qué NO se construye

Ningún archivo se mueve, renombra, ni cambia de comportamiento. Ningún import existente cambia.
`pathguard.py`/`hook_presupuesto.py`/`hook_validar_comando.py` no se refactorizan. Sin
multi-provider, sin adapters nuevos implementados.
