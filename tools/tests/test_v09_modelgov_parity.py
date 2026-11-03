"""Paridad de las reglas duplicadas de `govpolicy.py` / `modelgov.py` con sus
fuentes de verdad (Change `20261005-model-risk-responsible-ai`, R1, R8, R13, R16,
R19, R65-R68).

`govpolicy` y `modelgov` no pueden importar `dsguard.maturity`, `modelcard`,
`modelquality`, `qualityevidence` ni `datasources`: duplican vocabularios, la regla
de decodificación de `card_id` y el JSON canónico. Este test fija que cada
duplicación sigue siendo exacta. Solo los tests importan ambos lados.
"""
from __future__ import annotations

import ast
import hashlib
import itertools
import re
import unittest
from pathlib import Path

from tools.cards import core, govpolicy, modelcard, modelgov, resolvers
from tools.datasources import core as ds_core
from tools.dsguard import maturity

REPO_ORIGEN = Path(__file__).resolve().parents[2]
DIR_CARDS = REPO_ORIGEN / "tools" / "cards"
MODULOS_GOV = ("govpolicy.py", "modelgov.py")


def _resultado_decodificar(funcion, card_id):
    """`("ok", (model_id, model_version))` o `("error",)`; cualquier otra
    excepción (cruda) se propaga y hace fallar el test."""
    try:
        return ("ok", funcion(card_id))
    except core.CardError:
        return ("error",)


class TestParidadNivelesYVocabularios(unittest.TestCase):
    def test_levels_igual_a_risk_levels_de_maturity(self):
        self.assertEqual(govpolicy.LEVELS, maturity.RISK_LEVELS)
        self.assertEqual(govpolicy.LEVELS, ("low", "medium", "high"))

    def test_dimensiones_cerradas(self):
        self.assertEqual(
            govpolicy.DIMENSIONS,
            ("fairness", "explainability", "privacy", "security", "accountability", "human_oversight"),
        )

    def test_external_evidence_kinds_subconjunto_de_observed_y_sin_report_artifact(self):
        self.assertTrue(set(govpolicy.EXTERNAL_EVIDENCE_KINDS) <= set(core.OBSERVED_KINDS))
        self.assertNotIn("report_artifact", govpolicy.EXTERNAL_EVIDENCE_KINDS)
        self.assertEqual(len(set(govpolicy.EXTERNAL_EVIDENCE_KINDS)), len(govpolicy.EXTERNAL_EVIDENCE_KINDS))

    def test_kinds_estructurales_son_observed_kinds(self):
        self.assertTrue(set(govpolicy._STRUCTURAL_KINDS) <= set(core.OBSERVED_KINDS))
        self.assertEqual(modelgov._KIND_MODEL_CARD, "model_card")
        self.assertEqual(modelgov._KIND_GOVERNANCE_POLICY, "governance_policy")
        self.assertEqual(set(govpolicy._STRUCTURAL_KINDS), {modelgov._KIND_MODEL_CARD, modelgov._KIND_GOVERNANCE_POLICY})

    def test_kinds_por_defecto_de_modelgov_coinciden_con_los_atomos_de_un_spec_sin_accepted_kinds(self):
        spec = govpolicy.LevelSpec(severity="required", accepts=("observed",))
        self.assertEqual(frozenset(modelgov._KINDS_POR_DEFECTO), govpolicy.atoms(spec))

    def test_ids_estructurales_coinciden_entre_modulos(self):
        self.assertEqual(tuple(modelgov._ESTRUCTURALES), govpolicy.STRUCTURAL_REQUIREMENT_IDS)
        self.assertEqual(
            (modelgov.REQ_MODEL_CARD_PIN, modelgov.REQ_POLICY_HARDENING_PIN), govpolicy.STRUCTURAL_REQUIREMENT_IDS
        )

    def test_risk_declaration_es_un_requisito_de_la_base(self):
        self.assertIn(modelgov.REQ_RISK_DECLARATION, {r.requirement_id for r in govpolicy.BASE_POLICY.requirements})
        self.assertEqual(modelgov._IDS_BASE, frozenset(r.requirement_id for r in govpolicy.BASE_POLICY.requirements))

    def test_niveles_de_modelgov_son_los_de_govpolicy(self):
        # `modelgov` no tiene su propia copia: usa `govpolicy.LEVELS`.
        self.assertEqual(modelgov._nivel_idx("low"), maturity.RISK_LEVELS.index("low"))
        self.assertEqual(modelgov._nivel_idx("high"), maturity.RISK_LEVELS.index("high"))


