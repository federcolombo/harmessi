"""Tests de `tools.dsguard.decision` (Bloque 5, `20260910-decision-ledger-
bounded-remediation`): ledger de decisiones append-only en
`openspec/decisions/ledger.jsonl`.

Llamadas directas a las funciones sobre un directorio temporal (sin git,
igual que `TestKddInit` en `test_kdd.py`): estas funciones no dependen de
Git para nada.
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

from dsguard import core, decision  # noqa: E402

DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"


def _correr_ds_guard(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DS_GUARD), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _crear_repo_git_temporal(prefix: str = "decision_cli_test_") -> Path:
    repo = Path(tempfile.mkdtemp(prefix=prefix))
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    return repo


def _crear_dir_temporal(prefix: str = "decision_test_") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


class TestDecisionAdd(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_add_crea_primera_linea_con_seq_0_y_campos_r2(self):
        ok, findings = decision.decision_add(
            self.repo,
            "20260910-target-inicial",
            "target",
            "Definición del target",
            "Porque sí",
            "federico",
            "2026-09-10",
            "cita literal",
            change_id="20260910-cambio-x",
            kdd_etapa="modeling",
            evidencia=["openspec/changes/20260910-cambio-x/design.md"],
        )
        self.assertTrue(ok)
        self.assertEqual(findings, [])

        entradas, findings_lectura = decision.leer_entradas(decision.ledger_path(self.repo))
        self.assertEqual(findings_lectura, [])
        self.assertEqual(len(entradas), 1)
        entrada = entradas[0]
        self.assertEqual(entrada["seq"], 0)
        self.assertEqual(entrada["decision_id"], "20260910-target-inicial")
        self.assertEqual(entrada["accion"], "registrar")
        self.assertIsNone(entrada["referencia"])
        self.assertEqual(entrada["tipo"], "target")
        self.assertEqual(entrada["resumen"], "Definición del target")
        self.assertEqual(entrada["rationale"], "Porque sí")
        self.assertEqual(entrada["change_id"], "20260910-cambio-x")
        self.assertEqual(entrada["kdd_etapa"], "modeling")
        self.assertEqual(entrada["evidencia"], ["openspec/changes/20260910-cambio-x/design.md"])
        self.assertEqual(entrada["aprobado_por"], "federico")
        self.assertEqual(entrada["fecha_aprobacion"], "2026-09-10")
        self.assertEqual(entrada["cita"], "cita literal")
        self.assertEqual(entrada["registrado_por"], "lead")
        self.assertEqual(entrada["schema_version"], decision.SCHEMA_VERSION_SOPORTADA)
        self.assertIn("utc", entrada)

    def test_dos_add_sucesivos_conservan_la_primera_linea_byte_a_byte(self):
        decision.decision_add(
            self.repo, "20260910-a", "target", "r", "rat", "u", "f", "c"
        )
        path = decision.ledger_path(self.repo)
        primera_linea_bytes = path.read_bytes().splitlines()[0]

        decision.decision_add(
            self.repo, "20260910-b", "baseline", "r2", "rat2", "u", "f", "c"
        )
        segunda_lectura = path.read_bytes().splitlines()
        self.assertEqual(segunda_lectura[0], primera_linea_bytes)
        self.assertEqual(len(segunda_lectura), 2)

    def test_add_con_decision_id_duplicado_se_rehusa(self):
        decision.decision_add(self.repo, "20260910-a", "target", "r", "rat", "u", "f", "c")
        antes = core.capturar_bytes(decision.ledger_path(self.repo))

        ok, findings = decision.decision_add(self.repo, "20260910-a", "baseline", "r2", "rat2", "u", "f", "c")
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "DECISION-ID-DUPLICADO")
        self.assertEqual(core.capturar_bytes(decision.ledger_path(self.repo)), antes)

    def test_add_con_campo_vacio_se_rehusa(self):
        ok, findings = decision.decision_add(self.repo, "", "target", "", "rat", "u", "f", "c")
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "DECISION-CAMPO-VACIO")

    def test_add_con_tipo_invalido_se_rehusa(self):
        ok, findings = decision.decision_add(self.repo, "20260910-a", "no_existe", "r", "rat", "u", "f", "c")
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "DECISION-TIPO-INVALIDO")

    def test_add_con_kdd_etapa_desconocida_se_rehusa(self):
        ok, findings = decision.decision_add(
            self.repo, "20260910-a", "target", "r", "rat", "u", "f", "c", kdd_etapa="no_existe"
        )
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "KDD-ETAPA-DESCONOCIDA")

    def test_add_sobre_ledger_corrupto_se_rehusa_entero_y_no_escribe_nada(self):
        path = decision.ledger_path(self.repo)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("esto no es json\n", encoding="utf-8")
        antes = core.capturar_bytes(path)

        ok, findings = decision.decision_add(self.repo, "20260910-a", "target", "r", "rat", "u", "f", "c")
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "DECISION-LEDGER-CORRUPTO")
        self.assertEqual(core.capturar_bytes(path), antes)


class TestDecisionLecturaTolerante(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_ledger_ausente_devuelve_vacio_sin_findings(self):
        entradas, findings = decision.leer_entradas(decision.ledger_path(self.repo))
        self.assertEqual(entradas, [])
        self.assertEqual(findings, [])

    def test_linea_corrupta_se_reporta_y_se_sigue_leyendo_el_resto(self):
        decision.decision_add(self.repo, "20260910-a", "target", "r", "rat", "u", "f", "c")
        decision.decision_add(self.repo, "20260910-b", "baseline", "r2", "rat2", "u", "f", "c")
        path = decision.ledger_path(self.repo)
        # Simula corrupción externa (no vía las funciones del módulo, que son
        # fail-closed): se inserta una línea inválida entre dos válidas.
        lineas = path.read_text(encoding="utf-8").splitlines()
        lineas.insert(1, "esto no es json valido")
        path.write_text("\n".join(lineas) + "\n", encoding="utf-8")

        entradas, findings = decision.leer_entradas(path)
        self.assertEqual(len(entradas), 2)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].codigo, "DECISION-LINEA-CORRUPTA")
        self.assertIn("Línea 2", findings[0].mensaje)

    def test_list_y_show_reportan_corrupta_y_muestran_validas(self):
        decision.decision_add(self.repo, "20260910-a", "target", "r", "rat", "u", "f", "c")
        path = decision.ledger_path(self.repo)
        lineas = path.read_text(encoding="utf-8").splitlines()
        lineas.append("{invalido")
        path.write_text("\n".join(lineas) + "\n", encoding="utf-8")

        entradas, findings = decision.decision_list(self.repo)
        self.assertEqual(len(entradas), 1)
        self.assertEqual(findings[0].codigo, "DECISION-LINEA-CORRUPTA")

        entrada, findings_show = decision.decision_show(self.repo, "20260910-a")
        self.assertIsNotNone(entrada)
        self.assertEqual(findings_show[0].codigo, "DECISION-LINEA-CORRUPTA")


class TestDecisionSupersede(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()
        decision.decision_add(self.repo, "20260910-a", "target", "r", "rat", "u", "f", "c")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_supersede_no_reescribe_la_entrada_referenciada_y_show_refleja_estado(self):
        antes = core.capturar_bytes(decision.ledger_path(self.repo))

        ok, findings = decision.decision_supersede(
            self.repo, "20260910-a", "20260910-b", "target", "r2", "rat2", "u", "f", "c"
        )
        self.assertTrue(ok)
        self.assertEqual(findings, [])

        contenido_despues = decision.ledger_path(self.repo).read_bytes()
        # La primera línea (entrada original) no cambió; solo se agregó una segunda.
        self.assertEqual(contenido_despues.splitlines()[0], antes.splitlines()[0])

        entrada, _ = decision.decision_show(self.repo, "20260910-a")
        self.assertEqual(entrada["estado"], "superseded")
        self.assertEqual(entrada["superseded_por"], "20260910-b")

    def test_supersede_con_referencia_inexistente_se_rehusa_sin_escribir(self):
        antes = core.capturar_bytes(decision.ledger_path(self.repo))
        ok, findings = decision.decision_supersede(
            self.repo, "no-existe", "20260910-b", "target", "r2", "rat2", "u", "f", "c"
        )
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "DECISION-REFERENCIA-INVALIDA")
        self.assertEqual(core.capturar_bytes(decision.ledger_path(self.repo)), antes)


class TestDecisionRevoke(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()
        decision.decision_add(self.repo, "20260910-a", "target", "r", "rat", "u", "f", "c")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_revoke_no_reescribe_la_entrada_y_show_reporta_revocada(self):
        antes = core.capturar_bytes(decision.ledger_path(self.repo))
        ok, findings = decision.decision_revoke(self.repo, "20260910-a", "ya no aplica", "u", "f")
        self.assertTrue(ok)
        self.assertEqual(findings, [])

        contenido_despues = decision.ledger_path(self.repo).read_bytes()
        self.assertEqual(contenido_despues.splitlines()[0], antes.splitlines()[0])

        entrada, _ = decision.decision_show(self.repo, "20260910-a")
        self.assertEqual(entrada["estado"], "revocada")

    def test_revoke_con_referencia_inexistente_se_rehusa_sin_escribir(self):
        antes = core.capturar_bytes(decision.ledger_path(self.repo))
        ok, findings = decision.decision_revoke(self.repo, "no-existe", "motivo", "u", "f")
        self.assertFalse(ok)
        self.assertEqual(findings[0].codigo, "DECISION-REFERENCIA-INVALIDA")
        self.assertEqual(core.capturar_bytes(decision.ledger_path(self.repo)), antes)


class TestDecisionListFiltros(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()
        decision.decision_add(
            self.repo, "20260910-a", "target", "r", "rat", "u", "f", "c", change_id="cambio-1"
        )
        decision.decision_add(
            self.repo, "20260910-b", "baseline", "r2", "rat2", "u", "f", "c", change_id="cambio-2"
        )

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_filtra_por_tipo(self):
        entradas, _ = decision.decision_list(self.repo, tipo="target")
        self.assertEqual([e["decision_id"] for e in entradas], ["20260910-a"])

    def test_filtra_por_change_id(self):
        entradas, _ = decision.decision_list(self.repo, change_id="cambio-2")
        self.assertEqual([e["decision_id"] for e in entradas], ["20260910-b"])

    def test_filtra_por_estado(self):
        decision.decision_revoke(self.repo, "20260910-a", "motivo", "u", "f")
        entradas, _ = decision.decision_list(self.repo, estado="revocada")
        self.assertEqual([e["decision_id"] for e in entradas], ["20260910-a"])
        entradas_activas, _ = decision.decision_list(self.repo, estado="activa")
        self.assertEqual([e["decision_id"] for e in entradas_activas], ["20260910-b"])


class TestDecisionShowInexistente(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_show_inexistente_devuelve_none_y_finding(self):
        entrada, findings = decision.decision_show(self.repo, "no-existe")
        self.assertIsNone(entrada)
        self.assertEqual(findings[0].codigo, "DECISION-ID-INEXISTENTE")


class TestDecisionPrecedenciaCombinada(unittest.TestCase):
    """R6: revocada > superseded. Una decisión que es supersedida y además
    revocada (en cualquier orden de las llamadas) debe quedar en estado
    final `revocada`, nunca `superseded`."""

    def setUp(self):
        self.repo = _crear_dir_temporal()
        decision.decision_add(self.repo, "20260910-a", "target", "r", "rat", "u", "f", "c")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_supersede_luego_revoke_estado_final_revocada(self):
        decision.decision_supersede(
            self.repo, "20260910-a", "20260910-b", "target", "r2", "rat2", "u", "f", "c"
        )
        decision.decision_revoke(self.repo, "20260910-a", "ya no aplica", "u", "f")

        entrada, _ = decision.decision_show(self.repo, "20260910-a")
        self.assertEqual(entrada["estado"], "revocada")

        entradas, _ = decision.leer_entradas(decision.ledger_path(self.repo))
        estados = decision.resolver_estados(entradas)
        self.assertEqual(estados["20260910-a"]["estado"], "revocada")

    def test_revoke_luego_supersede_estado_final_revocada(self):
        decision.decision_revoke(self.repo, "20260910-a", "ya no aplica", "u", "f")
        decision.decision_supersede(
            self.repo, "20260910-a", "20260910-b", "target", "r2", "rat2", "u", "f", "c"
        )

        entrada, _ = decision.decision_show(self.repo, "20260910-a")
        self.assertEqual(entrada["estado"], "revocada")

        entradas, _ = decision.leer_entradas(decision.ledger_path(self.repo))
        estados = decision.resolver_estados(entradas)
        self.assertEqual(estados["20260910-a"]["estado"], "revocada")


class TestDecisionReferenciaHuerfana(unittest.TestCase):
    """Una entrada `supersede`/`revocar` escrita manualmente (no vía las
    funciones del módulo) cuya `referencia` nunca existió como
    `registrar`/`supersede` no debe crashear `resolver_estados`/
    `decision_list`/`decision_show`; simplemente no produce una entrada de
    estado para ese `decision_id` inexistente."""

    def setUp(self):
        self.repo = _crear_dir_temporal()
        path = decision.ledger_path(self.repo)
        path.parent.mkdir(parents=True, exist_ok=True)
        entrada_huerfana = {
            "schema_version": decision.SCHEMA_VERSION_SOPORTADA,
            "seq": 0,
            "decision_id": None,
            "utc": "2026-09-10T00:00:00Z",
            "accion": "revocar",
            "referencia": "20260910-nunca-existio",
            "motivo": "referencia huérfana",
            "aprobado_por": "u",
            "fecha_aprobacion": "f",
            "registrado_por": "lead",
        }
        path.write_text(json.dumps(entrada_huerfana, ensure_ascii=False) + "\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_resolver_estados_no_crashea_y_no_produce_entrada(self):
        entradas, findings = decision.leer_entradas(decision.ledger_path(self.repo))
        self.assertEqual(findings, [])
        estados = decision.resolver_estados(entradas)
        self.assertEqual(estados, {})

    def test_decision_list_no_crashea_y_devuelve_vacio(self):
        entradas, findings = decision.decision_list(self.repo)
        self.assertEqual(entradas, [])
        self.assertEqual(findings, [])

    def test_decision_show_no_crashea_y_reporta_inexistente(self):
        entrada, findings = decision.decision_show(self.repo, "20260910-nunca-existio")
        self.assertIsNone(entrada)
        self.assertEqual(findings[0].codigo, "DECISION-ID-INEXISTENTE")


class TestDecisionCliIntegracion(unittest.TestCase):
    """Integración CLI real (mismo patrón que `test_remediation.py`) para
    ejercitar el wiring de `argparse` (`choices`/`dest`/flags requeridos) de
    principio a fin: `decision add` -> `decision supersede` -> `decision show
    --json` contra un repo temporal real."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_add_supersede_show_via_cli(self):
        resultado_add = _correr_ds_guard(
            [
                "decision", "add",
                "--decision-id", "20260910-cli-a",
                "--tipo", "target",
                "--resumen", "resumen inicial",
                "--rationale", "rationale inicial",
                "--usuario", "federico",
                "--fecha", "2026-09-10",
                "--cita", "cita literal",
                "--json",
            ],
            self.repo,
        )
        self.assertEqual(resultado_add.returncode, 0, resultado_add.stderr)

        resultado_supersede = _correr_ds_guard(
            [
                "decision", "supersede",
                "--referencia", "20260910-cli-a",
                "--decision-id", "20260910-cli-b",
                "--tipo", "target",
                "--resumen", "resumen nuevo",
                "--rationale", "rationale nuevo",
                "--usuario", "federico",
                "--fecha", "2026-09-11",
                "--cita", "cita literal nueva",
                "--json",
            ],
            self.repo,
        )
        self.assertEqual(resultado_supersede.returncode, 0, resultado_supersede.stderr)

        resultado_show = _correr_ds_guard(
            ["decision", "show", "--decision-id", "20260910-cli-a", "--json"],
            self.repo,
        )
        self.assertEqual(resultado_show.returncode, 0, resultado_show.stderr)
        payload = json.loads(resultado_show.stdout)
        self.assertEqual(payload["decision"]["estado"], "superseded")
        self.assertEqual(payload["decision"]["superseded_por"], "20260910-cli-b")


if __name__ == "__main__":
    unittest.main()
