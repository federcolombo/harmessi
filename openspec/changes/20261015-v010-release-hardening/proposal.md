# Propuesta — 20261015-v010-release-hardening

## Problema
v0.10 (Changes 0–5) está implementada y commiteada en `v0.10-dev` pero no está preparada para publicarse: la versión sigue en 0.9.0, `.ds_init/control.json` es el baseline de v0.9 (harness_version 0.9.0; 105 entradas legacy sin `hash_alg`; 14 archivos administrados modificados legítimamente por los Changes 1–5; archivos administrados nuevos sin registrar), no hay notas de release, el roadmap no refleja el cierre, y la regresión completa y el sweep de privacidad no se corrieron sobre el estado final.

## Objetivo
Integrar, estabilizar, validar y publicar Harmessi v0.10.0: versión 0.10.0, baseline gestionado regenerado con el hashing de Change 1, notas de release en inglés, smoke de release, UNA regresión completa verde, Doctor sin ERROR, privacidad limpia, y publicación (main fast-forward, tag anotado `v0.10.0`, push de `main` y del tag, GitHub Release si `gh` está disponible).

## Evidencia (audit 2026-10-15)
- Versión: `tools/ds_init/version.py` (`HARNESS_VERSION = "0.9.0"`), `CITATION.cff` (`version: 0.9.0`, `date-released`), `.ds_init/control.json` (`harness_version: 0.9.0`), `tools/tests/test_v09_release_hardening_smoke.py` (`test_version_es_09`). No existe archivo VERSION ni pyproject.
- Proceso v0.9: commits «Prepare Harmessi v0.9.0 release hardening», «Refresh release control for v0.9.0», merge de `v0.9-dev` a `main`, «Mark v0.9.0 as published in roadmap», tag anotado `v0.9.0`; notas en `docs/releases/v0.9.0.md`.
- Managed hashing: `python -m tools.ds_init --destino . migrate-hashes` (dry-run): 105 migrables, 14 no verificables (drift real), 0 desconocidas. Doctor sobre el repo: 35 OK, 14 WARN (`HARMESSI-DRIFT`), 0 ERROR, 4 N/A; los archivos nuevos del manifest (`skill.md`, `skill_contract.py`, `ownership.py`, `domain-modeling.md`, `glossary.py`) figuran como «preexistentes del usuario» hasta registrar el baseline.
- Git: `main == origin/main == ff9a39d`; `v0.10-dev` desciende de `main` (fast-forward posible); tags v0.9.0 y anteriores; `docs/feedback/` y `.harmessi/` ignorados; el sweep de privacidad existe en `test_v09_release_hardening_smoke.py`. `gh` no se encuentra en el PATH de Bash.
- Roadmap: `docs/roadmap/v0.10.md` y `docs/roadmap/README.md` indican «en curso».

## Supuestos descartados
1. Que el drift de 14 archivos sea corrupción: son archivos administrados modificados por los Changes 1–5 (se verifica contra `git diff v0.9.0..HEAD`).
2. Que migrar hashes legacy sea re-adoptar: `migrate-hashes` solo migra entradas que verifican; el drift real se resuelve por contenido legítimo, nunca por baseline silencioso.
3. Que haga falta un archivo VERSION nuevo.

## Alcance
Versión 0.10.0; notas `docs/releases/v0.10.0.md` (inglés); README (sección v0.10); roadmap (v0.10.md, README de roadmap); smoke `test_v010_release_hardening_smoke.py` y actualización del smoke de v0.9; migración/regeneración de `.ds_init/control.json`; regresión completa; Doctor; privacidad; correctivos internos de estabilización encontrados por la regresión; publicación.

## Fuera de alcance
Features nuevas, SaaS/cloud/UI, ledger amend/correct, enum de decisiones, `ds_profile` columnar, T1 POSIX real, T2 de proveedor, scratchpad externo, nuevas skills, push de `v0.10-dev`.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- tools/**
- docs/**
- README.md
- CITATION.cff
- ARCHITECTURE.md
- .ds_init/control.json
- .claude/skills/lead-data-scientist/**
- .claude/agents/**

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
