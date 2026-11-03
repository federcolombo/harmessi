# Diseño — 20260915-checks-engine-foundation

## Decisión metodológica/técnica

1. **Ubicación: `tools/dsguard/checks.py`**. `doctor.py` ya importa `tools.dsguard.pathguard`
   hoy — la dirección de dependencia `harmessi → dsguard` ya existe, cero riesgo nuevo de ciclo.
   Futuros consumidores (`maturity.py`/readiness) ya viven en `dsguard/`, consumo directo sin
   cruzar paquetes. Mismo patrón de manifest ya probado 3 veces (`lifecycle.py`,
   `kdd_compat.py`, `maturity.py`).

2. **`Finding` y `CheckResult` quedan separados, sin unificar.** `Finding` (`dsguard/core.py`)
   es presencia-solamente (sin campo de severidad): su existencia ya significa "bloquea", usado
   en gates de SDD/pathguard/kdd/decision, ninguno de los cuales necesitó nunca representar
   "esto pasó" o "esto no aplica" como resultado explícito. `CheckResult` necesita exactamente
   eso como estados de primera clase. Unificarlos obligaría a `Finding` a cargar semántica
   (PASS, N/A) que su modelo binario actual (ausencia=OK) nunca necesitó, en código ya probado y
   usado ampliamente — cambio de alto riesgo sin beneficio concreto demostrado. Frontera:
   `Finding` = "algo está mal" (gate/validación), `CheckResult` = "resultado de evaluar un
   check" (diagnóstico/readiness).

3. **`CheckResult` como `@dataclass(frozen=True)`** — mismo patrón que `ResultadoCheck` ya usa
   hoy (inmutable, comparable por valor, fácil de testear con `assertEqual`, consistente con el
   estilo ya establecido en el módulo que retrofitea). Sin campos `metadata`/`evidence` — ningún
   consumidor actual (doctor) los necesita; agregarlos sería especulativo, se evalúa en el
   change que primero los necesite.

4. **`message` obligatorio siempre, no solo para `N/A`** — una sola regla sin casos especiales
   (mismo criterio ya aplicado en Change 3 para `reason` en `calibrate`/`set_risk`): ningún
   status se beneficia de un mensaje vacío, y una regla condicional ("solo N/A lo requiere")
   sería más código para el mismo resultado práctico.

5. **`ejecutar()`/`formatear()` de Doctor mantienen firma y comportamiento público EXACTOS.** El
   retrofit ocurre puramente dentro de las funciones `_check_*` (que pasan a devolver
   `CheckResult`) y en `_ejecutar_check` (que ahora delega en `checks.ejecutar_checks` y traduce
   el resultado a `ResultadoCheck` antes de devolverlo). `test_doctor.py` no necesita ninguna
   modificación para sus aserciones existentes — siguen viendo `ResultadoCheck` con
   `.nivel`/`.seccion`/`.codigo` de siempre. Esto prioriza "cero riesgo de romper UX/tests
   existentes" sobre "elegancia de tener un solo tipo de resultado en todo el pipeline" —
   trade-off consciente, ver Riesgos.

6. **`N/A` en el resumen de `formatear()` es condicional**: el segmento `"N [N/A]"` solo se
   agrega a la línea de resumen si el conteo es mayor a 0. Con el estado actual (ningún check
   emite N/A), la salida de `harmessi doctor` es byte a byte idéntica a la de antes del
   retrofit. Ningún check existente se modifica para introducir N/A artificialmente — sigue la
   preferencia explícita del usuario.

7. **Sin unificación de exit codes con `ds_guard.py`** (esquema 0/1/2/3). Doctor mantiene su
   esquema binario ya existente (`0`/`1`) — errores de entorno/uso hoy ya se representan como
   resultados `ERROR`/`FAIL` individuales dentro de la corrida normal (ej.
   `CORE-REPO-GIT`), no como un exit code separado. Unificar los dos esquemas no fue pedido y
   expandiría el alcance sin necesidad demostrada.

