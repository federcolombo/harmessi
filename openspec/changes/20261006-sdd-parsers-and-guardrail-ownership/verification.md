# Verificación — 20261006-sdd-parsers-and-guardrail-ownership

## Resumen ejecutivo
Corrective B de v0.9 (feedback real de Harmessi 0.8.0, hallazgos a, c y d). Cierra: (a) checkpoints de negocio autorreferenciales
(`proposal.md@sha256(proposal.md)`), (d) versiones con sufijos PEP 440 rechazadas en dependencias pre-aprobadas y (c) falso
`HARMESSI-DRIFT` al activar `autonomous` en `.claude/guardrails.json`. SDD aprobado por hash el 2026-10-06 con la autorización
humana anticipada. Todas las ejecuciones pasaron por el runtime gobernado (`ds_guard exec pytest`, aprobado con `exec approve`).
No incluye `ds_profile` (Corrective C) ni Change 5.

## Qué entrega
- **Checkpoints no circulares.** Sintaxis canónica `aprobacion: <change_id>/proposal.md@approved`. `ds_guard approve proposal.md`
  lee el archivo UNA vez (bytes), calcula el hash real con el mismo algoritmo que `core.hash_lf_v1` y lo usa para la entrada de
  `aprobaciones` y para materializar los `@approved` en `control["decisiones_preaprobadas"]` (nunca queda el literal). Para otro
  Change referenciado se usa la primitiva de aprobación vigente; si no está `verified` la aprobación se rechaza (exit 2, sin escribir).
  `@<64 hex>` legacy se acepta como antes; 64 ceros se acepta SINTÁCTICAMENTE pero nunca cuenta como aprobado (aviso `deprecated`;
  `verificar_checkpoints`/`status` lo muestran `placeholder`; la primitiva nunca devuelve `verified` para un hash cero).
- **Una sola primitiva de aprobación vigente.** `sdd.resolver_aprobacion_registrada` (Change en `changes/` o `archive/`, `control.json`,
  entrada artefacto+hash, la más reciente, hash en disco, forma y portabilidad) la comparten `tools/cards/approvals.py` (que conserva
  `AnchorResolution`, metadatos y la validación de forma de Cards) y los checkpoints (`verificar_checkpoints`, mostrado en `ds_guard status`,
  texto y `--json` clave `checkpoints`). Sin segundo resolver ni store; la definición de «no portable» también es única
  (`sdd.artefacto_no_portable`).
- **Subset PEP 440** (`tools/dsguard/pep440_subset.py`, solo stdlib, distribuido por el instalador): `N(.N)*` con `aN/bN/rcN`, `.postN`,
  `.devN`, `+local` solo en la versión consultada; ordering semántico (`1.0.dev1 < 1.0a1 < 1.0b1 < 1.0rc1 < 1.0 < 1.0.post1`,
  `1.0 == 1.0.0`, `2.9.0.post0 > 2.9.0`); rangos `>= <= > < == !=`; fail-closed fuera del subset (epochs, wildcards, `~=`, `===`,
  spellings alternativos, separadores `-`/`_`, locales en rangos, dígitos no ASCII). `==2.9.0.post0` funciona contra la instalada
  `2.9.0.post0` (y con `+local`). Documentado como «PEP 440 subset supported by Harmessi», no PEP 440 completo ni `packaging`.
- **Drift semántico de guardrails** (`tools/dsguard/guardrails_drift.py` + Doctor): lista CERRADA de paths mutables (`version`,
  `autonomy.mode`, `autonomy.version`, `autonomy.budgets`, `autonomy.limits`); el resto (holdouts, data_raw, secretos_extra,
  write_scopes, excepciones, sealed_sources, source_access y cualquier clave desconocida) sigue marcando `HARMESSI-DRIFT`. Formato/orden del
  JSON irrelevantes; JSON ilegible o baseline no confiable ⇒ drift fail-closed. Regla SOLO para guardrails (el resto de VERBATIM sigue por hash).
  Nuevo `HARMESSI-AUTONOMY-CONFIG`: valida los valores mutables con `parse_autonomy_policy` (inyectado por Doctor; `guardrails_drift` no importa
  autonomy) y las claves de `budgets`; valores inválidos ⇒ ERROR, claves desconocidas ⇒ WARN, válido ⇒ PASS con el modo efectivo.
