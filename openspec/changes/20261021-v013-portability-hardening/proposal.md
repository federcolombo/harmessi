# Propuesta — 20261021-v013-portability-hardening

> Change 4 de v0.13: Portability & Cross-Platform Hardening. Incluye las dos deudas de v0.12 (`dsimpact/git_source.py` fail-open; `## Skills cargados` duplicada).

## Problema
1. `tools/dsimpact/git_source.py` (`contenido_before`/`contenido_after`) devuelve `None` ante **cualquier** fallo de `git show` o de lectura: un estado Git ilegible se confunde con «el archivo no existía». Con eso `dsimpact` puede reportar 0 consumidores afectados sobre evidencia que no pudo obtener (unknown ≠ empty).
2. Una segunda sección `## Skills cargados` en `tasks.md` se ignora en silencio (solo se lee la primera).
3. No hay CI ni evidencia sistemática de portabilidad; el desarrollo y la validación ocurrieron solo en Windows. Hay hallazgos concretos (p. ej. la consola Windows con codepage no UTF-8 degrada tildes en la salida de CLIs).

## Objetivo
Cerrar las dos deudas con comportamiento fail-closed explícito, auditar los supuestos de plataforma, dejar tests de portabilidad ejercitados en el host real y un workflow mínimo de smoke para Windows/Linux/macOS — sin afirmar validación en plataformas donde no se ejecutó.

## Evidencia
- `tools/dsimpact/git_source.py:72-89` (`return ... else None`), llamadores `scan.py:62-65` y `:110-113`, `GitSourceError` ya traducida por `cli.py:44`.
- `tools/dsguard/repo.py`: `leer_en_commit`/`existe_en_commit` (también fail-open por diseño, documentado) y lista blanca de subcomandos; se reusa, sin capa Git nueva.
- `tools/dsguard/skill_contract.py:358-396` y llamador `tools/ds_guard.py:435`.
- Auditoría de `openspec/changes/*/tasks.md`: ningún Change existente tiene `## Skills cargados` duplicada (compatibilidad hacia atrás verificada por grep antes de endurecer).
- No existe `.github/`; `gh` no está instalado.
- La salida de `suite-check` mostró mojibake en la consola Windows (codepage no UTF-8).

## Supuestos descartados
- Que la CI remota pueda observarse desde esta máquina: no; el workflow se valida estructuralmente y su ejecución remota NO se afirma.
- Que haya host Linux/macOS: no; solo contratos, tests y CI.
- Fusionar secciones duplicadas: no; se rechaza con hallazgo.

## Alcance
- **dsimpact fail-closed**: `contenido_before`/`contenido_after` reciben el `status` esperado y lanzan `GitSourceError` cuando el contenido debía existir y no pudo obtenerse (ref/blob ilegible, error de Git, archivo ilegible en working tree); `None` solo cuando la ausencia es esperada por el status (added/deleted). Mensajes sin rutas absolutas. Llamadores y CLI traducen a mensaje + exit code existente; tests actualizados.
- **Sección duplicada**: nuevo hallazgo `SKILL-TRAZA-SECCION-DUPLICADA` (de `validar_referencias_skills`), determinista, sin fusión; documentación (methodology/sdd + mirrors `.tmpl`, ARCHITECTURE) actualizada.
- **Consola**: las CLIs nuevas de `harmessi_bench` degradan de forma segura ante codepage no UTF-8 (sin `UnicodeEncodeError`).
- **Auditoría de portabilidad**: `docs/portability.md` con tabla área → hallazgo → acción/estado (pathlib, subprocess, encodings, finales de línea, shell, lookup de ejecutables, temp dirs, symlinks/junctions, consola, Git, variables de entorno); test estático que impide regresiones en los módulos v0.13 (lecturas/escrituras de texto con encoding explícito, sin `shell=True`, sin rutas POSIX/Windows hardcodeadas).
- **Tests de portabilidad** en el host real: espacios, Unicode, CRLF/LF, temp dirs, subprocess, Git (repo temporal con espacios/Unicode).
- **CI**: `.github/workflows/portability-smoke.yml`: matriz `ubuntu-latest`/`windows-latest`/`macos-latest` × un Python central (3.12), corre la lista acotada de tests de portabilidad/contrato (no la suite completa); sin dependencias nuevas más allá de `pytest`; test estructural del workflow.
- Docs: ARCHITECTURE.md, README.md, roadmap (Change 4: qué es real y qué contractual).

## Fuera de alcance
Reescribir módulos para soporte POSIX completo, validar en Linux/macOS, suite completa en CI, ejecutar/observar Actions, cambios de versión, nuevas deprecaciones, cambios a hooks/permisos/roles.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- tools/dsimpact/git_source.py
- tools/dsimpact/scan.py
- tools/dsimpact/cli.py
- tools/dsimpact/tests/*.py
- tools/dsguard/skill_contract.py
- tools/ds_guard.py
- tools/tests/test_skill_contract.py
- tools/tests/test_skill_methodology.py
- tools/harmessi_bench/cli.py
- tools/harmessi_bench/tests/*.py
- tools/providers/conformance.py
- tools/tests/test_v013_portability_smoke.py
- tools/tests/test_v013_portability_audit.py
- tools/tests/test_v013_ci_workflow.py
- .github/workflows/portability-smoke.yml
- .claude/skills/lead-data-scientist/methodology.md
- .claude/skills/lead-data-scientist/sdd.md
- tools/ds_init/profiles/python_jupyter_data/templates/methodology.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/sdd.md.tmpl
- docs/portability.md
- ARCHITECTURE.md
- README.md
- docs/roadmap/v0.13.md
- openspec/changes/20261021-v013-portability-hardening/**
