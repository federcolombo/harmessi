# Spec — 20260916-scope-and-change-isolation

## Requisitos

### R1 — `tools/dsguard/scope.py`
```python
def archivos_tocados_desde_baseline(repo_root: Path, baseline_commit: str) -> list:
    """git diff --name-status -M <baseline_commit> (contra el working tree actual --
    incluye commits ya hechos desde baseline Y cambios sin confirmar, mismo comando/parseo
    que dsimpact.git_source.listar_cambios, pero reimplementado LOCALMENTE acá -- dsguard
    NUNCA importa dsimpact, dirección de dependencia prohibida, ver design.md).
    Devuelve rutas relativas POSIX (lado nuevo para renombres). Si `baseline_commit` no es
    una referencia válida, o el comando falla por cualquier motivo, devuelve [] (degradación
    silenciosa documentada, nunca lanza)."""

def evaluar_alcance(repo_root: Path, control: dict) -> list:
    """list[core.Finding], código único 'ALCANCE-RUTA'. Unión de:
    (a) repo.list_dirty_files(repo_root) (ya existente, working tree);
    (b) archivos_tocados_desde_baseline(repo_root, control["baseline"]["commit"]) si
        `control.get("baseline", {}).get("commit")` existe (si no, (b) es vacío).
    Deduplicada, comparada contra control["alcance"]["rutas_autorizadas"] vía
    repo.path_matches_any (reusado tal cual, sin reimplementar matching)."""
```
Reusa `dsguard.repo._git` (mismo patrón que `dsimpact.git_source`, `dsguard.notebooks`) y
`repo.path_matches_any`/`repo.list_dirty_files` (públicas, ya existentes) — nunca reimplementa
matching de patrones ni el wrapper de subprocess.

### R2 — Consolidación (eliminar duplicación)
`sdd.gate_cierre` y `ds_guard.cmd_validate` reemplazan su bucle inline
(`for r in repo.files_out_of_scope(repo_root, rutas_autorizadas): findings.append(Finding("ALCANCE-RUTA", ...))`)
por una sola llamada a `scope.evaluar_alcance(repo_root, control)`. `repo.files_out_of_scope` NO se
borra (puede tener otros usos/tests) pero deja de ser el camino usado por SDD para este check —
verificar con Grep antes de tocar nada más que la dependa.

### R3 — Fail-open documentado, no fail-closed
A diferencia de `pathguard`/`scientific_validity` (fail-closed ante corrupción), acá la ausencia o
invalidez de `baseline.commit` degrada al comportamiento YA EXISTENTE (solo working tree) sin
bloquear `validate`/`cierre` — un Change viejo sin `baseline.commit` (formato previo a esta versión)
no debe romperse. Documentado explícitamente como decisión deliberada (no un descuido), distinta del
criterio fail-closed de otros módulos.

### R4 — Docs
`.claude/skills/lead-data-scientist/verificador.md` + su `.tmpl` (idénticos entre sí): actualizar la
línea que describe `ALCANCE-RUTA` para reflejar que ahora cubre working tree + diff completo desde
`baseline.commit`, no solo "archivo sucio".

## Criterios de aceptación
- [ ] Archivo tocado fuera de scope, luego commiteado (working tree vuelve a estar limpio) →
      `evaluar_alcance` sigue reportando `ALCANCE-RUTA` (vía diff desde baseline) — el bug que
      `files_out_of_scope` solo no detectaba.
- [ ] Archivo tocado fuera de scope, sin commitear → sigue detectado (vía `list_dirty_files`, como
      hoy).
- [ ] Archivo dentro de `rutas_autorizadas` (commiteado o no) → sin finding.
- [ ] Sin `baseline.commit` en `control.json` → mismo comportamiento que hoy (solo working tree),
      sin excepción ni finding técnico nuevo.
- [ ] `baseline.commit` con una referencia que ya no existe (rebase/squash) → degrada
      silenciosamente, sin romper `validate`/`cierre`.
- [ ] `cmd_validate` (`ds_guard.py`) y `gate_cierre` (`sdd.py`) producen el mismo resultado para el
      mismo estado de repo (una sola fuente de verdad).
- [ ] Determinismo: mismo estado de repo → mismo conjunto de findings, mismo orden.
- [ ] Suite completa (`tools/tests`, `tools/ds_init/tests`, `tools/harmessi/tests`) pasa;
      `check_manifest_parity`/`harmessi doctor` sin errores nuevos.

## Cutoff / information boundary
No aplica.

## Baseline (condicional — modeling)
No aplica.
