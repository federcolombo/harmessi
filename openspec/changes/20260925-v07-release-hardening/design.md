# Diseño — 20260925-v07-release-hardening

## Decisión metodológica/técnica

Reutilizar el patrón de hardening de `20260918-v0-6-release-hardening`, sin inventar un proceso
nuevo, con orden obligatorio:

1. Redactar los 4 artefactos SDD (esta invocación) — sin tocar `.ds_init/control.json`.
2. Implementar los 2 smokes/fixtures nuevos identificados abajo (decisión 1), en
   `tools/tests/test_v07_release_hardening_smoke.py`. Sin código de producción.
3. Lead: correr `pytest tools -q` completo (R1), los smokes nuevos y todos los ya existentes
   citados en `spec.md` R2-R15, los scratch installs frescos (R16), backward compatibility contra
   `v0.6.0` (R17), el sweep de privacidad (R18), portabilidad (R19), paridad de manifest (R20) y
   `harmessi doctor` (R21). Recolecta evidencia real, no instala dependencias nuevas.
4. `data-science-reviewer` (read-only): revisión transversal del conjunto de los 5 Changes de
   v0.7, sin repetir revisiones individuales ya cerradas.
5. `python-data-engineer`: aplica solo correcciones de hardening acotadas a las rutas autorizadas,
   si la evidencia o el reviewer hallan defectos; re-correr lo afectado.
6. `python-data-engineer`: cierra con `verification.md` (evidencia real, hallazgos del reviewer,
   limitaciones, resultado final `READY FOR v0.7.0 RELEASE` o `NOT READY FOR v0.7.0 RELEASE` con
   razones) y actualiza `docs/roadmap/v0.7.md` (`[x] Change 5` solo si corresponde).

Alineación de versión canónica (`tools/ds_init/version.py`, `CITATION.cff`) y regeneración de
`.ds_init/control.json`: si el veredicto es `READY`, son tareas de una invocación separada
posterior dentro de este mismo Change (mismo patrón que v0.6, invocación 2 de
`openspec/changes/20260918-v0-6-release-hardening/tasks.md:9-11` y regeneración ÚLTIMA en la
invocación 6 de ese mismo `tasks.md`), explícitamente fuera de esta invocación 1 (redacción de
SDD) y sujetas a instrucción separada del Lead/usuario. `control.json` no se toca en ningún punto
de este documento.

Sin features nuevas. Sin push, merge a `main`, tag, GitHub Release ni borrado de `v0.7-dev`:
parada humana final.

### Decisión 1 — Smokes/fixtures nuevos que hacen falta

Se identificaron exactamente **2** necesidades nuevas, ambas en un único archivo nuevo:
`tools/tests/test_v07_release_hardening_smoke.py`.

