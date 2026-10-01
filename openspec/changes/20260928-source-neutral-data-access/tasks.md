# Tareas — 20260928-source-neutral-data-access

estado: cerrada

## Invocaciones planificadas

Convenciones: el `python-data-engineer` no ejecuta nada; el Lead ejecuta scripts y tests. Cada
invocación de implementación toca solo los archivos listados. Ninguna empieza antes de la
aprobación humana de `proposal.md`.

1. **Este SDD** (`python-data-engineer`): redacta `proposal.md`, `spec.md`, `design.md`,
   `tasks.md`. Sin código. Salida: estos cuatro archivos. **Hecha con esta entrega.**
2. **T0 — corpus dorado** (`python-data-engineer` escribe; **Lead ejecuta**): `build_golden_v07.py`
   y su corrida ANTES de tocar `validation.py`. Archivos: `tools/datacontracts/tests/parity/`.
3. **Núcleo `datasources`** (`python-data-engineer`): `core.py`, `scan.py`, `registry.py`,
   `__init__.py` + sus tests. Lead corre `pytest tools/datasources -q`.
4. **Runtime y bridge** (`python-data-engineer`): `runtime.py`, `profile_bridge.py`,
   `file_observer.py` + tests. Lead corre `pytest tools/datasources -q`.
5. **Refactor del evaluador** (`python-data-engineer`): `validation.py`, `legacy_wording.py` + tests
   nuevos de `datacontracts` (paridad, evaluador nativo, divergencias). Lead corre el golden test y
   `pytest tools/datacontracts -q`. Si el golden difiere en un fixture existente: STOP y reporte.
6. **CLI** (`python-data-engineer`): `tools/ds_guard.py` (comandos `source`, flag `--observation`) +
   tests de CLI. Lead corre `pytest tools/tests -k "ds_guard or contract" -q`.
7. **Manifiesto, tests de repo y documentación** (`python-data-engineer`): `manifest.py`, tests de
   neutralidad/paridad de `source_id`/boundaries, `ARCHITECTURE.md`. Lead corre
   `python -m tools.ds_init.check_manifest_parity` y los tests de repo dirigidos.
8. **`data-science-reviewer`**: revisa observer/gates de seguridad, paridad, sellado antes de
   importar, ausencia de PASS por falta de evidencia, inventario del corpus dorado.
9. **Cierre (Lead)**: suite completa (`.venv/Scripts/python -m pytest tools -q`, ~26 min) solo aquí;
   `python -m tools.ds_init.check_manifest_parity`; `verification.md`; tildar
   `docs/roadmap/v0.8.md`; resumen de qué se hizo, qué se encontró y qué queda abierto.

Las invocaciones 3-7 pueden dividirse si un archivo excede lo revisable; nunca se reescribe un
archivo grande completo: `validation.py` se cambia por bloques (gate, reglas, wrappers).

## Tareas

### T0 — Corpus dorado (antes de cualquier cambio a `validation.py`)
- [x] T0.1 Crear `tools/datacontracts/tests/parity/build_golden_v07.py`: reconstruye TODOS los
  fixtures de `test_validation.py` con los mismos helpers (`_campo`, `_contrato`, `_constraint`,
  `_col_entera`, `_col_texto`, `_col_fecha`, `_perfil`; `test_validation.py:22-99`), agrega la
  matriz sintética determinista (constraint_type × exacta/muestreada × nulos × duplicados en
  `top_valores` × campo ausente/extra × tipos × sampling), corre el evaluador v0.7 ACTUAL y
  escribe `golden_v07_validation.json` (lista completa de `CheckResult.to_dict()` por caso).
  `RANDOM_STATE` fijo si hay aleatoriedad. Sin importar `datasources`.
