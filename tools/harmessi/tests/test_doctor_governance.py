"""Tests de `doctor._check_governance` (Change 20261005, T5; R53-R58, tabla R55).

`tools.cards.discovery` se simula con reportes sintéticos (mismos nombres que el
contrato D de `interfaces.md`) para no depender del contenido real de Cards."""
from __future__ import annotations

import contextlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import tools.cards as cards_pkg
from tools.ds_init import control as control_mod
from tools.dsguard import checks
from tools.harmessi import doctor as doctor_mod
from tools.harmessi.tests.test_doctor import (
    _crear_interprete_falso,
    _crear_repo_git_temporal,
    _instalar_harness_real,
    _mock_solo_interprete,
)

CAPS_HISTORICA = "predictive_modeling"


def _reporte(kind="data", status="complete", card_id="c1", anchors=(), findings=()):
    return SimpleNamespace(
        kind=kind,
        rel_path=f"governance/cards/{kind}/{card_id}.json",
        card_id=card_id,
        status=status,
        anchors=tuple(anchors),
        findings=tuple(findings),
    )


def _gobierno(state="resolved", codigos=()):
    return SimpleNamespace(
        state=state,
        project_hardening_path="governance/policy/model-risk-hardening.json",
        findings=tuple(SimpleNamespace(code=c, path="", detail="") for c in codigos),
    )


@contextlib.contextmanager
def _discovery_falso(reportes=(), gobierno=None):
    """Reemplaza `tools.cards.discovery` por un doble con `validar_proyecto`."""
    falso = SimpleNamespace(
        validar_proyecto=lambda repo_root, kinds=None, paths=None: SimpleNamespace(
            reports=tuple(reportes), governance=gobierno, notes=()
        )
    )
    with patch.dict(sys.modules, {"tools.cards.discovery": falso}):
        with patch.object(cards_pkg, "discovery", falso, create=True):
            yield falso


def _por_codigo(resultados, codigo):
    return [r for r in resultados if r.code == codigo]


class _Base(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="doctor_gov_"))

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def control(self, caps="legacy", archivos=None):
        datos = {"archivos": archivos or []}
        if caps != "legacy":
            datos["capabilities_habilitadas"] = list(caps)
        return datos

    def escribir(self, ruta_rel, contenido="{}"):
        ruta = self.repo / ruta_rel
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(contenido, encoding="utf-8")
        return ruta

    def check(self, control, reportes=(), gobierno=None, etapa=None):
        with _discovery_falso(reportes, gobierno), patch.object(
            doctor_mod, "_gov_project_stage", return_value=etapa
        ):
            return doctor_mod._check_governance(self.repo, control)


class TestCapabilities(_Base):
    def test_ninguna_opt_in_habilitada_na(self):
        r = self.check(self.control([CAPS_HISTORICA]))
        self.assertEqual({x.status for x in _por_codigo(r, "HARMESSI-GOV-CAPABILITY")}, {checks.STATUS_NA})

    def test_legacy_sin_lista_opt_in_deshabilitadas(self):
        r = self.check(self.control("legacy"))
        self.assertEqual({x.status for x in _por_codigo(r, "HARMESSI-GOV-CAPABILITY")}, {checks.STATUS_NA})
        self.assertFalse(any(x.status != checks.STATUS_NA for x in r))

    def test_model_governance_sin_predictive_modeling_error(self):
        r = self.check(self.control(["model_governance"]))
        self.assertEqual({x.status for x in _por_codigo(r, "HARMESSI-GOV-CAPABILITY-INVALID")}, {checks.STATUS_FAIL})

    def test_capability_desconocida_warn_nunca_error(self):
        r = self.check(self.control([CAPS_HISTORICA, "inventada"]))
        self.assertEqual({x.status for x in _por_codigo(r, "HARMESSI-GOV-CAPABILITY-UNKNOWN")}, {checks.STATUS_WARN})
        self.assertNotIn(checks.STATUS_FAIL, {x.status for x in r})

    def test_installed_but_disabled_na(self):
        self.escribir("tools/cards/datacard.py", "")
        r = self.check(self.control([CAPS_HISTORICA]))
        self.assertEqual({x.status for x in _por_codigo(r, "HARMESSI-GOV-INSTALLED-DISABLED")}, {checks.STATUS_NA})

    def test_content_disabled_na_sin_validar(self):
        self.escribir("governance/cards/data/x.json")
        with _discovery_falso() as falso:
            falso.validar_proyecto = lambda *a, **k: self.fail("no debe validar contenido deshabilitado")
            r = doctor_mod._check_governance(self.repo, self.control([CAPS_HISTORICA]))
        self.assertEqual({x.status for x in _por_codigo(r, "HARMESSI-GOV-CONTENT-DISABLED")}, {checks.STATUS_NA})


