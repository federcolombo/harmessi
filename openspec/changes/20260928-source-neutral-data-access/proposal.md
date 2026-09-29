# Propuesta — 20260928-source-neutral-data-access

Change 1 de v0.8 (`docs/roadmap/v0.8.md`, sección "Change 1", líneas 556-596). Depende del
Change 0 (`20260928-project-autonomy-contract`, cerrado): reutiliza `source_id`,
`parse_autonomy_policy`, `effective_source_access` e `is_source_sealed`
(`tools/autonomy/core.py:332`, `tools/autonomy/policy.py:152,302,323`).

## Contexto

Hoy toda la validación de calidad de datos de Harmessi asume que la evidencia es un
`profile.json` de `ds_profile`, es decir, un archivo CSV/Parquet local. Tres acoplamientos lo
muestran:

1. `tools/datacontracts/validation.py` razona en el vocabulario de `ds_profile`
   (`dtype` `texto/entero/...`, `top_valores`, `exactitud`, `fecha_min`; ver
   `validation.py:112-120` y las reglas `_regla_*` en 238-719).
2. `ds_profile` persiste `dataset_path` (`tools/ds_profile/report.py:210`), posiblemente absoluto,
   dentro de la evidencia.
3. No existe un lugar declarativo donde un proyecto diga "la fuente `customers` se observa con este
   código", así que el humano no puede sellar/permitir fuentes que no son archivos (el sello de
   Change 0 opera por `source_id`, y ese `source_id` todavía no tiene contraparte en el código).

Los proyectos reales de ciencia de datos leen de bases de datos, APIs, lakes y servicios
corporativos. Harmessi no debe conocer esas tecnologías (principio 2 del roadmap, línea 57); debe
poder consumir una **observación neutral** producida por código del proyecto.

## Propuesta

Un paquete nuevo `tools/datasources/` que define el contrato neutral de fuentes, y un refactor
acotado de Data Contracts para que exista **un único evaluador** que trabaja sobre esa observación.

- Tipos neutrales: `SourceRef`, `SourceObserver` (extension point del proyecto), `SourceCapabilities`,
  `ObservationRequest`, `SourceObservation`, `FieldObservation`, `SourceProvenance`, `SourceError`,
  con serialización determinista y hash de contenido que excluye `generated_at`.
- Registro del proyecto `.harmessi/sources.json` (fuera del manifiesto de instalación: no puede
  producir drift) con validación **estática**.
- Runtime de observación: registro -> control de acceso inyectado (sellado por `source_id`) ->
  `importlib` -> capacidades -> observación -> gate de secretos/portabilidad -> persistencia
  atómica y portable.
- Bridge `profile.json -> SourceObservation` (puro) y un único observer incluido
  (`file_observer`), que orquesta `ds_profile` + bridge; `ds_profile` no cambia.
- Evaluador único `validate_contract_observation` nativo sobre observación; los wrappers v0.7
  (`validate_contract`, `validate_contract_against_profile_file`) quedan como
  `gate legacy -> bridge -> evaluador único` con paridad exacta contra un corpus dorado generado
  **antes** del refactor.
- Frescura: `compare_fingerprint` (igual PASS, distinto FAIL, no verificable WARN nunca PASS).
- CLI aditiva en `tools/ds_guard.py`: `source list|check|observe|check-stale` y
  `contract validate --observation`.

## Naming (SDD-1 delegado al SDD)

El roadmap usa "adapter" y `DataSourceRef` (no congelados). Se evita "adapter"/"provider" por
ambigüedad con los adapters de hooks (`ARCHITECTURE.md` §2.2) y `tools/providers`.

| Roadmap | Este Change |
|---|---|
| `DataSourceRef` | `SourceRef` |
| `DataSourceAdapter` / "adapter" | `SourceObserver` |
| "adapter de archivo mínimo" | `file_observer` |
| facetas `null_counts`, `min_max`, `uniqueness`, `domain`, `time_bounds` | `null_count`, `value_range`, `distinct_count`, `value_distribution`, `time_range` (por campo) |
| `SourceCapabilities`, `SourceObservation`, `SourceProvenance` | igual |

## Identificador lógico (congelado por el autor)

`source_id` sigue el patrón canónico `[a-z0-9][a-z0-9_-]{0,63}` y es un identificador **lógico,
estable y portable**. NO es nombre físico de tabla, schema, path, filename, bucket, endpoint, URL,
dataset externo ni identificador propietario. El regex no se amplía con `.`, `:` ni `/`. Si hiciera
falta jerarquía/namespace, sería otro campo/contrato explícito (fuera de este Change). Ejemplos:
`dbo.Clientes.Productores`, `project.dataset.customers`, `/v2/customers` y
`data/raw/customers.parquet` se registran todos como `source_id = customers`; lo físico vive en
`options`/`config_ref` y en el observer.

## Alcance

Dentro: los ítems de "Propuesta"; tests de neutralidad y paridad; entradas de manifiesto;
`ARCHITECTURE.md` (filas §2.1, regla 11, excepción de `tools.datacontracts`, mención en §6);
tildado del roadmap al cerrar.

Fuera (idéntico al roadmap, líneas 584-586, más lo decidido aquí): conectores a cualquier
base/API/nube, ORM o SQL en el core, DSL de consultas, extensión de `ds_profile` a fuentes no
archivo, gestor de secretos, SDK/generador de observers, sandbox, timeouts en proceso, escrituras a
fuentes, `ds_guard autonomy` (Change 3), integración con Doctor (Change 4; aquí solo la función
`check_registry` reutilizable), cambios a skills/plantillas, instalar dependencias.

## Criterios de cierre (resumen; detalle verificable en `spec.md`)

- Round-trip determinista de la observación (mismos bytes).
- Paridad exacta contra el corpus dorado v0.7 (mensajes incluidos) y tests existentes de
  datacontracts/ds_guard/qualityevidence sin editar.
- Un observer de prueba en memoria, sin archivos ni SQL, produce una observación válida.
- Faceta ausente nunca da PASS; el core no ramifica sobre `source_kind` ni por tecnología.
- Scan de secretos con casos positivos y negativos; neutralidad de dependencias por `ast`.
- Un solo motor de validación; el evaluador nativo no abre archivos.
- Fuente sellada por `source_id` no se observa aunque el registro la declare (antes de importar el
  observer); fallo de import o excepción del observer = `technical_error`.
- El hash del código del observer figura en `SourceProvenance`.
- `python -m tools.ds_init.check_manifest_parity` OK; suite completa verde en el gate final.

## Riesgos principales (detalle en `design.md`)

Observer en proceso sin sandbox; scan de secretos best-effort; corpus dorado solo tan bueno como su
representatividad; complejidad del catálogo de `wording` para preservar mensajes v0.7; observer
colgado sin timeout hasta el Change 2; `ds_profile` no distingue `date`/`datetime`.

## Aprobación

Pendiente. Este documento es una propuesta; no hay aprobación humana registrada. Ninguna tarea de
implementación de `tasks.md` puede iniciarse hasta que el autor apruebe la propuesta.
