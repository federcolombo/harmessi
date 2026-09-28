# Propuesta — 20260922-data-contracts-core

## Problema
Harmessi v0.7 (ML Quality & Data Contracts) necesita responder de forma determinista "qué
estructura de datos se esperaba" y "qué reglas de calidad aplican" (`docs/roadmap/v0.7.md:12-18`),
pero hoy no existe ningún objeto que declare esa expectativa: ni `DataContract`, ni `ContractField`,
ni una noción neutral de "familia de tipo", nullability, unicidad, rango, dominio, invariante o key
declarada. Sin ese contrato, el Change 1 (`data-contract-validation`) no tendría nada contra qué
evaluar `ds_profile.report`, y cada consumidor futuro (Change 2 políticas de modelo, Change 3
evidencia/drift, Change 4 CLI) tendería a inventar su propia forma de "expectativa de datos",
repitiendo el problema que `tools/reporting/core.py` ya resolvió para reportes
(`openspec/changes/20260918-reporting-core/proposal.md:3-9`).

Además, tres capas distintas de una expectativa de datos suelen confundirse en un solo objeto: la
estructura (campos, tipos, nullability, keys), la calidad esperada (rangos, dominios, unicidad,
invariantes simples) y las reglas de negocio semánticas (solo auditables por un humano, nunca
evaluables por el binario). Si el contrato no las separa explícitamente desde este Change, un
Change posterior corre el riesgo de intentar "evaluar" una regla de negocio y violar el principio
permanente "LLM decide lo semántico; el binario calcula y hace cumplir lo determinista"
(`docs/roadmap/v0.7.md:27-29`).

## Objetivo
Crear un paquete nuevo `tools/datacontracts/` con un módulo `core.py` neutral y solo-stdlib que
defina `DataContract`, `ContractField`, `Constraint`, `BusinessRule`, `ContractVersion` y
`CompatibilityPolicy`: contratos serializables, deterministas y versionables que declaran
estructura, expectativas de calidad y reglas de negocio referenciables — sin observar, evaluar ni
leer ningún dato, sin DSL de expresiones arbitrarias y sin depender de `ds_profile`, `dsguard`,
pandas, SQL, Spark ni ningún motor de almacenamiento.

## Evidencia
- `docs/roadmap/v0.7.md:144-190`: alcance completo de "Change 0 — data-contracts-core":
  conceptos candidatos (`DataContract`, `ContractField`, `Constraint`, `ContractVersion`,
  `CompatibilityPolicy`), lista de lo que un contrato debe poder expresar, separación en tres
  capas (schema/structure, quality expectations, semantic business rules) y criterios de cierre
  (round-trip determinista, versionado explícito, validación estructural, tests de neutralidad).
- `docs/roadmap/v0.7.md:73-110` (decisiones de diseño 1-8, congeladas): decisión 2 fija que
  `ds_profile` es el único observador de datos y que este Change no construye un segundo profiler;
  decisión 3 fija que la severidad se declara en el contrato y la verificabilidad la decide el
  binario (Change 1); decisión 8 prohíbe dependencias nuevas (Great Expectations, Pandera, etc.).
- `docs/roadmap/v0.7.md:112-127`: reglas de arquitectura para el código de v0.7 — core neutral
  solo-stdlib, dirección de dependencias (v0.7 podrá importar `dsguard.checks` y consumir
  `profile.json` como archivo en Changes posteriores; ningún paquete existente importa los
  paquetes nuevos de v0.7), serialización determinista con versionado explícito y hash de
  contenido.
- `docs/roadmap/v0.7.md:193-225` (Change 1, para no adelantarlo): el Change 1 evalúa observaciones
  reales contra `DataContract` reutilizando `ds_profile`, produce `CheckResult`, y exige que
  `sampling.activo=true` degrade a no-verificable las reglas que dependen de valores exactos —
  información que este Change 0 debe dejar puenteable sin implementarla.
- `docs/roadmap/v0.7.md:350-389` (Change 4, para no adelantarlo): la clasificación determinista de
  compatibilidad entre versiones de contrato (`additive compatible`, `removal`,
  `required-field addition`, `type change`, `constraint tightening/loosening`,
  `unknown/needs review`) es responsabilidad del Change 4, no de este Change.
