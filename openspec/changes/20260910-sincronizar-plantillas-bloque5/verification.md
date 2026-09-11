# Verificación — 20260910-sincronizar-plantillas-bloque5

## Evidencia obtenida
- `diff` confirmado por el Lead: `sdd.md.tmpl`/`verificador.md.tmpl`/`decision-ledger.md.tmpl`
  byte-idénticos a sus archivos vivos correspondientes; `SKILL_lead_data_scientist.md.tmpl`
  difiere de `SKILL.md` únicamente en `{{NOMBRE_PROYECTO}}` vs `harmessi` (única ocurrencia,
  línea de frontmatter).
- `git status --short -- tools/ds_init/` confirmado por el Lead: solo 5 archivos tocados
  (`manifest.py`, los 3 `.tmpl` sincronizados, el `.tmpl` nuevo) — ningún otro archivo de
  `tools/ds_init/` (agentes, `kdd.md.tmpl`, `nbrunner_manifest.py.tmpl`, `CLAUDE.md.tmpl`,
  `profile.json`) fue tocado.
- `tools/ds_init/tests`: 53 passed — sin regresión.
- `tools/tests`: 191 passed, 2 skipped (skips preexistentes, no relacionados) — sin regresión.
- `tools/harmessi/tests`: 56 passed — sin regresión.
- `check_manifest_parity`: `[OK]` en rutas VERBATIM; ahora lista 10 entradas `PLANTILLA` (las 9
  anteriores + `decision-ledger.md.tmpl` nueva) — ese listado es informativo e incondicional por
  diseño (no compara contenido/hash), así que seguir apareciendo ahí no es un fallo; lo que se
  verificó fue la fidelidad de contenido de cada `.tmpl` (ver primer punto).
- `harmessi doctor`: 26 [OK], 9 [WARN], 0 [ERROR]. Los WARN son working tree sucio (esperado) y
  drift de archivos administrados por el harness ya modificados en este bloque y en Bloque 5.
- Reviewer (`data-science-reviewer`): sin hallazgos bloqueantes ni de severidad media; confirmó
  byte a byte las cuatro plantillas y la entrada nueva del manifiesto.
- Revisión de `openspec/`: ningún archivo temporal, de staging o de sesión bajo `openspec/` —
  solo artefactos SDD legítimos (`proposal.md`/`spec.md`/`design.md`/`tasks.md`/`control.json`, y
  `verification.md` en el cambio ya cerrado de Bloque 5). `.gitignore` no excluye `openspec/`.

## Resultado final
Las plantillas instalables de `ds_init` quedaron sincronizadas con el contenido de Bloque 5: un
proyecto nuevo instalado hoy con `ds_init --perfil python-jupyter-data` recibe correctamente la
documentación de decision ledger y bounded remediation (comandos `decision *`/
`remediation {resolve,extend}`, reglas de reintentos/ventanas, y la regla explícita de que un
cambio de enfoque metodológico no es una remediación). Sin regresión en ninguna suite de tests.

## Limitaciones
- El listado `[INFO]` de `check_manifest_parity` seguirá mostrando siempre las 10 entradas
  `PLANTILLA` (incluidas las 4 tocadas en este cambio) en cualquier corrida futura, por diseño de
  `listar_plantillas()` (no hay comparación de contenido/hash automática) — no hay forma de que
  ese conteo "baje" sin cambiar el comportamiento de esa función, cosa que este cambio no incluyó
  (fuera de alcance, no fue pedido).
- Deuda explícita ya documentada en Bloque 5 (`design.md` de
  `20260910-decision-ledger-bounded-remediation`) sigue sin tocar, tal como se pidió: gap de
  `ds_guard scope add`, findings persistentes, enforcement por finding en el hook,
  integridad/hash del ledger, doble supersede/revoke, comportamiento de `retry_tecnico` sin
  `finding-id`.
