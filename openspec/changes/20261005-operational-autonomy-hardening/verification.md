# Verificación — 20261005-operational-autonomy-hardening

## Resumen ejecutivo
Corrective A de v0.9, originado en feedback de uso real de Harmessi 0.8.0. Cierra: límites agregados `autonomy.limits`
que nunca se aplicaban (h1), mensaje de recuperación sin comandos y allowlist rígida (h2/h3), comparación de intérprete
asimétrica en Windows (b), alcance declarable en `proposal.md` (e), `verification.md` por defecto (i), outputs internos
del harness dentro de `ALCANCE-RUTA`, semántica `dir/**` (f1) y el falso positivo de `2>/dev/null` en el hook de rutas
(N1). SDD aprobado por hash el 2026-10-05 con autorización humana anticipada. Todas las ejecuciones pasaron por el
runtime gobernado (`ds_guard exec pytest`, aprobado con `ds_guard exec approve`).

## Qué entrega
- **h1 (`ds_guard.py`, `autonomy/policy.py`):** `autonomy.budgets` canónica; `limits` legacy traducido
  (`max_sessions`, `max_total_minutes`→`aggregate_minutes`); si ambos, el MENOR; inválido o no-dict ⇒ fail-closed
  (`AUTONOMY-POLICY-LIMITS`); `session aggregate|status` muestran efectivo, fuente, consumo y restante;
  `session start` bloquea por minutos y por cantidad (E2E por CLI real). `policy.py` acepta `budgets` para el requisito de
  límites de `mode: autonomous` (valor efectivo = mínimo; inválido degrada). Aviso explícito si `guardrails.json` está
  ilegible (los límites NO se aplican).
- **Recuperación (`hook_presupuesto.py`):** todo bloqueo `PRESUPUESTO AGOTADO` incluye comandos literales (`status`,
  `close --estado pausada`, `start` marcado como posterior al cierre) en forma Bash y PowerShell, con el intérprete real y el
  `change_id` activo; cada `status`/`close` del mensaje es aceptado por el propio allowlist. `session start` no está en el
  allowlist (no evade una sesión activa agotada). Variantes aceptadas del MISMO intérprete: comillas opcionales, prefijo
  PowerShell `& `, case y separadores; solo rutas absolutas.
- **Intérprete (`leadrun/allowlist.py`, `ds_guard.py`):** `evaluar_comando` normaliza ambos lados; el hash de pytest usa el
  intérprete normalizado y registra `hash_legacy` (crudo) para no invalidar aprobaciones previas.
- **Alcance:** sección `## Alcance autorizado` (parser puro `sdd.parsear_alcance_autorizado`, todo-o-nada, rutas protegidas
  rechazadas) materializada en `control.json` al aprobar `proposal.md`; `init` incluye `verification.md`;
  `.harmessi/executions/**` y `openspec/decisions/ledger.jsonl` exentos del evaluador (`scope.es_output_intrinseco`, lista
  cerrada, sin autorizar `exec`); `dir/**` = directorio y descendientes, sin hermanos (en `exec` y validate).
- **N1 (`pathguard.py`):** las redirecciones sin efecto (`/dev/null`, `nul`, `$null`, `N>&M`) no cuentan como escritura;
  cualquier otra redirección o patrón de escritura sigue bloqueando. `Read`/`Grep` estructurados ya estaban permitidos
  (ahora fijado por tests); Bash sigue siendo best-effort (documentado).
- Plantilla `proposal.md` con la sección nueva; ARCHITECTURE §6.1; roadmaps (Corrective A en v0.9; deuda v0.10
  reformulada como «Mid-Change authorized scope amendment UX»).

## Ejecuciones reales (runtime gobernado)
Dirigida (tests nuevos + policy + allowlist): 129 + 64 passed (primera corrida, W-A y W-B); tras fixes del ciclo 1: 215
passed; tras fixes del ciclo 2: **195 passed, 96 subtests, 0 failed** (el conteo difiere porque `test_allowlist.py`
congelado quedó fuera y se agregaron tests).

Regresión relevante en lotes SECUENCIALES (exit code real leído del `ExecutionRecord`):

| Lote | Suite | Resultado |
|---|---|---|
| 1 | `tools/tests` | 1347 passed, 4 skipped, 28542 subtests, **1 failed** (ver abajo) |
| 2 | modelquality, qualityevidence, datasources, datacontracts | 511 passed, 150 subtests |
| 3 | autonomy, leadrun | 260 passed, 261 subtests |
| 4 | `tools/cards/tests` | 1127 passed, 28 skipped, 2501 subtests |
| 5 | ds_init, harmessi (Doctor), reporting | 1089 passed, 3 skipped, 637 subtests |

Agregado: 4334 passed, 35 skipped, 1 failed conocido, 32091 subtests.

