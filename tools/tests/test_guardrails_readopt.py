"""Tests de `guardrails_adoption` (re-adopción aditiva, registro encadenado, Doctor)."""
from __future__ import annotations

import ast
import copy
import dataclasses
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.dsguard import guardrails_adoption as ga  # noqa: E402

T1 = {
    "approval_channel": "console_confirmed",
    "confirmed_at": "2026-10-13T10:00:00Z",
    "channel_version": "console/v1",
}


def plantilla_base() -> dict:
    return {
        "version": 1,
        "holdouts": ["data/holdout", "data/sellado"],
        "data_raw": ["data/raw"],
        "secretos_extra": [".env"],
        "excepciones": [],
        "write_scopes": {"escritor": ["src/**"]},
        "autonomy": {
            "mode": "supervised",
            "sealed_sources": ["src/sellado"],
            "source_access": {"lectura": ["src/**"]},
        },
    }


def vacia() -> ga.ResultadoAdopciones:
    return ga.ResultadoAdopciones((), True, ())


class BaseTemporal(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        self.plantilla = plantilla_base()

    def adoptar(self, actual, **extra):
        """Planifica contra el registro real y aplica; devuelve (plan, entrada)."""
        plan = ga.planificar_adopcion(actual, self.plantilla, ga.cargar_adopciones(self.repo))
        entrada = ga.aplicar_adopcion(
            self.repo, plan, motivo="motivo", usuario="usuario", fecha="2026-10-13",
            campos_t1=T1, esperado_hash_antes=plan.hash_antes, **extra,
        )
        return plan, entrada

    def con_holdouts(self, *extra, base=None):
        actual = copy.deepcopy(self.plantilla)
        actual["holdouts"] = list(base if base is not None else actual["holdouts"]) + list(extra)
        return actual

    def lineas(self):
        return ga.ruta_registro(self.repo).read_text(encoding="utf-8").splitlines()

    def reescribir(self, entradas):
        ruta = ga.ruta_registro(self.repo)
        ruta.write_text("".join(json.dumps(e) + "\n" for e in entradas), encoding="utf-8")


class TestPlanificar(unittest.TestCase):
    def setUp(self):
        self.plantilla = plantilla_base()

    def plan(self, actual):
        return ga.planificar_adopcion(actual, self.plantilla, vacia())

    def test_solo_elegible_aditivo(self):
        actual = copy.deepcopy(self.plantilla)
        actual["holdouts"].append("data/nuevo")
        actual["data_raw"].append("data/raw2")
        plan = self.plan(actual)
        self.assertEqual(plan.rechazos, ())
        self.assertFalse(plan.es_noop)
        self.assertEqual(plan.adiciones, {"holdouts": ("data/nuevo",), "data_raw": ("data/raw2",)})
        self.assertNotEqual(plan.hash_antes, plan.hash_despues)

    def test_sealed_sources_solo_add(self):
        actual = copy.deepcopy(self.plantilla)
        actual["autonomy"]["sealed_sources"].append("src/otro")
        plan = self.plan(actual)
        self.assertEqual(plan.adiciones, {"autonomy.sealed_sources": ("src/otro",)})

    def test_sealed_sources_quitar_rechaza(self):
        actual = copy.deepcopy(self.plantilla)
        actual["autonomy"]["sealed_sources"] = []
        plan = self.plan(actual)
        self.assertTrue(plan.rechazos)
        self.assertFalse(plan.es_noop)
        self.assertEqual(plan.adiciones, {})

    def test_sealed_sources_ausente_rechaza(self):
        actual = copy.deepcopy(self.plantilla)
        del actual["autonomy"]["sealed_sources"]
        self.assertTrue(self.plan(actual).rechazos)

    def test_mixto_rechazo_total(self):
        casos = {
            "remocion": lambda a: a["data_raw"].clear(),
            "excepciones": lambda a: a.__setitem__("excepciones", ["x"]),
            "write_scopes": lambda a: a["write_scopes"].__setitem__("otro", ["y"]),
            "source_access": lambda a: a["autonomy"]["source_access"].__setitem__("w", ["z"]),
            "clave_desconocida": lambda a: a.__setitem__("nueva_clave", 1),
            "hooks": lambda a: a.__setitem__("hooks", {"pre": "x"}),
            "reemplazo": lambda a: a["secretos_extra"].__setitem__(0, ".otro"),
        }
        for nombre, mutar in casos.items():
            with self.subTest(nombre):
                actual = copy.deepcopy(self.plantilla)
                actual["holdouts"].append("data/nuevo")
                mutar(actual)
                plan = self.plan(actual)
                self.assertTrue(plan.rechazos)
                self.assertFalse(plan.es_noop)
                self.assertEqual(plan.adiciones, {})

    def test_solo_prohibido(self):
        actual = copy.deepcopy(self.plantilla)
        actual["excepciones"] = ["x"]
        plan = self.plan(actual)
        self.assertTrue(plan.rechazos)
        self.assertEqual(plan.adiciones, {})

    def test_duplicado_externo_es_noop(self):
        plan = self.plan(copy.deepcopy(self.plantilla))
        self.assertTrue(plan.es_noop)
        self.assertEqual(plan.adiciones, {})
        self.assertEqual(plan.hash_antes, plan.hash_despues)

    def test_duplicados_internos_como_conjunto(self):
        actual = copy.deepcopy(self.plantilla)
        actual["holdouts"] += ["n", "n", "data/holdout"]
        plan = self.plan(actual)
        self.assertEqual(plan.rechazos, ())
        self.assertEqual(plan.adiciones, {"holdouts": ("n",)})

    def test_solo_duplicados_es_noop(self):
        actual = copy.deepcopy(self.plantilla)
        actual["holdouts"].append("data/holdout")
        plan = self.plan(actual)
        self.assertTrue(plan.es_noop)
        self.assertEqual(plan.rechazos, ())

    def test_no_hashables_rechaza_sin_excepcion(self):
        for valor in ([["a"]], [{"a": 1}], [["a"], ["a"]], [None, None]):
            with self.subTest(valor=valor):
                actual = copy.deepcopy(self.plantilla)
                actual["holdouts"] = valor
                plan = self.plan(actual)
                self.assertTrue(plan.rechazos)
                self.assertEqual(plan.adiciones, {})

    def test_elementos_categorias_prohibidas(self):
        for elemento in ("a\ud800b", "a b", "a b", "ab", "a͸b", "a\x7fb"):
            with self.subTest(elemento=elemento):
                actual = copy.deepcopy(self.plantilla)
                actual["holdouts"].append(elemento)
                plan = self.plan(actual)
                self.assertTrue(plan.rechazos)
                self.assertEqual(plan.adiciones, {})

    def test_excepcion_inesperada_es_rechazo(self):
        actual = copy.deepcopy(self.plantilla)
        actual["holdouts"].append("n")
        for exc in (RecursionError, RuntimeError, TypeError):
            with self.subTest(exc=exc.__name__):
                with mock.patch.object(ga.guardrails_drift, "comparar", side_effect=exc("simulado")):
                    plan = self.plan(actual)
                self.assertEqual(plan.rechazos, ("error_interno:%s" % exc.__name__,))
                self.assertFalse(plan.es_noop)
                self.assertEqual(plan.adiciones, {})

    def test_plan_lleva_identidad_vacia_sin_registro(self):
        plan = self.plan(copy.deepcopy(self.plantilla))
        self.assertEqual((plan.ultima_seq, plan.ultimo_entry_hash), (0, ""))

    def test_hash_independiente_de_la_plantilla(self):
        otra = copy.deepcopy(self.plantilla)
        otra["holdouts"].append("agregado-por-harmessi")
        otra["excepciones"] = ["z"]
        a1 = copy.deepcopy(self.plantilla)
        a1["holdouts"].append("n")
        a2 = copy.deepcopy(otra)
        a2["holdouts"].append("n")
        p1 = ga.planificar_adopcion(a1, self.plantilla, vacia())
        p2 = ga.planificar_adopcion(a2, otra, vacia())
        self.assertEqual((p1.hash_antes, p1.hash_despues), (p2.hash_antes, p2.hash_despues))
        self.assertEqual(ga.hash_diff(p1), ga.hash_diff(p2))

    def test_reordenamiento_es_noop(self):
        actual = copy.deepcopy(self.plantilla)
        actual["holdouts"].reverse()
        self.assertTrue(self.plan(actual).es_noop)

    def test_rutas_mutables_ignoradas(self):
        actual = copy.deepcopy(self.plantilla)
        actual["version"] = 9
        actual["autonomy"]["mode"] = "autonomous"
        actual["autonomy"]["budgets"] = {"max_sessions": 3}
        actual["autonomy"]["limits"] = {"max_sessions": 3}
        actual["autonomy"]["version"] = 2
        plan = self.plan(actual)
        self.assertTrue(plan.es_noop)
        self.assertEqual(plan.rechazos, ())

    def test_noop_sin_mutacion(self):
        actual = copy.deepcopy(self.plantilla)
        plantilla = copy.deepcopy(self.plantilla)
        ga.planificar_adopcion(actual, plantilla, vacia())
        self.assertEqual(actual, self.plantilla)
        self.assertEqual(plantilla, self.plantilla)

    def test_plan_no_muta_entradas_con_adiciones(self):
        actual = copy.deepcopy(self.plantilla)
        actual["holdouts"].append("n")
        copia = copy.deepcopy(actual)
        ga.planificar_adopcion(actual, self.plantilla, vacia())
        self.assertEqual(actual, copia)
        self.assertEqual(self.plantilla, plantilla_base())

    def test_tipo_no_list_like(self):
        for valor in ("data/x", {"a": 1}, 5, None, ("a", "b"), [1, 2], [["a"]]):
            with self.subTest(valor=valor):
                actual = copy.deepcopy(self.plantilla)
                actual["holdouts"] = valor
                self.assertTrue(self.plan(actual).rechazos)

    def test_sealed_sources_tipo_invalido(self):
        actual = copy.deepcopy(self.plantilla)
        actual["autonomy"]["sealed_sources"] = "src/x"
        self.assertTrue(self.plan(actual).rechazos)

    def test_autonomy_no_dict_rechaza(self):
        actual = copy.deepcopy(self.plantilla)
        actual["autonomy"] = "texto"
        self.assertTrue(self.plan(actual).rechazos)

    def test_actual_malformado(self):
        for valor in ([], "x", None, 3):
            with self.subTest(valor=valor):
                plan = self.plan(valor)
                self.assertTrue(plan.rechazos)
                self.assertFalse(plan.es_noop)
                self.assertEqual(plan.adiciones, {})

    def test_elemento_invalido(self):
        invalidos = ["", "   ", "../x", "a/../b", "a\\..\\b", "/abs", "\\abs", "C:\\x", "c:/x",
                     "~/x", "a\x00b", "a\nb", "a" * 513, 5, None,
                     "a\x1b[31mb", "a‮b", "a​b", "a⁦b", " lead", "trail ", "x\t"]
        for elemento in invalidos:
            with self.subTest(elemento=elemento):
                actual = copy.deepcopy(self.plantilla)
                actual["holdouts"].append(elemento)
                plan = self.plan(actual)
                self.assertTrue(plan.rechazos)
                self.assertEqual(plan.adiciones, {})

    def test_elementos_validos_limite(self):
        actual = copy.deepcopy(self.plantilla)
        actual["holdouts"] += ["a" * 512, "dir/sub..x", "..oculto"]
        plan = self.plan(actual)
        self.assertEqual(plan.rechazos, ())
        self.assertEqual(len(plan.adiciones["holdouts"]), 3)

    def test_cadena_invalida_rechaza(self):
        invalida = ga.ResultadoAdopciones((), False, (ga._hallazgo("x"),))
        actual = copy.deepcopy(self.plantilla)
        actual["holdouts"].append("n")
        plan = ga.planificar_adopcion(actual, self.plantilla, invalida)
        self.assertTrue(plan.rechazos)

    def test_clave_nueva_ausente_en_plantilla(self):
        plantilla = {"version": 1}
        actual = {"version": 1, "holdouts": ["h"]}
        plan = ga.planificar_adopcion(actual, plantilla, vacia())
        self.assertEqual(plan.adiciones, {"holdouts": ("h",)})


class TestCargarAdopciones(BaseTemporal):
    def test_ausente_es_valida_y_vacia(self):
        res = ga.cargar_adopciones(self.repo)
        self.assertTrue(res.valida)
        self.assertEqual(res.entradas, ())
        self.assertEqual(res.hallazgos, ())

    def test_cadena_valida(self):
        self.adoptar(self.con_holdouts("h1"))
        self.adoptar(self.con_holdouts("h1", "h2"))
        res = ga.cargar_adopciones(self.repo)
        self.assertTrue(res.valida)
        self.assertEqual([e["seq"] for e in res.entradas], [1, 2])
        self.assertEqual(res.entradas[1]["prev_hash"], res.entradas[0]["entry_hash"])
        self.assertEqual(res.entradas[0]["prev_hash"], "")
        self.assertEqual(res.entradas[1]["guardrails_hash_before"], res.entradas[0]["guardrails_hash_after"])

    def _dos(self):
        # Reinicia el registro: los subTest comparten directorio y se alteran entre iteraciones.
        ga.ruta_registro(self.repo).unlink(missing_ok=True)
        self.adoptar(self.con_holdouts("h1"))
        self.adoptar(self.con_holdouts("h1", "h2"))
        return [json.loads(l) for l in self.lineas()]

    def _rehash(self, e):
        e["entry_hash"] = ga._hash_entrada(e)

    def assertInvalida(self, entradas=None, texto=None):
        if texto is not None:
            ga.ruta_registro(self.repo).write_text(texto, encoding="utf-8")
        else:
            self.reescribir(entradas)
        res = ga.cargar_adopciones(self.repo)
        self.assertFalse(res.valida)
        self.assertEqual(res.entradas, ())
        self.assertEqual(len(res.hallazgos), 1)
        h = res.hallazgos[0]
        self.assertEqual(h["code"], ga.COD_ADOPCION_INVALIDA)
        self.assertEqual(h["nivel"], "error")
        self.assertEqual(set(h), {"code", "path", "detail", "nivel"})

    def test_json_invalido(self):
        self._dos()
        self.assertInvalida(texto="{no es json\n")

    def test_linea_vacia_intermedia(self):
        es = self._dos()
        texto = json.dumps(es[0]) + "\n\n" + json.dumps(es[1]) + "\n"
        self.assertInvalida(texto=texto)

    def test_seq_con_hueco(self):
        es = self._dos()
        es[1]["seq"] = 3
        self._rehash(es[1])
        self.assertInvalida(es)

    def test_seq_fuera_de_orden(self):
        es = self._dos()
        self.assertInvalida([es[1], es[0]])

    def test_prev_hash_roto(self):
        es = self._dos()
        es[1]["prev_hash"] = "x" * 64
        self._rehash(es[1])
        self.assertInvalida(es)

    def test_entry_hash_alterado(self):
        es = self._dos()
        es[0]["motivo"] = "alterado"
        self.assertInvalida(es)

    def test_canal_distinto(self):
        es = self._dos()
        es[0]["approval_channel"] = "declared"
        self._rehash(es[0])
        self.assertInvalida(es)

    def test_falta_channel_version(self):
        es = self._dos()
        del es[0]["channel_version"]
        self.assertInvalida(es)

    def test_channel_version_vacio(self):
        es = self._dos()
        es[0]["channel_version"] = ""
        self._rehash(es[0])
        self.assertInvalida(es)

    def test_hash_before_no_encadena(self):
        es = self._dos()
        es[1]["guardrails_hash_before"] = "0" * 64
        self._rehash(es[1])
        self.assertInvalida(es)

    def test_clave_fuera_de_closed_list(self):
        es = self._dos()
        es[0]["claves"] = ["excepciones"]
        es[0]["adiciones"] = {"excepciones": ["x"]}
        self._rehash(es[0])
        self.assertInvalida(es)

    def test_elemento_invalido_en_registro(self):
        es = self._dos()
        es[0]["adiciones"] = {"holdouts": ["../x"]}
        self._rehash(es[0])
        self.assertInvalida(es)

    def test_campo_extra(self):
        es = self._dos()
        es[0]["extra"] = 1
        self._rehash(es[0])
        self.assertInvalida(es)

    def test_elemento_con_esc_o_bidi_en_registro(self):
        for malo in ("a\x1bb", "a‮b", " espacio"):
            with self.subTest(malo=malo):
                es = self._dos()
                es[0]["adiciones"] = {"holdouts": [malo]}
                self._rehash(es[0])
                self.assertInvalida(es)

    def test_no_hashables_en_registro_sin_excepcion(self):
        for campo, valor in (("claves", [["x"]]), ("adiciones", {"holdouts": [["a"]]}),
                             ("seq", [1]), ("claves", [{"a": 1}])):
            with self.subTest(campo=campo, valor=valor):
                es = self._dos()
                es[0][campo] = valor
                self._rehash(es[0])
                self.assertInvalida(es)

    def test_texto_libre_y_fecha_invalidos_en_registro(self):
        for campo, valor in (("motivo", "a\x1bb"), ("usuario", "a b"), ("motivo", "a\ud800b"),
                             ("motivo", "x" * 501), ("usuario", "y" * 201),
                             ("fecha_declarada", "２０２６-１０-１３"), ("fecha_declarada", "2026-02-30"),
                             ("fecha_declarada", "f")):
            with self.subTest(campo=campo, valor=valor):
                es = self._dos()
                es[0][campo] = valor
                self._rehash(es[0])
                self.assertInvalida(es)

    def test_recursion_profunda_en_registro(self):
        self._dos()
        self.assertInvalida(texto="[" * 200000 + "]" * 200000 + "\n")

    def test_hash_acumulado_no_coincide(self):
        es = self._dos()
        es[0]["guardrails_hash_after"] = "f" * 64
        es[1]["guardrails_hash_before"] = "f" * 64
        self._rehash(es[0])
        self._rehash(es[1])
        self.assertInvalida(es)

    def test_no_utf8(self):
        self._dos()
        ga.ruta_registro(self.repo).write_bytes(b"\xff\xfe\x00")
        res = ga.cargar_adopciones(self.repo)
        self.assertFalse(res.valida)
        self.assertEqual(res.entradas, ())

    def test_cadena_invalida_no_cuenta_en_baseline(self):
        es = self._dos()
        es[1]["seq"] = 7
        self.reescribir(es)
        res = ga.cargar_adopciones(self.repo)
        self.assertEqual(ga.baseline_efectivo(self.plantilla, res), self.plantilla)


class TestBaselineEfectivo(BaseTemporal):
    def test_sin_adopciones_es_copia(self):
        base = ga.baseline_efectivo(self.plantilla, vacia())
        self.assertEqual(base, self.plantilla)
        self.assertIsNot(base, self.plantilla)
        base["holdouts"].append("x")
        self.assertEqual(self.plantilla, plantilla_base())

    def test_acumulativo_y_orden(self):
        self.adoptar(self.con_holdouts("h3"))
        actual2 = self.con_holdouts("h3", "h4")
        actual2["autonomy"]["sealed_sources"].append("src/nuevo")
        actual2["data_raw"].append("raw2")
        plan2, _ = self.adoptar(actual2)
        # La segunda adopción parte del baseline ampliado: solo lo nuevo.
        self.assertEqual(plan2.adiciones["holdouts"], ("h4",))
        base = ga.baseline_efectivo(self.plantilla, ga.cargar_adopciones(self.repo))
        self.assertEqual(base["holdouts"], ["data/holdout", "data/sellado", "h3", "h4"])
        self.assertEqual(base["data_raw"], ["data/raw", "raw2"])
        self.assertEqual(base["autonomy"]["sealed_sources"], ["src/sellado", "src/nuevo"])
        self.assertEqual(base["excepciones"], [])
        self.assertEqual(base["autonomy"]["source_access"], self.plantilla["autonomy"]["source_access"])

    def test_segunda_adopcion_no_repite(self):
        self.adoptar(self.con_holdouts("h3"))
        plan = ga.planificar_adopcion(self.con_holdouts("h3"), self.plantilla, ga.cargar_adopciones(self.repo))
        self.assertTrue(plan.es_noop)

    def test_hash_estado_solo_claves_elegibles(self):
        a = plantilla_base()
        b = plantilla_base()
        b["excepciones"] = ["x"]
        b["autonomy"]["mode"] = "autonomous"
        b["autonomy"]["source_access"] = {"z": 1}
        self.assertEqual(ga.hash_estado(a), ga.hash_estado(b))
        b["secretos_extra"].append("nuevo")
        self.assertNotEqual(ga.hash_estado(a), ga.hash_estado(b))
        c = plantilla_base()
        c["autonomy"]["sealed_sources"].append("s")
        self.assertNotEqual(ga.hash_estado(a), ga.hash_estado(c))

    def test_claves_elegibles_exactas(self):
        self.assertEqual(ga.CLAVES_ELEGIBLES, ("holdouts", "data_raw", "secretos_extra", "autonomy.sealed_sources"))
        self.assertEqual(ga.RUTA_REGISTRO_RELATIVA, "openspec/decisions/guardrails-adoptions.jsonl")
        self.assertEqual(ga.SCHEMA_VERSION, 1)
        self.assertEqual(ga.COD_ADOPCION_INVALIDA, "GUARDRAILS-ADOPCION-INVALIDA")


class TestAplicarAdopcion(BaseTemporal):
    def test_exito_encadenado(self):
        plan1, e1 = self.adoptar(self.con_holdouts("h1"), utc="2026-10-13T10:00:01Z")
        self.assertEqual(e1["seq"], 1)
        self.assertEqual(e1["prev_hash"], "")
        self.assertEqual(e1["utc"], "2026-10-13T10:00:01Z")
        self.assertEqual(e1["claves"], ["holdouts"])
        self.assertEqual(e1["adiciones"], {"holdouts": ["h1"]})
        self.assertEqual(e1["guardrails_hash_before"], plan1.hash_antes)
        self.assertEqual(e1["guardrails_hash_after"], plan1.hash_despues)
        self.assertEqual(e1["approval_channel"], "console_confirmed")
        self.assertEqual(e1["channel_version"], "console/v1")
        self.assertEqual(e1["fecha_declarada"], "2026-10-13")
        self.assertEqual(e1["entry_hash"], ga._hash_entrada(e1))
        _, e2 = self.adoptar(self.con_holdouts("h1", "h2"))
        self.assertEqual(e2["seq"], 2)
        self.assertEqual(e2["prev_hash"], e1["entry_hash"])
        self.assertEqual(e2["guardrails_hash_before"], e1["guardrails_hash_after"])
        self.assertEqual(len(self.lineas()), 2)
        self.assertTrue(ga.cargar_adopciones(self.repo).valida)
        self.assertEqual([x for x in os.listdir(ga.ruta_registro(self.repo).parent) if x.endswith(".tmp")], [])

    def test_hash_despues_coincide_con_estado_siguiente(self):
        plan1, _ = self.adoptar(self.con_holdouts("h1"))
        plan2 = ga.planificar_adopcion(self.con_holdouts("h1", "h2"), self.plantilla, ga.cargar_adopciones(self.repo))
        self.assertEqual(plan2.hash_antes, plan1.hash_despues)

    def test_cadena_sobrevive_a_cambio_de_plantilla(self):
        self.adoptar(self.con_holdouts("h1"))
        # Harmessi actualiza la plantilla entre adopciones.
        self.plantilla["holdouts"].append("nuevo-de-harmessi")
        self.plantilla["excepciones"] = ["otra"]
        actual = self.con_holdouts("h1", "h2")
        plan, entrada = self.adoptar(actual)
        self.assertEqual(plan.adiciones, {"holdouts": ("h2",)})
        self.assertEqual(entrada["seq"], 2)
        res = ga.cargar_adopciones(self.repo)
        self.assertTrue(res.valida)
        self.assertEqual(len(res.entradas), 2)

    def test_plan_captura_identidad_de_ultima_entrada(self):
        _, e1 = self.adoptar(self.con_holdouts("h1"))
        plan = ga.planificar_adopcion(self.con_holdouts("h1", "h2"), self.plantilla, ga.cargar_adopciones(self.repo))
        self.assertEqual(plan.ultima_seq, 1)
        self.assertEqual(plan.ultimo_entry_hash, e1["entry_hash"])

    def test_hash_despues_inconsistente_rechaza(self):
        plan = ga.planificar_adopcion(self.con_holdouts("h1"), self.plantilla, vacia())
        malo = dataclasses.replace(plan, hash_despues="0" * 64)
        with self.assertRaises(ValueError):
            ga.aplicar_adopcion(self.repo, malo, motivo="m", usuario="u", fecha="2026-10-13",
                                campos_t1=T1, esperado_hash_antes=malo.hash_antes)
        self.assertFalse(ga.ruta_registro(self.repo).exists())

    def test_adiciones_alteradas_con_hash_original_rechaza(self):
        plan = ga.planificar_adopcion(self.con_holdouts("h1"), self.plantilla, vacia())
        malo = dataclasses.replace(plan, adiciones={"holdouts": ("otro",)})
        with self.assertRaises(ValueError):
            ga.aplicar_adopcion(self.repo, malo, motivo="m", usuario="u", fecha="2026-10-13",
                                campos_t1=T1, esperado_hash_antes=malo.hash_antes)

    def test_elemento_con_esc_en_plan_rechaza(self):
        plan = ga.planificar_adopcion(self.con_holdouts("h1"), self.plantilla, vacia())
        malo = dataclasses.replace(plan, adiciones={"holdouts": ("a\x1bb",)})
        with self.assertRaises(ValueError):
            ga.aplicar_adopcion(self.repo, malo, motivo="m", usuario="u", fecha="2026-10-13",
                                campos_t1=T1, esperado_hash_antes=malo.hash_antes)

    def test_carrera_justo_antes_del_replace(self):
        plan = ga.planificar_adopcion(self.con_holdouts("h1"), self.plantilla, vacia())
        # Primera lectura: registro ausente; segunda (previa al replace): alguien lo creó.
        with mock.patch.object(ga, "_leer_registro", side_effect=[None, b"otra-cosa\n"]):
            with self.assertRaises(ValueError):
                ga.aplicar_adopcion(self.repo, plan, motivo="m", usuario="u", fecha="2026-10-13",
                                    campos_t1=T1, esperado_hash_antes=plan.hash_antes)
        self.assertFalse(ga.ruta_registro(self.repo).exists())
        self.assertEqual([x for x in os.listdir(ga.ruta_registro(self.repo).parent) if x.endswith(".tmp")], [])

    def _intentar(self, plan, **kw):
        args = dict(motivo="m", usuario="u", fecha="2026-10-13")
        args.update(kw)
        return ga.aplicar_adopcion(self.repo, plan, campos_t1=T1,
                                   esperado_hash_antes=plan.hash_antes, **args)

    def test_texto_libre_invalido_rechaza(self):
        plan = ga.planificar_adopcion(self.con_holdouts("h1"), self.plantilla, vacia())
        casos = [
            {"motivo": "a\x1bb"}, {"usuario": "a\x1bb"},
            {"motivo": "a b"}, {"usuario": "a b"},
            {"motivo": "a\ud800b"}, {"motivo": "a‮b"}, {"usuario": "a​b"},
            {"motivo": "x" * 501}, {"usuario": "x" * 201},
            {"fecha": "２０２６-１０-１３"}, {"fecha": "2026-13-01"}, {"fecha": "2026-02-30"},
            {"fecha": "2026-10-13\n"}, {"fecha": "26-10-13"}, {"fecha": "f"},
        ]
        for kw in casos:
            with self.subTest(kw=kw):
                with self.assertRaises(ValueError):
                    self._intentar(plan, **kw)
        self.assertFalse(ga.ruta_registro(self.repo).exists())

    def test_texto_libre_en_limite_ok(self):
        plan = ga.planificar_adopcion(self.con_holdouts("h1"), self.plantilla, vacia())
        entrada = self._intentar(plan, motivo="x" * 500, usuario="y" * 200)
        self.assertEqual(len(entrada["motivo"]), 500)

    def test_crea_directorio(self):
        self.assertFalse(ga.ruta_registro(self.repo).parent.exists())
        self.adoptar(self.con_holdouts("h1"))
        self.assertTrue(ga.ruta_registro(self.repo).is_file())

    def test_conflicto_esperado_hash_antes(self):
        plan = ga.planificar_adopcion(self.con_holdouts("h1"), self.plantilla, vacia())
        with self.assertRaises(ValueError):
            ga.aplicar_adopcion(self.repo, plan, motivo="m", usuario="u", fecha="2026-10-13",
                                campos_t1=T1, esperado_hash_antes="0" * 64)
        self.assertFalse(ga.ruta_registro(self.repo).exists())

    def test_conflicto_registro_cambio(self):
        plan_viejo = ga.planificar_adopcion(self.con_holdouts("h1"), self.plantilla, vacia())
        self.adoptar(self.con_holdouts("hx"))  # otro proceso adopta antes
        antes = ga.ruta_registro(self.repo).read_bytes()
        with self.assertRaises(ValueError):
            ga.aplicar_adopcion(self.repo, plan_viejo, motivo="m", usuario="u", fecha="2026-10-13",
                                campos_t1=T1, esperado_hash_antes=plan_viejo.hash_antes)
        self.assertEqual(ga.ruta_registro(self.repo).read_bytes(), antes)

    def test_canal_distinto_rechaza(self):
        plan = ga.planificar_adopcion(self.con_holdouts("h1"), self.plantilla, vacia())
        malos = [
            {**T1, "approval_channel": "declared"},
            {k: v for k, v in T1.items() if k != "approval_channel"},
            {k: v for k, v in T1.items() if k != "channel_version"},
            {**T1, "confirmed_at": ""},
            None,
            "console_confirmed",
        ]
        for campos in malos:
            with self.subTest(campos=campos):
                with self.assertRaises(ValueError):
                    ga.aplicar_adopcion(self.repo, plan, motivo="m", usuario="u", fecha="2026-10-13",
                                        campos_t1=campos, esperado_hash_antes=plan.hash_antes)
        self.assertFalse(ga.ruta_registro(self.repo).exists())

    def test_rechaza_noop_y_rechazos(self):
        noop = ga.planificar_adopcion(copy.deepcopy(self.plantilla), self.plantilla, vacia())
        self.assertTrue(noop.es_noop)
        actual = self.con_holdouts("h1")
        actual["excepciones"] = ["x"]
        rechazado = ga.planificar_adopcion(actual, self.plantilla, vacia())
        for plan in (noop, rechazado):
            with self.assertRaises(ValueError):
                ga.aplicar_adopcion(self.repo, plan, motivo="m", usuario="u", fecha="2026-10-13",
                                    campos_t1=T1, esperado_hash_antes=plan.hash_antes)
        self.assertFalse(ga.ruta_registro(self.repo).exists())

    def test_campos_obligatorios(self):
        plan = ga.planificar_adopcion(self.con_holdouts("h1"), self.plantilla, vacia())
        for kw in ({"motivo": ""}, {"usuario": " "}, {"fecha": None}):
            with self.subTest(kw=kw):
                args = dict(motivo="m", usuario="u", fecha="2026-10-13")
                args.update(kw)
                with self.assertRaises(ValueError):
                    ga.aplicar_adopcion(self.repo, plan, campos_t1=T1,
                                        esperado_hash_antes=plan.hash_antes, **args)

    def test_cadena_previa_invalida_rechaza(self):
        self.adoptar(self.con_holdouts("h1"))
        ga.ruta_registro(self.repo).write_text("basura\n", encoding="utf-8")
        plan = ga.planificar_adopcion(self.con_holdouts("h1", "h2"), self.plantilla, vacia())
        with self.assertRaises(ValueError):
            ga.aplicar_adopcion(self.repo, plan, motivo="m", usuario="u", fecha="2026-10-13",
                                campos_t1=T1, esperado_hash_antes=plan.hash_antes)
        self.assertEqual(ga.ruta_registro(self.repo).read_text(encoding="utf-8"), "basura\n")

    def test_fallo_os_replace_sin_estado_a_medias(self):
        plan = ga.planificar_adopcion(self.con_holdouts("h1"), self.plantilla, vacia())
        with mock.patch.object(ga.os, "replace", side_effect=OSError("simulado")):
            with self.assertRaises(OSError):
                ga.aplicar_adopcion(self.repo, plan, motivo="m", usuario="u", fecha="2026-10-13",
                                    campos_t1=T1, esperado_hash_antes=plan.hash_antes)
        self.assertFalse(ga.ruta_registro(self.repo).exists())
        self.assertEqual(os.listdir(ga.ruta_registro(self.repo).parent), [])

    def test_fallo_os_replace_preserva_registro_previo(self):
        self.adoptar(self.con_holdouts("h1"))
        antes = ga.ruta_registro(self.repo).read_bytes()
        plan = ga.planificar_adopcion(self.con_holdouts("h1", "h2"), self.plantilla, ga.cargar_adopciones(self.repo))
        with mock.patch.object(ga.os, "replace", side_effect=OSError("simulado")):
            with self.assertRaises(OSError):
                ga.aplicar_adopcion(self.repo, plan, motivo="m", usuario="u", fecha="2026-10-13",
                                    campos_t1=T1, esperado_hash_antes=plan.hash_antes)
        self.assertEqual(ga.ruta_registro(self.repo).read_bytes(), antes)
        self.assertEqual([x for x in os.listdir(ga.ruta_registro(self.repo).parent) if x.endswith(".tmp")], [])

    def test_no_toca_guardrails_ni_control(self):
        claude = self.repo / ".claude"
        claude.mkdir()
        guardrails = claude / "guardrails.json"
        guardrails.write_text(json.dumps(self.con_holdouts("h1")), encoding="utf-8")
        control = self.repo / "control.json"
        control.write_text("{}", encoding="utf-8")
        antes = (guardrails.read_bytes(), control.read_bytes())
        self.adoptar(self.con_holdouts("h1"))
        self.assertEqual((guardrails.read_bytes(), control.read_bytes()), antes)
        self.assertEqual(sorted(p.name for p in self.repo.iterdir()), [".claude", "control.json", "openspec"])


class TestRutasCubiertas(BaseTemporal):
    def test_cubierta_exacta(self):
        actual = self.con_holdouts("h1")
        actual["autonomy"]["sealed_sources"].append("src/nuevo")
        self.adoptar(actual)
        res = ga.cargar_adopciones(self.repo)
        self.assertEqual(ga.rutas_cubiertas(actual, self.plantilla, res), {"holdouts", "autonomy.sealed_sources"})

    def test_cubierta_independiente_del_orden(self):
        self.adoptar(self.con_holdouts("h1", "h2"))
        actual = self.con_holdouts("h2", "h1", base=list(reversed(self.plantilla["holdouts"])))
        self.assertEqual(ga.rutas_cubiertas(actual, self.plantilla, ga.cargar_adopciones(self.repo)), {"holdouts"})

    def test_elemento_extra_no_adoptado(self):
        self.adoptar(self.con_holdouts("h1"))
        actual = self.con_holdouts("h1", "extra")
        self.assertEqual(ga.rutas_cubiertas(actual, self.plantilla, ga.cargar_adopciones(self.repo)), set())

    def test_sin_adopciones_no_cubre(self):
        self.assertEqual(ga.rutas_cubiertas(self.con_holdouts("h1"), self.plantilla, vacia()), set())

    def test_adoptado_eliminado(self):
        self.adoptar(self.con_holdouts("h1", "h2"))
        actual = self.con_holdouts("h1")
        self.assertEqual(ga.rutas_cubiertas(actual, self.plantilla, ga.cargar_adopciones(self.repo)), set())

    def test_clave_prohibida_cambiada(self):
        actual = self.con_holdouts("h1")
        self.adoptar(actual)
        actual["excepciones"] = ["x"]
        actual["autonomy"]["source_access"] = {"w": 1}
        res = ga.cargar_adopciones(self.repo)
        cubiertas = ga.rutas_cubiertas(actual, self.plantilla, res)
        self.assertEqual(cubiertas, {"holdouts"})  # las prohibidas siguen siendo drift
        self.assertNotIn("excepciones", cubiertas)
        self.assertNotIn("autonomy.source_access", cubiertas)

    def test_elegible_removido_de_plantilla(self):
        self.adoptar(self.con_holdouts("h1"))
        actual = self.con_holdouts("h1")
        actual["holdouts"].remove("data/sellado")
        self.assertEqual(ga.rutas_cubiertas(actual, self.plantilla, ga.cargar_adopciones(self.repo)), set())

    def test_sin_adopcion_para_la_ruta_no_cubre(self):
        # Reorden puro o duplicado puro sin adopción: el drift sigue siendo drift.
        reorden = copy.deepcopy(self.plantilla)
        reorden["holdouts"].reverse()
        duplicado = copy.deepcopy(self.plantilla)
        duplicado["holdouts"].append("data/holdout")
        for actual in (reorden, duplicado):
            self.assertEqual(ga.rutas_cubiertas(actual, self.plantilla, vacia()), set())
        # Con una adopción en OTRA ruta, tampoco cubre holdouts.
        otra = self.plantilla["data_raw"] + ["raw2"]
        a = copy.deepcopy(self.plantilla)
        a["data_raw"] = otra
        self.adoptar(a)
        res = ga.cargar_adopciones(self.repo)
        reorden["data_raw"] = otra
        self.assertEqual(ga.rutas_cubiertas(reorden, self.plantilla, res), {"data_raw"})

    def test_no_hashables_sin_excepcion(self):
        self.adoptar(self.con_holdouts("h1"))
        actual = self.con_holdouts("h1")
        actual["holdouts"] = [["a"]]
        self.assertEqual(ga.rutas_cubiertas(actual, self.plantilla, ga.cargar_adopciones(self.repo)), set())

    def test_tipo_erroneo(self):
        self.adoptar(self.con_holdouts("h1"))
        actual = self.con_holdouts("h1")
        actual["holdouts"] = "data/holdout"
        self.assertEqual(ga.rutas_cubiertas(actual, self.plantilla, ga.cargar_adopciones(self.repo)), set())

    def test_cadena_rota_ninguna(self):
        actual = self.con_holdouts("h1")
        self.adoptar(actual)
        es = [json.loads(l) for l in self.lineas()]
        es[0]["motivo"] = "alterado"
        self.reescribir(es)
        res = ga.cargar_adopciones(self.repo)
        self.assertFalse(res.valida)
        self.assertEqual(ga.rutas_cubiertas(actual, self.plantilla, res), set())

    def test_entradas_malformadas(self):
        self.assertEqual(ga.rutas_cubiertas([], self.plantilla, vacia()), set())
        self.assertEqual(ga.rutas_cubiertas(self.plantilla, [], vacia()), set())


class TestHashDiff(BaseTemporal):
    def plan(self):
        actual = self.con_holdouts("h1")
        actual["data_raw"].append("r2")
        return ga.planificar_adopcion(actual, self.plantilla, vacia())

    def test_diff_canonico_forma(self):
        plan = self.plan()
        d = ga.diff_canonico(plan)
        self.assertEqual(set(d), {"operacion", "target", "hash_antes", "adiciones", "hash_despues"})
        self.assertEqual(d["operacion"], "guardrails-readopt")
        self.assertEqual(d["target"], "guardrails.json")
        self.assertEqual(d["adiciones"], {"data_raw": ["r2"], "holdouts": ["h1"]})
        json.dumps(d)

    def test_estable(self):
        self.assertEqual(ga.hash_diff(self.plan()), ga.hash_diff(self.plan()))
        self.assertEqual(len(ga.hash_diff(self.plan())), 64)

    def test_sensible_a_cada_cambio(self):
        plan = self.plan()
        base = ga.hash_diff(plan)
        variantes = [
            dataclasses.replace(plan, hash_antes="a" * 64),
            dataclasses.replace(plan, hash_despues="b" * 64),
            dataclasses.replace(plan, adiciones={**plan.adiciones, "holdouts": ("h1", "h9")}),
            dataclasses.replace(plan, adiciones={"holdouts": plan.adiciones["holdouts"]}),
            dataclasses.replace(plan, adiciones={"holdouts": ("h1",), "data_raw": ("r3",)}),
        ]
        for v in variantes:
            self.assertNotEqual(ga.hash_diff(v), base)

    def test_orden_de_claves_no_afecta(self):
        plan = self.plan()
        otro = dataclasses.replace(plan, adiciones=dict(reversed(list(plan.adiciones.items()))))
        self.assertEqual(ga.hash_diff(otro), ga.hash_diff(plan))


class TestPrivacidadYStdlib(BaseTemporal):
    def test_claves_esperadas(self):
        _, entrada = self.adoptar(self.con_holdouts("h1"))
        self.assertEqual(set(entrada), {
            "schema_version", "seq", "utc", "claves", "adiciones", "guardrails_hash_before",
            "guardrails_hash_after", "prev_hash", "motivo", "usuario", "fecha_declarada",
            "approval_channel", "confirmed_at", "channel_version", "entry_hash",
        })
        texto = ga.ruta_registro(self.repo).read_text(encoding="utf-8").lower()
        for prohibido in ("challenge", "respuesta", "codigo"):
            self.assertNotIn(prohibido, texto)

    def test_campos_extra_de_t1_no_se_persisten(self):
        plan = ga.planificar_adopcion(self.con_holdouts("h1"), self.plantilla, vacia())
        entrada = ga.aplicar_adopcion(
            self.repo, plan, motivo="m", usuario="u", fecha="2026-10-13",
            campos_t1={**T1, "challenge": "ABC123", "terminal": "tty1"},
            esperado_hash_antes=plan.hash_antes,
        )
        self.assertNotIn("challenge", entrada)
        self.assertNotIn("terminal", entrada)
        self.assertNotIn("ABC123", ga.ruta_registro(self.repo).read_text(encoding="utf-8"))

    def test_solo_stdlib(self):
        fuente = Path(ga.__file__).read_text(encoding="utf-8")
        permitidos = {"__future__", "copy", "hashlib", "json", "os", "re", "tempfile",
                      "unicodedata", "dataclasses", "datetime", "pathlib"}
        for nodo in ast.walk(ast.parse(fuente)):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    self.assertIn(alias.name.split(".")[0], permitidos)
            elif isinstance(nodo, ast.ImportFrom):
                if nodo.level:
                    # Relativo dentro del mismo paquete: solo el módulo hermano de drift.
                    self.assertIsNone(nodo.module)
                    self.assertEqual([a.name for a in nodo.names], ["guardrails_drift"])
                else:
                    self.assertIn((nodo.module or "").split(".")[0], permitidos)
                    self.assertFalse((nodo.module or "").startswith("tools"))


# --- CLI: `ds_guard guardrails readopt` (Writer D) -------------------------------
# Repo destino temporal + plantilla "origen" temporal (parcheando `_ruta_plantilla_guardrails`).
# La confirmación T1 se inyecta parcheando `human_presence.solicitar_confirmacion`.

import contextlib  # noqa: E402
import io  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

_REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ORIGEN))
sys.path.insert(0, str(_REPO_ORIGEN / "tools"))

