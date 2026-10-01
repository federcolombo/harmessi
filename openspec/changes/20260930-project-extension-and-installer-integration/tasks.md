---
estado: cerrada
---

# Tareas — 20260930-project-extension-and-installer-integration

`T0` ya está hecha (audit de lectura, evidencia citada en `proposal.md`). `T1..Tn` son invocaciones
futuras del `python-data-engineer`, en orden de dependencia: capabilities primero (toca el manifiesto
que todo lo demás puede necesitar leer), config layering segundo (M9/M11/M12 dependen de esa capa),
instalación de dependencias tercero (depende de T2 para `dependencias_efectivas`), fuentes externas e
integridad después, adopción/Doctor al final porque compone todo lo anterior para reportarlo.
**Ninguna tarea de esta lista se ejecuta todavía — este documento es el plan, no la implementación.**

## T0 — Audit (hecho, Lead, solo lectura)

- [x] Confirmar que `tools/ds_init/preflight.py::validar_destino` no exige proyecto vacío.
- [x] Confirmar que `detectar_colisiones`/`_accion_para_entrada` ya implementan "nunca sobrescribir".
- [x] Confirmar que `EntradaManifiesto` no tiene ningún campo de capability hoy.
- [x] Confirmar que `tools/datasources/core.py` no tiene ningún campo de path físico (por diseño).
- [x] Confirmar que `tools/dsguard/pathguard.py` conoce una sola capa de config.
- [x] Confirmar que Change 2 no tiene una primitiva gobernada de instalación, y que
  `tools/leadrun/runtime.py` ya despacha `cli_diagnostic` a `scripts.ejecutar_script` con
  `code_hash=None` — la base de reuso para `dependency_install` (D7 de `design.md`).

## T1 — Project capabilities (M8, `tools/ds_init/manifest.py`)

- Auditoría exhaustiva de qué entradas del manifiesto son "exclusivas de modelado" (grep + revisión
  manual, documentada) antes de marcar ninguna con `capabilities=("predictive_modeling",)`.
- Campo `capabilities: tuple = ()` en `EntradaManifiesto`; `manifest_para_perfil_stage_y_capabilities`
  nueva (D1 de `design.md`).
- QA: paridad con el comportamiento actual sin declarar capabilities; filtro correcto con
  `predictive_modeling=false`; composición correcta con `stage_minimo`.

## T2 — Config layering (M10, `tools/ds_guard.py` + archivos nuevos bajo `.harmessi/`)

- Formato/ubicación exacta de project config y local overrides (R10 de `spec.md`).
- Función de composición fail-closed (D3 de `design.md`), sin tocar `pathguard.py`.
- QA: los 6 casos de "un override nunca amplía" (R11); ausencia de ambas capas es backward-compatible.

## T3 — Instalación gobernada de dependencias pre-aprobadas (M11, R24-R41 de `spec.md`)

- `tools/leadrun/core.py`: agregar `"dependency_install"` a `EXECUTION_FORMS` (única línea).
- `tools/leadrun/allowlist.py`: `_evaluar_forma_dependency_install` nueva y aislada (patrón cerrado
  de 6 tokens, comparación literal, sin regex laxo) + agregarla a la cadena de `evaluar_comando`.
- `tools/leadrun/runtime.py`: rama de despacho que reutiliza `scripts.ejecutar_script` para esta
  forma (mismo camino que `cli_diagnostic`) — sin tocar `scripts.py`.
- `tools/dsguard/sdd.py`: `_canonicalizar_nombre_paquete` nueva (R36, PEP 503, solo-stdlib);
  validación de forma de `--nombre` ANTES de canonicalizar/clasificar (R35: rechazo de URL, path,
  `file:`, `git+...`, `name @ ...`, extras, múltiples paquetes, metacaracteres) — `clasificar_dependencia`
  no cambia de firma (D8).
- `tools/ds_guard.py`: subcomando `dependency install --change-id <id> --nombre <n> --version <v>`;
  `dependencias_efectivas` (R26, compone T2); validación de forma + canonicalización (R35-R36) →
  clasificación ANTES de construir el `ExecutionRequest` (R25) → `_version_satisface_rango` sobre la
  versión exacta, nunca el rango hacia pip (R37) → restricciones project/local config (M10) →
  resolución del `.venv` ya reconocido del proyecto, intérprete construido por el runtime, nunca
  recibido libre (R27, R34) → `approval` con referencia a la pre-aprobación (R28) → captura de
  evidencia de entorno pre-instalación vía `importlib.metadata` (R38) → ejecución → revalidación
  post-instalación (R29) → captura de evidencia post + comparación de sets de distribuciones,
  diferencia inesperada → `CheckResult(kind="technical_error")`, sin STOP nuevo (R38-R39); fallo
  consume remediation existente (R30); sin soporte de `--index-url`/`--extra-index-url`/credenciales,
  redacción reutiliza `_redactar_argv`/`_redactar_resumen` (R41).
