# Spec — 20261006-sdd-parsers-and-guardrail-ownership

Cada `Rn` tiene criterio de aceptación verificable. Todo cambio es aditivo o más estricto; sin las sintaxis nuevas, el
comportamiento previo se conserva (salvo lo declarado en R9–R10, que son más estrictos y fail-closed).

## A. Primitiva compartida de resolución de aprobación (R1–R4)

**R1 — Primitiva única.** `dsguard.sdd.resolver_aprobacion_registrada(repo_root, change_id, artefacto, hash_esperado=None)`
devuelve un dict `{estado, detalle, entrada, hash_vigente}` con `estado ∈ {verified, stale, missing, unresolvable}`. Pasos
(los mismos de `cards.approvals`, R35 de Change 4): (1) `change_id`/`artefacto` con forma válida (`[0-9]{8}-[a-z0-9][a-z0-9-]*`;
nombre simple sin `/`, `\`, `..`, `:`, punto/espacio final, nombres reservados de Windows); (2) Change en
`openspec/changes/<id>` o `openspec/archive/<id>`; (3) `control.json` legible con lista `aprobaciones`; (4) existe una entrada
del artefacto (con ese `hash_esperado` si se dio); (5) esa entrada es la MÁS RECIENTE del artefacto (`_aprobacion_mas_reciente`),
si no ⇒ `stale`; (6) el archivo en disco (dentro del Change) conserva el hash (`hash_lf_v1`), si no ⇒ `stale`. Sin
`hash_esperado`, devuelve el `hash_vigente` de la última entrada (si verified). Solo lectura; nunca lanza.
**R2 — Sin segundo resolver.** `tools/cards/approvals.py` delega los pasos 2–6 en la primitiva (conserva su validación de forma,
`AnchorResolution` y metadatos informativos). Todos los tests de Change 4 (`test_approvals`, `test_integration_hooks`,
`test_discovery`) siguen verdes sin debilitarse.
**R3 — Sin store nuevo.** La fuente de verdad es `control["aprobaciones"]`.
**R4 — Trust model** idéntico al de Change 4: prueba una aprobación registrada y vigente, no identidad ni autoría.

## B. Checkpoints no circulares (R5–R14)

**R5 — Sintaxis canónica.** `- **<id>**: <resumen> — alcance: <a, b> — aprobacion: <change_id>/proposal.md@approved`. El proposal
NO contiene su propio hash. `@approved` significa «resolver contra la aprobación real registrada de ese artefacto»; nunca «confiar en el
archivo actual». La sintaxis `@<64 hex>` sigue siendo válida (R9–R10).
**R6 — Materialización.** Al aprobar `proposal.md` bajo `approval_mode: checkpoints`: se calcula el hash REAL (`hash_lf_v1`) del
proposal que se aprueba (el mismo de la entrada que se registra); para `change_id` == el Change propio, `@approved` se materializa a
ese hash; para otro `change_id`, se resuelve con la primitiva (`R1`) su aprobación vigente de `proposal.md` y se materializa su
`hash_vigente`, y si no es `verified` la aprobación del proposal se rechaza (exit 2, sin escribir, hallazgo
`CODE_PREAPPROVED_INVALID` ya existente). `control["decisiones_preaprobadas"]`
contiene SIEMPRE el hash concreto (nunca el literal `approved`), con la misma forma `PreApprovedDecision` actual; la materialización se
rehace en cada re-aprobación (reemplaza, no acumula).
**R7 — API.** `sdd.parsear_checkpoints_de_propuesta(texto, change_id=None, resolver_approved=None)` mantiene el retorno
`(checkpoints, hallazgos)`; para un bullet `@approved` invoca `resolver_approved(change_id_de_la_referencia) -> (hash|None, detalle)`;
sin resolver ⇒ hallazgo (nunca un checkpoint sin hash real). `validate_pre_approved` no se modifica.
**R8 — Verificación posterior.** `sdd.verificar_checkpoints(repo_root, control)` resuelve cada `decisiones_preaprobadas[*].approval_ref`
con la primitiva R1 y devuelve `[{summary, estado, detalle}]` con `estado ∈ {verified, stale, missing, placeholder, unresolvable}`.
`ds_guard status --change-id` (texto y `--json`, clave `checkpoints`) lo muestra; es informativo (no cambia exit codes).
**R9 — Legacy con hash real.** Un bullet `@<64 hex>` real se acepta como hoy; `verificar_checkpoints` lo resuelve como cualquier
otro (verified si coincide con la aprobación vigente, `stale`/`missing` si no). Sin migración automática.
**R10 — Legacy con 64 ceros.** Se acepta SINTÁCTICAMENTE (historia legible, la aprobación del proposal no se rechaza) pero NUNCA
cuenta como aprobado: `verificar_checkpoints` lo devuelve `placeholder` (y el hash cero no existe en `aprobaciones`, así que la
primitiva daría `missing`); `ds_guard approve` imprime un aviso `deprecated` por stderr con los ids afectados
(`sdd.checkpoints_con_placeholder_cero(texto)`); los Changes nuevos deben usar `@approved`.
**R11 — Cambio posterior.** Si el proposal cambia después de aprobar y no se re-aprueba, el checkpoint materializado queda `stale`;
re-aprobar rehace la materialización con el nuevo hash.
**R12 — Archivados.** La primitiva resuelve `openspec/archive/<id>`.
**R13 — Sin cambios** a `autonomy/core.py`, `policy.py`, `STOP_CATALOG`, `POLICY_TABLE`, `approval_mode` ni checkpoints de runtime.
**R14 — Aprobación sin sección** de checkpoints: comportamiento actual (no toca nada).

## C. Subset PEP 440 (R15–R24)

**R15 — Módulo.** `tools/dsguard/pep440_subset.py` (solo stdlib, distribuido por el instalador junto a `dsguard`): `parse_version(texto)`
→ objeto/tupla ordenable, `compare(a, b)`, `parse_range(texto)`, `satisfies(version, rango)`. `sdd.py` delega en él;
`_parsear_version`/`_parsear_rango_version`/`_comparar_versiones`/`_version_satisface_rango` desaparecen o quedan como alias finos.
**R16 — Subset soportado (documentado como «PEP 440 subset supported by Harmessi», no PEP 440 completo):**
`N(.N)*` con `(a|b|rc)N`, `.postN` y `.devN` opcionales, en ese orden (`1.0`, `1.0a1`, `1.0b2`, `1.0rc1`, `1.0.post1`, `1.0.dev1`, `1.0rc1.dev2`,
`1.0.post1.dev3`). Se acepta además un segmento local `+<alfanumérico/./-/_>` SOLO en la versión instalada/consultada (se ignora para
comparar, como PEP 440 con un especificador sin local). Normalización: minúsculas y espacios exteriores recortados. Los spellings alternativos de PEP 440 (`alpha`, `beta`, `c`, `pre`,
`preview`, `rev`, `r`, separadores `-`/`_`) NO se aceptan (fuera del subset: fail-closed). Fuera del subset ⇒ `ValueError` con mensaje claro (epochs `N!`, wildcards `.*`,
`~=`, `===`, direct references, locales en rangos, etc.).
**R17 — Ordering semántico** (nunca lexicográfico de strings): `1.0.dev1 < 1.0a1 < 1.0b1 < 1.0rc1 < 1.0 < 1.0.post1`;
`1.0.dev1 < 1.0` ; `1.0rc1.dev1 < 1.0rc1`; `1.0 == 1.0.0`; `2.9.0.post0 > 2.9.0` y `2.9.0.post0 < 2.9.1.dev0`; `1.0.post1.dev1 < 1.0.post1`.
**R18 — Rangos.** Operadores `>=`, `<=`, `>`, `<`, `==`, `!=` combinados con coma (como hoy). `==2.9.0.post0` satisface
`2.9.0.post0` (y `2.9.0.post0+local`), no `2.9.0`. `==1.0` satisface `1.0.0`. Semántica de `>`/`<` con pre/post-releases según el ordering R17 (sin las
reglas especiales de exclusión de pre-releases de PEP 440 §Version specifiers: documentado).
**R19 — Fail-closed.** Cualquier término o versión fuera del subset ⇒ `parsear_dependencias_preaprobadas` emite
`SDD-DEPENDENCY-PREAPPROVAL-INVALID` con el motivo; `clasificar_dependencia` clasifica como STOP `new_dependency` (comportamiento actual
ante «no parseable»).
**R20 — Compatibilidad.** Todos los rangos soportados hoy (`>=1.2,<2`, etc.) dan el mismo resultado; los tests existentes de dependency
preapproval/classify/install pasan sin cambios.
**R21–R24** reservadas.

## D. Drift semántico de guardrails (R25–R37)

**R25 — Módulo.** `tools/dsguard/guardrails_drift.py` (solo stdlib): `RUTAS_MUTABLES` (lista CERRADA), `normalizar(dict)`,
`comparar(actual, baseline) -> list[str]` (rutas que difieren fuera de la lista), `validar_autonomia_mutable(dict) -> list[dict]`.
**R26 — Lista cerrada de paths mutables** (allowlist mínima): `version` (nivel superior; solo su VALOR), `autonomy.mode`,
`autonomy.version`, `autonomy.budgets` (subárbol), `autonomy.limits` (subárbol). La existencia del objeto `autonomy` es mutable solo si
contiene exclusivamente esas claves. TODO lo demás es managed: `holdouts`, `data_raw`, `secretos_extra`, `write_scopes`, `excepciones`,
`autonomy.sealed_sources`, `autonomy.source_access`, cualquier clave desconocida o nueva a cualquier nivel.
**R27 — Semántica.** Doctor, para la entrada `.claude/guardrails.json` de `control["archivos"]` cuando el hash difiere: lee el JSON
actual y el baseline (la plantilla distribuida por el manifiesto: `raiz_repo_origen()/.claude/guardrails.json`), elimina de ambos los
paths mutables y compara por igualdad estructural (orden de claves y formato irrelevantes). Iguales ⇒ SIN drift. Distintos ⇒
`HARMESSI-DRIFT` WARN con las rutas de primer nivel que cambiaron. Hash igual ⇒ sin drift (camino rápido). JSON ilegible/no objeto,
baseline ilegible o cualquier excepción ⇒ `HARMESSI-DRIFT` WARN fail-closed (nunca «sin drift»); además `HARMESSI-GUARDRAILS-JSON` ya
reporta el JSON corrupto.
**R28 — Específico.** La regla aplica SOLO a `.claude/guardrails.json`; el resto de archivos VERBATIM mantiene la comparación por hash.
**R29 — Validez ≠ mutabilidad.** Nuevo check Doctor `HARMESSI-AUTONOMY-CONFIG`: valida los paths mutables con `autonomy.policy.parse_autonomy_policy`
(+ las 5 claves de `autonomy.budgets`: enteros positivos, bool excluido; claves desconocidas dentro de `budgets`/`limits` informadas):
cualquier hallazgo de valor inválido o de requisito insatisfecho de `mode: autonomous` (modo inválido, límites ausentes/no positivos,
versión baja/ inválida, `budgets`/`limits` no-dict) ⇒ ERROR con los códigos; claves desconocidas ⇒ WARN; sin sección `autonomy` o policy
válida ⇒ OK (`mode` efectivo informado: `autonomous` o `supervised`). Mutable no significa «cualquier valor es válido».
**R30 — Seguridad.** La lista cerrada NO permite cambiar silenciosamente: rutas protegidas (`holdouts`, `data_raw`, `secretos_extra`),
`write_scopes`, `excepciones` de holdout, `sealed_sources`/`source_access`, ni ningún otro campo no diseñado como user policy. Cualquier
duda ⇒ managed.
**R31 — E2E obligatorio.** Instalación limpia → editar `version`→2, `autonomy.mode: "autonomous"`, `autonomy.budgets`/`limits` válidos ⇒
Doctor sin `HARMESSI-DRIFT` sobre guardrails y `HARMESSI-AUTONOMY-CONFIG` OK; editar `holdouts`/`write_scopes`/`data_raw`/`autonomy.source_access`
o agregar una clave desconocida ⇒ `HARMESSI-DRIFT`; reordenar/reformatear el JSON ⇒ sin drift; `autonomy.mode: "turbo"` o `budgets` en 0 ⇒
sin drift pero `HARMESSI-AUTONOMY-CONFIG` ERROR; JSON roto ⇒ drift fail-closed + `HARMESSI-GUARDRAILS-JSON` FAIL.
**R32 — `autonomy.budgets` canónico y `limits` legacy** (Corrective A) se respetan sin reabrir su semántica; ambos mutables.
**R33 — Distribución.** `ds_init.manifest` agrega `tools/dsguard/guardrails_drift.py` y `tools/dsguard/pep440_subset.py` (VERBATIM, discovery, sin capabilities)
y los tests de manifiesto/instalabilidad se actualizan.
**R34 — Sin nuevo sistema de config; sin tocar `pathguard`/hooks** ni la protección de escritura de `guardrails.json`.
**R35–R37** reservadas.

## E. Compatibilidad e inercia (R38–R42)

**R38** Sin `@approved`, sin sufijos de versión y sin editar guardrails: comportamiento idéntico. **R39** `STOP_CATALOG`/`POLICY_TABLE`/`approval_mode`
sin cambios (tests de inercia existentes verdes); `autonomy/core.py` y `policy.py` no se modifican. **R40** Cards/Change 4 sin cambios de
contrato (R2). **R41** Sin dependencias nuevas. **R42** `docs/feedback/` y `.harmessi/` no se versionan.

## Tests requeridos (mínimo)
Checkpoints: sintaxis nueva sin hash propio; approve materializa hash real (= entrada registrada); resolución verified; approval ausente
(otro Change sin aprobación); proposal cambiado ⇒ stale; legacy hash real; 64 ceros ⇒ placeholder (no aprobado, aviso, no rechaza);
Change archivado; `@approved` sin resolver ⇒ hallazgo; re-aprobación rehace; compatibilidad cards/approvals. Dependencias: exacta normal;
`.postN`; `rcN`; `.devN`; `aN`/`bN`; ordering R17; rangos; local solo en instalada; malformado/fuera de subset fail-closed (epoch, wildcard,
`~=`, vacío, `1..2`); regresión de rangos existentes; `clasificar_dependencia`. Guardrails: baseline limpio; `mode`/`budgets`/`limits`/`version` ⇒
sin drift; reorder/format ⇒ sin drift; valor inválido ⇒ AUTONOMY-CONFIG ERROR; clave managed (`holdouts`, `write_scopes`, `data_raw`,
`source_access`, desconocida) ⇒ drift; JSON roto ⇒ fail-closed; otro VERBATIM sigue por hash; E2E con instalación real.
