# Propuesta — 20261001-v08-release-hardening

## Problema

Changes 0-4 de v0.8 implementaron, por separado, cada decisión material (M1-M12) y cada capacidad
opt-in (`approval_mode: checkpoints`, project capabilities, fuentes externas read-only, config
layering, dependency install gobernado, integridad detectiva, adopción de proyecto existente). Cada
Change verificó SU propia pieza de forma aislada (tests unitarios/de integración, mockeados o contra
fixtures sintéticos puntuales) — pero **ningún Change verificó todavía que todas estas piezas
funcionan JUNTAS, de punta a punta, en un proyecto real instalado desde cero**, con el Lead
completando trabajo real sin que un humano ejecute comandos intermedios (la métrica funcional clave
que el propio roadmap fija como gate principal de este Change).

**Auditoría explícita** (evidencia, no suposición):

- `tools/ds_init/tests/test_integracion_instalacion.py` ya verifica que una instalación scratch
  produce los archivos correctos, pero NO ejercita ningún flujo de trabajo del Lead sobre ese
  proyecto (solo confirma la instalación en sí, no su uso).
- Ningún test existente en `tools/leadrun/tests/`, `tools/tests/`, ni `tools/ds_init/tests/`
  combina MÁS DE UNA capacidad de M7-M12/B5 en un mismo escenario end-to-end (cada suite de Change
  4 testea su propia pieza aislada, con mocks).
- El roadmap (`docs/roadmap/v0.8.md`, sección "Change 5 — v0.8-release-hardening", Casos A-I) ya
  define en detalle QUÉ debe demostrarse, pero no existe todavía ningún `proposal.md`/`spec.md`/
  `design.md` que lo traduzca a un plan de verificación concreto y aprobable.
- `docs/roadmap/v0.10.md` (adenda 2026-10-01) registra `domain-modeling` como capacidad futura
  prioritaria; el roadmap de v0.8 (Caso I, misma adenda) pide que este Change confirme SOLO
  compatibilidad arquitectónica (un artefacto de contexto de dominio no administrado no debe romper
  nada ya construido) — explícitamente SIN implementar ninguna skill nueva.

## Objetivo

Verificar, de punta a punta y sin implementar ninguna feature nueva, que Harmessi v0.8 (Changes
0-4) funciona como un sistema coherente en escenarios realistas combinados — autonomía real con
cero ejecuciones humanas intermedias, capabilities, fuentes read-only, integridad, config
layering, adopción, dependency install gobernado, budgets/checkpoints, métricas de eficiencia,
compatibilidad con domain context del proyecto, y backward compatibility total — y producir el
veredicto formal `READY FOR v0.8.0 RELEASE` o `NOT READY FOR v0.8.0 RELEASE` que el roadmap exige
como resultado final de este Change.

## Evidencia

- `docs/roadmap/v0.8.md`, sección "Change 5 — v0.8-release-hardening" (Casos A-I, "Regresión por
  default", "Métricas de eficiencia", "Resultado final: READY/NOT READY").
- `docs/roadmap/v0.8.md`, blockquote superior, "Adenda 2026-10-01" (Caso I, domain context,
  compatibilidad únicamente).
- `docs/roadmap/v0.10.md`, "Composable Engineering & Data Science Skills" (contexto de por qué
  existe el Caso I, sin que este Change implemente nada de esa sección).
- `openspec/changes/20260930-project-extension-and-installer-integration/verification.md` (Change
  4, cerrado): confirma qué quedó verificado a nivel unitario/integración por cada pieza M8-M12/B5,
  base para identificar qué falta a nivel end-to-end.
- `tools/ds_init/tests/test_integracion_instalacion.py` (instalación scratch, sin flujo de Lead).
- Changes 0-3 (`20260928-source-neutral-data-access`, `20260929-lead-execution-runtime`,
  `20260930-autonomous-sdd-and-remediation`), cerrados: `tools/leadrun/`, `tools/autonomy/`,
  `tools/dsguard/sdd.py` como runtime/policy/SDD ya estables, base de todos los escenarios de este
  Change — no se reabren.

## Supuestos descartados

- Que este Change necesita una nueva skill de `domain-modeling` para cumplir el Caso I: el roadmap
  (adenda 2026-10-01) fija explícitamente que es "SOLO compatibilidad arquitectónica" — un artefacto
  de contexto de dominio no administrado (`GLOSSARY.md` sintético o equivalente) simplemente no debe
  romper nada ya construido. Ninguna skill, manager, ni mecanismo de lectura/parseo formal se
  implementa en v0.8.
- Que SQLite necesita validarse "como producto" (Caso D del roadmap/G de este `proposal.md`): se
  usa únicamente para demostrar que el contrato de adapter de `tools/datasources` sirve una fuente
  NO orientada a archivos, con un adapter mínimo escrito en el fixture del proyecto — nunca una
  evaluación de SQLite en sí.
- Que la verificación de dependency pre-approval (Caso G) requiere red real: el roadmap original de
  Change 3/4 y la instrucción del autor para este Change fijan explícitamente preferir tests
  deterministas/locales — no se hace depender el release de la disponibilidad de un índice PyPI
  público.

## Alcance

**Solo SDD en este Change** (proposal → spec → design → tasks, sin implementación): el plan de
verificación completo para los 11 casos A-K (ver `spec.md`), incluyendo para cada uno:
- qué fixture/proyecto scratch lo ejercita;
- si se verifica con un test automatizado (pytest) o con una demostración en vivo conducida por el
  Lead (algunos escenarios de "autonomía real de punta a punta" no son simulables por un test
  unitario sin mockear la esencia misma de lo que se quiere demostrar);
- qué evidencia queda persistida como artefacto del cierre de este Change.

Cuando este SDD se apruebe, la IMPLEMENTACIÓN (ejecución real de los escenarios, fixtures scratch,
el veredicto final) es una fase posterior de este mismo Change, no un Change nuevo.

## Fuera de alcance

- Cualquier feature nueva de Harmessi (nada de M1-M12 se reabre ni se extiende).
- La skill `domain-modeling` y cualquier otra de "Composable Engineering & Data Science Skills"
  (`v0.10.md`) — ninguna se implementa en v0.8.
- Thresholds de performance arbitrarios sobre las métricas de eficiencia (Caso I de este
  `proposal.md`) — solo se reportan, nunca se convierten en gate numérico.
- SQLite como producto evaluado, o cualquier conector/adapter nuevo más allá del mínimo necesario
  para demostrar el contrato (Caso D).
- Reapertura de Changes 0-4 (sus artefactos aprobados por hash quedan intocados).
- Push, tag, o release real — el resultado `READY FOR v0.8.0 RELEASE` es un veredicto documentado,
  no una acción de publicación.

## Holdout policy (condicional)

N/A — este Change no toca datos ni holdouts reales; todos los fixtures son sintéticos y genéricos.

## Criterios de aceptación (spec-lite)

Ver `spec.md`.

## Decisión técnica (design-lite)

Ver `design.md`.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
