# Diseño — 20260929-lead-execution-runtime

## 1. Resumen de la decisión

`tools/leadrun/` es un paquete independiente que **compone** `tools/nbrunner/` y `tools/autonomy/`
en vez de modificarlos — mismo criterio ya aplicado por Change 1
(`openspec/changes/20260928-source-neutral-data-access/design.md`, patrón de "paquete independiente
que compone en vez de modificar") y consistente con `ARCHITECTURE.md:131` (regla de familias
independientes verificada por test). `tools/leadrun/core.py` y `allowlist.py` quedan solo-stdlib
para que la función pura de evaluación de comandos pueda ser reutilizada, sin duplicarse, por el
futuro hook estricto de `v0.10.md` (M5 de Change 0, `docs/roadmap/v0.8.md:415-416`).

El diseño distingue tres responsabilidades que Change 0 ya separó en la tabla de política
(`tools/autonomy/core.py:180-218`) y que este Change no reabre:
1. **Forma del comando** (¿es una de las 4 formas reconocibles? `allowlist.py`, puro).
2. **Autorización semántica** (¿quién ejecuta, qué aprobación requiere, según modo? compuesta en
   `ds_guard.py`, reutilizando `tools.autonomy.core.resolve_action`).
3. **Ejecución + evidencia** (`runtime.py`, único productor de `ExecutionRecord`).

## 2. Alternativas descartadas

### 2.1 Extender `tools/nbrunner/manifest.py` con un campo `kind` en vez de componer