- `ARCHITECTURE.md:101-133` (§3, reglas de dependencia): la regla 6 (familia `tools/reporting`) es
  el precedente directo de la regla 7 que este Change propone para `tools/datacontracts`; hoy no
  existe ninguna fila en §2.1 ni regla en §3 para un paquete de contratos de calidad.
- `tools/reporting/core.py:1-29,82-84,264-276,960-963`: patrón de referencia más cercano —
  dataclasses `frozen=True`, excepción propia de contrato (`ReportingContractError`), helpers
  `_validar_id`/`_exigir_*`, `to_dict()`/`from_dict()`, `canonical_json()`, `content_sha256()`,
  `SCHEMA_VERSION` y política de evolución de esquema (campo nuevo → bump de `SCHEMA_VERSION`).
- `tools/reporting/profiles/eda.py:40-43`: `EXTENSION_PREFIX = "x_"`, el patrón exacto de
  extensiones controladas que este Change reutiliza.
- `tools/dsguard/checks.py:14-22,25-47`: vocabulario `PASS`/`WARN`/`FAIL`/`N/A` y `kind`
  (`check`/`technical_error`) de `CheckResult` — este Change no lo importa ni lo produce, pero la
  severidad declarada en `Constraint` debe ser puenteable a ese vocabulario para el Change 1.
- `tools/ds_profile/column_stats.py:105-127` (`clasificar_dtype`): las 5 familias de dtype que
  infiere `ds_profile` (`texto`, `booleano`, `entero`, `flotante`, `fecha`).
- `tools/ds_profile/report.py:205-232`: forma exacta de `profile.json` persistido (`schema`,
  `columnas_detalle` con `dtype`/`nulls`/`unique`/`min`/`max`/`mediana`/`cuantiles`/
  `fecha_min`/`fecha_max`, `sampling.activo`) contra la que un futuro Change 1 evaluará contratos.
- `tools/tests/test_v06_core_neutrality.py:1-16,30-33`: patrón `ast` de neutralidad de
  dependencias que este Change replica en `test_v07_core_neutrality.py` (invocación 2).
- `tools/ds_init/manifest.py:70-107` (`EntradaManifiesto`, `stage_minimo` default `"discovery"`):
  forma exacta de las entradas de manifest que el paquete nuevo necesitará.
- `openspec/changes/20260918-reporting-core/{proposal,spec,design,tasks}.md`: Change SDD más
  análogo en v0.6 (mismo tipo de tarea — contrato core neutral, versionado, serializable); usado
  como plantilla de estructura y nivel de detalle de estos 4 artefactos.

## Supuestos descartados
- Que este Change deba validar un `DataContract` contra un `profile.json` real o contra cualquier
  observación. Descartado explícitamente: `docs/roadmap/v0.7.md:146-147` dice "este Change no
  observa ni evalúa nada"; eso es el Change 1.
- Que `Constraint`/`BusinessRule` deban incluir un lenguaje de expresiones (p. ej. `pandas.eval`,
  una gramática propia de invariantes). Descartado: el roadmap prohíbe explícitamente un "lenguaje
  universal de validación ni DSL de expresiones arbitrarias" (`docs/roadmap/v0.7.md:182-183`); los
  invariantes son "declarativos y acotados" (`docs/roadmap/v0.7.md:169`) y las reglas de negocio
  son solo declarables/auditables, nunca evaluadas (`docs/roadmap/v0.7.md:176-179`).
- Que `ContractVersion`/`CompatibilityPolicy` deban incluir lógica de diff o clasificación de
  compatibilidad entre dos versiones. Descartado: esa clasificación determinista es del Change 4
  (`docs/roadmap/v0.7.md:371-381`); este Change solo declara ambos tipos como metadata/política
  versionada, sin comparar nada.
- Que el `type_family` de `ContractField` importe o reutilice el vocabulario textual exacto de
  `ds_profile` (`texto`/`booleano`/`entero`/`flotante`/`fecha`). Descartado (decisión de diseño ya
  congelada del brief de esta invocación): vocabulario propio y neutral, documentado como
  puenteable sin importar `ds_profile` (ver `design.md`).
