# Verificación — 20261021-v013-release-hardening

## Resumen
Cierre de release de Harmessi v0.13.0 («Portability, Evaluation & Contract Hardening»): marcadores de versión, notas, smoke, baseline managed (una sola regeneración, 131 entradas), regresión completa, instalación limpia y upgrade desde `v0.12.0`, dogfood de evaluación/provider/adapter/portabilidad y barrido de privacidad. v0.13 habilita la comparación reproducible de configuraciones del harness; **no mejora ni promueve** el harness.

## Evidencia obtenida
- **Smoke de release (R4):** `test_v013_release_hardening_smoke.py`: 29 passed, 8 subtests passed, 0 skipped (tras los fixes de wording de T6).
- **Baseline managed (R5):** regenerado UNA vez (131 entradas). `migrate-hashes` en dry-run: Migrables 0, Ya actuales 131, No verificables 0, Desconocidas 0.
- **Sin cambios de hooks/permisos/roles/settings/guardrails (R14):** `git diff v0.12.0 --stat -- .claude tools/dsguard/hook_launcher_*.py tools/nbrunner/hook_launcher.py` solo muestra 2 líneas en `.claude/skills/lead-data-scientist/methodology.md` y `sdd.md` (contenido de skills, no políticas); ningún archivo de hooks, agentes, `settings.json` ni `guardrails.json`.
- **Doctor del repo (R6):** 30 OK, 1 WARN (`CORE-WORKING-TREE`, árbol con cambios sin confirmar durante T6), 0 ERROR, 4 N/A.
- **Regresión completa (T3), serial P=1, 242 módulos con ledger:** 242/242 OK, 0 fallos (totales de la corrida final: el único módulo con hallazgo se repitió tras el fix y quedó verde; los demás no se repitieron).
  - Skips (64 unittest) por módulo (causa individual no desglosada en el ledger; no se investigó una a una): `cards/test_resolvers*` (23), `cards/test_discovery` (5), `tests/test_human_presence` (5), `ds_profile/test_bounded_memory` (5), `ds_profile/test_io_readers` (4), `tests/test_v08_change4_leadrun_diff` (4), `reporting/test_evidence` (2), `tests/test_pathguard` (2) y 14 módulos con 1 skip cada uno (incluye `test_v013_conformance_smoke` y `test_v013_portability_smoke`, opt-in).
  - unittest: 213 módulos, 5996 tests intentados, 5932 pasados, 64 skipped, 0 fallados.
  - pytest: 29 módulos, 637 tests intentados, 637 pasados, 0 skipped, 0 fallados.
  - Hallazgo único (categoría A, atribuible a v0.13): `tools/tests/test_v013_contract_inventory.py` fallaba al correrse suelto con pytest (`ModuleNotFoundError: dsguard` al importar `tools.dsimpact.cli`) porque no agregaba `tools/` a `sys.path`, como hacen los demás tests de `tools/`. Fix de 3 líneas en el test; módulo repetido: 33 passed. Sin cambios en código de producción.
