# Tareas — 20260922-quality-evidence-and-drift

estado: cerrada

## Invocaciones planificadas
1. `python-data-engineer` (writer, esta invocación) — redacta los 4 artefactos SDD (`proposal.md`,
   `spec.md`, `design.md`, `tasks.md`). No escribe código, no toca `control.json`. El Lead revisa,
   decide sobre los supuestos/dudas señalados en el reporte de cierre (en particular la decisión 2
   de `design.md`: NO importar `tools.reporting.evidence` en ninguna dirección, reimplementación
   local de hash/manifest; el nombre `tools/qualityevidence`; la convención
   `"quality:<ruta>"` para `resolve_evidence_ref`; el allowlist acotado de
   `_CAMPOS_NUMERICOS_PERMITIDOS` de `drift_from_profiles`) y, si aprueba, declara el alcance de la
   invocación 2 en `control.json` (`alcance.rutas_autorizadas`) antes de aprobarla.
2. `python-data-engineer` (writer, implementación) — implementa
   `tools/qualityevidence/__init__.py`, `core.py`, `evidence.py`, los tests
   (`tools/qualityevidence/tests/`), `tools/tests/test_v07_qualityevidence_neutrality.py`, las dos
   líneas en `MODULOS_CORE` de `tools/tests/test_architecture_boundaries.py`, las tres entradas de
   `MANIFEST` y las dos filas + regla 9 de `ARCHITECTURE.md`. No ejecuta nada (sin herramienta de
   ejecución); avisa al Lead exactamente qué debe correr. Alcance EXACTO de rutas autorizadas para
   esta invocación (ninguna otra ruta se toca sin volver a este documento y pedir ampliación al
   Lead):
   - `tools/qualityevidence/__init__.py`
   - `tools/qualityevidence/core.py`
   - `tools/qualityevidence/evidence.py`
   - `tools/qualityevidence/tests/__init__.py`
   - `tools/qualityevidence/tests/test_core.py`
   - `tools/qualityevidence/tests/test_evidence.py`
   - `tools/qualityevidence/tests/test_installability.py`
   - `tools/tests/test_v07_qualityevidence_neutrality.py`
   - `tools/tests/test_architecture_boundaries.py`
   - `tools/ds_init/manifest.py`
   - `ARCHITECTURE.md`
   - `openspec/changes/20260922-quality-evidence-and-drift/proposal.md`
   - `openspec/changes/20260922-quality-evidence-and-drift/spec.md`
   - `openspec/changes/20260922-quality-evidence-and-drift/design.md`
   - `openspec/changes/20260922-quality-evidence-and-drift/tasks.md`

   Deliberadamente NO incluye ningún archivo de `tools/datacontracts/`, `tools/modelquality/` ni
   `tools/reporting/` (Changes 0-2 y v0.6 Change 3-4, todos cerrados) — si la implementación
   descubriera una necesidad real de tocar algo ahí, corresponde señalarlo al Lead como duda antes
   de escribir, no asumir el permiso de este alcance. Tampoco incluye `docs/roadmap/v0.7.md`
   (se toca solo en la invocación 5, al cierre).
3. Lead — corre los tests nuevos y la suite completa (incluye
   `tools/qualityevidence/tests/`, `tools/tests/test_v07_qualityevidence_neutrality.py`,
   `tools/tests/test_architecture_boundaries.py`, `tools/tests/test_v05_core_neutrality.py`,
   `tools/tests/test_v06_core_neutrality.py`, `tools/tests/test_v07_core_neutrality.py`,
   `tools/tests/test_v07_validation_neutrality.py`,
   `tools/tests/test_v07_modelquality_neutrality.py`, `tools/datacontracts/tests/`,
   `tools/modelquality/tests/` (regresión, deben seguir verdes sin ningún diff en esos paquetes),
   `tools/reporting/tests/` (regresión, sin diff), `tools/ds_init/tests/`) y
   `python -m tools.ds_init.check_manifest_parity`; entrega los resultados reales.
