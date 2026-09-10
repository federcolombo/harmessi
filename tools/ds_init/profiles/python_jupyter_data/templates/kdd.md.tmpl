# KDD — lifecycle del proyecto (referencia)

Se lee bajo demanda, cuando un cambio declara o afecta una etapa KDD, o cuando hace falta
interpretar `openspec/kdd/state.json`. Nunca se carga por defecto.

## 1. Qué es y qué no es

KDD es el lifecycle del **proyecto** de Data Science: en qué etapa está (Problem Understanding,
Data Understanding, ..., Monitoring). SDD (`sdd.md`) sigue siendo el mecanismo para especificar,
decidir, implementar, revisar y verificar un **cambio** puntual dentro de ese lifecycle. KDD no
reemplaza a SDD, no tiene ledger de aprobaciones propio, no tiene sesión propia y no agrega ningún
hook nuevo — reutiliza la maquinaria SDD ya existente (`control.json` de cada cambio, el gate de
cierre de `ds_guard transition`).

Relación exacta:
- Un cambio **declara** a qué etapa(s) pertenece (`control["kdd"]`, ver §4).
- Al cerrar ese cambio (`ds_guard transition --a cerrada`), sus punteros/evidencia se agregan
  automáticamente al estado KDD (`sync`, ver §5) — nunca al revés, y nunca avanza el `estado` de
  una etapa por sí solo.
- Avanzar el `estado` de una etapa es siempre un comando explícito (`ds_guard kdd transition`),
  con aprobación del usuario cuando corresponda (mismo criterio de CLAUDE.md §3 para decisiones
  relevantes).

## 2. Catálogo de etapas

| Etapa | Descripción | v0.2 |
|---|---|---|
| `problem_understanding` | Problema/objetivo de negocio, hipótesis inicial | Activa |
| `data_understanding` | Fuentes, schema, calidad, unidad de análisis/grain | Activa |
| `data_preparation` | Flujo `raw → interim → processed`, QA | Activa |
| `feature_engineering` | Features, cutoff/information boundary, leakage | Activa |
| `modeling` | Selección y entrenamiento de modelos, baseline | Activa |
| `evaluation` | Métricas, protocolo de validación | Activa |
| `interpretation` | Conclusiones, explicabilidad, limitaciones | Activa |
| `production_readiness` | Checklist técnico/gobernanza previo a producción | **Futura** |
| `deployment` | Publicación/release del modelo | **Futura** |
| `monitoring` | Monitoreo post-deployment (drift, performance) | **Futura** |

Las tres etapas futuras existen en el catálogo (para que un cambio de hoy pueda referenciarlas sin
forzar una etiqueta incorrecta) pero nacen en `estado: futura` y no admiten transiciones ni campos
obligatorios en v0.2 — se activan en un bloque futuro.

## 3. `openspec/kdd/state.json`

Nace de forma perezosa (no lo crea `ds_init`, igual que `openspec/changes/`) con
`ds_guard kdd init` — idempotente: si ya existe y es válido, no lo toca; si existe y está
corrupto, no lo sobreescribe (el comando falla explícitamente).

```json
{
  "schema_version": 1,
  "creado_utc": "...",
  "etapas": {
    "modeling": {
      "estado": "no_iniciada | en_progreso | cerrada | futura",
      "changes": ["20260910-slug"],
      "evidencia": [{"change_id": "20260910-slug", "artefacto": "openspec/changes/20260910-slug/verification.md"}],
      "actualizado_utc": "..."
    }
  },
  "historial_transiciones": [
    {"utc": "...", "etapa": "modeling", "desde": "no_iniciada", "hacia": "en_progreso"}
  ]
}
```

No duplica contenido metodológico: `evidencia` solo guarda punteros (`change_id` + ruta del
artefacto real). El contenido vive únicamente en `openspec/changes/<id>/`.

## 4. Cómo un cambio declara su etapa

En `control.json` del cambio (nunca en `tasks.md` — ese archivo es la única fuente de verdad del
`estado:` SDD, y no se le agrega una segunda responsabilidad):

```json
"kdd": {
  "etapa_primaria": "modeling",
  "etapas_afectadas": ["feature_engineering"]
}
```

- `etapa_primaria`: obligatoria para cambios metodológicos/alto riesgo/sensibles que tocan
  lifecycle; opcional para medianas.
- `etapas_afectadas`: 0 o más etapas tocadas incidentalmente. Si un cambio no toca lifecycle en
  absoluto, se omite la clave `kdd` entera (equivalente a "no aplica") — `sync_al_cerrar` lo trata
  como no-op.
- La clave la escribe `python-data-engineer` al crear los borradores, con el valor que el Lead le
  pasa explícito en el prompt de delegación (mismo patrón que el resto del contenido SDD).

## 5. Sync al cierre — qué hace y qué no hace

Al correr `ds_guard transition --change-id <id> --a cerrada`:

1. **Antes** de escribir nada: si el cambio declara etapa(s) KDD, se valida que
   `openspec/kdd/state.json` exista y sea legible. Si falta o está corrupto, la transición se
   bloquea entera (`KDD-NO-INICIALIZADO` / `KDD-ESTADO-CORRUPTO`) — ni `tasks.md` ni `control.json`
   se tocan. Esto evita que el cambio quede cerrado sin que su evidencia KDD quede registrada en
   ningún lado.
2. Se aplica la transición SDD normal (sin cambios respecto de antes de este bloque).
3. **Después**, si la transición fue a `cerrada`, se sincroniza: para cada etapa declarada, se
   agrega `change_id` a `changes` y un puntero a `evidencia` (dedupe por `change_id` — reintentar
   nunca duplica). **Nunca** cambia `estado` de ninguna etapa.
