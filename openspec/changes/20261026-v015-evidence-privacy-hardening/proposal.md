# Propuesta — 20261026-v015-evidence-privacy-hardening

## Problema
Siete deudas de endurecimiento de evidencia/privacidad/procedencia siguen abiertas (matriz v0.15, B-20..B-25 + hueco heredado de C3):

- B-20: la redacción de privacidad existe por componente (`redact.redactar_texto`, `lessons._escanear_texto`, bloqueo `DIFF_SENSIBLE` en promotion) pero ningún test determinista barre los artefactos publicables (fixtures compat, docs/releases, resultados de bench) buscando rutas personales, emails, usernames, secretos obvios o términos de GLOSSARY.
- B-21: `proposal.json` no ata `probe.json`; `probe.json` no lleva hash propio; no hay test e2e «editar el candidate tras el probe y luego decidir/proponer/aplicar» que verifique cada eslabón.
- B-22: no hay test de scope anclado por `scope_hash` con enmiendas en el gate de promoción ni de que el Decision Ledger no se escribe solo (`ledger_text` solo sugerido).
- B-23: aplicabilidad/evidence refs/sanitización de lessons tienen tests; falta test de GLOSSARY ausente (`privacidad_no_superada`) y decisión explícita project-owned vs global.
- B-24: `harmessi_bench` acepta `run_id` reservados de Windows (`CON`, `NUL`, `COM1`, `foo.`), `load_run` lanza `JSONDecodeError` ante `result.json` corrupto, `cmd_run` sale 0 con todos los casos `ok=False`, `bloque_suite` acepta bloques incompletos y un caso v0 se acepta como suite.
- B-25: el rechazo de lesson-symlink (`lessons.es_enlace`) no tiene test.
- Heredado de C3: `docs/versioning.md` exige fixture real del tag al subir un schema (1->2); no existe fixture de Data Card v1 de v0.14.0 (`DATA_CARD_KIND_SCHEMA_VERSIONS_LEIDAS=(1,2)`, ventana 0.14-0.15).
<!-- qué problema motiva este cambio -->

## Objetivo
Cerrar o reclasificar con evidencia B-20..B-25 y el fixture real de Data Card v1, sin afirmar detección perfecta de privacidad ni procedencia criptográfica.
<!-- qué se busca lograr, en una frase -->

## Evidencia
- Auditoría de solo lectura del Lead (2026-10-26) sobre: `tools/harmessi_bench/{redact,storage,suite,cli}.py`, `tools/harmessi_improve/{candidate,probe,decision,promotion,lessons,budget}.py`, `tools/dsguard/scope.py:119-137,245`, `tools/cards/datacard.py:93-94,468-471`, `docs/versioning.md:69`, `tools/tests/fixtures/compat/{generate_v014.py,v0_14/MANIFEST.json}`.
- Tests existentes citados: `harmessi_bench/tests/{test_redact,test_storage,test_v013_hardening}.py`, `harmessi_improve/tests/{test_lessons,test_promotion,test_decision,test_hardening}.py`, `tools/tests/test_v014_dogfood.py:467`.
- `docs/roadmap/v0.15.md` §C5; `docs/roadmap/v0.15-debt-matrix.md` B-20..B-25.
<!-- archivo:línea o notebook/celda citados — nunca de memoria -->

## Supuestos descartados
- «La privacidad no tiene tests»: falso; hay redacción por componente. Lo que falta es el barrido transversal.
- «Hay que firmar la evidencia»: fuera de alcance (D5): la procedencia es no criptográfica y se documenta como ACCEPTED LIMITATION.
- «`scope_hash` vive en harmessi_improve»: falso; vive en `tools/dsguard/scope.py`; promotion usa `ds.alcance_efectivo`.
<!-- qué se creía y la exploración desmintió -->

## Hipótesis (condicional — solo cambios metodológicos)
<!-- qué se espera confirmar/descartar, si el cambio prueba una hipótesis concreta -->

## Alcance
- A (B-20): test determinista de barrido de privacidad sobre artefactos publicables del repo (fixtures compat, docs/releases, ejemplos/resultados de bench) con patrones de rutas personales, emails, secretos obvios y términos de GLOSSARY; declara explícitamente que es heurístico (sin garantía de detección perfecta).
- B (B-21): tests e2e de la cadena candidate->probe->decision->proposal->apply con manipulación en cada eslabón; `proposal.json` pasa a atar `probe` solo si es aditivo y retrocompatible con fixtures reales v0.14.0 (si no, se documenta como ACCEPTED LIMITATION y se cubre con re-derivación en el gate).
- C (B-22): tests de scope con enmiendas en el gate de promoción y de que `ledger_text` no escribe el Ledger.
- D (B-23/B-25): tests de GLOSSARY ausente, de lesson symlink/junction (con skip explícito sin privilegios) y decisión documentada project-owned vs global (lessons son repo-locales; sin export cross-project = limitación documentada).
- E (B-24): `run_id` reservados de Windows rechazados; `load_run` con `result.json` corrupto falla con error limpio (sin traceback); `harmessi_bench run` con flag opt-in `--fail-on-failure` (exit 1 si algún caso `ok=False`; el default NO cambia por la política de versionado); bloques de suite incompletos y caso v0 como suite rechazados con error claro; NFC/NFD verificado (si el regex ASCII ya lo excluye, se documenta).
- F (heredado C3): fixture real de Data Card v1 generado con el código del tag v0.14.0 (patrón `generate_v014.py`) + test de que el lector v0.15 la lee; actualizar MANIFEST y `docs/versioning.md`.
- G: matriz de deuda, roadmap §C5, ARCHITECTURE/README/contracts solo donde cambie lo documentado.

## Fuera de alcance
- PKI, firmas o procedencia criptográfica (D5).
- Export/import de lessons entre proyectos.
- Cambiar el exit code por defecto de `harmessi_bench run` (breaking según `docs/versioning.md`).
- Baseline de hashes managed (C7); versión 0.15.0 (C7); docs públicas (C6).

## Holdout policy (condicional — solo cambios "sensible")
<!-- si el cambio toca o podría tocar un holdout/dataset sellado: acceso solicitado, por qué, qué
decisión depende de eso, y la autorización del usuario transcripta literal (ver SKILL.md,
categoría "Sensible") -->

## Impacto en production-readiness (opcional)
<!-- nota libre; pasa a condicional cuando esa etapa KDD se active en un bloque futuro -->

## Criterios de aceptación (spec-lite — solo SDD abreviado)
<!-- en SDD completo, ver spec.md en su lugar -->

## Decisión técnica (design-lite — solo SDD abreviado)
<!-- en SDD completo, ver design.md en su lugar -->

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado
- tools/harmessi_bench/**
- tools/harmessi_improve/**
- tools/cards/tests/**
- tools/tests/**
- docs/roadmap/v0.15.md
- docs/roadmap/v0.15-debt-matrix.md
- docs/versioning.md
- docs/contracts/**
- ARCHITECTURE.md
- README.md
<!-- opcional: rutas que este Change puede tocar, una por línea como `- ruta` o `- dir/**`
(repo-relativas, sin `..`, sin rutas absolutas ni comodines repo-wide). Al aprobar proposal.md,
ds_guard las materializa en control.json junto con los artefactos por defecto del Change;
queda ligado al hash de la propuesta aprobada. Sin bullets, el alcance no se modifica. -->

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
