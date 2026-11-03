# Propuesta — 20261023-v014-release-hardening

## Problema
v0.14 (Changes 0–5) debe cerrarse como release verificable: versión, notas, inventario de contratos, dogfood de mejora basada en evidencia, regresión completa, install/upgrade, Doctor, baseline gestionado y privacidad.

## Objetivo
Publicar Harmessi v0.14.0 «Evidence-Driven Harness Improvement» sin features nuevas.

## Evidencia
Verificación de C1–C5 (`openspec/changes/20261023-v014-*/verification.md`), `docs/roadmap/v0.14.md`, patrón de `20261021-v013-release-hardening`.

## Supuestos descartados
- Promover una candidate real en el release: el dogfood termina en `promotion proposal ready`; el gate T1 se valida con fakes.
- Instalar `harmessi_improve`: es solo-checkout como `harmessi_bench` (decisión D1).

## Alcance
Marcadores de versión, `docs/releases/v0.14.0.md`, README, inventario de contratos, smoke de release, dogfood A–I como tests, CI de portabilidad (tests nuevos, acciones al día si es compatible), baseline `.ds_init/control.json` (una vez), regresión, install/upgrade, Doctor, privacidad, auditoría de deuda hacia v1.0.

## Fuera de alcance
Features nuevas, cambios al trust model, promoción real, push de `v0.14-dev`.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-10-23
- Alcance aprobado: Harmessi v0.14 Change 6
- Versión de artefactos referenciada: ver control.json
