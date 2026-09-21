# Propuesta — 20260918-report-evidence-and-validation

## Problema
Hasta el Change 2 un `Report` existe solo en memoria: el core (`tools/reporting/core.py`) define
contratos, `governance.py` decide destino/aislamiento/holdout, y `profiles/eda.py` valida la
declaración EDA. Falta lo que vuelve a un reporte auditable después de generarlo:
- No hay **procedencia persistida**: qué fuentes (con hash), qué commit, qué corte de datos, qué
  exclusiones, si se tocó un holdout, qué artefactos sensibles. El roadmap (`docs/roadmap/v0.6.md`,
  Change 3) lo exige como manifest.
- No hay **validación estructural de evidencia**: nada verifica que un gráfico tenga su tabla de
  respaldo, que un insight cite evidencia que exista, ni que las columnas de la figura estén en la
  tabla. Hoy son convenciones, no hechos verificados.
- No hay **puerta sobre un reporte ya escrito**: un directorio con `report.html` sin manifest, con
  un artefacto alterado o con una fuente que cambió después no dispara nada.
- El aislamiento de `governance.py` (`REPORT-ISOLATION-INPUT`, `governance.py:723-808`) mira rutas
  y manifests ancestros; copiar un artefacto exploratory a otra ruta lo evade.

## Objetivo
Persistir la evidencia de un reporte (manifest + artefactos con hashes de bytes) y validar de forma
determinista su coherencia estructural, sin crear una segunda fuente de verdad.

## Evidencia
- `tools/reporting/core.py:264` `canonical_json`; `:285` `TableArtifact`, `:428` `to_dict`, `:441`
  `from_dict`; `:466` `FigureSpec`, `:520` `columns_used`; `:569` `FigureArtifact`; `:652`
  `Insight`; `:746` `Chapter`; `:807` `Report`, `:879-884` `iter_tables`/`iter_figures`, `:915`
  `to_dict`, `:929` `from_dict`, `:960` `content_sha256`. Política de hash sobre bytes: docstring
  `core.py:17-24`.
- `tools/reporting/governance.py:244-264` `GovernanceContext`; `:191` `load_policy`; `:70`
  `REQUIRED_DESTINATION_CODES`; `:815` `check_flow_inputs`; `:949` `evaluate_governance`;
  `:53` `CODE_ISOLATION_INPUT`.
- `tools/ds_profile/fingerprint.py:15,18` `ALGORITMO = "sha256/bin/v1"`, `calcular_fingerprint`
  (devuelve `{"algoritmo", "hash"}`): ya es el hash de archivo del proyecto.
- `tools/dsguard/repo.py:46` `get_head`, `:53` `list_dirty_files`; `tools/dsguard/core.py:42`
  `ahora_utc`, `:88` `escribir_texto_atomico`.
- `docs/roadmap/v0.6.md:136-150` (Change 3, campos del manifest).

## Supuestos descartados
- "El hash del reporte alcanza como evidencia": `content_sha256` cubre el contenido lógico del
  `Report`, no los bytes persistidos ni las fuentes. Se usa como control adicional, no único.
- "Un directorio con `report.html` es un reporte": sin manifest no hay procedencia; es FAIL.
- "El aislamiento por ruta basta": una copia byte-idéntica de un artefacto exploratory en otra
  ruta lo evade; se agrega aislamiento por hash.

## Alcance
- `tools/reporting/evidence.py`: fuentes con hash, preparación de artefactos, manifest, escritura
  y carga del directorio de un reporte, índice de hashes exploratory y aislamiento por hash.
- `tools/reporting/validation.py`: `validate_report`, `validate_manifest`, `validate_report_dir`
  (puerta completa), todo `list[CheckResult]`, nunca lanza.
- `tools/reporting/cli.py`: subcomando `validate` y check aditivo `REPORT-ISOLATION-HASH` en
  `check-inputs` (solo lectura).
- Instalabilidad (`manifest.py`, `test_installability.py`), `ARCHITECTURE.md`, `MODULOS_CORE`.
- Tests: `test_evidence.py`, `test_validation.py`, `test_cli_validate.py`.

## Fuera de alcance
- Modificar `core.py`, `governance.py` o `profiles/eda.py` (R22 de `spec.md`).
- Renderizado HTML y design system (Change 4); `report.html` solo se reconoce, no se genera.
- Evaluar si una conclusión excede la evidencia, si la evidencia es adecuada o si una tabla es
  relevante para el insight: es juicio del Lead/metodólogo/reviewer.
- Firmas o autoría: los sha256 prueban integridad, no aprobación.
- Leer holdouts/datasets sellados, `data/raw` (más allá de hashear fuentes declaradas y permitidas
  por governance), `.claude/guardrails.json` o `.env*`.

## Holdout policy
No aplica: el Change no lee ni escribe holdouts. `holdout_access` del manifest solo registra lo
declarado por quien genera el reporte, y `governance.py` (Change 1) lo hace cumplir.

## Impacto en production-readiness
El manifest con commit, fuentes y hashes es el insumo natural de trazabilidad para una etapa de
deployment futura. Sin cambio de comportamiento hoy.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-18
- Alcance aprobado: Change 3 — report-evidence-and-validation (docs/roadmap/v0.6.md)
- Versión de artefactos referenciada: esta versión de proposal.md, spec.md, design.md, tasks.md
  (commit de este Change)
- Cita o descripción fiel de qué se aprobó: "Ejecutá autónomamente Harmessi v0.6 completa: ...
  Change 3 — report-evidence-and-validation ... Para cada Change: audit → SDD → implementación →
  tests → reviewer → fixes → re-tests → verification → close → commit local" (instrucción
  explícita del usuario, 2026-09-18, bajo el Contrato de autonomía de docs/roadmap/README.md).
