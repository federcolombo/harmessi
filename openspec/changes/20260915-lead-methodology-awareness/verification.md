# Verificación — 20260915-lead-methodology-awareness

## Evidencia obtenida
Implementación bajo autonomía acotada autorizada por el usuario, en 1 delegación principal de
implementación (documentación + tests, resumida 4 veces por límite de turnos del subagente — no
cuentan como nuevas delegaciones) + 1 delegación de reviewer (resumida 1 vez) + fixes menores
aplicados directamente por el Lead (sin subagente adicional, hallazgos cosméticos bien acotados):

- **`.claude/skills/lead-data-scientist/methodology.md`** (nuevo, + `.tmpl` fuente): 23 secciones
  normativas — jerarquía CRISP-DM/KDD/MLOps/SDD, comportamiento por `project_stage`, `status`
  como puerta de entrada, `project_stage` vs `installation_stage`, reglas de readiness/promotion/
  risk/lifecycle/KDD-canónico/foundations/evidence/SDD/decision-ledger/one-writer/delegación-
  proporcional/bounded-remediation/notebooks/EDA/human-in-the-loop/fail-closed/adopción, workflow
  Inspect→Classify→Plan→Execute→Verify→Close, 15 prohibiciones explícitas del Lead.
- **`SKILL.md`/`kdd.md`/`decision-ledger.md`** (ambas copias cada uno): correcciones puntuales de
  la frase de encuadre obsoleta ("KDD es el lifecycle del proyecto" sin matiz de CRISP-DM
  backbone), pointer a `methodology.md` agregado.
- **`verificador.md`** (ambas copias): entradas nuevas para `lifecycle migrate`, `project
  init/calibrate/set-risk/status/readiness/promote`, `mlops status/record/evidence add`, `status`
  unificado — comandos de Changes 1,3,5,6,8 que antes no estaban documentados en absoluto.
- **`production-readiness.md.tmpl`/`operations.md.tmpl`**: corregido el bug real de sintaxis
  (`ds_guard project promote --target <stage>` → `ds_guard project promote <stage>`, posicional)
  — confirmado que aparecía 2 veces en cada archivo (no 1 como sugería la evidencia inicial),
  ambas corregidas.
- **`tools/ds_init/manifest.py`**: entrada `PLANTILLA` para `methodology.md.tmpl`.
- **`tools/tests/test_skill_methodology.py`** (nuevo, 26 tests): cobertura de contenido/sintaxis/
  sincronización según `spec.md`.

Verificación real ejecutada por el Lead (nunca por el subagente, que no tiene Bash):
- **Sintaxis de CLI real**: `ds_guard project readiness --help` y `ds_guard project promote
  --help` corridos directamente — confirman exactamente lo documentado (`readiness --target
  <stage>`, `promote <stage> --reason` posicional).
- `tools/tests/`: primera corrida 523/523 OK excepto 1 fallo real de FIXTURE (no de contenido):
  `test_cada_par_tmpl_renderizado_es_identico` comparaba `SKILL_lead_data_scientist.md.tmpl`
  (único de los 5 pares que legítimamente usa el placeholder `{{NOMBRE_PROYECTO}}` en su
  frontmatter, preexistente a este change) byte a byte contra la copia local ya renderizada
  (con "harmessi" sustituido) — corregido sustituyendo el placeholder antes de comparar. Segunda
  corrida: 523/523 OK.
- `tools/harmessi/tests/`: 82/82 OK, sin regresión (nada de `doctor.py` tocado).
- `tools/ds_init/tests/`: 112/112 OK, sin regresión.
- `harmessi doctor` sobre este repo, comparado byte a byte con `git stash` antes/después: el
  único diff real es `CORE-WORKING-TREE` (esperado, desarrollo activo sin commit). Los 6
  `HARMESSI-DRIFT` (incluidos `SKILL.md`/`verificador.md`/`decision-ledger.md`, editados en este
  change) ya eran drift preexistente de ESTE MISMO REPO desde antes de esta sesión (self-hosting
  histórico, mismo patrón que `kdd.md`/`ds_guard.py`/`dsguard/kdd.py` ya documentados en changes
  anteriores) — las ediciones de este change profundizan un drift ya contabilizado, sin agregar
  entradas nuevas. **0 ERROR, 0 regresión real.**

