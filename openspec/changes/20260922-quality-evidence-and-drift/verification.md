# Verificación — 20260922-quality-evidence-and-drift

## Evidencia obtenida

- **Bugs reales encontrados y corregidos pre-revisión** (durante la implementación, antes de
  invocar al `data-science-reviewer`):
  1. `_CLAVES_RESULTADO_PERMITIDAS` en `core.py` no incluía `"kind"`, aunque
     `CheckResult.to_dict()` siempre lo produce -- corregido.
  2. **Bug de instalación real (el más importante):** los mensajes de error de
     `_validar_evidence_id`/`_validar_drift_id` usaban `{{8}}`/`{{6}}` (escape de f-string) para
     mostrar la longitud esperada del id. Ese patrón literal `{{...}}` coincidía con el detector de
     placeholders sin resolver de `tools/ds_init/writer.py`, por lo que **toda instalación real de
     Harmessi quedaba rota**: `InstalacionAbortadaError: Placeholder sin resolver`. Esto se
     manifestaba como 54 tests fallando en `tools/ds_init/tests/` cuando se corrían en aislamiento.
     Corregido reformulando los mensajes de error para no producir el patrón `{{...}}`.
  - Ambos fixes re-verificados de forma aislada antes de continuar: `tools/qualityevidence/tests`:
    **83 passed**; `tools/ds_init/tests` en aislamiento: **112 passed, 0 failed**.
- **Suite completa tras esos 2 fixes** (antes de la revisión del `data-science-reviewer`): **1165
  passed + 3 skipped + 665 subtests** sobre el resto de v0.7/reporting/datacontracts/modelquality/
  neutralidad. **Regresión completa** (`pytest tools -q`): **2408 passed, 10 skipped, 709 subtests,
  0 failed**.
- **Revisión de `data-science-reviewer`** (diff completo SDD + implementación, solo lectura): **1
  hallazgo bloqueante** (R20, privacidad: los mensajes de error de `write_manifest`/
  `read_manifest` interpolaban la ruta absoluta del repo en vez de una etiqueta repo-relativa) y
  **1 hallazgo no bloqueante** (faltaba un test de escritura atómica interrumpida).
- **Ciclo de remediación (1 de 2 usados):** ambos hallazgos aplicados en el mismo ciclo:
  - Fix de privacidad: los 4 mensajes de error afectados de `write_manifest`/`read_manifest` ahora
    usan una etiqueta repo-relativa en vez de la ruta absoluta; se agregó un test negativo que
    confirma la ausencia de ruta absoluta en esos mensajes.
  - Test nuevo de interrupción de `os.replace` durante `write_manifest`, que confirma que no queda
    un `manifest.json` parcial cuando la escritura se interrumpe.
- **Re-tests tras el ciclo de fixes**: `tools/qualityevidence/tests` +
  `test_v07_qualityevidence_neutrality.py` + `test_architecture_boundaries.py`: **106 passed, 0
  failed**.
- **Regresión completa final** (`pytest tools -q`): **2410 passed, 10 skipped, 709 subtests, 0
  failed**.
- **Paridad de manifest** (`check_manifest_parity`): `OK`.
- **Doctor** (`harmessi doctor`): `0 ERROR`, mismo perfil de `WARN` preexistente, no relacionado
  con este Change.
- Confirmado explícitamente por el reviewer: `tools/datacontracts/`, `tools/modelquality/` y
  `tools/reporting/` sin ningún diff.

## Ciclo de remediación

- 1 de 2 ciclos de remediación de revisión usados: en ese único ciclo se resolvieron ambos
  hallazgos de la revisión (el bloqueante R20 de privacidad y el no bloqueante de test de escritura
  atómica interrumpida). No hizo falta un segundo ciclo.
- Los 2 bugs descritos arriba (`"kind"` faltante en `_CLAVES_RESULTADO_PERMITIDAS` y el patrón
  `{{...}}` que rompía `ds_init`) fueron encontrados y corregidos **antes** de invocar al
  `data-science-reviewer`, no como remediación de un hallazgo de revisión.

## Fingerprint de dataset/artefacto

No aplica -- `tools/qualityevidence/{core,evidence}.py` opera sobre fixtures sintéticas
(`profile.json` y `guardrails.json` de prueba vía `tempfile`) y sobre estructuras en memoria
(`QualityEvidenceManifest`, `DriftEvidence`), sin dataset propio ni datos reales.

## Diferencias contra la spec

Ninguna. La implementación se ajustó a `spec.md` R1-R25 y `design.md` tal como quedaron aprobados
por el Lead al cierre de la invocación 1. Los 2 fixes pre-revisión corrigieron defectos de
implementación (una clave faltante en una whitelist y un patrón de mensaje de error incompatible
con el instalador), sin alterar el comportamiento declarado por la spec. El fix de privacidad del
ciclo de remediación (etiqueta repo-relativa en vez de ruta absoluta en mensajes de error) es
consistente con el requisito de portabilidad/privacidad de `spec.md` (paths repo-relativos, sin
datos privados) y no representa una desviación de lo aprobado.

## Limitaciones

1. `drift_from_profiles` compara únicamente los campos del allowlist
   `_CAMPOS_NUMERICOS_PERMITIDOS`, derivables de la evidencia de `profile.json`; no implementa una
   biblioteca estadística universal.
2. `DriftEvidence.result_status` nunca es `PASS`/`FAIL` cuando `threshold is None`: siempre `N/A`
   en ese caso.
3. `tools/qualityevidence/core.py` es solo-stdlib y no importa `tools.datacontracts`/
   `tools.modelquality`/`tools.reporting`/`dsguard`/`ds_profile`; `tools/qualityevidence/
   evidence.py` solo usa `dsguard.checks` y `ds_profile.holdout_guard.verificar_permitido` como
   punto de conexión declarado, aplicado a TODA ruta de `profile.json` antes de abrirla (incluidas
   ambas rutas de una comparación de drift).
4. `content_sha256()` de `QualityEvidenceManifest`/`DriftEvidence` excluye deliberadamente
   `generated_at`, verificado con test de reproducibilidad real.

## Pendientes derivados

- Change 4 (`quality-integration-and-cli`) consumirá `QualityEvidenceManifest`/`DriftEvidence`/
  `build_manifest`/`write_manifest`/`read_manifest`/`drift_from_profiles`/`resolve_evidence_ref`
  desde una futura CLI (`harmessi quality ...`).
- Change 5 (hardening) depende de este Change para sus fixtures de "reproducibilidad de la
  evidencia de calidad" y "comportamiento con evidencia faltante/stale".
- El patrón de mensaje de error `{{n}}` (escape de f-string) queda documentado acá como una clase
  de bug real que rompe la instalación (`ds_init`/`writer.py`); vale la pena tenerlo presente en
  Changes futuros que generen mensajes de error con llaves literales.

## Resultado final

**CERRADO -- Change 3 (`quality-evidence-and-drift`) aprobado para cerrar.** Suite nueva y
regresión completa en verde (2410 passed, 10 skipped, 709 subtests, 0 failed), paridad de manifest
OK, doctor sin `ERROR`, 2 bugs reales pre-revisión encontrados y corregidos (incluyendo un bug que
rompía toda instalación real de Harmessi vía `ds_init`), revisión del `data-science-reviewer` con 1
hallazgo bloqueante y 1 no bloqueante, ambos resueltos en el ciclo de remediación 1 de 2,
`tools/datacontracts/`, `tools/modelquality/` y `tools/reporting/` sin ningún diff.
