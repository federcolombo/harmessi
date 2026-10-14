# Diseño — 20261013-governed-amendments

Diseño del Change 3 de v0.10 (Governed Amendments). Audit + SDD; sin implementación. Primer consumidor obligatorio de T1 `console_confirmed` (Change 2). Los requisitos R# referencian `spec.md`.

## Decisión metodológica/técnica

### D1. Fuente de verdad del scope y por qué una cadena propia
Hoy el scope vive en `control["alcance"]["rutas_autorizadas"]`, materializado una sola vez en `cmd_approve`. Alternativas para registrar enmiendas:
- `control.json`: mutable, único y no autenticado; una enmienda allí es indistinguible de una edición manual. No sirve como evidencia.
- Ledger de decisiones (`openspec/decisions/ledger.jsonl`): no tiene operaciones amend/correct y su semántica es otra (decisiones, no estado derivado); además es output intrínseco del harness. Reutilizarlo mezclaría semánticas.
- Decisión: archivo de cadena por Change (`amendments.jsonl`) cuya última entrada válida define el scope efectivo; la caché de `control.json` es solo optimización (R18-R22, M3).

### D2. Modelo de versionado
- `scope_hash` = sha256 del JSON canónico de la lista ordenada de rutas; `prev_hash` encadena entradas; `entry_hash` cubre la entrada completa sin ese campo (R19-R20).
- Optimistic concurrency: `--expected-scope-hash` más relectura tras T1.
- No es blockchain ni firma: es detección de edición ingenua y de carreras; sin consenso ni claves.

### D3. `alcance_efectivo` único y fail-closed
- `scope.alcance_efectivo(change_dir, control) -> (rutas, hallazgos)` es el único camino de lectura para `evaluar_alcance`, status/validate y `exec` (R22).
- Cualquier anomalía de cadena deniega: `exec` rechaza y validate emite `ALCANCE-ENMIENDA-INVALIDA` (R23). Evita que tres lectores tengan tres semánticas.
- Sin enmiendas, el comportamiento es idéntico al actual (revisión 0 = caché de aprobación).

### D4. Semántica ADD/REMOVE y no-op
- Solo incrementales; sin replace total (más superficie de error y diff opaco).
- Add de lo presente / remove de lo ausente son no-op deterministas; si todo es no-op no hay T1 ni entrada, para no gastar confirmaciones humanas ni ensuciar el historial (R12).
- Las rutas por defecto del Change no se quitan: el Change debe poder seguir escribiendo sus propios artefactos y SDD (R11).
- Validación con `_normalizar_entrada_alcance`: no se duplica el parser ni se debilitan protecciones (R10, R15).

### D5. Reducción frente a evidencia, tasks y ownership
- Remover una ruta limita trabajo futuro; no borra artifacts, evidencia ni historia, ni reescribe tasks (R17).
- Ownership de writers y harness-owned paths no cambian: es Change 4. Evita acoplar dos modelos de autoridad en una sola operación.

### D6. T1 binding con la operación como «artefacto»
- Opciones consideradas: (A) forzar la aprobación de `proposal.md` con T1 en cada enmienda; (B) primitive nueva de operación; (C) operation approval embebida en el registro de la operación con los tres campos de Change 2.
- Se elige C. A obligaría a re-hashear la propuesta y re-materializar el scope (rompe la cadena, R28); B contradice la consigna de no crear primitive. C reutiliza `solicitar_confirmacion` y `campos_registro`: `artefacto="scope-amendment"|"guardrails-readopt"`, `hash` del diff canónico, `accion` descriptiva (R34-R36).
- El challenge liga la confirmación a ese diff concreto: otra mutación implica otro hash y otro challenge (R35).

