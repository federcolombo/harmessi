"""Ancla `docs/contracts/inventory.json` al código (v0.13 Change 5, R4).

El inventario es un inventario, no una promesa de estabilidad. Estos tests
comparan el JSON contra la realidad: rutas, subcomandos de cada CLI y
constantes de versión. No ejecutan acciones de las CLIs (solo `--help`/parsers).
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
INVENTARIO = RAIZ / "docs" / "contracts" / "inventory.json"

CATEGORIAS = {"cli", "schema", "skills", "managed-assets", "adapter", "provider", "surfaces", "upgrade"}
CLASES = {"public-candidate", "internal", "experimental"}
RE_KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _cargar() -> dict:
    return json.loads(INVENTARIO.read_text(encoding="utf-8"))


def _contratos() -> list:
    return _cargar()["contratos"]


def _clis() -> list:
    return [c for c in _contratos() if c["categoria"] == "cli"]


# --- Subcomandos reales ---------------------------------------------------------

def _subcomandos_de_parser(parser: argparse.ArgumentParser) -> set:
    for accion in parser._actions:
        if isinstance(accion, argparse._SubParsersAction):
            return set(accion.choices)
    return set()


def _help_subproceso(argumentos: list) -> str:
    entorno = dict(os.environ)
    entorno["PYTHONIOENCODING"] = "utf-8"
    entorno["COLUMNS"] = "200"
    resultado = subprocess.run(
        [sys.executable] + argumentos + ["--help"],
        cwd=str(RAIZ),
        capture_output=True,
        env=entorno,
        timeout=120,
    )
    assert resultado.returncode == 0, resultado.stderr.decode("utf-8", errors="replace")
    return resultado.stdout.decode("utf-8", errors="replace")


def _subcomandos_desde_help(texto: str) -> set:
    """Lista `{a,b,c}` del bloque `usage:` (primer grupo de choices); vacío si no hay."""
    bloque = texto.split("\n\n", 1)[0]
    bloque = re.sub(r"\s+", " ", bloque)
    coincidencia = re.search(r"\{([^{}]+)\}", bloque)
    if coincidencia is None:
        return set()
    return {parte.strip() for parte in coincidencia.group(1).split(",") if parte.strip()}


def _subcomandos_reales(ubicacion: str) -> set:
    if ubicacion == "tools/ds_guard.py":
        return _subcomandos_desde_help(_help_subproceso([str(RAIZ / "tools" / "ds_guard.py")]))
    if ubicacion == "tools/providers/conformance.py":
        return _subcomandos_desde_help(_help_subproceso(["-m", "tools.providers.conformance"]))
    if ubicacion == "tools/ds_init/cli.py":
        from tools.ds_init.cli import construir_parser

        for accion in construir_parser()._actions:
            if accion.dest == "accion":
                return set(accion.choices)
        raise AssertionError("ds_init: no se encontró el argumento 'accion'")
    fabricas = {
        "tools/harmessi/cli.py": ("tools.harmessi.cli", "construir_parser"),
        "tools/harmessi_bench/cli.py": ("tools.harmessi_bench.cli", "_construir_parser"),
        "tools/dsimpact/cli.py": ("tools.dsimpact.cli", "construir_parser"),
        "tools/reporting/cli.py": ("tools.reporting.cli", "_construir_parser"),
        "tools/ds_profile/cli.py": ("tools.ds_profile.cli", "_construir_parser"),
    }
    if ubicacion not in fabricas:
        pytest.fail(f"CLI sin extractor de subcomandos: {ubicacion}; agregarlo a mano en este test")
    modulo, nombre = fabricas[ubicacion]
    parser = getattr(importlib.import_module(modulo), nombre)()
    return _subcomandos_de_parser(parser)


# --- (a) forma ------------------------------------------------------------------

def test_json_valido_y_cabecera():
    datos = _cargar()
    assert datos["inventory_version"] == 1
    assert isinstance(datos["harmessi_version_documented"], str)
    assert isinstance(datos["contratos"], list) and datos["contratos"]


def test_ids_unicos_kebab_y_vocabulario():
    ids = [c["id"] for c in _contratos()]
    assert len(ids) == len(set(ids)), "ids duplicados"
    for contrato in _contratos():
        assert RE_KEBAB.match(contrato["id"]), contrato["id"]
        assert contrato["categoria"] in CATEGORIAS, contrato["id"]
        assert contrato["clase"] in CLASES, contrato["id"]
        assert isinstance(contrato.get("notas"), str) and contrato["notas"].strip(), contrato["id"]


def test_cobertura_minima_por_categoria():
    presentes = {c["categoria"] for c in _contratos()}
    assert presentes == CATEGORIAS
    ids = {c["id"] for c in _contratos()}
    for esperado in (
        "cli-ds-guard", "cli-ds-init", "cli-harmessi", "cli-harmessi-bench", "cli-dsimpact",
        "cli-providers-conformance", "schema-source-observation", "schema-source-registry",
        "schema-eval-result", "schema-run-manifest", "schema-eval-case", "schema-eval-suite",
        "schema-ds-init-baseline", "schema-change-control", "skills-frontmatter",
        "adapter-source-observer", "provider-adapter", "surfaces-harness", "upgrade-ds-init",
    ):
        assert esperado in ids, esperado


# --- (b) ubicaciones -------------------------------------------------------------

def test_ubicaciones_existen():
    for contrato in _contratos():
        ubicacion = contrato["ubicacion"]
        assert not Path(ubicacion).is_absolute() and "\\" not in ubicacion, contrato["id"]
        assert (RAIZ / ubicacion).exists(), f"{contrato['id']}: no existe {ubicacion}"


# --- (c) subcomandos de CLI -----------------------------------------------------

def test_cli_tienen_comando_subcomandos_y_exit_codes():
    for contrato in _clis():
        assert isinstance(contrato.get("comando"), str) and contrato["comando"], contrato["id"]
        assert isinstance(contrato.get("subcomandos"), list), contrato["id"]
        assert isinstance(contrato.get("exit_codes"), dict) and "0" in contrato["exit_codes"], contrato["id"]
        assert len(contrato["subcomandos"]) == len(set(contrato["subcomandos"])), contrato["id"]


@pytest.mark.parametrize("contrato", [c for c in _clis()], ids=lambda c: c["id"])
def test_subcomandos_coinciden_exactamente_con_los_reales(contrato):
    reales = _subcomandos_reales(contrato["ubicacion"])
    declarados = set(contrato["subcomandos"])
    assert declarados == reales, (
        f"{contrato['id']}: faltan en el inventario {sorted(reales - declarados)}; "
        f"sobran {sorted(declarados - reales)}"
    )


# --- (d) versiones ---------------------------------------------------------------

_DEPENDENCIAS_OPCIONALES = {"pandas", "pyarrow", "numpy", "plotly"}


def test_version_ref_resuelve_y_coincide():
    con_ref = [c for c in _contratos() if "version_ref" in c]
    assert con_ref, "se esperaban schemas con version_ref"
    for contrato in con_ref:
        modulo, _, constante = contrato["version_ref"].partition(":")
        assert modulo and constante, contrato["id"]
        try:
            valor = getattr(importlib.import_module(modulo), constante)
        except ModuleNotFoundError as exc:
            if exc.name in _DEPENDENCIAS_OPCIONALES:
                continue  # dependencia opcional ausente en este entorno
            raise
        assert "version" in contrato, contrato["id"]
        assert valor == contrato["version"], f"{contrato['id']}: {valor!r} != {contrato['version']!r}"


def test_version_ref_apunta_a_la_ubicacion_declarada():
    for contrato in _contratos():
        if "version_ref" in contrato:
            modulo = contrato["version_ref"].partition(":")[0]
            assert modulo.replace(".", "/") + ".py" == contrato["ubicacion"], contrato["id"]


# --- (e) public-candidate de schema requiere versión ---------------------------------

def test_schema_public_candidate_tiene_version():
    for contrato in _contratos():
        if contrato["categoria"] == "schema" and contrato["clase"] == "public-candidate":
            assert "version" in contrato, contrato["id"]
            assert "version_ref" in contrato, contrato["id"]


def test_inventario_no_promete_estabilidad_v1():
    texto = INVENTARIO.read_text(encoding="utf-8").casefold()
    assert "estable" not in texto and "garantiza" not in texto.replace("no garantizados", "")


# --- (f) ninguna CLI sin clasificar --------------------------------------------------

def test_todas_las_cli_conocidas_estan_inventariadas():
    conocidas = {p.relative_to(RAIZ).as_posix() for p in (RAIZ / "tools").glob("*/cli.py")}
    conocidas.add("tools/ds_guard.py")
    conocidas.add("tools/providers/conformance.py")
    inventariadas = {c["ubicacion"] for c in _clis()}
    sin_clasificar = sorted(conocidas - inventariadas)
    assert not sin_clasificar, f"CLI sin clasificar en el inventario: {sin_clasificar}"


# Scripts con guarda `__main__` fuera del inventario de CLIs, con su motivo.
EXCLUSIONES_MAIN = {
    "tools/notebook_runner.py": "wrapper de ejecución de notebooks invocado por 'ds_guard exec notebook'; no es una CLI pública",
    "tools/ds_init/check_manifest_parity.py": "script de desarrollo del checkout (paridad de manifest); no se instala",
}
PREFIJOS_HOOK = ("hook_",)  # entry points de hooks PreToolUse/launchers, no CLIs de usuario


def _es_test_o_fixture(partes: tuple) -> bool:
    return "tests" in partes or "fixtures" in partes or "__pycache__" in partes


def test_scripts_con_main_estan_inventariados_o_excluidos():
    inventariadas = {c["ubicacion"] for c in _clis()}
    sin_clasificar = []
    for ruta in sorted((RAIZ / "tools").rglob("*.py")):
        relativa = ruta.relative_to(RAIZ)
        if _es_test_o_fixture(relativa.parts) or ruta.name == "__main__.py":
            continue
        if re.search(r"""if\s+__name__\s*==\s*["']__main__["']""", ruta.read_text(encoding="utf-8")) is None:
            continue
        clave = relativa.as_posix()
        if clave in inventariadas or clave in EXCLUSIONES_MAIN or ruta.name.startswith(PREFIJOS_HOOK):
            continue
        sin_clasificar.append(clave)
    assert not sin_clasificar, f"scripts ejecutables sin clasificar ni excluir (con motivo): {sin_clasificar}"


def test_exclusiones_main_existen_y_tienen_motivo():
    for ruta, motivo in EXCLUSIONES_MAIN.items():
        assert (RAIZ / ruta).exists(), ruta
        assert motivo.strip()


# --- Exit codes anclados al código (M1) ---------------------------------------------------

CLIS_CON_DOCSTRING_DE_CODIGOS = {"cli-ds-guard", "cli-ds-profile", "cli-reporting"}


def _evidencia_codigo(fuente: str, codigo: str) -> bool:
    patrones = (
        rf"return\s+{codigo}\b",
        rf"sys\.exit\(\s*{codigo}\s*\)",
        rf"SystemExit\(\s*{codigo}\b",
        rf"EXIT_\w*\s*=\s*{codigo}\b",
    )
    if any(re.search(p, fuente) for p in patrones):
        return True
    if codigo == "2" and "argparse" in fuente:
        return True  # argparse sale con 2 ante uso inválido
    if codigo in ("0", "1") and "exit_code" in fuente:
        return True  # código derivado de un helper `exit_code(...)`
    return False


@pytest.mark.parametrize("contrato", [c for c in _clis()], ids=lambda c: c["id"])
def test_exit_codes_aparecen_en_el_modulo_de_la_cli(contrato):
    fuente = (RAIZ / contrato["ubicacion"]).read_text(encoding="utf-8")
    for codigo in contrato["exit_codes"]:
        assert _evidencia_codigo(fuente, codigo), f"{contrato['id']}: el código {codigo} no aparece en el módulo"


@pytest.mark.parametrize("contrato", [c for c in _clis() if c["id"] in CLIS_CON_DOCSTRING_DE_CODIGOS], ids=lambda c: c["id"])
def test_exit_codes_coinciden_con_el_docstring(contrato):
    import ast

    arbol = ast.parse((RAIZ / contrato["ubicacion"]).read_text(encoding="utf-8"))
    docstring = ast.get_docstring(arbol, clean=False) or ""
    documentados = set(re.findall(r"^ {4}(\d) ", docstring, flags=re.MULTILINE))
    assert documentados, f"{contrato['id']}: el docstring no lista códigos"
    assert documentados == set(contrato["exit_codes"]), contrato["id"]


def test_cli_public_candidate_declara_su_ancla():
    for contrato in _clis():
        if contrato["clase"] == "public-candidate":
            assert isinstance(contrato.get("ancla"), str) and contrato["ancla"].strip(), contrato["id"]


# --- Constantes de versión persistidas (M2) ----------------------------------------------

_RE_NOMBRE_VERSION = re.compile(r"SCHEMA_VERSION|_CONTRACT_VERSION|MANIFEST_VERSION|SCHEMA_VERSION_SOPORTADA")

# (ruta repo-relativa, nombre) -> motivo. Hoy vacío: los tests y fixtures se excluyen por directorio.
EXCLUSIONES_VERSION = {}


def _constantes_de_version_a_nivel_de_modulo() -> set:
    import ast

    halladas = set()
    for ruta in sorted((RAIZ / "tools").rglob("*.py")):
        relativa = ruta.relative_to(RAIZ)
        if _es_test_o_fixture(relativa.parts):
            continue
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in arbol.body:
            if isinstance(nodo, ast.Assign):
                nombres = [t.id for t in nodo.targets if isinstance(t, ast.Name)]
            elif isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
                nombres = [nodo.target.id]
            else:
                continue
            for nombre in nombres:
                if _RE_NOMBRE_VERSION.search(nombre):
                    halladas.add((relativa.as_posix(), nombre))
    return halladas


def test_toda_constante_de_version_esta_inventariada_o_excluida():
    inventariadas = set()
    for contrato in _contratos():
        if "version_ref" in contrato:
            modulo, _, constante = contrato["version_ref"].partition(":")
            inventariadas.add((modulo.replace(".", "/") + ".py", constante))
    sin_inventariar = sorted(h for h in _constantes_de_version_a_nivel_de_modulo() if h not in inventariadas and h not in EXCLUSIONES_VERSION)
    assert not sin_inventariar, f"constantes de versión sin entrada en el inventario ni exclusión con motivo: {sin_inventariar}"
    for clave, motivo in EXCLUSIONES_VERSION.items():
        assert motivo.strip(), clave
