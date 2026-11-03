# Harmessi v1.0 — Auditoría de readiness (sobre v0.15.0)

Fecha: 2026-10-30. Base: `main == 7e7c681 == v0.15.0`. Rama de trabajo: `v1-dev`.
Parte de la matriz de `openspec/changes/20261026-v015-release-hardening/verification.md` (R3) y la
re-evalúa con evidencia nueva de esta auditoría. No re-ejecuta la regresión completa de v0.15 (7.2k tests, ya
corrida el 2026-10-27); las corridas nuevas están en "Evidencia nueva".

## Evidencia nueva (esta auditoría)

| Evidencia | Resultado |
|---|---|
| CI remoto `portability-smoke` sobre `7e7c681` (v0.15.0) | success en ubuntu, windows y macos (Python 3.12), 2026-10-30. Cubre la lista acotada del workflow, no toda la suite. |
| Análisis estático de 472 `.py` con `ast.parse(feature_version=(3,9))` | 0 errores de sintaxis; 0 anotaciones `X \| Y` evaluadas en runtime; 1 API ≥3.9 (`is_relative_to`, válida en 3.9). Python 3.9 **no ejecutado**. |
| Clon sin tags (como quedará el repo público) + tests que usan tags `v0.11`–`v0.14` | 157 passed, 11 skipped (tag inexistente), 0 failed. Los tests se saltean limpiamente. |
| `test_public_docs`, `test_privacy_sweep`, `test_v015_release_hardening_smoke` con los cambios de licencia | 34 passed. |
| Backup privado `harmessi-pre-v1` | 29 refs idénticas al local, `fsck` limpio, `v0.15.0` → `7e7c681`. |
| Referencias a licencia | Solo `LICENSE`, `NOTICE`, `CITATION.cff`, `README.md`, `docs/roadmap/v1.0.md` (ya migradas en `c11a21e`). Sin `pyproject`, classifiers ni código de terceros empaquetado. |

## Inventario de contratos públicos

`docs/contracts/inventory.json` (51 contratos): 6 `public-candidate` (3 CLIs: `ds_guard`, `ds_init`,
`harmessi`; 3 schemas: `SourceObservation`, registro de fuentes, resultado de eval), 14 `internal`, 31
`experimental`. **Ninguno es `stable`** (`docs/versioning.md`). Anclaje actual de las CLIs: solo nombres de
subcomandos y exit codes; los flags no tienen ancla. Fixtures reales de tag: solo contratos improve y baselines
de `.ds_init/control.json`; los de los 3 schemas candidatos son sintéticos.

## Matriz de 14 criterios (re-evaluada)

| # | Criterio | v0.15 | Ahora | Nota |
|---|---|---|---|---|
| 1 | Contratos CLI estables | PARTIAL | PARTIAL → **G2** | Falta ancla de flags y promoción a `stable`. |
| 2 | Schemas versionados y migrables | PARTIAL | PARTIAL → **G2**, G4 | `control.json` sin `schema_version` por decisión B-02. |
| 3 | Upgrade/migration probado | PASS | PASS | 0.14→0.15 idempotente; falta repetir 0.15→1.0 (**G6**). |
| 4 | Backward compatibility formal | PARTIAL | PARTIAL → **G2**, G3 | Ventana solo para artefactos con test. |
| 5 | CI cross-platform | PARTIAL | **PASS (alcance declarado)** | Observado en 3 SO con Python 3.12 y lista acotada. Python 3.9 sin ejecutar → **G5**. |
| 6 | Instalación y upgrades reproducibles | PASS | PASS | |
| 7 | Compatibilidad de providers | PARTIAL | ACCEPTED LIMITATION | `claude_code` live-validated en un host; codex/gemini/grok contract-tested. Matriz honesta en `docs/providers.md`. |
| 8 | Evals/benchmarks públicos | ACCEPTED LIMITATION | ACCEPTED LIMITATION | Suite sintética de 9 casos, sin baseline numérico. |
| 9 | Release process repetible | PASS | PASS | |
| 10 | Documentación pública completa | PARTIAL | ACCEPTED LIMITATION | Sin validación de lector externo. |
| 11 | Privacidad/portabilidad verificadas | PARTIAL | ACCEPTED LIMITATION | Barrido heurístico; CI en 3 SO (acotado); suite completa solo en Windows. |
| 12 | Estrategia de deprecación | PASS | PASS | |
| 13 | Recuperación ante instalaciones parciales | PASS | PASS | |
| 14 | Versionado semántico consistente | PASS | PASS | Se activa la política 1.x en **G2**. |