class TestNone(_Base):
    def test_none_warn_en_production_candidate_y_production(self):
        for etapa in ("production_candidate", "production"):
            r = self.check(self.control([CAPS_HISTORICA, "data_cards"]), etapa=etapa)
            self.assertEqual({x.status for x in _por_codigo(r, "HARMESSI-GOV-NONE")}, {checks.STATUS_WARN}, etapa)

    def test_none_na_en_otros_casos(self):
        for etapa in (None, "discovery", "experiment", "validated_model"):
            r = self.check(self.control([CAPS_HISTORICA, "data_cards"]), etapa=etapa)
            self.assertEqual({x.status for x in _por_codigo(r, "HARMESSI-GOV-NONE")}, {checks.STATUS_NA}, etapa)

    def test_none_message_frase_requisitos(self):
        r = self.check(self.control([CAPS_HISTORICA, "data_cards"]), etapa="production")
        self.assertIn("card governance requirements not satisfied", r[-1].message)


class TestConfig(_Base):
    CAPS = [CAPS_HISTORICA, "model_governance"]

    def test_config_invalid_error(self):
        r = self.check(self.control(self.CAPS), gobierno=_gobierno("invalid", ["GOVCFG-RELAXATION"]))
        self.assertEqual({x.status for x in _por_codigo(r, "HARMESSI-GOV-CONFIG-INVALID")}, {checks.STATUS_FAIL})

    def test_config_unresolvable_warn(self):
        r = self.check(self.control(self.CAPS), gobierno=_gobierno("unresolvable", ["GOVCFG-UNRESOLVABLE"]))
        self.assertEqual({x.status for x in _por_codigo(r, "HARMESSI-GOV-CONFIG-UNRESOLVABLE")}, {checks.STATUS_WARN})

    def test_config_resuelta_no_emite_fila_de_config(self):
        r = self.check(self.control(self.CAPS), gobierno=_gobierno("resolved"))
        self.assertFalse([x for x in r if x.code.startswith("HARMESSI-GOV-CONFIG")])