- [x] T0.2 Lead ejecuta el script y commitea el JSON antes de la invocación 5.
- [x] T0.3 Reviewer (o Lead) revisa el inventario de casos del corpus (cobertura de R30).
- [x] T0.4 Verificar contra fixtures existentes qué casos caen en las divergencias declaradas
  (R35); si alguno existe, escalar al Lead antes de continuar.

### T1 — `core.py`
- [x] T1.1 `SOURCE_ID_PATTERN`, patrones `role`/`observer`/`config_ref`, `SOURCE_KIND_PATTERN`.
- [x] T1.2 Tipos frozen: `SourceRef`, `SourceCapabilities`, `ObservationRequest`, `FieldObservation`,
  `SourceProvenance`, `SourceObservation`, `SourceError`; `from_dict`/`to_dict` con orden fijo.
- [x] T1.3 `canonical_json`, `content_sha256` (excluye `provenance.generated_at`), `OBSERVED_TYPE_FAMILIES`,
  vocabulario de facetas y exactitudes, `CODES` (registro único de `SOURCE-*`).
- [x] T1.4 Tests: round-trip de bytes, hash sin `generated_at`, ausencia != 0, rechazo de `execute_query`,
  rechazo de claves de consulta en el pedido, unicidad de códigos, `ast` (solo stdlib).

### T2 — `scan.py` y `registry.py`
- [x] T2.1 `scan_secrets`, `scan_locators` (R19) con tabla de positivos/negativos; el hallazgo no
  reproduce el valor.
- [x] T2.2 `registry.py`: parseo/validación de `sources.json` (schema, ids únicos, `access_mode`
  reservado, `sensitivity`, `config_ref`, `options` acotadas, `x_*`); `resolve_observer_file` con
  `exists_fn` inyectable.
- [x] T2.3 Tests: los cuatro ejemplos físicos del autor rechazados como `source_id`; `customers`
  aceptado; `write` -> `SOURCE-ACCESS-MODE-RESERVED`; módulo con `..` rechazado.

### T3 — `runtime.py`
- [x] T3.1 `load_registry`, `check_registry` (estático, sin importar código del proyecto; probar con
  módulo señuelo que deja huella al importarse).
- [x] T3.2 `observe_source` con el orden de R16; `access_check` obligatorio (falta -> denegado);
  `technical_error` para fallo de import / excepción; normalización a tipos.
- [x] T3.3 Hash del código del observer (`observer_code_sha256`, LF normalizado; `null` +
  `SOURCE-OBSERVER-CODE-UNHASHABLE` si no hay archivo).
- [x] T3.4 Sensibilidad (`omitted_facets` + WARN), exactitud pedida (R18), gate de portabilidad
  sobre la observación normalizada, persistencia atómica idempotente en
  `.harmessi/observations/<id>/observation.json`.
- [x] T3.5 `compare_fingerprint` (6 casos de R26).
- [x] T3.6 Tests con observer en memoria (sin archivos ni SQL): observación válida; excepción;
  módulo inexistente; sellada -> no importa; capacidades inválidas; faceta no declarada no se pide;
  `native_type` con ruta absoluta o DSN -> nada persistido.

### T4 — `profile_bridge.py` y `file_observer.py`
- [x] T4.1 `profile_to_observation` (R27) con lectura tolerante de `seed`/`semilla`, `null` para
  rango observado y vacío, y `SourceError` sin forma mínima.
- [x] T4.2 `file_observer` con import perezoso de `ds_profile` y guard de holdout.
- [x] T4.3 Tests: perfil completo, no copia `dataset_path`, muestreado vs exacto, fingerprint
  ausente, CSV pequeño de tests contra `ds_profile` real.

### T5 — Evaluador único y wrappers (`tools/datacontracts/`)
- [x] T5.1 `legacy_wording.py` con el catálogo `LEGACY_PROFILE` (textos v0.7 verbatim) y
  `NEUTRAL` definido en el módulo del evaluador o junto al catálogo (decidir sin nuevo módulo core).
