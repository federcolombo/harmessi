# Propuesta — 20260916-v0-3-release-hardening

## Problema
Changes 0-9 completaron el roadmap metodológico/operativo de Harmessi v0.3 (lifecycle CRISP-DM/
KDD/MLOps, project maturity, checks engine, foundations, readiness/promotion, instalación
progresiva, status unificado, Lead methodology-aware), pero el repo todavía no está endurecido
para publicarse como release: la versión canónica sigue en `0.2.0`, el `README.md` describe el
modelo v0.2 (KDD legacy como único lifecycle, sin `ds_guard.py`/CRISP-DM/`project_stage`/
`readiness`/`status`), no existe un texto de release notes, no hay un registro explícito de
deuda/limitaciones conocidas para v0.4+, y una auditoría de privacidad encontró una fuga real de
un nombre de ruta/organización privada en 2 artefactos SDD ya cerrados.

## Objetivo
Endurecer el repo para el release v0.3.0: corregir el drift de versión (fuente canónica única),
auditar transversalmente Changes 0-9 buscando inconsistencias reales (no cosméticas), correr
regresión completa + validación E2E (scratch installs, progressive sync, readiness/promotion,
evidence, status, compatibilidad legacy), confirmar 0 escritura oculta en operaciones read-only,
limpiar cualquier filtración de contexto privado, actualizar README/release notes/known
limitations al mínimo necesario para que v0.3 no se publique materialmente desactualizado, y
regenerar `.ds_init/control.json` una sola vez al final — sin agregar ninguna feature nueva ni
tocar ningún engine/gate/schema salvo bug real demostrado.

## Evidencia
- **Drift de versión confirmado**: `tools/ds_init/version.py:13` (`HARNESS_VERSION = "0.2.0"`,
  fuente canónica — usada por `control.py`/`writer.py`/`templating.py` para
  `.ds_init/control.json["harness_version"]` y el bloque delimitado de `CLAUDE.md`) y
  `CITATION.cff:5` (`version: 0.2.0`) — ambos desactualizados frente al roadmap v0.3 completo.
  Confirmado por grep exhaustivo que el resto de las ~30 apariciones de "0.2.0" en el repo son
  anotaciones históricas legítimas ("Bloque N, reliability v0.2.0" — cuándo se introdujo un
  mecanismo, no la versión actual) que NO deben tocarse.
- **BLOCKER de privacidad encontrado y corregido durante este mismo audit**: `openspec/changes/
  20260914-fix-harness-version-drift/tasks.md` (2 ocurrencias) y `openspec/changes/
  20260915-checks-engine-foundation/spec.md` (1 ocurrencia) contenían una ruta local absoluta de
  usuario que incluía lo que aparentaba ser un nombre de organización privada — coincidiendo
  exactamente con el patrón que el usuario pidió buscar explícitamente (valor real no reproducido
  aquí a propósito, para no reintroducir la misma fuga al documentar su corrección). Redactado a
  "este mismo repo (checkout local de Harmessi)" en ambos artefactos — confirmado con grep
  exhaustivo, repetido de forma independiente por el reviewer de este change, que no queda ninguna
  otra ocurrencia en el repo (`.py`/`.md`/`.json`/`.cff`, working tree completo).
- **`README.md` materialmente desactualizado**: describe KDD como "a separate, persisted state...
  Problem Understanding → ... → Monitoring" (modelo v0.2 pre-Change-1); la sección "Commands" solo
  documenta `doctor`/`ds_profile`/`ds_init` — el CLI más usado del proyecto (`ds_guard.py`:
  SDD, `project`, `lifecycle`, `mlops`, `status`) no aparece mencionado en absoluto. Sin mención de
  `project_stage`/`installation_stage`/`risk_level`/CRISP-DM/MLOps/`readiness`/`promote`/
  progressive sync/`methodology.md`.
- **Sin `CHANGELOG`**: confirmado que no existe ningún archivo `CHANGELOG*` en la raíz del repo —
  no se crea un framework nuevo (brief §18), se prepara únicamente el texto de release notes de
  v0.3.0 como artefacto de este change (`verification.md`), sin publicarlo como release real.
- `.ds_init/control.json` (self-hosted, este repo): `harness_version: "0.2.0"`, `archivos[]` con
  51 entradas — ninguna de `checks.py`/`maturity.py`/`lifecycle.py`/`kdd_compat.py`/
  `mlops_foundations.py`/`readiness.py`/`mlops_evidence.py`/`status.py`/
  `production-readiness.md`/`operations.md`/`decision-ledger.md`/`methodology.md` (todas VERBATIM/
  PLANTILLA en `MANIFEST` desde Changes 1-9) — confirma que este archivo quedó desactualizado
  desde antes de esta sesión y debe regenerarse una sola vez, al final (brief §4), vía
  `control.regenerar_control` (mecanismo oficial ya existente desde Change 0, sin reimplementarlo).
- Import-smoke-test directo (`from dsguard import ...`, `from ds_init import ...`, `from harmessi
  import doctor`) confirma que no hay imports faltantes/rotos en ningún módulo de Changes 1-9.