class TestCards(_Base):
    CAPS = [CAPS_HISTORICA, "data_cards", "model_governance"]

    def test_filas_por_estado_de_card(self):
        esperado = {
            "invalid": ("HARMESSI-GOV-CARD-INVALID", checks.STATUS_FAIL),
            "stale": ("HARMESSI-GOV-CARD-STALE", checks.STATUS_WARN),
            "incomplete": ("HARMESSI-GOV-CARD-INCOMPLETE", checks.STATUS_WARN),
            "complete": ("HARMESSI-GOV-CARD-COMPLETE", checks.STATUS_PASS),
        }
        for kind in ("data", "model"):
            for estado, (codigo, status) in esperado.items():
                r = self.check(self.control(self.CAPS), [_reporte(kind, estado)])
                self.assertEqual({x.status for x in _por_codigo(r, codigo)}, {status}, (kind, estado))

    def test_filas_por_estado_de_assessment(self):
        esperado = {
            "invalid": ("HARMESSI-GOV-CARD-INVALID", checks.STATUS_FAIL),
            "stale": ("HARMESSI-GOV-ASSESSMENT-STALE", checks.STATUS_WARN),
            "incomplete": ("HARMESSI-GOV-ASSESSMENT-INCOMPLETE", checks.STATUS_WARN),
            "complete": ("HARMESSI-GOV-ASSESSMENT-COMPLETE", checks.STATUS_PASS),
        }
        for estado, (codigo, status) in esperado.items():
            r = self.check(self.control(self.CAPS), [_reporte("governance", estado)])
            self.assertEqual({x.status for x in _por_codigo(r, codigo)}, {status}, estado)

    def test_stale_e_incomplete_nunca_error(self):
        for estado in ("stale", "incomplete"):
            r = self.check(self.control(self.CAPS), [_reporte("data", estado), _reporte("governance", estado)])
            self.assertNotIn(checks.STATUS_FAIL, {x.status for x in r})

    def test_anchor_unverified_warn_por_estado_de_ancla_y_por_hallazgo(self):
        for ancla, hallazgo in (({"state": "missing"}, None), ({"resolution": {"state": "stale"}}, None),
                                 (None, {"code": "ANCHOR-UNRESOLVABLE"})):
            rep = _reporte("model", "incomplete", anchors=[ancla] if ancla else [],
                           findings=[hallazgo] if hallazgo else [])
            r = self.check(self.control(self.CAPS), [rep])
            self.assertEqual({x.status for x in _por_codigo(r, "HARMESSI-GOV-ANCHOR-UNVERIFIED")}, {checks.STATUS_WARN})

    def test_ancla_verified_no_emite_unverified(self):
        r = self.check(self.control(self.CAPS), [_reporte("data", "complete", anchors=[{"state": "verified"}])])
        self.assertFalse(_por_codigo(r, "HARMESSI-GOV-ANCHOR-UNVERIFIED"))

    def test_complete_incluye_aclaracion_y_nunca_aprobado(self):
        for kind in ("data", "model", "governance"):
            r = self.check(self.control(self.CAPS), [_reporte(kind, "complete")])
            ok = [x for x in r if x.status == checks.STATUS_PASS]
            self.assertTrue(ok)
            for x in ok:
                self.assertIn("complete ≠ éticamente aceptable/seguro/justo/compliant", x.message)
                self.assertNotIn("aprobado", x.message.lower())

    def test_mensajes_sin_autonomia_ni_ejecucion_y_con_frase(self):
        reportes = [_reporte(k, e) for k in ("data", "governance") for e in ("invalid", "stale", "incomplete", "complete")]
        r = self.check(self.control(self.CAPS), reportes, gobierno=_gobierno("invalid", ["GOVCFG-INVALID"]))
        for x in r:
            bajo = x.message.lower()
            for prohibido in ("autonom", "ejecu", "stop"):
                self.assertNotIn(prohibido, bajo, x.message)
            if x.code.startswith(("HARMESSI-GOV-CARD-", "HARMESSI-GOV-ASSESSMENT-")) and x.status != checks.STATUS_PASS:
                self.assertIn("card governance requirements not satisfied", x.message)

    def test_valores_de_usuario_se_escapan(self):
        r = self.check(self.control(self.CAPS), [_reporte("data", "stale", card_id="a\x1b[31mb" + "x" * 500)])
        msg = _por_codigo(r, "HARMESSI-GOV-CARD-STALE")[0].message
        self.assertNotIn("\x1b", msg)
        self.assertLess(len(msg), 600)


