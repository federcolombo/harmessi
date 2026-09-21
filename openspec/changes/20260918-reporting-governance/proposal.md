# Propuesta — 20260918-reporting-governance

## Problema
El Reporting Core (Change 0) define QUÉ es un reporte (`Report`, `report_kind`, `decision_scope`,
artefactos con flag `sensitive`), pero nada impide todavía que un reporte se escriba en cualquier
lugar, lea cualquier fuente o mezcle niveles de validez. Concretamente, hoy no existe un guard
que responda de forma mecánica:

1. ¿Puede este reporte escribirse en ese directorio? (secretos, holdouts, `data/raw`,
   `guardrails.json`, `write_scopes`).
2. ¿Ese directorio corresponde al `decision_scope` declarado? Un output exploratorio escrito en
   la zona de `model_valid` (o al revés) es un vector de leakage: un notebook de modelado podría
   consumirlo como si fuera evidencia validada.
3. ¿Un reporte con artefactos sensibles está yendo a un destino habilitado para eso?
4. ¿Las fuentes declaradas son legibles y, si tocan un holdout, el acceso está declarado y
   autorizado por la policy científica?
5. ¿Un flujo `model_valid`/`operational` está consumiendo outputs exploratorios como input?
6. ¿El corte de datos del reporte respeta el cutoff temporal de la policy científica?

Las piezas de bajo nivel ya existen y están probadas (`pathguard`, `scientific_validity`,
`checks`); lo que falta es la capa de reporting que las compone con los contratos del Change 0,
sin duplicarlas.

## Objetivo
Crear `tools/reporting/governance.py` (más `cli.py` y `__main__.py`): un "output guard"
determinista, de solo lectura, que evalúa un `GovernanceContext` y devuelve `CheckResult`
(`PASS`/`WARN`/`FAIL`/`N/A`) reusando `dsguard` como único motor y vocabulario, de modo que el
Change 4 (`publish`) pueda negarse a escribir ante cualquier `FAIL`, y que cualquier flujo
pueda verificar mecánicamente que sus inputs no son outputs exploratorios.

## Evidencia
- `docs/roadmap/v0.6.md:82-98`: alcance del Change 1 (output guard, destinos permitidos,
  separación `exploratory` ↔ `model_valid`, protección de holdout, aislamiento read/write,
  outputs sensibles, integración con scientific validity); `:94-95` "No duplicar sistemas de
  holdout, hashes o provenance que Harmessi ya tenga"; `:97-98` "Debe poder impedir
  mecánicamente que outputs exploratorios alimenten modelado cuando no corresponda".
