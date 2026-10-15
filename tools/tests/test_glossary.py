"""Tests de `tools.dsguard.glossary` (Change 20261014-domain-modeling, R1-R5, R10).
Usan tempdirs y un resolver falso; no requieren git."""
from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import glossary as g  # noqa: E402

CH = "20261014-x"
ART = "spec.md"
TERM = "Cliente activo"
DEF = "Cliente con al menos una compra en 90 dias."


def _hash_ok() -> str:
    return g.definition_hash(TERM, DEF)


def _approved(hash_: str | None = None, ref_hash: str | None = None, extra: str = "") -> str:
    h = hash_ or _hash_ok()
    return (
        f"## {TERM}\n- estado: approved\n- definicion: {DEF}\n"
        f"- approval_ref: {CH}/{ART}@{ref_hash or 'a' * 64}\n- definition_hash: {h}\n{extra}"
    )


def _resolver(state="verified", tier="T1"):
    return lambda ref: SimpleNamespace(state=state, trust_tier=tier)


def _codigos(hallazgos):
    return [h.codigo for h in hallazgos]


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def escribir(self, texto: str, nombre: str = "GLOSSARY.md"):
        (self.root / nombre).write_text(texto, encoding="utf-8")

    def artefacto(self, contenido: str, sub: str = "changes"):
        d = self.root / "openspec" / sub / CH
        d.mkdir(parents=True, exist_ok=True)
        (d / ART).write_text(contenido, encoding="utf-8")

    def evaluar(self, texto, resolver=None):
        self.escribir(texto)
        return g.evaluar_glossary(self.root, resolver)


class TestHypothesisYParser(_Base):
    def test_hypothesis_valida(self):
        h, p = self.evaluar("# Glosario\nprosa\n\n## Churn\n- estado: hypothesis\n- definicion: Baja de cliente.\n")
        self.assertEqual((h, p), ([], []))

    def test_archivo_ausente(self):
        self.assertEqual(g.evaluar_glossary(self.root), ([], []))

    def test_archivo_no_utf8(self):
        (self.root / "GLOSSARY.md").write_bytes(b"\xff\xfe\x00\xd8")
        h, p = g.evaluar_glossary(self.root)
        self.assertEqual(_codigos(h), [g.COD_MALFORMADO])

    def test_malformado_linea_suelta(self):
        h, _ = self.evaluar("## A\n- estado: hypothesis\nlinea suelta\n- definicion: x\n")
        self.assertIn(g.COD_MALFORMADO, _codigos(h))

    def test_campo_repetido_y_encabezado_vacio(self):
        h, _ = self.evaluar("##\n## A\n- estado: hypothesis\n- estado: hypothesis\n- definicion: x\n")
        self.assertEqual(_codigos(h).count(g.COD_MALFORMADO), 2)

    def test_campo_desconocido(self):
        h, _ = self.evaluar("## A\n- estado: hypothesis\n- definicion: x\n- owner: fede\n")
        self.assertEqual(_codigos(h), [g.COD_CAMPO_DESCONOCIDO])

    def test_duplicado_casefold(self):
        h, _ = self.evaluar("## Churn\n- estado: hypothesis\n- definicion: x\n## CHURN\n- estado: hypothesis\n- definicion: y\n")
        self.assertEqual(_codigos(h), [g.COD_TERMINO_DUPLICADO])

    def test_definicion_multilinea(self):
        ents, hall = g.parsear_glossary("## A\n- estado: hypothesis\n- definicion: uno\n  dos\n  tres\n")
        self.assertEqual(hall, [])
        self.assertEqual(ents[0].definicion, "uno dos tres")
        self.assertEqual(ents[0].ambiguedad, "none")
        self.assertEqual(ents[0].linea, 1)

    def test_comentario_html_ignorado(self):
        txt = "<!--\n## Ejemplo\n- estado: raro\n-->\n## Real\n- estado: hypothesis\n- definicion: x\n<!-- ## Otro -->\n"
        ents, hall = g.parsear_glossary(txt)
        self.assertEqual([e.termino for e in ents], ["Real"])
        self.assertEqual(hall, [])

    def test_bloque_cercado_en_preambulo_ignorado(self):
        txt = "```\n## Falso\nlinea suelta\n```\n## Real\n- estado: hypothesis\n- definicion: x\n"
        ents, hall = g.parsear_glossary(txt)
        self.assertEqual([e.termino for e in ents], ["Real"])
        self.assertEqual(hall, [])

    def test_bloque_cercado_dentro_de_entrada_es_malformado(self):
        for marca in ("```", "~~~"):
            txt = f"## Real\n- estado: hypothesis\n- definicion: x\n{marca}\n## Falso\nlinea suelta\n{marca}\n"
            ents, hall = g.parsear_glossary(txt)
            self.assertEqual([e.termino for e in ents], ["Real"])
            self.assertEqual(_codigos(hall), [g.COD_MALFORMADO])
            self.assertIn("dentro de entrada", hall[0].mensaje)

    def test_comentario_html_dentro_de_entrada_permitido(self):
        ents, hall = g.parsear_glossary("## A\n- estado: hypothesis\n<!-- nota -->\n- definicion: x\n")
        self.assertEqual((len(ents), hall), (1, []))

    def test_estado_desconocido(self):
        for est in ("pending", "Approved"):
            h, _ = self.evaluar(f"## A\n- estado: {est}\n- definicion: x\n")
            self.assertEqual(_codigos(h), [g.COD_ESTADO_INVALIDO], est)

    def test_entrada_sin_definicion(self):
        h, _ = self.evaluar("## A\n- estado: hypothesis\n")
        self.assertEqual(_codigos(h), [g.COD_DEFINICION_AUSENTE])

    def test_ambiguedad_invalida(self):
        h, _ = self.evaluar("## A\n- estado: hypothesis\n- definicion: x\n- ambiguedad: mucha\n")
        self.assertEqual(_codigos(h), [g.COD_AMBIGUEDAD_INVALIDA])

    def test_ambiguedad_material_en_hypothesis_es_pendiente(self):
        h, p = self.evaluar("## A\n- estado: hypothesis\n- definicion: x\n- ambiguedad: material\n")
        self.assertEqual((h, p), ([], ["A"]))

    def test_hypothesis_con_approval_ref(self):
        h, _ = self.evaluar(f"## A\n- estado: hypothesis\n- definicion: x\n- approval_ref: {CH}/{ART}@{'a' * 64}\n")
        self.assertEqual(_codigos(h), [g.COD_CAMPO_INESPERADO])

    def test_ubicacion(self):
        h, _ = self.evaluar("## A\n- estado: zzz\n- definicion: x\n")
        self.assertEqual(h[0].ubicacion, "GLOSSARY.md#A")


