# Spec — 20261021-v012-codebase-design

**R1.** `codebase-design.md` pasa `validar_skill` (sin claves nuevas, sin `artifacts`).
**R2.** Temas a razonar: boundaries, ownership de módulos, acoplamiento, cohesión, primitivas existentes, contrato público/interno, dirección de dependencias, impact radius, compatibilidad hacia atrás, migración, test seams.
**R3.** Preferencia explícita y ordenada: reusar primitiva existente > extender > nueva primitiva local > nuevo subsistema/framework; evitar duplicación, wrappers innecesarios, framework creep, abstracciones sin consumidor (un consumidor real concreto como criterio de entrada).
**R4.** Usa `ds_guard impact scan` (y el Impact Preflight de methodology §25) para el radio de impacto; no lo reimplementa. Produce su razonamiento en artefactos existentes (design.md del Change); no crea artefacto nuevo.
**R5.** Asesora: no decide permisos/runtime/scope; las decisiones materiales (cambio incompatible, dependencia nueva relevante, expansión de scope) siguen siendo STOP / decisión humana; no autoriza a editar fuera del ownership.
**R6.** Instalable: manifest VERBATIM, Doctor, SKILL.md/methodology §39/ARCHITECTURE §9.3 y espejos en paridad.
**R7.** Tests anclados por sección (preferencia ordenada, los temas, ausencia de autoridad), Doctor negativo, manifest; normalizar espacios.
**R8.** Tests específicos + smokes afectados; sin regresión completa.
