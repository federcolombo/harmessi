"""Tests de la atestación humana de rutas Protected (Change 20261027-v015-scope-closure-corrective, T5).

Aislados: directorios y repos git temporales; el canal T1 se parchea (sin consola real).
Reusa los fixtures CLI de `test_scope_amendments`.
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_scope_amendments import CID, _BaseCli, _resultado_fallo, _resultado_ok, ds_guard  # noqa: E402

from dsguard import core as dscore  # noqa: E402
from dsguard import human_presence  # noqa: E402
from dsguard import protected_attestation as pa  # noqa: E402
from dsguard import scope as dsscope  # noqa: E402
from dsguard import sdd  # noqa: E402
from test_scope_closure_window import A, B, _commit, _control, _escribir, _git, _guardar_control  # noqa: E402

SETTINGS = ".claude/settings.json"
GUARDRAILS = ".claude/guardrails.json"
FECHA = "2026-10-27"
MOTIVO = "cambio revisado a mano"
USUARIO = "federico"


def _t1():
    return human_presence.campos_registro(_resultado_ok())


class _BaseUnidad(unittest.TestCase):
    """Change y repo en directorios temporales (sin git)."""

    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="pa_unidad_"))
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)
        self.repo = self.raiz / "repo"
        self.change_dir = self.repo / "openspec" / "changes" / CID
        self.change_dir.mkdir(parents=True)
        self.escribir(SETTINGS, '{"a": 1}\n')

    def escribir(self, ruta, texto):
        p = self.repo / ruta
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(texto.encode("utf-8"))

    def plan(self, ruta=SETTINGS, change_id=CID):
        return pa.planificar_atestacion(self.change_dir, change_id, ruta, self.repo, MOTIVO, USUARIO)

    def atestar(self, ruta=SETTINGS, change_id=CID):
        return pa.aplicar_atestacion(
            self.change_dir, self.plan(ruta, change_id), usuario=USUARIO, fecha=FECHA, campos_t1=_t1())

    def evaluar(self, ruta=SETTINGS, change_id=CID):
        return pa.evaluar_atestacion(self.change_dir, change_id, ruta, self.repo)[0]


class TestConstantes(_BaseUnidad):
    def test_rutas_atestables_son_exactamente_las_tres(self):
        self.assertEqual(pa.RUTAS_ATESTABLES, (
            ".claude/guardrails.json", ".claude/settings.json", ".claude/settings.local.json"))

    def test_rutas_atestables_consistentes_con_rutas_protegidas_de_sdd(self):
        self.assertEqual(len(sdd._ALCANCE_RUTAS_PROTEGIDAS), 4)
        self.assertEqual(sdd._ALCANCE_RUTAS_PROTEGIDAS, pa.RUTAS_ATESTABLES + ("data/raw/x",))

    def test_ruta_fuera_de_rutas_atestables_es_rechazada_por_planificar(self):
        self.escribir("README.md", "hola\n")
        plan = self.plan("README.md")
        self.assertTrue(plan.errores)
        self.assertTrue(any("no atestable" in e for e in plan.errores))
        with self.assertRaises(ValueError):
            pa.aplicar_atestacion(self.change_dir, plan, usuario=USUARIO, fecha=FECHA, campos_t1=_t1())
        self.assertFalse(pa.ruta_archivo(self.change_dir).exists())


class TestAplicarYEvaluar(_BaseUnidad):
    def test_sin_registro_es_sin_atestacion(self):
        self.assertEqual(self.evaluar(), pa.COD_SIN_ATESTACION)

    def test_atestacion_valida_con_hash_actual_es_atestada(self):
        entrada = self.atestar()
        self.assertEqual(entrada["content_hash"], pa.hash_contenido(self.repo / SETTINGS))
        self.assertEqual(entrada["approval_channel"], "console_confirmed")
        self.assertEqual(self.evaluar(), pa.COD_ATESTADA)
        estado = pa.estado_atestaciones(self.change_dir)
        self.assertTrue(estado.valido)
        self.assertEqual(len(estado.entradas), 1)

    def test_archivo_cambia_despues_de_atestar_es_hash_distinto_y_vuelve_a_atestada(self):
        self.atestar()
        self.escribir(SETTINGS, '{"a": 2}\n')
        self.assertEqual(self.evaluar(), pa.COD_HASH_DISTINTO)
        self.escribir(SETTINGS, '{"a": 1}\n')  # contenido exacto atestado
        self.assertEqual(self.evaluar(), pa.COD_ATESTADA)

    def test_archivo_borrado_tras_atestar_es_hash_distinto(self):
        self.atestar()
        (self.repo / SETTINGS).unlink()
        self.assertEqual(self.evaluar(), pa.COD_HASH_DISTINTO)

    def test_atestacion_de_otro_change_id_no_cubre(self):
        self.atestar(change_id="20261027-otro-change")
        self.assertEqual(self.evaluar(), pa.COD_SIN_ATESTACION)

    def test_atestacion_de_otra_ruta_no_cubre(self):
        self.escribir(GUARDRAILS, '{"v": 2}\n')
        self.atestar(ruta=GUARDRAILS)
        self.assertEqual(self.evaluar(GUARDRAILS), pa.COD_ATESTADA)
        self.assertEqual(self.evaluar(SETTINGS), pa.COD_SIN_ATESTACION)

    def test_cadena_adulterada_un_byte_es_invalida_y_bloquea(self):
        self.atestar()
        ruta = pa.ruta_archivo(self.change_dir)
        crudo = ruta.read_bytes()
        self.assertIn(MOTIVO.encode(), crudo)
        ruta.write_bytes(crudo.replace(MOTIVO.encode(), b"cambio revisado a mana", 1))
        self.assertFalse(pa.estado_atestaciones(self.change_dir).valido)
        self.assertEqual(self.evaluar(), pa.COD_SIN_ATESTACION)

    def test_aplicar_dos_veces_acumula_seq_y_prev_hash(self):
        e1 = self.atestar()
        self.escribir(SETTINGS, '{"a": 3}\n')
        e2 = self.atestar()
        self.assertEqual((e1["seq"], e2["seq"]), (1, 2))
        self.assertEqual(e1["prev_hash"], "")
        self.assertEqual(e2["prev_hash"], e1["entry_hash"])
        estado = pa.estado_atestaciones(self.change_dir)
        self.assertTrue(estado.valido)
        self.assertEqual([e["seq"] for e in estado.entradas], [1, 2])
        self.assertEqual(self.evaluar(), pa.COD_ATESTADA)

    def test_atestar_no_modifica_el_archivo_atestado(self):
        antes = (self.repo / SETTINGS).read_bytes()
        self.atestar()
        self.assertEqual((self.repo / SETTINGS).read_bytes(), antes)

    def test_ejecucion_atomica_sin_archivos_tmp_residuales(self):
        self.atestar()
        self.atestar()
        with self.assertRaises(ValueError):
            pa.aplicar_atestacion(
                self.change_dir, self.plan(), usuario=USUARIO, fecha=FECHA,
                campos_t1={"approval_channel": "declared", "confirmed_at": "x", "channel_version": "y"})
        self.assertEqual(list(self.change_dir.glob("*.tmp")), [])
        self.assertEqual(list(self.change_dir.glob(".protected-attestations-*")), [])
        self.assertEqual(len(pa.estado_atestaciones(self.change_dir).entradas), 2)

    def test_canal_declared_en_campos_t1_es_valueerror_sin_escribir(self):
        campos = dict(_t1(), approval_channel="declared")
        with self.assertRaises(ValueError):
            pa.aplicar_atestacion(
                self.change_dir, self.plan(), usuario=USUARIO, fecha=FECHA, campos_t1=campos)
        self.assertFalse(pa.ruta_archivo(self.change_dir).exists())
        self.assertEqual(list(self.change_dir.iterdir()), [])

    def test_entrada_declared_escrita_a_mano_con_hash_recalculado_es_invalida(self):
        entrada = self.atestar()
        entrada["approval_channel"] = "declared"
        entrada["entry_hash"] = pa.hash_entrada(entrada)  # hash correcto: solo falla el canal
        pa.ruta_archivo(self.change_dir).write_text(
            json.dumps(entrada, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        estado = pa.estado_atestaciones(self.change_dir)
        self.assertFalse(estado.valido)
        self.assertTrue(any("console_confirmed" in e for e in estado.errores))
        self.assertEqual(self.evaluar(), pa.COD_SIN_ATESTACION)


class TestEvaluarAlcance(_BaseCli):
    """`evaluar_alcance` sobre un repo git temporal con baseline real."""

    def setUp(self):
        super().setUp()
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.repo), check=True,
                              capture_output=True, text=True).stdout.strip()
        control = self.control()
        control["baseline"]["commit"] = head
        dscore.escribir_control(self.control_path, control)

    def escribir_ruta(self, texto, ruta=SETTINGS):
        p = self.repo / ruta
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(texto.encode("utf-8"))

    def hallazgos_de(self, ruta=SETTINGS):
        return [h for h in dsscope.evaluar_alcance(self.repo, self.control()) if h.ubicacion == ruta]

    def atestar(self, ruta=SETTINGS):
        plan = pa.planificar_atestacion(self.change_dir, CID, ruta, self.repo, MOTIVO, USUARIO)
        return pa.aplicar_atestacion(self.change_dir, plan, usuario=USUARIO, fecha=FECHA, campos_t1=_t1())

    def test_ruta_protegida_tocada_sin_atestacion_bloquea_con_codigo_propio_no_alcance_ruta(self):
        self.escribir_ruta('{"x": 1}\n')
        hs = self.hallazgos_de()
        codigos = [h.codigo for h in hs]
        self.assertIn("ALCANCE-PROTEGIDA-SIN-ATESTACION", codigos)
        self.assertNotIn("ALCANCE-RUTA", codigos)
        self.assertTrue([h for h in dsscope.bloqueantes(hs) if h.codigo == "ALCANCE-PROTEGIDA-SIN-ATESTACION"])

    def test_con_atestacion_valida_y_hash_igual_es_atestada_informativa_sin_bloqueantes(self):
        self.escribir_ruta('{"x": 1}\n')
        self.atestar()
        hs = self.hallazgos_de()
        self.assertEqual([h.codigo for h in hs], ["ALCANCE-PROTEGIDA-ATESTADA"])
        self.assertEqual(dsscope.bloqueantes(hs), [])

    def test_cambio_posterior_a_la_atestacion_bloquea_hash_distinto_y_revertir_vuelve_a_atestada(self):
        self.escribir_ruta('{"x": 1}\n')
        self.atestar()
        self.escribir_ruta('{"x": 2}\n')
        hs = self.hallazgos_de()
        self.assertEqual([h.codigo for h in hs], ["ALCANCE-PROTEGIDA-HASH-DISTINTO"])
        self.assertEqual(len(dsscope.bloqueantes(hs)), 1)
        self.escribir_ruta('{"x": 1}\n')
        hs = self.hallazgos_de()
        self.assertEqual([h.codigo for h in hs], ["ALCANCE-PROTEGIDA-ATESTADA"])
        self.assertEqual(dsscope.bloqueantes(hs), [])


    def test_registro_propio_no_genera_alcance_ruta_y_no_bloquea(self):
        self.escribir_ruta('{"x": 1}\n')
        self.atestar()
        self.assertTrue(pa.ruta_archivo(self.change_dir).exists())
        hs = dsscope.evaluar_alcance(self.repo, self.control())  # SIN filtro por ruta
        self.assertEqual(dsscope.bloqueantes(hs), [])
        registro = (self.change_dir / pa.NOMBRE_ARCHIVO).relative_to(self.repo).as_posix()
        self.assertFalse([h for h in hs if h.codigo == "ALCANCE-RUTA" and h.ubicacion == registro])

    def test_registro_de_otro_change_sigue_bloqueando(self):
        otro = self.repo / "openspec" / "changes" / "20261027-otro-change" / pa.NOMBRE_ARCHIVO
        otro.parent.mkdir(parents=True, exist_ok=True)
        otro.write_text("{}\n", encoding="utf-8")
        ubic = otro.relative_to(self.repo).as_posix()
        hs = dsscope.evaluar_alcance(self.repo, self.control())
        self.assertIn(ubic, [h.ubicacion for h in dsscope.bloqueantes(hs) if h.codigo == "ALCANCE-RUTA"])

    def test_change_dir_none_con_ruta_protegida_es_sin_atestacion(self):
        self.assertEqual(
            pa.evaluar_atestacion(None, CID, SETTINGS, self.repo)[0], pa.COD_SIN_ATESTACION)


class TestEntradasInvalidas(_BaseUnidad):
    def _reescribir(self, entrada):
        pa.ruta_archivo(self.change_dir).write_text(
            json.dumps(entrada, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")

    def test_entrada_con_clave_extra_es_cadena_invalida(self):
        entrada = self.atestar()
        entrada["extra"] = "x"
        entrada["entry_hash"] = pa.hash_entrada(entrada)
        self._reescribir(entrada)
        self.assertFalse(pa.estado_atestaciones(self.change_dir).valido)
        self.assertEqual(self.evaluar(), pa.COD_SIN_ATESTACION)

    def test_seq_o_prev_hash_alterados_con_hash_recalculado_son_cadena_invalida(self):
        for clave, valor in (("seq", 2), ("prev_hash", "a" * 64)):
            with self.subTest(clave=clave):
                pa.ruta_archivo(self.change_dir).unlink(missing_ok=True)
                entrada = self.atestar()
                entrada[clave] = valor
                entrada["entry_hash"] = pa.hash_entrada(entrada)
                self._reescribir(entrada)
                self.assertFalse(pa.estado_atestaciones(self.change_dir).valido)

    def test_schema_version_float_o_bool_es_invalida(self):
        for valor in (1.0, True):
            with self.subTest(valor=valor):
                pa.ruta_archivo(self.change_dir).unlink(missing_ok=True)
                entrada = self.atestar()
                entrada["schema_version"] = valor
                entrada["entry_hash"] = pa.hash_entrada(entrada)
                self._reescribir(entrada)
                self.assertFalse(pa.estado_atestaciones(self.change_dir).valido)


class TestVentanaProtegida(unittest.TestCase):
    """Ruta Protected COMMITEADA dentro de la ventana de un Change con frontera (repo git temporal)."""

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="pa_ventana_"))
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@example.com")
        _git(self.repo, "config", "user.name", "Test")
        _escribir(self.repo, "base.py")
        c0 = _commit(self.repo, "inicial")
        self.control_a = _control(A, c0, ["a_dentro.py"])
        _guardar_control(self.repo, self.control_a)
        _escribir(self.repo, SETTINGS, '{"p": 1}\n')
        c1 = _commit(self.repo, "trabajo de A con ruta protegida")
        _guardar_control(self.repo, _control(B, c1, ["b.py"]))
        _escribir(self.repo, "b.py")
        _commit(self.repo, "trabajo de B")
        self.change_dir = self.repo / "openspec" / "changes" / A

    def test_commiteada_atestada_es_informativa_y_sin_atestar_bloquea(self):
        hs = dsscope.evaluar_alcance(self.repo, self.control_a)
        self.assertIn(dsscope.COD_VENTANA_ACOTADA, [h.codigo for h in hs])
        self.assertIn("ALCANCE-PROTEGIDA-SIN-ATESTACION", [h.codigo for h in dsscope.bloqueantes(hs)])
        plan = pa.planificar_atestacion(self.change_dir, A, SETTINGS, self.repo, MOTIVO, USUARIO)
        pa.aplicar_atestacion(self.change_dir, plan, usuario=USUARIO, fecha=FECHA, campos_t1=_t1())
        hs = dsscope.evaluar_alcance(self.repo, self.control_a)
        self.assertIn(pa.COD_ATESTADA, [h.codigo for h in hs])
        self.assertEqual(dsscope.bloqueantes(hs), [])


class TestCliAtestar(_BaseCli):
    def setUp(self):
        super().setUp()
        self.escribir_ruta('{"x": 1}\n')

    def escribir_ruta(self, texto, ruta=SETTINGS):
        p = self.repo / ruta
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(texto.encode("utf-8"))

    def argv_attest(self, ruta=SETTINGS, extra=()):
        return ["scope", "attest-protected", "--change-id", CID, "--path", ruta,
                "--motivo", MOTIVO, "--usuario", USUARIO] + list(extra)

    def archivo_att(self):
        return pa.ruta_archivo(self.change_dir)

    def test_dry_run_exit_0_y_no_crea_el_registro(self):
        codigo, _o, err, m = self.correr(self.argv_attest(extra=["--dry-run"]))
        self.assertEqual(codigo, 0, err)
        m.assert_not_called()
        self.assertFalse(self.archivo_att().exists())

    def test_ruta_no_atestable_exit_2(self):
        self.escribir_ruta("hola\n", "README.md")
        codigo, _o, err, m = self.correr(self.argv_attest(ruta="README.md"))
        self.assertEqual(codigo, 2)
        m.assert_not_called()
        self.assertFalse(self.archivo_att().exists())

    def test_canal_t1_que_falla_exit_2_sin_escribir(self):
        codigo, _o, _e, m = self.correr(self.argv_attest(), resultado=_resultado_fallo())
        self.assertEqual(codigo, 2)
        m.assert_called_once()
        self.assertFalse(self.archivo_att().exists())

    def test_archivo_cambia_durante_la_confirmacion_exit_2_sin_escribir(self):
        def carrera(_contexto):
            self.escribir_ruta('{"x": "cambiado"}\n')
            return _resultado_ok()

        codigo, _o, err, _m = self.correr(self.argv_attest(), efectos=carrera)
        self.assertEqual(codigo, 2)
        self.assertIn("cambió", err)
        self.assertFalse(self.archivo_att().exists())

    def test_confirmacion_ok_registra_entrada_console_confirmed_con_hash_correcto(self):
        antes = (self.repo / SETTINGS).read_bytes()
        codigo, _o, err, m = self.correr(self.argv_attest())
        self.assertEqual(codigo, 0, err)
        m.assert_called_once()
        entradas = [json.loads(x) for x in self.archivo_att().read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(entradas), 1)
        e = entradas[0]
        self.assertEqual(e["approval_channel"], "console_confirmed")
        self.assertEqual(e["channel_version"], human_presence.VERSION_CANAL)
        self.assertEqual(e["content_hash"], pa.hash_contenido(self.repo / SETTINGS))
        self.assertEqual((e["change_id"], e["ruta"]), (CID, SETTINGS))
        self.assertEqual((self.repo / SETTINGS).read_bytes(), antes)
        self.assertEqual(list(self.change_dir.glob("*.tmp")), [])

    def test_el_parser_rechaza_flag_channel(self):
        err = io.StringIO()
        with mock.patch.object(human_presence, "solicitar_confirmacion", return_value=_resultado_ok()) as m, \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                ds_guard.main(self.argv_attest(extra=["--channel", "declared"]))
        self.assertEqual(cm.exception.code, 2)
        m.assert_not_called()
        self.assertFalse(self.archivo_att().exists())

    def test_scope_amend_add_ruta_protegida_sigue_rechazado(self):
        codigo, _o, err, m = self.correr(self.argv(add=[SETTINGS]))
        self.assertEqual(codigo, 2)
        self.assertIn("ruta protegida", err)
        m.assert_not_called()
        self.assertFalse(self.archivo().exists())


if __name__ == "__main__":
    unittest.main()
