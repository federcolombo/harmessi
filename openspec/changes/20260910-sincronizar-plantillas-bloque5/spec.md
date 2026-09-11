# Spec — 20260910-sincronizar-plantillas-bloque5

## Requisitos
- R1. `sdd.md.tmpl` debe quedar idéntico a `.claude/skills/lead-data-scientist/sdd.md` salvo por
  la ausencia de cualquier placeholder que ese archivo no tenga hoy (no tiene ninguno) — en la
  práctica, agregar únicamente la subsección "### Bounded remediation" faltante, sin tocar el
  resto del archivo.
- R2. `SKILL_lead_data_scientist.md.tmpl` debe reflejar los dos agregados de Bloque 5 presentes en
  `SKILL.md` (referencia a `decision-ledger.md`; nota de `control["remediaciones"]` en "Límite de
  intentos"), preservando exactamente `{{NOMBRE_PROYECTO}}` donde ya está (nunca reemplazarlo por
  "harmessi" ni por ningún valor literal).
- R3. `verificador.md.tmpl` debe incluir los comandos `decision *`/`remediation
  {resolve,extend}`, la nota de exit codes del Bloque 5, los 14 códigos de hallazgo nuevos
  (`DECISION-*`/`REMEDIACION-*`) y la documentación del campo `remediaciones[]`, tal como
  aparecen en `verificador.md` hoy.
- R4. Nuevo `decision-ledger.md.tmpl`: copia verbatim de `decision-ledger.md` (sin placeholders,
  ya que el archivo fuente no referencia el nombre del proyecto ni ningún otro dato instalable).
- R5. `tools/ds_init/manifest.py`: nueva `EntradaManifiesto` con `fuente` apuntando al nuevo
  `.tmpl`, `tratamiento=PLANTILLA`, `destino=".claude/skills/lead-data-scientist/decision-ledger.md"`,
  agregada junto a las demás entradas `PLANTILLA` de la skill (después de la entrada de
  `kdd.md.tmpl`, mismo bloque temático).
- R6. Ningún otro archivo de `tools/ds_init/` se modifica: `kdd.md.tmpl`, los 4 `agent_*.tmpl`,
  `nbrunner_manifest.py.tmpl`, `CLAUDE.md.tmpl`, `profile.json` quedan intactos.
- R7. `check_manifest_parity` sigue reportando `[OK]` para las rutas VERBATIM (ninguna entrada
  VERBATIM se toca) y sigue listando las plantillas `PLANTILLA` en su sección `[INFO]` — ese
  listado es incondicional por diseño (`listar_plantillas()` no compara contenido), así que
  seguir apareciendo ahí **no** es un fallo; lo que se verifica es que el contenido de cada
  `.tmpl` tocado coincide con su archivo vivo (R1-R4), no que desaparezca de la lista.
- R8. Ningún test existente de `tools/ds_init/tests` debe romperse — en particular los que iteran
  `MANIFEST` (conteo de entradas, tratamientos válidos, resolución de `fuente` vía
  `raiz_repo_origen()`).

## Criterios de aceptación
- [ ] `diff sdd.md.tmpl sdd.md` vacío.
- [ ] `diff SKILL_lead_data_scientist.md.tmpl SKILL.md` solo difiere en `{{NOMBRE_PROYECTO}}` vs
      `harmessi` (ninguna otra diferencia).
- [ ] `diff verificador.md.tmpl verificador.md` vacío.
- [ ] `decision-ledger.md.tmpl` existe y es idéntico a `decision-ledger.md`.
- [ ] `tools/ds_init/manifest.py` tiene una `EntradaManifiesto` nueva para
      `decision-ledger.md.tmpl` → `.claude/skills/lead-data-scientist/decision-ledger.md`,
      `tratamiento=PLANTILLA`.
- [ ] `python -m tools.ds_init.check_manifest_parity` sigue devolviendo exit 0 (`[OK]` en rutas
      VERBATIM) y ahora lista 10 entradas `PLANTILLA` (las 9 anteriores + la nueva).
- [ ] `tools/ds_init/tests`, `tools/tests`, `tools/harmessi/tests` pasan sin regresión.
- [ ] `harmessi doctor` sigue en 0 `[ERROR]`.

## Unidad de análisis / grain (condicional)
No aplica — cambio técnico de tooling/harness (sincronización de plantillas), sin decisión de ML
de fondo.

## Cutoff / information boundary (condicional)
No aplica — cambio técnico de tooling/harness (sincronización de plantillas), sin decisión de ML
de fondo.

## Baseline (condicional)
No aplica — cambio técnico de tooling/harness (sincronización de plantillas), sin decisión de ML
de fondo.

## Métrica primaria (condicional)
No aplica — cambio técnico de tooling/harness (sincronización de plantillas), sin decisión de ML
de fondo.

## Métricas secundarias (opcional)
No aplica.
