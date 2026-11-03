# Diseño — 20260915-unified-status-surface

## Decisión metodológica/técnica

### 1. `status` reusa el subcomando existente, no crea uno paralelo
`ds_guard.py` ya tiene `status --change-id <id>` (SDD). El brief pide literalmente `ds_guard
status`. En vez de renombrar el existente (rompería backward compatibility, usado activamente por
todo el flujo SDD del propio proyecto) o inventar un nombre distinto (contradice el brief), se
hace `--change-id` opcional en el parser existente y se bifurca `cmd_status` según su presencia.
Invariante dura verificada: CUALQUIER invocación que pase `--change-id` (100% de las existentes,
ya que era `required=True`) sigue produciendo exactamente el mismo resultado.

### 2. `tools/dsguard/status.py` no depende obligatoriamente de nada fuera de `tools/dsguard`
Confirmado por auditoría: `tools/harmessi/doctor.py` y todo `tools/ds_init/` NUNCA se instalan en
un proyecto destino (ver `proposal.md § Evidencia`). Por lo tanto `status.py` solo puede depender
INCONDICIONALMENTE de módulos que SÍ viajan con cualquier instalación (`tools/dsguard/*` — todos,
per Change 7, siempre CORE_DISCOVERY). Las dos piezas que viven fuera de `tools/dsguard`
(`doctor.ejecutar` para integridad del harness, `legacy.inferir_installation_stage` para
inferencia legacy) se consumen EXCLUSIVAMENTE vía import perezoso dentro de un `try/except
ImportError` (más un `try/except Exception` alrededor de la llamada real, no solo del import, por
si la importación en sí es parcial/exitosa pero la ejecución falla por otra razón) — nunca un
`from tools.harmessi import doctor` a nivel de módulo de `status.py`. Esto preserva el principio
original de `ds_guard.py` ("no importa nada fuera de tools/dsguard") para el camino OBLIGATORIO,
y limita el alcance de la extensión al camino OPCIONAL, exactamente donde el brief permite
"extracción/reuso mínimo compatible" en vez de una dependencia dura.

