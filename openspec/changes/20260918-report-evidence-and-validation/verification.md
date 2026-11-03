# Verificación — 20260918-report-evidence-and-validation

## Evidencia obtenida

- **Tests del Change** (`pytest tools/reporting/tests tools/tests/test_v06_core_neutrality.py tools/tests/test_architecture_boundaries.py tools/tests/test_v05_core_neutrality.py tools/tests/test_manifest_dsguard_parity.py tools/ds_init/tests/test_manifest.py`):
  - 1ª corrida (tandas A/B/C, antes de la revisión): `576 passed`, 1 skipped, 523 subtests, en `32.53s`.
  - Tras los fixes del ciclo 1 (evidence, luego validation y CLI): `635 passed`, 2 skipped, 531 subtests, en `43.70s`.
  - Tras los fixes finales N1/N2: `638 passed`, 2 skipped, 531 subtests, en `44.96s`.
  - Los 2 skips: `test_evidence.py:253` y `:858`, "el SO no permite symlinks de archivo" (las junctions de directorio sí se ejercitan).
- **Paridad de manifest** (`check_manifest_parity`): `[OK]`.
- **Suites lentas que consumen `MANIFEST`** (`tools/ds_init/tests/test_control_file.py` + `tools/harmessi/tests/test_doctor.py`): `94 passed` en `384.70s`, corridas con las 2 entradas de manifest del Change; los fixes posteriores no tocaron `manifest.py`.
- **Smoke E2E real** (repo temporal, ejemplo genérico):
  - Persistir con evidence y correr `python -m tools.reporting validate --dir ...`: 0 FAIL, exit 0 (WARN de proveniencia por repo temporal sin git).
  - Alterar un byte de una tabla: FAIL `REPORT-ARTIFACT-HASH`, exit 1.
  - Manifest byte-idéntico entre dos corridas con reloj y `run_id` fijos: `True`.
  - `check-inputs --flow-scope model_valid --input data` con un holdout declarado dentro de `data/`: FAIL `REPORT-ISOLATION-HASH` "no verificable: acceso denegado (no se abrió)", sin abrir el holdout.
- **Reviewer** (`data-science-reviewer`, 2 pasadas):
  - 1ª pasada, NO APRUEBA por un BLOQUEANTE: el binario abría y hasheaba fuentes e inputs ANTES de que governance evaluara acceso (lectura de bytes de posibles holdouts/secretos; violaba el invariante del proyecto).
  - 3 importantes: lectura de artefactos sin contención de symlinks/junctions; integridad por bytes no exigida al conjunto completo (`artifacts: []` pasaba); "fail-closed" del aislamiento por hash con huecos (`os.walk` sin `onerror`, manifests exploratory ilegibles ignorados en silencio, techo de escala por contar subdirectorios de reportes).
  - Menores: API privada usada por la CLI, test tautológico de imports, fuga de rutas locales en mensajes, `source_notebook` sin normalizar.
  - Fixes en 3 tandas: `read_allowed` (mismo evaluador `pathguard` que el hook) antes de TODA apertura; `read_within` (contención con `resolve()`, rechazo de symlinks/junctions, `\x00`, nombres reservados) y single-read (`read_report_dir` + `report_from_bytes`: los mismos bytes se hashean y arman el Report, sin TOCTOU entre lecturas); `REPORT-ARTIFACT-SET` (conjunto exacto derivado del Report); `ExploratoryIndex`/`exploratory_index_status` públicos con `onerror`, WARN por manifests ilegibles y sin descender bajo un reporte; `REPORT-SOURCE-UNVERIFIABLE`; mensajes sin rutas absolutas.
  - 2ª pasada (acotada): APRUEBA CON FIXES. Bloqueante RESUELTO en todos los caminos con apertura de datos (verificado por lectura, con archivo:línea) y sin regresiones. Un hallazgo importante-menor (N1: `load_report_dir` sin `repo_root` opcional, docstring que sobreafirmaba) y N2 (`_no_listados` fail-open ante error de listado) corregidos; N3–N5 documentados como límites.
- **Sweep de privacidad**: grep de nombres, rutas y emails privados en `tools/reporting`, este Change y `ARCHITECTURE.md` → 0 resultados.
- **Alcance / backward compat**: `git diff` de `core.py`, `governance.py` y `profiles/eda.py` vacío. `cli.py` cambió solo aditivamente: `validate`, y el check por hash en `check-inputs` solo cuando hay índice exploratory. Sin línea `REPORT-ISOLATION-HASH` significa "no había manifests exploratory indexados", no "no corrió" (interpretación de la spec R19 que consta aquí).

## Fingerprint de dataset/artefacto

No aplica -- infraestructura del harness con datos sintéticos, sin dataset real.

## Diferencias contra la spec

- Enmiendas de los ciclos (R0/R3/R9/R10/R11/R16/R24, D6 y Leakage risks de `design.md`), re-aprobadas por hash.
- La spec original ordenaba verificar fuentes antes de governance leyendo bytes; corregido con acceso-antes-de-abrir.

## Limitaciones

1. sha256 del manifest AUTOATESTADOS: un manifest reescrito de forma consistente no se detecta; el ancla externa (`control.json`/commit) es tarea del hardening.
2. La hash-isolation cubre copias byte-idénticas, no derivados.
3. El binario no evalúa si una conclusión excede la evidencia ni si la tabla referenciada es pertinente.
4. N3: `.ds_init/control.json` se lee sin `read_allowed` (config del harness, no datos).
5. N4: con `out_dir` fuera del repo, la ruta pasada por el usuario puede aparecer como `subject`.
6. N5: nombres de archivos dentro de un holdout pueden aparecer como `subject` de un FAIL; no se lee contenido.
7. `read_allowed` recarga `guardrails.json` en cada llamada (costo, no correctitud).
8. El reviewer no pudo ejecutar nada: sus conclusiones son por lectura; la ejecución la aporta esta verificación.

## Pendientes derivados

Para el Change 4 (`publish`):
- Usar el camino con `repo_root` (`read_report_dir(..., repo_root=)` / `load_report_dir(..., repo_root=)`).
- Exigir cero FAIL de `validate_report_dir` y `require_codes` (`governance.REQUIRED_DESTINATION_CODES` + `REPORT-MANIFEST-*` + `REPORT-ARTIFACT-HASH` presentes; un `[]` no es OK).
- Renderizar desde el Report verificado en memoria y escribir `report.html` de forma atómica.
- Decidir si `report.html` entra al manifest con hash (hoy `ARTIFACT_KINDS` no lo prevé).
- Reevaluar el destino justo antes de escribir (TOCTOU).
- Valorar un WARN de `SCI-CUTOFF` cuando no hay policy científica en scopes `model_valid`/`operational`.

Hardening:
- `.gitattributes` con `-text` para `reports/**` (git `core.autocrlf` puede alterar bytes y disparar `REPORT-ARTIFACT-HASH`/`SOURCE-STALE` en otra máquina).
- Ancla externa del hash del manifest.
- Manifest parity.

## Resultado final

CERRADO — Change 3 cumple la spec (R0–R24 enmendada).