- Documentación: ARCHITECTURE §6.2 y roadmaps (v0.9 Corrective B; v0.10 deuda «Guardrails: re-adopción y customización de campos managed»).
- Autonomía intacta: sin cambios a `autonomy/core.py`, `policy.py`, `STOP_CATALOG`, `POLICY_TABLE`, `approval_mode` ni al runtime.

## Ejecuciones reales (runtime gobernado)
Dirigida (tests nuevos + los directamente afectados): primera corrida 88 passed/1 failed (detalle de `comparar` por sub-clave, corregido);
tras fixes del ciclo 1: **195 passed, 1 skipped, 67 subtests, 0 failed**.

Regresión relevante en lotes SECUENCIALES (exit code real del `ExecutionRecord`; lote 1 incluye tests de dsguard/sdd, approvals/checkpoints,
autonomy-neutralidad, manifest/instalabilidad e inercia):

| Lote | Suite | Resultado |
|---|---|---|
| 1 | `tools/tests` | 1465 passed, 7 skipped, 4 failed (ver abajo) |
| 2 | modelquality, qualityevidence, datasources, datacontracts | 511 passed |
| 3 | autonomy, leadrun | 260 passed |
| 4 | `tools/cards/tests` (incluye ApprovalRef de Change 4) | 1230 passed, 34 skipped |
| 5 | `tools/ds_init/tests` (manifest/installer) | 180 passed |
| 6 | `tools/harmessi/tests`, `tools/reporting/tests` (Doctor/drift/reporting) | 1024 passed, 3 skipped |

Los 4 fallos del lote 1 (`test_ds_guard_usuario_guard::TestGuardaCableadaEnLos5Handlers` ×4) son un artefacto de una edición de
`ds_guard.py` hecha por el Lead MIENTRAS corría el lote (`inspect.getsource` lee el archivo ya modificado con los números de línea del
módulo importado antes): re-ejecutado el archivo, **7 passed**. Además, sobre el estado FINAL del código se re-ejecutaron los 18 archivos de
`tools/tests` que ejercen `ds_guard`/approve/checkpoints/scope/drift/cards-CLI: **346 passed, 1 skipped, 0 failed**.

**Total único (sin doble contar re-runs):** 1469 (lote 1 incl. los 4 re-ejecutados) + 511 + 260 + 1230 + 180 + 1024 = **4674 passed**,
44 skipped (7 + 0 + 0 + 34 + 0 + 3), **0 failed** al cierre. La re-ejecución de 346 es confirmación del estado final y no se suma.

## Proceso de revisión (2 ciclos, máximo)
- **Ciclo 1** (2 revisores): 0 bloqueantes. Importantes: (I1 guardrails) baseline degenerado cuando el destino es el propio repo de Harmessi (la
  plantilla ES el archivo, el drift semántico habría dado «sin drift») ⇒ vuelve al WARN por hash; (I2/I3) `guardrails_drift` importaba
  `autonomy` por `importlib` (evasión del test de neutralidad e import de código del proyecto si el cwd tenía un `autonomy/`) ⇒ el parser se
  inyecta desde Doctor, que importa primero `tools.autonomy.policy` y exige que el archivo caiga dentro de la raíz de Harmessi; (I1 versiones)
  los límites exclusivos dejaban pasar pre-releases (`<2` aprobaba `2.0rc1`) ⇒ se implementó la regla de PEP 440 para `<V` y `>V` (más estricta).
  Menores: `normalizar` derivado de `RUTAS_MUTABLES`, modo efectivo desde la policy, TOCTOU de lectura de `proposal.md`, `hash_proposal` inicializado,
  duplicación de «no portable» (ahora una sola definición), hash cero en la primitiva, dígitos no ASCII, `descripcion` en el manifiesto, tests E2E
  faltantes.
