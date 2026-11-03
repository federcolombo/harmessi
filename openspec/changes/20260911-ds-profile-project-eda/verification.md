# Verificación — 20260911-ds-profile-project-eda

## Evidencia obtenida

Regresión completa corrida por el Lead (hoy, Bash directo, sin subagente):

```
tools/ds_profile/tests/  -> 111 passed, 5 skipped, 4 subtests passed (3.29s)
  (los 5 skipped son los tests de "Parquet disponible", vía unittest.skipUnless --
  pyarrow no está instalado en el .venv de este repo; el test de "Parquet no
  disponible" (exit 3) SÍ corrió y pasó, forzado con mock.patch, independiente
  del entorno real)
tools/tests/             -> 191 passed, 2 skipped (53.64s)
tools/ds_init/tests/     -> 53 passed (75.00s)
tools/harmessi/tests/    -> 56 passed (194.60s)
check_manifest_parity    -> exit 0, [OK] todas las rutas VERBATIM existen;
  eda.md listado correctamente entre las 11 entradas PLANTILLA a revisar a mano
  (igual que kdd.md/decision-ledger.md/etc. -- no es un error, es el flujo normal)
harmessi doctor          -> exit 0, 26 [OK], 9 [WARN], 0 [ERROR]. Los 9 WARN son
  preexistentes a este cambio (drift de archivos ya modificados antes de este
  bloque -- .claude/agents/*.md, SKILL.md, sdd.md, verificador.md,
  .claude/settings.json -- y "working tree con cambios sin confirmar", esperado
  porque no se hizo commit). Ninguno atribuible a ds_profile/Project EDA.
```

Revisión de `data-science-reviewer` sobre el diff completo (antes de correr cualquier test): sin hallazgos bloqueantes. 3 hallazgos "importantes", los 3 corregidos y re-testeados (remediaciones `r1`/`r2`/`r3` en `control.json`, resueltas):

1. `verificar_salida_permitida` (`holdout_guard.py`) no chequeaba `config.holdouts` para `--output`, solo `data_raw` — corregido, ahora deniega siempre que `--output` caiga en un holdout declarado (sin excepción posible, igual que `pathguard.py`).
2. `holdout_guard.py` trataba una ruta no resoluble (error de bajo nivel) igual que una ruta genuinamente fuera del repo (fail-open) — corregido a fail-closed, igual que `pathguard.py`.
3. `FORMATOS_FECHA` no cubría fracción de segundo — una columna `timestamp` nativa de Parquet con microsegundos caía a `texto` en vez de `fecha` — corregido, agregados 2 formatos con `.%f`.

Un cuarto hallazgo (ambigüedad `booleano`/`entero` para columnas cuyos valores observados son subconjunto de `{0,1}`) se documentó como limitación aceptada de v0.2 en `design.md` (sección "## Riesgos"), sin cambiar código.

## Fingerprint de dataset/artefacto (condicional — cambio sensible o reproducibilidad crítica)

No aplica: este cambio no perfila ningún dataset real del proyecto (es la herramienta misma). Ver en cambio `tools/ds_profile/tests/test_fingerprint.py` (5 tests, todos pasaron) como evidencia de que el algoritmo de fingerprint (`sha256/bin/v1`) es determinista y estable entre corridas — verificado en la regresión de arriba.

## Diferencias contra la spec

Ninguna funcional. Los 3 hallazgos del reviewer eran gaps de implementación sobre requisitos ya definidos en `spec.md` (no contradicciones de la spec), corregidos antes de este cierre. El cuarto (booleano/0-1) es una ambigüedad de un criterio que `spec.md` no desambiguaba explícitamente — documentada como limitación en `design.md`, no como diferencia contra la spec.

## Limitaciones