import ds_guard  # noqa: E402
from dsguard import human_presence  # noqa: E402
from tools.dsguard import checks as _checks  # noqa: E402
from tools.harmessi import doctor  # noqa: E402

_DS_GUARD = _REPO_ORIGEN / "tools" / "ds_guard.py"


def _resultado_ok():
    return human_presence.ResultadoPresencia(
        ok=True, canal=human_presence.CANAL_CONSOLE, confirmed_at="2026-10-13T12:00:00Z",
        channel_version="console/v1", motivo="")


def _resultado_fallo(motivo="confirmacion rechazada (prueba)"):
    return human_presence.ResultadoPresencia(
        ok=False, canal=None, confirmed_at=None, channel_version=None, motivo=motivo)


class _BaseReadopt(unittest.TestCase):
    def setUp(self):
        self.destino = Path(tempfile.mkdtemp(prefix="readopt_dest_"))
        self.origen = Path(tempfile.mkdtemp(prefix="readopt_orig_"))
        self.addCleanup(shutil.rmtree, self.destino, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.origen, ignore_errors=True)
        self.plantilla = plantilla_base()
        (self.origen / ".claude").mkdir()
        (self.origen / ".claude" / "guardrails.json").write_text(
            json.dumps(self.plantilla), encoding="utf-8")
        (self.destino / ".claude").mkdir()
        self.guardrails = self.destino / ".claude" / "guardrails.json"
        self.control = self.destino / "control.json"
        self.control.write_text('{"intacto": true}\n', encoding="utf-8")
        self.escribir(self.plantilla)
        parche = mock.patch.object(
            ds_guard, "_ruta_plantilla_guardrails",
            return_value=self.origen / ".claude" / "guardrails.json")
        parche.start()
        self.addCleanup(parche.stop)

    def escribir(self, datos):
        self.guardrails.write_text(json.dumps(datos), encoding="utf-8")

    def variante(self, **cambios):
        actual = copy.deepcopy(self.plantilla)
        actual.update(cambios)
        return actual

    def argv(self, extra=(), motivo="endurecer", usuario="federico"):
        return ["guardrails", "readopt", "--motivo", motivo, "--usuario", usuario,
                "--destino", str(self.destino), *extra]

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

    def registro(self):
        return ga.ruta_registro(self.destino)

    def drift(self):
        with mock.patch.object(doctor.manifest_mod, "raiz_repo_origen", return_value=self.origen):
            return doctor._drift_guardrails_json(self.guardrails, ".claude/guardrails.json", self.destino)

    def snapshot(self):
        return self.guardrails.read_bytes(), self.control.read_bytes()