### D7. Atomicidad
- Temp en el mismo directorio y `os.replace` (R31).
- Orden exacto (R31): recalcular inmediatamente antes → optimistic concurrency → T1 → releer y verificar que el estado no cambió (si cambió, abortar) → construir el contenido completo nuevo del registro (anterior + línea nueva) en archivo temporal y validar la cadena del temporal → `os.replace` → refrescar la caché de control best-effort (solo scope) → validación posterior.
- Se valida el temporal ANTES de reemplazar: nunca se publica una cadena inválida. El registro es la fuente de verdad: un crash tras el `os.replace` deja estado consistente aunque la caché quede desactualizada (R27, R32).
- Un fallo antes del `os.replace` no deja nada; el challenge consumido no se reutiliza (R33). Nunca es válido «aprobación registrada + mutación incompleta».
- La caché divergente nunca gana: se reconstruye desde la cadena y se emite `ALCANCE-CACHE-DIVERGENTE` (R25).

### D8. Detección de edición manual y sus límites
- Editar la caché es inocuo tras la primera enmienda (R25). Antes de ella (revisión 0) no hay cadena: sigue la confianza actual en `control.json`, límite explícito.
- Editar la cadena rompe `prev_hash`/`entry_hash` y se detecta (R26). Reescribirla completa y coherente no se detecta: por eso pathguard (D11) y el historial de git como evidencia externa.
- Sin criptografía; los registros no se firman.

### D9. Diagnóstico de guardrails
- Claves mutables (`version`, `autonomy.mode|version|budgets|limits`) ya son ignoradas por Doctor: NO necesitan re-adopción (R51).
- El problema real es el drift permanente en `holdouts`, `data_raw`, `secretos_extra`, `write_scopes`, `excepciones`, `autonomy.sealed_sources`, `autonomy.source_access`.
- Closed list aditiva y razonamiento por clave:
  - `holdouts`, `data_raw`, `secretos_extra`, `autonomy.sealed_sources`: elegibles solo como adición, porque añadir una ruta a una lista de deny REFUERZA la protección.
  - `excepciones`, `write_scopes`, `autonomy.source_access`: NO elegibles; añadir allí puede abrir acceso y debilitar el sistema.
  - Remociones: NO elegibles; quitar una protección es debilitar.
  - Claves desconocidas, security ceilings, hooks, permisos de tools: NO elegibles.
- Todo el diff debe ser elegible: un diff mixto rechaza todo, para impedir que una adición legítima contrabandee una inelegible (R43).
- Change 0 pidió excluir «source sealing» salvo contrato explícito. Esta propuesta define ese contrato: `autonomy.sealed_sources` solo admite adiciones, strings no vacíos, sin traversal ni absolutos, y valor actual superconjunto del baseline (R41). Ver M2.

### D10. Baseline de Doctor = plantilla ∪ adopciones
- Doctor compara por igualdad de conjuntos: la diferencia con la plantilla debe ser exactamente la unión de adiciones adoptadas válidas (R53). Un extra o faltante sigue siendo drift (R54).
- No se toca el hash gestionado de Change 1 ni se reutiliza `regenerar_control`: ese hash modela el baseline de la plantilla distribuida por archivo; mezclar adopciones lo debilitaría (R59).
- `guardrails.json` y `control.json` no se modifican en la re-adopción (R46): el archivo es la fuente protegida y la adopción solo reconoce su diferencia.
- Cadena inválida → la diferencia sigue siendo drift más hallazgo (R56).

### D11. Pathguard para los dos registros
- Sin protección, un agente podría escribir un `amendments.jsonl` o una adopción coherente con `approval_channel: console_confirmed` y T1 sería falsificable sin consola. Por eso se protegen `openspec/changes/*/amendments.jsonl` y `openspec/decisions/guardrails-adoptions.jsonl` con el patrón de `guardrails.json` (R61, M1).
- `control.json` no se protege: no está autenticado y deja de ser fuente de verdad del scope tras la primera enmienda (R63).
- Límite: la protección por shell es best-effort.

### D12. sync, managed hashing, upgrade/migration y re-adopción
- `sync` nunca re-adopta: el archivo existente se omite como hoy (R58).
- upgrade/migration reconcilian el repo con una versión del harness; la re-adopción reconoce adiciones de protección del usuario. Se mantienen separados (R60).
- El hash gestionado por archivo de Change 1 permanece sin cambios (R59).

