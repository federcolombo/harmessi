"""Tests de `sync` conservador (M-A, R27-R28b, R43b de
`20261008-cross-platform-managed-hashing`): `sync` reconcilia contra el
baseline ANTERIOR, nunca adopta drift preexistente, y `migrate-hashes` migra
solo entradas legacy que verifican. Usa repositorios Git temporales propios
(nunca este repositorio) y bytes explícitos (sin depender de `core.autocrlf`)."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.ds_init import control as control_mod
from tools.ds_init import managed_hash, writer
from tools.ds_init.cli import main
from tools.ds_init.manifest import manifest_para_perfil_y_stage, raiz_repo_origen

PERFIL = "python-jupyter-data"
RUTA_ASSET = "tools/ds_guard.py"  # VERBATIM de texto, presente desde 'discovery'
RUTA_ASSET_EXPERIMENT = ".claude/agents/metodologo.md"  # solo desde 'experiment'


def _crear_repo_git_temporal() -> Path:
    ruta = Path(tempfile.mkdtemp(prefix="ds_init_test_sync_baseline_"))
    subprocess.run(["git", "init", str(ruta)], capture_output=True, text=True, check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.name", "Test"], check=True)
    (ruta / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    _commit_todo(ruta, "inicial")
    return ruta


def _commit_todo(repo: Path, mensaje: str) -> None:
    # `sync --execute` exige working tree limpio (preflight).
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", mensaje], check=True, capture_output=True, text=True)


def _ruta_control(repo: Path) -> Path:
    return repo / control_mod.DIR_CONTROL / control_mod.NOMBRE_ARCHIVO_CONTROL


def _leer_control(repo: Path) -> dict:
    return json.loads(_ruta_control(repo).read_text(encoding="utf-8"))


def _entradas_por_ruta(control: dict) -> dict:
    return {e["ruta"]: e for e in control["archivos"]}


def _a_lf(datos: bytes) -> bytes:
    return datos.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _a_crlf(datos: bytes) -> bytes:
    return _a_lf(datos).replace(b"\n", b"\r\n")


def _hacer_legacy(repo: Path) -> None:
    """Reescribe control.json en forma legacy: sin `hash_alg`, `sha256` = hash
    de los bytes crudos actuales de cada archivo."""
    control = _leer_control(repo)
    for entrada in control["archivos"]:
        entrada.pop("hash_alg", None)
        entrada["sha256"] = hashlib.sha256((repo / entrada["ruta"]).read_bytes()).hexdigest()
    _ruta_control(repo).write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8", newline="")


def _correr(argv: list):
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(io.StringIO()):
        codigo = main(argv)
    return codigo, salida.getvalue()


class _RaizFalsa:
    """Raíz de origen que redirige solo algunas fuentes a archivos temporales;
    el resto se resuelve contra la raíz real."""

    def __init__(self, reales: Path, reemplazos: dict):
        self._reales = reales
        self._reemplazos = reemplazos

    def __truediv__(self, rel):
        clave = str(rel).replace("\\", "/")
        if clave in self._reemplazos:
            return self._reemplazos[clave]
        return self._reales / rel


class _BaseSync(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        codigo, _ = _correr(
            ["--destino", str(self.repo), "--nombre", "proyecto-de-prueba", "--stage", "discovery", "--execute"]
        )
        self.assertEqual(codigo, 0)
        _commit_todo(self.repo, "instalar discovery")
        self.control_inicial = _leer_control(self.repo)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _sync_experiment(self):
        return _correr(["sync", "--destino", str(self.repo), "--stage", "experiment", "--execute"])


class TestSyncConservador(_BaseSync):
    def test_pristine_sin_cambios_conserva_baseline_y_verifica_ok(self):
        codigo, salida = self._sync_experiment()
        self.assertEqual(codigo, 0)
        self.assertNotIn("DRIFT preservado", salida)

        control = _leer_control(self.repo)
        por_ruta = _entradas_por_ruta(control)
        for ruta in _entradas_por_ruta(self.control_inicial):
            self.assertIn(ruta, por_ruta)
            estado, _ = managed_hash.verificar_entrada(self.repo / ruta, por_ruta[ruta])
            self.assertEqual(estado, managed_hash.ESTADO_OK, ruta)

    def test_archivo_modificado_por_el_usuario_no_se_rebaselinea(self):
        ruta_abs = self.repo / RUTA_ASSET
        contenido_usuario = ruta_abs.read_bytes() + b"\n# cambio local del usuario\n"
        ruta_abs.write_bytes(contenido_usuario)
        _commit_todo(self.repo, "modificacion del usuario")
        entrada_previa = _entradas_por_ruta(self.control_inicial)[RUTA_ASSET]

        codigo, salida = self._sync_experiment()

        self.assertEqual(codigo, 0)  # el drift no cambia el código de salida
        self.assertEqual(ruta_abs.read_bytes(), contenido_usuario)
        self.assertIn(f"DRIFT preservado: {RUTA_ASSET}", salida)
        entrada_nueva = _entradas_por_ruta(_leer_control(self.repo))[RUTA_ASSET]
        self.assertEqual(entrada_nueva, entrada_previa)
        estado, _ = managed_hash.verificar_entrada(ruta_abs, entrada_nueva)
        self.assertEqual(estado, managed_hash.ESTADO_DRIFT)

    def test_control_json_conserva_las_entradas_previas(self):
        self._sync_experiment()
        rutas_previas = set(_entradas_por_ruta(self.control_inicial))
        rutas_nuevas = set(_entradas_por_ruta(_leer_control(self.repo)))
        self.assertTrue(rutas_previas.issubset(rutas_nuevas))
        self.assertGreater(len(rutas_nuevas), len(rutas_previas))

    def test_pristine_con_nueva_version_distribuida_se_actualiza(self):
        entrada_manifest = next(
            e for e in manifest_para_perfil_y_stage(PERFIL, "discovery") if e.destino == RUTA_ASSET
        )
        fuente_real = raiz_repo_origen() / entrada_manifest.fuente
        nuevo = fuente_real.read_bytes() + b"\n# version nueva distribuida\n"
        tmp = Path(tempfile.mkdtemp(prefix="ds_init_test_fuente_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        fuente_falsa = tmp / "ds_guard_nuevo.py"
        fuente_falsa.write_bytes(nuevo)
        raiz_falsa = _RaizFalsa(raiz_repo_origen(), {str(entrada_manifest.fuente).replace("\\", "/"): fuente_falsa})
        hash_previo = _entradas_por_ruta(self.control_inicial)[RUTA_ASSET]["sha256"]

        with mock.patch.object(writer, "raiz_repo_origen", lambda: raiz_falsa):
            codigo, salida = self._sync_experiment()

        self.assertEqual(codigo, 0)
        self.assertEqual((self.repo / RUTA_ASSET).read_bytes(), nuevo)
        self.assertIn(RUTA_ASSET, salida)
        entrada = _entradas_por_ruta(_leer_control(self.repo))[RUTA_ASSET]
        self.assertNotEqual(entrada["sha256"], hash_previo)
        self.assertEqual(
            entrada["sha256"], managed_hash.hash_managed_file(fuente_falsa, entrada["hash_alg"])
        )
        estado, _ = managed_hash.verificar_entrada(self.repo / RUTA_ASSET, entrada)
        self.assertEqual(estado, managed_hash.ESTADO_OK)

    def test_legacy_con_checkout_crlf_migra_sin_drift(self):
        ruta_abs = self.repo / RUTA_ASSET
        base_lf = _a_lf(ruta_abs.read_bytes())
        ruta_abs.write_bytes(base_lf)
        _hacer_legacy(self.repo)  # baseline legacy sobre bytes LF
        ruta_abs.write_bytes(_a_crlf(base_lf))  # checkout CRLF equivalente
        _commit_todo(self.repo, "legacy + checkout crlf")

        codigo, salida = self._sync_experiment()

        self.assertEqual(codigo, 0)
        self.assertNotIn("DRIFT preservado", salida)
        entrada = _entradas_por_ruta(_leer_control(self.repo))[RUTA_ASSET]
        self.assertIn("hash_alg", entrada)
        estado, _ = managed_hash.verificar_entrada(ruta_abs, entrada)
        self.assertEqual(estado, managed_hash.ESTADO_OK)

    def test_existente_sin_entrada_previa_no_se_adopta(self):
        ruta_abs = self.repo / RUTA_ASSET_EXPERIMENT
        ruta_abs.parent.mkdir(parents=True, exist_ok=True)
        contenido_usuario = b"# archivo propio del usuario, distinto del distribuido\n"
        ruta_abs.write_bytes(contenido_usuario)
        _commit_todo(self.repo, "archivo propio")
        self.assertNotIn(RUTA_ASSET_EXPERIMENT, _entradas_por_ruta(self.control_inicial))

        codigo, _ = self._sync_experiment()

        self.assertEqual(codigo, 0)
        self.assertEqual(ruta_abs.read_bytes(), contenido_usuario)
        self.assertNotIn(RUTA_ASSET_EXPERIMENT, _entradas_por_ruta(_leer_control(self.repo)))


RUTA_SETTINGS = ".claude/settings.json"


def _verbatim_solo_experiment(cantidad: int) -> list:
    """Entradas VERBATIM de texto que aparecen recién en 'experiment'."""
    from tools.ds_init.manifest import VERBATIM

    en_discovery = {e.destino for e in manifest_para_perfil_y_stage(PERFIL, "discovery")}
    candidatas = [
        e
        for e in manifest_para_perfil_y_stage(PERFIL, "experiment")
        if e.tratamiento == VERBATIM and e.destino not in en_discovery
    ]
    return candidatas[:cantidad]


class TestSyncFixesCiclo1(_BaseSync):
    def test_settings_con_drift_y_regenerar_control_fallido_conserva_entrada_previa(self):
        ruta_abs = self.repo / RUTA_SETTINGS
        datos = json.loads(ruta_abs.read_text(encoding="utf-8"))
        datos["clave_propia_del_usuario"] = {"valor": 1}
        ruta_abs.write_text(json.dumps(datos, indent=2) + "\n", encoding="utf-8", newline="")
        _commit_todo(self.repo, "settings del usuario")
        entrada_previa = _entradas_por_ruta(self.control_inicial)[RUTA_SETTINGS]

        with mock.patch.object(control_mod, "regenerar_control", side_effect=RuntimeError("falla simulada")):
            codigo, _ = self._sync_experiment()

        self.assertEqual(codigo, 1)
        entrada = _entradas_por_ruta(_leer_control(self.repo))[RUTA_SETTINGS]
        self.assertEqual(entrada, entrada_previa)

    def test_settings_sin_baseline_y_regenerar_control_fallido_no_aparece_en_control(self):
        ruta_abs = self.repo / RUTA_SETTINGS
        datos = json.loads(ruta_abs.read_text(encoding="utf-8"))
        datos["clave_propia_del_usuario"] = {"valor": 1}
        ruta_abs.write_text(json.dumps(datos, indent=2) + "\n", encoding="utf-8", newline="")
        control = _leer_control(self.repo)
        control["archivos"] = [e for e in control["archivos"] if e["ruta"] != RUTA_SETTINGS]
        _ruta_control(self.repo).write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8", newline="")
        _commit_todo(self.repo, "settings sin baseline")

        with mock.patch.object(control_mod, "regenerar_control", side_effect=RuntimeError("falla simulada")):
            codigo, salida = self._sync_experiment()

        self.assertEqual(codigo, 1)
        self.assertNotIn(RUTA_SETTINGS, _entradas_por_ruta(_leer_control(self.repo)))
        self.assertNotIn(f"DRIFT preservado: {RUTA_SETTINGS}", salida)

    def test_sync_con_drift_y_sin_cambios_conserva_entrada_del_drift(self):
        ruta_abs = self.repo / RUTA_ASSET
        ruta_abs.write_bytes(ruta_abs.read_bytes() + b"\n# cambio local\n")
        _commit_todo(self.repo, "drift")
        previas = _entradas_por_ruta(self.control_inicial)

        codigo, salida = self._sync_experiment()

        self.assertEqual(codigo, 0)
        self.assertIn("Sin cambios", salida)
        nuevas = _entradas_por_ruta(_leer_control(self.repo))
        self.assertEqual(nuevas[RUTA_ASSET], previas[RUTA_ASSET])
        otra = next(r for r in previas if r != RUTA_ASSET and r != RUTA_SETTINGS)
        estado, _ = managed_hash.verificar_entrada(self.repo / otra, nuevas[otra])
        self.assertEqual(estado, managed_hash.ESTADO_OK)

    def test_existente_sin_entrada_identico_se_registra_y_distinto_no(self):
        identica, distinta = _verbatim_solo_experiment(2)
        ruta_identica = self.repo / identica.destino
        ruta_distinta = self.repo / distinta.destino
        ruta_identica.parent.mkdir(parents=True, exist_ok=True)
        ruta_distinta.parent.mkdir(parents=True, exist_ok=True)
        ruta_identica.write_bytes(_a_crlf((raiz_repo_origen() / identica.fuente).read_bytes()))
        contenido_usuario = b"# contenido propio distinto del distribuido\n"
        ruta_distinta.write_bytes(contenido_usuario)
        _commit_todo(self.repo, "preexistentes sin baseline")

        codigo, _ = self._sync_experiment()

        self.assertEqual(codigo, 0)
        por_ruta = _entradas_por_ruta(_leer_control(self.repo))
        self.assertIn(identica.destino, por_ruta)
        estado, _ = managed_hash.verificar_entrada(ruta_identica, por_ruta[identica.destino])
        self.assertEqual(estado, managed_hash.ESTADO_OK)
        self.assertEqual(ruta_distinta.read_bytes(), contenido_usuario)
        self.assertNotIn(distinta.destino, por_ruta)

    def test_settings_existente_sin_baseline_no_se_adopta(self):
        # Se quita la entrada de settings.json del baseline: existe pero sin entrada.
        control = _leer_control(self.repo)
        control["archivos"] = [e for e in control["archivos"] if e["ruta"] != RUTA_SETTINGS]
        _ruta_control(self.repo).write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8", newline="")
        _commit_todo(self.repo, "settings sin baseline")

        codigo, _ = self._sync_experiment()

        self.assertEqual(codigo, 0)
        self.assertNotIn(RUTA_SETTINGS, _entradas_por_ruta(_leer_control(self.repo)))


class TestMigrateHashes(_BaseSync):
    def test_dry_run_no_escribe_y_execute_migra_de_forma_idempotente(self):
        _hacer_legacy(self.repo)
        bytes_legacy = _ruta_control(self.repo).read_bytes()

        codigo, salida = _correr(["migrate-hashes", "--destino", str(self.repo)])
        self.assertEqual(codigo, 0)
        self.assertIn("DRY-RUN", salida)
        self.assertEqual(_ruta_control(self.repo).read_bytes(), bytes_legacy)

        codigo, _ = _correr(["migrate-hashes", "--destino", str(self.repo), "--execute"])
        self.assertEqual(codigo, 0)
        control = _leer_control(self.repo)
        for entrada in control["archivos"]:
            self.assertIn("hash_alg", entrada)
            estado, _ = managed_hash.verificar_entrada(self.repo / entrada["ruta"], entrada)
            self.assertEqual(estado, managed_hash.ESTADO_OK, entrada["ruta"])

        bytes_migrado = _ruta_control(self.repo).read_bytes()
        codigo, _ = _correr(["migrate-hashes", "--destino", str(self.repo), "--execute"])
        self.assertEqual(codigo, 0)
        self.assertEqual(_ruta_control(self.repo).read_bytes(), bytes_migrado)

    def test_execute_no_migra_entradas_con_drift(self):
        ruta_abs = self.repo / RUTA_ASSET
        base = ruta_abs.read_bytes()
        _hacer_legacy(self.repo)
        ruta_abs.write_bytes(base + b"\n# modificacion real\n")

        codigo, _ = _correr(["migrate-hashes", "--destino", str(self.repo), "--execute"])

        self.assertEqual(codigo, 0)
        por_ruta = _entradas_por_ruta(_leer_control(self.repo))
        self.assertNotIn("hash_alg", por_ruta[RUTA_ASSET])
        self.assertEqual(por_ruta[RUTA_ASSET]["sha256"], hashlib.sha256(base).hexdigest())
        estado, _ = managed_hash.verificar_entrada(ruta_abs, por_ruta[RUTA_ASSET])
        self.assertEqual(estado, managed_hash.ESTADO_DRIFT)


if __name__ == "__main__":
    unittest.main()