El roadmap deja esta alternativa explícitamente abierta a SDD (`docs/roadmap/v0.8.md:613-614`,
"SDD decide: extender el manifest de `nbrunner` de forma aditiva con `kind` vs. un paquete hermano
que componga sus primitivas"). Se descartó porque:
- el encargo del Lead (D1) ya cerró esta decisión con el mismo criterio usado en Change 1 con
  `tools/datasources`/`tools/ds_profile` (componer, no tocar ni un archivo del paquete existente ni
  sus tests);
- `tools/nbrunner/manifest.py` valida específicamente notebooks (`hash_aprobado`,
  `entradas_permitidas`/`salidas_permitidas` sobre archivos, `fsdiff`) — extenderlo con `kind`
  obligaría a ramificar cada validación por tipo de ejecución dentro del mismo módulo, mezclando dos
  modelos de manifest (notebook con `hash_aprobado` de un `.ipynb`; script sin notebook) en un único
  schema, contra el principio de "un core no ramifica por tecnología" que el roadmap aplica también
  a fuentes (`docs/roadmap/v0.8.md:159`, aplicado aquí por analogía a formas de ejecución);
- modificar `tools/nbrunner/manifest.py` obligaría a re-certificar el hook ya existente
  (`hook_validar_comando.py`) y sus tests — pero no hay tests de `nbrunner` en el repo (hallazgo del
  audit, ver `proposal.md` y §4 de este documento), así que cualquier cambio ahí quedaría sin
  cobertura de regresión visible.

### 2.2 Ejecutar sin allowlist (confiar en la composición de aprobación de `autonomy`)

Se descartó porque la tabla de política de Change 0 (`tools/autonomy/core.py:184-185`) resuelve
"quién ejecuta y qué aprobación requiere", pero no la FORMA del comando — sin una allowlist de forma
cerrada, `runtime.py` ejecutaría literalmente cualquier `argv` que el Lead le pase, lo cual es
exactamente el "shell irrestricto sin governance" que el roadmap prohíbe
(`docs/roadmap/v0.8.md:625`, "no crear shell irrestricto sin governance"; decisión 3 del roadmap,
línea 454-455). La allowlist es la capa que hace que "ejecutar" signifique "ejecutar una de 4 formas
reconocidas", no "ejecutar lo que sea".

### 2.3 Hook preventivo de `PreToolUse` ya en v0.8

Fuera de alcance por decisión explícita del roadmap: "El hook estricto global de allowlist queda
diferido a `v0.10.md` y deberá reutilizar la misma función pura de evaluación, sin crear otra
allowlist" (`docs/roadmap/v0.8.md:415-416`, M5). Este Change construye esa función pura
(`allowlist.evaluar_comando`) precisamente para que v0.10 la reutilice sin reinventarla, pero no
instala ningún hook nuevo.

### 2.4 Sandbox/contenedores para aislar la ejecución

Fuera de alcance explícito (`docs/roadmap/v0.8.md:625-626`, "sandbox/contenedores"). El roadmap es
explícito en que la garantía de v0.8 es "gobernanza + evidencia + enforcement en las superficies
controladas", no un sandbox total del proceso (`docs/roadmap/v0.8.md:429-431`). Este Change no
introduce ningún mecanismo de aislamiento de proceso más allá de lo que ya ofrece
`subprocess.run(timeout=...)`.

## 3. Composición con `nbrunner` (detalle de `notebooks.py`)

`tools/leadrun/notebooks.py` no reimplementa ninguna validación: importa directamente
`tools.nbrunner.manifest.{cargar_manifest, validar_interprete, validar_hash_notebook,
validar_aprobacion, validar_rutas_prohibidas}`, `tools.nbrunner.core.{Finding, hash_lf_v1}`,
`tools.nbrunner.execute.ejecutar_notebook` y `tools.nbrunner.fsdiff.{snapshot, diferencia,
clasificar, cuarentena}` (nombres citados en el encargo, confirmados presentes en
`tools/nbrunner/manifest.py:62,93,124,145,173,257` — `execute.py`/`fsdiff.py` se asumen con la
misma interfaz que el encargo describe, ya que el encargo los declara "COMPLETOS" y este documento
no los reproduce por brevedad; cualquier discrepancia de firma real se resuelve en implementación,
sin alterar el contrato de `nbrunner`).

`tools/notebook_runner.py` es el único llamador de `tools.leadrun.notebooks` para el flujo CLI; el
subcomando `ds_guard.py exec notebook` (R14) es una segunda vía equivalente que construye el mismo
`ExecutionRequest` con `command_form="notebook"` y delega en `runtime.py` → `notebooks.py`, para que
la evidencia de ejecución de notebooks también pase por `ExecutionRecord` de forma uniforme con
scripts/pytest. Ambos caminos comparten la misma composición de aprobación (R12); no hay una tercera
ruta de ejecución de notebooks.

## 4. Riesgos

**R-A — Proceso huérfano en Windows para scripts/pytest con hijos anidados.**
`subprocess.run(..., timeout=...)` mata el proceso directo en cualquier plataforma al expirar el
timeout, pero en Windows un proceso hijo que a su vez lanzó otros procesos (p. ej. un script que
invoca a otro binario) puede sobrevivir. Es el MISMO límite que `tools/nbrunner/execute.py` ya
declara para notebooks (uso de `psutil` best-effort). Este Change no introduce una solución nueva
(prohibido por D9 del encargo): se documenta como límite conocido, mitigado únicamente por el
timeout duro a nivel del proceso padre y por la revisión previa del código (reviewer) antes de
ejecutar.

**R-B — Timeout no robusto multiplataforma.** Mismo riesgo que R-A, desde el ángulo de "qué
garantiza `timeout_seconds`": garantiza que el proceso *padre* termina y que `ExecutionRecord.
timed_out=True`, no que todo el árbol de procesos terminó. Mitigación: ninguna nueva en este Change;
documentado en `spec.md` R10.

**R-C — Sin sandbox.** Un script ejecutado por `scripts.py` corre con los mismos permisos que el
proceso Python del Lead — puede, en teoría, escribir fuera de lo declarado en su `scope`, abrir una
conexión de red, o leer un archivo fuera del alcance. La mitigación no es técnica en este Change:
revisión previa del reviewer (read-only, antes de ejecutar), `pathguard`/`guardrails.json` para
escritura a rutas protegidas, fsdiff/cuarentena solo para el subconjunto de rutas que el
`ExecutionRequest` declaró como salidas esperadas (paridad con notebooks). Documentado también en
`docs/roadmap/v0.8.md:443-444` como límite honesto ya aceptado para el runtime.

**R-D — El script `tools/notebook_runner.py` no existía (hallazgo del audit).** Confirmado con
evidencia en `proposal.md` (Glob sin resultados). Riesgo residual: cualquier otro documento o hook
del repo que asuma la existencia de ese script con una interfaz distinta a la que
`hook_validar_comando.py:66-69` ya fija quedaría descubierto recién en implementación. Mitigación:
`tasks.md` prioriza crear el script y su test de paridad con el hook antes que cualquier otra pieza
de ejecución (T2 en `tasks.md`).

**R-E — Ausencia de tests de `tools/nbrunner/` (segundo hallazgo del audit).** No existe
`tools/nbrunner/tests/` ni `tools/tests/test_nbrunner.py` (confirmado por `Glob`/lectura fallida,
ver `proposal.md`). Esto significa que la composición de `tools/leadrun/notebooks.py` sobre
`tools.nbrunner.*` no tiene, hoy, ninguna red de regresión previa que confirme que el comportamiento
de `nbrunner` es el documentado en sus docstrings — este Change confía en la lectura directa del
código fuente (ya hecha, citada por línea en `spec.md`) y agrega tests **nuevos** para
`tools/notebook_runner.py` y `tools/leadrun/notebooks.py` que ejercitan `nbrunner` indirectamente,
pero no retro-cubre `tools/nbrunner/` en sí (fuera de alcance: no se modifica ese paquete, y agregar
tests para código que no se toca excede el criterio de cambio mínimo). Se registra como deuda
externa a este Change, a evaluar por el autor si amerita un Change propio.

**R-F — Colisión de nombre de paquete.** Se verificó que no existe hoy ningún paquete ni módulo
llamado `tools/leadrun` en el repositorio (`Glob("tools/leadrun/**")` sin resultados antes de
escribir este documento). No hay colisión real detectada; se usa el nombre tal cual propuesto por
el Lead (D15 del encargo). Si en el futuro apareciera un uso previo de "leadrun" en otro contexto
(por ejemplo, documentación externa), es una decisión a confirmar por el autor, no resuelta acá.

**R-G — Excepciones de dependencia documentadas pero no verificadas por un test dedicado de
"catálogo de excepciones".** `runtime.py` importa `tools.datasources.scan` (R1, R9 de `spec.md`) y
`ExecutionRecord.approval` transporta la forma serializada de `tools.autonomy.core.PolicyApproval`
sin importar `autonomy` directamente (R7 de `spec.md`). A diferencia de Change 1, que documentó su
excepción de M1 con una cita textual acotada en `datacontracts/validation.py`, este Change no crea
un archivo separado de "excepciones de dependencia": quedan documentadas en `spec.md` R1/R7/R9 y en
el test de neutralidad (R15) como parte del conjunto de imports permitido de `runtime.py`. Riesgo:
si `tools.datasources.scan` cambia de firma en un Change futuro de la familia `datasources`,
`tools/leadrun/runtime.py` puede romperse sin que ningún test de `datasources` lo detecte (la
dirección de dependencia permitida es unidireccional: `leadrun → datasources`, nunca al revés). Se
acepta como riesgo conocido, mismo patrón que ya asume Change 1 para `datacontracts →
datasources`.

## 5. `stage_minimo` y manifiesto de instalación

Confirmado por lectura directa de `tools/ds_init/manifest.py:132-184`: las 5 `EntradaManifiesto` de
`tools/nbrunner/*` usan `stage_minimo="experiment"` de forma consistente (no `"discovery"` ni
`"production_candidate"`). Como `tools/leadrun/notebooks.py` y `tools/notebook_runner.py` dependen
en tiempo de import de `tools.nbrunner.*` (R1 de `spec.md`), instalarlos en un stage anterior a
`experiment` produciría un `ImportError` en cuanto se invocara la forma `notebook` de la allowlist.
Por eso las entradas nuevas de este Change usan el mismo `stage_minimo="experiment"` — no se separa
`core.py`/`allowlist.py` (que no dependen de `nbrunner`) en un stage distinto porque el paquete se
instala como unidad, igual que ya hace `tools/nbrunner/*` (todas sus 5 entradas comparten stage, no
hay instalación parcial del paquete).

## 6. Qué no resuelve este Change (límites honestos, para citar en cierre)

- No hay enforcement técnico de que toda ejecución del Lead pase por `tools/leadrun/`: es un
  contrato de proceso (Change 3), no un candado técnico (R13 de `spec.md`).
- No hay sandbox de proceso; un script ejecutado hereda los permisos del proceso Python que lo lanzó.
- El timeout no garantiza la terminación de árboles de procesos anidados en Windows.
- No se agregan tests retroactivos a `tools/nbrunner/`, a pesar de que no existen hoy (R-E).
- La allowlist es cerrada por diseño: cualquier necesidad legítima futura de una quinta forma de
  comando requiere un Change nuevo que la agregue explícitamente a `allowlist.py`, no una excepción
  ad hoc.
