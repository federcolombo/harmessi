# Spec — 20260914-lifecycle-migration-and-kdd-repoint

## Requisitos
Ver `proposal.md` § Alcance y `design.md` para el detalle de implementación. Tabla de mapeo legacy completa (tal como la aprobó el usuario):

| Legacy (10) | CRISP-DM | KDD | MLOps tier |
|---|---|---|---|
| `problem_understanding` | `business_understanding` | — | — |
| `data_understanding` | `data_understanding` | `selection` | — |
| `data_preparation` | `data_preparation` | `preprocessing` | — |
| `feature_engineering` | `data_preparation` | `transformation` | — |
| `modeling` | `modeling` | `data_mining` | — |
| `evaluation` | `evaluation` | `interpretation_evaluation` | — |
| `interpretation` | `evaluation` | `interpretation_evaluation` | — |
| `production_readiness` | `production_readiness` | — | `production_readiness` (solo referencia conceptual, ver design.md — NO se auto-asigna a ninguna capacidad específica) |
| `deployment` | `deployment` | — | `operations` (solo referencia conceptual, no auto-asignada) |
| `monitoring` | `monitoring` | — | `operations` (solo referencia conceptual, no auto-asignada) |

**Fases con roll-up** (tienen paso(s) KDD subordinados — su `estado` se deriva SIEMPRE de sus pasos, nunca se escribe directo): `data_understanding` (1 paso: `selection`), `data_preparation` (2 pasos: `preprocessing`, `transformation`), `modeling` (1 paso: `data_mining`), `evaluation` (1 paso: `interpretation_evaluation`). **Fases sin roll-up** (sin pasos KDD, `estado` se escribe directo desde la etapa legacy 1:1): `business_understanding`, `production_readiness`, `deployment`, `monitoring`.

