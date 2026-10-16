"""Tests de `decision correct` / `decision verify` (Change 2 de v0.11,
`20261016-v011-decision-ledger-corrections`): correcciones append-only,
`prev_hash` encadenado e integridad. Ledgers temporales; el ledger real del
repo solo se lee (se copia a un temporal, nunca se modifica)."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import decision  # noqa: E402

DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"
LEDGER_REAL = REPO_ORIGEN / "openspec" / "decisions" / "ledger.jsonl"


def _codigos(findings) -> list:
    return [f.codigo for f in findings]


def _lineas(repo: Path) -> list:
    return decision.ledger_path(repo).read_bytes().split(b"\n")[:-1]


def _agregar_base(repo: Path, decision_id: str = "20261016-a", tipo: str = "target"):
    ok, f = decision.decision_add(repo, decision_id, tipo, "resumen", "rationale", "u", "2026-10-16", "cita")
    assert ok, f


class Base(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="decision_correct_"))

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def reescribir(self, lineas: list) -> None:
        ruta = decision.ledger_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(b"\n".join(lineas) + b"\n")


class TestCorrect(Base):
    def test_correct_agrega_entrada_con_campos_y_valores_previos(self):
        _agregar_base(self.repo)
        ok, f = decision.decision_correct(
            self.repo, "20261016-a", {"resumen": "nuevo"}, "typo", "u", "2026-10-17"
        )
        self.assertTrue(ok, f)
        entradas, _ = decision.leer_entradas(decision.ledger_path(self.repo))
        c = entradas[1]
        self.assertEqual(c["accion"], "corregir")
        self.assertEqual(c["referencia"], "20261016-a")
        self.assertEqual(c["campos"], {"resumen": "nuevo"})
        self.assertEqual(c["valores_previos"], {"resumen": "resumen"})
        self.assertEqual(c["motivo"], "typo")
        self.assertEqual(c["schema_version"], 2)
        self.assertEqual(c["seq"], 1)
        self.assertEqual(decision.verificar_integridad(self.repo), [])

    def test_correct_de_id_inexistente_no_escribe(self):
        _agregar_base(self.repo)
        antes = decision.ledger_path(self.repo).read_bytes()
        ok, f = decision.decision_correct(self.repo, "no-existe", {"resumen": "x"}, "m", "u", "f")
        self.assertFalse(ok)
        self.assertEqual(f[0].codigo, "DECISION-REFERENCIA-INVALIDA")
        self.assertEqual(decision.ledger_path(self.repo).read_bytes(), antes)

    def test_correct_con_referencia_a_entrada_que_no_es_decision_id_se_rehusa(self):
        _agregar_base(self.repo)
        decision.decision_revoke(self.repo, "20261016-a", "m", "u", "f")  # seq 1, decision_id None
        decision.decision_correct(self.repo, "20261016-a", {"resumen": "v2"}, "m", "u", "f")  # seq 2
        antes = decision.ledger_path(self.repo).read_bytes()
        # Ni el seq de una entrada revocar/corregir ni "None" son decision_id de registrar/supersede.
        for referencia in ("1", "2", "None"):
            ok, f = decision.decision_correct(self.repo, referencia, {"resumen": "x"}, "m", "u", "f")
            self.assertFalse(ok)
            self.assertEqual(f[0].codigo, "DECISION-REFERENCIA-INVALIDA")
        self.assertEqual(decision.ledger_path(self.repo).read_bytes(), antes)

    def test_correct_sobre_decision_revocada_se_acepta(self):
        _agregar_base(self.repo)
        decision.decision_revoke(self.repo, "20261016-a", "m", "u", "f")
        ok, f = decision.decision_correct(self.repo, "20261016-a", {"resumen": "v2"}, "m", "u", "f")
        self.assertTrue(ok, f)
        mostrada, _ = decision.decision_show(self.repo, "20261016-a")
        self.assertEqual(mostrada["estado"], "revocada")
        self.assertEqual(mostrada["efectivo"]["resumen"], "v2")

    def test_correccion_sin_cambio_se_rehusa(self):
        _agregar_base(self.repo)
        antes = decision.ledger_path(self.repo).read_bytes()
        ok, f = decision.decision_correct(self.repo, "20261016-a", {"resumen": "resumen"}, "m", "u", "f")
        self.assertFalse(ok)
        self.assertEqual(f[0].codigo, "DECISION-CORRECCION-SIN-CAMBIO")
        self.assertEqual(decision.ledger_path(self.repo).read_bytes(), antes)
        # Tras corregir, repetir el mismo valor efectivo tambien es no-op.
        decision.decision_correct(self.repo, "20261016-a", {"resumen": "v2"}, "m", "u", "f")
        ok, f = decision.decision_correct(self.repo, "20261016-a", {"resumen": "v2"}, "m", "u", "f")
        self.assertFalse(ok)
        self.assertEqual(f[0].codigo, "DECISION-CORRECCION-SIN-CAMBIO")

    def test_list_change_id_filtra_por_valor_efectivo(self):
        _agregar_base(self.repo)
        decision.decision_correct(self.repo, "20261016-a", {"change_id": "cambio-nuevo"}, "m", "u", "f")
        self.assertEqual(len(decision.decision_list(self.repo, change_id="cambio-nuevo")[0]), 1)
        self.assertEqual(decision.decision_list(self.repo, change_id="otro")[0], [])

    def test_campo_no_permitido_vacio_y_etapa_invalida(self):
        _agregar_base(self.repo)
        antes = decision.ledger_path(self.repo).read_bytes()
        for campos, codigo in (
            ({"tipo": "baseline"}, "DECISION-CAMPO-NO-CORREGIBLE"),
            ({"decision_id": "otro"}, "DECISION-CAMPO-NO-CORREGIBLE"),
            ({"resumen": "  "}, "DECISION-CAMPO-VACIO"),
            ({"evidencia": []}, "DECISION-CAMPO-VACIO"),
            ({}, "DECISION-CAMPO-VACIO"),
            ({"kdd_etapa": "no_existe"}, "KDD-ETAPA-DESCONOCIDA"),
        ):
            ok, f = decision.decision_correct(self.repo, "20261016-a", campos, "m", "u", "f")
            self.assertFalse(ok, campos)
            self.assertIn(codigo, _codigos(f))
        self.assertEqual(decision.ledger_path(self.repo).read_bytes(), antes)

    def test_doble_correccion_efectivo_es_la_ultima_y_conserva_historia(self):
        _agregar_base(self.repo)
        decision.decision_correct(self.repo, "20261016-a", {"resumen": "v2", "cita": "c2"}, "m1", "u", "f")
        decision.decision_correct(self.repo, "20261016-a", {"resumen": "v3"}, "m2", "u", "f")
        entradas, _ = decision.leer_entradas(decision.ledger_path(self.repo))
        self.assertEqual(entradas[2]["valores_previos"], {"resumen": "v2"})

        mostrada, _ = decision.decision_show(self.repo, "20261016-a")
        self.assertEqual(mostrada["resumen"], "resumen")  # original intacto
        self.assertEqual(mostrada["efectivo"]["resumen"], "v3")
        self.assertEqual(mostrada["efectivo"]["cita"], "c2")
        self.assertEqual(mostrada["efectivo"]["rationale"], "rationale")
        self.assertEqual(len(mostrada["correcciones"]), 2)
        self.assertEqual(mostrada["estado"], "activa")

        listadas, _ = decision.decision_list(self.repo)
        self.assertEqual(listadas[0]["efectivo"]["resumen"], "v3")
        self.assertEqual(len(listadas[0]["correcciones"]), 2)

    def test_correct_evidencia_lista(self):
        _agregar_base(self.repo)
        ok, f = decision.decision_correct(self.repo, "20261016-a", {"evidencia": ["a.md", "b.md"]}, "m", "u", "f")
        self.assertTrue(ok, f)
        mostrada, _ = decision.decision_show(self.repo, "20261016-a")
        self.assertEqual(mostrada["efectivo"]["evidencia"], ["a.md", "b.md"])
        self.assertEqual(mostrada["evidencia"], [])


class TestAppendYCadena(Base):
    def test_historia_byte_identica_en_todas_las_escrituras(self):
        _agregar_base(self.repo)
        acumuladas = _lineas(self.repo)
        pasos = (
            lambda: decision.decision_add(self.repo, "20261016-b", "baseline", "r", "rt", "u", "f", "c"),
            lambda: decision.decision_supersede(
                self.repo, "20261016-a", "20261016-c", "target", "r", "rt", "u", "f", "c"
            ),
            lambda: decision.decision_correct(self.repo, "20261016-b", {"cita": "x"}, "m", "u", "f"),
            lambda: decision.decision_revoke(self.repo, "20261016-b", "m", "u", "f"),
        )
        for paso in pasos:
            ok, f = paso()
            self.assertTrue(ok, f)
            nuevas = _lineas(self.repo)
            self.assertEqual(nuevas[: len(acumuladas)], acumuladas)
            self.assertEqual(len(nuevas), len(acumuladas) + 1)
            acumuladas = nuevas
        self.assertEqual(decision.verificar_integridad(self.repo), [])

    def test_prev_hash_es_sha256_de_la_linea_anterior(self):
        _agregar_base(self.repo)
        decision.decision_revoke(self.repo, "20261016-a", "m", "u", "f")
        lineas = _lineas(self.repo)
        entradas, _ = decision.leer_entradas(decision.ledger_path(self.repo))
        self.assertIsNone(entradas[0]["prev_hash"])
        self.assertEqual(entradas[1]["prev_hash"], hashlib.sha256(lineas[0]).hexdigest())

    def test_cadena_tolera_crlf(self):
        _agregar_base(self.repo)
        path = decision.ledger_path(self.repo)
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        ok, f = decision.decision_revoke(self.repo, "20261016-a", "m", "u", "f")
        self.assertTrue(ok, f)
        self.assertEqual(decision.verificar_integridad(self.repo), [])

    def test_ledger_sin_salto_final_se_extiende(self):
        _agregar_base(self.repo)
        path = decision.ledger_path(self.repo)
        path.write_bytes(path.read_bytes().rstrip(b"\n"))
        ok, f = decision.decision_revoke(self.repo, "20261016-a", "m", "u", "f")
        self.assertTrue(ok, f)
        self.assertEqual(decision.verificar_integridad(self.repo), [])


class TestIntegridad(Base):
    def _ledger_de_tres(self):
        _agregar_base(self.repo)
        decision.decision_add(self.repo, "20261016-b", "baseline", "r", "rt", "u", "f", "c")
        decision.decision_correct(self.repo, "20261016-b", {"cita": "x"}, "m", "u", "f")

    def test_ledger_ausente_es_integro(self):
        self.assertEqual(decision.verificar_integridad(self.repo), [])

    def test_cambio_de_un_byte_en_linea_no_final(self):
        self._ledger_de_tres()
        lineas = _lineas(self.repo)
        lineas[0] = lineas[0].replace(b"resumen", b"resumeN", 1)
        self.reescribir(lineas)
        self.assertIn("DECISION-CADENA-ROTA", _codigos(decision.verificar_integridad(self.repo)))

    def test_borrado_de_linea_intermedia(self):
        self._ledger_de_tres()
        lineas = _lineas(self.repo)
        del lineas[1]
        self.reescribir(lineas)
        codigos = _codigos(decision.verificar_integridad(self.repo))
        self.assertIn("DECISION-SEQ-ROTO", codigos)
        self.assertIn("DECISION-CADENA-ROTA", codigos)

    def test_seq_alterado(self):
        self._ledger_de_tres()
        lineas = _lineas(self.repo)
        entrada = json.loads(lineas[2])
        entrada["seq"] = 7
        lineas[2] = json.dumps(entrada, ensure_ascii=False).encode("utf-8")
        self.reescribir(lineas)
        self.assertIn("DECISION-SEQ-ROTO", _codigos(decision.verificar_integridad(self.repo)))

    def test_linea_corrupta(self):
        self._ledger_de_tres()
        lineas = _lineas(self.repo)
        lineas.insert(1, b"basura")
        self.reescribir(lineas)
        self.assertIn("DECISION-LINEA-CORRUPTA", _codigos(decision.verificar_integridad(self.repo)))

    def test_id_duplicado_y_referencia_colgante(self):
        _agregar_base(self.repo)
        lineas = _lineas(self.repo)
        lineas.append(lineas[0])  # mismo decision_id (seq/cadena tambien se rompen)
        colgante = {"schema_version": 1, "seq": 2, "decision_id": None, "accion": "revocar", "referencia": "fantasma"}
        lineas.append(json.dumps(colgante).encode("utf-8"))
        self.reescribir(lineas)
        codigos = _codigos(decision.verificar_integridad(self.repo))
        self.assertIn("DECISION-ID-DUPLICADO", codigos)
        self.assertIn("DECISION-REFERENCIA-COLGANTE", codigos)

    def test_cadena_faltante_tras_iniciarse(self):
        _agregar_base(self.repo)
        lineas = _lineas(self.repo)
        legacy = {"schema_version": 1, "seq": 1, "decision_id": None, "accion": "revocar", "referencia": "20261016-a"}
        lineas.append(json.dumps(legacy).encode("utf-8"))
        self.reescribir(lineas)
        self.assertEqual(_codigos(decision.verificar_integridad(self.repo)), ["DECISION-CADENA-FALTANTE"])

    def test_schema_version_2_sin_prev_hash_es_cadena_faltante(self):
        entrada = {"schema_version": 2, "seq": 0, "decision_id": "20261016-a", "accion": "registrar",
                   "referencia": None}
        self.reescribir([json.dumps(entrada).encode("utf-8")])
        self.assertEqual(_codigos(decision.verificar_integridad(self.repo)), ["DECISION-CADENA-FALTANTE"])

    def test_escrituras_fail_closed_ante_inconsistencia(self):
        self._ledger_de_tres()
        lineas = _lineas(self.repo)
        del lineas[1]
        self.reescribir(lineas)
        antes = decision.ledger_path(self.repo).read_bytes()
        intentos = (
            lambda: decision.decision_add(self.repo, "20261016-z", "target", "r", "rt", "u", "f", "c"),
            lambda: decision.decision_supersede(self.repo, "20261016-a", "20261016-z", "target", "r", "rt", "u", "f", "c"),
            lambda: decision.decision_revoke(self.repo, "20261016-a", "m", "u", "f"),
            lambda: decision.decision_correct(self.repo, "20261016-a", {"cita": "x"}, "m", "u", "f"),
        )
        for intento in intentos:
            ok, f = intento()
            self.assertFalse(ok)
            self.assertEqual(f[0].codigo, "DECISION-LEDGER-INCONSISTENTE")
            self.assertEqual(decision.ledger_path(self.repo).read_bytes(), antes)

    def test_escritura_fail_closed_ante_linea_corrupta(self):
        _agregar_base(self.repo)
        path = decision.ledger_path(self.repo)
        path.write_bytes(path.read_bytes() + b"basura\n")
        antes = path.read_bytes()
        ok, f = decision.decision_correct(self.repo, "20261016-a", {"cita": "x"}, "m", "u", "f")
        self.assertFalse(ok)
        self.assertEqual(f[0].codigo, "DECISION-LEDGER-CORRUPTO")
        self.assertEqual(path.read_bytes(), antes)


class TestLedgerV1(Base):
    def test_ledger_v1_sintetico_se_lee_y_se_extiende_encadenando(self):
        legacy = {
            "schema_version": 1, "seq": 0, "decision_id": "20260101-x", "utc": "2026-01-01T00:00:00Z",
            "accion": "registrar", "referencia": None, "tipo": "target", "resumen": "r", "rationale": "rt",
            "change_id": None, "kdd_etapa": None, "evidencia": [], "aprobado_por": "u",
            "fecha_aprobacion": "f", "cita": "c", "registrado_por": "lead",
        }
        path = decision.ledger_path(self.repo)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Bytes con "\n" explícito (write_text en Windows escribiría CRLF).
        path.write_bytes((json.dumps(legacy) + "\n").encode("utf-8"))
        self.assertEqual(decision.verificar_integridad(self.repo), [])
        listadas, _ = decision.decision_list(self.repo)
        self.assertEqual(listadas[0]["estado"], "activa")
        self.assertEqual(listadas[0]["efectivo"]["resumen"], "r")

        antes = _lineas(self.repo)
        ok, f = decision.decision_correct(self.repo, "20260101-x", {"resumen": "r2"}, "m", "u", "f")
        self.assertTrue(ok, f)
        despues = _lineas(self.repo)
        self.assertEqual(despues[0], antes[0])
        self.assertEqual(json.loads(despues[1])["prev_hash"], hashlib.sha256(antes[0]).hexdigest())
        self.assertEqual(decision.verificar_integridad(self.repo), [])

    def test_edicion_del_prefijo_legacy_solo_se_detecta_en_la_ultima_linea_legacy(self):
        def _legacy(seq, decision_id):
            return json.dumps({
                "schema_version": 1, "seq": seq, "decision_id": decision_id, "accion": "registrar",
                "referencia": None, "tipo": "target", "resumen": "r", "rationale": "rt",
                "change_id": None, "kdd_etapa": None, "evidencia": [], "cita": "c",
            }).encode("utf-8")

        self.reescribir([_legacy(0, "20260101-x"), _legacy(1, "20260101-y")])
        ok, f = decision.decision_correct(self.repo, "20260101-x", {"resumen": "r2"}, "m", "u", "f")
        self.assertTrue(ok, f)
        original = _lineas(self.repo)

        # Línea 0 legacy: ninguna entrada v2 la hashea -> edición NO detectada (límite documentado).
        editado = list(original)
        editado[0] = editado[0].replace(b'"resumen": "r"', b'"resumen": "R"', 1)
        self.reescribir(editado)
        self.assertEqual(decision.verificar_integridad(self.repo), [])

        # Última línea legacy: la primera entrada v2 la encadena -> edición detectada.
        editado = list(original)
        editado[1] = editado[1].replace(b'"resumen": "r"', b'"resumen": "R"', 1)
        self.reescribir(editado)
        self.assertEqual(_codigos(decision.verificar_integridad(self.repo)), ["DECISION-CADENA-ROTA"])

    def test_ledger_real_del_repo_lectura_y_verify_sin_modificarlo(self):
        if not LEDGER_REAL.exists():
            self.skipTest("el repo no tiene ledger real")
        bytes_originales = LEDGER_REAL.read_bytes()
        path = decision.ledger_path(self.repo)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes_originales)  # copia temporal

        self.assertEqual(decision.verificar_integridad(LEDGER_REAL), [])
        listadas, findings = decision.decision_list(self.repo)
        self.assertEqual(findings, [])
        self.assertGreaterEqual(len(listadas), 1)
        for d in listadas:
            # Solo decisiones sin correcciones (el ledger real puede corregirse en el futuro).
            if not d["correcciones"]:
                self.assertEqual(d["efectivo"]["resumen"], d["resumen"])

        # Extender la copia (nunca el original) mantiene el prefijo y la integridad.
        primero = listadas[0]["decision_id"]
        ok, f = decision.decision_correct(self.repo, primero, {"cita": "cita corregida en test"}, "m", "u", "f")
        self.assertTrue(ok, f)
        self.assertTrue(path.read_bytes().startswith(bytes_originales))
        self.assertEqual(decision.verificar_integridad(self.repo), [])
        self.assertEqual(LEDGER_REAL.read_bytes(), bytes_originales)


class TestCli(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="decision_correct_cli_"))
        subprocess.run(["git", "init", "-q"], cwd=str(self.repo), check=True)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def correr(self, args: list):
        return subprocess.run(
            [sys.executable, str(DS_GUARD), *args],
            cwd=str(self.repo), capture_output=True, text=True, encoding="utf-8",
        )

    def test_correct_y_verify_via_cli(self):
        r = self.correr([
            "decision", "add", "--decision-id", "20261016-cli", "--tipo", "target", "--resumen", "r",
            "--rationale", "rt", "--usuario", "Federico", "--fecha", "2026-10-16", "--cita", "c", "--json",
        ])
        self.assertEqual(r.returncode, 0, r.stderr)

        r = self.correr([
            "decision", "correct", "--decision-id", "20261016-cli", "--set", "resumen=nuevo=con igual",
            "--evidencia", "a.md", "--motivo", "m", "--usuario", "Federico", "--fecha", "2026-10-17", "--json",
        ])
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.correr(["decision", "show", "--decision-id", "20261016-cli", "--json"])
        payload = json.loads(r.stdout)["decision"]
        self.assertEqual(payload["efectivo"]["resumen"], "nuevo=con igual")
        self.assertEqual(payload["efectivo"]["evidencia"], ["a.md"])

        r = self.correr(["decision", "verify", "--json"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        # Corrupción de la primera línea: verify devuelve 1.
        path = decision.ledger_path(self.repo)
        path.write_bytes(path.read_bytes().replace(b'"resumen": "r"', b'"resumen": "R"', 1))
        r = self.correr(["decision", "verify", "--json"])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("DECISION-CADENA-ROTA", r.stdout)

    def test_correct_rechaza_email_y_set_malformado(self):
        r = self.correr([
            "decision", "correct", "--decision-id", "x", "--set", "resumen=y", "--motivo", "m",
            "--usuario", "a@b.com", "--fecha", "f",
        ])
        self.assertEqual(r.returncode, 2)
        r = self.correr([
            "decision", "correct", "--decision-id", "x", "--set", "sin_igual", "--motivo", "m",
            "--usuario", "Fede", "--fecha", "f",
        ])
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
