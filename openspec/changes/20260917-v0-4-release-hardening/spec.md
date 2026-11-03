# Spec — 20260917-v0-4-release-hardening

## Requisitos

### R1 — Versión canónica única
`tools/ds_init/version.py:HARNESS_VERSION = "0.4.0"`. `CITATION.cff:version: 0.4.0`,
`date-released: "2026-09-17"`. Anotaciones históricas ("Bloque N, reliability v0.2.0", "Change N
v0.3") en docstrings NO se tocan — documentan cuándo se introdujo algo, no la versión vigente.

### R2 — README mínimamente actualizado
Sección `### ds_guard` menciona los grupos `science status`, `impact scan` (aclarando que requiere
`tools/dsimpact/`, instalado desde `experiment`), `efficiency report`. Mención breve de que
`validate`/`ALCANCE-RUTA` ahora cubre el diff completo desde `baseline.commit`, no solo el working
tree. Sin reescribir secciones que siguen siendo correctas.

### R3 — Privacidad transversal
Grep exhaustivo sobre el working tree completo (`.py`/`.md`/`.json`/`.cff`) para los patrones ya
usados en cada Change 0-4 (`AGD`, `UNCO`, `Model-churn`, rutas `C:\`/`C:\Users\`, emails personales
fuera de metadata pública legítima, secrets/tokens) — cero resultados nuevos esperados, confirmando
que la limpieza per-change ya fue suficiente; cualquier hallazgo nuevo se corrige antes de cerrar.

### R4 — Regresión completa final, 0 failures no diagnosticados
`tools/tests/`, `tools/harmessi/tests/`, `tools/ds_init/tests/`, `tools/ds_profile/tests/`,
`tools/dsimpact/tests/` — las 5 suites completas, una corrida final después de todos los cambios de
este change (incluida la regeneración de `control.json`, que no debería afectar ningún test dado
que es un archivo de estado de este repo, no de un fixture). El único fallo ya diagnosticado en
sesiones anteriores (`test_este_repo_no_tiene_installation_stage_en_su_control_json`, preexistente,
no relacionado con ningún Change de v0.4 — confirmado por `git diff` vacío sobre
`.ds_init/control.json` en cada Change 0-4) se espera que DESAPAREZCA en este change, porque R7 lo
regenera con `installation_stage` correcto — si sigue fallando después de R7, es una señal real a
investigar, no a ignorar.

### R5 — `harmessi doctor` final, 0 ERROR
Corrido DESPUÉS de R7 (regeneración de `control.json`) — a diferencia de v0.3, donde R5 corría antes
de la regeneración; acá correrlo después es más informativo porque el drift de
HARMESSI-DRIFT/HARMESSI-INSTALLATION-STAGE debería resolverse con el control.json fresco. Cada
WARN/N-A restante se clasifica explícitamente (esperado/deuda conocida/blocker).

### R6 — Smoke E2E de los 4 componentes nuevos de v0.4
Dos scratch installs reales (discovery y experiment, repos git temporales independientes, nunca
mocks):
- **Discovery**: `tools/dsimpact/` NO instalado (stage_minimo experiment); `ds_guard impact scan`
  degrada con exit 3 y mensaje claro (no traceback) — comportamiento ya verificado en Change 1,
  reconfirmado acá con el manifest FINAL de v0.4 completo (no solo dsimpact).
- **Experiment**: `tools/dsimpact/`, `tools/dsguard/scientific_validity.py`, `scope.py`,
  `efficiency.py` todos presentes e importables. Smoke real (no solo `--help`):
  - `ds_guard science status --json` corre sin error sobre un repo sin `scientific-policy.json`
    (todo N/A).
  - `ds_guard impact scan --since HEAD --json` corre sin error (diff vacío, `findings: []`).
  - `ds_guard efficiency report --change-id <id inexistente> --json` da FAIL technical_error
    controlado (sin traceback), confirmando el camino de error también funciona end-to-end.
  - Un change SDD real con un archivo fuera de `rutas_autorizadas` ya commiteado (working tree
    limpio) → `ds_guard validate --change-id <id> --gate cierre` reporta `ALCANCE-RUTA` una sola vez
    (regresión del fix de Change 2, reconfirmada en un scratch install real, no solo en el repo de
    desarrollo).

### R7 — `.ds_init/control.json` regenerado una sola vez, al final
Vía `control.regenerar_control` (mecanismo oficial, sin reimplementar), invocado directamente por el
Lead sobre ESTE repo (no vía `ds_init sync` completo, que además correría `writer.instalar` con
riesgo real de tocar `.claude/settings.json` vía su tratamiento `MERGE` sobre un repo de desarrollo
en uso — `regenerar_control` es la operación mínima y ya documentada como segura: "no reinstala
nada, solo recalcula hashes reales"). Ejecutado DESPUÉS de que R1-R2 ya estén en su versión final
(si se regenerara antes, `archivos[]` quedaría con hashes de una versión intermedia).

## Criterios de aceptación
- [ ] `HARNESS_VERSION`/`CITATION.cff` consistentes en `0.4.0`.
- [ ] README menciona los 4 componentes nuevos.
- [ ] Privacidad: cero hallazgos nuevos.
- [ ] Regresión completa (5 suites): 0 failures sin diagnosticar.
- [ ] `harmessi doctor` final: 0 `[ERROR]`.
- [ ] Scratch installs discovery + experiment: smoke de los 4 componentes pasa.
- [ ] `.ds_init/control.json` regenerado: `harness_version: "0.4.0"`, `archivos[]` incluye
      `scientific_validity.py`/`scope.py`/`efficiency.py`/todo `tools/dsimpact/*` vigente.
- [ ] `verification.md` incluye release notes v0.4.0 + known limitations/deuda v0.5+.
- [ ] `git status`/`git diff --stat` finales limpios de archivos temporales/backup accidentales.

## Cutoff / information boundary
No aplica.

## Baseline (condicional — modeling)
No aplica.
