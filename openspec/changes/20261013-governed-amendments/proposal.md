# Propuesta — 20261013-governed-amendments

> Change 3 de v0.10 («Integration & Stabilization + Composable Data Science Skills»), roadmap en `docs/roadmap/v0.10.md`. Cubre
> «Governed Amendments»: (A) enmienda de scope autorizado a mitad de un Change y (B) re-adopción de guardrails sobre closed list. Es
> audit + SDD únicamente: NO implementa nada. Es el PRIMER consumidor obligatorio de T1 `console_confirmed` (Change 2).

## Problema
Dos modificaciones sensibles de governance hoy no tienen camino explícito, auditable ni atado a hash:

1. **Scope.** Ampliar o reducir el scope autorizado de un Change ya aprobado obliga a re-aprobar toda la propuesta (lo que reemplaza la
   lista completa) o a editar `control.json` a mano, y nadie autentica `control.json`: una edición manual de `rutas_autorizadas` no se
   detecta.
2. **Guardrails.** Un proyecto que declara legítimamente claves propias en `.claude/guardrails.json` (holdouts, data_raw, secretos,
   fuentes selladas) queda con un WARN `HARMESSI-DRIFT` permanente en Doctor, porque no existe forma de aceptar esa configuración como
   nuevo baseline sin tocar la plantilla. El archivo está protegido contra agentes y solo lo edita el humano a mano; falta el paso
   «aceptar lo ya editado» con registro.

Además, pathguard protege hoy solo `guardrails.json`: cualquier registro nuevo de enmiendas o adopciones sería escribible por un agente
con Write/Edit, y entonces falsificable (T1 sería un mero registro).

## Objetivo
Que toda modificación sensible de governance (enmienda de scope, re-adopción de guardrails) sea explícita, auditable, atada a hash y
acompañada de una confirmación T1 `console_confirmed`, sin que un agente pueda auto-ampliarse el scope ni auto-readoptarse.

## Evidencia
Audit del código de `v0.10-dev` (2026-10-13), referencias archivo:línea aproximadas.

### Scope
- Fuente de verdad: `control["alcance"]["rutas_autorizadas"]` (lista de rutas o `dir/**`), materializada en `tools/ds_guard.py::cmd_approve`
  (~l.415-435) a partir de los artefactos por defecto del Change (`_rutas_por_defecto_change`: `.md` del Change, `control.json`,
  `verification.md`) unidos a `## Alcance autorizado` de `proposal.md`. El parser es `sdd.parsear_alcance_autorizado` /
  `_normalizar_entrada_alcance`: rechaza rutas protegidas, `data/raw`, repo-wide y traversal. Re-aprobar `proposal.md` REEMPLAZA la lista
  (imprime +/-).
- Consumidores de la lista: `tools/dsguard/scope.py::evaluar_alcance` (~l.73, `path_matches_any`); status/validate de `ds_guard.py`
  (~l.225, `repo.files_out_of_scope`); runtime de `exec` (`ds_guard.py` ~l.2290, `scope=tuple(...)` hacia la allowlist de `leadrun`,
  `_coincide_alcance`).
- Outputs intrínsecos del harness (`.harmessi/executions/**`, `openspec/decisions/ledger.jsonl`) se excluyen por
  `scope.es_output_intrinseco` (lista cerrada; este Change NO la amplía).
- Nadie autentica `control.json`: la edición manual de `rutas_autorizadas` no se detecta hoy.

### Guardrails
- `.claude/guardrails.json` está protegido por `pathguard` contra Write/Edit/NotebookEdit y (best-effort) Bash/PowerShell
  (`RUTA_GUARDRAILS_PROTEGIDA`). La única edición es manual del humano fuera de Claude Code.
- Doctor compara el archivo contra la PLANTILLA del repo origen (`raiz_repo_origen()/.claude/guardrails.json`) con drift semántico:
  `guardrails_drift.RUTAS_MUTABLES` (`version`, `autonomy.mode|version|budgets|limits`) se ignoran (validadas aparte); cualquier otra
  diferencia es WARN `HARMESSI-DRIFT` permanente (`doctor._drift_guardrails_json`).
