# Diseño — 20260922-quality-evidence-and-drift

## Decisión metodológica/técnica

Flujo conceptual de v0.7 (`docs/roadmap/v0.7.md:45-71`): `DECLARACIÓN → OBSERVACIÓN → EVALUACIÓN
DETERMINISTA → EVIDENCE → INTERPRETACIÓN`. Changes 0-1 cubrieron `DECLARACIÓN`/`EVALUACIÓN` para
datos; Change 2, ambas para modelo. Este Change 3 es la primera vez que v0.7 llega a la etapa
`EVIDENCE`: tomar los `list[CheckResult]` que `validate_contract`/`evaluate_policy` ya producen EN
MEMORIA y darles una forma persistida, reproducible, con hash y `generated_at`, más una segunda
capacidad nueva (comparar dos observaciones = drift). `INTERPRETACIÓN` sigue sin ser de este módulo.

### Decisión 1 — Nombre del paquete: `tools/qualityevidence` (`core.py` + `evidence.py`)

Paquete nuevo de primer nivel, mismo patrón `__init__.py` + `core.py` (declaración, solo-stdlib) +
módulo de I/O que `tools/datacontracts`/`tools/modelquality`/`tools/reporting`. El segundo módulo se
llama `evidence.py` (no `validation.py`): no produce un veredicto de PASS/WARN/FAIL sobre una
declaración vs. una observación (eso ya lo hicieron Changes 1 y 2) — persiste y compara evidencia
YA evaluada. El nombre replica, a propósito, el de `tools/reporting/evidence.py` (mismo concepto,
familia distinta).