- Instalar Great Expectations, Pandera o cualquier librería de validación de esquemas para modelar
  el contrato. Descartado por decisión 8 del roadmap (`docs/roadmap/v0.7.md:108-110`): sin
  dependencias nuevas.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica.

## Alcance
- `tools/datacontracts/__init__.py` y `tools/datacontracts/core.py` (solo stdlib): vocabularios,
  `DataContractError`, `ContractField`, `Constraint`, `BusinessRule`, `ContractVersion`,
  `CompatibilityPolicy`, `DataContract`, `canonical_json`, `DataContract.content_sha256()`.
- `tools/datacontracts/tests/__init__.py`, `test_core.py`, `test_installability.py`.
- `tools/tests/test_v07_core_neutrality.py` (nuevo) y agregar `tools/datacontracts/core.py` a
  `MODULOS_CORE` en `tools/tests/test_architecture_boundaries.py`.
- `tools/ds_init/manifest.py`: dos entradas VERBATIM (`tools/datacontracts/__init__.py`,
  `tools/datacontracts/core.py`) con `stage_minimo` por defecto (`discovery`).
- `ARCHITECTURE.md`: fila nueva en §2.1 y regla 7 en §3.
- `docs/roadmap/v0.7.md`: al cerrar el Change, tildar `[x] Change 0`.
- `openspec/changes/20260922-data-contracts-core/verification.md` (al cierre, invocación 5).

Ver `tasks.md` para el desglose exacto de rutas por invocación.

## Fuera de alcance
- Observar o evaluar cualquier `profile.json` real u otra evidencia contra un `DataContract`:
  Change 1 (`data-contract-validation`).
- Producir `CheckResult` o cualquier resultado `PASS`/`WARN`/`FAIL`/`N/A`: Change 1.
- `ModelQualityPolicy`, `MetricRequirement`, `ObservedMetric`, `BaselineReference`,
  `EvaluationContext`: Change 2 (`model-quality-policies`).
- Evidencia de calidad persistida, `generated_at`, hashes de bytes persistidos, drift: Change 3
  (`quality-evidence-and-drift`).
- CLI (`harmessi contract ...`/`harmessi quality ...`), clasificación determinista de
  compatibilidad entre versiones de contrato, impact preflight de contratos: Change 4
  (`quality-integration-and-cli`).
- Cualquier cambio a `dsguard`, `ds_profile`, `dsimpact`, `reporting`, `providers`, `routing`,
  `fallback`, `harmessi_bench` salvo el registro de manifest y la fila/regla de
  `ARCHITECTURE.md` listados en "Alcance".
- Leer, escribir o inferir sobre cualquier dataset real, sintético o de ejemplo.

## Holdout policy (condicional — solo cambios "sensible")
No aplica: este Change define contratos de datos en memoria (declaración pura); no lee ningún
dataset, no observa ningún `profile.json`, no toca `holdout_guard` ni ninguna política de
scientific validity. La validación contra observaciones reales (donde sí importaría el guard de
holdout) es explícitamente del Change 1 (`docs/roadmap/v0.7.md:220-222`).

## Impacto en production-readiness (opcional)
No aplica en este bloque: decisión 5 del roadmap (`docs/roadmap/v0.7.md:96-101`) fija que ningún
resultado de v0.7 modifica readiness, promotion gates ni el lifecycle; este Change 0 en particular
ni siquiera produce resultados (solo declaración), por lo que no hay ninguna superficie de
readiness que tocar.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md` (SDD completo).

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md` (SDD completo).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-22
- Alcance aprobado: "Change 0 — data-contracts-core (docs/roadmap/v0.7.md)"
- Versión de artefactos referenciada: esta versión de los 4 archivos (commit de este Change)
- Cita: "Ejecutá autónomamente los Changes de docs/roadmap/v0.7.md ... Change 0 —
  data-contracts-core ... audit acotado → SDD → validación contra roadmap/arquitectura →
  implementación → tests → reviewer → fixes → re-tests → verification → cierre → commit local
  (instrucción explícita del usuario, 2026-09-22, bajo el Contrato de autonomía de
  `docs/roadmap/README.md`)."

## Motivo de rechazo
No aplica.

## Desacuerdo registrado
No aplica.
