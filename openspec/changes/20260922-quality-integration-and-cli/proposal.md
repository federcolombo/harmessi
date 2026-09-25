# Propuesta — 20260922-quality-integration-and-cli

## Problema
Los Changes 0-3 de v0.7 ya producen, en memoria o persistidos, todas las piezas de "calidad
verificable" que pedía el roadmap: `DataContract`/`ContractVersion`/`CompatibilityPolicy`
(`tools/datacontracts/core.py`), evaluación de contrato contra `profile.json`
(`tools/datacontracts/validation.py:774,848`), `ModelQualityPolicy`/`ObservedMetric`/
`BaselineReference` (`tools/modelquality/core.py`), evaluación determinista de política
(`tools/modelquality/validation.py:449`), y evidencia persistida + drift acotado
(`tools/qualityevidence/{core,evidence}.py`, `.harmessi/quality/<evidence_id>/manifest.json`,
`tools/qualityevidence/evidence.py:293,324,354,467`). Pero **nada de esto es invocable hoy**: no
existe ningún comando que un Lead, un metodólogo o CI puedan correr para validar un contrato,
evaluar una política o leer evidencia ya escrita; no existe ninguna función que compare dos
versiones de un `DataContract` y clasifique el cambio (`ContractVersion`/`CompatibilityPolicy` se
declararon explícitamente en Change 0 SIN esa lógica, dejándola "íntegramente" para este Change,
`openspec/changes/20260922-data-contracts-core/design.md:253-264`); `status`
(`tools/dsguard/status.py`) no muestra evidencia de calidad; e `impact preflight`
(`tools/dsimpact`) no tiene ninguna noción de qué consumidores podrían verse afectados por un
cambio de contrato. Sin este Change, v0.7 sigue siendo una biblioteca sin superficie de uso.

El riesgo central, señalado por el roadmap y esta invocación con la máxima prioridad, es que la
forma más simple de "conectar" calidad con el resto del sistema sea hacer que un resultado de
`FAIL` bloquee `readiness`/`promote` — exactamente la decisión 5 del roadmap, congelada, lo
prohíbe: **"Quality no es gate. Ningún resultado de v0.7 modifica readiness, promotion gates ni el
exit code de `status`/`project readiness`/`project promote`, ni muta el lifecycle... Convertir
quality checks en gates de promoción es cambio arquitectónico material → STOP para decisión
humana."** (`docs/roadmap/v0.7.md:96-101`). Este Change debe demostrarlo con tests, no solo
declararlo.

## Objetivo
Exponer las capacidades de v0.7 (contratos, políticas de calidad de modelo, evidencia y drift) a
través de comandos nuevos en el CLI existente `ds_guard.py` (`contract ...` / `quality ...`), sin
crear un cuarto patrón de hosting de CLI y sin comandos redundantes; agregar la clasificación
determinista de compatibilidad entre versiones de un `DataContract`
(`tools/datacontracts/evolution.py`, nuevo, aditivo); mostrar evidencia de calidad de forma
aditiva e informativa en `ds_guard.py status` (nunca en `tools/dsguard/status.py`, ver
`design.md` decisión 4); identificar consumidores potencialmente afectados por un cambio de
contrato reusando los primitivos ya públicos de `tools.dsimpact`, sin modificarlo; y demostrar con
tests reales que `project readiness`/`project promote`/`status` producen exactamente la misma
salida y el mismo exit code con y sin evidencia de calidad presente.

