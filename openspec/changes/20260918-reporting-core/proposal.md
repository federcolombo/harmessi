# Propuesta — 20260918-reporting-core

## Problema
Harmessi v0.6 (Governed Reporting) necesita gobernar, validar, registrar y renderizar reportes
de análisis, pero hoy no existe ningún contrato común de "qué es un reporte": ni un objeto
`Report`, ni capítulos, ni tablas/figuras/insights como artefactos con identidad. Sin ese
contrato, los Changes posteriores de v0.6 (governance, EDA profile, evidence/validation,
renderer) no tendrían un objeto neutral sobre el cual operar, y cada uno tendería a inventar su
propia forma de datos, acoplándose a un dominio, a un profile (EDA) o a una librería gráfica.

Además, dos dimensiones distintas suelen confundirse en un mismo campo: qué tipo de reporte es
(`report_kind`) y para qué decisiones puede usarse (`decision_scope`). Si el contrato base las
fusiona, la separación `exploratory` ↔ `model_valid` que gobierna el Change 1 no tiene dónde
anclarse.

## Objetivo
Crear `tools/reporting/core.py`, un módulo neutral y solo-stdlib con los contratos `Report`,
`Chapter`, `FigureArtifact`, `TableArtifact` e `Insight` (más `FigureSpec`), con la separación
ortogonal `report_kind` × `decision_scope`, validación estructural estricta en construcción y
serialización determinista, sin conocer EDA, Plotly, HTML ni ningún dominio.

## Evidencia
- `docs/roadmap/v0.6.md:53-59`: los contratos a definir son `Report`, `Chapter`,
  `FigureArtifact`, `TableArtifact`, `Insight`.
- `docs/roadmap/v0.6.md:61-72`: `report_kind` (`eda`/`model`/`evaluation`/`production`) y
  `decision_scope` (`exploratory`/`model_valid`/`operational`) son "dos dimensiones ortogonales,
  que no deben confundirse entre sí".
- `docs/roadmap/v0.6.md:74-78`: el notebook calcula, Harmessi gobierna/valida/registra/renderiza;
  `.ipynb` es el artefacto reproducible y `.html` el de comunicación.
- `docs/roadmap/v0.6.md:130-132`: no hardcodear técnicas específicas (PCA, clustering, etc.) en
  el core; `:211-213`: Plotly no forma parte del contrato central, `FigureArtifact` debe
  permanecer neutral.
- `docs/roadmap/v0.6.md:170-187`: "ningún gráfico sin su tabla de respaldo" debe ser regla
  verificable (Change 3); `Insight` separa `technical_claim`, `business_claim`, `evidence_refs`,
  `population`, `time_scope`, `claim_type`, `uncertainty`.
- `ARCHITECTURE.md:25-46` (§2.1, inventario de core) y `ARCHITECTURE.md:90-109` (§3, reglas de
  dependencia): hoy no hay fila ni regla para un paquete de reporting; la regla 5
  (`ARCHITECTURE.md:100-106`) cubre solo los paquetes de v0.5.
- `tools/tests/test_architecture_boundaries.py:32-80`: `MODULOS_CORE` es la lista que refleja
  `ARCHITECTURE.md` §2.1 y `:160-174` verifica que ningún core lea stdin.
- `tools/tests/test_v05_core_neutrality.py:24-29` y `:52-68`: patrón `ast` de neutralidad
  (`CORE_FILES`, `_imports_nivel_modulo`) que este Change replica para v0.6.
- `tools/ds_init/manifest.py:70-107`: `EntradaManifiesto` con `stage_minimo` por defecto
  `"discovery"`; `:126-585` (`MANIFEST`) no contiene entradas de `tools/providers`,
  `tools/routing` ni ningún paquete de reporting; `:659-678`: los bundles son acumulativos.
- `tools/ds_init/tests/test_manifest.py:37-39` (destinos sin overlap), `:57-63` (ningún destino
  dentro de `EXCLUSIONES_PERMANENTES`), `:176-187` (bundles estrictamente monotónicos): deben
  seguir verdes tras agregar entradas de manifest.
