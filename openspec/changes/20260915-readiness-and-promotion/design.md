# Diseño — 20260915-readiness-and-promotion

## Decisión metodológica/técnica

### 1. Dos módulos nuevos, uno por responsabilidad real
- **`tools/dsguard/mlops_evidence.py`**: mecanismo GENÉRICO de evidencia de artifact, parametrizado
  por `(tier, capability)`, para los tiers `production_readiness`/`operations`. No sabe nada de
  readiness ni de `project_stage`.
- **`tools/dsguard/readiness.py`**: matriz de readiness + `promote`. Consume
  `checks.py`/`lifecycle.py`/`maturity.py`/`mlops_foundations.py`/`mlops_evidence.py` sin
  modificar ninguno. Mismo criterio de "un módulo por dominio real" ya usado para
  `kdd`/`lifecycle`/`project`/`mlops`.
- Se descarta extender `mlops_foundations.py` para que además cubra `production_readiness`/
  `operations`: ese módulo se llama y se documenta explícitamente como acotado al tier
  `foundations` (`mlops_foundations.py:1-9`, docstring propio, decisión ya tomada en Change 5) —
  ensancharlo ahora sería revertir esa decisión sin necesidad real (los dos tiers nuevos tienen
  semántica distinta: evidencia de artifact explícita, no medición automática del propio repo).

### 2. `mlops_evidence.py` — hash binario duplicado localmente, no importado de `ds_profile`
`tools/ds_profile/fingerprint.py` ya calcula sha256 binario chunked, pero su propio docstring
declara la decisión de mantenerlo local a `ds_profile` para no crear una dependencia compartida
sin necesidad real. La única dependencia cruzada existente hoy es `ds_profile → dsguard`
(`ds_profile/holdout_guard.py`, que importa `dsguard.pathguard`/`dsguard.repo`) — nunca al revés.
Agregar `dsguard → ds_profile` invertiría esa dirección establecida sin necesidad real (son ~8
líneas de hashlib). Se duplica el hash binario chunked localmente en `mlops_evidence.py`, con un
comentario que documenta por qué (mismo criterio que el propio `fingerprint.py` documenta su
propia decisión de no compartir el código).

### 3. Reuso explícito de `pathguard` para validar `--artifact`, sin duplicar su lógica de gating
`mlops_evidence.py` importa `pathguard.cargar_config`/`pathguard.resolver_ruta_relativa` (ambas
públicas) y `repo.path_matches_any`, y replica LOCALMENTE (siguiendo el mismo precedente que
`ds_profile/holdout_guard.py` ya estableció) el matching case-insensitive de holdouts/secretos y
la vigencia de excepciones de lectura — en vez de importar los símbolos privados
(`pathguard._matchea_patrones`/`pathguard._excepcion_vigente`) de otro módulo del mismo paquete.
Mantiene el mismo criterio fail-closed: `guardrails.json` corrupto → rechazado (nunca se asume
`ConfigGuardrails()` por defecto ante un error real de parseo, a diferencia de "ausente" que sí
usa el default seguro).

### 4. Forma de la evidencia y dedup
`{"tipo": "artifact_evidence", "path": <relativa-posix>, "sha256": <hex>, "reason": <str>, "utc":
<str>}`, agregada a `mlops.<tier>.<capability>.evidencia`. Dedup: antes de agregar, se recorre la
lista existente de esa capability buscando una entrada `tipo=="artifact_evidence"` con el MISMO
`path` Y el MISMO `sha256` — si existe, no se agrega nada nuevo (`agregado=False,
duplicado=True`, se devuelve la entrada existente). Un mismo `path` con hash distinto (el archivo
cambió) SÍ agrega una entrada nueva — el hash es parte de la identidad de la evidencia, no la
ruta sola (una ruta reusada con contenido distinto es, por definición, evidencia distinta).

### 5. `evidencia_valida` vive en `mlops_evidence.py`, no en `readiness.py`
Co-localizado con el lado de escritura: quien escribe la forma del registro es quien mejor sabe
validarla (evita que `readiness.py` conozca el schema interno de `artifact_evidence`).
`readiness.py` solo llama `mlops_evidence.evidencia_valida(repo_root, tier, capability) -> (bool,
detalle)` y usa el booleano para construir su propio `CheckResult` con código de readiness.

