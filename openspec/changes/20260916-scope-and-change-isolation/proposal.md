# Proposal — 20260916-scope-and-change-isolation

## Contexto (audit primero — hallazgo clave)

Auditoría directa de `tools/dsguard/sdd.py`, `tools/ds_guard.py` (`cmd_validate`), `tools/dsguard/repo.py`
confirma que **el scope check ya existe parcialmente**: `repo.files_out_of_scope(repo_root,
rutas_autorizadas)` compara `repo.list_dirty_files` (equivalente a `git status --porcelain`) contra
`control["alcance"]["rutas_autorizadas"]`, y produce `Finding("ALCANCE-RUTA", ...)`. Se usa en DOS
lugares (`cmd_validate` en `ds_guard.py`, y `sdd.gate_cierre`), duplicado.

**Gap real**: `list_dirty_files` (`git status`) solo ve el **working tree actual** — un archivo
tocado fuera de scope y ya COMMITEADO dentro del rango del Change (después de `baseline.commit`,
capturado por `ds_guard init`) es invisible para el check de hoy si el working tree quedó limpio de
nuevo. Esto es exactamente "expansión accidental"/"cambios encadenados no declarados" que el
roadmap pide poder detectar.

Este Change NO construye un mecanismo nuevo desde cero — **extiende y consolida** el que ya existe,
eliminando la duplicación entre `cmd_validate` y `gate_cierre`, y ampliando la fuente de "qué se
tocó" de "solo working tree" a "working tree + diff completo desde `baseline.commit`" (misma
semántica de `git diff <ref>` ya usada por `tools/dsimpact` en Change 1 — sin importar `dsimpact`
desde `dsguard`, dirección de dependencia prohibida; se reusa `repo._git` directamente, igual que
Change 1).

## Qué se construye

1. `tools/dsguard/scope.py` (módulo nuevo, pequeño): `archivos_tocados_desde_baseline(repo_root,
   baseline_commit)` (git diff --name-status -M contra el working tree, mismo patrón que
   `dsimpact.git_source`) + `evaluar_alcance(repo_root, control)` (unión de working tree sucio +
   diff desde baseline, contra `rutas_autorizadas`, produce `list[core.Finding]` con código
   `ALCANCE-RUTA`, código canónico único).
2. `sdd.gate_cierre` y `ds_guard.cmd_validate` dejan de llamar `repo.files_out_of_scope` inline y
   pasan a llamar `scope.evaluar_alcance` — una sola implementación, sin duplicar.
3. Degradación con gracia: sin `baseline.commit` en `control.json`, o si la referencia ya no es
   válida (ej. rebase/squash), se degrada silenciosamente al comportamiento actual (solo working
   tree) — nunca bloquea `validate`/`cierre` por un problema técnico ajeno al scope real. Documentado
   como límite conocido, no oculto.
4. `verificador.md` (+ `.tmpl`) actualiza la descripción de `ALCANCE-RUTA` para reflejar la cobertura
   ampliada.

## Qué NO se construye (fuera de alcance explícito)

Sandbox de filesystem, merge inteligente, sistema de permisos genérico, graph de dependencias, CLI
nueva (se reusa `ds_guard validate`, ya es el punto de entrada), enforcement que bloquee escrituras
en tiempo real (eso es pathguard/write_scopes, ya existe y no se toca), integración con `dsimpact`
más allá de reusar el mismo patrón de `git diff` (no se cruza semánticamente "impacto" con "scope" —
son conceptos relacionados pero distintos, mismo criterio que Change 0 mantuvo separados scientific
validity y readiness).

## Decisión/deuda registrada
Si más adelante se quiere que `ALCANCE-RUTA` bloquee `promote`/`readiness`, es una decisión de un
change futuro, no de este.
