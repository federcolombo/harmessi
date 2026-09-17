# Spec — 20260916-agent-efficiency-and-token-governance

## Requisitos

### R1 — `tools/dsguard/efficiency.py`
Usa `checks.CheckResult`/`STATUS_*` (motor neutral ya existente, mismo criterio que Change 0) — no
crea un segundo motor. Nunca escribe nada.

```python
CODIGO_SESION_LIMITE = "EFICIENCIA-SESION-LIMITE"
CODIGO_SESION_DELEGACIONES = "EFICIENCIA-SESION-DELEGACIONES"
CODIGO_REMEDIACION_INTENTOS = "EFICIENCIA-REMEDIACION-INTENTOS"
CODIGO_REMEDIACION_REPETIDA = "EFICIENCIA-REMEDIACION-REPETIDA"

def evaluar_sesion(sesion: dict) -> list:
    """Reusa sdd.chequear_limites(sesion) TAL CUAL (no reimplementa el cálculo de límites) --
    cada Finding devuelto se traduce a CheckResult WARN (uno por límite excedido); si
    chequear_limites no devuelve nada, PASS único. Funciona igual para una sesión activa o ya
    cerrada -- chequear_limites no distingue eso, solo mira presupuesto vs. contadores."""

def evaluar_delegaciones_sesion(sesion: dict) -> list:
    """N/A si la sesión no declara max_roles en su presupuesto. WARN si
    len(sesion['roles']) >= max_roles declarado. PASS si no."""

def evaluar_remediacion(remediacion: dict) -> list:
    """N/A si no hay ventanas registradas. WARN (CODIGO_REMEDIACION_INTENTOS) si la ventana vigente
    agotó sus intentos (len(intentos) >= max_intentos). WARN adicional (CODIGO_REMEDIACION_REPETIDA)
    si hay >=2 intentos en la ventana vigente y TODOS declaran exactamente la misma 'causa' (string
    comparison exacta, determinista -- nunca similitud difusa ni juicio semántico). PASS si ninguna
    de las dos señales aplica."""

def evaluar_eficiencia_change(repo_root, change_id) -> list:
    """Lee control.json del change (openspec/changes/<id>/ o, si no está ahí,
    openspec/archive/<id>/ -- un change archivado también es válido de reportar). Evalúa CADA
    sesión en control['sesiones'] (activa o cerrada, todas) y CADA remediación en
    control['remediaciones']. Nunca lanza por control.json ausente/corrupto -- FAIL único con
    kind=technical_error, mismo patrón que scientific_validity.evaluar_scientific_checks ante
    policy corrupta."""
```

### R2 — CLI
`python -m tools.ds_guard efficiency report --change-id <id> [--json]`. Exit code:
`checks.exit_code(resultados)` (consistente con `science status`/`mlops status` — aunque acá
`FAIL` es raro, casi todo el vocabulario esperado es PASS/WARN/N-A; un `FAIL` real solo ocurre por
`control.json` corrupto/ausente, kind=technical_error). Formato humano compacto, igual estilo que
`science status` (`STATUS  CODE: message`, resumen de conteos al final).

### R3 — Read-only estricto
`evaluar_eficiencia_change`/CLI nunca llama `session_note`/`remediation_note`/`remediation_resolve`/
`remediation_extend`/`escribir_control`/`session_start`/`session_close`. Verificado byte a byte en
tests (mismo patrón que Change 0/1: `dsguard.core.capturar_bytes` antes/después).

### R4 — Docs
`methodology.md` + `.tmpl`: sección nueva mínima (10-15 líneas) sobre cuándo el Lead puede consultar
`ds_guard efficiency report` — nunca obligatorio, nunca convierte un WARN en bloqueo de nada.

## Criterios de aceptación
- [ ] Sesión activa dentro de todos sus límites → `EFICIENCIA-SESION-LIMITE` PASS.
- [ ] Sesión (activa o cerrada) que excedió `max_reintentos` → WARN, mensaje reusa el texto de
      `chequear_limites` (no lo reinventa).
- [ ] Sesión sin `max_roles` declarado (formato viejo) → `EFICIENCIA-SESION-DELEGACIONES` N/A, nunca
      FAIL/WARN por un campo ausente.
- [ ] Remediación con ventana vigente agotada → WARN `EFICIENCIA-REMEDIACION-INTENTOS`.
- [ ] Remediación con 2+ intentos y la misma `causa` textual exacta → WARN adicional
      `EFICIENCIA-REMEDIACION-REPETIDA`.
- [ ] Remediación con intentos de `causa` distinta → sin ese WARN (solo PASS o el WARN de intentos
      si corresponde).
- [ ] `control.json` ausente/corrupto → 1 resultado FAIL `kind=technical_error`, no crashea.
- [ ] Change archivado (`openspec/archive/<id>/control.json`) también se puede reportar.
- [ ] Read-only verificado byte a byte (CLI y función directa).
- [ ] Determinismo: misma corrida sobre el mismo `control.json` → mismo resultado.
- [ ] Suite completa + manifest parity + doctor sin errores nuevos.

## Cutoff / information boundary
No aplica.

## Baseline (condicional — modeling)
No aplica.
