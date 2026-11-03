# Diseño — 20260922-data-contract-validation

## Decisión metodológica/técnica

Flujo conceptual de v0.7 (`docs/roadmap/v0.7.md:45-71`): `DECLARACIÓN → OBSERVACIÓN → EVALUACIÓN
DETERMINISTA → EVIDENCE → INTERPRETACIÓN`. Change 0 implementó `DECLARACIÓN`. `OBSERVACIÓN` ya
existe (`ds_profile`, fuera de este Change). Este Change implementa `EVALUACIÓN DETERMINISTA` para
datos: una función pura `(DataContract, profile: dict) → list[CheckResult]`, más una puerta con
I/O que respeta el guard de holdout existente. `EVIDENCE` (persistencia con hash/`generated_at`) es
Change 3; `INTERPRETACIÓN` es responsabilidad del Lead/metodólogo/reporting, nunca de este módulo.

### Decisión de diseño 1 — Nombre del módulo: `tools/datacontracts/validation.py`

Mismo paquete que Change 0 (`tools/datacontracts`), sibling de `core.py`, mismo patrón exacto que
`tools/reporting/core.py` + `tools/reporting/validation.py` (citado explícitamente en el brief de
esta invocación como la referencia más cercana, y confirmado leyendo el archivo completo).

Alternativas descartadas:
1. **`tools/datacontracts/evaluation.py`**: rechazada. "Evaluación" es el nombre de TODA la etapa
   conceptual del pipeline v0.7 (`docs/roadmap/v0.7.md:54`, "EVALUACIÓN DETERMINISTA"), compartida
   por Change 1 (datos) y Change 2 (`ModelQualityPolicy`, que también evalúa
   `observed vs threshold vs baseline`, `docs/roadmap/v0.7.md:256-268`). Usar "evaluation" para el
   módulo de datos específicamente invitaría a que Change 2 tuviera que buscar otro nombre solo
   para diferenciarse, cuando "validation" es un término ya establecido y sin ambigüedad en este
   repo (`tools/reporting/validation.py`) para "comparar una declaración contra evidencia real y
   producir `CheckResult`".
2. **Paquete nuevo `tools/contractvalidation/`** (separado de `tools/datacontracts`): rechazada.
   El propio `design.md` de Change 0 (`openspec/changes/20260922-data-contracts-core/
   design.md:253-263`) ya anticipa que los módulos siguientes de esta familia (incluido un futuro
   `evolution.py` para Change 4) viven como siblings dentro de `tools/datacontracts`, exactamente
   como `tools/reporting` aloja `core.py`/`governance.py`/`evidence.py`/`validation.py`/`style.py`
   en un solo paquete. Partir la familia en dos paquetes desde el segundo Change rompe ese patrón
   sin ninguna ganancia (la frontera conceptual "contratos de datos" vs. "políticas de modelo" ya
   la resuelve el nombre `datacontracts` del paquete, no hace falta subdividirlo más).
