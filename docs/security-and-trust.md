# Seguridad y modelo de confianza

Harmessi es un conjunto de guías, guardas y herramientas para trabajo de ciencia de datos con agentes. No es un sandbox ni un producto de seguridad. Esta página dice qué se hace cumplir técnicamente y qué descansa en convención.

## Qué se hace cumplir y qué es cooperativo

- **Hooks de Claude Code**: algunas reglas se aplican con hooks `PreToolUse` que corren antes de una llamada a herramienta (`tools/dsguard/`). Solo protegen lo que está registrado en `.claude/settings.json` (superficie protegida, que se modifica por un paso humano) y solo dentro de Claude Code. Fuera de ese entorno no hay enforcement.
- **Controles cooperativos**: varias protecciones dependen de que los agentes y el código del proyecto las respeten. Ejemplos documentados: los output roots son un «control cooperativo, no sandbox» (`docs/cli-reference.md`); el lock de `ds_init` es cooperativo y no detecta el pid (`docs/installation.md`); las continuaciones de subagentes son cooperativas (`docs/releases/v0.10.0.md`).
- **Reglas de proceso**: el Lead no edita archivos, quien implementa no controla el lifecycle del Change, y los holdouts requieren autorización explícita del usuario (`.claude/skills/lead-data-scientist/SKILL.md`). Son reglas del rol; el hook de rutas agrega una barrera técnica solo para las rutas protegidas.

## Rutas protegidas y fail-closed

`tools/dsguard/hook_rutas.py` protege holdouts, `data/raw`, secretos y `.claude/guardrails.json`. Es fail-closed a propósito: un payload ilegible o inválido, un `guardrails.json` corrupto o cualquier excepción durante la evaluación deniegan (exit 2) en lugar de permitir. La lógica de evaluación está en `tools/dsguard/pathguard.py`.

## Hooks fail-open

- `tools/dsguard/hook_presupuesto.py` (presupuesto de sesión) es fail-safe hacia permitir: protege disponibilidad, y bloquear todo por un `control.json` ilegible sería peor.
- `tools/dsguard/hook_subagentes.py` es telemetría de `SubagentStart`/`SubagentStop` y es fail-open: `main()` siempre devuelve 0. Sin sesión activa no registra. Lee solo `hook_event_name`, `agent_id` y `agent_type`; no lee ni persiste el mensaje del asistente, transcripts, prompt ni `cwd`. No usa lock: queda una carrera residual de milisegundos que puede perder un alta o revertir un contador, sin corromper el archivo. Está inactivo hasta que el evento se registra en `.claude/settings.json`.

## Privacidad: best-effort y heurística

- La redacción de evidencia de evals (`tools/harmessi_bench/redact.py`, aplicada en `storage.py` a `stdout_excerpt`, `score.detail`, `availability_error`, `model` y `effort`) es best-effort. No se persiste el prompt de los casos.
- El escaneo de privacidad de candidates de `harmessi_improve` reutiliza esa redacción: rechaza un texto que la redacción modificaría (`tools/harmessi_improve/candidate.py`). Es heurístico (`docs/releases/v0.14.0.md`).
- El barrido de tests `tools/tests/test_privacy_sweep.py` busca, con expresiones regulares, rutas personales, emails reales, secretos obvios y el nombre de usuario del autor en `tools/tests/fixtures/`, `docs/`, `ARCHITECTURE.md`, `README.md` y las suites de `tools/harmessi_bench`. Su propio aviso: es determinista pero heurístico, y la ausencia de hallazgos no prueba que no haya datos sensibles.
- La CLI de `harmessi_improve` sanea la ruta del repositorio en su salida, pero los textos de error del sistema operativo pueden incluir rutas (`docs/releases/v0.14.0.md`).

## Procedencia no criptográfica

Los artefactos bajo `.harmessi/improvement` y `.harmessi/evals` tienen hashes y manifests que permiten detectar inconsistencias internas, pero no prueban quién los escribió: no hay firmas. Las cadenas de enmiendas son append-only sin enforcement criptográfico (`docs/releases/v0.10.0.md`). Un `run_manifest` identifica la configuración (git, hashes de skills/guardrails, suite), no al autor.

## Límites del cierre de alcance

Reglas en `ARCHITECTURE.md` §12. Límites:

- La confirmación T1 acredita presencia en consola, no identidad; `--usuario` es metadata declarada.
- La atestación de cambios Protected no es criptográfica (cadena de hashes sin firmas) y no es una exención: un cambio posterior del archivo falla cerrado.
- El registro de atestaciones no tiene secreto (`entry_hash` no es una clave): quien pueda escribir el archivo por otra vía puede forjar una cadena; la defensa es pathguard (best-effort) y la revisión humana del diff. El hash se compara con el contenido actual (un Change posterior que re-modifique la ruta exige re-atestar), `hash_lf_v1` ignora BOM y fin de línea, y el prompt T1 muestra 12 hex, no el diff.
- La frontera de la ventana exige que el baseline del sucesor sea ancestro de HEAD pero no valida su estado ni aprobación: un Change descartado o forjado en `openspec/changes/` puede acotarla (siempre se informa con `ALCANCE-VENTANA-ACOTADA`).
- La ventana de cierre por ascendencia git supone Changes secuenciales; un sucesor creado mientras el antecesor seguía en implementación no se detecta. Con sucesores equidistantes se desempata por `change_id` menor; los Changes con `estado: descartada` no acotan.
- Un Change archivado deja de acotar la ventana (solo se consulta `openspec/changes/`): cerrar en orden (p. ej. C4→C5→C6) antes de archivar.
- El trabajo de A posterior al baseline de su sucesor B no lo ve la ventana de A; lo evalúa la ventana de B (o el working tree sucio).

## Qué Harmessi NO garantiza

- Que un dataset o modelo sea ético, justo, seguro, privado o conforme a normas (`README.md`).
- Aislamiento: los agentes corren con los permisos de su entorno; no hay sandbox.
- Detección completa de datos sensibles o secretos.
- Autoría ni integridad frente a un actor que modifique archivos locales.
- Equivalencia de comportamiento entre providers: solo hay un host validado en vivo (`docs/providers.md`).
- Calidad semántica de las evaluaciones (`docs/evaluation.md`).
- Validación fuera de Windows por ejecución, ni ejecución observada de CI remoto durante la publicación (`docs/releases/v0.14.0.md`).

## Reportar un problema

El `README.md` y `docs/` no documentan un canal de reporte de vulnerabilidades ni un archivo `SECURITY` en el repositorio. Hasta que exista uno documentado, no se promete un canal ni un plazo de respuesta.
