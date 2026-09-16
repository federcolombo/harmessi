# Diseño — 20260916-v0-3-release-hardening

## Decisión metodológica/técnica

### 1. Audit transversal por el Lead, sin subagentes de auditoría
El brief pide explícitamente no volver a auditar Changes 0-9 uno por uno con subagentes — el Lead
ya construyó, revisó y verificó cada uno de esos changes en esta misma sesión, con su propio
reviewer dedicado por change. El audit de Change 10 se apoya en ese conocimiento acumulado más
verificación puntual y barata (grep exhaustivo, import-smoke-test, corridas E2E reales) en vez de
releer módulo por módulo. Ya identificado sin subagente: drift de versión (2 archivos), fuga de
privacidad (2 archivos, 3 ocurrencias, ya corregida), README desactualizado, ausencia de
CHANGELOG, `control.json` desactualizado.

### 2. Privacidad: fix inmediato pese a romper el hash-pin de 2 changes ya cerrados
`openspec/changes/20260914-fix-harness-version-drift/tasks.md` y `openspec/changes/
20260915-checks-engine-foundation/spec.md` ya tenían aprobación registrada (hash-pinned,
`control.json["aprobaciones"]`) antes de este fix. Editarlos invalida esa aprobación histórica
(el hash actual ya no coincide con el aprobado). Se decide corregir de todas formas: el propósito
del hash-pin es detectar DRIFT ACCIDENTAL entre lo aprobado y lo implementado, no impedir una
corrección real y demostrada de un BLOCKER de release explícitamente clasificado como tal por el
usuario (§15 del brief: "Cualquier filtración real: BLOCKER"). Esos 2 changes ya están cerrados y
archivables — no se reabre su ciclo SDD (sería desproporcionado para una redacción de 3 líneas);
se documenta la excepción de forma transparente en `proposal.md`/`verification.md` de ESTE change,
que es quien la autoriza y la registra.

### 3. `README.md`: edición dirigida, no reescritura
El brief pide explícitamente "no escribir documentación enorme... solo corregir lo necesario". Se
identifican los 2 gaps reales (sección KDD desactualizada, `ds_guard.py` ausente de "Commands") y
se editan quirúrgicamente esas secciones — el resto del README (Requirements, Quickstart, Platform
compatibility, Development, License) ya es correcto y no se toca.

### 4. Release notes / known limitations / roadmap: solo texto en `verification.md`, no archivos
nuevos publicados
El brief es explícito: "Si no existe CHANGELOG: NO crear un framework nuevo... preparar un texto
de release notes... pero NO publicar release" y "No abrir Changes nuevos" para el roadmap post-v0.3.
Estos 3 contenidos (release notes, known limitations, roadmap) viven como secciones de
`verification.md` de este mismo change — evidencia del hardening, no un artefacto publicado nuevo.
Si el usuario decide después publicar un `CHANGELOG.md` real, es una decisión aparte, posterior a
este change.

### 5. Validación E2E ejecutada directamente por el Lead, con Bash, reusando fixtures existentes
Todo lo de R6-R12 de `spec.md` es verificación, no implementación — no requiere delegar a
`python-data-engineer` (que además no tiene Bash, y estas verificaciones necesitan correr comandos
reales). El Lead reusa los patrones de fixture YA establecidos en `test_readiness.py`/
`test_status.py`/`test_cli.py`/`test_legacy.py` (repos git temporales reales, nunca mocks para lo
que puede validarse E2E barato) en vez de escribir tests nuevos — esto es validación de cierre de
release, no una batería de regresión permanente nueva (aunque si algún gap real de cobertura
aparece durante la validación, se puede agregar un test puntual, igual que en changes anteriores).

### 6. Orden estricto: fixes de contenido → validación E2E → regeneración de `control.json` al final
`control.regenerar_control` recalcula `archivos[]` desde el manifiesto VIGENTE en el momento en
que se corre — si se ejecutara antes de terminar los fixes de README/versión, quedaría
desactualizado otra vez. Se ejecuta como el último paso de escritura real de este change, después
de que `harmessi doctor` final y las 4 suites ya confirmaron el estado correcto.

### 7. Ningún cambio a engines/gates/schemas salvo lo ya demostrado
Confirmado por el import-smoke-test y el conocimiento acumulado de Changes 1-9: no hay imports
rotos, no hay comandos documentados que no existan (ya verificado exhaustivamente en Change 9
contra `tools/ds_guard.py` real), no hay gates contradictorios nuevos. Si la validación E2E de
este change revelara un bug real no cosmético, se clasifica BLOCKER/IMPORTANT (arreglado ahora,
alcance mínimo) o MINOR/DEBT (documentado para v0.4, nunca arreglado en este change) — nunca se
rediseña nada preventivamente.

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica — cambio de hardening/release del harness, no de datos de un proyecto DS.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica.

## Alternativas descartadas
- Dejar el drift de versión sin corregir hasta el tag real — rechazada: el brief pide
  explícitamente que este change deje la versión consistente en `0.3.0` como parte del hardening,
  antes de cualquier tag/release futuro.
- No tocar los 2 artefactos SDD ya cerrados con la fuga de privacidad, dejándolo como deuda
  documentada para v0.4 — rechazada: el brief clasifica explícitamente cualquier filtración real
  como BLOCKER a resolver AHORA, no como deuda diferible.
- Reescribir `README.md` completo desde cero — rechazada, ver punto 3: el brief pide
  explícitamente lo mínimo necesario, no un documento nuevo.
- Crear un `CHANGELOG.md` real publicado como parte de este change — rechazada explícitamente por
  el usuario (§18: "NO crear un framework nuevo... NO publicar release").
- Delegar la validación E2E a un subagente adicional — rechazada, ver punto 5: son verificaciones
  read-only con Bash, que python-data-engineer no tiene, y el brief pide explícitamente minimizar
  subagentes en este change ("1 writer si hay fixes reales; 1 reviewer final").
- Regenerar `control.json` al principio del change (para tener una "foto" temprana) — rechazada,
  ver punto 6: quedaría desactualizado en cuanto se aplicaran los fixes de versión/README.

## Riesgos
- Romper el hash-pin de 2 changes ya cerrados (punto 2) podría, en teoría, confundir una futura
  auditoría que espere que `control["aprobaciones"]` siempre coincida con el contenido actual —
  mitigado documentando la excepción explícitamente en `proposal.md`/`verification.md` de este
  change, que queda como el registro auditable de POR QUÉ y CUÁNDO se rompió esa invariante, y
  para qué (un BLOCKER de privacidad real, no un descuido).
- La validación E2E de progressive sync (R7) y readiness/promotion (R8) puede revelar
  comportamiento inesperado en combinaciones no cubiertas por los tests unitarios existentes de
  Changes 6-8 — aceptado como el propósito mismo de este change (encontrarlo AHORA, antes del
  release, es exactamente el valor de un change de hardening).
- Regenerar `control.json` al final es una escritura real sobre este propio repo (no un repo de
  fixture) — mitigado porque `regenerar_control` ya está ampliamente testeado (Changes 0/7) y es
  no-destructivo por diseño (recalcula hashes de archivos ya presentes, no reinstala nada).

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
Ver `proposal.md § Aprobación`.
