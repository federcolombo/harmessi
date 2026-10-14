# Verificación — 20261013-governed-amendments

## Resumen
Change 3 de v0.10 «Governed Amendments»: enmiendas gobernadas de scope y re-adopción de guardrails por closed list, primer consumidor obligatorio de T1 (`console_confirmed`, `console/v1`). SDD aprobado por hash el 2026-10-13 por Federico Colombo bajo T0 (proposal `0b7f3d97…`, spec `cba9c853…`, design `afd4a98f…`) con las decisiones M1–M4 resueltas en SÍ. Implementación con instancias de `python-data-engineer` de ownership disjunto (A: `scope_amendments.py`; B: `guardrails_adoption.py`; C: `scope.py` + `pathguard.py`; D: `ds_guard.py`; E: `doctor.py`; F: docs y boundaries); el Lead no escribió código de implementación (salvo la intervención de emergencia declarada en Incidentes).

## Qué entrega
- `ds_guard scope amend|show` (con `--dry-run`, `--reparar-cache`) y `ds_guard guardrails readopt`. Sin `--channel`, `--yes` ni `--force`; ambos mutadores exigen T1 real; el dry-run no pide T1; un no-op no pide T1 ni escribe.
- Cadena de scope `openspec/changes/<id>/amendments.jsonl` (append-only, `seq`/`prev_hash`/`entry_hash`, scope antes/después, campos T1). Lectura única vía `scope.alcance_efectivo`; la caché de `control.json` nunca supera a la cadena (`ALCANCE-CACHE-DIVERGENTE`); cadena inválida o ancla `scope_hash` contradicha → `ALCANCE-ENMIENDA-INVALIDA` y rutas vacías (fail-closed). Re-aprobar `proposal.md` con enmiendas efectivas se rechaza.
- Cadena de re-adopción `openspec/decisions/guardrails-adoptions.jsonl`, closed list `holdouts`, `data_raw`, `secretos_extra`, `autonomy.sealed_sources` (solo adiciones); diff mixto o inelegible se rechaza completo; hash acumulado independiente de la plantilla; `guardrails.json` y `control.json` no se modifican; `sync` nunca re-adopta; Doctor reconoce solo igualdad exacta de conjunto con adopciones no vacías.
- Pathguard protege ambos registros (herramientas de edición, escrituras shell detectables, git mutante que nombra el registro, streams NTFS); no bloquea lectura ni el CLI gobernado. Protección de mejor esfuerzo, no criptográfica.
- Atomicidad: recalcular → concurrencia optimista → T1 → releer/verificar → temporal con cadena validada → comprobación byte a byte → `os.replace` → refresco de caché (best-effort) → post-validación.

## Evidencia obtenida
- Tests dirigidos y regresión relevante final (una sola, tras todos los fixes): 690 OK (8 skipped) en scope, módulos nuevos, CLI, pathguard/hook, boundaries, smoke de roadmap, T1 y approvals de Cards, checkpoints/SDD, rutas Unicode, drift de guardrails, exec approve y exec scope; más 140 OK en sync, managed hash y Doctor. Sin regresión completa, sin Cards/governance completas, sin `ds_profile`. `ds_guard validate --change-id 20261013-governed-amendments`: «Sin hallazgos».
- Prueba negativa desde el runtime del agente: las ejecuciones reales de `scope amend` y `guardrails readopt` dan exit 2 sin escribir registros.
- Reviewer `data-science-reviewer`, 2/2 ciclos (cada uno en dos revisores paralelos: scope y guardrails): ciclo 1 sin blockers, un alto por lado, corregidos (ancla sin cadena, validación de ruta de cadena, relectura de concurrencia, sanitización, `change_dir` en `evaluar_alcance`, patrones git/NTFS en pathguard, independencia del hash de cadena respecto de la plantilla). Ciclo 2 sin blockers; 2 altos de scope (el humano no veía las rutas confirmadas; texto previo al prompt sin sanitizar) y un medio de guardrails (sanitizado de `motivo`/`usuario`), todos corregidos. Sin hallazgos abiertos.
- ACEPTACIÓN MANUAL HUMANA (T8), ejecutada por Federico Colombo en su PowerShell interactiva real sobre un repo temporal descartable (`%TEMP%\hm_gov_acceptance`), con T1 real en las tres operaciones:
  - **Scope ADD** `+ scripts/prueba.py`: dry-run correcto sin T1; ejecución real con challenge `console_confirmed` ingresado a mano; `$LASTEXITCODE = 0`; amendment #1; revisión 0→1; `scope_hash` cambió; `amendments.jsonl` registró `approval_channel=console_confirmed`, `channel_version=console/v1`, `confirmed_at`, `scope_hash_before/after`, `prev_hash`, `entry_hash` y usuario declarado; la ruta quedó en el scope efectivo.
  - **Scope REMOVE** `- scripts/prueba.py`: nuevo challenge T1 con binding distinto, ingresado a mano; exit 0; amendment #2; revisión 1→2; el scope volvió al hash inicial y la ruta dejó de estar autorizada.
  - **Guardrails readopt** (`holdouts += data/holdout_prueba/**`, `secretos_extra += **/*.token_prueba`): dry-run solo con las dos adiciones y sin T1; ejecución real con challenge `guardrails-readopt: holdouts+1 secretos_extra+1`; exit 0; re-adopción #1 con `approval_channel`, `channel_version`, `confirmed_at`, `guardrails_hash_before/after`, `prev_hash`, `entry_hash` y adiciones exactas; `guardrails.json` y `control.json` NO modificados.
  - **No-op posterior**: un segundo `readopt --dry-run` sobre el mismo estado respondió «Sin diferencias adoptables (no-op): no se pide confirmación ni se escribe nada.»
  - Los valores de hash concretos quedaron en el repo temporal descartable y no se copian acá; el usuario reportó la evidencia cualitativa.
  - No se repitieron pruebas, reviewer ni regresión tras la aceptación.

