# Diseño — 20260918-reporting-governance

## Decisión metodológica/técnica
Principio permanente: "LLM decide lo semántico; el binario calcula y hace cumplir lo
determinista". Flujo de v0.6: Proyecto/Notebook → Report objects → **Governance** →
Evidence/Validation → Design System → Renderer → `report.html` + `manifest.json` +
`insights.json` + `artifacts/`. Este Change implementa únicamente el eslabón "Governance": un
output guard declarativo, de solo lectura, que compone piezas ya existentes de `dsguard` con los
contratos del Change 0 y no agrega motores, vocabularios ni matching propios.

**Módulos.** `tools/reporting/governance.py` (núcleo), `tools/reporting/cli.py` (`argparse`,
portable) y `tools/reporting/__main__.py` (mismo patrón que `tools/ds_profile/__main__.py`).
`core.py` y `__init__.py` del Change 0 no se tocan. `governance.py` importa solo stdlib,
`dsguard` (`checks`, `pathguard`, `repo`, `scientific_validity`, `core`, con el patrón
`sys.path.insert` + `from dsguard import ...` de `tools/ds_profile/holdout_guard.py:25-31`) y
`from . import core as reporting_core`. La dirección `reporting → dsguard` está permitida por la
regla 6 de `ARCHITECTURE.md`; nunca al revés.

**Vocabulario único.** Todo resultado es `dsguard.checks.CheckResult` (`PASS`/`WARN`/`FAIL`/`N/A`)
y las corridas pasan por `checks.ejecutar_checks`, que ya garantiza "nunca frena" y convierte
excepciones inesperadas en `<codigo>-EXCEPCION` (`technical_error`). Los 10 códigos son
`REPORT-POLICY`, `REPORT-DEST-SAFE`, `REPORT-DEST-SCOPE`, `REPORT-DEST-CROSS-SCOPE`,
`REPORT-SENSITIVE-DEST`, `REPORT-SOURCE-ACCESS`, `REPORT-HOLDOUT-ACCESS`,
`REPORT-HOLDOUT-SOURCE`, `REPORT-ISOLATION-INPUT` y `REPORT-SCI-CUTOFF`. Regla transversal:
ausencia ≠ PASS; ningún check devuelve lista vacía.

**Policy opcional `.harmessi/reporting-policy.json`.** `load_policy(repo_root)` devuelve una
`ReportingPolicy` inmutable. Ausente → defaults deterministas (`reports/<scope>` para
`exploratory`, `model_valid`, `operational`; `sensitive_destination_roots = []`), nunca
heurística. Existente pero inválida → `ReportingPolicyError` (fail-closed, sin recuperación con
defaults). Los roots deben estar en forma canónica estricta (relativos, `/`, sin `.`/`..`, sin
`/` final, sin metacaracteres de `fnmatch`) porque de cada root se deriva `<root>/**` para
`repo.path_matches_any`. Los 3 roots de scope son distintos y no anidados (el aislamiento
exploratory ↔ model_valid depende de esa disjunción) y cada root sensible cuelga estrictamente de
un root de scope. `resolve_output_dir(policy, scope, report_id)` compone `<root>/<report_id>` sin
tocar disco.

**Flujo de evaluación.**
1. `evaluate_governance(ctx)` (y `evaluate_destination(ctx)`, que es su prefijo de 4 checks) arma
   la lista de checks en orden fijo y la ejecuta con `checks.ejecutar_checks`.
2. `REPORT-POLICY` carga la policy de reporting. Si falla → se devuelve solo ese FAIL
   `technical_error` (mismo precedente que `SCI-POLICY`, `scientific_validity.py:532-562`) y no se
   evalúa nada más: sin policy válida no hay roots contra los cuales decidir.
3. `REPORT-DEST-SAFE`: carga `guardrails.json` con `pathguard.cargar_config` (corrupto → FAIL
   `technical_error`) y evalúa las cuatro rutas canónicas de salida (`report.html`,
   `manifest.json`, `insights.json`, `artifacts/_`) como un `Write` sintético.
