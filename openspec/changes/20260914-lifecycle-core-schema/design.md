# Diseño — 20260914-lifecycle-core-schema

## Decisión metodológica/técnica
1. Un solo archivo (`openspec/lifecycle/state.json`) con 3 bloques anidados (`crispdm`, `kdd`,
   `mlops`), en vez de 3 archivos separados — evita que se conviertan en 3 máquinas de estado
   independientes que puedan desincronizarse; es exactamente lo que pidió el roadmap v0.3
   aprobado ("no crear una segunda máquina de estado independiente", tanto para KDD como para
   MLOps).
2. El mapeo CRISP-DM↔KDD (`MAPEO_CRISPDM_A_KDD`/`MAPEO_KDD_A_CRISPDM`) son CONSTANTES DE CÓDIGO
   en `lifecycle.py`, no datos persistidos dentro de cada `state.json` de proyecto — es una regla
   metodológica fija de Harmessi, no un dato específico del proyecto; persistirla en cada archivo
   generaría redundancia y riesgo de drift entre proyectos si el mapeo cambia en el futuro.
3. Las tres categorías (fases CRISP-DM, pasos KDD, capacidades MLOps) comparten exactamente la
   misma forma de entrada (`{estado, changes, evidencia, actualizado_utc}`) y el mismo enum de
   estados — un solo validador/inicializador interno reusado las tres veces, en vez de tres
   formas distintas. Mantiene la promesa de "un solo lifecycle", no tres con convenciones
   propias.
4. `futura` NO se incluye en `ESTADOS_VALIDOS` de este nuevo schema (queda
   `no_iniciada | en_progreso | cerrada`) — es el único cambio de semántica real respecto de v0.2;
   se justifica en detalle en la subsección siguiente porque el usuario pidió evaluarlo
   explícitamente antes de decidir, no cambiarlo en silencio.
5. `fase_actual`/`paso_actual` NO se persisten en este schema v1 — ajuste pedido por el usuario tras
   la primera revisión del borrador: son valores derivables del estado de `crispdm.fases`/
   `kdd.pasos`, y persistirlos introduciría una segunda fuente de verdad dentro del mismo archivo
   con riesgo real de divergencia (ej. una fase marcada `cerrada` mientras `fase_actual` sigue
   apuntando a otra, por una escritura parcial o un caller que actualiza una sin la otra). Si en el
   futuro hace falta cachear un valor derivado (por motivos de performance o de consulta, no de
   corrección), se evaluará como una evolución versionada del schema (`schema_version` 2+), no
   agregándolo ahora sin necesidad real. Este change tampoco incluye funciones puras de
   derivación — no hay ningún consumidor todavía que las necesite, y definir qué significa "fase
   actual" bajo un proceso iterativo/no lineal como CRISP-DM es en sí una decisión de diseño que
   conviene tomar cuando exista un caso de uso real (candidato: un change futuro de superficie de
   estado unificada), no de forma especulativa acá.
6. `migrado_desde: null` se incluye desde ahora (siempre `null` en este change) para que Change 2
   no necesite un bump de schema solo para agregar el campo — la forma que va a tomar
   (`{"formato": "kdd_v1", "schema_version_origen": 1, "utc": "..."}`) queda documentada en el
   docstring del módulo, no implementada todavía.

**Sobre el estado `futura` — análisis y recomendación**

