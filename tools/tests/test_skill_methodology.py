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

import re
import shutil
import sys
import tempfile
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
    "No permitir instancias writer sin ownership disjunto y predeclarado",
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


# --- Change 4 (20261014-composable-skills-writer-semantics) ---
AGENTES_DIR = REPO_ORIGEN / ".claude" / "agents"
SDD_RENDERIZADO = SKILL_DIR / "sdd.md"
TOOLS_DIR = REPO_ORIGEN / "tools"

PARES_AGENTES = (
    ("python-data-engineer", TEMPLATES / "agent_python_data_engineer.md.tmpl"),
    ("data-science-reviewer", TEMPLATES / "agent_data_science_reviewer.md.tmpl"),
    ("metodologo", TEMPLATES / "agent_metodologo.md.tmpl"),
)


def _leer_norm(ruta: Path) -> str:
    """Lee con EOL normalizado a `\\n`."""
    return _leer(ruta).replace("\r\n", "\n")


def _frontmatter_agente(nombre: str) -> str:
    texto = _leer_norm(AGENTES_DIR / f"{nombre}.md")
    partes = texto.split("---\n")
    # texto = "" + "---\n" + frontmatter + "---\n" + cuerpo
    return partes[1] if len(partes) >= 3 else texto


class TestChange4SkillsYWriters(unittest.TestCase):
    """Protege las decisiones de Change 4: skills componibles, semántica de
    writers (ownership disjunto), ESTADO-AGENTE y continuaciones."""

    FRASES_METHODOLOGY = (
        "One writer = un ROL writer autorizado",
        "Skills enseñan cómo razonar; Roles determinan quién puede actuar; Runtime hace cumplir y calcula",
        "Guidance, nunca authority",
        "(1) governance/runtime, (2) contrato del rol, (3) contrato del proyecto (`CLAUDE.md`), (4) guidance de la skill",
        "`ml-engineer` NO existe",
        "Evals ≠ tests",
        "Anti-loop",
        "ESTADO-AGENTE",
        "Retry/reintento",
        "SDD-ESTADO-DIVERGENTE",
        "Intervenciones de emergencia",
        "checkpoint Git limpio/conocido",
        "N roles writer distintos escribiendo: no",
    )
    FRASES_AUSENTES = (
        "Nunca** hay dos writers concurrentes",
        "No permitir dos writers concurrentes",
    )

    def test_methodology_md_y_tmpl_contienen_las_frases(self):
        for ruta in (METHODOLOGY_RENDERIZADO, METHODOLOGY_TMPL):
            contenido = _leer_norm(ruta)
            for frase in self.FRASES_METHODOLOGY:
                with self.subTest(archivo=ruta.name, frase=frase):
                    self.assertIn(frase, contenido)

    def test_methodology_md_y_tmpl_no_contienen_frases_obsoletas(self):
        for ruta in (METHODOLOGY_RENDERIZADO, METHODOLOGY_TMPL):
            contenido = _leer_norm(ruta)
            for frase in self.FRASES_AUSENTES:
                with self.subTest(archivo=ruta.name, frase=frase):
                    self.assertNotIn(frase, contenido)

    def test_sdd_md_contiene_secciones_de_change_4(self):
        contenido = _leer_norm(SDD_RENDERIZADO)
        for frase in ("Ownership de writers", "Skills cargados", "Continuación"):
            with self.subTest(frase=frase):
                self.assertIn(frase, contenido)

    def test_skill_md_documenta_skills_componibles_y_continuacion(self):
        contenido = _leer_norm(SKILL_RENDERIZADO)
        self.assertIn("## Skills componibles", contenido)
        self.assertIn("continuación", contenido)

    def test_verificador_md_documenta_ownership_y_continuaciones(self):
        contenido = _leer_norm(VERIFICADOR_RENDERIZADO)
        for frase in (
            "ownership check",
            "--max-continuaciones",
            "SDD-ESTADO-DIVERGENTE",
            "OWNERSHIP-SOLAPADO",
        ):
            with self.subTest(frase=frase):
                self.assertIn(frase, contenido)

    def test_estado_agente_en_agentes_skill_y_methodology(self):
        formato = "ESTADO-AGENTE: completed|continue|blocked|needs-review"
        rutas = (
            [AGENTES_DIR / f"{nombre}.md" for nombre, _ in PARES_AGENTES]
            + [tmpl for _, tmpl in PARES_AGENTES]
            + [SKILL_RENDERIZADO, SKILL_TMPL, METHODOLOGY_RENDERIZADO, METHODOLOGY_TMPL]
        )
        for ruta in rutas:
            with self.subTest(archivo=str(ruta)):
                self.assertIn(formato, _leer_norm(ruta))

    def test_sdd_fija_que_el_writer_no_edita_tasks_md(self):
        # I3: el Lead dicta tasks.md; lo escribe una instancia de python-data-engineer.
        for ruta in (SDD_RENDERIZADO, TEMPLATES / "sdd.md.tmpl"):
            with self.subTest(archivo=ruta.name):
                self.assertIn("no edita `tasks.md` por su cuenta", _leer_norm(ruta))

    def test_paridad_exacta_md_tmpl_methodology_verificador_y_agentes(self):
        pares = [
            (METHODOLOGY_RENDERIZADO, METHODOLOGY_TMPL),
            (VERIFICADOR_RENDERIZADO, VERIFICADOR_TMPL),
        ] + [(AGENTES_DIR / f"{nombre}.md", tmpl) for nombre, tmpl in PARES_AGENTES]
        for renderizado, tmpl in pares:
            with self.subTest(renderizado=renderizado.name):
                self.assertEqual(
                    _leer_norm(tmpl).replace("{{NOMBRE_PROYECTO}}", "harmessi"),
                    _leer_norm(renderizado),
                    f"Desincronizado: {tmpl} vs {renderizado}",
                )


