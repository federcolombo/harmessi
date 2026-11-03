"""Contratos `stable` de v1 (Change 20261030-v1-contract-stabilization, R2-R5).

- R2: exactamente 6 ids con clase `stable` en `docs/contracts/inventory.json`.
- R5: los fixtures reales de `v0.15.0` (`fixtures/compat/v0_15/`) coinciden con su MANIFEST y se leen con
  los lectores ACTUALES de los 3 schemas stable.
- R3: política de campos desconocidos top-level (aditivo tolerado) y de versión (futura rechazada;
  ausente rechazada en SourceObservation/registro, leída como 0 en eval-result).
- R4: la superficie CLI del snapshot de `v0.15.0` está incluida en la superficie viva de las 3 CLIs stable
  (agregar no rompe; quitar/renombrar un subcomando o flag, o endurecer required/choices, sí).

Sin red. No ejecuta comandos de las CLIs: solo introspecciona los parsers.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tools.datasources import registry as registry_mod
from tools.datasources.core import SourceError, SourceObservation
from tools.harmessi_bench.storage import RESULT_SCHEMA_VERSION, load_run

RAIZ = Path(__file__).resolve().parents[2]
V015 = Path(__file__).resolve().parent / "fixtures" / "compat" / "v0_15"
INVENTARIO = RAIZ / "docs" / "contracts" / "inventory.json"

IDS_STABLE = {
    "cli-ds-guard", "cli-ds-init", "cli-harmessi",
    "schema-source-observation", "schema-source-registry", "schema-eval-result",
}
FIXTURES_V015 = (
    "source_observation.json", "sources_registry.json", "eval_result.json", "cli_surface.json",
)


def _cargar_extraer_superficie():
    """Carga `tools/tests/cli_surface.py` por ruta (tools/tests no es un paquete)."""
    ruta = Path(__file__).resolve().parent / "cli_surface.py"
    spec = importlib.util.spec_from_file_location("cli_surface_v1", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.extraer_superficie


extraer_superficie = _cargar_extraer_superficie()


def _fx(nombre: str) -> dict:
    return json.loads((V015 / nombre).read_text(encoding="utf-8"))


# --- R2: exactamente 6 ids stable -----------------------------------------------------

def test_ids_stable_son_exactamente_los_seis():
    contratos = json.loads(INVENTARIO.read_text(encoding="utf-8"))["contratos"]
    stable = {c["id"] for c in contratos if c["clase"] == "stable"}
    assert stable == IDS_STABLE, (
        f"faltan {sorted(IDS_STABLE - stable)}; sobran {sorted(stable - IDS_STABLE)}"
    )


# --- R6: doc-tests ----------------------------------------------------------------------

def _seccion(texto: str, titulo: str) -> str:
    """Cuerpo de la sección `titulo` hasta el siguiente encabezado del mismo o mayor nivel."""
    nivel = len(titulo) - len(titulo.lstrip("#"))
    lineas = texto[texto.index(titulo) + len(titulo):].splitlines()
    cuerpo = []
    for linea in lineas:
        if linea.startswith("#") and len(linea.split(" ", 1)[0]) <= nivel:
            break
        cuerpo.append(linea)
    return " ".join(cuerpo)


def test_versioning_declara_promesa_v1():
    texto = (RAIZ / "docs" / "versioning.md").read_text(encoding="utf-8")
    assert "Ningún contrato es `stable` hoy" not in texto
    assert "Hoy no se promete estabilidad v1.0" not in texto
    for id_stable in IDS_STABLE:
        assert id_stable in texto, id_stable
    ventana = _seccion(texto, "## Ventana de compatibilidad")
    assert "1.x" in ventana
    assert "v0_15" in ventana or "v0.15.0" in ventana
    assert "artefactos de **0.15**" in ventana
    assert "desconocidas" in texto


def test_versioning_acota_la_promesa_de_exit_codes():
    texto = (RAIZ / "docs" / "versioning.md").read_text(encoding="utf-8")
    seccion = _seccion(texto, "### Exit codes garantizados")
    assert "0 = éxito" in seccion and "distinto de 0" in seccion
    assert "observado, no garantizado" in seccion


def test_inventario_exit_codes_contrato_coherente_con_la_promesa_acotada():
    contratos = json.loads(INVENTARIO.read_text(encoding="utf-8"))["contratos"]
    for c in contratos:
        if c["id"] in {"cli-ds-guard", "cli-ds-init", "cli-harmessi"}:
            promesa = c["exit_codes_contrato"]
            assert "0 = éxito" in promesa and "observado" in promesa, c["id"]
            assert "comprometidos" not in promesa, c["id"]


def test_readme_contratos_define_stable():
    texto = (RAIZ / "docs" / "contracts" / "README.md").read_text(encoding="utf-8")
    assert "- `stable`:" in texto
    assert "no una promesa de estabilidad" not in texto


# --- R5: MANIFEST ---------------------------------------------------------------------

def test_manifest_v015_coincide_con_los_fixtures():
    manifiesto = _fx("MANIFEST.json")
    assert manifiesto["tag_origen"] == "v0.15.0"
    # SHA del commit del tag (los tags se borran antes del corte publico: queda la huella).
    assert re.fullmatch(r"[0-9a-f]{40}", manifiesto["commit_origen"]), manifiesto.get("commit_origen")
    assert sorted(manifiesto["fixtures"]) == sorted(FIXTURES_V015)
    for nombre, datos in manifiesto["fixtures"].items():
        # Se normaliza CRLF -> LF: autocrlf de Windows puede alterar los bytes en el checkout.
        crudo = (V015 / nombre).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(crudo).hexdigest() == datos["sha256"], nombre


# --- R5/R3: SourceObservation -----------------------------------------------------------

def test_source_observation_v015_se_lee_y_hace_round_trip():
    datos = _fx("source_observation.json")
    observacion = SourceObservation.from_dict(datos)
    assert observacion.schema_version == 1
    assert observacion.to_dict() == datos
    assert SourceObservation.from_dict(observacion.to_dict()) == observacion


def test_source_observation_version_futura_se_rechaza():
    datos = _fx("source_observation.json")
    datos["schema_version"] = 2
    with pytest.raises(SourceError):
        SourceObservation.from_dict(datos)


def test_source_observation_version_ausente_se_rechaza():
    datos = _fx("source_observation.json")
    del datos["schema_version"]
    with pytest.raises(SourceError):
        SourceObservation.from_dict(datos)


def test_source_observation_clave_top_level_extra_se_tolera():
    datos = _fx("source_observation.json")
    datos["clave_aditiva_v1"] = {"x": 1}
    observacion = SourceObservation.from_dict(datos)
    # La clave extra se ignora (no se conserva en la re-serialización).
    assert "clave_aditiva_v1" not in observacion.to_dict()


def test_source_observation_dataset_rechaza_clave_desconocida():
    datos = _fx("source_observation.json")
    datos["dataset"]["clave_aditiva_v1"] = 1
    with pytest.raises(SourceError):
        SourceObservation.from_dict(datos)


def test_source_observation_provenance_ignora_clave_desconocida():
    datos = _fx("source_observation.json")
    datos["provenance"]["clave_aditiva_v1"] = 1
    assert "clave_aditiva_v1" not in SourceObservation.from_dict(datos).to_dict()["provenance"]


# --- R5/R3: registro de fuentes ----------------------------------------------------------

def test_registro_v015_valida_sin_hallazgos():
    assert registry_mod.validate_registry(_fx("sources_registry.json")) == []


def test_registro_version_futura_da_hallazgo():
    datos = _fx("sources_registry.json")
    datos["schema_version"] = 2
    hallazgos = registry_mod.validate_registry(datos)
    assert any(ruta == "$.schema_version" for _, ruta, _ in hallazgos), hallazgos


def test_registro_version_ausente_da_hallazgo():
    datos = _fx("sources_registry.json")
    del datos["schema_version"]
    hallazgos = registry_mod.validate_registry(datos)
    assert any(ruta == "$.schema_version" for _, ruta, _ in hallazgos), hallazgos


def test_registro_clave_top_level_extra_se_tolera():
    # `validate_registry` solo mira `schema_version` y `sources`: una clave top-level extra no genera hallazgo.
    datos = _fx("sources_registry.json")
    datos["clave_aditiva_v1"] = 1
    assert registry_mod.validate_registry(datos) == []


def test_registro_entrada_rechaza_clave_desconocida():
    datos = _fx("sources_registry.json")
    datos["sources"][0]["clave_aditiva_v1"] = 1
    hallazgos = registry_mod.validate_registry(datos)
    assert any(ruta == "$.sources[0].clave_aditiva_v1" for _, ruta, _ in hallazgos), hallazgos


# --- R5/R3: eval-result ---------------------------------------------------------------------

def _instalar_run(tmp_path: Path, datos: dict) -> Path:
    destino = tmp_path / datos["run_id"]
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "result.json").write_text(json.dumps(datos, indent=2), encoding="utf-8")
    return tmp_path


def test_eval_result_v015_se_lee_con_load_run(tmp_path):
    datos = _fx("eval_result.json")
    leido = load_run(datos["run_id"], root=_instalar_run(tmp_path, datos))
    assert leido == datos
    assert leido["schema_version"] == RESULT_SCHEMA_VERSION == 1


def test_eval_result_version_futura_se_rechaza(tmp_path):
    datos = _fx("eval_result.json")
    datos["schema_version"] = 99
    with pytest.raises(ValueError):
        load_run(datos["run_id"], root=_instalar_run(tmp_path, datos))


def test_eval_result_version_ausente_se_lee_como_legado(tmp_path):
    # `load_run` hace `contenido.get("schema_version", 0)`: ausente == 0 (legado), igual que un 0 explicito.
    ausente = _fx("eval_result.json")
    del ausente["schema_version"]
    explicito = _fx("eval_result.json")
    explicito["schema_version"] = 0
    leido_ausente = load_run(ausente["run_id"], root=_instalar_run(tmp_path / "a", ausente))
    leido_explicito = load_run(explicito["run_id"], root=_instalar_run(tmp_path / "b", explicito))
    assert leido_ausente == ausente  # se lee sin error ni modificacion
    assert {k: v for k, v in leido_explicito.items() if k != "schema_version"} == leido_ausente


def test_eval_result_version_cero_no_se_trata_como_futura(tmp_path):
    datos = _fx("eval_result.json")
    datos["schema_version"] = 0
    assert load_run(datos["run_id"], root=_instalar_run(tmp_path, datos))["schema_version"] == 0


def test_eval_result_clave_top_level_extra_se_acepta(tmp_path):
    datos = _fx("eval_result.json")
    datos["clave_aditiva_v1"] = 1
    leido = load_run(datos["run_id"], root=_instalar_run(tmp_path, datos))
    assert leido["clave_aditiva_v1"] == 1


# --- R4: superficie CLI ------------------------------------------------------------------------

def comparar_superficie(snapshot: dict, vivo: dict) -> list:
    """Violaciones de compatibilidad de `vivo` respecto de `snapshot` (ambos de `extraer_superficie`).

    Se detecta: ruta de subcomando ausente; flag ausente; flag que pasa de no-requerido a requerido;
    `choices` del snapshot no contenidas en las vivas (o flag libre que pasa a tener `choices`);
    posicional del snapshot ausente. Agregar rutas, flags o choices NO es violación.
    """
    violaciones: list = []
    for ruta, esperado in snapshot.items():
        etiqueta = ruta or "<raiz>"
        if ruta not in vivo:
            violaciones.append(f"subcomando ausente: {etiqueta}")
            continue
        actual = vivo[ruta]
        for flag, info in esperado["flags"].items():
            if flag not in actual["flags"]:
                violaciones.append(f"flag ausente: {etiqueta} {flag}")
                continue
            vivo_info = actual["flags"][flag]
            if vivo_info["required"] and not info["required"]:
                violaciones.append(f"flag pasa a required: {etiqueta} {flag}")
            if vivo_info["nargs"] != info["nargs"]:
                violaciones.append(f"nargs cambiado: {etiqueta} {flag}")
            if info["choices"] is None:
                if vivo_info["choices"] is not None:
                    violaciones.append(f"flag libre pasa a tener choices: {etiqueta} {flag}")
            elif vivo_info["choices"] is None or not set(info["choices"]) <= set(vivo_info["choices"]):
                violaciones.append(f"choices reducidas: {etiqueta} {flag}")
        for flag, vivo_info in actual["flags"].items():
            if flag not in esperado["flags"] and vivo_info["required"]:
                violaciones.append(f"flag nuevo obligatorio: {etiqueta} {flag}")
        for nombre, info in esperado["posicionales"].items():
            if nombre not in actual["posicionales"]:
                violaciones.append(f"posicional ausente: {etiqueta} {nombre}")
                continue
            vivo_info = actual["posicionales"][nombre]
            if vivo_info["nargs"] != info["nargs"] or (vivo_info["required"] and not info["required"]):
                violaciones.append(f"posicional cambiado (nargs/required): {etiqueta} {nombre}")
            if info["choices"] is not None and (
                vivo_info["choices"] is None or not set(info["choices"]) <= set(vivo_info["choices"])
            ):
                violaciones.append(f"choices reducidas: {etiqueta} {nombre}")
        for nombre, vivo_info in actual["posicionales"].items():
            if nombre not in esperado["posicionales"] and vivo_info["required"]:
                violaciones.append(f"posicional nuevo obligatorio: {etiqueta} {nombre}")
        previos = list(esperado["posicionales"])
        if all(n in actual["posicionales"] for n in previos) and list(actual["posicionales"])[: len(previos)] != previos:
            violaciones.append(f"posicionales reordenados: {etiqueta}")
    return violaciones


@functools.lru_cache(maxsize=None)
def _superficie_ds_guard_subproceso() -> str:
    """Superficie de `ds_guard` extraida en un subproceso (D3): importar `tools/ds_guard.py` hace
    `sys.path.insert(0, ...)`, efecto secundario que no se quiere en el proceso de pytest."""
    codigo = (
        "import importlib.util, json, sys\n"
        "spec = importlib.util.spec_from_file_location('cli_surface_sub', sys.argv[1])\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "from tools.ds_guard import construir_parser\n"
        "print(json.dumps(m.extraer_superficie(construir_parser())))\n"
    )
    ruta = str(Path(__file__).resolve().parent / "cli_surface.py")
    proceso = subprocess.run(
        [sys.executable, "-c", codigo, ruta], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return proceso.stdout.strip().splitlines()[-1]


def _superficie_viva(cli_id: str) -> dict:
    if cli_id == "cli-ds-guard":
        return json.loads(_superficie_ds_guard_subproceso())
    if cli_id == "cli-ds-init":
        from tools.ds_init.cli import construir_parser
    elif cli_id == "cli-harmessi":
        from tools.harmessi.cli import construir_parser
    else:  # pragma: no cover
        raise AssertionError(cli_id)
    return extraer_superficie(construir_parser())


CLIS_STABLE = ("cli-ds-guard", "cli-ds-init", "cli-harmessi")


def test_snapshot_cubre_las_tres_clis_stable():
    snapshot = _fx("cli_surface.json")
    assert snapshot["snapshot_version"] == 2
    assert set(snapshot["clis"]) == set(CLIS_STABLE)
    for cli_id in CLIS_STABLE:
        superficie = snapshot["clis"][cli_id]
        assert "" in superficie and len(superficie) >= 2, f"{cli_id}: snapshot vacio o sin subcomandos"
        assert any(r["flags"] or r["posicionales"] for r in superficie.values()), cli_id


def test_generador_usa_el_helper_unico_de_superficie():
    texto = (Path(__file__).resolve().parent / "fixtures" / "compat" / "generate_v015.py").read_text(encoding="utf-8")
    assert "def extraer_superficie" not in texto and "def _recorrer" not in texto
    assert "cli_surface.py" in texto


@pytest.mark.parametrize("cli_id", CLIS_STABLE)
def test_superficie_viva_incluye_el_snapshot_v015(cli_id):
    snapshot = _fx("cli_surface.json")["clis"][cli_id]
    assert comparar_superficie(snapshot, _superficie_viva(cli_id)) == []


def test_superficie_viva_es_comparable_consigo_misma():
    # Sanidad: el parser vivo es compatible con su propia extracción (no hay falsos positivos).
    for cli_id in CLIS_STABLE:
        superficie = _superficie_viva(cli_id)
        assert comparar_superficie(superficie, superficie) == [], cli_id


def _parser_sintetico(*, con_flag=True, con_sub=True, flag_requerido=False, choices=("a", "b"), extra=False, nuevo_requerido=False):
    parser = argparse.ArgumentParser(prog="sintetico")
    parser.add_argument("--global", dest="global_", action="store_true")
    subs = parser.add_subparsers(dest="cmd")
    if con_sub:
        sub = subs.add_parser("correr")
        sub.add_argument("entrada")
        if con_flag:
            sub.add_argument("--modo", choices=list(choices) if choices else None, required=flag_requerido)
        if extra:
            sub.add_argument("--nuevo", required=nuevo_requerido)
    subs.add_parser("otro")
    if extra:
        subs.add_parser("agregado")
    return parser


def test_comparador_acepta_superficie_identica_o_ampliada():
    base = extraer_superficie(_parser_sintetico())
    assert comparar_superficie(base, extraer_superficie(_parser_sintetico())) == []
    ampliada = extraer_superficie(_parser_sintetico(choices=("a", "b", "c"), extra=True))
    assert comparar_superficie(base, ampliada) == []  # agregar subcomando/flag/choice no rompe


def test_comparador_detecta_flag_removido():
    base = extraer_superficie(_parser_sintetico())
    violaciones = comparar_superficie(base, extraer_superficie(_parser_sintetico(con_flag=False)))
    assert any("flag ausente" in v and "--modo" in v for v in violaciones), violaciones


def test_comparador_detecta_subcomando_removido():
    base = extraer_superficie(_parser_sintetico())
    violaciones = comparar_superficie(base, extraer_superficie(_parser_sintetico(con_sub=False)))
    assert any("subcomando ausente" in v and "correr" in v for v in violaciones), violaciones


def test_comparador_detecta_flag_vuelto_requerido():
    base = extraer_superficie(_parser_sintetico())
    violaciones = comparar_superficie(base, extraer_superficie(_parser_sintetico(flag_requerido=True)))
    assert any("pasa a required" in v and "--modo" in v for v in violaciones), violaciones


def test_comparador_detecta_flag_nuevo_obligatorio():
    base = extraer_superficie(_parser_sintetico())
    violaciones = comparar_superficie(base, extraer_superficie(_parser_sintetico(extra=True, nuevo_requerido=True)))
    assert any("flag nuevo obligatorio" in v and "--nuevo" in v for v in violaciones), violaciones


def test_comparador_detecta_cambio_de_nargs():
    def parser(nargs):
        p = argparse.ArgumentParser(prog="s")
        p.add_argument("--lista", nargs=nargs)
        return p

    violaciones = comparar_superficie(extraer_superficie(parser("*")), extraer_superficie(parser("+")))
    assert any("nargs cambiado" in v for v in violaciones), violaciones


def test_comparador_detecta_posicional_nuevo_obligatorio():
    def parser(extra):
        p = argparse.ArgumentParser(prog="s")
        p.add_argument("a")
        if extra:
            p.add_argument("b")
        return p

    violaciones = comparar_superficie(extraer_superficie(parser(False)), extraer_superficie(parser(True)))
    assert any("posicional nuevo obligatorio" in v for v in violaciones), violaciones


def test_comparador_detecta_choices_reducidas():
    base = extraer_superficie(_parser_sintetico())
    violaciones = comparar_superficie(base, extraer_superficie(_parser_sintetico(choices=("a",))))
    assert any("choices reducidas" in v for v in violaciones), violaciones
