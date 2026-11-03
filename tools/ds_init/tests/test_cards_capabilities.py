"""Tests de capabilities opt-in `data_cards`/`model_governance` (Change
`20261005-cards-governance-integration`, R1-R12 de `spec.md`, tarea T1).

Patrón de `test_cli.py`: repo Git temporal como destino; nunca escribe sobre
este repositorio."""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from tools.ds_init import manifest
from tools.ds_init.cli import main
from tools.ds_init.manifest import (
    CAPABILITIES_CONOCIDAS,
    CAPABILITIES_OPT_IN,
    CAPABILITIES_VALIDAS,
    EXCLUSIONES_PERMANENTES,
    MANIFEST,
    EntradaManifiesto,
    capabilities_efectivas_sync,
    filtrar_entradas_por_capabilities,
    manifest_para_perfil_stage_y_capabilities,
    validar_capabilities,
)

PERFIL = "python-jupyter-data"
COMPARTIDOS = ("__init__", "core", "assess", "resolvers", "approvals", "discovery", "report")
SOLO_DATA = ("datacard",)
SOLO_MODEL = ("modelcard", "govpolicy", "modelgov", "govconfig")
HIST = "predictive_modeling"


def _repo_temporal() -> Path:
    ruta = Path(tempfile.mkdtemp(prefix="ds_init_test_cards_caps_"))
    subprocess.run(["git", "init", str(ruta)], capture_output=True, text=True, check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.name", "Test"], check=True)
    (ruta / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    _commit(ruta, "inicial")
    return ruta


def _commit(repo: Path, mensaje: str = "commit de prueba") -> None:
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", mensaje], capture_output=True, text=True, check=True)


def _control(repo: Path) -> dict:
    return json.loads((repo / ".ds_init" / "control.json").read_text(encoding="utf-8"))


def _correr(argv: list):
    """Devuelve (codigo, stdout, stderr); SystemExit de argparse -> su código."""
    salida, error = io.StringIO(), io.StringIO()
    with redirect_stdout(salida), redirect_stderr(error):
        try:
            codigo = main(argv)
        except SystemExit as exc:
            codigo = exc.code
    return codigo, salida.getvalue(), error.getvalue()


def _rutas(control: dict) -> list:
    """Rutas (posix) de `control["archivos"]` (lista de dicts `{ruta, sha256}`)."""
    return [str(a["ruta"]).replace("\\", "/") for a in control["archivos"]]


def _snapshot(repo: Path) -> dict:
    return {
        str(p.relative_to(repo)): p.read_bytes()
        for p in repo.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(repo).parts
    }


def _entrada(**kw) -> EntradaManifiesto:
    return EntradaManifiesto(fuente="x", tratamiento=manifest.VERBATIM, destino=kw.pop("destino", "x"), **kw)


class TestVocabularioYHelpers(unittest.TestCase):
    def test_vocabulario(self):
        self.assertEqual(CAPABILITIES_CONOCIDAS, ("predictive_modeling",))
        self.assertEqual(CAPABILITIES_OPT_IN, ("data_cards", "model_governance"))
        self.assertEqual(CAPABILITIES_VALIDAS, CAPABILITIES_CONOCIDAS + CAPABILITIES_OPT_IN)

    def test_validar_capabilities(self):
        self.assertEqual(validar_capabilities({HIST, "model_governance"}), [])
        self.assertEqual(validar_capabilities({"data_cards"}), [])
        self.assertEqual(validar_capabilities(set()), [])
        errores = validar_capabilities({"model_governance"})
        self.assertEqual(len(errores), 1)
        self.assertIn("model_governance", errores[0])
        self.assertIn("predictive_modeling", errores[0])

    def test_filtro_cualquiera_de(self):
        libre = _entrada(destino="libre")
        estricta = _entrada(destino="estricta", capabilities=("a", "b"))
        cualquiera = _entrada(destino="cualquiera", capabilities_cualquiera=("a", "b"))
        todas = [libre, estricta, cualquiera]

        def destinos(caps):
            return [e.destino for e in filtrar_entradas_por_capabilities(todas, caps)]

        self.assertEqual(destinos(set()), ["libre"])
        self.assertEqual(destinos({"a"}), ["libre", "cualquiera"])
        self.assertEqual(destinos({"b"}), ["libre", "cualquiera"])
        self.assertEqual(destinos({"a", "b"}), ["libre", "estricta", "cualquiera"])
        self.assertEqual(destinos({"c"}), ["libre"])

    def test_default_de_campo_cualquiera_vacio(self):
        self.assertEqual(_entrada().capabilities_cualquiera, ())

    def test_capabilities_efectivas_sync(self):
        f = capabilities_efectivas_sync
        # (a) sin flags: histórica por default; opt-in = persistidas.
        self.assertEqual(f(None, None, None), frozenset({HIST}))
        self.assertEqual(f([], None, None), frozenset({HIST}))
        self.assertEqual(f([HIST, "data_cards"], None, None), frozenset({HIST, "data_cards"}))
        self.assertEqual(f(["data_cards"], None, [HIST]), frozenset({"data_cards"}))
        # (b) con flags y lista persistida: parte de lo persistido.
        self.assertEqual(f(["data_cards"], ["model_governance"], None), frozenset({"data_cards", "model_governance"}))
        self.assertEqual(f([HIST, "data_cards"], None, ["data_cards"]), frozenset({HIST}))
        # (c) legacy con flags: default histórico.
        self.assertEqual(f(None, ["data_cards"], None), frozenset({HIST, "data_cards"}))
        self.assertEqual(f(None, None, [HIST]), frozenset())
        # M1: nombres persistidos desconocidos no se descartan sin flags.
        self.assertEqual(f([HIST, "futura_x"], None, None), frozenset({HIST, "futura_x"}))
        self.assertEqual(f(["futura_x"], None, None), frozenset({HIST, "futura_x"}))
        self.assertEqual(f([HIST, "futura_x"], None, ["futura_x"]), frozenset({HIST}))


class TestEntradasManifiesto(unittest.TestCase):
    def _por_destino(self) -> dict:
        return {e.destino: e for e in MANIFEST if e.destino.startswith("tools/cards")}

    def test_entradas_compartidas(self):
        entradas = self._por_destino()
        for nombre in COMPARTIDOS:
            e = entradas[f"tools/cards/{nombre}.py"]
            self.assertEqual(e.capabilities_cualquiera, ("data_cards", "model_governance"))
            self.assertEqual(e.capabilities, ())

    def test_entradas_por_capability(self):
        entradas = self._por_destino()
        for nombre in SOLO_DATA:
            self.assertEqual(entradas[f"tools/cards/{nombre}.py"].capabilities, ("data_cards",))
        for nombre in SOLO_MODEL:
            self.assertEqual(entradas[f"tools/cards/{nombre}.py"].capabilities, ("model_governance",))

    def test_verbatim_discovery_fuente_igual_destino_sin_tests(self):
        entradas = self._por_destino()
        self.assertEqual(len(entradas), len(COMPARTIDOS) + len(SOLO_DATA) + len(SOLO_MODEL))
        for destino, e in entradas.items():
            self.assertEqual(e.tratamiento, manifest.VERBATIM)
            self.assertEqual(e.fuente, destino)
            self.assertEqual(e.stage_minimo, "discovery")
            self.assertNotIn("/tests/", destino)

    def test_ningun_destino_bajo_governance(self):
        self.assertEqual([e.destino for e in MANIFEST if e.destino.startswith("governance")], [])

    def test_governance_en_exclusiones_permanentes(self):
        self.assertIn("governance/", EXCLUSIONES_PERMANENTES)

    def test_tests_de_cards_no_se_distribuyen(self):
        for e in MANIFEST:
            self.assertFalse(e.destino.startswith("tools/cards/tests"))

    def test_filtro_del_manifiesto_real(self):
        def cards(caps):
            return {
                e.destino
                for e in manifest_para_perfil_stage_y_capabilities(PERFIL, "discovery", caps)
                if e.destino.startswith("tools/cards")
            }

        compartidos = {f"tools/cards/{n}.py" for n in COMPARTIDOS}
        datos = {f"tools/cards/{n}.py" for n in SOLO_DATA}
        modelo = {f"tools/cards/{n}.py" for n in SOLO_MODEL}
        self.assertEqual(cards({HIST}), set())
        self.assertEqual(cards(set()), set())
        self.assertEqual(cards({HIST, "data_cards"}), compartidos | datos)
        self.assertEqual(cards({HIST, "model_governance"}), compartidos | modelo)
        self.assertEqual(cards({HIST, "data_cards", "model_governance"}), compartidos | datos | modelo)

    @staticmethod
    def _dependencias(ruta: Path) -> list:
        """`(nombre_modulo, en_funcion)` de cada dependencia: imports estáticos
        (`import`/`from`) y por string literal (`_importar("x")`,
        `_importar_perezoso("x")`, `__import__("x")`, `importlib.import_module("x")`)."""
        import ast

        funciones_dinamicas = {"_importar", "_importar_perezoso", "__import__", "import_module"}
        encontradas = []

        def visitar(nodo, en_funcion):
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                en_funcion = True
            if isinstance(nodo, ast.ImportFrom):
                encontradas.append(((nodo.module or "").split(".")[-1], en_funcion))
                encontradas.extend((a.name, en_funcion) for a in nodo.names)
            elif isinstance(nodo, ast.Import):
                encontradas.extend((a.name.split(".")[-1], en_funcion) for a in nodo.names)
            elif isinstance(nodo, ast.Call):
                f = nodo.func
                nombre = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
                if nombre in funciones_dinamicas:
                    for arg in nodo.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            encontradas.append((arg.value.split(".")[-1], en_funcion))
            for hijo in ast.iter_child_nodes(nodo):
                visitar(hijo, en_funcion)

        visitar(ast.parse(ruta.read_text(encoding="utf-8")), False)
        return encontradas

    def test_los_12_modulos_existen_en_disco(self):
        raiz = manifest.raiz_repo_origen()
        for nombre in COMPARTIDOS + SOLO_DATA + SOLO_MODEL:
            self.assertTrue((raiz / "tools" / "cards" / f"{nombre}.py").is_file(), nombre)

    def test_grafo_de_imports_de_produccion_respeta_capabilities(self):
        """R8, en ambos sentidos y con imports por string. Sin saltear ausentes.
        - datacard no depende de módulos de model_governance (en ningún nivel).
        - modelcard/govpolicy/modelgov/govconfig no dependen de datacard.
        - compartidos: dependencias a módulos opt-in solo de forma PEREZOSA (dentro
          de funciones, condicionadas al kind); nunca a nivel de módulo."""
        raiz = manifest.raiz_repo_origen() / "tools" / "cards"
        solo_model, solo_data = set(SOLO_MODEL), set(SOLO_DATA)
        for nombre in SOLO_DATA:
            with self.subTest(modulo=nombre):
                deps = {n for n, _ in self._dependencias(raiz / f"{nombre}.py")}
                self.assertEqual(deps & solo_model, set())
        for nombre in SOLO_MODEL:
            with self.subTest(modulo=nombre):
                deps = {n for n, _ in self._dependencias(raiz / f"{nombre}.py")}
                self.assertEqual(deps & solo_data, set())
        for nombre in set(COMPARTIDOS) - {"__init__"}:
            with self.subTest(modulo=nombre):
                estaticas = {n for n, en_funcion in self._dependencias(raiz / f"{nombre}.py") if not en_funcion}
                self.assertEqual(estaticas & (solo_model | solo_data), set())

    def test_deteccion_de_imports_por_string(self):
        import tempfile as _tf

        with _tf.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "m.py"
            ruta.write_text(
                "import importlib\nx = _importar('cards.modelgov')\n"
                "def f():\n    __import__('datacard')\n    importlib.import_module('govpolicy')\n"
                "    _importar_perezoso('cards')\n",
                encoding="utf-8",
            )
            deps = self._dependencias(ruta)
        self.assertIn(("modelgov", False), deps)
        self.assertIn(("datacard", True), deps)
        self.assertIn(("govpolicy", True), deps)
        self.assertIn(("cards", True), deps)

    def test_instalacion_data_cards_only_importa_y_valida_proyecto_sin_cards(self):
        """Simula `data_cards` sin `model_governance`: copia SOLO los módulos
        provisionados (según el manifiesto) a un tmp e importa en un subproceso
        aislado compartidos + datacard + discovery + report, sin los módulos de
        model_governance; `validar_proyecto` sobre un repo sin cards no debe fallar."""
        import sys
        import textwrap

        origen = manifest.raiz_repo_origen()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            destinos = [
                e.destino
                for e in manifest_para_perfil_stage_y_capabilities(PERFIL, "discovery", {"data_cards"})
                if e.destino.startswith("tools/cards/")
            ]
            self.assertEqual(
                sorted(Path(d).stem for d in destinos), sorted(COMPARTIDOS + SOLO_DATA)
            )
            (tmp / "tools").mkdir()
            (tmp / "tools" / "__init__.py").write_text("", encoding="utf-8")
            (tmp / "tools" / "cards").mkdir()
            for destino in destinos:
                shutil.copy2(origen / destino, tmp / destino)
            for paquete in ("dsguard", "reporting"):
                shutil.copytree(
                    origen / "tools" / paquete,
                    tmp / "tools" / paquete,
                    ignore=shutil.ignore_patterns("tests", "__pycache__"),
                )
            for ausente in SOLO_MODEL:
                self.assertFalse((tmp / "tools" / "cards" / f"{ausente}.py").exists())
            repo_vacio = tmp / "proyecto"
            repo_vacio.mkdir()
            script = textwrap.dedent(
                f"""
                import sys
                sys.path[:0] = [{str(tmp)!r}, {str(tmp / "tools")!r}]
                import importlib
                for nombre in ("core", "assess", "resolvers", "datacard", "approvals", "discovery", "report"):
                    importlib.import_module("tools.cards." + nombre)
                from tools.cards import discovery
                from pathlib import Path
                resultado = discovery.validar_proyecto(Path({str(repo_vacio)!r}))
                assert resultado is not None
                for prohibido in ("modelcard", "govpolicy", "modelgov", "govconfig"):
                    assert "tools.cards." + prohibido not in sys.modules, prohibido
                print("OK")
                """
            )
            salida = subprocess.run(
                [sys.executable, "-I", "-c", script], capture_output=True, text=True, cwd=str(tmp)
            )
            self.assertEqual(salida.returncode, 0, salida.stdout + salida.stderr)
            self.assertIn("OK", salida.stdout)


class _CliBase(unittest.TestCase):
    def setUp(self):
        self.repo = _repo_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _install(self, *flags, stage="discovery", execute=True):
        argv = ["--destino", str(self.repo), "--nombre", "p", "--stage", stage, *flags]
        if execute:
            argv.append("--execute")
        return _correr(argv)

    def _sync(self, stage, *flags, execute=True):
        argv = ["sync", "--destino", str(self.repo), "--stage", stage, *flags]
        if execute:
            argv.append("--execute")
        return _correr(argv)

    def _cards_en_disco(self) -> set:
        d = self.repo / "tools" / "cards"
        return {p.name for p in d.glob("*.py")} if d.exists() else set()


class TestInstallCapabilities(_CliBase):
    def test_default_sin_flags_identico_a_v08(self):
        codigo, _, _ = self._install()
        self.assertEqual(codigo, 0)
        control = _control(self.repo)
        self.assertEqual(control["capabilities_habilitadas"], ["predictive_modeling"])
        self.assertFalse((self.repo / "tools" / "cards").exists())
        self.assertFalse((self.repo / "governance").exists())
        self.assertEqual([a["ruta"] for a in control["archivos"] if "cards" in a["ruta"].split("/")], [])
        self.assertTrue((self.repo / "tools" / "modelquality" / "__init__.py").exists())

    def test_baseline_independiente_de_archivos_en_install_default(self):
        """R2/I4: el esperado se calcula SIN el helper nuevo de filtro: manifiesto
        por stage menos tools/cards/ y entradas de capabilities opt-in."""
        self._install()
        opt_in = set(CAPABILITIES_OPT_IN)
        esperado = {
            e.destino.replace("\\", "/")
            for e in manifest.manifest_para_perfil_y_stage(PERFIL, "discovery")
            if not e.destino.replace("\\", "/").startswith("tools/cards/")
            and not (set(e.capabilities) & opt_in)
            and not (set(e.capabilities_cualquiera) & opt_in)
        }
        esperado.discard(".ds_init/control.json")
        real = {str(a["ruta"]).replace("\\", "/") for a in _control(self.repo)["archivos"]}
        real.discard(".ds_init/control.json")
        self.assertEqual(real, esperado)

    def test_plan_dry_run_default_igual_a_enable_historica_explicita(self):
        _, plan_default, _ = self._install(execute=False)
        _, plan_explicito, _ = self._install("--enable-capability", HIST, execute=False)
        self.assertEqual(plan_default, plan_explicito)
        self.assertNotIn("tools/cards", plan_default.replace("\\", "/"))

    def test_opt_in_data_cards_sin_predictive(self):
        codigo, _, _ = self._install("--enable-capability", "data_cards", "--disable-capability", HIST)
        self.assertEqual(codigo, 0)
        self.assertEqual(_control(self.repo)["capabilities_habilitadas"], ["data_cards"])
        self.assertFalse((self.repo / "tools" / "modelquality").exists())
        cards = self._cards_en_disco()
        self.assertIn("datacard.py", cards)
        self.assertNotIn("modelcard.py", cards)
        self.assertNotIn("modelgov.py", cards)
        self.assertFalse((self.repo / "tools" / "cards" / "tests").exists())

    def test_model_governance_con_predictive(self):
        codigo, _, _ = self._install("--enable-capability", "model_governance")
        self.assertEqual(codigo, 0)
        self.assertEqual(_control(self.repo)["capabilities_habilitadas"], sorted([HIST, "model_governance"]))
        cards = self._cards_en_disco()
        self.assertIn("modelgov.py", cards)
        self.assertIn("core.py", cards)
        self.assertNotIn("datacard.py", cards)

    def test_ambas_no_crea_governance(self):
        codigo, _, _ = self._install("--enable-capability", "data_cards", "--enable-capability", "model_governance")
        self.assertEqual(codigo, 0)
        self.assertFalse((self.repo / "governance").exists())

    def test_model_governance_sin_predictive_rechazado_sin_escribir(self):
        antes = _snapshot(self.repo)
        for flags in (
            ["--enable-capability", "model_governance", "--disable-capability", HIST],
            ["--enable-capability", "model_governance", "--enable-capability", "data_cards", "--disable-capability", HIST],
        ):
            with self.subTest(flags=flags):
                codigo, _, err = self._install(*flags)
                self.assertEqual(codigo, 2)
                self.assertIn("model_governance", err)
                self.assertIn("predictive_modeling", err)
                self.assertEqual(_snapshot(self.repo), antes)

    def test_flag_en_enable_y_disable_a_la_vez_es_error_de_uso(self):
        codigo, _, _ = self._install("--enable-capability", "data_cards", "--disable-capability", "data_cards")
        self.assertEqual(codigo, 2)

    def test_choices_invalidos(self):
        self.assertEqual(self._install("--enable-capability", "nope")[0], 2)
        self.assertEqual(self._install("--disable-capability", "nope")[0], 2)


class TestSyncCapabilities(_CliBase):
    def test_enable_later_en_el_mismo_stage(self):
        self._install()
        _commit(self.repo)
        codigo, out, _ = self._sync("discovery", "--enable-capability", "data_cards")
        self.assertEqual(codigo, 0)
        self.assertNotIn("nada que hacer", out)
        self.assertEqual(_control(self.repo)["capabilities_habilitadas"], sorted([HIST, "data_cards"]))
        self.assertIn("datacard.py", self._cards_en_disco())
        self.assertEqual(_control(self.repo)["installation_stage"], "discovery")
        self.assertFalse((self.repo / "governance").exists())

    def test_mismo_stage_sin_flags_nada_que_hacer(self):
        self._install()
        _commit(self.repo)
        antes = _snapshot(self.repo)
        codigo, out, _ = self._sync("discovery")
        self.assertEqual(codigo, 0)
        self.assertIn("nada que hacer", out)
        self.assertEqual(_snapshot(self.repo), antes)

    def test_mismo_stage_flag_que_no_cambia_el_set_nada_que_hacer(self):
        self._install("--enable-capability", "data_cards")
        _commit(self.repo)
        codigo, out, _ = self._sync("discovery", "--enable-capability", "data_cards")
        self.assertEqual(codigo, 0)
        self.assertIn("nada que hacer", out)

    def test_stage_menor_con_flags_nada_que_hacer(self):
        self._install(stage="experiment")
        _commit(self.repo)
        antes = _snapshot(self.repo)
        codigo, out, _ = self._sync("discovery", "--enable-capability", "data_cards")
        self.assertEqual(codigo, 0)
        self.assertIn("nada que hacer", out)
        self.assertEqual(_snapshot(self.repo), antes)

    def test_model_governance_en_sync_con_predictive_ok(self):
        self._install()
        _commit(self.repo)
        codigo, _, _ = self._sync("discovery", "--enable-capability", "model_governance")
        self.assertEqual(codigo, 0)
        self.assertIn("modelgov.py", self._cards_en_disco())

    def test_caso_critico_predictive_deshabilitada_y_model_governance_rechazado(self):
        self._install("--disable-capability", HIST)
        _commit(self.repo)
        antes = _snapshot(self.repo)
        codigo, _, err = self._sync("discovery", "--enable-capability", "model_governance")
        self.assertEqual(codigo, 2)
        self.assertIn("model_governance", err)
        self.assertIn("predictive_modeling", err)
        self.assertIn("--enable-capability predictive_modeling", err)
        self.assertEqual(_snapshot(self.repo), antes)
        self.assertFalse((self.repo / "tools" / "modelquality").exists())

    def test_caso_critico_habilitando_ambas_ok(self):
        self._install("--disable-capability", HIST)
        _commit(self.repo)
        codigo, _, _ = self._sync(
            "discovery", "--enable-capability", HIST, "--enable-capability", "model_governance"
        )
        self.assertEqual(codigo, 0)
        self.assertEqual(_control(self.repo)["capabilities_habilitadas"], sorted([HIST, "model_governance"]))
        self.assertTrue((self.repo / "tools" / "modelquality" / "__init__.py").exists())
        self.assertIn("modelgov.py", self._cards_en_disco())

    def test_caso_critico_data_cards_no_rehabilita_predictive(self):
        self._install("--disable-capability", HIST)
        _commit(self.repo)
        codigo, _, _ = self._sync("discovery", "--enable-capability", "data_cards")
        self.assertEqual(codigo, 0)
        self.assertEqual(_control(self.repo)["capabilities_habilitadas"], ["data_cards"])
        self.assertFalse((self.repo / "tools" / "modelquality").exists())

    def test_opt_in_persistida_se_preserva_con_flags_de_otra_capability(self):
        self._install("--enable-capability", "data_cards")
        _commit(self.repo)
        codigo, _, _ = self._sync("discovery", "--enable-capability", "model_governance")
        self.assertEqual(codigo, 0)
        self.assertEqual(
            _control(self.repo)["capabilities_habilitadas"],
            sorted([HIST, "data_cards", "model_governance"]),
        )

    def test_opt_in_persistida_se_preserva_en_sync_de_stage_superior_sin_flags(self):
        self._install("--enable-capability", "data_cards")
        _commit(self.repo)
        codigo, _, _ = self._sync("experiment")
        self.assertEqual(codigo, 0)
        self.assertEqual(_control(self.repo)["capabilities_habilitadas"], sorted([HIST, "data_cards"]))
        self.assertIn("datacard.py", self._cards_en_disco())

    def test_sync_sin_flags_historica_deshabilitada_se_reprovisiona_como_v08(self):
        self._install("--disable-capability", HIST)
        _commit(self.repo)
        codigo, _, _ = self._sync("experiment")
        self.assertEqual(codigo, 0)
        self.assertEqual(_control(self.repo)["capabilities_habilitadas"], [HIST])
        self.assertTrue((self.repo / "tools" / "modelquality" / "__init__.py").exists())

    def test_disable_no_borra_archivos(self):
        self._install("--enable-capability", "data_cards")
        _commit(self.repo)
        antes = {k: v for k, v in _snapshot(self.repo).items() if k.replace("\\", "/").startswith("tools/cards/")}
        self.assertTrue(antes)
        codigo, _, _ = self._sync("discovery", "--disable-capability", "data_cards")
        self.assertEqual(codigo, 0)
        control = _control(self.repo)
        self.assertEqual(control["capabilities_habilitadas"], [HIST])
        self.assertEqual([a["ruta"] for a in control["archivos"] if a["ruta"].replace("\\", "/").startswith("tools/cards/")], [])
        despues = _snapshot(self.repo)
        for clave, contenido in antes.items():
            self.assertEqual(despues.get(clave), contenido)

    def test_legacy_sin_lista(self):
        self._install()
        ruta = self.repo / ".ds_init" / "control.json"
        control = json.loads(ruta.read_text(encoding="utf-8"))
        del control["capabilities_habilitadas"]
        ruta.write_text(json.dumps(control, indent=2), encoding="utf-8")
        _commit(self.repo)
        # sin flags: nada que hacer (mismo stage), las opt-in siguen deshabilitadas
        codigo, out, _ = self._sync("discovery")
        self.assertEqual(codigo, 0)
        self.assertIn("nada que hacer", out)
        self.assertFalse((self.repo / "tools" / "cards").exists())
        # con flag: parte del default histórico
        codigo, _, _ = self._sync("discovery", "--enable-capability", "data_cards")
        self.assertEqual(codigo, 0)
        self.assertEqual(_control(self.repo)["capabilities_habilitadas"], sorted([HIST, "data_cards"]))


class TestSyncRevisionCiclo1(_CliBase):
    def _editar_capabilities_persistidas(self, lista) -> None:
        ruta = self.repo / ".ds_init" / "control.json"
        control = json.loads(ruta.read_text(encoding="utf-8"))
        control["capabilities_habilitadas"] = lista
        ruta.write_text(json.dumps(control, indent=2), encoding="utf-8")
        _commit(self.repo, "edicion manual de capabilities")

    def test_enable_model_governance_con_disable_predictive_rechazado(self):
        self._install()
        _commit(self.repo)
        antes = _snapshot(self.repo)
        codigo, _, err = self._sync(
            "discovery", "--enable-capability", "model_governance", "--disable-capability", HIST
        )
        self.assertEqual(codigo, 2)
        self.assertIn("model_governance", err)
        self.assertEqual(_snapshot(self.repo), antes)

    def test_disable_predictive_sobre_persistido_con_model_governance_rechazado_sin_sugerir_enable(self):
        self._install("--enable-capability", "model_governance")
        _commit(self.repo)
        antes = _snapshot(self.repo)
        codigo, _, err = self._sync("discovery", "--disable-capability", HIST)
        self.assertEqual(codigo, 2)
        self.assertIn("predictive_modeling", err)
        # M3: la causa es un disable explícito; no se sugiere re-habilitarla.
        self.assertNotIn("--enable-capability predictive_modeling", err)
        self.assertEqual(_snapshot(self.repo), antes)

    def test_m2_persistido_invalido_rechazado_con_y_sin_flags(self):
        self._install("--enable-capability", "data_cards")
        self._editar_capabilities_persistidas(["model_governance"])
        antes = _snapshot(self.repo)
        for flags, stage in (([], "discovery"), ([], "experiment"), (["--enable-capability", "data_cards"], "discovery")):
            with self.subTest(flags=flags, stage=stage):
                codigo, _, err = self._sync(stage, *flags)
                self.assertEqual(codigo, 2)
                self.assertIn("control.json persistido inválido", err)
                self.assertEqual(_snapshot(self.repo), antes)

    def test_m1_nombre_persistido_desconocido_no_se_descarta_sin_flags(self):
        self._install()
        self._editar_capabilities_persistidas([HIST, "futura_x"])
        codigo, _, _ = self._sync("experiment")
        self.assertEqual(codigo, 0)
        self.assertEqual(_control(self.repo)["capabilities_habilitadas"], sorted([HIST, "futura_x"]))

    def test_m4_aviso_de_flags_ignorados_con_stage_menor(self):
        self._install(stage="experiment")
        _commit(self.repo)
        codigo, out, _ = self._sync("discovery", "--enable-capability", "data_cards")
        self.assertEqual(codigo, 0)
        self.assertIn("los flags de capability se ignoraron", out)
        self.assertNotIn("data_cards", _control(self.repo)["capabilities_habilitadas"])

    def test_m4_aviso_con_mismo_stage_sin_cambio_y_sin_aviso_sin_flags(self):
        self._install()
        _commit(self.repo)
        _, out, _ = self._sync("discovery", "--enable-capability", HIST)
        self.assertIn("los flags de capability se ignoraron", out)
        _, out, _ = self._sync("discovery")
        self.assertNotIn("los flags de capability se ignoraron", out)

    def test_legacy_mismo_stage_con_disable_procede(self):
        self._install()
        ruta = self.repo / ".ds_init" / "control.json"
        control = json.loads(ruta.read_text(encoding="utf-8"))
        del control["capabilities_habilitadas"]
        ruta.write_text(json.dumps(control, indent=2), encoding="utf-8")
        _commit(self.repo)
        codigo, out, _ = self._sync("discovery", "--disable-capability", HIST)
        self.assertEqual(codigo, 0)
        self.assertNotIn("nada que hacer", out)
        self.assertEqual(_control(self.repo)["capabilities_habilitadas"], [])


class TestGovernanceExcluido(_CliBase):
    def test_install_con_todo_nunca_crea_governance(self):
        self._install("--enable-capability", "data_cards", "--enable-capability", "model_governance")
        _commit(self.repo)
        self._sync("experiment")
        self.assertFalse((self.repo / "governance").exists())
        self.assertEqual([a["ruta"] for a in _control(self.repo)["archivos"] if a["ruta"].startswith("governance")], [])


if __name__ == "__main__":
    unittest.main()