Alternativas descartadas:
1. **Extender `tools/datacontracts` o `tools/modelquality` con un submódulo de evidencia** (p. ej.
   `tools/datacontracts/evidence.py`): rechazada. La evidencia de calidad de este Change abarca
   AMBAS familias a la vez (`docs/roadmap/v0.7.md:301-306`: "evaluación de contrato; resultados de
   calidad de datos; resultados de calidad de modelo" en una sola lista de requisitos) — colgarla de
   una sola de las dos rompería la independencia ya establecida entre ambas
   (`ARCHITECTURE.md:154-159`, regla 8: "familia independiente, sin tipos compartidos") y obligaría
   a elegir arbitrariamente en cuál de las dos vive el tipo compartido `QualityEvidenceManifest`.
2. **`tools/quality/` genérico con submódulos `data.py`/`model.py`/`evidence.py`**: rechazada, mismo
   motivo que la alternativa 2 de Change 2 (`openspec/changes/20260922-model-quality-policies/
   design.md:31-39`): ningún paquete de primer nivel de este repo usa ese nivel de anidación, y un
   paquete `quality` genérico invitaría a que datos/modelo/evidencia convivan sin frontera clara.
3. **`tools/evidence/` genérico** (sin prefijo `quality`, pensando en reutilizarlo para OTRO tipo de
   evidencia futura, p. ej. Model Cards de v0.8): rechazada por ahora; el roadmap nombra esta
   capacidad "evidencia de calidad" específicamente (`docs/roadmap/v0.7.md:299`, título del Change:
   "quality-evidence-and-drift") y generalizar el nombre antes de que exista una segunda necesidad
   real sería inventar alcance no pedido — si v0.8 necesita un paquete de evidencia más genérico,
   ese es un Change futuro con su propio SDD, no una preocupación de este.

### Decisión 2 — Relación con `tools.reporting.evidence`: NINGUNA dependencia de import, en ninguna
dirección; reimplementación local mínima de primitivas de hash/manifest.

Esta es la decisión más delicada de todo el Change (señalada así por el brief). Se resuelve con
evidencia real, comparando 3 alternativas:

**Alternativa A — `tools.qualityevidence` importa `tools.reporting.evidence` para reusar
`describe_source`/`build_manifest`/`write_report_dir`/hash.** Descartada. Costo real medido en
`tools/reporting/evidence.py` (leído completo para esta decisión):
- `describe_source`/`read_allowed` (`tools/reporting/evidence.py:249-330,156-167`) dependen de
  `dsguard.pathguard.evaluar_tool_call` + `dsguard.pathguard.cargar_config`, que a su vez evalúan
  TODO `guardrails.json` (secretos + holdouts + excepciones), no solo el guard de holdout acotado
  que `tools.datacontracts.validation` ya usa (`ds_profile.holdout_guard.verificar_permitido`,
  `tools/ds_profile/holdout_guard.py:89-104`). Importar `reporting.evidence` para una sola función
  arrastraría, transitivamente, `reporting.core` y `reporting.governance` (que a su vez importa
  `dsguard.checks`, `dsguard.pathguard`, `dsguard.repo`, `dsguard.core`) — superficie muy superior a
  lo que este Change necesita.
- `build_manifest` (`tools/reporting/evidence.py:458-517`) produce un dict con forma de REPORTE:
  `report_id`, `report_kind`, `decision_scope`, `holdout_access`, `sensitivity`, `source_notebook`,
  `artifacts` (tablas/figuras/insights) — ninguno de esos campos tiene un análogo natural en
  evidencia de calidad de datos/modelo (no hay "capítulos", ni "artefactos sensibles" en el mismo
  sentido, ni un `decision_scope` de `exploratory`/`model_valid`/`operational`).
- Crearía una dirección de dependencia (`tools.qualityevidence -> tools.reporting`) que ninguna
  regla de `ARCHITECTURE.md` prevé hoy: la regla 6 (`ARCHITECTURE.md:122-134`) documenta que
  `reporting` puede importar `dsguard`/`ds_profile.fingerprint`, y que la dirección INVERSA
  (`dsguard`, `ds_profile`, etc. -> `reporting`) está prohibida — pero nunca contempló que un
  paquete de v0.7 importara `reporting`. Agregar esa dirección sin que el roadmap la pida
  explícitamente (el roadmap solo pide la dirección opuesta: "reporting consume evidencia de
  calidad... no importando el paquete de calidad", `docs/roadmap/v0.7.md:339-341`) sería una
  decisión arquitectónica nueva no autorizada por el brief, que la pide "decidida con evidencia
  real", no asumida.

**Alternativa B — reimplementar localmente las primitivas mínimas (hash sha256 chunked, JSON
canónico, escritura atómica, `generated_at`), sin importar `tools.reporting` en ninguna dirección.**
**Elegida.** Precedente directo, en este mismo repo, de la MISMA decisión: `tools/dsguard/
mlops_evidence.py:1-23,50-60` (`_hash_binario_sha256`, docstring completo leído para este Change)
duplica localmente el hash sha256 chunked en vez de importar `ds_profile.fingerprint.
calcular_fingerprint`, con la justificación textual: "mantiene la única dirección de dependencia
cruzada existente hoy (`ds_profile -> dsguard`, nunca al revés)". El mismo razonamiento aplica acá:
`tools.qualityevidence` reimplementa (stdlib puro: `hashlib`, `json`, `tempfile`/`os.replace`) sus
propias funciones equivalentes a `describe_source`/`_json_bytes`/escritura atómica, documentando el
mismo `ALGORITHM = "sha256/bin/v1"` como **coincidencia de valor documentada, no import** — mismo
criterio que `SEVERITIES = ("FAIL", "WARN")` se duplicó, sin importar, entre
`tools/datacontracts/core.py:76` y `tools/modelquality/core.py:75` (`design.md` de Change 2,
decisión 1). "Reutilizar capacidades existentes" (`docs/roadmap/v0.7.md:38`) se satisface
reutilizando el mismo ALGORITMO y el mismo PATRÓN de manifest (hashes + `generated_at` separado +
escritura atómica + lectura verificada), no necesariamente el mismo símbolo Python importado — el
propio repo ya trató "mismo patrón, código duplicado a propósito" como forma válida de reutilización
cuando la alternativa es una dependencia cruzada nueva y no prevista.
- `qualityevidence` SÍ importa `ds_profile.holdout_guard.verificar_permitido` (mismo símbolo único
  que `tools/datacontracts/validation.py` ya usa) para leer `profile.json` en `DriftEvidence` — esto
  NO es una dependencia nueva: ya está prevista por la regla 7 de `ARCHITECTURE.md` y por la
  redacción general del roadmap ("los paquetes de v0.7 pueden importar `dsguard.checks` y consumir
  `profile.json` como archivo", `docs/roadmap/v0.7.md:118-120`).

**Alternativa C — no reimplementar nada; delegar la construcción del manifest completo a un
`dict` sin ninguna validación de forma propia** (dejar que el llamador arme el JSON a mano).
Descartada: violaría "todo serializable con orden determinista, versionado explícito y hash de
contenido" (`docs/roadmap/v0.7.md:126`) — sin un tipo propio (`QualityEvidenceManifest`) no hay
forma de garantizar reproducibilidad ni de detectar un manifest malformado antes de escribirlo.

**Consecuencia directa para la integración con Reporting v0.6 (el bullet del roadmap que sí pide
integración):** un manifest de `tools.qualityevidence` es, para `reporting.evidence`, un archivo
más del repo. Un chapter de reporte puede llamar
`reporting.evidence.describe_source(repo_root, ".harmessi/quality/<evidence_id>/manifest.json",
role="quality_evidence")` (`tools/reporting/evidence.py:249-307`, ya existente, sin ningún cambio) y
obtener `{kind: "file", role, path, sha256, algorithm, size_bytes}` — exactamente "evidencia de
calidad como archivo con hash" (`docs/roadmap/v0.7.md:339`), SIN que `reporting` conozca el schema
interno del manifest de calidad y SIN que `qualityevidence` conozca nada de `reporting`. Esto
resuelve la integración pedida por el roadmap con CERO líneas de código nuevas en `tools/reporting`
(cumple "si la integración exige cambiar el schema del manifest de v0.6 de forma incompatible →
STOP" trivialmente: no lo cambia en absoluto) y sin ninguna dependencia cruzada en ninguna
dirección. Se documenta como el mecanismo de integración de este Change (ver R16 de `spec.md`).

### Decisión 3 — Forma exacta del manifest de evidencia de calidad (`QualityEvidenceManifest`)

```python
SCHEMA_VERSION = 1
SUBJECT_KINDS = ("data_contract_evaluation", "model_quality_evaluation")
EVIDENCE_SOURCE_KINDS = ("file", "generated")
_STATUS_VALIDOS = ("PASS", "WARN", "FAIL", "N/A")   # mismo literal que dsguard.checks -- coincidencia
                                                     # documentada, no import (ver decisión 1 de
                                                     # Changes 0/2 para el mismo criterio)

@dataclass(frozen=True)
class EvidenceSource:
    kind: str                       # ∈ EVIDENCE_SOURCE_KINDS
    role: str                       # p. ej. "profile", "contract", "policy", "input"
    path: Optional[str] = None      # SOLO para kind="file": relativo al repo, posix (nunca absoluto)
    sha256: Optional[str] = None    # para kind="file": hash de los bytes; para kind="generated":
                                     # hash de params canónico
    algorithm: str = "sha256/bin/v1"
    description: Optional[str] = None   # SOLO para kind="generated"
    params: Optional[dict] = None       # SOLO para kind="generated", JSON-seguro

@dataclass(frozen=True)
class DeclarationRef:
    declaration_kind: str           # "data_contract" | "model_quality_policy" (str libre, ver R5)
    declaration_id: str             # contract_id / policy_id (str ya extraído por el llamador)
    version: Optional[str] = None   # ContractVersion.version si aplica; None para ModelQualityPolicy
    content_sha256: str = ""        # DataContract.content_sha256() / ModelQualityPolicy.content_sha256()

@dataclass(frozen=True)
class ScopeWindow:
    population: str = ""            # texto libre, igual que EvaluationContext.population
    time_start: Optional[str] = None    # ISO 8601, opcional
    time_end: Optional[str] = None      # ISO 8601, opcional

@dataclass(frozen=True)
class QualityEvidenceManifest:
    schema_version: int
    evidence_id: str                        # "qe-YYYYMMDDTHHMMSSZ-<6hex>"
    subject_kind: str                       # ∈ SUBJECT_KINDS
    declaration: DeclarationRef
    source: EvidenceSource                  # el "artefacto/run de origen" (profile.json u otro)
    scope: ScopeWindow
    check_results: tuple                    # tuple[dict] -- forma de CheckResult.to_dict(), kind="check"
    technical_errors: tuple                 # tuple[dict] -- kind="technical_error", SEPARADO (decisión 4 heredada)
    generated_at: str                       # declarado aparte del hash (ver requisito de reproducibilidad)
    content_sha256: str                     # hash de TODO lo anterior EXCEPTO generated_at (ver abajo)
```

`content_sha256` se calcula sobre `canonical_json(to_dict() sin "generated_at" ni "content_sha256")`
— la misma entrada produce el mismo hash sin importar cuándo se generó (requisito de
reproducibilidad del roadmap, `docs/roadmap/v0.7.md:316`: "misma entrada → mismo contenido salvo
`generated_at`, que se declara aparte"). `check_results`/`technical_errors` son tuplas de `dict`
JSON-puros con exactamente las claves que `CheckResult.to_dict()` produce
(`tools/dsguard/checks.py:49-55`: `status`, `code`, `message`, `kind`, y opcionalmente `detail`/
`subject`) — `core.py` valida la FORMA de esos dicts (claves conocidas, `status` ∈ vocabulario,
`kind` coincide con la lista en la que está) sin importar `dsguard.checks` (mismo criterio de
"coincidencia de vocabulario documentada" que el resto de v0.7); `evidence.py` es quien SÍ importa
`dsguard.checks` y hace `[r.to_dict() for r in results if r.kind == checks.KIND_CHECK]` /
`[... KIND_TECHNICAL_ERROR]` antes de construir el manifest.

Portabilidad (`docs/roadmap/v0.7.md:318-320`, nota concreta sobre `dataset_path` absoluto de
`ds_profile`): `EvidenceSource.path` se valida SIEMPRE relativo al repo y posix (mismo patrón
`_ruta_posix_relativa`/`_ruta_relativa_segura` que `tools/reporting/evidence.py:432-442,206-221`,
reimplementado localmente) — nunca se copia `profile.get("dataset_path")` tal cual (que puede ser
absoluto); si el llamador necesita referenciar el dataset de origen, pasa la ruta del `profile.json`
persistido (ya repo-relativo por convención de `ds_profile`), no `dataset_path`.

Alternativas descartadas:
1. **Persistir el `Report`/`Report.chapters` completo dentro del manifest de calidad** (para que
   sea autocontenido sin necesitar un `profile.json` externo): rechazada; duplicaría datos ya
   persistidos por `ds_profile`, violando "no duplicar" y volviendo el manifest potencialmente
   gigante; el manifest referencia su fuente por hash (`EvidenceSource`), no la incluye.
2. **Un único campo `results: tuple[dict]` con `kind` mezclado, sin separar `check_results`/
   `technical_errors`**: rechazada explícitamente; el roadmap exige "separa `technical_error` de
   resultados de calidad" (`docs/roadmap/v0.7.md:320`) heredando la decisión 4 del roadmap
   (`docs/roadmap/v0.7.md:92-95`) — separar en dos tuplas físicas, en vez de solo un campo `kind`
   dentro de un único campo `results`, hace el requisito verificable por FORMA (dos claves
   distintas del dict) sin depender de que el consumidor filtre correctamente.
3. **`content_sha256` calculado sobre bytes JSON completos INCLUYENDO `generated_at`** (más simple
   de implementar): rechazada de plano; rompería literalmente el requisito de reproducibilidad del
   roadmap ("misma entrada → mismo contenido salvo `generated_at`") — dos corridas idénticas en
   contenido pero en momentos distintos tendrían hashes distintos, imposibilitando detectar
   "¿esta evidencia es exactamente la misma que la de ayer?".

### Decisión 4 — Forma exacta de "drift evidence" (`DriftEvidence`)

```python
DRIFT_COMPARISON_MODES = ("absolute_diff", "relative_diff")

@dataclass(frozen=True)
class DriftEvidence:
    schema_version: int
    drift_id: str                        # "dr-YYYYMMDDTHHMMSSZ-<6hex>"
    metric_name: str                     # ^[a-z][a-z0-9_]*$ -- mismo patrón que ObservedMetric.metric_name,
                                          # reimplementado localmente (ver decisión 1 de Change 2 para el
                                          # mismo criterio de no-import entre familias)
    baseline_window: EvidenceSource      # ventana de referencia: profile.json baseline (u otro origen)
    baseline_label: str                  # p. ej. "2026-08", "pre-release", texto libre declarado
    current_window: EvidenceSource       # ventana actual
    current_label: str
    baseline_value: float                # número YA extraído/observado (ver decisión 4 abajo)
    current_value: float
    comparison_mode: str                 # ∈ DRIFT_COMPARISON_MODES
    observed_difference: float           # calculado por evidence.py, validado (no recalculado) por core.py
    threshold: Optional[float]           # magnitud máxima permitida de observed_difference (abs), o None
    result_status: str                   # ∈ {"PASS","WARN","FAIL","N/A"} -- mismo vocabulario de checks.py
    result_message: str
    generated_at: str
    content_sha256: str                  # mismo criterio que QualityEvidenceManifest: excluye generated_at
```

Ejemplo concreto de cómo se calcula `observed_difference` (acotado, determinista, sin librería
estadística — exactamente lo que pide el brief):

- **`"absolute_diff"`**: `observed_difference = current_value - baseline_value`. Ejemplo: tasa de
  nulos de una columna en `profile.json` baseline = `0.02` (2%), en el actual = `0.07` (7%) →
  `observed_difference = 0.05`. Con `threshold = 0.03`, `abs(observed_difference) = 0.05 > 0.03` →
  `result_status = "FAIL"`, `result_message` explicita ambos valores y la ventana.
- **`"relative_diff"`**: si `baseline_value == 0` → `result_status = "WARN"` "no verificable
  (baseline en cero)" (mismo tratamiento que `relative_to_baseline` en `tools/modelquality/
  validation.py:194-196`, `_comparar_baseline`, reimplementado localmente sin importar ese módulo);
  si no, `observed_difference = (current_value - baseline_value) / baseline_value`. Ejemplo:
  cardinalidad distinta (`unique.count`) de una columna: baseline = `1000`, actual = `1200` →
  `observed_difference ≈ 0.20` (20% de aumento). Con `threshold = 0.15` → `FAIL`.
- Si `threshold is None` → `result_status = "N/A"`, `result_message` = "sin threshold declarado:
  evidencia registrada sin veredicto" (evidencia comparativa PURA, sin política — cumple
  explícitamente la decisión 6 del roadmap: registrar sin afirmar).
- `result_status` NUNCA es más fuerte que lo que el `threshold` permite verificar: sin threshold,
  jamás `PASS`/`FAIL`, solo `N/A` — mismo principio "nunca PASS por falta de evidencia" aplicado a
  drift (sin política de comparación, no hay ni PASS ni FAIL posibles, solo registro).

**Dos funciones en `evidence.py` (ver decisión 5), NO una sola**, para separar "comparar dos números
ya en memoria" (genérico, sin I/O) de "extraer un número de dos `profile.json`" (acotado a un
allowlist, con I/O guardado):

```python
def build_drift_evidence(*, metric_name, baseline_value, current_value, baseline_window,
                          baseline_label, current_window, current_label, comparison_mode,
                          threshold=None, clock=None) -> dict: ...

_CAMPOS_NUMERICOS_PERMITIDOS = ("filas", "nulls_count", "unique_count", "min", "max")

def drift_from_profiles(repo_root, *, metric_name, baseline_profile_path, current_profile_path,
                         column=None, field, comparison_mode, threshold=None,
                         baseline_label="baseline", current_label="current", clock=None) -> dict: ...
```

`drift_from_profiles` es el "observador natural: dos `profile.json`" que pide el roadmap
(`docs/roadmap/v0.7.md:332`): aplica `ds_profile.holdout_guard.verificar_permitido` a AMBAS rutas
ANTES de abrirlas (una denegada → `FAIL kind="technical_error"`, ninguna se abre), lee ambos
`profile.json`, extrae `field` de `_CAMPOS_NUMERICOS_PERMITIDOS` (con `column=None` para `"filas"`,
que es de nivel dataset; con `column` requerido para los demás, que son de `columnas_detalle[column]
[...]`) y delega en `build_drift_evidence`. `field` fuera del allowlist → `FAIL kind=
"technical_error"` "campo no soportado", nunca una excepción sin capturar — el allowlist es
deliberadamente el mismo vocabulario ya persistido por `ds_profile` y ya consumido por
`tools/datacontracts/validation.py` (`filas`, `columnas_detalle[c]["nulls"]["count"]`,
`columnas_detalle[c]["unique"]["count"]`, `columnas_detalle[c]["min"]`,
`columnas_detalle[c]["max"]`), sin inventar ningún estadístico nuevo.

Alternativas descartadas:
1. **Una sola función que siempre lee dos `profile.json`** (sin `build_drift_evidence` genérico):
   rechazada; obligaría a persistir un `profile.json` sintético incluso para comparar dos
   `ObservedMetric.value` ya reportados por el proyecto (caso de uso real: comparar una métrica de
   modelo entre dos corridas, no solo estadísticas de columnas) — `build_drift_evidence` cubre ese
   caso sin I/O.
2. **Permitir cualquier campo numérico de `profile.json`, sin allowlist** (dejar que el llamador
   pase cualquier ruta de claves anidadas, tipo JSONPath): rechazada de plano; es exactamente la
   "biblioteca estadística universal" que el brief prohíbe — el allowlist acotado y ya-existente en
   `ds_profile` es lo que mantiene esto "acotado, determinista y justificado".
3. **Reutilizar `tools.modelquality.core.COMPARISON_MODES` (3 modos) en vez de declarar
   `DRIFT_COMPARISON_MODES` (2 modos) propio**: rechazada; los modos de Change 2 comparan un valor
   OBSERVADO contra un BASELINE con una `direction` de "mejor/peor" (`higher_is_better`/
   `lower_is_better`) — drift no juzga "mejor o peor", solo "cuánto cambió" (evidencia comparativa
   pura, decisión 6 del roadmap); forzar el mismo vocabulario obligaría a inventar una `direction`
   sin sentido semántico para "cuánto cambió la cardinalidad de una columna". Además, importar
   `tools.modelquality.core` solo para una tupla de 3 strings repetiría el patrón ya rechazado en
   "Supuestos descartados" de `proposal.md` (mantener a `qualityevidence` sin dependencia de ninguna
   de las dos familias).

### Decisión 5 — Reinterpretación de `evidence_ref` (Change 2, inmutable) — por CONVENCIÓN externa

`tools/modelquality/core.py` no se toca (Change 2 cerrado). `ObservedMetric.evidence_ref`/
`BaselineReference.evidence_ref` siguen siendo `Optional[str]` genérico
(`tools/modelquality/core.py:488,569`). Este Change define, solo en `tools.qualityevidence`, una
CONVENCIÓN opcional (nunca obligatoria) que un `evidence_ref` puede seguir para volverse verificable:

```python
def resolve_evidence_ref(evidence_ref: str, repo_root) -> dict:
    """Si `evidence_ref` tiene la forma `"quality:.harmessi/quality/<evidence_id>/manifest.json"`
    (prefijo `"quality:"` + ruta repo-relativa posix), intenta leer y verificar ESE manifest
    (mismo `content_sha256` propio). Devuelve
    `{"resolvable": True, "valid": bool, "detail": str, "manifest": dict|None}` si sigue la
    convención, o `{"resolvable": False, "detail": "..."}` si no la sigue (evidence_ref con
    cualquier otra forma: ruta de notebook, id de corrida externo, URI) -- NUNCA lanza, NUNCA
    asume que todo evidence_ref debe seguir esta convención."""
```

Esto satisface el punto de conexión que Change 2 dejó explícitamente abierto
(`openspec/changes/20260922-model-quality-policies/design.md:101-102`: "Change 3 podrá, en su
propio SDD, decidir si reinterpreta `evidence_ref` como una ruta bajo `.harmessi/` con hash
verificable, sin que este Change se comprometa de antemano con esa forma") sin ningún cambio de
tipo en Change 2: la reinterpretación vive enteramente del lado de `tools.qualityevidence`, como una
función que OPCIONALMENTE sabe leer un formato de `str` que este Change inventa (`"quality:<ruta>"`)
— cualquier `ObservedMetric`/`BaselineReference` construido antes de este Change (con `evidence_ref`
en cualquier otra forma) sigue siendo válido y evaluable exactamente igual que hoy por
`evaluate_policy` (que ni siquiera importa `tools.qualityevidence`).

Alternativas descartadas:
1. **Pedir a Change 2 (reabrirlo) que cambie `evidence_ref` a un tipo estructurado** (p. ej.
   `dict`/dataclass con `path`/`sha256`): rechazada de plano; Change 2 está cerrado, y el brief
   prohíbe explícitamente tocar `tools/modelquality/{core,validation}.py` en este Change. Reabrir un
   Change cerrado por una conveniencia de diseño de OTRO Change es exactamente el tipo de deuda que
   el roadmap busca evitar con Changes secuenciales congelados.
2. **No definir ninguna convención, dejar `evidence_ref` sin ningún significado operativo**:
   rechazada; dejaría sin resolver el punto que Change 2 dejó abierto explícitamente a propósito, y
   el roadmap sí exige un enlace real entre evidencia de modelo y evidencia persistida
   ("artefacto/run de origen", `docs/roadmap/v0.7.md:310`).
3. **Convención SIN prefijo `"quality:"`** (tratar cualquier `str` que "parezca" una ruta bajo
   `.harmessi/quality/` como resoluble): rechazada; ambigua con `evidence_ref` legítimos que
   casualmente contengan ese texto en otro contexto (p. ej. una descripción libre); el prefijo hace
   la convención auto-identificable sin heurística.

### Decisión 6 — Regla 9 de `ARCHITECTURE.md` §3

Texto exacto a insertar (tras la regla 8 existente), por la invocación 2:

> 9. Familia `tools/qualityevidence` (v0.7 Change 3): `core.py` es solo-stdlib y no importa
>    hermanos ni ningún paquete existente (ni `tools.datacontracts`, ni `tools.modelquality`, ni
>    `tools.reporting`: ver `design.md` del Change, decisiones 1-2). `evidence.py` importa
>    `dsguard.checks` (para envolver `list[CheckResult]` ya producidos por el llamador) y
>    `ds_profile.holdout_guard.verificar_permitido` (único símbolo, mismo criterio que la regla 7
>    aplicó a `tools/datacontracts/validation.py`, para leer `profile.json` en `DriftEvidence`);
>    reimplementa localmente sus propias primitivas de hash sha256 chunked, JSON canónico y
>    escritura atómica (mismo criterio que `tools/dsguard/mlops_evidence.py`, sin importar
>    `ds_profile.fingerprint` ni `tools.reporting.evidence`). `tools.qualityevidence` NO importa
>    `tools.datacontracts` ni `tools.modelquality` en ninguna dirección (el llamador extrae
>    `contract_id`/`policy_id`/`version`/`content_sha256()` como valores planos antes de invocar
>    `evidence.py`) y NO importa `tools.reporting` en ninguna dirección (la integración con
>    Reporting v0.6 ocurre exclusivamente porque `reporting.evidence.describe_source` puede hashear
>    cualquier archivo del repo, incluido un manifest de `qualityevidence`, sin que ninguno de los
>    dos paquetes importe al otro). Nunca al revés: `dsguard`, `ds_profile`, `dsimpact`, `reporting`,
>    `tools.datacontracts`, `tools.modelquality`, `providers`, `routing`, `fallback` y
>    `harmessi_bench` no importan `tools.qualityevidence`. Verificado por
>    `tools/tests/test_v07_qualityevidence_neutrality.py`.

Y las dos filas correspondientes en §2.1, mismo estilo que las filas de `tools/modelquality`:

> `tools/qualityevidence/core.py` | Tipos neutrales de evidencia de calidad (v0.7 Change 3:
> `QualityEvidenceManifest`/`DriftEvidence`/`EvidenceSource`/`DeclarationRef`/`ScopeWindow`,
> serialización determinista y hash de contenido que excluye `generated_at`) -- solo stdlib; no
> calcula nada desde datos crudos, no observa ningún dataset; familia independiente de
> `tools.datacontracts`/`tools.modelquality`/`tools.reporting`, sin tipos compartidos; no conoce
> protocolo de hooks, es core.
>
> `tools/qualityevidence/evidence.py` | Persistencia de evidencia de calidad y cómputo de drift
> (v0.7 Change 3: construcción/escritura atómica/lectura verificada de
> `QualityEvidenceManifest` bajo `.harmessi/quality/`, `build_drift_evidence`/
> `drift_from_profiles` con `DRIFT_COMPARISON_MODES` acotado a diferencia absoluta/relativa,
> `resolve_evidence_ref` como convención opcional sobre `ObservedMetric.evidence_ref`/
> `BaselineReference.evidence_ref` de Change 2, sin modificarlo) -- importa `dsguard.checks` y
> `ds_profile.holdout_guard.verificar_permitido` (único símbolo); reimplementa localmente hash
> sha256 chunked/JSON canónico/escritura atómica (mismo criterio que
> `tools/dsguard/mlops_evidence.py`); nunca lee un `profile.json` sin el guard; nunca `PASS`/`FAIL`
> de drift sin threshold declarado (`N/A` "evidencia registrada sin veredicto"); no conoce
> protocolo de hooks, es core.

### Vocabulario completo de `core.py`

```python
SCHEMA_VERSION = 1
SUBJECT_KINDS = ("data_contract_evaluation", "model_quality_evaluation")
EVIDENCE_SOURCE_KINDS = ("file", "generated")
DRIFT_COMPARISON_MODES = ("absolute_diff", "relative_diff")
_STATUS_VALIDOS = ("PASS", "WARN", "FAIL", "N/A")  # coincidencia documentada con dsguard.checks
_KINDS_VALIDOS = ("check", "technical_error")       # coincidencia documentada con dsguard.checks

class QualityEvidenceError(ValueError):
    """Violación de forma de evidencia de calidad (entrada estructuralmente inválida)."""
```

**Ids**: `evidence_id`/`drift_id` siguen el patrón `"<prefijo>-YYYYMMDDTHHMMSSZ-<6hex>"` (mismo
formato que `reporting.evidence.new_run_id`, reimplementado localmente vía `datetime`/`secrets`
de stdlib, sin importar `reporting.evidence`). `metric_name` (de `DriftEvidence`) reutiliza el
patrón `^[a-z][a-z0-9_]*$`, reimplementado localmente (mismo criterio de no-import entre familias
que ya aplicaron Changes 0-2 entre sí).

### Instalabilidad

Tres entradas `VERBATIM` en `MANIFEST` (`tools/qualityevidence/__init__.py`,
`tools/qualityevidence/core.py`, `tools/qualityevidence/evidence.py`) con `stage_minimo` por defecto
(`"discovery"`, mismo criterio que `tools/datacontracts`/`tools/modelquality`). Los tests del
paquete no se instalan.

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica un split propio: `ScopeWindow`/`baseline_label`/`current_label` son texto DECLARADO por
quien construye la evidencia (mismo criterio que `EvaluationContext.split` en Change 2), nunca
calculado ni verificado contra un dataset real por este módulo.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
Riesgo mitigado explícitamente: `drift_from_profiles` solo lee `profile.json` YA persistidos (nunca
un dataset ni una columna cruda), y solo tras `ds_profile.holdout_guard.verificar_permitido` sobre
AMBAS rutas — si cualquiera de las dos está protegida sin excepción de lectura vigente, ninguna de
las dos se abre (fail-closed: no se compara un profile permitido contra uno denegado a medias). Los
`profile.json` en sí ya son metadata agregada (no filas crudas), mismo principio que Change 1 aplicó
a `validate_contract_against_profile_file`.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica aleatoriedad determinística de negocio: no hay `RANDOM_STATE`. `new_evidence_id`/
`new_drift_id` usan `secrets.token_hex` para el sufijo (mismo patrón que
`reporting.evidence.new_run_id`), por lo que dos evidencias del mismo contenido en el mismo segundo
tienen ids distintos — el determinismo que importa (`content_sha256`) es independiente del id y del
sufijo aleatorio, igual que `report_id`/`run_id` son independientes de `hashes.report_content` en
`tools/reporting/evidence.py:499-517`. Tests que verifiquen reproducibilidad de contenido fijan
`clock`/`suffix` explícitos, mismo patrón que `tools/reporting/evidence.py:381-391`
(`new_run_id(now=..., suffix=...)`).

## Alternativas descartadas (adicionales a las de cada decisión numerada arriba)
1. **Un solo módulo `tools/qualityevidence/core.py` con TODO (tipos + I/O)**: rechazada; mismo
   argumento que Change 2 rechazó fusionar `core.py`+`validation.py`
   (`openspec/changes/20260922-model-quality-policies/design.md:485-492`) — mezclar dataclasses
   `frozen=True` puras con funciones que hacen I/O (hash de archivos, escritura atómica, lectura de
   `profile.json` guardada) forzaría a que la declaración misma dejara de ser solo-stdlib.
2. **Persistir evidencia de drift dentro del MISMO archivo `manifest.json` de
   `QualityEvidenceManifest`** (un solo tipo de documento para ambos): rechazada; el roadmap los
   trata como conceptos distintos con campos distintos (`docs/roadmap/v0.7.md:301-330`, dos
   secciones separadas) — un `QualityEvidenceManifest` envuelve resultados de UNA evaluación (contra
   una declaración), mientras que `DriftEvidence` compara DOS observaciones sin declaración
   intermedia; forzarlos al mismo tipo obligaría a campos opcionales cruzados y confusos.
3. **Ubicar los manifests bajo `reports/` (mismo árbol que Reporting v0.6)** en vez de
   `.harmessi/quality/`: rechazada; el roadmap pide explícitamente "ubicación distinta de la
   declaración (SDD define la ruta bajo `.harmessi/`)" (`docs/roadmap/v0.7.md:321`) — `.harmessi/`
   es, además, el árbol ya usado por `mlops_evidence`/`harmessi_bench`/`fallback.handoff` para
   evidencia/estado generado por el harness (`ARCHITECTURE.md:43,59`), consistente con el patrón
   existente.

## Riesgos
- **Duplicación de primitivas de hash/manifest entre `tools.qualityevidence` y
  `tools.reporting.evidence`** (mismo algoritmo, dos implementaciones): riesgo de drift de
  implementación si el algoritmo de hash cambiara alguna vez; aceptado explícitamente, mismo
  criterio que `mlops_evidence.py` ya aceptó frente a `ds_profile.fingerprint` — mantener las
  familias sin dependencia cruzada nueva es más valioso que evitar esta duplicación puntual y
  pequeña (documentado como deuda vigilada, mismo criterio que la deuda 6 de `ARCHITECTURE.md`
  §4.1).
- **`resolve_evidence_ref` depende de una convención de texto (`"quality:<ruta>"`) que
  `ObservedMetric`/`BaselineReference` de Change 2 no imponen ni documentan en su propio tipo**:
  riesgo de que un llamador nunca adopte la convención y `evidence_ref` quede, en la práctica,
  siempre no resoluble; aceptado porque la alternativa (forzar la convención en Change 2, cerrado)
  no es viable sin reabrir un Change ya aprobado — la convención queda disponible para quien la
  quiera usar (p. ej. Change 4 CLI), sin bloquear a quien no.
- **`_CAMPOS_NUMERICOS_PERMITIDOS` de `drift_from_profiles` es deliberadamente chico** (5 campos):
  riesgo de que un caso de uso real necesite un campo no cubierto (p. ej. percentiles, si algún día
  `ds_profile` los persistiera); aceptado, mismo costo normal de un vocabulario cerrado que
  `CONSTRAINT_TYPES`/`COMPARISON_MODES` ya asumieron en Changes 0 y 2 — extender el allowlist es un
  SDD propio, aditivo, sin romper `schema_version`.

## Aprobación humana
El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único por
cambio y vive en la sección "Aprobación" de `proposal.md` — no se duplica acá.
