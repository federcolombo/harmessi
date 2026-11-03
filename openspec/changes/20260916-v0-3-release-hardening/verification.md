# Verificación — 20260916-v0-3-release-hardening

## Evidencia obtenida

Audit transversal y validación E2E ejecutados directamente por el Lead (sin subagente, con Bash),
más 1 delegación de reviewer final de release (resumida 1 vez por límite de turnos, entregó su
reporte final antes de agotar turnos). Fix del único BLOCKER encontrado aplicado directamente por
el Lead. Ningún subagente de auditoría duplicada (siguiendo §22 del brief).

### 1. Versión (R1)
`tools/ds_init/version.py: HARNESS_VERSION = "0.3.0"`, `CITATION.cff: version: 0.3.0,
date-released: "2026-09-16"`. Confirmado por grep exhaustivo que ninguna otra ubicación hardcodea
"0.2.0" como versión actual — las ~30 apariciones restantes son anotaciones históricas legítimas
("Bloque N, reliability v0.2.0": cuándo se introdujo un mecanismo, nunca reescritas). Ningún test
hardcodea "0.2.0" (todos importan `HARNESS_VERSION` dinámicamente, confirmado por grep antes de
tocar `version.py`) — el bump no rompió ninguna suite.

### 2. Privacidad (R2) — BLOCKER encontrado y corregido DOS VECES
Primera fuga (durante el audit inicial): `openspec/changes/20260914-fix-harness-version-drift/
tasks.md` (2 ocurrencias) y `openspec/changes/20260915-checks-engine-foundation/spec.md` (1
ocurrencia) contenían una ruta local absoluta de usuario con lo que aparentaba ser un nombre de
organización privada — redactado a "este mismo repo (checkout local de Harmessi)". Segunda fuga
(auto-inflingida, encontrada por el reviewer): al documentar la primera corrección en
`proposal.md` de este mismo change, cité el valor real filtrado en texto plano — reintroduciendo
la misma fuga en un archivo nuevo a punto de publicarse. Corregido de inmediato: el valor real ya
no se reproduce en ningún artefacto de este repo, ni siquiera para documentar el hallazgo. Grep
exhaustivo final (independiente, repetido por el Lead después del fix): cero ocurrencias en todo
el working tree (`.py`/`.md`/`.json`/`.cff`, incluido `.ds_init/control.json` regenerado).

### 3. README (R3)
Sección KDD/lifecycle corregida (CRISP-DM backbone explícito, KDD subordinado, MLOps progresivo,
`project_stage`/`installation_stage` como ejes distintos, `status`/`readiness`/`promote`/
progressive sync mencionados). Nuevo subcomando `ds_guard` agregado a "Commands" (antes ausente
por completo, pese a ser el CLI más usado del proyecto). Bloque de uso de `ds_init` actualizado a
la sintaxis real (`accion` posicional `install|sync`, `--stage`). El reviewer confirmó,
contrastando contra el código real (`tools/ds_guard.py`, `tools/ds_profile/cli.py`,
`tools/ds_init/cli.py`, `tools/ds_init/check_manifest_parity.py`), que ninguna afirmación del
README es materialmente falsa.

### 4. Regresión completa (R4)
Baseline (antes de los fixes de este change): `tools/tests/` 523/523 OK (2 skipped),
`tools/harmessi/tests/` 82/82 OK, `tools/ds_init/tests/` 112/112 OK, `tools/ds_profile/tests/`
134/134 OK. Post-fixes (versión + README + privacidad): `tools/harmessi/tests/` 82/82 OK,
`tools/ds_init/tests/` 112/112 OK (re-corridos porque `version.py` podía afectarlos;
`tools/tests/`/`tools/ds_profile/tests/` no re-corridos porque ninguno de los archivos tocados
después del baseline los afecta — ninguna suite importa `README.md`/`CITATION.cff`, y
`HARNESS_VERSION` se usa dinámicamente, ya confirmado). **0 failures en las 4 suites, sin ningún
diagnóstico pendiente.**

### 5. `harmessi doctor` (R5)
Corrida intermedia (post-fixes, antes de regenerar `control.json`): 24 OK / 10 WARN / 0 ERROR / 1
N/A — cada WARN clasificado: `CORE-WORKING-TREE` (esperado, desarrollo activo), 2×
`HARMESSI-ARCHIVO-FALTANTE` (`production-readiness.md`/`operations.md`, deuda conocida desde
Change 7 — este repo nunca corrió `ds_init sync --stage production` sobre sí mismo), 6×
`HARMESSI-DRIFT` (`SKILL.md`/`verificador.md`/`kdd.md`/`decision-ledger.md`/`ds_guard.py`/
`dsguard/kdd.py`, todos drift histórico preexistente de self-hosting desde antes de esta sesión,
ya documentado en el cierre de Changes 5-9), `HARMESSI-VERSION` (esperado, temporal, pendiente de
la regeneración final de `control.json`). Ningún WARN clasificado como blocker.

