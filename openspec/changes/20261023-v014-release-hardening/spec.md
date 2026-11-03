# Spec — 20261023-v014-release-hardening

**R1.** `HARNESS_VERSION == "0.14.0"`; `CITATION.cff` (`version`, `date-released`), README y `docs/roadmap/v0.14.md` (estado) alineados.
**R2.** `docs/releases/v0.14.0.md` en inglés: narrativa Evidence-Driven Harness Improvement; qué puede (generar/aceptar candidates, probar, comparar, producir promotion proposals gobernadas) y qué NO (auto-modificarse, auto-promover, tocar Protected, saltear governance); inspiración conceptual sin dependencia externa; wording obligatorio (remote CI execution not observed during release; Linux/macOS no validados por ejecución; providers máximo `contract-tested`; GitHub Release UI pending si no hay `gh`; H1 UNCONFIRMED).
**R3.** `docs/contracts/inventory.json` incluye los contratos nuevos (CLI `harmessi_improve`, candidate, probe, decision, proposal, lesson, budget state) con clase `experimental` o `public-candidate` y su ancla de versión; `harmessi_version_documented` = `0.14.x`; los tests de inventario de v0.13 pasan.
**R4.** Smoke de release `test_v014_release_hardening_smoke.py`: versión, notas y wording, Changes cerrados, módulos presentes, `harmessi_improve` en `SOLO_CHECKOUT`, sin imports de red/telemetría, barrido de privacidad del diff.
**R5.** Dogfood A–I como tests deterministas sobre un repo temporal con una copia de `diagnosing-bugs.md` (la skill real no se modifica): A candidate vs baseline con evidencia; B `candidate_better`; C `baseline_better`; D `equivalent`; E `inconclusive`; F Protected rechazado antes del probe; G propuesta de promoción lista y gate bloqueado sin T1 (y desbloqueado solo con un Change T1 falso); H lesson evidence-backed sin fuga de conocimiento del proyecto; I agotamiento determinista de `max_candidates`/`max_probe_cycles`. Más: un candidate no queda `promotable` por metadata/texto "better".
**R6.** Baseline `.ds_init/control.json` regenerado UNA vez al final (`harness_version` 0.14.0); `migrate-hashes` dry-run: 0 migrables; sin drift inesperado; sin adoptar drift.
**R7.** Regresión completa serial P=1 con ledger por batch; fallos → fix y re-run solo del batch afectado.
**R8.** Instalación limpia y upgrade desde el tag `v0.13.0` con idempotencia; preservan CLAUDE.md editado, notebooks, datos, GLOSSARY y skills locales; no instalan `.harmessi/improvement` ni candidates/lessons.
**R9.** Doctor del repo: 0 ERROR.
**R10.** CI: `portability-smoke.yml` incluye los tests nuevos livianos; acciones actualizadas solo si la actualización es compatible y los tests del workflow pasan.
**R11.** Sin cambios de hooks/permisos/roles/settings/guardrails; sin telemetría; sin push de `v0.14-dev`.
**R12.** Auditoría de contratos pendientes para v1.0 registrada en `docs/roadmap/v0.14.md`.

## Criterios de aceptación
- [ ] R1–R4. - [ ] R5 dogfood. - [ ] R6–R9 baseline/regresión/install/Doctor. - [ ] R10–R12.
