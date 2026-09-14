# Propuesta — 20260914-fix-harness-version-drift

## Problema
`.ds_init/control.json` de este repo (harmessi auto-instalado sobre sí mismo) quedó
desactualizado. `harness_version` dice `"0.1.0"` (línea 2) mientras
`tools/ds_init/version.py:13` define `HARNESS_VERSION = "0.2.0"` desde el commit
`1458054` ("Prepare Harmessi v0.2.0 release"), que no tocó `control.json`. Además, la
lista `archivos` (11 entradas, líneas 11-52) solo refleja el snapshot de la instalación
original (2026-09-09) y nunca se refrescó tras tres commits posteriores que agregaron
archivos administrados por el harness directamente al repo: `24c07e4`
(`tools/dsguard/kdd.py`, `kdd.md`), `b653e6a` (`tools/dsguard/decision.py`,
`decision-ledger.md`, adiciones de remediación en `sdd.py`), `07f4c14`
(`tools/ds_profile/*`, `eda.md`). Esos archivos son invisibles para `_check_hashes_drift`
de `doctor.py` porque ese check solo itera lo que ya está listado en
`control.json["archivos"]` — es un punto ciego silencioso de detección de drift.

## Objetivo
Corregir `harness_version` y refrescar `archivos` en el `control.json` real de este
repo, y dejar una función reutilizable (`regenerar_control`) para hacerlo de forma
segura y testeable en el futuro.

## Evidencia
- `.ds_init/control.json:2` → `"harness_version": "0.1.0"`
- `tools/ds_init/version.py:13` → `HARNESS_VERSION = "0.2.0"`
- `tools/harmessi/doctor.py:706-734` (`_check_coherencia_version`) — ya implementa la
  comparación exacta; hoy devuelve `NIVEL_WARN` (`HARMESSI-VERSION`) para este repo
- `tools/harmessi/doctor.py:422-475` (`_check_hashes_drift`) — solo verifica hash de lo
  que ya está en `control_data["archivos"]`, por eso los archivos agregados después de
  la instalación original no están cubiertos
- Commits `24c07e4`, `b653e6a`, `07f4c14` agregaron archivos administrados sin
  refrescar `control.json`; `1458054` bumpeó `HARNESS_VERSION` sin refrescarlo tampoco

## Supuestos descartados
No se contempla implementar un comando `update`/`upgrade` completo de `ds_init` — eso
sigue explícitamente fuera de alcance del MVP (R15, docstring de
`tools/ds_init/version.py`). Tampoco se retro-corrige `fecha_utc` a la fecha de hoy:
`fecha_utc` representa la fecha de instalación original (2026-09-09T18:08:09Z) y
regenerar `archivos`/`harness_version` no cambia cuándo se instaló el harness por
primera vez — perder ese dato sería una pérdida de evidencia histórica innecesaria.

Regenerar `.ds_init/control.json` en este repo es una recalibración puntual del
snapshot instalado en este momento — no una garantía de ausencia de drift futuro. No
implica que este repo self-hosted vaya a permanecer sin drift durante todo el
desarrollo de v0.3: en cuanto se modifiquen archivos administrados por el harness (por
ejemplo al implementar los changes 1..N del roadmap v0.3 aprobado), `harmessi doctor`
puede volver a reportar `HARMESSI-VERSION`/`HARMESSI-DRIFT` en `WARN` — eso es el
comportamiento esperado hasta la próxima recalibración explícita o hasta un release
que la incluya. El mecanismo permanente de upgrade/update (R15) sigue fuera de alcance
de este change.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica — cambio técnico, no metodológico.

## Alcance
1. Agregar parámetro opcional `fecha_utc: str | None = None` a `generar_control()` en
   `tools/ds_init/control.py` (si no se pasa, mantiene el comportamiento actual de
   estampar `datetime.now(timezone.utc)` — no rompe a `writer.py`, que la sigue
   llamando posicionalmente con 4 argumentos).
2. Agregar función nueva `regenerar_control(destino, control_previo: dict, *,
   perfil: str | None = None) -> dict` en el mismo módulo: recalcula `archivos`
   (hashes reales) a partir de `manifest_para_perfil(perfil or
   control_previo["perfil"])` (excluyendo la entrada `.ds_init/control.json`, misma
   exclusión que ya aplica `doctor.py:395`), preserva `configuracion` y `fecha_utc` de
   `control_previo`, usa el `HARNESS_VERSION` vigente (no el de `control_previo`). No
   reinstala nada — asume que los archivos administrados ya existen en destino. La
   escritura de `regenerar_control()`/`generar_control()` sobre
   `.ds_init/control.json` sigue el patrón actual del módulo `tools/ds_init/control.py`,
   que **no** usa escritura atómica (a diferencia de `tools/dsguard/core.py`, que sí
   implementa `escribir_texto_atomico`/`_escribir_atomico` para el control.json de SDD
   — es un módulo distinto, sin relación con este). No se introduce atomicidad nueva en
   este change: ampliaría el alcance más allá de lo aprobado y ese no es el patrón
   existente que este fix debe preservar.
