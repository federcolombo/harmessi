---
name: diagnosing-bugs
purpose: Diagnosticar fallos de forma sistemática, separando síntoma de causa raíz y atribuyendo el fallo (introducido, preexistente, entorno) con evidencia focalizada, sin prueba y error.
when_to_load: Cuando un test o pipeline está roto o un resultado es inesperado y la causa no es evidente; no para fallos triviales evidentes (typo, import faltante, mensaje de error que ya señala la línea).
roles: [lead-data-scientist, python-data-engineer, data-science-reviewer, metodologo]
---

# diagnosing-bugs

## 1. Guidance, nunca authority

Esta skill no otorga permisos, tools, hooks, ejecución, lifecycle ni ampliación de scope. No cambia aprobaciones, no salta STOPs y no cambia los topes de remediation ni de reintentos. No reemplaza tests ni al reviewer.

## 2. Cuándo cargar

- Un test o pipeline está roto, o un resultado es inesperado, y la causa no es evidente.
- NO se carga para fallos triviales evidentes: se corrigen directamente.

## 3. Workflow

Cada paso exige una evidencia observable; sin evidencia no se avanza al siguiente. No se corrige por prueba y error.

1. **reproduce**: ejecutar el caso y capturar el fallo (comando, salida, semilla). Evidencia: el fallo se repite. Si reproducir implica un proceso largo sobre datasets completos, rige el aviso previo de CLAUDE.md §1; con holdouts, STOP.
2. **minimize**: reducir al mínimo test, archivo o dato que lo dispara. Evidencia: caso mínimo que sigue fallando.
3. **classify**: asignar una clase de fallo (sección 4). Evidencia: el dato que justifica la clase.
4. **hypothesis**: formular una causa falsable: qué observación la refutaría. Una hipótesis que ninguna observación puede refutar no sirve.
5. **instrument**: agregar el mínimo de logs, asserts o inspección para observar lo que decide la hipótesis (sección 7 dice quién y dónde). Evidencia: la observación existe y es reproducible.
6. **test hypothesis**: contrastar la hipótesis con esa observación. Si se refuta, volver a 4 con lo aprendido. Los ciclos 6→4 están acotados: tras 3 ciclos sin una hipótesis nueva y falsable se escala al humano o al `metodologo`, no se sigue probando. Es un tope propio del diagnóstico, no de remediation.
7. **fix root cause**: corregir la causa, no el síntoma (sección 5). Evidencia: el cambio explica la observación del paso 6. Un intento de fix fallido cuenta como reintento/remediation (máximo según methodology §16 y sdd §8).
8. **regression test**: cuando aplique según methodology §29, un test que falla antes del fix y pasa después. Se escribe antes del fix, o se comprueba que falla revirtiendo el fix en una copia. No aplica a environment, configuration ni expected behavior sin cambio de código.
9. **verify**: reejecutar el caso original y el mínimo, y retirar la instrumentación. Evidencia: ambos pasan.

## 4. Clases de fallo

- **code bug**: error en el código. Fix en el código + regression test.
- **data issue**: el dato no cumple lo esperado. No se toca `raw/` ni holdouts/datos sellados; se corrige aguas arriba en la transformación o se escala al Lead.
- **environment**: dependencia, versión, ruta o intérprete. No se atribuye al código; se documenta. Instalar dependencias va por el mecanismo gobernado, con aviso.
- **configuration**: parámetro o constante mal fijada. Se corrige en el bloque editable de setup.
- **contract mismatch**: el dato real difiere del Data Contract. El diagnóstico PROPONE; decide el Lead/humano. Se resuelve contra el Data Contract o el Decision Ledger (que requiere decisión aprobada); no se parchea silenciosamente.
- **expected behavior**: el comportamiento es correcto y la expectativa es la errónea. El diagnóstico PROPONE corregir test o expectativa; decide el Lead/humano, y no se debilita un test sin que lo vea el reviewer.
- **nondeterminism**: el resultado varía entre corridas. Fijar `RANDOM_STATE`/semilla y revisar orden de datos y paralelismo antes de cualquier otra hipótesis.

La clase `environment` describe la causa del fallo (paso 3); `environment` en la sección 6 es una atribución respecto del baseline. Pueden coincidir pero no son lo mismo.

## 5. Síntoma ≠ causa raíz

Silenciar el error, relajar un assert, capturar la excepción o reintentar hasta que pase es tratar el síntoma. Se pregunta «¿por qué ocurre?» hasta llegar a una causa que, corregida, elimina la clase de fallo y no solo este caso. Si la causa raíz es metodológica (leakage, validación), va al Decision Ledger o al `metodologo`; se escala al Lead/humano, que decide si se reabre el SDD. No es remediation.

## 6. Baseline-aware

Solo ante un fallo durante un Change Y duda razonable de si lo introdujo el Change (no ante todo fallo), de forma focalizada y de SOLO LECTURA:

- Leer el baseline con `git show <commit>:<ruta>` o `git diff <commit> -- <ruta>` (commit baseline en `control.json`).
- Si hay que ejecutar: extraer solo los archivos mínimos con `git show <commit>:<ruta>` al «área temporal», un único directorio temporal definido una sola vez. Debe estar en el scope del Change, verificarse con `git check-ignore`, no ser nunca `data/` ni `.harmessi/`, y se limpia al terminar. Si no hay un directorio así disponible ⇒ `inconclusive`. Correr SOLO el test concreto (test actual contra código baseline); si el test no existe en baseline ⇒ `inconclusive`. Nunca la suite completa.
- Prohibido `git checkout`, `stash`, `reset`, `clean`, `switch` sobre el árbol del usuario y mover HEAD.
- `data/` no está versionada: un fallo por datos ausentes es `environment` o `inconclusive`, nunca `pre-existing`.
- Nunca correr pipelines, notebooks, tests ni scripts que lean datasets completos u holdouts: ante eso, `inconclusive` o STOP.
- Clasificación: `introduced` (falla ahora, pasa en baseline), `pre-existing` (falla también en baseline), `environment` (depende del entorno, no del código) o `inconclusive` (no se puede determinar).
- `inconclusive` se registra como tal (tasks/verification): ni se atribuye al Change ni se ignora.

## 7. Quién hace qué

- El Lead diagnostica y ejecuta vía el runtime gobernado (`ds_guard exec`); no hay runner ni debugger nuevo.
- La instrumentación la escribe el writer dentro de su ownership/scope, o es un script desechable en el «área temporal» (sección 6); el Lead la ejecuta y se retira en verify.
- El writer corrige la causa raíz y agrega el regression test (methodology §29), dentro de su ownership.
- El reviewer lee y revisa; no ejecuta ni corrige.
- El `metodologo` interviene si la causa es metodológica; es una invocación que cuenta contra el presupuesto de roles.
- Privacidad: casos mínimos con datos sintéticos o agregados; no se imprimen registros individuales. Ante holdout o dataset sellado el Lead se detiene (STOP vigente).
- Los topes de remediation y de reintentos no cambian.

## 8. Separación

- Diagnóstico: por qué falla y de dónde viene.
- Tests (methodology §29): qué comportamiento queda protegido.
- Reviewer: control independiente del cambio.
- Data Contract / Decision Ledger: qué debe cumplir el dato y por qué se decidió algo.

No se fusionan ni se duplican: se referencian por id en la prosa.
