# Verificación — 20261020-v011-release-hardening

## Resumen
Change 6 de v0.11: versión `0.11.0`, notas de release (inglés), smoke de release, baseline managed regenerado una vez, regresión completa por batches seriales, dogfooding A/B/C, Doctor, privacidad. Sin features nuevas. SDD aprobado por hash (T0/declared).

## Evidencia obtenida

### Regresión completa (batches seriales, P=1, foreground; ledger por módulo)
| batch | attempted | passed | skipped | failed |
|---|---|---|---|---|
| unittest: 235 módulos/clases (incl. `test_doctor` dividido en sus 12 clases por duración) | 5781 tests | 5781 salvo 3 smokes | 51 | 3 (smokes de versión, ver abajo) |
| pytest (.venv) de los 21 módulos pytest-only (datacontracts, datasources, fallback, harmessi_bench, modelquality, providers, qualityevidence, routing, leadrun fixtures) | 636 | 636 (+158 subtests) | 0 | 0 |
- Los 3 fallos (`test_v09/v010/v011_release_hardening_smoke`: `control.json` en 0.10.0 ≠ 0.11.0) se corrigieron regenerando el baseline managed; re-corridos: 12 + 21 + 19 OK. Los 21 módulos que unittest no recolecta (rc=5 / ImportError) son pytest-style y se ejecutaron con el intérprete correcto (`.venv`, pytest 9.1.1).
- Corridas previas amplias paralelas fueron terminadas por presión de memoria (incidente operacional, no funcional); se reemplazaron por batches seriales. Comparación con baseline: las fallas observadas en la corrida amplia inicial del Change 1 (28 módulos) fallaban también en el baseline; en la regresión final no queda ninguna.
- Pendiente de transparencia: `test_doctor` se midió por clases (10+9+8+6+5+10+2+6+5+3 + las restantes registradas en el ledger), no como un único módulo.

### Baseline managed
`regenerar_control(..., stage="experiment")` una vez: `harness_version` 0.11.0, 127 entradas; `migrate-hashes` dry-run: Migrables 0, Ya actuales 127, No verificables 0, Desconocidas 0.

### Doctor
Este repositorio: 30 OK, 1 WARN (`CORE-WORKING-TREE`, árbol sin commitear durante el check), 0 ERROR, 4 N/A. Proyectos dogfood: 0 ERROR cuando existe `.venv`; sin `.venv` aparece `RUNTIME-INTERPRETE` ERROR (esperado: los proyectos temporales no crean venv).

### Dogfooding (fixtures sintéticos, directorios temporales, script reproducible)
- **A. Proyecto nuevo v0.11.0:** `install --execute` (127 archivos), imports reales desde el destino instalado con `python -I` (core, decision, scope, repo, sdd, scope_amendments, human_presence, guardrails_adoption, glossary, ds_guard), `ds_guard init`/`validate` (los únicos hallazgos fueron `__pycache__` generados por el propio chequeo de imports), `decision verify` sin hallazgos, Doctor sin errores de producto.
- **B. Upgrade desde el tag público `v0.10.0`** (checkout del tag, `harness_version` 0.10.0): se agregaron GLOSSARY.md, datos, notebook, Card y una decisión del ledger; `upgrade` dry-run listó 13 managed a actualizar y preservó guardrails/CLAUDE.md; `--execute`: «Upgrade completo ('0.10.0' -> '0.11.0'): 13 actualizado(s)»; segunda corrida «Nada que hacer»; archivos project-owned byte-idénticos (sha256 antes/después); `decision verify` sin hallazgos; Doctor `HARMESSI-VERSION` OK y `HARMESSI-MIGRACION` OK.
- **C. Upgrade interrumpido:** kill duro del proceso (`os._exit`) tras el primer reemplazo → Doctor `HARMESSI-MIGRACION` ERROR con el remedio literal, `upgrade` abortó indicando `recover`, `recover` dry-run listó la restauración, lock huérfano borrado a mano (documentado), `recover --execute` dejó el árbol idéntico al commit v0.10 (git status vacío), `upgrade` convergió y la segunda corrida fue «Nada que hacer»; Doctor con `.venv`: 0 ERROR.
- Primer intento de C: el script de corte tenía un `sys.path` inválido para Python nativo en Windows (la interrupción no ocurrió y el upgrade completó); se corrigió y se repitió el escenario completo.

### Reviewer (release notes/smoke/privacidad, solo lectura)
0 bloqueantes, 0 altos, 5 medios: copy evalúa solo destino (notas corregidas); upgrade desde tag real no probado (ahora probado y documentado); limitación del último fix del Change 4 sin revisar independiente (agregada); reloj wall-clock sin pausa (agregada); smoke no verificaba todas las afirmaciones (reforzado). No se usó un segundo ciclo.

### Privacidad
Barrido de los 98 archivos cambiados desde `2e76956` (rutas personales, usuario real, emails, tokens, nombres de proyecto/fuentes reales): solo URLs públicas del repositorio y fixtures sintéticos preexistentes. `git ls-files docs/feedback .harmessi` vacío.

## Limitaciones
Validación en host Windows únicamente (POSIX/macOS sin host real). El upgrade desde `v0.10.0` se probó con fixtures sintéticos. `dsimpact/git_source.py` conserva fail-open (deuda diferida). H1 permanece UNCONFIRMED; 4A no entró.

## Divergencias respecto del SDD
La regresión se hizo en batches seriales por módulo (no por directorio) por restricciones de memoria; los módulos pytest-only se ejecutaron con pytest del `.venv`.

## Resultado final
Candidato 0.11.0 verificado: regresión verde, dogfood A/B/C verde, Doctor sin errores, baseline coherente, privacidad limpia. Listo para publicar.
