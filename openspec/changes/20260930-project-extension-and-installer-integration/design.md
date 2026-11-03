# Diseño — 20260930-project-extension-and-installer-integration

## Decisión metodológica/técnica

**D1 — `capabilities` como tupla aditiva en `EntradaManifiesto`, filtro en una función hermana
nueva.** No se modifica `manifest_para_perfil_y_stage` (ya usada por Change 0-3 indirectamente vía
`ds_init`/tests de paridad) — se agrega `manifest_para_perfil_stage_y_capabilities` como wrapper
puro que llama a la existente y filtra el resultado. Cualquier llamador que no pase
`capabilities_habilitadas` sigue usando la función vieja sin cambios. Vocabulario inicial acotado a
`predictive_modeling` porque es el único caso con entradas reales identificables hoy (tooling de
holdout/modeling ya existe como paquetes reconocibles: `tools/modelquality`, partes de
`tools/qualityevidence` si aplican, agentes/skills de modelado si los hubiera) — `data_analysis`/
`reporting` quedan como vocabulario reservado, sin lista de exclusión real todavía, para no inventar
un filtro que no excluye nada (deuda explícita, no silenciosa).

**D2 — Resolución de path externo (M9) inyectada, no importada.** `tools/datasources/file_observer.py`
(Change 1, cerrado) ya recibe su configuración vía parámetros (no importa `tools.dsguard` ni
`tools.ds_guard` directamente — regla 11 de `ARCHITECTURE.md`). La resolución de "¿esta fuente tiene
un path externo declarado en local override?" la hace el LLAMADOR (`tools/ds_guard.py`, que sí puede
importar la capa de config M10) y se la pasa al observer como el path ya resuelto — el mismo patrón
que ya usa el registro estático de Change 1 (`resolve_observer_file` con `exists_fn` inyectable). No
se reabre `file_observer.py` para agregarle un import nuevo; si su firma actual no admite recibir un
path inyectado, se audita en implementación si hace falta un parámetro nuevo (aditivo, con default
que preserva el comportamiento de archivo-en-el-repo de hoy) — a confirmar en la propia invocación
de implementación, no una decisión cerrada acá si resulta que ya lo admite.

**D3 — Config layering compuesto en `ds_guard.py`, mismo patrón que `_resolver_budgets`.** `project
config`/`local overrides` son archivos nuevos bajo `.harmessi/` (ubicación exacta, nombres exactos:
`SDD` de implementación, ya delegado en `spec.md` R10) leídos por una función nueva en
`tools/ds_guard.py` que compone `pathguard.cargar_config` (policy humana) ∩ project config ∩ local
override — igual que Change 3 compuso budgets sin tocar `tools/autonomy/policy.py`. `pathguard.py`
(Change 0) no gana ningún import ni lógica nueva de capas — sigue siendo la única fuente de la
policy humana (el techo).

**D4 — Fingerprint pre/post compuesto en `_ejecutar_exec_comun` (Change 3), no en `runtime.ejecutar`
(Change 2).** Mismo patrón exacto que la referencia liviana de métricas de eficiencia: se captura el
fingerprint ANTES de llamar a `leadrun_runtime.ejecutar(...)` (ya devuelve el control al llamador
antes de ejecutar) y se recalcula DESPUÉS, comparando contra el `ExecutionRequest.scope`/entradas
declaradas de la fuente externa. Si difiere, se compone un `CheckResult` con código `data_loss_risk`
(buscado en `STOP_CATALOG` igual que M11, público, no el helper privado) y se agrega a
`resultado["checks"]` antes de imprimir — sin tocar `tools/leadrun/`.

**D5 — Doctor: extensión aditiva de `harmessi doctor`, no un comando nuevo.** Las nuevas categorías
(N/A-capability, ownership de 5 vías, diagnóstico de permisos OS) se agregan como checks nuevos
dentro del comando `doctor` ya existente (`tools/harmessi/doctor.py` o equivalente — confirmar
ubicación exacta en implementación), produciendo `dsguard.checks.CheckResult` como el resto de
Doctor — ningún vocabulario de salida nuevo fuera de `PASS`/`WARN`/`FAIL`/`N/A`/`technical_error` ya
establecido.