- **Ciclo 2:** 0 bloqueantes. Verificó la regla de límites exclusivos, el orden y estados de la primitiva/`cards.approvals`, que el hash inline de
  `cmd_approve` es idéntico a `core.hash_lf_v1`, y que Doctor/`guardrails_drift` no dejan pasar un cambio managed. Menores cerrados: texto
  engañoso del resumen de drift, relectura redundante de `proposal.md`, tests de `limits` con clave extra (WARN) y `budgets` anidado (ERROR).

## Precisiones por encima del spec aprobado (el spec no se editó; todas más estrictas)
- Límites exclusivos con la regla de exclusión de PEP 440 para pre/post-releases de la misma release (el spec R18 declaraba no implementarla).
- `cmd_approve` parsea `proposal.md` desde el texto normalizado (BOM y CR/CRLF → LF) del que sale el hash; el hash de la entrada registrada deja de
  releerse del disco.
- Doctor: caso «destino == repo origen» y parser de policy confinado a la raíz de Harmessi (fail-closed si no se puede cargar).
- La primitiva devuelve `missing`/`unresolvable` para hashes de 64 ceros y valida `hash_esperado`.
- `guardrails_drift.validar_autonomia_mutable` recibe `parse_policy` inyectado (el spec no fijaba la firma).

## Limitaciones conocidas y deuda (no bloqueantes)
- **Personalizar `holdouts`/`data_raw`/`secretos_extra`/`write_scopes`/`excepciones`/`autonomy.sealed_sources`/`source_access` sigue marcando
  `HARMESSI-DRIFT`** (decisión de seguridad: allowlist mínima). No hay comando de re-adopción; deuda registrada en v0.10.
- La baseline es la plantilla del manifiesto del Harmessi que ejecuta Doctor: si la plantilla cambia entre versiones, el efecto es un drift
  conservador (WARN), nunca un falso negativo.
- `HARMESSI-DRIFT` no se emite si solo cambiaron rutas mutables; el PASS de drift lo aclara («guardrails.json se compara semánticamente»).
- Claves desconocidas dentro de `autonomy.budgets`/`limits` (rutas mutables) producen WARN en `HARMESSI-AUTONOMY-CONFIG`, no ERROR ni drift.
- `RESERVADOS_WINDOWS` no cubre `conin$`/`conout$`/superíndices; no explotable porque el artefacto debe existir dentro del Change.
- `<1.0.post1` rechaza `1.0.post1.dev1` (más estricto que PEP 440); `1.0RC1` se normaliza a minúsculas para clasificar pero `dependency install`
  compara la versión instalada por igualdad de string (falso `version_no_coincide` posible con mayúsculas; solo advertencia).
- Nadie en producción consume `decisiones_preaprobadas` para decidir (el llamador de `resolve_methodological_decision` debe armar la lista);
  este Change expone la verificación vía `status`, sin cambiar el runtime de autonomía.
- `core.autocrlf` avisa conversión a CRLF al commitear (deuda v0.10 LF/CRLF).
- v0.10: approval-origin authenticity, LF/CRLF hashing, mid-Change authorized scope amendment UX, composable skills/domain-modeling, one-writer,
  guardrails re-adopción. Corrective C (`ds_profile`) pendiente y NO abierto; `docs/feedback/` y `.harmessi/` sin versionar.

## One-writer
Tres instancias `python-data-engineer` en paralelo con propiedad de archivos disjunta y explícita (W-A `sdd.py`/`pep440_subset.py`; W-B `ds_guard`
approve/status y `cards/approvals.py`; W-C `guardrails_drift`/Doctor/manifest). El Lead editó directamente, tras terminar los writers,
`pep440_subset.py` (regla de límites exclusivos), `guardrails_drift.comparar` (detalle por sub-clave), `approvals.py` (uso de la definición única),
`ds_guard.py` (relectura redundante), `doctor.py` (texto) y tests menores, sin solapes concurrentes.

## Resultado final
Corrective B completo y verde. Sin STOP nuevos; autonomía/runtime intactos. Listo para cierre.
