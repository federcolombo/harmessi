# Propuesta — 20260915-checks-engine-foundation

## Problema
`tools/harmessi/doctor.py` (995 líneas) ya implementa, de hecho, un motor de checks casi
completo (`ResultadoCheck`, `_ejecutar_check` con manejo de excepciones, orquestación que nunca
frena, conteos, exit code) pero acoplado a su propio vocabulario `OK/WARN/ERROR` y sin ser
reutilizable por otros consumidores futuros (readiness, promotion). El roadmap v0.3 necesita un
vocabulario canónico `PASS/WARN/FAIL/N/A` neutral, extraíble a un módulo compartido.

## Objetivo
Crear `tools/dsguard/checks.py` (motor neutral: `CheckResult`, ejecución sin short-circuit,
conteos, exit code) y convertir `harmessi doctor` en su primer consumidor real, preservando
byte a byte su UX pública actual (mismos códigos, mensajes, secciones, orden, exit code,
conteos — 27 OK / 3 WARN / 0 ERROR en este repo salvo hallazgo real).

## Evidencia
- `tools/harmessi/doctor.py:95-104` (`ResultadoCheck`, frozen dataclass) y `:107-123`
  (`_ejecutar_check`, ya atrapa excepciones inesperadas y las convierte en `ERROR` con sufijo
  `-EXCEPCION`) y `:926-973` (`ejecutar`, orquesta ~20 checks en 3 secciones fijas, nunca frena,
  `exit_code = 1 if any ERROR`).
- `tools/harmessi/doctor.py:32` — `from tools.dsguard import pathguard`: la dependencia
  `harmessi → dsguard` YA existe hoy, confirma que ubicar el engine nuevo en `dsguard/` no
  introduce ningún ciclo.
- `tools/dsguard/core.py:148-161` (`Finding`) — sin campo de severidad, semántica de
  presencia-solamente (gates de SDD/pathguard/kdd/decision: "sin findings = OK"),
  estructuralmente distinto de lo que necesita `CheckResult` (representar PASS y N/A como
  resultados de primera clase, no como ausencia de problema).
- `tools/harmessi/tests/test_doctor.py` (453 líneas) — asertan directamente sobre
  `.nivel`/`.seccion`/`.codigo` de `ResultadoCheck` y sobre `exit_code`; el retrofit debe
  preservar la firma pública de `ejecutar()` para no requerir reescribirlos.
- `tools/harmessi/doctor.py:1-9` (docstring del módulo) — doctor corre desde el checkout fuente
  de Harmessi apuntando `--destino` a cualquier repo; **no se instala** en proyectos destino
  (confirmado, sin relevancia de manifest para `doctor.py`/`cli.py` en sí).
- Roadmap v0.3 aprobado (Change 4 de la serie), Change 3 (`maturity.py`, cerrado) como
  precedente directo de módulo neutral en `dsguard/`.

## Supuestos descartados
No se implementa readiness, `project promote`, checks MLOps, gates de
production_candidate/production, cutoff/baseline, scaffold progresivo, Lead awareness, unified
status, reporting, multi-provider, dsimpad — todos changes posteriores del roadmap. No se
unifican `Finding` y `CheckResult`. No se cambia el esquema de exit codes 0/1/2/3 de
`ds_guard.py` (doctor mantiene su propio esquema binario, ya distinto hoy). No se "arreglan" los
3 WARN de drift actuales del repo (esperados, documentados en Changes 0/2/3). No se introduce
`N/A` artificialmente en ningún check existente.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica.

## Alcance
1. **`tools/dsguard/checks.py`** (nuevo): `CheckResult` (dataclass frozen:
   `status, code, message, detail=None, subject=None, kind: str = "check"` — `kind` distingue
   FAIL funcional de error técnico, ver `design.md` punto 9), constantes
   `STATUS_PASS/WARN/FAIL/NA`, `ejecutar_checks(registros) -> list[CheckResult]` (nunca frena,
   excepción → `FAIL` con sufijo `-EXCEPCION`, mismo formato de mensaje que `_ejecutar_check`
   hoy), `contar_por_status`, `hay_bloqueo`, `exit_code`, `filtrar_por_status`.
2. **Retrofit de `tools/harmessi/doctor.py`**: las ~20 funciones `_check_*` pasan a devolver
   `list[CheckResult]` internamente; `_ejecutar_check` delega en `checks.ejecutar_checks` y
   traduce a `ResultadoCheck` (`PASS→OK, WARN→WARN, FAIL→ERROR`, `subject→ubicacion`);
   `_ejecutar_check_con_dato` se mantiene doctor-local pero reusa la misma traducción.
   `ejecutar()`/`formatear()` mantienen firma y comportamiento público EXACTOS. `N/A` se agrega
   al resumen de `formatear()` solo condicionalmente (si el conteo es > 0) — hoy nunca aparece,
   cero cambio de salida.
3. **Manifest**: entrada VERBATIM de `tools/dsguard/checks.py`; test de paridad extendido con
   aserción explícita hardcodeada.
4. **Tests**: ver `tasks.md` — engine (15 casos) + Doctor (9 casos, incluida regresión de
   conteos/exit code/mensajes exactos) + regresión completa + scratch install.

## Fuera de alcance
Readiness, `project promote`, checks MLOps, gates de production_candidate/production,
risk-based checks, project_stage-aware severities, cutoff, baseline, inference checks, scaffold
progresivo, unified status, Lead methodology awareness, Agent Efficiency/Token Governance (queda
anotada como deuda futura, no implementada), dsimpact, reporting, multi-provider. Ningún cambio
a `Finding`/`dsguard/core.py`. Ninguna unificación de exit codes entre `doctor` y `ds_guard.py`.

## Holdout policy (condicional — solo cambios "sensible")
No aplica.

## Impacto en production-readiness (opcional)
Ninguno directo — sienta la infraestructura de vocabulario que los changes futuros de
readiness/promotion van a consumir.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md`.

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md`.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-14
- Alcance aprobado: Motor neutral de checks (tools/dsguard/checks.py) con vocabulario PASS/WARN/FAIL/N-A y campo `kind` (check/technical_error), retrofit de `harmessi doctor` preservando el contrato público de `ResultadoCheck`/`ejecutar()`/`formatear()`
- Versión de artefactos referenciada: hashes sha256/lf/v1 registrados en `control.json` de este change (proposal.md, spec.md, design.md, tasks.md), aprobados 2026-09-14
- Cita o descripción fiel de qué se aprobó: "El diseño queda aprobado con un único ajuste antes de implementar. Agregar a CheckResult un campo mínimo y estable: kind. [...] Ejecutá autónomamente el Change 4 completo [...] Modo de ejecución desde ahora: BOUNDED AUTONOMY."

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
