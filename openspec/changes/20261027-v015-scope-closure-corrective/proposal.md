# Propuesta — 20261027-v015-scope-closure-corrective

## Problema
El protocolo de cierre de v0.15 tiene tres defectos que impiden cerrar formalmente C4/C5/C6 (y por lo tanto publicar v0.15.0):

- (A) Atribución del cierre. `archivos_tocados_desde_baseline` compara el `baseline.commit` del Change contra el working tree. Un Change viejo en `en_verificacion` hereda todos los archivos de los Changes posteriores y el gate de cierre lo bloquea por trabajo ajeno.
- (B) Edición humana protegida. C4 requirió una edición humana explícita de `.claude/settings.json` (hooks SubagentStart/Stop). Esa ruta es Protected y no puede autorizarse en `scope amend`; hoy no existe un camino gobernado para que el cierre reconozca una edición humana legítima, y el gate bloquea.
- (C) Límite T1 de 120 caracteres. `cmd_scope_amend` rechaza ("demasiadas rutas") toda enmienda cuya cadena de acción no cabe en 120 caracteres, aunque la ligadura real de la confirmación ya es el hash canónico completo del plan. Una enmienda de ≥6 rutas exactas (la que necesita C6) no se puede ejecutar.

## Objetivo
Corregir el protocolo de cierre con un único Change correctivo pre-release (ventana de cierre por frontera git, atestación humana T1 de cambios Protected, acción T1 compacta), sin debilitar Protected, sin globs anchos y sin cambiar el significado de T0/T1.

## Evidencia
- `tools/dsguard/scope.py:30-53` `archivos_tocados_desde_baseline`: `repo_mod.diff_name_status(repo_root, baseline_commit)` = diff contra el working tree, sin frontera superior.
- `tools/dsguard/scope.py:109-214` `evaluar_alcance`: une `list_dirty_files` (l.155) con `archivos_tocados_desde_baseline` (l.159), y emite `ALCANCE-RUTA` por cada ruta fuera de alcance (l.192); `CODIGOS_INFORMATIVOS` (l.221) es la lista cerrada de hallazgos no bloqueantes.
- `tools/dsguard/sdd.py:1397-1402` `_ALCANCE_RUTAS_PROTEGIDAS` (guardrails.json, settings.json, settings.local.json, data/raw/x): impide autorizarlas en el alcance; se conserva.
- `tools/ds_guard.py:4717` `_LIMITE_ACCION_T1 = 120`; `:4720-4722` `_accion_scope` concatena todas las rutas; `:4911-4925` y `:4940-4945` `cmd_scope_amend` rechaza si no cabe; `:4938` ya liga la confirmación a `hash_binding = scope_amendments.hash_diff(...)`.
- Simulación de ventanas (frontera = baseline del sucesor más cercano): baselines C4(173b54c) -> C5(dc8bb19) -> C6(4b0c99a) -> C7(c6336b0). Resultado: C4 deja solo `.claude/settings.json` fuera de alcance; C5 deja 0; C6 deja 6 rutas (control.json/tasks.md/verification.md de runtime-observability y evidence-privacy-hardening, escritas por c6336b0).
- Los `creado_utc`/`transiciones` de C4/C5/C6 se solapan (C5 se creó antes de que C4 llegara a `en_verificacion`), por lo que el orden temporal de control.json no sirve; la ascendencia git de los baselines sí es una cadena.

## Supuestos descartados
- "El orden por timestamps de control.json identifica el Change sucesor": falso (solape verificado).
- "El límite de 120 caracteres protege la integridad de la confirmación": falso; solo limita el texto mostrado, la ligadura es el hash canónico completo.
- "Se puede resolver C4 autorizando `.claude/settings.json` por enmienda": no, Protected lo impide y no cambia.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica.

## Alcance
- Ventana de cierre por Change: `baseline.commit` hasta el baseline del sucesor más cercano (ascendencia estricta con `git merge-base --is-ancestor`, mínimo `git rev-list --count`, desempate por `change_id`); sin sucesor, HEAD; fail-closed al comportamiento actual si no resuelve.
- Atestación humana de cambio protegido: `protected-attestations.jsonl` append-only con cadena de hashes, módulo `tools/dsguard/protected_attestation.py`, comando `ds_guard scope attest-protected` con T1 real, integración en `evaluar_alcance`/gate de cierre, nuevo archivo en superficies Protected de pathguard y skill_contract.
- Acción T1 compacta determinista para `scope amend` cuando la acción completa excede 120; se elimina el rechazo "demasiadas rutas".
- Tests, manifest/inventario de contratos, documentación y verificación con dry-run real sobre C4/C5/C6.

## Fuera de alcance
- Features nuevas, PKI o firma criptográfica de usuarios, cambios en el significado de T0/T1 o de `console_confirmed`.
- Reescribir el lifecycle de Changes ni editar estados/control.json a mano.
- Cambios de comportamiento de producto.
- Escritura de archivos Protected por agentes; autorizar `.claude/settings.json` o cualquier ruta Protected; exención general de Protected.
- La enmienda de scope de C6 y la atestación de C4 son acciones humanas posteriores, no parte del código de este Change.

## Holdout policy (condicional — solo cambios "sensible")
No aplica: no hay datos ni holdouts.

## Impacto en production-readiness (opcional)
Bloquea la publicación de v0.15.0 hasta cerrar este Change.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver spec.md.

## Decisión técnica (design-lite — solo SDD abreviado)
Ver design.md.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado
- tools/dsguard/scope.py
- tools/dsguard/protected_attestation.py
- tools/dsguard/pathguard.py
- tools/dsguard/skill_contract.py
- tools/dsguard/repo.py
- tools/ds_guard.py
- tools/ds_init/manifest.py
- tools/ds_init/tests/test_manifest.py
- tools/tests/test_scope.py
- tools/tests/test_scope_amendments.py
- tools/tests/test_pathguard.py
- tools/tests/test_skill_contract.py
- tools/tests/test_scope_closure_window.py
- tools/tests/test_protected_attestation.py
- tools/tests/test_scope_amend_compact_t1.py
- docs/contracts/inventory.json
- tools/tests/test_v013_contract_inventory.py
- ARCHITECTURE.md
- docs/cli-reference.md
- docs/security-and-trust.md
- docs/roadmap/v0.15.md
- docs/roadmap/v0.15-debt-matrix.md
- openspec/changes/20261027-v015-scope-closure-corrective/**

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
