# Spec — 20261021-v012-diagnosing-bugs

**R1.** `diagnosing-bugs.md` pasa `validar_skill` (sin claves nuevas, sin `artifacts`).
**R2.** Workflow en orden: reproduce, minimize, classify, formulate hypothesis, instrument, test hypothesis, fix root cause, regression test, verify.
**R3.** Clases: code bug, data issue, environment, configuration, contract mismatch, expected behavior, nondeterminism. Exige separar síntoma de causa raíz.
**R4.** Baseline-aware: ante fallo durante un Change y duda razonable, evaluar el baseline de forma focalizada (el test/archivo concreto en el commit baseline, nunca la suite completa) y clasificar introduced | pre-existing | environment | inconclusive; `inconclusive` no se atribuye ni se ignora, se registra.
**R5.** No crea debugger, no reemplaza tests ni reviewer; el regression test sigue `methodology.md` §29; no cambia topes de remediation/reintentos; ejecuta solo vía runtime gobernado (`ds_guard exec`); sin autoridad.
**R6.** Datos: un data issue no se «arregla» tocando raw ni holdouts; ante holdout/dataset sellado rigen los STOPs vigentes.
**R7.** Instalable: manifest VERBATIM, Doctor, SKILL.md/methodology §38/ARCHITECTURE y espejos en paridad.
**R8.** Tests específicos + smokes afectados; sin regresión completa.
