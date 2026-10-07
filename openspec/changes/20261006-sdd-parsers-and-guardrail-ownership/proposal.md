# Propuesta — 20261006-sdd-parsers-and-guardrail-ownership

> Corrective B de v0.9, originado en feedback real de Harmessi 0.8.0 (un informe de feedback externo no versionado,
> hallazgos a, c y d). No renumera Changes 0–5. Corrective C (`ds_profile`) y Change 5 NO se tocan.

## Problema
(a) El bullet de checkpoint exige `aprobacion: <change_id>/proposal.md@<sha256>`, es decir el hash del propio
`proposal.md` que lo contiene: autorreferencial. El workaround (64 ceros) no tiene efecto alguno porque nada compara ese hash.
(d) `==2.9.0.post0` y cualquier versión con sufijo (`post`, `rc`, `dev`, `a`, `b`) rompe el parser de dependencias
pre-aprobadas (`SDD-DEPENDENCY-PREAPPROVAL-INVALID`) y rechazaría la aprobación completa de `proposal.md`.
(c) `.claude/guardrails.json` se instala VERBATIM y se hashea; la única edición que Harmessi pide a un humano (activar
`autonomy.mode: autonomous` con sus límites) produce `HARMESSI-DRIFT`, indistinguible de tampering.

## Objetivo
Cerrar los tres con cambios mínimos y backward-compatible: checkpoint no circular resuelto contra la aprobación real
registrada, subset documentado de PEP 440 con ordering correcto, y drift SEMÁNTICO específico de guardrails con lista cerrada
de paths mutables, sin aflojar su protección.

## Evidencia (audit 2026-10-06, archivo:línea)
- Checkpoints: `_RE_CHECKPOINT_BULLET` (`sdd.py:917-921`) exige hash de 64 hex; `parsear_checkpoints_de_propuesta`
  (`sdd.py:923-1019`) lo copia a `approval_ref.hash`; `cmd_approve` (`ds_guard.py:~341-372`) persiste
  `control["decisiones_preaprobadas"]`. Nadie verifica ese hash: `autonomy.policy.resolve_methodological_decision`
  (`policy.py:~439-460`) solo valida forma de la lista que le pasa el llamador, y ningún código de producción la arma
  desde `control.json`. `validate_pre_approved`/`_validar_ref` (`autonomy/core.py:571-611`) aceptan cualquier sha256, ceros incluidos.
- ApprovalRef (Change 4): `tools/cards/approvals.py:96-159` ya implementa la resolución real (Change en `changes/` o
  `archive/`, `control.json`, entrada artefacto+hash, la más reciente, hash en disco) con primitivas de dsguard
  (`sdd._aprobacion_mas_reciente`, `core.hash_lf_v1`, `core.leer_control`).
- Versiones: `_parsear_version` (`sdd.py:1278-1292`) solo enteros separados por `.`; `_parsear_rango_version` /
  `_comparar_versiones` / `_version_satisface_rango` (`sdd.py:1295-1372`) padding de tuplas; sin consumidores externos de
  las funciones privadas (solo `clasificar_dependencia` y `parsear_dependencias_preaprobadas`, públicas). `dependency install`
  (`ds_guard.py:1266-1470`) pasa `<nombre>==<versión>` a pip y compara la versión instalada por igualdad de string (`:1421`).
- Guardrails: `.claude/guardrails.json` es entrada VERBATIM del manifiesto (`manifest.py:383-388`); `_check_hashes_drift`
  (`doctor.py:~461-526`) compara sha256 de `control["archivos"]`. Template: `version`, `holdouts`, `data_raw`,
  `secretos_extra`, `write_scopes`, `excepciones`. Activar autonomía exige (`autonomy/policy.py:~175-300`): `version` de nivel
  superior ≥ 2 (ausente o 1 degrada), `autonomy.mode`, y límites (`autonomy.limits` o `autonomy.budgets`); `pathguard`
  fail-closed ante `version` fuera de [1, `POLICY_VERSION_MAX`] (`pathguard.py:~149-155`). Doctor NO parsea la policy de
  autonomía hoy (`_check_guardrails_json` solo usa `pathguard.cargar_config`).