4. `REPORT-DEST-SCOPE` / `REPORT-DEST-CROSS-SCOPE`: resuelve `out_dir` con
   `pathguard.resolver_ruta_relativa` (sigue symlinks) y lo ubica contra los roots. Bajo su root
   → PASS; bajo el root de otro scope → FAIL cross-scope; igual al root o fuera de todos → FAIL.
5. `REPORT-SENSITIVE-DEST`: solo si hay artefactos sensibles (`context_from_report` los deriva de
   `Report.iter_tables()`/`iter_figures()`).
6. Solo `evaluate_governance`: `REPORT-SOURCE-ACCESS` (`Read` sintético por fuente),
   `REPORT-HOLDOUT-ACCESS` (declaración `none`/`read` contra la policy científica),
   `REPORT-HOLDOUT-SOURCE` (contradicción fuentes vs. declaración), `REPORT-ISOLATION-INPUT`
   (`check_flow_inputs` sobre `ctx.sources` con `flow_scope = ctx.decision_scope`) y
   `REPORT-SCI-CUTOFF` (declaración del reporte contra `temporal.cutoff_utc`).
7. `output_allowed(results)` es `True` sii `not checks.hay_bloqueo(results)`. Es el guard que el
   Change 4 (`publish`) invocará: ante cualquier FAIL, no escribe. `WARN` y `N/A` no bloquean.

**Por qué reusar `pathguard.evaluar_tool_call` con un payload sintético.** El hook de escritura y
lectura ya decide con esa función (`pathguard.py:436-456`): secretos, holdouts, `data_raw`,
`guardrails.json` protegido, `write_scopes` por `agent_type`, excepciones de lectura con
vencimiento y fail-closed ante rutas fuera del repo o no resolubles. Construir
`{"tool_name": "Write"|"Read", "tool_input": {"file_path": ruta}, "agent_type": ...}` y llamar al
MISMO evaluador garantiza que governance y hook nunca diverjan: si el hook cambia una regla,
governance la hereda sin tocar código, y no queda una réplica privada que envejezca (como las de
`holdout_guard.py:34-63` o `scientific_validity.py:110-139`, que este Change no repite). El costo,
asumido, es acoplarse a la forma del payload PreToolUse (ver Riesgos).

**Matching case-insensitive.** `pathguard` compara en minúsculas para que un FS case-insensitive
(Windows, macOS por defecto) no permita esquivar patrones con otro casing. Governance hace lo
mismo en los checks propios: pertenencia a un root =
`path_matches_any(ruta.casefold(), [f"{root.casefold()}/**"])`, y la comparación de roots entre
sí (R5) también con `casefold`. Sin esto, `Reports/EXPLORATORY/r1` esquivaría los roots, y `Out`
vs `out/mv` pasaría como "no anidados". El `/**` exige subdirectorio/archivo ESTRICTO del root
(el root mismo y `reports/exploratory-x` no pertenecen).

**Aislamiento exploratory ↔ model_valid (`check_flow_inputs`).** Dos señales deterministas y
locales: (a) el input cae bajo el root exploratory de la policy; (b) el input, si es directorio, o
un ancestro suyo hasta la raíz del repo contiene un `manifest.json` que es de reporte Harmessi
(objeto con `report_id` y `decision_scope`) con `decision_scope == "exploratory"`. Un manifest
ajeno, ilegible o no JSON se ignora; no se abre ninguno cuya lectura `pathguard` deniegue. Lo que
no puede verificarse (input fuera del repo, no `str`, no resoluble) es FAIL, no PASS. El chequeo
por hash de contenido contra artefactos exploratorios queda diferido al Change 3, dueño de los
hashes de artefactos y de fuentes.
Enmienda ciclo 1: un input igual a, bajo o ANCESTRO del root exploratory (incluida la raíz del
repo) es FAIL, comparado lexicalmente con casefold contra el root textual y el resuelto (root que
es symlink/junction); un input con metacaracteres de glob es "no verificable" (FAIL). La búsqueda
hacia abajo de manifests exploratorios anidados en un input-directorio se difiere al hash del
Change 3. Análogamente, `REPORT-HOLDOUT-SOURCE` sin patrones en `guardrails.json` no es PASS
(FAIL si la policy científica declara holdout, N/A si no), `resolve_output_dir` valida ids con
`reporting_core.es_id_valido` (adición aditiva a `core.py`) y `output_allowed` admite
`require_codes` con `REQUIRED_DESTINATION_CODES` para que `publish` no trate "no se evaluó nada"
como permitido.