- `tools/ds_init/check_manifest_parity.py:21-32`: verifica que toda fuente VERBATIM exista.
- `tools/dsguard/checks.py:14-18`: vocabulario `PASS`/`WARN`/`FAIL`/`N-A` que el Change 3
  reusará para validar reportes (este Change no lo importa).

## Supuestos descartados
- Que el core deba validar completitud semántica/evidencial (figura sin tabla de respaldo,
  insight sin evidencia) al construir el objeto. Descartado: lo hace la validación determinista
  del Change 3, que devuelve `FAIL`/`WARN`; así un notebook puede construir el objeto y recibir
  un resultado de validación en vez de una excepción a mitad de un análisis.
- Que `FigureArtifact` deba llevar una figura de un backend gráfico embebida. Descartado: acopla
  el core al backend (ver `design.md`); la especificación declarativa (`FigureSpec`) es neutral y
  el backend concreto es un escape hatch opaco.
- Que `report_kind` restrinja `decision_scope` (p. ej. "un `eda` solo puede ser `exploratory`").
  Descartado en el core: cualquier restricción entre ambos es política de governance (Change 1).

## Hipótesis (condicional — solo cambios metodológicos)
No aplica.

## Alcance
- `tools/reporting/__init__.py` y `tools/reporting/core.py` (solo stdlib): vocabularios,
  `ReportingContractError`, `TableArtifact`, `FigureSpec`, `FigureArtifact`, `Insight`,
  `Chapter`, `Report`, `canonical_json`, `Report.content_sha256()`.
- `tools/reporting/tests/__init__.py`, `test_core.py`, `test_installability.py`.
- `tools/tests/test_v06_core_neutrality.py` (nuevo) y agregar `tools/reporting/core.py` a
  `MODULOS_CORE` en `tools/tests/test_architecture_boundaries.py`.
- `tools/ds_init/manifest.py`: dos entradas VERBATIM (`tools/reporting/__init__.py`,
  `tools/reporting/core.py`) con `stage_minimo` por defecto (`discovery`).
- `ARCHITECTURE.md`: fila nueva en §2.1 y regla 6 en §3.
- `docs/roadmap/v0.6.md`: estado real "EN CURSO en `v0.6-dev`" y, al cerrar, tildar Change 0.
- `openspec/changes/20260918-reporting-core/verification.md` (al cierre).

## Fuera de alcance
- Governance (output guard, destinos permitidos, holdout, sensibles): Change 1.
- Profile EDA y su anatomía: Change 2.
- Manifest de reporte, provenance, hashes de fuentes, validación determinista
  (`FAIL`/`WARN`) y `insights.json`/`manifest.json`: Change 3.
- Renderer HTML, Plotly, design system, tema y estilo editorial: Change 4.
- CLI de reporting, escritura de archivos a disco, `report.html`: Changes 3–4.
- Cualquier cambio de comportamiento en `dsguard`, `ds_profile`, `dsimpact`, `providers`,
  `routing`, `fallback`, `harmessi_bench` o `tools/harmessi/*`.

## Holdout policy (condicional — solo cambios "sensible")
No aplica: el Change es un contrato de datos en memoria; no lee ni escribe ningún dataset ni
holdout, y no tiene ejecución de datos.

## Impacto en production-readiness (opcional)
No aplica en este bloque.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md` (SDD completo).

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md` (SDD completo).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-18
- Alcance aprobado: Change 0 — reporting-core (docs/roadmap/v0.6.md)
- Versión de artefactos referenciada: esta versión de `proposal.md`, `spec.md`, `design.md`,
  `tasks.md` (commit de este Change)
- Cita o descripción fiel de qué se aprobó: "Ejecutá autónomamente Harmessi v0.6 completa:
  Change 0 — reporting-core ... Para cada Change: audit → SDD → implementación → tests →
  reviewer → fixes → re-tests → verification → close → commit local" (instrucción explícita
  del usuario, 2026-09-18, bajo el Contrato de autonomía de `docs/roadmap/README.md`).

## Motivo de rechazo
No aplica (estado: no descartada).

## Desacuerdo registrado
No aplica.
