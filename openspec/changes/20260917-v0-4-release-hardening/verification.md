# Verificación — 20260917-v0-4-release-hardening

## Evidencia obtenida

Todas las corridas son reales, ejecutadas por el Lead sobre este repo y sobre repos git temporales
independientes (nunca mocks para lo que exige evidencia real).

- **R1 (versión)**: `tools/ds_init/version.py:HARNESS_VERSION = "0.4.0"`, `CITATION.cff:version:
  0.4.0`/`date-released: "2026-09-17"`. Confirmado con `git diff` — solo esas dos líneas por
  archivo, ninguna anotación histórica ("Bloque N, reliability v0.2.0", "Change N v0.3") tocada.
- **R2 (README)**: agregado un párrafo sobre `science status`/`efficiency report`/`ALCANCE-RUTA`
  ampliado, y una subsección `### ds_guard impact scan` (mismo tamaño que `### ds_profile`), en la
  sección `## Commands`. Ninguna otra sección reescrita.
- **R3 (privacidad transversal)**: `grep` recursivo sobre todo `.py`/`.md`/`.json`/`.cff` del
  working tree para `AGD`/`UNCO-Intelligence`/`Model-churn` (case-insensitive) → 3 resultados, los 3
  son el propio texto de instrucciones de búsqueda de este change y del hardening de v0.3 (mencionan
  el patrón a buscar, no una fuga real — mismo criterio ya aplicado por el hardening de v0.3).
  `grep` para rutas `C:\Users\fcolombo`/`C:\Datos` y para `federcolombo@gmail.com` → 0 resultados en
  todo el repo. Cero hallazgos nuevos.
- **R4 (regresión completa final, 5 suites)**:
  - `tools/tests`: 625 passed, 2 skipped.
  - `tools/harmessi/tests`: 82 passed (0 failures — ver "Diferencias contra la spec" abajo, el único
    fallo preexistente de sesiones anteriores fue diagnosticado y corregido en este mismo change).
  - `tools/ds_init/tests`: 112 passed.
  - `tools/ds_profile/tests`: 129 passed, 5 skipped (dependientes de `pyarrow`, no instalado en este
    entorno — mismo comportamiento ya documentado en Changes anteriores).
  - `tools/dsimpact/tests`: 68 passed.
  - **Total: 1016 passed, 7 skipped, 0 failures.**
- **R5 (`harmessi doctor` final, corrido DESPUÉS de R7)**: `27 [OK], 1 [WARN], 0 [ERROR], 1 [N/A]`.
  El único WARN es `CORE-WORKING-TREE` (cambios sin confirmar — esperado, este mismo change todavía
  no está commiteado al momento de correr doctor). El único N/A es `HARMESSI-INSTALLATION-STAGE`
  (este repo de desarrollo nunca corrió `ds_guard project init`, esperado, sin relación con v0.4).
  `HARMESSI-DRIFT` pasó de 3 `[WARN]` (visto en cada Change 0-4 de esta sesión) a `[OK]` — resuelto
  por la regeneración de R7.
