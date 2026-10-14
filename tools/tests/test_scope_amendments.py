"""Tests de `tools.dsguard.scope_amendments` (Change 3 de v0.10, Writer A).

Sin consola ni red: directorios temporales y campos T1 inyectados. Una clase
por tema (otra instancia puede agregar clases CLI al final sin pisar nada).
"""
from __future__ import annotations

import ast
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import scope_amendments as sa  # noqa: E402

T1 = {
    "approval_channel": "console_confirmed",
    "confirmed_at": "2026-10-13T12:00:00Z",
    "channel_version": "console/v1",
}
DEFECTO = ["openspec/changes/c1/proposal.md", "openspec/changes/c1/tasks.md"]
INICIAL = DEFECTO + ["src/a.py"]


def normalizar(crudo):
    """Stub de `sdd._normalizar_entrada_alcance`."""
    if not isinstance(crudo, str) or not crudo.strip():
        return None, "vacía"
    ruta = crudo.strip().replace("\\", "/")
    if ".." in ruta.split("/") or ruta.startswith("/"):
        return None, "ruta no permitida"
    return ruta, None


def control_con(rutas, **extra):
    alcance = {"rutas_autorizadas": list(rutas)}
    alcance.update(extra)
    return {"alcance": alcance}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.control = control_con(INICIAL)

    def plan(self, add=(), remove=(), control=None):
        estado = sa.estado_alcance(self.dir, control or self.control)
        return estado, sa.planificar_enmienda(estado, add, remove, DEFECTO, normalizar)

    def aplicar(self, add=(), remove=(), control=None, **kw):
        estado, plan = self.plan(add, remove, control)
        return sa.aplicar_enmienda(
            self.dir, plan, motivo="m", usuario="u", fecha="2026-10-13",
            campos_t1=kw.pop("campos_t1", T1), esperado_hash_antes=plan.hash_antes,
            utc="2026-10-13T12:00:00Z", change_id="c1", **kw)

    def lineas(self):
        return sa.ruta_archivo(self.dir).read_text(encoding="utf-8").split("\n")[:-1]

    def escribir(self, lineas):
        sa.ruta_archivo(self.dir).write_text("\n".join(lineas) + "\n", encoding="utf-8")

    def cadena3(self):
        self.aplicar(add=["src/b.py"])
        self.aplicar(add=["src/c.py"])
        self.aplicar(remove=["src/b.py"])

    def invalido(self):
        e = sa.estado_alcance(self.dir, self.control)
        self.assertFalse(e.valido)
        self.assertEqual(e.rutas, ())
        self.assertTrue(e.hallazgos)
        self.assertTrue(all(h.codigo == sa.COD_ENMIENDA_INVALIDA for h in e.hallazgos))


class TestHashes(unittest.TestCase):
    def test_hash_alcance_orden_y_duplicados(self):
        self.assertEqual(sa.hash_alcance(["b", "a", "a"]), sa.hash_alcance(["a", "b"]))
        self.assertNotEqual(sa.hash_alcance(["a"]), sa.hash_alcance(["a", "b"]))

    def test_hash_entrada_ignora_entry_hash(self):
        self.assertEqual(sa.hash_entrada({"a": 1, "entry_hash": "x"}),
                         sa.hash_entrada({"a": 1, "entry_hash": "y"}))
        self.assertNotEqual(sa.hash_entrada({"a": 1}), sa.hash_entrada({"a": 2}))

    def test_constantes(self):
        self.assertEqual(sa.SCHEMA_VERSION, 1)
        self.assertEqual(sa.NOMBRE_ARCHIVO, "amendments.jsonl")
        self.assertEqual(sa.ruta_archivo("x").name, "amendments.jsonl")


class TestPlan(Base):
    def test_add(self):
        _, p = self.plan(add=["src/b.py"])
        self.assertEqual(p.operacion, "add")
        self.assertEqual(p.add, ("src/b.py",))
        self.assertIn("src/b.py", p.rutas_despues)
        self.assertEqual(p.hash_despues, sa.hash_alcance(p.rutas_despues))
        self.assertFalse(p.es_noop)

    def test_remove(self):
        _, p = self.plan(remove=["src/a.py"])
        self.assertEqual(p.operacion, "remove")
        self.assertNotIn("src/a.py", p.rutas_despues)

    def test_mixta(self):
        _, p = self.plan(add=["src/b.py"], remove=["src/a.py"])
        self.assertEqual(p.operacion, "mixta")

    def test_noop_determinista(self):
        _, p = self.plan(add=["src/a.py"], remove=["src/zzz.py"])
        self.assertTrue(p.es_noop)
        self.assertEqual(p.noop_add, ("src/a.py",))
        self.assertEqual(p.noop_remove, ("src/zzz.py",))
        self.assertEqual(p.hash_antes, p.hash_despues)

    def test_noop_parcial_no_es_noop(self):
        _, p = self.plan(add=["src/a.py", "src/b.py"])
        self.assertFalse(p.es_noop)
        self.assertEqual(p.noop_add, ("src/a.py",))
        self.assertEqual(p.add, ("src/b.py",))

    def test_remove_ruta_por_defecto_error(self):
        _, p = self.plan(remove=[DEFECTO[0]])
        self.assertTrue(p.errores)
        self.assertFalse(p.es_noop)

    def test_entrada_invalida_rechazo_total(self):
        _, p = self.plan(add=["src/b.py", "../fuera"])
        self.assertTrue(p.errores)
        self.assertEqual(p.add, ())
        self.assertEqual(p.rutas_despues, p.rutas_antes)

    def test_remove_invalido_tambien(self):
        _, p = self.plan(remove=["/abs"])
        self.assertTrue(p.errores)

    def test_add_y_remove_misma_ruta(self):
        _, p = self.plan(add=["src/b.py"], remove=["src/b.py"])
        self.assertTrue(p.errores)

    def test_sin_nada_es_error(self):
        _, p = self.plan()
        self.assertTrue(p.errores)

    def test_estado_invalido_error(self):
        self.aplicar(add=["src/b.py"])
        lineas = self.lineas()
        lineas[0] = lineas[0].replace("src/b.py", "src/x.py")
        self.escribir(lineas)
        estado, p = self.plan(add=["src/q.py"])
        self.assertFalse(estado.valido)
        self.assertTrue(p.errores)

    def test_funcion_pura(self):
        estado, p1 = self.plan(add=["src/b.py"])
        _, p2 = self.plan(add=["src/b.py"])
        self.assertEqual(p1, p2)
        self.assertFalse(sa.ruta_archivo(self.dir).exists())


