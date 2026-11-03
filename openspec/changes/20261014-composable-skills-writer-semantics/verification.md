# Verificación — 20261014-composable-skills-writer-semantics

## Resumen
Change 4 de v0.10: contrato de skills componibles (solo contrato, sin skills nuevas) y semántica de writers (ownership disjunto, continuaciones, `SDD-ESTADO-DIVERGENTE`). Implementado con instancias de `python-data-engineer` de ownership disjunto; el Lead no escribió implementación. Sin intervenciones de emergencia ni archivos self-governing tocados.

## Qué entrega
- `tools/dsguard/skill_contract.py` y `tools/dsguard/ownership.py`; `sdd.chequear_estado_divergente`.
- `ds_guard ownership check`, integración en `ds_guard validate`, `session start --max-continuaciones` (1–5, default 1) expuesto en `session status`.
- Doctor `HARMESSI-SKILL-CONTRATO` (WARN, nunca FAIL; módulo ausente => WARN).
- Plantilla `templates/skill.md`, entradas de manifest (plantilla + 2 módulos).
- Docs: methodology §14/§23-15/§27–§32, SKILL.md, sdd.md, verificador.md, agentes con bloque de turnos y `ESTADO-AGENTE`, ARCHITECTURE §7.2, roadmap.
- No cambió: `maxTurns` 12/16/8/4, default `max_continuaciones_por_subagente = 1`, 90 min y semántica wall-clock, hooks (incluido `hook_presupuesto.py`), pathguard, scope/amendments, trust tiers, hashing managed. No se creó ninguna skill componible (ni `domain-modeling`, `GLOSSARY.md`, `tdd`). `ml-engineer` no existe.

## Evidencia obtenida
- Regresión relevante (35 módulos de test: scope, amendments, approvals, session/budgets/remediation/efficiency, pathguard/hook_rutas, Doctor, manifest/paridad, boundaries, skill methodology y los tests nuevos): 1218 tests OK (skipped=8), 1541 s, corrida posterior a los fixes del ciclo 1 (la corrida previa a los fixes dio 1205 OK).
- Tras los fixes menores del ciclo 2, los 6 módulos afectados (test_ownership, test_skill_contract, test_sdd_estado_divergente, test_skill_methodology, test_architecture_boundaries, test_doctor_skill_contract): 168 tests OK.
- `ds_guard validate` del propio Change: sin hallazgos. `ds_guard ownership check` sobre el `## Ownership de writers` real de este `tasks.md`: sin hallazgos (dogfooding).
- Censo de `SDD-ESTADO-DIVERGENTE` sobre los Changes históricos: 0 divergencias (57/57 al momento del audit; cubierto por `TestCensoRepoReal`).
- `python -m tools.ds_init.check_manifest_parity`: las rutas VERBATIM del manifest existen.
- Reviewer `data-science-reviewer`:
  - Ciclo 1: llegó a 16 turnos sin informe (truncamiento real); se lo reanudó UNA vez como continuación del mismo ciclo (no ciclo nuevo) y entregó informe parcial: 0 bloqueantes, 3 importantes (I1 sección de ownership malformada fallaba abierta; I2 mensaje de `SDD-ESTADO-DIVERGENTE` podía legitimar un salto de estados; I3 contradicción «Lead no edita» vs «Lead actualiza ownership») y menores M1–M9. Se corrigieron I1–I3, M1, M4, M5, M6, M7, M8.
  - Ciclo 2: 0 bloqueantes, 0 importantes, I1–I3 resueltos; menores aplicados: encabezado de ownership no canónico o fence sin cerrar => ilegible, prosa «Ninguna skill cargada» ignorada, tests de `ESTADO-AGENTE` y de la frase de I3.
  - Total: 2 ciclos de reviewer + 1 continuación técnica.
- H1 (hook `subagent_type` vs `name`): UNCONFIRMED. No apareció un payload real de `Agent`/`SendMessage`; el hook quedó intacto; T8a/T8b omitidas; deuda verificada solo con tests sintéticos.
- Intervenciones de emergencia: ninguna. Sesión `s1` (480 min) sin vencer.

## Fingerprint de dataset/artefacto
No aplica (sin datasets).

## Diferencias contra la spec
- R21 condicional no ejecutada (sin payload real).
- R19 `ESTADO-AGENTE` está cubierto por tests en agentes, SKILL.md y methodology; `sdd.md` describe la continuación sin repetir la marca.
- `sdd.md.tmpl` ya estaba desfasado de `sdd.md` por cambios previos; no se sincronizó, solo se aplicaron las mismas ediciones.
- Desvíos del plan de ownership: documentados en `## Historial de ownership` de `tasks.md`.

## Limitaciones
- El ownership se valida antes de delegar; no hay hook por instancia ni atribución post-hoc de ediciones.
- Las continuaciones son cooperativas (H1 sin confirmar).
- Protocolo self-governing y emergencias son contractuales.
- `SDD-ESTADO-DIVERGENTE` no autentica `control.json`.
- Deuda de sesión: 90 min triplicado, sin warning anticipado ni pausa por T1.
- `.ds_init/control.json` se regenera en Change 6.

## Pendientes derivados
- `validate` calcula `alcance_efectivo` aunque no haya sección de ownership y, con cadena de scope inválida, emite una cascada de `OWNERSHIP-FUERA-DE-ALCANCE`.
- El mensaje del hook dice «la continuación automática permitida» en singular aunque el tope sea configurable (hook intacto por H1).
- La nomenclatura «ownership» (5 vías de instalación vs writers) puede confundir.
- Algunos asserts de tests de contenido comparan cadenas literales (frágiles ante reescrituras).
- Sin test de CLI para sufijo/duplicada/rol inválido (cubiertos en `test_ownership.py`).

## Resultado final
Change 4 cumple los criterios de M1–M7 y la spec; listo para Change 5; sin push.