4. `data-science-reviewer` — revisa el diff completo (SDD + implementación), solo lectura. Presta
   especial atención a: (a) que `tools/qualityevidence/core.py` sea solo-stdlib y no importe
   `tools.datacontracts`/`tools.modelquality`/`tools.reporting`/`dsguard`/`ds_profile` en ningún
   caso; (b) que `tools/qualityevidence/evidence.py` aplique
   `ds_profile.holdout_guard.verificar_permitido` a TODA ruta de `profile.json` antes de abrirla
   (tanto en `describe_source_file` como en `drift_from_profiles`, incluidas AMBAS rutas de una
   comparación de drift), sin excepción y sin bypass; (c) que `content_sha256()` de
   `QualityEvidenceManifest`/`DriftEvidence` realmente excluya `generated_at` (test de
   reproducibilidad real, no solo revisión de código); (d) que `DriftEvidence.result_status` nunca
   sea `PASS`/`FAIL` cuando `threshold is None` (siempre `N/A` en ese caso); (e) que
   `write_manifest` escriba de forma atómica y nunca deje un `manifest.json` parcial ante una
   interrupción simulada; (f) que ningún `EvidenceSource.path`/mensaje de error contenga una ruta
   absoluta local; (g) que `tools/datacontracts/{core,validation}.py`,
   `tools/modelquality/{core,validation}.py` y `tools/reporting/*` no tengan ningún diff.
5. `python-data-engineer` (writer, cierre) — aplica fixes de la revisión, escribe
   `verification.md` con la evidencia real del Lead, tilda `[x] Change 3` en
   `docs/roadmap/v0.7.md` y deja `estado: en_verificacion`.

## Tareas
- [x] `proposal.md` (esta invocación).
- [x] `spec.md` (esta invocación).
- [x] `design.md` (esta invocación).
- [x] `tasks.md` (esta invocación).
- [x] `tools/qualityevidence/__init__.py` mínimo (sin lógica ni imports de hermanos).
- [x] `tools/qualityevidence/core.py`: vocabularios, `SCHEMA_VERSION`, `QualityEvidenceError`,
      validadores de id (`evidence_id`/`drift_id`, patrones propios de R3) y de `metric_name`
      (implementación propia, no importada de `tools.modelquality.core`), normalización JSON-segura
      con copia profunda (ver `spec.md` R2-R6).
- [x] `core.py`: `EvidenceSource`, `DeclarationRef`, `ScopeWindow`,
      `QualityEvidenceManifest` (validación de forma de `check_results`/`technical_errors`, R7),
      `DriftEvidence` (R8).
- [x] `core.py`: `to_dict()`/`from_dict()` por dataclass, `canonical_json`,
      `content_sha256()` de `QualityEvidenceManifest` y de `DriftEvidence` (excluyendo
      `generated_at`, R10).
- [x] `tools/qualityevidence/evidence.py`: constante `CODES` (8 códigos, R11), hash sha256 chunked
      local (R12), escritura atómica local (R12), `describe_source_file`/
      `describe_source_generated` (R13), `new_evidence_id`/`new_drift_id` locales,
      `build_manifest` (R14), `write_manifest`/`read_manifest` (R15/R16),
      `build_drift_evidence` (R17), `drift_from_profiles` con el allowlist
      `_CAMPOS_NUMERICOS_PERMITIDOS` y el guard simétrico sobre ambas rutas (R18),
      `resolve_evidence_ref` (R19).
- [x] `tools/qualityevidence/tests/__init__.py` y `test_core.py` (ids, `metric_name`, las dos
      formas de `EvidenceSource` (`file`/`generated`) válidas e inválidas, `ScopeWindow` con
      ventana inconsistente, forma cerrada de `check_results`/`technical_errors`,
      serialización/hash con y sin variar `generated_at`, copia profunda, ausencia de parámetros
      de datos reales en cualquier constructor).
- [x] `tools/qualityevidence/tests/test_evidence.py`: fixtures sintéticas de `profile.json`
      (`tempfile`, nunca un dataset real) y de `guardrails.json` con un holdout de prueba; los 8
      códigos con caso positivo y caso de violación; `write_manifest`/`read_manifest`
      round-trip e idempotencia; el caso de manifest manipulado a mano (`QUALITYEVIDENCE-READ`);
      las dos fórmulas de `comparison_mode` con caso `PASS`/`FAIL`/`N/A` (sin threshold) cada una,
      más el caso `baseline_value == 0` bajo `relative_diff`; `drift_from_profiles` con field fuera
      de allowlist y con una ruta denegada por el guard de holdout (spy verificando que NINGÚN
      archivo se abrió); `resolve_evidence_ref` con las 3 variantes (no sigue convención, sigue y
      resuelve, sigue y no resuelve).
- [x] `tools/qualityevidence/tests/test_installability.py` (entradas de `MANIFEST` presentes,
      VERBATIM, `discovery`, fuentes existentes).