class TestEstadoAlcance(Base):
    def test_sin_archivo(self):
        e = sa.estado_alcance(self.dir, self.control)
        self.assertEqual(e.rutas, tuple(sorted(INICIAL)))
        self.assertEqual((e.revision, e.valido, e.desde_cadena, e.hallazgos), (0, True, False, ()))
        self.assertEqual(e.scope_hash, sa.hash_alcance(INICIAL))

    def test_cadena_valida(self):
        self.cadena3()
        e = sa.estado_alcance(self.dir, self.control)
        self.assertTrue(e.valido and e.desde_cadena)
        self.assertEqual(e.revision, 3)
        self.assertIn("src/c.py", e.rutas)
        self.assertNotIn("src/b.py", e.rutas)
        self.assertEqual(e.scope_hash, sa.hash_alcance(e.rutas))

    def test_cache_divergente_hallazgo_y_efectivo_de_cadena(self):
        self.aplicar(add=["src/b.py"])
        ctl = control_con(INICIAL + ["src/evil.py"])
        e = sa.estado_alcance(self.dir, ctl)
        self.assertTrue(e.valido)
        self.assertIn("src/b.py", e.rutas)
        self.assertNotIn("src/evil.py", e.rutas)
        self.assertEqual([h.codigo for h in e.hallazgos], [sa.COD_CACHE_DIVERGENTE])

    def test_cache_refrescada_sin_hallazgo(self):
        self.aplicar(add=["src/b.py"])
        ctl = control_con(INICIAL + ["src/b.py"])
        e = sa.estado_alcance(self.dir, ctl)
        self.assertEqual(e.hallazgos, ())

    def test_edicion_manual_cache_no_cambia_efectivo(self):
        self.aplicar(add=["src/b.py"])
        base = sa.estado_alcance(self.dir, self.control).rutas
        for ctl in (control_con(["x"]), control_con([]), {}):
            self.assertEqual(sa.estado_alcance(self.dir, ctl).rutas, base)

    def test_ancla_scope_hash_aprobacion(self):
        ctl = control_con(INICIAL, scope_hash=sa.hash_alcance(INICIAL))
        self.aplicar(add=["src/b.py"], control=ctl)
        self.assertTrue(sa.estado_alcance(self.dir, ctl).valido)
        # La caché fue editada entre aprobación y primera enmienda.
        ctl_malo = control_con(INICIAL, scope_hash=sa.hash_alcance(["otro"]))
        self.assertFalse(sa.estado_alcance(self.dir, ctl_malo).valido)

    def test_cache_editada_antes_de_primera_enmienda_con_scope_hash(self):
        aprobado = control_con(INICIAL, scope_hash=sa.hash_alcance(INICIAL))
        # Con ancla en el control, la caché editada ya no permite planificar (A1)...
        editado = control_con(INICIAL + ["src/evil.py"], scope_hash=aprobado["alcance"]["scope_hash"])
        estado, plan = self.plan(add=["src/b.py"], control=editado)
        self.assertFalse(estado.valido)
        self.assertTrue(plan.errores)
        # ...y si la primera enmienda se armó sobre la caché editada (sin ancla),
        # validar contra la ancla de aprobación la declara inválida.
        self.aplicar(add=["src/b.py"], control=control_con(INICIAL + ["src/evil.py"]))
        self.assertFalse(sa.estado_alcance(self.dir, aprobado).valido)

    def test_legado_sin_scope_hash_acepta(self):
        self.aplicar(add=["src/b.py"])
        self.assertTrue(sa.estado_alcance(self.dir, self.control).valido)

    # --- A1: ancla de aprobación sin cadena ---
    def invalido_con(self, ctl):
        e = sa.estado_alcance(self.dir, ctl)
        self.assertFalse(e.valido)
        self.assertEqual(e.rutas, ())
        self.assertEqual([h.codigo for h in e.hallazgos], [sa.COD_ENMIENDA_INVALIDA])

    def test_cache_editada_con_ancla_sin_cadena_invalido(self):
        ctl = control_con(INICIAL + ["src/evil.py"], scope_hash=sa.hash_alcance(INICIAL))
        self.invalido_con(ctl)

    def test_cache_igual_a_ancla_sin_cadena_valido(self):
        ctl = control_con(INICIAL, scope_hash=sa.hash_alcance(INICIAL))
        e = sa.estado_alcance(self.dir, ctl)
        self.assertTrue(e.valido)
        self.assertEqual(e.rutas, tuple(sorted(INICIAL)))

    def test_archivo_borrado_tras_enmienda_invalido(self):
        ctl = control_con(INICIAL, scope_hash=sa.hash_alcance(INICIAL))
        self.aplicar(add=["src/b.py"], control=ctl)
        refrescada = control_con(INICIAL + ["src/b.py"], scope_hash=sa.hash_alcance(INICIAL))
        sa.ruta_archivo(self.dir).unlink()
        self.invalido_con(refrescada)

    def test_archivo_vacio_con_ancla_y_cache_editada_invalido(self):
        sa.ruta_archivo(self.dir).write_text("", encoding="utf-8")
        self.invalido_con(control_con(["x"], scope_hash=sa.hash_alcance(INICIAL)))

    # --- M1: rutas estructurales ---
    def _reiniciar_registro(self):
        """Los subTest comparten directorio: parte siempre sin registro previo."""
        sa.ruta_archivo(self.dir).unlink(missing_ok=True)

    def _entrada_con_add(self, ruta):
        self._reiniciar_registro()
        self.aplicar(add=["src/b.py"])
        e = json.loads(self.lineas()[0])
        e["add"] = [ruta]
        e["rutas_despues"] = sorted(set(INICIAL) | {ruta})
        e["scope_hash_after"] = sa.hash_alcance(e["rutas_despues"])
        e["entry_hash"] = sa.hash_entrada(e)
        self.escribir([json.dumps(e, sort_keys=True, ensure_ascii=False)])

    def test_rutas_estructuralmente_invalidas_en_cadena(self):
        for ruta in ("**", "/etc/passwd", "../x", "a/../b", "data/raw/x.csv", "DATA/RAW",
                     "C:/x", "~/x", "a\\b", "./a", ".git/config", ".harmessi/x",
                     ".claude/guardrails.json", ".claude/settings.local.json",
                     "*/x", "a\x00b", ""):
            with self.subTest(ruta=ruta):
                self.assertIsNotNone(sa.motivo_ruta_invalida(ruta))
                self._entrada_con_add(ruta)
                self.invalido()

    def test_rutas_validas_pasan_validador(self):
        for ruta in ("src/**", "datos_área/ficha.txt", "docs/a b.md", "data/processed/x"):
            self.assertIsNone(sa.motivo_ruta_invalida(ruta), ruta)

    # --- B1: formatos ---
    def _entrada_con(self, **cambios):
        self._reiniciar_registro()
        self.aplicar(add=["src/b.py"])
        e = json.loads(self.lineas()[0])
        e.update(cambios)
        e["entry_hash"] = sa.hash_entrada(e)
        # ensure_ascii=True: permite escribir surrogates sueltos como \uXXXX.
        self.escribir([json.dumps(e, sort_keys=True, ensure_ascii=True)])

    def test_formatos_invalidos(self):
        for cambios in ({"utc": "2026-10-13"}, {"utc": "2026-10-13T12:00:00+00:00"},
                        {"confirmed_at": "ayer"}, {"motivo": ""}, {"usuario": "  "},
                        {"fecha_declarada": None}, {"fecha_declarada": ""}):
            with self.subTest(cambios=cambios):
                self._entrada_con(**cambios)
                self.invalido()

    def test_motivo_usuario_caracteres_y_largo(self):
        malos = [{"motivo": "a\nb"}, {"motivo": "a\x00b"}, {"motivo": "a‮b"},
                 {"motivo": "a b"}, {"motivo": "a b"}, {"motivo": "a\ud800b"},
                 {"motivo": "x" * 501}, {"usuario": "u\tx"}, {"usuario": "u​x"},
                 {"usuario": "y" * 201}]
        for cambios in malos:
            with self.subTest(cambios=cambios):
                self._entrada_con(**cambios)
                self.invalido()

    def test_motivo_usuario_en_el_limite_y_unicode_validos(self):
        self._reiniciar_registro()
        self.aplicar(add=["src/b.py"])
        e = json.loads(self.lineas()[0])
        e["motivo"] = "ñ" * 500
        e["usuario"] = "Ana María " + "u" * 190
        e["entry_hash"] = sa.hash_entrada(e)
        self.escribir([json.dumps(e, sort_keys=True, ensure_ascii=False)])
        self.assertTrue(sa.estado_alcance(self.dir, self.control).valido)

    def test_fecha_declarada_formato_y_validez(self):
        for fecha in ("2026-13-01", "2026-02-30", "2026-1-01", "26-10-13", "2026/10/13",
                      "2026-10-13 ", "٢٠٢٦-١٠-١٣", "2026-10-13T00:00:00Z", " ", 20261013):
            with self.subTest(fecha=fecha):
                self._entrada_con(fecha_declarada=fecha)
                self.invalido()

    def test_texto_con_caracteres_de_control(self):
        for malo in ("\x00", "\n", "\x7f", "​", " ", " ", "\ud800", "", "͸"):
            self.assertTrue(sa.texto_con_caracteres_de_control("ok" + malo), repr(malo))
        for bueno in ("normal", "ñandú área", "con espacios", "日本語/ファイル"):
            self.assertFalse(sa.texto_con_caracteres_de_control(bueno), bueno)

    def test_ruta_con_formato_o_no_asignado_rechazada(self):
        for ruta in ("src/a​b.py", "src/a‮b.py", "src/a b.py", "src/ab.py",
                     "src/a͸b.py", "src/a\x7fb.py"):
            self.assertIsNotNone(sa.motivo_ruta_invalida(ruta), repr(ruta))

    def test_hallazgo_cache_divergente_menciona_reparar_cache(self):
        self.aplicar(add=["src/b.py"])
        e = sa.estado_alcance(self.dir, control_con(["otra"]))
        self.assertEqual([h.codigo for h in e.hallazgos], [sa.COD_CACHE_DIVERGENTE])
        self.assertIn("ds_guard scope show --reparar-cache", e.hallazgos[0].mensaje)

    # --- cadena inválida por cada causa ---
    def test_invalida_linea_editada(self):
        self.cadena3()
        ls = self.lineas()
        ls[1] = ls[1].replace("src/c.py", "src/z.py")
        self.escribir(ls)
        self.invalido()

    def test_invalida_json_roto(self):
        self.aplicar(add=["src/b.py"])
        self.escribir(["{no es json"])
        self.invalido()

    def test_invalida_linea_intermedia_borrada(self):
        self.cadena3()
        ls = self.lineas()
        del ls[1]
        self.escribir(ls)
        self.invalido()

    def test_invalida_reordenada(self):
        self.cadena3()
        ls = self.lineas()
        ls[0], ls[1] = ls[1], ls[0]
        self.escribir(ls)
        self.invalido()

    def test_invalida_canal_t0(self):
        self.aplicar(add=["src/b.py"])
        e = json.loads(self.lineas()[0])
        e["approval_channel"] = "declared"
        e["entry_hash"] = sa.hash_entrada(e)  # re-hash coherente
        self.escribir([json.dumps(e, sort_keys=True, ensure_ascii=False)])
        self.invalido()

    def test_invalida_sin_channel_version(self):
        self.aplicar(add=["src/b.py"])
        e = json.loads(self.lineas()[0])
        del e["channel_version"]
        e["entry_hash"] = sa.hash_entrada(e)
        self.escribir([json.dumps(e, sort_keys=True, ensure_ascii=False)])
        self.invalido()

    def test_invalida_channel_version_vacia(self):
        self.aplicar(add=["src/b.py"])
        e = json.loads(self.lineas()[0])
        e["channel_version"] = ""
        e["entry_hash"] = sa.hash_entrada(e)
        self.escribir([json.dumps(e, sort_keys=True, ensure_ascii=False)])
        self.invalido()

    def test_invalida_scope_hash_before_roto_coherente(self):
        self.aplicar(add=["src/b.py"])
        self.aplicar(add=["src/c.py"])
        ls = self.lineas()
        e = json.loads(ls[1])
        e["scope_hash_before"] = sa.hash_alcance(["otra"])
        e["entry_hash"] = sa.hash_entrada(e)
        ls[1] = json.dumps(e, sort_keys=True, ensure_ascii=False)
        self.escribir(ls)
        self.invalido()

    def test_invalida_scope_hash_before_seq1_roto(self):
        self.aplicar(add=["src/b.py"])
        e = json.loads(self.lineas()[0])
        e["scope_hash_before"] = sa.hash_alcance(["otra"])
        e["entry_hash"] = sa.hash_entrada(e)
        self.escribir([json.dumps(e, sort_keys=True, ensure_ascii=False)])
        self.invalido()

    def test_invalida_scope_hash_after_roto(self):
        self.aplicar(add=["src/b.py"])
        e = json.loads(self.lineas()[0])
        e["scope_hash_after"] = "0" * 64
        e["entry_hash"] = sa.hash_entrada(e)
        self.escribir([json.dumps(e, sort_keys=True, ensure_ascii=False)])
        self.invalido()

    def test_invalida_rutas_despues_no_equivale(self):
        self.aplicar(add=["src/b.py"])
        e = json.loads(self.lineas()[0])
        e["rutas_despues"] = sorted(e["rutas_despues"] + ["src/colada.py"])
        e["scope_hash_after"] = sa.hash_alcance(e["rutas_despues"])
        e["entry_hash"] = sa.hash_entrada(e)
        self.escribir([json.dumps(e, sort_keys=True, ensure_ascii=False)])
        self.invalido()

    def test_invalida_prev_hash_incorrecto(self):
        self.aplicar(add=["src/b.py"])
        self.aplicar(add=["src/c.py"])
        ls = self.lineas()
        e = json.loads(ls[1])
        e["prev_hash"] = "f" * 64
        e["entry_hash"] = sa.hash_entrada(e)
        ls[1] = json.dumps(e, sort_keys=True, ensure_ascii=False)
        self.escribir(ls)
        self.invalido()

    def test_invalida_utf8_roto(self):
        sa.ruta_archivo(self.dir).write_bytes(b"\xff\xfe\x00")
        self.invalido()


