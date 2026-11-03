"""Generador de fixtures reales de contratos del tag v0.15.0 (Change 20261030-v1-contract-stabilization, T1).

SOLO-CHECKOUT: no se instala en proyectos ni lo corre la suite normal. Los fixtures NO se escriben a mano:
se generan con el CODIGO DEL TAG v0.15.0 (no con el checkout actual).

Uso (desde cualquier directorio; <dir_tree> debe ser un directorio NUEVO y VACIO fuera del repo):

    git archive v0.15.0 | tar -x -C <dir_tree>
    python tools/tests/fixtures/compat/generate_v015.py --tree <dir_tree> --out tools/tests/fixtures/compat/v0_15

El script hace `chdir(<dir_tree>)` y antepone el arbol a `sys.path`; importa `tools.*` del tag y aborta si el
paquete importado no vive en el arbol o si HARNESS_VERSION != "0.15.0".

Genera en `--out`:
- `source_observation.json`: `SourceObservation.to_dict()` (tools.datasources.core), `generated_at` fijo.
- `sources_registry.json`: registro `{schema_version, sources}` con `SourceRef.to_dict()`; se verifica que
  `registry.validate_registry` no devuelva hallazgos.
- `eval_result.json`: `result.json` real escrito por `tools.harmessi_bench.storage.save_run` con suite,
  `cases_hash` y `run_manifest` (volatiles: `timestamp_utc`, `started_utc`/`finished_utc`, plataforma, git).
- `cli_surface.json`: snapshot de ds_guard / ds_init / harmessi por introspeccion del parser (sin ejecutar).
- `MANIFEST.json`: tag_origen, harmessi_version, generador y sha256 de cada fixture.

`extraer_superficie` NO se duplica: se importa por ruta de `tools/tests/cli_surface.py` (fuente unica, solo
stdlib; se aplica a los parsers del arbol del tag). Normalizacion: en `eval_result.json` timestamps, plataforma
y git se fijan a valores constantes, de modo que regenerar produce los mismos bytes. El MANIFEST registra
`commit_origen` (SHA pelado de `git rev-parse v0.15.0^{commit}`, ejecutado en el repo del generador).

Efectos secundarios del import: `tools/ds_guard.py` hace `sys.path.insert(0, <arbol>/tools)` al importarse;
solo afecta a este proceso. Los archivos se escriben en bytes (LF), sin conversion de fin de linea.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TAG_ORIGEN = "v0.15.0"
VERSION_ESPERADA = "0.15.0"
GENERADOR = "tools/tests/fixtures/compat/generate_v015.py"
GENERATED_AT = "2026-10-30T12:00:00+00:00"
FIXTURES = ("source_observation.json", "sources_registry.json", "eval_result.json", "cli_surface.json")


def _preparar_arbol(arbol: Path) -> None:
    """Fija cwd y sys.path en el arbol del tag y verifica que `tools` venga de ahi."""
    if not (arbol / "tools" / "datasources").is_dir() or not (arbol / "tools" / "harmessi_bench").is_dir():
        raise SystemExit(f"--tree no parece un arbol de {TAG_ORIGEN} (faltan tools/datasources o tools/harmessi_bench)")
    os.chdir(arbol)
    sys.path.insert(0, str(arbol))
    for nombre in [n for n in sys.modules if n == "tools" or n.startswith("tools.")]:
        del sys.modules[nombre]
    import tools  # noqa: PLC0415
    import tools.datasources  # noqa: PLC0415
    import tools.harmessi_bench  # noqa: PLC0415

    # `tools` es un namespace package (sin __init__.py): se valida con `__path__`.
    raiz_arbol = arbol.resolve()
    for paquete in (tools, tools.datasources, tools.harmessi_bench):
        for entrada in list(paquete.__path__):
            ruta = Path(entrada).resolve()
            if ruta != raiz_arbol and raiz_arbol not in ruta.parents:
                raise SystemExit(f"`{paquete.__name__}` se importo de {ruta}, fuera del arbol {arbol}")
    from tools.ds_init.version import HARNESS_VERSION  # noqa: PLC0415

    if HARNESS_VERSION != VERSION_ESPERADA:
        raise SystemExit(f"HARNESS_VERSION del arbol es {HARNESS_VERSION!r}; se esperaba {VERSION_ESPERADA!r}")


def _commit_del_tag() -> str:
    """SHA del commit (pelado, sin el objeto tag anotado) al que apunta `v0.15.0` en el repo del generador."""
    repo = Path(__file__).resolve().parents[4]
    try:
        salida = subprocess.run(
            ["git", "rev-parse", f"{TAG_ORIGEN}^{{commit}}"], cwd=repo, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"no se pudo resolver el commit de {TAG_ORIGEN} con git rev-parse: {exc}")
    if len(salida) != 40 or any(c not in "0123456789abcdef" for c in salida):
        raise SystemExit(f"git rev-parse devolvio un SHA invalido: {salida!r}")
    return salida


def _serializar(obj) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _generar_source_observation() -> bytes:
    from tools.datasources.core import FieldObservation, SourceObservation, SourceProvenance  # noqa: PLC0415

    provenance = SourceProvenance(
        source_id="demo-orders", observer_id="observers.demo:crear_observer", observer_code_sha256=None,
        access_mode="read", source_kind="file", generated_at=GENERATED_AT,
        tool_versions={"harmessi": VERSION_ESPERADA},
        requested_facets=("schema", "row_count", "null_count", "value_range"), unsupported_facets=(),
    )
    campos = (
        FieldObservation("order_id", "integer", "int64",
                         {"null_count": {"value": 0, "exactness": "exact"},
                          "value_range": {"value": {"min": 1, "max": 1000}, "exactness": "exact"}}),
        FieldObservation("estado", "string", "object",
                         {"value_distribution": {"value": [{"value": "abierto", "frequency": 600},
                                                           {"value": "cerrado", "frequency": 400}],
                                                 "exactness": "exact", "complete": True}}),
        FieldObservation("fecha_pedido", "date", None,
                         {"time_range": {"value": {"min": "2026-01-01", "max": "2026-09-30"}, "exactness": "exact"}}),
    )
    obs = SourceObservation(
        source_id="demo-orders", provenance=provenance,
        dataset={"row_count": {"value": 1000, "exactness": "exact"},
                 "fingerprint": {"algorithm": "sha256", "value": "0" * 64},
                 "snapshot": {"as_of": "2026-09-30", "cutoff": None},
                 "sampling": {"active": False, "method": None, "sample_size": None, "seed": None}},
        fields=campos,
        omitted_facets=({"field": "estado", "facet": "distinct_count", "reason": "no soportada por el observer"},),
    )
    datos = obs.to_dict()
    SourceObservation.from_dict(datos)  # round-trip con el lector del tag
    return _serializar(datos)


def _generar_registry() -> bytes:
    from tools.datasources.core import SourceRef  # noqa: PLC0415
    from tools.datasources.registry import validate_registry  # noqa: PLC0415

    fuentes = [
        SourceRef("demo-orders", "raw_table", "observers.demo:crear_observer", "read", "internal",
                  config_ref="env:DEMO_ORDERS_REF", options={"formato": "csv"}, extra={"x_nota": "fixture"}),
        SourceRef("demo-features", "feature_table", "observers.demo:crear_observer", "read", "public"),
    ]
    registro = {"schema_version": 1, "sources": [f.to_dict() for f in fuentes]}
    hallazgos = validate_registry(registro)
    if hallazgos:
        raise SystemExit(f"validate_registry del tag rechazo el registro generado: {hallazgos}")
    return _serializar(registro)


def _generar_eval_result(arbol: Path, tmp: Path) -> bytes:
    from tools.ds_init.version import HARNESS_VERSION  # noqa: PLC0415
    from tools.harmessi_bench.core import EvalResult, EvalTarget, Scenario, ScoreResult  # noqa: PLC0415
    from tools.harmessi_bench.runmanifest import construir_manifest  # noqa: PLC0415
    from tools.harmessi_bench.storage import load_run, save_run  # noqa: PLC0415
    from tools.harmessi_bench.suite import Suite, calcular_cases_hash  # noqa: PLC0415

    run_id = "fixture-v015"
    target = EvalTarget(provider_id="fake", model="m1", effort="low")
    escenarios = [
        Scenario("s1", "Responde OK", "basico", expected={"tipo": "contains", "valores": ["OK"]}),
        Scenario("s2", "Responde LISTO", "basico", expected={"tipo": "contains", "valores": ["LISTO"]}),
    ]
    cases_hash = calcular_cases_hash(escenarios)
    suite = Suite("suite-fake", 1, [e.scenario_id for e in escenarios], cases_hash, 1)
    resultados = [
        EvalResult(run_id=run_id, scenario_id=e.scenario_id, target=target, exit_code=0, ok=True,
                   availability_error=None, duration_s=0.5, stdout_excerpt=texto,
                   score=ScoreResult(passed=True, score=1.0, detail="coincide"),
                   harmessi_version=HARNESS_VERSION, timestamp_utc=GENERATED_AT)
        for e, texto in zip(escenarios, ("OK", "LISTO"))
    ]
    manifest = construir_manifest(run_id, target, suite=suite, cases_hash=cases_hash, seed=0, repo_root=arbol)
    raiz = tmp / "evals"
    ruta = save_run(run_id, resultados, target, root=raiz, suite=suite, cases_hash=cases_hash, run_manifest=manifest)
    cargado = load_run(run_id, root=raiz)  # lector del tag
    for clave in ("schema_version", "cases_hash", "run_manifest", "suite"):
        if clave not in cargado:
            raise SystemExit(f"result.json generado sin {clave!r}")
    return _normalizar_eval_result(json.loads(ruta.read_text(encoding="utf-8")))


def _normalizar_eval_result(datos: dict) -> bytes:
    """Reemplaza lo volatil (timestamps, plataforma, git) por valores fijos: fixture reproducible.

    `identity_hash` no depende de esos campos (ver `runmanifest.py`), asi que sigue siendo el real.
    """
    datos["timestamp_utc"] = GENERATED_AT
    manifiesto = datos["run_manifest"]
    manifiesto["started_utc"] = GENERATED_AT
    manifiesto["finished_utc"] = GENERATED_AT
    manifiesto["platform"] = {"system": "fixture", "python": "0.0.0", "implementation": "fixture"}
    manifiesto["git"] = {"commit": "unknown", "clean": None}
    for sesion in manifiesto["sesiones"]:
        sesion["started_utc"] = GENERATED_AT
        sesion["finished_utc"] = GENERATED_AT
        sesion["git_commit"] = "unknown"
    return _serializar(datos)


# --- extraccion de superficie CLI: fuente unica en tools/tests/cli_surface.py ----------------------

def _cargar_extraer_superficie():
    """Importa `extraer_superficie` del helper del repo actual (solo stdlib), por ruta."""
    ruta = Path(__file__).resolve().parents[2] / "cli_surface.py"
    spec = importlib.util.spec_from_file_location("cli_surface_generador", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.extraer_superficie


def _generar_cli_surface() -> bytes:
    extraer_superficie = _cargar_extraer_superficie()
    from tools import ds_guard  # noqa: PLC0415
    from tools.ds_init import cli as ds_init_cli  # noqa: PLC0415
    from tools.harmessi import cli as harmessi_cli  # noqa: PLC0415

    snapshot = {
        "snapshot_version": 2,
        "tag_origen": TAG_ORIGEN,
        "clis": {
            "cli-ds-guard": extraer_superficie(ds_guard.construir_parser()),
            "cli-ds-init": extraer_superficie(ds_init_cli.construir_parser()),
            "cli-harmessi": extraer_superficie(harmessi_cli.construir_parser()),
        },
    }
    return _serializar(snapshot)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Genera fixtures de compat de v0.15.0 (solo-checkout).")
    parser.add_argument("--tree", required=True, help="Directorio con el arbol de `git archive v0.15.0`.")
    parser.add_argument("--out", required=True, help="Destino de los fixtures (p. ej. tools/tests/fixtures/compat/v0_15).")
    args = parser.parse_args(argv)

    salida = Path(args.out).resolve()  # resolver antes del chdir al arbol
    arbol = Path(args.tree).resolve()
    commit_origen = _commit_del_tag()  # antes del chdir: se ejecuta en el repo actual
    _preparar_arbol(arbol)

    with tempfile.TemporaryDirectory(prefix="fixtures v015 ") as tmp:
        contenidos = {
            "source_observation.json": _generar_source_observation(),
            "sources_registry.json": _generar_registry(),
            "eval_result.json": _generar_eval_result(arbol, Path(tmp)),
            "cli_surface.json": _generar_cli_surface(),
        }

    salida.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for nombre in FIXTURES:
        (salida / nombre).write_bytes(contenidos[nombre])
        hashes[nombre] = hashlib.sha256(contenidos[nombre]).hexdigest()

    manifiesto = {
        "tag_origen": TAG_ORIGEN,
        "commit_origen": commit_origen,
        "harmessi_version": VERSION_ESPERADA,
        "generador": GENERADOR,
        "fixtures": {nombre: {"sha256": hashes[nombre]} for nombre in sorted(hashes)},
    }
    (salida / "MANIFEST.json").write_bytes(_serializar(manifiesto))
    print(f"fixtures de {TAG_ORIGEN} escritos en {salida} ({len(hashes)} archivos + MANIFEST.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