class TestChange4InvariantesNoRegresion(unittest.TestCase):
    """Invariantes que Change 4 no debe haber alterado."""

    def test_max_turns_por_agente(self):
        esperado = {
            "python-data-engineer": 12,
            "data-science-reviewer": 16,
            "metodologo": 8,
            "notebook-runner": 4,
        }
        for nombre, turnos in esperado.items():
            with self.subTest(agente=nombre):
                self.assertRegex(_frontmatter_agente(nombre), rf"(?m)^maxTurns: {turnos}\s*$")

    def test_tools_por_agente(self):
        esperado = {
            "python-data-engineer": "Read, Edit, Write, NotebookEdit, Grep, Glob",
            "data-science-reviewer": "Read, Grep, Glob",
            "metodologo": "Read, Grep, Glob",
            "notebook-runner": "Bash",
        }
        for nombre, herramientas in esperado.items():
            with self.subTest(agente=nombre):
                self.assertRegex(
                    _frontmatter_agente(nombre), rf"(?m)^tools: {herramientas}\s*$"
                )

    def test_reviewer_y_metodologo_sin_bash_en_tools(self):
        for nombre in ("data-science-reviewer", "metodologo"):
            with self.subTest(agente=nombre):
                self.assertNotIn("Bash", _frontmatter_agente(nombre))

    def test_reviewer_no_menciona_bash_como_herramienta(self):
        texto = _leer_norm(AGENTES_DIR / "data-science-reviewer.md")
        for linea in texto.splitlines():
            if "Bash" in linea:
                self.assertIn("no tenés Bash", linea, f"Mención de Bash como herramienta: {linea!r}")

    def test_no_existe_ml_engineer(self):
        self.assertFalse((AGENTES_DIR / "ml-engineer.md").exists())

    def test_ds_guard_conserva_budget_y_tope_de_continuaciones(self):
        contenido = _leer_norm(TOOLS_DIR / "ds_guard.py")
        # Cambio de contrato (v0.11 Change 3): el valor 90 queda intacto pero el
        # literal es único, definido en core.py y referenciado desde ds_guard.py.
        self.assertIn('"session_minutes": core.SESSION_MINUTES_DEFAULT', contenido)
        contenido_core = _leer_norm(TOOLS_DIR / "dsguard" / "core.py")
        self.assertIn("SESSION_MINUTES_DEFAULT = 90", contenido_core)
        self.assertIn("MAX_CONTINUACIONES_DURO = 5", contenido)

    def test_sdd_conserva_default_de_continuaciones(self):
        contenido = _leer_norm(TOOLS_DIR / "dsguard" / "sdd.py")
        # Change 3 (R4b): el parametro es Optional y el default efectivo sigue siendo 1.
        self.assertIn("max_continuaciones_por_subagente: Optional[int] = None", contenido)
        self.assertIn('"max_continuaciones_por_subagente", 1', contenido)

    def test_hook_presupuesto_no_cambio_prioridad_de_claves(self):
        # H1 (identidad del subagente) esta UNCONFIRMED: el hook no se toca.
        contenido = _leer_norm(TOOLS_DIR / "dsguard" / "hook_presupuesto.py")
        self.assertIn('("agent_id", "agent_name", "id", "subagent_type", "name")', contenido)