class TestAplicar(Base):
    def test_primera_y_segunda_encadenadas(self):
        e1 = self.aplicar(add=["src/b.py"])
        e2 = self.aplicar(remove=["src/a.py"])
        self.assertEqual((e1["seq"], e2["seq"]), (1, 2))
        self.assertEqual(e1["prev_hash"], "")
        self.assertEqual(e2["prev_hash"], e1["entry_hash"])
        self.assertEqual(e2["scope_hash_before"], e1["scope_hash_after"])
        self.assertEqual(e1["entry_hash"], sa.hash_entrada(e1))
        self.assertEqual(len(self.lineas()), 2)
        self.assertEqual(json.loads(self.lineas()[1]), e2)
        est = sa.estado_alcance(self.dir, self.control)
        self.assertTrue(est.valido)
        self.assertEqual(est.revision, 2)
        self.assertNotIn("src/a.py", est.rutas)

    def test_claves_exactas_y_privacidad(self):
        e = self.aplicar(add=["src/b.py"])
        self.assertEqual(set(e), set(sa.CLAVES_ENTRADA))
        self.assertEqual(len(e), 17)
        texto = sa.ruta_archivo(self.dir).read_text(encoding="utf-8").lower()
        for prohibido in ("challenge", "respuesta", "response", "terminal", "change_id"):
            self.assertNotIn(prohibido, texto)

    def test_conflicto_esperado_hash(self):
        _, plan = self.plan(add=["src/b.py"])
        with self.assertRaises(ValueError):
            sa.aplicar_enmienda(self.dir, plan, motivo="m", usuario="u", fecha="2026-10-13",
                                campos_t1=T1, esperado_hash_antes="0" * 64)
        self.assertFalse(sa.ruta_archivo(self.dir).exists())

    def test_plan_viejo_tras_cambio_concurrente(self):
        _, plan = self.plan(add=["src/b.py"])
        self.aplicar(add=["src/c.py"])  # alguien enmendó entre medio
        antes = sa.ruta_archivo(self.dir).read_bytes()
        with self.assertRaises(ValueError):
            sa.aplicar_enmienda(self.dir, plan, motivo="m", usuario="u", fecha="2026-10-13",
                                campos_t1=T1, esperado_hash_antes=plan.hash_antes)
        self.assertEqual(sa.ruta_archivo(self.dir).read_bytes(), antes)

    def test_sin_archivo_cache_de_disco_cambiada(self):
        (self.dir / "control.json").write_text(
            json.dumps(control_con(INICIAL + ["src/otra.py"])), encoding="utf-8")
        _, plan = self.plan(add=["src/b.py"])
        with self.assertRaises(ValueError):
            sa.aplicar_enmienda(self.dir, plan, motivo="m", usuario="u", fecha="2026-10-13",
                                campos_t1=T1, esperado_hash_antes=plan.hash_antes)
        self.assertFalse(sa.ruta_archivo(self.dir).exists())

    def test_cadena_invalida_previa(self):
        self.aplicar(add=["src/b.py"])
        _, plan = self.plan(add=["src/c.py"])
        ls = self.lineas()
        ls[0] = ls[0].replace("src/b.py", "src/x.py")
        self.escribir(ls)
        antes = sa.ruta_archivo(self.dir).read_bytes()
        with self.assertRaises(ValueError):
            sa.aplicar_enmienda(self.dir, plan, motivo="m", usuario="u", fecha="2026-10-13",
                                campos_t1=T1, esperado_hash_antes=plan.hash_antes)
        self.assertEqual(sa.ruta_archivo(self.dir).read_bytes(), antes)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["amendments.jsonl"])

    def test_fallo_os_replace_sin_residuos(self):
        self.aplicar(add=["src/b.py"])
        antes = sa.ruta_archivo(self.dir).read_bytes()
        _, plan = self.plan(add=["src/c.py"])
        with mock.patch.object(sa.os, "replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                sa.aplicar_enmienda(self.dir, plan, motivo="m", usuario="u", fecha="2026-10-13",
                                    campos_t1=T1, esperado_hash_antes=plan.hash_antes)
        self.assertEqual(sa.ruta_archivo(self.dir).read_bytes(), antes)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["amendments.jsonl"])

    def test_fallo_os_replace_primera_enmienda(self):
        _, plan = self.plan(add=["src/b.py"])
        with mock.patch.object(sa.os, "replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                sa.aplicar_enmienda(self.dir, plan, motivo="m", usuario="u", fecha="2026-10-13",
                                    campos_t1=T1, esperado_hash_antes=plan.hash_antes)
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_carrera_antes_del_replace_aborta(self):
        self.aplicar(add=["src/b.py"])
        _, plan = self.plan(add=["src/c.py"])
        real = sa._validar_cadena
        llamadas = []

        def con_carrera(texto, ancla):
            llamadas.append(1)
            res = real(texto, ancla)
            if len(llamadas) == 2:  # validación del temporal: otro proceso escribe ahora
                with open(sa.ruta_archivo(self.dir), "ab") as fh:
                    fh.write(b"\n")
            return res

        with mock.patch.object(sa, "_validar_cadena", side_effect=con_carrera):
            with self.assertRaises(ValueError):
                sa.aplicar_enmienda(self.dir, plan, motivo="m", usuario="u", fecha="2026-10-13",
                                    campos_t1=T1, esperado_hash_antes=plan.hash_antes)
        self.assertEqual(len(self.lineas()), 2)  # línea original + el "\n" intruso
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["amendments.jsonl"])

    def test_fecha_ausente_rechazada_sin_escribir(self):
        _, plan = self.plan(add=["src/b.py"])
        for fecha in (None, ""):
            with self.assertRaises(ValueError):
                sa.aplicar_enmienda(self.dir, plan, motivo="m", usuario="u", fecha=fecha,
                                    campos_t1=T1, esperado_hash_antes=plan.hash_antes)
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_canal_distinto_rechazado(self):
        for campos in (dict(T1, approval_channel="declared"),
                       {k: v for k, v in T1.items() if k != "channel_version"},
                       dict(T1, extra="x"),
                       dict(T1, channel_version="")):
            with self.assertRaises(ValueError):
                self.aplicar(add=["src/b.py"], campos_t1=campos)
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_plan_no_aplicable(self):
        _, noop = self.plan(add=["src/a.py"])
        _, err = self.plan(remove=[DEFECTO[0]])
        for p in (noop, err):
            with self.assertRaises(ValueError):
                sa.aplicar_enmienda(self.dir, p, motivo="m", usuario="u", fecha="2026-10-13",
                                    campos_t1=T1, esperado_hash_antes=p.hash_antes)
        self.assertEqual(list(self.dir.iterdir()), [])