## Fingerprint de dataset/artefacto
No aplica (sin datasets).

## Diferencias contra la spec
`spec.md` y `design.md` quedan intactos (aprobados por hash). Desvíos declarados:
- R23: una cadena inválida devuelve rutas vacías, no el scope previo.
- R62: existe `scope show --reparar-cache` (T0; solo alinea la caché derivada, no toca la cadena).
- El ancla `control["alcance"]["scope_hash"]` actúa también cuando no existe cadena (caché contradice ancla → inválido).
- Spec R24/R25: ajustes de detalle de sanitización y de visualización del diff en el prompt (el diff completo de `readopt` se imprime antes del prompt; el challenge lleva resumen de conteos).

## Limitaciones
- T1 es señal de presencia interactiva, no identidad ni no-repudio; no resiste input de consola sintetizado deliberadamente (fuera de garantía, no ejercitado); la validación T1 en un host POSIX real sigue sin ejercitarse.
- Las cadenas no son criptográficamente auténticas: quien escriba el filesystem por una vía que pathguard no ve puede reescribir una cadena completa y coherente. Git sigue siendo la evidencia externa frente a truncado o reescritura sofisticada (p. ej. `git checkout .` sin nombrar el registro puede volver a un prefijo; `--reparar-cache` alinearía la caché a ese prefijo).
- `control.json` no está protegido por pathguard.
- Los Changes legados sin ancla `scope_hash` no tienen protección contra edición manual de la caché antes de su primera enmienda.
- `readopt` en proyectos instalados requiere correrse desde el clon de Harmessi con `--destino` (la plantilla es el `guardrails.json` del repo origen).
- Los registros se cubren con protección de mejor esfuerzo en pathguard.

## Incidentes de proceso (input para Change 4; NO resueltos acá)
- Tres writers y un reviewer alcanzaron `maxTurns` y requirieron reanudación.
- La sesión venció por reloj (600 min de wall-clock): hubo que cerrar `s1` y abrir `s2` (480 min).
- Pathguard se rompió dos veces durante la implementación (nombres sin definir en `pathguard.py` que hicieron que el hook denegara toda escritura). La primera vez se revirtió con git; la segunda requirió una reparación de emergencia por Bash (único canal no bloqueado), con texto escrito por el writer.
- En la sesión nueva se perdió el `PATH` en Bash; las pruebas siguieron por PowerShell con el python de `.venv`.

## Pendientes derivados
- Change 4: turn limits y reanudaciones, expiración de sesión por reloj, ciclo de vida de writers, robustez de pathguard ante errores del propio editor.
- Sin resolver y preservados: sesión por defecto de 90 min, enum de ledger amend/decision, scratchpad, verificación POSIX en host real, Domain Modeling.

## Resultado final
Change 3 verificado con las pruebas relevantes indicadas y la aceptación manual humana (T8) del 2026-10-14; sin hallazgos abiertos del reviewer.