4. Si ese paso 3 fallara por algo excepcional (el pre-chequeo del paso 1 ya cubre los casos
   esperados), `ds_guard transition` igual reporta la transición SDD aplicada, pero además imprime
   `[KDD-SYNC-FALLO]` y devuelve código de salida distinto de 0 — nunca en silencio.

Un cambio que no declara ninguna etapa KDD no se ve afectado por nada de esto: el sync es un
no-op y el cierre funciona exactamente igual que antes del Bloque 4.

## 6. Avanzar una etapa: `ds_guard kdd transition`

Siempre explícito, nunca automático:

```
ds_guard kdd transition --etapa modeling --a en_progreso
ds_guard kdd transition --etapa modeling --a cerrada
```

Transiciones válidas: `no_iniciada → en_progreso → cerrada → en_progreso` (reapertura). Una etapa
`futura` no admite ninguna transición en v0.2 (`KDD-ETAPA-FUTURA`). Cerrar una etapa sin ninguna
evidencia registrada se rechaza (`KDD-SIN-EVIDENCIA`) — chequeo estructural (¿hay evidencia?), no
de calidad (si esa evidencia alcanza, lo evalúa el Lead con el usuario antes de correr el comando).

El Lead corre este comando solo después de proponer el avance de etapa al usuario y recibir
aprobación explícita — es una "decisión relevante" en el sentido de CLAUDE.md §3, igual que
aprobar target/features/modelo.

## 7. `ds_guard kdd status`: guidance / detectable / enforceable

`ds_guard kdd status` es puramente informativo (nunca falla por contenido, mismo espíritu que
`ds_guard status` para SDD). Reporta, por etapa, sus **criterios detectables**: si al menos uno de
los cambios referenciados como evidencia tiene una sección esperada no vacía.

Resolución del directorio de cada cambio referenciado en `evidencia`/`changes`: primero
`openspec/changes/<id>/` (cambio activo); si no está ahí, `openspec/archive/<id>/` (cambio
archivado con `ds_guard archive`) — un cambio archivado no deja de contar como evidencia solo por
haberse movido. Si no aparece en ninguno de los dos, no se trata como error: ese `change_id` se
lista en `changes_no_localizados` (informativo, no persiste en `state.json`) y simplemente no
aporta a ningún criterio detectable.

| Etapa | Criterio detectable (v0.2) |
|---|---|
| `problem_understanding` | `proposal.md` → `## Objetivo` no vacío |
| `data_understanding` | `spec.md` → `## Unidad de análisis` no vacío |
| `data_preparation` | `proposal.md` → `## Alcance` no vacío |
| `feature_engineering` | `spec.md` → `## Cutoff / information boundary` no vacío |
| `modeling` | `spec.md` → `## Baseline` no vacío |
| `evaluation` | `spec.md` → `## Métrica primaria` no vacío |
| `interpretation` | `verification.md` → `## Resultado final` no vacío |

Tres niveles, para no confundir "detectable" con "enforceable":
- **Guidance**: expectativa en prosa (ej. "Data Understanding no debería cerrarse sin
  schema/calidad/grain conocidos"). Informa el juicio del Lead, ningún comando la chequea.
- **Detectable**: lo que `kdd status` reporta arriba — presencia de contenido, nunca su calidad.
  Informativo, no bloquea nada.
- **Enforceable**: `kdd transition --a cerrada` bloqueando si no se cumple un criterio de
  contenido. **No implementado en v0.2** — deliberado, para no abrir juicio metodológico
  automatizado todavía. Queda para v0.3+.

## 8. Campos DS-specific en los templates SDD

`proposal.md`/`spec.md`/`design.md` (`.claude/skills/lead-data-scientist/templates/`) tienen
secciones condicionales para esto — se completan solo cuando la etapa/categoría del cambio las
activa, nunca por defecto:

| Campo | Se completa cuando | Vive en |
|---|---|---|
| Hipótesis | Cambio metodológico | `proposal.md` |
| Unidad de análisis / grain | `data_understanding`, `feature_engineering` o `modeling` | `spec.md` |
| Cutoff / information boundary | `feature_engineering`, `data_preparation` o `modeling` | `spec.md` |
| Target | `feature_engineering` o `modeling` | `design.md` |
| Features permitidas/prohibidas | `feature_engineering` | `design.md` |
| Estrategia de split/validación | Holdout involucrado, `modeling` o `evaluation` | `design.md` |
| Baseline | `modeling` | `spec.md` |
| Métrica primaria / secundarias | `modeling` o `evaluation` | `spec.md` |
| Leakage risks | `feature_engineering`, `data_preparation` o `modeling` | `design.md` |
| Fingerprint de dataset/artefacto | Cambio sensible o reproducibilidad crítica de una corrida | `verification.md` |
| Holdout policy | Cambio "sensible" (routing de `SKILL.md`) | `proposal.md` |
| Reproducibilidad | Solo si se desvía del default (RANDOM_STATE fijo, `.venv`) | `design.md` |
| Impacto en production-readiness | Opcional hoy; condicional cuando esa etapa se active | `proposal.md` |

Ninguno es obligatorio para cambios pequeños o refactors sin decisión metodológica — esos siguen
sin SDD, y por lo tanto sin estos campos.

## 9. Relación con la documentación existente

`sdd.md` §10 seguía sin resolver qué artefacto representaba el "histórico de fase" del proyecto —
ese lugar lo ocupa `openspec/kdd/state.json`, documentado acá. El resto de esa sección
(documento maestro de diseño, handoff, esquema de datos) no cambia: KDD no los reemplaza ni los
duplica, solo agrega el nivel de estado de lifecycle que faltaba.
