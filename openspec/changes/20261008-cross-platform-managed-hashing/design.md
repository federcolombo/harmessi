# Diseño — 20261008-cross-platform-managed-hashing

Diseño del Change 1 de v0.10 (solo deuda A). Audit + SDD; sin implementación. Refina el diseño conceptual D3 del Change 0.

## Decisión metodológica/técnica

### D1. Algoritmo `sha256/eol-lf/v1` a nivel de bytes
- Hashea bytes con CRLF -> LF y luego CR -> LF, sin decodificar, sin quitar BOM, sin tocar nada más.
- No se reutiliza `hash_lf_v1`: descarta BOM y exige UTF-8, y el contrato de este Change es «solo EOL». Además `hash_lf_v1` sirve a aprobaciones y no debe acoplarse a los managed.
- CR solitario -> LF por consistencia con `hash_lf_v1` y con `datasources/runtime.py`. Límite aceptado: un CR solitario cambiado a LF no se ve como drift.
- Descartado: hash AST/semántico; normalizar whitespace/Unicode; heurística «decode ok => texto».

### D2. Binarios y `contenido` en el manifest
- `EntradaManifiesto.contenido` (`texto` por defecto | `binario`) decide el algoritmo; `sha256/bin/v1` por convención de ids.
- Hoy los 134 managed son texto; el contrato no impide agregar binarios. Un test de paridad por extensión evita olvidar declarar `binario`.

### D3. `hash_alg` por entrada vs top-level
- Por entrada: precisión, migración parcial, sin bump de `schema_version`.
- Riesgo: un Harmessi anterior lee el `sha256` nuevo con su hash crudo y reporta falso drift en archivos CRLF (downgrade). Aceptado: la migración es explícita y se documenta.
- Alternativa descartada: bump de schema (innecesario, rompe lectura backward-compatible).

### D4. Compatibilidad legacy: estrategia A
- A (elegida): una entrada sin `hash_alg` verifica si coincide el hash crudo del archivo, el de su forma LF-canónica o el de su forma CRLF. Luego la migración la convierte al algoritmo nuevo.
- B (descartada): dual-check temporal permanente = ventana permisiva sin fin.
- C (descartada): regenerar en `sync` = rehash silencioso de contenido modificado.
- No se acepta: modificaciones reales de contenido ni EOL mixto no verificable (se reporta; rebaseline explícito).
- Quién autoriza: la migración no acepta contenido nuevo, solo cambia el algoritmo de contenido ya verificado; su ejecución (`--execute`) es el acto explícito. Doctor solo sugiere.

### D5. Primitive única y límites
- Una sola primitive para hashes managed; no es una abstracción para todos los hashes del proyecto.
- Frontera managed vs evidence:

| Superficie | Hash |
|---|---|
| Managed texto | `sha256/eol-lf/v1` |
| Managed binario | `sha256/bin/v1` |
| Evidence / pins (Cards, EvidenceRef) | bytes exactos |
| Aprobaciones / ApprovalRef / checkpoints | `hash_lf_v1` |
| JSON canónico | lógico (sin cambios) |

### D6. Guardrails
- Orden de evaluación en Doctor: primero hash canónico; la comparación semántica solo corre si difiere.
- La closed-list `RUTAS_MUTABLES` no se toca. EOL no puede generar falso drift en `.claude/guardrails.json`, y una customización no soportada sigue siendo drift.

### D7. `.gitattributes`
- No gestionado ni sobrescrito por Harmessi. Puede documentarse como complemento opcional, nunca como requisito de correctness: Harmessi debe funcionar con o sin `core.autocrlf`.

