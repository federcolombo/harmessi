# Verificación — 20261021-v012-release-hardening

## Resumen
Change 6 de v0.12: versión `0.12.0`, notas de release (inglés), smoke de release, baseline managed regenerado una vez, regresión completa por batches seriales, fresh install, upgrade desde el tag público `v0.11.0`, Doctor, privacidad y dogfooding A–E con fixtures sintéticos. Sin features nuevas. SDD aprobado por hash (T0/declared, autorización anticipada).

## Evidencia obtenida

### Regresión completa (serial, P=1, foreground; ledger por módulo)
| batch | modules | attempted | passed | skipped | failed |
|---|---|---|---|---|---|
| unittest (módulos `tools/**/test_*.py`) | 204 | 5838 | 5777 | 61 | 0 |
| pytest (.venv, módulos pytest-only) | 21 | 277 | 277 | 0 | 0 |
- Total 225 módulos, 0 fallos tras la corrección. Primera pasada: 221 módulos verdes y 4 fallos (`test_v09/v010/v011/v012_release_hardening_smoke`: el baseline `.ds_init/control.json` seguía en 0.11.0 ≠ 0.12.0); se regeneró el baseline una vez y se repitieron SOLO esos 4 módulos (12 + 21 + 19 + 22 OK). Los 3 módulos de datacontracts que unittest no recolecta se corrieron con pytest.
- Incidente operativo: una corrida en background fue terminada por el sistema por poca memoria; no se relanzó en background, se continuó en foreground con tandas acotadas desde el ledger (los módulos de `ds_init`/`harmessi` tardan minutos cada uno).
- Los conteos de pytest son los del resumen de pytest (sin desglosar subtests); no son comparables 1:1 con v0.11.

### Baseline managed
`regenerar_control(..., stage="experiment")` una vez: `harness_version` 0.12.0, 130 entradas; `migrate-hashes` dry-run: Migrables 0, Ya actuales 130, No verificables 0, Desconocidas 0.

### Doctor
Este repositorio: 30 OK, 1 WARN (`CORE-WORKING-TREE`, árbol sin commitear durante el check), 0 ERROR, 4 N/A. Proyectos temporales (instalado y actualizado): único ERROR esperado `RUNTIME-INTERPRETE` por ausencia de `.venv` en directorios temporales; `HARMESSI-SKILL-CONTRATO` OK y `HARMESSI-MIGRACION` OK; WARN `HARMESSI-DRIFT` solo por la edición intencional de `CLAUDE.md` del proyecto.

### Fresh install y upgrade (directorios temporales)
- **Fresh v0.12.0:** `install --execute` → 130 archivos; `harness_version` 0.12.0; las 4 skills instaladas y válidas; `GLOSSARY.md` NO creado.
- **Upgrade desde el tag público `v0.11.0`** (checkout del tag con `git archive`, instalado con su propio ds_init, 127 archivos; más `GLOSSARY.md`, datos, `NOTAS.md` y una línea propia en `CLAUDE.md` como estado del proyecto): `upgrade` dry-run listó 7 managed a actualizar y 3 skills a crear, con los guardrails y `CLAUDE.md` del proyecto preservados; `--execute`: «Upgrade completo ('0.11.0' -> '0.12.0'): 7 actualizado(s), 3 creado(s)»; sha256 de los archivos project-owned idénticos antes y después; con árbol limpio la segunda corrida fue «Nada que hacer». Con árbol sin commitear `upgrade` aborta (comportamiento de seguridad esperado). `glossary check` sin hallazgos.

### Dogfooding (fixtures sintéticos genéricos; observaciones cualitativas)
- **A. Framing:** brief ambiguo de «churn» sintético → `problem-framing`: los elementos materiales (población, éxito) se explicitan en los artefactos del Change; el resto se infiere o queda como supuesto trazable. Sin interrogatorio.
- **B. Framing → domain-modeling:** el término «cliente activo» queda como `hypothesis` con `ambiguedad: material`; `ds_guard glossary check` reporta `PENDIENTE (ambigüedad material)`: aparece el checkpoint humano, no se inventa la definición.
- **C. Debugging:** función de normalización min-max con rango cero → reproduce (ZeroDivisionError) → minimize (caso constante) → classify (code bug) → hipótesis falsable → fix de causa raíz → test de regresión → verify (2 tests OK). El baseline focalizado de solo lectura (`git show HEAD:<ruta>`) sobre un archivo inexistente en el baseline da `inconclusive`, como prescribe la skill.
- **D. Codebase design:** una feature nueva reutiliza la primitiva existente (reuse > extend); `ds_guard impact scan --since HEAD~1` reporta 0 consumidores potencialmente afectados (análisis estático).
- **E. Composición:** `tasks.md` con `## Skills cargados` con 2 skills (`problem-framing`, `domain-modeling`) valida sin hallazgos; una skill inexistente produce `SKILL-REFERENCIA-DESCONOCIDA`; las otras dos skills no se citan ni se cargan.
- Observación: una segunda sección `## Skills cargados` duplicada en `tasks.md` se ignora en silencio (solo se lee la primera); se descubrió al armar el fixture y queda documentada como limitación.

### Roles, permisos y hooks sin cambio
`git diff v0.11.0` sobre los contratos de agentes, `settings.json`, la configuración de guardrails y los launchers de hooks → vacío.

### Reviewer (notas, smoke, privacidad)
1 ciclo, sin blocker. 2 HIGH de proceso (declarar «publicada» y referenciar esta verificación antes de que existiera; se resuelven con este archivo y el commit de release), 5 MED y LOW aplicados: roadmap «cerrado», regla de conflicto fiel a §40, limitaciones faltantes (ownership por instancia/H1, enum de decisiones, sección duplicada), test de diff contra el tag para roles/permisos/settings, barrido de privacidad reforzado (emails, rutas de usuario, tokens), negaciones y límites anclados a su sección. Los fixes son de texto y tests y no cambian materialmente lo revisado: sin segundo ciclo. Smokes tras los fixes: 162 tests OK.

### Privacidad
Barrido de los archivos cambiados desde `917339f` (rutas personales, emails, tokens): solo registros de aprobación de `control.json` por el flujo estándar y fixtures sintéticos preexistentes. `git ls-files docs/feedback .harmessi` vacío.

## Limitaciones
Validación en host Windows únicamente. Las skills son guidance: la calidad metodológica se revisa, no se testea (evals ≠ tests). La traza `## Skills cargados` es cooperativa. H1 sigue UNCONFIRMED. Deudas diferidas: ver `docs/roadmap/v0.12.md`.

## Divergencias respecto del SDD
Regresión por módulo con ledger en lugar de por directorio (restricción de memoria).

## Resultado final
Candidato 0.12.0 verificado: regresión verde, fresh install y upgrade verdes, dogfood A–E verde, Doctor sin errores de producto, baseline coherente, privacidad limpia. Listo para publicar.