En v0.2, `futura` conflacionaba dos cosas distintas: (a) "esta etapa todavía no arrancó" (eso ya
es `no_iniciada`) y (b) "esta etapa no puede arrancar todavía porque una precondición externa —el
proyecto llegó a `production_candidate`— no se cumplió" (eso es una regla de GATING de madurez de
proyecto). La arquitectura v0.3 aprobada separa explícitamente `project_stage` (Change 3) de este
lifecycle schema (Change 1) precisamente para no mezclar "en qué fase metodológica estoy" con
"qué tan maduro es el proyecto". Si `futura` se mantiene acá, el gating de madurez quedaría
implementado en DOS lugares (el estado `futura` de este archivo, y la lógica de promoción de
`project_stage` en Changes futuros) — exactamente el tipo de duplicación que todo el rediseño de
v0.3 busca evitar. Recomendación: **retirar `futura`**; toda fase/paso/capacidad nace
`no_iniciada` desde el día uno, sin importar el `project_stage` del proyecto — la eventual
restricción de "no deberías estar trabajando en `deployment` si tu `project_stage` es
`discovery`" se implementa más adelante (Changes 5/6 del roadmap) como un check que lee AMBOS
archivos (`lifecycle/state.json` + `.harmessi/project.json`), no como un estado estructural acá.
Ningún check/gate se pierde por esto en v0.3 real — hoy tampoco hay ninguno (este change es "solo
schema"), así que no hay regresión de comportamiento, solo una simplificación del modelo de
datos.

**Nota para Change 2 (migración)**: al migrar desde `openspec/kdd/state.json` v0.2, toda etapa que
hoy está en `estado: "futura"` (`production_readiness`, `deployment`, `monitoring`) debe mapearse a
`estado: "no_iniciada"` en el nuevo schema — nunca se pierde silenciosamente que esa etapa nació
como `futura` en v0.2: ese origen debe quedar preservado en el bloque
`migrado_desde`/`historial_transiciones` de la migración (por ejemplo, una entrada de historial con
un motivo tipo `estado_legacy: futura`, o un campo equivalente dentro de `migrado_desde`), de forma
que la trazabilidad hacia atrás no se pierda aunque el estado estructural ya no distinga `futura`
de `no_iniciada`. Este change (Change 1) solo deja documentada esta regla — no la implementa; la
migración real es Change 2 (`lifecycle-migration-and-kdd-repoint`).

## Target (condicional — feature_engineering, modeling)
No aplica — no hay datos, target ni features involucrados en este change.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica — no hay datos, target ni features involucrados en este change.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica — no hay datos, target ni features involucrados en este change.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
<!-- riesgos considerados por quien propone, incluida la clase "foto sin fecha" de CLAUDE.md;
complementa, no reemplaza, la revisión independiente de data-science-reviewer -->
No aplica — no hay datos, target ni features involucrados en este change.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica — no hay aleatoriedad en este change.

## Alternativas descartadas
- 3 archivos separados (`crispdm.json`, `kdd.json`, `mlops.json`) — rechazada: reintroduce el
  problema de sincronización que el roadmap pidió evitar.
- Persistir el mapeo CRISP-DM↔KDD dentro de cada `state.json` de proyecto — rechazada: redundante
  y propensa a drift entre proyectos si el mapeo cambia.
- Mantener `futura` sin cambios — rechazada, ver análisis arriba.
- Vocabulario de 4 valores (PASS/WARN/FAIL/N/A) para el estado de las entradas ya en este change
  — rechazada: ese vocabulario es explícitamente para el FUTURO motor de checks (decisión ya
  tomada en el roadmap v0.3, punto 8), que evalúa cumplimiento de un requisito — un eje distinto
  de "en qué estado de trabajo está esta unidad", que es lo que este schema representa ahora.
  Mezclarlos ahora anticiparía una decisión de un change posterior sin necesidad.

## Riesgos
- Retirar `futura` es un cambio de semántica real respecto de v0.2 — mitigado dejándolo explícito
  acá y pidiendo aprobación antes de implementar, no decidiéndolo en silencio.
- Si Change 2 (migración) necesitara un shape distinto al definido acá para migrar sin pérdida
  desde las 10 etapas v0.2, este change tendría que revisarse — mitigado por haber revisado
  explícitamente el mapeo contra las 10 etapas v0.2 antes de fijar el schema (ver `## Alcance` de
  `proposal.md`).
- Nombre repetido `production_readiness` como fase CRISP-DM Y como tier MLOps — es intencional
  (ambos refieren al mismo hito de madurez desde ángulos distintos) pero puede confundir en el
  código; mitigado documentándolo explícitamente en el docstring del módulo y usando siempre
  rutas completas (`crispdm.fases.production_readiness` vs `mlops.production_readiness`) en vez
  de nombres sueltos.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
Ver `proposal.md` § Aprobación — registro único por cambio, no se duplica acá.
