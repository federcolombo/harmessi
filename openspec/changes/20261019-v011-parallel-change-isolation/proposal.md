# Propuesta — 20261019-v011-parallel-change-isolation

## Problema
Change 4 de v0.11 (roadmap congelado, 4B). `scope.evaluar_alcance` compara las rutas tocadas (working tree + diff desde baseline) solo contra el alcance del Change evaluado. Con dos Changes abiertos en paralelo, la modificación legítima de uno aparece como `ALCANCE-RUTA` en el otro (falso positivo), lo que empuja a enmendar alcances que no corresponden o a ignorar el hallazgo (debilita el gate). A la vez, una ruta que cae en el alcance de dos Changes abiertos es un conflicto real que hoy pasa sin señal.

## Objetivo
Atribuir las rutas fuera de alcance al Change abierto que las posee, y reportar como hallazgo las rutas sin dueño o con dos dueños, sin debilitar nunca el scope.

## Evidencia
- `tools/dsguard/scope.py:107-164` (`evaluar_alcance`: único alcance, sin noción de otros Changes).
- `tools/dsguard/scope.py:68-89` (`alcance_efectivo`: lectura única del alcance con cadena de enmiendas; fail-closed si la cadena es inválida).
- `docs/roadmap/v0.11.md` Change 4.

## Supuestos descartados
4A (atribución por runtime en hook): no hay evidencia de payload real de hook capturada en este release; H1 permanece UNCONFIRMED y el hook NO se toca. Se documenta la decisión en `verification.md`.

## Hipótesis (condicional — solo cambios metodológicos)
<!-- qué se espera confirmar/descartar, si el cambio prueba una hipótesis concreta -->

## Alcance
4B: en `evaluar_alcance`, cada ruta fuera del alcance propio se clasifica contra el alcance efectivo de los demás Changes abiertos (`openspec/changes/*` con `tasks.md` en estado distinto de `cerrada`/`descartada`): sin dueño → `ALCANCE-RUTA` (igual que hoy); un solo otro dueño → hallazgo informativo `ALCANCE-ATRIBUIDA-OTRO-CHANGE` (no bloquea); además, una ruta dentro del alcance propio Y de otro Change abierto → `ALCANCE-CONFLICTO-CHANGES` (bloquea). Cadena de enmiendas inválida o `control.json` ilegible de otro Change: no autoriza nada (la ruta queda como `ALCANCE-RUTA`) y se reporta `ALCANCE-OTRO-CHANGE-INVALIDO`. Tests y docs.

## Fuera de alcance
4A / cambios de hook, scheduler, worktree manager, locks, ownership por instancia en hook, cambios al formato de `control.json`.

## Holdout policy (condicional — solo cambios "sensible")
<!-- si el cambio toca o podría tocar un holdout/dataset sellado: acceso solicitado, por qué, qué
decisión depende de eso, y la autorización del usuario transcripta literal (ver SKILL.md,
categoría "Sensible") -->

## Impacto en production-readiness (opcional)
<!-- nota libre; pasa a condicional cuando esa etapa KDD se active en un bloque futuro -->

## Criterios de aceptación (spec-lite — solo SDD abreviado)
<!-- en SDD completo, ver spec.md en su lugar -->

## Decisión técnica (design-lite — solo SDD abreviado)
<!-- en SDD completo, ver design.md en su lugar -->

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado
- tools/dsguard/scope.py
- tools/ds_guard.py
- tools/dsguard/sdd.py
- .claude/skills/lead-data-scientist/verificador.md
- .claude/skills/lead-data-scientist/methodology.md
- tools/ds_init/profiles/**
- tools/tests/**
- docs/roadmap/v0.11.md
- openspec/changes/20261019-v011-parallel-change-isolation/**
<!-- opcional: rutas que este Change puede tocar, una por línea como `- ruta` o `- dir/**`
(repo-relativas, sin `..`, sin rutas absolutas ni comodines repo-wide). Al aprobar proposal.md,
ds_guard las materializa en control.json junto con los artefactos por defecto del Change;
queda ligado al hash de la propuesta aprobada. Sin bullets, el alcance no se modifica. -->

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
