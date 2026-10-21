# Verificación — 20261021-v013-portability-hardening

## Resumen
`dsimpact` ya no trata evidencia desconocida como vacía (fail-closed en `git_source`; consumidores y cambios no analizados visibles en `summary` y CLI); la sección `## Skills cargados` duplicada produce `SKILL-TRAZA-SECCION-DUPLICADA` con un único criterio de lectura; consola segura en las CLIs nuevas; `docs/portability.md`; tests de portabilidad ejercitados en Windows; workflow de GitHub Actions `portability-smoke`.

## Evidencia obtenida
- pytest serial por tandas: dsimpact (85 tests, tras corregir un fixture de test), skill_contract/methodology/portability audit/CI workflow/architecture (185 passed, 1 skipped, 516 subtests), harmessi_bench + providers + portability smoke + conformance smoke (367 passed, 4 skipped).
- `ds_guard validate`: sin hallazgos.
- Compatibilidad hacia atrás de la sección duplicada: grep sobre los `tasks.md` de `openspec/changes/` antes de endurecer: ningún Change existente la tiene duplicada.
- Reviewer ciclo 1: 0 blocker, 2 HIGH (fail-open de consumidores en `scan.py`; degradación a `_procesar_otro` con `parse_error` falso), varios MED. Fixes aplicados (listas `consumidores_no_analizados`/`cambios_no_analizados`, CLI «resultado no concluyente», `validar_ref` traduce git ausente, criterio único `_encabezados_reales` con fences ``` y ~~~, saneo de ruta, workflow endurecido). Ciclo 2 (justificado por los HIGH): 0 blocker/HIGH.

## Real vs contractual
- **Windows:** ejecución real en este host (tests de espacios, Unicode, CRLF/LF, temp dirs, subprocess, Git, symlink con skip si no hay privilegios).
- **Linux/macOS:** workflow presente y validado estructuralmente; **ejecución remota no observada**; sin validación real en esas plataformas.

## Compatibilidad (nota para release)
`ds_guard validate` ahora emite `SKILL-TRAZA-SECCION-DUPLICADA` si una traza `tasks.md` tiene dos secciones `## Skills cargados`: proyectos instalados con esa duplicación recibirán el hallazgo tras actualizar.

## Limitaciones conocidas (deuda)
Celdas de notebook consumidor con magics se ignoran sin señal; `parse_error` de un archivo cambiado vive solo en `changed[]` (no en `cambios_no_analizados`) y la CLI imprime a la vez `[parse_error]` y «ningún consumidor»; `ds_guard contract impact` (fuera de alcance) conserva el patrón de omisión silenciosa; exit code 0 aun con resultado no concluyente; estado `U` en `--staged` aborta fail-closed; saneo de ruta solo en `_git_show`; fences sin cerrar en `tasks.md`; `verificador.md` no lista el nuevo hallazgo; `errors="replace"` puede alterar salida `--json` en consolas no UTF-8; auditoría de portabilidad de módulos heredados pendiente (marcados `deuda` en `docs/portability.md`).

## Divergencias respecto del SDD
Se agregó `ast.parse`/`json.loads` previos en `scan.py` para contar consumidores no analizables sin modificar `consumers_py`/`consumers_text`.

## Resultado final
Change 4 verificado con tests focalizados verdes. Listo para commit.