**Reviewer (`data-science-reviewer`)**: sin hallazgos bloqueantes ni importantes. Confirmó
exhaustivamente que la sintaxis de CLI documentada coincide con `tools/ds_guard.py` (incluida la
verificación de que las 2 apariciones de `promote` en cada uno de `production-readiness.md.tmpl`/
`operations.md.tmpl` quedaron corregidas, no solo una), que `methodology.md` no reimplementa
ningún criterio determinista, que las prohibiciones no quedan diluidas entre secciones, que los 5
pares `.tmpl`↔renderizado están sincronizados, y que el alcance se respetó (ningún engine/gate/
schema/agente tocado). 2 hallazgos **menores** (cosméticos):
1. `proposal.md`/`spec.md`/`tasks.md` decían "14 prohibiciones" cuando el brief original del
   usuario enumera 15 (la compresión de "no editar `project_stage`/`installation_stage`" en un
   solo ítem redujo el conteo de 15 a 14 durante el borrador de `spec.md`). **Corregido**:
   `methodology.md` (ambas copias) y `test_skill_methodology.py` ahora reflejan las 15
   prohibiciones separadas, exactamente como las enumeró el usuario. Los artefactos SDD ya
   aprobados (`proposal.md`/`spec.md`/`tasks.md`, hash-pinned) NO se editaron retroactivamente
   (preserva la aprobación registrada) — esta nota documenta la diferencia explícitamente, mismo
   criterio ya usado en Changes 6/8 para ajustes menores post-aprobación.
2. Fragmentos de test cortos/genéricos en `PROHIBICIONES_14` (ahora `PROHIBICIONES_15`) — **
   corregido** junto con el punto anterior: cada fragmento ahora es una frase más larga y
   específica, reduciendo el riesgo de falso-positivo futuro.

## Fingerprint de dataset/artefacto (condicional — cambio sensible o reproducibilidad crítica)
No aplica.

## Diferencias contra la spec
Una, menor, documentada arriba: `methodology.md` enumera 15 prohibiciones (no 14 como decían los
artefactos SDD aprobados) — corrige una compresión accidental del propio Lead al redactar
`spec.md`, restaurando fidelidad total al brief original del usuario. No cambia ningún
comportamiento ni agrega contenido nuevo — solo separa un ítem ya presente en dos.

## Limitaciones
`production-readiness.md`/`operations.md` siguen sin copia renderizada local en este repo (ya
documentado desde el cierre de Change 8) — solo sus `.tmpl` fuente quedaron corregidos, correcto
según `design.md` punto 4 (auto-renderizarlos requeriría una operación `ds_init sync` real, fuera
de alcance). El drift preexistente de `SKILL.md`/`verificador.md`/`decision-ledger.md`/`kdd.md`/
`ds_guard.py`/`dsguard/kdd.py` en este repo sigue sin resolverse (no es responsabilidad de este
change corregir drift histórico de auto-hosting, solo no agregar drift nuevo — confirmado que no
se agregó).

## Pendientes derivados
Ninguno bloqueante. Este era el último change del roadmap v0.3 (Changes 0-9), todos cerrados vía
SDD, ninguno commiteado — pendiente de revisión/commit del usuario.

## Resultado final
Todos los requisitos R1-R8 de `spec.md` implementados con evidencia real (más la corrección de
fidelidad de 14→15 prohibiciones, hallazgo menor del reviewer). Reviewer sin hallazgos bloqueantes
ni importantes. Regresión completa limpia (523/523 + 82/82 + 112/112, baseline de doctor
preservado exactamente salvo drift preexistente ya explicado). Change listo para cierre.