**El único fallo** es `test_v08_change4_leadrun_diff::test_allowlist_py_agrega_funcion_aislada_sin_tocar_las_4_existentes`:
compara `tools/leadrun/allowlist.py` contra `HEAD` y su propio `setUpClass` documenta que, tras commitear, el diff queda
vacío y el test se salta («limitación conocida de un test dirigido por diff de working tree»). Falla mientras el cambio no
esté commiteado porque este Change modifica `allowlist.py` por diseño (R18/R35). La suite congelada
`test_allowlist.py` (que ese test exige sin cambios) quedó intacta: los tests nuevos viven en `test_allowlist_operational.py`.
Se reconfirma tras el commit local (ver addendum en el reporte de cierre).

## Hallazgo de dogfooding durante la implementación
Al usar el propio `## Alcance autorizado` para ejecutar la regresión, `pytest tools/tests` con solo `tools/tests/**`
declarado era rechazado: `dir/**` no cubría al propio directorio. Se corrigió `_coincide_alcance` (R33: «el directorio y
todos sus descendientes») y se agregó test. Además, el scope inicial no incluía las carpetas de tests de regresión de otros
paquetes: se agregaron a la sección y se re-aprobó `proposal.md` (mismo flujo soportado, nuevo hash).
Durante la sesión el presupuesto de 600 min venció; el mensaje de recuperación nuevo se usó tal cual (close pausada →
start s2), validando el flujo de punta a punta.

## Proceso de revisión (2 ciclos)
- **Ciclo 1:** 1 bloqueante (B1: el token de intérprete del allowlist permitía inyección vía `..` + metacaracteres) y 9
  importantes/menores (I1 ruta relativa dependiente del cwd, I2 forma PowerShell, I3 guardrails ilegible sin aviso, I4
  `budgets` no-dict, I5b ruido `unknown_key`, I6 invalidación de aprobaciones pytest, I7/I8 rutas protegidas y `.git`
  case/NTFS en el parser, I9 lookahead `>&N`, M4 bullets no soportados). Todos corregidos.
- **Ciclo 2:** 0 bloqueantes. Importante: `\r` y saltos Unicode en la cola del allowlist (PowerShell) — corregido; tests
  del PoC exacto de B1, ruta relativa real (sin `..`), borde `data/raw` (`data/raw_features` válido), R39 (executions/ledger no
  autorizan `exec`) y `pytest <dir>` con `dir/**` agregados.

## Precisiones por encima del spec aprobado (el spec no se editó; todas más estrictas)
- **R13:** el spec decía «ruta relativa resuelta contra la raíz del repo»; se implementó SOLO ruta absoluta (una relativa
  depende del cwd real del shell y no es inequívoca). Alineado con la instrucción de aceptar variantes que «puedan resolverse
  inequívocamente».
- **R23:** el parser rechaza además rutas protegidas (`.claude/guardrails.json`, `.claude/settings*.json`, `data/raw`,
  `.harmessi`, `.git`), segmentos con punto/espacio final y `:`; el reviewer evidenció que sin esto el scope era
  autodeclarable hacia rutas sensibles.
- **R3:** `limits`/`budgets` no-dict fallan cerrado (el spec solo lo exigía a `limits`).
- **R12/R11:** el mensaje muestra la forma Bash y la PowerShell; el allowlist admite el prefijo `& `.
- `policy.py` ya no reporta `budgets` como clave desconocida.

## Limitaciones conocidas (no bloqueantes)
- **Después de `close`, un proyecto sin topes agregados configurados puede abrir otra sesión** (el mensaje lo ofrece);
  por diseño: sin tope configurado no hay límite. Con topes, `session start` bloquea (E2E).
- Entradas legacy con `*` en `control.json` ahora se resuelven como glob en `exec` (antes, literal); consistente con validate.
- `mensaje_recuperacion` con `sys.executable` que contiene `$` o backtick: el comando generado es rechazado por el hook
  (caso marginal).
- El filtro de algoritmos de `hash_legacy` en `_resolver_aprobacion_exec` no discrimina por forma (exige igualdad exacta del
  hash, no es explotable sin editar `control.json`).
- Los tests de hash crudo vs normalizado corren solo en Windows (en POSIX `normcase` es identidad).
- Bash sigue siendo best-effort (sin parser de shell); N1 se resolvió solo para redirecciones inocuas.
- Fin de línea: `core.autocrlf` avisa conversión a CRLF al commitear (deuda v0.10 LF/CRLF).
- v0.10: approval-origin authenticity, LF/CRLF hashing, mid-Change authorized scope amendment UX, composable skills/
  domain-modeling, one-writer. Corrective B (checkpoints circulares, `.postN`, drift de `guardrails.json`) y C (`ds_profile`)
  pendientes, y Change 4 sin tocar salvo la revalidación de su SDD.

## One-writer
Dos instancias writer en paralelo con propiedad de archivos disjunta y explícita (W-A: ds_guard/policy/sdd/scope; W-B:
hook_presupuesto/pathguard/allowlist). El Lead editó directamente, tras terminar ambos writers, `allowlist.py` (R33, directorio
mismo), `hook_presupuesto.py` (clase de caracteres de cola) y `sdd.py` (borde `data/raw`), sin solapes concurrentes.

## Resultado final
Corrective A completo y verde salvo el test histórico de diff (documentado). Sin STOP nuevos, sin cambios a `STOP_CATALOG`/
`POLICY_TABLE`/`repo.path_matches_any`. Listo para cierre.
