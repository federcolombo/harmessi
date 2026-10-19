# Propuesta — 20261019-v011-upgrade-migration-resilience

## Problema
Change 5 de v0.11 (roadmap congelado). Hoy no existe una operación `upgrade`; `install` sobre un proyecto ya instalado omite lo existente y `sync` solo amplía stage/capabilities sin comparar `harness_version`. Una instalación interrumpida deja un staging huérfano que `preflight` solo detecta («revisar a mano»); el journal y los backups quedan dentro del staging sin consumidor. `control.json` del instalador se escribe sin atomicidad ni backup (`generar_control`, `migrar_hashes`) y `regenerar_control` corre fuera de la transacción en `sync`. Doctor reporta `HARMESSI-VERSION` sin remedio accionable. No hay test genérico de completitud del MANIFEST. Riesgo: proyectos `half old / half new` silenciosos y pérdida de customizaciones.

## Objetivo
Nunca dejar silenciosamente un proyecto half old / half new: upgrade explícito con dry-run por defecto, recovery soportado de instalaciones interrumpidas, escritura atómica del estado instalado y Doctor con remedio accionable.

## Evidencia
- Audit de solo lectura (informe del Lead, 2026-10-19): `tools/ds_init/cli.py` (acciones install/sync/migrate-hashes; sin upgrade), `writer.py` (staging, journal, backups, rollback en proceso, sin lock ni recovery), `preflight.py::_detectar_staging_huerfano`, `control.py::generar_control/migrar_hashes` (open('w')), `tools/harmessi/doctor.py::_check_coherencia_version` (WARN sin remedio), `check_manifest_parity.py` (solo dirección verbatim→repo), 19 módulos de tools/ fuera del MANIFEST consumidos solo desde el checkout (fallback, providers, routing, harmessi_bench).
- `docs/roadmap/v0.11.md` Change 5.

## Supuestos descartados
Ningún schema de Changes 2 y 3 exige migración de datos (el ledger lee v1 y v2; el control.json de SDD sigue en schema_version 1). Si durante la implementación aparece una exigencia, se documenta y se decide en ese momento.

## Alcance
(i) Test genérico de completitud del MANIFEST con allowlist explícita «solo checkout». (ii) `ds_init upgrade` (dry-run por defecto, `--execute` escribe): actualiza managed assets pristine, crea managed nuevos del manifest, reporta drift sin adoptarlo, no toca project-owned ni exclusiones permanentes, usa la transacción con journal existente y regenera `.ds_init/control.json` dentro de ella. (iii) Journal persistente consumible y `ds_init recover` (dry-run por defecto): detecta staging/journal huérfano y revierte desde los backups a un estado consistente o aborta con instrucción exacta; lock de instalación simple que impide ejecuciones concurrentes. Escritura atómica de `.ds_init/control.json` (tmp + `os.replace`) y backup en `migrate-hashes`. (iv) Doctor: remedio literal en `HARMESSI-VERSION` y check de staging/journal huérfano. (v) Idempotencia. (vi) Byte-identidad de los archivos del proyecto (guardrails customizados, amendments, GLOSSARY.md, ledger, approvals, Cards, Data Contracts). Tests (unitarios, E2E sobre proyecto sintético v0.10 con fixtures propios, inyección de fallos por fase), docs y registro de `ds_init`/Doctor. No incluye el bump de versión a 0.11.0 (Change 6).

## Fuera de alcance
Rollback entre versiones mayores o downgrade; migrar datos del proyecto; plataformas no Windows reales; bump de versión (Change 6); regresión completa (Change 6); features nuevas ajenas al upgrade/recovery.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado
- tools/ds_init/**
- tools/harmessi/**
- tools/dsguard/core.py
- tools/dsguard/repo.py
- tools/ds_guard.py
- tools/launcher_common.py
- tools/tests/**
- .claude/skills/lead-data-scientist/SKILL.md
- .claude/skills/lead-data-scientist/methodology.md
- .claude/skills/lead-data-scientist/verificador.md
- docs/**
- README.md
- ARCHITECTURE.md
- openspec/changes/20261019-v011-upgrade-migration-resilience/**

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
