# Propuesta — 20260914-lifecycle-migration-and-kdd-repoint

## Problema
`openspec/kdd/state.json` (v0.2, 10 etapas, `tools/dsguard/kdd.py`) sigue siendo el storage vivo que usan `ds_guard kdd init/status/transition`, el pre-gate/sync de cierre SDD (`validar_antes_de_cerrar`/`sync_al_cerrar`, invocados desde `tools/ds_guard.py` en la transición a `cerrada`), y el decision ledger (`--kdd-etapa`, validado contra `kdd.ETAPAS`). `openspec/lifecycle/state.json` (Change 1, cerrado) define el schema canónico nuevo pero hoy nadie lo escribe ni lo lee salvo tests. Además, auditoría de este change encontró que `tools/dsguard/lifecycle.py` (agregado en Change 1) **no tiene entrada en `tools/ds_init/manifest.py`** — repite exactamente el bug de `decision.py` documentado en `openspec/changes/20260911-release-v0-2-0-blockers/` (módulo funcional en el repo, ausente del manifiesto, `ImportError` en cualquier proyecto instalado en cuanto algo lo importe).

## Objetivo
(1) Migrar proyectos v0.2 de `openspec/kdd/state.json` a `openspec/lifecycle/state.json` sin pérdida de evidencia/historial/provenance. (2) Repuntar `ds_guard kdd init/status/transition` + el pre-gate/sync de cierre SDD para que, una vez migrado, operen exclusivamente sobre `lifecycle/state.json`, manteniendo el vocabulario legacy de 10 nombres como capa de compatibilidad de INPUT (CLI/decision ledger/control.json), nunca como storage. (3) `openspec/kdd/state.json` queda congelado (histórico, nunca más escrito por ningún flujo normal). (4) Agregar `lifecycle.py` al manifiesto de `ds_init` (bug encontrado).

## Evidencia
- `tools/ds_guard.py:235-278` (`cmd_transition`) — llama `kdd.validar_antes_de_cerrar`/`kdd.sync_al_cerrar` alrededor de la transición SDD a `cerrada`.
- `tools/ds_guard.py:766-857` (`cmd_kdd_init/status/transition`) — wrappers directos de `kdd.kdd_init/kdd_status/kdd_transition`; usan `kdd.state_path(repo_root)` para chequear existencia y `kdd.ETAPAS` como `choices` del flag `--etapa` (línea 1083).
- `tools/ds_guard.py:1135` (`--kdd-etapa`, subcomando `decision add/supersede`) — `choices=list(kdd.ETAPAS)`.
- `tools/dsguard/decision.py:169,245` — `registrar()`/`supersede()` validan `kdd_etapa not in kdd.ETAPAS` de forma independiente (import directo de `kdd`, no solo vía CLI).
- `tools/dsguard/sdd.py` — **cero** referencias a `kdd`/etapas (confirmado por grep completo): SDD en sí no tiene acoplamiento, todo el enlace vive en `ds_guard.py`.
- `tools/dsguard/kdd.py:24-53` (`ETAPAS`, `ETAPAS_FUTURAS`) y `:145-218` (`_CRITERIOS_DETECTABLES`, keyed por 7 de los 10 nombres legacy) y `:221-243` (`kdd_status`) y `:348-383` (`sync_al_cerrar`).
- `tools/ds_init/manifest.py:193-254` — patrón `EntradaManifiesto` VERBATIM de cada módulo de `dsguard/`; `lifecycle.py` ausente (confirmado, grep directo).
- `tools/tests/test_manifest_dsguard_parity.py` — test existente que solo cubre módulos que `ds_guard.py` importa a nivel de módulo (hoy no incluye `lifecycle` porque `ds_guard.py` todavía no lo importa); dejará de tener este punto ciego en cuanto este change agregue el import real.
- Roadmap v0.3 aprobado por el usuario (Change 2 de la serie), decisiones ya aprobadas en Change 1 (`futura` retirado del schema nuevo, `fase_actual`/`paso_actual` no persistidos).

## Supuestos descartados
No se modifica el schema del decision ledger ni se reescriben decisiones históricas (capa de traducción vía `kdd.ETAPAS`/mapeo, sin tocar `dsguard/decision.py`). No se modifica `dsguard/sdd.py` (cero acoplamiento real). No se implementa `project_stage`/`risk_level`/`calibrate`/`promote`/readiness/checks engine/scaffold progresivo/Lead awareness/cutoff-baseline enforceable — todo eso son changes posteriores del roadmap. No se agrega un comando general `ds_guard lifecycle status/transition` de propósito amplio — solo `ds_guard lifecycle migrate`, más el repunte interno de los comandos `kdd` ya existentes.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica.