- Hallazgo clave: las keys MUTABLES ya no producen drift, así que NO necesitan re-adopción. El problema real son las keys declaradas por
  el proyecto: `holdouts`, `data_raw`, `secretos_extra`, `write_scopes`, `excepciones`, `autonomy.sealed_sources`,
  `autonomy.source_access`.
- El baseline gestionado de `control.json` (hash por archivo, Change 1) NO es el mecanismo relevante: el archivo difiere de la plantilla
  por hash y cae en la comparación semántica.

### Pathguard
- Solo `guardrails.json` está protegido. `control.json` y cualquier registro nuevo serían escribibles por un agente con Write/Edit.

## Supuestos descartados
1. Que las keys mutables de guardrails necesiten re-adopción: ya no generan drift.
2. Que el baseline gestionado de `control.json` (Change 1) sirva para guardrails: el archivo cae en la comparación semántica.
3. Que `regenerar_control` o `sync` sirvan como re-adopción: aceptarían estado sin decisión humana; `sync` nunca re-adopta.
4. Que guardar enmiendas en `control.json` sea auditable: un único archivo mutable, no append-only, no autenticado.
5. Que el decision ledger sirva de almacén: no tiene amend/correct (deuda aparte) y mezcla semánticas.
6. Que un registro sea suficiente sin pathguard: sin protección de escritura, T1 sería solo un registro falsificable.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica: cambio de infraestructura/governance, no prueba una hipótesis sobre datos.

## Alcance

### Principio
Una modificación sensible de governance debe ser explícita, auditable, atada a hash y acompañada de T1 `console_confirmed`. T0
(`declared`) nunca alcanza. Sin consola de control soportada, la operación falla cerrada; no se degrada.

### Separación de conceptos
- **Hash migration**: mismo contenido, algoritmo nuevo (Change 1).
- **Managed upgrade**: archivo pristine + asset nuevo de la plantilla.
- **Re-adoption**: configuración legítimamente modificada, aceptada como nuevo baseline por un humano. Es lo que define este Change.
- `regenerar_control` NO se reutiliza. `sync` nunca re-adopta.

### (A) Enmienda de scope autorizado
- Comandos: `ds_guard scope amend --change-id X [--add P]... [--remove P]... --motivo "..." --usuario U [--fecha F] [--dry-run]
  [--expected-scope-hash H]` y `ds_guard scope show`.
- Operaciones ADD/REMOVE (sin replace total). Reutiliza `_normalizar_entrada_alcance` (mismas protecciones: rutas protegidas,
  `data/raw`, repo-wide y traversal rechazados).
- No se pueden quitar las rutas por defecto del propio Change.
- Add de lo ya presente o remove de lo ausente = no-op determinista, reportado; si todo es no-op no hay mutación ni T1.
- Solo Changes aprobados y no cerrados ni descartados.
- Historial append-only con cadena de hashes en `openspec/changes/<id>/amendments.jsonl`. Cada línea: `seq`, `utc`, operación,
  add/remove, `rutas_despues` completas, `scope_hash_before/after`, `prev_hash`, motivo, usuario y fecha declarados,
  `approval_channel`/`confirmed_at`/`channel_version` de T1, `entry_hash`.
- El scope efectivo es la última línea validada de la cadena; `control["alcance"]["rutas_autorizadas"]` pasa a ser caché.
- Los tres consumidores (`evaluar_alcance`, status/validate, runtime de `exec`) leen vía una función única
  `scope.alcance_efectivo(change_dir, control)`, que valida la cadena y falla cerrado ante cadena rota o T1 ausente. `validate` informa
  `ALCANCE-ENMIENDA-INVALIDA`.
- Re-aprobar `proposal.md` con enmiendas existentes se RECHAZA (exit 2): el scope pasa a estar gobernado por enmiendas.
- Una reducción afecta trabajo futuro; no borra artifacts ni historia.
- Enmienda de scope ≠ ownership de writer (Change 4).

