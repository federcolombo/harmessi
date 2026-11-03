# Tareas — 20260911-release-v0-2-0-blockers

estado: cerrada

## Invocaciones planificadas
1. `python-data-engineer` — borradores SDD — **esta invocación**.
2. `python-data-engineer` — implementación de los 9 puntos del alcance + tests.
3. `data-science-reviewer` — revisión del diff antes de correr tests.
4. `python-data-engineer` — corrección de hallazgos del reviewer (si los hay) o confirmación; deja `estado: en_verificacion`.
5. El Lead (Bash directo) corre: regresión completa (4 suites + check_manifest_parity + doctor) + instalación real en scratch repo + verificación empírica de los 4 puntos pedidos por el usuario.
6. `python-data-engineer` — cierre: agrega "## Verificación" a `tasks.md` con evidencia real, deja `estado: cerrada`.

## Tareas
- [ ] Entrada `decision.py` en `MANIFEST`
- [ ] Test de la omisión puntual (decision.py / módulos dsguard importados por ds_guard.py)
- [ ] `HARNESS_VERSION = "0.2.0"` en `version.py`
- [ ] `CITATION.cff` version 0.2.0 + date-released 2026-09-11
- [ ] `README.md` actualizado (3 CLIs, ds_profile, Project EDA)
- [ ] `SKILL_lead_data_scientist.md.tmpl` sincronizado con `SKILL.md`
- [ ] `CLAUDE.md.tmpl` actualizado con ds_profile/Project EDA
- [ ] `EXCLUSIONES_PERMANENTES` con test_decision.py/test_remediation.py si corresponde

## Dependencias
Ninguna.

## Próximo paso exacto
No aplica.

## Verificación

### Evidencia obtenida
```
tools/ds_profile/tests/  -> 129 passed, 5 skipped (Parquet, sin pyarrow), 4 subtests (3.56s)
tools/tests/             -> 193 passed, 2 skipped (55.17s) -- incluye los 2 tests nuevos de test_manifest_dsguard_parity.py
tools/ds_init/tests/     -> 53 passed (68.61s)
tools/harmessi/tests/    -> 56 passed (200.62s)
check_manifest_parity    -> exit 0, OK
harmessi doctor          -> exit 0, 25 OK, 10 WARN (drift preexistente + el propio manifest.py/version.py/README.md/etc. modificados en este cambio, esperado), 0 ERROR
```

### Revisión de data-science-reviewer
Sin hallazgos bloqueantes. Todos los 7 criterios de aceptación de la revisión cumplidos: entrada de manifest bien formada, test nuevo con lógica correcta (ceguera documentada y aceptada ante `import dsguard.decision` sin `from`, o ante un import envuelto en try/except -- ninguno es el patrón actual), alcance respetado (nbrunner/.gitignore sin tocar), versión consistente entre CITATION.cff y version.py, README preciso (exit codes/CSV-Parquet/features verificados contra el código real), templates sincronizados fielmente, EXCLUSIONES_PERMANENTES correcto. 2 notas menores sin acción requerida: una imprecisión preexistente en SKILL.md (de un cambio anterior, fuera de este alcance) sobre `.harmessi/profiles` como si fuera default automático quimba `--output` es requerido; un caso de ceguera del test ya documentado en su propio docstring.

### Verificación empírica en scratch repo (instalación real, descartable, fuera del repo)
1. `python -m tools.ds_init --destino <scratch> --nombre audit-scratch --execute`: 52 archivos instalados (51 antes de este fix + `decision.py`).
2. `python -m tools.ds_guard status --change-id nope` en el scratch repo: ya NO da `ImportError` -- da el error esperado de "cambio inexistente" (exit 2), confirmando que `ds_guard.py` carga correctamente.
3. `python -m tools.ds_guard decision list` en el scratch repo: corre sin error, exit 0 (ledger vacío) -- confirma que el decision ledger es funcionalmente accesible.
4. `.ds_init/control.json` del scratch repo: `"harness_version": "0.2.0"`.
5. `CLAUDE.md` del scratch repo: `Instalado por ds_init (harness 0.2.0) el <fecha>`.
6. `.claude/skills/lead-data-scientist/SKILL.md` y `CLAUDE.md` del scratch repo: ambos mencionan `ds_profile`/`eda.md`/Project EDA (grep confirmado línea por línea).
7. `tools/dsguard/decision.py` y el paquete completo `tools/ds_profile/` presentes en el scratch repo.
8. Scratch repo eliminado al terminar (era descartable, fuera de este repositorio real).

### Diferencias contra la spec
Ninguna. Los 8 puntos de `## Alcance` de `proposal.md` se implementaron exactamente como se especificaron.

### Limitaciones
- Las 2 notas menores del reviewer no requirieron corrección (ver arriba) -- documentadas, no accionadas, por estar fuera del alcance acordado de este cambio puntual.
- El scanner genérico de imports vs. manifest sigue siendo deuda futura explícita (no implementado a propósito, según lo acordado).
- Deuda ya conocida de bloques anteriores sin cambios: Parquet real de `ds_profile` no probado end-to-end (sin pyarrow instalado); sin prueba con dataset de varios GB.

### Resultado final
BLOCKER de release (decision.py ausente del manifest) corregido y verificado empíricamente con una instalación real. Versión estampada correctamente en 0.2.0 en todos los lugares machine-readable relevantes. README y ambos templates instalables (SKILL_lead_data_scientist.md.tmpl, CLAUDE.md.tmpl) sincronizados con las capacidades reales de ds_profile/Project EDA. Regresión completa en verde. Harmessi v0.2.0 queda lista para taggear en cuanto a los hallazgos mínimos identificados por la auditoría de release -- la decisión final de taggear/commitear queda en manos del usuario. No se hizo commit/tag/push en este cambio.
