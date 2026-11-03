# Verificación — 20260928-source-neutral-data-access

## Resumen ejecutivo

Change 1 de v0.8 (SDD aprobado por el autor, 2026-09-29) implementa el contrato neutral de fuentes
(`tools/datasources/`), el bridge `profile.json` → `SourceObservation`, el evaluador único de
Data Contracts sobre observación (M1) con wrappers v0.7 que conservan firma/comportamiento, el CLI
`ds_guard source ...` / `contract validate --observation`, y el manifiesto/documentación de
arquitectura correspondientes. Se construyó primero un corpus dorado determinista (114 casos) del
evaluador v0.7 ANTES de tocar `validation.py`, y se validó paridad exacta del evaluador nuevo contra
ese corpus. La regresión completa final corre en verde: `2820 passed, 10 skipped, 1092 subtests
passed`, exit code 0. Dos rondas de revisión de `data-science-reviewer` cubrieron el 100% de los
módulos nuevos/tocados; encontraron 2 hallazgos IMPORTANTES (ninguno BLOQUEANTE), ambos corregidos y
re-verificados. Se documentan cinco desvíos/aclaraciones de implementación (a)-(e), ninguno relaja un
criterio de cierre del roadmap ni un requisito de `spec.md`.

**Change 1 cumple R1-R40 con las aclaraciones y correcciones documentadas** (ver "Resultado final").

## Commits del Change (orden, rama `v0.8-dev`)

| Commit | Qué aportó |
|---|---|
| `931532e` | T0 — corpus dorado v0.7: 114 casos deterministas, `sha256` verificado idéntico en dos corridas. Anterior a cualquier cambio a `validation.py` (condición de R34(a)). |
| `39f09e4` | T1-T4 — paquete `tools/datasources` (`core.py`, `scan.py`, `registry.py`, `runtime.py`, `profile_bridge.py`, `file_observer.py`): 125 tests. |
| `ef5ba30` | T5 — evaluador único sobre `SourceObservation` en `tools/datacontracts/validation.py` + `legacy_wording.py`: 182 tests de `datacontracts`, paridad exacta contra los 114 casos del golden. |
| `90792a4` | T6 — CLI `ds_guard source ...` y `contract validate --observation`: 47 tests de `ds_guard`/`contract`/`source`. Bug real encontrado y corregido: `source_id="__legacy__"` inválido contra `SOURCE_ID_PATTERN` colapsaba todo a `CONTRACT-EVIDENCE-MISSING`. |
| `f628f5b` | T7 — manifiesto, tests de repo, `ARCHITECTURE.md`: 22 tests nuevos. Bug real encontrado y corregido: el evaluador nativo reconstruía el dtype legacy desde `FieldObservation.native_type` en vez de `type_family`, rompiendo `CONTRACT-TYPE-MISMATCH` en observaciones no provenientes del bridge de archivos. |
| `d98dc94` | Correcciones de la primera revisión: (1) `scan.py` propagaba la exención de claves hash/sha/fingerprint más allá del hijo inmediato — hueco de seguridad real en el gate R19/R20, corregido a exención de un solo nivel; (2) faltaba la rama WARN de R30 para observación `type_family="unknown"` con contrato de `type_family` mapeada, daba FAIL en vez de WARN — agregado post-proceso sin tocar `_regla_type_mismatch`. |
| `cb0f23e` | Actualización de `tools/tests/test_v07_validation_neutrality.py` (test v0.7 pre-existente que codificaba la frontera de imports ANTERIOR a Change 1) para reflejar la excepción de M1 (`datasources` y `.legacy_wording`) sin relajar la detección de imports genuinamente prohibidos. |

## Resultado por requisito (R1-R40)

Agrupado por sección de `spec.md`.

### §1 Paquete y dependencias (R1-R3)