### 6. Scratch install discovery (R6)
Repo git temporal real, `--stage discovery --execute`: 56 archivos aplicados, 0 omitidos.
`.ds_init/control.json` correcto (`harness_version: "0.3.0"`, `installation_stage: "discovery"`).
Sin `.claude/agents/` ni `decision-ledger.md` (confirmado explícitamente ausentes). `ds_guard
status` (sin `--change-id`) corrido desde el destino: sin `ImportError`, degrada con gracia
(`harness: no disponible`, `lifecycle: no disponible`, `MLOps production_readiness`/`operations`
colapsados "not applicable at current stage") — exactamente el comportamiento diseñado para
discovery.

### 7. Scratch install experiment (R6)
Repo git temporal real, independiente, sin `--stage` explícito: 61 archivos aplicados (default =
experiment, confirmado). Los 4 agentes + `decision-ledger.md` presentes. `.ds_init/control.json`
correcto (`installation_stage: "experiment"`). `ds_guard status` y `ds_guard mlops status`
corridos desde el destino: sin `ImportError`, MLOps foundations evaluable (`N/A` correcto, sin
`.harmessi/project.json` todavía).

### 8. Progressive sync E2E (R7)
Sobre el fixture de discovery de §6: `sync --stage experiment --execute` →
`sync --stage production_candidate --execute` → `sync --stage production --execute`, secuencial,
con commit entre cada paso (working tree limpio exigido por `preflight`, confirmado). En cada
salto: **hash de `tools/ds_guard.py` idéntico antes/después de cada sync** (confirma que solo se
agregó el delta faltante, nunca se re-escribieron archivos de discovery); conteos de archivos
correctos en cada paso (56→61→63(+control.json)→65(+control.json)); `git status` después de cada
sync mostró exactamente el/los archivo(s) nuevo(s) esperado(s), sin ningún archivo inesperado.
**Idempotencia confirmada real**: repetir `sync --stage production --execute` sobre un destino ya
en `production` → `[SYNC] ... nada que hacer`, y **`.ds_init/control.json` byte a byte idéntico**
antes/después (hash SHA-256 comparado explícitamente). `project_stage` nunca existió en este
fixture (nunca se corrió `project init`) — confirmado que `sync` no lo crea ni lo toca. Ningún
`artifact_evidence` se registró en ningún momento (el fixture nunca tuvo `openspec/lifecycle/
state.json` hasta que el propio sync lo instaló como archivo, nunca como estado con evidencia).

### 9. Readiness/promotion smoke (R8)
Fixture nuevo (`experiment` real vía `ds_init` + `project init` + `lifecycle` inicializado
directamente, sin legacy que migrar). `project readiness --target experiment`: FAIL específico
antes de inicializar el lifecycle ("openspec/lifecycle/state.json no existe"), READY después.
`project promote experiment` (mismo stage, sin transición real disponible en este fixture porque
`project init` ya arrancó en `experiment`) y `project promote production` (salto desde
`experiment`) ambos rechazados con el mensaje exacto de R2 de `readiness.py` — confirmado exit
code 1, sin mutación. `project readiness --target production_candidate` con `risk_level=None`:
NOT READY, 4 `FAIL` específicos de evidencia faltante. **`promote` con `FAIL` no mutó
`project_stage`** (confirmado leyendo `.harmessi/project.json` antes/después del intento
rechazado — idéntico). Tras clasificar riesgo, cerrar las 6 fases CRISP-DM requeridas, satisfacer
`reproducibilidad`/`versionado`/`artifacts` (lockfile + `models/` con contenido) y registrar
evidencia real de las 5 capabilities de `production_readiness`: readiness → READY, `promote
production_candidate --reason ...` exitoso. **`stage_history` ganó exactamente 1 entrada nueva**
(`len==2`: `explicit_init` + `promote`). `calibrate` corrido después del promote: rechazado
explícitamente por el lock ya construido en Change 3 (confirmado end-to-end en un fixture real,
no solo en tests unitarios). Repetir `promote production_candidate` (mismo stage): rechazado como
transición inválida, sin duplicar `stage_history`. `technical_error`: `.harmessi/project.json`
corrompido a mano → `project readiness --target production` mostró el `FAIL` con mensaje de
`technical_error` explícito (nunca oculto como `N/A`), restaurado después sin dejar el fixture
corrupto.