- [x] T5.2 Refactor de `_regla_*` de `validation.py:238-719` para operar sobre observación con
  `wording`; los mensajes salen del catálogo.
- [x] T5.3 `validate_contract_observation` (nunca lanza; acepta dict u objeto).
- [x] T5.4 Reescribir `validate_contract` y `validate_contract_against_profile_file` como wrappers:
  gate legacy (`_validar_evidencia`) -> bridge -> evaluador con `LEGACY_PROFILE`; `verificar_permitido`
  antes de abrir el archivo; sin lógica de reglas en los wrappers.
- [x] T5.5 Tests nuevos: `test_parity_golden.py` (igualdad exacta), `test_observation_native.py`
  (matriz R30, nunca PASS sin faceta, sensibilidad), `test_divergencias_declaradas.py` (R35),
  `test_dual_import_identity.py`, y `ast` de que los wrappers no contienen reglas. Los tests
  existentes no se editan salvo hallazgo reportado.

### T6 — CLI en `tools/ds_guard.py`
- [x] T6.1 `access_check` real (R24): `cargar_config`, `parse_autonomy_policy`,
  `effective_source_access`, `is_source_sealed`; fail-closed (guardrails corrupto, `autonomy` sin
  paquete). Leer `policy.py:323` antes de escribirlo.
- [x] T6.2 Subcomandos `source list|check|observe|check-stale` con `--json` y exit codes 0/1/2/3.
- [x] T6.3 `contract validate --observation` mutuamente excluyente con `--profile`;
  `fuente_role="observation"` con `--record-evidence`; comportamiento `--profile` intacto.
- [x] T6.4 Tests de CLI y de sellado end-to-end (sellada por `source_id` aunque el registro la
  declare; módulo del observer no importado).

### T7 — Manifiesto, tests de repo y documentación
- [x] T7.1 `tools/ds_init/manifest.py`: entradas VERBATIM (paquete `datasources` en `discovery`,
  `file_observer.py` en `experiment`, `legacy_wording.py` en `discovery`), siguiendo el patrón de las
  entradas de `datacontracts` y `ds_profile`.
- [x] T7.2 `tools/tests/test_v08_datasources_neutrality.py` (imports por `ast`, dirección inversa
  salvo la excepción de datacontracts, `core` sin ramificar por tecnología ni `source_kind`).
- [x] T7.3 `tools/tests/test_v08_source_id_parity.py` y actualización de
  `tools/tests/test_architecture_boundaries.py` (`MODULOS_CORE`).
- [x] T7.4 `ARCHITECTURE.md`: filas en §2.1, regla 11 para `tools/datasources`, la excepción de
  `tools.datacontracts`, ajuste de la mención en §6.

### T8 — Revisión y cierre
- [x] T8.1 Revisión por `data-science-reviewer` (temas de la invocación 8).
- [x] T8.2 Lead: `python -m tools.ds_init.check_manifest_parity`.
- [x] T8.3 Lead: suite completa `.venv/Scripts/python -m pytest tools -q` (una sola vez, gate final).
- [x] T8.4 `verification.md` (con las divergencias R35 y los números de la corrida) y tildar
  `docs/roadmap/v0.8.md`.

## Dependencias

- T0 -> T5 (el golden debe existir antes de tocar `validation.py`).
- T1 -> T2 -> T3 -> T4 (T4 puede ir en paralelo con T3 tras T1).
- T4 (bridge) -> T5 (wrappers).
- T3 + T5 -> T6 (CLI).
- T6 -> T7 -> T8.
- Aprobación humana de `proposal.md` -> todo lo demás.
- Requiere Change 0 cerrado (`tools/autonomy`, `pathguard.POLICY_VERSION_MAX`).

## Próximo paso exacto

Aprobación humana de `proposal.md`; luego invocación 2 (T0): el `python-data-engineer` escribe
`build_golden_v07.py` y el Lead lo ejecuta antes de cualquier cambio a `validation.py`.
