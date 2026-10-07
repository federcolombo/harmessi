"""Tests de `ds_guard exec approve {pytest,script,notebook}`
(`20261002-exec-approval-registration`, R1-R20).

Todo vía subprocess del CLI real en repos git temporales. Las aprobaciones
se registran SIEMPRE con el CLI; la única excepción es el test de
compatibilidad histórica de la aprobación legacy de script
(`sha256/lf/v1`), que inserta esa entrada a mano a propósito (R9b)."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_ds_guard_exec import (  # noqa: E402
    INTERPRETER,
    _GUARDRAILS_AUTONOMOUS,
    _GUARDRAILS_SUPERVISED,
    _BaseRepoGit,
    _crear_repo_git_temporal,
    _correr_ds_guard,
    _escribir_guardrails,
    _escribir_script_ok,
    _scaffold_change,
    core,
)
from leadrun import core as leadrun_core  # noqa: E402

CLAVES_ENTRADA = {
    "artefacto", "algoritmo", "hash", "registrado_utc",
    "usuario", "fecha_declarada", "alcance_aprobado", "cita",
}
ALGO_V2 = "sha256/script-content+argv/v2"
TEST_A = "tests/test_trivial.py"
TEST_B = "tests/test_otro.py"
SCRIPT = "scripts/ok_script.py"
OTRO_CHANGE = "20261002-otro-change"


class _BaseApprove(_BaseRepoGit):
    SCRIPT_RELATIVO = SCRIPT

    def setUp(self):
        self.repo = _crear_repo_git_temporal(prefix="cli_exec_approve_")
        _escribir_script_ok(self.repo, SCRIPT)
        for rel in (TEST_A, TEST_B):
            ruta = self.repo / rel
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        _escribir_script_ok(self.repo, "otros/fuera.py")
        (self.repo / "scripts" / "run.sh").write_text("echo hola\n", encoding="utf-8")
        self.change_dir = self._crear_change(self.CHANGE_ID)
        self.control_path = self.change_dir / "control.json"
        self._crear_change(OTRO_CHANGE)

    def _crear_change(self, change_id: str) -> Path:
        change_dir = _scaffold_change(self.repo, change_id, SCRIPT)
        ruta = change_dir / "control.json"
        control = json.loads(ruta.read_text(encoding="utf-8"))
        control["alcance"]["rutas_autorizadas"] = ["scripts", "tests"]
        core.escribir_control(ruta, control)
        return change_dir

    # --- helpers de CLI ---------------------------------------------------
    def _meta(self, usuario="federico"):
        return ["--usuario", usuario, "--fecha", "2026-10-02", "--alcance", "alcance de prueba", "--cita", "n/a"]

    def ap_pytest(self, paths=(TEST_A,), flags=(), change=None, interp=INTERPRETER, usuario="federico"):
        args = ["exec", "approve", "pytest", "--change-id", change or self.CHANGE_ID,
                "--interpreter", interp, *self._meta(usuario), "--paths", *paths]
        if flags:
            args += ["--", *flags]
        return _correr_ds_guard(args, self.repo)

    def ex_pytest(self, paths=(TEST_A,), flags=(), change=None):
        args = ["exec", "pytest", "--change-id", change or self.CHANGE_ID,
                "--interpreter", INTERPRETER, "--json", "--paths", *paths]
        if flags:
            args += ["--", *flags]
        return _correr_ds_guard(args, self.repo)

    def ap_script(self, script=SCRIPT, sargs=(), usuario="federico"):
        args = ["exec", "approve", "script", "--change-id", self.CHANGE_ID,
                "--interpreter", INTERPRETER, *self._meta(usuario), "--script", script]
        if sargs:
            args += ["--", *sargs]
        return _correr_ds_guard(args, self.repo)

    def ex_script(self, script=SCRIPT, sargs=()):
        args = ["exec", "script", "--change-id", self.CHANGE_ID,
                "--interpreter", INTERPRETER, "--json", "--script", script]
        if sargs:
            args += ["--", *sargs]
        return _correr_ds_guard(args, self.repo)

    def ap_notebook(self, manifest):
        return _correr_ds_guard(
            ["exec", "approve", "notebook", "--change-id", self.CHANGE_ID, "--interpreter", INTERPRETER,
             *self._meta(), "--manifest", manifest, "--execute"], self.repo)

    def ex_notebook(self, manifest):
        return _correr_ds_guard(
            ["exec", "notebook", "--change-id", self.CHANGE_ID, "--interpreter", INTERPRETER,
             "--manifest", manifest, "--execute", "--json"], self.repo)

    def aprobaciones(self, change_dir=None):
        ruta = (change_dir or self.change_dir) / "control.json"
        return json.loads(ruta.read_text(encoding="utf-8"))["aprobaciones"]

    def records(self):
        d = self.repo / ".harmessi" / "executions"
        if not d.exists():
            return []
        return [json.loads((p / "record.json").read_text(encoding="utf-8")) for p in d.iterdir()]


class TestPytestSupervised(_BaseApprove):
    def setUp(self):
        super().setUp()
        _escribir_guardrails(self.repo, _GUARDRAILS_SUPERVISED)

    # (1)
    def test_sin_aprobacion_bloqueado(self):
        r = self.ex_pytest()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("aprobación ausente", r.stderr)
        self.assertEqual(self.records(), [])

    # (2) + (16 paridad registrada == exigida) + (12)
    def test_approve_crea_entrada_con_semantica_pytest(self):
        r = self.ap_pytest(flags=("-q",))
        self.assertEqual(r.returncode, 0, r.stderr)
        ap = self.aprobaciones()
        self.assertEqual(len(ap), 1)
        e = ap[0]
        self.assertEqual(set(e), CLAVES_ENTRADA)
        self.assertEqual(e["artefacto"], "pytest:" + TEST_A)
        self.assertEqual(e["algoritmo"], "sha256/argv-canonical-json")
        self.assertEqual(e["hash"], leadrun_core.content_sha256([INTERPRETER, "-m", "pytest", TEST_A, "-q"]))
        self.assertEqual(
            (e["usuario"], e["fecha_declarada"], e["alcance_aprobado"], e["cita"]),
            ("federico", "2026-10-02", "alcance de prueba", "n/a"),
        )
        self.assertIn(e["hash"], r.stdout)
        self.assertIn("sha256/argv-canonical-json", r.stdout)

    # (3) + (13)
    def test_exec_exacto_permitido_y_record_creado(self):
        self.assertEqual(self.ap_pytest(flags=("-q",)).returncode, 0)
        r = self.ex_pytest(flags=("-q",))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("execution_id", json.loads(r.stdout))
        recs = self.records()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["command_form"], "pytest")
        self.assertEqual(recs[0]["executed_by"], "human")
        self.assertEqual(recs[0]["mode"], "supervised")
        self.assertEqual(recs[0]["approval"], {"tipo": "human_manifest_aprobado"})
        self.assertEqual(recs[0]["exit_code"], 0)

    # (4)
    def test_target_distinto_no_matchea(self):
        self.ap_pytest()
        r = self.ex_pytest(paths=(TEST_B,))
        self.assertEqual(r.returncode, 2)
        self.assertIn("aprobación ausente", r.stderr)
        self.assertEqual(self.records(), [])

    # (5)
    def test_flag_distinto_y_orden_distinto_no_matchean(self):
        self.ap_pytest(flags=("-q", "-x"))
        r = self.ex_pytest(flags=("-q",))
        self.assertEqual(r.returncode, 2)
        self.assertIn("desincronizada", r.stderr)
        r = self.ex_pytest(flags=("-x", "-q"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("desincronizada", r.stderr)
        # orden de paths: cambia el artefacto
        self.ap_pytest(paths=(TEST_A, TEST_B))
        r = self.ex_pytest(paths=(TEST_B, TEST_A))
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.records(), [])

    # (6)
    def test_otro_change_id_no_matchea(self):
        self.ap_pytest()
        r = self.ex_pytest(change=OTRO_CHANGE)
        self.assertEqual(r.returncode, 2)
        self.assertIn("aprobación ausente", r.stderr)
        self.assertEqual(self.aprobaciones(self.repo / "openspec" / "changes" / OTRO_CHANGE), [])
        self.assertEqual(len(self.aprobaciones()), 1)

    # (7) + (8)
    def _assert_rechazo_sin_escritura(self, fabricas, mensaje_esperado=None):
        """Cada fábrica corre un `approve` que debe terminar en 2 dejando
        `control.json` BYTE A BYTE idéntico al previo."""
        for i, fabrica in enumerate(fabricas):
            antes = self.control_path.read_bytes()
            r = fabrica()
            self.assertEqual(r.returncode, 2, f"caso {i}: {r.stdout}{r.stderr}")
            if mensaje_esperado is not None:
                self.assertIn(mensaje_esperado, r.stderr, f"caso {i}: {r.stderr}")
            self.assertEqual(self.control_path.read_bytes(), antes, f"caso {i}: control.json cambió")
        self.assertEqual(self.aprobaciones(), [])

    # (7) errores del builder (hash de artefacto inexistente) y validación de usuario
    def test_request_invalido_por_builder_no_crea_entrada(self):
        self._assert_rechazo_sin_escritura([
            lambda: self.ap_pytest(usuario="a@b.com"),
            lambda: self.ap_script(script="no_existe.py"),
            lambda: self.ap_script(script="/abs/x.py"),  # inexistente: falla el hash del builder
            lambda: self.ap_notebook("openspec/changes/x/runs/no_existe.json"),
        ])
        # los fallos de hash del builder se distinguen de los de la allowlist por el mensaje
        r = self.ap_script(script="no_existe.py")
        self.assertIn("No se pudo calcular el hash", r.stderr)
        self.assertNotIn("allowlist", r.stderr)

    # (8) R12: el artefacto existe (el builder no falla) pero la allowlist rechaza
    def test_request_rechazado_por_allowlist_no_crea_entrada(self):
        # (sin caso interp="otro_interprete": el exec preexistente tampoco fija el intérprete; paridad)
        self._assert_rechazo_sin_escritura([
            lambda: self.ap_pytest(paths=("/etc/x.py",)),
            lambda: self.ap_pytest(paths=("tests/../x.py",)),
            lambda: self.ap_pytest(paths=("otros/fuera.py",)),
            lambda: self.ap_script(script="otros/fuera.py"),  # existe, fuera de alcance
            lambda: self.ap_script(script="scripts/../otros/fuera.py"),  # existe, traversal
            lambda: self.ap_script(script="scripts/run.sh"),  # existe, forma no reconocida (no .py)
            lambda: self.ap_notebook("README.md"),  # existe pero fuera de la forma permitida
        ])
        # discriminación frente al builder: ninguno de estos falla por hash
        r = self.ap_script(script="otros/fuera.py")
        self.assertNotIn("No se pudo calcular el hash", r.stderr)
        self.assertIn("allowlist", r.stderr)

    # (9)
    def test_sin_hash_ni_forma_desconocida(self):
        base = ["exec", "approve", "pytest", "--change-id", self.CHANGE_ID, "--interpreter", INTERPRETER,
                *self._meta()]
        r = _correr_ds_guard(base + ["--hash", "abc", "--paths", TEST_A], self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr.strip())
        r = _correr_ds_guard(["exec", "approve", "bash", "--change-id", self.CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 2)
        r = _correr_ds_guard(["exec", "approve"], self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.aprobaciones(), [])

    # (12) estructura de entrada comparada con `approve` y archivo escrito por escribir_control
    def test_entrada_y_archivo_con_estructura_de_approve(self):
        (self.change_dir / "proposal.md").write_text("# p\n", encoding="utf-8")
        r = _correr_ds_guard(
            ["approve", "--change-id", self.CHANGE_ID, "--artefacto", "proposal.md", *self._meta()], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.ap_pytest().returncode, 0)
        ap = self.aprobaciones()
        self.assertEqual(len(ap), 2)
        self.assertEqual(set(ap[0]), set(ap[1]))
        self.assertEqual(set(ap[1]), CLAVES_ENTRADA)
        # el archivo es exactamente lo que `escribir_control` produce
        control = core.leer_control(self.control_path)
        copia = self.repo / "copia_control.json"
        core.escribir_control(copia, control)
        self.assertEqual(copia.read_bytes(), self.control_path.read_bytes())

    # (10)
    def test_approve_de_archivo_fisico_sigue_funcionando(self):
        (self.change_dir / "proposal.md").write_text("# p\n", encoding="utf-8")
        r = _correr_ds_guard(
            ["approve", "--change-id", self.CHANGE_ID, "--artefacto", "proposal.md", *self._meta()], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        e = self.aprobaciones()[0]
        self.assertEqual(e["algoritmo"], "sha256/lf/v1")
        self.assertEqual(e["hash"], core.hash_lf_v1(self.change_dir / "proposal.md"))

    # (16) vectores fijos de regresión del hash de pytest
    def test_vector_fijo_hash_pytest(self):
        argv = [r"c:\interp\python.exe", "-m", "pytest", "tests/test_a.py", "-q"]
        # hex congelado: cualquier cambio del hash canónico rompe este test
        self.assertEqual(
            leadrun_core.content_sha256(argv),
            "c62996dabf2d5174af7e7b72ee505e0ace065edac95ddbad559bb5b0aaf457e3",
        )
        # el CLI registra exactamente ese cálculo para el argv real
        self.ap_pytest(flags=("-q",))
        real = hashlib.sha256(
            json.dumps([INTERPRETER, "-m", "pytest", TEST_A, "-q"], sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False).encode("utf-8")).hexdigest()
        self.assertEqual(self.aprobaciones()[0]["hash"], real)

    # ayuda (R4)
    def test_ayuda_menciona_ligadura_y_ausencia_de_autenticacion(self):
        r = _correr_ds_guard(["exec", "approve", "-h"], self.repo)
        self.assertEqual(r.returncode, 0)
        texto = " ".join(r.stdout.split()).lower()
        self.assertIn("exacta", texto)
        self.assertIn("sin autenticación criptográfica", texto)

    def test_ayuda_de_la_forma_pytest(self):
        # El encargo pide `exec approve pytest -h`; el spec R4 pide `exec approve -h`.
        r = _correr_ds_guard(["exec", "approve", "pytest", "-h"], self.repo)
        self.assertEqual(r.returncode, 0)
        texto = " ".join(r.stdout.split()).lower()
        self.assertIn("exacta", texto)
        self.assertIn("autenticación criptográfica", texto)


class TestModos(_BaseApprove):
    # (11)
    def test_autonomous_ejecuta_sin_aprobacion_y_approve_no_cambia_modo(self):
        ruta = _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        antes = ruta.read_bytes()
        r = self.ex_pytest()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.records()[0]["mode"], "autonomous")
        self.assertIsNone(self.records()[0]["approval"])
        self.assertEqual(self.ap_pytest().returncode, 0)
        self.assertEqual(len(self.aprobaciones()), 1)
        self.assertEqual(ruta.read_bytes(), antes)
        r = self.ex_pytest(flags=("-q",))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(all(x["mode"] == "autonomous" and x["approval"] is None for x in self.records()))


class TestScriptV2(_BaseApprove):
    def setUp(self):
        super().setUp()
        _escribir_guardrails(self.repo, _GUARDRAILS_SUPERVISED)

    # (14)
    def test_approve_script_v2_y_exec_ok(self):
        r = self.ap_script(sargs=("uno", "dos"))
        self.assertEqual(r.returncode, 0, r.stderr)
        e = self.aprobaciones()[0]
        self.assertEqual(e["algoritmo"], ALGO_V2)
        self.assertEqual(e["artefacto"], SCRIPT)
        esperado = leadrun_core.content_sha256({
            "algorithm": ALGO_V2,
            "script": SCRIPT,
            "script_sha256": core.hash_lf_v1(self.repo / SCRIPT),
            "argv": [INTERPRETER, SCRIPT, "uno", "dos"],
        })
        self.assertEqual(e["hash"], esperado)
        r = self.ex_script(sargs=("uno", "dos"))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(len(self.records()), 1)
        self.assertNotIn("legacy", r.stderr)

    def test_contenido_argumento_y_orden_invalidan(self):
        self.assertEqual(self.ap_script(sargs=("uno", "dos")).returncode, 0)
        for sargs in ((), ("uno",), ("dos", "uno"), ("uno", "tres")):
            r = self.ex_script(sargs=sargs)
            self.assertEqual(r.returncode, 2, f"{sargs}: {r.stdout}")
            self.assertIn("desincronizada", r.stderr)
            self.assertNotIn("legacy", r.stderr)
        self.assertEqual(self.records(), [])
        (self.repo / SCRIPT).write_text("import sys\nsys.exit(0)\n# cambio\n", encoding="utf-8")
        r = self.ex_script(sargs=("uno", "dos"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("desincronizada", r.stderr)
        self.assertNotIn("legacy", r.stderr)

    def test_vector_fijo_hash_script_v2(self):
        identidad = {
            "algorithm": ALGO_V2,
            "script": "scripts/run.py",
            "script_sha256": "a" * 64,
            "argv": [r"c:\interp\python.exe", "scripts/run.py", "--x", "1"],
        }
        # hex congelado del objeto de identidad v2
        self.assertEqual(
            leadrun_core.content_sha256(identidad),
            "aa5c61d4aa2a94493434c12efcd851af898ebd648eb122079bd276aa5b46f884",
        )
        # el CLI registra el cálculo independiente (misma serialización canónica) para el script real
        self.ap_script(sargs=("uno",))
        independiente = hashlib.sha256(
            json.dumps({
                "algorithm": ALGO_V2,
                "script": SCRIPT,
                "script_sha256": core.hash_lf_v1(self.repo / SCRIPT),
                "argv": [INTERPRETER, SCRIPT, "uno"],
            }, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        self.assertEqual(self.aprobaciones()[0]["hash"], independiente)

    # Ligadura a intérprete: NO es viable probar por CLI que otra grafía del mismo
    # intérprete (mayúsculas / `/`) siga siendo válida, porque la allowlist compara
    # `normalizar_interprete(argv[0])` contra `--interpreter` TAL CUAL (sin normalizar):
    # solo una grafía ya normalizada pasa, y no existe un segundo path de intérprete
    # válido. La normalización dentro del hash v2 queda cubierta por el vector fijo
    # y por la comparación independiente (que usa INTERPRETER ya normalizado).
    # Lo que sí se prueba: la ligadura a la RUTA del script.
    def test_aprobacion_ligada_a_la_ruta_del_script(self):
        copia = "scripts/copia_ok.py"
        shutil.copyfile(self.repo / SCRIPT, self.repo / copia)
        self.assertEqual(core.hash_lf_v1(self.repo / SCRIPT), core.hash_lf_v1(self.repo / copia))
        self.assertEqual(self.ap_script().returncode, 0)
        # mismo contenido, mismo intérprete y argv, otra ruta: la aprobación del primero no sirve
        r = self.ex_script(script=copia)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("aprobación ausente", r.stderr)
        self.assertEqual(self.records(), [])
        # aprobada la copia, su hash v2 difiere del original (la ruta está en la identidad)
        self.assertEqual(self.ap_script(script=copia).returncode, 0)
        ap = self.aprobaciones()
        self.assertNotEqual(ap[0]["hash"], ap[1]["hash"])
        self.assertEqual(self.ex_script(script=copia).returncode, 0)
        self.assertEqual(self.ex_script().returncode, 0)

    def test_approve_script_nunca_crea_legacy(self):
        self.ap_script()
        self.ap_script(sargs=("a",))
        self.assertTrue(all(e["algoritmo"] == ALGO_V2 for e in self.aprobaciones()))
        self.assertEqual(len(self.aprobaciones()), 2)

    # (14) única inserción manual: compatibilidad histórica legacy (R9b)
    def test_legacy_historica_aceptada_con_aviso_y_v2_no_cae_a_legacy(self):
        control = json.loads(self.control_path.read_text(encoding="utf-8"))
        control["aprobaciones"].append({
            "artefacto": SCRIPT,
            "algoritmo": "sha256/lf/v1",
            "hash": core.hash_lf_v1(self.repo / SCRIPT),
            "registrado_utc": core.ahora_utc(),
            "usuario": "federico",
            "fecha_declarada": "2026-09-29",
            "alcance_aprobado": "legacy",
            "cita": "n/a",
        })
        core.escribir_control(self.control_path, control)
        r = self.ex_script(sargs=("x",))  # el legacy no liga argumentos
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("aprobación legacy (sha256/lf/v1)", r.stderr)
        self.assertEqual(self.records()[0]["approval"], {"tipo": "human_manifest_aprobado"})

        # Una aprobación v2 posterior es la más reciente: ya no se cae al legacy.
        self.assertEqual(self.ap_script(sargs=("y",)).returncode, 0)
        r = self.ex_script(sargs=("x",))
        self.assertEqual(r.returncode, 2)
        self.assertIn("desincronizada", r.stderr)
        self.assertNotIn("legacy", r.stderr)


    # R9b: solo `sha256/lf/v1` con hash correcto del contenido es legacy aceptable.
    # Inserción manual (misma excepción que el test de legacy histórica).
    def _insertar_manual(self, algoritmo, hash_, registrado_utc):
        control = json.loads(self.control_path.read_text(encoding="utf-8"))
        control["aprobaciones"].append({
            "artefacto": SCRIPT,
            "algoritmo": algoritmo,
            "hash": hash_,
            "registrado_utc": registrado_utc,
            "usuario": "federico",
            "fecha_declarada": "2026-09-29",
            "alcance_aprobado": "manual",
            "cita": "n/a",
        })
        core.escribir_control(self.control_path, control)

    def test_r9b_algoritmo_distinto_mas_reciente_no_se_acepta(self):
        hash_lf = core.hash_lf_v1(self.repo / SCRIPT)
        # legacy válida (antigua) + entrada más reciente de otro algoritmo con hash == hash_lf_v1
        self._insertar_manual("sha256/lf/v1", hash_lf, "2020-01-01T00:00:00Z")
        self._insertar_manual("sha256/otro", hash_lf, "2099-01-01T00:00:00Z")
        r = self.ex_script()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("legacy", r.stderr)
        self.assertEqual(self.records(), [])

    def test_r9b_otro_algoritmo_unico_no_se_acepta(self):
        self._insertar_manual("sha256/otro", core.hash_lf_v1(self.repo / SCRIPT), "2026-09-29T00:00:00Z")
        r = self.ex_script()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("legacy", r.stderr)
        self.assertEqual(self.records(), [])

    def test_r9b_legacy_con_hash_incorrecto_no_se_acepta(self):
        self._insertar_manual("sha256/lf/v1", "0" * 64, "2026-09-29T00:00:00Z")
        r = self.ex_script()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("legacy", r.stderr)
        self.assertEqual(self.records(), [])


class TestNotebook(_BaseApprove):
    MANIFEST = "openspec/changes/20260929-lead-execution-runtime/runs/run1.json"

    # (15) cubre builder + registro + gate de aprobación. NO ejecuta un notebook
    # real (requiere manifest/notebook completos): se valida solo que el gate
    # de aprobación deje pasar / bloquee; el resultado del runner no se afirma.
    def test_approve_manifest_pasa_gate_y_cambio_lo_bloquea(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_SUPERVISED)
        ruta = self.repo / self.MANIFEST
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("{}\n", encoding="utf-8")
        r = self.ex_notebook(self.MANIFEST)
        self.assertIn("aprobación ausente", r.stderr)
        r = self.ap_notebook(self.MANIFEST)
        self.assertEqual(r.returncode, 0, r.stderr)
        e = self.aprobaciones()[0]
        self.assertEqual(e["artefacto"], self.MANIFEST)
        self.assertEqual(e["algoritmo"], "sha256/lf/v1")
        self.assertEqual(e["hash"], core.hash_lf_v1(ruta))
        r = self.ex_notebook(self.MANIFEST)
        self.assertNotIn("Aprobación denegada", r.stderr)
        ruta.write_text('{"x": 1}\n', encoding="utf-8")
        r = self.ex_notebook(self.MANIFEST)
        self.assertEqual(r.returncode, 2)
        self.assertIn("desincronizada", r.stderr)


if __name__ == "__main__":
    unittest.main()