1. **Smoke de "reporting consumption"** (spec R12): no existe hoy ningún test que instancie
   `reporting.evidence.describe_source` sobre un artefacto de `tools.qualityevidence` (confirmado
   por glob: ninguno de los 10 archivos de `tools/reporting/tests/` menciona `qualityevidence`,
   `datacontracts` ni `modelquality`). El smoke construye un `QualityEvidenceManifest` sintético
   (Change 3), lo persiste con `write_manifest` bajo un repo git temporal, y llama
   `reporting.evidence.describe_source(repo_root, ruta_manifest)`, verificando: (a) el hash
   reportado coincide con el hash real del archivo (round-trip), y (b) por inspección de imports a
   nivel de módulo, ni `tools/reporting/evidence.py` importa `tools.qualityevidence` ni
   `tools/qualityevidence/{core,evidence}.py` importa `tools.reporting` — consistente con
   `ARCHITECTURE.md:192-194` ("la integración con Reporting v0.6 ocurre exclusivamente porque
   `reporting.evidence.describe_source` puede hashear cualquier archivo del repo ... sin que
   ninguno de los dos paquetes importe al otro").
2. **Smoke de neutralidad agregada de las 3 familias nuevas de v0.7**: los 5 tests de neutralidad
   existentes (`test_v07_core_neutrality.py`, `test_v07_validation_neutrality.py`,
   `test_v07_modelquality_neutrality.py`, `test_v07_qualityevidence_neutrality.py`,
   `test_v07_evolution_neutrality.py`) verifican cada familia por separado contra el universo de
   paquetes preexistentes; ninguno verifica las 3 familias juntas (`tools.datacontracts`,
   `tools.modelquality`, `tools.qualityevidence`) contra el mismo universo en una sola pasada, que
   es justamente el enunciado de la regla 7-9 de `ARCHITECTURE.md`. Se agrega un test simple (grep
   estructurado de imports, mismo criterio que los tests de neutralidad existentes, sin reinventar
   el mecanismo) que confirma cero imports de las 3 familias nuevas desde
   `dsguard`/`ds_profile`/`dsimpact`/`reporting`/`providers`/`routing`/`fallback`/
   `harmessi_bench`.

**Descartado explícitamente**: un smoke de "fresh scratch install" como test de pytest persistido.
A diferencia de R12, el precedente de v0.6 (`openspec/changes/20260918-v0-6-release-hardening/
verification.md:44-48`, R6) ejecutó los scratch installs como procedimiento del Lead en la
invocación 3 (`python -m tools.ds_init` directo sobre un repo temporal del scratchpad), no como un
archivo de test permanente en el repo — un test de pytest que invoque `ds_init` de punta a punta ya
existe y corre en `tools/ds_init/tests/test_integracion_instalacion.py`; duplicar ese mecanismo en
un test nuevo de este Change agregaría un segundo instalador de prueba sin necesidad. R16 se
verifica como corrida del Lead, documentada con evidencia real en `verification.md`, igual que en
v0.6.

**Descartado explícitamente**: un fixture nuevo para "impact integration smoke" (spec R13). El
gate lo pide como ítem a confirmar-o-agregar; la lectura de
`tools/tests/test_ds_guard_contract_quality_cli.py:234-257` confirma que `TestContractImpact` ya
cubre el caso concreto (consumidor potencialmente afectado por un cambio de contrato, vocabulario
"potentially affected", ambos exit codes) con 2 tests explícitos. Agregar un tercer test
redundante no aportaría cobertura nueva; se documenta la decisión de "confirmar suficiencia" en vez
de "agregar", con la cita exacta como evidencia.

### Decisión 2 — Formato del veredicto final

`verification.md` de este Change sigue exactamente la estructura de
`openspec/changes/20260918-v0-6-release-hardening/verification.md`: una sección "Evidencia
obtenida" que **cita** (no repite en extenso) cada uno de los 5 `verification.md` de Changes 0-4 —
un párrafo por Change con sus números reales ya registrados (suite propia, regresión en ese
momento, hallazgos del reviewer, ciclos de remediación usados) — seguida de la evidencia NUEVA de
este Change (R1, R12, R16-R21 de `spec.md`), una sección "Diferencias contra la spec", una
"Limitaciones" que reafirma las ya declaradas por Changes anteriores sin repetirlas palabra por
palabra (solo las que sigan vigentes al cierre), "Pendientes derivados" (deuda para v0.8+, ver
decisión 3), y termina con el veredicto literal `READY FOR v0.7.0 RELEASE` o
`NOT READY FOR v0.7.0 RELEASE` con razones concretas, mismo patrón que el veredicto (inicialmente
`NOT READY`, luego superado por addendum) de v0.6.

A diferencia de v0.6 (que tuvo un único motivo de `NOT READY` — el bundle de Plotly — resuelto por
addendum), v0.7 no tiene hoy ninguna dependencia externa condicionante conocida (decisión 8 del
roadmap: "sin dependencias nuevas"); si la regresión completa (R1) o el reviewer transversal (R22)
encuentran un defecto real, el veredicto debe nombrarlo como razón concreta en vez de forzar
`READY`.

### Decisión 3 — Ajustes menores no-funcionales: documentación diferida, no en alcance

La deuda concreta identificada (README sin documentar `ds_guard.py contract`/`quality`, igual que
la deuda ya declarada en v0.6 para `python -m tools.reporting`) **se documenta como deuda diferida
para v0.8/v0.9**, siguiendo el patrón ya escrito en `docs/roadmap/v0.7.md` ("Deuda que v0.7 no
debe crear" enumera clases de deuda que SÍ deben evitarse desde el inicio — constantes duplicadas,
estilo de imports dual, textos hardcodeados — pero documentar comandos nuevos en el README no es
una de esas clases, y el precedente de v0.6 la difirió explícitamente). Razón: este Change es
hardening puro (verificación + corrección de defectos), no alcance para escribir documentación de
usuario nueva; agregarla sin que la pida el gate sería expansión de scope no autorizada por el
roadmap. Si el reviewer transversal (R22) señala esta ausencia como hallazgo, se evalúa igual que
cualquier otro hallazgo no bloqueante: aceptar y diferir, o aplicar como corrección de hardening
acotada si el Lead decide que es de bajo riesgo — pero no se agrega preventivamente en esta
redacción de SDD.

## Target (condicional)

No aplica.

## Features permitidas/prohibidas (condicional)

No aplica. Está prohibido agregar features; el diff solo puede contener los 4 artefactos SDD, el
smoke nuevo de `tools/tests/test_v07_release_hardening_smoke.py`, `verification.md`, el estado de
`docs/roadmap/v0.7.md` y correcciones de hardening acotadas.

## Estrategia de split/validación (condicional)

No aplica. Los smokes nuevos (R12, neutralidad agregada) usan fixtures 100% sintéticos en
directorios temporales; ningún holdout real se abre.

## Leakage risks (condicional)

No aplica como leakage metodológico. El riesgo análogo es filtrar rutas/nombres privados en
artefactos versionados, cubierto por R18 (sweep de privacidad). El riesgo de contaminación entre
familias (`datacontracts`/`modelquality`/`qualityevidence` importando `dsguard`/`ds_profile`/
`dsimpact`/`reporting` en la dirección prohibida) se cubre con el smoke de neutralidad agregada de
la decisión 1.

## Reproducibilidad (opcional)

Sin aleatoriedad nueva. El smoke de R12 usa un `QualityEvidenceManifest` sintético con
`generated_at` fijo (mismo patrón que los tests de `content_sha256()` ya existentes en Change 3);
determinismo del hash verificado por round-trip único (no requiere 2 corridas: el hash se compara
contra `hashlib.sha256` calculado sobre el mismo archivo dentro del mismo test).

## Alternativas descartadas

1. **Agregar un tercer test de impact preflight**: descartado (decisión 1) — los 2 tests
   existentes de `TestContractImpact` ya cubren el caso; se confirma, no se duplica.
2. **Persistir el scratch install como test de pytest en el repo**: descartado (decisión 1) — ya
   existe `tools/ds_init/tests/test_integracion_instalacion.py`; R16 se ejecuta como corrida del
   Lead, no como archivo nuevo, mismo criterio que R6 del hardening de v0.6.
3. **Documentar los subcomandos `contract`/`quality` en el README dentro de este Change**:
   descartado (decisión 3) — expansión de scope no pedida por el gate; queda como deuda diferida
   para v0.8/v0.9, mismo patrón que la deuda ya declarada en v0.6.
4. **Regenerar `.ds_init/control.json` en esta invocación 1**: descartado — instrucción explícita
   del usuario de no tocarlo en esta redacción de SDD; su regeneración (si el veredicto es
   `READY`) es una invocación separada posterior, después de cualquier corrección de hardening
   (mismo criterio de "regenerar ÚLTIMO" que v0.4-v0.6).
5. **Instalar una dependencia nueva para verificar algún ítem del gate**: descartado — a
   diferencia de v0.6 (Plotly), no hay ningún ítem del gate de v0.7 que dependa de una librería
   externa (decisión 8 del roadmap: "sin dependencias nuevas"); si apareciera una necesidad real
   durante la verificación, el Lead debe presentar los 5 puntos al usuario antes de cualquier `pip
   install` (mismo procedimiento que v0.6) y eso sería motivo de parada, no de decisión autónoma.

## Riesgos

- **Regresión completa nunca corrida de punta a punta sobre v0.7**: cada Change corrió su propio
  alcance; es posible que la combinación de las 3 familias nuevas con `tools/reporting` o
  `tools/dsimpact` revele una interacción no vista (p. ej. un import perezoso que falle solo bajo
  cierto orden de colección de tests). Mitigación: R1 corre `pytest tools -q` completo, no por
  paquete.
- **Reviewer transversal de la misma familia de modelo**: mismo riesgo ya declarado en v0.6; no
  hay una segunda familia real disponible.
- **Backward compatibility contra `v0.6.0` con un diff grande** (5 Changes acumulados, incluidas
  ~683 líneas nuevas en `tools/ds_guard.py`): riesgo de que el `git diff --stat` sea difícil de
  auditar línea por línea; mitigación: apoyarse en los 5 `verification.md` ya cerrados, que ya
  documentaron Change a Change qué tocaron y qué confirmaron sin diff (en particular,
  `tools/reporting/**` confirmado sin diff desde Change 3 en adelante).
- **Ausencia de ancla externa del hash del manifest** y **solo Windows**: mismas limitaciones ya
  declaradas en v0.6, sin resolver en v0.7 (deuda heredada, no nueva de este Change).
- **Correcciones tardías que invaliden evidencia previa**: se mitiga re-corriendo R1 y los smokes
  afectados tras cualquier fix de hardening, antes de emitir el veredicto final.

## Aprobación humana

El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único por
cambio y vive en la sección "Aprobación" de `proposal.md` — no se duplica acá.
