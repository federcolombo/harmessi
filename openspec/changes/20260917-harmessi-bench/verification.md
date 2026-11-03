# Verification — 20260917-harmessi-bench

## Evidencia obtenida

- **Regresión, suite `tools/harmessi_bench/tests`** (tras los fixes de la ronda de reviewer):
  `.venv/Scripts/python.exe -m pytest tools/harmessi_bench/tests -q` → `29 passed` en `0.34s`.
- **Regresión completa, suite `tools/tests`** (corrida antes de los fixes de reviewer, ya que
  los fixes solo tocaron `tools/harmessi_bench/` de forma aislada, sin necesidad de repetir la
  suite completa de 11 minutos después — criterio de eficiencia ya aplicado en este proyecto):
  `625 passed, 2 skipped, 32 subtests passed` en `696.54s` (0:11:36).
- **Smoke real end-to-end contra `claude_code`** (previsto en `tasks.md`): el Lead ejecutó
  `python -m tools.harmessi_bench.cli run --scenarios tools/harmessi_bench/scenarios/examples.json
  --provider claude_code --run-id v05-change1-smoke --json` de verdad. Resultado real:
  `{"run_id": "v05-change1-smoke", "total": 3, "pasaron": 3, "ruta":
  ".harmessi/evals/v05-change1-smoke/result.json"}` — los 3 escenarios de ejemplo
  (`responde-ok`, `suma-simple`, `formato-lista`) pasaron contra la CLI real de Claude Code, con
  `duration_s` de `8.05`/`5.52`/`6.16` segundos respectivamente y `stdout_excerpt`
  `"OK"`/`"4"`/`"Rojo\nAzul"` — confirma que el pipeline completo (CLI → `PROVIDER_REGISTRY` →
  `adapter.invoke()` real → parseo de `--output-format json` → scoring `exact`/`contains`/`regex`
  → `save_run`) funciona de punta a punta contra un proveedor real, no solo con adapters fake en
  tests. También se ejecutó `python -m tools.harmessi_bench.cli compare --baseline
  v05-change1-smoke --candidate v05-change1-smoke --json` (comparación de la corrida contra sí
  misma) → `{"regressions": [], "improvements": [], "unchanged": [3 escenarios],
  "solo_en_baseline": [], "solo_en_candidate": []}`, confirmando que `compare` funciona
  correctamente sobre datos reales. El directorio `.harmessi/evals/v05-change1-smoke/` generado
  por esta corrida no se commitea ni queda en el working tree (se borró después de capturar la
  evidencia): es un artefacto de verificación puntual, no parte del alcance de archivos aprobado
  de este Change (`control.json` no declara `.harmessi/evals/**` como ruta autorizada — un
  intento de agregarlo fue correctamente rechazado por el subagente anterior por ser una
  expansión del archivo de control de alcance sin confirmación explícita del usuario; el Lead
  optó por no insistir y en cambio no commitear el artefacto, dejando la evidencia registrada acá
  como texto en vez de como archivo del repo). Esta corrida real no se repite en Changes futuros
  salvo que cambie el contrato de `runner.py`/`cli.py` — mismo criterio que el smoke real de
  `claude -p` en Change 0.
- **Reviewer, ronda 1** (`data-science-reviewer`): revisó el diff completo. 4 hallazgos
  "importante": (1) `compare.py` accedía `resultado["score"]["passed"]` sin validar forma,
  `KeyError` crudo ante un `result.json` corrupto; (2) `cli.py` no capturaba errores de
  `load_scenarios`/`load_run` fuera de la ruta de provider, traceback crudo; (3) docstring de
  `core.py` afirmaba (incorrectamente) importar `tools.providers.core`, y la fila de
  `ARCHITECTURE.md` conflacia responsabilidades de `runner.py`/`storage.py` bajo la entrada de
  `core.py`; (4) flag `--root` de `cli.py` visible en `--help` pese a describirse como "no
  estable", inconsistente entre `run` y `compare`. Más 2 hallazgos "menor": `storage.py::save_run`
  podía dejar `harmessi_version=None` con un set vacío de escenarios; los 3 scorers no manejaban
  algunos casos de borde de tipos (`valores` no-lista, patrón regex inválido, `result` no-string).
