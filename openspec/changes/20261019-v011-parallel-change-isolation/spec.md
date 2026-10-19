# Spec — 20261019-v011-parallel-change-isolation

## Requisitos
**R1.** `scope.otros_changes_activos(repo_root, change_id_propio)` lista los Changes en `openspec/changes/` (no `archive`) distintos del propio cuyo `tasks.md` declara estado en `{aprobada_implementacion, en_implementacion, en_verificacion}`. Un ajeno cuenta (para atribuir y para conflicto) solo si es «activo y aprobado», verificado sobre el SNAPSHOT del ajeno en el commit baseline del Change propio, no sobre disco. (a) El baseline propio (`control["baseline"]["commit"]`) debe ser un SHA hexadecimal completo (40 o 64 caracteres); `HEAD`, ramas, prefijos cortos, ausente o ref inexistente => ningún ajeno cuenta, sin hallazgo extra. (b) En ese commit, `tasks.md`, `control.json` y los artefactos se leen con `git show`: el estado (`tasks.md`) debe estar en `{aprobada_implementacion, en_implementacion, en_verificacion}`, `control.json` debe tener `alcance.scope_hash`, y CADA artefacto de `sdd.artefactos_requeridos(modo)` (modo inválido => `completo`) debe tener su aprobación más reciente en `aprobaciones[]` con el hash `hash_lf_v1` del contenido del artefacto en ese mismo commit. (c) El `alcance.scope_hash` del `control.json` en disco debe ser igual al del baseline (ancla inmutable); si difiere, o `control.json` en disco es ilegible, => `ALCANCE-OTRO-CHANGE-INVALIDO` (R4). (d) El alcance efectivo del ajeno se calcula desde disco con `alcance_efectivo` (cadena de enmiendas), de modo que enmiendas legítimas posteriores al baseline se respetan. Limitaciones documentadas: un ajeno aprobado/activado DESPUÉS del baseline propio no atribuye (fail-closed); la atribución es «honesta, no autenticada»: forjar un ajeno requiere un commit previo al baseline propio con aprobación y hashes coherentes, lo que eleva el costo de la evasión pero no la hace imposible; la garantía real del alcance propio nunca se afloja (D1). Un ajeno legítimo que edita su propio `tasks.md`/`control.json` en paralelo sigue atribuyendo (el estado/aprobación se miden en el baseline). `propuesta_pendiente`, `aprobada_diseño`, `pausada_bloqueada`, `cerrada`, `descartada`, estado desconocido, `tasks.md` ausente/ilegible o control sin `scope_hash` (legado), ajeno ausente del baseline propio o con algún artefacto requerido sin aprobación verificada en el baseline NO cuentan: se ignoran sin hallazgo (fail-closed: atribuir menos es el lado seguro). De las rutas de un ajeno que cuenta se descartan (no atribuyen ni generan conflicto) los patrones catch-all (sin prefijo literal de directorio: `*`, `**`, `**/*`, `*/**`, `*.py`, `s?c/**`, `[a-z]*/**`) y los que `scope_amendments.motivo_ruta_invalida` rechaza (`.`/`..`, absolutas, `.git`, `.harmessi`, `data/raw`, guardrails/settings) o cuelgan de `.claude/`.
**R2.** Para cada ruta tocada fuera del alcance efectivo propio: si no cae en el alcance efectivo (`alcance_efectivo`) de ningún otro Change activo y aprobado (R1) → `ALCANCE-RUTA` (sin cambio). Si cae en exactamente uno → `Finding("ALCANCE-ATRIBUIDA-OTRO-CHANGE", ..., ruta)` mencionando el Change dueño; NO es un fallo de gate.
**R3.** Si cae en dos o más otros Changes activos y aprobados y no en el propio → `ALCANCE-CONFLICTO-CHANGES` (bloquea). Si cae en el propio y en otro activo y aprobado → `ALCANCE-CONFLICTO-CHANGES` (bloquea) aunque esté autorizada.
**R4.** Cadena de enmiendas inválida, `control.json` ilegible/no-objeto o `scope_hash` en disco distinto del aprobado en el baseline propio, de otro Change activo+aprobado (R1): sus rutas no autorizan nada (R22 de scope-isolation); la ruta queda como `ALCANCE-RUTA` y se agrega `ALCANCE-OTRO-CHANGE-INVALIDO` (bloquea) nombrando el Change. Solo se emite si hay al menos una ruta fuera del alcance propio y el ajeno es activo+aprobado; los ajenos no activos se ignoran sin hallazgo.
**R5.** Se excluyen del conflicto los outputs intrínsecos (`es_output_intrinseco`) y los artefactos propios: las rutas bajo `openspec/changes/<change_id_propio>/` nunca se atribuyen a otro Change ni generan conflicto por alcance ajeno; se evalúan solo contra el alcance propio.
**R6.** Con Git ilegible se mantiene `ALCANCE-GIT-ILEGIBLE` (fail-closed); sin otros Changes abiertos el resultado es idéntico al actual.
**R7.** `ALCANCE-ATRIBUIDA-OTRO-CHANGE` no cuenta como incumplimiento en `validate`/`gate_cierre`; los demás códigos nuevos sí. Los consumidores existentes de `evaluar_alcance` deben tratarlo por código.
**R8.** Docs en `verificador.md` (+ plantilla) y `methodology.md`; tests: dos Changes disjuntos validan limpio, ruta sin dueño, ruta con dos dueños, ruta propia+ajena, cadena ajena inválida, `control.json` ajeno ilegible, Change ajeno cerrado no atribuye, regresión de `test_scope*`.

## Criterios de aceptación
- [ ] R1–R3 [ ] R4–R6 [ ] R7–R8
- 4A: sin evidencia de payload real → hook intacto, H1 UNCONFIRMED documentado.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
<!-- qué representa cada fila del dataset sobre el que se trabaja -->

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
<!-- fecha de corte y qué información es anterior/posterior a ella; base del chequeo anti-leakage -->

## Baseline (condicional — modeling)
<!-- modelo/heurística de referencia y su métrica, contra la que se compara todo lo nuevo -->

## Métrica primaria (condicional — modeling, evaluation)

## Métricas secundarias (opcional)
