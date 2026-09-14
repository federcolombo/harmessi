# Diseño — 20260915-project-maturity-state-and-calibration

## Decisión metodológica/técnica

1. **`tools/dsguard/maturity.py`** (nombre confirmado, sin alternativa propuesta): mismo patrón arquitectónico que `lifecycle.py`/`kdd_compat.py` (catálogos + excepción + `state_path`/`leer_estado`/`validar_estructura`/`escribir_estado`/`<x>_init` idempotente). Sin dependencia hacia `kdd.py`/`kdd_compat.py`/`lifecycle.py` salvo una excepción puntual: `inferir_stage` importa `lifecycle.state_path`/`kdd_compat.state_path_legacy` ÚNICAMENTE para construir las dos rutas a chequear existencia (nunca lee su contenido, nunca los importa para lógica) — evita hardcodear el mismo string de ruta en dos lugares sin crear acoplamiento de lógica real. Dependencia unidireccional preservada: `maturity.py` consulta, nunca es consultado ni mutado por los otros módulos.

2. **`risk_status` NO se persiste como campo separado** (responde a la pregunta B del usuario). Se deriva puro: `estado_riesgo(project_data) = "classified" if project_data["risk_level"] is not None else "unclassified"`. Justificación — precedente directo YA sentado en este mismo repo: Change 1 (`openspec/changes/20260914-lifecycle-core-schema/design.md` punto 5) rechazó persistir `fase_actual`/`paso_actual` en `lifecycle.py` exactamente por este motivo — son valores 100% derivables de otro campo del mismo archivo, y persistirlos introduce una segunda fuente de verdad con riesgo real de divergencia (alguien podría, por bug o edición manual, dejar `risk_level: "low", risk_status: "unclassified"` — un estado contradictorio que solo puede existir si hay dos campos). Con un solo campo (`risk_level`), esa contradicción es estructuralmente imposible, no solo evitada por validación. Se considera la alternativa "persistir ambos + validar el invariante en `validar_estructura`" (mencionada como posible ventaja: auto-documentación sin conocer la convención `null`, y detección de corrupción) pero se descarta: el mismo precedente de Change 1 ya estableció que "evitar la segunda fuente" pesa más que "auto-documentación", y la función pura `estado_riesgo()` da la misma legibilidad en cualquier punto de consumo (CLI `status`, futuros checks) sin el riesgo.

3. **`project init` separa explícitamente proyecto nuevo de adopción** (ajuste del usuario tras la revisión, L2 — reemplaza la lectura de "inferencia uniforme" de la versión anterior de este documento). Dos intenciones distintas, dos flags:
   - `project init` (sin flags) o `project init --stage {discovery,experiment}` → **proyecto nuevo**: `project_stage` = el valor de `--stage`, o `"experiment"` si se omite (default acordado para proyectos nuevos). `via: "explicit_init"` siempre.
   - `project init --adopt` → **adopción/migración de un proyecto existente**: infiere `project_stage` chequeando existencia de `openspec/lifecycle/state.json` u `openspec/kdd/state.json` (legacy) — `experiment` si alguno existe, `discovery` si ninguno existe. `via: "migration_inference"`, con `reason` que explique qué se detectó (o la ausencia).
   - `--adopt` y `--stage` son mutuamente excluyentes — pasar ambos es un error de uso (CLI y función rechazan explícitamente, mensaje claro).

   Justificación (razonamiento del usuario, no mío): la ausencia de lifecycle/legacy no permite distinguir automáticamente entre un proyecto genuinamente nuevo (cuyo default correcto es `experiment`) y un proyecto existente todavía no gestionado por Harmessi (que puede razonablemente inferirse `discovery`) — usar la misma heurística para ambos casos, como proponía la versión anterior de este documento, sería una heurística silenciosa que oculta una decisión que en realidad requiere intención explícita del invocador. El backend determinista (`ds_guard project init`) debe exigir esa intención sin ambigüedad; un futuro `harmessi init` puede esconder esta complejidad detrás de una UX simple (preguntando "¿es nuevo o estás adoptando uno existente?"), pero no antes de que exista esa capa.

4. **`project init --stage` solo acepta `discovery`/`experiment`** (responde a la pregunta explícita de la sección 4 del brief: "Analizá si project init debería permitir esos stages directamente o si deberían pasar exclusivamente por calibrate"). Recomendación: exclusivamente por `calibrate`, incluso para la primerísima asignación de stage de un proyecto. Justificación: `calibrate` ya tiene, por diseño, exactamente las propiedades que el brief pide para cualquier declaración de `production_candidate`/`production` sin gates reales — `reason` obligatorio, `via: "calibrate"` distinguible, documentado explícitamente como "no es promoción validada". Si `project init` también aceptara esos dos stages, habría DOS caminos para llegar al mismo lugar con semántica ligeramente distinta (uno con reason opcional, otro obligatorio) — invitando a inconsistencia. Un solo camino, una sola semántica.

5. **`calibrate` exige que `.harmessi/project.json` ya exista** — no bootstrapea implícitamente. Si no existe, error claro pidiendo `project init` primero. Mantiene `init` (crear) y `calibrate` (declarar/corregir el punto de partida real) como verbos de responsabilidad única, mismo criterio que ya separa `lifecycle_init` de una futura transición, o `kdd_init` de `kdd_transition`.

