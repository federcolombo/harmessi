# Spec — 20261021-v012-skill-selection-composition

**R1.** Tabla de selección en `methodology.md` §40: ambigüedad de problema → `problem-framing`; concepto de negocio → `domain-modeling`; bug/fallo → `diagnosing-bugs`; cambio estructural → `codebase-design`. Las skills de proyecto se seleccionan por su `when_to_load`.
**R2.** Carga mínima: solo las pertinentes; ninguna si ninguna aplica; no cargar «todas siempre»; leer la skill cuando se necesita, no por adelantado (menos contexto/tokens).
**R3.** Composición simple: pares razonables (`problem-framing`+`domain-modeling`; `diagnosing-bugs`+`codebase-design`; otras combinaciones solo si los `when_to_load` de ambas aplican); sin resolver de dependencias, grafo, registry, marketplace ni plugins.
**R4.** Conflicto: precedencia governance/runtime > contrato del rol > contrato del proyecto > guidance de skill (sin cambio). Entre dos skills, el Lead resuelve semánticamente sin violar capas superiores y deja constancia del criterio en el motivo de la traza; si el conflicto involucra una capa superior gana esa capa y rigen los STOPs vigentes; no hay merge engine. Se reemplaza «el Lead se detiene y consulta» en SKILL.md, §28 y ARCHITECTURE §7.2.
**R5.** Traza: se registra en `## Skills cargados` (`- <skill> — <tarea> — <motivo>`) solo cuando la skill influye materialmente (decisión, criterios de aceptación, delegación, scope/ownership, diseño); no lecturas triviales; composición = un bullet por skill; sin telemetría.
**R6.** Se preserva la foundation v0.10: skills = markdown, bajo demanda, sin permisos, sin hooks, sin ejecución (afirmación explícita en §40).
**R7.** `SKILL.md` reorganiza la sección «Skills componibles» (breve, con puntero a §40) y `templates/tasks.md`/`sdd.md` reflejan el criterio de traza; espejos `.tmpl` en paridad exacta.
**R8.** Test determinista: toda skill distribuida (los `skills/*.md` del repo) aparece en la tabla de selección de §40; tests de frases normativas por sección (espacios normalizados). Sin cambios de código de producción.
**R9.** Tests específicos + smokes afectados; sin regresión completa.
