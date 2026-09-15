# Verificación — 20260915-progressive-capability-installation-and-scaffold

## Evidencia obtenida
Implementación bajo autonomía acotada autorizada por el usuario, en 1 delegación principal de
implementación (código + tests, resumida 6 veces por límite de turnos del subagente dado el
tamaño real de este change — no cuentan como nuevas delegaciones) + 1 delegación de reviewer
(resumida 1 vez por límite de turnos) + fixes de 2 hallazgos importantes + 1 test de fixture,
todos aplicados directamente por el Lead sin subagente adicional (fixes bien acotados, el Lead ya
conocía el código exacto por haber diseñado la arquitectura):

- **`tools/ds_init/manifest.py`**: `ORDEN_STAGES`, `stage_minimo` en `EntradaManifiesto`, 5
  entradas reclasificadas a `experiment` (4 agentes + `decision-ledger.md`), 2 entradas nuevas
  (`production-readiness.md`/`operations.md`), `manifest_para_perfil_y_stage` (aditiva,
  `manifest_para_perfil` intacta).
- **`tools/ds_init/legacy.py`** (nuevo): `inferir_installation_stage`.
- **2 plantillas nuevas** (`production-readiness.md.tmpl`/`operations.md.tmpl`): documentación
  pura, sin placeholders de datos ni referencias privadas.
- **`tools/ds_init/planner.py`/`writer.py`**: `stage` opcional, backward-compatible.
- **`tools/ds_init/control.py`**: `installation_stage` opcional en `generar_control`/
  `regenerar_control`, aditivo.
- **`tools/ds_init/cli.py`**: positional `accion` (`install`/`sync`, default `install`),
  `--stage`, lógica de `sync` completa.
- **`tools/harmessi/doctor.py`**: `_check_archivos_administrados` stage-aware con fallback legacy
  exacto; nuevo check `HARMESSI-INSTALLATION-STAGE`.
- Tests nuevos/extendidos en `tools/ds_init/tests/{test_manifest,test_control_file,
  test_writer_staging,test_cli,test_legacy}.py` y `tools/harmessi/tests/test_doctor.py`.

Durante la implementación el subagente no encontró ninguna contradicción real entre
`spec.md`/`design.md` y el código existente (confirmado explícitamente en su resumen final).
Decisiones de implementación propias documentadas por el subagente (todas razonables y
consistentes con el resto del harness, revisadas por el Lead): (1) el rechazo de `--stage
production_candidate`/`production` en `install` se resuelve con `parser.error()` manual en vez de
`choices=` restringido a nivel de parser, porque `install`/`sync` comparten un único flag
`--stage` bajo el positional `accion` (sin subparsers, por R14); (2) idempotencia de `sync`
repetido implementada como short-circuit explícito antes de tocar el plan, en vez de dejar que el
plan completo recorra `ACCION_OMITIR_EXISTENTE` para cada entrada — mismo resultado observable;
(3) los fixtures de test que instalan `production_candidate`/`production` "reales" llaman
`writer.instalar(..., stage=...)` directamente (nivel de escritura, sin la restricción de UX de
`cli.py`), evitando simular `promote`/`readiness` real, consistente con R9 (ejes ortogonales).

**Reviewer (`data-science-reviewer`)**: sin hallazgos bloqueantes. 2 hallazgos **importantes**,
ambos tocando los dos puntos de mayor riesgo ya identificados en `design.md`:
1. `cli.py` — una falla en `regenerar_control` (el paso posterior a `writer.instalar` que
   completa `control.json` con el set acumulado) no estaba envuelta en manejo de errores: podía
   escapar como excepción no controlada, dejando `control.json` con `archivos` incompleto sin
   ningún mensaje ni exit code claro. **Corregido**: el paso ahora está envuelto en
   `try/except Exception`, reporta `[ABORTADO-PARCIAL]` con mensaje explícito (los archivos SÍ se
   aplicaron, pero el registro puede haber quedado incompleto; `sync` es idempotente, reintentar
   resuelve la reconciliación), exit 1. Test nuevo:
   `test_sync_falla_en_regenerar_control_reporta_error_no_escapa_ni_miente_exito`.
