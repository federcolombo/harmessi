# Verificación — 20261021-v013-contract-inventory-compat

## Resumen
Inventario de contratos (`docs/contracts/inventory.json` + README) con clases `public-candidate` / `internal` / `experimental`, anclado a la realidad por tests (subcomandos de las CLIs, constantes de versión, scripts con `__main__`); ventana de compatibilidad con fixtures sintéticos v0_11/v0_12/v0_13; convención y primitiva mínima de deprecación (`tools/harmessi/deprecation.py`, registro vacío); `docs/versioning.md` y `docs/deprecation.md`. Es un inventario, no una promesa de estabilidad v1.0.

## Evidencia obtenida
- pytest serial: `test_v013_contract_inventory`, `test_v013_compat_window`, `test_deprecation`, `test_manifest_completitud`, `test_architecture_boundaries`: 119 passed.
- `ds_guard validate`: ver cierre.
- Reviewer ciclo 1: 0 blocker, 3 HIGH de exactitud (exit codes de `ds_guard` y `ds_profile`; `schema-change-control` sin constante), 10 MED. Fixes: exit codes corregidos, 21 schemas persistidos agregados, test de cobertura de constantes `*_VERSION` y de scripts con `__main__`, campo `ancla`, anclaje de exit codes por código/docstring, compat con APIs públicas (`leer_control`, `migrar_hashes`, `verificar_entrada`), `deprecation.py` endurecido (1.x, `fullmatch`, nunca lanza). Ciclo 2 (justificado por los HIGH): 0 blocker/HIGH; verificó que los exit codes de las 8 CLIs y las 27 constantes coinciden con el código.

## Ventana de compatibilidad (documentada en `docs/versioning.md`)
Lectura soportada de los artefactos cubiertos por los tests de compatibilidad, de la versión actual y las dos menores previas; anterior = mejor esfuerzo. Fixtures sintéticos; verificación contra los tags `v0.11.0`/`v0.12.0` opcional (skip si no existen).

## Limitaciones conocidas (deuda)
`_evidencia_codigo` tiene atajos laxos (el 2 pasa si el módulo menciona argparse; 0/1 pasan si menciona `exit_code`) y no detecta códigos reales no declarados salvo en `ds_guard`/`ds_profile`/`reporting`; `cli-harmessi` es `public-candidate` aunque solo-checkout; extracción de subcomandos por `--help` sin normalizar `\r\n`/ANSI; `advertir` lanza por diseño (`KeyError`/`ValueError`); `test_inventario_no_promete_estabilidad_v1` es un chequeo de cadenas; `HARNESS_VERSION` no anclado al cierre de release; los fixtures de compat son derivados a mano y no extraídos de los tags.

## Divergencias respecto del SDD
Se inventariaron 8 CLIs (R2 pedía 6): `reporting` y `ds_profile` entran por R4(f). Se agregaron entradas de schema para todas las constantes `*_VERSION` halladas (exigido por el test de cobertura).

## Resultado final
Change 5 verificado con tests focalizados verdes. Listo para commit.
