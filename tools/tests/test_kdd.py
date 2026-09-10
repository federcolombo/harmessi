"""Tests de `tools.dsguard.kdd` (Bloque 4, v0.2.0): lifecycle KDD del
proyecto -- init idempotente, status/criterios detectables, transición de
etapa, y su integración con el cierre de un cambio SDD (`ds_guard transition
--a cerrada`). Usa repositorios temporales propios (nunca este repositorio).

Los tests de `TestKddInit`/`TestKddEstadoCorrupto`/`TestKddStatus`/
`TestKddTransition`/`TestSyncAlCerrar` llaman directamente a las funciones de
`tools.dsguard.kdd` sobre un directorio temporal (sin Git: esas funciones no
lo necesitan). `TestCliCierreIntegraKdd` corre el `tools/ds_guard.py` real
como subproceso contra un repositorio Git temporal, mismo contrato que vería
Claude Code -- ahí es donde se verifica la integración con `sdd.transition`.
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

from dsguard import core, kdd, sdd  # noqa: E402

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
        # El sync al cierre escribe en openspec/kdd/state.json como parte del
        # propio cierre de este cambio -- se declara en el alcance autorizado
        # para no disparar ALCANCE-RUTA sobre un archivo que este mismo test
        # (via `kdd init`, corrido antes) dejó dirty en el working tree.
        rutas_autorizadas.append("openspec/kdd/state.json")

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


class TestKddInit(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_init_crea_state_json_con_las_10_etapas(self):
        estado, creado = kdd.kdd_init(self.repo)
        self.assertTrue(creado)
        self.assertEqual(set(estado["etapas"].keys()), set(kdd.ETAPAS))
        for etapa in kdd.ETAPAS_FUTURAS:
            self.assertEqual(estado["etapas"][etapa]["estado"], "futura")
        for etapa in set(kdd.ETAPAS) - kdd.ETAPAS_FUTURAS:
            self.assertEqual(estado["etapas"][etapa]["estado"], "no_iniciada")
        self.assertTrue(kdd.state_path(self.repo).exists())

    def test_init_es_idempotente(self):
        estado1, creado1 = kdd.kdd_init(self.repo)
        bytes1 = kdd.state_path(self.repo).read_bytes()
        estado2, creado2 = kdd.kdd_init(self.repo)
        bytes2 = kdd.state_path(self.repo).read_bytes()

        self.assertTrue(creado1)
        self.assertFalse(creado2)
        self.assertEqual(bytes1, bytes2)
        self.assertEqual(estado1, estado2)

    def test_init_no_pisa_archivo_corrupto(self):
        ruta = kdd.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("esto no es json valido", encoding="utf-8")
        antes = ruta.read_bytes()

        with self.assertRaises(kdd.KddEstadoError):
            kdd.kdd_init(self.repo)

        self.assertEqual(ruta.read_bytes(), antes)


class TestKddEstadoCorrupto(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_archivo_ausente_levanta_filenotfound(self):
        with self.assertRaises(FileNotFoundError):
            kdd.leer_estado(kdd.state_path(self.repo))

    def test_json_invalido_levanta_kddestadoerror(self):
        ruta = kdd.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("{invalido", encoding="utf-8")
        with self.assertRaises(kdd.KddEstadoError):
            kdd.leer_estado(ruta)

    def test_schema_con_etapas_incompletas_levanta(self):
        ruta = kdd.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        datos = kdd.estado_inicial()
        del datos["etapas"]["modeling"]
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        with self.assertRaises(kdd.KddEstadoError):
            kdd.leer_estado(ruta)

    def test_schema_version_desconocida_levanta(self):
        ruta = kdd.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        datos = kdd.estado_inicial()
        datos["schema_version"] = 999
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        with self.assertRaises(kdd.KddEstadoError):
            kdd.leer_estado(ruta)


class TestKddStatus(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()
        kdd.kdd_init(self.repo)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_criterio_detectable_cumplido_cuando_hay_contenido_real(self):
        change_id = "20260101-modelo-baseline"
        change_dir = self.repo / "openspec" / "changes" / change_id
        change_dir.mkdir(parents=True)
        (change_dir / "spec.md").write_text(
            "# Spec\n\n## Baseline\nRegresión logística simple, AUC 0.62.\n", encoding="utf-8"
        )

        estado = kdd.leer_estado(kdd.state_path(self.repo))
        estado["etapas"]["modeling"]["changes"].append(change_id)
        kdd._escribir_estado(kdd.state_path(self.repo), estado)

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
        """Requisito: si el change se archiva (`ds_guard archive`, `git mv`
        de openspec/changes/<id>/ a openspec/archive/<id>/), la evidencia KDD
        ya registrada sigue siendo detectable sin tocar state.json."""
        change_id = "20260101-modelo-archivado"
        change_dir = self.repo / "openspec" / "changes" / change_id
        change_dir.mkdir(parents=True)
        (change_dir / "spec.md").write_text(
            "# Spec\n\n## Baseline\nRegresión logística simple, AUC 0.62.\n", encoding="utf-8"
        )

        estado = kdd.leer_estado(kdd.state_path(self.repo))
        estado["etapas"]["modeling"]["changes"].append(change_id)
        kdd._escribir_estado(kdd.state_path(self.repo), estado)

        payload_antes = kdd.kdd_status(self.repo)
        self.assertTrue(payload_antes["etapas"]["modeling"]["criterios_detectables"][0]["cumplido"])

        # Simula `ds_guard archive`: mover el directorio completo, sin tocar
        # openspec/kdd/state.json en absoluto.
        bytes_state_antes = kdd.state_path(self.repo).read_bytes()
        destino = self.repo / "openspec" / "archive" / change_id
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(change_dir), str(destino))

        payload_despues = kdd.kdd_status(self.repo)
        self.assertTrue(payload_despues["etapas"]["modeling"]["criterios_detectables"][0]["cumplido"])
        self.assertEqual(payload_despues["etapas"]["modeling"]["changes_no_localizados"], [])
        self.assertEqual(kdd.state_path(self.repo).read_bytes(), bytes_state_antes)

    def test_criterio_detectable_directamente_en_archive_sin_pasar_por_changes(self):
        """No solo el caso "se movió": un change_id cuya evidencia se agrega
        cuando YA está solo en openspec/archive/ (nunca existió en
        openspec/changes/ en esta corrida) también debe resolverse."""
        change_id = "20260101-modelo-ya-archivado"
        change_dir = self.repo / "openspec" / "archive" / change_id
        change_dir.mkdir(parents=True)
        (change_dir / "spec.md").write_text(
            "# Spec\n\n## Baseline\nBaseline histórico.\n", encoding="utf-8"
        )

        estado = kdd.leer_estado(kdd.state_path(self.repo))
        estado["etapas"]["modeling"]["changes"].append(change_id)
        kdd._escribir_estado(kdd.state_path(self.repo), estado)

        payload = kdd.kdd_status(self.repo)
        self.assertTrue(payload["etapas"]["modeling"]["criterios_detectables"][0]["cumplido"])
        self.assertEqual(payload["etapas"]["modeling"]["changes_no_localizados"], [])

    def test_change_inexistente_en_ambos_lugares_es_controlado(self):
        """Un change_id que no está ni en changes/ ni en archive/ (dato
        obsoleto o corrupto en evidencia) nunca crashea: no cuenta para
        ningún criterio y queda reportado en `changes_no_localizados`."""
        change_id = "20260101-no-existe-en-ningun-lado"
        estado = kdd.leer_estado(kdd.state_path(self.repo))
        estado["etapas"]["modeling"]["changes"].append(change_id)
        kdd._escribir_estado(kdd.state_path(self.repo), estado)

        payload = kdd.kdd_status(self.repo)  # no debe levantar ninguna excepción
        self.assertFalse(payload["etapas"]["modeling"]["criterios_detectables"][0]["cumplido"])
        self.assertEqual(payload["etapas"]["modeling"]["changes_no_localizados"], [change_id])

    def test_etapa_futura_sin_criterios_detectables(self):
        payload = kdd.kdd_status(self.repo)
        self.assertEqual(payload["etapas"]["production_readiness"]["criterios_detectables"], [])


class TestKddTransition(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()
        kdd.kdd_init(self.repo)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_transicion_valida_no_iniciada_a_en_progreso(self):
        ok, findings = kdd.kdd_transition(self.repo, "modeling", "en_progreso")
        self.assertTrue(ok)
        self.assertEqual(findings, [])
        estado = kdd.leer_estado(kdd.state_path(self.repo))
        self.assertEqual(estado["etapas"]["modeling"]["estado"], "en_progreso")
        self.assertEqual(len(estado["historial_transiciones"]), 1)

    def test_transicion_invalida_salta_estados(self):
        ok, findings = kdd.kdd_transition(self.repo, "modeling", "cerrada")
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "KDD-TRANSICION-INVALIDA")
        estado = kdd.leer_estado(kdd.state_path(self.repo))
        self.assertEqual(estado["etapas"]["modeling"]["estado"], "no_iniciada")

    def test_etapa_futura_no_admite_transicion(self):
        ok, findings = kdd.kdd_transition(self.repo, "deployment", "en_progreso")
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "KDD-ETAPA-FUTURA")

    def test_etapa_desconocida(self):
        ok, findings = kdd.kdd_transition(self.repo, "no_existe", "en_progreso")
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "KDD-ETAPA-DESCONOCIDA")

    def test_cerrar_sin_evidencia_se_rechaza(self):
        kdd.kdd_transition(self.repo, "modeling", "en_progreso")
        ok, findings = kdd.kdd_transition(self.repo, "modeling", "cerrada")
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "KDD-SIN-EVIDENCIA")

    def test_cerrar_con_evidencia_funciona(self):
        kdd.kdd_transition(self.repo, "modeling", "en_progreso")
        estado = kdd.leer_estado(kdd.state_path(self.repo))
        estado["etapas"]["modeling"]["evidencia"].append(
            {"change_id": "20260101-x", "artefacto": "openspec/changes/20260101-x/verification.md"}
        )
        kdd._escribir_estado(kdd.state_path(self.repo), estado)

        ok, findings = kdd.kdd_transition(self.repo, "modeling", "cerrada")
        self.assertTrue(ok)
        self.assertEqual(findings, [])


class TestSyncAlCerrar(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_sin_declaracion_kdd_es_no_op(self):
        control = {"modo": "completo"}
        resultado = kdd.sync_al_cerrar(self.repo, control, "20260101-x")
        self.assertFalse(resultado["sincronizado"])

    def test_validar_antes_de_cerrar_ok_si_no_declara_etapa(self):
        control = {"modo": "completo"}
        self.assertEqual(kdd.validar_antes_de_cerrar(self.repo, control), [])

    def test_validar_antes_de_cerrar_no_inicializado(self):
        control = {"modo": "completo", "kdd": {"etapa_primaria": "modeling"}}
        findings = kdd.validar_antes_de_cerrar(self.repo, control)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].codigo, "KDD-NO-INICIALIZADO")

    def test_validar_antes_de_cerrar_corrupto(self):
        kdd.kdd_init(self.repo)
        kdd.state_path(self.repo).write_text("{invalido", encoding="utf-8")
        control = {"modo": "completo", "kdd": {"etapa_primaria": "modeling"}}
        findings = kdd.validar_antes_de_cerrar(self.repo, control)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].codigo, "KDD-ESTADO-CORRUPTO")

    def test_sync_agrega_evidencia_sin_duplicar(self):
        kdd.kdd_init(self.repo)
        control = {
            "modo": "completo",
            "kdd": {"etapa_primaria": "modeling", "etapas_afectadas": ["feature_engineering"]},
        }
        resultado1 = kdd.sync_al_cerrar(self.repo, control, "20260101-x")
        resultado2 = kdd.sync_al_cerrar(self.repo, control, "20260101-x")

        self.assertTrue(resultado1["sincronizado"])
        self.assertEqual(set(resultado1["etapas_actualizadas"]), {"modeling", "feature_engineering"})

        estado = kdd.leer_estado(kdd.state_path(self.repo))
        self.assertEqual(estado["etapas"]["modeling"]["changes"], ["20260101-x"])
        self.assertEqual(len(estado["etapas"]["modeling"]["evidencia"]), 1)
        # Ninguna transición de estado la produce el sync -- nunca avanza de etapa.
        self.assertEqual(estado["etapas"]["modeling"]["estado"], "no_iniciada")
        self.assertEqual(resultado2, resultado1)


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
        # No declara etapa KDD: el sync es un no-op transparente (se informa,
        # no se oculta), y no escribe ningún archivo KDD.
        self.assertFalse(payload["kdd_sync"]["sincronizado"])
        estado, _ = sdd.read_estado(self.repo / "openspec" / "changes" / change_id / "tasks.md")
        self.assertEqual(estado, "cerrada")
        # El comportamiento sin declaración KDD no crea ningún estado KDD.
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

        estado = kdd.leer_estado(kdd.state_path(self.repo))
        self.assertIn(change_id, estado["etapas"]["modeling"]["changes"])
        self.assertEqual(len(estado["etapas"]["modeling"]["evidencia"]), 1)
        # No avance automático de etapa: sigue "no_iniciada" pese a tener evidencia nueva.
        self.assertEqual(estado["etapas"]["modeling"]["estado"], "no_iniciada")

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
        (self.repo / "openspec" / "kdd" / "state.json").write_text("{invalido", encoding="utf-8")

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

    def test_kdd_transition_cli_rechaza_etapa_futura(self):
        _correr_ds_guard(["kdd", "init"], self.repo)
        resultado = _correr_ds_guard(
            ["kdd", "transition", "--etapa", "monitoring", "--a", "en_progreso", "--json"], self.repo
        )
        self.assertEqual(resultado.returncode, 1)
        payload = json.loads(resultado.stdout)
        codigos = [f["codigo"] for f in payload["findings"]]
        self.assertIn("KDD-ETAPA-FUTURA", codigos)


if __name__ == "__main__":
    unittest.main()