Sin FAIL. Resultado: PASS 7, PARTIAL 3 (criterios 1, 2 y 4, los tres cerrados por G2), ACCEPTED LIMITATION 4.

## Gaps y clasificación

| id | Gap | Clase | Cierre |
|---|---|---|---|
| G1 | Licencia Apache-2.0 → PolyForm Shield 1.0.0; falta un ancla en tests. | **V1 BLOCKER** | Texto y metadatos hechos (`c11a21e`); ancla de test en C2. |
| G2 | Ningún contrato es `stable`: v1.0 debe significar contratos usables por terceros con estabilidad esperable. | **V1 BLOCKER** | C1: promover exactamente los 6 `public-candidate`. Implementado en el Change 20261030-v1-contract-stabilization (cerrado 2026-11-02, GREEN). |
| G3 | Ventana de compatibilidad solo para artefactos con test. | ACCEPTED FOR V1 | Se declara para 1.0 en C1; el resto queda fuera de la promesa. Implementado en el Change 20261030-v1-contract-stabilization (cerrado 2026-11-02, GREEN). |
| G4 | `.ds_init/control.json` sin `schema_version` (B-02). | ACCEPTED FOR V1 | Decisión documentada. |
| G5 | `README` declara Python 3.9+ pero CI solo ejecuta 3.12. | **V1 BLOCKER** (solo texto) | C2: declarar 3.12 verificado y 3.9 mínimo no ejecutado. |
| G6 | Upgrade 0.15.0→1.0.0 sin probar; baseline y notas de 1.0.0. | **V1 BLOCKER** | C2: release hardening estándar. |
| G7 | 31 contratos `experimental` y 14 `internal` fuera de la promesa. | ACCEPTED FOR V1 | Se declara explícitamente en `versioning.md`/inventory. Implementado en el Change 20261030-v1-contract-stabilization (cerrado 2026-11-02, GREEN). |
| G8 | Providers: un solo host live-validated. | ACCEPTED FOR V1 | Matriz honesta; live de codex/gemini/grok es POST-V1. |
| G9 | Evals sin baseline numérico. | ACCEPTED FOR V1 | Baseline real y suite no sintética son POST-V1. |
| G10 | Docs sin lector externo; privacidad heurística; suite completa solo en Windows. | ACCEPTED FOR V1 | Revisión externa y CI de suite completa son POST-V1. |
| G11 | Tests que usan tags `v0.x` y fixtures generados desde tags que se borrarán del repo público. | ACCEPTED FOR V1 | Verificado: se saltean sin fallar; los fixtures quedan versionados. La procedencia por tag deja de ser verificable por terceros: se declara en las notas de 1.0.0. |
| G12 | CI remoto del nuevo historial público solo observable tras el corte. | ACCEPTED FOR V1 | Se verifica el primer push post-corte. |
| G13 | Instalaciones de `ds_init` en repos de terceros no incluyen aviso de licencia propio (Shield exige pasar los términos al redistribuir). | **V1 BLOCKER** (decidido 2026-10-30) | C2: asset managed `HARMESSI-LICENSE.txt` con términos/notice de los componentes Harmessi, aclarando que NO relicencia el proyecto del usuario; sin `LICENSE` genérico; en manifest, baseline, tests y upgrade. |
| G14 | GitHub Release UI manual (sin `gh`). | ACCEPTED FOR V1 | Paso manual en el corte. |
| G15 | Procedencia no criptográfica; sin validación en macOS/Linux de la suite completa. | POST-V1 | |

## Roadmap mínimo para v1.0 (2 Changes, sin features)

1. **`20261030-v1-contract-stabilization`** (G2, G3, G7): promover a `stable` los 3 CLIs y 3 schemas
   `public-candidate` cumpliendo los criterios de promoción de `docs/versioning.md`: ventana 1.0 declarada,
   fixtures reales generados del tag `v0.15.0` (deben generarse **antes** del corte porque los tags se borran),
   test de lector fail-closed, ancla de flags/subcomandos de las 3 CLIs y ancla doc-test. Activar la política
   1.x y declarar fuera de la promesa todo lo `experimental`/`internal`.
2. **`20261030-v1-release-hardening`** (G1, G5, G6, G13): ancla de licencia (LICENSE idéntico al texto oficial,
   `Required Notice:` presente, sin "Apache"/"open source" fuera de notas históricas), precisión de Python en
   README, versión 1.0.0, notas, baseline regenerado una vez, regresión serial, install limpio, upgrade
   0.15.0→1.0.0 idempotente, Doctor 0 ERROR, barrido de privacidad, clon sin tags, matriz final.

