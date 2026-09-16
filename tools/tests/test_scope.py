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

from dsguard import core, scope, sdd  # noqa: E402

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
