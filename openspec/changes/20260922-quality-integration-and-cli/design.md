# Diseño — 20260922-quality-integration-and-cli

## Decisión metodológica/técnica

### Decisión 1 — Host del CLI: `tools/ds_guard.py` (launcher top-level), subcomandos `contract`/`quality`

**Elegido**: agregar `contract` y `quality` como subparsers de primer nivel en
`tools/ds_guard.py` (el archivo, no el paquete `tools/dsguard/`), con el mismo patrón que
`impact` (`tools/ds_guard.py:1645-1655`, `_importar_dsimpact`/`cmd_impact_scan`,
`tools/ds_guard.py:792-825`): import perezoso opcional del paquete correspondiente dentro de
cada `cmd_*`, degradación con exit code 3 si no está instalado en el stage actual, y la
función `cmd_*` en sí NUNCA contiene lógica de validación/clasificación/evaluación — solo
parsea, carga JSON, llama UNA función pública del paquete, formatea.

**Criterio real que ya sigue el repo** (evidencia, no preferencia): un paquete nuevo de
`tools/` obtiene su propia CLI de paquete (`python -m tools.<paquete>[.cli]`) cuando es la
implementación CANÓNICA de una capacidad acotada que se consume de forma relativamente
autónoma (`tools/reporting/cli.py`, `tools/ds_profile/cli.py`, `tools/dsimpact/cli.py` — los
tres tienen su propio `main()`/`construir_parser()` y se invocan directamente). Cuando esa
capacidad necesita, ADEMÁS, integrarse con las superficies de gobernanza que ya vive en
`ds_guard.py` (`project`/`lifecycle`/`mlops`/`science`/`impact`), el mecanismo real usado en
el repo NO es agregar una cuarta CLI ni hacer que `ds_guard.py` invoque la CLI de paquete como
subproceso: es un subcomando DELGADO en `ds_guard.py` que importa el MÓDULO (no el `cli.py`)
del paquete y llama directamente a su función pública — exactamente `cmd_impact_scan`, que
importa `tools.dsimpact.scan` (el módulo `scan.py`, no `tools.dsimpact.cli`) y llama
`ejecutar_scan(...)` (`tools/ds_guard.py:796,817`). `dsimpact` SÍ tiene su propio
`tools/dsimpact/cli.py` (`python -m tools.dsimpact scan`, `tools/dsimpact/cli.py:1-4`) para
uso autónomo, Y `ds_guard.py` wrappea la MISMA función pública para integrarla con el resto de
la gobernanza del proyecto — los dos hosts coexisten sin ser redundantes porque exponen la
MISMA función por dos rutas de invocación distintas (autónoma vs. integrada), nunca dos
implementaciones distintas del mismo comportamiento.