- `docs/roadmap/README.md:19` (principio "LLM decide lo semántico; el binario calcula y hace
  cumplir lo determinista") y `:21-42` (contrato de autonomía).
- `tools/reporting/core.py:45-46` (vocabularios `REPORT_KINDS`/`DECISION_SCOPES`), `:59-62`
  (nombres canónicos `report.html`/`manifest.json`/`insights.json`/`artifacts`), `:289` y `:574`
  (`sensitive` en `TableArtifact`/`FigureArtifact`), `:873-886` (`iter_tables`/`iter_figures`).
- `tools/dsguard/pathguard.py:436-456` (`evaluar_tool_call`, mismo evaluador del hook) y
  `:252-289` (secretos `:269`, holdouts `:272-277`, `data_raw` `:279`, `write_scopes`
  `:282-287`, `guardrails.json` protegido `:265`); `:166-191` (`resolver_ruta_relativa`, sigue
  symlinks, nunca lanza); `:111-160` (`cargar_config`, `ConfigGuardrailsError` fail-closed).
- `tools/dsguard/checks.py:14-22` (vocabulario `PASS`/`WARN`/`FAIL`/`N/A` y `kind`), `:25-55`
  (`CheckResult`), `:72-84` (`ejecutar_checks`: nunca frena, convierte excepciones en
  `technical_error`), `:94-99` (`hay_bloqueo`, `exit_code`).
- `tools/dsguard/scientific_validity.py:74-97` (`leer_policy`, solo lectura, ausente => forma
  vacía, corrupta => `ScientificPolicyError`), `:187-211` (`temporal.declared`, `cutoff_utc`),
  `:298`/`:368-371` (`holdout.declared`, `holdout.final_evaluation.authorized`), `:532-562`
  (orquestador; precedente de policy corrupta => FAIL `technical_error`).
- `tools/dsguard/repo.py:109-121`: `path_matches_any` usa `fnmatch`; `*` cruza `/`.
- `tools/ds_profile/holdout_guard.py:25-31`: patrón `sys.path.insert` + `from dsguard import ...`
  que este Change reusa; `:34-63`: réplicas privadas de `pathguard` que este Change NO repite.
- `tools/ds_profile/cli.py:4-8` y `:97-104`: patrón de CLI `argparse` con exit codes documentados;
  `tools/ds_profile/__main__.py:1-9`: patrón de `__main__`.
- `tools/tests/test_architecture_boundaries.py:32-81` (`MODULOS_CORE`, `:69` ya incluye
  `tools/reporting/core.py`), `:141-158` (ningún core importa un adapter), `:161-175` (ningún
  core contiene `sys.stdin`); `tools/tests/test_v06_core_neutrality.py:149-160` (`__init__.py`
  vacío), `:172-188` (ningún paquete previo importa `reporting`).
- `ARCHITECTURE.md:46` (fila de `tools/reporting/core.py`) y `:108-112` (regla 6: módulos
  posteriores de la familia pueden importar `dsguard`; nunca al revés).
- `tools/ds_init/manifest.py:543-553`: entradas VERBATIM de `tools/reporting/__init__.py` y
  `core.py`; entradas de `dsguard` sin `stage_minimo` (default `discovery`):
  `manifest.py:229-236` (`core.py`, `repo.py`), `:274-278` (`checks.py`), `:314-318`
  (`scientific_validity.py`), `:342-346` (`pathguard.py`).
- `.claude/guardrails.json:3-4`: el repo declara `holdouts: []` y `data_raw` por defecto (los
  tests deben construir repos temporales propios con holdouts sintéticos).

## Supuestos descartados
- Que governance necesite su propio motor de checks o su propio vocabulario de resultados.
  Descartado: `dsguard.checks.CheckResult` ya es el vocabulario canónico y `ejecutar_checks` ya
  garantiza "nunca lanza".
- Que baste replicar el matching de `pathguard` (como hacen `holdout_guard.py:34-63` y
  `scientific_validity.py:110-139`). Descartado: el guard llama a `pathguard.evaluar_tool_call`
  (el MISMO evaluador que el hook) y así hereda secretos, holdouts, `data_raw`,
  `guardrails.json` y `write_scopes` sin reimplementarlos.
- Que el scope de un reporte pueda inferirse del directorio o del nombre. Descartado: sin
  heurística; el scope viene del `Report` (o de `--scope`) y el destino se valida contra él.
- Que el aislamiento exploratory ↔ model_valid pueda cerrarse con hashes de contenido en este
  Change. Descartado: los hashes de artefactos viven en el manifest del Change 3; se difiere allí
  (ver `design.md`).

## Hipótesis (condicional — solo cambios metodológicos)
No aplica.

## Alcance
- `tools/reporting/governance.py`: `ReportingPolicy`/`ReportingPolicyError`/`load_policy`/
  `resolve_output_dir`, `GovernanceContext`/`context_from_report`, los 10 códigos de check
  `REPORT-*`, `check_flow_inputs`, `evaluate_destination`, `evaluate_governance`,
  `output_allowed`.
- `tools/reporting/cli.py` y `tools/reporting/__main__.py`: `python -m tools.reporting` con los
  subcomandos `check-inputs` y `check-destination`.
- `tools/reporting/tests/test_governance.py` y `tools/reporting/tests/test_cli.py`.
- `tools/ds_init/manifest.py`: tres entradas VERBATIM nuevas (`governance.py`, `cli.py`,
  `__main__.py`), `stage_minimo` por defecto (`discovery`), tras las de `core.py`.
- `tools/tests/test_architecture_boundaries.py`: agregar `governance.py` y `cli.py` a
  `MODULOS_CORE`. `ARCHITECTURE.md` §2.1: filas para ambos.
- `docs/roadmap/v0.6.md`: tildar `[x] Change 1` en el cierre.
- `openspec/changes/20260918-reporting-governance/verification.md` (al cierre).

## Fuera de alcance
- Manifest de reporte, provenance, hashes de fuentes/artefactos (incluido el chequeo por hash de
  contenido contra artefactos exploratorios), validación determinista de evidencia y
  `insights.json`/`manifest.json`: Change 3.
- Profile EDA: Change 2. Renderer HTML, `publish`, subcomandos `validate`/`render`: Changes 3-4.
- Observación de lecturas en runtime de un notebook (lo cubren los hooks de `pathguard` para
  agentes y `nbrunner` fsdiff) y parseo confiable de shell (`Bash`/`PowerShell` siguen
  best-effort, `pathguard.py:8-14`).
- Cualquier modificación de `dsguard`, `pathguard`, `scientific_validity`, `ds_profile`,
  `.claude/guardrails.json`, `tools/reporting/core.py` o `tools/reporting/__init__.py`.
- Leer el contenido de cualquier holdout o dataset sellado.

## Holdout policy (condicional — solo cambios "sensible")
No se accede a ningún holdout ni dataset sellado. El guard solo EVALÚA rutas (nunca abre el
contenido de una fuente ni de un holdout) y lee únicamente `.claude/guardrails.json`,
`.harmessi/scientific-policy.json`, `.harmessi/reporting-policy.json` y `manifest.json` de
directorios ancestros de un input (excluyendo cualquier ruta que `pathguard` deniegue leer). Los
tests usan repos temporales con patrones de holdout sintéticos. `.claude/guardrails.json` no se
modifica.

## Impacto en production-readiness (opcional)
No aplica en este bloque.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md` (SDD completo).

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md` (SDD completo).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-18
- Alcance aprobado: Change 1 — reporting-governance (docs/roadmap/v0.6.md)
- Versión de artefactos referenciada: esta versión de `proposal.md`, `spec.md`, `design.md`,
  `tasks.md` (commit de este Change)
- Cita o descripción fiel de qué se aprobó: "Ejecutá autónomamente Harmessi v0.6 completa: ...
  Change 1 — reporting-governance ... Para cada Change: audit → SDD → implementación → tests →
  reviewer → fixes → re-tests → verification → close → commit local" (instrucción explícita del
  usuario, 2026-09-18, bajo el Contrato de autonomía de `docs/roadmap/README.md`).

## Motivo de rechazo
No aplica (estado: no descartada).

## Desacuerdo registrado
No aplica.