- **R6 (smoke E2E de los 4 componentes nuevos)**: dos scratch installs reales, temporales,
  independientes de este repo:
  - **Discovery** (`--stage discovery --execute`, 59 archivos): `tools/dsimpact/` correctamente
    ausente; `scope.py`/`efficiency.py`/`scientific_validity.py` presentes (sin `stage_minimo`,
    default discovery); `ds_guard impact scan --since HEAD` → exit `3`, mensaje claro ("impact
    preflight no está instalado en este stage..."), sin traceback; `ds_guard status` corre limpio.
  - **Experiment** (default, 74 archivos, mismo conteo que `archivos[]` tras la regeneración de R7
    de este repo — confirma consistencia entre el manifiesto y el estado real): `ds_guard impact
    scan --since HEAD --json` → `{"changed": [], "findings": [], ...}` (diff vacío, correcto, los
    archivos recién instalados están untracked y `git diff` no los ve — comportamiento documentado
    de `dsimpact`, no un bug); `ds_guard science status --json` → los 7 checks en N/A (sin policy
    declarada, correcto); `ds_guard efficiency report --change-id no-existe --json` → 1 resultado
    FAIL `kind=technical_error`, mensaje nombra las dos rutas intentadas, exit `1` (camino de error
    también verificado end-to-end); `ds_guard init --change-id smoke-scope --modo abreviado` +
    archivo `fuera_de_scope.py` creado y COMMITEADO (working tree limpio) + `ds_guard validate
    --change-id smoke-scope --json` → exactamente 1 `ALCANCE-RUTA` para `fuera_de_scope.py`
    (confirma en un scratch install real, no solo en tests unitarios, que Change 2 detecta un
    archivo fuera de scope ya commiteado, y que el fix de duplicado de Change 2 sigue sin duplicar).
- **R7 (`.ds_init/control.json` regenerado)**: vía `control.regenerar_control(repo_root,
  control_previo, stage="experiment")`, invocado directamente por el Lead (no vía `ds_init sync`
  completo, para no arriesgar el tratamiento `MERGE` de `.claude/settings.json` sobre este repo de
  desarrollo en uso activo — ver `design.md`... este change no tiene `design.md` propio, la
  justificación completa está en `spec.md` R7). Resultado: `harness_version: "0.4.0"` (antes
  `"0.3.0"`, desactualizado desde antes de esta sesión), `installation_stage: "experiment"`
  (preservado, sin cambios), `archivos[]`: 61 → 74 entradas (coincide exactamente con el conteo del
  scratch install experiment fresco de R6, confirmando que el manifiesto y el estado real están
  sincronizados). `configuracion`/`fecha_utc` preservados sin cambios (comportamiento documentado de
  `regenerar_control`).

## Fingerprint de dataset/artefacto
No aplica — cambio de hardening/release del harness, no de datos de un proyecto DS.

## Diferencias contra la spec

Durante R4 se encontró y corrigió 1 test desactualizado (fuera del alcance original de "solo
version.py/CITATION.cff/README.md", pero explícitamente autorizado por spec.md R4: "un fixture bug
se corrige solo si está claramente demostrado por lectura del código de producción real"):
`tools/harmessi/tests/test_doctor.py::test_este_repo_no_tiene_installation_stage_en_su_control_json`
afirmaba que `.ds_init/control.json` de este repo NO debía tener la clave `installation_stage` — cierto
antes de Change 7 v0.3 (que introdujo ese campo), falso desde entonces (este repo lo tiene, correcta
y legítimamente, desde antes de esta sesión — confirmado por `git log`/`git diff`: ningún Change de
v0.4 tocó `.ds_init/control.json` hasta la regeneración de R7 de este mismo change). El test nunca
se actualizó tras Change 7 y fallaba de forma predecible, no por ningún bug real. Reemplazado por
`test_este_repo_tiene_installation_stage_valido_en_su_control_json`, que afirma lo contrario
(presencia + valor válido). Diagnóstico verificado por el Lead antes de autorizar el fix; corregido
por `python-data-engineer` en una única tarea acotada, sin tocar ningún otro test ni módulo de
producción.

Sin otras diferencias contra `spec.md` — los 7 requisitos (R1-R7) se cumplieron tal como se
especificaron.

## Limitaciones

Ninguna limitación nueva introducida por este change (es hardening, no features). Limitaciones
conocidas de v0.4, registradas explícitamente como deuda para v0.5+ (ninguna se resuelve acá):

1. **Reestructuración física core/adapter** (Change 3, `ARCHITECTURE.md` §4, 5 items): eager-import
   de `ds_guard.py`, contrato de datos de `pathguard.py` acoplado a la forma de `PreToolUse`,
   `hook_presupuesto.py`/`hook_validar_comando.py` sin separar lógica de I/O, `launcher_common.py`
   mixto, instalador orientado a Claude Code únicamente.
2. **Captura automática de eficiencia de agentes** (Change 4): el campo `subagentes` del schema de
   sesión sigue muerto — `ds_guard efficiency report` solo agrega señales YA registradas
   explícitamente (sesiones/remediaciones vía `session note`/`remediation`), nunca captura
   automática de "agentes lanzados/rol/task-id/duración" (requeriría un hook nuevo sobre
   `Agent`/`SendMessage`, con riesgo real de concurrencia/efectos colaterales — decisión
   arquitectónica material, no tomada unilateralmente).
3. **Scientific validity/scope/efficiency no son gates de `readiness`/`promote`** (decisión
   deliberada de Change 0/2/4): un `FAIL`/`WARN` de ninguno de los tres bloquea una promoción hoy —
   si se decide que alguno debería, es una decisión explícita de un change futuro.
4. **`EFICIENCIA-REMEDIACION-REPETIDA`** es una señal puramente textual (misma `causa` declarada dos
   veces, sin verificar adyacencia real) — nunca un juicio semántico de si un reintento fue
   genuinamente inútil.
5. **`dsimpact` v1** conserva sus límites ya documentados en Change 1: sin parser YAML/TOML real,
   sin resolución de aliasing/imports dinámicos, sin dependency graph.
6. **Sin multi-provider real** — `ARCHITECTURE.md` deja la frontera documentada pero no implementa
   ningún adapter nuevo (Codex/Gemini/Grok), tal como pedía el roadmap explícitamente.

## Pendientes derivados

Ninguno bloqueante. Las 6 limitaciones de arriba quedan como candidatas para v0.5 (`docs/roadmap/
v0.5.md`, ya lista de antes: evals, reporting, ML quality/data contracts, multi-provider) — este
change no abre ningún Change nuevo, solo las deja registradas en el texto de esta verificación y en
`docs/roadmap/v0.4.md` (cada Change 0-4 ya documentó la suya individualmente).

## Resultado final

**READY FOR v0.4.0 RELEASE** (para consolidación local — commit en `v0.4-dev`, sin tag/push/GitHub
Release, pendiente de aprobación humana explícita para publicar, tal como pidió el usuario).

Fundamento: los 7 requisitos de `spec.md` se cumplieron con evidencia real; las 5 suites de test
completas pasan con 0 failures (1016 passed, 7 skipped, ninguno relacionado con v0.4); `harmessi
doctor` final da 0 `[ERROR]`; los 4 componentes nuevos de v0.4 fueron verificados end-to-end en
scratch installs reales (no solo en tests unitarios); privacidad transversal sin hallazgos nuevos;
`.ds_init/control.json` de este propio repo regenerado y consistente (`harness_version: "0.4.0"`,
74 archivos, coincide exactamente con un scratch install fresco al mismo stage); `git status` final
limpio de cualquier archivo temporal/backup accidental.