**`REPORT-SCI-CUTOFF`.** Compara el `data_cutoff` DECLARADO del reporte con `temporal.cutoff_utc`
de la policy científica (`scientific_validity.leer_policy`, `dsguard_core.parsear_utc`). Un
`YYYY-MM-DD` se interpreta como `T00:00:00Z`. En `model_valid`/`operational` un cutoff ausente o
posterior es FAIL; en `exploratory` es WARN (con la advertencia de no alimentar `model_valid`). No
duplica `SCI-CUTOFF`, que compara el profile del dataset.

**CLI.** `python -m tools.reporting {check-inputs,check-destination}`, `--repo-root` (default
cwd), `--json`; exit codes `0` sin FAIL, `1` con FAIL (`checks.exit_code`), `2` uso, `3` entorno.
No escribe ni lee `stdin`. `validate` y `render` los agregan los Changes 3-4.

**Instalabilidad y arquitectura.** Tres entradas VERBATIM en `MANIFEST` (`stage_minimo` por
defecto `discovery`) inmediatamente después de `tools/reporting/core.py`; los tests no se
instalan. `governance.py` y `cli.py` entran en `MODULOS_CORE` y en `ARCHITECTURE.md` §2.1. Las
dependencias en `dsguard` ya se instalan desde `discovery`, así que la instalación no queda rota.

## Target (condicional — feature_engineering, modeling)
No aplica: infraestructura del harness; no hay target ni modelo.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica: no se construyen features.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica: no se lee ni se particiona ningún dataset. El guard solo evalúa RUTAS de holdouts
declarados en `guardrails.json`; nunca abre su contenido. Los tests usan patrones de holdout
sintéticos en repos temporales.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
Este Change es una mitigación de leakage, no un riesgo sobre datos. Vectores considerados:
- **Output exploratorio consumido como evidencia validada**: un reporte `exploratory` escrito en
  la zona de `model_valid` (o al revés) o un notebook de modelado que lea un output exploratorio.
  Se cubre con `DEST-SCOPE`/`DEST-CROSS-SCOPE` (roots disjuntos y no anidados) e
  `ISOLATION-INPUT` (root + `manifest.json` ancestro).
- **Reporte que cubre datos posteriores al cutoff de modelado**: `SCI-CUTOFF` (FAIL en
  `model_valid`/`operational`, WARN en `exploratory`).
- **Acceso a holdout no declarado o no autorizado**: `HOLDOUT-ACCESS`/`HOLDOUT-SOURCE` exigen
  declaración explícita y autorización de la policy científica; `DEST-SAFE` nunca autoriza escribir
  en un holdout.
- **Foto sin fecha / snapshot como evento**: no aplica a este Change (no hay features); la
  fecha del corte se toma de la declaración del reporte, no de un campo del dataset.
Complementa, no reemplaza, la revisión independiente de `data-science-reviewer`.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica aleatoriedad: no hay `RANDOM_STATE`. Determinismo por construcción: orden fijo de
checks, sin reloj salvo el vencimiento de excepciones de lectura que evalúa `pathguard` (UTC).

## Alternativas descartadas
1. **Un nuevo engine de checks o un vocabulario de resultados propio para governance**:
   rechazada; `dsguard.checks.CheckResult` y `ejecutar_checks` ya son el vocabulario canónico y
   garantizan "nunca frena". Un segundo engine dividiría exit codes y consumo (`hay_bloqueo`).
2. **Réplicas privadas adicionales de `pathguard`** (secretos, holdouts, `data_raw`,
   `write_scopes` reimplementados en governance): rechazada; ya hay dos réplicas parciales
   (`holdout_guard.py`, `scientific_validity.py`) y cada una es una fuente de deriva. Se llama al
   mismo evaluador que el hook; el único matching propio es el de roots de reporting, con el mismo
   `path_matches_any`, y un test de paridad contra `pathguard` en `HOLDOUT-SOURCE`.
