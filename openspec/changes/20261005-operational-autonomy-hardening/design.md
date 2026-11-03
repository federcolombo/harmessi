# Diseño — 20261005-operational-autonomy-hardening

## Decisiones

**D1 — Corregir la lectura, no el enforcement.** `session start` ya bloquea por topes agregados; el defecto es que el
resolvedor ignora `autonomy.limits`. Se extiende `_resolver_budgets` (mismo retorno de 5 claves, una variante añade las
fuentes) con la regla «el más estricto». Alternativas descartadas: migrar `limits` a `budgets` reescribiendo el archivo
del usuario (editaría `guardrails.json`, protegido); que `limits` pise a `budgets` (puede ampliar).

**D2 — `budgets` habilita `autonomous`.** `policy.py` exige `limits.*` para no degradar. Declarar `budgets` como canónico
sin tocar eso dejaría la canónica inutilizable para activar autonomía. Cambio mínimo y simétrico: cada eje puede venir de
`limits` o `budgets`; valores efectivos = mínimo; inválido ⇒ degrada (más estricto que hoy). Con `limits` completos el
resultado es idéntico. Es el único cambio en `tools/autonomy`; no toca STOP ni la tabla de políticas.

**D3 — Mensaje de recuperación generado, validado por el propio hook.** El texto se construye con `sys.executable` y el
`change_id` de la sesión activa (el hook ya los conoce) y se prueba contra `_matchea_allowlist`: la UX y el hook no pueden
divergir. `session start` queda fuera del allowlist a propósito: con sesión activa agotada no debe poder evadirse; tras
`close` no hay sesión activa y el hook permite todo.

**D4 — Variantes del intérprete = misma identidad normalizada.** Se admiten comillas opcionales y ruta relativa resuelta
contra la raíz del repo; todo termina en la comparación exacta post-`normcase/normpath`. No hay resolución por nombre
(`python`) porque no es inequívoca. Ningún cambio al rechazo de metacaracteres.

**D5 — Intérprete simétrico y hash estable.** El «intérprete autorizado» de `exec` es el propio `--interpreter`
(`ds_guard.py:1945`), así que el fallo era solo de forma; se normalizan ambos lados en `evaluar_comando`. El hash de
pytest pasa a usar el intérprete normalizado para que la identidad no dependa de mayúsculas; coincide con el valor
anterior para quien ya pasaba la forma normalizada, así que no invalida aprobaciones.

**D6 — Alcance declarado en la propuesta, aprobado por hash.** Mismo patrón que checkpoints y dependencias
(`cmd_approve` parsea `proposal.md` y materializa en `control.json`), pero válido en cualquier `approval_mode`. Parser
puro y estricto, todo-o-nada, en `dsguard/sdd.py`. Declarativo: la lista resultante = defaults ∪ declarados. Sin
sección ⇒ no toca nada (los Changes existentes con alcance editado a mano no se alteran). Se evita `scope add` (v0.10).
Arranque (bootstrap) de este mismo Change: se aprueba el SDD con el código viejo (que ignora la sección) y, tras
implementar, se re-aprueba `proposal.md` con el mismo hash usando el comando soportado; así el Change usa su propia
función y no se edita `control.json` a mano.

**D7 — `dir/**` canónico sin tocar `path_matches_any`.** `fnmatchcase` ya cubre `dir/**` y lo usan otros 8 módulos; la
brecha está solo en el matcher de exec. Se le agrega la forma `dir/**` conservando la semántica previa (exacto/prefijo
plano). Resultado: declarar únicamente `dir/**` funciona en validate y en exec.

**D8 — `verification.md` por defecto + outputs intrínsecos por lista cerrada.** `verification.md` es parte del
lifecycle (lo exige `gate_cierre`), así que entra al scope por defecto. `.harmessi/executions/**` y el ledger son
bookkeeping del harness: se excluyen en el evaluador (`scope.es_output_intrinseco`, lista cerrada de dos entradas), no se
agregan al scope funcional ni se autorizan para exec. Cualquier otra ruta interna sigue contando.

**D9 — N1 estrecho.** Los tools estructurados `Read`/`Grep` ya están permitidos: solo se agregan tests que lo fijan. Para
Bash se neutralizan únicamente redirecciones sin efecto (`/dev/null`, `nul`, `$null`, `N>&M`) antes de la heurística de
escritura; cualquier otra redirección o patrón de escritura mantiene el bloqueo. No se construye un parser de shell; el
resto de Bash queda documentado como best-effort.

## Riesgos y mitigaciones
- **Activar límites que antes se ignoraban** puede bloquear proyectos con consumo ya alto (caso real: 4424 min > 3600):
  es el comportamiento correcto y es LIMIT/`checkpoint_resumable`; el mensaje de `session start` indica la fuente.
- **`policy.py` más estricto con valores inválidos en `budgets`:** solo degrada a supervised (nunca amplía).
- **Materialización destructiva:** reemplaza solo si la sección existe y es válida, e imprime lo retirado.
- **Race de writers sobre `ds_guard.py`:** propiedad de archivos disjunta por instancia (ver tasks.md).

## Archivos previstos
`tools/ds_guard.py`, `tools/autonomy/policy.py`, `tools/dsguard/{sdd,scope,hook_presupuesto,pathguard}.py`,
`tools/leadrun/allowlist.py`, `.claude/skills/lead-data-scientist/templates/proposal.md`, `ARCHITECTURE.md`,
`docs/roadmap/{v0.9,v0.10}.md`; tests nuevos en `tools/tests/` (`test_operational_budgets.py`,
`test_operational_session_recovery.py`, `test_operational_scope.py`, `test_operational_hook_guardrails.py`,
`test_operational_inert.py`), `tools/autonomy/tests/test_policy.py` y `tools/leadrun/tests/test_allowlist.py` (adiciones).

## Fuera de alcance
Ver proposal.md.
