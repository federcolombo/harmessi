# Spec — 20261023-v014-lessons-and-improvement-cycle

## A. Lessons
**R1.** `LESSON_CONTRACT_VERSION=1`. Campos: `lesson_id` (`les-`+sha256[:12] del contenido canónico), `pattern`, `recommendation` (str ≤ 500), `applicability` {`contexts`: 1–5 tags `^[a-z0-9][a-z0-9-]{1,39}$`}, `evidence_refs` (≥ 1: `probe_id`, `decision_hash`, `suite_id`), `status`, `created_utc`, `lesson_hash`.
**R2.** El estado lo calcula el módulo: `evidence-backed` si la decisión recomputada (`decision.decidir`) coincide con `decision_hash`, su veredicto es `candidate_better`/`baseline_better` y la política tiene `repeats ≥ 2`; si no, `hypothesis`. `deprecated` solo por `deprecar`. Una evidencia que no se puede recomputar → `LessonRechazada(EVIDENCIA_NO_VERIFICABLE)`.
**R3.** Privacidad: `pattern`/`recommendation`/tags deben ser invariantes bajo `redactar_texto`; se rechazan rutas (`\`, letra de unidad, `://`, `/` seguida de segmentos), emails, tokens y cualquier término del GLOSSARY del proyecto → `CONTENIDO_SENSIBLE` / `CONOCIMIENTO_DEL_PROYECTO`. No se almacenan prompts, filas ni nombres.
**R4.** Creación gobernada: `crear_lesson(repo_root, change_id, ...)` exige un Change existente en `en_implementacion` cuyo `control.json` tenga ese `change_id`; sin él → `LessonRechazada(SIN_CHANGE)`. Ninguna función de probe/decision/promotion/cycle escribe lessons (una ejecución normal no modifica la biblioteca).
**R5.** `lessons_aplicables(repo_root, contexts, evals_root=None)`: devuelve solo lessons no `deprecated` con intersección de tags de aplicabilidad, `lesson_hash` íntegro, privacidad re-escaneada y evidencia vigente (decisión recomputada igual); el resto va a `descartadas` con motivo. Sin intersección de contexto no se aplica (no hay globalización por defecto).
**R6.** Almacenamiento `.harmessi/improvement/lessons/<id>.json`, escritura atómica, dentro de la raíz (sin enlaces).

## B. Ciclo acotado
**R7.** `ejecutar_ciclo(repo_root, propuestas, suite_path, adapter, target, policy, ...)`: por cada propuesta {base_surface, content, hypothesis, provenance} crea la candidate, hace el probe, decide y aplica la decisión; todas con la misma política y suite. Se detiene de forma determinista ante `PresupuestoAgotado` y reporta `detenido_por` (recurso) y el resultado parcial. No selecciona ni promueve nada: devuelve la lista de candidates con estado.
**R8.** Sin recursión: el ciclo no se puede anidar (`CicloAnidado`, guardia con lock de archivo) y no acepta propuestas sobre el engine (`tools/…` es Protected → rechazo estructural por `crear_candidate`). Profundidad máxima 1: una candidate se basa siempre en el archivo activo.
**R9.** Techos duros intactos: ninguna configuración del ciclo supera `HARD_CEILING`.

## C. CLI
**R10.** `python -m tools.harmessi_improve` con subcomandos `budget`, `candidate {create,list,show}`, `probe`, `decide`, `promote {propose,gate,apply}`, `lesson {add,list,applicable}`, `cycle`. Códigos de salida 0 ok / 1 rechazo de gate o regla / 2 uso inválido / 3 error de entorno; salida segura de consola; `--json`. Providers solo vía `PROVIDER_REGISTRY` diferido; sin red ni telemetría.

## Criterios de aceptación
- [ ] R1–R6 lessons. - [ ] R7–R9 ciclo. - [ ] R10 CLI.
