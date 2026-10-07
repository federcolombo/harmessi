# Verificación — 20261007-v09-release-hardening

## Resumen ejecutivo
Change 5 (último) de v0.9: release hardening de `v0.9-dev`, sin features nuevas. SDD aprobado por hash el 2026-10-07 con la autorización humana
anticipada. Único cambio bajo `tools/**` además del smoke de release: `tools/ds_init/version.py` (`HARNESS_VERSION = "0.9.0"`). Sin push, tag, merge ni
GitHub Release.

## Audit de estado (verificado, no asumido)
- Changes 0–4 (`20261002-card-and-evidence-foundation`, `20261002-data-cards`, `20261005-model-cards`, `20261005-model-risk-responsible-ai`,
  `20261005-cards-governance-integration`), interludio `20261002-exec-approval-registration` y Correctives A/B/C: todos `estado: cerrada` en su `tasks.md`.
- Seis Changes históricos de v0.3/v0.4 siguen `en_progreso` (preexistentes, ajenos a v0.9; ver limitaciones).
- `origin` solo con `main`; `v0.9-dev` local; sin tag v0.9; `git ls-files docs/feedback .harmessi` vacío.

## Qué entrega
- **Versión 0.9.0** en las tres ubicaciones de la convención de v0.8.0: `version.py` (fuente canónica), `CITATION.cff` (`version`, `date-released 2026-10-07`) y
  `.ds_init/control.json` (`harness_version`, regenerado UNA vez con `control.regenerar_control`; el resto de hashes ya coincidía). Versionados internos
  independientes sin tocar (`ds_profile.TOOL_VERSION`, `sampling.VERSION_ALGORITMO`).
- **Roadmap:** `v0.9.md` (estado final, tabla de Changes/Correctives, Changes 1–3 marcados implementados), `README.md` de roadmap (v0.9.0 «lista para publicar», no
  «publicada»), `v0.10.md` con sección de handoff consolidada (deuda viva, sin deudas resueltas marcadas pendientes).
- **Docs públicas:** README (bullet de Data Cards/Model Cards/Model Governance con la salvedad de que Harmessi gobierna evidencia y no afirma
  ético/justo/seguro/privado/conforme; párrafo de `ds_profile` exact→sampled) y `docs/releases/v0.9.0.md` («Harmessi v0.9.0 — Cards & Model Governance») con
  limitaciones públicas separadas de la deuda interna. `ARCHITECTURE.md` §7: se corrigió un aviso obsoleto («no hay Cards ni CLI/Doctor») hallado por el reviewer.
- **Privacidad:** sweep sobre 731+ archivos tracked. Se sanitizaron 4 referencias al nombre del informe de feedback externo (roadmap v0.9 y 3 propuestas de
  Correctives) y una ruta personal de usuario en una propuesta histórica; `.gitignore` agrega `docs/feedback/` y `.harmessi/`. `fijaciones_granos`, `planes_comerciales`,
  emails personales y tokens: sin hallazgos (los valores tipo credencial son fixtures del scanner de secretos). Dimensiones de un dataset real (~620 k × 27) permanecen
  en documentos del Corrective C como dato anónimo (decisión consciente).
- **Smoke de release** (`tools/tests/test_v09_release_hardening_smoke.py`, 12 tests): coherencia de versión, higiene de tracked y `.gitignore`, sweep de privacidad
  (patrones por concatenación, sobre tracked + nuevos no ignorados), dependencias (solo stdlib; `pyarrow` solo perezoso) en Cards/pep440/guardrails_drift/ds_profile,
  roadmap v0.9/v0.10, honestidad de las release notes, Cards sin imports de autonomy/leadrun.

## Evidencia de release (real, en directorios temporales)
- **Matriz de instalación (CLI real, `--stage experiment`):** A default → `[predictive_modeling]`, sin `tools/cards` ni `governance/` (120 archivos); B `data_cards` → `data_cards` +
  `tools/cards`; C `data_cards`+`model_governance` → ambas con `predictive_modeling`, sin `governance/`; D `predictive_modeling` deshabilitada + `model_governance` → exit 2, 0 archivos
  escritos; E sync con `predictive_modeling` deshabilitada + enable `data_cards` → `predictive_modeling` NO se reactiva, y `model_governance` en sync sin predictive se rechaza.
  También `data_cards` sin predictive (stage discovery) instala/importa. Cubierto además por `tools/ds_init/tests/test_cards_capabilities.py` (en la regresión).