**D6 — Mensaje de colisión enriquecido vive en `cli.py`, no en `planner.py`.** `planner.py` sigue
devolviendo solo `AccionPlan(destino, accion, descripcion)` — la lógica de decisión no cambia
(D1 de este documento ya cubre lo único aditivo a `manifest.py`). `cli.py` es quien arma el mensaje
para el usuario a partir de `AccionPlan` + la `EntradaManifiesto` correspondiente (ya tiene acceso a
ambas), agregando tipo de conflicto/asset querido/alternativas — cambio de presentación, no de
lógica de decisión.

**D7 — Instalación gobernada de dependencias (M11, resolución 2026-09-30): extensión aditiva
confirmada, no reapertura material de Change 2.** Auditado en detalle contra el código real de
`tools/leadrun/`:

- `tools/leadrun/runtime.py::ejecutar` **ya** despacha la forma `"cli_diagnostic"` a
  `scripts.ejecutar_script` con `code_hash=None` (sin un único archivo canónico que hashear) —
  exactamente la forma que necesita una instalación de dependencia (`pip install` tampoco tiene un
  único archivo). La nueva rama de despacho para `"dependency_install"` reutiliza el MISMO camino,
  sin ninguna lógica de ejecución nueva.
- `tools/leadrun/scripts.py::ejecutar_script` ya es un ejecutor genérico de `subprocess.run(argv,
  cwd=repo_root, timeout=...)` — sirve cualquier `argv` válido, sin ningún cambio.
- `tools/leadrun/core.py::EXECUTION_FORMS` gana un 5º valor de un vocabulario cerrado — no cambia el
  significado de los 4 existentes, no cambia ningún campo de `ExecutionRequest`/`ExecutionRecord`.
- `tools/leadrun/allowlist.py` gana una función de reconocimiento de forma nueva y AISLADA
  (`_evaluar_forma_dependency_install`), agregada al final de la cadena de verificación de
  `evaluar_comando` (después de `cli_diagnostic`) — las 4 funciones de forma existentes no se tocan.

**Por qué esto NO es "romper o rediseñar materialmente el contrato de `tools/leadrun`"**: ningún
consumidor existente de `ExecutionForm`/`ExecutionRequest`/`ExecutionRecord`/`evaluar_comando`/
`ejecutar` cambia de comportamiento para las 4 formas que ya usa. La prueba de aceptación (R24) es
que los 4 suites de test de Change 2 (`tools/leadrun/tests/`) pasan sin editar una sola línea. La
"materialidad" real de un cambio de contrato sería: cambiar un campo existente, cambiar semántica de
una forma existente, o requerir que un llamador existente cambie su código — nada de eso ocurre acá.

**Por qué el diseño alternativo (redefinir la forma `"script"` para que también acepte `pip
install`) se descartó**: habría sido MÁS invasivo, no menos — redefine la semántica de una forma ya
usada por otros 3 Changes en vez de agregar una nueva y aislada. Ver "Alternativas descartadas".

**Composición de la autorización semántica (fuera de `tools/leadrun/`, en `tools/ds_guard.py`,
territorio de Change 3/4)**: `clasificar_dependencia` (Change 3) decide ANTES de construir el
`ExecutionRequest` — si no es `"no_stop"`, ni siquiera se llega a `allowlist.evaluar_comando`. La
allowlist nueva de `tools/leadrun/` solo reconoce la FORMA sintáctica (`-m pip install --no-deps
<nombre>==<versión>`), nunca decide si ESE nombre/versión puntual está autorizado — mismo principio
ya establecido por R9 de Change 2 ("`allowlist.py` no decide autorización semántica").

**D8 — Las cuatro guardas de la aprobación 2026-09-30 (R34-R41 de `spec.md`) son aclaraciones de
contrato sobre D7, no una pieza de arquitectura nueva:**

- **Guarda 1 (intérprete, R34).** El intérprete `.venv` del proyecto ya lo resuelve
  `tools/ds_guard.py` para construir el `ExecutionRequest` de las 4 formas existentes (mismo patrón
  que ya usa `cli_diagnostic`/`pytest`). `dependency_install` reutiliza esa misma resolución —
  ninguna función nueva de descubrimiento de intérprete. El comando final (`argv`) lo arma
  `tools/ds_guard.py` a partir de piezas ya validadas (intérprete resuelto + patrón fijo de 6
  tokens + nombre canonicalizado + versión exacta) — nunca se acepta un `argv`/string ya armado
  desde afuera (writer, CLI libre, config).