### (B) Re-adopción de guardrails sobre closed list
- Comando: `ds_guard guardrails readopt --motivo "..." --usuario U [--dry-run] [--expected-guardrails-hash H]`.
- Calcula el diff semántico del archivo actual contra la plantilla más las adopciones previas. TODO el diff debe estar en la closed list
  y ser aditivo.
- Closed list aprobada (M2): `holdouts`, `data_raw`, `secretos_extra`, `autonomy.sealed_sources`; solo ADICIONES a listas de
  deny (superconjunto del baseline; elementos válidos: strings no vacíos, sin traversal ni absolutos).
- NO elegibles: `excepciones`, `write_scopes`, `autonomy.source_access`, remociones de cualquier elemento del baseline, claves
  desconocidas, security ceilings, hooks, permisos de tools, mutables (innecesario).
- Diff mixto o inelegible: rechazo total. No-op: sin mutación.
- Registro append-only con cadena en `openspec/decisions/guardrails-adoptions.jsonl`: `seq`, `utc`, claves y elementos añadidos, hash de
  guardrails normalizado antes/después, `prev_hash`, motivo, usuario y fecha, campos T1, `entry_hash`.
- NO modifica `guardrails.json` ni `control.json`.
- Doctor excluye del drift las claves cuya diferencia esté exactamente cubierta por adopciones válidas (igualdad de conjuntos con
  plantilla ∪ adiciones adoptadas), emite un PASS informativo con las adopciones y trata una cadena inválida como fallo cerrado (la
  diferencia sigue siendo drift y se emite un hallazgo).
- Nada de `accept-current-state` ni `adopt-all`.
- Nota: Change 0 pidió no re-adoptar «source sealing» salvo contrato explícito; este Change define ese contrato (solo adiciones).

### T1 (sin primitive nueva)
- Ambas operaciones usan `human_presence.solicitar_confirmacion` de Change 2 con contexto `{change_id (o "proyecto"), artefacto:
  "scope-amendment"|"guardrails-readopt", hash: hash del diff canónico {operación, estado antes, cambio exacto, estado después}, accion}`.
  Single-use; no reutilizable para otra mutación. Se persisten los campos de `campos_registro`.
- No existe flag de canal: T1 es obligatorio (sin `declared`).
- `--dry-run` no pide T1 ni muta.
- Execute recalcula desde cero, pide T1, re-verifica por optimistic concurrency (`expected_*_hash` y relectura) y aplica de forma
  atómica (archivo temporal + `os.replace`). Si falla la escritura no queda aprobación a medias.

### Pathguard
- Se protegen (M1) `openspec/changes/*/amendments.jsonl` y `openspec/decisions/guardrails-adoptions.jsonl` contra
  Write/Edit/NotebookEdit y escrituras best-effort por shell (mismo patrón que `guardrails.json`).
- `control.json` no se protege: tras la primera enmienda ya no es fuente de verdad del scope.

### Alternativas descartadas
Guardar enmiendas en `control.json` (un solo archivo mutable, no append-only, difícil de auditar); en el decision ledger (sin
amend/correct, mezcla semánticas); reutilizar `regenerar_control`.

### Limitaciones (honestas)
- Sin criptografía. Un agente que pueda editar archivos fuera de pathguard o sintetizar input de consola puede falsificar.
- La detección de edición manual es por cadena de hashes y git history, no por autoría.
- T1 es señal de presencia, no identidad (ver Change 2).

### Decisiones aprobadas (2026-10-13)
- **M1 — Pathguard sobre los registros: SÍ.** Se extiende pathguard para proteger `openspec/changes/<change-id>/amendments.jsonl` y
  `openspec/decisions/guardrails-adoptions.jsonl` contra Write/Edit/NotebookEdit y escrituras detectables por shell (redirecciones y
  comandos de escritura). NO se bloquea lectura, `validate`, `--dry-run` ni la escritura interna legítima de `ds_guard scope amend` /
  `guardrails readopt` (proceso Python). No hay ruta alternativa de «editar y reparar»: un registro alterado manualmente es inválido y
  falla cerrado. Pathguard NO vuelve auténtico criptográficamente el registro; la seguridad es la combinación de T1 `console_confirmed`
  + binding exacto de operación + cadena/hash + validación fail-closed + Git como evidencia externa.