### 6. Reinterpretación de severidad — nunca toca `mlops_foundations.py`
`readiness.py` llama `mlops_foundations.evaluar_foundations(repo_root)` (que ya recorre
`reproducibilidad`/`versionado`/`lineage`/`artifacts`) y envuelve cada resultado en un
`CheckResult` NUEVO con código `READINESS-FOUNDATIONS-<CAP>`:
- `reproducibilidad`/`versionado`/`artifacts`: `status==PASS` → `PASS` preservado; cualquier otro
  status (`WARN`/`FAIL`/`N/A`) → `FAIL` (mensaje original + nota de que WARN/N-A se trata como
  FAIL en este contexto de readiness).
- `lineage`: status preservado TAL CUAL (nunca convertido a `FAIL`) — como hoy solo puede dar
  `WARN`/`N/A`, esto los deja naturalmente no bloqueantes vía `checks.hay_bloqueo` (que solo mira
  `FAIL`), sin necesidad de un caso especial en la lógica de bloqueo.
Esto satisface el principio del usuario (R16/§17 del brief): "foundations PASS no implica
production ready" y al revés, "foundations WARN en este contexto SÍ bloquea production_candidate"
— sin mutar el significado propio de `mlops_foundations.py` para ningún otro consumidor (p. ej.
`mlops status` sigue mostrando WARN, no FAIL, fuera de este contexto de readiness).

### 7. Manejo de prerrequisitos ausentes (sin short-circuit)
`evaluar_readiness` intenta leer `project.json`/`lifecycle/state.json` UNA vez al principio de la
función del target correspondiente. Si falta o está corrupto, emite el `CheckResult` de ese
prerrequisito (`FAIL` normal si falta, `technical_error` si está corrupto — mismo patrón
"con-dato" que `mlops_foundations.evaluar_foundations`/`doctor._ejecutar_check_con_dato`) y
CONTINÚA evaluando el resto de la matriz completa para ese target: cada gate que dependería de
leer ese archivo se construye igual, como `CheckResult(FAIL, código, "no se pudo evaluar: <qué
prerrequisito falta>")`, en vez de omitirse. Esto cumple "reportar todos los checks, nunca
short-circuit" (R12/§13 del brief) manteniendo el roster de códigos siempre completo y
predecible (mismo número de resultados sin importar el estado del repo), lo que además hace los
tests más simples de escribir (longitud de la lista de resultados fija por target).

### 8. `promote` — orquestación fina, mutación acotada a `maturity.py`
`promote(repo_root, target, reason)`:
1. Valida `reason` no vacío y `target` en el vocabulario válido (`ValueError`/`PromotionError`
   propio, sin tocar `maturity.py`).