class TestCliReadopt(_BaseReadopt):
    def test_adicion_elegible_aplicada(self):
        self.escribir(self.variante(holdouts=self.plantilla["holdouts"] + ["data/nuevo"]))
        antes = self.snapshot()
        codigo, out, err, m = self.correr(self.argv())
        self.assertEqual(codigo, 0, err)
        m.assert_called_once()
        self.assertIn("data/nuevo", out)
        self.assertEqual(self.snapshot(), antes)  # guardrails.json y control.json intactos byte a byte
        res = ga.cargar_adopciones(self.destino)
        self.assertTrue(res.valida)
        self.assertEqual(len(res.entradas), 1)
        self.assertEqual(res.entradas[0]["adiciones"], {"holdouts": ["data/nuevo"]})
        self.assertEqual(res.entradas[0]["approval_channel"], "console_confirmed")

    def test_mixto_con_excepciones_rechazo_total(self):
        self.escribir(self.variante(holdouts=self.plantilla["holdouts"] + ["data/nuevo"], excepciones=["x"]))
        codigo, _o, err, m = self.correr(self.argv())
        self.assertEqual(codigo, 2)
        m.assert_not_called()
        self.assertFalse(self.registro().exists())
        self.assertIn("excepciones", err)

    def test_mixto_con_remocion_rechazo_total(self):
        self.escribir(self.variante(holdouts=["data/holdout", "data/nuevo"]))  # quita data/sellado
        codigo, _o, _e, m = self.correr(self.argv())
        self.assertEqual(codigo, 2)
        m.assert_not_called()
        self.assertFalse(self.registro().exists())

    def test_solo_inelegible_rechazo(self):
        self.escribir(self.variante(write_scopes={"escritor": ["src/**", "otro/**"]}))
        codigo, _o, _e, m = self.correr(self.argv())
        self.assertEqual(codigo, 2)
        m.assert_not_called()
        self.assertFalse(self.registro().exists())

    def test_sealed_sources_solo_add(self):
        actual = copy.deepcopy(self.plantilla)
        actual["autonomy"]["sealed_sources"] = ["src/sellado", "src/otro"]
        self.escribir(actual)
        codigo, _o, err, _m = self.correr(self.argv())
        self.assertEqual(codigo, 0, err)
        # desellar no es re-adoptable
        actual["autonomy"]["sealed_sources"] = []
        self.escribir(actual)
        codigo, _o, _e, m = self.correr(self.argv())
        self.assertEqual(codigo, 2)
        m.assert_not_called()
        self.assertEqual(len(ga.cargar_adopciones(self.destino).entradas), 1)

    def test_noop_sin_t1_ni_registro(self):
        codigo, out, _e, m = self.correr(self.argv())
        self.assertEqual(codigo, 0)
        m.assert_not_called()
        self.assertIn("no-op", out)
        self.assertFalse(self.registro().exists())

    def test_dry_run(self):
        self.escribir(self.variante(data_raw=self.plantilla["data_raw"] + ["data/raw2"]))
        antes = self.snapshot()
        codigo, out, _e, m = self.correr(self.argv(extra=["--dry-run"]))
        self.assertEqual(codigo, 0)
        m.assert_not_called()
        self.assertIn("hash_diff", out)
        self.assertIn("data/raw2", out)
        self.assertFalse(self.registro().exists())
        self.assertEqual(self.snapshot(), antes)

    def test_t1_fallido_sin_escritura(self):
        self.escribir(self.variante(holdouts=self.plantilla["holdouts"] + ["data/nuevo"]))
        codigo, _o, err, m = self.correr(self.argv(), resultado=_resultado_fallo("sin consola"))
        self.assertEqual(codigo, 2)
        m.assert_called_once()
        self.assertIn("sin consola", err)
        self.assertFalse(self.registro().exists())

    def test_control_en_motivo_o_elemento_rechaza_antes_del_prompt(self):
        self.escribir(self.variante(holdouts=self.plantilla["holdouts"] + ["data/nuevo"]))
        codigo, _o, _e, m = self.correr(self.argv(motivo="x\x1b[2Jy"))
        self.assertEqual(codigo, 2)
        m.assert_not_called()
        self.escribir(self.variante(holdouts=self.plantilla["holdouts"] + ["data/n\x1bnuevo"]))
        codigo, _o, _e, m = self.correr(self.argv())
        self.assertEqual(codigo, 2)
        m.assert_not_called()
        self.assertFalse(self.registro().exists())

    def test_diff_muestra_destino_y_declarados(self):
        self.escribir(self.variante(holdouts=self.plantilla["holdouts"] + ["data/nuevo"]))
        codigo, out, _e, _m = self.correr(self.argv(extra=["--dry-run"]))
        self.assertEqual(codigo, 0)
        self.assertIn("destino:", out)
        self.assertIn("endurecer", out)
        self.assertIn("federico", out)

    def test_fecha_invalida(self):
        self.escribir(self.variante(holdouts=self.plantilla["holdouts"] + ["data/nuevo"]))
        codigo, _o, _e, m = self.correr(self.argv(extra=["--fecha", "2026-02-30"]))
        self.assertEqual(codigo, 2)
        m.assert_not_called()

    def test_sin_flags_de_canal_ni_atajos(self):
        for flag in (["--channel", "declared"], ["--yes"], ["--force"], ["--accept-current-state"],
                     ["--adopt-all"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
                ds_guard.main(self.argv(extra=flag))
            self.assertEqual(cm.exception.code, 2)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ds_guard.main(["guardrails", "accept-current-state"])

    def test_expected_guardrails_hash(self):
        self.escribir(self.variante(holdouts=self.plantilla["holdouts"] + ["data/nuevo"]))
        codigo, _o, _e, m = self.correr(self.argv(extra=["--expected-guardrails-hash", "0" * 64]))
        self.assertEqual(codigo, 2)
        m.assert_not_called()
        self.assertFalse(self.registro().exists())
        actual = json.loads(self.guardrails.read_text(encoding="utf-8"))
        ok = ga.planificar_adopcion(actual, self.plantilla, ga.cargar_adopciones(self.destino)).hash_antes
        codigo, _o, err, _m = self.correr(self.argv(extra=["--expected-guardrails-hash", ok]))
        self.assertEqual(codigo, 0, err)

    def test_estado_cambia_durante_t1_aborta(self):
        self.escribir(self.variante(holdouts=self.plantilla["holdouts"] + ["data/nuevo"]))

        def efecto(_ctx):
            self.escribir(self.variante(holdouts=self.plantilla["holdouts"] + ["data/nuevo", "data/otro"]))
            return _resultado_ok()

        codigo, _o, err, _m = self.correr(self.argv(), efectos=efecto)
        self.assertEqual(codigo, 2)
        self.assertIn("cambió durante la confirmación", err)
        self.assertFalse(self.registro().exists())

    def test_guardrails_malformado_o_inexistente(self):
        self.guardrails.write_text("{no es json", encoding="utf-8")
        codigo, _o, _e, m = self.correr(self.argv())
        self.assertEqual(codigo, 2)
        m.assert_not_called()
        self.guardrails.unlink()
        codigo, _o, _e, m = self.correr(self.argv())
        self.assertEqual(codigo, 2)
        self.assertFalse(self.registro().exists())

    def test_plantilla_indeterminable(self):
        self.escribir(self.variante(holdouts=self.plantilla["holdouts"] + ["data/nuevo"]))
        with mock.patch.object(ds_guard, "_ruta_plantilla_guardrails", return_value=None):
            codigo, _o, err, m = self.correr(self.argv())
        self.assertEqual(codigo, 2)
        m.assert_not_called()
        self.assertIn("clon de Harmessi", err)

    def test_binding_hash_diff_y_distinto_entre_operaciones(self):
        actual1 = self.variante(holdouts=self.plantilla["holdouts"] + ["data/nuevo"])
        self.escribir(actual1)
        plan1 = ga.planificar_adopcion(actual1, self.plantilla, vacia())
        codigo, _o, err, m1 = self.correr(self.argv())
        self.assertEqual(codigo, 0, err)
        ctx1 = m1.call_args[0][0]
        self.assertEqual(ctx1["hash"], ga.hash_diff(plan1))
        self.assertEqual(ctx1["change_id"], "proyecto")
        self.assertEqual(ctx1["artefacto"], "guardrails-readopt")
        self.assertEqual(ctx1["accion"], "guardrails-readopt: holdouts+1")
        self.escribir(self.variante(holdouts=self.plantilla["holdouts"] + ["data/nuevo", "data/dos"]))
        codigo, _o, err, m2 = self.correr(self.argv())
        self.assertEqual(codigo, 0, err)
        self.assertNotEqual(m2.call_args[0][0]["hash"], ctx1["hash"])
        self.assertEqual(len(ga.cargar_adopciones(self.destino).entradas), 2)

    def test_doctor_refleja_nuevo_baseline(self):
        self.escribir(self.variante(holdouts=self.plantilla["holdouts"] + ["data/nuevo"]))
        self.assertEqual(self.drift().status, _checks.STATUS_WARN)
        codigo, _o, err, _m = self.correr(self.argv())
        self.assertEqual(codigo, 0, err)
        res = self.drift()
        self.assertEqual(res.status, _checks.STATUS_PASS)
        self.assertIn("re-adopci", res.message)
        # drift posterior: un elemento extra no adoptado vuelve a ser drift
        self.escribir(self.variante(holdouts=self.plantilla["holdouts"] + ["data/nuevo", "data/extra"]))
        self.assertEqual(self.drift().status, _checks.STATUS_WARN)
        # volver a la plantilla ya no es drift
        self.escribir(self.plantilla)
        self.assertIsNone(self.drift())
        self.assertTrue(ga.cargar_adopciones(self.destino).valida)

    def test_registro_alterado_deja_de_contar(self):
        self.escribir(self.variante(holdouts=self.plantilla["holdouts"] + ["data/nuevo"]))
        self.correr(self.argv())
        texto = self.registro().read_text(encoding="utf-8")
        self.registro().write_text(texto.replace("data/nuevo", "data/otro"), encoding="utf-8")
        self.assertEqual(self.drift().status, _checks.STATUS_WARN)
        codigo, _o, _e, m = self.correr(self.argv())
        self.assertEqual(codigo, 2)
        m.assert_not_called()

    def test_subproceso_real_con_stdin_por_pipe_falla_cerrado(self):
        canal, _motivo = human_presence.canal_consola_real()
        if canal is not None:
            canal.cerrar()
            self.skipTest("hay consola de control real en este entorno")
        real = json.loads((_REPO_ORIGEN / ".claude" / "guardrails.json").read_text(encoding="utf-8"))
        real["holdouts"] = list(real.get("holdouts", [])) + ["data/nuevo_subproceso"]
        self.escribir(real)
        r = subprocess.run(
            [sys.executable, str(_DS_GUARD), *self.argv()],
            cwd=str(self.destino), input="ABCDEF\n", capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse(self.registro().exists())


if __name__ == "__main__":
    unittest.main()
