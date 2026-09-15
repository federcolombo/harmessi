"""Tests livianos de contenido (Change 9 v0.3:
`20260915-lead-methodology-awareness`): verifican presencia/ausencia de
cadenas concretas sobre los `.tmpl` fuente de la skill del Lead, sin parser
de Markdown (`open().read()` + `assertIn`/`assertNotIn`), mismo nivel de
sofisticación que `test_manifest.py`/`test_manifest_dsguard_parity.py`.

No re-audita todo el contenido normativo (`spec.md` R1 ya lo detalla) --
verifica los puntos concretos y verificables por texto plano listados en
`spec.md` § Criterios de aceptación y `tasks.md`.
"""
from __future__ import annotations

import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
TEMPLATES = REPO_ORIGEN / "tools" / "ds_init" / "profiles" / "python_jupyter_data" / "templates"
SKILL_DIR = REPO_ORIGEN / ".claude" / "skills" / "lead-data-scientist"

METHODOLOGY_TMPL = TEMPLATES / "methodology.md.tmpl"
METHODOLOGY_RENDERIZADO = SKILL_DIR / "methodology.md"

SKILL_TMPL = TEMPLATES / "SKILL_lead_data_scientist.md.tmpl"
SKILL_RENDERIZADO = SKILL_DIR / "SKILL.md"

KDD_TMPL = TEMPLATES / "kdd.md.tmpl"
KDD_RENDERIZADO = SKILL_DIR / "kdd.md"

DECISION_LEDGER_TMPL = TEMPLATES / "decision-ledger.md.tmpl"
DECISION_LEDGER_RENDERIZADO = SKILL_DIR / "decision-ledger.md"

VERIFICADOR_TMPL = TEMPLATES / "verificador.md.tmpl"
VERIFICADOR_RENDERIZADO = SKILL_DIR / "verificador.md"

PRODUCTION_READINESS_TMPL = TEMPLATES / "production-readiness.md.tmpl"
OPERATIONS_TMPL = TEMPLATES / "operations.md.tmpl"

PASOS_KDD = (
    "selection",
    "preprocessing",
    "transformation",
    "data_mining",
    "interpretation_evaluation",
)

FASES_CRISPDM = (
    "business_understanding",
    "data_understanding",
    "data_preparation",
    "modeling",
    "evaluation",
    "production_readiness",
    "deployment",
    "monitoring",
)

PROJECT_STAGES = ("discovery", "experiment", "production_candidate", "production")

PROHIBICIONES_15 = (
    "No editar `project_stage` manualmente",
    "No editar `installation_stage` manualmente",
    "No cerrar una fase de lifecycle por intuición",
    "No inventar un `PASS` que el engine no reportó",
    "No convertir un `WARN` en `PASS` por conveniencia",
    "No registrar un template o scaffold como evidencia real",
    "No usar `calibrate` como bypass de la promoción normal",
    "con algún `FAIL` pendiente en la matriz de `readiness`",
    "No instalar capabilities silenciosamente",
    "No duplicar gates dentro de prompts de delegación",
    "No inferir `risk_level` en una adopción",
    "No asumir datos o métricas que no salieron de una corrida real",
    "No abrir agentes de espera",
    "No delegarle escritura al `data-science-reviewer`",
    "No permitir dos writers concurrentes",
)