## Alcance
1. **Nuevo módulo `tools/dsguard/kdd_compat.py`**: capa de compatibilidad explícita que conoce AMBAS ontologías (legacy v0.2 y `lifecycle.py`). Owns: catálogo legacy (`ETAPAS`, `ETAPAS_FUTURAS`, movidos acá desde `kdd.py`), mapeo legacy→nuevo (`MAPEO_LEGACY_A_CRISPDM`/`MAPEO_LEGACY_A_KDD`/`MAPEO_LEGACY_A_MLOPS_TIER`), reglas de merge/convergencia, `migrar_desde_legacy(repo_root)`, y las implementaciones reales repuntadas de `kdd_init`/`kdd_status`/`kdd_transition`/`validar_antes_de_cerrar`/`sync_al_cerrar`. `lifecycle.py` NO se modifica para saber nada de legacy (permanece neutral) — gana únicamente una función pura nueva, `calcular_estado_fase()` (roll-up, ver `design.md`), que no requiere ningún conocimiento legacy. `tools/dsguard/kdd.py` se convierte en el adaptador público delgado: re-exporta `ETAPAS`/`ETAPAS_FUTURAS` desde `kdd_compat.py` (`kdd.ETAPAS` sigue funcionando igual para código externo), define `KddEstadoError` (excepción pública), y sus funciones `kdd_init/status/transition/validar_antes_de_cerrar/sync_al_cerrar` son wrappers delgados que llaman a `kdd_compat.py` y envuelven `lifecycle.LifecycleEstadoError`/`kdd_compat.KddCompatError` como `KddEstadoError` en el borde público (ver `design.md` para la justificación completa, incluida la resolución de un import circular real que este split introduce).
2. **Mapeo legacy**: constantes en `kdd_compat.py` (no en `kdd.py` — ver punto 1): `MAPEO_LEGACY_A_CRISPDM`, `MAPEO_LEGACY_A_KDD`, `MAPEO_LEGACY_A_MLOPS_TIER` (ver `design.md` para la tabla exacta y las reglas de merge/roll-up).
3. **Repunte del CLI `kdd`**: las implementaciones reales de `kdd_init`/`kdd_status`/`kdd_transition`/`validar_antes_de_cerrar`/`sync_al_cerrar` viven en `kdd_compat.py` y operan sobre `lifecycle/state.json`; `kdd.py` expone wrappers delgados con la misma firma pública de siempre. `ds_guard.py` no necesita reescribir su wiring de `cmd_kdd_*`/`cmd_transition`, salvo el chequeo de existencia de archivo (pasa a `lifecycle.state_path` donde corresponde) y el manejo de excepciones (ver `design.md`).
4. Los 5 casos de disponibilidad de archivos (proyecto nuevo / legacy sin migrar / ya migrado / lifecycle inválido / ninguno presente, sección 9 del brief del usuario) quedan resueltos dentro de las implementaciones repuntadas de `kdd_compat.py` (`kdd_init`/`kdd_status`/`kdd_transition`), sin necesitar una función pública separada.
5. **Manifest**: agregar `EntradaManifiesto` VERBATIM para `tools/dsguard/lifecycle.py` en `tools/ds_init/manifest.py` (mismo patrón que sus hermanos). Evaluar agregar `openspec/lifecycle/` a `EXCLUSIONES_PERMANENTES` por simetría con `openspec/kdd/` (defensa en profundidad, ds_init nunca debe scaffoldear estado de proyecto).
6. **Tests**: ver `tasks.md` — cobertura completa de migración, merge de etapas convergentes, `futura`→`no_iniciada` con provenance, los 5 casos de disponibilidad de archivos, repunte del CLI, compatibilidad de decision ledger/SDD, manifest/instalación.
7. Comando `ds_guard lifecycle migrate` produce errores controlados y claros por sí mismo (no depende de que `kdd.py` los envuelva) — importa `kdd_compat`/`lifecycle` directamente en `ds_guard.py`.
8. Actualización factual mínima de `.claude/skills/lead-data-scientist/kdd.md` y su plantilla instalable (`tools/ds_init/profiles/python_jupyter_data/templates/kdd.md.tmpl`, deben quedar sincronizados) indicando: CRISP-DM/`openspec/lifecycle/state.json` es ahora el estado canónico; los 10 nombres legacy siguen disponibles como superficie de compatibilidad v0.2; `ds_guard kdd` opera vía el adapter de compatibilidad; `openspec/kdd/state.json` queda legacy/read-only tras migrar; la experiencia completa del Lead (project_stage/risk_level/readiness) se amplía en un change posterior. Sin introducir esos conceptos todavía.
9. `openspec/lifecycle/` agregado a `EXCLUSIONES_PERMANENTES` en `tools/ds_init/manifest.py` (estado generado, no contenido estático).
10. `tools/dsguard/lifecycle.py` Y `tools/dsguard/kdd_compat.py` con entrada VERBATIM en `MANIFEST`; test de paridad manifest extendido para cubrir ambos explícitamente (no solo vía lo que `ds_guard.py` importe); scratch install real verificando presencia de ambos módulos en el destino.

## Fuera de alcance
`project_stage`, `risk_level`, `calibrate`, `promote`, readiness, checks engine, MLOps checks, scaffold progresivo, unified init, Lead methodology awareness, cutoff/baseline enforceable, multi-provider, reporting, dsimpact. Ningún comando `ds_guard lifecycle status/transition` de propósito general. No se reescribe `dsguard/decision.py` ni `dsguard/sdd.py`. Sí se hace una actualización FACTUAL MÍNIMA de `.claude/skills/lead-data-scientist/kdd.md`/template (ver `## Alcance` punto 8) para que no queden afirmando algo materialmente falso sobre el estado canónico — pero NO se hace el rewrite completo de "Lead methodology awareness" (project_stage/risk_level/readiness en el Lead), que sigue siendo un change posterior.

## Holdout policy (condicional — solo cambios "sensible")
No aplica.

## Impacto en production-readiness (opcional)
Ninguno directo — sienta la base de compatibilidad para que los changes de readiness/promotion (posteriores) puedan operar sobre un único storage canónico.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md`.

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md`.

## Aprobación
- Usuario: pendiente
- Fecha: pendiente
- Alcance aprobado: pendiente
- Versión de artefactos referenciada: pendiente
- Cita o descripción fiel de qué se aprobó: pendiente

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