- **Adopción pre-v0.9:** proyecto instalado en discovery con `governance/mi_nota.md`, `notebooks/a.py` y `CLAUDE.md` con regla propia, sync a experiment con ambas
  capabilities: contenido del usuario byte a byte intacto, ninguna Card creada automáticamente, `governance/` project-owned.
- **Cards E2E, governance/reporting, inercia de autonomía, Correctives A/B/C:** cubiertos por los tests existentes dentro de la regresión global
  (`tools/cards/tests`, `tools/reporting/tests`, `tools/harmessi/tests`, `tools/autonomy/tests`, neutralidad en `tools/tests`, `tools/ds_profile/tests`); no se duplicaron fixtures.
  `report_kind="governance"` es exploratorio y solo `evaluation` autoriza lectura de holdout (verificado por el reviewer contra `tools/reporting/governance.py`).

## Regresión global final (UNA vez, runtime gobernado, lotes secuenciales)
| Lote | Suites | Exit | passed | skipped | subtests |
|---|---|---|---|---|---|
| B1 | `tools/tests` | 0 | 1482 | 7 | 30 215 |
| B2 | `tools/ds_init/tests` | 0 | 180 | 0 | 16 |
| B3 | modelquality, qualityevidence, datasources, datacontracts | 0 | 511 | 0 | 150 |
| B4 | autonomy, leadrun | 0 | 260 | 0 | 261 |
| B5 | `tools/cards/tests` | 0 | 1230 | 34 | 2 577 |
| B6 | harmessi, reporting | 0 | 1024 | 3 | 677 |
| B7 | ds_profile, dsimpact, fallback, harmessi_bench, providers, routing | 0 | 351 | 10 | 29 |

**Total único: 5038 passed, 54 skipped, 0 failed, 33 925 subtests.** Los lotes B4–B7 incluyen el archivo del smoke solo como ancla de alcance del runtime
(`--deselect`, 12 tests deseleccionados por lote, no contados). Intentos previos sin tests ejecutados (no cuentan): B1 por un error de colección de mi propio smoke (un byte NUL
escrito por un script, corregido) y B4–B7 por un node id de ancla que pytest no resolvió (exit 2/4, 0 tests); se reejecutaron solo esos lotes. La corrida dirigida previa
(smoke + v07 smoke + ds_init: 197 passed) se reemplaza por B1/B2 y no se suma. Los 10 skips de B7 son tests de Parquet sin `pyarrow` en el venv del repo; con `pyarrow` (otro intérprete, Corrective C)
`tools/ds_profile/tests` dio 169 passed, 0 skipped sobre el mismo código.

## Proceso de revisión
Un reviewer transversal (ciclo 1, solo lectura): 0 bloqueantes; 1 IMPORTANTE (`ARCHITECTURE.md` §7 obsoleto) corregido; menores atendidos: tiempos verbales de `v0.9.md` (Changes 1–3 marcados
implementados), smoke con `ls-files -z --cached --others --exclude-standard`. Menores aceptados como limitaciones del smoke: patrones de privacidad específicos del autor, lista de exclusión por nombre de Change, chequeo de import
perezoso heurístico, `test_version_es_09` fija 0.9.0 (actualizar en v0.10). Ciclo 2 no necesario (sin bloqueantes pendientes).

## Dependencias
Sin dependencias nuevas (verificado por el smoke y por inspección: Cards, governance, subset PEP 440 y guardrails_drift solo stdlib; `pyarrow` sigue opcional y perezoso en `ds_profile`; sin `packaging`/sklearn).

## Limitaciones conocidas (públicas en `docs/releases/v0.9.0.md`; internas en `v0.10.md`)
Públicas: ApprovalRef no es prueba criptográfica; Cards/governance no son motor de cumplimiento ni bloquean autonomía; `.harmessi/` local no versionado; Data Card histórica `stale`; presupuesto de
memoria de `ds_profile` estimativo; cobertura limitada de symlink/junction en Windows; hashing CRLF/LF; personalizar campos managed de guardrails marca drift. Internas: seis Changes históricos v0.3/v0.4 aún
`en_progreso`; `core.autocrlf` avisa conversión a CRLF; CSV irregular en `ds_profile`; one-writer; amend de scope a mitad de Change.

## Resultado final
Change 5 completo y verde. Sin STOP. Pendiente exclusivamente la aprobación humana y el release (merge/tag/GitHub Release), fuera de este Change.