class TestToolingYOwnership(_Base):
    def test_import_de_cards_falla_warn_tooling(self):
        with patch.dict(sys.modules, {"tools.cards": None}):
            r = doctor_mod._check_governance(self.repo, self.control([CAPS_HISTORICA, "data_cards"]))
        self.assertEqual({x.status for x in _por_codigo(r, "HARMESSI-GOV-TOOLING")}, {checks.STATUS_WARN})
        self.assertNotIn(checks.STATUS_FAIL, {x.status for x in r})

    def test_ownership_warn_si_archivos_lista_governance(self):
        ctl = self.control([CAPS_HISTORICA], archivos=[{"ruta": "governance/cards/data/a.json", "sha256": "x"},
                                                         {"ruta": "tools/x.py", "sha256": "y"}])
        r = self.check(ctl)
        own = _por_codigo(r, "HARMESSI-GOV-OWNERSHIP")
        self.assertEqual([x.status for x in own], [checks.STATUS_WARN])

    def test_sin_ownership_si_archivos_no_lista_governance(self):
        r = self.check(self.control([CAPS_HISTORICA], archivos=[{"ruta": "tools/x.py", "sha256": "y"}]))
        self.assertFalse(_por_codigo(r, "HARMESSI-GOV-OWNERSHIP"))

    def test_control_none_na(self):
        r = doctor_mod._check_governance(self.repo, None)
        self.assertEqual({x.status for x in r}, {checks.STATUS_NA})


class TestSinDrift(_Base):
    def test_governance_no_produce_drift(self):
        gestionado = self.escribir("tools/x.py", "x = 1\n")
        ctl = self.control([CAPS_HISTORICA], archivos=[
            {"ruta": "tools/x.py", "sha256": control_mod.sha256_de_archivo(gestionado)}])
        self.escribir("governance/cards/data/a.json", '{"v": 1}')
        antes = doctor_mod._check_hashes_drift(self.repo, ctl)
        self.escribir("governance/cards/data/a.json", '{"v": 2}')  # modificado
        self.escribir("governance/model-risk/nuevo.json")  # creado después
        despues = doctor_mod._check_hashes_drift(self.repo, ctl)
        self.assertEqual({x.status for x in antes}, {checks.STATUS_PASS})
        self.assertEqual({x.status for x in despues}, {checks.STATUS_PASS})
        self.assertEqual([x.code for x in despues], ["HARMESSI-DRIFT"])

    def test_check_es_solo_lectura(self):
        self.escribir("governance/cards/data/a.json")
        antes = sorted(p.relative_to(self.repo).as_posix() for p in self.repo.rglob("*"))
        self.check(self.control([CAPS_HISTORICA, "data_cards"]), [_reporte("data", "complete")])
        despues = sorted(p.relative_to(self.repo).as_posix() for p in self.repo.rglob("*"))
        self.assertEqual(antes, despues)


