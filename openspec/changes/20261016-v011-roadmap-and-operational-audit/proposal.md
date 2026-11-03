# Propuesta — 20261016-v011-roadmap-and-operational-audit

> Change 0 de v0.11 («Operational Robustness & Recovery»): auditoría operacional post-v0.10 y congelamiento de roadmap. Solo docs/SDD: NO implementa nada.

## Problema
v0.10.0 está publicada con deuda operativa registrada (`docs/roadmap/v0.10.md`) y un bug real de release (módulos runtime ausentes del manifest instalado).
Esa deuda no fue contrastada con el código de `main` ni ordenada por dependencia. Sin auditoría se arriesga implementar deuda ya resuelta, duplicar
mecanismos o dejar sin cubrir la ruta de upgrade/recovery que v1.0 necesita.

## Objetivo
Auditar cada deuda contra `main` (`2e76956`), clasificarla (vigente/parcial/resuelta/diferida) y congelar un roadmap v0.11 mínimo y ordenado.

## Evidencia
Medida sobre el código actual (detalle y rutas en `docs/roadmap/v0.11.md`, tabla de auditoría):
- Git/scope: `repo.list_dirty_files` no verifica returncode; `archivos_tocados_desde_baseline` sigue degradando a `[]` ante `GitCommandError` y `except Exception`;
  rename/copy evalúa un solo lado; refs sin `--`; `text=True`; `ALCANCE-GIT-ILEGIBLE` sin documentar en `verificador.md`.
- Ledger: acciones `registrar/supersede/revocar`; sin corrección append-only; `TIPOS_DECISION` solo lo consume la CLI.
- Sesiones: literal `90` en `ds_guard.py:757`, `dsguard/core.py:72`, `dsguard/sdd.py:827`; el hook bloquea a ≤5/≤0 min sin aviso proactivo.
- Atribución/paralelismo: H1 sin evidencia de payload real; `ALCANCE-RUTA` evalúa todo el working tree.
- Instalación: todos los módulos actuales están en `MANIFEST` (verificado), pero el guard (`test_manifest_dsguard_parity`) cubre solo imports de nivel módulo de
  `ds_guard.py`; instalación interrumpida = abortar y revisar a mano; `sync` no actualiza a mismo stage; sin operación de upgrade.

## Supuestos descartados
- Que el manifest tuviera módulos faltantes hoy: verificado completo (salvo Doctor, fuera por diseño).
- Que hubiera que ampliar el enum de decisiones: no hay consumidor real.
- Que el default de 90 minutos deba cambiar: no se cambia.

## Alcance
Roadmap `docs/roadmap/v0.11.md`, línea v0.11 en `docs/roadmap/README.md` y este SDD. Cambios 1–6 definidos con objetivo, scope, boundaries,
dependencias, aceptación, riesgos y diferidos.

## Fuera de alcance
Implementar Changes 1–6; tocar `tools/**`, hooks, migrations, ledger, sesiones o Git; cambiar `ARCHITECTURE.md` o la definición de v1.0; crear roadmaps v0.12/v0.13;
versión, push, tag o publicación.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- docs/roadmap/v0.11.md
- docs/roadmap/README.md
- openspec/changes/20261016-v011-roadmap-and-operational-audit/**

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
