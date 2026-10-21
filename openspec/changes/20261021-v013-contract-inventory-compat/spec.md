# Spec — 20261021-v013-contract-inventory-compat

## A. Inventario
**R1.** `docs/contracts/inventory.json`: `{"inventory_version": 1, "harmessi_version_documented": "0.13.x", "contratos": [...]}`; cada contrato con `id` único (kebab-case), `categoria` (`cli`, `schema`, `skills`, `managed-assets`, `adapter`, `provider`, `surfaces`, `upgrade`), `clase` (`public-candidate` | `internal` | `experimental`), `ubicacion` (ruta repo-relativa existente), `notas`; los de categoría `schema` con `version` y `version_ref` (módulo:constante) cuando exista constante; los `cli` con `comando` y `subcomandos` y `exit_codes` observados.
**R2.** Cobertura mínima: CLI de `ds_guard`, `ds_init`, `harmessi` (doctor etc.), `harmessi_bench`, `dsimpact`, `providers.conformance`; schemas: `SourceObservation`, registro de fuentes, resultado de eval, run manifest, caso de eval, suite, baseline `.ds_init/control.json`, `control.json` de Change; contrato de frontmatter de skills; contrato de adapter de fuente (observer) y de `ProviderAdapter`; superficies del harness; comportamiento de upgrade (`ds_init upgrade`).
**R3.** Clasificación honesta: nada se marca `public-candidate` si es heredado sin versión explícita y sin test que lo ancle; lo nuevo de v0.13 que se persiste entre corridas lleva versión. Ninguna entrada promete estabilidad v1.0; el README del inventario lo dice.
**R4.** `test_v013_contract_inventory.py`: (a) JSON válido, ids únicos, categorías/clases dentro del vocabulario; (b) cada `ubicacion` existe; (c) para cada `cli` el conjunto de subcomandos del inventario coincide EXACTAMENTE con los reales (extraídos con `argparse`/`--help`, sin ejecutar acciones); (d) cada `version_ref` se resuelve por import y su valor coincide con `version`; (e) todo schema `public-candidate` tiene `version`; (f) las CLIs conocidas del repo (`tools/*/cli.py`, `tools/ds_guard.py`, `tools/providers/conformance.py`) figuran en el inventario (no hay CLI sin clasificar).

## B. Compatibilidad
**R5.** Fixtures sintéticos genéricos en `tools/tests/fixtures/compat/v0_11/` y `v0_12/` (sin datos reales): resultado de eval legado sin `schema_version` y sin `run_manifest`; resultado v0.13 con `cases_hash`; `SourceObservation` v1 como dict; registro de fuentes; baseline `.ds_init/control.json` de esa release (estructura mínima); `control.json` de Change; skill con frontmatter v0.12; `tasks.md` con traza.
**R6.** `test_v013_compat_window.py`: el código actual lee/valida esos artefactos sin error y con el significado esperado (`load_run` legado ⇒ comparable solo bajo las reglas de legado; `SourceObservation.from_dict`; `validate_registry`; `skill_contract` valida skills v0.12; `referencias_skills_cargados` lee trazas v0.11/v0.12; el lector del baseline managed reconoce la estructura). Una versión de schema **futura** se rechaza explícitamente (fail-closed) donde el contrato lo define.
**R7.** Verificación contra los tags reales `v0.11.0` y `v0.12.0` cuando existen localmente (`git show <tag>:<ruta>` de artefactos de plantilla/baseline): se parsean con el código actual; si el tag no existe ⇒ skip explícito (no falso OK).
**R8.** La ventana de soporte queda documentada en `docs/versioning.md`: lectura soportada de artefactos de la versión actual y las dos menores previas; anterior = mejor esfuerzo, sin garantía.

## C. Deprecación
**R9.** `tools/harmessi/deprecation.py` (solo-checkout, stdlib): `Deprecation(nombre, tipo, desde, reemplazo, remocion_minima)` (dataclass congelada), `DEPRECATIONS: tuple = ()`, `validar_registro(entradas)` (devuelve lista de problemas: versión semver válida `X.Y.Z`, `remocion_minima` estrictamente posterior a `desde` y al menos una versión menor posterior mientras sea 0.x, `reemplazo` no vacío, `tipo` en `{cli, flag, schema-field, skill-key, api}`, nombres únicos) y `advertir(nombre, registro=DEPRECATIONS)` que emite `DeprecationWarning` con formato fijo `"<nombre> está deprecado desde <desde>; usar <reemplazo>; se removerá no antes de <remocion_minima>"` y falla (`KeyError`) si el nombre no está registrado.
**R10.** `docs/deprecation.md`: cómo marcar, advertir, documentar el reemplazo y la versión de remoción más temprana; política: en 0.x una deprecación vive al menos una versión menor antes de remover; en 1.x al menos hasta la siguiente mayor; el registro v0.13 está vacío.
**R11.** Sin framework: sin decoradores globales, sin telemetría, sin escritura a disco.

## D. Versionado
**R12.** `docs/versioning.md`: interpretación de `0.x` (minor puede traer cambios incompatibles con nota de release y camino de upgrade; patch no) frente a `1.x` (incompatibles solo en major); reglas para cambios de schema (campo aditivo opcional = sin bump; cambio incompatible = bump de `schema_version` + lectura de la anterior dentro de la ventana), de CLI (flag nuevo = minor; remover/renombrar = deprecación + major en 1.x) y de assets managed; relación `HARNESS_VERSION` ↔ versiones de schema. No cambia la política vigente; la formaliza.

## E. Boundaries
**R13.** No se modifica ninguna CLI, exit code ni schema existente. Sin dependencias nuevas. Sin datos reales en fixtures. Tests no tocan la red.

## Criterios de aceptación
- [ ] R1–R4 inventario anclado. - [ ] R5–R8 compatibilidad y ventana. - [ ] R9–R11 deprecación. - [ ] R12 versionado. - [ ] R13 boundaries.
- [ ] Tests nuevos y de boundaries/manifest verdes.