- **M2 — Closed list EXACTA de cuatro campos: SÍ.** `holdouts`, `data_raw`, `secretos_extra`, `autonomy.sealed_sources`, SOLO con
  semántica monotónica de endurecimiento: únicamente ADICIONES (`effective_new = effective_previous + elementos nuevos válidos`); nunca
  remover, reemplazar, modificar un elemento, relajar ni aceptar listas arbitrarias. Duplicado = no-op. Estructura no list-like =
  fail-closed, sin coerciones. Diff mixto (una adición permitida más cualquier remoción, modificación o key prohibida) = rechazo TOTAL,
  sin aplicar parcialmente. EXCLUIDOS: `excepciones`, `write_scopes`, `autonomy.source_access`, hooks, permisos de tools, security
  ceilings, protected paths, cualquier clave desconocida y las cuatro mutables de Corrective B (`autonomy.mode|version|budgets|limits`,
  que no necesitan re-adopción). La closed list no se amplía en implementación sin decisión material. `sealed_sources` se aprueba porque
  existe contrato explícito SOLO ADD (desellar no es re-adoptable), lo que satisface el boundary de Change 0.
- **M3 — Almacenamiento propio append-only: SÍ.** Enmiendas en `openspec/changes/<id>/amendments.jsonl`; adopciones en
  `openspec/decisions/guardrails-adoptions.jsonl`, artifact separado: NO es `ledger.jsonl`, NO usa acciones ni semántica del decision
  ledger, NO depende de `decision amend`, con schema y validator propios. Si en implementación hay una ubicación project-level más
  coherente puede usarse siempre que sea separada y versionable. Sin event sourcing genérico. Cadena simple: schema/version,
  `prev_hash`, `entry_hash`, state hash before/after, operación/diff canónico, motivo, usuario declarado, timestamp y metadata de
  `console_confirmed`. Sin blockchain ni firmas: prueba consistencia y tamper evidence básico, no autoría.
  - Fuente de verdad del scope: tras la primera enmienda válida, scope efectivo = scope inicial aprobado + secuencia válida de
    enmiendas. `control.json["alcance"]["rutas_autorizadas"]` es caché/materialización de compatibilidad y NUNCA supera al historial.
    Si caché e historial divergen no se acepta la caché en silencio: el scope efectivo se reconstruye determinísticamente desde la
    cadena y se emite el hallazgo `ALCANCE-CACHE-DIVERGENTE`; una edición manual del control NO se convierte en enmienda. Cadena
    inválida = fail-closed (`exec` rechaza, `validate` da error).
- **M4 — Rechazar re-aprobar `proposal.md` con enmiendas: SÍ.** Con una o más enmiendas efectivas, re-aprobar `proposal.md` termina
  en exit 2 / fail-closed: la proposal define el scope BASE; sin rebase ni replay automáticos. Cambiar materialmente la proposal
  requiere un flujo futuro explícito o un nuevo Change; no se implementa ahora.

### Contrato aprobado de `scope amend`
- ADD y REMOVE, sin replace. ADD autoriza trabajo futuro; REMOVE revoca autorización futura sin borrar artifacts, evidence, historia ni
  commits. Las rutas estructurales por defecto del Change no pueden eliminarse.
- No-op (add existente / remove ausente): determinista, sin mutación y sin T1.
- T1 `console_confirmed` obligatorio para operaciones efectivas: T0 insuficiente, no existe `--channel declared`, sin consola de
  control = fail-closed. `--dry-run` no requiere T1.
- Operation binding: la confirmación queda ligada exactamente a tipo de operación, target, hash del estado actual, diff exacto, hash
  del estado resultante y Change/proyecto; no es reutilizable para otra operación; sin token persistente.
- Atomicidad, orden exacto: recalcular inmediatamente antes de ejecutar; optimistic concurrency; T1; releer y verificar que el estado no
  cambió (si cambió, abortar); construir el contenido completo nuevo del registro (anterior + línea nueva) en archivo temporal y validar
  la cadena del temporal; `os.replace`; refrescar la caché de control (best-effort, solo scope; si falla el estado sigue consistente
  porque la cadena es la fuente de verdad); validación posterior. Nunca es válido el estado «aprobación registrada + mutación incompleta».
