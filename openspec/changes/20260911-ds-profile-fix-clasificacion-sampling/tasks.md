# Tareas — 20260911-ds-profile-fix-clasificacion-sampling

estado: cerrada

## Invocaciones planificadas
1. `python-data-engineer` — borradores SDD (`proposal.md`/`tasks.md`) — **esta invocación**.
2. `python-data-engineer` — implementación de las 2 correcciones + tests nuevos, en `tools/ds_profile/{column_stats.py,io_readers.py}` y sus tests (y `report.py`/`sampling.py` solo si hiciera falta un ajuste mínimo de integración, sin rediseñar nada).
3. `data-science-reviewer` — revisión del diff antes de correr tests (toca el contrato de `column_stats.py`, que ya tiene tests existentes que dependían del comportamiento viejo de `{0,1}` → booleano).
4. `python-data-engineer` — corrección de hallazgos del reviewer (si los hay) o confirmación; deja `estado: en_verificacion`.
5. El Lead (Bash directo) corre la regresión: `tools/ds_profile/tests`, `tools/tests`, `tools/ds_init/tests`, `tools/harmessi/tests`, `check_manifest_parity`, `harmessi doctor`.
6. `python-data-engineer` — cierre: agrega la sección "## Verificación" a este mismo `tasks.md` (SDD abreviado: la evidencia va ahí, no en un `verification.md` aparte) con la evidencia real del paso 5, deja `estado: cerrada`.

## Tareas
- [ ] Corregir `clasificar_dtype` en `column_stats.py` (quitar rama `{0,1}` de booleano)
- [ ] Agregar `es_binario_numerico` (o equivalente) y flag `binary_numeric` en `construir_metricas_columna`
- [ ] Actualizar/quitar el test viejo que esperaba `{0,1}` → `booleano` (ej. `test_booleano_0_1` si existe con ese nombre) y agregar los 4 tests nuevos de clasificación pedidos por el usuario
- [ ] Implementar `LectorCSV.filas_exactas()` con conteo real en pasada streaming
- [ ] Agregar los 5 tests nuevos de umbral de filas en CSV pedidos por el usuario (chico bajo ambos límites, excede filas no MB, excede MB no filas, reproducibilidad, metadata de exactitud)
- [ ] Confirmar que `report.py`/`sampling.py` siguen funcionando sin cambios (o con el ajuste mínimo que haga falta) contra el nuevo `filas_exactas()` de CSV

## Dependencias
Depende de que `20260911-ds-profile-project-eda` ya esté `cerrada` (lo está).

## Próximo paso exacto
No aplica (no es `pausada_bloqueada`).

## Verificación

### Evidencia obtenida
```
tools/ds_profile/tests/  -> 129 passed, 5 skipped (Parquet real, sin pyarrow instalado), 4 subtests (3.59s)
tools/tests/             -> 191 passed, 2 skipped (53.17s)
tools/ds_init/tests/     -> 53 passed (88.26s)
tools/harmessi/tests/    -> 56 passed (198.63s)
check_manifest_parity    -> exit 0, OK, sin cambios respecto de la corrida anterior
harmessi doctor          -> exit 0, 26 OK, 9 WARN (mismos preexistentes de siempre, no atribuibles a este cambio), 0 ERROR
```

### Revisión de data-science-reviewer
Sin hallazgos bloqueantes. 1 hallazgo importante: `LectorCSV.filas_exactas()` contaba líneas en blanco del cuerpo del CSV con `csv.reader` crudo, mientras `iter_filas()` (vía `csv.DictReader`) las descarta -- podía desincronizar `sampling.decidir_modo`. Corregido: `filas_exactas()` ahora usa `csv.DictReader`, mismo motor que `iter_filas()`, garantizando el mismo conteo. Test de consistencia agregado (`test_filas_exactas_consistente_con_iter_filas_con_lineas_en_blanco`). Remediación `r1` resuelta en `control.json`. También se corrigió un docstring desactualizado en `sampling.py` (mencionaba que CSV devolvía `None`, ya no es así) -- solo comentario, sin cambio de código.

El reviewer confirmó explícitamente sin regresión en los flags existentes (`alta_cardinalidad`/`posible_id`/`constante` no se ven afectados por el cambio de clasificación booleano→numérico) y que `report.py`/`sampling.py` no necesitaron cambios de lógica (solo el docstring de `sampling.py`).

### Diferencias contra la spec
Ninguna. Las 2 correcciones de `proposal.md` (clasificación binaria numérica, umbral de filas en CSV) se implementaron exactamente como se especificaron. El hallazgo del reviewer era un bug de la implementación elegida (no una discrepancia con lo que pedía `proposal.md`), corregido antes del cierre.

### Limitaciones
- Las limitaciones ya documentadas en `openspec/changes/20260911-ds-profile-project-eda/verification.md` que NO forman parte del alcance de este cambio siguen vigentes sin cambios (Parquet real no validado end-to-end sin pyarrow instalado; ausencia de test end-to-end con archivo genuinamente grande).
- Ninguna limitación nueva introducida por esta corrección — el hallazgo del reviewer (líneas en blanco en CSV) fue corregido, no documentado como limitación aceptada.

### Resultado final
Las 2 correcciones pedidas por el usuario (clasificación binaria numérica con flag `binary_numeric`, umbral de filas en CSV vía `LectorCSV.filas_exactas()` con pasada streaming propia) implementadas, revisadas y verificadas. 1 hallazgo importante del reviewer corregido y re-testeado. Regresión completa en verde (429 tests entre las 4 suites relevantes + `check_manifest_parity` + `harmessi doctor`, 0 errores nuevos). No se tocó ningún otro archivo del diseño ya cerrado de `20260911-ds-profile-project-eda`. No se instaló pyarrow ni ninguna dependencia nueva. No se reabrió Project EDA ni se agregaron capacidades nuevas.
