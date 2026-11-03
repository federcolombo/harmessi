# Propuesta — 20261016-v011-decision-ledger-corrections

> Change 2 de v0.11. Principio: corregir sin reescribir historia; preservar evidencia.

## Problema
El ledger (`openspec/decisions/ledger.jsonl`) solo tiene `registrar`, `supersede` y `revocar`. Corregir un dato (resumen, rationale, cita, evidencia) obliga a crear una decisión nueva con aprobación completa, o a editar el archivo a mano. Además, cada escritura reserializa todas las entradas (no preserva los bytes previos) y la lectura no verifica continuidad de `seq`, ids duplicados, referencias colgantes ni tamper-evidence.

## Objetivo
Agregar la operación append-only `decision correct` y una verificación de integridad razonable (tamper-evidence, no autenticidad criptográfica), sin romper ledgers v0.10.

## Evidencia
`tools/dsguard/decision.py`: acciones `registrar/supersede/revocar`; `_escribir_entradas` reescribe todo con `json.dumps`; `leer_entradas` solo detecta JSON inválido; `ds_guard.py` (`p_decision`) como único consumidor de `TIPOS_DECISION`/`resolver_estados`.

## Supuestos descartados
El enum de tipos NO se amplía: no hay consumidor funcional real (diferido, como en el roadmap).

## Alcance
`decision correct` (acción `corregir`), `decision verify`, escritura append que preserva bytes previos, `prev_hash` encadenado para entradas nuevas, hallazgos de integridad, `list/show` con valores efectivos e historia, docs, tests.

## Fuera de alcance
Cripto/firmas, event sourcing genérico, cambios de tipos, migración de ledgers existentes, cambiar `supersede`/`revoke`.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- tools/dsguard/decision.py
- tools/ds_guard.py
- .claude/skills/lead-data-scientist/decision-ledger.md
- .claude/skills/lead-data-scientist/verificador.md
- tools/ds_init/profiles/**
- tools/tests/**
- docs/roadmap/v0.11.md
- openspec/changes/20261016-v011-decision-ledger-corrections/**

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