Paquete `tools/datasources/` con la separación de módulos exacta de R1 (core solo-stdlib; `scan`,
`registry`, `profile_bridge` puros sobre dicts; `runtime` con I/O e `importlib`; `file_observer` con
import perezoso de `ds_profile`), verificado por `tools/tests/test_v08_datasources_neutrality.py`
(T7.2, commit `f628f5b`), patrón `ast` análogo a `test_v07_validation_neutrality.py` /
`test_v08_autonomy_neutrality.py`. Dirección de dependencias (R2) — ningún paquete de `dsguard`,
`ds_profile`, `dsimpact`, `reporting`, `providers`, `routing`, `fallback`, `harmessi_bench`,
`modelquality`, `qualityevidence`, `autonomy` importa `datasources`; única excepción enumerada por
nombre de archivo, `tools.datacontracts.validation`/`legacy_wording.py` — cubierta por el mismo test
y por `cb0f23e` (actualización de la frontera de imports v0.7 preexistente para reflejar la
excepción). Neutralidad tecnológica del core (R3, `source_kind` no ramificado) verificada por el
mismo test `ast` sobre `core.py`. **Cumplido.**

### §2 Tipos y serialización (R4-R9)

Tipos frozen `SourceRef`, `SourceCapabilities`, `ObservationRequest`, `FieldObservation`,
`SourceProvenance`, `SourceObservation`, `SourceError` implementados en `core.py` (commit `39f09e4`,
T1.1-T1.3) con los patrones exactos de R4 (`SOURCE_ID_PATTERN`, `role`, `observer`, `access_mode`
solo `read` con `write` reservado, `sensitivity`, `config_ref`, `options` acotadas). Serialización
determinista, `canonical_json`, `content_sha256` que excluye únicamente `provenance.generated_at`
(R7), registro único de códigos `SOURCE-*` (R9, `CODES`), cubiertos por los 125 tests de
`tools/datasources` del commit `39f09e4` (T1.4, incluye round-trip de bytes, hash sin
`generated_at`, ausencia != 0, rechazo de `execute_query`/claves de consulta, unicidad de códigos,
test `ast` de solo-stdlib de `core.py`). `SourceError` (R8) como excepción de `core` que no escapa de
los puntos de entrada de `runtime`/evaluador. **Cumplido.**

### §3 Capacidades (R10-R11)

`SourceCapabilities` en dos ejes (`facets`/`operations`), `access_ceiling = read`, `execute_query`
fuera del vocabulario (`SOURCE-CAPABILITIES-INVALID`); `ObservationRequest` sin texto de consulta
(`SOURCE-OBSERVATION-INVALID` ante clave desconocida). Cubiertos por T1 (`core.py`) y T3.6 (tests de
`runtime` con capacidades inválidas), dentro de los 125 tests de `39f09e4`. **Cumplido.**

### §4 Registro (R12-R14)

`.harmessi/sources.json` como archivo del proyecto (no en el manifiesto ni en
`control.json["archivos"]`) verificado por T7.1/T7.2 (commit `f628f5b`). `check_registry` estático
(R13) sin importar código del proyecto, probado con módulo señuelo que deja huella al importarse
(T3.1/T3.6, commit `39f09e4`): tras `check_registry` el archivo señuelo no existe y `sys.modules` no
gana el módulo. `resolve_observer_file` (R14) puro salvo `Path.exists` inyectable, rechaza `..`,
rutas absolutas y separadores (T2.2/T2.3). **Cumplido.**

### §5 Observer y runtime (R15-R18)

Contrato de observer en frontera JSON (R15) verificado con observer de prueba en memoria (T3.6).
`observe_source` (R16) con el orden obligatorio de 9 pasos implementado en `runtime.py` (T3.2-T3.4,
commit `39f09e4`); test con `access_check` espía que verifica que el import del módulo señuelo no
ocurre si `access_check` deniega, test de observer que lanza, test de módulo inexistente (T3.6). Sin
timeout en proceso (R17) documentado explícitamente como límite honesto (ver "Desvíos/aclaraciones
(e)" y "Límites y pendientes"); `design.md` y la ayuda del CLI lo enuncian (cubierto en T6.2/T6.4,
commit `90792a4`). Exactitud pedida (R18): facetas `approximate` descartadas con WARN cuando se pide
`exact` (T3.4). **Cumplido**, con R17 como límite declarado (no defecto).

