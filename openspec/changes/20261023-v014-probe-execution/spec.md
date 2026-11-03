# Spec — 20261023-v014-probe-execution

## A. Política congelada
**R1.** `ProbePolicy` (`POLICY_VERSION=1`): `primary="passed"` (único soportado), `secondary` ⊆ {`mean_score`,`duration_s`}, `tie_policy` ∈ {`equivalent`,`secondary`,`inconclusive`}, `repeats` entero 1..3, `min_stable_ratio` en (0,1], `min_delta` ≥ 0. Valores inválidos → `PolicyInvalida`. `policy_hash` determinista.
**R2.** La política se persiste en `probe.json` (con su hash) **antes** de ejecutar; no hay API para cambiarla después de iniciado el probe.

## B. Mismas condiciones
**R3.** Baseline y candidate comparten suite, cases_hash, target, evaluator, seed, adapter y repeticiones; la única diferencia es la guía inyectada (`GuidanceAdapter`: antepone la guía al prompt y delega en el adapter real).
**R4.** Cada corrida se persiste con `storage.save_run` y un `run_manifest` v0.13. El manifest del lado candidate refleja la superficie candidate mediante `runmanifest.sustituir_superficie` (recalcula `skills`/`surfaces_hash`/`identity_hash`, sin escribir el archivo activo). `compare_runs` entre ambas corridas no es `inconclusive` por manifest.
**R5.** Precondiciones fail-closed: candidate en `proposed`/`inconclusive`; `base_vigente`; suite compatible con `suite_ids` si se declararon; manifest sin problemas de identidad. Si no, `ProbeRechazado(codigo)` sin ejecutar ni consumir runs.

## C. Budget
**R6.** Un probe consume 1 `probe_cycle` y `2*repeats` `runs` de la candidate antes de ejecutar (agotamiento → `PresupuestoAgotado` sin ejecutar); los reintentos por fallo de entorno consumen `retries`; el wall-clock se verifica entre corridas y, si vence, el probe termina `inconclusive` con motivo.

## D. Resultado y evidencia
**R7.** `outcome` ∈ {`success`,`candidate_failure`,`baseline_failure`,`environment_failure`,`inconclusive`}. Fallos con `availability_error` (o en ambos lados) son `environment_failure`; `ok=False` solo en un lado sin `availability_error` es failure de ese lado. Nunca se interpreta un fallo de entorno como "candidate peor".
**R8.** `probe.json` (`PROBE_CONTRACT_VERSION=1`) registra: `probe_id`, `candidate_id`, `base_surface`, `baseline_surface_hash`, `candidate_hash`, `budget_version`, `policy` + `policy_hash`, `suite` (id/version/hash), `cases_hash`, `target`, `seed`, runs (`run_id`, rol, repetición, `identity_hash`, `sha256` del `result.json`), `outcome`, motivos, timestamps. Sin prompts, sin secretos, rutas redactadas.
**R9.** Resume: `resume=True` reutiliza repeticiones completas y exige igualdad de policy_hash, candidate_hash, baseline_surface_hash, suite_hash, cases_hash, target y budget_version; si no → `ProbeIncompatible`. Sin `resume`, un `probe_id` existente → `ProbeRechazado(PROBE_EXISTENTE)`.
**R10.** El probe no transiciona el estado de la candidate (lo hace la decisión, Change 3) y no modifica ningún archivo fuera de `.harmessi/improvement/probes/` y `.harmessi/evals/`.

## E. Arquitectura
**R11.** `tools.providers.core` queda permitido solo para `InvocationRequest`; el resto de R13 de Change 1 se mantiene.

## Criterios de aceptación
- [ ] R1–R2 política. - [ ] R3–R5 condiciones iguales. - [ ] R6 budget. - [ ] R7–R10 evidencia/resume. - [ ] R11.