- **Fixes aplicados** (única reinvocación correctiva del Change, cuenta 1 de 2 del contrato de
  autonomía): `compare.py` ahora valida la forma de cada resultado y levanta `ValueError` con
  `scenario_id`/`run_id` en el mensaje; `cli.py` captura `FileNotFoundError`/`json.JSONDecodeError`
  /`ValueError` en `cmd_run` y `cmd_compare` (incluyendo el `ValueError` de `compare_runs`, que en
  una primera pasada del fix había quedado fuera del bloque `try` — el propio test nuevo del fix
  lo detectó y se corrigió en la misma ronda) devolviendo exit 1 + mensaje claro sin traceback;
  docstring de `core.py` corregido y fila de `ARCHITECTURE.md` reescrita para describir solo
  `core.py`; `--root` oculto con `argparse.SUPPRESS` en ambos subcomandos; `storage.py::save_run`
  usa `HARNESS_VERSION` importado directo; `scorer_contains`/`scorer_regex` validan tipos y
  capturan `re.error`, `runner.py` normaliza un `result` no-string a `str` antes de scorear. 6
  tests nuevos agregados cubriendo los 6 fixes.
- **Alcance**: `python tools/ds_guard.py status --change-id 20260917-harmessi-bench --json` →
  `"fuera_de_alcance": []` (`control.json` se declaró con el alcance completo desde el inicio de
  la implementación, sin necesidad de correcciones de trazabilidad como en Change 0 — lección
  aplicada).
- **Privacidad**: no aplica un sweep dedicado (contenido genérico de framework de evals, sin
  nombres/rutas de AGD/UNCO/clientes); el sweep transversal obligatorio es Change 5.
- **Cero dependencias nuevas**: confirmado por lectura — todos los imports de
  `tools/harmessi_bench/*` son stdlib (`json`, `re`, `dataclasses`, `pathlib`, `argparse`, `sys`,
  `datetime`) + `tools.providers.core` (Change 0) + `tools.ds_init.version` (ya existente).

## Fingerprint

N/A — este Change es infraestructura de evals del harness, no un dataset ni un modelo de un
proyecto DS (ver secciones condicionales de `spec.md`).

## Diferencias contra la spec

Ninguna respecto a los requisitos R1-R9 de `spec.md`. Los fixes no cambiaron ningún contrato
público, solo endurecieron manejo de errores tal como preveía `design.md` ("Riesgos").

## Limitaciones

1. Scoring puramente determinista (contains/regex/exact) — proxy superficial de texto, no mide
   calidad semántica real. LLM-as-judge queda fuera de alcance de v0.5 (documentado en
   `design.md`).
2. El set de ejemplo (`examples.json`, 3 escenarios) es demostrativo, no una suite real de
   evaluación de Harmessi — cualquier uso serio requiere escenarios propios.
3. Sin `__main__.py` propio: se invoca como `python -m tools.harmessi_bench.cli`, no
   `python -m tools.harmessi_bench`.
4. No se evalúan flujos multi-agente completos (Lead + subagentes reales orquestando SDD) — solo
   escenarios puntuales de prompt→output contra un target, decisión explícita de alcance de este
   Change.
5. `.harmessi/evals/**` todavía no está declarado como ruta autorizada en ningún `control.json` de
   Change — una corrida real de `harmessi-bench` hoy genera un artefacto que un Change no puede
   commitear sin una declaración de alcance explícita y, dado lo sensible de tocar
   `rutas_autorizadas`, sin confirmación humana. Queda como decisión pendiente para quien use
   `harmessi-bench` en un Change futuro (o para el usuario, si quiere resolverlo de forma
   general).

## Pendientes derivados

- Las 5 limitaciones listadas arriba quedan como deuda de roadmap para v0.6+; ninguna bloquea el
  cierre de este Change.
- La decisión sobre cómo declarar `.harmessi/evals/**` como ruta autorizada (limitación 5) queda
  abierta para el próximo Change que necesite commitear una corrida real, o para el usuario.

## Resultado final

Change 1 (harmessi-bench) completo: framework de evals (core neutral + scenarios + runner +
storage + compare + CLI) implementado, revisado (1 ronda, 4 hallazgos importantes + 2 menores
corregidos) y verificado (654 tests totales entre las 2 suites afectadas + 1 corrida real de 3/3
escenarios contra claude_code + 1 compare real + alcance limpio); listo para cierre SDD y commit
local.