class TestParidadDecodificacionDeCardId(unittest.TestCase):
    VALIDOS = (
        "clasificador__1_0",
        "a__1",
        "1__2",
        "m-x_y__1_2",
        "m-x_y__1-rc1",
        "modelo__2_10_3",
        "a" * 61 + "__1",  # exactamente 64 caracteres
    )
    INVALIDOS = (
        "",
        "a",
        "a__",
        "__1",
        "__",
        "a__b__c",
        "A__1",
        "a__1__",
        "a___1",
        "a____1",
        "a__1_",
        "a__ _1",
        "a__.1",
        "a__1.0",  # '.' sin codificar: no es la forma canónica
        "_a__1",
        "a_-b__1",
        "a__1__2",
        "a" * 62 + "__1",  # 65 caracteres
        "ñ__1",
        "a__ñ",
        None,
        5,
        b"a__1",
        ["a__1"],
        {"a": 1},
        1.5,
        True,
    )

    def test_tabla_de_casos_validos_mismos_resultados(self):
        for card_id in self.VALIDOS:
            with self.subTest(card_id=card_id):
                esperado = modelcard.decode_model_card_id(card_id)
                self.assertEqual(modelgov._decodificar_card_id(card_id), esperado)
                self.assertEqual(modelcard.model_card_id(*esperado), card_id)

    def test_tabla_de_casos_invalidos_mismos_errores(self):
        for card_id in self.INVALIDOS:
            with self.subTest(card_id=card_id):
                self.assertEqual(
                    _resultado_decodificar(modelgov._decodificar_card_id, card_id),
                    _resultado_decodificar(modelcard.decode_model_card_id, card_id),
                )
                self.assertEqual(_resultado_decodificar(modelgov._decodificar_card_id, card_id), ("error",))

    def test_codigo_de_error_de_modelgov(self):
        with self.assertRaises(core.CardError) as ctx:
            modelgov._decodificar_card_id("a__b__c")
        self.assertEqual(ctx.exception.code, modelgov.CODE_IDENTITY_MISMATCH)

    def test_generacion_exhaustiva_de_combinaciones_cortas(self):
        tokens = ("a", "1", "_", "__", "-", ".")
        total = validos = 0
        for largo in range(1, 5):
            for combo in itertools.product(tokens, repeat=largo):
                card_id = "".join(combo)
                total += 1
                esperado = _resultado_decodificar(modelcard.decode_model_card_id, card_id)
                actual = _resultado_decodificar(modelgov._decodificar_card_id, card_id)
                if esperado != actual:
                    self.fail(f"divergencia para {card_id!r}: modelcard={esperado} modelgov={actual}")
                if esperado[0] == "ok":
                    validos += 1
        self.assertGreater(total, 1000)
        self.assertGreater(validos, 5, "la generación exhaustiva no produjo casos válidos: el test sería vacuo")

    def test_generacion_exhaustiva_con_alfabeto_de_dos_letras_y_separador(self):
        tokens = ("a", "b", "1", "_", "__", "-")
        validos = 0
        for largo in range(1, 5):
            for combo in itertools.product(tokens, repeat=largo):
                card_id = "".join(combo)
                esperado = _resultado_decodificar(modelcard.decode_model_card_id, card_id)
                self.assertEqual(_resultado_decodificar(modelgov._decodificar_card_id, card_id), esperado, card_id)
                validos += esperado[0] == "ok"
        self.assertGreater(validos, 5)

    def test_constantes_duplicadas_iguales_a_modelcard(self):
        self.assertEqual(modelgov._MODEL_ID_PATTERN, modelcard.MODEL_ID_PATTERN)
        self.assertEqual(modelgov._MODEL_VERSION_PATTERN, modelcard.MODEL_VERSION_PATTERN)
        self.assertEqual(modelgov._CARD_ID_SEPARATOR, modelcard.CARD_ID_SEPARATOR)
        self.assertEqual(modelgov._MAX_ID, modelcard._MAX_ID)
        self.assertEqual(modelgov._DIR_MODEL_CARDS, "/".join(modelcard.CARD_DIR_PARTES))

    def test_problemas_de_identidad_equivalentes(self):
        pares = (
            ("clasificador", "1.0"),
            ("a", "1"),
            ("A", "1"),
            ("a", "1_0"),
            ("a__b", "1"),
            ("a", ""),
            ("", "1"),
            ("a" * 62, "1"),
            ("a" * 61, "1"),
            (None, "1"),
            ("a", None),
            (5, 6),
        )
        for model_id, version in pares:
            with self.subTest(model_id=model_id, version=version):
                self.assertEqual(
                    bool(modelgov._problemas_identidad(model_id, version)),
                    bool(modelcard._problemas_identidad(model_id, version)),
                )

    def test_ref_id_de_model_card_usa_el_mismo_formato_que_data_card(self):
        esperado = "(?P<cid>" + core.CARD_ID_PATTERN + ")__(?P<h>[0-9a-f]{12})"
        self.assertEqual(modelgov._RE_REF_MODEL_CARD.pattern, esperado)
        self.assertEqual(modelgov._RE_REF_MODEL_CARD.pattern, modelcard._RE_DATA_CARD_REF.pattern)