### D13. Dry-run y UX
- `--dry-run` muestra el diff exacto sin T1 ni mutación (R29).
- El usuario no calcula hashes a mano: `scope show` informa revisión y hash; el comando acepta `--expected-*` opcional.
- Ejecución: recalcula, muestra el diff exacto antes del prompt, pide T1 (R30, R48). Prompt corto con operación, hash abreviado y límites de T1 (Change 2 D12).

### D14. Autonomía y STOP
- El Lead razona hasta «necesito ampliar scope X por motivo Y», corre el dry-run y se detiene solo para el T1 humano; luego continúa (R64-R65).
- Sin pasos humanos extra: no hay re-aprobación de propuesta ni edición manual de archivos.

### D15. Riesgos y límites
- T1 es señal de presencia interactiva, no identidad (R5-R6).
- Archivos fuera de pathguard o shell no cubierto permiten escribir registros: límite aceptado (R97).
- Input sintético de consola puede falsificar T1 (Change 2 D2): fuera de garantía.
- El historial de git es evidencia externa para detectar reescritura coherente de la cadena.

## Decisiones aprobadas (2026-10-13)
El humano resolvió M1-M4 y aprobó el SDD.
- **M1.** Pathguard protege `openspec/changes/<change-id>/amendments.jsonl` y `openspec/decisions/guardrails-adoptions.jsonl` contra Write/Edit/NotebookEdit y escrituras detectables por shell. No bloquea lectura, validate, `--dry-run` ni la escritura interna del CLI gobernado (proceso Python). Sin ruta de «editar y reparar»; registro alterado = inválido/fail-closed. No autentica criptográficamente: la seguridad es T1 + binding exacto + cadena/hash + validación fail-closed + Git como evidencia externa.
- **M2.** Closed list EXACTA: `holdouts`, `data_raw`, `secretos_extra`, `autonomy.sealed_sources`, solo monotónica de endurecimiento (effective_new = effective_previous + nuevos válidos). Excluidos: `excepciones`, `write_scopes`, `autonomy.source_access`, hooks, permisos de tools, security ceilings, protected paths, claves desconocidas y las cuatro mutables de Corrective B. `sealed_sources` solo ADD: esto es el contrato explícito que Change 0 exigía para «source sealing». No se amplía sin decisión material.
- **M3.** Archivos de cadena propios: `amendments.jsonl` por Change y `guardrails-adoptions.jsonl` project-level; no es `ledger.jsonl`, no usa su semántica ni depende de `decision amend`; schema y validator propios; tamper evidence básico, no autoría.
- **M4.** Re-aprobar `proposal.md` con enmiendas efectivas → exit 2, sin rebase/replay; cambiar materialmente la proposal exige un flujo futuro o un nuevo Change.

## Target (condicional — feature_engineering, modeling)
No aplica (Change documental).

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica; no se toca ningún holdout.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica; sin datos ni features. Nota: `autonomy.sealed_sources` es configuración de protección, no un dataset consultado.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
Sin desvíos. El challenge de T1 usa `secrets` por diseño; los tests lo fijan con el canal inyectado.

## Alternativas descartadas
- Registrar enmiendas en `control.json` o en el ledger (D1).
- Reemplazo total del scope (D4).
- Forzar la re-aprobación de `proposal.md` o crear una primitive nueva de operación (D6).
- Re-adopción tipo `accept-current-state`/`adopt-all` (D9).
- Closed list que incluya `excepciones`, `write_scopes` o `autonomy.source_access`, o que admita remociones (D9).
- Tocar el hash gestionado de Change 1 o reutilizar `regenerar_control` (D10).
- `sync` re-adoptando (D12).
- Aceptar T0 `declared` como fallback (R1-R3).
- Firmas criptográficas del historial (D8).

## Riesgos
- Falsificación por quien escriba fuera de pathguard o sintetice input de consola (D15).
- Revisión 0 sin cadena depende de `control.json` no autenticado (D8).
- Divergencia entre caché y cadena: mitigada con `alcance_efectivo` único y hallazgo informativo.
- Sobre-promesa de T1: mitigada con el texto normativo R5.
- Falsos negativos de consola en terminales atípicas: fallo cerrado; el humano usa su terminal real.
- Aceptar M2 amplía el contrato de «source sealing» respecto de Change 0.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
Ver `proposal.md`.
