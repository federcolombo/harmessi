# Diseño — 20261027-v015-scope-closure-corrective

## Decisión metodológica/técnica
Decisión ya aprobada por el humano: un único Change correctivo pre-release.

(A) Ventana de cierre. Nueva función en `scope.py` (apoyada en helpers de `repo.py`: `is_ancestor`, `rev_list_count`, `resolve_commit`) que busca el sucesor más cercano recorriendo `openspec/changes/*/control.json`: baseline válido y resoluble, commit distinto, baseline de A ancestro estricto del de B; mínimo `rev-list --count A..B`, desempate por `change_id`. `archivos_tocados_desde_baseline` recibe una frontera opcional (`git diff --name-status -z -M A B` en lugar de contra el working tree). Sin sucesor o ante cualquier fallo de resolución: frontera ausente = comportamiento actual. `list_dirty_files` no cambia.

(B) Atestación humana de cambio protegido. Módulo `tools/dsguard/protected_attestation.py` modelado sobre `scope_amendments` (reusa helpers de cadena/hash canónico/escritura atómica): validación de cadena y `planificar`/`aplicar`. Comando `scope attest-protected` en `ds_guard.py` (dry-run imprime `content_hash`; ejecución con `human_presence.solicitar_confirmacion`, artefacto `protected-attestation`). `evaluar_alcance` consulta la atestación solo para rutas de la lista protegida exacta tocadas en la ventana y compara `content_hash` contra el contenido actual (`sha256/lf/v1`). Códigos: `ALCANCE-PROTEGIDA-ATESTADA` (informativo, agregado a `CODIGOS_INFORMATIVOS`), `ALCANCE-PROTEGIDA-SIN-ATESTACION`, `ALCANCE-PROTEGIDA-HASH-DISTINTO`. El nuevo archivo se agrega a Protected en `pathguard.py` (y espejo en archive) y a `_ARCHIVOS_CHANGE_PROTEGIDOS`.

(C) T1 compacta. En `cmd_scope_amend`, `_accion_scope(plan)` devuelve la forma completa si cabe en 120; si no, `scope-amend: <operacion> +N -M hash=<12 hex de hash_diff>`. Se eliminan los dos rechazos (l.4911-4925 y l.4940-4945). La ligadura sigue siendo `hash_diff` completo, recalculado antes del prompt (l.4929-4936).

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica (sin datos). Análogo: la atestación nunca puede ser auto-generada por agentes (T1 real y archivo Protected).

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
Sin desvíos; la elección de sucesor y la acción compacta son deterministas.

## Alternativas descartadas
- Timestamps de control.json para ordenar Changes: descartado; `creado_utc`/`transiciones` de C4/C5/C6 se solapan (C5 creado antes de que C4 llegara a `en_verificacion`), mientras los baselines forman la cadena git C4->C5->C6->C7.
- "Ignorar todo lo posterior a X": sin frontera verificable en git, abre un hueco de evasión.
- Exención general de Protected o autorizar `.claude/settings.json` en `scope amend`: debilita la superficie Protected.
- Globs anchos (`tools/**`, `.claude/**`) para absorber el ruido: pierden la precisión del scope.
- Auto-edición de estados / control.json para "limpiar" el cierre: viola el lifecycle y la gobernanza.
- Canal `declared` para la atestación: no aporta presencia humana; se rechaza en validación.
- Dividir enmiendas en pasos chicos (statu quo): para 6 rutas exactas es inviable y no mejora la seguridad, que reside en el hash.

## Riesgos
- Changes paralelos: el trabajo de A posterior a la frontera (baseline del sucesor) queda fuera de la ventana de A y lo chequea la ventana del sucesor (o el working tree sucio). Límite documentado: A no responde por commits posteriores al baseline de B.
- Un Change archivado deja de acotar la ventana (solo se leen `openspec/changes/*`): cerrar en orden C4→C5→C6 antes de archivar.
- Los Changes con `estado: descartada` (tasks.md) se excluyen como sucesores; si el estado es ilegible el candidato se conserva.
- `attest-protected` se restringe a los estados de `scope amend` (`aprobada_implementacion`, `en_implementacion`, `en_verificacion`).
- Un baseline de sucesor forzado a un commit arbitrario acortaría la ventana de A; mitigado por exigir ascendencia estricta y resolubilidad, y por fail-closed a HEAD.
- Cadena `protected-attestations.jsonl` borrada: sin archivo, la ruta protegida bloquea (`SIN-ATESTACION`).
- Costo de git: un `merge-base` y `rev-list` por Change candidato; aceptable con pocos Changes.
- `tools/tests/test_parallel_change_isolation.py` ejercita `evaluar_alcance`; puede requerir verificación aunque no se edite.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
