# Propuesta — 20261016-v011-git-scope-fail-closed

> Change 1 de v0.11 (Operational Robustness & Recovery). Principio: `unknown Git state != clean Git state`.

## Problema
Según la auditoría del Change 0 (`docs/roadmap/v0.11.md`), un fallo de Git puede leerse como «sin archivos tocados»:
`repo.list_dirty_files`, `get_head`, `diff_check` e `is_tree_clean` no verifican `returncode`; `scope.archivos_tocados_desde_baseline` devuelve `[]` ante
`GitCommandError` y ante cualquier `Exception`; rename/copy evalúa solo el lado nuevo; las refs no llevan guarda contra `-`/`--`; `_git` usa
`text=True` (altera `\r` en nombres POSIX); `ALCANCE-GIT-ILEGIBLE` no está documentado en `verificador.md`.

## Objetivo
Que ningún fallo de Git (comando fallido, ref inválida, Git ausente, salida malformada) se convierta en estado limpio o en «sin archivos»; cada uno
produce un hallazgo gobernado o un error explícito.

## Evidencia
`tools/dsguard/repo.py` (`_git`, `list_dirty_files`, `get_head`, `diff_check`, `is_tree_clean`), `tools/dsguard/scope.py:28-50,135-138`,
`tools/ds_guard.py` (usos en `cmd_status`, `cmd_validate`, `cmd_archive`, `cmd_init`, notebook-diff), `tools/dsguard/notebooks.py:54-57`.

## Supuestos descartados
La salida ilegible ya es fail-closed (v0.10) y el parseo `-z` es correcto; no se tocan.

## Alcance
Verificación de returncode en `repo.py`; excepción única `GitCommandError` (ya existente); `scope.evaluar_alcance` traduce cualquier fallo a
`ALCANCE-GIT-ILEGIBLE`; rename → ambos lados, copy → destino; validación de refs (`-` inicial rechazado, `--` posterior); captura de bytes sin
universal newlines; callers de `ds_guard.py` convierten el error en hallazgo/exit 3; documentación; tests.

## Fuera de alcance
Nuevos subcomandos Git, framework Git, cambios al parseo `-z`, scope amendments, CI cross-platform.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- tools/dsguard/repo.py
- tools/dsguard/scope.py
- tools/dsguard/notebooks.py
- tools/dsguard/mlops_foundations.py
- tools/ds_guard.py
- .claude/skills/lead-data-scientist/verificador.md
- tools/ds_init/profiles/**
- tools/tests/**
- tools/ds_init/tests/**
- docs/roadmap/v0.11.md
- openspec/changes/20261016-v011-git-scope-fail-closed/**

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
