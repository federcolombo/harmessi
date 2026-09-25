# Tareas — 20260925-v07-release-hardening

estado: cerrada

## Invocaciones planificadas

1. **`python-data-engineer`** (esta invocación): redacta los 4 artefactos SDD (`proposal.md`,
   `spec.md`, `design.md`, `tasks.md`). Sin código. No toca `.ds_init/control.json`.
2. **`python-data-engineer`**: implementa los 2 smokes nuevos identificados en `design.md`
   (decisión 1) en un único archivo nuevo, `tools/tests/test_v07_release_hardening_smoke.py`:
   (a) smoke de "reporting consumption" (`reporting.evidence.describe_source` sobre un
   `QualityEvidenceManifest` sintético de `tools.qualityevidence`, spec R12); (b) smoke de
   neutralidad agregada de las 3 familias nuevas de v0.7 contra el universo completo de paquetes
   preexistentes. Sin cambios en `tools/datacontracts/*`, `tools/modelquality/*`,
   `tools/qualityevidence/*`, `tools/reporting/*` ni `tools/ds_guard.py`. QA: correr el archivo
   nuevo de forma aislada antes de pasar a la invocación 3 (a cargo del Lead, el
   `python-data-engineer` no ejecuta).
3. **Lead** (sin subagente de escritura): corre, en este orden, `pytest tools -q` completo (R1),
   el smoke nuevo de la invocación 2, los scratch installs frescos `experiment` y `discovery` vía
   `tools/ds_init` en el scratchpad de la sesión con `harmessi doctor --destino` (R16), backward
   compatibility contra `v0.6.0` (`git diff --stat`, R17), el sweep de privacidad transversal sobre
   todo el diff de v0.7 (R18), portabilidad (R19), `check_manifest_parity` (R20) y `harmessi
   doctor` sobre este repo (R21). Recolecta evidencia real y no instala dependencias nuevas; si
   detecta la necesidad de una dependencia, presenta los 5 puntos al usuario antes de cualquier
   `pip install` y no continúa autónomamente en ese punto.
4. **`data-science-reviewer`** (read-only): revisión transversal del conjunto de los 5 Changes de
   v0.7 (Changes 0-4 + este Change 5), sin repetir revisiones individuales ya cerradas.
5. **`python-data-engineer`**: aplica solo correcciones de hardening acotadas a las rutas
   autorizadas en `proposal.md` (Alcance), si la evidencia de la invocación 3 o el reviewer de la
   invocación 4 hallan defectos. Re-correr lo afectado (no necesariamente toda la regresión, salvo
   que el fix pueda afectar el gate completo).
6. **`python-data-engineer`**: cierra con `verification.md` (evidencia real citando los 5
   `verification.md` de Changes 0-4 más la evidencia nueva de este Change, hallazgos del reviewer,
   limitaciones, resultado final `READY FOR v0.7.0 RELEASE` o `NOT READY FOR v0.7.0 RELEASE` con
   razones concretas) y actualiza `docs/roadmap/v0.7.md` (`[x] Change 5` solo si corresponde al
   cierre). No toca `.ds_init/control.json`.
7. **(Condicional, solo si el veredicto de la invocación 6 es `READY` y el usuario lo autoriza
   explícitamente)**: invocación separada para alinear versión canónica
   (`tools/ds_init/version.py`, `CITATION.cff`) y regenerar `.ds_init/control.json` ÚLTIMO,
   siguiendo el mismo patrón que las invocaciones 2 y 6 de
   `openspec/changes/20260918-v0-6-release-hardening/tasks.md`. Fuera del alcance mecánico de las
   invocaciones 1-6 de este `tasks.md`; requiere decisión explícita posterior, no incluida en esta
   redacción de SDD.

## Tareas

- [x] Artefactos SDD completos (`proposal.md`, `spec.md`, `design.md`, `tasks.md`) redactados
      (invocación 1). Sin tocar `.ds_init/control.json`.
- [x] `tools/tests/test_v07_release_hardening_smoke.py` con los 2 smokes nuevos (R12 y
      neutralidad agregada) (invocación 2).
- [x] Regresión completa `pytest tools -q` en verde, sin `failed` (R1) (invocación 3).
- [x] Scratch installs `experiment` y `discovery` frescos, con doctor sin `ERROR` sobre el
      instalado (R16) (invocación 3).
- [x] Backward compatibility contra `v0.6.0` (R17) (invocación 3).
- [x] Sweep de privacidad transversal sobre todo el diff de v0.7 (R18) (invocación 3).
- [x] Portabilidad confirmada (R19) (invocación 3).
- [x] Paridad de manifest (R20) y `harmessi doctor` sobre este repo sin `ERROR` (R21)
      (invocación 3).
- [x] Confirmación por lectura de que R2-R11, R13-R15 (ítems ya cubiertos por Changes 0-4) siguen
      verdes dentro de R1, con cita concreta por ítem en `verification.md` (invocación 3/6).
- [x] Reviewer transversal (R22) y resolución de hallazgos (invocación 4).
- [x] Correcciones de hardening acotadas, si las hay (R23), y re-corrida de lo afectado
      (invocación 5). Corrección aplicada: `tools/datacontracts/validation.py` (Change 1) faltaba
      en `tools/ds_init/manifest.py`; agregada la entrada VERBATIM correspondiente,
      `stage_minimo="discovery"`; re-verificado (`tools/ds_init/tests/test_manifest.py` +
      `tools/tests/test_manifest_dsguard_parity.py` → 40 passed).
- [x] `verification.md` con resultado final explícito `READY FOR v0.7.0 RELEASE` o
      `NOT READY FOR v0.7.0 RELEASE` con razones concretas (R24) (invocación 6).
- [x] `docs/roadmap/v0.7.md` con `[x] Change 5` solo si corresponde al cierre (invocación 6).
- [x] Pendiente condicionante declarado: alineación de versión canónica y regeneración de
      `.ds_init/control.json` quedan fuera de este `tasks.md`, sujetas a autorización explícita
      posterior si el veredicto es `READY` (invocación 7, condicional).

## Dependencias

Depende de que los Changes 0-4 de v0.7 estén cerrados con `verification.md` propio (confirmado:
`data-contracts-core`, `data-contract-validation`, `model-quality-policies`,
`quality-evidence-and-drift`, `quality-integration-and-cli`, los 5 con estado `CERRADO`). Sin
dependencias externas nuevas (decisión 8 del roadmap: sin dependencias nuevas en v0.7). El smoke de
la invocación 2 depende de las APIs ya cerradas de `tools.qualityevidence.core`/`evidence` (Change
3) y `tools.reporting.evidence.describe_source` (Change 3 de v0.6); no depende de ningún cambio de
comportamiento nuevo en esos módulos.

## Próximo paso exacto

No aplica (`estado: propuesta_pendiente`, no `pausada_bloqueada`). Espera aprobación humana de los
4 artefactos antes de iniciar la invocación 2 (implementación de los smokes nuevos).