class TestHashDiff(Base):
    def test_diff_forma_y_estable(self):
        _, p = self.plan(add=["src/b.py"], remove=["src/a.py"])
        d = sa.diff_canonico("c1", p)
        self.assertEqual(set(d), {"operacion", "target", "change_id", "hash_antes",
                                  "add", "remove", "hash_despues"})
        self.assertEqual(d["target"], "scope-amendment")
        self.assertEqual(sa.hash_diff("c1", p), sa.hash_diff("c1", p))

    def test_cambia_con_cualquier_elemento(self):
        _, p = self.plan(add=["src/b.py"], remove=["src/a.py"])
        base = sa.hash_diff("c1", p)
        from dataclasses import replace
        variantes = [
            sa.hash_diff("c2", p),
            sa.hash_diff("c1", replace(p, operacion="add")),
            sa.hash_diff("c1", replace(p, hash_antes="a" * 64)),
            sa.hash_diff("c1", replace(p, hash_despues="b" * 64)),
            sa.hash_diff("c1", replace(p, add=("src/otro.py",))),
            sa.hash_diff("c1", replace(p, remove=("src/otro.py",))),
        ]
        for v in variantes:
            self.assertNotEqual(v, base)
        self.assertEqual(len(set(variantes + [base])), 7)


class TestUnicodeYEspacios(Base):
    def test_unicode_literal(self):
        ruta = "datos_área/ficha.txt"
        self.aplicar(add=[ruta, "mi carpeta/archivo con espacios.txt"])
        crudo = sa.ruta_archivo(self.dir).read_text(encoding="utf-8")
        self.assertIn(ruta, crudo)  # ensure_ascii=False
        est = sa.estado_alcance(self.dir, self.control)
        self.assertIn(ruta, est.rutas)
        self.assertIn("mi carpeta/archivo con espacios.txt", est.rutas)
        _, p = self.plan(add=[ruta])
        self.assertTrue(p.es_noop)
        _, p = self.plan(remove=[ruta])
        self.assertEqual(p.remove, (ruta,))

    def test_hash_unicode_estable(self):
        self.assertEqual(sa.hash_alcance(["datos_área/ficha.txt"]),
                         sa.hash_alcance(["datos_área/ficha.txt"]))
        self.assertNotEqual(sa.hash_alcance(["datos_area/ficha.txt"]),
                            sa.hash_alcance(["datos_área/ficha.txt"]))