- **Guarda 2 (identidad del paquete, R35-R36).** `_canonicalizar_nombre_paquete` (R36) es una
  función nueva, pura, solo-stdlib (`re.sub(r"[-_.]+", "-", nombre).lower()`, PEP 503), ubicada en
  `tools/dsguard/sdd.py` junto a `clasificar_dependencia` (mismo módulo, mismo dueño). El rechazo de
  formas no soportadas (R35: URL, path, `file:`, `git+...`, `name @ ...`, extras `pkg[extra]`,
  múltiples paquetes, metacaracteres de shell) se implementa como validación de forma ANTES de
  llamar a `clasificar_dependencia` — un nombre que no matchea el patrón simple de distribución PyPI
  nunca llega a comparación semántica. `clasificar_dependencia` en sí **no cambia de firma**: sigue
  recibiendo nombre/versión ya canonicalizados/validados por el llamador, igual que hoy.
- **Guarda 3 (rango vs. versión exacta, R37).** El flujo ya estaba implícito en R25/R27 de la
  resolución original; R37 lo hace explícito como secuencia obligatoria en el propio subcomando
  `dependency install`: versión exacta solicitada (argumento `--version`) → canonicalizar nombre →
  verificar que la versión está dentro del rango de `dependencias_preaprobadas`
  (`_version_satisface_rango`, ya existe de Change 3) → aplicar restricciones de
  project/local config (M10, solo puede restringir) → recién ahí construir el `argv` cerrado. El
  rango en sí (`>=1.2,<2`) nunca se serializa hacia `pip` — pip solo ve el pin exacto.
  Fuera de rango reutiliza el STOP `new_dependency` ya existente (sin STOP nuevo).
- **Guarda 4 (evidencia de entorno pre/post, R38-R39).** Usa `importlib.metadata.version`/
  `importlib.metadata.distributions()` (stdlib, sin dependencia nueva) capturado ANTES y DESPUÉS de
  `runtime.ejecutar`, igual patrón que D4 (fingerprint de fuentes externas) — captura compuesta en
  `tools/ds_guard.py`, no en `tools/leadrun/`. El set de distribuciones post se compara contra el
  set pre; la única diferencia esperada es la distribución solicitada (agregada o con versión
  cambiada). Cualquier diferencia adicional (indicio de que `--no-deps` no evitó un efecto lateral
  inesperado) se reporta como `CheckResult(kind="technical_error")` — reutiliza el vocabulario ya
  existente de Doctor/checks, **no** un STOP nuevo (R39 lo fija explícitamente).

Ninguna de las 4 guardas agrega una pieza de orquestación nueva ni una dependencia de Harmessi
nueva — todas son composición adicional sobre piezas que D7 ya dejaba definidas (resolución de
intérprete existente, `clasificar_dependencia` existente, `_version_satisface_rango` existente,
`runtime.ejecutar` existente).

## Target / Features permitidas / Split / Leakage risks (condicionales)

N/A — Change de infraestructura/instalador, no toca datos ni modelado.

## Reproducibilidad (opcional)

Sin aleatoriedad nueva.

## Alternativas descartadas

- **Modo `--adopt-existing` nuevo.** Descartado tras auditoría: `validar_destino` ya no exige
  proyecto vacío, `detectar_colisiones`/`_accion_para_entrada` ya nunca sobrescriben. Un flag nuevo
  sería una distinción sin diferencia de comportamiento real — se prefiere mejorar lo que sí falta
  (mensaje, ownership en Doctor, test end-to-end) en vez de agregar superficie de CLI innecesaria.
- **`capabilities` como segundo `installation_stage`.** Descartado explícitamente (M8, regla ya
  congelada en el roadmap): son ejes distintos, nunca se funden — `capabilities` es "qué dominio de
  trabajo tiene habilitado el proyecto", `installation_stage` es "madurez de instalación progresiva".
- **Fingerprint con `sha256` siempre.** Descartado por costo: archivos grandes en cada ejecución
  gobernada sería una penalidad de performance no pedida ni necesaria para el caso común (tamaño+
  mtime ya detecta la gran mayoría de modificaciones reales) — hash opcional, configurable, con
  umbral de costo razonable.
- **Sandbox real de fuentes externas (chroot/contenedor/FS overlay).** Descartado: fuera de alcance
  explícito de v0.8 (roadmap), cambiaría radicalmente el modelo de ejecución del Lead (mismo proceso
  hoy) — M12 es defensa detectiva, no preventiva, por diseño del roadmap, no por limitación técnica
  de esta implementación puntual.
