# Spec — 20261016-v011-decision-ledger-corrections

**R1.** `ds_guard decision correct --decision-id X --set campo=valor (repetible) [--evidencia e ...] --motivo M --usuario U --fecha F [--json]` agrega UNA entrada `accion: "corregir"` con `referencia` = decision_id corregida, `campos` (nuevos valores), `valores_previos` (efectivos al momento), `motivo`, `aprobado_por`, `fecha_aprobacion`, `utc`, `registrado_por`.
**R2.** Campos corregibles (lista cerrada): `resumen`, `rationale`, `cita`, `evidencia`, `change_id`, `kdd_etapa` (validada contra `kdd.ETAPAS`). No se corrigen `tipo`, `decision_id` ni relaciones: eso es `supersede`/`revocar`. Valores vacíos y campos desconocidos se rechazan.
**R3.** Append-only: las líneas existentes quedan byte a byte idénticas tras cualquier escritura (add/supersede/revoke/correct). Corregir una decisión ya corregida es válido: el valor efectivo es el de la última corrección por campo; toda la historia se conserva.
**R4.** Referencia inexistente (no es un `decision_id` de `registrar`/`supersede`) → `DECISION-REFERENCIA-INVALIDA`; nada se escribe.
**R5.** Entradas nuevas llevan `prev_hash` = sha256 hex de la línea anterior exacta (sin terminador) y `schema_version: 2`. Las entradas legacy (v1 sin `prev_hash`) siguen leyéndose; la cadena arranca en la primera entrada con `prev_hash` y desde ahí es obligatoria.
**R6.** `verificar_integridad` y `decision verify` (solo lectura, exit 1 con hallazgos): `DECISION-SEQ-ROTO`, `DECISION-ID-DUPLICADO`, `DECISION-REFERENCIA-COLGANTE`, `DECISION-CADENA-ROTA` (hash no coincide), `DECISION-CADENA-FALTANTE`, `DECISION-LINEA-CORRUPTA`. Es tamper-evidence contra edición manual ingenua; NO es autenticidad: quien recalcule la cadena no es detectado.
**R7.** Toda escritura (add/supersede/revoke/correct) es fail-closed: si hay hallazgos de integridad no escribe (`DECISION-LEDGER-INCONSISTENTE`/`CORRUPTO`).
**R8.** `list`/`show` exponen `correcciones` (historia) y `efectivo` (valores vigentes) sin alterar los campos originales. Un ledger v0.10 sin cambios se lee y lista igual que antes.
**R9.** `TIPOS_DECISION` no cambia. Sin metadata ornamental.
**R10.** Docs: `decision-ledger.md`, `verificador.md` y plantillas con paridad. Tests: add, supersede, revoke, correct, correct de id inexistente, doble corrección, campo no permitido, referencias inválidas, línea corrupta, edición manual ingenua (cambio de un byte/seq/borrado de línea), compatibilidad con ledger v1 (incluido el ledger real del repo), historia byte-idéntica.

## Criterios de aceptación
- [ ] R1–R4 R7 por tests. [ ] R5–R6 R8 por tests. [ ] R9–R10.
