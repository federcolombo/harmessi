# Propuesta — 20260914-lifecycle-core-schema

## Problema
Harmessi v0.2 usa `openspec/kdd/state.json` (10 etapas, `tools/dsguard/kdd.py`) como lifecycle
principal del proyecto. La arquitectura v0.3 aprobada por el usuario (roadmap discutido en la
sesión: Methodology Core / Project Maturity / Progressive Scaffold) requiere que CRISP-DM pase a
ser la fuente de verdad metodológica canónica, con KDD como proceso técnico subordinado y MLOps
como capacidades progresivas — todo dentro de un único archivo nuevo (`openspec/lifecycle/state.json`)
para no crear máquinas de estado paralelas que puedan desincronizarse. Hoy ese archivo no existe
y no hay ninguna librería que lo lea, escriba o valide.

## Objetivo
Definir el schema v1 de `openspec/lifecycle/state.json` y la librería `tools/dsguard/lifecycle.py`
(catálogos CRISP-DM/KDD, mapeo entre ambos, estructura MLOps, init/lectura/validación/escritura
atómica) — sin migración desde v0.2, sin repuntar el CLI `kdd`, sin `project_stage`/`risk_level`,
sin readiness/promotion, sin scaffold progresivo. Solo la base estructural sobre la que se
construyen los Changes 2 en adelante del roadmap v0.3 aprobado.

## Evidencia
- `tools/dsguard/kdd.py:24-35` (catálogo `ETAPAS`, 10 nombres) — formato v0.2, a migrar recién en
  Change 2, no en este.
- `tools/dsguard/kdd.py:40` (`ETAPAS_FUTURAS`) y `:267-273` (bloqueo de transición) — precedente
  del estado `futura` de v0.2, reevaluado en este change (ver `design.md` § Decisión técnica).
- `tools/dsguard/core.py:88-93` (`escribir_texto_atomico`) y `:42-44` (`ahora_utc`) — utilidades
  ya existentes, reusadas sin modificar `core.py`.
- Roadmap v0.3 aprobado por el usuario en esta sesión (Change 1 = `lifecycle-core-schema`,
  primero de la serie).

## Supuestos descartados
No se migra desde `openspec/kdd/state.json` en este change (queda para Change 2,
`lifecycle-migration-and-kdd-repoint`). No se repunta `ds_guard kdd` (Change 2). No se agregan
`project_stage`/`risk_level` (Change 3). No hay checks/gates/enforcement de ningún tipo — eso son
los Changes 4 en adelante del roadmap (`checks-engine-foundation`, `mlops-foundations-experiment`,
`readiness-and-promotion`). No se toca `tools/dsguard/kdd.py`, `tools/ds_guard.py`, el decision
ledger, `tools/harmessi/doctor.py`, `ds_init`, la skill del Lead, `ds_profile`/EDA — todos quedan
exactamente como están hoy.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica — cambio de arquitectura/tooling del harness, no una hipótesis sobre datos de un
proyecto de ciencia de datos concreto.

## Alcance
1. Crear `openspec/lifecycle/state.json` (schema v1) con tres bloques anidados (`crispdm`, `kdd`,
   `mlops`) + `historial_transiciones` + metadata (`schema_version`, `creado_utc`, `migrado_desde`).
2. Crear `tools/dsguard/lifecycle.py`: catálogos (`FASES_CRISPDM`, `PASOS_KDD`,
   `MAPEO_CRISPDM_A_KDD`, `MAPEO_KDD_A_CRISPDM`, `MLOPS_TIERS`, `MLOPS_CAPACIDADES`,
   `ESTADOS_VALIDOS`), excepción `LifecycleEstadoError`, funciones `estado_inicial`, `state_path`,
   `leer_estado`, `validar_estructura`, `escribir_estado`, `lifecycle_init`.
3. Tests exhaustivos (14 casos, ver `tasks.md`).

## Fuera de alcance
Migración v0.2→v0.3, repunte de `kdd` CLI, `project_stage`/`risk_level`, readiness/promotion,
scaffold progresivo, cualquier integración con `ds_guard`, `doctor`, Lead, decision ledger,
`ds_profile`.

## Holdout policy (condicional — solo cambios "sensible")
No aplica — este change no toca datos, holdouts ni datasets sellados.

## Impacto en production-readiness (opcional)
Ninguno directo: este change no activa ni gatea nada — sienta la estructura de datos sobre la
que Changes futuros del roadmap (5, 6) construirán checks reales de production-readiness.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md` — SDD completo.

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md` — SDD completo.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-14
- Alcance aprobado: Schema v1 de openspec/lifecycle/state.json + tools/dsguard/lifecycle.py, según proposal.md/spec.md/design.md con los 2 ajustes incorporados (retiro de `futura` + no persistir `fase_actual`/`paso_actual`)
- Versión de artefactos referenciada: hash sha256/lf/v1 8961b30f911701a4cb7ed419a3267b8625b7636e7a2fcd53433ef8896293eada (proposal.md), 15eb04129f59a88cd4cbebb8f4b7daf67b8710992700f62177e7ec73598d2df6 (spec.md), 6df0a5b5df51bcda365a6fca3b4ece445df947afa42e914a4f40f06c2a9f151b (design.md), 7c5fe988bf6811bc4dd22be6c91650dda16afa009ab960b30568c96af8942375 (tasks.md) — registrados en control.json a las 2026-09-14T14:23:2xZ
- Cita o descripción fiel de qué se aprobó: "Aprobado con dos ajustes menores antes de implementar. [...] El resto del diseño queda aprobado [...] Incorporá estos dos ajustes a los artefactos SDD, aprobá el diseño según el flujo vigente e implementá únicamente Change 1."

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