## Supuestos descartados
- «El hash del checkpoint hay que firmarlo en el proposal»: la aprobación registrada ya contiene el hash real; basta
  materializarlo al aprobar.
- «Los 64 ceros son una aprobación»: no; ningún registro tiene ese hash, así que resuelven `missing` (fail-closed).
- «Hace falta un PEP 440 completo (o `packaging`)»: Harmessi solo necesita igualdad, límites y rangos sobre versiones de
  paquetes comunes; se implementa un subset documentado, solo-stdlib.
- «Sacar guardrails del manifiesto resuelve el drift»: borraría la detección de tampering de un archivo de seguridad.
- «Cualquier clave bajo `autonomy` es customización humana»: `sealed_sources` y `source_access` son controles sensibles; solo
  `mode`, `version`, `budgets` y `limits` se declaran mutables.

## Alcance
`tools/dsguard/sdd.py` (checkpoints, primitiva de resolución de aprobación, parser de versiones), módulos nuevos
`tools/dsguard/pep440_subset.py` y `tools/dsguard/guardrails_drift.py`, `tools/ds_guard.py` (`approve`, `status`),
`tools/cards/approvals.py` (reutiliza la primitiva), `tools/harmessi/doctor.py` (drift semántico + validación de la
configuración de autonomía mutable), `tools/ds_init/manifest.py` (distribuir los módulos nuevos), tests y documentación.

## Fuera de alcance
`ds_profile` (Corrective C), Change 5, un comando de re-adopción de guardrails, mover guardrails a otro sistema de config,
tocar `STOP_CATALOG`/`POLICY_TABLE`/runtime de autonomía, reabrir la semántica `budgets`/`limits` de Corrective A, un PEP 440
completo, drift semántico para otros archivos VERBATIM, un nuevo approval store o un segundo resolver de aprobaciones.

## Principios
Fail-closed; la aprobación vigente es la única fuente de verdad del hash; allowlist mínima de paths mutables; «mutable» no
significa «válido»; un placeholder nunca es una aprobación; no sobreprometer PEP 440; sin dependencias nuevas.

## Deudas
v0.10: approval-origin authenticity, LF/CRLF hashing, mid-Change authorized scope amendment UX, composable skills/
domain-modeling, one-writer. Quedan fuera y vigentes: personalizar `holdouts`/`data_raw`/`secretos_extra`/`write_scopes`/
`excepciones`/`autonomy.sealed_sources`/`source_access` sigue marcando `HARMESSI-DRIFT` (no hay re-adopción soportada);
Corrective C.

## Criterios de cierre
Ver spec.md. Resumen: checkpoint nuevo sin hash propio y con hash real materializado al aprobar; ceros y hashes legacy sin
conceder aprobación indebida; `==2.9.0.post0` y `rc/dev/a/b` soportados con ordering fijado por tests; activar `autonomous` por la
vía soportada no produce drift y editar una clave managed sí; valores inválidos siguen fallando; sin regresión.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- openspec/changes/20261006-sdd-parsers-and-guardrail-ownership/**
- ARCHITECTURE.md
- docs/roadmap/v0.9.md
- docs/roadmap/v0.10.md
- tools/ds_guard.py
- tools/dsguard/sdd.py
- tools/dsguard/pep440_subset.py
- tools/dsguard/guardrails_drift.py
- tools/cards/approvals.py
- tools/cards/tests/**
- tools/harmessi/doctor.py
- tools/harmessi/tests/**
- tools/ds_init/manifest.py
- tools/ds_init/tests/**
- tools/tests/**
- tools/autonomy/tests/**
- tools/leadrun/tests/**
- tools/modelquality/tests/**
- tools/qualityevidence/tests/**
- tools/datasources/tests/**
- tools/datacontracts/tests/**
- tools/reporting/tests/**

## Motivo de rechazo

## Desacuerdo registrado