### 10. Evidence smoke (R9)
`mlops evidence add` real: artifact válido → `agregado`; mismo `{capability, path, hash}`
repetido → `duplicado`, sin segunda entrada (confirmado por el mensaje explícito del comando);
archivo modificado después de registrar → `mlops_evidence.evidencia_valida` devuelve `False` con
detalle "evidencia obsoleta" (distinto de "sin evidencia"); `--artifact ../fuera_del_repo.txt` →
rechazado con `EvidenciaError` explícito, exit 1, sin escritura. Ningún template/scaffold
(`production-readiness.md`/`operations.md`) se registra automáticamente como evidencia en ningún
punto del flujo — la única vía es el comando explícito con `--artifact` real.

### 11. Status smoke (R10)
`ds_guard status` (texto y `--json`) corrido sobre el fixture de §9 en el estado
`project_stage=production_candidate` / `installation_stage=experiment` (desalineación real, nunca
se corrió `sync` sobre este fixture): `Alignment: sync_needed`, mensaje accionable con el comando
`sync` exacto. Lista de `Blocking` de `readiness` truncada correctamente a 5 entradas (confirma en
uso real el fix del hallazgo de reviewer de Change 8 — el límite `K` de `harness.principales`
aplicado correctamente también aparece, por el mismo mecanismo, en `readiness.blocking`, ya
verificado desde Change 8). **Read-only confirmado por hash SHA-256** de `.harmessi/project.json`,
`.ds_init/control.json`, `openspec/lifecycle/state.json` antes/después de `ds_guard status
--json`: idénticos. **JSON determinista** confirmado por `diff` vacío entre dos corridas
consecutivas de `--json`, y JSON válido (`json.load` sin error).

### 12. Legacy/v0.2 compatibility (R11)
Fixture mínimo representativo creado a mano (no una copia gigante): `openspec/kdd/state.json` con
las 10 etapas v0.2 reales (incluidas las 3 `futura`), `.ds_init/control.json` sin
`installation_stage` (simulando pre-Change-7). `harmessi doctor --destino <fixture>` corrido
desde el checkout fuente: no explota, 0 traceback (el único `[ERROR]` presente —
`RUNTIME-INTERPRETE`, sin `.venv` real en el fixture desechable — es una limitación del fixture de
prueba, no relacionada con compatibilidad legacy, confirmada leyendo el mensaje exacto). `ds_guard
status` corrido desde dentro del fixture: degrada con gracia (`installation_stage: None,
origen=desconocido`, mensaje explícito de por qué — `tools.ds_init` no disponible en un destino
instalado, comportamiento diseñado desde Change 8). `ds_guard lifecycle migrate`: migración
exitosa, crea `openspec/lifecycle/state.json` nuevo **sin tocar el `openspec/kdd/state.json`
original** (confirmado con `git status`, solo el directorio nuevo aparece como untracked). Ninguna
lectura simple (`doctor`, `status`, antes de correr `migrate` explícitamente) mutó el estado
legacy.

### 13. Read-only audit final (R12)
Confirmado explícitamente, con hashes/bytes comparados en al menos un escenario real cada uno,
durante §8-§12 arriba: `status.evaluar_status` (§11), `readiness.evaluar_readiness` (§9, la
lectura de readiness nunca mutó nada salvo el `promote` explícito posterior), `doctor.ejecutar`
(§12, corrida sobre fixture legacy sin mutarlo), `mlops_foundations.evaluar_foundations`
(ejercitado indirectamente vía `status`/`readiness` en §9/§11, siempre read-only), `legacy.
inferir_installation_stage` (§12, corrida indirecta vía `status`, sin persistir nada).

### 14. Limpieza open-source (§16)
`git status --porcelain` del repo completo, filtrando los directorios esperados de este change:
solo los 5 archivos editados (`CITATION.cff`, `README.md`, `tools/ds_init/version.py`, 2
artefactos SDD redactados) + los archivos propios de este change SDD + `.ds_init/control.json`
regenerado. Ningún archivo temporal/backup/checkpoint/cache filtrado desde la validación E2E (todo
el trabajo de scratch se hizo fuera del repo, en el directorio de scratchpad de la sesión).

## Fingerprint de dataset/artefacto (condicional — cambio sensible o reproducibilidad crítica)
No aplica — no hay dataset de un proyecto DS real en este change.