class TestSoloStdlib(unittest.TestCase):
    PERMITIDOS = {"__future__", "re", "unicodedata", "fnmatch", "hashlib", "json", "os", "tempfile", "dataclasses",
                  "datetime", "pathlib", "typing"}

    def test_imports(self):
        fuente = (REPO_ORIGEN / "tools" / "dsguard" / "scope_amendments.py").read_text(encoding="utf-8")
        for nodo in ast.walk(ast.parse(fuente)):
            if isinstance(nodo, ast.Import):
                for a in nodo.names:
                    self.assertIn(a.name.split(".")[0], self.PERMITIDOS)
            elif isinstance(nodo, ast.ImportFrom):
                if nodo.level:
                    self.assertEqual(nodo.module, "core")
                else:
                    self.assertIn(nodo.module.split(".")[0], self.PERMITIDOS)


# --- CLI: `ds_guard scope amend|show` (Writer D) --------------------------------
# Repo git temporal con un Change sintético; la confirmación T1 se inyecta parcheando
# `human_presence.solicitar_confirmacion`. Solo el test de subproceso toca la consola real.

import contextlib  # noqa: E402
import io  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
from types import SimpleNamespace  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_ds_guard_exec import DS_GUARD, _crear_repo_git_temporal  # noqa: E402

import ds_guard  # noqa: E402
from dsguard import core as dscore  # noqa: E402
from dsguard import human_presence  # noqa: E402
from dsguard import scope as dsscope  # noqa: E402

CID = "20261013-cli-scope"
PROPIA = f"openspec/changes/{CID}/amendments.jsonl"


def _resultado_ok():
    return human_presence.ResultadoPresencia(
        ok=True, canal=human_presence.CANAL_CONSOLE, confirmed_at="2026-10-13T12:00:00Z",
        channel_version="console/v1", motivo="")


def _resultado_fallo(motivo="confirmacion rechazada (prueba)"):
    return human_presence.ResultadoPresencia(
        ok=False, canal=None, confirmed_at=None, channel_version=None, motivo=motivo)


class _BaseCli(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal(prefix="cli_scope_")
        self.change_dir = self.repo / "openspec" / "changes" / CID
        self.change_dir.mkdir(parents=True)
        self.escribir_estado("en_implementacion")
        self.defecto = ds_guard._rutas_por_defecto_change(CID, ["proposal.md", "tasks.md"])
        # Change "legado": su scope aprobado aún no incluye amendments.jsonl (los nuevos sí).
        self.inicial = sorted([r for r in self.defecto if r != PROPIA] + ["src/a.py"])
        self.control_path = self.change_dir / "control.json"
        dscore.escribir_control(self.control_path, {
            "schema_version": 1, "change_id": CID, "modo": "abreviado", "origen": "test",
            "creado_utc": dscore.ahora_utc(),
            "baseline": {"commit": "0" * 40, "rama": "main", "capturado_utc": dscore.ahora_utc()},
            "alcance": {"rutas_autorizadas": list(self.inicial),
                        "scope_hash": sa.hash_alcance(self.inicial)},
            "aprobaciones": [], "transiciones": [], "sesiones": [],
        })
        self.cwd_previo = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd_previo)

    def escribir_estado(self, estado):
        (self.change_dir / "tasks.md").write_text(f"estado: {estado}\n", encoding="utf-8")

    def control(self):
        return json.loads(self.control_path.read_text(encoding="utf-8"))

    def archivo(self):
        return sa.ruta_archivo(self.change_dir)

    def entradas(self):
        if not self.archivo().exists():
            return []
        return [json.loads(x) for x in self.archivo().read_text(encoding="utf-8").splitlines()]

    def argv(self, add=(), remove=(), extra=(), usuario="federico", motivo="necesito ampliar"):
        a = ["scope", "amend", "--change-id", CID, "--motivo", motivo, "--usuario", usuario]
        for r in add:
            a += ["--add", r]
        for r in remove:
            a += ["--remove", r]
        return a + list(extra)

    def correr(self, argv, efectos=None, resultado=None):
        out, err = io.StringIO(), io.StringIO()
        if efectos is not None:
            parche = mock.patch.object(human_presence, "solicitar_confirmacion", side_effect=efectos)
        else:
            parche = mock.patch.object(
                human_presence, "solicitar_confirmacion", return_value=resultado or _resultado_ok())
        with parche as m, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            codigo = ds_guard.main(argv)
        return codigo, out.getvalue(), err.getvalue(), m

    def efectivo(self):
        return dsscope.alcance_efectivo(self.change_dir, self.control())

    def inyectar(self, add):
        """Agrega una enmienda legítima directamente (simula una carrera)."""
        control = self.control()
        estado = sa.estado_alcance(self.change_dir, control)
        pedidas = list(add) + ([PROPIA] if estado.revision == 0 else [])
        plan = sa.planificar_enmienda(estado, pedidas, [], self.defecto, normalizar)
        sa.aplicar_enmienda(self.change_dir, plan, motivo="carrera", usuario="otro", fecha="2026-10-13",
                            campos_t1=T1, esperado_hash_antes=plan.hash_antes)