## Criterios de aceptación
- Migración completa (sin legacy previo migrado, todas las 10 etapas con datos reales): `ds_guard lifecycle migrate` crea `openspec/lifecycle/state.json` con las 8 fases/5 pasos poblados según la tabla, `migrado_desde` con `formato: "kdd_v1"`, `schema_version_origen: 1`, `utc` de la migración, y un registro por cada una de las 10 etapas legacy (`etapas_legacy`) con `estado_legacy` y su mapeo — nunca borra ni modifica `openspec/kdd/state.json`.
- `evaluation`+`interpretation` convergen en `crispdm.fases.evaluation` y `kdd.pasos.interpretation_evaluation`: `estado` resultante = el más avanzado de los dos (`cerrada` > `en_progreso` > `no_iniciada`); `changes`/`evidencia` = unión deduplicada (por `change_id` y por `(change_id, artefacto)` respectivamente); `actualizado_utc` = el más reciente (max) de los dos orígenes.
- `data_preparation`+`feature_engineering`: ambas escriben evidencia/changes en `crispdm.fases.data_preparation` (unión, mismas reglas que arriba), pero cada una en su propio paso KDD (`preprocessing`/`transformation` respectivamente, sin merge entre pasos KDD distintos).
- Etapa legacy en `estado: "futura"` (`production_readiness`/`deployment`/`monitoring`): migra a `estado: "no_iniciada"` en `crispdm.fases`, y `migrado_desde.etapas_legacy.<nombre>.estado_legacy == "futura"` preserva el valor original — verificable incluso si el proyecto nunca tuvo evidencia real en esas etapas.
- Etapa legacy `futura` que SÍ tiene `changes`/`evidencia` acumulada (posible en v0.2: `sync_al_cerrar` no chequea `estado`, solo `kdd_transition` bloquea): esa evidencia/changes migra íntegra al `crispdm.fases.<nombre>` correspondiente — nunca se descarta por haber estado en `futura`. Ningún capability de `mlops` se auto-puebla.
- Migración a mitad de lifecycle (mezcla de `no_iniciada`/`en_progreso`/`cerrada` entre las 10 etapas): cada destino recibe exactamente el estado que le corresponde según las reglas de merge; ninguna etapa sin actividad legacy queda con datos inventados.
- Roll-up de fase CRISP-DM con pasos subordinados: `calcular_estado_fase(estados_pasos)` es una función PURA en `lifecycle.py` (nueva, sin conocimiento legacy) que implementa exactamente: todos `no_iniciada` → `no_iniciada`; todos `cerrada` → `cerrada`; cualquier combinación intermedia (algún `en_progreso`, o mezcla de `cerrada`/`no_iniciada`) → `en_progreso`. El resultado no depende del orden de los estados de entrada.
- El roll-up gobierna el `estado` de la fase TANTO en migración (la fase recibe `calcular_estado_fase()` sobre los estados ya migrados de sus pasos subordinados, nunca un cálculo independiente sobre las etapas legacy) COMO en transición en vivo (`kdd transition` sobre una etapa legacy con paso KDD asociado recalcula la fase vía roll-up después de escribir el paso).
- Ejemplo concreto (`data_preparation`, pasos `preprocessing`+`transformation`): `preprocessing=cerrada` + `transformation=no_iniciada` → fase `en_progreso`. `preprocessing=cerrada` + `transformation=en_progreso` → fase `en_progreso`. Ambas `cerrada` → fase `cerrada`. Ambas `no_iniciada` → fase `no_iniciada`. Transicionar primero `feature_engineering` y después `data_preparation` (o al revés) produce el mismo estado final de fase.
- Convergencia al mismo target (`evaluation`+`interpretation` → mismo paso `interpretation_evaluation`): sigue la regla de merge de "más avanzado" (`cerrada`>`en_progreso`>`no_iniciada`) — es una regla DISTINTA del roll-up, y se aplica solo en migración (post-migración son sinónimos sobre una única entrada, no hay nada que volver a mezclar en vivo).
- `sync_al_cerrar` repuntado, para una etapa legacy con paso KDD asociado, agrega evidencia/changes tanto al paso como a la fase (ambos niveles se mantienen vivos y consistentes, no solo el paso) — usando el mismo dedup idempotente ya existente (`if change_id not in changes`, `if not any evidencia match`) en cada nivel.
- `kdd_compat.py` define su propia excepción `KddCompatError` (no importa `kdd.KddEstadoError` — evitaría el ciclo) para fallas de lectura del legacy o precondiciones de migración; `kdd.py` envuelve tanto `KddCompatError` como `lifecycle.LifecycleEstadoError` como `KddEstadoError` en el borde público.
- `ds_guard lifecycle migrate` (comando nuevo) captura `KddCompatError`/`LifecycleEstadoError` directamente (sin pasar por `kdd.py`) y produce mensajes claros y accionables — no reutiliza silenciosamente el wrapping de `kdd.py`.
- `.claude/skills/lead-data-scientist/kdd.md` y `tools/ds_init/profiles/python_jupyter_data/templates/kdd.md.tmpl` quedan sincronizados entre sí y afirman correctamente: lifecycle/state.json es el estado canónico, los 10 nombres son superficie de compatibilidad, kdd opera vía adapter, legacy queda read-only tras migrar.
- `tools/dsguard/lifecycle.py` y `tools/dsguard/kdd_compat.py` ambos con entrada VERBATIM en MANIFEST; instalación scratch deja ambos presentes en el destino.
- `historial_transiciones` legacy se traduce y preserva íntegro: cada entrada legacy (`{utc, etapa, desde, hacia, motivo?}`) aparece en el `historial_transiciones` nuevo con su `etapa` legacy original conservada además de su traducción a fase/paso nuevo.
- JSON legacy corrupto (`openspec/kdd/state.json` no parseable) → `migrate` falla con el mismo tipo de error que ya usa `kdd.leer_estado` (`KddEstadoError`), no escribe `lifecycle/state.json`, no borra nada.
- `schema_version` legacy desconocida → mismo comportamiento fail-closed.
- `openspec/lifecycle/state.json` ya existe y es válido → `migrate` es no-op (no lo reescribe, sin importar si el legacy cambió desde entonces) — idempotencia.
- `openspec/lifecycle/state.json` existe pero es inválido/corrupto (y hay legacy también) → `migrate` falla cerrado, **nunca** cae de vuelta a leer/escribir el legacy.
- Sin legacy y sin lifecycle → `migrate` reporta "nada que migrar" sin crear ningún archivo (esa es tarea de `lifecycle init`, no de `migrate`).
- No hay ningún flujo (comando normal, sin flags especiales) que escriba `openspec/kdd/state.json` después de que exista `openspec/lifecycle/state.json` — verificable con un test que corre `kdd status`/`kdd transition` repuntados y confirma que el legacy no cambió de bytes.
- `ds_guard kdd status/transition` sobre un proyecto CON legacy pero SIN `lifecycle/state.json` (no migrado todavía) → error claro indicando correr `ds_guard lifecycle migrate` primero, exit code de uso/config (2) — nunca auto-migra, nunca opera sobre el legacy.
- `ds_guard kdd init` sobre proyecto nuevo (sin legacy, sin lifecycle) → equivalente a `lifecycle init` (crea `openspec/lifecycle/state.json` directamente, nunca crea `openspec/kdd/state.json`).
- `ds_guard kdd status/transition` sobre proyecto YA migrado (`lifecycle/state.json` existe) → opera exclusivamente sobre él, traduciendo el nombre legacy de `--etapa`/`--kdd-etapa` recibido.
- `kdd transition --etapa evaluation ...` y `kdd transition --etapa interpretation ...` son funcionalmente sinónimos post-migración (mismo destino subyacente) — comportamiento esperado y documentado, no un bug.
- `decision add/supersede --kdd-etapa <legacy>` sigue funcionando sin cambios de schema del ledger — `dsguard/decision.py` no requiere modificaciones (sigue validando contra `kdd.ETAPAS`, sin cambios).
- `control["kdd"]["etapa_primaria"/"etapas_afectadas"]` (control.json de SDD) sigue aceptando los 10 nombres legacy sin cambios de schema; `validar_antes_de_cerrar`/`sync_al_cerrar` repuntados producen el mismo tipo de resultado (`list[Finding]` / `dict` con `sincronizado`/`etapas_actualizadas`) que hoy, operando sobre `lifecycle/state.json` internamente.
- `tools/dsguard/lifecycle.py` tiene entrada VERBATIM en `MANIFEST` (`tools/ds_init/manifest.py`) — test de paridad existente (`test_manifest_dsguard_parity.py`) pasa una vez que `ds_guard.py` importa `lifecycle` a nivel de módulo; test explícito adicional (no depende de qué importe `ds_guard.py`) confirma la entrada de `lifecycle.py` en el manifiesto.
- Instalación desde cero (`ds_init` sobre un repo temporal) deja `tools/dsguard/lifecycle.py` presente en el destino.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Baseline (condicional — modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Métrica primaria (condicional — modeling, evaluation)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Métricas secundarias (opcional)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.