class TestApproved(_Base):
    def test_approved_valida(self):
        self.artefacto(f"aprobado: {_hash_ok()}\n")
        h, p = self.evaluar(_approved(), _resolver())
        self.assertEqual((h, p), ([], []))

    def test_approved_en_archive(self):
        self.artefacto(f"hash {_hash_ok()}", sub="archive")
        h, _ = self.evaluar(_approved(), _resolver())
        self.assertEqual(h, [])

    def test_t0_sin_t1(self):
        self.artefacto(_hash_ok())
        h, _ = self.evaluar(_approved(), _resolver(tier="T0"))
        self.assertEqual(_codigos(h), [g.COD_APROBACION_SIN_T1])

    def test_state_no_verified(self):
        self.artefacto(_hash_ok())
        for st in ("stale", "missing"):
            h, _ = self.evaluar(_approved(), _resolver(state=st))
            self.assertEqual(_codigos(h), [g.COD_APROBACION_INVALIDA], st)

    def test_sin_resolver_no_promueve(self):
        self.artefacto(_hash_ok())
        h, _ = self.evaluar(_approved())
        self.assertEqual(_codigos(h), [g.COD_APROBACION_INVALIDA])

    def test_resolver_que_lanza(self):
        def malo(ref):
            raise RuntimeError("x")
        h, _ = self.evaluar(_approved(), malo)
        self.assertEqual(_codigos(h), [g.COD_APROBACION_INVALIDA])

    def test_hash_obsoleto(self):
        self.artefacto(_hash_ok())
        h, _ = self.evaluar(_approved().replace(DEF, DEF + " Cambiada."), _resolver())
        self.assertEqual(_codigos(h), [g.COD_APROBACION_OBSOLETA])

    def test_artefacto_sin_hash(self):
        self.artefacto("nada relevante")
        h, _ = self.evaluar(_approved(), _resolver())
        self.assertEqual(_codigos(h), [g.COD_APROBACION_NO_VINCULA])

    def test_artefacto_inexistente(self):
        h, _ = self.evaluar(_approved(), _resolver())
        self.assertEqual(_codigos(h), [g.COD_APROBACION_NO_VINCULA])

    def test_artefacto_con_dotdot(self):
        (self.root / "secreto.md").write_text(_hash_ok(), encoding="utf-8")
        txt = _approved().replace(f"{CH}/{ART}@", f"{CH}/../../../secreto.md@")
        h, _ = self.evaluar(txt, _resolver())
        self.assertEqual(_codigos(h), [g.COD_APROBACION_NO_VINCULA])

    def test_segmento_punto_y_change_id_punto(self):
        self.artefacto(_hash_ok())
        for ref in (f"{CH}/./{ART}@", f"{CH}/sub/./{ART}@", f"./{ART}@", f"./{CH}/{ART}@"):
            txt = _approved().replace(f"{CH}/{ART}@", ref)
            h, _ = self.evaluar(txt, _resolver())
            self.assertEqual(_codigos(h), [g.COD_APROBACION_NO_VINCULA], ref)
        txt = _approved().replace(f"{CH}/{ART}@", f"./{ART}@")  # change_id vacio => ref invalido
        h, _ = self.evaluar(txt, _resolver())
        self.assertTrue(h)

    def test_artefacto_absoluto(self):
        txt = _approved().replace(f"{CH}/{ART}@", f"{CH}//etc/x@")
        h, _ = self.evaluar(txt, _resolver())
        self.assertEqual(_codigos(h), [g.COD_APROBACION_NO_VINCULA])

    def test_approved_sin_aprobacion(self):
        h, _ = self.evaluar(f"## A\n- estado: approved\n- definicion: x\n", _resolver())
        self.assertEqual(_codigos(h), [g.COD_APROBACION_AUSENTE])

    def test_approval_ref_invalido(self):
        txt = _approved().replace(f"{CH}/{ART}@{'a' * 64}", "basura")
        h, _ = self.evaluar(txt, _resolver())
        self.assertEqual(_codigos(h), [g.COD_APROBACION_INVALIDA])

    def test_ambiguedad_material_en_approved(self):
        self.artefacto(_hash_ok())
        h, p = self.evaluar(_approved(extra="- ambiguedad: material\n"), _resolver())
        self.assertEqual(_codigos(h), [g.COD_AMBIGUEDAD_EN_APPROVED])
        self.assertEqual(p, [])