6. **Prevención de bypass futuro de `calibrate` (sección 7 del brief): derivada de `stage_history`, sin campo nuevo** — `calibrar()` revisa `any(entry.get("via") == "promote" for entry in stage_history)` antes de escribir; si hay alguna, rechaza con mensaje claro. Sigue la preferencia explícita del usuario ("derivar de history antes que duplicar estado") y es real, no solo documentado: aunque `promote` no existe todavía en este change, el chequeo ya está activo y listo para cuando un change futuro empiece a escribir `via: "promote"`. Alternativa descartada: campo `calibration_locked: bool` — se rechaza por ser exactamente el tipo de segunda fuente de verdad que el punto 2 de esta lista ya evita en otro contexto (el dato ya existe en `stage_history`, duplicarlo en un booleano separado arriesga que ambos diverjan).

7. **`set_risk` siempre exige `--reason`**, incluso para la primera clasificación (responde a la sección 8 del brief, que invitaba a proponer una regla mejor que "solo después de la primera"). Justificación: una sola regla sin casos especiales, consistente con que `calibrate` también exige `reason` siempre; el costo de pedirlo desde la primera vez es mínimo (un flag de CLI) y da trazabilidad completa desde el día uno, sin necesitar que el código distinga "es la primera vez o no" (lo cual además requeriría leer el estado antes de decidir si el argumento es obligatorio — complejidad evitable).

8. **CLI: solo `ds_guard project init/calibrate/set-risk/status` en este change** (responde a la sección 11 del brief). `tools/harmessi/cli.py` (ya existente, wrapper delgado sobre `doctor.py` — mismo patrón que se seguiría acá) NO se toca en este change — pero `maturity.py` se diseña para que agregar un futuro subcomando `harmessi project ...` sea trivial: sus funciones públicas toman `repo_root`/parámetros primitivos y devuelven dicts planos, sin ningún acoplamiento a `argparse.Namespace` — exactamente el mismo contrato que ya usan `lifecycle.py`/`kdd_compat.py`, consumidos hoy por `ds_guard.py` y mañana, sin cambios, por `tools/harmessi/cli.py`. No se construye esa segunda superficie ahora porque no fue pedida y sería alcance no demostrado.

9. **Downgrade (sección 14 del brief)**: no se implementa `set-stage` genérico. El comportamiento resultante del diseño ya es, por construcción, exactamente lo que pide el brief: mientras no exista ningún `via: "promote"` en el historial, `calibrate` puede corregir el stage en cualquier dirección (incluso hacia abajo) porque todavía es "fase de adopción/configuración", no una operación productiva real. Una vez que exista un `via: "promote"`, NINGÚN comando de este change puede cambiar `project_stage` en ninguna dirección — el downgrade de un proyecto realmente promovido queda, de hecho, imposible hasta que un change futuro diseñe un mecanismo administrativo explícito. No se necesita lógica adicional para lograr esto — es consecuencia directa del punto 6.

## Target (condicional — feature_engineering, modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Alternativas descartadas
- Persistir `risk_status` como campo independiente — rechazada, ver punto 2 (precedente directo de Change 1).
- Usar la misma heurística de inferencia para "proyecto nuevo" y "proyecto adoptado" sin distinguir la intención — rechazada: es una heurística silenciosa que esconde una decisión que requiere intención explícita (ver punto 3).
- Permitir `project init --stage production_candidate/production` directamente — rechazada, ver punto 4: duplicaría el camino que ya cubre `calibrate` con mejor semántica.
- `calibrate` bootstrapeando `project.json` implícitamente si no existe — rechazada, ver punto 5: mezcla dos responsabilidades que conviene mantener separadas.
- Campo `calibration_locked: bool` para prevenir bypass de `calibrate` — rechazada, ver punto 6: segunda fuente de verdad evitable, `stage_history` ya tiene la información.
- `reason` opcional en la primera clasificación de `set_risk` — rechazada, ver punto 7: una sola regla sin casos especiales.
- Implementar `harmessi project ...` en este change — rechazada, ver punto 8: alcance no pedido, se prepara el terreno sin construirlo.

## Riesgos
- El punto 3 fue ajustado explícitamente por el usuario tras la primera revisión de este documento (L2: separación de `init` sin flags/`--stage` — proyecto nuevo, default `"experiment"` — de `init --adopt` — inferencia, `"migration_inference"`) — no es una interpretación propia pendiente de confirmar, ya está incorporado al diseño.
- Si un change futuro de `promote` decide usar un valor de `via` distinto de `"promote"` literal, el chequeo de bypass de `calibrate` (punto 6) dejaría de detectarlo — mitigado documentando acá que `"promote"` es el valor reservado y exacto que ese chequeo espera; cualquier change futuro que implemente `promote` debe usar ese literal.
- `.harmessi/profiles/` (ds_profile, v0.2) y `.harmessi/project.json` (este change) comparten el mismo directorio raíz `.harmessi/` — ambos ya excluidos de instalación por ser estado generado, sin conflicto de nombres entre ambos subsistemas (verificado: `profiles/` vs `project.json`, rutas distintas dentro del mismo directorio).

## Aprobación humana
Ver `proposal.md § Aprobación`.
