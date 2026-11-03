# Tareas — 20260914-lifecycle-migration-and-kdd-repoint

estado: cerrada

## Invocaciones planificadas
- Python Data Engineer (implementación): mapeo legacy + `migrar_desde_legacy` + repunte de `kdd_init/status/transition/validar_antes_de_cerrar/sync_al_cerrar` + comando `ds_guard lifecycle migrate` + entrada de manifest + tests.
- Data Science Reviewer (antes de ejecutar nada): revisa el diff.
- Python Data Engineer (post-revisión, planificada): corrige si hace falta, `estado: en_verificacion`.
- Python Data Engineer (cierre, planificada): `verification.md` con evidencia real, `estado: cerrada`.

## Tareas
- [x] Mover catálogo legacy (`ETAPAS`, `ETAPAS_FUTURAS`, `_TRANSICIONES_VALIDAS_ETAPA`, estados válidos) de `kdd.py` a `tools/dsguard/kdd_compat.py` (nuevo módulo).
- [x] `kdd_compat.py`: constantes `MAPEO_LEGACY_A_CRISPDM`, `MAPEO_LEGACY_A_KDD`, `MAPEO_LEGACY_A_MLOPS_TIER`, función `traducir_etapa_legacy(etapa_legacy) -> (fase, paso_opcional)`.
- [x] `kdd_compat.py`: excepción `KddCompatError`.
- [x] `lifecycle.py`: función pura nueva `calcular_estado_fase(estados_pasos: list) -> str` (roll-up, ver spec.md) + tests dedicados de esta función en `tools/tests/test_lifecycle.py` (extiende el archivo de Change 1).
- [x] `kdd_compat.py`: `migrar_desde_legacy(repo_root)` — lee legacy (fail-closed), traduce las 10 etapas, aplica merge de convergencia (evaluation+interpretation) y roll-up de fase-desde-pasos, arma `migrado_desde` con `etapas_legacy` completo (incluye `estado_legacy` de las 3 futuras), traduce `historial_transiciones`, escribe atómico vía `lifecycle.escribir_estado`. Idempotente, nunca toca el legacy.
- [x] `kdd_compat.py`: `kdd_init(repo_root)`, `kdd_status(repo_root)`, `kdd_transition(repo_root, etapa, hacia, motivo=None)` — repuntados, aplicando roll-up donde corresponda tras cada transición; `validar_antes_de_cerrar(repo_root, control)`, `sync_al_cerrar(repo_root, control, change_id)` — repuntados, escribiendo evidencia/changes en paso Y fase cuando el paso existe.
- [x] `kdd.py`: re-exportar `ETAPAS`/`ETAPAS_FUTURAS` desde `kdd_compat`; mantener `KddEstadoError`, `state_path` (legacy, sin cambios de comportamiento), `_CRITERIOS_DETECTABLES`/`_contenido_de_seccion`/`_dir_del_change`/`_criterios_detectables_etapa` (sin cambios); reescribir `kdd_init/status/transition/validar_antes_de_cerrar/sync_al_cerrar` como wrappers delgados sobre `kdd_compat`, envolviendo `KddCompatError`/`LifecycleEstadoError` → `KddEstadoError`.
- [x] `ds_guard.py`: nuevo grupo de subcomando `lifecycle` con `migrate` (`cmd_lifecycle_migrate`, importa `kdd_compat`/`lifecycle` directo, error handling propio y claro); actualizar `cmd_kdd_init/status/transition` para chequear `lifecycle.state_path` en vez de `kdd.state_path` donde corresponda, con mensajes distintos para "legacy sin migrar" vs "nada existe todavía".
- [x] `tools/ds_init/manifest.py`: `EntradaManifiesto` VERBATIM para `tools/dsguard/lifecycle.py` y `tools/dsguard/kdd_compat.py`; agregar `openspec/lifecycle/` a `EXCLUSIONES_PERMANENTES`.
- [x] `tools/tests/test_manifest_dsguard_parity.py`: extender para cubrir explícitamente `lifecycle.py`/`kdd_compat.py` (no depender únicamente de qué importe `ds_guard.py`).
- [x] Actualizar `.claude/skills/lead-data-scientist/kdd.md` Y `tools/ds_init/profiles/python_jupyter_data/templates/kdd.md.tmpl` (sincronizados) con la actualización factual mínima descrita en `proposal.md` punto 8.
- [x] Tests — migración completa (10 etapas con datos reales), incluye roll-up correcto en fases con pasos.
- [x] Tests — migración parcial/a mitad de lifecycle.
- [x] Tests — `futura` → `no_iniciada` + provenance (incluye evidencia real acumulada en etapa futura).
- [x] Tests — convergencia `evaluation`+`interpretation`: estado más avanzado, unión dedup, timestamp max.
- [x] Tests — roll-up `data_preparation` (`preprocessing`+`transformation`): los 4 casos explícitos del usuario (cerrada+no_iniciada→en_progreso; cerrada+en_progreso→en_progreso; ambas cerrada→cerrada; ambas no_iniciada→no_iniciada) + invarianza de orden.
- [x] Tests — `historial_transiciones` preservado con etapa legacy original + traducción.
- [x] Tests — JSON legacy corrupto / schema legacy desconocido → fail-closed vía `KddCompatError`.
- [x] Tests — lifecycle existente válido → no-op; inválido → fail-closed sin fallback; ninguno presente → no crea nada.
- [x] Tests — legacy congelado (bytes sin cambios) tras operar con CLI repuntado.
- [x] Tests — `kdd status`/`transition` repuntados vía subprocess real de `ds_guard.py` (mismo patrón que `test_kdd.py`), incluye roll-up en vivo tras transicionar un paso.
- [x] Tests — compatibilidad de identificadores legacy (`--etapa`/`--kdd-etapa`, 10 nombres).
- [x] Tests — sync SDD (`validar_antes_de_cerrar`/`sync_al_cerrar`) contra `lifecycle/state.json`, mismo contrato de retorno; verifica escritura en paso Y fase.
- [x] Tests — decision ledger: `decision add --kdd-etapa <legacy>` sin cambios en `dsguard/decision.py`.
- [x] Tests — manifest: `lifecycle.py` Y `kdd_compat.py` con entrada VERBATIM (test explícito).
- [x] Tests — instalación desde cero deja ambos módulos presentes en destino.
- [x] Tests — `ds_guard lifecycle migrate` produce errores propios claros (no depende de `kdd.py`).
- [x] Tests — `kdd.md`/template sincronizados y factualmente correctos (test simple de contenido, o verificación manual documentada en verification.md si no amerita test automatizado).

## Dependencias
Catálogo+mapeo en `kdd_compat.py` → roll-up en `lifecycle.py` (independiente, puede ir en paralelo) → migración → repunte de `kdd.py`/`ds_guard.py` → manifest (puede ir en paralelo) → doc de kdd.md (puede ir en paralelo) → tests al final de cada pieza. Depende de Change 1 (cerrado) por `lifecycle.py`; no depende de Change 0.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->
