# Propuesta — 20261026-v015-contract-stabilization

## Problema
Los contratos públicos candidatos de Harmessi no tienen una ventana de compatibilidad explícita ni
fixtures de tags reales: los 7 contratos `harmessi_improve` (candidate, probe, decision, proposal,
lesson, budget_state, policy) están `experimental` sin ningún test de compat (B-01); el baseline
`.ds_init/control.json` no tiene `schema_version` y no hay decisión documentada (B-02); los exit
codes y flags de las CLIs candidatas no están garantizados y `harmessi_bench compare` devuelve 0
aun con `baseline_better` (B-03); la política de deprecación está reducida a un helper mínimo con
registro vacío (B-04); `docs/versioning.md` no define SemVer 0.x vs 1.x (B-05); y las constantes de
versión no tienen test dedicado (B-06). Además el run manifest no valida `manifest_version`, de modo
que una versión futura o inválida no se detecta.

## Objetivo
Dejar cada contrato candidato con ventana de compat, lector estricto probado contra artefactos de
tags reales (v0.13.0, v0.14.0) o explícitamente clasificado, y publicar las políticas de SemVer y
deprecación, sin agregar features.

## Evidencia
- `docs/roadmap/v0.15.md` §C1 (alcance, fuera, salida) y `docs/roadmap/v0.15-debt-matrix.md` filas
  B-01..B-06 (bloqueantes de v1 salvo B-06).
- `tools/harmessi_bench/runmanifest.py:186-206` (`campos_faltantes`/`evaluar_compatibilidad`): sin
  validación de `manifest_version`.
- Preflight del Lead (verificado): los lectores `cargar_candidate`, `cargar_probe`, `cargar_decision`,
  `cargar_propuesta`, `cargar_lesson`, `cargar_presupuesto`/`_leer_estado` y `ProbePolicy.desde_dict`
  exigen igualdad exacta de claves y `contract_version == 1`; los hashes internos (candidate_id,
  policy_hash, decision_hash, proposal_hash, lesson_hash) atan contenido.
- `docs/contracts/inventory.json`: 50 contratos, `inventory_version=1`, pineado `==1` por los smokes
  v0.13/v0.14.
- `tools/harmessi/deprecation.py`: dataclass `Deprecation(nombre, tipo, desde, reemplazo,
  remocion_minima)`, registro vacío.
- Tags anotados `v0.13.0` y `v0.14.0` existen en el repo local.

## Supuestos descartados
- "Los contratos improve se pueden fixturar a mano": descartado; los hashes internos atan el
  contenido, los fixtures deben ser generados por el flujo real del tag.
- "Los contratos improve existen desde v0.13": nacieron en 0.14; su ventana es 0.14-0.15.
- "`compare` ya señaliza regresión por exit code": devuelve 0 con `baseline_better` y los tests lo
  afirman; el default no cambia.
- "El manifest valida su versión": no lo hace.

## Alcance
1. Ventana de compat pre-v1 (0.15, 0.14, 0.13) documentada y probada solo para artefactos con test
   (D1).
2. Tabla de compat por contrato improve y política de bump de `contract_version` (D2).
3. Fixtures reales de v0.14.0 (generador solo-checkout) y de baseline v0.13/v0.14 (D3, D5); test
   v0.15 de lectura con los lectores actuales.
4. Validación de `manifest_version` en el run manifest, aditiva (D4).
5. Decisión documentada sobre el baseline `.ds_init/control.json` sin `schema_version` (D5).
6. Exit codes de CLIs `public-candidate` como "candidatos garantizados"; flag opt-in
   `--fail-on-regression` en `harmessi_bench compare` (D6).
7. Política de deprecación completa: campo `guia`, mensaje, validación, test de cruce con inventory
   (D7).
8. SemVer 0.x vs 1.x y política de promoción experimental -> public-candidate -> stable; campo
   opcional `compat` en inventory (D8).
9. Test de constantes de versión y anclaje de `HARNESS_VERSION` (B-06).

## Fuera de alcance
- Nuevas features; promover a público contratos sin test.
- Subir `inventory_version`, cambiar `MANIFEST_VERSION`, agregar `schema_version` al baseline.
- Cambios al manifest de ds_init, al Doctor o al contenido del baseline `.ds_init/control.json`
  (se gestiona en C7).
- Migraciones de contratos improve (no existen mientras versión==1).
- Cambiar el default de `compare` (sigue 0 con regresión).
- Regresión completa de la suite (la corre el Lead en otra fase).

## Holdout policy (condicional — solo cambios "sensible")
No aplica: el cambio no toca datos ni holdouts.

## Impacto en production-readiness (opcional)
Cubre criterios v1 #1, #2, #3 (parcial, con C7), #4, #12 y #14 del roadmap v0.15.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md` (SDD completo).

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md` (SDD completo).

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado
- docs/versioning.md
- docs/deprecation.md
- docs/contracts/inventory.json
- docs/contracts/README.md
- docs/roadmap/v0.15.md
- docs/roadmap/v0.15-debt-matrix.md
- tools/tests/fixtures/compat/v0_13/**
- tools/tests/fixtures/compat/v0_14/**
- tools/tests/fixtures/compat/generate_v014.py
- tools/tests/test_v015_compat_window.py
- tools/tests/test_v013_compat_window.py
- tools/tests/test_v013_contract_inventory.py
- tools/harmessi/deprecation.py
- tools/harmessi/tests/test_deprecation.py
- tools/harmessi_bench/runmanifest.py
- tools/harmessi_bench/cli.py
- tools/harmessi_bench/tests/test_runmanifest.py
- tools/harmessi_bench/tests/test_cli.py
- tools/harmessi_improve/tests/test_cli.py
- tools/ds_init/tests/test_cli.py
- tools/harmessi/tests/test_cli.py
- tools/tests/test_v013_release_hardening_smoke.py
- tools/tests/test_v014_release_hardening_smoke.py
- ARCHITECTURE.md

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