3. **`tools/datacontracts/checks.py`**: rechazada por riesgo de confusión de nombre: el módulo
   importa `dsguard.checks` (`from dsguard import checks`); nombrar el propio archivo `checks.py`
   crearía ambigüedad léxica real en cada `import` y en cualquier referencia futura ("¿el `checks`
   de `dsguard` o el de `datacontracts`?"), sin ningún beneficio sobre `validation.py`, que además
   ya es el nombre usado por el precedente directo (`tools/reporting/validation.py`).

### Decisión de diseño 2 — Firma de las funciones principales

```python
def validate_contract(contract: DataContract, profile: dict) -> list:
    """Pura: sin I/O, sin guard, sin Path. `profile` es un dict YA cargado
    (la forma de profile.json). Nunca lanza."""

def validate_contract_against_profile_file(
    contract: DataContract, profile_path: Path, repo_root: Path,
) -> list:
    """Con I/O: guard de holdout -> lectura -> json.loads -> validate_contract.
    Nunca lanza."""
```

Mismo patrón exacto de `tools/reporting/validation.py:405-412` (`validate_report`, pura) vs.
`tools/reporting/validation.py:1045-1053` (`validate_report_dir`, con I/O) — separar la lógica de
evaluación (testeable con fixtures `dict`, sin filesystem) de la lógica de acceso a disco (que sí
necesita el guard).

`profile` se pasa YA CARGADO (no una ruta) a `validate_contract` por el mismo motivo que
`tools/reporting/validation.py` reconstruye el `Report` UNA vez y pasa el objeto, no la ruta, a
`_validar_report`: evita re-lecturas, hace la función testeable sin tocar disco, y deja el único
punto de I/O + guard concentrado en una sola función (`validate_contract_against_profile_file`),
auditable de punta a punta.

**Quién carga el `dict` y con qué guard**: `validate_contract_against_profile_file` es la única
función de este módulo que abre un archivo. Antes de abrirlo, llama a
`ds_profile.holdout_guard.verificar_permitido(profile_path, repo_root)` — ver decisión 3 para por
qué se importa esa función en particular.

### Decisión de diseño 3 — Importar `ds_profile.holdout_guard` (extensión aditiva narrow, a confirmar por el Lead)

**Posición por defecto que fija el brief de esta invocación** (y que ya está escrita en la regla 7
de `ARCHITECTURE.md:132-140`, redactada por Change 0): los módulos de `tools/datacontracts`
"podrán... leer `profile.json` de `ds_profile` como archivo persistido (nunca importar `ds_profile`
como librería para observar datos... salvo una extensión aditiva de `ds_profile` decidida
explícitamente en SDD)". Es decir: el default es NO importar ningún símbolo de `ds_profile`,
usar `json.load` puro sobre el archivo, y reimplementar el chequeo de holdout con las primitivas de
`dsguard` directamente (mismo patrón interno que usa `holdout_guard.py`: `dsguard.pathguard` +
`dsguard.repo`).

**Decisión tomada en este SDD**: en vez del default, este Change SÍ importa
`ds_profile.holdout_guard.verificar_permitido` — y SOLO ese símbolo, de ese único módulo. Motivo:
el propio roadmap, en el alcance textual de Change 1, no deja esto abierto a interpretación:
"no leer holdout si la scientific/governance policy lo prohíbe: se reutiliza el guard existente,
**no se replica**" (`docs/roadmap/v0.7.md:221-222`, énfasis en el original). "El guard existente"
para esta responsabilidad exacta (decidir si una ruta puede abrirse dado `.claude/guardrails.json`)
es, literalmente, `ds_profile.holdout_guard.verificar_permitido` — la única función del repo que ya
implementa esa lógica completa (carga de config, resolución de ruta relativa, matching de
holdouts, excepciones de lectura vigentes, fail-closed ante rutas no resolubles;
`tools/ds_profile/holdout_guard.py:89-125`). Reimplementarla en `validation.py` sería exactamente
"replicar", lo que el roadmap prohíbe en la misma frase que exige reusarla. Se interpreta esta
instrucción como el ejercicio explícito de la cláusula de excepción de la regla 7
("salvo una extensión aditiva de `ds_profile` decidida explícitamente en SDD") — decisión que se
toma ACÁ, por escrito, no de forma implícita en el código.

Se distingue explícitamente de "importar `ds_profile` como librería para observar datos" (lo
prohibido sin excepción): `holdout_guard.verificar_permitido` no observa ningún dato ni construye
ningún perfil — es una función de PERMISO de lectura de ruta (booleano + motivo), estructuralmente
idéntica a lo que hace `dsguard.pathguard.evaluar_tool_call` para otro contexto. Consumirla no crea
ningún segundo profiler ni reintroduce la responsabilidad de `ds_profile` (observar datos) dentro
de `datacontracts`.

Alternativas descartadas:
1. **Reimplementar el matching de holdouts en `validation.py`** (duplicar la lógica de
   `dsguard.pathguard`/`dsguard.repo`, mismo patrón que `holdout_guard.py` hace internamente):
   rechazada de forma explícita por el texto del roadmap ("no se replica"); además crea dos
   implementaciones independientes de una decisión de seguridad (acceso a holdouts) que
   inevitablemente divergen con el tiempo (mismo riesgo que Change 0 ya documentó para
   `SEVERITIES` duplicado de `dsguard.checks`, pero ahí SÍ aceptable por ser solo vocabulario de
   texto — acá sería lógica de control de acceso, un riesgo cualitativamente mayor).