2. Lee `project_stage` actual vía `maturity.leer_estado` (si `project.json` no existe, propaga
   `FileNotFoundError` — mismo criterio que el resto de `maturity.py`, "correr project init
   primero", nunca bootstrap implícito).
3. Calcula el único próximo stage secuencial válido desde el actual (tabla fija
   `{"discovery":"experiment", "experiment":"production_candidate",
   "production_candidate":"production"}`); si `target` no coincide exactamente → error de dominio
   (`PromotionError`), sin leer readiness siquiera (más barato y más claro: un salto/downgrade no
   necesita evaluar 15 gates para ser rechazado).
4. Corre `evaluar_readiness(repo_root, target)` (solo lectura). Si `checks.hay_bloqueo(...)` →
   devuelve `{"promovido": False, "resultados": ..., "project_stage": actual}`, SIN escribir nada.
5. Si pasa: relee el estado de madurez (mismo objeto ya leído en el paso 2, no una segunda
   lectura — evita una ventana de re-lectura innecesaria en un proceso de una sola invocación de
   CLI, no concurrente) y aplica la mutación IN-MEMORY (`project_stage = target`,
   `stage_history.append({...via:"promote"...})`), después `maturity.escribir_estado(repo_root,
   estado)` — la MISMA función atómica que ya usa `calibrar`/`set_risk`, sin reimplementar
   escritura.
`promote` nunca llama a `lifecycle.escribir_estado` ni a `mlops_evidence`/`decision` — su única
escritura posible es vía `maturity.escribir_estado`.

### 9. `checks.py` no se modifica ni se acopla a readiness
`readiness.py` es quien conoce `project_stage`/CRISP-DM/MLOps tiers/evidencia; el engine sigue
siendo neutral (mismo principio ya aplicado en Change 5 punto 8 de su propio `design.md`).

### 10. CLI: subgrupo nuevo `evidence` bajo `mlops`, y `readiness`/`promote` bajo `project`
`project readiness`/`project promote` viven bajo el grupo `project` (eje de madurez/gobernanza,
igual que `init`/`calibrate`/`set-risk`/`status`) — no bajo un grupo nuevo. `mlops evidence add`
vive bajo el grupo `mlops` ya existente (`mlops status`/`mlops record` de Change 5), como un
subgrupo anidado (`mlops evidence add`), reflejando que es sobre las mismas capacidades MLOps del
catálogo, con un mecanismo de persistencia distinto al de `foundations`.

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica — este change no toca datos de un proyecto real; define gates sobre metadata de
madurez/evidencia (existencia de archivos, hashes, estados de fase), no sobre contenido de ningún
dataset.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica — sin aleatoriedad en el código de este change.

## Alternativas descartadas
- Ensanchar `mlops_foundations.py` para cubrir los 3 tiers — rechazada, ver punto 1: revertiría
  una decisión ya tomada en Change 5 sin necesidad real; los tiers nuevos tienen semántica de
  evidencia explícita, no de medición automática.
- Importar `ds_profile.fingerprint.calcular_fingerprint` desde `dsguard` — rechazada, ver punto 2:
  invertiría la única dirección de dependencia cruzada existente (`ds_profile → dsguard`) sin
  necesidad real, por ~8 líneas de hashlib.
- Poner `evidencia_valida` en `readiness.py` en vez de `mlops_evidence.py` — rechazada, ver punto
  5: forzaría a `readiness.py` a conocer el schema interno de `artifact_evidence`, acoplamiento
  innecesario.
- Short-circuit de la matriz de readiness cuando falta un prerrequisito (project.json/lifecycle)
  — rechazada, ver punto 7: el brief pide explícitamente reportar todos los checks siempre, y un
  roster de longitud variable complica los tests sin necesidad.
- Dedup de evidencia solo por `path` (ignorando el hash) — rechazada: perdería la capacidad de
  registrar una segunda evidencia legítima cuando el mismo archivo cambió de contenido con el
  tiempo (p. ej. se re-generó el mismo artifact con una versión distinta).
- Cambiar `schema_version` de `lifecycle.py` para la nueva forma de evidencia — rechazada, ver
  `proposal.md § Evidencia`: confirmado por lectura directa que `validar_estructura` nunca
  inspecciona las claves internas de `evidencia[]`, no hace falta ningún cambio de schema (el
  trigger de STOP del usuario para esto no aplica).
- Registrar la promoción también en el decision ledger — rechazada explícitamente por el usuario
  como default de este change (sería un trigger de STOP, no una decisión unilateral).
- `promote` re-leyendo `project.json` dos veces (una para calcular el próximo stage válido, otra
  justo antes de escribir) — rechazada, ver punto 8: una sola invocación de CLI no tiene
  concurrencia real que justifique una doble lectura defensiva; se reusa el mismo objeto en
  memoria, coherente con que la escritura sigue siendo atómica a nivel de archivo
  (`escribir_texto_atomico`).

## Riesgos
- La reinterpretación WARN/FAIL/N-A→FAIL de foundations para `production_candidate` (punto 6)
  introduce un segundo lugar que "sabe" sobre las 4 capabilities de foundations, además de
  `mlops_foundations.py` — mitigado con una tabla explícita `{código_foundations:
  código_readiness}` y un único punto de reinterpretación (`_reinterpretar_foundation`), nunca
  lógica duplicada de qué constituye reproducibilidad/versionado/artifacts.
- El roster fijo de `CheckResult` por target (punto 7) puede parecer verboso cuando falta un
  prerrequisito (p. ej. 15 `FAIL` en vez de 1) — aceptado conscientemente: el brief pide
  explícitamente "reportar todos los checks", y un mensaje "no se pudo evaluar: lifecycle no
  disponible" en cada uno sigue siendo honesto y accionable (apunta al mismo prerrequisito raíz).
- `mlops_evidence.py` duplica ~10 líneas de sha256 binario y una versión reducida del matching de
  pathguard — aceptado, ver puntos 2/3: mantiene la dirección de dependencias existente y sigue
  el mismo precedente ya usado por `ds_profile/holdout_guard.py` para el mismo tipo de
  duplicación deliberada.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
Ver `proposal.md § Aprobación`.
