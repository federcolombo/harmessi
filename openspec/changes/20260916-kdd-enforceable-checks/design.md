# Design — 20260916-kdd-enforceable-checks

## 1. Por qué un archivo de policy nuevo

Se auditó `checks.py`, `lifecycle.py`, `maturity.py`, `readiness.py`, `mlops_foundations.py`,
`mlops_evidence.py`, `pathguard.py`, `ds_profile/*`, `eda.md`/`templates/spec.md`. Cutoff/baseline/
target ya se **declaran** hoy, pero solo como prosa libre en `spec.md` de cada change
("## Cutoff / information boundary", "## Baseline") — no son parseables de forma determinista sin
heurística sobre texto libre, lo cual está explícitamente prohibido ("no inferir cutoff/target/
baseline por heurística silenciosa"). No existe ninguna fuente estructurada reutilizable para estos
campos. Por eso se usa la pre-aprobación del brief para `.harmessi/scientific-policy.json`: un único
archivo declarativo nuevo, opcional, sin resultados derivados.

## 2. Por qué no un template instalado de scientific-policy.json

`.harmessi/` ya está en `EXCLUSIONES_PERMANENTES` de `manifest.py` — ningún archivo bajo ese
directorio se instala nunca (mismo criterio que `project.json`, que se crea vía `project init`, no
vía scaffold). Declarar aquí un template supondría además el riesgo de "generar reglas falsas" que el
brief prohíbe explícitamente. La política se autoría a mano (mismo patrón editorial que
`guardrails.json`), cuando el Lead/usuario la necesite.

## 3. Por qué el leakage temporal no duplica el check de cutoff

`SCI-CUTOFF` ya responde exactamente la pregunta "¿los datos usados exceden el cutoff declarado?".
Un check `SCI-LEAKAGE-TEMPORAL` sería una reimplementación del mismo parseo/comparación de fechas con
otro código — el brief pide expresamente reutilizar, no duplicar. `evaluar_scientific_checks` incluye
`SCI-CUTOFF` una sola vez en la lista compuesta; cuando `temporal.declared = true`, ese resultado
representa tanto "cutoff" como "leakage temporal verificable" al mismo tiempo.

## 4. Por qué dos checks de holdout, no uno

`SCI-HOLDOUT-PROTECTION` verifica una garantía **estructural** (¿el holdout declarado en la policy
también está protegido físicamente por `pathguard` vía `guardrails.json → holdouts`? -- si no, hay
una inconsistencia detectable de forma determinista). `SCI-HOLDOUT-USAGE` verifica **declaraciones**
de uso metodológico (operaciones prohibidas). Son preguntas distintas con distintos requisitos de
evidencia -- separarlas evita que un FAIL de una tape la lectura de la otra.

## 5. Por qué el binario nunca lee el contenido del holdout

Ninguno de los dos checks de holdout abre el archivo/directorio holdout declarado -- solo consultan
`guardrails.json` (patrones) y la policy (declaraciones de uso). Esto es deliberado: "no intentes
descubrir intención leyendo código arbitrario con IA", y desde el binario tampoco se lee el dataset
protegido para inferir uso -- solo se puede verificar lo que está **declarado**. Ausencia de
declaración -> WARN/N-A, nunca PASS por omisión (fail-closed en el sentido de "nunca inventa
confianza").

## 6. Reuso de pathguard sin importar símbolos privados

`scientific_validity.py` vive en `tools/dsguard/`, junto a `pathguard.py` -- mismo criterio que
`mlops_evidence.py` (ya en ese paquete): importa las funciones públicas de `pathguard`
(`cargar_config`, `resolver_ruta_relativa`) y `repo.path_matches_any`, y replica localmente
`_matchea_patrones`/`_excepcion_vigente` (privadas) en una función `_resolver_ruta_lectura` -- tercera
instancia de este patrón ya establecido dos veces en el repo (`ds_profile/holdout_guard.py`,
`dsguard/mlops_evidence.py`), documentado en sus propios docstrings como la forma deliberada de evitar
depender de símbolos privados de otro módulo.

## 7. Por qué el hash de baseline es opcional

`evidence_sha256` es opcional en la policy: sin él, el check solo confirma existencia + no-vacío
(suficiente para "existe evidencia real, no un archivo vacío/template"). Con él, agrega protección de
staleness (mismo concepto que `mlops_evidence.evidencia_valida`, sin reusar ese mecanismo directamente
porque está parametrizado por `(tier, capability)` de `lifecycle.MLOPS_CAPACIDADES`, y "baseline" no
es una capability de ese catálogo -- forzarlo ahí sería deformar un mecanismo existente para un caso
que no encaja, lo cual el brief prohíbe explícitamente ("si encaja sin deformarlo").

## 8. Por qué comparar fechas como UTC-naive

`ds_profile` (`column_stats.FORMATOS_FECHA`) nunca interpreta offset de timezone -- todos sus
`datetime` son naive. Para comparar contra `cutoff_utc` (parseado con `dsguard.core.parsear_utc`,
tz-aware) sin introducir una conversión de timezone que `ds_profile` mismo no hace, se compara
`cutoff.replace(tzinfo=None)` contra la fecha naive del profile. Documentado explícitamente como
limitación conocida (no soporta datasets con offsets de timezone reales) -- no se agrega parsing de
timezone nuevo que `ds_profile` no tenga, para no crear dos fuentes de verdad sobre cómo se interpreta
una fecha.

## 9. No wiring a readiness/promotion

Deliberado (brief, sección READINESS): estos checks son evidencia de calidad científica, un concepto
relacionado pero distinto de madurez de lifecycle/gates de promoción. Se registra como decisión/deuda
para un change futuro de v0.4 si corresponde incorporarlos.

## 10. Riesgos aceptados / límites conocidos

- La policy es autodeclarada: un `usage_declarations` que miente ("used: false" siendo falso) no es
  detectable de forma determinista -- documentado en `methodology.md` para que el Lead nunca lo trate
  como garantía absoluta, solo como señal.
- `SCI-CUTOFF` depende de que `ds_profile` se haya corrido sobre el dataset correcto -- un
  `profile_path` que apunta a un profile viejo/de otro dataset no se detecta (fuera de alcance: no se
  verifica que el profile corresponda al dataset "correcto" más allá de que exista y sea legible).
- `SCI-HOLDOUT-PROTECTION` confirma que *algún* patrón de holdout está declarado en
  `guardrails.json`, no que sea específicamente el holdout relevante del corte/dataset en curso -- la
  policy no tiene un campo de ruta de holdout propio para esa comparación (deliberado, ver §2 sobre
  minimalismo del schema).
