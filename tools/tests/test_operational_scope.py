"""Tests de alcance autorizado, verification.md por defecto, outputs intrínsecos y
hash de pytest (R19, R22-R27, R33-R34, R37-R40 de 20261005-operational-autonomy-hardening, T2).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

import ds_guard  # noqa: E402
from dsguard import repo as repo_mod  # noqa: E402
from dsguard import scope, sdd  # noqa: E402

DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"
_TEMPLATES_ORIGEN = REPO_ORIGEN / ".claude" / "skills" / "lead-data-scientist" / "templates"
_CHANGE_ID = "20261005-test-operational-scope"
_BASE = f"openspec/changes/{_CHANGE_ID}"


def _propuesta(bullets: str, extra: str = "") -> str:
    return (
        "# Propuesta\n\n## Alcance\n- algo no relacionado\n\n"
        f"## Alcance autorizado\n<!-- comentario de plantilla -->\n{bullets}\n\n{extra}"
        "## Motivo de rechazo\n"
    )


def _codigos(hallazgos) -> list:
    return [h.codigo for h in hallazgos]


class TestParsearAlcance(unittest.TestCase):
    def _ok(self, bullets: str) -> list:
        rutas, hall = sdd.parsear_alcance_autorizado(_propuesta(bullets))
        self.assertEqual(hall, [], bullets)
        return rutas

    def _invalido(self, bullets: str) -> None:
        rutas, hall = sdd.parsear_alcance_autorizado(_propuesta(bullets))
        self.assertEqual(_codigos(hall), ["SDD-ALCANCE-INVALIDO"] * len(hall), bullets)
        self.assertTrue(hall, bullets)
        self.assertEqual(rutas, [], bullets)

    def test_sin_seccion_o_sin_bullets(self):
        self.assertEqual(sdd.parsear_alcance_autorizado("# x\n## Alcance\n- a/b.py\n"), ([], []))
        self.assertEqual(sdd.parsear_alcance_autorizado(_propuesta("solo prosa")), ([], []))

    def test_titulo_exacto_no_se_confunde_con_alcance(self):
        texto = "## Alcance\n- tools/x.py\n\n## Fuera de alcance\n- y\n"
        self.assertEqual(sdd.parsear_alcance_autorizado(texto), ([], []))
        texto = "## Alcance autorizado extra\n- tools/x.py\n"
        self.assertEqual(sdd.parsear_alcance_autorizado(texto), ([], []))
        # y el bullet de `## Alcance` no contamina la sección autorizada
        self.assertEqual(self._ok("- tools/a.py"), ["tools/a.py"])

    def test_ruta_exacta_dir_y_glob(self):
        self.assertEqual(
            self._ok("- tools/a.py\n- `tools/dsguard/**`\n- tools/tests/test_x_*.py"),
            ["tools/a.py", "tools/dsguard/**", "tools/tests/test_x_*.py"],
        )

    def test_lineas_no_bullet_ignoradas_y_duplicados(self):
        self.assertEqual(self._ok("texto libre\n- a/b.py\n- a/b.py"), ["a/b.py"])

    def test_bullets_no_soportados_se_rechazan(self):
        self._invalido("* a/b.py")
        self._invalido("+ a/b.py")
        rutas, hall = sdd.parsear_alcance_autorizado(_propuesta("- a/ok.py\n* a/b.py"))
        self.assertEqual(rutas, [])
        self.assertEqual(_codigos(hall), ["SDD-ALCANCE-INVALIDO"])

    def test_rutas_protegidas_y_segmentos_raros(self):
        casos = [
            "- .GIT/config", "- .git./x", "- .Git /x", "- .harmessi/project.json", "- .HARMESSI/**",
            "- .claude/guardrails.json", "- .Claude/Settings.json", "- .claude/settings.local.json",
            "- .claude/**", "- data/raw", "- data/raw/x.csv", "- Data/Raw/x.csv", "- data/**",
            "- a./b.py", "- a/b.", "- a/b :x.py", "- a/b.py:stream", "- a/b./c.py",
        ]
        for caso in casos:
            with self.subTest(caso=caso):
                self._invalido(caso)
        # no deben confundirse con rutas legítimas
        self.assertEqual(self._ok("- .claude/skills/x.md\n- data/processed/x.csv"),
                         [".claude/skills/x.md", "data/processed/x.csv"])

    def test_barra_final_y_normalizacion(self):
        self.assertEqual(self._ok("- tools/dsguard/"), ["tools/dsguard/**"])
        self.assertEqual(self._ok("- ./tools//a.py"), ["tools/a.py"])

    def test_rechazos(self):
        casos = [
            "- ../x.py", "- a/../b.py", "- /etc/passwd", "- C:/x/y.py", "- ~/x", "- a\\b.py",
            "- a b.py", "- a;b", "- a&b", "- a|b", "- a$b", "- a>b", "- a<b", "- a(b)", '- a"b', "- a'b",
            "- a?b", "- a[1].py", "- a{b}", "- a!b",
            "- *", "- **", "- */x", "- **/x.py", "- *.py",
            "- a/**/b", "- a/**b", "- a/b**",
            "- .git/config", "- .git/**",
            "- " + "a" * 261,
        ]
        for caso in casos:
            with self.subTest(caso=caso):
                self._invalido(caso)

    def test_todo_o_nada(self):
        rutas, hall = sdd.parsear_alcance_autorizado(_propuesta("- a/ok.py\n- ../mal.py"))
        self.assertEqual(rutas, [])
        self.assertEqual(len(hall), 1)

    def test_maximo_500_entradas(self):
        ok = "\n".join(f"- d/f{i}.py" for i in range(500))
        self.assertEqual(len(self._ok(ok)), 500)
        self._invalido(ok + "\n- d/extra.py")


class TestSemanticaDirectorio(unittest.TestCase):
    def test_scripts_glob_no_cubre_hermano(self):
        pm = repo_mod.path_matches_any
        self.assertTrue(pm("scripts/a.py", ["scripts/**"]))
        self.assertTrue(pm("scripts/b/c.py", ["scripts/**"]))
        self.assertFalse(pm("scripts_old/a.py", ["scripts/**"]))


class TestOutputsIntrinsecos(unittest.TestCase):
    def test_es_output_intrinseco(self):
        f = scope.es_output_intrinseco
        self.assertTrue(f(".harmessi/executions/x/y.json"))
        self.assertTrue(f(".harmessi\\executions\\x.json"))
        self.assertTrue(f("openspec/decisions/ledger.jsonl"))
        self.assertFalse(f(".harmessi/project.json"))
        self.assertFalse(f(".harmessi/executions"))
        self.assertFalse(f(".harmessi/executions_old/x"))
        self.assertFalse(f("openspec/decisions/otro.jsonl"))
        self.assertFalse(f("tools/ds_guard.py"))

    def test_evaluar_alcance_exenta_solo_intrinsecos(self):
        sucios = [
            ".harmessi/executions/a.json",
            "openspec/decisions/ledger.jsonl",
            ".harmessi/project.json",
            "tools/fuera.py",
            "tools/dentro.py",
        ]
        control = {"alcance": {"rutas_autorizadas": ["tools/dentro.py"]}}
        with mock.patch.object(repo_mod, "list_dirty_files", return_value=sucios):
            hall = scope.evaluar_alcance(Path("."), control)
        self.assertEqual(
            sorted(h.ubicacion if hasattr(h, "ubicacion") else h.mensaje for h in hall),
            sorted([".harmessi/project.json", "tools/fuera.py"]),
        )
        self.assertEqual(set(_codigos(hall)), {"ALCANCE-RUTA"})


def _crear_repo_git_temporal() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="op_scope_"))
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)
    (repo / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    shutil.copytree(_TEMPLATES_ORIGEN, repo / ".claude" / "skills" / "lead-data-scientist" / "templates")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=str(repo), check=True)
    return repo


def _cli(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DS_GUARD), *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8"
    )


class _BaseCli(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        r = _cli(["init", "--change-id", _CHANGE_ID, "--modo", "completo"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _ruta_control(self) -> Path:
        return self.repo / "openspec" / "changes" / _CHANGE_ID / "control.json"

    def _control(self) -> dict:
        return json.loads(self._ruta_control().read_text(encoding="utf-8"))

    def _escribir_propuesta(self, texto: str) -> None:
        (self.repo / "openspec" / "changes" / _CHANGE_ID / "proposal.md").write_text(texto, encoding="utf-8")

    def _aprobar(self) -> subprocess.CompletedProcess:
        return _cli(
            ["approve", "--change-id", _CHANGE_ID, "--artefacto", "proposal.md", "--usuario", "Tester",
             "--fecha", "2026-10-05", "--alcance", "test", "--cita", "ok"],
            self.repo,
        )

    def _rutas(self) -> list:
        return self._control()["alcance"]["rutas_autorizadas"]


class TestInit(_BaseCli):
    def test_init_incluye_verification_md_sin_crearlo(self):
        rutas = self._rutas()
        self.assertIn(f"{_BASE}/verification.md", rutas)
        self.assertIn(f"{_BASE}/control.json", rutas)
        for nombre in ("proposal.md", "tasks.md", "spec.md", "design.md"):
            self.assertIn(f"{_BASE}/{nombre}", rutas)
        self.assertFalse((self.repo / "openspec" / "changes" / _CHANGE_ID / "verification.md").exists())

    def test_plantilla_tiene_seccion(self):
        texto = (_TEMPLATES_ORIGEN / "proposal.md").read_text(encoding="utf-8")
        self.assertIn("## Alcance autorizado", texto)
        self.assertLess(texto.index("## Alcance autorizado"), texto.index("## Motivo de rechazo"))
        # la plantilla recién creada no declara bullets: el parser no devuelve nada
        self.assertEqual(sdd.parsear_alcance_autorizado(texto), ([], []))


class TestApprove(_BaseCli):
    def test_sin_seccion_no_toca_alcance(self):
        self._escribir_propuesta("# P\n\n## Alcance\n- x\n")
        previo = self._rutas()
        self.assertEqual(self._aprobar().returncode, 0)
        self.assertEqual(self._rutas(), previo)

    def test_seccion_sin_bullets_no_toca_alcance(self):
        self._escribir_propuesta(_propuesta("solo prosa"))
        previo = self._rutas()
        self.assertEqual(self._aprobar().returncode, 0)
        self.assertEqual(self._rutas(), previo)

    def test_materializa_defaults_union_declaradas_ordenado(self):
        self._escribir_propuesta(_propuesta("- tools/z.py\n- tools/a/**\n- tools/z.py"))
        r = self._aprobar()
        self.assertEqual(r.returncode, 0, r.stderr)
        rutas = self._rutas()
        self.assertEqual(rutas, sorted(set(rutas)))
        for esperado in ("tools/z.py", "tools/a/**", f"{_BASE}/verification.md", f"{_BASE}/control.json",
                         f"{_BASE}/proposal.md"):
            self.assertIn(esperado, rutas)
        self.assertIn("+ tools/z.py", r.stdout)

    def test_idempotente(self):
        self._escribir_propuesta(_propuesta("- tools/z.py"))
        self.assertEqual(self._aprobar().returncode, 0)
        primera = self._rutas()
        r = self._aprobar()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self._rutas(), primera)
        self.assertNotIn("  + ", r.stdout)
        self.assertNotIn("  - ", r.stdout)

    def test_reemplaza_e_informa_retirados(self):
        self._escribir_propuesta(_propuesta("- tools/uno.py"))
        self.assertEqual(self._aprobar().returncode, 0)
        self._escribir_propuesta(_propuesta("- tools/dos.py"))
        r = self._aprobar()
        self.assertEqual(r.returncode, 0, r.stderr)
        rutas = self._rutas()
        self.assertIn("tools/dos.py", rutas)
        self.assertNotIn("tools/uno.py", rutas)
        self.assertIn("- tools/uno.py", r.stdout)
        self.assertIn("+ tools/dos.py", r.stdout)

    def test_seccion_invalida_rechaza_sin_escribir(self):
        self._escribir_propuesta(_propuesta("- tools/ok.py\n- ../mal.py"))
        antes = self._ruta_control().read_bytes()
        r = self._aprobar()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("SDD-ALCANCE-INVALIDO", r.stderr)
        self.assertEqual(self._ruta_control().read_bytes(), antes)

    def test_aplica_en_modo_checkpoints(self):
        r = _cli(["init", "--change-id", "20261005-test-scope-ckpt", "--modo", "completo",
                  "--approval-mode", "checkpoints"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        ruta = self.repo / "openspec" / "changes" / "20261005-test-scope-ckpt" / "proposal.md"
        ruta.write_text(_propuesta("- tools/ckpt.py"), encoding="utf-8")
        r = _cli(["approve", "--change-id", "20261005-test-scope-ckpt", "--artefacto", "proposal.md",
                  "--usuario", "Tester", "--fecha", "2026-10-05", "--alcance", "t", "--cita", "c"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        control = json.loads(
            (ruta.parent / "control.json").read_text(encoding="utf-8")
        )
        self.assertIn("tools/ckpt.py", control["alcance"]["rutas_autorizadas"])

    def test_materializado_cubre_validate_con_dir_glob(self):
        self._escribir_propuesta(_propuesta("- tools/nuevo/**"))
        self.assertEqual(self._aprobar().returncode, 0)
        (self.repo / "tools" / "nuevo").mkdir(parents=True)
        (self.repo / "tools" / "nuevo" / "a.py").write_text("x = 1\n", encoding="utf-8")
        (self.repo / "tools" / "nuevo_old.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(self.repo), check=True)
        r = _cli(["status", "--change-id", _CHANGE_ID, "--json"], self.repo)
        fuera = json.loads(r.stdout)["fuera_de_alcance"]
        self.assertNotIn("tools/nuevo/a.py", fuera)
        self.assertIn("tools/nuevo_old.py", fuera)


class TestStatusOutputsIntrinsecos(_BaseCli):
    def test_status_exenta_executions_y_ledger_pero_no_project_ni_funcional(self):
        for rel in (".harmessi/executions/x/out.json", "openspec/decisions/ledger.jsonl",
                    ".harmessi/project.json", "tools/funcional.py"):
            destino = self.repo / rel
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text("{}\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(self.repo), check=True)
        r = _cli(["status", "--change-id", _CHANGE_ID, "--json"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        fuera = json.loads(r.stdout)["fuera_de_alcance"]
        self.assertNotIn(".harmessi/executions/x/out.json", fuera)
        self.assertNotIn("openspec/decisions/ledger.jsonl", fuera)
        self.assertIn(".harmessi/project.json", fuera)
        self.assertIn("tools/funcional.py", fuera)


class TestHashPytest(unittest.TestCase):
    def _hash(self, interprete: str) -> str:
        args = argparse.Namespace(interpreter=interprete, paths=["tools/tests/test_x.py"], pytest_args=["-q"])
        spec = ds_guard._construir_exec_pytest(args, Path("."))
        self.assertEqual(spec.argv[0], interprete)  # la ejecución usa el valor provisto
        return spec.hash_comando

    @unittest.skipUnless(os.name == "nt", "mayúsculas/minúsculas equivalentes solo en Windows")
    def test_estable_ante_mayusculas_y_separadores(self):
        base = self._hash(sys.executable)
        self.assertEqual(self._hash(sys.executable.upper()), base)
        self.assertEqual(self._hash(sys.executable.lower()), base)
        self.assertEqual(self._hash(sys.executable.replace("\\", "/")), base)

    @unittest.skipUnless(os.name == "nt", "intérprete crudo distinto del normalizado solo en Windows")
    def test_hash_legacy_crudo_cuando_difiere(self):
        crudo = sys.executable.upper()
        args = argparse.Namespace(interpreter=crudo, paths=["tools/tests/test_x.py"], pytest_args=["-q"])
        spec = ds_guard._construir_exec_pytest(args, Path("."))
        self.assertIsNotNone(spec.hash_legacy)
        self.assertNotEqual(spec.hash_legacy, spec.hash_comando)
        # si el intérprete ya viene normalizado, no hay legacy
        from leadrun import allowlist

        norm = argparse.Namespace(
            interpreter=allowlist.normalizar_interprete(sys.executable),
            paths=["tools/tests/test_x.py"], pytest_args=["-q"],
        )
        self.assertIsNone(ds_guard._construir_exec_pytest(norm, Path(".")).hash_legacy)

    @unittest.skipUnless(os.name == "nt", "intérprete crudo distinto del normalizado solo en Windows")
    def test_aprobacion_previa_con_hash_crudo_sigue_resolviendo(self):
        crudo = sys.executable.upper()
        args = argparse.Namespace(interpreter=crudo, paths=["tools/tests/test_x.py"], pytest_args=["-q"])
        spec = ds_guard._construir_exec_pytest(args, Path("."))
        control = {"aprobaciones": [{
            "artefacto": spec.artefacto, "algoritmo": spec.algoritmo, "hash": spec.hash_legacy,
            "registrado_utc": "2026-01-01T00:00:00Z",
        }]}
        repo = Path(tempfile.mkdtemp(prefix="op_scope_aprob_"))
        try:
            ok, _por, _modo, _aprob, motivo = ds_guard._resolver_aprobacion_exec(
                repo, control, spec.artefacto, spec.hash_comando, spec.hash_legacy
            )
            self.assertTrue(ok, motivo)
            # un hash cualquiera sigue sin valer
            control["aprobaciones"][0]["hash"] = "0" * 64
            ok, *_resto = ds_guard._resolver_aprobacion_exec(
                repo, control, spec.artefacto, spec.hash_comando, spec.hash_legacy
            )
            self.assertFalse(ok)
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_interprete_distinto_cambia_hash(self):
        self.assertNotEqual(self._hash(sys.executable), self._hash(sys.executable + "_otro"))

    def test_igual_al_valor_previo_con_interprete_normalizado(self):
        from leadrun import allowlist, core as leadrun_core

        norm = allowlist.normalizar_interprete(sys.executable)
        args = argparse.Namespace(interpreter=norm, paths=["tools/tests/test_x.py"], pytest_args=["-q"])
        previo = leadrun_core.content_sha256([norm, "-m", "pytest", "tools/tests/test_x.py", "-q"])
        self.assertEqual(ds_guard._construir_exec_pytest(args, Path(".")).hash_comando, previo)


class TestCierreCiclo2(unittest.TestCase):
    """Precisiones del ciclo 2 del reviewer."""

    def test_data_raw_solo_rechaza_el_directorio_exacto(self):
        nl = chr(10)
        rutas, hallazgos = sdd.parsear_alcance_autorizado(
            nl.join(["## Alcance autorizado", "", "- data/raw_features/x.csv", "- data/rawdata/x.csv", ""])
        )
        self.assertEqual(hallazgos, [])
        self.assertEqual(sorted(rutas), ["data/raw_features/x.csv", "data/rawdata/x.csv"])
        for malo in ("data/raw", "data/raw/x.csv", "Data/Raw/x.csv"):
            _r, h = sdd.parsear_alcance_autorizado(nl.join(["## Alcance autorizado", "", f"- {malo}", ""]))
            self.assertTrue(h, malo)

    def test_outputs_intrinsecos_no_quedan_autorizados_para_exec(self):
        # R39: se excluyen del evaluador de scope, pero NO autorizan `exec`.
        from leadrun import allowlist

        alcance = ("openspec/changes/x/**",)
        for ruta in (".harmessi/executions/pytest__abc/record.json", "openspec/decisions/ledger.jsonl"):
            self.assertTrue(scope.es_output_intrinseco(ruta))
            self.assertFalse(allowlist._coincide_alcance(ruta, alcance))
            ok, _f, _m = allowlist.evaluar_comando(
                [sys.executable, ruta], alcance, allowlist.normalizar_interprete(sys.executable)
            )
            self.assertFalse(ok)

    def test_pytest_a_directorio_con_dir_doble_asterisco(self):
        from leadrun import allowlist

        ok, forma, _m = allowlist.evaluar_comando(
            [sys.executable, "-m", "pytest", "tools/tests"],
            ("tools/tests/**",),
            allowlist.normalizar_interprete(sys.executable),
        )
        self.assertTrue(ok, _m)
        self.assertEqual(forma, "pytest")


if __name__ == "__main__":
    unittest.main()