class TestEjecutarExitCode(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal(prefix="doctor_gov_exec_")
        _instalar_harness_real(self.repo)
        _crear_interprete_falso(self.repo)
        ruta = self.repo / ".ds_init" / "control.json"
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["capabilities_habilitadas"] = [CAPS_HISTORICA, "data_cards"]
        ruta.write_text(json.dumps(datos), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _ejecutar(self, reportes):
        with _discovery_falso(reportes), patch(
            "tools.harmessi.doctor.subprocess.run", side_effect=_mock_solo_interprete(0, "")
        ):
            return doctor_mod.ejecutar(self.repo)

    def test_warn_y_na_no_cambian_exit_code(self):
        resultados, codigo = self._ejecutar([_reporte("data", "stale")])
        self.assertEqual(codigo, 0)
        gov = [r for r in resultados if r.codigo.startswith("HARMESSI-GOV-")]
        self.assertTrue(any(r.nivel == doctor_mod.NIVEL_WARN for r in gov))
        self.assertTrue(all(r.seccion == doctor_mod.SECCION_HARMESSI for r in gov))

    def test_error_de_governance_da_exit_1(self):
        resultados, codigo = self._ejecutar([_reporte("data", "invalid")])
        self.assertEqual(codigo, 1)
        self.assertIn("HARMESSI-GOV-CARD-INVALID", {r.codigo for r in resultados if r.nivel == doctor_mod.NIVEL_ERROR})

    def test_excepcion_en_governance_se_convierte_en_error_excepcion(self):
        with patch.object(doctor_mod, "_check_governance", side_effect=RuntimeError("boom")), patch(
            "tools.harmessi.doctor.subprocess.run", side_effect=_mock_solo_interprete(0, "")
        ):
            resultados, codigo = doctor_mod.ejecutar(self.repo)
        self.assertEqual(codigo, 1)
        self.assertIn("HARMESSI-GOV-EXCEPCION", {r.codigo for r in resultados})

    def test_complete_da_ok_y_exit_0(self):
        resultados, codigo = self._ejecutar([_reporte("data", "complete")])
        self.assertEqual(codigo, 0)
        ok = [r for r in resultados if r.codigo == "HARMESSI-GOV-CARD-COMPLETE"]
        self.assertEqual([r.nivel for r in ok], [doctor_mod.NIVEL_OK])
        self.assertNotIn("aprobado", ok[0].mensaje.lower())


def _commit_todo(repo: Path, mensaje: str):
    import subprocess

    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", mensaje], capture_output=True, check=True)


class TestInstalacionRealPorCli(unittest.TestCase):
    """I1/I2 (R78): instalación real por la CLI de ds_init + Doctor."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal(prefix="doctor_gov_cli_")
        self.out = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.out.cleanup()
        shutil.rmtree(self.repo, ignore_errors=True)

    def _cli(self, *args):
        import io
        from contextlib import redirect_stderr, redirect_stdout

        from tools.ds_init.cli import main

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return main(list(args))

    def _doctor(self):
        _crear_interprete_falso(self.repo)
        with patch("tools.harmessi.doctor.subprocess.run", side_effect=_mock_solo_interprete(0, "")):
            return doctor_mod.ejecutar(self.repo)

    def test_install_por_defecto_conserva_resumen_legacy(self):
        codigo = self._cli("install", "--destino", str(self.repo), "--nombre", "p", "--execute")
        self.assertEqual(codigo, 0)
        resultados, exit_code = self._doctor()
        self.assertEqual(exit_code, 0)
        self.assertIn("HARMESSI-ARCHIVOS-ESPERADOS", {r.codigo for r in resultados if r.nivel == doctor_mod.NIVEL_OK})
        self.assertNotIn("HARMESSI-CAPABILITY-DISABLED", {r.codigo for r in resultados})
        na = {r.codigo for r in resultados if r.nivel == "N/A"}
        self.assertLessEqual(na, {"HARMESSI-GOV-CAPABILITY", "HARMESSI-INSTALLATION-STAGE"})
        self.assertIn("HARMESSI-GOV-CAPABILITY", na)
        self.assertNotIn(doctor_mod.NIVEL_ERROR, {r.nivel for r in resultados})

    def test_enable_y_luego_disable_data_cards_sin_ownership_espurio(self):
        base = ("--destino", str(self.repo), "--stage", "discovery", "--execute")
        self.assertEqual(self._cli("install", "--nombre", "p", "--enable-capability", "data_cards", *base), 0)
        _commit_todo(self.repo, "install con data_cards")
        self.assertEqual(self._cli("sync", "--disable-capability", "data_cards", *base), 0)
        self.assertTrue((self.repo / "tools" / "cards" / "datacard.py").exists())  # disable no borra

        resultados, _ = self._doctor()
        codigos = {r.codigo for r in resultados}
        self.assertIn("HARMESSI-GOV-INSTALLED-DISABLED", codigos)
        na = {r.codigo for r in resultados if r.nivel == "N/A"}
        self.assertIn("HARMESSI-GOV-INSTALLED-DISABLED", na)
        espurios = [
            r for r in resultados
            if r.codigo == "HARMESSI-OWNERSHIP-USUARIO" and "tools/cards" in (r.ubicacion or "")
        ]
        self.assertEqual(espurios, [])
        self.assertNotIn("HARMESSI-DRIFT-FALTANTE", codigos)


if __name__ == "__main__":
    unittest.main()