- [x] `tools/tests/test_v07_qualityevidence_neutrality.py` (patrón `ast`, cubriendo AMBOS módulos:
      imports permitidos de `core.py` y de `evidence.py` por separado, sin
      `tools.datacontracts`/`tools.modelquality`/`tools.reporting`/`ds_profile.fingerprint`/
      `dsguard` (salvo `dsguard.checks` en `evidence.py`) en ninguno; dirección inversa: `dsguard`,
      `ds_profile`, `dsimpact`, `reporting`, `tools.datacontracts`, `tools.modelquality`,
      `providers`, `routing`, `fallback`, `harmessi_bench` no importan `tools.qualityevidence`).
- [x] `tools/tests/test_architecture_boundaries.py`: agregar `tools/qualityevidence/core.py` y
      `tools/qualityevidence/evidence.py` a `MODULOS_CORE`.
- [x] `tools/ds_init/manifest.py`: tres entradas VERBATIM; leer antes
      `tools/ds_init/tests/test_manifest.py`, `tools/tests/test_manifest_dsguard_parity.py`,
      `tools/ds_init/tests/test_control_file.py` y `tools/harmessi/tests/test_doctor.py` (usos de
      `MANIFEST`) y mantenerlos verdes sin editarlos (si fuera inevitable, listar la edición mínima
      en el alcance antes de hacerla).
- [x] `ARCHITECTURE.md`: dos filas en §2.1 y regla 9 en §3 (texto exacto en `design.md`).
- [x] `verification.md` (invocación 5).
- [x] Tildar `[x] Change 3` en `docs/roadmap/v0.7.md` (invocación 5; nada más del roadmap se
      toca).

## Dependencias
- Change 0 (`data-contracts-core`), Change 1 (`data-contract-validation`) y Change 2
  (`model-quality-policies`), cerrados: este Change NO consume ningún tipo de
  `tools.datacontracts`/`tools.modelquality` en su código (familia independiente, ver `design.md`
  decisión 1 y "Supuestos descartados" de `proposal.md`) — la dependencia es de PRECEDENTE de
  patrón (dataclass `frozen=True`, `canonical_json`/`content_sha256`, no-import entre familias con
  duplicación documentada de vocabularios pequeños) y de PUNTO DE CONEXIÓN explícito
  (`ObservedMetric.evidence_ref`, resuelto por convención externa en `resolve_evidence_ref`, sin
  tocar Change 2).
- v0.6 Change 3 (`report-evidence-and-validation`, `tools/reporting/evidence.py`), cerrado: lectura
  completa como referencia de diseño (ver `design.md` decisión 2), sin importarlo ni modificarlo.
- Lectura (no modificación) de `tools/dsguard/checks.py` (vocabulario `CheckResult`),
  `tools/dsguard/mlops_evidence.py` (precedente de duplicación local de hash),
  `tools/ds_profile/holdout_guard.py` (`verificar_permitido`), `tools/ds_profile/fingerprint.py`
  (`ALGORITMO`, valor reutilizado como constante documentada, sin import),
  `ARCHITECTURE.md` (reglas 6-8, precedente directo de la regla 9 nueva).
- Change 4 (`quality-integration-and-cli`) depende de este: consumirá
  `QualityEvidenceManifest`/`DriftEvidence`/`build_manifest`/`write_manifest`/`read_manifest`/
  `drift_from_profiles`/`resolve_evidence_ref` desde una futura CLI (`harmessi quality ...`), y
  decidirá cómo (o si) exponer `resolve_evidence_ref` como parte de la integración con `status`.
  Change 5 (hardening) depende de este para sus fixtures de "reproducibilidad de la evidencia de
  calidad" y "comportamiento con evidencia faltante/stale" del roadmap.
- Alcance a autorizar en `control.json` (`alcance.rutas_autorizadas`) para la invocación 2: ver la
  lista exacta dentro de "Invocaciones planificadas", punto 2 (idéntica, no se repite acá para
  evitar que las dos listas diverjan).

## Próximo paso exacto
El Lead revisa estos 4 artefactos contra `docs/roadmap/v0.7.md` (en particular la sección Change 3,
líneas 297-346, y la decisión 6, líneas 102-104), `ARCHITECTURE.md`, `tools/reporting/evidence.py` y
el precedente de `tools/datacontracts`/`tools/modelquality`, decide sobre los supuestos/dudas
señalados en el reporte de cierre de esta invocación (en particular la decisión 2 de `design.md`:
NO importar `tools.reporting.evidence` en ninguna dirección) y, si los aprueba, declara el alcance
de la invocación 2 en `control.json` y la aprueba (`ds_guard approve`). Invocación 2: un writer
implementa el código y los tests según `spec.md` R1-R25, sin ejecutar nada, y avisa al Lead qué debe
correr. (Estado: `propuesta_pendiente`, no `pausada_bloqueada`.)
