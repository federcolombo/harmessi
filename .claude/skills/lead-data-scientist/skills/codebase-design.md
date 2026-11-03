---
name: codebase-design
purpose: Razonar antes de un cambio estructural en la codebase del proyecto (boundaries, acoplamiento, primitivas existentes, contratos, impacto, migración) prefiriendo reusar a extender y extender a crear, sin sobre-diseñar.
when_to_load: Cuando el cambio es estructural (módulo nuevo, mover responsabilidades entre módulos, cambiar un contrato interno o público, dependencia entre módulos); no para cambios locales dentro de una función o módulo que no alteran sus contratos.
roles: [lead-data-scientist, python-data-engineer, data-science-reviewer, metodologo]
---

# codebase-design

## 1. Guidance, nunca authority

Esta skill no otorga permisos, tools, hooks, ejecución, lifecycle ni ampliación de scope. No cambia aprobaciones, no salta STOPs y no autoriza a editar fuera del ownership. Aplica a la codebase del PROYECTO; no impone la arquitectura de Harmessi. No reemplaza al reviewer.

## 2. Cuándo cargar

- Cambio estructural: módulo nuevo, mover responsabilidades entre módulos, cambiar un contrato interno o público, o crear una dependencia entre módulos del proyecto (no confundir con una dependencia externa: un paquete, ver sección 4).
- NO se carga para cambios locales (un bug acotado, un renombre interno, una función que no altera contratos): se hacen directamente.
- Se aplica en la fase de diseño del Change, antes de delegar al writer.
- Proporcionalidad: se razonan solo los temas pertinentes; para un módulo local pequeño bastan 2 o 3 líneas.

## 3. Temas a razonar

Cada tema se responde con una pregunta concreta:

- **boundaries**: ¿dónde termina la responsabilidad de este módulo y empieza la de otro?
- **ownership de módulos**: ¿quién es dueño de cada archivo afectado y está dentro del ownership autorizado?
- **acoplamiento**: ¿qué tendría que cambiar en otros módulos si este cambia?
- **cohesión**: ¿las piezas que viven juntas cambian por la misma razón?
- **primitivas existentes**: ¿ya existe una función, clase o utilidad que resuelva esto?
- **contrato público/interno**: ¿qué usan otros fuera del módulo y qué es detalle interno?
- **dirección de dependencias**: ¿las dependencias apuntan de lo específico a lo general, sin ciclos?
- **impact radius**: ¿qué archivos podrían verse afectados? (sección 5)
- **compatibilidad hacia atrás**: ¿los consumidores actuales siguen funcionando sin cambios? Solo importa si hay consumidores fuera del control del Change.
- **migración**: ¿cómo se pasa del estado actual al nuevo, en qué pasos y con qué plan de vuelta atrás?
- **test seams**: ¿dónde se puede probar el comportamiento en aislamiento? Solo con un consumidor real que lo necesite.

Anclas de ciencia de datos: no sacar del pipeline las transformaciones que aprenden de los datos (escalado, imputación, encoding); respetar el flujo `raw/` → `interim/` → `processed/`; los notebooks importan de `utils/`, no duplican.

## 4. Escalera de preferencia

Se baja un escalón solo si el anterior no alcanza, y se anota por qué:

1. **reuse**: reusar una primitiva existente tal como está.
2. **extend**: extender la existente de forma compatible.
3. **new local primitive**: una primitiva nueva y local al módulo que la necesita.
4. **new subsystem/framework**: un subsistema o framework nuevo; último recurso.

Criterio de entrada para crear algo nuevo (escalones 3 y 4): un consumidor real y concreto que existe hoy, no uno hipotético. Se evita:

- duplicación de lógica que ya existe;
- wrappers innecesarios que solo delegan sin agregar valor;
- framework creep: un mecanismo genérico donde bastaba una función;
- abstracciones sin consumidor.

Bajar al escalón 4, o sumar cualquier dependencia externa nueva relevante, es una propuesta: se espera la aprobación humana (CLAUDE.md §3 y §1); el Lead no lo decide solo.

Ejemplo genérico: dos notebooks necesitan la misma limpieza de fechas. Primero se busca si una utilidad existente la cubre (reuse); si cubre casi todo, se la extiende con un parámetro opcional (extend); solo si no encaja se crea una función nueva en el módulo de utilidades (new local primitive). Un registro de estrategias configurable sin segundo consumidor no entra.

## 5. Impact radius

El radio de impacto se obtiene con `ds_guard impact scan` y el Impact Preflight de methodology §25. Esta skill no lo reimplementa ni lo reemplaza. Rigen las reglas de §25:

- Lo corre el Lead mismo, no el writer ni el reviewer.
- Es solo estático: lo que devuelve es «potencialmente afectado», no un veredicto.
- Nunca es obligatorio para un cambio trivial.
- Si `dsimpact` no está disponible, el Lead razona a mano el radio y lo anota.

## 6. Compatibilidad y migración

- Distinguir qué es público (lo que importan o invocan otros módulos, notebooks o scripts) y qué es interno (se puede cambiar libremente).
- Si todos los consumidores están en el mismo repo y dentro del Change, se los actualiza de forma atómica, sin shims. Si hay consumidores fuera del control del Change, preferir cambios aditivos, mantener la firma anterior y migrar de a uno.
- Plan de migración: pasos ordenados, cada uno con su verificación y un plan de vuelta atrás. El rollback es un plan escrito, no una acción; está prohibido `git reset`, `checkout`, `stash` o `clean` sobre el árbol del usuario.
- Un cambio incompatible, una dependencia nueva relevante o una expansión de scope requieren decisión humana: rige el STOP vigente. La skill los señala pero no los resuelve.

## 7. Dónde registrar el razonamiento

- Si el Change aún no está aprobado, en su `design.md`, con las alternativas consideradas y por qué se descartaron.
- Si el Change ya está aprobado, en `verification.md` o en una nota del Lead, sin tocar los artefactos aprobados.
- Si no hay SDD (tarea pequeña), en el mensaje al humano.
- Una «enmienda» es la enmienda de scope gobernada (`ds_guard scope amend`, requiere humano T1) y solo aplica cuando cambia el scope; no sirve para registrar razonamiento.
- Decision Ledger: para una decisión con porqué que conviene recordar. Propone el Lead o el `metodologo`, registra el Lead y aprueba el usuario (decision-ledger.md §4-§5); nunca es automático.
- No crea artefactos nuevos.

## 8. Quién hace qué

- Asesora al Lead, que sigue siendo quien decide el diseño y lo somete a aprobación humana cuando corresponde.
- El writer implementa solo dentro de su ownership; si el diseño exige tocar un archivo ajeno, lo devuelve al Lead.
- El reviewer lee y revisa que el cambio respete el diseño y la escalera de preferencia; no ejecuta ni corrige.
- El `metodologo` interviene si el diseño toca la validez metodológica (por ejemplo, dónde viven las transformaciones que aprenden).
- Nadie decide por esta skill permisos, runtime ni scope.

## 9. Separación

- Diseño: cómo se estructura el cambio y por qué.
- Impact preflight (methodology §25): qué podría verse afectado.
- Reviewer: control independiente del resultado.
- Decision Ledger: qué se decidió y por qué.

No se fusionan ni se duplican: se referencian en la prosa.