Conclusión provisoria: **NOT READY FOR v1.0 — gaps G1, G2, G5, G6, G13** (los cinco con cierre definido arriba).

## Estado de corte (2026-11-02)

- Fases A, B y C cerradas. Backup `harmessi-pre-v1` verificado; el repo público no se tocó.
- Fase D, Change 1 `20261030-v1-contract-stabilization`: **cerrado GREEN** (reviewer final sin BLOCKER/HIGH; 660 tests dirigidos verdes).
  Evidencia en `openspec/changes/20261030-v1-contract-stabilization/verification.md`. Deuda LOW que pasa al Change 2:
  `True`/`1.0` aceptados como `schema_version` en `tools/datasources/registry.py`; `test_v015_compat_window.py` ancla `HARNESS_VERSION == "0.15.0"`.
- Change 2 `20261102-v1-release-hardening`: **cerrado GREEN** (2026-11-03). Asset `HARMESSI-LICENSE.txt` (G13), ancla de licencia (G1),
  README Python 3.12/3.9 (G5), versión 1.0.0, notas `docs/releases/v1.0.0.md`, baseline regenerado una vez (135 archivos), upgrade 0.15.0→1.0.0 idempotente (G6).
  Evidencia en `openspec/changes/20261102-v1-release-hardening/verification.md`: lote 1 (2759 passed + 1 test obsoleto corregido, 44 passed en su archivo),
  lote 2 (4581 passed, 0 failed), privacidad 20 passed, clon sin tags 1487 passed, Doctor 0 ERROR. Una enmienda T1 (2 rutas).
- Deuda post-v1 (no bloquea 1.0): `T1 scope preflight / amendment batching` — detectar de forma conservadora los paths previsibles
  (hooks, telemetría, artefactos generados, tests auxiliares, baseline, verification, cierre) y pedir una única ampliación exacta.
- Fase E sin empezar. STOP humano obligatorio antes de cualquier operación destructiva sobre el repo público.

### Hallazgos del reviewer (resueltos en f287fb0 y fb62461; ronda final GREEN)

No revisado: `deprecation.md`, sección Contracts de `README.md`, `ARCHITECTURE.md` ~l.976, `test_v015_compat_window.py`, privacidad completa de `cli_surface.json`; no corrió tests (yo sí: 179 verdes).

- **H1** Exit codes "garantizados" sin test que lo respalde: `inventory.json` se contradice (l.7 "comprometidos" vs l.25/l.41 "observados"); el test `test_v013_contract_inventory.py:268-299` solo verifica que el código aparece en el módulo. Arreglar: tests de significado por CLI o acotar la promesa y alinear inventory/versioning/README.
- **H2** Doc-test de ventana 1.0 vacuo (`test_v1_stable_contracts.py:68-75` busca "1.0" y "desconocidas"). Anclar la sección de ventana, "1.x" y `v0_15`.
- **M1** Sub-objetos rechazan claves desconocidas (dataset, provenance, entradas del registro) sin test y en tensión con "aditivo = minor": documentar el límite de la promesa y testearlo.
- **M2** `harmessi_version_documented` "1.0.x" y docs en pasado ("se promovieron en 1.0.0") con `HARNESS_VERSION` 0.15.0: aceptable hasta el bump de C2; revisar redacción.
- **M3** Snapshot CLI: no compara `nargs`; un flag/posicional nuevo `required=True` pasa como adición; el test de cobertura no impide snapshot vacío; `import tools.ds_guard` con `sys.path.insert` (D3 pedía subproceso).
- **M4** Fixtures no reproducibles byte a byte (timestamps/plataforma en `eval_result.json`) y el MANIFEST no guarda el SHA del commit de `v0.15.0`: guardarlo antes del corte (`7e7c681`).
- **M5** `tools/tests/cli_surface.py` falta en el alcance autorizado (amendar o declarar); `tasks.md` sin marcar; `extraer_superficie` duplicada (generador y `cli_surface.py`) sin test de divergencia.
- **LOW** `IDS_STABLE` duplicado; chequeo débil de "garantiza"; nombres de tests con `public_candidate`; `True` pasa como `schema_version` en el registro; test de versión ausente en eval-result no verifica lectura como 0; ventana pre-v1 vs 1.0 puede confundir.
