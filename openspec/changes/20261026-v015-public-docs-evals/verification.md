# Verificación — 20261026-v015-public-docs-evals

## Resumen
Change C6 de v0.15: documentación pública derivada del código, doc de evaluación, runbook de release y `.gitattributes` acotado (B-26..B-30, B-34), con un test de consistencia de docs.

## Cambios de código
- Nuevos: `.gitattributes`, `docs/{installation,concepts,cli-reference,evaluation,security-and-trust,release-process}.md`, `tools/tests/test_public_docs.py`.
- Editados: `README.md` (índice de documentación y sección `reporting`), `ARCHITECTURE.md` §4/§4.1 (marcas Resuelto/Vigente/Parcial), `verificador.md` y su template (`SKILL-TRAZA-SECCION-DUPLICADA`), matriz de deuda y roadmap §C6.

## Evidencia obtenida
- `suite-check` real de la suite pública: válida, `suite_id` harmessi-core-synthetic, `suite_version` 1, 9 casos, `suite_hash` 71ae5ae2…c002b (el test de docs recalcula el hash con la función real).
- `test_public_docs` + `test_privacy_sweep` + `test_architecture_boundaries` + `test_skill_methodology` + `test_skill_contract` + `test_v013_contract_inventory`: 221 passed, 579 subtests.
- Revisión independiente de docs: 0 bloqueantes, 2 mayores (comando del runbook sin `--out`; marca «Resuelto» sobrestimada en ARCHITECTURE §4.1 pto 11) y 4 menores, todos corregidos; el revisor confirmó contra los parsers los comandos y flags muestreados.

## Limitaciones
- No se publica baseline numérico de evals (requiere provider real; un solo host live-validado): ACCEPTED LIMITATION.
- CI remoto no observado: «pending observation» hasta el push (C7); sin Python 3.9 en la matriz.
- Doctor solo corre desde un checkout (`--destino`); `reports/**` de proyectos instalados no cubierto por `.gitattributes`.
- El paso de baseline de hashes managed del runbook no tiene comando dedicado.
- La documentación no se contrastó con un lector externo real.
- Cierre SDD formal PENDIENTE: la transición a `cerrada` no pasa retroactivamente (gate de alcance: C4, C5 y C6 comparten `tools/tests/**` y el baseline de cada uno ve los cambios de los otros). El Change queda en `en_verificacion`, implementado, probado y revisado; ver brecha de proceso en `docs/roadmap/v0.15.md`.