class TestRevisorCiclo1(_Base):
    def test_fence_sin_cerrar_oculta_entrada(self):
        txt = "## A\n- estado: hypothesis\n- definicion: x\n```\n" + _approved()
        ents, hall = g.parsear_glossary(txt)
        self.assertEqual([e.termino for e in ents], ["A"])
        self.assertEqual(_codigos(hall), [g.COD_MALFORMADO, g.COD_MALFORMADO])
        self.assertTrue(any("sin cerrar" in h.mensaje for h in hall))

    def test_fence_tilde(self):
        txt = "~~~\n## Falso\nsuelta\n~~~\n## A\n- estado: hypothesis\n- definicion: x\n"
        ents, hall = g.parsear_glossary(txt)
        self.assertEqual(([e.termino for e in ents], hall), (["A"], []))
        _, hall2 = g.parsear_glossary("~~~\n## A\n")
        self.assertEqual(_codigos(hall2), [g.COD_MALFORMADO])

    def test_comentario_dentro_de_fence_no_consume(self):
        txt = "```\n<!--\n```\n## Real\n- estado: hypothesis\n- definicion: x\n-->\n"
        ents, hall = g.parsear_glossary(txt)
        self.assertEqual([e.termino for e in ents], ["Real"])
        self.assertEqual(_codigos(hall), [g.COD_MALFORMADO])  # el '-->' suelto es linea no-bullet

    def test_encabezado_a_mitad_de_entrada(self):
        for enc in ("### Sub", "#foo", "# Titulo"):
            _, hall = g.parsear_glossary(f"## A\n- estado: hypothesis\n{enc}\n- definicion: x\n")
            self.assertEqual(_codigos(hall), [g.COD_MALFORMADO], enc)
        _, hall = g.parsear_glossary("# GLOSSARY\n### nota\n## A\n- estado: hypothesis\n- definicion: x\n")
        self.assertEqual(hall, [])

    def test_clave_termino_duplicados(self):
        self.assertEqual(g.clave_termino("  Cliente   ACTIVO "), g.clave_termino("cliente activo"))
        self.assertEqual(g.clave_termino("caf\u00e9"), g.clave_termino("cafe\u0301"))
        h, _ = self.evaluar("## cliente  activo\n- estado: hypothesis\n- definicion: x\n## cliente activo\n- estado: hypothesis\n- definicion: y\n")
        self.assertEqual(_codigos(h), [g.COD_TERMINO_DUPLICADO])
        h, _ = self.evaluar("## caf\u00e9\n- estado: hypothesis\n- definicion: x\n## cafe\u0301\n- estado: hypothesis\n- definicion: y\n")
        self.assertEqual(_codigos(h), [g.COD_TERMINO_DUPLICADO])
        self.assertEqual(g.definition_hash("caf\u00e9", "d"), g.definition_hash("cafe\u0301", "d"))

    def test_hash_en_comentario_html_no_vincula(self):
        self.artefacto(f"texto\n<!-- {_hash_ok()} -->\n")
        h, _ = self.evaluar(_approved(), _resolver())
        self.assertEqual(_codigos(h), [g.COD_APROBACION_NO_VINCULA])

    def test_hash_dentro_de_cadena_hex_mas_larga_no_vincula(self):
        for texto in (_hash_ok() + "ab", "f" + _hash_ok()):
            self.artefacto(texto)
            h, _ = self.evaluar(_approved(), _resolver())
            self.assertEqual(_codigos(h), [g.COD_APROBACION_NO_VINCULA])
        self.artefacto(f"hash={_hash_ok().upper()}.")
        h, _ = self.evaluar(_approved(), _resolver())
        self.assertEqual(h, [])

    def test_backslash_y_unidad(self):
        self.artefacto(_hash_ok())
        for art in ("sub\\spec.md", "C:spec.md", "sub/C:/spec.md"):
            txt = _approved().replace(f"{CH}/{ART}@", f"{CH}/{art}@")
            h, _ = self.evaluar(txt, _resolver())
            self.assertEqual(_codigos(h), [g.COD_APROBACION_NO_VINCULA], art)

    def test_symlink_fuera_del_change(self):
        externo = self.root / "externo.md"
        externo.write_text(_hash_ok(), encoding="utf-8")
        d = self.root / "openspec" / "changes" / CH
        d.mkdir(parents=True)
        try:
            (d / ART).symlink_to(externo)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks no disponibles")
        h, _ = self.evaluar(_approved(), _resolver())
        self.assertEqual(_codigos(h), [g.COD_APROBACION_NO_VINCULA])