### §6 Secretos y portabilidad (R19-R20)

`scan.py` (`scan_secrets`, `scan_locators`) con tabla de positivos/negativos (T2.1, commit `39f09e4`)
y gate antes de persistir (R20) que corre sobre `observation.to_dict()` completo (T3.4, T3.6:
`native_type` con ruta absoluta o DSN → nada persistido). Corrección real de seguridad en `d98dc94`:
la exención original de claves hash/sha/fingerprint en `scan.py` se propagaba más allá del hijo
inmediato (hueco real en el gate R19/R20), corregida a exención de un solo nivel — ver "Desvíos
(d)". **Cumplido** (con la corrección aplicada y re-verificada en la regresión final).

### §7 Provenance, sensibilidad y persistencia (R21-R23)

Hash del código del observer (R21, `observer_code_sha256`, LF normalizado, `null` +
`SOURCE-OBSERVER-CODE-UNHASHABLE` sin archivo) y sensibilidad (R22, omisión de
`value_distribution`/`value_range`/`time_range` para `sensitive` con `omitted_facets` + WARN, nunca
en silencio) implementados en `runtime.py` (T3.3-T3.4). Persistencia atómica idempotente (R23,
`observation_id = <source_id>__<12hex>`, archivo temporal + `os.replace`) cubierta por T3.4/T3.6,
dentro de los 125 tests de `39f09e4`. **Cumplido.**

### §8 Sellado y control de acceso (R24-R25)

`access_check` real compuesto en `tools/ds_guard.py` (R24: `cargar_config` fail-closed,
`parse_autonomy_policy`, `effective_source_access`, `is_source_sealed`) implementado en T6.1 (commit
`90792a4`), con tests de sellado end-to-end: sellada por `source_id` aunque el registro la declare →
`SOURCE-SEALED` sin importar el observer señuelo; guardrails corrupto → denegado; `autonomy` presente
sin paquete → denegado (T6.4, dentro de los 47 tests de CLI). `datasources` no importa `autonomy` ni
`pathguard` (R25): `access_check` es parámetro obligatorio, sin él `observe_source` falla cerrado con
`SOURCE-ACCESS-DENIED` — verificado por el mismo test de neutralidad de R1-R2 y por T3.6. **Cumplido.**

### §9 Frescura (R26)

`compare_fingerprint` pura con los 6 casos de la tabla (igual, distinto, falta en stored, falta en
fresh, algoritmo distinto, `as_of` distinto con igual fingerprint) — T3.5, commit `39f09e4`.
**Cumplido.**

### §10 Bridge `profile.json` → observación (R27-R28)

`profile_bridge.profile_to_observation` (R27) pura, con el mapeo dtype→familia exacto, lectura
tolerante `seed`/`semilla`, `null` para rango observado y vacío, sin copiar `dataset_path` ni
`tamano_bytes`, `SourceError` sin forma mínima — T4.1, commit `39f09e4`. `file_observer` (R28) único
observer incluido, import perezoso de `ds_profile`, guard de holdout (`verificar_permitido`) — T4.2,
con tests contra un CSV pequeño real de `ds_profile` (T4.3). **Cumplido.**

### §11 Evaluador único y paridad (R29-R35) — núcleo del criterio de cierre M1

