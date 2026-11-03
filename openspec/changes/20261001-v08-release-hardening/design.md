# Diseño — 20261001-v08-release-hardening

## Decisión metodológica/técnica

**D1 — Dos fases dentro del mismo Change, no dos Changes.** Este SDD (fase 1) no implementa nada;
la fase 2 (tras aprobación humana por hash de `proposal.md`/`spec.md`/este documento) ejecuta los
escenarios A-K reales y produce el veredicto final. Mismo `tasks.md`, mismo `change_id` — evita
fragmentar la trazabilidad de un release gate en dos SDD separados.

**D2 — Clasificación de cada caso por tipo de verificación** (ya resuelto en `spec.md`, resumido
acá para justificar el diseño de los fixtures):

| Caso | Tipo de verificación | Motivo |
|---|---|---|
| A (autonomía e2e) | Demostración en vivo, Lead-driven | "Cero ejecuciones humanas intermedias" no es simulable por un test unitario sin mockear la esencia misma de lo que se quiere demostrar (que el Lead real complete un ciclo real) |
| B (sin modelado) | pytest, instalación real | Extiende patrón ya existente de `test_integracion_instalacion.py` |
| C (fuente externa) | pytest, sin mocks de subprocess/importlib donde sea viable | Necesita `pathguard`/Doctor reales, no solo la función aislada |
| D (source-neutral) | pytest, fixture con adapter de ejemplo | Contrato ya estable (Change 1), solo se ejercita con una fuente no-file real |
| E (overrides) | pytest, instalación + mutación real + Doctor real | Mismo patrón que C |
| F (adopción) | Reuso directo de test ya existente (Change 4) + extensión puntual | No reinventar lo ya construido |
| G (dependency install) | Regresión dirigida de Change 4 + 1 escenario local opcional | Decisión abierta (ver "Riesgos") sobre si agregar un escenario de instalación real 100% local |
| H (budgets/checkpoints) | Regresión dirigida de Change 3 | Ya cubierto a fondo, sin necesidad de un escenario nuevo |
| I (eficiencia) | Reuso de una corrida ya hecha para otro caso | Evita una corrida dedicada solo para medir |
| J (domain context) | pytest, mínimo, combinado con E o F | Caso de compatibilidad puro, no necesita su propio fixture aislado |
| K (backward compat) | Regresión completa + checklist de cierre | Mismo patrón ya aceptado en el cierre de Changes 2-4 |