- QA obligatorio (no negociable, per instrucción del autor): **los 4 suites de
  `tools/leadrun/tests/{test_core,test_allowlist,test_scripts,test_runtime}.py` (Change 2) pasan sin
  editar una sola línea** — es la prueba de que esto es aditivo, no material. Más, cada uno con su
  propio test explícito:
  - Los 11 requisitos de seguridad de la resolución 2026-09-30 (solo pre-aprobadas, nombre+versión
    exactos, fuera de rango → STOP, project/local config solo restringe, solo `.venv` del proyecto,
    nunca global, nunca Harmessi, sin shell arbitrario, sin argumentos libres, nunca desde el writer,
    evidence/ledger, remediation sin contador paralelo).
  - Intérprete fuera del `.venv` reconocido → rechazado (R34).
  - URL/path/VCS/extra/referencia directa → rechazado (R35).
  - Más de un paquete en una sola invocación → rechazado (R35).
  - Flags extra inyectados (`--index-url`, `--user`, etc.) → rechazado.
  - Nombre canónicamente equivalente (mayúsculas/`_`/`.` vs `-`) se comporta de forma determinística
    (R36) sin autorizar un paquete distinto.
  - Versión exacta dentro del rango → permitida; fuera del rango → STOP `new_dependency` (R37).
  - El rango aprobado nunca se pasa literalmente a pip (verificado por inspección del `argv`
    construido, no solo por el resultado) (R37).
  - Dependencia transitiva faltante NO se autoinstala (R40).
  - `ExecutionRecord`/evidencia sin secretos, incluida la captura pre/post de `importlib.metadata`
    (R38-R39, R41).

## T4 — Fuentes externas file-backed read-only (M9)

- Declaración de path externo en local override (T2); resolución inyectada hacia `file_observer.py`
  (D2, auditar si su firma actual ya admite esto o necesita un parámetro aditivo).
- Enforcement de solo lectura en `pathguard.py` (extensión aditiva, nueva categoría de ruta
  protegida).
- QA: los 4 casos Given/When/Then de R7-R8.

## T5 — Integridad detectiva (M12)

- Fingerprint tamaño+mtime pre/post en `_ejecutar_exec_comun` (D4 de `design.md`); hash opcional.
- Mapeo a `data_loss_risk` (STOP 7 existente, buscado vía `STOP_CATALOG` público).
- Diagnóstico de permisos OS en Doctor (solo lectura, `unknown/partial` explícito); helper
  cooperativo de output roots (R18).
- QA: los casos de R14-R18, incluida la discrepancia de fingerprint real.

## T6 — Adopción de proyecto existente (B5)

- Mensaje de colisión enriquecido en `tools/ds_init/cli.py` (D6, sin tocar `planner.py`).
- Ownership de 5 vías en Doctor (D5).
- Test end-to-end de adopción sobre un repo scratch con código/brief existentes (no existía antes).

## T7 — Tests de repo, neutralidad, manifiesto

- Test de que `tools/datasources`/`tools/autonomy` (Changes 0-1, cerrados) no ganaron ningún import
  nuevo por esta integración; test dirigido de que `tools/leadrun` (Change 2, cerrado) SOLO cambió en
  los 3 puntos exactos de T3, verificado por diff (R45).
- `check_manifest_parity` en verde; `ARCHITECTURE.md` actualizado solo donde corresponda (contratos/
  límites reales, no solo planificación) — incluida la nueva excepción de dirección hacia
  `tools/leadrun` si `tools/ds_guard.py` compone algo que hoy no compone.

## T8 — Revisión (data-science-reviewer, solo lectura)

- Revisar T1-T7 contra `spec.md` completo (R1-R45) y contra los riesgos de `design.md`.
- Atención especial a R24 (los 4 suites de Change 2 sin editar) y a los requisitos de seguridad de
  T3 (11 originales + R34-R41, las cuatro guardas de la aprobación 2026-09-30) — cada uno con
  evidencia puntual, no una revisión genérica.

## T9 — Cierre (Lead)

- Gate final: regresión completa (lotes secuenciales si hace falta, patrón ya aceptado).
- `verification.md` de cierre con evidencia por R1-R45.
- `docs/roadmap/v0.8.md`: tildar Change 4, solo tras aprobación humana de este `proposal.md`.
