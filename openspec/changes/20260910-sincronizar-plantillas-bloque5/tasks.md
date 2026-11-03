# Tareas — 20260910-sincronizar-plantillas-bloque5

estado: cerrada

## Invocaciones planificadas
- `python-data-engineer` (1ra, ya en curso): redactar borradores SDD — esta misma invocación.
- `python-data-engineer` (2da, planificada): sincronizar los 3 `.tmpl` existentes, crear
  `decision-ledger.md.tmpl`, registrar la entrada en `tools/ds_init/manifest.py`.
- `data-science-reviewer` (planificada): revisar el diff antes de ejecutar nada.
- `python-data-engineer` (planificada, corre siempre después del reviewer): corrige hallazgos si
  los hay; deja `estado: en_verificacion`.
- El Lead corre `tools/ds_init/tests`, `tools/tests`, `tools/harmessi/tests`,
  `check_manifest_parity`, `harmessi doctor`, y revisa qué archivos de `openspec/` corresponde
  versionar.
- `python-data-engineer` (planificada, cierre): escribe `verification.md` con la evidencia real.

## Tareas
- [x] Borradores SDD.
- [ ] Sincronizar `sdd.md.tmpl`.
- [ ] Sincronizar `SKILL_lead_data_scientist.md.tmpl` (preservando `{{NOMBRE_PROYECTO}}`).
- [ ] Sincronizar `verificador.md.tmpl`.
- [ ] Crear `decision-ledger.md.tmpl`.
- [ ] Registrar la entrada nueva en `tools/ds_init/manifest.py`.
- [ ] Revisión de `data-science-reviewer`.
- [ ] Corrección de hallazgos (si los hay).
- [ ] Regresión completa (Lead, vía Bash): `ds_init/tests`, `tools/tests`, `harmessi/tests`,
      `check_manifest_parity`, `harmessi doctor`.
- [ ] Revisión de qué artefactos de `openspec/` corresponde versionar.
- [ ] `verification.md` con evidencia real.

## Dependencias
Ninguna — depende únicamente de contenido ya aprobado y cerrado en Bloque 5.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->