class TestChange4NoExistenSkillsNiGlosario(unittest.TestCase):
    def test_domain_modeling_existe_y_pasa_skill_contract(self):
        ruta = SKILL_DIR / "skills" / "domain-modeling.md"
        self.assertTrue(ruta.exists())
        roles = {"lead-data-scientist"} | {p.stem for p in AGENTES_DIR.glob("*.md")}
        herramientas = str(TOOLS_DIR)
        agregado = herramientas not in sys.path
        if agregado:
            sys.path.insert(0, herramientas)
        try:
            from dsguard import skill_contract
        finally:
            if agregado:
                sys.path.remove(herramientas)
        self.assertEqual(skill_contract.validar_skill(ruta, roles), [])

    def test_no_existen_skill_tdd_ni_glossary_en_raiz(self):
        for ruta in (
            SKILL_DIR / "skills" / "tdd.md",
            REPO_ORIGEN / "GLOSSARY.md",
        ):
            with self.subTest(ruta=str(ruta)):
                self.assertFalse(ruta.exists(), f"No debería existir: {ruta}")

    def test_plantilla_de_skill_existe_y_pasa_skill_contract(self):
        plantilla = SKILL_DIR / "templates" / "skill.md"
        self.assertTrue(plantilla.exists())
        herramientas = str(TOOLS_DIR)
        agregado = herramientas not in sys.path
        if agregado:
            sys.path.insert(0, herramientas)
        try:
            from dsguard import skill_contract
        finally:
            if agregado:
                sys.path.remove(herramientas)
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "nombre-de-skill.md"
            shutil.copyfile(plantilla, destino)
            hallazgos = skill_contract.validar_skill(destino, {"lead-data-scientist"})
        self.assertEqual(
            hallazgos, [], f"La plantilla no pasa skill_contract: {hallazgos}"
        )


# --- Change 5 (20261014-domain-modeling) ---
DOMAIN_MODELING_SKILL = SKILL_DIR / "skills" / "domain-modeling.md"