- **Un nuevo STOP para integridad de fuentes.** Descartado (M12 lo fija explícitamente): reutiliza
  `data_loss_risk` (STOP 7) ya existente, evita inflar el catálogo de 12 STOP materiales por un caso
  que ya encaja semánticamente.
- **Redefinir la forma `"script"` de `tools/leadrun` para que también acepte `pip install`.**
  Descartado (D7): sería redefinir la semántica de una forma ya usada y probada por 3 Changes, más
  invasivo que agregar una 5ª forma aislada y claramente nombrada.
- **Instalación sin `--no-deps`.** Descartado: permitiría que una dependencia pre-aprobada arrastre
  transitivas nunca declaradas en la propuesta humana — contradice directamente "no decidir
  automáticamente qué paquete necesita el proyecto" (R40). `--no-deps` es obligatorio, sin excepción,
  parte del patrón cerrado de R24.
- **Un segundo runtime/CLI dedicado a instalación de dependencias.** Descartado explícitamente por
  el autor: reutiliza el runtime de Change 2 de punta a punta (allowlist, `ExecutionRequest`,
  `ejecutar`, `ExecutionRecord`) — ninguna pieza nueva de orquestación.
- **`ApprovalRef` individual por instalación.** Descartado: la trazabilidad ya existe vía
  `control["dependencias_preaprobadas"]`, poblada al aprobar `proposal.md` por hash (Change 3) — una
  `ApprovalRef` nueva por cada instalación sería una segunda estructura de aprobación redundante.

## Riesgos

- **Filtro de capabilities incompleto o inconsistente** si la auditoría de implementación no
  identifica correctamente TODAS las entradas "exclusivas de modelado" del manifiesto actual.
  Mitigación: la tarea de implementación arranca con un grep/auditoría explícita de
  `tools/ds_init/manifest.py` completo, documentada en `tasks.md`, antes de marcar ninguna entrada
  con `capabilities=("predictive_modeling",)`.
- **Resolución de path externo (M9) termina acoplando `tools/datasources` a `tools/dsguard`/
  `tools/ds_guard` por conveniencia de implementación.** Mitigación: D2 fija explícitamente
  inyección, no import; el test de neutralidad de R45 lo verifica de forma explícita, no solo por
  revisión de código.
- **Diagnóstico de permisos OS da falsos positivos/negativos entre plataformas** (POSIX vs Windows
  difieren mucho en semántica de permisos). Mitigación: R17 exige `unknown/partial` explícito ante
  incertidumbre — nunca afirmar protección no verificada; tests acotados a lo que el entorno de CI
  puede determinar de forma confiable, documentando qué casos quedan sin cubrir automáticamente.
- **Mensaje de colisión enriquecido (R20) termina filtrando información sensible** (p. ej. contenido
  del archivo del usuario en el mensaje de conflicto). Mitigación: el mensaje describe la
  `EntradaManifiesto` (lo que Harmessi quería instalar) y la ruta, nunca el contenido del archivo
  existente del usuario.
- **Fingerprint pre/post agrega latencia perceptible a ejecuciones con muchas fuentes externas
  declaradas.** Mitigación ya fijada por R14: tamaño+mtime es O(1) por archivo (una llamada a
  `stat`), el costo real solo aparece si se configura hash — documentado como opt-in con umbral.
- **La 5ª forma de `tools/leadrun` (`dependency_install`) termina reconociendo patrones más amplios
  de lo pretendido**, por un regex/parseo de `_evaluar_forma_dependency_install` mal acotado (p. ej.
  aceptando flags extra por un error de conteo de tokens). Mitigación: R24 fija el patrón como
  EXACTAMENTE 6 tokens con comparación literal de `("-m", "pip", "install", "--no-deps")`, no un
  regex laxo; tests de sanity explícitos con intentos de inyección de flags (`--index-url`,
  `--user`, paquetes múltiples, ausencia de `--no-deps`) confirmando rechazo de cada uno.
- **`dependencias_efectivas` (R26) se calcula mal y termina ampliando en vez de restringir** (bug de
  intersección). Mitigación: mismo patrón de test ya usado para M10 en general (R11 de la sección 3)
  — casos explícitos de que project/local config NUNCA agregan una dependencia que la propuesta
  humana no declaró.

## Aprobación humana

Ver `proposal.md` § "Aprobación" — registro único por Change, no se duplica acá.
