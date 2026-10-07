# Propuesta — 20261002-exec-approval-registration

> Change CORRECTIVO preexistente (interlude de v0.9-dev). No renumera los Changes 0–5 de v0.9 ni toca el
> roadmap funcional de Cards. `20261002-card-and-evidence-foundation` queda PAUSADO sin tocar.

## Problema
En modo `supervised`, `ds_guard exec script|pytest|notebook` exige una aprobación humana vigente en
`control["aprobaciones"]` (`_resolver_aprobacion_exec`, `tools/ds_guard.py:1798`), pero ningún comando
soportado puede crearla para esas ejecuciones. El único escritor de `aprobaciones` es `cmd_approve`
(`tools/ds_guard.py:376`), que exige que el artefacto sea un archivo dentro de la carpeta del Change
(`:327-329`) y guarda `hash_lf_v1(archivo)`. Pero `exec` busca otra clave y otro hash:
- pytest: artefacto `"pytest:" + "|".join(paths)` (`:2183`), hash `content_sha256(argv)` (`:2181-2185`);
- script: artefacto = ruta repo-relativa del script, hash `hash_lf_v1(script)` (`:2153-2158`);
- notebook: artefacto = ruta repo-relativa del manifest, hash `hash_lf_v1(manifest)` (`:2203-2210`).
Hoy solo los tests construyen esa entrada a mano (`tools/tests/test_ds_guard_exec.py:171`).

Causa raíz: el runtime puede exigir y consumir una aprobación de ejecución, pero no existe interfaz de
usuario soportada para registrarla cuando el artefacto no es un archivo del Change.

## Objetivo
Agregar `ds_guard exec approve <forma>`, que registre la aprobación de exactamente la ejecución que
`ds_guard exec <forma>` construiría, sin que el humano calcule ni suministre hashes.

## Evidencia
Audit read-only del 2026-10-02: `tools/ds_guard.py:313-376` (approve), `:1798-1839`
(`_resolver_aprobacion_exec`), `:1960-2010` (`_ejecutar_exec_comun`), `:2140-2210` (builders pytest/
script/notebook), `tools/nbrunner/manifest.py:173-215` (`validar_aprobacion`),
`tools/dsguard/sdd.py:233` (`_aprobacion_mas_reciente`), `tools/leadrun/allowlist.py:166-221,264-340`,
`.claude/skills/lead-data-scientist/sdd.md:73,111` (dice «aprobación humana» sin indicar cómo registrarla).

## Supuestos descartados
- «`approve --artefacto pytest:…` sirve»: falla por `exists()` y, aunque pasara, hashearía un archivo en
  vez del argv.
- «dependency_install y cli_diagnostic tienen el mismo gap»: no; no usan este mecanismo de aprobación
  (dependency_install usa pre-aprobación M11; cli_diagnostic fue diseñado sin aprobación por corrida).
  Quedan FUERA de alcance.

## Alcance
- Subcomando aditivo `ds_guard exec approve {pytest,script,notebook}`.
- Extracción de builders puros compartidos entre `exec` y `exec approve`.
- Tests nuevos (archivo nuevo), documentación de la vía de aprobación en `sdd.md` y su template, y la
  deuda v0.10 (ya registrada en `docs/roadmap/v0.10.md`).

## Fuera de alcance
- Primitive de autenticación/origen humano de las aprobaciones (deuda v0.10, no se diseña ahora).
- Cambiar la semántica de hash de pytest/notebook ni migrar aprobaciones legacy de script (M1: script
  gana una semántica v2 solo para aprobaciones NUEVAS).
- `dependency_install`, `cli_diagnostic`, autonomous, checkpoints, `STOP_CATALOG`, `ExecutionRecord`,
  runtime de Change 2, `ds_guard approve` existente.
- Segundo store/sidecar/ledger de aprobaciones; migración de aprobaciones existentes.
- Lo ya escrito de Cards (no se toca ni se ejecuta).

## Modelo de confianza (congelado)
Las aprobaciones de Harmessi son *recorded human declarations under the harness trust model*: no son
firma criptográfica, prueba de identidad, prueba de que una persona tipeó el comando ni
non-repudiation. `--usuario` conserva su semántica actual. `exec approve` mantiene PARIDAD con
`approve`: no distingue técnicamente humano vs. agente. Un `ApprovalRef` es una referencia verificable a
una aprobación registrada por Harmessi, no prueba criptográfica de autoría (relevante para
`HumanAttestation(anchored)` de v0.9; sin afirmar autenticidad criptográfica).

## Hallazgos adicionales (no corregidos aquí)
- **F1 — script: argumentos no ligados (RESUELTO por M1 en este Change: semántica v2 versionada +
  legacy reconocida; ver spec R9/R9b).** La aprobación de `script` liga solo el
  contenido del script. `argv[2:]` (argumentos del script) no entra al hash ni es validado por la
  allowlist (`_evaluar_forma_script` solo mira `argv[1]`, `allowlist.py:166-178`). Un script aprobado puede
  ejecutarse luego con otros argumentos sin invalidar la aprobación. Es una parte material de la
  ejecución. Este Change NO lo corrige; preserva la semántica y exige decisión (ver design).
- **F2 — `algoritmo` de la entrada.** `approve` rotula `sha256/lf/v1`; para pytest el hash es de argv
  (JSON canónico), por lo que la entrada nueva se rotula con un algoritmo distinto y honesto.
- **F3 — «la última gana».** `_aprobacion_mas_reciente` filtra por `artefacto`; dos variantes de flags
  de pytest sobre las mismas rutas comparten artefacto y solo la última aprobada es vigente. Se
  documenta; no se cambia.
- **F4 — documentación gestionada.** Editar `sdd.md.tmpl` y su copia instalada cambia hashes de archivos
  gestionados (`.ds_init/control.json`); requiere regeneración por la vía soportada (precedente: commit
  `8a8d6ec`).

## Criterios de cierre
Ver spec.md. En particular: flujo E2E `exec approve pytest` → `exec pytest` con ejecución gobernada real,
suites preexistentes de exec sin editar y en verde.

## Impacto en production-readiness (opcional)
Aditivo; sin cambio de comportamiento para quien no use el subcomando nuevo.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Motivo de rechazo

## Desacuerdo registrado
