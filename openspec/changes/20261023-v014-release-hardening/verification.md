# Verificación — 20261023-v014-release-hardening

## Resumen
Cierre de release de Harmessi v0.14.0 «Evidence-Driven Harness Improvement»: marcadores de versión, notas, inventario de contratos, smoke de release, dogfood A–I, baseline managed (una sola regeneración), regresión completa serial, instalación limpia y upgrade desde `v0.13.0`, Doctor y barrido de privacidad. v0.14 permite proponer, probar, comparar y producir propuestas de promoción gobernadas; **no** se auto-modifica ni promueve nada.

## Evidencia obtenida
- **Regresión completa (T3), serial P=1, 256 módulos con ledger, reanudada dos veces sin reiniciar desde cero (una por vencimiento de sesión/fixes del reviewer y otra por reinicio de la máquina):** 256/256 módulos OK, 0 fallos. unittest: 227 módulos, 6333 tests intentados, 69 skipped; pytest: 29 módulos, 639 tests intentados, 0 skipped. Total: 6972 intentados, 6903 pasados, 69 skipped, 0 fallados.

| batch | modules | attempted | passed | skipped | failed |
|---|---|---|---|---|---|
| autonomy | 3 | 153 | 153 | 0 | 0 |
| cards | 21 | 1279 | 1245 | 34 | 0 |
| datacontracts | 8 | 185 | 185 | 0 | 0 |
| datasources | 7 | 164 | 164 | 0 | 0 |
| ds_init | 25 | 331 | 331 | 0 | 0 |
| ds_profile | 9 | 169 | 159 | 10 | 0 |
| dsimpact | 7 | 85 | 85 | 0 | 0 |
| fallback | 3 | 26 | 26 | 0 | 0 |
| harmessi | 11 | 261 | 261 | 0 | 0 |
| harmessi_bench | 12 | 286 | 286 | 0 | 0 |
| harmessi_improve | 10 | 268 | 263 | 5 | 0 |
| leadrun | 8 | 107 | 107 | 0 | 0 |
| modelquality | 3 | 108 | 108 | 0 | 0 |
| providers | 4 | 67 | 66 | 1 | 0 |
| qualityevidence | 3 | 85 | 85 | 0 | 0 |
| reporting | 16 | 856 | 853 | 3 | 0 |
| routing | 3 | 21 | 21 | 0 | 0 |
| tools/tests | 103 | 2521 | 2505 | 16 | 0 |
| **total** | 256 | 6972 | 6903 | 69 | 0 |

  Los módulos tocados después de su primera pasada (CLI de `harmessi_improve`, inventario de contratos, workflow de CI, smokes v0.13/v0.14 y dogfood) se invalidaron en el ledger y se repitieron; el resto no se repitió. Skips por causa: symlinks no disponibles sin privilegios en Windows (5 en `harmessi_improve`), opt-in/entorno en `cards` (resolvers, discovery), `ds_profile` (pandas ausente), `human_presence`, `pathguard`, smokes locales `test_v013_*` y `leadrun`; la causa individual no se desglosó una a una.
