# Propuesta — 20260917-remove-personal-email

## Problema
El email personal del dueño del repo quedó persistido en artefactos versionados de v0.5: una
auditoría (`git grep` sobre todo el repo trackeado, buscando el patrón de contacto personal del
autor) encontró exactamente 25 apariciones en 9 archivos -- 20 en el campo `"usuario"` de
`aprobaciones` de 5 `control.json` (`20260917-multi-provider-adapters`, `20260917-harmessi-bench`,
`20260917-provider-routing`, `20260917-fallback-and-handoffs`,
`20260917-cross-provider-hardening`, 4 cada uno), 2 en la línea "Usuario: Federico Colombo" seguida
del contacto personal entre paréntesis en `proposal.md` de `20260917-multi-provider-adapters` y
`20260917-harmessi-bench`, y 2 citando el propio patrón de búsqueda de un sweep de privacidad
anterior (`openspec/changes/20260917-v0-4-release-hardening/verification.md` línea 18 y
`openspec/changes/20260917-v0-5-release-hardening/verification.md` línea 17 -- estas 2 no son una
fuga, son evidencia textual de que ya se había buscado). El usuario pidió explícitamente, antes de
publicar el repositorio, eliminar su email personal de todos los archivos versionados del proyecto.

## Objetivo
Eliminar el email personal del dueño del repo de todo el contenido versionado actual, y agregar una
guarda técnica real (`core.validar_usuario_sin_email`) para que un futuro `--usuario` con forma de
email no pueda volver a persistirse vía los comandos de `ds_guard` que escriben ese campo
(`approve`, `remediation extend`, `decision add/supersede/revoke`).

## Evidencia
Auditoría del Lead: `git grep` sobre todo el repo trackeado, buscando el patrón de contacto
personal del autor, → 25 apariciones en 9 archivos, desglosadas en "Problema" arriba. Confirmado
también que `CITATION.cff`
NO contiene ningún email (solo `family-names: "Colombo"` / `given-names: "Federico"`).

## Supuestos descartados
No aplica -- no hubo una hipótesis alternativa descartada en la auditoría, el hallazgo fue directo.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica -- este cambio no prueba una hipótesis metodológica, es limpieza de artefactos + una
guarda técnica del harness.

## Alcance
Las 16 rutas siguientes:
- `openspec/changes/20260917-multi-provider-adapters/control.json`
- `openspec/changes/20260917-multi-provider-adapters/proposal.md`
- `openspec/changes/20260917-harmessi-bench/control.json`
- `openspec/changes/20260917-harmessi-bench/proposal.md`
- `openspec/changes/20260917-provider-routing/control.json`
- `openspec/changes/20260917-fallback-and-handoffs/control.json`
- `openspec/changes/20260917-cross-provider-hardening/control.json`
- `openspec/changes/20260917-v0-4-release-hardening/verification.md`
- `openspec/changes/20260917-v0-5-release-hardening/verification.md`
- `tools/dsguard/core.py`
- `tools/ds_guard.py`
- `tools/tests/test_validar_usuario_sin_email.py`
- `tools/tests/test_ds_guard_usuario_guard.py`
- `.claude/skills/lead-data-scientist/sdd.md`
- `.claude/skills/lead-data-scientist/decision-ledger.md`
- `openspec/changes/20260917-remove-personal-email/verification.md`

## Fuera de alcance
Reescribir historia de git (commits anteriores) -- el email queda en el historial, solo se elimina
del working tree/HEAD actual; `CITATION.cff` (no tiene email, confirmado); cualquier archivo de
`tools/providers/`, `tools/routing/`, `tools/fallback/`, `tools/harmessi_bench/` (no relacionados
con este hallazgo); push, merge, tag o release (instrucción explícita del usuario: "No push. No
merge. No tag. No release.").

## Holdout policy (condicional — solo cambios "sensible")
No aplica -- este cambio no toca datos ni holdouts de ningún proyecto DS, es limpieza de artefactos
del harness y tooling de `ds_guard`.

## Impacto en production-readiness (opcional)
No aplica en esta etapa del harness.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
- Cero apariciones del email personal del autor en `git grep` sobre el repo trackeado tras el
  cambio.
- Los 5 `control.json` siguen siendo JSON válido, con únicamente el campo `usuario` de cada entrada
  de `aprobaciones` corregido (ningún otro campo tocado).
- `core.validar_usuario_sin_email` existe, es una función pura, y está cableada como primera
  validación (antes de cualquier escritura) en los 5 command handlers de `tools/ds_guard.py` que
  persisten `usuario`.
- Tests nuevos (`test_validar_usuario_sin_email.py`, `test_ds_guard_usuario_guard.py`) determinan
  que un `--usuario` con forma de email es rechazado con exit code 2, sin escribir nada.

## Decisión técnica (design-lite — solo SDD abreviado)
Heurística simple (`"@" in usuario`) en vez de un parser de email completo: suficiente para el
propósito (detectar la forma, no validar exhaustivamente qué es un email válido), consistente con
el resto del estilo de `dsguard/core.py` (funciones puras, deterministas, sin dependencias
externas). La guarda se agrega como primera validación tras resolver `repo_root` en cada handler,
antes de cualquier lectura/escritura de `control.json`/ledger -- fail-fast, ningún archivo se
escribe si la validación falla.

## Aprobación
- Usuario: Federico Colombo.
- Fecha: 2026-09-17.
- Alcance aprobado: eliminar email personal de artefactos versionados + guarda técnica, pedido
  explícito del usuario en su mensaje de esta misma conversación (no requiere el contrato de
  autonomía de v0.5, es una instrucción directa punto por punto).
- Versión de artefactos referenciada: primer borrador de este `proposal.md`/`tasks.md`.
- Cita o descripción fiel de qué se aprobó: "Quiero que el repositorio público no contenga mi email
  personal dentro de archivos del proyecto... Corregí la fuente/template/lógica que lo genera... No
  push. No merge. No tag. No release."

## Motivo de rechazo
No aplica — estado no es `descartada`.

## Desacuerdo registrado
No aplica — no hubo rondas de revisión sin acuerdo.
