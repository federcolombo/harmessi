# Diseño — 20261102-v1-release-hardening

## Decisión metodológica/técnica

- D1 Asset de licencia VERBATIM con fuente en la raíz (`HARMESSI-LICENSE.txt`): así `regenerar_control` lo hashea y entra al baseline
  propio. No se usa PLANTILLA bajo `profiles/` porque el repo propio no tendría el archivo. Nombre distinto de `LICENSE` para no
  sugerir que relicencia el proyecto del usuario.
- D2 Golden de licencia: el texto oficial PolyForm Shield 1.0.0 se guarda como fixture y se compara contra `LICENSE` normalizando CRLF a LF.
  Se obtiene de la fuente oficial al implementar; si no se puede verificar contra la fuente oficial, el golden es el `LICENSE` actual
  (introducido en `c11a21e`) y la limitación se declara en `verification.md`.
- D3 Allowlist de "Apache"/"open source": solo líneas que digan versiones v0.x / anteriores / "Apache License 2.0" históricas y
  "not open source" / "no open source". Barrido sobre `LICENSE`, `NOTICE`, `CITATION.cff`, `README.md`, `HARMESSI-LICENSE.txt`,
  `COMMERCIAL-LICENSE.md` y `docs/*.md` excluyendo `docs/roadmap/**` y `docs/releases/v0.*`.
- D4 Orden para evitar `HARMESSI-DRIFT`: primero todo el contenido (asset, manifest, `.gitattributes`, versión, docs, README),
  luego tests, y **al final** `regenerar_control` una sola vez. Cualquier edición posterior a un archivo managed obliga a regenerar de nuevo
  y se registra como excepción.
- D5 No se toca `.claude/settings.json`, agentes ni guardrails (los guards contra tags comparan su contenido).
- D6 README: se conservan los bloques v0.14.0 y v0.15.0 (los smokes previos exigen su mención); se agrega el de v1.0.0.
- D7 El upgrade 0.15.0→1.0.0 se prueba con un baseline simulado sin la entrada del asset (test) y con una instalación real desde el
  tag `v0.15.0` (`git archive`) en la corrida de verificación.
- D8 Regresión serial en lotes y en background, un lote a la vez, con ledger; no se repiten módulos verdes.

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
Sin desvío.

## Alternativas descartadas

- Plantilla bajo `profiles/` para el asset: el baseline propio no lo listaría (D1).
- Un `LICENSE` en la instalación: implicaría relicenciar el proyecto del usuario.
- Endurecer `schema_version` en `registry.py`: código de producción, POST-v1.
- Cambiar la matriz de CI a 3.9: ampliaría el alcance; se declara 3.9 como no ejecutado (G5).

## Riesgos

- `HARMESSI-DRIFT` por editar un managed tras regenerar el baseline (D4).
- El asset y el golden entran al barrido de privacidad por ser `.txt`: se verifica que no disparen `RE_RUTA_UNIX`/`RE_EMAIL`.
- CRLF/LF en Windows al hashear: el baseline usa `sha256/eol-lf/v1`; `.gitattributes` fija LF para el asset.
- Sin red para verificar el texto oficial (D2).

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