2. `doctor.py` — `_check_installation_stage` solo capturaba `maturity.MaturityEstadoError`; un
   `OSError`/`UnicodeDecodeError` de bajo nivel (p. ej. una carrera TOCTOU entre el `.exists()` y
   el `open()` interno de `leer_estado`) podía escapar hasta `checks.ejecutar_checks` y
   convertirse en `ERROR`, violando la regla explícita del usuario ("nunca ERROR/FAIL bajo ningún
   escenario", R11/§18). **Corregido**: la función se dividió en un wrapper con
   `try/except Exception` (degrada a `N/A` ante cualquier fallo inesperado) + la lógica interna
   sin cambios. Test nuevo: `test_nunca_error_ante_excepcion_inesperada_no_de_dominio` (mockea
   `maturity.leer_estado` con un `OSError` genérico, confirma `N/A`, nunca `FAIL`).

Hallazgo **menor** (brecha de cobertura, mismo riesgo #1): ningún test end-to-end (solo unitario)
confirmaba que `control.json["archivos"]` tras un `sync` real incluyera el set ACUMULADO completo
(archivos de corridas anteriores + delta nuevo), no solo el delta. **Corregido**: test nuevo
`test_sync_deja_archivos_de_control_json_con_el_set_acumulado_completo` en `test_cli.py`,
end-to-end real contra un repo git temporal.

Verificación real ejecutada por el Lead (nunca por el subagente, que no tiene Bash):
- `tools/ds_init/tests/`: primera corrida 110/110 OK (sin regresión, ya incluía toda la nueva
  cobertura del subagente). Segunda corrida (tras los fixes + 2 tests nuevos): 112/112 OK.
- `tools/harmessi/tests/`: primera corrida 81/81 con 2 fallos reales de FIXTURE (no de
  producción, confirmados leyendo el código fuente directamente):
  (a) `test_legacy_sin_installation_stage_se_comporta_exactamente_igual_que_hoy` asumía que una
  instalación "legacy" (sin `--stage`) no tendría los 2 documentos nuevos, pero
  `manifest_para_perfil` (sin filtrar, R3) instala literalmente TODO, incluidos los 2 documentos
  nuevos de este mismo change — corregido borrándolos explícitamente en el fixture para simular
  una instalación legacy REAL (anterior a que esas entradas existieran);
  (b) `test_formatear_sin_resultados_na_no_agrega_segmento` asumía "ningún check da N/A", pero el
  nuevo `HARMESSI-INSTALLATION-STAGE` legítimamente da N/A sin `.harmessi/project.json` — corregido
  agregando `maturity.project_init(...)` al fixture para preservar la intención original del test
  (verificar el caso "cero N/A" de `formatear()`). Segunda corrida (tras ambos fixes): 81/81 OK.
  Tercera corrida (tras los 2 fixes de reviewer + 1 test nuevo): 82/82 OK.
- `tools/tests/` (no tocado por este change): 444/444 OK, sin necesidad de re-corrida tras los
  fixes (ningún archivo de ese árbol fue modificado).
- `harmessi doctor` sobre este repo: **25 [OK], 6 [WARN], 0 [ERROR], 1 [N/A]**, idéntico
  antes/después de los fixes de reviewer. Los 6 WARN: 1 working tree sucio (esperado, desarrollo
  activo sin commit); 2 nuevos (`production-readiness.md`/`operations.md` faltantes — este propio
  repo es una instalación legacy que nunca corrió `sync`, comportamiento esperado y documentado
  en `design.md`); 3 preexistentes (drift de `kdd.md`/`ds_guard.py`/`dsguard/kdd.py`, sin
  relación con este change). El 1 N/A: `HARMESSI-INSTALLATION-STAGE` sin
  `.harmessi/project.json` en este repo (nunca se corrió `project init` sobre sí mismo). **0
  ERROR nuevo.**

## Fingerprint de dataset/artefacto (condicional — cambio sensible o reproducibilidad crítica)
No aplica — no hay dataset ni artefacto de modelo propio en este change.

## Diferencias contra la spec
Ninguna sustancial. Los 2 fixes de reviewer (manejo de excepción en `cli.py`/`doctor.py`) son
endurecimientos de robustez explícitamente pedidos por R11 ("nunca ERROR") y por el propio riesgo
#1 documentado en `design.md` §5 — no cambian ningún comportamiento del camino feliz descrito en
`spec.md`, solo blindan los caminos de error que antes no estaban cubiertos.

## Limitaciones
Este propio repositorio (instalación legacy) no tiene `installation_stage` ni
`.harmessi/project.json` — para verlo reflejado con datos reales habría que correr `ds_guard
project init` + `ds_init sync --stage production --execute` sobre él, lo cual requeriría un
working tree limpio (imposible durante esta sesión, con cambios pendientes de commit) — queda
como una operación futura, no bloqueante para el cierre de este change. La inferencia legacy
(`legacy.inferir_installation_stage`) solo distingue `"discovery"`/`"production"` con confianza —
documentado y aceptado explícitamente en `design.md` punto 6 (no hay señal para distinguir
`experiment`/`production_candidate`/`production` entre sí en instalaciones anteriores a este
change).

## Pendientes derivados
Ninguno bloqueante. Recordatorio para futuros changes: `harmessi CLI pública`/`unified status`
(Change 8) podrían eventualmente exponer `sync`/`installation_stage` de forma más visible, sin
necesidad de cambios en `ds_init`/`doctor` más allá de wiring nuevo.

## Resultado final
Todos los requisitos R1-R14 de `spec.md` implementados con evidencia real. Reviewer con 2
hallazgos importantes + 1 menor, todos corregidos y verificados con tests nuevos dedicados.
Regresión completa limpia (112/112 + 82/82 + 444/444, 0 ERROR en doctor). Change listo para
cierre.