class TestHashYRef(unittest.TestCase):
    def test_hash_estable(self):
        base = g.definition_hash("Cliente Activo", "a b c")
        self.assertEqual(base, g.definition_hash("  cliente   ACTIVO ", "a\r\nb\n  c  "))
        self.assertEqual(len(base), 64)
        self.assertNotEqual(base, g.definition_hash("cliente activo", "a b d"))

    def test_parsear_approval_ref(self):
        h = "b" * 64
        self.assertEqual(g.parsear_approval_ref(f"c1/a/b.md@{h}"),
                         {"change_id": "c1", "artefacto": "a/b.md", "hash": h})
        self.assertEqual(g.parsear_approval_ref(f"c1/x@y@{h}")["artefacto"], "x@y")
        for malo in ("", "c1", f"c1@{h}", f"/x@{h}", f"c1/@{h}", "c1/x@abc", f"c1/x@{h.upper()}", f"c1/x@{'b' * 63}"):
            self.assertIsNone(g.parsear_approval_ref(malo), malo)


class TestBoundaries(unittest.TestCase):
    def test_imports_prohibidos(self):
        fuente = (REPO_ORIGEN / "tools" / "dsguard" / "glossary.py").read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        modulos = []
        for n in ast.walk(arbol):
            if isinstance(n, ast.Import):
                modulos += [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                modulos.append(("." * n.level) + (n.module or ""))
        for m in modulos:
            for prohibido in ("cards", "decision", "datacontracts", "sdd"):
                self.assertNotIn(prohibido, m)
        for nombre in ("claude", "codex", "gemini", "sendmessage"):
            self.assertNotIn(nombre, fuente.lower())


if __name__ == "__main__":
    unittest.main()