def _leer(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8")


class TestMethodologyContenidoNormativo(unittest.TestCase):
    """R1 de spec.md: presencia de los catálogos exactos y sintaxis de CLI
    correcta, distinguida entre `promote` (posicional) y `readiness`
    (`--target`)."""

    def setUp(self) -> None:
        self.contenido = _leer(METHODOLOGY_TMPL)

    def test_archivo_existe(self):
        self.assertTrue(METHODOLOGY_TMPL.exists())

    def test_contiene_los_5_pasos_kdd_canonicos(self):
        for paso in PASOS_KDD:
            self.assertIn(paso, self.contenido, f"Falta el paso KDD canónico {paso!r}")

    def test_contiene_las_8_fases_crispdm(self):
        for fase in FASES_CRISPDM:
            self.assertIn(fase, self.contenido, f"Falta la fase CRISP-DM {fase!r}")

    def test_contiene_los_4_project_stages(self):
        for stage in PROJECT_STAGES:
            self.assertIn(stage, self.contenido, f"Falta el project_stage {stage!r}")

    def test_distingue_project_stage_de_installation_stage(self):
        self.assertIn("project_stage", self.contenido)
        self.assertIn("installation_stage", self.contenido)
        self.assertIn(
            "project_stage` ≠ `installation_stage",
            self.contenido,
            "No se encontró la distinción explícita entre project_stage e installation_stage",
        )

    def test_sintaxis_promote_posicional_sin_target(self):
        self.assertIn('ds_guard project promote <stage> --reason "<texto>"', self.contenido)

    def test_sintaxis_readiness_con_target(self):
        self.assertIn(
            "ds_guard project readiness --target <stage>",
            self.contenido.replace("\n", " "),
        )

    def test_contiene_las_15_prohibiciones(self):
        for frase in PROHIBICIONES_15:
            self.assertIn(frase, self.contenido, f"Falta la prohibición: {frase!r}")

    def test_no_presenta_10_etapas_legacy_como_catalogo_principal(self):
        # `feature_engineering` e `interpretation` son etapas legacy (v0.2)
        # que NO están en los 5 PASOS_KDD canónicos ni en las 8 FASES_CRISPDM
        # -- si aparecen, deben estar en contexto de compatibilidad explícita,
        # nunca como catálogo principal.
        for etapa_solo_legacy in ("feature_engineering", "problem_understanding"):
            if etapa_solo_legacy in self.contenido:
                self.assertIn("compatibilidad", self.contenido)
                self.assertIn("legacy", self.contenido)

    def test_no_presenta_las_4_metodologias_como_paralelas_sin_jerarquia(self):
        self.assertIn("no son cuatro metodologías paralelas", self.contenido.lower())


class TestSkillYaNoTieneFraseObsoleta(unittest.TestCase):
    """R2 de spec.md: SKILL.md ya no describe KDD como "el lifecycle del
    proyecto" sin matiz de CRISP-DM backbone."""

    def test_skill_tmpl_no_contiene_frase_obsoleta(self):
        contenido = _leer(SKILL_TMPL)
        self.assertNotIn(
            "KDD es en qué etapa",
            contenido,
            "SKILL.md.tmpl sigue con la frase obsoleta que describe KDD como "
            "el lifecycle del proyecto sin matiz de CRISP-DM backbone",
        )

    def test_skill_tmpl_menciona_crispdm_como_backbone(self):
        contenido = _leer(SKILL_TMPL)
        self.assertIn("CRISP-DM", contenido)
        self.assertIn("backbone", contenido)

    def test_skill_tmpl_apunta_a_methodology(self):
        contenido = _leer(SKILL_TMPL)
        self.assertIn("methodology.md", contenido)

    def test_skill_renderizado_no_contiene_frase_obsoleta(self):
        contenido = _leer(SKILL_RENDERIZADO)
        self.assertNotIn("KDD es en qué etapa", contenido)


class TestKddYDecisionLedgerCorregidos(unittest.TestCase):
    """R3 de spec.md."""

    def test_kdd_tmpl_no_afirma_kdd_es_el_lifecycle_sin_matiz(self):
        contenido = _leer(KDD_TMPL)
        self.assertNotIn("KDD es el lifecycle del **proyecto**", contenido)
        self.assertIn("CRISP-DM", contenido)
        self.assertIn("methodology.md", contenido)

    def test_kdd_renderizado_no_afirma_kdd_es_el_lifecycle_sin_matiz(self):
        contenido = _leer(KDD_RENDERIZADO)
        self.assertNotIn("KDD es el lifecycle del **proyecto**", contenido)

    def test_decision_ledger_tmpl_no_afirma_kdd_es_en_que_etapa(self):
        contenido = _leer(DECISION_LEDGER_TMPL)
        self.assertNotIn(
            "KDD (`kdd.md`) es en qué etapa del lifecycle de Data Science está el",
            contenido,
        )
        self.assertIn("CRISP-DM", contenido)
        self.assertIn("methodology.md", contenido)

    def test_decision_ledger_renderizado_no_afirma_kdd_es_en_que_etapa(self):
        contenido = _leer(DECISION_LEDGER_RENDERIZADO)
        self.assertNotIn(
            "KDD (`kdd.md`) es en qué etapa del lifecycle de Data Science está el",
            contenido,
        )


class TestVerificadorTieneComandosNuevos(unittest.TestCase):
    """R4 de spec.md: entradas nuevas para lifecycle/project/mlops/status
    unificado."""

    COMANDOS_ESPERADOS = (
        "lifecycle migrate",
        "project init",
        "project calibrate",
        "project set-risk",
        "project status",
        "project readiness --target",
        "project promote <stage> --reason",
        "mlops status",
        "mlops record",
        "mlops evidence add",
    )

    def test_tmpl_documenta_todos_los_comandos_nuevos(self):
        contenido = _leer(VERIFICADOR_TMPL)
        for comando in self.COMANDOS_ESPERADOS:
            self.assertIn(comando, contenido, f"Falta documentar el comando {comando!r}")

    def test_renderizado_documenta_todos_los_comandos_nuevos(self):
        contenido = _leer(VERIFICADOR_RENDERIZADO)
        for comando in self.COMANDOS_ESPERADOS:
            self.assertIn(comando, contenido, f"Falta documentar el comando {comando!r}")

    def test_tmpl_documenta_status_unificado_sin_change_id_obligatorio(self):
        contenido = _leer(VERIFICADOR_TMPL)
        self.assertIn("status [--change-id <id>] [--json] [--verbose]", contenido)
        self.assertIn("unificado", contenido)


class TestSintaxisPromoteCorregidaEnReadinessDocs(unittest.TestCase):
    """R5 de spec.md: production-readiness.md.tmpl/operations.md.tmpl ya no
    usan `--target` en la línea de `promote`."""

    def _lineas_de_promote(self, contenido: str) -> list:
        return [linea for linea in contenido.splitlines() if "project promote" in linea]

    def test_production_readiness_promote_sin_target(self):
        contenido = _leer(PRODUCTION_READINESS_TMPL)
        for linea in self._lineas_de_promote(contenido):
            self.assertNotIn("--target", linea)
        self.assertIn("ds_guard project promote production_candidate --reason", contenido)

    def test_operations_promote_sin_target(self):
        contenido = _leer(OPERATIONS_TMPL)
        for linea in self._lineas_de_promote(contenido):
            self.assertNotIn("--target", linea)
        self.assertIn("ds_guard project promote production --reason", contenido)

    def test_production_readiness_readiness_conserva_target(self):
        # `readiness` sí usa --target -- no se confunde con el fix de `promote`.
        contenido = _leer(PRODUCTION_READINESS_TMPL)
        self.assertIn("project readiness --target production_candidate", contenido)

    def test_operations_readiness_conserva_target(self):
        contenido = _leer(OPERATIONS_TMPL)
        self.assertIn("project readiness --target production", contenido)


class TestSincronizacionTmplRenderizado(unittest.TestCase):
    """R6 de spec.md: los 5 archivos que tienen copia local deben quedar
    byte-idénticos (salvo diferencias triviales de terminador de línea) entre
    su `.tmpl` fuente y su copia renderizada en
    `.claude/skills/lead-data-scientist/`."""

    PARES = (
        (SKILL_TMPL, SKILL_RENDERIZADO),
        (KDD_TMPL, KDD_RENDERIZADO),
        (DECISION_LEDGER_TMPL, DECISION_LEDGER_RENDERIZADO),
        (VERIFICADOR_TMPL, VERIFICADOR_RENDERIZADO),
        (METHODOLOGY_TMPL, METHODOLOGY_RENDERIZADO),
    )

    def test_cada_par_tmpl_renderizado_es_identico(self):
        for tmpl, renderizado in self.PARES:
            with self.subTest(tmpl=str(tmpl), renderizado=str(renderizado)):
                self.assertTrue(tmpl.exists(), f"No existe el .tmpl fuente: {tmpl}")
                self.assertTrue(
                    renderizado.exists(), f"No existe la copia renderizada: {renderizado}"
                )
                # `SKILL_lead_data_scientist.md.tmpl` es el unico de los 5 que trae
                # un placeholder real de proyecto ({{NOMBRE_PROYECTO}}, en su
                # frontmatter, preexistente a este change) -- la copia
                # renderizada de este propio repo ya lo tiene sustituido por
                # "harmessi" (su propio nombre de proyecto). Sustituirlo acá
                # antes de comparar evita un falso positivo de "desincronizado"
                # por el unico placeholder legitimo entre estos 5 archivos.
                contenido_tmpl = (
                    _leer(tmpl).replace("\r\n", "\n").strip("\n").replace("{{NOMBRE_PROYECTO}}", "harmessi")
                )
                contenido_renderizado = _leer(renderizado).replace("\r\n", "\n").strip("\n")
                self.assertEqual(
                    contenido_tmpl,
                    contenido_renderizado,
                    f"Contenido desincronizado entre {tmpl} y {renderizado}",
                )


if __name__ == "__main__":
    unittest.main()
