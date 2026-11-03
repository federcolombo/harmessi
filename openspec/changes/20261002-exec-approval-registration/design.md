# Diseño — 20261002-exec-approval-registration

## Decisión metodológica/técnica

**D1 — Builders puros compartidos.** Se extrae de cada `cmd_exec_*` (`tools/ds_guard.py:2140-2210`) la
parte que calcula `(argv, artefacto, hash_comando)` a `_construir_exec_pytest/_script/_notebook(args,
repo_root)`, devolviendo una `NamedTuple` local `ExecSpec(forma, argv, artefacto, hash_comando,
algoritmo)`. `cmd_exec_*` pasan a: construir → `_ejecutar_exec_comun`. `cmd_exec_approve_*` pasan a:
construir → `_validar_request_exec` → registrar. No hay segundo cálculo de hash.

**D2 — Helper de validación del request.** El tramo de `_ejecutar_exec_comun` (`:1964-1983`) que arma
`ExecutionRequest` y llama a `evaluar_comando` se extrae a `_validar_request_exec(args, command_form,
argv, control)` y lo usan ambos consumidores; mismos mensajes y exit codes que hoy.

**D3 — Registro.** `_registrar_aprobacion_exec(...)`: `control.setdefault("aprobaciones", []).append(
entrada)` + `core.escribir_control` — espejo de `cmd_approve` (`:360-376`), con `algoritmo` por forma.
Sin `registrado_utc` manipulable (`core.ahora_utc()`).

**D4 — CLI.** El grupo `exec` tiene subparsers `{script,pytest,notebook}`; se agrega `approve` con
subparsers anidados `{pytest,script,notebook}`. Las definiciones de argumentos semánticos se factorizan
en `_agregar_args_exec_<forma>(parser)` usadas por ambos grupos, para que no puedan divergir. Metadata
humana igual a `approve` (`--usuario --fecha --alcance --cita`, requeridos). Flags de pytest tras `--`.
Sin `--timeout` en approve (no entra al hash; `ExecutionRequest` usa el default).

**D5 — Semántica por forma.** pytest: hash de argv (preservado). notebook: `hash_lf_v1` del manifest
(preservado). script: NUEVA semántica v2 (R9), y legacy reconocida (R9b). Se rotula `algoritmo` con la
verdad por forma (F2). Ningún hash de pytest/notebook existente cambia (R19, vectores fijos).
El builder de script devuelve además `hash_legacy` (= `hash_lf_v1(script)`); `_resolver_aprobacion_exec`
consulta la entrada más reciente (`sdd._aprobacion_mas_reciente`), y SOLO si su `algoritmo` es
`sha256/lf/v1` acepta el hash legacy; en cualquier otro caso exige el hash v2. `nbrunner.manifest.
validar_aprobacion` no se modifica.

**D6 — Trust model.** Paridad con `approve`: sin autenticación nueva (deuda v0.10 ya registrada en
`docs/roadmap/v0.10.md`). El texto de ayuda y `sdd.md` lo dicen explícitamente.

**D7 — Documentación.** `sdd.md` (copia instalada del repo) y `sdd.md.tmpl`: reemplazar «aprobación
humana» por la vía concreta; regenerar `.ds_init/control.json` con la herramienta soportada (precedente
`8a8d6ec`), verificando Doctor sin drift.

## Archivos
Modifica: `tools/ds_guard.py`, `.claude/skills/lead-data-scientist/sdd.md`,
`tools/ds_init/profiles/python_jupyter_data/templates/sdd.md.tmpl`, `.ds_init/control.json`
(regenerado), `docs/roadmap/v0.10.md` (deuda; ya agregada). Nuevo: `tools/tests/test_ds_guard_exec_approve.py`.
No toca: `tools/leadrun/*`, `tools/autonomy/*`, `tools/nbrunner/*`, `tools/dsguard/*`, tests existentes,
`tools/cards/*`, Change 0.

## Tests (archivo nuevo, vía subprocess del CLI real, sin insertar JSON a mano)
Los 16 del encargo: (1) supervised pytest sin aprobación bloquea; (2) `exec approve pytest` crea entrada;
(3) exec exacto permitido; (4) otro target; (5) otro flag (y otro orden); (6) otro change; (7) request
inválido sin aprobación; (8) allowlist reject sin aprobación (fuera de alcance, absoluta, traversal);
(9) sin `--hash`/forma desconocida; (10) `approve` de archivo físico intacto; (11) autonomous sin
cambios; (12) `escribir_control` (estructura de entrada y de archivo); (13) consumo por runtime real
(`ExecutionRecord` creado); (14) script (contenido invalida, argumentos no, documentando F1); (15)
notebook; (16) suites preexistentes sin editar. E2E: `exec approve pytest` → `exec pytest` → ejecución
gobernada real. Más: vectores fijos de regresión del hash (R19) y paridad builder↔exec (R7).

## Target (condicional)
No aplica.

## Features permitidas/prohibidas (condicional)
No aplica.

## Estrategia de split/validación (condicional)
No aplica.

## Leakage risks (condicional)
No aplica a datos. Riesgo análogo: aprobar algo distinto de lo que se ejecuta. Mitigación: builder único
(R5/R7), allowlist previa (R12), hash nunca suministrado por el humano (R2).

## Reproducibilidad (opcional)
Sin aleatoriedad; relojes reales solo en `registrado_utc`.

## Alternativas descartadas
- `approve --artefacto pytest:… --hash H` (hash opaco fabricado por el humano).
- Relajar `cmd_approve` para aceptar artefactos no-archivo (mezcla dos contratos de hash).
- Segundo store de aprobaciones o sidecar.
- Cambiar script/notebook a argv hashing (redefine aprobaciones existentes; ver F1).
- Distinguir humano vs. agente en este fix (deuda v0.10).

## Riesgos
- Refactor de `cmd_exec_*` rompe comportamiento: mitigado con suites preexistentes sin editar + vectores
  fijos.
- Drift de archivos gestionados al editar la plantilla: regeneración soportada de `control.json`.
- F3 («última gana») sorprende: documentado.

**D8 — Notebook.** Se audita en implementación qué liga el manifest. Si aparece un hueco material
comparable (p. ej. parámetros de ejecución fuera del manifest), se versiona igual que script si es
pequeño; si exige rediseño transversal → STOP.

## Decisión material
**M1 — RESUELTA por el autor (2026-10-02):** no se preserva la semántica débil de script; las
aprobaciones nuevas usan v2 (contenido + argv canónico, intérprete normalizado), la legacy
`sha256/lf/v1` sigue reconocida con aviso, sin migración. F3 se documenta como comportamiento actual
(el hash exacto diferencia la ejecución; no se agrega mecanismo para aprobaciones simultáneas).

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