- **Dogfood A–I (T2):** `tools/tests/test_v014_dogfood.py`, 25 tests OK. A evidencia baseline vs candidate en disco sin tocar la skill; B `candidate_better`; C `baseline_better`; D `equivalent`; E `inconclusive` (nunca `baseline_better` por entorno); F Protected rechazado antes del probe sin consumir `probe_cycles`; G `promotion proposal ready` con gate bloqueado sin T1 y desbloqueado solo con un Change fixture falso (valida el gate, no es aprobación real); H lesson evidence-backed con rechazos de ruta/email/glosario; I agotamiento determinista de `max_candidates`/`max_probe_cycles`, techo duro y ciclo anidado. Más: ninguna candidate queda `promotable` por metadata o por texto «better». El adapter es scripteado y determinista: valida la cañería de evidencia/decisión/gobierno, no mide la calidad real de la skill.
- **Baseline managed (T2):** `.ds_init/control.json` regenerado UNA vez (`harness_version` 0.14.0, 131 entradas); único cambio del archivo: la versión. `migrate-hashes` dry-run: Migrables 0, Ya actuales 131, No verificables 0, Desconocidas 0. Sin adoptar drift.
- **Instalación limpia (T4):** 131 archivos, versión 0.14.0; sin `tools/harmessi_improve`, `.harmessi/` ni candidates/lessons; imports con `python -I` OK; Doctor del destino: 30 OK, 1 WARN (árbol sin commitear), 0 ERROR (con venv real vacío).
- **Upgrade desde el tag `v0.13.0` (T4):** instalado con su propio `ds_init`; contenido de proyecto agregado (CLAUDE.md editado, GLOSSARY.md, notebook, datos en `data/interim`, skill local); upgrade `0.13.0 → 0.14.0`: 0 actualizados, 0 creados, 0 con drift (en v0.14 no cambió ningún archivo managed); los 5 archivos de proyecto con el mismo sha256 antes/después; segunda corrida: «Nada que hacer»; `harmessi_improve` no instalado.
- **Doctor del repo:** 30 OK, 0 ERROR (único WARN: árbol con cambios sin confirmar durante el cierre).
- **Reviewer (T6), 1 ciclo:** 0 BLOCKER, 0 HIGH, 5 MED, 6 LOW; corregidos: «publicada» prematura en el roadmap, promesa «nothing is sent anywhere» (ahora: sin telemetría; un provider real recibe prompts), `EXIT_*` como fuente única en la CLI, precisión de rutas absolutas en `docs/portability.md`, tautología del dogfood G, dogfood en el workflow de CI, aclaración del alcance del adapter scripteado, filas de la tabla de auditoría, smoke más estricto. Revisión parcial por límite de turnos: quedaron sin releer el diff de README/CITATION/`docs/contracts/README.md` (verificados por los tests del smoke y del inventario) y la CI remota.
- **Privacidad:** barrido del diff contra `v0.13.0` (sin `openspec/`): solo fixtures sintéticos de tests de rechazo y el propio test de barrido; `git ls-files docs/feedback .harmessi` vacío; sin telemetría ni red en `tools/harmessi_improve` (test AST).
- **Sin cambios de hooks/permisos/roles/settings/guardrails (R11):** cubierto por el smoke contra el tag `v0.13.0`.

## Wording obligatorio
- Remote portability CI pending observation: workflow actualizado (checkout v5, setup-python v6, inferidas compatibles, no observadas); remote CI execution not observed during release.
- Linux/macOS no validados por ejecución en este release (evidencia remota previa de v0.13: Windows, Ubuntu y macOS en verde).
- Providers: máximo `contract-tested`; ningún probe corrió contra un provider real.
- H1 (payload del hook) sigue UNCONFIRMED.
- GitHub Release UI pending (sin `gh`).
- v0.14 habilita mejora gobernada con evidencia; no mejora ni promueve el harness por sí mismo.

## Limitaciones
Evals = proxies deterministas de texto; `duration_s`, tokens, retries y STOP no se usan para decidir; escaneo de privacidad heurístico; procedencia de la evidencia no criptográfica; `harmessi_improve` es solo-checkout (no se instala); sin ventana de compatibilidad para los contratos nuevos; resume de dos procesos simultáneos sobre un mismo probe no se bloquea durante la ejecución. Ver `docs/roadmap/v0.14.md` (deudas y contratos pendientes antes de v1.0).

## Divergencias respecto del SDD
Ninguna material. `docs/contracts/inventory.json` suma `BUDGET_VERSION` y `POLICY_VERSION` (no exigidos por el test). Se editó `tools/tests/test_v013_contract_inventory.py` (extractor de la nueva CLI) y la CLI de `harmessi_improve` (alias `EXIT_*`).

## Resultado final
Change 6 verificado: regresión 256/256, instalación limpia y upgrade correctos, Doctor 0 ERROR, baseline coherente, dogfood A–I verde, privacidad limpia. Listo para integración, tag y push.