**D3 — Fixtures scratch reusables entre casos.** En vez de un fixture nuevo por caso (12+
proyectos sintéticos), se diseñan 2-3 proyectos scratch COMBINADOS que ejercitan varios casos a la
vez, igual que ya hace el Caso F del roadmap original ("combinación end-to-end de la enmienda,
agregado, no duplica A-E"):

- **Fixture 1 ("autonomía combinada")**: `autonomous` + `approval_mode: checkpoints` +
  `predictive_modeling=false` + fuente externa file-backed read-only + project config + local
  override + `GLOSSARY.md` sintético. Ejercita A, B, C (parcial), E, J en un solo proyecto — mismo
  patrón que el "Caso F" ya congelado en el roadmap de Change 4, ahora extendido con J.
- **Fixture 2 ("adopción + dependencia")**: repo preexistente con código/brief de usuario +
  dependencia pre-aprobada declarada + script preexistente ejecutado por el runtime. Ejercita F, G,
  parte de E.
- **Fixture 3 ("source-neutral")**: proyecto mínimo con un adapter `sqlite3` y un adapter
  `module:callable` custom, sin las demás capacidades (aislado a propósito, D depende del contrato
  de Change 1, no de M7-M12).
- **Regresión/backward compat (K)**: reusa los fixtures YA EXISTENTES de Changes 0-4 (ninguno
  nuevo) — es exactamente lo que esos Changes ya prueban sin ninguna opción nueva activada.

**D4 — Verificación de "cero ejecuciones humanas" (R2/R4 de A).** No se inventa un mecanismo de
detección automática nueva: se audita la sesión real (`control["sesiones"]`, `ExecutionRecord`s
persistidos en `.harmessi/executions/`) después de la demostración en vivo y se confirma que la
única intervención humana registrada es la aprobación inicial + checkpoints — mismo principio que
"solo el runtime gobernado produce evidencia válida de ejecución" (decisión M5, Change 0).

**D5 — Caso G (dependency install), RESUELTA por decisión explícita del autor (2026-10-01): SÍ,
instalación real.** La regresión dirigida de Change 4 (24 tests, todos mockeados a nivel de
`subprocess`) NO alcanza como evidencia de release hardening para una capability nueva y sensible
como `dependency_install` — se agrega un escenario de instalación REAL, 100% local y reproducible,
sin red, sin credenciales, sin índice público.

**Mecanismo (sin relajar el contrato cerrado de M11, sin ningún flag libre en el comando
gobernado):**
- Un paquete Python mínimo se empaqueta como wheel (`.whl`) usando EXCLUSIVAMENTE `zipfile` +
  metadata manual de la stdlib (sin `build`/`setuptools`/`wheel` como dependencia nueva de
  Harmessi ni de su suite de tests) — `_construir_wheel_minimo(nombre, version, destino)`, helper
  de test puro.
- La resolución local de pip se configura por ENTORNO TEMPORAL del proceso que invoca
  `ds_guard dependency install` (variables `PIP_NO_INDEX=1`, `PIP_FIND_LINKS=<dir con el .whl>`),
  nunca como flag del `argv` gobernado — `tools/leadrun/scripts.py::ejecutar_script` ya hereda el
  entorno del proceso llamador por default (`subprocess.run` sin `env=` explícito), así que esto
  NO requiere ningún cambio de código en `tools/leadrun/` ni en `tools/ds_guard.py`: es
  exclusivamente configuración del fixture de test. El `argv` final sigue siendo EXACTAMENTE
  `<venv-python> -m pip install --no-deps <nombre>==<versión>`, verificado por el mismo patrón de
  aserción ya usado en Change 4 (`TestArgvPatronDe6TokensConVersionExacta`).
- Ninguna ruta absoluta de esta máquina se versiona: el directorio del wheel y el `PIP_FIND_LINKS`
  se generan en un `tempfile.TemporaryDirectory()` por test, nunca hardcodeados ni committeados.

**Los 13 puntos exigidos por el autor, mapeados a tests concretos** (nuevos, en un archivo de test
dedicado de este Change, NO en los archivos de Change 4 que deben seguir sin editar): paquete local
`A` versión exacta pre-aprobada (1); dentro del rango humano aprobado (2); `exit_code == 0` real
(3); ausente antes (4, confirmado vía `importlib.metadata` real, sin mock); presente con la versión
correcta después (5, idem); `ExecutionRecord` real persistido en `.harmessi/executions/` (6);
`approval`/evidencia ligada a la pre-aprobación real (7, `dependency_evidence.json` real); sin
paquetes adicionales inesperados (8, comparación real de `importlib.metadata.distributions()`
pre/post); sin acceso de red (9, `PIP_NO_INDEX=1` fuerza el fallo si pip intentara salir a
internet -- se confirma además corriendo el test con la red deshabilitada a nivel de fixture si el
entorno de CI lo permite, o documentando honestamente si no se puede aislar la red del proceso de
test); instalación únicamente en el `.venv` del proyecto scratch, nunca el `.venv` de Harmessi (10,
mismo mecanismo ya probado de `launcher_common.ruta_interprete_venv`); el mismo paquete fuera de
rango → STOP `new_dependency` real (11); paquete no aprobado → STOP real (12); ninguna instalación
ocurre en los dos casos STOP, confirmado por `importlib.metadata` real sin cambios (13).

**Cláusula de escape explícita, per instrucción del autor**: si el entorno real de pip hace
imposible demostrar el caso local de forma limpia SIN modificar el contrato cerrado de M11 (p. ej.
si `PIP_NO_INDEX`/`PIP_FIND_LINKS` no bastan para que pip resuelva un wheel local con el comando
`-m pip install --no-deps` exacto, en el entorno real de Windows de este repo), la fase de
implementación DEBE STOP y explicar por qué, en vez de relajar la allowlist o agregar un flag al
comando gobernado para "hacer pasar" el test.

## Reproducibilidad

Sin aleatoriedad nueva (ningún escenario depende de un seed). `.venv` del proyecto scratch creado
igual que cualquier instalación real de Harmessi.

## Alternativas descartadas

- **Un test end-to-end automatizado que simule al Lead con un LLM mockeado para el Caso A.**
  Descartado: mockear las decisiones del Lead vacía la demostración de su propósito real (demostrar
  que el Lead REAL completa el ciclo) — la demostración en vivo (D2) es más honesta que un mock que
  simula justamente lo que se quiere probar.
- **Un fixture scratch nuevo por cada uno de los 11 casos.** Descartado: 12+ proyectos sintéticos
  por mantener, con alto solapamiento de setup — D3 combina en 3 fixtures reusables, mismo patrón
  que el Caso F del roadmap de Change 4 ya validó como aceptable.
- **Convertir las métricas de eficiencia (Caso I) en un gate numérico de este Change.** Descartado
  explícitamente por el roadmap y por la instrucción del autor — observación, nunca optimización a
  costa de validación.
- **Implementar `domain-modeling` como parte de este Change para "probar de verdad" el Caso J.**
  Descartado explícitamente por el autor — el Caso J es compatibilidad arquitectónica pura, un
  `GLOSSARY.md` sintético sin ningún mecanismo de lectura formal basta para demostrarla.
- **Validar dependency install (Caso G) contra PyPI real.** Descartado por instrucción explícita
  del autor ("no hacer depender el release de disponibilidad de red pública") — ver D5.

## Riesgos

- **El Caso A (demostración en vivo) no es reproducible automáticamente en CI.** Mitigación: se
  documenta como tal desde el SDD (D2), con la sesión real + `ExecutionRecord`s como evidencia
  persistida, auditable después de los hechos aunque no sea un `pytest` que corra en cualquier
  máquina.
- **Combinar demasiados casos en un solo fixture (D3) dificulta diagnosticar cuál caso falló.**
  Mitigación: cada fixture combinado todavía produce evidencia/checks ETIQUETADOS por caso (mismo
  código/`CheckResult` que cada pieza ya usa individualmente) — un fallo señala su caso de origen
  sin ambigüedad.
- **El Caso G puede quedar sin un escenario de instalación 100% real si se elige la opción (a) de
  D5.** Mitigación: decisión explícita y documentada en `verification.md`, no una omisión
  silenciosa — el autor puede pedir la opción (b) si considera que (a) no es evidencia suficiente.
- **La regresión completa final (Caso K) puede volver a chocar con el límite de duración de
  procesos en background ya observado durante el cierre de Change 4.** Mitigación: mismo patrón ya
  aceptado (lotes secuenciales, o dejar que una llamada en foreground se auto-convierta a background
  en vez de pasar `run_in_background: true` explícito, que empíricamente recibió un límite más
  corto en esta sesión).

## Aprobación humana

Ver `proposal.md` § "Aprobación" — registro único por Change, no se duplica acá.
