---
name: domain-modeling
purpose: Mantener un lenguaje de dominio compartido del proyecto (conceptos, definiciones y ambigüedades materiales) sin inferir negocio.
when_to_load: Cuando un brief, un Change o un análisis usa conceptos de negocio (target, población, unidad de análisis, universo, cutoff, KPI, reglas de inclusión/exclusión) o hay dudas sobre qué significa un término.
roles: [lead-data-scientist, python-data-engineer, metodologo, data-science-reviewer]
artifacts: [GLOSSARY.md]
---

# domain-modeling

## 1. Guidance, nunca authority

Esta skill no otorga permisos, tools, hooks, ejecución, lifecycle ni ampliación de scope.
`GLOSSARY.md` debe estar en el scope/ownership del Change antes de editarlo.

## 2. Cuándo identificar conceptos

Al leer un brief, un Change o un dataset, listar los términos de negocio que sostienen una
decisión. Revisar primero `GLOSSARY.md` (raíz del proyecto) si existe.

## 3. Estados

- `hypothesis`: propuesta del Lead, writer, LLM o humano. NO es verdad de negocio.
- `approved`: definición aceptada explícitamente por una persona.

Un LLM nunca convierte `hypothesis` en `approved`, ni por uso repetido ni por coherencia.

## 4. Ambigüedad material

Existen definiciones plausibles distintas que pueden afectar materialmente: target, población,
unidad de análisis, universo, cutoff, métrica de negocio/KPI, regla de inclusión/exclusión,
una variable o concepto usado en una decisión, o la interpretación de resultados materiales.
Un sinónimo o wording menor NO es ambigüedad material.

## 5. Qué hacer ante ambigüedad material

- No inventar la definición.
- Registrar una entrada `hypothesis` con `ambiguedad: material`.
- Pedir resolución humana cuando sea necesaria para continuar (checkpoint).
- No avanzar la decisión que depende de ella.

## 6. Reutilizar approved

Si el término está `approved` y vigente, usarlo sin volver a preguntar. «Approved y vigente»
es lo que devuelve `ds_guard glossary check` sin hallazgos, no la mera presencia de
`estado: approved` en el archivo.

## 7. No inferir negocio desde nombres de columnas

Un nombre de columna es evidencia, no definición.

## 8. Formato de GLOSSARY.md

```
# GLOSSARY

## cliente activo
- estado: hypothesis
- definicion: Cliente con al menos una compra en los últimos 90 días (a confirmar).
- ambiguedad: material
```

Para `approved` se agregan `approval_ref: <change_id>/<artefacto>@<sha256>` y
`definition_hash`.

Notas: un bloque ``` sin cerrar o un `###` dentro de una entrada hacen inválido el GLOSSARY
(`GLOSSARY-MALFORMADO`). Un bloque de código cercado (``` o ~~~) dentro de una entrada también
lo invalida (`GLOSSARY-MALFORMADO`): la definición es prosa. El texto en comentarios HTML
`<!-- -->` dentro de una entrada es anotación: NO forma parte de la definición ni del
`definition_hash`. Términos que difieren solo en espacios, mayúsculas o Unicode se
consideran el mismo término.

## 9. Cómo se aprueba

1. `ds_guard glossary hash --term X` calcula el hash de la definición.
2. Un artefacto del Change (p. ej. `domain-approval.md`) lista término + hash.
3. El humano corre `ds_guard approve --artefacto domain-approval.md --channel console_confirmed`
   (señal de presencia T1, no prueba de identidad).
4. El writer completa `estado: approved`, `approval_ref` y `definition_hash`.
5. `ds_guard glossary check` valida: exige verified + T1 + que el artefacto contenga el hash.
   Si la definición cambia después, la aprobación queda obsoleta.

Prohibido: el agente NO ejecuta `ds_guard approve` para promover un término, ni lo pide fuera
de un checkpoint humano. El humano debe LEER el artefacto antes de aprobarlo; `control.json` no
está autenticado y T1 no prueba autoría ni intención.

## 10. Separación

- Domain Model: qué significa un concepto.
- Decision Ledger: por qué se tomó una decisión.
- Data Contract: qué estructura/evidencia debe cumplir el dato.
- Data Card: qué sabemos de un data product concreto.

No se fusionan ni se duplican: se referencian por id en la prosa. El glossary no es ledger, ni
contract, ni card.