class TestChange5DomainModeling(unittest.TestCase):
    FRASES_METHODOLOGY = (
        "## 33. Domain modeling",
        "hypothesis",
        "approved",
        "Decision Ledger",
        "Data Contract",
        "Data Card",
        "managed",
        "console_confirmed",
    )

    def test_methodology_md_y_tmpl_identicos_con_frases(self):
        md = _leer_norm(METHODOLOGY_RENDERIZADO)
        tmpl = _leer_norm(METHODOLOGY_TMPL).replace("{{NOMBRE_PROYECTO}}", "harmessi")
        self.assertEqual(tmpl, md)
        for frase in self.FRASES_METHODOLOGY:
            with self.subTest(frase=frase):
                self.assertIn(frase, md)

    def test_skill_contiene_frases_y_frontmatter_sin_claves_prohibidas(self):
        contenido = _leer_norm(DOMAIN_MODELING_SKILL)
        for frase in ("hypothesis", "approved", "ambigüedad material"):
            with self.subTest(frase=frase):
                self.assertIn(frase, contenido)
        frontmatter = contenido.split("---\n")[1]
        for clave in ("tools", "permissions", "hooks"):
            with self.subTest(clave=clave):
                self.assertNotRegex(frontmatter, rf"(?m)^{clave}\s*:")

    def test_skill_md_y_tmpl_mencionan_domain_modeling(self):
        for ruta in (SKILL_RENDERIZADO, SKILL_TMPL):
            with self.subTest(archivo=ruta.name):
                self.assertIn("domain-modeling", _leer_norm(ruta))

    def test_problem_framing_frases_normativas(self):
        ruta = SKILL_DIR / "skills" / "problem-framing.md"
        contenido = _leer_norm(ruta)
        for frase in (
            "Tres niveles", "checkpoint humano", "supuesto explícito y trazable",
            "domain-modeling", "grill-me", "opt-in", "metodologo",
            "No es un interrogatorio obligatorio", "NO se carga por defecto",
        ):
            with self.subTest(frase=frase):
                self.assertIn(frase, contenido)
        # grill-me: opt-in anclado a la sección 6; no existe como skill aparte.
        seccion = contenido.split("## 6. ")[1].split("## 7. ")[0]
        for frase in ("opt-in", "Solo si el humano pide"):
            with self.subTest(seccion6=frase):
                self.assertIn(frase, seccion)
        self.assertFalse((SKILL_DIR / "skills" / "grill-me.md").exists())
        frontmatter = contenido.split("---\n")[1]
        for clave in ("tools", "permissions", "hooks", "artifacts"):
            with self.subTest(clave=clave):
                self.assertNotRegex(frontmatter, rf"(?m)^{clave}\s*:")

    def test_problem_framing_en_skill_md_methodology_y_tmpl(self):
        for ruta in (SKILL_RENDERIZADO, SKILL_TMPL):
            with self.subTest(archivo=ruta.name):
                contenido = _leer_norm(ruta)
                self.assertIn("problem-framing", contenido)
                self.assertIn("grill-me", contenido)
        for ruta in (METHODOLOGY_RENDERIZADO, METHODOLOGY_TMPL):
            with self.subTest(archivo=ruta.name):
                self.assertIn("## 37. Problem framing", _leer_norm(ruta))

    def test_diagnosing_bugs_frases_normativas(self):
        ruta = SKILL_DIR / "skills" / "diagnosing-bugs.md"
        contenido = _leer_norm(ruta)
        # Workflow: los 9 pasos en orden, anclados a la sección 3.
        seccion3 = contenido.split("## 3. ")[1].split("## 4. ")[0]
        pasos = ["reproduce", "minimize", "classify", "hypothesis", "instrument",
                 "test hypothesis", "fix root cause", "regression test", "verify"]
        posiciones = []
        for i, paso in enumerate(pasos, start=1):
            marca = f"{i}. **{paso}**"
            with self.subTest(paso=paso):
                self.assertIn(marca, seccion3)
            posiciones.append(seccion3.find(marca))
        self.assertEqual(posiciones, sorted(posiciones))
        # Clases de fallo (sección 4).
        seccion4 = contenido.split("## 4. ")[1].split("## 5. ")[0]
        for clase in ("code bug", "data issue", "environment", "configuration",
                      "contract mismatch", "expected behavior", "nondeterminism"):
            with self.subTest(clase=clase):
                self.assertIn(f"**{clase}**", seccion4)
        for frase in ("raw/", "Data Contract", "RANDOM_STATE"):
            with self.subTest(seccion4=frase):
                self.assertIn(frase, seccion4)
        # Baseline-aware focalizado (sección 6).
        seccion6 = contenido.split("## 6. ")[1].split("## 7. ")[0]
        for clase in ("introduced", "pre-existing", "environment", "inconclusive"):
            with self.subTest(clasificacion=clase):
                self.assertIn(f"`{clase}`", seccion6)
        seccion6_n = re.sub(r"\s+", " ", seccion6)
        for frase in ("Nunca la suite completa", "ni se atribuye al Change ni se ignora",
                      "SOLO LECTURA", "git show", "git diff", "Prohibido `git checkout`",
                      "nunca `pre-existing`", "duda razonable", "git check-ignore",
                      "área temporal", "tests ni scripts que lean datasets completos u holdouts"):
            with self.subTest(seccion6=frase):
                self.assertIn(frase, seccion6_n)
        # Ausencia de autoridad y reparto de roles (espacios normalizados).
        contenido_n = re.sub(r"\s+", " ", contenido)
        for frase in ("Guidance, nunca authority", "ds_guard exec", "NO se carga",
                      "Síntoma ≠ causa raíz", "No reemplaza tests ni al reviewer",
                      "cuenta como reintento/remediation", "cuando aplique según methodology §29",
                      "PROPONE", "datos sintéticos o agregados", "se retira en verify",
                      "CLAUDE.md §1", "se escala al humano o al `metodologo`",
                      "tope propio del diagnóstico, no de remediation",
                      "que decide si se reabre el SDD"):
            with self.subTest(frase=frase):
                self.assertIn(frase, contenido_n)
        frontmatter = contenido.split("---\n")[1]
        for clave in ("tools", "permissions", "hooks", "artifacts"):
            with self.subTest(clave=clave):
                self.assertNotRegex(frontmatter, rf"(?m)^{clave}\s*:")

    def test_diagnosing_bugs_en_skill_md_methodology_y_tmpl(self):
        for ruta in (SKILL_RENDERIZADO, SKILL_TMPL):
            with self.subTest(archivo=ruta.name):
                contenido = _leer_norm(ruta)
                self.assertIn("diagnosing-bugs", contenido)
                self.assertIn("baseline", contenido)
        for ruta in (METHODOLOGY_RENDERIZADO, METHODOLOGY_TMPL):
            with self.subTest(archivo=ruta.name):
                self.assertIn("## 38. Diagnóstico de fallos", _leer_norm(ruta))

    def test_verificador_md_y_tmpl_mencionan_glossary(self):
        for ruta in (VERIFICADOR_RENDERIZADO, VERIFICADOR_TMPL):
            contenido = _leer_norm(ruta)
            for frase in ("glossary check", "glossary hash", "GLOSSARY-APROBACION-SIN-T1"):
                with self.subTest(archivo=ruta.name, frase=frase):
                    self.assertIn(frase, contenido)

    def test_manifest_no_tiene_entrada_glossary(self):
        herramientas = str(TOOLS_DIR)
        agregado = herramientas not in sys.path
        if agregado:
            sys.path.insert(0, herramientas)
        try:
            from ds_init import manifest
        finally:
            if agregado:
                sys.path.remove(herramientas)
        destinos = [e.destino for e in manifest.MANIFEST]
        self.assertNotIn("GLOSSARY.md", destinos)

    def test_glossary_py_no_importa_human_presence(self):
        codigo = _leer_norm(TOOLS_DIR / "dsguard" / "glossary.py")
        self.assertNotIn("human_presence", codigo)

    def test_roadmap_documenta_change_5(self):
        contenido = _leer_norm(REPO_ORIGEN / "docs" / "roadmap" / "v0.10.md")
        self.assertIn("Change 5 — Domain Modeling", contenido)
        self.assertIn("GLOSSARY.md", contenido)