3. **Leer el contenido de holdouts (o de fuentes) para verificar su naturaleza**: rechazada;
   viola la regla de holdouts intocables. El guard evalúa rutas, nada más.
4. **Inferir el `decision_scope` por heurística** (del directorio, del nombre, del contenido):
   rechazada; el scope viene del `Report` o de `--scope`, y el destino se valida contra él. Una
   inferencia permitiría que un output mal ubicado "se autocorrija" en vez de fallar.
5. **Hashes de contenido contra artefactos exploratorios ahora**: rechazada para este Change;
   los hashes de fuentes y artefactos y el manifest pertenecen al Change 3. Duplicarlos acá
   contradice `docs/roadmap/v0.6.md:94-95`. Se difiere allí.
6. **Enforcement por un hook nuevo** (PreToolUse/PostToolUse propio de reporting): rechazada;
   agrega superficie de instalación y un segundo camino de decisión. Governance es una función
   invocable (Change 4 la llama desde `publish`) y `pathguard` ya cubre el hook de agentes.

## Riesgos
- **Governance es declarativa**: valida lo que el `GovernanceContext` declara (fuentes,
  `holdout_access`, `data_cutoff`). No observa lecturas en runtime de un notebook; un notebook
  puede leer algo que no declaró. Mitigación fuera de este Change: hooks de `pathguard` para
  agentes y fsdiff de `nbrunner`; verificación de evidencia y provenance en el Change 3.
- **Parseo de shell best-effort**: `pathguard` trata `Bash`/`PowerShell` como mejor esfuerzo
  (`pathguard.py:8-14`); governance no lo mejora, evalúa rutas ya extraídas.
- **Escrituras fuera de `publish`**: un notebook que escriba directamente fuera de `publish` no
  pasa por el guard. Mitigación: Change 3 (manifest con hashes que detecta artefactos no
  registrados) y Change 4 (`publish` como única vía soportada de escritura).
- **`fnmatch` `*` cruza `/`** (`repo.py:109-121`): los patrones de `guardrails.json` pueden ser más
  amplios de lo que aparentan. Governance no lo cambia; los roots de reporting se restringen a
  forma canónica sin metacaracteres para que `<root>/**` sea inequívoco.
- **Nombres case-insensitive**: se comparan con `casefold`, coherente con `pathguard`. Efecto
  colateral: dos roots que solo difieren en mayúsculas se rechazan como colisión, y en un FS
  case-sensitive un directorio con otro casing se trata igual que el root.
- **Fuentes fuera del repo = FAIL** (fail-closed): no se puede verificar el acceso; una fuente
  legítima fuera del repo requiere traerla al repo o declarar una excepción en `guardrails.json`
  por su dueño. Es una fricción deliberada.
- **`date-only = T00:00:00Z`**: un `data_cutoff` `YYYY-MM-DD` cuenta como el inicio del día; igual
  al `cutoff_utc` de medianoche pasa (`<=`), pero `2026-01-01` con datos de todo el día no está
  distinguido del inicio. Quien necesite precisión debe declarar `YYYY-MM-DDTHH:MM:SSZ`.
- **Acoplamiento a la forma del payload PreToolUse**: `evaluar_tool_call` espera `tool_name`,
  `tool_input.file_path` y `agent_type`; si el protocolo de hooks cambia, governance debe seguirlo.
  Ya registrado en `ARCHITECTURE.md` §4 punto 2; un test cruza la decisión de governance con la de
  `pathguard` para detectar la deriva.
- **Excepción a "nunca lanza"**: `load_policy` y `resolve_output_dir` levantan
  `ReportingPolicyError` por diseño (son constructores de policy, no checks); ningún check ni
  agregador la deja propagar.
- **Mantenimiento del manifest**: cada módulo nuevo de `tools/reporting` requiere su entrada
  (`check_manifest_parity`); este Change agrega tres.

## Aprobación humana
El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único por
cambio y vive en la sección "Aprobación" de `proposal.md` — no se duplica acá.
