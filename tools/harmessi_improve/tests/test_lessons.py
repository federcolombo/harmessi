"""Tests de lessons (v0.14 Change 5, R1-R6). Evidencia real: probes con FakeAdapter en tempdirs."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from tools.harmessi_improve import decision as dec
from tools.harmessi_improve import lessons as les
from tools.harmessi_improve.lessons import LessonRechazada
from tools.harmessi_improve.policy import ProbePolicy
from tools.harmessi_improve.tests._fakes import FakeAdapter
from tools.harmessi_improve.tests._helpers import CHANGE_ID, GLOSSARY_BASICO, crear_change, snapshot
from tools.harmessi_improve.tests.test_probe import SOLO_1, TODOS, Base

AHORA = datetime(2026, 10, 23, 14, 0, tzinfo=timezone.utc)
PATRON = "Las guias largas degradan el seguimiento de instrucciones"
RECO = "Preferir guias breves con pasos numerados"
CTX = ["python-notebook-debugging"]


class BaseLessons(Base):
    def setUp(self):
        super().setUp()
        crear_change(self.raiz, "h")

    def evidencia(self, repeats=2, probe_id="p1"):
        self.probe(FakeAdapter(SOLO_1, TODOS), ProbePolicy(repeats=repeats), probe_id=probe_id)
        d = dec.decidir(self.raiz, probe_id)
        return [{"probe_id": probe_id, "decision_hash": d["decision_hash"], "suite_id": "suite-fake"}]

    def crear(self, refs, **kw):
        args = dict(pattern=PATRON, recommendation=RECO, contexts=CTX, evidence_refs=refs, ahora=AHORA)
        change_id = kw.pop("change_id", CHANGE_ID)
        args.update(kw)
        return les.crear_lesson(self.raiz, change_id, **args)

    def codigo(self, refs, **kw):
        with self.assertRaises(LessonRechazada) as cm:
            self.crear(refs, **kw)
        return cm.exception.codigo

    def ruta(self, lesson_id):
        return self.raiz / ".harmessi" / "improvement" / "lessons" / f"{lesson_id}.json"


class TestCreacion(BaseLessons):
    def test_evidence_backed_con_repeats_2(self):
        l = self.crear(self.evidencia(2))
        self.assertEqual(l["status"], "evidence-backed")
        self.assertTrue(l["lesson_id"].startswith("les-"))
        self.assertEqual(les.cargar_lesson(self.raiz, l["lesson_id"]), l)
        self.assertEqual(les.listar_lessons(self.raiz), [l])

    def test_hypothesis_con_repeats_1(self):
        self.assertEqual(self.crear(self.evidencia(1))["status"], "hypothesis")

    def test_idempotente(self):
        refs = self.evidencia(2)
        a = self.crear(refs)
        b = self.crear(refs, ahora=datetime(2027, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(a, b)
        self.assertEqual(len(list(self.ruta("x").parent.glob("*.json"))), 1)

    def test_evidencia_inexistente(self):
        ref = [{"probe_id": "nada", "decision_hash": "abc", "suite_id": "suite-fake"}]
        self.assertEqual(self.codigo(ref), "EVIDENCIA_NO_VERIFICABLE")

    def test_decision_hash_distinto_o_suite_distinta(self):
        refs = self.evidencia(2)
        self.assertEqual(self.codigo([dict(refs[0], decision_hash="0" * 64)]), "EVIDENCIA_NO_VERIFICABLE")
        self.assertEqual(self.codigo([dict(refs[0], suite_id="otra")]), "EVIDENCIA_NO_VERIFICABLE")

    def test_evidencia_alterada(self):
        refs = self.evidencia(2)
        r = self.evals / "p1-base-r1" / "result.json"
        r.write_bytes(r.read_bytes() + b" ")
        self.assertEqual(self.codigo(refs), "EVIDENCIA_NO_VERIFICABLE")

    def test_campos_invalidos(self):
        refs = self.evidencia(2)
        self.assertEqual(self.codigo(refs, contexts=[]), "CAMPO_INVALIDO")
        self.assertEqual(self.codigo(refs, contexts=["Mal Tag"]), "CAMPO_INVALIDO")
        self.assertEqual(self.codigo(refs, contexts=[f"tag-{i}" for i in range(6)]), "CAMPO_INVALIDO")
        self.assertEqual(self.codigo([]), "CAMPO_INVALIDO")
        self.assertEqual(self.codigo(refs, recommendation="x" * 501), "CAMPO_INVALIDO")
        self.assertEqual(self.codigo(refs, pattern=""), "CAMPO_INVALIDO")

    def test_privacidad(self):
        refs = self.evidencia(2)
        casos = [
            "Revisar C:\\Users\\ana\\datos", "Revisar D:/datos", "Ver https://ejemplo.org/x",
            "Mirar /opt/app/config", "Mirar /home/ana/datos", "Escribir a ana@ejemplo.org",
            "Usar sk-abcdefgh12345678", "Usar ghp_abcdefgh12345678",
        ]
        for texto in casos:
            with self.subTest(texto=texto):
                self.assertEqual(self.codigo(refs, recommendation=texto), "CONTENIDO_SENSIBLE")
        self.assertEqual(self.codigo(refs, pattern="C:\\x"), "CONTENIDO_SENSIBLE")

    def test_prompt_largo_rechazado(self):
        self.assertEqual(self.codigo(self.evidencia(2), recommendation="Respondé así: " + "palabra " * 200),
                         "CAMPO_INVALIDO")

    def test_termino_del_glossary(self):
        refs = self.evidencia(2)
        (self.raiz / "GLOSSARY.md").write_text(GLOSSARY_BASICO, encoding="utf-8")
        self.assertEqual(self.codigo(refs, recommendation="Reducir el churn con guias breves"),
                         "CONOCIMIENTO_DEL_PROYECTO")
        self.assertEqual(self.codigo(refs, contexts=["churn"]), "CONOCIMIENTO_DEL_PROYECTO")

    def test_sin_change(self):
        refs = self.evidencia(2)
        self.assertEqual(self.codigo(refs, change_id="20261023-no-existe"), "SIN_CHANGE")
        crear_change(self.raiz, "h", change_id="20261023-cerrado", estado="aprobado")
        self.assertEqual(self.codigo(refs, change_id="20261023-cerrado"), "SIN_CHANGE")
        crear_change(self.raiz, "h", change_id="20261023-otro", control_change_id="20261023-distinto")
        self.assertEqual(self.codigo(refs, change_id="20261023-otro"), "SIN_CHANGE")
        self.assertFalse(self.ruta("x").parent.exists())

    def test_flujo_probe_decide_apply_no_crea_lessons(self):
        self.probe(FakeAdapter(SOLO_1, TODOS), ProbePolicy(repeats=2))
        dec.aplicar_decision(self.raiz, "p1", ahora=AHORA)
        self.assertFalse(self.ruta("x").parent.exists())


class TestAplicables(BaseLessons):
    def test_coincidencia_y_no_coincidencia(self):
        l = self.crear(self.evidencia(2))
        r = les.lessons_aplicables(self.raiz, ["python-notebook-debugging", "otro-tag"])
        self.assertEqual([x["lesson_id"] for x in r["aplicables"]], [l["lesson_id"]])
        r = les.lessons_aplicables(self.raiz, ["sql-modeling"])
        self.assertEqual(r["aplicables"], [])
        self.assertEqual([d["lesson_id"] for d in r["descartadas"]], [l["lesson_id"]])
        self.assertTrue(r["descartadas"][0]["motivo"])

    def test_deprecada_excluida(self):
        l = self.crear(self.evidencia(2))
        d = les.deprecar(self.raiz, CHANGE_ID, l["lesson_id"], "ya no aplica", ahora=AHORA)
        self.assertEqual(d["status"], "deprecated")
        self.assertEqual(les.cargar_lesson(self.raiz, l["lesson_id"])["status"], "deprecated")
        r = les.lessons_aplicables(self.raiz, CTX)
        self.assertEqual((r["aplicables"], r["descartadas"][0]["motivo"]), ([], "deprecated"))
        with self.assertRaises(LessonRechazada) as cm:
            les.deprecar(self.raiz, "20261023-no-existe", l["lesson_id"], "x")
        self.assertEqual(cm.exception.codigo, "SIN_CHANGE")

    def test_evidencia_que_dejo_de_ser_verificable(self):
        l = self.crear(self.evidencia(2))
        r_ = self.evals / "p1-cand-r1" / "result.json"
        r_.write_bytes(r_.read_bytes() + b" ")
        r = les.lessons_aplicables(self.raiz, CTX)
        self.assertEqual(r["aplicables"], [])
        self.assertEqual(r["descartadas"], [{"lesson_id": l["lesson_id"], "motivo": "evidencia_no_verificable"}])

    def test_lesson_hash_manipulado(self):
        l = self.crear(self.evidencia(2))
        ruta = self.ruta(l["lesson_id"])
        datos = json.loads(ruta.read_text("utf-8"))
        datos["recommendation"] = "Otra recomendación"
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        with self.assertRaises(LessonRechazada) as cm:
            les.cargar_lesson(self.raiz, l["lesson_id"])
        self.assertEqual(cm.exception.codigo, "LESSON_CORRUPTA")
        r = les.lessons_aplicables(self.raiz, CTX)
        self.assertEqual(r["aplicables"], [])
        self.assertEqual(r["descartadas"][0]["motivo"], "lesson_corrupta")

    def test_privacidad_se_rescanea(self):
        self.crear(self.evidencia(2))
        (self.raiz / "GLOSSARY.md").write_text("# Glosario\n\n## guias\n- estado: hypothesis\n- definicion: x\n",
                                               encoding="utf-8")
        r = les.lessons_aplicables(self.raiz, CTX)
        self.assertEqual(r["aplicables"], [])
        self.assertEqual(r["descartadas"][0]["motivo"], "privacidad_no_superada")

    def test_contextos_invalidos(self):
        with self.assertRaises(LessonRechazada):
            les.lessons_aplicables(self.raiz, [])


GLOSSARY_VARIOS = ("# Glosario\n\n## valor de cliente\n- estado: hypothesis\n- definicion: x\n\n"
                   "## cohesión interna\n- estado: hypothesis\n- definicion: y\n")


class TestNormalizacionYRutas(BaseLessons):
    def test_glossary_normalizado(self):
        refs = self.evidencia(2)
        (self.raiz / "GLOSSARY.md").write_text(GLOSSARY_VARIOS, encoding="utf-8")
        textos = ["Medir el valor-de-cliente", "Medir el valor_de_cliente", "Medir el valor  de\ncliente",
                  "Medir el VALOR DE CLIENTE", "Medir la cohesión interna"]
        for texto in textos:
            with self.subTest(texto=texto):
                self.assertEqual(self.codigo(refs, recommendation=texto), "CONOCIMIENTO_DEL_PROYECTO")
        self.assertEqual(self.codigo(refs, contexts=["valor-de-cliente"]), "CONOCIMIENTO_DEL_PROYECTO")

    def test_rutas_endurecidas(self):
        refs = self.evidencia(2)
        for texto in ["Abrir notas/informe.txt", "Abrir modelo.ipynb", "Abrir datos.csv", "Ir a ~/datos",
                      "Subir a ../otro", "Abrir a/b/c.py", "Ver config.yaml"]:
            with self.subTest(texto=texto):
                self.assertEqual(self.codigo(refs, recommendation=texto), "CONTENIDO_SENSIBLE")

    def test_unidad_solo_real(self):
        refs = self.evidencia(2)
        l = self.crear(refs, recommendation="Nota A: preferir pasos cortos")
        self.assertEqual(l["status"], "evidence-backed")

    def test_ids_de_evidencia_se_escanean(self):
        refs = self.evidencia(2)
        (self.raiz / "GLOSSARY.md").write_text(GLOSSARY_BASICO + "\n## valor de cliente\n- estado: hypothesis\n- definicion: x\n",
                                               encoding="utf-8")
        self.assertEqual(self.codigo([dict(refs[0], probe_id="churn")]), "CONOCIMIENTO_DEL_PROYECTO")
        self.assertEqual(self.codigo([dict(refs[0], suite_id="valor-de-cliente")]), "CONOCIMIENTO_DEL_PROYECTO")

    def test_coherencia_status_claves(self):
        l = self.crear(self.evidencia(2))
        ruta = self.ruta(l["lesson_id"])
        datos = json.loads(ruta.read_text("utf-8"))
        datos["status"] = "deprecated"
        datos["lesson_hash"] = les._hash_lesson(datos)
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        with self.assertRaises(LessonRechazada) as cm:
            les.cargar_lesson(self.raiz, l["lesson_id"])
        self.assertEqual(cm.exception.codigo, "LESSON_CORRUPTA")

    def test_created_utc_invalido(self):
        l = self.crear(self.evidencia(2))
        ruta = self.ruta(l["lesson_id"])
        datos = json.loads(ruta.read_text("utf-8"))
        datos["created_utc"] = "ayer"
        datos["lesson_hash"] = les._hash_lesson(datos)
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        with self.assertRaises(LessonRechazada):
            les.cargar_lesson(self.raiz, l["lesson_id"])