- Ambigüedad booleano/entero para columnas `{0,1}`-only (ver `design.md` § Riesgos, texto completo ahí).
- El umbral de filas exactas (`--max-filas-exactas`) solo aplica cuando el lector puede saber `filas_exactas` sin escanear (Parquet, vía metadata) — para CSV, `filas_exactas()` es siempre `None` (`io_readers.LectorCSV`), así que un CSV de millones de filas chicas (bajo el umbral de MB) nunca dispara modo muestreado por cantidad de filas, solo por tamaño en bytes. Documentado en `sampling.decidir_modo`, es una simplificación deliberada de v0.2 (ver `design.md`), no un bug.
- Los tests de "Parquet disponible" (`LectorParquet`, lectura real de un `.parquet`) están `skipUnless(pyarrow instalado)` — en el `.venv` de este repo, sin pyarrow instalado, esos 5 tests se saltean; solo queda ejercitado el camino de "Parquet sin pyarrow" (exit 3), determinista vía mock. La lectura Parquet real (streaming por row-group, metadata de filas) no está validada end-to-end en este entorno de desarrollo — validación pendiente en cualquier entorno que sí tenga pyarrow instalado.
- Incidente de bookkeeping del Lead con `sesiones[].reintentos` de la sesión `s1` (ver abajo) — documentado íntegro: 3 notas de reintento logueadas por 1 sola reinvocación real, lo cual efectivamente disparó el hook técnico de bloqueo de `hook_presupuesto.py` y obligó a cerrar `s1` y abrir `s2` para poder continuar.
- No hay test end-to-end con un archivo genuinamente grande (GB); la cobertura de "dataset grande/chunking" es vía umbrales forzados artificialmente bajos sobre datasets sintéticos chicos, más los tests unitarios de `ReservoirSampler` — razonable para tests unitarios, pero es la forma más débil de validación de esa característica (nota del reviewer, sin acción tomada por ser de bajo riesgo).

### Incidente de bookkeeping del Lead (`reintentos` de la sesión `s1`)

Al registrar la corrección de los 3 hallazgos, el Lead corrió `ds_guard session note --tipo reintento` **3 veces** (una por `--finding-id`), cuando en realidad fue **una sola** reinvocación real de `python-data-engineer` que corrigió los 3 hallazgos en la misma corrida. Esto infló el contador agregado `sesiones[].reintentos` de la sesión original (`s1`) a 3, superando el `max_reintentos` de 2 configurado al abrirla. El usuario, consultado explícitamente, autorizó continuar y documentarlo (en vez de pausar el cambio formalmente). Confirmado que `ds_guard transition --a cerrada` no depende de ese contador (`chequear_limites` solo la usa `ds_guard validate`, no el gate de `transition`) — pero **el hook técnico real `tools/dsguard/hook_presupuesto.py` sí bloqueó** una nueva convocatoria de subagente (`Agent`) mientras la sesión `s1` seguía activa con `reintentos(3) >= max_reintentos(2)` — esto SÍ es un bloqueo técnico real, no solo informativo, y confirma que el hook funciona como está diseñado. El Lead resolvió esto cerrando `s1` (`ds_guard session close --estado completada`, todo el trabajo de esa sesión — implementación + corrección — ya estaba completo y verificado) y abriendo una sesión nueva `s2` específicamente para esta invocación de cierre, que no consume reintentos (es una invocación planificada, no una corrección). Esta es la invocación de cierre corrida bajo `s2`.

### Alcance del cambio (`control.json`)

El Lead extendió `control["alcance"]["rutas_autorizadas"]` después de `ds_guard init` (que solo la puebla con los artefactos SDD) para incluir los archivos reales creados/modificados — mismo patrón ya usado en el cambio previo `20260910-sincronizar-plantillas-bloque5`. `ds_guard validate --gate cierre` corrido después de esa extensión: sin hallazgos `ALCANCE-RUTA`.

## Pendientes derivados

- Validar la lectura Parquet real (`LectorParquet`) en un entorno con `pyarrow` instalado — no se instaló en este bloque por decisión explícita del usuario ("no instalar pandas, pyarrow ni ninguna dependencia nueva automáticamente").
- Evaluar si la ambigüedad booleano/entero amerita una corrección de diseño en v0.3+ (requiere aprobación explícita del usuario, no es una corrección unilateral).
- Evaluar si el umbral de filas para CSV amerita un mecanismo de conteo/estimación propio en v0.3+ (hoy solo el umbral de MB aplica a CSV).

## Resultado final

Cambio implementado, revisado y verificado según el plan de `tasks.md`. Regresión completa en verde (411 tests entre las 4 suites relevantes + `check_manifest_parity` + `harmessi doctor`, 0 errores nuevos atribuibles a este cambio). 3 hallazgos importantes del reviewer corregidos y re-testeados; 1 documentado como limitación aceptada. Cierre autorizado por el Lead tras consulta explícita al usuario sobre el incidente de bookkeeping de `reintentos` de la sesión `s1` (ver "Limitaciones"), resuelto operativamente cerrando esa sesión y abriendo `s2` para esta invocación.