- Dry-run (en ambas operaciones): calcula, valida, muestra diff y hashes, no pide T1 y no muta. Execute recalcula todo y no confía en
  datos del dry-run.

### Contrato aprobado de Doctor y `sync`
- Doctor: una diferencia únicamente sobre adiciones previamente re-adoptadas con cadena válida no es drift. Elemento adicional no
  adoptado, elemento adoptado eliminado, key prohibida cambiada, cadena rota o `guardrails.json` malformado = hallazgo/drift según la
  severidad existente. No se actualiza el managed hash de Change 1 para simular aceptación.
- `sync` nunca hace re-adopción, ni scope amendment, ni T1 automática.

### Archivos previstos
| Archivo | Cambio |
|---|---|
| `tools/dsguard/scope_amendments.py` (nuevo) | cadena de enmiendas, diff canónico, aplicación atómica |
| `tools/dsguard/guardrails_adoption.py` (nuevo) | diff semántico, closed list, cadena de adopciones |
| `tools/dsguard/scope.py` | `alcance_efectivo`, hallazgo `ALCANCE-ENMIENDA-INVALIDA` |
| `tools/dsguard/pathguard.py` | rutas protegidas nuevas |
| `tools/ds_guard.py` | subcomandos `scope amend\|show`, `guardrails readopt`; rechazo de re-aprobar proposal con enmiendas; consumidores vía `alcance_efectivo` |
| `tools/harmessi/doctor.py` | `_drift_guardrails_json` con adopciones |
| `tools/tests/test_scope_amendments.py`, `tools/tests/test_guardrails_readopt.py` (nuevos) | tests de las dos operaciones |
| `tools/tests/test_pathguard.py`, `tools/tests/test_scope.py`, `tools/harmessi/tests/test_doctor_guardrails.py` | ajustes |
| `tools/tests/test_architecture_boundaries.py`, `ARCHITECTURE.md`, `docs/roadmap/v0.10.md` | boundaries y docs |
| `.claude/skills/lead-data-scientist/sdd.md` | guía del Lead |

## Fuera de alcance
Writer ownership y concurrencia (Change 4), writer lifecycle, domain modeling, ledger amend/correct, enum de tipos de decisión, default
de sesión de 90 min, scratchpad, turn limits/reanudaciones, validación T1 real en host POSIX, non-ASCII paths (ya corregido), T2,
`decision`/`remediation` a T1, managed hashing, `ds_profile`. Se preservan como deuda aparte; este Change no las resuelve.

## Holdout policy (condicional — solo cambios "sensible")
No aplica: no se toca ningún holdout ni dataset sellado. La re-adopción solo registra ADICIONES a listas de deny ya declaradas por el
humano; no lee ni accede a datos sellados.

## Impacto en production-readiness (opcional)
Ninguno directo.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md` (SDD completo).

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md` (SDD completo).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-10-13
- Alcance aprobado: Implementación y validación de Change 3 Governed Amendments
- Versión de artefactos referenciada: proposal.md/spec.md/design.md vigentes al momento del hash
- Cita o descripción fiel de qué se aprobó: «Aprobación humana explícita del SDD de Change 3 y decisiones M1-M4»

## Alcance autorizado

- tools/dsguard/scope_amendments.py
- tools/dsguard/guardrails_adoption.py
- tools/dsguard/scope.py
- tools/dsguard/pathguard.py
- tools/ds_guard.py
- tools/harmessi/doctor.py
- tools/tests/test_scope_amendments.py
- tools/tests/test_guardrails_readopt.py
- tools/tests/test_pathguard.py
- tools/tests/test_scope.py
- tools/harmessi/tests/test_doctor_guardrails.py
- tools/tests/test_architecture_boundaries.py
- ARCHITECTURE.md
- docs/roadmap/v0.10.md
- .claude/skills/lead-data-scientist/sdd.md

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
