# Diseño — 20260915-mlops-foundations-experiment

## Decisión metodológica/técnica

1. **Ubicación: `tools/dsguard/mlops_foundations.py`** (nombre acotado al alcance real de este
   change — solo el tier `foundations`, no `production_readiness`/`operations`, que son changes
   futuros con posiblemente otra forma; evita comprometerse a que un solo módulo `mlops.py` deba
   crecer para albergar los 3 tiers, decisión que no corresponde tomar ahora). Consume
   `checks.py`/`lifecycle.py`/`maturity.py`/`repo.py` sin modificarlos.

2. **Dos vocabularios distintos, sin fusionar**: el `estado` persistido en
   `mlops.foundations.<capability>` (`no_iniciada/en_progreso/cerrada`, workflow de trabajo) y el
   `status` de un `CheckResult` (`PASS/WARN/FAIL/N-A`, medición puntual) son ejes diferentes —
   igual que ya lo son `Finding` y `CheckResult` (Change 4). Este change NO mapea uno al otro ni
   muta `estado` nunca: no existe todavía ningún mecanismo (ni en este change ni en ninguno
   anterior) que decida cuándo una capability MLOps pasa a `en_progreso`/`cerrada` — eso es una
   decisión de workflow reservada para un change futuro (posiblemente ligado a `promote`).
   Persistir evidencia (`registrar_evidencia`) es puramente informativo/histórico, un snapshot de
   medición, no un cambio de estado de trabajo.

3. **`lineage` nunca da `PASS` en este change (siempre `WARN` cuando está activo)** — decisión
   deliberada, no un bug. El brief es explícito: "no construir ahora un lineage engine completo...
   si la evidencia disponible todavía es insuficiente: usar WARN/N-A según corresponda, no
   inventar PASS". Hoy la única evidencia indirecta disponible es el vínculo SDD↔KDD
   (`changes[]`/`evidencia[]` por paso, ya existente desde Change 2) — no es un lineage real
   datos→features→modelo, así que emitir `PASS` sería falsear la medición. `WARN` permanente
   hasta que exista un mecanismo real es la lectura honesta.

4. **Resolución de `project_stage` sigue el patrón "con-dato" de
   `doctor._ejecutar_check_con_dato`** (Change 4): se resuelve una vez, con su propio
   `CheckResult` informativo (`MLOPS-FOUNDATIONS-PROJECT-STAGE`), y el valor resuelto (`str` o
   `None`) se pasa como argumento a los 4 checks de capability — ninguno de ellos vuelve a leer
   `project.json` por su cuenta. `.harmessi/project.json` ausente es un estado LEGÍTIMO (no un
   error): produce `N/A` explícito con mensaje que apunta a `project init`, nunca un
   `technical_error`. `project.json` corrupto SÍ es un `technical_error` (falla real de
   integridad de datos, se deja propagar y el wrapper lo convierte).

5. **`registrar_evidencia` es una operación separada y explícita, nunca llamada implícitamente
   por `status`/`evaluar_foundations`.** Principio fuerte del usuario: "status/check →
   read-only". La forma del snapshot (`{tipo: "check_snapshot", status, kind, message, utc}`) es
   deliberadamente distinta de la forma `{change_id, artefacto}` que ya usa `evidencia[]` para
   vínculos con SDD (Change 2) — un resultado de check no está atado a ningún `change_id`,
   forzarlo a esa forma sería inventar un vínculo que no existe. Ambas formas conviven en la
   misma lista `evidencia[]` sin conflicto (son dicts con claves distintas, cualquier consumidor
   futuro puede distinguirlas por la presencia de `tipo` vs `change_id`).

6. **Reproducibilidad exige evidencia real, nunca "usa Git" solo** — working tree limpio (no
   alcanza con que el HEAD exista, si hay cambios sin confirmar el commit no representa el estado
   real), fingerprint de datos SOLO si hay `data/` con contenido (no se exige si no aplica),
   lockfile de entorno. Ninguna de estas señales es "ML supervisado only" — aplican a cualquier
   tipo de proyecto (analítico, no supervisado, etc.), y cada una se omite limpiamente si no
   corresponde (ej. sin `data/`, no se exige fingerprint).

7. **CLI: nuevo grupo `mlops`** (`status`/`record`), no bajo `project` (madurez/gobernanza, eje
   distinto) ni bajo `lifecycle` (transiciones CRISP-DM/KDD, no capacidades MLOps) — mismo
   criterio de "un grupo por dominio real" ya usado para `kdd`/`lifecycle`/`project`/`decision`.

8. **`checks.py` no se modifica ni se acopla a `project_stage`** — `mlops_foundations.py` es
   quien conoce `project_stage` y decide N/A; el engine sigue sin saber nada de
   CRISP-DM/project_stage/risk_level/MLOps, tal como se diseñó en Change 4.

## Target (condicional — feature_engineering, modeling)
No aplica — no hay target de un dataset concreto en este change.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica — este change no toca datos de un proyecto real, define checks genéricos sobre
metadata de evidencia (commits, fingerprints, presencia de archivos), no sobre el contenido de
ningún dataset.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica — no hay aleatoriedad en el código de este change (del propio change, no confundir con
el check `check_reproducibilidad` que implementa, descripto en la sección anterior).

## Alternativas descartadas
- Mapear automáticamente `CheckResult.status` a `estado` de la capability (`PASS→cerrada`, etc.)
  — rechazada, ver punto 2: confundiría medición con decisión de workflow, y no hay mecanismo de
  transición diseñado para `mlops.*` todavía.
- Forzar `lineage` a dar `PASS` cuando hay "suficiente" evidencia indirecta — rechazada, ver
  punto 3: sería falsear la medición, el brief pide explícitamente no inventar PASS.
- Reusar la forma `{change_id, artefacto}` de `evidencia[]` para los snapshots de check —
  rechazada, ver punto 5: un check no está atado a un `change_id`, forzar esa forma sería
  inventar un vínculo falso.
- Exigir `PASS` de reproducibilidad con solo verificar que el repo es Git — rechazada
  explícitamente por el usuario, ver punto 6.
- Un solo módulo `tools/dsguard/mlops.py` que ya prevea los 3 tiers — rechazada, ver punto 1:
  alcance especulativo sobre changes futuros no diseñados todavía.
- Acoplar severidad de los checks a `risk_level` en este change — rechazada: el usuario pidió
  explícitamente mantenerlo ortogonal y no implementar Responsible AI/governance todavía.

## Riesgos
- `check_lineage` siempre `WARN` (nunca `PASS`) podría leerse como "un check roto" si no se
  documenta bien — mitigado dejándolo explícito acá y en el mensaje mismo del check ("no hay
  motor de lineage real todavía").
- La forma nueva de snapshot (`tipo: "check_snapshot"`) en `evidencia[]` introduce
  heterogeneidad de forma en esa lista (conviven `{change_id, artefacto}` y `{tipo, status, kind,
  message, utc}`) — aceptado conscientemente (punto 5) porque forzar una forma común sería peor
  (inventar un `change_id` falso). Un consumidor futuro de `evidencia[]` debe tolerar ambas
  formas.
- Los checks de `reproducibilidad`/`versionado`/`artifacts` dependen de convenciones (`data/`,
  `models/`, `reports/`, `.harmessi/profiles/`) que todavía no tienen scaffold obligatorio
  (Change 7) — mitigado tratando su AUSENCIA como señal neutral/negativa suave (N/A donde
  corresponde, WARN donde corresponde), nunca como error.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
Ver `proposal.md § Aprobación`.
