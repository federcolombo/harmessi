# Spec — 20260914-lifecycle-core-schema

## Requisitos
El schema completo de `openspec/lifecycle/state.json` y la lista de funciones/constantes
públicas de `tools/dsguard/lifecycle.py` están detallados en `proposal.md` § Alcance (puntos 1 y
2) — remite a esa sección en vez de repetirla palabra por palabra. Se dejan explícitos acá los
nombres exactos que ese schema debe usar:

- **8 fases CRISP-DM** (`FASES_CRISPDM`): `business_understanding`, `data_understanding`,
  `data_preparation`, `modeling`, `evaluation`, `production_readiness`, `deployment`,
  `monitoring`.
- **5 pasos KDD** (`PASOS_KDD`): `selection`, `preprocessing`, `transformation`, `data_mining`,
  `interpretation_evaluation`.
- **3 tiers MLOps** (`MLOPS_TIERS`) con sus capacidades (`MLOPS_CAPACIDADES`), 16 en total:
  - `foundations` (4): `reproducibilidad`, `versionado`, `lineage`, `artifacts`.
  - `production_readiness` (5): `packaging`, `environment_reproducible`, `inference_contract`,
    `inference_tests`, `trazabilidad_fuerte`.
  - `operations` (7): `deployment`, `cicd`, `monitoring`, `rollback`, `drift`, `alerts`,
    `retraining`.

Cada entrada (fase CRISP-DM, paso KDD, capacidad MLOps) tiene la forma
`{estado, changes, evidencia, actualizado_utc}`, con `estado` restringido a `ESTADOS_VALIDOS`
(`{"no_iniciada", "en_progreso", "cerrada"}`).

## Criterios de aceptación
<!-- checklist o Given/When/Then, verificables -->
- Dado un repo sin `openspec/lifecycle/state.json`, cuando se llama `lifecycle_init(repo_root)`,
  entonces se crea el archivo con la estructura inicial completa y devuelve `(estado, creado=True)`.
- Dado un repo con `state.json` ya válido, cuando se llama `lifecycle_init` de nuevo, entonces NO
  se reescribe el archivo (mismos bytes exactos) y devuelve `(estado, creado=False)` —
  idempotencia.
- `estado_inicial()` contiene exactamente las 8 fases CRISP-DM, cada una
  `{estado: "no_iniciada", changes: [], evidencia: [], actualizado_utc: <str>}`.
- `estado_inicial()` contiene exactamente los 5 pasos KDD, misma forma.
- `estado_inicial()` contiene exactamente los 3 tiers MLOps con sus 16 capacidades exactas, misma
  forma (incluye `changes`).
- `MAPEO_CRISPDM_A_KDD` mapea exactamente: `business_understanding→()`,
  `data_understanding→(selection,)`, `data_preparation→(preprocessing,transformation)`,
  `modeling→(data_mining,)`, `evaluation→(interpretation_evaluation,)`,
  `production_readiness/deployment/monitoring→()`.
- `MAPEO_KDD_A_CRISPDM` es la inversa exacta de `MAPEO_CRISPDM_A_KDD`, derivada por código (no
  hardcodeada aparte) — un test que reconstruye la inversa a mano desde `MAPEO_CRISPDM_A_KDD` y
  la compara debe pasar.
- `leer_estado(path)` sobre JSON corrupto levanta `LifecycleEstadoError`, sin escribir nada.
- `leer_estado(path)` sobre `schema_version` desconocida levanta `LifecycleEstadoError` con
  mensaje explícito que incluya el valor recibido y el esperado.
- `leer_estado(path)` sobre archivo inexistente levanta `FileNotFoundError`.
- `escribir_estado` escribe atómicamente (mismo patrón que `core.escribir_texto_atomico`: nunca
  deja el archivo en un estado parcial si algo falla a mitad de la escritura).
- Round-trip: escribir un estado y volver a leerlo da una estructura idéntica (`==`) a la
  escrita.
- Ninguna función de lectura (`leer_estado`, `validar_estructura`) escribe en disco bajo ninguna
  circunstancia — verificable capturando bytes del archivo antes/después de llamarlas.
- `state_path(repo_root)` devuelve exactamente `Path(repo_root) / "openspec" / "lifecycle" /
  "state.json"`.
- `validar_estructura` rechaza un dict con una fase/paso/capacidad faltante o con una clave extra
  no reconocida.
- `validar_estructura` rechaza una entrada con `estado` fuera de `ESTADOS_VALIDOS` (que en este
  schema es `{"no_iniciada", "en_progreso", "cerrada"}` — sin `"futura"`, ver `design.md`).
- `estado_inicial()["crispdm"]` no contiene una clave `fase_actual`, y `estado_inicial()["kdd"]` no
  contiene una clave `paso_actual` — no se persisten en schema v1 (ver `design.md`, ajuste del
  usuario tras la primera revisión).

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica — no hay datos, target ni features involucrados en este change de arquitectura del
harness.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica — no hay datos, target ni features involucrados en este change de arquitectura del
harness.

## Baseline (condicional — modeling)
No aplica — no hay datos, target ni features involucrados en este change de arquitectura del
harness.

## Métrica primaria (condicional — modeling, evaluation)
No aplica — no hay datos, target ni features involucrados en este change de arquitectura del
harness.

## Métricas secundarias (opcional)
No aplica — no hay datos, target ni features involucrados en este change de arquitectura del
harness.