8. **Sin contexto/god-object en el engine.** `ejecutar_checks(registros)` recibe
   `(codigo_base, funcion, args)` por cada check — cada check recibe exactamente los argumentos
   posicionales que necesita (mismo patrón que `_ejecutar_check(seccion, codigo_base, funcion,
   *args)` ya usa hoy). No hay necesidad concreta de un dict de contexto compartido entre
   checks; introducirlo sería infraestructura especulativa para un caso de uso (readiness
   futuro) que todavía no está diseñado.

9. **`CheckResult` distingue FAIL funcional de error técnico vía `kind`** (ajuste del usuario tras
   la aprobación): campo `kind: str = "check"`, valores `{"check", "technical_error"}`. Un
   requisito que legítimamente no se cumple es `kind="check"` (default, no requiere que los
   checks existentes cambien nada); una excepción inesperada capturada por `ejecutar_checks` es
   `status=FAIL, kind="technical_error", code="{codigo_base}-EXCEPCION"`. Ambos bloquean igual
   (`hay_bloqueo`/`exit_code` miran solo `status`) — `kind` es metadata de diagnóstico, no cambia
   la semántica de bloqueo. Justificación: sin este campo, un `FAIL` legítimo ('el venv no
   existe') y un `FAIL` producido porque el CÓDIGO del check tiene un bug ('TypeError inesperado')
   son indistinguibles para quien lea los resultados — importante ya desde ahora porque un futuro
   motor de readiness va a necesitar poder decir 'este check nunca se pudo evaluar' de forma
   distinta a 'este check se evaluó y no pasa'. `ResultadoCheck` (Doctor) NO gana el campo — ambos
   siguen renderizando como `[ERROR]`, sin cambio de UX pública en este change.

## Target (condicional — feature_engineering, modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Alternativas descartadas
- Unificar `Finding` y `CheckResult` en un solo tipo — rechazada, ver punto 2.
- Cambiar la firma pública de `doctor.ejecutar()` para devolver `list[CheckResult]`
  directamente — rechazada, ver punto 5: rompería `test_doctor.py` sin necesidad y expandiría
  el riesgo del retrofit más allá de lo pedido.
- Agregar `metadata`/`evidence` a `CheckResult` ahora — rechazada, ver punto 3: especulativo,
  ningún consumidor actual lo necesita.
- Contexto compartido tipo dict para los checks — rechazada, ver punto 8.
- Unificar exit codes de `doctor` con el esquema 0/1/2/3 de `ds_guard.py` — rechazada, ver
  punto 7.
- Introducir un check sintético que emita N/A solo para demostrar la capacidad — rechazada:
  preferencia explícita del usuario, y hubiera sido un cambio de comportamiento observable no
  solicitado.

## Riesgos
- El retrofit de ~20 funciones `_check_*` es mecánico pero extenso (cambia el vocabulario
  interno de cada una) — mitigado por: (a) la firma pública de `ejecutar()` no cambia, (b)
  verificación real corriendo `harmessi doctor` sobre este repo antes/después y comparando
  línea por línea, (c) suite completa de regresión (`test_doctor.py`, `test_cli.py`,
  `tools/tests/`, `tools/ds_init/tests/`).
- Mantener dos tipos de resultado (`CheckResult` interno, `ResultadoCheck` público de Doctor) es
  una capa de traducción adicional permanente — aceptado conscientemente (punto 5) a cambio de
  cero riesgo de romper UX/tests existentes; un change futuro podría reconsiderar esto si
  `ResultadoCheck` deja de tener consumidores que dependan de su forma actual.
- Si un check futuro de Doctor alguna vez necesita `N/A` de verdad, su aparición en el resumen
  (nuevo segmento) será la primera vez que la salida de `harmessi doctor` cambie de formato —
  comportamiento esperado y ya diseñado, no un bug cuando ocurra.
- Si `kind` nunca se consume por nada más que estos tests en este change, es metadata sin uso
  observable todavía — aceptado conscientemente: el campo es barato (un string con default), y el
  costo de agregarlo después (cuando readiness lo necesite) sería mayor que el de incluirlo ahora
  con su semántica ya bien definida.

## Aprobación humana
Ver `proposal.md § Aprobación`.