2. **No aplicar ningún guard en este Change, dejar que el Lead/CLI (Change 4) lo aplique antes de
   invocar `validate_contract_against_profile_file`**: rechazada; el roadmap dice explícitamente
   "no leer holdout" como una responsabilidad DE ESTE Change ("Change 1"), no de un Change
   posterior — dejarlo fuera violaría el alcance textual y dejaría una vía de lectura de holdout
   sin guardas si algún consumidor futuro llama a la función directamente sin pasar por una CLI
   que aplique el guard por su cuenta.
3. **Importar `ds_profile` completo (sin restringir a `holdout_guard`)**: rechazada; sería
   exactamente lo que la regla 7 prohíbe sin excepción explícita ("nunca importar `ds_profile`
   como librería para observar datos"), y no hay ninguna necesidad real de ningún otro símbolo de
   `ds_profile` en este Change (el `dtype`, `min`, `max`, etc. ya vienen en el `dict` de
   `profile.json`, no hace falta recalcular nada).

**Este punto se deja marcado explícitamente como una decisión a confirmar por el Lead** (no es una
ambigüedad menor): si el Lead prefiere el default estricto (nunca tocar `ds_profile`, ni siquiera
`holdout_guard`), la alternativa 1 (reimplementar con `dsguard.pathguard`/`dsguard.repo`
directamente, mismo patrón interno) es perfectamente viable y no cambia ningún requisito de
`spec.md` salvo R1 (el set de imports permitidos pasaría a ser `stdlib + dsguard.checks +
dsguard.pathguard + dsguard.repo + dsguard.core`, en vez de incluir `ds_profile.holdout_guard`).

### Decisión de diseño 4 — Bridge `type_family → dtype`, implementado ahora (no solo documentado)

Change 0 dejó la tabla de mapeo en el docstring de `core.py`, sin código
(`tools/datacontracts/core.py:79-96`). Este Change la implementa como constante privada de
`validation.py`:

```python
_DTYPE_ESPERADO_POR_FAMILIA = {
    "string": frozenset({"texto"}),
    "integer": frozenset({"entero"}),
    "float": frozenset({"flotante"}),
    "boolean": frozenset({"booleano"}),
    "date": frozenset({"fecha"}),
    "datetime": frozenset({"fecha"}),   # ds_profile no distingue date de datetime
    "unknown": frozenset(),             # sin mapeo -> siempre N/A
}
```

`"date"` y `"datetime"` mapean al mismo dtype observado (`"fecha"`) porque `ds_profile` no separa
ambos casos (`clasificar_dtype`, `tools/ds_profile/column_stats.py:105-127`, un solo bucket
`"fecha"`). Consecuencia documentada como límite honesto: un `ContractField` declarado `"datetime"`
nunca puede distinguirse de uno declarado `"date"` con la evidencia actual de `ds_profile` — ambos
pasan o fallan exactamente igual. No se intenta inferir la presencia de componente de hora
inspeccionando strings crudos (fuera de alcance: eso sería observar datos más allá del perfil ya
agregado).

### Decisión de diseño 5 — Hallazgo de `ds_profile`: qué es exacto SIEMPRE vs. qué depende del muestreo

Verificado leyendo el código real (no asumido de la lectura superficial del roadmap), citado en
`proposal.md`: el loop principal de `generar_perfil` llama `acumuladores[nombre].observar(valor)`
en TODAS las filas del dataset, ANTES de la bifurcación `if modo_muestreado` que decide qué se
retiene para los estadísticos de orden (`tools/ds_profile/report.py:150-170`). `AcumuladorColumna.
observar` (`tools/ds_profile/column_stats.py:172-196`) actualiza `nulos`, `min_numerico`,
`max_numerico`, `min_fecha`, `max_fecha` en esa misma llamada — streaming completo, nunca desde una
muestra. Por lo tanto, en `columnas_detalle[nombre]` (`construir_metricas_columna`,
`tools/ds_profile/column_stats.py:243-306`):

| Campo | Exacto SIEMPRE (streaming completo) | Depende de `exactitud_orden` (muestra bajo sampling) |
|---|---|---|
| `nulls.count`/`pct` | Sí (marcado `"exactitud": "exacta"` fijo, línea 269) | — |
| `min`/`max` (entero/flotante) | Sí (`acumulador.min_numerico`/`max_numerico`) | — |
| `fecha_min`/`fecha_max` | Sí (`acumulador.min_fecha`/`max_fecha`) | — |
| `unique.count` | — | Sí (`len(set(valores_orden))`, marcado `unique.exactitud`) |
| `top_valores` | — | Sí (`Counter(valores_orden)`, presencia real pero frecuencia aproximada) |
| `mediana`/`cuantiles` | — | Sí (`valores_orden`, marcado `exactitud_estadisticos`) |

Consecuencia de diseño (R7 de `spec.md`): `CONTRACT-NULLABILITY`, `CONTRACT-RANGE` y
`CONTRACT-DATE-RANGE` se evalúan siempre como `PASS`/`FAIL` determinista, sin condicionar a
`sampling.activo` — usar esa bandera global como gate habría sido MÁS conservador de lo que la
evidencia real permite, violando "check everything" sin necesidad real. `CONTRACT-UNIQUENESS`,
`CONTRACT-KEY` (unicidad de key simple) y `CONTRACT-DOMAIN` sí consultan el campo `exactitud`
específico de cada estadístico (`unique.exactitud`), nunca `sampling.activo` directamente — es más
preciso y ya viene provisto por `ds_profile` sin que este Change tenga que inferir nada.

**Asimetría violación-vs-cumplimiento bajo muestreo** (aplicada a `unique`/`allowed_values`/`keys`
simples): una muestra puede DEMOSTRAR una violación (un valor duplicado u observado fuera de
dominio en la muestra es evidencia real, porque esos valores efectivamente existen en el dataset),
pero NUNCA puede demostrar cumplimiento (la ausencia de violación en la muestra no descarta que
exista en las filas no muestreadas). Esta asimetría es la aplicación literal de "aplicable pero no
verificable → WARN... nunca un PASS inventado" (decisión 3 del roadmap) al caso concreto de
`ds_profile`, no una regla nueva inventada por este Change.

**Criterio de duplicado bajo muestreo, implementado con el campo del perfil que sí existe (revisión
del Change 1, hallazgo 1)**: `profile.json` no persiste el tamaño de la muestra NO NULA de una
columna concreta (`sampling.tamano_muestra` es el tamaño de la muestra de FILAS completas, no de
valores no nulos de una columna dada) — reconstruir esa longitud de muestra no es posible con la
evidencia disponible. En su lugar, la implementación real (`_evaluar_unicidad_campo`,
`tools/datacontracts/validation.py`) usa una señal directa y siempre disponible: si algún
`top_valores[i]["frecuencia"] > 1`, eso es evidencia real e inequívoca de un valor repetido
observado dentro de la muestra (un `Counter` no puede reportar frecuencia > 1 sin que el valor haya
aparecido más de una vez en los datos vistos), sin importar si `top_valores` está truncado a
`top_n`. Ausencia de cualquier frecuencia > 1 en `top_valores` nunca se interpreta como evidencia de
`PASS` (podría haber un duplicado fuera de las top-N filas más frecuentes) — cae en `WARN` "no
verificable como cumplimiento", igual que exige R10.2 de `spec.md`. Es más conservador que el
criterio de longitud de muestra reconstruida (nunca convierte ausencia de evidencia en `PASS`) y
cumple R12 igual; comparte el mismo campo del perfil (`top_valores`) que ya usa `allowed_values`
(R10.3), sin introducir una fuente de evidencia nueva. Mismo criterio para `CONTRACT-KEY` (R11) con
key simple bajo muestreo, por compartir `_evaluar_unicidad_campo`. `spec.md` (R10.2/R11) refleja
este criterio real, no una longitud de muestra reconstruida.

### Decisión de diseño 6 — Severidad de checks sin `Constraint.severity` asociada

`CONTRACT-FIELD-MISSING`, `CONTRACT-FIELD-UNEXPECTED`, `CONTRACT-TYPE-MISMATCH`,
`CONTRACT-NULLABILITY` y `CONTRACT-KEY` (para key simple) derivan de `ContractField`/
`DataContract.keys`, capas de Change 0 que NO llevan un campo `severity` (solo `Constraint` lo
tiene, `tools/datacontracts/core.py:416`). Este Change fija defaults uniformes, sin volverlos
configurables (no hay ningún mecanismo en `DataContract` para declararlos distinto):
- `CONTRACT-FIELD-MISSING`: `FAIL` fijo — un campo requerido ausente es, por definición, una
  violación de estructura declarada explícitamente (`required=True`), no una expectation de
  calidad opcional.
- `CONTRACT-FIELD-UNEXPECTED`: `WARN` fijo — ver decisión 7 (política de "unexpected field").
- `CONTRACT-TYPE-MISMATCH`: `FAIL` fijo (salvo `N/A` para `"unknown"`) — mismo criterio que
  `FIELD-MISSING`: la familia de tipo es una declaración estructural, no una expectation opcional.
- `CONTRACT-NULLABILITY`: `FAIL` fijo — misma razón.
- `CONTRACT-KEY` (key simple): `FAIL` fijo — una key declarada es, por convención de todo el
  vocabulario de bases de datos que el propio `DataContract.keys` imita, una propiedad estructural
  no negociable, no una expectation con severidad declarable.

Alternativa descartada: agregar un parámetro opcional a `validate_contract` (p. ej.
`structural_severity: str = "FAIL"`) para que el llamador pudiera bajar estos a `WARN`
globalmente. Rechazada: el roadmap no pide configurabilidad de este tipo en ningún lado, y
agregarla sin que ningún Change la pida sería inventar superficie de API no solicitada (mismo
criterio que Change 0 rechazó agregar un stub de `evaluate` "por si acaso").

### Decisión de diseño 7 — Política de `CONTRACT-FIELD-UNEXPECTED`: `WARN` uniforme (a confirmar por el Lead)

`DataContract` no tiene ningún campo `allow_extra_fields` (confirmado leyendo `core.py` completo:
no existe en `ContractField`, `Constraint` ni `DataContract`). El brief de esta invocación pide
decidir una política razonable por defecto si el core no la declara, con justificación, marcando
`WARN` como sugerencia explícita del propio brief ("WARN, nunca FAIL, salvo que digas lo
contrario"). Se adopta esa sugerencia: `WARN` siempre, sin distinguir por `dataset_role`.

Motivo: un campo observado y no declarado en el contrato es, en la enorme mayoría de los casos
reales, evolución normal de un dataset (una columna nueva agregada aguas arriba) — tratarlo como
`FAIL` bloquearía sistemáticamente cualquier evolución aditiva del dataset sin que el roadmap haya
pedido ese comportamiento en ningún lado (y contradiría, en espíritu, la idea de "additive
compatible" que Change 4 va a clasificar sobre contratos — un campo nuevo observado es
estructuralmente análogo a un "additive change" desde el lado de la observación, no desde el
contrato, pero el paralelismo conceptual es el mismo: aditivo no es lo mismo que ruptura).

Alternativas descartadas:
1. **`FAIL` uniforme**: rechazada; sería más estricto de lo que cualquier decisión congelada del
   roadmap exige, y generaría fricción operativa alta (cualquier columna nueva agregada al dataset
   -- común en la práctica -- rompería la validación de contrato sin que el contrato mismo haya
   cambiado, cuando el roadmap distingue explícitamente entre severidad declarada y verificabilidad
   -- acá no hay ninguna declaración del contrato sobre este caso en absoluto).
2. **Severidad condicionada a `dataset_role`** (p. ej. `FAIL` para `"raw_table"`, `WARN` para
   `"feature_table"`/`"scoring_output"`): rechazada por ahora; sería inventar una regla de negocio
   metodológica no pedida por el roadmap ni por ninguna decisión de diseño congelada — exactamente
   el tipo de decisión semántica que corresponde al Lead/metodólogo, no a este Change técnico
   (principio "LLM decide lo semántico", pero incluso el LLM del Lead debería decidirlo mirando el
   roadmap, no este SDD inventándolo unilateralmente).
3. **Agregar `allow_extra_fields: bool` a `DataContract`**: rechazada de plano; requeriría
   modificar `tools/datacontracts/core.py` (Change 0, cerrado e inmutable salvo bug real) y
   cambiar `SCHEMA_VERSION`/`content_sha256()` de todos los contratos existentes — fuera de alcance
   explícito de este Change, y una decisión de ese calibre requiere su propio SDD si se toma.

### Decisión de diseño 8 — "Stale" acotado a "perfil ausente/no parseable", sin recomputar fingerprint

El brief ofrece dos opciones (comparar `fingerprint` contra el dataset actual, o solo verificar que
el perfil exista y sea parseable). Se adopta la segunda. Motivo: comparar el `fingerprint`
persistido en `profile.json` (`tools/ds_profile/report.py:200-212`, calculado por
`fingerprint_mod.calcular_fingerprint(ruta_input)`) contra el dataset VIVO exigiría, como mínimo,
(a) conocer la ruta del dataset original (`profile["dataset_path"]`, que el propio roadmap señala
como potencialmente absoluto y no portable, `docs/roadmap/v0.7.md:318-319`), (b) volver a abrir y
leer ESE archivo para recalcular su hash, y (c) importar `ds_profile.fingerprint` (un módulo de
`ds_profile` distinto de `holdout_guard`, y esta vez sí "observando datos" en sentido literal —
tocar el dataset crudo otra vez). Las tres cosas juntas violarían la decisión 2 del roadmap
("`ds_profile` es el único observador de datos... no se construye un segundo profiler") de una
forma mucho más sustancial que el import narrow de `holdout_guard` (decisión 3): acá sí habría una
nueva ruta de lectura de dataset crudo, con su propio guard de holdout a aplicar, su propio riesgo
de leer un holdout, y su propio manejo de errores (formato no soportado, archivo movido, etc.) —
scope material, no una extensión aditiva menor. Change 3 (`quality-evidence-and-drift`) ya tiene
`generated_at` en su alcance explícito (`docs/roadmap/v0.7.md:297-321`) y es el lugar natural para
esta responsabilidad, con su propio SDD.

Este Change, entonces, acota "evidencia faltante o stale" a: perfil inexistente, ruta denegada por
holdout, ilegible, JSON inválido, o con forma estructural inválida (le faltan claves mínimas) —
todo bajo `CONTRACT-EVIDENCE-MISSING`. La palabra "stale" en el sentido de "el dataset cambió desde
que se generó el perfil" NO se implementa en este Change; se documenta como límite explícito (ver
`proposal.md`, "Supuestos descartados").

### Decisión de diseño 9 — `min_length`/`max_length`: extensión aditiva de `ds_profile` evaluada y NO tomada

Evaluada explícitamente (el brief lo exige si hiciera falta una extensión): `ds_profile` no calcula
ninguna estadística de longitud de texto (`tools/ds_profile/column_stats.py:243-306`, confirmado
completo — no hay ningún campo `length`/`longitud`/`len_min`/`len_max`). Para verificar
`min_length`/`max_length` de forma determinista, `ds_profile` necesitaría un nuevo acumulador
(`longitud_min`/`longitud_max` sobre `len(_texto(valor))`, streaming, mismo patrón que
`min_numerico`/`max_numerico`) y dos campos nuevos en `columnas_detalle[nombre]`.

**Evaluación de impacto** (siguiendo el criterio del roadmap: "si esa extensión rompe el schema del
perfil → STOP", decisión 2): agregar dos campos nuevos a `columnas_detalle[nombre]` es, en
principio, un cambio ADITIVO de forma (no rompe consumidores existentes que ignoran claves
desconocidas) — no calificaría como STOP material por sí solo. Pero modificar `ds_profile` está
fuera del alcance explícito de este Change (`docs/roadmap/v0.7.md`, límite "no construir un segundo
profiler" se extiende, por prudencia, a "no modificar el profiler existente sin que el propio
Change de datos lo pida"), y el propio brief de esta invocación es explícito: "si hiciera falta una
extensión ADITIVA de `ds_profile`, evaluarla en el SDD... documentar la decisión, aunque decidas NO
hacerla en este Change". Se decide NO tomarla en este Change: `min_length`/`max_length` quedan
siempre `WARN` "no verificable con la evidencia actual" (R2/R10.5 de `spec.md`). Si el Lead
considera que esta constraint es prioritaria, la extensión de `ds_profile` (nuevo acumulador +
campo en el schema de `profile.json`, con su propio bump de `SCHEMA_VERSION` de `ds_profile` si
aplica) es candidata a un SDD propio, posiblemente dentro de este mismo Change como una segunda
invocación si el Lead lo aprueba explícitamente antes de implementar — no se asume esa aprobación
acá.

### Texto exacto de la fila nueva en `ARCHITECTURE.md` §2.1

> `tools/datacontracts/validation.py` | Evaluación de `DataContract` contra evidencia real (v0.7
> Change 1: `validate_contract`/`validate_contract_against_profile_file`, códigos `CONTRACT-*`,
> produce `dsguard.checks.CheckResult`) -- importa `dsguard.checks` (dirección permitida por la
> regla 7) y, de `ds_profile`, SOLO `holdout_guard.verificar_permitido` (nunca `ds_profile.report`,
> `.column_stats`, `.fingerprint` ni ningún otro símbolo: no observa datos, solo reusa el guard de
> lectura de holdout); consume `profile.json` como `dict` ya cargado, nunca recalcula estadísticas
> ni reabre el dataset original; vocabulario `PASS`/`WARN`/`FAIL`/`N/A`, nunca `PASS` por falta de
> evidencia; no conoce protocolo de hooks, es core.

### Texto exacto de la ampliación de la regla 7 en `ARCHITECTURE.md` §3

Se agrega al final del párrafo existente de la regla 7 (sin borrar nada de lo ya escrito por
Change 0):

> Change 1 (`data-contract-validation`) ejercita esta cláusula de extensión aditiva de forma
> concreta y acotada: `tools/datacontracts/validation.py` importa únicamente
> `ds_profile.holdout_guard.verificar_permitido` (un solo símbolo, de un solo módulo, que decide
> permiso de lectura de una ruta -- no observa ni agrega datos) para no replicar la lógica de
> guard de holdout, siguiendo la instrucción explícita del roadmap ("se reutiliza el guard
> existente, no se replica"). No importa ningún otro símbolo de `ds_profile` (`report`,
> `column_stats`, `fingerprint`, `sampling`, `quality_flags`, `schema`, `io_readers` quedan
> fuera). Verificado por `tools/tests/test_v07_validation_neutrality.py`.

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica un split de modelado; sí aplica el guard de holdout sobre la lectura del `profile.json`
persistido (ver "Holdout policy" en `proposal.md` y decisión de diseño 3 arriba).

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica a features de modelado. Riesgo de diseño relacionado, mitigado explícitamente: si
`validate_contract` alguna vez recibiera datos crudos (filas) en vez de un `profile` ya agregado,
un consumidor podría usar este módulo para "espiar" evidencia sin pasar por el guard de holdout
único. Mitigación: `validate_contract` solo acepta `dict` con la forma agregada de `profile.json`
(nunca un `DataFrame`, nunca una lista de filas); la única vía de lectura de disco
(`validate_contract_against_profile_file`) aplica el guard ANTES de abrir cualquier archivo, sin
excepción.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica aleatoriedad: no hay `RANDOM_STATE`. `validate_contract` es determinista por construcción
(misma entrada `contract`+`profile` → misma `list[CheckResult]`, mismo orden); los tests de
`test_validation.py` usan fixtures literales, sin generación aleatoria de datos sintéticos (a
diferencia de `tools/reporting/examples/eda_generic.py`, que si necesitara aleatoriedad usaría
`random.Random(RANDOM_STATE)` -- no es el caso de este Change, los fixtures son valores fijos
escritos a mano).

## Alternativas descartadas (adicionales a las de cada decisión numerada arriba)
1. **Un único código genérico `CONTRACT-VIOLATION` con el `constraint_type` en `detail`** en vez de
   un código por `constraint_type`: rechazada; el roadmap pide explícitamente distinguir "campo
   requerido ausente", "campo inesperado", "tipo incompatible", "nullability", "unicidad",
   "rango/dominio", "key/invariante" como categorías separadas (`docs/roadmap/v0.7.md:200-212`), y
   la deuda 6 de `ARCHITECTURE.md` §4.1 ya exige un "registro único de códigos `CONTRACT-*`/
   `QUALITY-*` desde el inicio" (`docs/roadmap/v0.7.md:461-463`) -- códigos específicos y
   documentados en `spec.md` R2 cumplen esa deuda desde el primer Change que los define.
2. **Devolver un solo `CheckResult` agregado por `DataContract` (PASS global / FAIL global)** en
   vez de una lista granular: rechazada; contradice "check everything, report everything"
   (`tools/dsguard/checks.py:6-7`) y el propio patrón `_resumir` de `tools/reporting/validation.py`
   que este Change replica -- un solo agregado ocultaría exactamente qué campo/constraint violó.
3. **Evaluar `Constraint.field is None` (alcance de dataset) genéricamente para TODOS los
   `constraint_type`, no solo caso por caso**: rechazada; cada `constraint_type` tiene una relación
   distinta con "alcance de dataset" (p. ej. `unique` con `params["fields"]` SÍ tiene sentido con
   `field=None`, `allowed_values` NO) -- generalizar habría introducido comportamiento incorrecto
   para al menos dos de los diez tipos; se documenta caso por caso en `spec.md` R10.

## Riesgos
- **Import narrow de `ds_profile.holdout_guard` como precedente**: si un Change futuro (Change 2,
  3) necesita otro símbolo puntual de `ds_profile`/`dsguard` por un motivo similarmente acotado, el
  precedente de este Change (import de un solo símbolo, documentado explícitamente en
  `ARCHITECTURE.md`, nunca el paquete completo) es el patrón a seguir -- mitigado dejándolo por
  escrito acá y en `ARCHITECTURE.md`, no repitiendo la decisión de forma implícita.
- **`dtype` observado sin marca de exactitud propia** (a diferencia de `unique`/`mediana`): si
  `ds_profile` alguna vez agrega una marca de confianza al `dtype` (p. ej. bajo muestreo muy
  agresivo con muy pocas filas distintas observadas), `CONTRACT-TYPE-MISMATCH` de este Change no lo
  reflejaría automáticamente -- riesgo aceptado y documentado (R6 de `spec.md`), no bloqueante:
  `ds_profile` ya decide su propio `dtype` con un umbral de clasificación
  (`_UMBRAL_CLASIFICACION`, `tools/ds_profile/column_stats.py`), este Change confía en esa
  decisión sin cuestionarla, coherente con "no construir un segundo profiler".
- **Comparación de `allowed_values`/`top_valores` por texto (`_texto(v)`)**: `ds_profile` normaliza
  todo a texto para `top_valores` (`Counter(_texto(v) for v in valores_orden)`,
  `tools/ds_profile/column_stats.py:261-262`); este Change hace la misma normalización al comparar
  contra `params["values"]` (que puede tener `int`/`float`/`bool`/`str`/`None`) -- documentado
  explícitamente en R10.3 de `spec.md`: la comparación es por representación de texto, no por tipo
  Python exacto, para ser consistente con cómo `ds_profile` ya perdió esa distinción al construir
  `top_valores`. Riesgo aceptado: `allowed_values=[1]` y un valor observado `"1"` (string) se
  tratarían como coincidentes -- mismo comportamiento que tendría cualquier comparación contra
  `top_valores`, no una imprecisión nueva de este Change.
- **`min_length`/`max_length` permanentemente `WARN`**: si el Lead considera esta constraint
  importante, la extensión de `ds_profile` (decisión 9) queda pendiente de aprobación explícita
  antes de tomarse -- riesgo de que quede como deuda permanente si nadie la prioriza; se documenta
  para que no se pierda de vista, no se implementa preventivamente.
- **Asimetría de robustez entre `CONTRACT-RANGE` y `CONTRACT-DATE-RANGE`**: `_regla_min_max_value`
  no defiende explícitamente contra `min`/`max` `None` con `dtype` numérico (a diferencia de
  `_regla_date_min_max`, que sí trata `fecha_min`/`fecha_max` no parseable como `WARN`) -- señalado
  en la revisión del Change 1 (`data-science-reviewer`); aceptado como riesgo diferido, sin fix: con
  el `ds_profile` actual esa rama es inalcanzable (`min`/`max` numérico se acumula siempre que el
  `dtype` es `"entero"`/`"flotante"`, nunca queda `None` para una columna con ese `dtype`).

## Aprobación humana
El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único por
cambio y vive en la sección "Aprobación" de `proposal.md` -- no se duplica acá.
