"""Ventana de compatibilidad de lectura (v0.13 Change 5, R5-R7).

El código actual debe leer artefactos sintéticos con la forma de v0.11 y v0.12
(`tools/tests/fixtures/compat/`) y rechazar versiones de schema futuras donde
el contrato lo define. La verificación contra los tags reales es un refuerzo:
si el tag o git no están, el test se saltea explícitamente (nunca falso OK).
Sin red, sin datos reales.
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.datasources.core import SourceError, SourceObservation
from tools.datasources.registry import validate_registry
from tools.ds_init import control as control_mod
from tools.ds_init import managed_hash
from tools.dsguard import skill_contract
from tools.dsguard.core import ControlJsonError, leer_control
from tools.harmessi_bench import compare as compare_mod
from tools.harmessi_bench.compare import compare_runs
from tools.harmessi_bench.storage import load_run

RAIZ = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "compat"
VERSIONES = ("v0_11", "v0_12")
ROLES = {skill_contract.ROL_LEAD}


def _leer_json(version: str, nombre: str) -> dict:
    return json.loads((FIXTURES / version / nombre).read_text(encoding="utf-8"))


def _guardar_run(raiz: Path, datos: dict) -> str:
    run_id = datos["run_id"]
    directorio = raiz / run_id
    directorio.mkdir(parents=True, exist_ok=True)
    (directorio / "result.json").write_text(json.dumps(datos), encoding="utf-8")
    return run_id


# --- Resultados de eval ---------------------------------------------------------

@pytest.mark.parametrize("version", VERSIONES)
def test_resultado_legado_se_lee_como_version_0(version, tmp_path):
    datos = _leer_json(version, "eval_result_legado.json")
    assert "schema_version" not in datos and "run_manifest" not in datos
    cargado = load_run(_guardar_run(tmp_path, datos), root=tmp_path)
    assert cargado == datos


def test_legado_vs_legado_se_compara_solo_bajo_reglas_de_legado(tmp_path):
    datos = _leer_json("v0_11", "eval_result_legado.json")
    base = load_run(_guardar_run(tmp_path, datos), root=tmp_path)
    reporte = compare_runs(base, copy.deepcopy(base))
    assert reporte.verdict == compare_mod.VEREDICTO_EQUIVALENTE
    assert "legadas" in reporte.verdict_reason


def test_legado_vs_v013_es_inconcluso(tmp_path):
    legado = _leer_json("v0_12", "eval_result_legado.json")
    nuevo = _leer_json("v0_13", "eval_result_cases_hash.json")
    a = load_run(_guardar_run(tmp_path, legado), root=tmp_path)
    b = load_run(_guardar_run(tmp_path, nuevo), root=tmp_path)
    assert b["schema_version"] == 1 and len(b["cases_hash"]) == 64
    assert compare_runs(a, b).verdict == compare_mod.VEREDICTO_INCONCLUSO


def test_resultado_con_schema_futuro_se_rechaza(tmp_path):
    datos = _leer_json("v0_13", "eval_result_cases_hash.json")
    datos["schema_version"] = 99
    run_id = _guardar_run(tmp_path, datos)
    with pytest.raises(ValueError):
        load_run(run_id, root=tmp_path)


# --- Fuentes --------------------------------------------------------------------

@pytest.mark.parametrize("version", VERSIONES)
def test_source_observation_v1_se_lee(version):
    datos = _leer_json(version, "source_observation_v1.json")
    observacion = SourceObservation.from_dict(datos)
    assert observacion.schema_version == 1
    assert observacion.source_id == "fuente-ejemplo"
    assert observacion.to_dict()["fields"][0]["name"] == "columna_a"


def test_source_observation_futura_se_rechaza():
    datos = _leer_json("v0_12", "source_observation_v1.json")
    datos["schema_version"] = 2
    with pytest.raises(SourceError):
        SourceObservation.from_dict(datos)


@pytest.mark.parametrize("version", VERSIONES)
def test_registro_de_fuentes_valida(version):
    assert validate_registry(_leer_json(version, "sources_registry.json")) == []


def test_registro_de_fuentes_futuro_se_rechaza():
    datos = _leer_json("v0_12", "sources_registry.json")
    datos["schema_version"] = 2
    assert validate_registry(datos)


# --- Baseline managed y control de Change ---------------------------------------------

def _instalar_baseline(tmp_path: Path, version: str) -> Path:
    """Copia el fixture a `<tmp>/.ds_init/control.json` (donde lo busca la API real)."""
    destino = tmp_path / "proyecto"
    (destino / control_mod.DIR_CONTROL).mkdir(parents=True)
    origen = FIXTURES / version / "ds_init_control.json"
    (destino / control_mod.DIR_CONTROL / control_mod.NOMBRE_ARCHIVO_CONTROL).write_bytes(origen.read_bytes())
    return destino


def test_baseline_v012_migrate_hashes_reconoce_hash_alg(tmp_path):
    destino = _instalar_baseline(tmp_path, "v0_12")
    informe = control_mod.migrar_hashes(destino)  # dry-run
    assert sorted(informe.ya_actuales) == ["docs/ejemplo-managed.md", "docs/otro-managed.md"]
    assert not informe.migradas and not informe.desconocidas and not informe.no_verificables


def test_baseline_v011_sin_hash_alg_no_se_trata_como_actual(tmp_path):
    destino = _instalar_baseline(tmp_path, "v0_11")
    informe = control_mod.migrar_hashes(destino)  # dry-run; los archivos no existen en disco
    assert not informe.ya_actuales and not informe.migradas
    assert sorted(informe.no_verificables) == ["docs/ejemplo-managed.md", "docs/otro-managed.md"]


def test_verificar_entrada_legacy_y_vigente(tmp_path):
    archivo = tmp_path / "archivo.md"
    archivo.write_bytes(b"contenido sintetico\n")
    legado = dict(_leer_json("v0_11", "ds_init_control.json")["archivos"][0])
    legado["sha256"] = managed_hash.hash_crudo_file(archivo)
    assert "hash_alg" not in legado
    assert managed_hash.verificar_entrada(archivo, legado)[0] == managed_hash.ESTADO_OK_LEGACY

    vigente = dict(_leer_json("v0_12", "ds_init_control.json")["archivos"][0])
    vigente["sha256"] = managed_hash.hash_managed_file(archivo, vigente["hash_alg"])
    assert managed_hash.verificar_entrada(archivo, vigente)[0] == managed_hash.ESTADO_OK

    desconocido = dict(vigente, hash_alg="algoritmo/inexistente/v9")
    assert managed_hash.verificar_entrada(archivo, desconocido)[0] == managed_hash.ESTADO_ALG_DESCONOCIDO


@pytest.mark.parametrize("version", VERSIONES)
def test_control_de_change_se_lee_con_leer_control(version, tmp_path):
    ruta = tmp_path / "openspec" / "changes" / "20200101-ejemplo" / "control.json"
    ruta.parent.mkdir(parents=True)
    ruta.write_bytes((FIXTURES / version / "change_control.json").read_bytes())
    control = leer_control(ruta)
    assert control["schema_version"] == 1
    assert control["change_id"] == "20200101-ejemplo"
    assert control["alcance"]["rutas_autorizadas"] == ["docs/ejemplo.md"]


def test_control_de_change_con_schema_futuro_se_rechaza(tmp_path):
    datos = _leer_json("v0_12", "change_control.json")
    datos["schema_version"] = 99
    ruta = tmp_path / "control.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(ControlJsonError):
        leer_control(ruta)


# --- Skills ---------------------------------------------------------------------------

@pytest.mark.parametrize("version", VERSIONES)
def test_skill_con_frontmatter_de_la_release_valida(version):
    ruta = FIXTURES / version / "skill-ejemplo.md"
    assert skill_contract.validar_skill(ruta, ROLES) == []


@pytest.mark.parametrize(
    "version, esperadas",
    [("v0_11", ["skill-ejemplo", "otra-skill"]), ("v0_12", ["skill-ejemplo"])],
)
def test_traza_de_skills_cargados_se_lee(version, esperadas):
    texto = (FIXTURES / version / "tasks_con_traza.md").read_text(encoding="utf-8")
    assert skill_contract.referencias_skills_cargados(texto) == esperadas


def test_skill_con_clave_desconocida_se_rechaza():
    ruta = FIXTURES / "v0_12" / "skill-ejemplo.md"
    texto = ruta.read_text(encoding="utf-8").replace("roles:", "autonomy: alta\nroles:")
    # Se valida sobre una copia en memoria vía archivo temporal con el mismo nombre.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "skill-ejemplo.md"
        copia.write_text(texto, encoding="utf-8")
        codigos = {f.codigo for f in skill_contract.validar_skill(copia, ROLES)}
    assert "SKILL-CAMPO-NO-PERMITIDO" in codigos


# --- Verificación opcional contra los tags reales -----------------------------------------

def _git(*argumentos: str):
    if shutil.which("git") is None:
        pytest.skip("git no está disponible")
    return subprocess.run(["git", *argumentos], cwd=str(RAIZ), capture_output=True, timeout=60)


def _exigir_tag(tag: str) -> None:
    resultado = _git("rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}")
    if resultado.returncode != 0:
        pytest.skip(f"el tag {tag} no existe localmente")


def _git_show(tag: str, ruta: str):
    resultado = _git("show", f"{tag}:{ruta}")
    if resultado.returncode != 0:
        pytest.skip(f"{ruta} no existe en {tag}")
    return resultado.stdout.decode("utf-8")


@pytest.mark.parametrize("tag", ["v0.11.0", "v0.12.0"])
def test_baseline_real_del_tag_se_parsea(tag):
    _exigir_tag(tag)
    control = json.loads(_git_show(tag, ".ds_init/control.json"))
    assert isinstance(control.get("harness_version"), str)
    assert control_mod._entradas_previas_validas(control)


@pytest.mark.parametrize("tag", ["v0.11.0", "v0.12.0"])
def test_skills_reales_del_tag_tienen_frontmatter_parseable(tag):
    _exigir_tag(tag)
    listado = _git("ls-tree", "--name-only", tag, f"{skill_contract.DIR_SKILLS}/")
    nombres = [n for n in listado.stdout.decode("utf-8").splitlines() if n.endswith(".md")]
    if not nombres:
        pytest.skip(f"{tag} no tiene skills componibles")
    for nombre in nombres:
        datos, hallazgos = skill_contract.parsear_frontmatter(_git_show(tag, nombre))
        assert datos is not None and not hallazgos, nombre
        for clave in skill_contract.CLAVES_OBLIGATORIAS:
            assert clave in datos, f"{nombre}: falta {clave}"