3. Test unitario nuevo en `tools/ds_init/tests/test_control_file.py` (extiende la
   clase existente, sigue el patrón de `_crear_repo_git_temporal()` — **nunca usar
   este propio repo como fixture**, ver docstring del archivo/R14/AC15): cubre que
   (a) `generar_control` sin `fecha_utc` sigue comportándose igual que hoy (no rompe
   nada existente), (b) `regenerar_control` produce un `control.json` con
   `harness_version` = `HARNESS_VERSION` actual, `archivos` cubriendo el manifiesto
   completo vigente con hashes reales, y `fecha_utc` preservado del `control_previo`
   pasado.
4. Invocar `regenerar_control` **una sola vez, sobre este propio repo**, para
   corregir su `.ds_init/control.json` real (esto es la aplicación puntual del fix,
   no una feature nueva expuesta por CLI).
5. Verificación: correr `harmessi doctor` antes/después y confirmar que
   `HARMESSI-VERSION` pasa de `WARN` a `OK`, sin que aparezcan `WARN`/`ERROR` nuevos.

## Fuera de alcance
Ningún subcomando CLI nuevo en `ds_guard`/`ds_init` (R15 sigue diferido). Ningún
cambio a `manifest.py` (`MANIFEST`/`EXCLUSIONES_PERMANENTES`). Ningún cambio a la
lógica de checks de `doctor.py` (ya detecta correctamente; el fix corrige el dato, no
el check).

## Holdout policy (condicional — solo cambios "sensible")
No aplica — este cambio no toca datos, holdouts ni datasets sellados.

## Impacto en production-readiness (opcional)
El roadmap aprobado de Harmessi v0.3 (Methodology Core / Project Maturity /
Progressive Scaffold) incluye una capa de `unified-status-surface` y
`checks-engine-foundation` que van a leer `harness_version`/`control.json` para
reportar salud del proyecto. Si esto queda sin corregir, esas superficies nuevas van a
reportar mal el estado de este propio repo desde el día uno, y el punto ciego de
cobertura de drift se arrastra a la v0.3.

Nota: este fix corrige el estado presente, no instala un mecanismo que mantenga
`control.json` sincronizado indefinidamente — `regenerar_control()` queda disponible
como función reutilizable para la próxima vez que haga falta recalibrar, pero nadie la
invoca automáticamente todavía.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
- `generar_control()` sin `fecha_utc` produce el mismo resultado que antes del cambio
  (no regresión).
- `regenerar_control()` con un `control_previo` de ejemplo produce `harness_version ==
  HARNESS_VERSION` actual, `fecha_utc` idéntico al de `control_previo`, y `archivos` =
  exactamente el conjunto de `manifest_para_perfil(perfil)` menos
  `.ds_init/control.json`, con sha256 reales verificables contra los archivos en
  disco.
- Test nuevo pasa en un repo git temporal, nunca sobre este repo.
- Tras aplicar `regenerar_control` sobre este repo: `.ds_init/control.json
  ["harness_version"] == "0.2.0"`, `fecha_utc` sigue siendo
  `"2026-09-09T18:08:09Z"`, `archivos` incluye los archivos agregados por
  `24c07e4`/`b653e6a`/`07f4c14` además de los 11 originales.
- `harmessi doctor` sobre este repo, después del fix: `HARMESSI-VERSION` = OK. Ningún
  check que antes era OK pasa a WARN/ERROR.
- `regenerar_control()` preserva `configuracion` exactamente (igualdad completa
  dict-a-dict contra `control_previo["configuracion"]`, no solo verificación de claves
  sueltas).
- `regenerar_control()` preserva `fecha_utc` exactamente igual al de `control_previo`.
- `regenerar_control()` actualiza `harness_version` al valor vigente de
  `HARNESS_VERSION`, incluso si `control_previo["harness_version"]` era distinto.
- `regenerar_control()` reconstruye `archivos` **exclusivamente** desde
  `manifest_para_perfil(perfil)` vigente — no es una unión con las entradas de
  `control_previo["archivos"]`.
- `regenerar_control()` **no conserva entradas obsoletas**: si
  `control_previo["archivos"]` tiene una entrada cuya ruta ya no aparece en el
  manifiesto vigente, esa entrada debe estar ausente del resultado.

## Decisión técnica (design-lite — solo SDD abreviado)
Reutilizar `generar_control()` existente en vez de duplicar la lógica de
hashing/escritura de JSON — `regenerar_control()` es un wrapper delgado que arma
`archivos_aplicados` desde el manifiesto vigente y delega el resto. Alternativa
descartada: script ad-hoc de un solo uso (no versionable, no testeable, no
reinvocable si vuelve a driftear). Alternativa descartada: implementar el comando
`update` completo de R15 — sobredimensionado para este fix puntual, corresponde a un
track separado si se decide más adelante.

## Aprobación
- Usuario: pendiente
- Fecha: pendiente
- Alcance aprobado: pendiente
- Versión de artefactos referenciada: pendiente
- Cita o descripción fiel de qué se aprobó: pendiente — el usuario revisa este
  `proposal.md` antes de continuar.

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
