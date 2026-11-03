# Spec — 20261021-v013-release-hardening

## A. Versión y notas
**R1.** `HARNESS_VERSION == "0.13.0"` y `CITATION.cff` `version: 0.13.0` (fecha de release); `README.md` documenta v0.13 y enlaza `docs/releases/v0.13.0.md`; no existen `VERSION` ni `pyproject.toml` raíz.
**R2.** `docs/releases/v0.13.0.md` en inglés con las secciones: resumen (Portability, Evaluation & Contract Hardening), qué entra (evaluation & benchmark foundation, reproducible runs, provider/adapter conformance, portability + dsimpact fail-closed + duplicate heading finding + CI workflow, contract inventory/compatibility/deprecation), compatibilidad y upgrade (incluye el nuevo hallazgo `SKILL-TRAZA-SECCION-DUPLICADA`), **Known limitations** (evals deterministas = proxy de texto; Windows único host de ejecución; CI sin ejecución remota observada; providers max `contract-tested`; live opt-in no validado; resumen de deuda), y la aclaración explícita: **v0.13 enables evidence-based comparison but does NOT automatically improve or promote harness changes**.
**R3.** Las notas no afirman «self-improving», optimizer, candidate generation, promoción automática, lecciones globales, validación Linux/macOS por ejecución ni `live-validated`; las menciones solo aparecen negadas en la misma oración.

## B. Smoke de release
**R4.** `test_v013_release_hardening_smoke.py` valida: versión (>= 0.13.0) y coherencia CITATION/control.json/README; notas (contenido clave, afirmaciones prohibidas negadas, Known limitations); Changes 0–5 de v0.13 cerrados y Change 6 en implementación/verificación/cerrado; roles/permisos sin cambio (maxTurns, tools por agente) y `git diff v0.12.0` vacío sobre contratos de agentes, settings, guardrails y hooks; skills v0.12 presentes y válidas; módulos de v0.13 presentes (`harmessi_bench` suite/runmanifest/redact, `providers/conformance`, `datasources/conformance`, `deprecation`), `datasources/conformance.py` en el manifest, workflow presente y `docs/contracts/inventory.json` válido; roadmap v0.13 menciona los Changes y dirección v0.14; higiene Git (feedback/evidencia local no versionados, sin temporales); privacidad (sin rutas personales, emails ni tokens en archivos versionados, con los Changes de release excluidos del sweep); `migrate-hashes` dry-run sin pendientes. Todo determinista, sin red.

## C. Baseline y Doctor
**R5.** `.ds_init/control.json` se regenera **una sola vez** (`harness_version` 0.13.0, entradas con `hash_alg` válido); `migrate-hashes` dry-run: 0 migrables, 0 no verificables, 0 desconocidas; sin adoptar drift (no se modifican archivos fuente para que coincidan).
**R6.** Doctor en este repo: 0 ERROR; WARN solo legítimos y documentados; conteo registrado.

## D. Regresión completa
**R7.** Regresión completa serial P=1 en foreground por módulo con ledger fuera del repo; tabla `batch | attempted | passed | skipped | failed`; si falla un módulo: corregir y repetir SOLO el afectado. 0 fallos finales. Los skips se listan por causa.

## E. Instalación y upgrade
**R8.** Fresh install de v0.13.0 en un directorio temporal: instala los archivos del manifest, las 4 skills, `GLOSSARY.md` NO se crea; **imports desde el destino instalado** (no desde el repo) de los módulos instalados que v0.13 agrega (`datasources.conformance` y los preexistentes críticos); Doctor del destino sin errores de producto.
**R9.** Upgrade desde el tag público `v0.12.0` (instalado con su propio `ds_init`) a v0.13.0: actualiza los managed, preserva project-owned (`CLAUDE.md` editado, `GLOSSARY.md`, datos, notas, approvals/ledger/amendments, skills/contexto de proyecto); segunda corrida idempotente («Nada que hacer») con árbol limpio.

## F. Dogfood
**R10.** Evaluación: suite pública sintética corrida con dos adapters falsos (baseline y candidate manual; el candidate usa una superficie Optimizable *fixture* en un directorio temporal, nunca el harness real): identidades de run distintas (`identity_hash`), comparación con `config_diff` y veredictos `candidate_better`, `baseline_better`, `equivalent` e `inconclusive` según la evidencia, y `--resume` incompatible rechazado sin tocar el resultado. No se promueve nada.
**R11.** Provider/adapter: conformance local de los 4 providers (contract-tested; smoke real de `detect()` de lo disponible con `HARMESSI_SMOKE_LOCAL=1`), provider faltante/desconocido (exit 1/mensaje claro), observer conformante e inválido (falla el chequeo esperado). Sin llamadas live ni pagas.
**R12.** Portabilidad en Windows: directorios con espacios y Unicode, CRLF/LF, temp dirs, subprocess, Git (repo temporal). Linux/macOS: solo contratos/tests/CI config; **remote CI execution not observed during release**.

## G. Privacidad y límites
**R13.** Barrido de privacidad de archivos cambiados desde `95f3cde` (rutas personales, emails, tokens) y de `result.json` de los dogfood: limpio. Sin telemetría. `git ls-files docs/feedback .harmessi` vacío.
**R14.** Sin cambios a hooks, permisos, roles, settings ni guardrails.

## Criterios de aceptación
- [ ] R1–R3 versión y notas. - [ ] R4 smoke. - [ ] R5–R6 baseline y Doctor. - [ ] R7 regresión. - [ ] R8–R9 install/upgrade. - [ ] R10–R12 dogfood. - [ ] R13–R14 privacidad y límites.