`validate_contract_observation` (R29) en `tools/datacontracts/validation.py`, nativo sobre
`SourceObservation`/dict, sin I/O, nunca lanza, con el orden de `CheckResult` de v0.7 preservado —
commit `ef5ba30` (T5.2-T5.3), 182 tests de `datacontracts`. Reglas sobre facetas (R30, matriz por
regla × exactitud × presencia de faceta, faceta no observada nunca produce PASS) y evidencia
"observado y vacío" (R31) cubiertas por la misma suite; la rama WARN faltante para
`type_family="unknown"` observado con contrato mapeado (parte de R30) fue detectada en la revisión y
corregida en `d98dc94` — ver "Desvíos (c)". Wrappers v0.7 (R32, `validate_contract` /
`validate_contract_against_profile_file` conservan firma, códigos, orden y comportamiento;
`verificar_permitido` antes de abrir el archivo; sin lógica de reglas en los wrappers, verificado por
test `ast`) y catálogo `wording` (R33, `NEUTRAL`/`LEGACY_PROFILE` en `legacy_wording.py`) —
T5.1/T5.4/T5.5.

**R34 (paridad exacta, criterio de cierre no negociable de M1):** corpus dorado generado ANTES de
tocar `validation.py` (commit `931532e`, T0, 114 casos deterministas, `sha256` verificado idéntico en
dos corridas), commiteado antes del refactor del evaluador (`ef5ba30`) — orden confirmado por `git
log --oneline --reverse`. `test_parity_golden.py` compara el wrapper nuevo contra el golden con
igualdad exacta de `to_dict()` para todos los casos, dentro de los 182 tests de `datacontracts` de
`ef5ba30`. **Cumplido**, con verificación explícita de orden de commits documentada por el Lead.

**R35 (divergencias declaradas):** las tres divergencias (a: faceta ausente da WARN en vez de
PASS/FAIL heredado de v0.7 por evidencia ausente; b: dtype `unknown` fuera de los 5 valores da WARN
"no clasificable" en vez de FAIL; c: campo en `schema` sin entrada en `columnas_detalle` da WARN en
vez de FAIL) están fijadas por `test_divergencias_declaradas.py` (T5.5) y confirmadas contra los
fixtures existentes en T0.4 sin que ninguna apareciera de forma inesperada. **Cumplido.**

### §12 CLI (R36-R37)

`ds_guard source list|check|observe|check-stale` (R36) con `--json`, exit codes 0/1/2/3, imports
perezosos — T6.2, commit `90792a4`; ayuda del CLI menciona "best-effort" (R19) y "sin timeout en
proceso" (R17) por T6.2/T6.4. Durante esta invocación se encontró y corrigió el bug real de
`source_id="__legacy__"` inválido contra `SOURCE_ID_PATTERN` (colapsaba todo a
`CONTRACT-EVIDENCE-MISSING`) — ver tabla de commits. `contract validate --observation` (R37) aditivo
y mutuamente excluyente con `--profile` (exactamente uno; ninguno o ambos → exit 2), `--record-evidence`
con `fuente_role="observation"`, comportamiento `--profile` intacto (tests existentes de `contract
validate` pasan sin editar) — T6.3/T6.4, dentro de los 47 tests de CLI. **Cumplido** (con el bug real
encontrado y corregido dentro de la misma invocación, antes de la revisión formal).

### §13 Instalabilidad y arquitectura (R38-R40)

Manifiesto (R38): entradas VERBATIM para el paquete `datasources` en `stage_minimo=discovery`,
`file_observer.py` en `experiment`, `datacontracts/legacy_wording.py` en `discovery` — T7.1, commit
`f628f5b`, verificado por `python -m tools.ds_init.check_manifest_parity` → `[OK] Todas las rutas
VERBATIM del manifiesto existen`, exit 0. Tests de repo (R39):
`tools/tests/test_v08_datasources_neutrality.py`, `tools/tests/test_v08_source_id_parity.py`,
actualización de `tools/tests/test_architecture_boundaries.py` (`MODULOS_CORE`) — T7.2/T7.3, dentro
de los 22 tests nuevos de `f628f5b`. Documentación (R40): `ARCHITECTURE.md` con filas en §2.1, regla
11 para `tools/datasources`, excepción de `tools.datacontracts`, ajuste de §6 — T7.4;
`docs/roadmap/v0.8.md` con Change 1 tildado en esta misma invocación de cierre. **Cumplido.**

