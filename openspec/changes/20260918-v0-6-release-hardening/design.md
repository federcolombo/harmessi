# Diseño — 20260918-v0-6-release-hardening

## Decisión metodológica/técnica

Reutilizar el patrón de hardening de `20260917-v0-5-release-hardening`, sin inventar un proceso
nuevo, con orden obligatorio:

1. Alinear versión y estado (`version.py`, `CITATION.cff`, `docs/roadmap/v0.6.md`).
2. Verificar: 10 suites secuenciales (por memoria), contract tests, scratch installs reales
   (`experiment` y `discovery`), smokes R7-R15, backward compatibility contra `v0.5.0`, sweeps de
   privacidad y portabilidad, `harmessi doctor`.
3. Reviewer transversal sobre los 5 Changes de v0.6.
4. Corregir SOLO defectos de hardening dentro de las rutas autorizadas y re-correr lo afectado.
5. Regenerar `.ds_init/control.json` ÚLTIMO, después de cualquier corrección, invocando el Lead
   `control.regenerar_control` directamente (mismo criterio que v0.4/v0.5, para no arriesgar el
   MERGE de `.claude/settings.json`), y re-verificar paridad y consistencia de versión.
6. Emitir el veredicto `READY FOR v0.6.0 RELEASE` o `NOT READY FOR v0.6.0 RELEASE`.

Sin features nuevas. Sin push, merge a `main`, tag, GitHub Release ni borrado de `v0.6-dev`:
parada humana final.

Regla de veredicto sobre `plotly.js`: el `plotly.js` REAL no se ejecutó nunca; todo lo de figuras
se verificó con un bundle FALSO, y por restricción vigente del usuario (2026-09-21) no se instala
Plotly ni ninguna dependencia nueva. Esa verificación (offline y dark/print con bundle real, y
`Plotly.react` en `beforeprint`) es un requisito PENDIENTE que condiciona el resultado final. Si
sigue pendiente al cierre, el veredicto debe nombrarlo como razón concreta y no puede afirmar
verificación con bundle real. Cualquier `pip install` requiere antes que el Lead presente al
usuario los 5 puntos (por qué es necesaria, si puede seguir opcional, qué contrato/dependencia
agrega, alternativas sin dependencia, impacto en instalación y backward compat) y espere respuesta.

## Target (condicional)

No aplica.

## Features permitidas/prohibidas (condicional)

No aplica. Está prohibido agregar features; el diff solo puede contener versión, estado,
verificación y correcciones de hardening.

## Estrategia de split/validación (condicional)

No aplica. Los smokes de holdout usan fixtures sintéticos en directorios temporales; ningún
holdout real se abre.

## Leakage risks (condicional)

No aplica como leakage metodológico. El riesgo análogo es filtrar datos, nombres o rutas privadas
en artefactos públicos, cubierto por R3 y R7. El riesgo de contaminación entre scopes
(`exploratory` vs `model_valid`) se verifica con los smokes R8-R10.

## Reproducibilidad (opcional)

Sin aleatoriedad. Determinismo verificado por R7 (2 corridas, mismo hash y HTML) y R12 (manifest
byte a byte con reloj y `run_id` fijos). Las suites corren de a una para acotar el uso de memoria.

## Alternativas descartadas

1. **Agregar features o documentación no pedida (p. ej. comandos de `tools.reporting` en el
   README)**: descartado. Este Change es hardening puro; la documentación de esos comandos queda
   como deuda declarada para v0.7+.
2. **Regenerar `.ds_init/control.json` antes de las correcciones de hardening**: descartado. Una
   corrección posterior en `tools/reporting/**` o en el manifest lo dejaría desactualizado
   (deriva de hashes/rutas). Se regenera ÚLTIMO y se re-verifica R17/R18.
3. **Instalar Plotly sin decisión del usuario para verificar con el bundle real**: descartado. Va
   contra la restricción vigente; requiere presentar los 5 puntos y esperar aprobación.
4. **Marcar `READY` sin verificar el bundle real**: descartado. Sería afirmar una garantía que
   nunca se comprobó; el veredicto debe reflejar el pendiente con razones concretas.
5. **Publicar (push, merge, tag, release, borrar `v0.6-dev`)**: descartado. Prohibido por el
   usuario; es la parada humana final y requiere aprobación separada.

## Riesgos

- **`plotly.js` real no verificado**: la salida offline y el comportamiento dark/print con figuras
  reales, y `Plotly.react` en `beforeprint`, pueden diferir del bundle FALSO. Mitigación:
  declararlo en `verification.md` y en el veredicto; verificarlo en v0.7+ o tras decisión del
  usuario.
- **Solo Windows**: portabilidad a otros SO y CI sin ejecutar; `core.autocrlf` puede alterar los
  bytes de `reports/**` (deuda: `.gitattributes -text`). Se declara como limitación.
- **Sin ancla externa del hash del manifest**: quien controle el repo puede reescribir manifest y
  hash a la vez. Deuda declarada para v0.7+.
- **Reviewer de la misma familia de modelo**: no hay una segunda familia real disponible; se
  reafirma la limitación en lugar de fingir una garantía.
- **Correcciones tardías que invaliden evidencia previa**: se mitiga re-corriendo las suites y
  smokes afectados y regenerando `control.json` ÚLTIMO.
- Deuda adicional para v0.7+: otros SO/CI, múltiples renderers, LLM-as-judge.

## Aprobación humana

El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único por
cambio y vive en la sección "Aprobación" de `proposal.md` — no se duplica acá.