- Roadmap v0.3 aprobado (Change 10, cierre del roadmap); Changes 0-9 cerrados, ninguno reabierto
  salvo la corrección puntual de privacidad ya aplicada (justificada explícitamente como BLOCKER
  de release, por encima del costo de invalidar el hash-pin de aprobación de esos 2 artefactos ya
  cerrados — documentado aquí de forma transparente en vez de ocultarlo).

## Supuestos descartados
No se agrega ninguna feature nueva (cutoff/baseline enforcement, dsimpact, scope isolation,
portable core, eval framework, reporting, data contracts nuevos, provider abstraction, token
telemetry, Responsible AI, deployment/CI-CD/monitoring reales, nuevos stages, nuevos gates,
schema nuevo de lifecycle). No se crea un framework de CHANGELOG nuevo. No se rediseña ningún
componente de Changes 0-9 sin un bug real demostrado. No se hace tag/push/GitHub Release — el
commit final del hardening también queda pendiente de aprobación humana.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica — cambio de hardening/release del harness, no de datos de un proyecto DS.

## Alcance
1. **Versión**: `tools/ds_init/version.py` (`HARNESS_VERSION = "0.3.0"`), `CITATION.cff`
   (`version: 0.3.0`, `date-released` actualizado). Ninguna otra fuente de versión nueva.
2. **README.md**: actualización mínima necesaria — capabilities reales de Changes 1-9
   (`project_stage`/`installation_stage`/CRISP-DM+KDD+MLOps+SDD/`readiness`/`promote`/
   progressive sync/`status` unificado), `ds_guard.py` agregado a "Commands", sin reescribir todo
   el documento ni inflar su tamaño.
3. **Release notes v0.3.0** (texto en `verification.md` de este change, no un archivo publicado):
   resumen de Changes 0-9, backward compatibility relevante, limitaciones conocidas.
4. **Known limitations** (documentadas en `verification.md`, deuda explícita para v0.4+): revisar
   si las limitaciones listadas por el usuario siguen aplicando (runtime completo en discovery por
   imports/hooks globales; lineage sin engine completo; evidence valida integridad no calidad
   semántica; sin tooling real de deployment/monitoring; sin multi-provider; sin cutoff/baseline
   enforceable) y documentarlas tal cual, sin arreglarlas.
5. **Roadmap post-v0.3** (documentado en `verification.md`, sin abrir ningún change nuevo): v0.4
   candidatos (KDD enforceable checks, cutoff/baseline, Impact Preflight/dsimpact, Scope & Change
   Isolation, Portable Core, Agent Efficiency/Token Governance), v0.5+ candidatos (evals/
   harmessi-bench, reporting, Data Contracts avanzados, multi-provider).
6. **Fixes de auditoría transversal**: solo los ya demostrados (privacidad, versión); cualquier
   otro hallazgo real que surja durante la validación E2E de este change, dentro del mismo
   criterio (BLOCKER/IMPORTANT arreglado ahora, MINOR/DEBT documentado para v0.4).
7. **Validación E2E completa** (ejecutada por el Lead, sin subagente — ver `tasks.md`): regresión
   completa de las 4 suites, scratch installs discovery/experiment, progressive sync E2E,
   readiness/promotion smoke, evidence smoke, status smoke, compatibilidad legacy/v0.2, auditoría
   read-only, `harmessi doctor` final.
8. **`.ds_init/control.json` regenerado una sola vez, al final**, vía `control.regenerar_control`
   (mecanismo oficial, sin reimplementar), después de que todos los demás cambios de este change
   ya estén aplicados.

## Fuera de alcance
Toda la lista de §23 del brief del usuario (cutoff/baseline enforcement, dsimpact, scope
isolation, portable core, eval framework, reporting, data contracts nuevos, provider abstraction,
token telemetry, Responsible AI, deployment/CI-CD/monitoring reales, nuevos stages, nuevos gates
de maturity, nuevo schema lifecycle). Tag, push, GitHub Release, commit final sin aprobación
humana. Ningún Change nuevo abierto para deuda de v0.4+ (solo se registra conceptualmente).

## Holdout policy (condicional — solo cambios "sensible")
No aplica.

## Impacto en production-readiness (opcional)
No aplica — este change es sobre el propio harness Harmessi, no sobre un proyecto DS instalado.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md`.

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md`.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-16
- Alcance aprobado: "v0.3-release-hardening — endurecer, validar y dejar READY para release
  v0.3.0: audit final transversal, fixes solo si son blockers reales, regresión completa, scratch
  validation, reviewer, verification, cierre — sin expandir scope, sin tag/push/release"
- Versión de artefactos referenciada: hashes a registrar en `control.json` de este change
- Cita o descripción fiel de qué se aprobó: brief íntegro del usuario para Change 10 ("Este change
  es SOLO hardening de release... Si aparece una mejora deseable pero no bloqueante: registrarla
  como deuda para v0.4, NO implementarla ahora.").

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
