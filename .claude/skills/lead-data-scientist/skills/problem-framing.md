---
name: problem-framing
purpose: Hacer explícita la formulación del problema (objetivo, decisión, población, éxito, supuestos) antes de analizar o construir, preguntando solo lo material.
when_to_load: Cuando el brief es ambiguo o el pedido es analizar o construir algo sin objetivo, decisión o criterio de éxito claros; no por defecto en toda tarea ni en tareas pequeñas con objetivo explícito.
roles: [lead-data-scientist, metodologo, data-science-reviewer, python-data-engineer]
---

# problem-framing

## 1. Guidance, nunca authority

Esta skill no otorga permisos, tools, hooks, ejecución, lifecycle ni ampliación de scope. No
cambia aprobaciones ni salta STOPs. No es un interrogatorio obligatorio: solo se pregunta lo material.

## 2. Cuándo cargar

- El brief es ambiguo, o el pedido es «analizar» o «construir» algo sin objetivo claro.
- NO se carga por defecto en toda tarea, ni en tareas pequeñas con objetivo explícito.

## 3. Elementos a explicitar

- Objetivo y decisión que el resultado va a soportar.
- Unidad de análisis y población/universo.
- Target (si existe).
- Restricciones y criterios de éxito.
- Evidencia disponible, incógnitas y supuestos.
- Ambigüedades materiales.

Se explicitan solo los elementos que falten y sean materiales; no es un cuestionario.
Materialidad: la misma de `domain-modeling` §4 (target, población, unidad de análisis,
cutoff, KPI, reglas de inclusión/exclusión, interpretación de resultados); se referencia, no se copia.

## 4. Tres niveles

- Inferible o técnica: el Lead decide y sigue, sin preguntar.
- Ambigua pero no material: se adopta un supuesto explícito y trazable. Destino: si el Change aún no está aprobado, su proposal/spec; si ya está aprobado,
  NO se editan proposal/spec (invalida el hash): usar enmienda, Decision Ledger o una nota en
  verification/tasks. Sin Change: en el mensaje al humano y, si es una decisión con porqué, en el ledger.
- Material (cambia el resultado o la decisión): checkpoint humano; no se avanza lo que depende de ella.
- Si es semántica de negocio (qué significa un término), cargar `domain-modeling`; no se
  duplica GLOSSARY ni el ledger.

## 5. Qué producir

Criterios de éxito explícitos y supuestos, escritos en los artefactos existentes del Change
(proposal/spec). No se crea un artefacto nuevo.

## 6. Modo `grill-me` (opt-in)

- Solo si el humano pide desafiar la definición del problema. No es una skill aparte ni se
  activa por defecto.
- Checklist: contradicciones, casos límite, métricas proxy, leakage conceptual (definición o
  target que filtra información futura), población incorrecta, éxito mal definido, requisitos
  incompatibles.
- Lo metodológico (diseño de validación, leakage experimental) se deriva al `metodologo`; es una
  invocación que cuenta contra el presupuesto de roles.
- Sigue sin ser interrogatorio: se plantean solo los hallazgos que importan.

## 7. Separación

- Problem framing: qué problema se resuelve y cómo se sabrá que se resolvió.
- Domain model (`domain-modeling`): qué significa un concepto.
- Decision Ledger: por qué se tomó una decisión.
- Data Contract: qué estructura/evidencia debe cumplir el dato.

No se fusionan ni se duplican: se referencian por id en la prosa.