### 3. `installation_stage` declarado se lee sin depender de `tools.ds_init`
La mayoría de los proyectos reales (cualquiera sincronizado vía Change 7) tiene
`installation_stage` EXPLÍCITO en su propio `.ds_init/control.json` — leerlo es un `json.load()`
plano, sin ningún import de `tools.ds_init`. Solo el caso legacy (control.json sin esa clave)
necesita el import perezoso opcional descrito en el punto 2. Esto significa que, en la práctica,
la sección `installation`/`alignment` funciona completa y sin degradación en el caso común
(proyecto instalado post-Change-7), y solo se degrada (`origen="desconocido"`) para el caso
legacy corriendo fuera del checkout fuente — un caso ya reconocido como de cobertura reducida
desde el propio Change 7 (`design.md` de ese change, punto 6: "solo dos estados distinguibles con
confianza").

### 4. `harness` (integridad) nunca copia lógica de Doctor
Se llama `doctor.ejecutar(repo_root)` (función pública ya existente, `(list[ResultadoCheck],
exit_code)`) tal cual, vía el import perezoso del punto 2, y se REDUCE su salida a un resumen
(conteos por nivel + hasta K mensajes WARN/ERROR más relevantes) — nunca se reimplementan sus
~40 checks individuales. Cuando no está disponible, se muestra un mensaje honesto, nunca una
aproximación falsa (p. ej. NUNCA se infiere integridad a partir de archivos parciales presentes
en el destino instalado — eso sería inventar un segundo motor de integridad, prohibido).

### 5. `next_target`/`readiness` son cálculo puro + reuso directo, sin reinterpretación nueva
`next_target(project_stage)` es una función pura de una línea (tabla de sucesión, mismo
vocabulario que `readiness._SECUENCIA` de Change 6, pero SIN importar ese símbolo privado —
`status.py` define su propia tabla pública mínima, ya que es información puramente derivada del
vocabulario `PROJECT_STAGES`, no lógica de promoción). La evaluación real de gates es SIEMPRE
`readiness.evaluar_readiness(repo_root, next_target)` sin ninguna capa intermedia.

### 6. Proporcionalidad por stage vive en `status.py`, nunca en `readiness.py`
Cuando `project_stage=discovery`, `mlops.production_readiness`/`operations` se muestran
colapsados en el output COMPACTO — esto es una decisión de PRESENTACIÓN de `status.py`
(qué tan detallado mostrar el inventario de capabilities), nunca una decisión de qué evalúa
`readiness.evaluar_readiness` (que sigue evaluando el target pedido siempre completo, sin
importar el stage actual — Change 6 no se toca). `--verbose` desactiva ese colapso a pedido
explícito del usuario.

### 7. `production_readiness`/`operations` en `mlops.*` vs. en `readiness.blocking`: dos vistas
del mismo dato, sin duplicar lógica
`mlops.production_readiness`/`operations` (inventario de capabilities, siempre presente aunque
colapsado) y `readiness.blocking` (qué bloquea específicamente el `next_target`) ambos llaman
`mlops_evidence.evidencia_valida` — el primero directamente por capability (para el inventario),
el segundo indirectamente vía `readiness.evaluar_readiness` (que ya lo hace internamente para
`production_candidate`/`production`). Es la MISMA función llamada desde dos puntos con propósitos
de presentación distintos (inventario permanente vs. gate del próximo target) — no hay
reimplementación, solo dos invocaciones del mismo evaluador ya existente.

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica.

## Alternativas descartadas
- Renombrar el `status` existente (SDD) para liberar el nombre — rechazada: rompería backward
  compatibility de un comando usado activamente en todo el flujo SDD del proyecto.
- Importar `tools.harmessi.doctor`/`tools.ds_init.legacy` incondicionalmente desde `status.py` —
  rechazada, ver punto 2: rompería `ModuleNotFoundError` en el caso más común (proyecto
  instalado), justo lo que el brief pide evitar explícitamente (§24).
- Duplicar la lógica de `_check_archivos_administrados`/`_check_hashes_drift` de Doctor dentro de
  `tools/dsguard/status.py` para que funcione sin import perezoso — rechazada: esa lógica
  requiere el catálogo del manifiesto (`tools/ds_init/manifest.py`), que TAMPOCO se instala —
  duplicarla no resolvería el problema real (el catálogo simplemente no existe en un destino
  instalado) y sí introduciría una segunda fuente de verdad de integridad, prohibido.
- Reimplementar la reinterpretación WARN→FAIL de foundations (Change 6) dentro de `status.py` —
  rechazada: `mlops.foundations` en `status` es un inventario neutral, no una decisión de
  promoción; esa reinterpretación es exclusiva del contexto de `readiness.py` y ya se refleja ahí
  sin necesidad de repetirla.
- Un health score numérico agregado — rechazada explícitamente por el usuario (§14).

## Riesgos
- La degradación con gracia de `harness`/`installation.origen="inferido"` significa que, para la
  gran mayoría de instalaciones reales (cualquier proyecto que no sea el propio checkout de
  Harmessi), esas dos piezas de información nunca se completan — aceptado conscientemente (mismo
  criterio que Change 7 ya documentó para la inferencia legacy): es una limitación estructural
  real del ecosistema actual (Doctor/ds_init son herramientas del lado del mantenedor, no del
  proyecto instalado), no una limitación introducida por este change.
- Mostrar `mlops.production_readiness`/`operations` colapsado en `discovery`/`experiment` podría
  ocultar información a un usuario que sí quiere verla temprano — mitigado con `--verbose`,
  disponible en cualquier stage.
- `evidencia_valida` recalcula sha256 de cada archivo de evidencia registrado cada vez que
  `status` corre (una por capability, hasta 12 en producción) — aceptado, mismo costo que ya paga
  `readiness.evaluar_readiness` al evaluar un target; sin caching nuevo (fuera de alcance,
  "no persistent status cache").

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
Ver `proposal.md § Aprobación`.
