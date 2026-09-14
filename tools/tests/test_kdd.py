"""Tests de `tools.dsguard.kdd` (Change 2, v0.3:
20260914-lifecycle-migration-and-kdd-repoint) -- adapter público de
compatibilidad legacy v0.2. El storage real y la lógica de migración/merge/
roll-up viven en `kdd_compat.py` (ver `test_kdd_compat.py`); este archivo
cubre la superficie pública que `kdd.py` sigue exponiendo sin cambios de
contrato (mismos nombres/firmas/retornos que en v0.2) y la integración real
vía CLI (`tools/ds_guard.py` como subproceso).

`TestReexportacionDesdeKddCompat`/`TestKddEstadoErrorEnvuelveAmbos` llaman
directo a `tools.dsguard.kdd` sobre un directorio temporal propio (sin Git).
`TestCliKddYLifecycle`/`TestCliCierreIntegraKdd` corren el `tools/ds_guard.py`
real como subproceso contra un repositorio Git temporal propio, mismo
contrato que vería Claude Code. Nunca usa este repositorio real como
fixture.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import core, kdd, kdd_compat, lifecycle, sdd  # noqa: E402

DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"


def _crear_dir_temporal(prefix: str = "kdd_test_") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def _crear_repo_git_temporal() -> Path:
    repo = _crear_dir_temporal("kdd_cli_test_")
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    return repo


def _correr_ds_guard(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DS_GUARD), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _crear_change_cerrable(repo: Path, change_id: str, kdd_decl: dict = None) -> Path:
    """Un cambio mínimo, ya en `en_verificacion`, con sesión activa y
    `verification.md` con evidencia real -- listo para `transition --a
    cerrada` sin pasar por todo el ciclo de aprobaciones (no es lo que testea
    este archivo)."""
    change_dir = repo / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True, exist_ok=True)

    (change_dir / "tasks.md").write_text(
        "# Tareas — %s\n\nestado: en_verificacion\n\n## Tareas\n- [x] hacer algo\n" % change_id,
        encoding="utf-8",
    )
    (change_dir / "verification.md").write_text(
        "# Verificación — %s\n\n## Evidencia obtenida\nCorrida real de prueba, output X.\n"
        % change_id,
        encoding="utf-8",
    )

    rutas_autorizadas = [f"openspec/changes/{change_id}/*"]
    if kdd_decl is not None:
        # El sync al cierre escribe en openspec/lifecycle/state.json como parte
        # del propio cierre de este cambio -- se declara en el alcance
        # autorizado para no disparar ALCANCE-RUTA sobre un archivo que este
        # mismo test (via `kdd init`, corrido antes) dejó dirty en el working
        # tree.
        rutas_autorizadas.append("openspec/lifecycle/state.json")

    control = {
        "schema_version": 1,
        "change_id": change_id,
        "modo": "completo",
        "origen": "test",
        "creado_utc": core.ahora_utc(),
        "baseline": {"commit": "0" * 40, "rama": "main", "capturado_utc": core.ahora_utc()},
        "alcance": {"rutas_autorizadas": rutas_autorizadas},
        "aprobaciones": [],
        "transiciones": [
            {"utc": core.ahora_utc(), "desde": "aprobada_implementacion", "hacia": "en_implementacion"},
            {"utc": core.ahora_utc(), "desde": "en_implementacion", "hacia": "en_verificacion"},
        ],
        "sesiones": [],
    }
    if kdd_decl is not None:
        control["kdd"] = kdd_decl
    sdd.session_start(control, minutos=90)

    core.escribir_control(change_dir / "control.json", control)
    return change_dir


# --- Re-exportación / envoltura de excepciones --------------------------------

class TestReexportacionDesdeKddCompat(unittest.TestCase):
    def test_etapas_reexportada_mismo_contenido(self):
        self.assertEqual(kdd.ETAPAS, kdd_compat.ETAPAS)
        self.assertIs(kdd.ETAPAS, kdd_compat.ETAPAS)

    def test_etapas_futuras_reexportada_mismo_contenido(self):
        self.assertEqual(kdd.ETAPAS_FUTURAS, kdd_compat.ETAPAS_FUTURAS)
        self.assertIs(kdd.ETAPAS_FUTURAS, kdd_compat.ETAPAS_FUTURAS)

    def test_estados_etapa_validos_reexportada(self):
        self.assertEqual(kdd.ESTADOS_ETAPA_VALIDOS, kdd_compat.ESTADOS_ETAPA_VALIDOS)

    def test_estados_etapa_destino_validos_reexportada(self):
        self.assertEqual(kdd.ESTADOS_ETAPA_DESTINO_VALIDOS, kdd_compat.ESTADOS_ETAPA_DESTINO_VALIDOS)


class TestKddEstadoErrorEnvuelveAmbos(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_envuelve_kddcompaterror(self):
        """Legacy presente sin migrar -> kdd_compat.KddCompatError envuelto
        en kdd.KddEstadoError."""
        ruta_legacy = kdd_compat.state_path_legacy(self.repo)
        ruta_legacy.parent.mkdir(parents=True, exist_ok=True)
        ruta_legacy.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "creado_utc": core.ahora_utc(),
                    "etapas": {
                        etapa: {"estado": "no_iniciada", "changes": [], "evidencia": [], "actualizado_utc": core.ahora_utc()}
                        for etapa in kdd.ETAPAS
                    },
                    "historial_transiciones": [],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(kdd.KddEstadoError) as ctx:
            kdd.kdd_init(self.repo)
        self.assertIsInstance(ctx.exception.__cause__, kdd_compat.KddCompatError)

    def test_envuelve_lifecycleestadoerror(self):
        """lifecycle/state.json corrupto -> lifecycle.LifecycleEstadoError
        envuelto en kdd.KddEstadoError."""
        lifecycle.lifecycle_init(self.repo)
        lifecycle.state_path(self.repo).write_text("{invalido", encoding="utf-8")
        with self.assertRaises(kdd.KddEstadoError) as ctx:
            kdd.kdd_status(self.repo)
        self.assertIsInstance(ctx.exception.__cause__, lifecycle.LifecycleEstadoError)


# --- CLI real: kdd/lifecycle -------------------------------------------------

class TestCliKddYLifecycle(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_kdd_init_sobre_proyecto_nuevo_crea_lifecycle_state(self):
        resultado = _correr_ds_guard(["kdd", "init", "--json"], self.repo)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertTrue((self.repo / "openspec" / "lifecycle" / "state.json").exists())
        self.assertFalse((self.repo / "openspec" / "kdd" / "state.json").exists())

    def test_kdd_status_despues_de_migrar_opera_sobre_lifecycle_real(self):
        _correr_ds_guard(["kdd", "init"], self.repo)
        resultado = _correr_ds_guard(["kdd", "status", "--json"], self.repo)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        payload = json.loads(resultado.stdout)
        self.assertEqual(set(payload["etapas"].keys()), set(kdd.ETAPAS))

    def test_kdd_transition_despues_de_migrar_opera_sobre_lifecycle_real(self):
        _correr_ds_guard(["kdd", "init"], self.repo)
        resultado = _correr_ds_guard(
            ["kdd", "transition", "--etapa", "modeling", "--a", "en_progreso", "--json"], self.repo
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        self.assertEqual(estado["kdd"]["pasos"]["data_mining"]["estado"], "en_progreso")

    def test_evaluation_e_interpretation_son_sinonimos_post_migracion(self):
        _correr_ds_guard(["kdd", "init"], self.repo)
        _correr_ds_guard(["kdd", "transition", "--etapa", "evaluation", "--a", "en_progreso"], self.repo)

        resultado_eval = _correr_ds_guard(["kdd", "status", "--json"], self.repo)
        payload_eval = json.loads(resultado_eval.stdout)
        resultado_interp = _correr_ds_guard(["kdd", "status", "--json"], self.repo)
        payload_interp = json.loads(resultado_interp.stdout)

        self.assertEqual(
            payload_eval["etapas"]["evaluation"]["estado"], payload_interp["etapas"]["interpretation"]["estado"]
        )
        self.assertEqual(payload_eval["etapas"]["evaluation"]["estado"], "en_progreso")
        self.assertEqual(payload_interp["etapas"]["interpretation"]["estado"], "en_progreso")

    def test_los_10_nombres_legacy_siguen_aceptados_como_choices_de_etapa(self):
        _correr_ds_guard(["kdd", "init"], self.repo)
        for etapa in kdd.ETAPAS:
            resultado = _correr_ds_guard(
                ["kdd", "transition", "--etapa", etapa, "--a", "en_progreso", "--json"], self.repo
            )
            # No debe ser un error de argparse (exit 2 "invalid choice"); puede
            # ser 0 (transición aplicada) o 1 (finding, p. ej. transición
            # inválida si ya se movió antes), pero nunca "unrecognized"/2.
            self.assertNotEqual(resultado.returncode, 2, resultado.stderr)
            self.assertNotIn("invalid choice", resultado.stderr)

    def test_lifecycle_migrate_end_to_end_legacy_corrupto(self):
        ruta_legacy = self.repo / "openspec" / "kdd" / "state.json"
        ruta_legacy.parent.mkdir(parents=True, exist_ok=True)
        ruta_legacy.write_text("{invalido", encoding="utf-8")

        resultado = _correr_ds_guard(["lifecycle", "migrate", "--json"], self.repo)
        self.assertNotEqual(resultado.returncode, 0)
        self.assertTrue(resultado.stderr.strip())
        self.assertFalse((self.repo / "openspec" / "lifecycle" / "state.json").exists())
        # Legacy nunca se toca.
        self.assertEqual(ruta_legacy.read_text(encoding="utf-8"), "{invalido")

    def test_lifecycle_migrate_end_to_end_nada_que_migrar(self):
        resultado = _correr_ds_guard(["lifecycle", "migrate", "--json"], self.repo)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        payload = json.loads(resultado.stdout)
        self.assertFalse(payload["migrado"])
        self.assertFalse((self.repo / "openspec" / "lifecycle" / "state.json").exists())

    def test_lifecycle_migrate_end_to_end_exitoso(self):
        legacy = {
            "schema_version": 1,
            "creado_utc": core.ahora_utc(),
            "etapas": {
                etapa: {
                    "estado": "futura" if etapa in kdd.ETAPAS_FUTURAS else "no_iniciada",
                    "changes": [],
                    "evidencia": [],
                    "actualizado_utc": core.ahora_utc(),
                }
                for etapa in kdd.ETAPAS
            },
            "historial_transiciones": [],
        }
        ruta_legacy = self.repo / "openspec" / "kdd" / "state.json"
        ruta_legacy.parent.mkdir(parents=True, exist_ok=True)
        ruta_legacy.write_text(json.dumps(legacy), encoding="utf-8")
        bytes_legacy_antes = ruta_legacy.read_bytes()

        resultado = _correr_ds_guard(["lifecycle", "migrate", "--json"], self.repo)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        payload = json.loads(resultado.stdout)
        self.assertTrue(payload["migrado"])
        self.assertTrue((self.repo / "openspec" / "lifecycle" / "state.json").exists())
        self.assertEqual(ruta_legacy.read_bytes(), bytes_legacy_antes)

    def test_kdd_status_o_transition_sin_migrar_da_error_claro(self):
        ruta_legacy = self.repo / "openspec" / "kdd" / "state.json"
        ruta_legacy.parent.mkdir(parents=True, exist_ok=True)
        ruta_legacy.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "creado_utc": core.ahora_utc(),
                    "etapas": {
                        etapa: {"estado": "no_iniciada", "changes": [], "evidencia": [], "actualizado_utc": core.ahora_utc()}
                        for etapa in kdd.ETAPAS
                    },
                    "historial_transiciones": [],
                }
            ),
            encoding="utf-8",
        )
        resultado = _correr_ds_guard(["kdd", "status"], self.repo)
        self.assertEqual(resultado.returncode, 2)
        self.assertIn("lifecycle migrate", resultado.stderr)


# --- Criterios detectables (informativo) -- sin cambios vs v0.2 --------------

class TestCriteriosDetectables(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        _correr_ds_guard(["kdd", "init"], self.repo)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_criterio_detectable_cumplido_cuando_hay_contenido_real(self):
        change_id = "20260101-modelo-baseline"
        change_dir = self.repo / "openspec" / "changes" / change_id
        change_dir.mkdir(parents=True)
        (change_dir / "spec.md").write_text(
            "# Spec\n\n## Baseline\nRegresión logística simple, AUC 0.62.\n", encoding="utf-8"
        )

        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        estado["kdd"]["pasos"]["data_mining"]["changes"].append(change_id)
        lifecycle.escribir_estado(self.repo, estado)

        payload = kdd.kdd_status(self.repo)
        criterios = payload["etapas"]["modeling"]["criterios_detectables"]
        self.assertEqual(len(criterios), 1)
        self.assertTrue(criterios[0]["cumplido"])
        self.assertEqual(payload["etapas"]["modeling"]["changes_no_localizados"], [])

    def test_criterio_detectable_no_cumplido_sin_evidencia(self):
        payload = kdd.kdd_status(self.repo)
        criterios = payload["etapas"]["modeling"]["criterios_detectables"]
        self.assertEqual(len(criterios), 1)
        self.assertFalse(criterios[0]["cumplido"])

    def test_criterio_detectable_sigue_cumplido_tras_archivar_el_change(self):
        change_id = "20260101-modelo-archivado"
        change_dir = self.repo / "openspec" / "changes" / change_id
        change_dir.mkdir(parents=True)
        (change_dir / "spec.md").write_text(
            "# Spec\n\n## Baseline\nRegresión logística simple, AUC 0.62.\n", encoding="utf-8"
        )

        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        estado["kdd"]["pasos"]["data_mining"]["changes"].append(change_id)
        lifecycle.escribir_estado(self.repo, estado)

        payload_antes = kdd.kdd_status(self.repo)
        self.assertTrue(payload_antes["etapas"]["modeling"]["criterios_detectables"][0]["cumplido"])

        bytes_state_antes = lifecycle.state_path(self.repo).read_bytes()
        destino = self.repo / "openspec" / "archive" / change_id
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(change_dir), str(destino))

        payload_despues = kdd.kdd_status(self.repo)
        self.assertTrue(payload_despues["etapas"]["modeling"]["criterios_detectables"][0]["cumplido"])
        self.assertEqual(payload_despues["etapas"]["modeling"]["changes_no_localizados"], [])
        self.assertEqual(lifecycle.state_path(self.repo).read_bytes(), bytes_state_antes)

    def test_change_inexistente_en_ambos_lugares_es_controlado(self):
        change_id = "20260101-no-existe-en-ningun-lado"
        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        estado["kdd"]["pasos"]["data_mining"]["changes"].append(change_id)
        lifecycle.escribir_estado(self.repo, estado)

        payload = kdd.kdd_status(self.repo)  # no debe levantar ninguna excepción
        self.assertFalse(payload["etapas"]["modeling"]["criterios_detectables"][0]["cumplido"])
        self.assertEqual(payload["etapas"]["modeling"]["changes_no_localizados"], [change_id])

    def test_etapa_futura_sin_criterios_detectables(self):
        payload = kdd.kdd_status(self.repo)
        self.assertEqual(payload["etapas"]["production_readiness"]["criterios_detectables"], [])


# --- Integración con el cierre SDD -------------------------------------------

class TestCliCierreIntegraKdd(unittest.TestCase):
    """Nivel CLI real: `tools/ds_guard.py transition --a cerrada` como lo
    invocaría el Lead."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_regresion_sdd_cierre_sin_kdd_declarado(self):
        change_id = "20260101-regresion-sdd"
        _crear_change_cerrable(self.repo, change_id, kdd_decl=None)

        resultado = _correr_ds_guard(
            ["transition", "--change-id", change_id, "--a", "cerrada", "--json"], self.repo
        )

        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        payload = json.loads(resultado.stdout)
        self.assertEqual(payload["transicion_aplicada"], "cerrada")
        self.assertFalse(payload["kdd_sync"]["sincronizado"])
        estado, _ = sdd.read_estado(self.repo / "openspec" / "changes" / change_id / "tasks.md")
        self.assertEqual(estado, "cerrada")
        self.assertFalse((self.repo / "openspec" / "lifecycle").exists())
        self.assertFalse((self.repo / "openspec" / "kdd").exists())

    def test_cierre_sincroniza_evidencia_sin_avanzar_etapa(self):
        _correr_ds_guard(["kdd", "init"], self.repo)
        change_id = "20260101-modelo-v1"
        _crear_change_cerrable(
            self.repo, change_id, kdd_decl={"etapa_primaria": "modeling", "etapas_afectadas": []}
        )

        resultado = _correr_ds_guard(
            ["transition", "--change-id", change_id, "--a", "cerrada", "--json"], self.repo
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        payload = json.loads(resultado.stdout)
        self.assertEqual(payload["kdd_sync"]["sincronizado"], True)
        self.assertEqual(payload["kdd_sync"]["etapas_actualizadas"], ["modeling"])

        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        self.assertIn(change_id, estado["crispdm"]["fases"]["modeling"]["changes"])
        self.assertIn(change_id, estado["kdd"]["pasos"]["data_mining"]["changes"])
        self.assertEqual(len(estado["crispdm"]["fases"]["modeling"]["evidencia"]), 1)
        # No avance automático de etapa: sigue "no_iniciada" pese a tener evidencia nueva.
        self.assertEqual(estado["crispdm"]["fases"]["modeling"]["estado"], "no_iniciada")

    def test_cierre_bloqueado_si_kdd_no_inicializado(self):
        change_id = "20260101-modelo-v2"
        _crear_change_cerrable(
            self.repo, change_id, kdd_decl={"etapa_primaria": "modeling"}
        )
        # Deliberadamente sin correr `kdd init`.

        resultado = _correr_ds_guard(
            ["transition", "--change-id", change_id, "--a", "cerrada", "--json"], self.repo
        )

        self.assertEqual(resultado.returncode, 1)
        payload = json.loads(resultado.stdout)
        codigos = [f["codigo"] for f in payload["findings"]]
        self.assertIn("KDD-NO-INICIALIZADO", codigos)
        # Atomicidad: el cierre no se aplicó.
        estado, _ = sdd.read_estado(self.repo / "openspec" / "changes" / change_id / "tasks.md")
        self.assertEqual(estado, "en_verificacion")

    def test_cierre_bloqueado_si_state_corrupto(self):
        _correr_ds_guard(["kdd", "init"], self.repo)
        (self.repo / "openspec" / "lifecycle" / "state.json").write_text("{invalido", encoding="utf-8")

        change_id = "20260101-modelo-v3"
        _crear_change_cerrable(
            self.repo, change_id, kdd_decl={"etapa_primaria": "modeling"}
        )

        resultado = _correr_ds_guard(
            ["transition", "--change-id", change_id, "--a", "cerrada", "--json"], self.repo
        )

        self.assertEqual(resultado.returncode, 1)
        payload = json.loads(resultado.stdout)
        codigos = [f["codigo"] for f in payload["findings"]]
        self.assertIn("KDD-ESTADO-CORRUPTO", codigos)
        estado, _ = sdd.read_estado(self.repo / "openspec" / "changes" / change_id / "tasks.md")
        self.assertEqual(estado, "en_verificacion")

    def test_kdd_status_cli_informa_sin_fallar(self):
        _correr_ds_guard(["kdd", "init"], self.repo)
        resultado = _correr_ds_guard(["kdd", "status", "--json"], self.repo)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        payload = json.loads(resultado.stdout)
        self.assertEqual(set(payload["etapas"].keys()), set(kdd.ETAPAS))

    def test_etapa_evaluation_e_interpretation_sinonimos_en_cierre(self):
        """--etapa evaluation e --etapa interpretation son sinónimos
        funcionales post-migración: declarar cualquiera de las dos como
        etapa_primaria sincroniza el mismo paso subyacente."""
        _correr_ds_guard(["kdd", "init"], self.repo)
        change_id = "20260101-eval-v1"
        _crear_change_cerrable(
            self.repo, change_id, kdd_decl={"etapa_primaria": "interpretation"}
        )
        resultado = _correr_ds_guard(
            ["transition", "--change-id", change_id, "--a", "cerrada", "--json"], self.repo
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        self.assertIn(change_id, estado["kdd"]["pasos"]["interpretation_evaluation"]["changes"])
        self.assertIn(change_id, estado["crispdm"]["fases"]["evaluation"]["changes"])


if __name__ == "__main__":
    unittest.main()
