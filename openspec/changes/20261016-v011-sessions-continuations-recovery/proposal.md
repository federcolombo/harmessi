# Propuesta — 20261016-v011-sessions-continuations-recovery

> Change 3 de v0.11. Principio: `session expiry != lost work`. El valor 90 y la semántica wall-clock NO cambian.

## Problema
(1) El default de minutos está triplicado: `ds_guard.py:_BUDGET_DEFAULTS`, `dsguard/core.py` (fallback) y `dsguard/sdd.py` (default de firma). (2) No hay aviso anticipado: el hook solo bloquea a ≤5 min y a ≤0. (3) El recovery tras vencer (cerrar + abrir otra sesión) existe pero la sesión nueva nace en cero: se pierden `rondas_revision`, `reintentos` y los contadores de continuación de subagentes, es decir, el ciclo de reviewer y los límites acotados se reinician. Evidencia real: en Change 1 de v0.11, s1 y s2 vencieron por reloj esperando tests.

## Objetivo
Una única fuente funcional del default, aviso anticipado determinista, y recovery verificable que preserve el estado relevante.

## Alcance
Constante canónica `SESSION_MINUTES_DEFAULT` en `core.py` reutilizada por `sdd.py`, `ds_guard.py`; `minutos_restantes` y `aviso` en `session status`; aviso `AVISO-SESION-POR-VENCER` (stderr) cuando restan ≤10 min en los comandos que cargan un Change; `session start --retomar` que hereda de la última sesión cerrada del Change `rondas_revision`, `reintentos`, `roles`, `tareas` y contadores de continuación por subagente, con `retomada_de`; el mensaje de recuperación del hook muestra el comando literal con `--retomar`; docs y tests.

## Fuera de alcance
Cambiar el valor 90, `maxTurns`, el reloj wall-clock, pausar el reloj durante T1, cambiar el protocolo de salida del hook, scheduler, H1.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- tools/dsguard/core.py
- tools/dsguard/sdd.py
- tools/dsguard/hook_presupuesto.py
- tools/ds_guard.py
- .claude/skills/lead-data-scientist/methodology.md
- .claude/skills/lead-data-scientist/SKILL.md
- .claude/skills/lead-data-scientist/verificador.md
- tools/ds_init/profiles/**
- tools/tests/**
- docs/roadmap/v0.11.md
- openspec/changes/20261016-v011-sessions-continuations-recovery/**

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
