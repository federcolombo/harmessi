# Diseño — 20261030-v1-contract-stabilization

## Decisión metodológica/técnica

- D1 `stable` = nuevo valor de `clase`; sin cambiar `inventory_version` (valor nuevo de campo existente, aditivo).
- D2 Política de claves desconocidas: se documenta el comportamiento real (top-level aditivo tolerado). Es coherente con SemVer
  ("campo aditivo opcional = minor"). Rechazar claves extra sería un cambio de runtime y rompería lectores viejos con
  artefactos nuevos.
- D3 Snapshot de CLI: introspección del parser (`construir_parser`) sin ejecutar comandos; formato
  `{cli: {ruta_subcomando: {flags: {opcion: {required, choices, nargs}}}}}`. Test de inclusión (snapshot ⊆ vivo). ds_init usa el
  posicional `accion` con `choices`; se modela como "subcomandos". Si importar `ds_guard.construir_parser` tiene efectos
  secundarios, se usa subproceso `--help` recursivo.
- D4 Los fixtures se generan con el código del tag v0.15.0 (`git archive` en directorio vacío; el generador valida
  `HARNESS_VERSION == 0.15.0`), nunca a mano. Deben generarse antes del corte público porque los tags se borran.
- D5 Ventana 1.0: 1.x completo + lectura de artefactos de 0.15 con fixture. Lo `experimental`/`internal` queda explícitamente
  fuera.
- D6 No se bumpea la versión ni se toca el runtime aquí; las docs hablan de "a partir de 1.0.0".

## Target (condicional — feature_engineering, modeling)

## Features permitidas/prohibidas (condicional — feature_engineering)

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
<!-- riesgos considerados por quien propone, incluida la clase "foto sin fecha" de CLAUDE.md;
complementa, no reemplaza, la revisión independiente de data-science-reviewer -->

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)

## Alternativas descartadas

- Promover más contratos (improve, Data Card): amplía el compromiso sin necesidad; POST-v1.
- Rechazar claves extra: cambio de runtime; descartado (D2).
- Congelar `--help` textual: frágil; se ancla la estructura, no el texto.

## Riesgos

- Efectos secundarios al importar `tools/ds_guard.py`: mitigado con subproceso.
- Generar fixtures del tag en Windows: CRLF; el MANIFEST se verifica normalizando saltos de línea.
- El snapshot fija la superficie de v0.15.0: si una CLI ya perdió algo respecto de 0.15 el test lo marca (es lo deseado).

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