class TestParidadPatronesConCore(unittest.TestCase):
    def test_patron_de_ids_y_sha256_iguales_a_core(self):
        self.assertEqual(modelgov._RE_ID.pattern, core.CARD_ID_PATTERN)
        self.assertEqual(modelgov._RE_SHA256.pattern, core._RE_SHA256.pattern)

    def test_patron_de_declaracion_de_riesgo_cubre_exactamente_los_niveles(self):
        for nivel in govpolicy.LEVELS:
            with self.subTest(nivel=nivel):
                self.assertIsNotNone(modelgov._RE_RIESGO.fullmatch(f"risk_level={nivel}"))
        for malo in ("risk_level=critical", "risk_level=", "risk_level=Low", "risk_level=low ", " risk_level=low"):
            with self.subTest(malo=malo):
                self.assertIsNone(modelgov._RE_RIESGO.fullmatch(malo))

    def test_ids_de_core_coinciden_en_aceptacion_y_rechazo(self):
        casos = ("a", "a1", "a_b", "a-b", "0a", "_a", "-a", "A", "a" * 64, "a" * 65, "", "a b", "ñ")
        re_core = re.compile(core.CARD_ID_PATTERN)
        for caso in casos:
            with self.subTest(caso=caso):
                self.assertEqual(
                    modelgov._RE_ID.fullmatch(caso) is not None, re_core.fullmatch(caso) is not None
                )

    def test_sha256_hex_acepta_y_rechaza_como_core(self):
        for caso in ("a" * 64, "0" * 64, "A" * 64, "a" * 63, "a" * 65, "g" * 64, ""):
            with self.subTest(caso=caso):
                try:
                    core._exigir_sha256(caso, "x")
                    esperado = True
                except core.CardError:
                    esperado = False
                self.assertEqual(modelgov._RE_SHA256.fullmatch(caso) is not None, esperado)

    def test_ids_reservados_de_core_se_rechazan_como_requirement_id(self):
        for reservado in core.RESERVED_CARD_IDS:
            with self.subTest(reservado=reservado):
                with self.assertRaises(govpolicy.GovPolicyError):
                    govpolicy.PolicyRequirement(
                        reservado, "privacy", {"low": govpolicy.LevelSpec("required", ("attestation",))}
                    )


