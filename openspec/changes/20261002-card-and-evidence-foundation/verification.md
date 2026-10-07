# Verificación — 20261002-card-and-evidence-foundation

## Resumen ejecutivo
Change 0 de v0.9: contrato base de Cards respaldadas por evidencia en `tools/cards/` (solo stdlib), sin
ninguna Card concreta. SDD aprobado por hash el 2026-10-02 con O1–O3 resueltas (unión estricta
`declared`/`anchored`; sin ruta canónica de Cards; fuera del manifest hasta Change 4). Todas las
ejecuciones pasaron por el runtime gobernado (`ds_guard exec pytest`), aprobadas con el subcomando
`exec approve` del corrective Change `20261002-exec-approval-registration` (commit `c49a7e4`).

## Qué entrega
- `core.py`: `EvidenceRef` (puntero con `content_sha256` obligatorio, sin payload), `HumanAttestation`
  (unión estricta: `declared` sin `approval_ref`; `anchored` con `approval_ref` estructuralmente válido,
  sin afirmar verificación), `Claim`, `Requirement`, `CardEnvelope` (sin campo `status`), `validate_card`,
  serialización determinista (`canonical_json`/`content_sha256` idénticos a `datasources`), `CODES`.
- `assess.py`: `Resolution`, estados derivados evidencia → requisito → Card con
  `PRECEDENCIA_CARD = (invalid, stale, incomplete, complete)`, `evaluate`, `evaluate_file`,
  `file_sha256_resolver`, `a_check_results`, `read_card`/`write_card` por ruta explícita.
- Arquitectura: regla 13 y §8 de `ARCHITECTURE.md`; nota de progreso en `docs/roadmap/v0.9.md`.
- Inerte: ningún cambio en `ds_guard.py`, manifest, Doctor, capabilities, autonomy ni `STOP_CATALOG`
  (test `test_v09_cards_inert.py`).

## Ejecuciones reales
Corrida dirigida (`tools/cards/tests` + `test_v09_cards_{neutrality,parity,inert}`): primera corrida
330 passed, 1 skipped, 853 subtests; tras los fixes del reviewer: **339 passed, 1 skipped, 859 subtests,
0 failed**.

Regresión relevante, lotes SECUENCIALES (exit code real del proceso pytest leído del `ExecutionRecord`):

| Lote | Suite | Resultado | pytest exit |
|---|---|---|---|
| 1 | `tools/tests` | 1064 passed, 6 skipped, 378 subtests | 0 |
| 2 | `tools/ds_init/tests` | 134 passed | 0 |
| 3 | `tools/datasources/tests` | 133 passed | 0 |
| 4 | `tools/autonomy/tests` | 145 passed, 246 subtests | 0 |
| 5 | `tools/leadrun/tests` | 96 passed, 15 subtests | 0 |
| 6 | `tools/cards/tests` (5 archivos) | 288 passed, 1 skipped, 535 subtests | 0 |

**Agregado: 1860 passed, 7 skipped, 0 failed, 1174 subtests passed; 6 lotes.** Los 3 tests v09 de repo
están contados una sola vez (en el lote 1). Adicional tras editar `ARCHITECTURE.md`:
`test_architecture_boundaries.py` 2 passed. Reintentos por memoria: 1 (un intento previo que combinaba
todas las suites en un solo proceso fue detenido por el sistema por presión de memoria; no fue un fallo
de tests y se reemplazó por los lotes secuenciales; no hubo ningún FAIL real).

## Proceso de revisión (ciclo 1 de máximo 2)
Reviewer: 0 bloqueantes, 2 importantes, 4 menores; los 12 puntos de foco cumplen.
- Importante 1: `validate_approval_ref` lanzaba `TypeError` con claves de tipos mixtos → ordena con
  `key=repr`; tests nuevos. 
- Importante 2: `revision_id` declarado ≠ recomputado (o pin malformado, o `status` en el archivo) se
  rechazaba con `CardError` pero no era un `card_status` evaluable → se agregó `evaluate_file`, que
  devuelve `card_status == invalid` con el hallazgo y sin invocar resolvers; `read_card` sigue lanzando.
  Documentado en los docstrings.
- Reuso evaluado: no se importan tipos de v0.6–v0.8 para preservar la neutralidad (regla 13); la
  duplicación de helpers sigue el patrón del repo y tiene tests de paridad.
- No hizo falta ciclo 2.

## Interpretación de «hash mismatch»
Pin `content_sha256` malformado o `revision_id` declarado ≠ recomputado → `invalid`; hash resuelto
distinto del pin (formato válido) → evidencia `stale` (R28 del SDD aprobado).

## Límites, limitaciones y deuda (no bloqueantes)
- `HumanAttestation.reference` con forma de id aún no se valida contra las evidencias de la Card.
- `body`, `extensions` y `approval_ref` son `dict` mutables dentro de dataclasses frozen (los hashes
  se recomputan siempre; hay una ventana validar-y-luego-mutar).
- `CARD-REQUIREMENT-EMPTY` se reutiliza para una Card vacía sin requisitos.
- Un `PASS` puede coexistir con `WARN` en una misma evaluación (requisito `recommended` no satisfecho o
  evidencia `stale` con Card `complete`).
- `anchored` es estructural: la verificación real del `ApprovalRef` contra `control.json`/ledger es
  Change 4. Las aprobaciones de Harmessi son declaraciones registradas, no firmas ni prueba de autoría
  (deuda v0.10 «Approval origin / human authorization authenticity»).
- Para Change 4 (requisitos preservados del audit): `data_cards`/`model_governance` no pueden agregarse a
  `CAPABILITIES_CONOCIDAS` si eso las activa por defecto; validar `model_governance=true` +
  `predictive_modeling=false` como configuración inválida fail-closed.
- Resolvers específicos por kind, ubicación de Cards y provisioning: Changes 1–4.
- Limitación operativa del validator: `ds_guard validate` considera todo el working tree y el historial
  desde el baseline, sin distinguir Changes abiertos en paralelo. Se resolvió re-baselineando este Change
  al commit del corrective (`c49a7e4`, que no toca ningún archivo de Change 0, verificado con
  `git diff --name-only`), sin ampliar el scope; el baseline anterior queda registrado en `control.json`.
  Las `rutas_autorizadas` se editaron en `control.json` porque `ds_guard` no ofrece un comando para
  ampliarlas.
- Fin de línea: los archivos nuevos se crearon con LF; `core.autocrlf` advierte conversión a CRLF al
  commitear (deuda LF/CRLF ya registrada en v0.10). Los hashes de aprobación usan `sha256/lf/v1`.

## Resultado final
Change 0 completo y verde. Listo para cierre.
