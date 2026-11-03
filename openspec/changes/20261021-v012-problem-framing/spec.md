# Spec — 20261021-v012-problem-framing

**R1.** `problem-framing.md` pasa `validar_skill` (name=archivo, `purpose`, `when_to_load`, `roles` conocidos; sin claves nuevas; `artifacts` vacío o ausente).
**R2.** Lista los elementos a explicitar: objetivo, decisión a soportar, unidad de análisis, población/universo, target (si existe), restricciones, criterios de éxito, evidencia disponible, incógnitas, supuestos, ambigüedades materiales.
**R3.** Distingue tres niveles: inferible/técnica (el Lead decide y sigue), ambigua no material (supuesto explícito y trazable, p. ej. en proposal/spec del Change o ledger), material (checkpoint humano). Semántica/negocio ⇒ cargar `domain-modeling` (no se duplica GLOSSARY); decisión con porqué ⇒ Decision Ledger (no se duplica).
**R4.** Sección `grill-me` como modo opt-in: solo si el humano pide desafiar la definición; busca contradicciones, casos límite, métricas proxy, leakage conceptual, población incorrecta, éxito mal definido, requisitos incompatibles; no por defecto; deriva a `metodologo` lo metodológico.
**R5.** Guidance, nunca authority (permisos, scope, aprobaciones, STOPs intactos); no es interrogatorio obligatorio.
**R6.** Instalable: entrada VERBATIM en manifest; Doctor la espera; test de manifest actualizado (skills distribuidas); `SKILL.md`/`methodology.md` (+`.tmpl`) la mencionan con paridad.
**R7.** Tests: contrato, manifest, Doctor, frases normativas (3 niveles, grill-me opt-in, referencia a domain-modeling) y no-regresión de las skills existentes.
**R8.** Tests específicos + smokes afectados; sin regresión completa.
