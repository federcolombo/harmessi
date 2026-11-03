# Diseño — 20261019-v011-parallel-change-isolation

## Decisión metodológica/técnica
- **D1** La atribución es solo clasificación de hallazgos: nunca amplía el alcance propio ni autoriza escritura.
- **D2** Se reutiliza `alcance_efectivo` para cada otro Change, de modo que la cadena de enmiendas gobierna igual para propios y ajenos.
- **D3** Un ajeno cuenta solo si es activo y aprobado, verificado sobre su SNAPSHOT en el commit baseline propio (`_aprobacion_ajena_verificada`; `tasks.md`, `control.json` y artefactos vía `git show`/`repo.leer_en_commit`, nunca disco). El baseline propio debe ser SHA hexadecimal completo (40/64; `HEAD`, ramas o prefijos cortos => nadie cuenta). En el snapshot: estado en `{aprobada_implementacion, en_implementacion, en_verificacion}`, `alcance.scope_hash` presente y aprobación más reciente de CADA artefacto de `sdd.artefactos_requeridos(modo)` (modo inválido => completo) con hash `hash_lf_v1` igual al del contenido en el baseline. En disco, el `scope_hash` debe ser igual al del baseline (ancla inmutable; si difiere => `ALCANCE-OTRO-CHANGE-INVALIDO`), y el alcance efectivo se calcula desde disco con `alcance_efectivo` (respeta enmiendas legítimas posteriores). Todo lo demás (sin aprobar, pausado, cerrado, estado/tasks ilegible, sin `scope_hash`, creado o aprobado tras el baseline, baseline ausente/no SHA completo/ref inválida, aprobación incompleta o no verificada) NO cuenta: fail-closed = atribuir menos, sin hallazgo extra. Patrones ajenos inválidos (`scope_amendments.motivo_ruta_invalida`), catch-all o bajo `.claude/` se descartan. No se agrega campo a `control.json`. Limitación: un ajeno aprobado después del baseline propio no atribuye. La atribución es «honesta, no autenticada» (ver Riesgos).
- **D4** `ALCANCE-ATRIBUIDA-OTRO-CHANGE` es informativo para no bloquear trabajo paralelo legítimo; el conflicto (doble dueño) y la cadena ajena inválida bloquean.
- **D5** 4A no se implementa: sin payload real el hook no cambia.

## Target (condicional — feature_engineering, modeling)

## Features permitidas/prohibidas (condicional — feature_engineering)

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
<!-- riesgos considerados por quien propone, incluida la clase "foto sin fecha" de CLAUDE.md;
complementa, no reemplaza, la revisión independiente de data-science-reviewer -->

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)

## Alternativas descartadas
Ignorar rutas de otros Changes (debilita el gate); unir alcances de todos los Changes abiertos (oculta conflictos); locks/worktrees (fuera de boundaries).

## Riesgos
Debilitar el scope → mitigado por R3/R4. Atribución «honesta, no autenticada»: la aprobación en `control.json` es editable por quien tiene el repo (forjar un ajeno cuesta un commit previo al baseline propio, con tasks activo, todos los artefactos requeridos aprobados con hash coherente y `scope_hash` coherente; el estado y la aprobación se leen del snapshot del baseline, así que forjar en el working tree o después del baseline no sirve); SHA completo + snapshot + ancla `scope_hash` inmutable + conflicto bloqueante + descarte de catch-all/rutas protegidas elevan el costo de la evasión pero no la hacen imposible. Limitación asumida: un ajeno legítimo aprobado después del baseline propio no atribuye (fail-closed; sus rutas quedan como `ALCANCE-RUTA`). Mitigación de fondo: la atribución es solo clasificación informativa y nunca afloja el alcance propio (D1); lo que no se atribuye sigue siendo `ALCANCE-RUTA`. Costo O(Changes abiertos) por validate: lectura de JSON local, aceptable.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