class TestCliScopeAmend(_BaseCli):
    def test_add_basico_cambia_efectivo_en_evaluar_alcance_status_y_exec(self):
        nuevo = self.repo / "src" / "b.py"
        nuevo.parent.mkdir(parents=True, exist_ok=True)
        nuevo.write_text("x = 1\n", encoding="utf-8")
        control = self.control()
        antes = [f.ubicacion for f in dsscope.evaluar_alcance(self.repo, control) if f.codigo == "ALCANCE-RUTA"]
        self.assertIn("src/b.py", antes)
        codigo, _o, err, m = self.correr(self.argv(add=["src/b.py"]))
        self.assertEqual(codigo, 0, err)
        m.assert_called_once()
        control = self.control()
        rutas, hallazgos = dsscope.alcance_efectivo(self.change_dir, control)
        self.assertIn("src/b.py", rutas)
        self.assertEqual(hallazgos, [])
        despues = [f.ubicacion for f in dsscope.evaluar_alcance(self.repo, control) if f.codigo == "ALCANCE-RUTA"]
        self.assertNotIn("src/b.py", despues)
        # status --json: fuera_de_alcance ya no lista src/b.py
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(ds_guard.main(["status", "--change-id", CID, "--json"]), 0)
        self.assertNotIn("src/b.py", json.loads(out.getvalue())["fuera_de_alcance"])
        # scope pasado al runtime de exec
        captura = {}

        class _Req:
            def __init__(self, **kw):
                captura.update(kw)
                self.argv, self.scope, self.interpreter = kw["argv"], kw["scope"], kw["interpreter"]

        fake_core = SimpleNamespace(ExecutionRequest=_Req, ExecutionError=ValueError)
        fake_allow = SimpleNamespace(evaluar_comando=lambda *a: (True, "f", ""))
        ns = SimpleNamespace(change_id=CID, interpreter="python", timeout=5)
        with mock.patch.object(ds_guard, "_leadrun_modulos", return_value=(fake_core, fake_allow, None)):
            req, cod = ds_guard._validar_request_exec(ns, "script", ["x.py"], control)
        self.assertIsNone(cod)
        self.assertIn("src/b.py", captura["scope"])

    def test_primera_enmienda_agrega_amendments_jsonl_y_no_la_segunda(self):
        codigo, out, err, _m = self.correr(self.argv(add=["src/b.py"]))
        self.assertEqual(codigo, 0, err)
        e1 = self.entradas()[0]
        self.assertEqual(e1["add"], sorted(["src/b.py", PROPIA]))
        self.assertEqual(e1["approval_channel"], "console_confirmed")
        codigo, _o, err, _m = self.correr(self.argv(add=["src/c.py"]))
        self.assertEqual(codigo, 0, err)
        self.assertEqual(self.entradas()[1]["add"], ["src/c.py"])

    def test_change_nuevo_ya_incluye_registro_propio(self):
        rutas = sorted(self.inicial + [PROPIA])
        control = self.control()
        control["alcance"] = {"rutas_autorizadas": rutas, "scope_hash": sa.hash_alcance(rutas)}
        dscore.escribir_control(self.control_path, control)
        codigo, _o, err, _m = self.correr(self.argv(add=["src/b.py"]))
        self.assertEqual(codigo, 0, err)
        self.assertEqual(self.entradas()[0]["add"], ["src/b.py"])

    def test_init_incluye_registro_y_scope_hash(self):
        self.assertIn(PROPIA, ds_guard._rutas_por_defecto_change(CID, ["proposal.md"]))

    def test_preview_dry_run_marca_registro_propio(self):
        codigo, out, _e, m = self.correr(self.argv(add=["src/b.py"], extra=["--dry-run"]))
        self.assertEqual(codigo, 0)
        self.assertIn("(+ registro de la propia enmienda)", out)
        self.assertIn("hash_antes", out)
        self.assertIn("hash_despues", out)
        self.assertIn("hash_diff", out)
        m.assert_not_called()
        self.assertFalse(self.archivo().exists())

    def test_remove(self):
        self.correr(self.argv(add=["src/b.py"]))
        codigo, _o, err, _m = self.correr(self.argv(remove=["src/b.py"]))
        self.assertEqual(codigo, 0, err)
        rutas, _h = self.efectivo()
        self.assertNotIn("src/b.py", rutas)
        self.assertEqual(len(self.entradas()), 2)
        self.assertEqual(self.entradas()[1]["operacion"], "remove")

    def test_noop_sin_t1_ni_escritura(self):
        for argv in (self.argv(add=["src/a.py"]), self.argv(remove=["src/inexistente.py"])):
            codigo, out, _e, m = self.correr(argv)
            self.assertEqual(codigo, 0)
            m.assert_not_called()
            self.assertIn("no-op", out)
            self.assertFalse(self.archivo().exists())

    def test_ruta_por_defecto_no_removible(self):
        codigo, _o, err, m = self.correr(self.argv(remove=[f"openspec/changes/{CID}/tasks.md"]))
        self.assertEqual(codigo, 2)
        m.assert_not_called()
        self.assertFalse(self.archivo().exists())
        self.assertIn("no se puede quitar", err)

    def test_propio_registro_no_removible(self):
        self.correr(self.argv(add=["src/b.py"]))
        codigo, _o, _e, _m = self.correr(self.argv(remove=[PROPIA]))
        self.assertEqual(codigo, 2)
        self.assertEqual(len(self.entradas()), 1)

    def test_ruta_invalida_rechaza_todo(self):
        codigo, _o, err, m = self.correr(self.argv(add=["src/ok.py", "../fuera.py"]))
        self.assertEqual(codigo, 2)
        m.assert_not_called()
        self.assertFalse(self.archivo().exists())
        self.assertIn("inválida", err)

    def test_expected_scope_hash_viejo(self):
        antes = self.control_path.read_bytes()
        codigo, _o, _e, m = self.correr(self.argv(add=["src/b.py"], extra=["--expected-scope-hash", "0" * 64]))
        self.assertEqual(codigo, 2)
        m.assert_not_called()
        self.assertFalse(self.archivo().exists())
        self.assertEqual(self.control_path.read_bytes(), antes)
        ok = sa.hash_alcance(self.inicial)
        codigo, _o, err, _m = self.correr(self.argv(add=["src/b.py"], extra=["--expected-scope-hash", ok]))
        self.assertEqual(codigo, 0, err)

    def test_dry_run_sin_t1_ni_escritura(self):
        antes = self.control_path.read_bytes()
        codigo, _o, _e, m = self.correr(self.argv(add=["src/b.py"], extra=["--dry-run"]))
        self.assertEqual(codigo, 0)
        m.assert_not_called()
        self.assertFalse(self.archivo().exists())
        self.assertEqual(self.control_path.read_bytes(), antes)

    def test_t1_fallido_sin_escritura(self):
        antes = self.control_path.read_bytes()
        codigo, _o, err, m = self.correr(self.argv(add=["src/b.py"]), resultado=_resultado_fallo("sin consola"))
        self.assertEqual(codigo, 2)
        m.assert_called_once()
        self.assertIn("sin consola", err)
        self.assertFalse(self.archivo().exists())
        self.assertEqual(self.control_path.read_bytes(), antes)

    def test_estado_cambia_durante_confirmacion_aborta(self):
        def efecto(_ctx):
            self.inyectar(["src/carrera.py"])
            return _resultado_ok()

        codigo, _o, err, _m = self.correr(self.argv(add=["src/b.py"]), efectos=efecto)
        self.assertEqual(codigo, 2)
        self.assertIn("cambió durante la confirmación", err)
        entradas = self.entradas()
        self.assertEqual(len(entradas), 1)  # solo la inyectada
        self.assertEqual(entradas[0]["motivo"], "carrera")

    def test_cadena_invalida_exec_rechaza_y_show_falla(self):
        self.correr(self.argv(add=["src/b.py"]))
        texto = self.archivo().read_text(encoding="utf-8")
        self.archivo().write_text(texto.replace("src/b.py", "src/z.py"), encoding="utf-8")
        ns = SimpleNamespace(change_id=CID, interpreter="python", timeout=5)
        fake_core = SimpleNamespace(ExecutionRequest=lambda **kw: SimpleNamespace(**kw), ExecutionError=ValueError)
        fake_allow = SimpleNamespace(evaluar_comando=lambda *a: (True, "f", ""))
        err = io.StringIO()
        with mock.patch.object(ds_guard, "_leadrun_modulos", return_value=(fake_core, fake_allow, None)), \
                contextlib.redirect_stderr(err):
            req, cod = ds_guard._validar_request_exec(ns, "script", ["x.py"], self.control())
        self.assertIsNone(req)
        self.assertEqual(cod, 2)
        self.assertIn("inválido", err.getvalue())
        codigo, _o, _e, _m = self.correr(["scope", "show", "--change-id", CID])
        self.assertEqual(codigo, 1)
        hallazgos = dsscope.evaluar_alcance(self.repo, self.control())
        self.assertTrue(any(h.codigo == "ALCANCE-ENMIENDA-INVALIDA" for h in hallazgos))
        codigo, _o, _e, _m = self.correr(self.argv(add=["src/c.py"]))
        self.assertEqual(codigo, 2)

    def test_cache_editada_a_mano_no_cambia_efectivo(self):
        self.correr(self.argv(add=["src/b.py"]))
        esperado, _h = self.efectivo()
        control = self.control()
        control["alcance"]["rutas_autorizadas"] = ["src/**"]
        dscore.escribir_control(self.control_path, control)
        rutas, hallazgos = self.efectivo()
        self.assertEqual(rutas, esperado)
        self.assertTrue(any(h.codigo == sa.COD_CACHE_DIVERGENTE for h in hallazgos))
        codigo, out, _e, _m = self.correr(["scope", "show", "--change-id", CID])
        self.assertEqual(codigo, 0)
        self.assertIn(sa.COD_CACHE_DIVERGENTE, out)

    def test_fecha_por_defecto_hoy_y_formato_validado(self):
        codigo, _o, err, _m = self.correr(self.argv(add=["src/b.py"]))
        self.assertEqual(codigo, 0, err)
        fecha = self.entradas()[0]["fecha_declarada"]
        self.assertRegex(fecha, r"^\d{4}-\d{2}-\d{2}$")
        codigo, _o, _e, m = self.correr(self.argv(add=["src/c.py"], extra=["--fecha", "13/10/2026"]))
        self.assertEqual(codigo, 2)
        m.assert_not_called()
        codigo, _o, err, _m = self.correr(self.argv(add=["src/c.py"], extra=["--fecha", "2026-10-13"]))
        self.assertEqual(codigo, 0, err)
        self.assertEqual(self.entradas()[1]["fecha_declarada"], "2026-10-13")

    def test_archivo_en_blanco_cuenta_como_enmiendas_al_reaprobar(self):
        (self.change_dir / "proposal.md").write_text("# P\n", encoding="utf-8")
        self.archivo().write_text("\n", encoding="utf-8")
        codigo, _o, err, _m = self.correr(
            ["approve", "--change-id", CID, "--artefacto", "proposal.md", "--usuario", "federico",
             "--fecha", "2026-10-13", "--alcance", "x", "--cita", "n/a"])
        self.assertEqual(codigo, 2)
        self.assertIn("gobernado por enmiendas", err)

    def test_show_reparar_cache(self):
        self.correr(self.argv(add=["src/b.py"]))
        control = self.control()
        ancla = control["alcance"]["scope_hash"]
        control["alcance"]["rutas_autorizadas"] = ["src/**"]
        dscore.escribir_control(self.control_path, control)
        codigo, _o, _e, m = self.correr(["scope", "show", "--change-id", CID, "--reparar-cache"])
        self.assertEqual(codigo, 0)
        m.assert_not_called()
        alcance = self.control()["alcance"]
        self.assertEqual(alcance["scope_hash"], ancla)
        self.assertEqual(sa.hash_alcance(alcance["rutas_autorizadas"]), self.entradas()[-1]["scope_hash_after"])
        _r, hallazgos = self.efectivo()
        self.assertEqual(hallazgos, [])

    def test_accion_t1_lleva_las_rutas(self):
        self.correr(self.argv(add=["src/b.py"]))
        _c, _o, _e, m = self.correr(self.argv(add=["data_x/y.py"], remove=["src/b.py"]))
        accion = m.call_args[0][0]["accion"]
        self.assertEqual(accion, "scope-amend: +data_x/y.py -src/b.py")
        self.assertLessEqual(len(accion), 120)

    def test_accion_demasiado_larga_no_ejecuta_y_dry_run_avisa(self):
        rutas = [f"src/{'x' * 20}{i}.py" for i in range(6)]
        codigo, _o, err, m = self.correr(self.argv(add=rutas))
        self.assertEqual(codigo, 2)
        m.assert_not_called()
        self.assertIn("demasiadas rutas", err)
        self.assertFalse(self.archivo().exists())
        codigo, out, _e, m = self.correr(self.argv(add=rutas, extra=["--dry-run"]))
        self.assertEqual(codigo, 0)
        m.assert_not_called()
        self.assertIn("demasiadas rutas", out)
        for r in rutas:
            self.assertIn(r, out)

    def test_caracteres_de_control_rechazados_antes_del_prompt(self):
        for argv in (self.argv(add=["src/b.py"], motivo="mal\x1b[31mmotivo"),
                     self.argv(add=["src/b.py"], usuario="fede\x1b"),
                     self.argv(add=["src/b‮.py"]),
                     self.argv(remove=["src/a\x07.py"])):
            codigo, _o, _e, m = self.correr(argv)
            self.assertEqual(codigo, 2, argv)
            m.assert_not_called()
        self.assertFalse(self.archivo().exists())

    def test_imprimible_reemplaza_no_imprimibles(self):
        self.assertEqual(ds_guard._imprimible("a\x1bb‮c"), "a?b?c")

    def test_fecha_no_ascii_o_invalida(self):
        for f in ("２０２６-10-13", "2026-13-40", "2026-1-3"):
            codigo, _o, _e, m = self.correr(self.argv(add=["src/b.py"], extra=["--fecha", f]))
            self.assertEqual(codigo, 2, f)
            m.assert_not_called()

    def test_validate_pasa_change_dir_explicito(self):
        with mock.patch.object(ds_guard.scope, "evaluar_alcance", return_value=[]) as ev, \
                contextlib.redirect_stdout(io.StringIO()):
            ds_guard.main(["validate", "--change-id", CID])
        ev.assert_called_once()
        self.assertEqual(ev.call_args.kwargs["change_dir"].name, CID)

    def test_scope_show_change_id_invalido(self):
        for malo in ("../x", "a/b", "a\\b"):
            codigo, _o, err, _m = self.correr(["scope", "show", "--change-id", malo])
            self.assertEqual(codigo, 2, malo)

    def test_accion_t1_resumen_corto(self):
        _c, _o, _e, m = self.correr(self.argv(add=["src/b.py"]))
        accion = m.call_args[0][0]["accion"]
        self.assertTrue(accion.startswith("scope-amend: +"))
        self.assertLessEqual(len(accion), 120)

    def test_cache_refrescada_sin_tocar_scope_hash(self):
        ancla = self.control()["alcance"]["scope_hash"]
        self.correr(self.argv(add=["src/b.py"]))
        alcance = self.control()["alcance"]
        self.assertIn("src/b.py", alcance["rutas_autorizadas"])
        self.assertEqual(alcance["scope_hash"], ancla)

    def test_reaprobar_proposal_con_enmiendas_rechaza(self):
        (self.change_dir / "proposal.md").write_text("# P\n", encoding="utf-8")
        aprobar = ["approve", "--change-id", CID, "--artefacto", "proposal.md", "--usuario", "federico",
                   "--fecha", "2026-10-13", "--alcance", "x", "--cita", "n/a"]
        codigo, _o, err, _m = self.correr(aprobar)
        self.assertEqual(codigo, 0, err)  # sin enmiendas sigue funcionando
        self.correr(self.argv(add=["src/b.py"]))
        antes = self.control_path.read_bytes()
        codigo, _o, err, _m = self.correr(aprobar)
        self.assertEqual(codigo, 2)
        self.assertIn("gobernado por enmiendas", err)
        self.assertEqual(self.control_path.read_bytes(), antes)

    def test_cambio_cerrado_descartado_o_sin_aprobar_rechazado(self):
        for estado in ("cerrada", "descartada", "propuesta_pendiente"):
            self.escribir_estado(estado)
            codigo, _o, err, m = self.correr(self.argv(add=["src/b.py"]))
            self.assertEqual(codigo, 2, estado)
            m.assert_not_called()
            self.assertFalse(self.archivo().exists())

    def test_binding_hash_es_hash_diff_y_cambia_entre_operaciones(self):
        estado = sa.estado_alcance(self.change_dir, self.control())
        plan1 = sa.planificar_enmienda(estado, [PROPIA, "src/b.py"], [], self.defecto, normalizar)
        codigo, _o, err, m1 = self.correr(self.argv(add=["src/b.py"]))
        self.assertEqual(codigo, 0, err)
        ctx1 = m1.call_args[0][0]
        self.assertEqual(ctx1["hash"], sa.hash_diff(CID, plan1))
        self.assertEqual(ctx1["artefacto"], "scope-amendment")
        self.assertEqual(ctx1["accion"], f"scope-amend: +{PROPIA} +src/b.py")
        self.assertEqual(ctx1["change_id"], CID)
        _c, _o, _e, m2 = self.correr(self.argv(add=["src/c.py"]))
        self.assertNotEqual(m2.call_args[0][0]["hash"], ctx1["hash"])

    def test_no_existen_flags_channel_yes_force(self):
        for flag in (["--yes"], ["--force"], ["--channel", "declared"], ["--set", "x"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
                ds_guard.main(self.argv(add=["src/b.py"], extra=flag))
            self.assertEqual(cm.exception.code, 2)
        self.assertFalse(self.archivo().exists())

    def test_validaciones_de_uso(self):
        casos = [
            self.argv(add=["src/b.py"], motivo="   "),
            self.argv(add=["src/b.py"], usuario="a@b.com"),
            self.argv(),
        ]
        for argv in casos:
            codigo, _o, _e, m = self.correr(argv)
            self.assertEqual(codigo, 2, argv)
            m.assert_not_called()
        self.assertFalse(self.archivo().exists())

    def test_scope_show(self):
        codigo, out, _e, m = self.correr(["scope", "show", "--change-id", CID])
        self.assertEqual(codigo, 0)
        m.assert_not_called()
        self.assertIn("Revisión: 0", out)
        self.assertIn(sa.hash_alcance(self.inicial), out)
        self.assertIn("src/a.py", out)
        self.correr(self.argv(add=["src/b.py"]))
        _c, out, _e, _m = self.correr(["scope", "show", "--change-id", CID])
        self.assertIn("Revisión: 1", out)
        self.assertIn("src/b.py", out)

    def test_subproceso_real_con_stdin_por_pipe_falla_cerrado(self):
        canal, _motivo = human_presence.canal_consola_real()
        if canal is not None:
            canal.cerrar()
            self.skipTest("hay consola de control real en este entorno")
        r = subprocess.run(
            [sys.executable, str(DS_GUARD), *self.argv(add=["src/b.py"])],
            cwd=str(self.repo), input="ABCDEF\n", capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse(self.archivo().exists())


if __name__ == "__main__":
    unittest.main()