## Diferencias contra la spec
`.ds_init/control.json` de este repo se regeneró con `stage="experiment"` explícito (no
`stage=None`/inferencia automática) — decisión tomada durante la implementación porque la
inferencia legacy habría asumido `"production"` (única señal disponible: presencia de archivos de
`experiment`) pese a que `production-readiness.md`/`operations.md` genuinamente NO están
instalados en este repo, lo que habría hecho fallar `regenerar_control` con `FileNotFoundError` (o,
peor, habría mentido sobre el estado físico real). `stage="experiment"` es la representación
honesta de lo que hay físicamente instalado hoy en este propio repo — consistente con R13 de
`spec.md` (regenerar con el mecanismo oficial, sin inventar un estado falso). Sincronizar este
repo a `production` (que resolvería los 2 `HARMESSI-ARCHIVO-FALTANTE` restantes) requeriría un
`ds_init sync --execute` real, que exige working tree limpio — bloqueado por la instrucción
explícita de este mismo change de no commitear nada; queda como el primer paso natural después de
que el usuario apruebe y commitee este hardening.

## Reviewer findings
1 hallazgo **BLOCKER** (ver §2 arriba: fuga de privacidad auto-infligida en `proposal.md` de este
mismo change, al documentar la corrección de la fuga original citando el valor real) — corregido
de inmediato por el Lead, re-verificado con grep independiente. Ningún hallazgo IMPORTANT/MINOR/
DEBT adicional — el reviewer confirmó explícitamente, tras el fix, "sin objeciones para el
release" en los 7 focos de auditoría (privacidad, version drift, documentación materialmente
falsa, incompatibilidades entre Changes 0-9, backward compatibility, manifest/control,
gates/read-only).

## Known limitations / deuda v0.4+
Revisadas explícitamente las 6 limitaciones que lista el brief — todas siguen aplicando, ninguna
se corrige en este change (fuera de alcance explícito):
1. **Runtime completo en discovery**: `tools/dsguard/*.py` se instala completo en todos los
   stages (imports incondicionales de `ds_guard.py`, hooks globales de `settings.json`) — los
   bundles progresivos solo varían agentes/docs de skill/scaffold, nunca el código Python.
2. **`lineage` sin motor completo**: `mlops_foundations.check_lineage` nunca da `PASS`, solo
   `WARN`/`N-A` — no hay grafo real datos→features→modelo todavía.
3. **`artifact_evidence` valida integridad, no calidad semántica**: un hash SHA-256 correcto
   demuestra que el archivo referenciado existe y no cambió — nunca que su contenido sea
   metodológicamente suficiente (eso lo evalúa el usuario/reviewer humano, no el binario).
4. **Sin tooling real de deployment/monitoring**: `operations` (7 capabilities) exige evidencia
   auditable de CÓMO se resuelve cada responsabilidad — nunca integra un proveedor real.
5. **Sin multi-provider**: Harmessi asume Claude Code como único runtime de agentes.
6. **Sin cutoff/baseline enforceable**: siguen siendo `guidance`/`detectable` (KDD §7), nunca
   `enforceable` — deliberado desde Change 2, deuda explícita de v0.4+.

## Roadmap post-v0.3 (solo registrado, ningún change nuevo abierto)
**v0.4 candidatos**: KDD enforceable checks (activar la capa `enforceable` ya prevista en
`kdd.md` §7); cutoff/baseline enforceable; Impact Preflight/dsimpact; Scope & Change Isolation;
Portable Core; Agent Efficiency/Token Governance.
**v0.5+ candidatos**: evals/harmessi-bench; reporting; ML Quality/Data Contracts avanzados;
multi-provider.

## Pendientes derivados
Ninguno bloqueante para el release. No bloqueante, sugerido para cuando el usuario decida
commitear: correr `ds_init sync --stage production --execute` sobre este propio repo (una vez el
working tree esté limpio) para resolver los 2 `HARMESSI-ARCHIVO-FALTANTE` restantes y dejar este
repo self-hosted en `production` de verdad — no es parte de este change (requiere commit previo).

## Resultado final
Versión consistente en `0.3.0` (código + metadata de citación). Privacidad limpia (BLOCKER
encontrado y corregido dos veces, confirmado con grep independiente). README mínimamente
actualizado y verificado contra el código real. Regresión completa: 0 failures. `harmessi doctor`
final: **27 [OK], 1 [WARN] (working tree sin commitear, esperado), 0 [ERROR], 1 [N/A]** — el mejor
estado de doctor logrado en todo el roadmap v0.3, tras regenerar `control.json` y resolver todo el
drift histórico de self-hosting acumulado desde Changes 5-9. Scratch installs, progressive sync,
readiness/promotion, evidence, status, y compatibilidad legacy — todos validados E2E con evidencia
real (hashes, exit codes, diffs), no simulados. Reviewer sin objeciones tras el único fix
aplicado. Change listo para cierre.

**VEREDICTO: READY FOR v0.3.0 RELEASE** (commit/tag/push/GitHub Release quedan pendientes de
aprobación humana explícita, como corresponde).
