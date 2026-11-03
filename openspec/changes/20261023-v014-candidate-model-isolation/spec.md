# Spec — 20261023-v014-candidate-model-isolation

## A. Contrato Candidate
**R1.** `CANDIDATE_CONTRACT_VERSION = 1`. Campos: `candidate_id`, `base_surface`, `base_hash`, `content_hash`, `hypothesis`, `provenance`, `created_utc`, `status`, `status_history`, `suite_ids`, `budget_version`. El contenido propuesto vive en `content.md` junto a `candidate.json`. Sin chain-of-thought ni secretos.
**R2.** `candidate_id = "cand-" + sha256(base_surface\nbase_hash\ncontent_hash)[:12]`: reproducible; crear dos veces la misma candidate es idempotente y no consume budget dos veces.
**R3.** Estados `proposed|evaluated|promotable|rejected|inconclusive`; transiciones válidas `proposed→evaluated`, `evaluated→promotable|rejected|inconclusive`, `inconclusive→evaluated`; `promotable` y `rejected` son terminales. Todo estado distinto de `proposed` exige una referencia de evidencia estructurada (`probe_id` y `decision_hash` no vacíos).

## B. Aislamiento y fronteras
**R4.** Crear una candidate solo escribe bajo `.harmessi/improvement/candidates/<id>/`; el archivo activo, el managed baseline y el resto del árbol quedan byte a byte iguales.
**R5.** `base_surface` debe clasificar como Optimizable según `superficie_de_ruta`; Protected y Project-owned fallan con `CandidateRechazada` (códigos `SUPERFICIE_PROTEGIDA` / `SUPERFICIE_PROYECTO`), antes de cualquier escritura y sin modo "solo para probar".
**R6.** Rutas inválidas (absolutas, `..`, comodines, no str) son Protected por fail-safe y se rechazan. La base debe existir y ser legible (`BASE_ILEGIBLE`).
**R7.** Privacidad: contenido, hipótesis y etiqueta de provenance se rechazan si `redactar_texto` los modifica (rutas de usuario, emails, tokens) → `CONTENIDO_SENSIBLE`. Si existe GLOSSARY del proyecto, contenido que contenga un término suyo se rechaza → `CONOCIMIENTO_DEL_PROYECTO`. Contenido idéntico a la base → `SIN_CAMBIO`. Contenido vacío, con NUL o > 200 KB → `CONTENIDO_INVALIDO`.
**R8.** Una candidate no deriva de otra candidate (la base es siempre el archivo activo; profundidad 1).
**R9.** `cargar_candidate` verifica `content_hash` contra `content.md` y la versión de contrato; manipulación → `CandidateCorrupta`. `base_vigente` informa si el archivo activo sigue con `base_hash`.

## C. Budgets
**R10.** `BUDGET_VERSION = 1`. Defaults `max_candidates=3`, `max_probe_cycles=2`, `max_runs_per_candidate=6`, `max_retries=1`, `max_wall_clock_s=1800`; techos duros 10/5/20/3/7200. Valores no enteros, bool, < 1 o sobre el techo → `PresupuestoInvalido`.
**R11.** Estado persistido en `.harmessi/improvement/budget_state.json`; `consumir(...)` agota de forma determinista (`PresupuestoAgotado`) y persiste contadores; crear una candidate nueva consume `max_candidates`.
**R12.** `verificar_wall_clock` es puro; superar el límite → `PresupuestoAgotado`.

## D. Arquitectura
**R13.** `harmessi_improve` importa solo stdlib, `tools.harmessi_bench` y `tools.dsguard`; ningún módulo de `dsguard`/`harmessi_bench` lo importa; sin `subprocess`, red ni telemetría. Registrado en `SOLO_CHECKOUT` (ambas listas) y documentado en ARCHITECTURE.md.

## Criterios de aceptación
- [ ] R1–R3 contrato y estados. - [ ] R4–R9 aislamiento y fronteras. - [ ] R10–R12 budgets. - [ ] R13 arquitectura.