## Ejecución real (corrida por el Lead, 2026-09-29)

- **Regresión completa final** (`.venv/Scripts/python -m pytest tools -q`): `2820 passed, 10 skipped,
  1092 subtests passed in 1801.66s (0:30:01)`, exit code 0, CERO fallas. Una corrida intermedia
  previa a las correcciones de revisión dio `2818 passed, 1 failed` — la falla era exactamente el
  test de neutralidad v0.7 corregido en `cb0f23e`; quedó resuelta y re-verificada en la corrida
  final.
- **Paridad de manifest** (`python -m tools.ds_init.check_manifest_parity`): `[OK] Todas las rutas
  VERBATIM del manifiesto existen`, exit 0.
- Conteos de tests por commit (evidencia de cobertura por bloque, no una corrida separada): 114 casos
  del golden v0.7 (`931532e`); 125 tests de `tools/datasources` (`39f09e4`); 182 tests de
  `tools/datacontracts` con paridad exacta contra los 114 casos del golden (`ef5ba30`); 47 tests de
  `ds_guard`/`contract`/`source` (`90792a4`); 22 tests nuevos de repo/manifiesto/documentación
  (`f628f5b`).

## Proceso de revisión (2 rondas) y disposición de hallazgos

Dos invocaciones de `data-science-reviewer`, sin solapamiento de alcance:

- **Primera ronda**: cortó por límite de turnos; cubrió `core.py`, `runtime.py`, `scan.py`,
  `profile_bridge.py`, `validation.py`, `ds_guard.py` (`_access_check_real`, `cmd_source_*`,
  `contract validate`), `autonomy/policy.py`, `pathguard.py`.
- **Segunda ronda**: cubrió lo que la primera no llegó a leer: `registry.py`, `file_observer.py`,
  `legacy_wording.py`, `build_golden_v07.py`, el manifiesto, `ARCHITECTURE.md`, y las suites de test
  restantes.

**Veredicto combinado: sin hallazgos BLOQUEANTES.** No se encontró ningún fail-open de seguridad en
`_access_check_real`; el sellado por `source_id` deniega ANTES de importar el observer en todos los
caminos trazados; el observer nunca se importa en la resolución estática del registro; la ruta local
nunca aparece en ninguna observación persistida; el guard de holdout corre antes de leer cualquier
archivo.

**2 hallazgos IMPORTANTES, ambos corregidos y re-verificados** (commit `d98dc94`):

1. `scan.py` propagaba la exención de claves hash/sha/fingerprint más allá del hijo inmediato —
   hueco de seguridad real en el gate R19/R20; corregido a exención de un solo nivel.
2. Faltaba la rama WARN de R30 para observación `type_family="unknown"` con contrato de
   `type_family` mapeada: daba FAIL en vez de WARN; agregada como post-proceso
   (`_reclasificar_type_mismatch_unknown_observado`) sin tocar `_regla_type_mismatch`, verificado que
   no rompe paridad porque el bridge nunca produce esa combinación.

**Hallazgos MENORES, sin acción requerida** (documentados por el Lead en el chat, no bloquean
cierre): doble lectura redundante de `guardrails.json` en `_access_check_real` (no es fallo de
seguridad, solo oportunidad de simplificación); comentario desactualizado en `runtime.py` sobre
agrupación de pasos.

## Desvíos y aclaraciones de implementación

`proposal.md`, `spec.md` y `design.md` quedan sin modificar por estar aprobados por hash; se
registran acá como enmiendas de implementación. Ninguna relaja un criterio de cierre de `spec.md` ni
del roadmap.

- **(a) Estrategia A confirmada** (adaptador "bridge inverso" `_observation_como_profile_like`, sin
  tocar ninguna `_regla_*` de v0.7): permitió reutilizar el 100% del motor de reglas ya probado por
  825 líneas de tests existentes, a costa de que el evaluador "nativo" en realidad pasa por una
  reconstrucción intermedia con forma de perfil legacy — documentado extensamente en el docstring de
  esa función.
