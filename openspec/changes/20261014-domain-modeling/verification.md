# Verificación — 20261014-domain-modeling

## Resumen
Change 5 de v0.10: skill componible `domain-modeling` y `GLOSSARY.md` con términos `hypothesis|approved`, validados por `ds_guard`. Implementado con instancias de `python-data-engineer` de ownership disjunto; el Lead no escribió implementación. Sin intervenciones de emergencia.

## Qué entrega
- Skill `.claude/skills/lead-data-scientist/skills/domain-modeling.md` (frontmatter válido; roles lead-data-scientist, python-data-engineer, metodologo, data-science-reviewer; artifacts `[GLOSSARY.md]`).
- `tools/dsguard/glossary.py`: parser y validador stdlib, `clave_termino`, `definition_hash` (NFC + whitespace), vínculo textual artefacto-hash, T1 vía resolver inyectado, 13 códigos `GLOSSARY-*`.
- `ds_guard glossary check [--json] [--strict]` y `glossary hash --term`; chequeo en `validate` solo si existe `GLOSSARY.md`. Resolver real: `cards.approvals.resolve_approval_ref` (import perezoso; sin resolver => fail-closed).
- Manifest (skill + `glossary.py`) y Doctor (skill esperada); methodology §33, SKILL.md, verificador.md, ARCHITECTURE §7.3, roadmap Change 5.
- Reglas: `approved` exige aprobación `verified` + `trust_tier == T1` (`console_confirmed`) + artefacto aprobado que contiene el `definition_hash` + hash vigente (si la definición cambia => obsoleta). Un agente/LLM no puede producir T1, por lo tanto no puede promover. Ambigüedad material = pendiente (no error; `--strict` falla). Bloque de código dentro de una entrada o fence sin cerrar => `GLOSSARY-MALFORMADO`.
- No cambió: `human_presence.py`. El installer NO crea `GLOSSARY.md` (test de instalación).

## Evidencia obtenida
- Regresión relevante (18 módulos: glossary, CLI, skill methodology, boundaries, ownership/skill/estado, approvals/human_presence, manifest/instalación, Doctor, scope/amendments, pathguard): 714 tests OK (skipped=8), 872 s.
- Tras los últimos fixes menores del ciclo 2, módulos glossary + CLI glossary + skill_methodology + boundaries: 132 tests OK (skipped=1).
- `ds_guard validate` del Change: sin hallazgos.
- Bug real hallado y corregido: `approvals.make_anchor_verifier` espera una atestación, no un ref; el CLI usa `resolve_approval_ref`.
- Reviewer `data-science-reviewer`:
  - Ciclo 1 (sin truncamiento): 0 bloqueantes, 4 importantes (fence sin cerrar ocultaba entradas; `glossary hash` con BOM/definición None; GLOSSARY ilegible debía dar exit 2; frase obsoleta en methodology) y menores (`###` a mitad de entrada, clave de término NFC/espacios, vínculo del hash por token y sin comentarios HTML, `_ruta_segura` con backslash/unidad/symlink). Todos corregidos.
  - Ciclo 2: 0 bloqueantes, 0 importantes; menores aplicados: fence dentro de entrada => MALFORMADO, segmento `.` rechazado, exit codes de verificador.md corregidos, nota de comentarios HTML fuera de definición.
  - Total: 2 ciclos, 0 continuaciones.
- Intervenciones de emergencia: ninguna.

## Fingerprint de dataset/artefacto
No aplica (sin datasets).

## Diferencias contra la spec
- `validar_glossary` recibe `(entradas, repo_root=None, resolver=None)`; design.md decía el orden inverso. design.md está aprobado por hash y no se editó.
- La clave de término del hash se extendió a NFC/whitespace (aún no hay GLOSSARY en uso).

## Limitaciones
- El vínculo aprobación T1-definición es textual: un hash citado en cualquier otro contexto del artefacto aprobado lo satisface; no prueba autoría.
- T1 = señal de presencia, no identidad; `control.json` no está autenticado.
- No hay resolución semántica de sinónimos.
- El cierre de fences es laxo (` ```python ` cierra).
- `glossary hash` no valida el archivo.

## Pendientes derivados
- Tests CLI para fences/`###` (hoy cubiertos en unitarios).
- Símbolo muerto: fallback `getattr` en `ds_guard.py`.
- Frases históricas de Change 4 en ARCHITECTURE y roadmap.

## Resultado final
Change 5 cumple su spec. Sin push.