`tools/datacontracts`, `tools/modelquality`, `tools/qualityevidence` NO tienen, hoy, ningún
`cli.py` propio (a diferencia de `reporting`/`ds_profile`/`dsimpact`). Las capacidades que este
Change expone (`validate`, `diff`, `evaluate`, `evidence show`, `drift`) necesitan, TODAS,
integrarse con al menos una superficie de `ds_guard.py` (`status` para evidencia, `dsimpact`
para impact preflight) — a diferencia de `reporting`, que no integra con `status`/`impact` y por
eso NUNCA fue wrappeado por `ds_guard.py` (`grep` de "report"/"reporting" en
`tools/ds_guard.py` no arroja ningún subparser, solo la palabra "report" del subcomando SDD
`session report`, sin relación). Como ninguna de las 6 capacidades de este Change tiene sentido
"autónoma" sin esa integración (ver Objetivo del roadmap: "Integrar cuando corresponda con:
`status`..., impact preflight..."), no hay justificación para pagar el costo de una CLI de
paquete nueva que la mayoría de los usos terminaría invocando solo a través de `ds_guard.py`
de todas formas.

**Verificación técnica que hace posible esta elección** (no solo preferencia de estilo):
`tools/tests/test_v07_core_neutrality.py:36-45,175-192` (`PAQUETES_SIN_DATACONTRACTS`) escanea
los DIRECTORIOS `tools/dsguard`, `tools/ds_profile`, `tools/dsimpact`, `tools/reporting`,
`tools/providers`, `tools/routing`, `tools/fallback`, `tools/harmessi_bench` — nunca
`tools/ds_guard.py` (el archivo top-level) ni `tools/harmessi/`. Los tests de neutralidad
análogos de Changes 1-3 (`test_v07_validation_neutrality.py`,
`test_v07_modelquality_neutrality.py`, `test_v07_qualityevidence_neutrality.py`) siguen el
mismo patrón. Esto confirma, con evidencia verificable (no supuesto), que `tools/ds_guard.py`
puede importar `tools.datacontracts`/`tools.modelquality`/`tools.qualityevidence` sin violar
ninguna regla de `ARCHITECTURE.md` ni romper ningún test existente — es exactamente la misma
posición estructural que ya ocupa para `tools.dsimpact` y, vía import perezoso, para
`tools.harmessi.doctor`/`tools.ds_init.legacy` (usados desde `tools/dsguard/status.py`, un caso
análogo pero DENTRO del paquete `dsguard` — ver decisión 4 para por qué ESE caso no es el
precedente aplicable a la integración de `status` de este Change).

**Alternativas descartadas**:
1. `tools/harmessi/cli.py` (`harmessi contract`/`harmessi quality`, la CLI conceptual literal
   del roadmap). Descartada: su dominio actual (`doctor`/`providers`/`routing`/`fallback`) es
   confiabilidad multi-proveedor de IA, conceptualmente distinto de contratos/calidad de datos;
   no importa `dsguard`/`ds_profile`/`dsimpact` en ningún punto de `tools/harmessi/cli.py` (leído
   completo, 490 líneas) — agregar `contract`/`quality` ahí exigiría que `harmessi/cli.py`
   empezara a importar `dsguard`/`dsimpact` (para `status`/impact preflight), una dirección de
   dependencia nueva sin ningún precedente, mientras que `ds_guard.py` YA la tiene establecida.
   Mezclar dos dominios sin relación bajo un mismo entrypoint también contradice la idea de "sin
   comandos redundantes ni confusos" del roadmap.
2. `python -m tools.datacontracts.cli` + `python -m tools.modelquality.cli` (+ posiblemente
   `tools.qualityevidence.cli`), un cuarto — en realidad un QUINTO, si se cuentan por
   separado — punto de entrada nuevo por paquete. Descartada: fragmenta una superficie
   conceptualmente unificada (`contract ...`/`quality ...`) en 2-3 launchers distintos que un
   Lead debería recordar además de `ds_guard.py` (que ya es el punto de entrada de
   `status`/`readiness`/`impact`/`lifecycle`); cada uno necesitaría, de todas formas, importar
   `tools.dsimpact` (para impact preflight) y, para `status`, terminaría reinventando el mismo
   mecanismo de extensión aditiva que ya existe en `ds_guard.py::cmd_status_unificado` — sin
   ganar nada a cambio, y violando explícitamente "sin comandos redundantes" del roadmap
   (`docs/roadmap/v0.7.md:362,365`).

### Decisión 2 — Módulo de clasificación: `tools/datacontracts/evolution.py`

Nombre y ubicación exactos, ya anticipados por Change 0
(`openspec/changes/20260922-data-contracts-core/design.md:253-264`: "probablemente en un
módulo aparte, p. ej. `tools/datacontracts/evolution.py`, a decidir en el SDD de ese Change").
Vive DENTRO de `tools/datacontracts/` (no en un paquete nuevo) porque su única entrada/salida
es `DataContract`/`CompatibilityPolicy` (tipos de ese paquete) y porque Change 0 dejó
constancia expresa de esperar esta ubicación — reabrir la discusión sin evidencia nueva sería
desperdiciar la decisión ya documentada. Es la única excepción a "Changes 0-3 son inmutables"
de este Change, prevista explícitamente por su propio autor original.

**Alternativas descartadas**:
1. `tools/ds_guard.py` (la lógica de clasificación embebida directamente en `cmd_contract_diff`).
   Descartada: mezclaría lógica de dominio determinista (clasificación de compatibilidad,
   reutilizable por cualquier otro consumidor futuro, p. ej. v0.8 Model/Data Cards) con el CLI
   (una capa que, por regla del repo, solo parsea/formatea) — mismo motivo por el que
   `validate_contract`/`evaluate_policy` viven en sus paquetes y no en `ds_guard.py`.
2. Un paquete nuevo `tools/contractevolution/` (mismo patrón dual `core.py`+módulo de
   Changes 1-3). Descartada: agregaría una CUARTA familia con vocabulario/patrón a duplicar
   (`CompatibilityPolicy`/`DataContract` ya viven en `tools.datacontracts`; separar la
   clasificación a otro paquete solo para "no tocar" `tools/datacontracts` ignora que Change 0
   ya autorizó explícitamente esta extensión ahí mismo, y multiplicaría el número de
   `test_v07_*_neutrality.py` sin beneficio real (evolution.py no tiene ninguna superficie de
   evidencia/persistencia que justifique separarlo, a diferencia de `qualityevidence`, que sí
   necesitaba independencia de ambas familias para no crear un "hub").

### Decisión 3 — Forma de `classify_contract_change`: reusa `dsguard.checks.CheckResult`

`classify_contract_change(old, new, policy=None) -> list[CheckResult]`. Ver R6-R8 de `spec.md`
para la tabla completa de categorías deterministas vs. `unknown / needs review`.

Honestidad sobre qué es determinista y qué no (exigencia explícita del roadmap, "no decidir
compatibilidad semántica cuando dependa del dominio"): lo que `DataContract` puede EVIDENCIAR
sin ambigüedad es la forma sintáctica declarada (presencia/ausencia de campos, `type_family`,
`required`, `nullable`, parámetros numéricos/de dominio de una `Constraint` EMPAREJADA por
`constraint_id` idéntico). Lo que NO puede evidenciar de forma determinista, y por eso cae
siempre en `unknown / needs review`: (a) si dos campos con nombres distintos en `old`/`new`
representan en realidad un "rename" del mismo concepto de negocio (se reportan como `removal` +
`additive compatible`/`required-field addition` SEPARADOS, nunca inferidos como un rename — el
roadmap ni siquiera pide detectar renames); (b) cualquier `BusinessRule` (por diseño, Change 0:
"solo declarables, nunca evaluadas" — clasificar su severidad sería evaluarlas); (c) el
significado de un `invariant` (texto libre); (d) si un cambio de `keys` es "compatible" o no
(depende de qué consumidor asume unicidad, información que `DataContract` no tiene); (e) si dos
`constraint_id` distintos en `old`/`new` sobre el MISMO campo son, en espíritu, "la misma
regla" — deliberadamente NO se intenta esa inferencia (ver "Alternativas descartadas" abajo).

**Alternativas descartadas**:
1. Un enum propio de 7 valores (`ContractChangeCategory`) sin relación con `CheckResult`.
   Descartada: `CompatibilityPolicy` ya declara una ACCIÓN (`block`/`warn`/`allow`) por
   categoría (`core.py:543-592`) que mapea 1:1 a `FAIL`/`WARN`/`PASS`; reusar `CheckResult`
   (permitido por la regla 7 de `ARCHITECTURE.md`, que anticipa exactamente este uso: "podrán
   importar `dsguard.checks`... en Changes posteriores") da vocabulario uniforme con
   `validate_contract`/`evaluate_policy`/`status`/reporting, evitando un vocabulario de
   resultado más (deuda de "constantes/códigos duplicados", `docs/roadmap/v0.7.md:461-463`).
2. Emparejar constraints por `(field, constraint_type)` en vez de por `constraint_id` exacto
   (heurística "más útil" cuando el autor del contrato no reusó IDs entre versiones).
   Descartada de plano: dos constraints con el mismo `(field, constraint_type)` pero
   `constraint_id` distinto podrían representar reglas NO relacionadas (p. ej. dos
   `allowed_values` sucesivas con distinto propósito de negocio); inferir que "son la misma
   regla evolucionada" es exactamente el tipo de juicio semántico que el roadmap prohíbe
   decidir sin contexto de dominio. Sin ese emparejamiento, el peor caso es reportar una
   `constraint loosening` (la vieja, ausente en `new`) + una `constraint tightening` (la
   nueva, ausente en `old`) en vez de un único finding "modificada" — es más ruidoso pero nunca
   incorrecto, cumple "nunca `PASS` por falta de evidencia" aplicado a clasificación.

### Decisión 4 — Integración con `status`: en `ds_guard.py`, nunca en `tools/dsguard/status.py`

`tools/dsguard/status.py` está DENTRO del perímetro de `tools/tests/test_v07_core_neutrality.py`
(que escanea el directorio `tools/dsguard`, ver decisión 1) y de las reglas 7-9 de
`ARCHITECTURE.md` ("`dsguard`... no importan los paquetes de v0.7", sin excepción para imports
perezosos). El patrón YA existente en `status.py` de import perezoso opcional
(`_importar_doctor`/`_importar_legacy`, `status.py:63-93`) NO es un precedente aplicable acá:
`tools.harmessi`/`tools.ds_init` no son paquetes de v0.7 y ninguna regla de `ARCHITECTURE.md`
prohíbe que `dsguard` los importe — el precedente cubre "un paquete OPCIONAL fuera del
perímetro de neutralidad de v0.7", no "un paquete de v0.7 dentro de ese perímetro". Modificar
`status.py` para agregar ESE import específico rompería la regla 7/8/9 y el test
`test_v07_core_neutrality.py` (aplicado por extensión al resto de la familia v0.7 en sus propios
tests de neutralidad, mismo patrón `PAQUETES_SIN_DATACONTRACTS`).

En cambio, `tools/ds_guard.py::cmd_status_unificado` (`tools/ds_guard.py:94-111`) ya vive FUERA
de ese perímetro (ver decisión 1) y ya es el punto donde se llama
`status.evaluar_status(repo_root)` y se decide cómo imprimirlo. Este Change agrega, ahí mismo,
una función nueva `_resumen_quality_evidence(repo_root) -> dict` que importa
`tools.qualityevidence.evidence` de forma perezosa (dentro de la función, mismo criterio que
`_importar_dsimpact`), lee `.harmessi/quality/**/manifest.json` (si existe) vía
`read_manifest` (que YA verifica hash internamente, `evidence.py:324-352`), y agrega los
resultados como una clave NUEVA (`"quality_evidence"`) al `dict` devuelto por `evaluar_status`
ANTES de imprimir — nunca reemplazando ni reordenando las 8 claves existentes. Esto satisface
"aditivo e informativo" (decisión 5 del roadmap) sin necesitar ningún cambio en
`tools/dsguard/status.py`, preservando R16 de `spec.md` (esa función es IDÉNTICA antes y
después de este Change, verificado con test directo).

Costo de esta decisión: la rama `status --change-id <id>` (SDD) no gana visibilidad de calidad
(no la necesita: es un status de progreso de un Change SDD, no de calidad de datos/modelo) y el
resumen de calidad solo aparece en `ds_guard.py status` (unificado), nunca si alguien importa
`dsguard.status.evaluar_status` directamente desde Python sin pasar por `ds_guard.py` — aceptado
explícitamente: cualquier consumidor que quiera evidencia de calidad debe pasar por el CLI o
llamar `tools.qualityevidence.evidence.read_manifest` directamente, nunca a través de
`dsguard.status`.

**Alternativas descartadas**:
1. Editar `tools/dsguard/status.py` agregando un import perezoso análogo a
   `_importar_doctor`. Descartada: viola la regla 7/8/9 de `ARCHITECTURE.md` y rompería (o
   forzaría a debilitar) `test_v07_core_neutrality.py`/sus análogos — un test de neutralidad que
   necesita una excepción ad hoc para pasar ya no está verificando lo que dice verificar.
2. Que `tools.qualityevidence` (o un paquete nuevo) exponga una función
   `resumen_para_status(repo_root)` que `ds_guard.py` importe y llame tal cual, para no tener
   ninguna lógica de agregación en `ds_guard.py`. Descartada por alcance: implica agregar una
   función nueva a `tools/qualityevidence/evidence.py` (Change 3, cerrado) o crear un módulo
   nuevo dentro de ese paquete — ninguna de las dos está entre las excepciones aditivas
   permitidas (la única excepción concedida es `tools/datacontracts/evolution.py`, ver
   `proposal.md` "Alcance"). La agregación (leer un directorio, contar por status, separar
   `technical_error`) es lo bastante simple y específica de "cómo se ve en `status`" como para
   vivir en el adapter (`ds_guard.py`), igual que `_seccion_harness`/`_bloque_mlops_tier` viven
   en `status.py` mismo (agregación de presentación, no de dominio).

### Decisión 5 — Impact preflight: composición desde `ds_guard.py`, sin tocar `dsimpact`

`dsimpact.scan.ejecutar_scan(repo_root, since, staged)` es ÍNTEGRAMENTE diff-de-Git: extrae
"changed items" (símbolos/strings) de archivos `.py`/`.ipynb` MODIFICADOS entre dos referencias,
y de archivos eliminados/renombrados (`scan.py:56-222`). Un archivo `.json` modificado (la forma
natural de persistir un `DataContract` en el repo) cae en `_procesar_otro`
(`scan.py:188-206`), que devuelve `targets_simbolos`/`targets_strings`/`targets_path` VACÍOS —
confirmado leyendo el archivo completo, no supuesto: `_construir_fuente` (`scan.py:209-221`)
solo llama a `_procesar_py`/`_procesar_notebook` para `.py`/`.ipynb`, y a
`_procesar_eliminado_o_renombrado` para deleted/renamed; cualquier otra extensión (incluido
`.json`) usa `_procesar_otro`. Por lo tanto `ejecutar_scan` tal cual NO puede, hoy, detectar que
cambió un campo de un `DataContract.json` y buscar sus consumidores — extender `dsimpact` para
que entienda contratos sería tocar un paquete de un Change de v0.4 ya cerrado, fuera del alcance
de v0.7, y el roadmap no lo pide ("usar impact preflight para identificar consumidores... sin
afirmar que están rotos", no "enseñarle a `dsimpact` sobre contratos").

En cambio, `dsimpact` expone 3 funciones PÚBLICAS reutilizables sin ningún cambio:
`git_source.listar_consumidores_candidatos(repo_root)` (universo de archivos candidatos,
`git_source.py:96-108`), `consumers_py.buscar_en_texto_python(texto, targets_simbolos,
targets_strings)` (`consumers_py.py:25`), `consumers_text.buscar_en_json`/
`buscar_en_texto_plano(texto, targets)` (`consumers_text.py:14,48`). `ds_guard.py::
cmd_contract_impact` (nuevo) construye el conjunto de `targets` manualmente a partir del
`DataContract` dado (`contract_id` + nombres de campo, ver R10 de `spec.md`) y llama a esas
4 funciones directamente sobre la lista de candidatos, reportando resultados con el mismo
vocabulario "potentially affected" que `dsimpact` ya usa (nunca "broken"/"roto") — sin
reimplementar ninguna búsqueda de texto/AST propia, solo reusando lo público.

Dirección de dependencia resultante: `tools/ds_guard.py` (adapter top-level) →
`tools.dsimpact.{git_source,consumers_py,consumers_text}` (ya establecida por `impact scan`,
sin ninguna dirección nueva) y `tools/ds_guard.py` → `tools.datacontracts.core` (nueva, pero
del MISMO tipo que ya existe hacia `tools.dsimpact`/`tools.harmessi.doctor`/`tools.ds_init.legacy`
— un adapter top-level importando módulos core, permitido y sin cobertura de ninguna regla de
neutralidad, ver decisión 1). `tools.dsimpact` NUNCA importa `tools.datacontracts` (ni al
revés): la composición ocurre enteramente en el adapter, ninguno de los dos paquetes conoce al
otro.

Se descarta deliberadamente reusar la escalada de 3 pasos de `dsimpact._evidence_type`
(`scan.py:46-53`, `PATH_REFERENCE`/`TEST_REFERENCE` según si el `changed_item` es un
path-reference target o el consumidor es un archivo de test) — esa lógica es específica de
"¿este cambio de código rompe un test/una referencia de path?", un contexto de diff de código
que no aplica a "¿este archivo menciona el id de este contrato?". `contract impact` usa
`evidence_type = "CONTRACT_REFERENCE"` uniforme (R10 de `spec.md`), documentado como
simplificación deliberada, no como una limitación descubierta tarde.

**Alternativas descartadas**:
1. Extender `dsimpact.scan._construir_fuente`/`_procesar_otro` para que un `.json` de contrato
   también produzca `targets`. Descartada: es una modificación real a un paquete de v0.4 (fuera
   de alcance de v0.7 según las reglas de arquitectura del roadmap, que solo autorizan tocar
   `tools/datacontracts` con la excepción de `evolution.py`); además acoplaría `dsimpact` (hoy
   agnóstico de cualquier dominio, solo entiende símbolos Python/AST) al vocabulario de
   `DataContract`, exactamente la dirección de dependencia que la regla 7 de `ARCHITECTURE.md`
   prohíbe (`dsimpact` no importa `tools.datacontracts`).
2. Que `contract impact` reutilice `ejecutar_scan(repo_root, since, staged)` completo y luego
   filtre sus `findings` por los que mencionen el `contract_id`. Descartada: como se demostró
   arriba, `ejecutar_scan` nunca genera NINGÚN finding a partir de un `.json` modificado (targets
   vacíos), así que filtrar su salida siempre devolvería una lista vacía para el caso de uso
   real (un contrato editado) — no es una alternativa funcional, es un enfoque que no cumple el
   requisito, documentado acá para que quede constancia de por qué se descartó con evidencia y
   no solo por preferencia de diseño.

### Decisión 6 — Tests de no-alteración de readiness/promote/status (R16-R17 de `spec.md`)

Tres pruebas, en un proyecto de prueba sintético con `tempfile` (nunca el repo real de
Harmessi ni datos reales):

1. **`evaluar_status` directo**: se llama `dsguard.status.evaluar_status(repo_root)` dos veces
   sobre el MISMO estado de fixture, una vez sin `.harmessi/quality/` y otra con un
   `.harmessi/quality/<id>/manifest.json` sintético escrito a mano (bytes fijos, sin pasar por
   `tools.qualityevidence`, para no acoplar este test a que ese paquete esté instalado) — se
   afirma `dict` idéntico en ambos casos (trivial dado que `status.py` no cambia, pero es la
   prueba que hace la garantía verificable en vez de solo argumentada).
2. **`ds_guard.py project readiness --target <t> --json`**: se invoca `cmd_project_readiness`
   (o el CLI completo vía `main(argv=[...])`, capturando stdout) sobre un fixture con
   `.harmessi/project.json`/lifecycle mínimos, una vez sin evidencia de calidad y otra con ella
   presente — se afirma stdout + exit code idénticos byte a byte.
3. **`ds_guard.py project promote <stage> --reason <r> --json`**: mismo patrón, en DOS
   directorios de fixture independientes con el mismo estado inicial (promote muta
   `.harmessi/project.json`, así que no puede reusarse el mismo directorio para las dos
   corridas) — se afirma stdout + exit code + contenido final de `.harmessi/project.json`
   idénticos entre la corrida sin y con evidencia de calidad presente.

Estas pruebas son el REQUISITO explícito del roadmap ("Tests obligatorios (Changes 4 y 5)
garantizan que readiness y promote mantienen exactamente su comportamiento previo... con y sin
evidencia de calidad presente", `docs/roadmap/v0.7.md:99-101`) y del brief de esta invocación
("DEBES leerlos para escribir tests reales que demuestren que su comportamiento... es IDÉNTICO
con y sin evidencia de calidad presente"). Se implementan en Change 4 (no diferidas a Change 5,
instrucción explícita del brief), como archivo nuevo
`tools/tests/test_v07_readiness_promote_status_no_alteration.py`.

## Target (condicional — feature_engineering, modeling)
No aplica (Change de integración/CLI, sin target ni modelado).

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica: ningún subcomando de este Change abre un dataset ni un holdout directamente (ver
`proposal.md`, "Holdout policy").

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica (sin features, sin modelado).

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
Sin aleatoriedad en este Change: `classify_contract_change` es puro y determinista (mismo par de
`DataContract` + misma `CompatibilityPolicy` → misma lista, mismo orden — orden fijo: primero
campos en el orden de `new.fields`, luego constraints en el orden de `new.constraints`, luego
`unknown / needs review` estructurales en un orden fijo declarado en el propio módulo). Los
subcomandos de CLI no generan ningún dato aleatorio; `--record-evidence` reusa
`build_manifest`/`write_manifest` tal cual (ya deterministas salvo `generated_at`, separado del
hash, por diseño de Change 3).

## Alternativas descartadas
Ver cada decisión arriba (1-6), cada una con al menos 2 alternativas descartadas y su motivo
basado en evidencia real del repo, no en preferencia de estilo.

## Riesgos
- **`quality drift` sin persistencia** (ver `proposal.md`, "Supuestos descartados"): un usuario
  que quiera comparar un `DriftEvidence` calculado ahora contra uno calculado la semana pasada
  no tiene, en este Change, ningún archivo al que apuntar — debe recalcular ambos a partir de
  los `profile.json` originales cada vez. Aceptado como límite explícito de este Change (evitar
  tocar `tools/qualityevidence/evidence.py`); si se vuelve una necesidad real, es una extensión
  aditiva de ese módulo para un Change futuro (`write_drift_evidence`/`read_drift_evidence`,
  mismo patrón que `write_manifest`/`read_manifest`), NO de este Change.
- **`contract impact` puede tener falsos negativos** (un consumidor real que referencia el
  contrato de una forma que el buscador de texto/AST de `dsimpact` no reconoce — p. ej. un
  `contract_id` construido dinámicamente con f-string) y falsos positivos (un archivo que
  contiene el string `contract_id` por coincidencia, no como referencia real). Mismo riesgo ya
  aceptado y documentado por `dsimpact scan` desde v0.4 (vocabulario "potentially affected", no
  "afectado con certeza") — este Change hereda esa limitación sin agravarla, y el `--help`/
  mensajes de salida lo dejan explícito.
- **`classify_contract_change` puede sobre-reportar `unknown / needs review`** en escenarios
  legítimos (p. ej. un autor que SIEMPRE reasigna `constraint_id` nuevos al editar una regla,
  aunque conceptualmente sea "la misma regla ajustada") — decisión 2 de esta sección lo acepta
  explícitamente: preferir ruido (dos findings separados) sobre una inferencia semántica
  incorrecta.
- **Riesgo de reabrir la decisión 5 "por comodidad de implementación"**: dado que `contract
  diff`/`quality evaluate` ya calculan una lista de `CheckResult` con status `FAIL`, es
  TÉCNICAMENTE trivial conectarlos a `project promote`. Este riesgo se neutraliza
  explícitamente con el "STOP explícito" de `tasks.md` — cualquier invocación futura que lo
  sugiera debe detenerse y consultar al Lead/usuario, nunca implementarlo por default.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