- **(b) Bug de `native_type` vs `type_family` (corregido en `d98dc94`, encontrado originalmente en
  T6):** el diseño original de T5 reconstruía el dtype legacy desde `native_type` (etiqueta arbitraria
  para observers no-`file_observer`), lo cual funcionaba para el corpus v0.7 (siempre pasa por el
  bridge) pero rompía `CONTRACT-TYPE-MISMATCH` para cualquier observación nativa real. Corregido para
  derivar del `type_family` (la autoridad neutral real), vía el mapeo inverso exacto del bridge —
  biyectivo sobre los 5 dtypes legacy, sin alterar ningún resultado del golden.
- **(c) R30 "unknown" observado + contrato mapeado:** ahora da WARN "no clasificable" vía
  post-proceso `_reclasificar_type_mismatch_unknown_observado`, distinto del caso ya existente donde
  el CONTRATO declara `type_family="unknown"` (ese sigue dando N/A, comportamiento heredado de v0.7
  sin cambios).
- **(d) Scan de secretos (R19):** confirmado por patrón, best-effort, con exención de UN SOLO NIVEL
  para claves nombradas hash/sha/fingerprint (nunca hereda a nietos). Sigue siendo un límite
  declarado, no una garantía exhaustiva — la garantía fuerte sigue siendo `pathguard` (`.env`/claves)
  y que el observer maneje credenciales.
- **(e) Sin timeout en proceso (R17, M6 del roadmap):** `observe_source` no implementa timeout; un
  observer colgado bloquea el proceso que lo invoca. Documentado como límite honesto, a resolver por
  el runtime de ejecución del Change 2.

Adicionalmente:

- **Verificación de orden de commits (M1/paridad):** confirmado por `git log --oneline --reverse` que
  T0 (generación del golden) se commiteó ANTES que T5 (refactor de `validation.py`) — la paridad se
  validó contra el código v0.7 real, no contra una reconstrucción posterior.
- **Decisión de simplificación de R33 (catálogo `wording`):** confirmada y aceptada por el Lead
  durante el cierre de T5 (documentada en `legacy_wording.py`): el catálogo `LEGACY_PROFILE` solo
  cubre los 2 mensajes nuevos del gate de forma de `validate_contract_observation`; las reglas
  heredadas de v0.7 (Estrategia A) emiten su texto verbatim de siempre, sin distinguir wording — es
  una simplificación frente a la letra de R33 que prioriza R34 (paridad exacta, el criterio no
  negociable), sin tocar ningún criterio de STOP material del contrato de autonomía de
  `docs/roadmap/README.md`.

## Límites y pendientes

**Change 3**
- Integración de `harmessi source observe`/CLI en el ciclo autónomo de ejecución del Lead.
- Enforcement de `session_budget`/`aggregate_budget` aplicado también a observaciones de fuente.

**Change 4**
- Check dedicado de Doctor para el registro `.harmessi/sources.json` (hoy `check_registry` es una
  función reutilizable, no integrada a `harmessi doctor`).
- Integración con el instalador (el registro del proyecto NO es un archivo administrado, por diseño,
  para no producir `HARMESSI-DRIFT`).
- Diagnóstico del modo efectivo de autonomía combinado con fuentes.

**Fuera de alcance explícito de Change 1** (según `proposal.md`): conectores a cualquier base/API/
nube, ORM o SQL en el core, DSL de consultas, extensión de `ds_profile` a fuentes no-archivo, gestor
de secretos, SDK/generador de observers, sandbox, timeouts en proceso, escrituras a fuentes.

**Sin sandbox:** un observer en proceso comparte permisos con el proceso que lo carga; Harmessi no
puede detectar writes a una base/API hechos por fuera de las interfaces gobernadas (límite ya
documentado en el roadmap v0.8, "Límites honestos").

## Resultado final

**Change 1 cumple R1-R40 con las aclaraciones y correcciones documentadas.**