- **Instalación limpia (T4):** 131 archivos aplicados con el `ds_init` del candidate; `harmessi doctor` sobre el destino: 0 ERROR (el WARN es el árbol sin commitear; el destino de prueba no trae `.venv`, se creó vacío para el chequeo `RUNTIME-INTERPRETE`). Imports con `python -I` y `sys.path` limitado al destino: `datasources.conformance`, `datasources`, `autonomy`, `datacontracts`, `ds_profile.cli`, `dsimpact.cli`, `leadrun`, `modelquality`, `nbrunner`, `qualityevidence`, `reporting.cli`, `dsguard` OK.
- **Upgrade desde el tag `v0.12.0` (T4):** instalado con su propio `ds_init` (130 archivos); upgrade con el actual: `0.12.0 → 0.13.0`, 6 actualizados, 1 creado (`tools/datasources/conformance.py`), 0 con drift. sha256 de `CLAUDE.md` editado, `notebooks/` y `data/` idénticos antes/después. Segunda corrida: «Nada que hacer», árbol limpio. Doctor del destino: 0 ERROR (WARN esperado: `CLAUDE.md` modificado por el proyecto).
- **Doctor del repo:** 0 ERROR.
- **Privacidad:** barrido del diff desde `95f3cde` (sin `openspec/`): solo texto descriptivo de redacción/secretos sintéticos, sin rutas personales, emails ni tokens; `result.json` de los dogfood sin hallazgos; `git ls-files docs/feedback .harmessi` vacío; sin telemetría.
- **Dogfood de evaluación (T5):** suite pública `harmessi-core-synthetic` (9 casos) con adapters falsos deterministas y dos repos fixture en directorio temporal con espacios y Unicode (el candidate cambia una superficie Optimizable fixture; nunca el harness real). `identity_hash` distinto entre baseline y candidate. Veredictos observados: `candidate_better` (base 7/9 vs cand 9/9), `baseline_better` (9/9 vs 7/9), `equivalent` (9/9 vs 9/9) e `inconclusive` (candidate con un caso no disponible); `config_diff = [skills, surfaces_hash]` en todos. `run --resume` con skills cambiadas: exit 1, mensaje «incompatible», `result.json` byte a byte intacto. Provider no disponible: exit 1 sin guardar corrida.
- **Dogfood provider/adapter (T5):** `providers.conformance` de los 4 providers: nivel `contract-tested`; provider desconocido: exit 2 con mensaje claro (el CLI de conformance usa 2, el de `harmessi_bench run` usa 1); `--live` sin variable: exit 2 sin invocar. Smoke local con `HARMESSI_SMOKE_LOCAL=1`: `detect()` real de `claude` OK (3 passed). Observer conformante: 9 chequeos OK; 7 observers inválidos fallan exactamente el chequeo esperado (facetas, source_id, fuga de rutas, token, reproducibilidad, error acotado, `source_id` inválido).
- **Portabilidad Windows (T5):** directorios con espacios y Unicode, CRLF/LF (mismo hash), repo Git temporal (`leer_git`), subprocess con `cwd` Unicode y tempdir del sistema. Linux/macOS: solo contratos/tests/config de CI.

## Wording obligatorio
- remote CI execution not observed during release (workflow presente y validado estructuralmente).
- Linux/macOS no validados por ejecución.
- Providers: máximo `contract-tested`; nunca `live-validated`.
- Smoke real de `FileObserver` omitido (`ds_profile`/pandas no instalado): sin validación real de un observer, solo fixtures.
- v0.13 habilita comparación; no mejora ni promueve el harness.

## Divergencias respecto del SDD
- R11 esperaba «exit 1» ante provider faltante; el CLI de conformance devuelve exit 2 (contrato ya documentado en C3). Sin cambios.

## Limitaciones conocidas (deuda)
Ver `docs/roadmap/v0.13.md` y los `verification.md` de C1–C5 (p. ej. `ds_guard contract impact` con omisión silenciosa, celdas de notebook con magics, `verificador.md` sin el hallazgo `SKILL-TRAZA-SECCION-DUPLICADA`). GitHub Release UI pending (sin `gh`).

## Revisión (T6)
Ciclo 1: 0 BLOCKER, 2 HIGH (wording obligatorio ausente en las notas: smoke de FileObserver omitido y «GitHub Release UI pending» condicional; evidencia faltante en este documento), 7 MED, 4 LOW. Corregido: wording exacto en notas/README, smoke endurecido (frases obligatorias y `Desconocidas: 0`), fecha de `date-released` alineada a 2026-10-22, evidencia R4/R5/R6/R7/R14 agregada. No se pidió segundo ciclo (ningún HIGH modificó materialmente lo revisado).
Aclaraciones: el smoke local de `claude` pasó, pero el nivel declarado sigue siendo `contract-tested`; el barrido de privacidad excluyó `openspec/` y se hizo aparte sobre `openspec/` y `docs/` sin hallazgos de rutas personales o emails.

## Resultado final
Change 6 verificado: regresión 242/242, instalación limpia y upgrade correctos, dogfood completo, privacidad limpia. Listo para commit de release.
