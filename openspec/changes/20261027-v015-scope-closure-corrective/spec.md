# Spec — 20261027-v015-scope-closure-corrective

## Requisitos
- R1. Ventana del Change: `archivos_tocados` se calcula como diff `baseline.commit..frontera`, con frontera = baseline.commit del sucesor más cercano o, sin sucesor, el working tree/HEAD (comportamiento actual).
- R2. Sucesor B de A: otro Change en `openspec/changes/*/control.json` con `baseline.commit` válido y resoluble, distinto del de A, tal que el baseline de A es ancestro estricto del de B (`git merge-base --is-ancestor`). Se elige el de menor `git rev-list --count A..B`; desempate determinista por `change_id`. Nunca se usan timestamps.
- R3. Fail-closed: si el baseline de un candidato no resuelve o git falla, ese candidato se ignora (comportamiento actual, frontera HEAD); si git falla al leer, `ALCANCE-GIT-ILEGIBLE`.
- R4. Los archivos sucios (`list_dirty_files`) se siguen evaluando igual, sin ventana.
- R5. Un archivo modificado por A dentro de su ventana y fuera de su alcance sigue bloqueando (`ALCANCE-RUTA`).
- R6. Atestación protegida: registro append-only `openspec/changes/<id>/protected-attestations.jsonl` con campos schema_version, seq, prev_hash, entry_hash (sha256 canónico), utc, change_id, ruta exacta, content_hash (`sha256/lf/v1`), motivo, usuario declarado, fecha_declarada, approval_channel, confirmed_at, channel_version. Cadena validada como la de `amendments.jsonl`.
- R7. Validación: solo se acepta `approval_channel == "console_confirmed"`; cualquier otro valor (p. ej. `declared`) invalida la entrada y la cadena.
- R8. Comando humano `ds_guard scope attest-protected --change-id X --path RUTA --motivo M --usuario U [--fecha F] [--dry-run]`: solo acepta rutas de la lista protegida exacta (`.claude/guardrails.json`, `.claude/settings.json`, `.claude/settings.local.json`); calcula el hash del contenido actual; `--dry-run` lo imprime sin pedir T1 ni escribir; la ejecución pide T1 real (`human_presence.solicitar_confirmacion`, artefacto `protected-attestation`, hash canónico de `{change_id, ruta, content_hash, motivo}`). No existe flag para canal `declared`. No modifica el archivo atestado.
- R9. Gate de cierre / `evaluar_alcance`: una ruta protegida tocada en la ventana se considera cubierta solo con atestación válida (cadena íntegra, `console_confirmed`, mismo `change_id`, ruta exacta) cuyo `content_hash` coincide con el contenido actual del working tree. Informativo: `ALCANCE-PROTEGIDA-ATESTADA`. Bloqueantes: `ALCANCE-PROTEGIDA-SIN-ATESTACION`, `ALCANCE-PROTEGIDA-HASH-DISTINTO`, y cadena inválida.
- R10. No es whitelist: la atestación liga change_id + ruta + hash exacto; no autoriza otros Changes ni otros contenidos.
- R11. `protected-attestations.jsonl` (y su espejo en `openspec/archive/*/`) se agrega a las superficies Protected de `pathguard.py` y a `_ARCHIVOS_CHANGE_PROTEGIDOS` de `skill_contract.py`; los agentes no pueden escribirlo.
- R12. Acción T1 compacta: si `_accion_scope(plan)` excede `_LIMITE_ACCION_T1` (120), la acción es `scope-amend: <operacion> +N -M hash=<12 primeros de hash_diff>` (≤120, determinista). Se elimina el rechazo "demasiadas rutas". El `--dry-run` imprime la lista completa de rutas; `amendments.jsonl` la conserva.
- R13. La confirmación sigue ligada a `hash_diff(change_id, plan)` completo; si el payload cambia entre confirmación y escritura, el replan detecta hash distinto y no escribe.
- R14. Sin cambios de schema de `amendments.jsonl`; sin dependencias nuevas; Protected no se debilita; no hay exención general; T0/T1 y `console_confirmed` conservan su significado.

## Criterios de aceptación
Tests obligatorios (cada uno como caso explícito):
1. Change A cerrado después de B: archivos exclusivos de B no bloquean A (`test_scope_closure_window.py`).
2. Archivo realmente modificado por A dentro de su ventana y fuera de su scope sigue bloqueando A.
3. Ruta protegida tocada sin atestación bloquea (`ALCANCE-PROTEGIDA-SIN-ATESTACION`).
4. Protegida con atestación T1 válida y hash exacto del contenido actual permite el cierre (`ALCANCE-PROTEGIDA-ATESTADA` informativo).
5. Protegida que cambia después de la atestación bloquea (`ALCANCE-PROTEGIDA-HASH-DISTINTO`).
6. Entrada con `approval_channel` distinto de `console_confirmed` (T0/declarada) se rechaza en la validación y la cadena queda inválida.
7. `scope amend` con muchas rutas exactas (acción completa >120) se confirma con acción compacta y payload canónico, sin globs amplios (`test_scope_amend_compact_t1.py`).
8. Si el payload cambia tras la confirmación, el replan detecta hash distinto, no escribe y la confirmación no aplica.
9. Compatibilidad: `amendments.jsonl` existentes siguen válidos y Changes sin sucesor se evalúan igual que antes (frontera HEAD).
10. Dry-run de cierre sobre C4/C5/C6 reales: C4 deja solo `.claude/settings.json`; C5 deja 0 rutas; C6 deja las 6 rutas de c6336b0; ninguno hereda Changes posteriores.

Adicionales:
- [ ] Protected no debilitado: `_ALCANCE_RUTAS_PROTEGIDAS` sin cambios y `scope amend` sigue rechazando rutas protegidas.
- [ ] Tests del suite afectado (test_scope, test_scope_amendments, test_pathguard, test_skill_contract, test_manifest, test_v013_contract_inventory, test_parallel_change_isolation) en verde, ejecutados por el Lead.
- [ ] `git diff` no toca `.claude/**`, `.ds_init/**` ni control.json de otros Changes.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica.

## Baseline (condicional — modeling)
No aplica.

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
No aplica.
