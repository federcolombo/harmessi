# Tareas — 20260911-ds-profile-project-eda

estado: cerrada

## Invocaciones planificadas
1. `python-data-engineer` — borradores SDD (`proposal.md`/`spec.md`/`design.md`/`tasks.md`) — **esta invocación**.
2. `python-data-engineer` — implementación completa: paquete `tools/ds_profile/` + tests, `.claude/skills/lead-data-scientist/eda.md` + `templates/eda.md`, actualización de `tools/ds_init/manifest.py` y `.claude/skills/lead-data-scientist/SKILL.md`, espejo de plantillas en `tools/ds_init/profiles/python_jupyter_data/templates/`.
3. `data-science-reviewer` — revisión del diff completo antes de que se ejecute cualquier test.
4. `python-data-engineer` — corrección de hallazgos del reviewer (si los hay; reinvocación correctiva) o confirmación de que no hace falta; en cualquier caso deja `estado: en_verificacion`.
5. El Lead (sin subagente, Bash directo) corre la regresión completa: tests de `ds_profile`, `tools/tests`, `tools/ds_init/tests`, `tools/harmessi/tests`, `check_manifest_parity`, `harmessi doctor`.
6. `python-data-engineer` — cierre: agrega `verification.md` con la evidencia real de la corrida del paso 5, dejando `estado: cerrada`.

## Tareas
- [ ] Crear `tools/ds_profile/__init__.py`, `__main__.py`, `cli.py` (subcomando `run`, exit codes 0/1/2/3)
- [ ] Crear `tools/ds_profile/io_readers.py` (interfaz común + lector CSV stdlib + lector Parquet con import perezoso de pyarrow)
- [ ] Crear `tools/ds_profile/fingerprint.py` (hash sha256 streaming de bytes crudos)
- [ ] Crear `tools/ds_profile/schema.py` (filas, columnas, tamaño, schema, duplicados de fila)
- [ ] Crear `tools/ds_profile/column_stats.py` (nulls, cardinalidad, min/max, media/mediana/std, cuantiles, top-N, fechas)
- [ ] Crear `tools/ds_profile/quality_flags.py` (constante, casi_constante, alta_cardinalidad, posible_id, calidad agregada)
- [ ] Crear `tools/ds_profile/sampling.py` (umbrales, reservoir sampling reproducible, marcado de exactitud)
- [ ] Crear `tools/ds_profile/holdout_guard.py` (reuso de `dsguard.pathguard`/`dsguard.repo`)
- [ ] Crear `tools/ds_profile/report.py` (ensamblado de `profile.json` + `profile.md` opcional, escritura atómica)
- [ ] Crear `tools/ds_profile/tests/` con la suite completa (ver Criterios de aceptación de `spec.md`)
- [ ] Crear `.claude/skills/lead-data-scientist/eda.md`
- [ ] Crear `.claude/skills/lead-data-scientist/templates/eda.md`
- [ ] Actualizar `tools/ds_init/manifest.py` (entradas nuevas + `EXCLUSIONES_PERMANENTES`)
- [ ] Actualizar `.claude/skills/lead-data-scientist/SKILL.md` (referencia a `eda.md`, mención de `ds_profile` como CLI del Lead)
- [ ] Espejo en `tools/ds_init/profiles/python_jupyter_data/templates/` para que `eda.md`/plantilla lleguen al proyecto destino

## Dependencias
Ninguna dependencia externa a este cambio; no depende de que otro cambio SDD esté abierto o cerrado primero.

## Próximo paso exacto
No aplica (no es `pausada_bloqueada`).