## Evidencia
- `docs/roadmap/v0.7.md:350-389` (Change 4 completo): objetivo, "CLI conceptual candidata"
  (`harmessi contract`/`harmessi quality`, nombres A DEFINIR en SDD), estado actual de los tres
  hosts de CLI ("hoy conviven `harmessi`... `ds_guard.py`... y CLIs de paquete... el SDD debe
  elegir el host sin agregar un cuarto patrón"), contract evolution (6 categorías exactas),
  impact preflight ("identificar consumidores potencialmente afectados... nunca afirmar que están
  rotos"), límite firme de la decisión 5.
- `docs/roadmap/v0.7.md:96-101` (decisión 5, cita textual reproducida arriba en "Problema").
- `docs/roadmap/v0.7.md:112-127` (reglas de arquitectura para v0.7): dirección de dependencias
  ("los paquetes de v0.7 pueden importar `dsguard.checks` y consumir `profile.json`...; `dsguard`,
  `ds_profile`, `dsimpact`, `reporting`... **no** importan los paquetes de v0.7, verificable con un
  test de neutralidad").
- `openspec/changes/20260922-data-contracts-core/design.md:253-264`: "La clasificación
  determinista real (comparar dos versiones de un `DataContract` y decidir `additive
  compatible`/`removal`/`required-field addition`/`type change`/`constraint tightening`/
  `constraint loosening`/`unknown / needs review`) es íntegramente del Change 4..., que
  consumirá estos tipos como entrada y salida de su propia función de clasificación
  (probablemente en un módulo aparte, p. ej. `tools/datacontracts/evolution.py`...)".
- `tools/datacontracts/core.py:494-537` (`ContractVersion`, sin `compare`/`diff`/`classify`),
  `tools/datacontracts/core.py:543-592` (`CompatibilityPolicy`, 6 campos `on_*` requeridos,
  `COMPAT_ACTIONS = ("block", "warn", "allow")` en `core.py:77`): forma exacta de entrada/salida
  que `classify_contract_change` debe consumir/producir.
- `ARCHITECTURE.md:137-154` (regla 7): "los módulos de la familia podrán importar `dsguard.checks`
  (para producir resultados `PASS`/`WARN`/`FAIL`/`N/A`)... pero nunca al revés: `dsguard`,
  `ds_profile`, `dsimpact`, `reporting`... no importan `tools/datacontracts`. Verificado por
  `tools/tests/test_v07_core_neutrality.py`."
- `tools/tests/test_v07_core_neutrality.py:36-45,175-192` (`PAQUETES_SIN_DATACONTRACTS`): el
  escaneo de neutralidad cubre los DIRECTORIOS de paquete (`tools/dsguard`, `tools/ds_profile`,
  `tools/dsimpact`, `tools/reporting`, `tools/providers`, `tools/routing`, `tools/fallback`,
  `tools/harmessi_bench`) — **no incluye** `tools/ds_guard.py` (el launcher de nivel superior) ni
  `tools/harmessi/cli.py`: evidencia real de que el launcher top-level SÍ puede importar los
  paquetes de v0.7 sin violar ninguna regla de neutralidad existente, a diferencia de cualquier
  módulo dentro de `tools/dsguard/`.
- `tools/ds_guard.py:792-799,802-825` (`_importar_dsimpact`/`cmd_impact_scan`): patrón YA
  establecido de subcomando delegado con import perezoso opcional (degrada con `return 3` si el
  paquete no está instalado en el stage actual), sin reimplementar lógica — el mismo patrón que
  este Change reutiliza para `contract`/`quality`.
- `tools/ds_guard.py:1163-1216,1588-1601` (`cmd_project_readiness`/`cmd_project_promote` +
  parser): ninguna referencia a `.harmessi/quality`, `tools.datacontracts`, `tools.modelquality`
  ni `tools.qualityevidence` en ninguna parte de estas funciones ni de
  `tools/dsguard/readiness.py` (leído completo) — confirma que la "no alteración" exigida por la
  decisión 5 ya se cumple estructuralmente hoy (nada las conecta); este Change debe PROBARLO con
  tests, no solo mantenerlo por omisión, y NO debe tocar ninguna de las dos funciones ni
  `tools/dsguard/readiness.py`.
- `tools/dsguard/status.py:1-30,484-513` (`evaluar_status`, docstring "Principios NO
  negociables"): orquesta 8 secciones fijas, solo lectura, "solo depende INCONDICIONALMENTE de
  módulos que viajan con cualquier instalación (`tools/dsguard/*`...)" y usa import perezoso
  opcional únicamente para `tools.harmessi.doctor`/`tools.ds_init.legacy` (`status.py:63-93`) —
  ninguno de los dos es un paquete de v0.7; agregar un tercer import perezoso de
  `tools.qualityevidence` violaría la regla 7/8/9 de `ARCHITECTURE.md` si viviera dentro de
  `tools/dsguard/status.py` (paquete cubierto por `test_v07_core_neutrality.py`), así que la
  integración con `status` debe vivir fuera de ese archivo (ver "Evidencia" del punto anterior y
  `design.md` decisión 4).
- `tools/ds_guard.py:94-121` (`cmd_status_unificado`/`cmd_status`): el subcomando `status` sin
  `--change-id` ya envuelve `status.evaluar_status(repo_root)` en el launcher top-level (no dentro
  de `tools/dsguard/status.py`), exit code 0 siempre salvo error de entorno — el punto de
  extensión aditiva correcto para mostrar evidencia de calidad sin tocar el módulo core.
- `tools/dsimpact/scan.py:56-88,158-222` (`_procesar_py`/`_procesar_notebook`/
  `_procesar_eliminado_o_renombrado`/`_construir_fuente`): SOLO `.py`/`.ipynb` (y archivos
  eliminados/renombrados) producen `targets_simbolos`/`targets_strings`/`targets_path`; un archivo
  `.json` modificado (la forma natural de persistir un `DataContract`) cae en `_procesar_otro`
  (`scan.py:188-206`) con targets vacíos — evidencia real de que `dsimpact scan` NO puede, tal
  cual, detectar cambios a nivel de campo de un contrato serializado en JSON: hace falta componer
  sus primitivos públicos de búsqueda con targets provistos manualmente (ver `design.md`,
  decisión 5), no su función `ejecutar_scan` basada en diff de Git.
- `tools/dsimpact/consumers_py.py:25` (`buscar_en_texto_python(texto, targets_simbolos,
  targets_strings)`), `tools/dsimpact/consumers_text.py:14,48` (`buscar_en_json(texto, targets)`,
  `buscar_en_texto_plano(texto, targets)`), `tools/dsimpact/git_source.py:96-108`
  (`listar_consumidores_candidatos(repo_root)`): las 4 funciones públicas que este Change compone
  desde `tools/ds_guard.py`, sin modificar `tools/dsimpact` y sin que `tools/dsimpact` importe
  `tools.datacontracts` (dirección única: `ds_guard.py` → `dsimpact`, ya establecida por
  `impact scan`).
- `tools/dsguard/checks.py:14-56` (`CheckResult`, `STATUS_*`, `KIND_*`): vocabulario que
  `classify_contract_change` reutiliza (regla 7 de `ARCHITECTURE.md` ya anticipa que los módulos
  de la familia, en Changes posteriores a Change 0, "podrán importar `dsguard.checks`").
- `tools/qualityevidence/evidence.py:354-421` (`build_drift_evidence`, pura, sin I/O) y ausencia
  de cualquier `write_drift_evidence`/`read_drift_evidence` en todo el archivo (grep completo de
  `^def `, `tools/qualityevidence/evidence.py`): `DriftEvidence` NO tiene, hoy, ningún mecanismo
  de persistencia propio (a diferencia de `QualityEvidenceManifest`, que sí tiene
  `write_manifest`/`read_manifest`, `evidence.py:293,324`) — evidencia real de que este Change no
  puede ofrecer "persistir un `DriftEvidence`" sin tocar `tools/qualityevidence/evidence.py`
  (fuera de alcance, ver abajo); el subcomando `quality drift` de este Change es de solo lectura/
  cómputo, sin escritura.
- `tools/harmessi/cli.py:1-27,279-291` (docstring + `construir_parser`/`main`): CLI acotado a
  `doctor`/`providers`/`routing`/`fallback` (confiabilidad multi-proveedor), sin ningún import de
  `dsguard`/`ds_profile`/`dsimpact` en todo el archivo — dominio conceptualmente distinto al de
  contratos/calidad de datos.
- `tools/reporting/cli.py:1-2` y `tools/ds_profile/cli.py`, `tools/dsimpact/cli.py:1-4`: los tres
  ejemplos reales de "CLI de paquete" (`python -m tools.<paquete>`) — ninguno integra con
  `status`/`impact`/`readiness`; cuando un paquete SÍ necesita esa integración (como `dsimpact`),
  el mecanismo real usado es un subcomando delegado en `ds_guard.py` (`impact scan`), no una
  cuarta CLI.
- `docs/roadmap/README.md` (Contrato de autonomía, citado igual que en Changes 1-3).

## Supuestos descartados
- Que el nombre exacto de los comandos deba ser literalmente `harmessi contract`/`harmessi
  quality` porque así aparece en el roadmap. Descartado: el propio roadmap dice "Los nombres
  exactos de comandos y dónde se alojan se definen en SDD" (`docs/roadmap/v0.7.md:362`) — es una
  CLI conceptual, no una decisión congelada (a diferencia de las decisiones 1 y 5, explícitamente
  marcadas como tales en `docs/roadmap/v0.7.md:4-5`). Se elige `ds_guard.py contract`/
  `ds_guard.py quality` con evidencia real (ver `design.md`, decisión 1).
- Que integrar con `status` signifique editar `tools/dsguard/status.py` (la lectura más literal
  de "status" en el roadmap). Descartado tras verificar que ese archivo está DENTRO del perímetro
  de `test_v07_core_neutrality.py`/reglas 7-9 de `ARCHITECTURE.md`: importar cualquier paquete de
  v0.7 ahí rompería la neutralidad verificada. La integración vive en `tools/ds_guard.py`
  (launcher top-level, fuera de ese perímetro), envolviendo la salida YA producida por
  `status.evaluar_status` sin modificarla (ver `design.md`, decisión 4).
- Que `classify_contract_change` deba producir un tipo de resultado nuevo (p. ej. un enum de 7
  categorías sin relación con `CheckResult`). Descartado: `CompatibilityPolicy` YA declara una
  acción (`block`/`warn`/`allow`) por categoría (`core.py:543-592`), que mapea 1:1 a
  `FAIL`/`WARN`/`PASS`; reusar `dsguard.checks.CheckResult` (permitido por la regla 7) da
  vocabulario uniforme con el resto de v0.7 y con `status`/reporting, en vez de inventar un
  quinto vocabulario de resultado (ver `design.md`, decisión 3).
- Que identificar "consumidores potencialmente afectados por un cambio de contrato" deba extender
  `tools/dsimpact/scan.py` (p. ej. enseñarle a extraer targets de un `.json` de contrato).
  Descartado: extender `dsimpact` es tocar un paquete de un Change anterior cerrado (v0.4) fuera
  del alcance de v0.7, y el propio roadmap solo pide "usar impact preflight para identificar
  consumidores... sin afirmar automáticamente que están rotos" — no pide que `dsimpact` entienda
  contratos. Se compone desde `ds_guard.py` con los primitivos públicos ya existentes de
  `dsimpact` (ver "Evidencia" y `design.md`, decisión 5), sin ninguna línea nueva en
  `tools/dsimpact/`.
- Que este Change deba agregar persistencia de `DriftEvidence` (`write_drift_evidence`) para que
  `quality drift` sea "completo". Descartado: eso exige modificar
  `tools/qualityevidence/evidence.py` (Change 3, cerrado), fuera de la única excepción aditiva
  permitida (un módulo NUEVO dentro de `tools/datacontracts`, ver "Alcance"). `quality drift` de
  este Change es de solo cómputo/lectura (dos `profile.json` de entrada, salida impresa); si se
  necesita persistir un `DriftEvidence` en el futuro, es una extensión aditiva de
  `tools/qualityevidence/evidence.py` decidida en un Change posterior — se documenta como nota
  abierta, no se implementa acá (ver `design.md`, "Riesgos").
- Que "convertir un `FAIL` de `classify_contract_change`/`validate_contract`/`evaluate_policy` en
  bloqueo de `project promote`" sería una mejora natural de este Change (más simple de
  "aprovechar" ya que la CLI ya tiene los resultados en memoria). Rechazado de plano: es
  exactamente el STOP material de la decisión 5 del roadmap (cita completa en "Problema"). Ver
  "STOP explícito" en `tasks.md` — no se implementa ni se sugiere como default bajo ninguna
  circunstancia sin decisión humana explícita posterior.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica.

## Alcance
- `tools/datacontracts/evolution.py` (nuevo, único archivo nuevo dentro de un paquete de un
  Change anterior, excepción explícitamente prevista por Change 0,
  `openspec/changes/20260922-data-contracts-core/design.md:253-264`): `classify_contract_change`
  y helpers privados de comparación de campos/constraints (ver `design.md`, decisión 3). Importa
  `tools.datacontracts.core` (sibling) y `dsguard.checks` (permitido por regla 7 de
  `ARCHITECTURE.md`); no importa `dsimpact`, `tools.modelquality`, `tools.qualityevidence` ni
  ningún otro paquete.
- `tools/datacontracts/tests/test_evolution.py` (nuevo).
- `tools/ds_guard.py`: subparsers `contract` (`validate`, `diff`, `impact`) y `quality`
  (`evaluate`, `evidence show`, `drift`), siguiendo el patrón exacto de `_importar_dsimpact`/
  `cmd_impact_scan` (import perezoso opcional por subcomando, degradación con `return 3` si el
  paquete no está instalado en el stage actual); extensión aditiva de `cmd_status_unificado`
  (resumen de evidencia de calidad, ver `design.md` decisión 4) SIN tocar
  `tools/dsguard/status.py`.
- `tools/tests/test_ds_guard_contract_quality_cli.py` (nuevo): smoke de los 6 subcomandos nuevos
  (texto y `--json`, exit codes).
- `tools/tests/test_v07_readiness_promote_status_no_alteration.py` (nuevo, ver `design.md`
  decisión 6 y "STOP explícito" de `tasks.md`): compara salida + exit code de
  `ds_guard.py project readiness`, `ds_guard.py project promote` y `ds_guard.py status` con y sin
  `.harmessi/quality/**/manifest.json` presente en un proyecto de prueba sintético.
- `tools/tests/test_v07_evolution_neutrality.py` (patrón `ast`, análogo a
  `test_v07_core_neutrality.py`/`test_v07_validation_neutrality.py`): imports permitidos de
  `tools/datacontracts/evolution.py` (`tools.datacontracts.core`, `dsguard.checks`, stdlib);
  dirección inversa (`dsguard`, `ds_profile`, `dsimpact`, `reporting`, `tools.modelquality`,
  `tools.qualityevidence`, `providers`, `routing`, `fallback`, `harmessi_bench` no importan
  `tools.datacontracts.evolution`).
- `tools/ds_init/manifest.py`: una entrada VERBATIM para `tools/datacontracts/evolution.py`
  (mismo `stage_minimo` que el resto de `tools/datacontracts`).
- `ARCHITECTURE.md`: una fila nueva en §2.1 para `tools/datacontracts/evolution.py` (texto exacto
  en `design.md`); nota aditiva en la regla 7 de §3 mencionando `evolution.py`; sin regla 10 nueva
  (ver `design.md`, decisión sobre `ARCHITECTURE.md`).
- `docs/roadmap/v0.7.md`: al cerrar el Change, tildar `[x] Change 4`.
- `openspec/changes/20260922-quality-integration-and-cli/verification.md` (al cierre).

Ver `tasks.md` para el desglose exacto de rutas autorizadas por invocación.

## Fuera de alcance
- Cualquier cambio a `tools/datacontracts/core.py`, `tools/datacontracts/validation.py`,
  `tools/modelquality/{core,validation}.py`, `tools/qualityevidence/{core,evidence}.py` (Changes
  0-3, cerrados e inmutables). `evolution.py` es la ÚNICA adición dentro de esos paquetes,
  explícitamente prevista por Change 0.
- Cualquier cambio a `tools/dsguard/status.py`, `tools/dsguard/readiness.py`, o a
  `cmd_project_readiness`/`cmd_project_promote` de `tools/ds_guard.py` — se leen, nunca se
  modifican; solo se agregan tests que prueban su comportamiento sin cambios.
- Cualquier cambio a `tools/dsimpact/*` — se reusan solo sus funciones públicas ya existentes
  desde `tools/ds_guard.py`.
- Cualquier cambio a `tools/harmessi/cli.py` ni a `tools/reporting/*` (no se elige ese host, ver
  `design.md` decisión 1; la integración con reporting es de uso — pasar un `evidence_ref` de
  `.harmessi/quality/` como fuente a `reporting.evidence.describe_source`, ya soportado hoy —, no
  de código).
- Persistencia de `DriftEvidence` (`write_drift_evidence`): fuera de alcance por requerir tocar
  `tools/qualityevidence/evidence.py` (ver "Supuestos descartados").
- Cualquier forma de que un resultado de `contract`/`quality` bloquee, condicione o altere
  `readiness`/`promote`/lifecycle/exit codes existentes (decisión 5 del roadmap, STOP material).
- Calcular métricas de modelo, entrenar modelos, monitoring continuo, scheduling, alertas,
  retraining automático, Model/Data Cards, Responsible AI (todos fuera de alcance de v0.7 entero,
  `docs/roadmap/v0.7.md:431-449`).
- Dependencias nuevas (decisión 8 del roadmap): solo stdlib + lo ya instalado.

## Holdout policy (condicional — solo cambios "sensible")
Aplica parcialmente, mismo razonamiento que Change 1/3: este Change SÍ puede leer archivos del
repo (contratos, políticas, `profile.json`, manifests de evidencia), pero nunca abre un dataset
crudo ni una columna de datos directamente.

- `contract validate`/`quality evaluate` leen `profile.json`/observaciones YA producidas por el
  proyecto — mismo criterio que Change 1/2: `validate_contract_against_profile_file` YA aplica
  `ds_profile.holdout_guard.verificar_permitido` internamente (`tools/datacontracts/
  validation.py:848` y `783-847`, leído en esta invocación); este Change NO reimplementa ese
  guard, solo invoca la función pública existente. `evaluate_policy` no tiene ninguna superficie
  de I/O (recibe objetos ya construidos en memoria, `ARCHITECTURE.md:156-166`).
- `quality drift` invoca `drift_from_profiles` (`tools/qualityevidence/evidence.py:467-529`), que
  YA aplica el mismo guard sobre AMBAS rutas de `profile.json` (confirmado en el docstring del
  módulo, leído en esta invocación: "Nunca lee un `profile.json` sin `verificar_permitido` ANTES
  de abrirlo..., simétrico y fail-closed"). Este Change pasa las rutas dadas por el usuario tal
  cual a esa función, sin abrir ningún archivo por su cuenta.
- `contract impact` lee archivos de código/config del repo (vía
  `dsimpact.git_source.listar_consumidores_candidatos`, que respeta `.gitignore` y nunca
  `git show` de contenido de datos) para buscar referencias textuales a un `contract_id`/nombre de
  campo — nunca abre un dataset, nunca usa el guard de holdout (no aplica: no son datos, son
  código/config, mismo criterio que `dsimpact scan` ya establecido en v0.4).
- `quality evidence show` lee únicamente manifests bajo `.harmessi/quality/` (metadata de
  evaluación generada por Harmessi, no datos ni holdout — mismo criterio que
  `qualityevidence.evidence.read_manifest`, que no aplica ningún guard porque no son datos).

Este Change no abre ningún dataset crudo, columna de datos ni holdout directamente en ningún
subcomando nuevo.

## Impacto en production-readiness (opcional)
Ninguno, por diseño y por decisión 5 del roadmap (cita completa en "Problema"). Este Change agrega
tests que DEMUESTRAN la ausencia de impacto (ver "Alcance",
`test_v07_readiness_promote_status_no_alteration.py`), en vez de solo declararla.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md` (SDD completo).

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md` (SDD completo).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-22
- Alcance aprobado: "Change 4 — quality-integration-and-cli (docs/roadmap/v0.7.md)"
- Versión de artefactos referenciada: esta versión de los 4 archivos (commit de este Change)
- Cita del contrato de autonomía: "Ejecutá autónomamente los Changes de docs/roadmap/v0.7.md ...
  Change 4 — quality-integration-and-cli ... audit acotado → SDD → validación contra
  roadmap/arquitectura → implementación → tests → reviewer → fixes → re-tests → verification →
  cierre → commit local (instrucción explícita del usuario, 2026-09-22, bajo el Contrato de
  autonomía de `docs/roadmap/README.md`)." (adaptada de la cita transcripta para Change 3 en
  `openspec/changes/20260922-quality-evidence-and-drift/proposal.md:243-249`, mismo contrato de
  autonomía vigente, aplicado ahora a Change 4). Cita textual, reproducida íntegra por ser el
  límite material de este Change: "Quality no es gate. Ningún resultado de v0.7 modifica
  readiness, promotion gates ni el exit code de `status`/`project readiness`/`project promote`,
  ni muta el lifecycle... Convertir quality checks en gates de promoción es cambio arquitectónico
  material → STOP para decisión humana." (`docs/roadmap/v0.7.md:96-101`, decisión 5).

## Motivo de rechazo
No aplica.

## Desacuerdo registrado
No aplica.