# --- Change 1 v0.12 (20261021-v012-harness-surfaces) ---
class TestV012SuperficiesDelHarness(unittest.TestCase):
    CODIGO = "SKILL-ARTIFACT-SUPERFICIE-PROTEGIDA"

    def test_methodology_md_y_tmpl_documentan_superficies(self):
        for ruta in (METHODOLOGY_RENDERIZADO, METHODOLOGY_TMPL):
            contenido = _leer_norm(ruta)
            for frase in ("## 36. Superficies del harness", "Optimizable ≠ auto-modificable",
                          "superficie_de_ruta", self.CODIGO):
                with self.subTest(archivo=ruta.name, frase=frase):
                    self.assertIn(frase, contenido)

    def test_skill_verificador_y_plantilla_mencionan_codigo(self):
        for ruta in (SKILL_RENDERIZADO, SKILL_TMPL):
            with self.subTest(archivo=ruta.name):
                self.assertIn("Optimizable ≠ auto-modificable", _leer_norm(ruta))
        for ruta in (VERIFICADOR_RENDERIZADO, VERIFICADOR_TMPL, SKILL_DIR / "templates" / "skill.md"):
            with self.subTest(archivo=ruta.name):
                self.assertIn(self.CODIGO, _leer_norm(ruta))

    def test_architecture_documenta_superficies(self):
        contenido = _leer_norm(REPO_ORIGEN / "ARCHITECTURE.md")
        for frase in ("## 9. Harness Surfaces (v0.12)", "Optimizable ≠ auto-modificable", "candidate/probe engine"):
            with self.subTest(frase=frase):
                self.assertIn(frase, contenido)


if __name__ == "__main__":
    unittest.main()