class TestParidadCanonicaConV08(unittest.TestCase):
    def _documentos(self):
        efectiva = govpolicy.merge(govpolicy.BASE_POLICY)
        hardening = govpolicy.HardeningDocument(policy_id="harmessi-base", base_version=1, risk_floor="medium")
        return (
            ("base", govpolicy.BASE_POLICY),
            ("hardening", hardening),
            ("efectiva", efectiva),
        )

    def test_content_sha256_de_la_policy_igual_a_sha256_de_canonical_json_de_datasources(self):
        esperado = hashlib.sha256(ds_core.canonical_json(govpolicy.BASE_POLICY.to_dict()).encode("utf-8")).hexdigest()
        self.assertEqual(govpolicy.BASE_POLICY.content_sha256(), esperado)
        self.assertEqual(govpolicy.BASE_POLICY_SHA256, esperado)

    def test_paridad_para_hardening_y_policy_efectiva(self):
        for nombre, documento in self._documentos():
            with self.subTest(documento=nombre):
                canonico = ds_core.canonical_json(documento.to_dict()).encode("utf-8")
                esperado = hashlib.sha256(canonico).hexdigest()
                actual = documento.effective_sha256() if nombre == "efectiva" else documento.content_sha256()
                self.assertEqual(actual, esperado)

    def test_canonical_json_de_cards_identico_al_de_datasources(self):
        for caso in (
            {"b": 1, "a": [1, 2.5, None, True], "ñ": "á"},
            [],
            {"k": {"z": 1, "a": 2}},
            govpolicy.BASE_POLICY.to_dict(),
        ):
            with self.subTest(caso=str(caso)[:40]):
                self.assertEqual(core.canonical_json(caso), ds_core.canonical_json(caso))

    def test_hash_independiente_del_orden_de_requisitos_de_entrada(self):
        reqs = tuple(govpolicy.BASE_POLICY.requirements)
        invertida = govpolicy.GovernancePolicy("harmessi-base", 1, tuple(reversed(reqs)))
        self.assertEqual(invertida.content_sha256(), govpolicy.BASE_POLICY.content_sha256())

    def test_hash_cambia_con_la_version_y_con_el_contenido(self):
        reqs = tuple(govpolicy.BASE_POLICY.requirements)
        self.assertNotEqual(
            govpolicy.GovernancePolicy("harmessi-base", 2, reqs).content_sha256(), govpolicy.BASE_POLICY_SHA256
        )
        self.assertNotEqual(
            govpolicy.GovernancePolicy("harmessi-base", 1, reqs[:-1]).content_sha256(), govpolicy.BASE_POLICY_SHA256
        )

    def test_govpolicy_hashea_via_core_canonical_json(self):
        arbol = ast.parse((DIR_CARDS / "govpolicy.py").read_text(encoding="utf-8"))
        atributos = {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
        self.assertIn("canonical_json", atributos)
        # No reimplementa JSON canónico con `json` propio.
        raices = set()
        for n in ast.walk(arbol):
            if isinstance(n, ast.Import):
                raices.update(a.name.split(".")[0] for a in n.names)
            elif isinstance(n, ast.ImportFrom) and n.level == 0:
                raices.add((n.module or "").split(".")[0])
        self.assertNotIn("json", raices)


class TestHashDocumentoResolvers(unittest.TestCase):
    def test_hash_document_determinista_ante_orden_de_claves(self):
        a = {"requirement": "x", "n": 1, "anidado": {"b": 2, "a": [1, 2]}}
        b = {"anidado": {"a": [1, 2], "b": 2}, "n": 1, "requirement": "x"}
        self.assertEqual(resolvers.hash_document(a), resolvers.hash_document(b))
        self.assertEqual(resolvers.hash_document(a), resolvers.hash_document(a))
        self.assertRegex(resolvers.hash_document(a), r"[0-9a-f]{64}")

    def test_hash_document_distinto_ante_cambios(self):
        base = {"k": "v", "n": [1, 2]}
        h = resolvers.hash_document(base)
        for cambio in (
            {"k": "w", "n": [1, 2]},
            {"k": "v", "n": [2, 1]},
            {"k": "v", "n": [1, 2], "extra": None},
            {"k": "v"},
            {"k": "v", "n": [1, 2.5]},
            [],
        ):
            with self.subTest(cambio=cambio):
                self.assertNotEqual(resolvers.hash_document(cambio), h)

    def test_hash_document_igual_al_canonico_de_datasources(self):
        for caso in ({"a": 1}, [{"b": 1, "a": 2}], {"nombre": "ñandú"}):
            with self.subTest(caso=caso):
                self.assertEqual(resolvers.hash_document(caso), ds_core.content_sha256(caso))

    def test_hash_document_de_policy_y_hardening_coincide_con_su_content_sha256(self):
        """El hash que `evidence_document`/`governance_policy` pinean a nivel de
        dict es el mismo que el `content_sha256()` del tipo (misma canonicalización)."""
        hardening = govpolicy.HardeningDocument(policy_id="harmessi-base", base_version=1, risk_floor="high")
        self.assertEqual(resolvers.hash_document(hardening.to_dict()), hardening.content_sha256())
        self.assertEqual(
            resolvers.hash_document(govpolicy.BASE_POLICY.to_dict()), govpolicy.BASE_POLICY.content_sha256()
        )


class TestVocabularioDeDimensionesSinModelQuality(unittest.TestCase):
    PROHIBIDOS = ("modelquality", "qualityevidence")

    def test_ni_import_ni_referencia_en_ast(self):
        for nombre in MODULOS_GOV:
            arbol = ast.parse((DIR_CARDS / nombre).read_text(encoding="utf-8"))
            for nodo in ast.walk(arbol):
                with self.subTest(archivo=nombre, nodo=type(nodo).__name__, linea=getattr(nodo, "lineno", 0)):
                    if isinstance(nodo, ast.ImportFrom):
                        segmentos = set((nodo.module or "").split(".")) | {a.name for a in nodo.names}
                        self.assertFalse(segmentos & set(self.PROHIBIDOS))
                    elif isinstance(nodo, ast.Import):
                        self.assertFalse(any(p in a.name for a in nodo.names for p in self.PROHIBIDOS))
                    elif isinstance(nodo, ast.Name):
                        self.assertNotIn(nodo.id, self.PROHIBIDOS)
                    elif isinstance(nodo, ast.Attribute):
                        self.assertNotIn(nodo.attr, self.PROHIBIDOS)

    def test_model_task_roles_y_vocabulario_de_calidad_no_se_referencian(self):
        for nombre in MODULOS_GOV:
            arbol = ast.parse((DIR_CARDS / nombre).read_text(encoding="utf-8"))
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.Name):
                    self.assertNotIn(nodo.id, ("MODEL_TASK_ROLES", "SUBJECT_KINDS"), nombre)
                elif isinstance(nodo, ast.Attribute):
                    self.assertNotIn(nodo.attr, ("MODEL_TASK_ROLES", "SUBJECT_KINDS"), nombre)

    def test_dimensiones_de_governance_no_son_las_de_calidad_de_modelo(self):
        # Las dimensiones de governance son un vocabulario propio y cerrado.
        for dim in govpolicy.DIMENSIONS:
            self.assertRegex(dim, r"[a-z_]+")
        self.assertNotIn("accuracy", govpolicy.DIMENSIONS)


if __name__ == "__main__":
    unittest.main()
