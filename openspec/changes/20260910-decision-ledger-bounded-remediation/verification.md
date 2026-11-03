# Verificación — 20260910-decision-ledger-bounded-remediation

## Evidencia obtenida
- `tools/tests` (incluye `test_decision.py` con 24 tests y `test_remediation.py` con 25 tests,
  ambos nuevos de este cambio): 191 passed, 2 skipped (skips preexistentes de symlink, no
  relacionados con este cambio) — corrida por el Lead vía
  `.venv/Scripts/python.exe -m pytest tools/tests -v`.
- `tools/ds_init/tests`: 53 passed — sin regresión.
- `tools/harmessi/tests`: 56 passed — sin regresión.
- `check_manifest_parity`: `[OK] Todas las rutas VERBATIM del manifiesto existen`; 9 entradas
  marcadas `PLANTILLA` para revisión manual (`.claude/agents/*.md`, `SKILL.md`, `sdd.md`,
  `verificador.md`, `kdd.md`, `tools/nbrunner/manifest.py`) — preexistente, no bloqueante (ver
  limitación abajo).
- `harmessi doctor`: 26 [OK], 9 [WARN], 0 [ERROR]. Los 9 WARN son `CORE-WORKING-TREE` (working
  tree con cambios sin commitear, esperado en este punto del ciclo) y 8 `HARMESSI-DRIFT` sobre
  archivos administrados por el harness. De esos 8, 3 corresponden a archivos efectivamente
  modificados por este cambio —
  `.claude/skills/lead-data-scientist/{SKILL.md,sdd.md,verificador.md}`—; los 5 restantes son
  drift preexistente sobre archivos que este cambio no tocó (no se agregó
  `decision-ledger.md` a la lista de drift porque es un archivo nuevo, no una modificación de
  uno ya administrado).
- Reviewer (`data-science-reviewer`): 1 hallazgo bloqueante (documentación de ownership
  inconsistente con el modelo de permisos de agentes) + 4 notas menores, todos corregidos o
  documentados como deuda explícita en `design.md` antes de este cierre.
- Dos reinvocaciones correctivas consumidas en la sesión `s1` (hallazgos del reviewer; bug de
  test `git init` faltante en `_crear_dir_temporal_change`) — `s1` se cerró `pausada` al agotar
  su presupuesto de reintentos y tiempo; la sesión `s2` completó el fix final y esta verificación.

## Resultado final
Las dos capacidades (decision ledger en `openspec/decisions/ledger.jsonl` y bounded remediation
en `control["remediaciones"]`) quedaron implementadas, documentadas y cubiertas por 49 tests
nuevos (`test_decision.py` + `test_remediation.py`), sin romper ningún test preexistente de
`tools/tests`, `tools/ds_init/tests` ni `tools/harmessi/tests`. La extensión de
`hook_presupuesto.py` fue validada en la práctica durante esta misma sesión de implementación:
bloqueó una convocatoria real de subagente al agotarse `max_reintentos` de `s1`, confirmando el
enforcement en tiempo real descrito en `spec.md` R19.

## Limitaciones
- Los archivos `.tmpl` de `tools/ds_init/profiles/python_jupyter_data/templates/` (`sdd.md.tmpl`,
  `SKILL_lead_data_scientist.md.tmpl`, `verificador.md.tmpl`) no se actualizaron con el contenido
  nuevo de Bloque 5 — quedan desincronizados de los archivos reales del proyecto hasta que se
  sincronicen a mano (`check_manifest_parity` ya los señala como `PLANTILLA` a revisar). Un
  proyecto nuevo creado con `ds_init` hoy no incluiría la documentación de decision ledger/bounded
  remediation en su scaffold inicial.
- Deuda explícita de diseño documentada en `design.md` "Deuda para v0.3+": persistencia de
  findings de reviewer/metodólogo como artefacto propio; enforcement en tiempo real por finding
  específico en el hook; hash/cadena de integridad del ledger; gates automatizados
  decision-ledger↔KDD; y la laguna de integridad de `decision_supersede`/`decision_revoke` sobre
  una `referencia` ya afectada (agregada durante la corrección de hallazgos del reviewer).
