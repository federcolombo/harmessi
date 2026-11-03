# Spec — 20261102-v1-release-hardening

## Requisitos
- R1 (G13) `HARMESSI-LICENSE.txt` es un asset managed VERBATIM en la raíz, presente en `MANIFEST`, en el baseline y en toda
  instalación; declara términos/notice de los componentes Harmessi y que NO relicencia el proyecto del usuario; no existe `LICENSE`
  genérico en la instalación.
- R2 (G1) Ancla de licencia: `LICENSE` idéntico (normalizando CRLF) al texto oficial PolyForm Shield 1.0.0; `NOTICE` contiene
  `Required Notice:`; ningún "Apache" ni "open source" fuera de una allowlist explícita de notas históricas.
- R3 (G5) El README y `docs/installation.md` declaran: Python 3.12 verificado en CI (ubuntu/windows/macos, lista acotada) y 3.9 como mínimo
  declarado y no ejecutado.
- R4 (G6) `HARNESS_VERSION`, `CITATION.cff` y `.ds_init/control.json` coinciden en `1.0.0`; `docs/releases/v1.0.0.md` existe con
  Compatibility, Known limitations (incluye G11 y G14) y Deferred; el README menciona v1.0.0, v0.15.0 y v0.14.0.
- R5 (G6) Upgrade 0.15.0→1.0.0: crea el asset como managed nuevo, 0 drift, y una segunda corrida es idempotente ("Nada que hacer").
- R6 El baseline se regenera una sola vez al final; Doctor sin `HARMESSI-DRIFT`; 0 ERROR en checkout, instalación limpia y upgrade.
- R7 Regresión serial completa sin fallos no explicados; barrido de privacidad verde; clon sin tags sin fallos (skips permitidos).
- R8 Las docs hablan de 1.0.0 en presente y conservan los textos que `test_v1_stable_contracts.py` ancla.

## Criterios de aceptación
- [ ] R1: test de manifest (VERBATIM, discovery, fuente existe), de baseline (hash correcto), de install y del texto (frases "no relicencia").
- [ ] R2: `test_license_anchor.py` verde con golden en `tools/tests/fixtures/license/`; falla si se agrega "Apache" fuera de la allowlist.
- [ ] R3: tests que leen README e installation.md y exigen 3.12 y 3.9 con la salvedad "no ejecutado".
- [ ] R4: `test_v1_release_hardening_smoke.py` verde; `test_v015_compat_window.py` sin ancla estricta a 0.15.0.
- [ ] R5: `test_v1_license_asset.py` cubre install, upgrade desde baseline previo sin el asset y re-upgrade idempotente.
- [ ] R6/R7: evidencia real de las corridas en `verification.md` (números salen de la salida, no de memoria).
- [ ] R8: `test_v1_stable_contracts.py`, `test_public_docs`, `test_privacy_sweep` verdes.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica.

## Baseline (condicional — modeling)
No aplica (el "baseline" aquí es `.ds_init/control.json`).

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
