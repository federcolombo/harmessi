"""Tests de `tools.dsguard.scope` (Change 2, v0.4:
20260916-scope-and-change-isolation) -- alcance de un Change SDD: working
tree actual MÁS el diff completo desde `control["baseline"]["commit"]`,
consolidando lo que antes era `repo.files_out_of_scope` (solo working tree)
duplicado en `sdd.gate_cierre`/`ds_guard.cmd_validate`.

Mismo patrón de fixtures que `tools/tests/test_mlops_foundations.py`/
`tools/dsimpact/tests/test_git_source.py`: repo git temporal real vía
`subprocess`/`tempfile.mkdtemp`, `git init`/`config`/`add`/`commit`. Nunca usa
este repositorio real como fixture.
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

from dsguard import core, scope, scope_amendments, sdd  # noqa: E402

DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), check=True, capture_output=True, text=True
    )


def _crear_repo() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="dsguard_scope_test_"))
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "openspec").mkdir()
    (repo / "openspec" / "dentro.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "inicial")
    return repo


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _control(repo: Path, baseline_commit=None, rutas=None) -> dict:
    control = {
        "schema_version": 1,
        "alcance": {"rutas_autorizadas": rutas if rutas is not None else ["openspec/*"]},
    }
    if baseline_commit is not None:
        control["baseline"] = {"commit": baseline_commit}
    return control


class TestArchivosTocadosDesdeBaseline(unittest.TestCase):
    def tearDown(self):
        pass

    def test_sin_baseline_devuelve_vacio(self):
        repo = _crear_repo()
        try:
            self.assertEqual(scope.archivos_tocados_desde_baseline(repo, None), [])
            self.assertEqual(scope.archivos_tocados_desde_baseline(repo, ""), [])
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_referencia_invalida_no_lanza_devuelve_vacio(self):
        repo = _crear_repo()
        try:
            resultado = scope.archivos_tocados_desde_baseline(repo, "0" * 40)
            self.assertEqual(resultado, [])
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_archivo_modificado_y_commiteado_desde_baseline(self):
        repo = _crear_repo()
        try:
            baseline = _head(repo)
            (repo / "fuera.py").write_text("y = 1\n", encoding="utf-8")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "fuera de scope")
            resultado = scope.archivos_tocados_desde_baseline(repo, baseline)
            self.assertIn("fuera.py", resultado)
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_rename_detectado(self):
        repo = _crear_repo()
        try:
            baseline = _head(repo)
            _git(repo, "mv", "openspec/dentro.py", "openspec/renombrado.py")
            _git(repo, "commit", "-q", "-m", "rename")
            resultado = scope.archivos_tocados_desde_baseline(repo, baseline)
            self.assertIn("openspec/renombrado.py", resultado)
            self.assertNotIn("openspec/dentro.py", resultado)
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_copia_detectada_toma_ruta_nueva(self):
        repo = _crear_repo()
        try:
            baseline = _head(repo)
            # Contenido suficientemente grande para que git detecte copia (-M
            # incluye detección de copia solo si el original está intacto y
            # hay overlap; usamos contenido idéntico repetido para maximizar
            # similitud).
            contenido = "x = 1\n" * 50
            (repo / "openspec" / "dentro.py").write_text(contenido, encoding="utf-8")
            (repo / "openspec" / "copia.py").write_text(contenido, encoding="utf-8")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "copia")
            r = subprocess.run(
                ["git", "diff", "--name-status", "-M", "-C", baseline],
                cwd=str(repo),
                capture_output=True,
                text=True,
            )
            # Solo verificamos el parseo de scope.py sobre la salida real de
            # git -- si git no detectó copia (requiere -C, no solo -M), el
            # archivo aparece como agregado, cubierto igual por el mismo
            # código de campos[1].
            resultado = scope.archivos_tocados_desde_baseline(repo, baseline)
            self.assertIn("openspec/copia.py", resultado)
        finally:
            shutil.rmtree(repo, ignore_errors=True)


class TestEvaluarAlcance(unittest.TestCase):
    def test_archivo_fuera_de_scope_sin_commitear(self):
        repo = _crear_repo()
        try:
            (repo / "fuera.py").write_text("y = 1\n", encoding="utf-8")
            control = _control(repo, baseline_commit=_head(repo))
            findings = scope.evaluar_alcance(repo, control)
            codigos_ubicaciones = {(f.codigo, f.ubicacion) for f in findings}
            self.assertIn(("ALCANCE-RUTA", "fuera.py"), codigos_ubicaciones)
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_archivo_fuera_de_scope_ya_commiteado_working_tree_limpio(self):
        """El bug real que este change corrige: working tree limpio, pero el
        archivo fuera de scope quedó commiteado dentro del rango del Change."""
        repo = _crear_repo()
        try:
            baseline = _head(repo)
            (repo / "fuera.py").write_text("y = 1\n", encoding="utf-8")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "fuera de scope, commiteado")
            control = _control(repo, baseline_commit=baseline)
            findings = scope.evaluar_alcance(repo, control)
            codigos_ubicaciones = {(f.codigo, f.ubicacion) for f in findings}
            self.assertIn(("ALCANCE-RUTA", "fuera.py"), codigos_ubicaciones)
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_archivo_dentro_de_scope_commiteado_sin_finding(self):
        repo = _crear_repo()
        try:
            baseline = _head(repo)
            (repo / "openspec" / "dentro.py").write_text("x = 2\n", encoding="utf-8")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "dentro de scope")
            control = _control(repo, baseline_commit=baseline, rutas=["openspec/*"])
            findings = scope.evaluar_alcance(repo, control)
            self.assertEqual(findings, [])
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_archivo_dentro_de_scope_sin_commitear_sin_finding(self):
        repo = _crear_repo()
        try:
            (repo / "openspec" / "nuevo_dentro.py").write_text("z = 1\n", encoding="utf-8")
            control = _control(repo, baseline_commit=_head(repo), rutas=["openspec/*"])
            findings = scope.evaluar_alcance(repo, control)
            self.assertEqual(findings, [])
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_sin_baseline_commit_se_comporta_como_solo_working_tree(self):
        repo = _crear_repo()
        try:
            (repo / "fuera.py").write_text("y = 1\n", encoding="utf-8")
            control = _control(repo, baseline_commit=None)
            self.assertNotIn("baseline", control)
            findings = scope.evaluar_alcance(repo, control)
            codigos_ubicaciones = {(f.codigo, f.ubicacion) for f in findings}
            self.assertIn(("ALCANCE-RUTA", "fuera.py"), codigos_ubicaciones)
            # Sin baseline, un archivo fuera de scope ya commiteado (fuera del
            # working tree actual) NO se detecta -- comportamiento idéntico
            # al chequeo viejo (solo working tree), sin excepción.
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_sin_baseline_commit_ya_commiteado_no_detectado(self):
        repo = _crear_repo()
        try:
            (repo / "fuera.py").write_text("y = 1\n", encoding="utf-8")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "fuera de scope commiteado")
            control = _control(repo, baseline_commit=None)
            findings = scope.evaluar_alcance(repo, control)
            self.assertEqual(findings, [])
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_baseline_commit_referencia_invalida_no_lanza(self):
        repo = _crear_repo()
        try:
            (repo / "fuera.py").write_text("y = 1\n", encoding="utf-8")
            control = _control(repo, baseline_commit="0" * 40)
            findings = scope.evaluar_alcance(repo, control)
            codigos_ubicaciones = {(f.codigo, f.ubicacion) for f in findings}
            # Sigue detectando vía working tree, aunque la referencia sea
            # inválida.
            self.assertIn(("ALCANCE-RUTA", "fuera.py"), codigos_ubicaciones)
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_determinismo_mismo_estado_mismo_resultado(self):
        repo = _crear_repo()
        try:
            baseline = _head(repo)
            (repo / "fuera.py").write_text("y = 1\n", encoding="utf-8")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "fuera de scope")
            (repo / "otro_fuera.py").write_text("y = 2\n", encoding="utf-8")
            control = _control(repo, baseline_commit=baseline)
            r1 = scope.evaluar_alcance(repo, control)
            r2 = scope.evaluar_alcance(repo, control)
            self.assertEqual(len(r1), len(r2))
            for f1, f2 in zip(r1, r2):
                self.assertEqual(f1.codigo, f2.codigo)
                self.assertEqual(f1.mensaje, f2.mensaje)
                self.assertEqual(f1.ubicacion, f2.ubicacion)
        finally:
            shutil.rmtree(repo, ignore_errors=True)


# --- Alcance efectivo con enmiendas gobernadas (Change 20261013-governed-amendments, R21-R25) ---

_CAMPOS_T1_FALSOS = {
    "approval_channel": "console_confirmed",
    "confirmed_at": "2026-10-13T00:00:00Z",
    "channel_version": "console/v1",
}
_CHANGE_ID = "abc"
_REGISTRO_REL = f"openspec/changes/{_CHANGE_ID}/amendments.jsonl"


def _enmendar(change_dir: Path, control: dict, add=(), remove=()) -> dict:
    """Agrega una enmienda real vía `scope_amendments` (T1 falso: el módulo de datos no pide T1)."""
    estado = scope_amendments.estado_alcance(change_dir, control)
    plan = scope_amendments.planificar_enmienda(estado, list(add), list(remove), (), lambda r: (r, None))
    return scope_amendments.aplicar_enmienda(
        change_dir, plan, motivo="prueba", usuario="tester", fecha="2026-10-13",
        campos_t1=dict(_CAMPOS_T1_FALSOS), esperado_hash_antes=plan.hash_antes,
        utc="2026-10-13T00:00:00Z",
    )


class TestAlcanceEfectivo(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dsguard_alcance_efectivo_"))
        self.change_dir = self.tmp / "openspec" / "changes" / _CHANGE_ID
        self.change_dir.mkdir(parents=True)
        self.control = {"change_id": _CHANGE_ID, "alcance": {"rutas_autorizadas": ["a.py", "b.py"]}}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sin_archivo_es_la_cache(self):
        rutas, hallazgos = scope.alcance_efectivo(self.change_dir, self.control)
        self.assertEqual(sorted(rutas), ["a.py", "b.py"])
        self.assertEqual(hallazgos, [])

    def test_change_dir_none_es_la_cache(self):
        rutas, hallazgos = scope.alcance_efectivo(None, self.control)
        self.assertEqual(rutas, ["a.py", "b.py"])
        self.assertEqual(hallazgos, [])

    def test_cadena_valida_es_la_ultima_entrada(self):
        _enmendar(self.change_dir, self.control, add=["c.py"])
        _enmendar(self.change_dir, self.control, remove=["a.py"])
        self.control["alcance"]["rutas_autorizadas"] = ["b.py", "c.py"]  # caché al día
        rutas, hallazgos = scope.alcance_efectivo(self.change_dir, self.control)
        self.assertEqual(sorted(rutas), ["b.py", "c.py"])
        self.assertEqual(hallazgos, [])

    def test_cadena_invalida_rutas_vacias_y_hallazgo(self):
        _enmendar(self.change_dir, self.control, add=["c.py"])
        registro = self.change_dir / "amendments.jsonl"
        registro.write_text(registro.read_text(encoding="utf-8").replace("prueba", "alterado"), encoding="utf-8")
        rutas, hallazgos = scope.alcance_efectivo(self.change_dir, self.control)
        self.assertEqual(rutas, [])
        self.assertIn("ALCANCE-ENMIENDA-INVALIDA", [h.codigo for h in hallazgos])

    def test_json_invalido_rutas_vacias_y_hallazgo(self):
        (self.change_dir / "amendments.jsonl").write_text("{no es json\n", encoding="utf-8")
        rutas, hallazgos = scope.alcance_efectivo(self.change_dir, self.control)
        self.assertEqual(rutas, [])
        self.assertIn("ALCANCE-ENMIENDA-INVALIDA", [h.codigo for h in hallazgos])

    def test_cache_divergente_gana_la_cadena_y_hay_hallazgo(self):
        _enmendar(self.change_dir, self.control, add=["c.py"])
        # La caché de control.json NO se refrescó (o fue editada a mano): la cadena manda.
        self.control["alcance"]["rutas_autorizadas"] = ["a.py", "b.py", "z_manual.py"]
        rutas, hallazgos = scope.alcance_efectivo(self.change_dir, self.control)
        self.assertEqual(sorted(rutas), ["a.py", "b.py", "c.py"])
        self.assertNotIn("z_manual.py", rutas)
        self.assertIn("ALCANCE-CACHE-DIVERGENTE", [h.codigo for h in hallazgos])

    def test_rutas_con_unicode_y_espacios(self):
        _enmendar(self.change_dir, self.control, add=["carpeta con espacio/ñandú.py"])
        rutas, _ = scope.alcance_efectivo(self.change_dir, self.control)
        self.assertIn("carpeta con espacio/ñandú.py", rutas)


class TestEvaluarAlcanceConEnmiendas(unittest.TestCase):
    """`evaluar_alcance` usa el alcance efectivo. El `amendments.jsonl` entra en la caché del
    scope (como lo hace la primera enmienda en el CLI) para no contar como archivo fuera de alcance."""

    def setUp(self):
        self.repo = _crear_repo()
        self.change_dir = self.repo / "openspec" / "changes" / _CHANGE_ID
        self.change_dir.mkdir(parents=True)
        (self.change_dir / "tasks.md").write_text("t\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "change")
        self.control = _control(
            self.repo, baseline_commit=_head(self.repo),
            rutas=["openspec/dentro.py", _REGISTRO_REL],
        )
        self.control["change_id"] = _CHANGE_ID

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _ubicaciones_ruta(self) -> set:
        return {f.ubicacion for f in scope.evaluar_alcance(self.repo, self.control) if f.codigo == "ALCANCE-RUTA"}

    def test_sin_enmiendas_equivale_a_la_cache(self):
        (self.repo / "nuevo.py").write_text("n = 1\n", encoding="utf-8")
        self.assertEqual(self._ubicaciones_ruta(), {"nuevo.py"})

    def test_ruta_agregada_deja_de_dar_alcance_ruta(self):
        (self.repo / "nuevo.py").write_text("n = 1\n", encoding="utf-8")
        self.assertIn("nuevo.py", self._ubicaciones_ruta())
        _enmendar(self.change_dir, self.control, add=["nuevo.py"])
        self.control["alcance"]["rutas_autorizadas"] = sorted(
            set(self.control["alcance"]["rutas_autorizadas"]) | {"nuevo.py"})
        findings = scope.evaluar_alcance(self.repo, self.control)
        self.assertEqual(findings, [])

    def test_ruta_removida_vuelve_a_dar_alcance_ruta(self):
        _enmendar(self.change_dir, self.control, remove=["openspec/dentro.py"])
        self.control["alcance"]["rutas_autorizadas"] = [_REGISTRO_REL]
        (self.repo / "openspec" / "dentro.py").write_text("x = 99\n", encoding="utf-8")
        self.assertIn("openspec/dentro.py", self._ubicaciones_ruta())

    def test_cache_divergente_emite_aviso_y_manda_la_cadena(self):
        _enmendar(self.change_dir, self.control, add=["nuevo.py"])
        # caché no refrescada: sigue sin "nuevo.py"
        (self.repo / "nuevo.py").write_text("n = 1\n", encoding="utf-8")
        findings = scope.evaluar_alcance(self.repo, self.control)
        codigos = [f.codigo for f in findings]
        self.assertIn("ALCANCE-CACHE-DIVERGENTE", codigos)
        self.assertNotIn("ALCANCE-RUTA", codigos)

    def test_cache_editada_a_mano_no_autoriza(self):
        _enmendar(self.change_dir, self.control, add=["nuevo.py"])
        self.control["alcance"]["rutas_autorizadas"].append("manual.py")
        (self.repo / "manual.py").write_text("m = 1\n", encoding="utf-8")
        findings = scope.evaluar_alcance(self.repo, self.control)
        self.assertIn(("ALCANCE-RUTA", "manual.py"), {(f.codigo, f.ubicacion) for f in findings})
        self.assertIn("ALCANCE-CACHE-DIVERGENTE", [f.codigo for f in findings])

    def test_cadena_invalida_todo_queda_fuera_de_alcance(self):
        (self.change_dir / "amendments.jsonl").write_text("{no es json\n", encoding="utf-8")
        # Modificar un archivo que la caché SÍ autorizaba: con cadena inválida ya no vale.
        (self.repo / "openspec" / "dentro.py").write_text("x = 2\n", encoding="utf-8")
        findings = scope.evaluar_alcance(self.repo, self.control)
        pares = {(f.codigo, f.ubicacion) for f in findings}
        self.assertIn(("ALCANCE-RUTA", "openspec/dentro.py"), pares)
        self.assertIn("ALCANCE-ENMIENDA-INVALIDA", [f.codigo for f in findings])

    def test_change_dir_archivado_se_resuelve(self):
        archivo = self.repo / "openspec" / "archive"
        archivo.mkdir(parents=True)
        shutil.move(str(self.change_dir), str(archivo / _CHANGE_ID))
        (archivo / _CHANGE_ID / "amendments.jsonl").write_text("{no es json\n", encoding="utf-8")
        findings = scope.evaluar_alcance(self.repo, self.control)
        self.assertIn("ALCANCE-ENMIENDA-INVALIDA", [f.codigo for f in findings])

    def test_sin_directorio_del_change_usa_la_cache(self):
        control = _control(self.repo, baseline_commit=_head(self.repo), rutas=["openspec/dentro.py"])
        control["change_id"] = "inexistente"
        self.assertEqual(scope.evaluar_alcance(self.repo, control), [])

    def test_control_con_ancla_sin_change_id_es_fail_closed(self):
        control = _control(self.repo, baseline_commit=_head(self.repo), rutas=["openspec/dentro.py"])
        control["alcance"]["scope_hash"] = scope_amendments.hash_alcance(["openspec/dentro.py"])
        (self.repo / "openspec" / "dentro.py").write_text("x = 2\n", encoding="utf-8")
        findings = scope.evaluar_alcance(self.repo, control)
        pares = {(f.codigo, f.ubicacion) for f in findings}
        self.assertIn("ALCANCE-ENMIENDA-INVALIDA", [f.codigo for f in findings])
        self.assertIn(("ALCANCE-RUTA", "openspec/dentro.py"), pares)

    def test_control_con_ancla_y_directorio_inexistente_es_fail_closed(self):
        control = _control(self.repo, baseline_commit=_head(self.repo), rutas=["openspec/dentro.py"])
        control["change_id"] = "inexistente"
        control["alcance"]["scope_hash"] = scope_amendments.hash_alcance(["openspec/dentro.py"])
        findings = scope.evaluar_alcance(self.repo, control)
        self.assertIn("ALCANCE-ENMIENDA-INVALIDA", [f.codigo for f in findings])

    def test_change_dir_explicito_se_usa_tal_cual(self):
        control = _control(self.repo, baseline_commit=_head(self.repo), rutas=["openspec/dentro.py"])
        control["alcance"]["scope_hash"] = scope_amendments.hash_alcance(["openspec/dentro.py"])
        # Sin change_id en el control, pero con change_dir explícito: no es fail-closed.
        self.assertEqual(scope.evaluar_alcance(self.repo, control, change_dir=self.change_dir), [])
        (self.change_dir / "amendments.jsonl").write_text("{no es json\n", encoding="utf-8")
        findings = scope.evaluar_alcance(self.repo, control, change_dir=self.change_dir)
        self.assertIn("ALCANCE-ENMIENDA-INVALIDA", [f.codigo for f in findings])

    def test_legado_sin_ancla_sin_change_id_usa_la_cache(self):
        control = _control(self.repo, baseline_commit=_head(self.repo), rutas=["openspec/dentro.py"])
        self.assertNotIn("scope_hash", control["alcance"])
        (self.repo / "openspec" / "dentro.py").write_text("x = 2\n", encoding="utf-8")
        self.assertEqual(scope.evaluar_alcance(self.repo, control), [])

    def test_unicode_y_espacios_en_ruta_agregada(self):
        nombre = "ñandú nuevo.py"
        (self.repo / nombre).write_text("n = 1\n", encoding="utf-8")
        self.assertIn(nombre, self._ubicaciones_ruta())
        _enmendar(self.change_dir, self.control, add=[nombre])
        self.control["alcance"]["rutas_autorizadas"] = sorted(
            set(self.control["alcance"]["rutas_autorizadas"]) | {nombre})
        self.assertEqual(scope.evaluar_alcance(self.repo, self.control), [])


def _correr_ds_guard(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DS_GUARD), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _crear_change_cerrable_con_archivo_fuera_de_scope(repo: Path, change_id: str, con_sesion: bool) -> None:
    """Repo con un commit inicial (baseline), un archivo `fuera.py` fuera de
    `rutas_autorizadas` tocado y COMMITEADO después del baseline (working tree
    limpio al final -- exactamente el escenario que el IMPORTANT del reviewer
    señaló: `validate --gate cierre` no debe duplicar `ALCANCE-RUTA` para
    este caso, y no debe perderlo cuando `gate_cierre` no llega a correr por
    falta de sesión)."""
    baseline = _head(repo)

    (repo / "fuera.py").write_text("y = 1\n", encoding="utf-8")

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

    control = {
        "schema_version": 1,
        "change_id": change_id,
        "modo": "completo",
        "origen": "test",
        "creado_utc": core.ahora_utc(),
        "baseline": {"commit": baseline, "rama": "main", "capturado_utc": core.ahora_utc()},
        "alcance": {"rutas_autorizadas": [f"openspec/changes/{change_id}/*"]},
        "aprobaciones": [],
        "transiciones": [],
        "sesiones": [],
    }
    if con_sesion:
        sdd.session_start(control, minutos=90)

    core.escribir_control(change_dir / "control.json", control)

    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "cambios del change, incluye fuera.py fuera de scope")


class TestCliValidateGateCierreNoDuplicaAlcanceRuta(unittest.TestCase):
    """Regresión del IMPORTANT de review: `validate --gate cierre` no debe
    reportar `ALCANCE-RUTA` dos veces (una del chequeo inicial en
    `cmd_validate`, otra de `sdd.gate_cierre`, que ya lo incluye
    internamente), y tampoco debe perderlo en la rama donde `gate_cierre` no
    llega a correr (`SESION-AUSENTE`)."""

    def test_con_sesion_activa_alcance_ruta_aparece_una_sola_vez(self):
        repo = _crear_repo()
        try:
            change_id = "20260101-test-gate-cierre"
            _crear_change_cerrable_con_archivo_fuera_de_scope(repo, change_id, con_sesion=True)

            resultado = _correr_ds_guard(
                ["validate", "--change-id", change_id, "--gate", "cierre", "--json"], repo
            )
            payload = json.loads(resultado.stdout)
            hallazgos_alcance_ruta = [
                f for f in payload["findings"]
                if f["codigo"] == "ALCANCE-RUTA" and f.get("ubicacion") == "fuera.py"
            ]
            self.assertEqual(
                len(hallazgos_alcance_ruta),
                1,
                f"Se esperaba exactamente 1 ALCANCE-RUTA para fuera.py, hubo "
                f"{len(hallazgos_alcance_ruta)}: {payload['findings']}",
            )
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_sin_sesion_activa_alcance_ruta_sigue_apareciendo_una_vez(self):
        repo = _crear_repo()
        try:
            change_id = "20260101-test-gate-cierre-sin-sesion"
            _crear_change_cerrable_con_archivo_fuera_de_scope(repo, change_id, con_sesion=False)

            resultado = _correr_ds_guard(
                ["validate", "--change-id", change_id, "--gate", "cierre", "--json"], repo
            )
            payload = json.loads(resultado.stdout)
            codigos = [f["codigo"] for f in payload["findings"]]
            self.assertIn("SESION-AUSENTE", codigos)
            hallazgos_alcance_ruta = [
                f for f in payload["findings"]
                if f["codigo"] == "ALCANCE-RUTA" and f.get("ubicacion") == "fuera.py"
            ]
            self.assertEqual(
                len(hallazgos_alcance_ruta),
                1,
                f"Se esperaba exactamente 1 ALCANCE-RUTA para fuera.py (cobertura preservada "
                f"aunque gate_cierre no corra), hubo {len(hallazgos_alcance_ruta)}: "
                f"{payload['findings']}",
            )
        finally:
            shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
