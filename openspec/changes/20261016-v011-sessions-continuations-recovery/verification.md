# Verificación — 20261016-v011-sessions-continuations-recovery

## Resumen
Change 3 de v0.11: `session expiry != lost work`. Constante única `SESSION_MINUTES_DEFAULT` (valor 90 intacto), aviso anticipado `AVISO-SESION-POR-VENCER` (stderr, ≤10 min), `minutos_restantes`/`aviso` en `session status`, y `session start --retomar` que hereda contadores y topes `max_*` de la última sesión cerrada (R4b, decisión del usuario).

## Reviewer
Ciclo 1 (`data-science-reviewer`, solo lectura, sin ejecutar tests): 0 bloqueantes, 0 altos, 2 medios, 4 menores.
- M1 (topes `max_*` no heredados): resuelto con R4b (decisión explícita del usuario).
- M2 (recovery tras agotar reintentos): resuelto; el mensaje del hook aclara `remediation extend` / `--max-reintentos` mayor, sin subir límites automáticamente.
- m3 (spec R6 vs allowlist): spec corregido. m4 (`--retomar` en sinopsis de `verificador.md`): aplicado en archivo y plantilla.
- m5 (relanzar con mismo `agent_id` pisa el contador): comportamiento previo del hook, H1 intacto; no se toca. Limitación cooperativa, documentada aquí.
- m6 (`<= 0` vs `< 0` en vencimiento): no es bug real, cambiarlo altera semántica de límites; no se toca.
No se usó ciclo 2: sin blocker/HIGH y los fixes no cambian la semántica revisada salvo M1, decidida por el usuario.

## Evidencia obtenida
Tests dirigidos, corrida real tras los fixes:
- `test_session_recovery`: 28 OK
- `test_operational_session_recovery`: 26 OK
- `test_operational_budgets`: 28 OK
- `test_ds_guard_budgets_cli`: 36 OK
- `test_manifest_dsguard_parity`: 11 OK
- `test_skill_methodology`: 52 OK (tras actualizar `test_sdd_conserva_default_de_continuaciones`: el parámetro pasó a `Optional[int] = None` con default efectivo 1 vía `_tope`; el invariante «default 1» se mantiene y ahora se fija en ambas formas).

Cobertura nueva de M1: retomar sin flags conserva topes 10/5 y contadores 8/4 sin `SESION-LIMITE-*`; `--max-tareas 12` reemplaza solo ese tope; `max_sessions` y `aggregate_minutes` siguen bloqueando al retomar; `start` sin `--retomar` conserva defaults 3/2/2/2/1.

### Caso real de expiración y recovery (s1→s2→s3, Change 1 de v0.11)
Fuente: `openspec/changes/20261016-v011-git-scope-fail-closed/control.json`.
- s1: deadline 15:50:51Z, cerrada 15:55:53Z, 95.03 min consumidos (venció por reloj esperando tests).
- s2: abierta 15:56:00Z, deadline 17:26:00Z, cerrada 17:33:46Z, 97.77 min (venció igual).
- s3: abierta 17:33:49Z, 26.07 min, sin pérdida de trabajo pero con contadores en cero (el problema que motiva este Change). s4 se abrió con `--minutos 480` (deadline 02:00:08Z).
Sin `--retomar` cada sesión nueva nacía en cero (`rondas_revision`, `reintentos`, continuaciones). Este Change lo corrige y además se usó en la práctica: la sesión s2 de este Change se abrió con `--retomar` (`retomada_de: s1`) el 2026-10-19 tras 3 días de pausa, sin perder el estado.

## Diferencias contra la spec
R4b se agregó al spec durante la revisión (decisión del usuario); R6 se corrigió (m3). Sin otras divergencias.

## Limitaciones
- Regresión completa diferida a Change 6 (batches seriales, por el incidente de memoria registrado en Change 1).
- Los artefactos de código los escribió `python-data-engineer`; el Lead ejecutó los tests.
- La herencia de `continuaciones` solo protege la vía SendMessage; un `Agent` nuevo con el mismo `agent_id` reinicia su contador (hook sin cambios, H1).
- El reviewer no ejecutó tests ni revisó el diff completo; la verificación ejecutable es la de este documento.

## Pendientes derivados
Change 4 (4B primero), 5, 6 y release.

## Resultado final
Change 3 verificado: gate técnico satisfecho con tests dirigidos (181 OK, 0 fallos) y sin hallazgos abiertos del reviewer.