### D8. `sync` y hallazgo F-1 (decisión M-A aprobada)
- Hoy `sync` rehashea todos los managed y oculta modificaciones (F-1).
- Principio: `sync` reconcilia, NO adopta; sync never adopts pre-existing drift. Clasifica antes de escribir, contra el baseline anterior: pristine / legacy verificable por EOL / drift real (incluye `algoritmo_desconocido`, fail-closed) / entrada nueva.
- Pristine + asset distinto: se actualiza (journal con backup y rollback) y se registra el hash del nuevo contenido; idéntico: no se escribe. Legacy verificado: migra al algoritmo vigente. Drift: archivo intacto, entrada conservada tal cual, mensaje accionable, Doctor sigue reportando. Existente sin entrada: no se adopta salvo que coincida con lo distribuido. Merge (`.claude/settings.json`, `CLAUDE.md` con `--integrar-claude`): se aplica igual; baseline actualizado solo si el previo era pristine o inexistente.
- `regenerar_control` explícito mantiene el rebaseline total como primitive de mantenimiento (el mantenedor lo usa en el procedimiento de release); `sync` lo usa solo en modo conservador vía `clasificacion`, sin renombrar APIs ni cambiar defaults.
- Separación: hash migration != managed upgrade != re-adoption (Change 3).
- Alternativas descartadas: mantener el rehash total de `sync` (conserva F-1); reutilizar `regenerar_control` indiscriminadamente (rebaseline silencioso); adoptar archivos existentes sin baseline (legitima drift preexistente).
- Riesgo: un retry tras fallo parcial podría perder las entradas conservadas y dejar `control.json` sin ellas o con hashes del contenido modificado; por eso `generar_control` recibe `entradas_conservadas`.
- Aprobación humana: ver proposal.md.

### D9. Portabilidad y performance
- Sin comportamiento específico de OS; lectura en streaming por bloques; sin dependencias; resultado independiente del tamaño de bloque.

### D10. Migración vs re-adopción
- La migración cambia el algoritmo de contenido verificado; la re-adopción (Change 3) acepta una modificación soportada como nuevo baseline. No comparten código ni semántica; no se mezclan.

### D11. Hallazgo F-2
- Pins byte-exact de evidencia versionada bajo autocrlf pueden romperse en checkouts CRLF. Candidato futuro; no se cambia en este Change.

### D12. Clasificación previa y modo conservador
- `sync` invoca `clasificar_baseline(destino, control_previo)` antes de cualquier escritura; la clasificación se fija contra el baseline anterior y no se recalcula con hashes regenerados.
- El planner decide la acción por archivo con `clasificacion` (`ACCION_ACTUALIZAR_MANAGED` para pristine/legacy con asset distinto; omitir drift; con `None` el plan es idéntico al actual).
- El writer arma el staging del contenido distribuido; si el hash managed del staging coincide con el del archivo actual, no escribe (`sin_cambios`); si no, actualiza (`actualizados`).
- El journal reutiliza el backup/rollback de `reemplazar-merge`.
- `regenerar_control(..., clasificacion=...)` conserva entradas de drift tal cual y recibe `entradas_conservadas` en la escritura de control.

### D13. API de contrato
Ver spec.md sección G2 (R45-R49): `managed_hash` (constantes `ALG_*`, `CONTENIDO_*`, `ESTADO_*`, `algoritmo_para_contenido`, `hash_managed_file`, `hash_crudo_file`, `verificar_entrada`), `control` (`generar_control(..., entradas_conservadas=None)`, `clasificar_baseline`, `regenerar_control(..., clasificacion=None, resultado=None)`, `migrar_hashes`/`InformeMigracion`), `manifest` (`contenido`, `contenido_de`), `planner` (`ACCION_ACTUALIZAR_MANAGED`, `construir_plan(..., clasificacion=None)`), `writer` (`actualizados`, `sin_cambios`), `cli` (`migrate-hashes [--execute]`, `sync` conservador). Los writers implementan en paralelo contra estas firmas.

## Target (condicional — feature_engineering, modeling)
No aplica (Change documental).

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica; no se toca ningún holdout.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica; sin datos ni features.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
Sin desvíos. El hash y la migración son deterministas.

## Alternativas descartadas
- Hash AST/semántico; normalización de whitespace/Unicode; heurística de decodificación.
- Reutilizar `hash_lf_v1` para managed.
- Bump de `schema_version`; `hash_alg` top-level.
- Compatibilidad B (dual-check permanente) y C (regeneración en `sync`).
- Para `sync` (D8): rehash total, uso indiscriminado de `regenerar_control`, adopción de archivos existentes sin baseline.
- Gestionar `.gitattributes`; depender de `core.autocrlf`.
- Abstracción única para todos los hashes del proyecto.

## Riesgos
- Baseline legacy con EOL mixto no verificable: se reporta; requiere rebaseline explícito.
- Olvidar declarar `binario` en un managed nuevo: mitigado por test de paridad.
- Downgrade a un Harmessi anterior: falso drift en CRLF (D3); aceptado.
- Regenerar `control.json` de este repo antes de tiempo: se hace una única vez en el Change 6.
- Un CR solitario cambiado a LF no se detecta (D1); aceptado.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
Ver `proposal.md`.
