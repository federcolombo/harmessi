"""Manifiesto de instalación: qué archivo fuente se instala, con qué
tratamiento (`VERBATIM` / `PLANTILLA` / `GENERADO` / `MERGE`) y en qué ruta
destino relativa al repo instalado.

`ds_init` nunca embebe una copia estática de los archivos VERBATIM dentro de
`tools/ds_init/`: `MANIFEST` guarda únicamente *rutas relativas* al árbol de
este repositorio (resueltas en runtime vía `raiz_repo_origen()`, nunca
hardcodeadas), para que la Sesión 2 (`writer.py`) las lea al momento de la
corrida y evitar drift entre lo que se instala y lo que este repo usa hoy
(`design.md` §4).

Este módulo no escribe nada en disco: solo describe el plan. La escritura real
es responsabilidad de `writer.py` (Sesión 2, todavía no implementado en este
paquete).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Tratamientos posibles de una entrada del manifiesto.
VERBATIM = "VERBATIM"
PLANTILLA = "PLANTILLA"
GENERADO = "GENERADO"
MERGE = "MERGE"

TRATAMIENTOS_VALIDOS = (VERBATIM, PLANTILLA, GENERADO, MERGE)

# Vocabulario de bundles/stages de instalación progresiva (Change 7 v0.3:
# 20260915-progressive-capability-installation-and-scaffold). Acumulativo:
# cada stage incluye todo lo de los stages anteriores más sus propias
# entradas nuevas (`spec.md` R1). Eje ortogonal a `PROJECT_STAGES` de
# `tools/dsguard/maturity.py` (`installation_stage` describe qué está
# físicamente instalado; `project_stage` describe madurez alcanzada -- nunca
# se confunden ni se escriben implícitamente entre sí).
ORDEN_STAGES = ("discovery", "experiment", "production_candidate", "production")

# Vocabulario cerrado de capabilities conocidas (M8, Change 4:
# `20260930-project-extension-and-installer-integration`, R1-R2 de su
# `spec.md`). Único eje con contenido real a excluir hoy: `predictive_modeling`
# (`data_analysis`/`reporting` quedan documentados como vocabulario reservado,
# sin entradas que los declaren todavía). Usado por `cli.py` (Change 5,
# hallazgo de hardening: la función de filtro ya existía pero no estaba
# wireada a ningún flag real del instalador) para resolver el default "todas
# habilitadas" -- backward compatible, cero cambio si nadie deshabilita nada.
CAPABILITIES_CONOCIDAS = ("predictive_modeling",)

# Capabilities opt-in (Change `20261005-cards-governance-integration`, R1/D1):
# default-OFF, a diferencia de `CAPABILITIES_CONOCIDAS` (default-on histórico).
# Mismo campo persistido (`capabilities_habilitadas`) y mismo filtro de
# manifiesto; solo cambia el cómputo del set. `CAPABILITIES_CONOCIDAS` NO se
# amplía: hacerlo activaría Cards en toda instalación nueva y en todo `sync`.
CAPABILITIES_OPT_IN = ("data_cards", "model_governance")
CAPABILITIES_VALIDAS = CAPABILITIES_CONOCIDAS + CAPABILITIES_OPT_IN

# Mapeo explícito entre el identificador público de perfil (el que se escribe
# en `--perfil` / el default de la CLI, con guiones, R2) y el nombre real del
# directorio del perfil bajo `profiles/` (con guion bajo — no se renombra).
# Cualquier función que necesite resolver la ruta en disco de un perfil debe
# pasar por `resolver_dir_perfil`, nunca concatenar el identificador público
# directamente como nombre de directorio.
PERFILES: dict = {
    "python-jupyter-data": "python_jupyter_data",
}


class PerfilDesconocidoError(ValueError):
    """El identificador de perfil recibido no está en `PERFILES`."""


def resolver_dir_perfil(perfil: str) -> str:
    """Traduce el identificador público de perfil (p. ej. `python-jupyter-data`)
    al nombre real de su directorio bajo `profiles/` (p. ej.
    `python_jupyter_data`). Levanta `PerfilDesconocidoError` con mensaje
    explícito si `perfil` no está en `PERFILES` — nunca deja que un
    `FileNotFoundError` de bajo nivel sea el primer síntoma de un perfil mal
    escrito."""
    if perfil not in PERFILES:
        perfiles_validos = ", ".join(sorted(PERFILES))
        raise PerfilDesconocidoError(
            f"Perfil desconocido: {perfil!r}. Perfiles válidos: {perfiles_validos}"
        )
    return PERFILES[perfil]


@dataclass(frozen=True)
class EntradaManifiesto:
    """Una fila del manifiesto de instalación.

    - `fuente`: ruta relativa a la raíz de este repositorio (origen). `None`
      para entradas `GENERADO`, que no tienen archivo fuente real.
    - `tratamiento`: uno de `TRATAMIENTOS_VALIDOS`.
    - `destino`: ruta relativa a la raíz del repo instalado (destino).
    - `perfiles`: perfiles a los que aplica esta entrada (por defecto, todos
      los perfiles declarados en `profile.json` la incluyen si no se filtra).
    - `stage_minimo`: bundle/stage de instalación progresiva mínimo que
      incluye esta entrada (uno de `ORDEN_STAGES`, default `"discovery"` --
      compatible hacia atrás: cualquier construcción existente sin este kwarg
      sigue funcionando igual, clasificada `discovery`, R3 de `spec.md`).
    - `capabilities`: dominios de trabajo (eje ortogonal a `stage_minimo`) a
      los que esta entrada es exclusiva (por defecto `()`, sin filtro: la
      entrada aplica sin importar qué capabilities tenga habilitadas el
      proyecto -- compatible hacia atrás, R1/R5 de `spec.md` Change
      `20260930-project-extension-and-installer-integration`). Vocabulario
      inicial: `"predictive_modeling"`.
    - `capabilities_cualquiera`: variante «cualquiera de» (R7 del Change
      `20261005-cards-governance-integration`): la entrada aplica si al menos
      una de estas capabilities está habilitada (intersección no vacía). Default
      `()` sin efecto. Compatible con `capabilities` (subconjunto estricto).
    """

    fuente: Optional[str]
    tratamiento: str
    destino: str
    descripcion: str = ""
    perfiles: tuple = field(default_factory=tuple)
    stage_minimo: str = "discovery"
    capabilities: tuple = field(default_factory=tuple)
    capabilities_cualquiera: tuple = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.tratamiento not in TRATAMIENTOS_VALIDOS:
            raise ValueError(
                f"tratamiento inválido {self.tratamiento!r} para destino {self.destino!r}"
            )
        if self.tratamiento != GENERADO and not self.fuente:
            raise ValueError(
                f"entrada {self.destino!r} con tratamiento {self.tratamiento!r} "
                "requiere 'fuente'"
            )
        if self.stage_minimo not in ORDEN_STAGES:
            raise ValueError(
                f"stage_minimo inválido {self.stage_minimo!r} para destino {self.destino!r} "
                f"(válidos: {ORDEN_STAGES})"
            )


def raiz_repo_origen() -> Path:
    """Raíz de este repositorio (origen de las entradas VERBATIM/PLANTILLA),
    resuelta en runtime a partir de la ubicación de este archivo — nunca
    hardcodeada (R16)."""
    # tools/ds_init/manifest.py -> tools/ds_init -> tools -> raíz del repo
    return Path(__file__).resolve().parents[2]


def _dir_templates(perfil: str) -> str:
    return f"tools/ds_init/profiles/{perfil}/templates"


# Manifiesto exacto, ver `design.md` §3 del cambio
# `20260909-inicializador-harness-datos`. Las plantillas viven en
# `profiles/<perfil>/templates/*.tmpl`; su ruta destino es la ruta final en el
# repo instalado, sin el sufijo `.tmpl`.
#
# Auditoría de `capabilities` (Change `20260930-project-extension-and-
# installer-integration`, R2): únicas entradas exclusivas de modelado
# predictivo son `tools/modelquality/*` (ModelQualityPolicy/métricas/baseline
# de modelo). `readiness.py`, `mlops_foundations.py`, `mlops_evidence.py`,
# `qualityevidence/*` y `holdout_guard.py` son MLOps/calidad/holdout
# genéricos (aplican a cualquier pipeline de datos, no solo a modelos
# predictivos) -- no se marcan.
MANIFEST: tuple = (
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/agent_python_data_engineer.md.tmpl",
        tratamiento=PLANTILLA,
        destino=".claude/agents/python-data-engineer.md",
        descripcion="Subagente de implementación (único con permiso de escritura)",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/agent_data_science_reviewer.md.tmpl",
        tratamiento=PLANTILLA,
        destino=".claude/agents/data-science-reviewer.md",
        descripcion="Subagente de revisión, solo lectura",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/agent_metodologo.md.tmpl",
        tratamiento=PLANTILLA,
        destino=".claude/agents/metodologo.md",
        descripcion="Subagente de diseño experimental/metodología, solo lectura",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/agent_notebook_runner.md.tmpl",
        tratamiento=PLANTILLA,
        destino=".claude/agents/notebook-runner.md",
        descripcion="Subagente de ejecución controlada de notebooks",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/SKILL_lead_data_scientist.md.tmpl",
        tratamiento=PLANTILLA,
        destino=".claude/skills/lead-data-scientist/SKILL.md",
        descripcion="Skill orquestador principal",
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/sdd.md.tmpl",
        tratamiento=PLANTILLA,
        destino=".claude/skills/lead-data-scientist/sdd.md",
        descripcion="Referencia SDD ligero",
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/verificador.md.tmpl",
        tratamiento=PLANTILLA,
        destino=".claude/skills/lead-data-scientist/verificador.md",
        descripcion="Referencia del verificador determinista",
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/kdd.md.tmpl",
        tratamiento=PLANTILLA,
        destino=".claude/skills/lead-data-scientist/kdd.md",
        descripcion="Referencia del lifecycle KDD del proyecto (Bloque 4)",
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/decision-ledger.md.tmpl",
        tratamiento=PLANTILLA,
        destino=".claude/skills/lead-data-scientist/decision-ledger.md",
        descripcion="Referencia del decision ledger del proyecto (Bloque 5)",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/methodology.md.tmpl",
        tratamiento=PLANTILLA,
        destino=".claude/skills/lead-data-scientist/methodology.md",
        descripcion="Jerarquía CRISP-DM/KDD/MLOps/SDD, comportamiento del Lead por project_stage "
        "y prohibiciones explícitas (Change 9 v0.3)",
    ),
    EntradaManifiesto(
        fuente=".claude/skills/lead-data-scientist/templates/proposal.md",
        tratamiento=VERBATIM,
        destino=".claude/skills/lead-data-scientist/templates/proposal.md",
    ),
    EntradaManifiesto(
        fuente=".claude/skills/lead-data-scientist/templates/spec.md",
        tratamiento=VERBATIM,
        destino=".claude/skills/lead-data-scientist/templates/spec.md",
    ),
    EntradaManifiesto(
        fuente=".claude/skills/lead-data-scientist/templates/design.md",
        tratamiento=VERBATIM,
        destino=".claude/skills/lead-data-scientist/templates/design.md",
    ),
    EntradaManifiesto(
        fuente=".claude/skills/lead-data-scientist/templates/tasks.md",
        tratamiento=VERBATIM,
        destino=".claude/skills/lead-data-scientist/templates/tasks.md",
    ),
    EntradaManifiesto(
        fuente=".claude/skills/lead-data-scientist/templates/verification.md",
        tratamiento=VERBATIM,
        destino=".claude/skills/lead-data-scientist/templates/verification.md",
    ),
    EntradaManifiesto(
        fuente="tools/ds_guard.py",
        tratamiento=VERBATIM,
        destino="tools/ds_guard.py",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/__init__.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/__init__.py",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/core.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/core.py",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/repo.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/repo.py",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/sdd.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/sdd.py",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/decision.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/decision.py",
        descripcion="Decision ledger append-only del proyecto (Bloque 5)",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/kdd.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/kdd.py",
        descripcion="Lifecycle KDD del proyecto: state.json, criterios detectables, sync al cierre (Bloque 4)",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/lifecycle.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/lifecycle.py",
        descripcion="Lifecycle metodologico neutral: CRISP-DM/KDD/MLOps, openspec/lifecycle/state.json (Change 1 v0.3)",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/kdd_compat.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/kdd_compat.py",
        descripcion="Compatibilidad legacy v0.2 -> lifecycle v0.3: migracion, mapeo, roll-up (Change 2 v0.3)",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/maturity.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/maturity.py",
        descripcion="Estado de madurez/gobernanza del proyecto: .harmessi/project.json (Change 3 v0.3)",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/checks.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/checks.py",
        descripcion="Motor neutral de checks: CheckResult PASS/WARN/FAIL/N-A, reusado por harmessi doctor (Change 4 v0.3)",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/mlops_foundations.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/mlops_foundations.py",
        descripcion="Fundamentos MLOps (reproducibilidad/versionado/lineage/artifacts) desde experiment, vía checks.py (Change 5 v0.3)",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/mlops_evidence.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/mlops_evidence.py",
        descripcion="Evidencia genérica de artifact para tiers production_readiness/operations, vía mlops evidence add (Change 6 v0.3)",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/readiness.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/readiness.py",
        descripcion="Matriz de readiness + promocion secuencial gateada, vía project readiness/promote (Change 6 v0.3)",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/status.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/status.py",
        descripcion=(
            "Superficie unificada de status de proyecto (project/installation/alignment/"
            "lifecycle/mlops/readiness/harness), de solo lectura, vía ds_guard status "
            "(sin --change-id) (Change 8 v0.3)"
        ),
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/scope.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/scope.py",
        descripcion="Alcance de un Change SDD: working tree + diff desde baseline vs. rutas_autorizadas (Change 2 v0.4)",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/scientific_validity.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/scientific_validity.py",
        descripcion="Scientific validity checks (cutoff/holdout/leakage/baseline) sobre .harmessi/scientific-policy.json opcional, vía ds_guard science status (v0.4 Change 0)",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/efficiency.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/efficiency.py",
        descripcion="Observabilidad de eficiencia de agentes: reevalúa sesiones/remediaciones de un Change contra su propio presupuesto declarado, vía ds_guard efficiency report (v0.4 Change 4)",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/notebooks.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/notebooks.py",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/hook_presupuesto.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/hook_presupuesto.py",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/hook_launcher_presupuesto.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/hook_launcher_presupuesto.py",
        descripcion="Lanzador Python puro del hook de presupuesto (sin bash, cross-platform)",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/pathguard.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/pathguard.py",
        descripcion="Protección de rutas: holdouts, data/raw, secretos, guardrails.json (Bloque 3)",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/hook_rutas.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/hook_rutas.py",
    ),
    EntradaManifiesto(
        fuente="tools/dsguard/hook_launcher_rutas.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/hook_launcher_rutas.py",
        descripcion="Lanzador Python puro del hook de protección de rutas (sin bash, cross-platform)",
    ),
    EntradaManifiesto(
        fuente=".claude/guardrails.json",
        tratamiento=VERBATIM,
        destino=".claude/guardrails.json",
        descripcion="Config de pathguard: holdouts/data_raw/secretos_extra/write_scopes/excepciones (R10: no se sobrescribe si ya existe)",
    ),
    EntradaManifiesto(
        fuente="tools/nbrunner/__init__.py",
        tratamiento=VERBATIM,
        destino="tools/nbrunner/__init__.py",
    ),
    EntradaManifiesto(
        fuente="tools/nbrunner/core.py",
        tratamiento=VERBATIM,
        destino="tools/nbrunner/core.py",
    ),
    EntradaManifiesto(
        fuente="tools/nbrunner/execute.py",
        tratamiento=VERBATIM,
        destino="tools/nbrunner/execute.py",
    ),
    EntradaManifiesto(
        fuente="tools/nbrunner/fsdiff.py",
        tratamiento=VERBATIM,
        destino="tools/nbrunner/fsdiff.py",
    ),
    EntradaManifiesto(
        fuente="tools/nbrunner/hook_validar_comando.py",
        tratamiento=VERBATIM,
        destino="tools/nbrunner/hook_validar_comando.py",
    ),
    EntradaManifiesto(
        fuente="tools/nbrunner/hook_launcher.py",
        tratamiento=VERBATIM,
        destino="tools/nbrunner/hook_launcher.py",
        descripcion="Lanzador Python puro del hook de notebook-runner (sin bash, cross-platform)",
    ),
    EntradaManifiesto(
        fuente="tools/launcher_common.py",
        tratamiento=VERBATIM,
        destino="tools/launcher_common.py",
        descripcion="Lógica compartida de resolución de worktree/intérprete de venv de ambos lanzadores",
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/nbrunner_manifest.py.tmpl",
        tratamiento=PLANTILLA,
        destino="tools/nbrunner/manifest.py",
        descripcion="Schema del manifest de corridas, sin rutas prohibidas hardcodeadas",
    ),
    EntradaManifiesto(
        fuente="tools/leadrun/__init__.py",
        tratamiento=VERBATIM,
        destino="tools/leadrun/__init__.py",
        descripcion="Paquete del runtime de ejecución controlada del Lead (v0.8 Change 2)",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente="tools/leadrun/core.py",
        tratamiento=VERBATIM,
        destino="tools/leadrun/core.py",
        descripcion="Tipos base del runtime de ejecución (ExecutionRequest/ExecutionRecord, catálogo EXEC-*, v0.8 Change 2)",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente="tools/leadrun/allowlist.py",
        tratamiento=VERBATIM,
        destino="tools/leadrun/allowlist.py",
        descripcion="Reconocimiento puro de la forma de un comando (script/pytest/notebook/cli_diagnostic, v0.8 Change 2)",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente="tools/leadrun/scripts.py",
        tratamiento=VERBATIM,
        destino="tools/leadrun/scripts.py",
        descripcion="Ejecución de script/pytest vía subprocess.run, sin volver a evaluar la allowlist (v0.8 Change 2)",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente="tools/leadrun/notebooks.py",
        tratamiento=VERBATIM,
        destino="tools/leadrun/notebooks.py",
        descripcion="Composición de tools.nbrunner.* para ejecutar un manifest de notebook desde el runtime del Lead (v0.8 Change 2)",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente="tools/leadrun/runtime.py",
        tratamiento=VERBATIM,
        destino="tools/leadrun/runtime.py",
        descripcion="Orquestador único que produce y persiste ExecutionRecord bajo .harmessi/executions/ (v0.8 Change 2)",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente="tools/notebook_runner.py",
        tratamiento=VERBATIM,
        destino="tools/notebook_runner.py",
        descripcion="CLI de nivel superior 'run --manifest' que cierra el gap del audit de notebook-runner (v0.8 Change 2)",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/smoke_test_generico.py.tmpl",
        tratamiento=GENERADO,
        destino="tools/tests/test_harness_smoke.py",
        descripcion="Smoke test mínimo instalado en el destino (no la suite completa de desarrollo)",
    ),
    EntradaManifiesto(
        fuente="tools/ds_profile/__init__.py",
        tratamiento=VERBATIM,
        destino="tools/ds_profile/__init__.py",
        descripcion="Paquete ds_profile: profiling determinista de datasets CSV/Parquet (Bloque 6)",
    ),
    EntradaManifiesto(
        fuente="tools/ds_profile/__main__.py",
        tratamiento=VERBATIM,
        destino="tools/ds_profile/__main__.py",
    ),
    EntradaManifiesto(
        fuente="tools/ds_profile/cli.py",
        tratamiento=VERBATIM,
        destino="tools/ds_profile/cli.py",
        descripcion="CLI de ds_profile (subcomando 'run', exit codes 0/1/2/3)",
    ),
    EntradaManifiesto(
        fuente="tools/ds_profile/io_readers.py",
        tratamiento=VERBATIM,
        destino="tools/ds_profile/io_readers.py",
        descripcion="Capa de lectura desacoplada: lector CSV (stdlib) y lector Parquet (pyarrow perezoso)",
    ),
    EntradaManifiesto(
        fuente="tools/ds_profile/fingerprint.py",
        tratamiento=VERBATIM,
        destino="tools/ds_profile/fingerprint.py",
    ),
    EntradaManifiesto(
        fuente="tools/ds_profile/schema.py",
        tratamiento=VERBATIM,
        destino="tools/ds_profile/schema.py",
    ),
    EntradaManifiesto(
        fuente="tools/ds_profile/column_stats.py",
        tratamiento=VERBATIM,
        destino="tools/ds_profile/column_stats.py",
    ),
    EntradaManifiesto(
        fuente="tools/ds_profile/quality_flags.py",
        tratamiento=VERBATIM,
        destino="tools/ds_profile/quality_flags.py",
    ),
    EntradaManifiesto(
        fuente="tools/ds_profile/sampling.py",
        tratamiento=VERBATIM,
        destino="tools/ds_profile/sampling.py",
    ),
    EntradaManifiesto(
        fuente="tools/ds_profile/holdout_guard.py",
        tratamiento=VERBATIM,
        destino="tools/ds_profile/holdout_guard.py",
        descripcion="Defensa en profundidad de holdouts para --input/--output, reusa dsguard.pathguard",
    ),
    EntradaManifiesto(
        fuente="tools/ds_profile/report.py",
        tratamiento=VERBATIM,
        destino="tools/ds_profile/report.py",
        descripcion="Ensamblado y escritura atómica de profile.json/profile.md",
    ),
    EntradaManifiesto(
        fuente="tools/dsimpact/__init__.py",
        tratamiento=VERBATIM,
        destino="tools/dsimpact/__init__.py",
        descripcion="Impact Preflight estático (v0.4 Change 1): detecta consumidores potenciales de un diff, solo lectura.",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente="tools/dsimpact/__main__.py",
        tratamiento=VERBATIM,
        destino="tools/dsimpact/__main__.py",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente="tools/dsimpact/cli.py",
        tratamiento=VERBATIM,
        destino="tools/dsimpact/cli.py",
        descripcion="CLI de dsimpact (subcomando 'scan', --since/--staged, --json)",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente="tools/dsimpact/git_source.py",
        tratamiento=VERBATIM,
        destino="tools/dsimpact/git_source.py",
        descripcion="Fuente del cambio via git (reusa dsguard.repo._git), R1",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente="tools/dsimpact/py_changes.py",
        tratamiento=VERBATIM,
        destino="tools/dsimpact/py_changes.py",
        descripcion="Changed items de Python: simbolos de nivel modulo, strings contractuales, R2/R3/R4",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente="tools/dsimpact/consumers_py.py",
        tratamiento=VERBATIM,
        destino="tools/dsimpact/consumers_py.py",
        descripcion="Busqueda de consumidores en texto Python (archivo/celda de notebook), R5/R6",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente="tools/dsimpact/consumers_text.py",
        tratamiento=VERBATIM,
        destino="tools/dsimpact/consumers_text.py",
        descripcion="Busqueda de consumidores en JSON/YAML/TOML/MD, R6",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente="tools/dsimpact/notebooks_source.py",
        tratamiento=VERBATIM,
        destino="tools/dsimpact/notebooks_source.py",
        descripcion="Lectura de celdas de codigo de notebooks (reusa dsguard.notebooks), R8",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente="tools/dsimpact/generic_filter.py",
        tratamiento=VERBATIM,
        destino="tools/dsimpact/generic_filter.py",
        descripcion="Filtro de tokens genericos (denylist + longitud minima), R7",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente="tools/dsimpact/scan.py",
        tratamiento=VERBATIM,
        destino="tools/dsimpact/scan.py",
        descripcion="Orquestador de Impact Preflight: junta changed items + consumidores, dedup/orden, solo lectura",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente="tools/reporting/__init__.py",
        tratamiento=VERBATIM,
        destino="tools/reporting/__init__.py",
        descripcion="Paquete de reporting gobernado (v0.6), sin logica",
    ),
    EntradaManifiesto(
        fuente="tools/reporting/core.py",
        tratamiento=VERBATIM,
        destino="tools/reporting/core.py",
        descripcion="Contratos neutrales de reporting (Report/Chapter/Table/Figure/Insight), solo stdlib",
    ),
    EntradaManifiesto(
        fuente="tools/reporting/governance.py",
        tratamiento=VERBATIM,
        destino="tools/reporting/governance.py",
        descripcion="Governance de reportes (policy, destino, aislamiento, holdout, cutoff), output guard solo lectura",
    ),
    EntradaManifiesto(
        fuente="tools/reporting/cli.py",
        tratamiento=VERBATIM,
        destino="tools/reporting/cli.py",
        descripcion="CLI de reporting gobernado (check-inputs, check-destination, validate: solo lectura; render: escribe report.html de forma atomica, --check no escribe)",
    ),
    EntradaManifiesto(
        fuente="tools/reporting/__main__.py",
        tratamiento=VERBATIM,
        destino="tools/reporting/__main__.py",
        descripcion="Punto de entrada python -m tools.reporting",
    ),
    EntradaManifiesto(
        fuente="tools/reporting/profiles/__init__.py",
        tratamiento=VERBATIM,
        destino="tools/reporting/profiles/__init__.py",
        descripcion="Paquete de profiles de reporting (v0.6), sin logica",
    ),
    EntradaManifiesto(
        fuente="tools/reporting/profiles/eda.py",
        tratamiento=VERBATIM,
        destino="tools/reporting/profiles/eda.py",
        descripcion="Profile EDA de reporting (catalogo de bloques, aplicabilidad explicita y validador EDA-*), solo lectura",
    ),
    EntradaManifiesto(
        fuente="tools/reporting/examples/__init__.py",
        tratamiento=VERBATIM,
        destino="tools/reporting/examples/__init__.py",
        descripcion="Paquete de ejemplos de reporting (v0.6), sin logica",
    ),
    EntradaManifiesto(
        fuente="tools/reporting/examples/eda_generic.py",
        tratamiento=VERBATIM,
        destino="tools/reporting/examples/eda_generic.py",
        descripcion="Ejemplo generico y sintetico de reporte EDA (solo stdlib, determinista)",
    ),
    EntradaManifiesto(
        fuente="tools/reporting/evidence.py",
        tratamiento=VERBATIM,
        destino="tools/reporting/evidence.py",
        descripcion="Evidencia de reportes (fuentes, manifest, escritura/lectura de directorio de reporte, aislamiento por hash)",
    ),
    EntradaManifiesto(
        fuente="tools/reporting/validation.py",
        tratamiento=VERBATIM,
        destino="tools/reporting/validation.py",
        descripcion="Validador de reportes (figuras, insights, manifest y puerta completa sobre un directorio), solo lectura",
    ),
    EntradaManifiesto(
        fuente="tools/reporting/style.py",
        tratamiento=VERBATIM,
        destino="tools/reporting/style.py",
        descripcion="Design system de reportes (estilo visual/editorial, locale, overrides del proyecto); solo stdlib mas dsguard.checks y reporting.evidence (carga gobernada de archivos)",
    ),
    EntradaManifiesto(
        fuente="tools/reporting/plotly_backend.py",
        tratamiento=VERBATIM,
        destino="tools/reporting/plotly_backend.py",
        descripcion="Backend opcional de figuras (dict tipo plotly sin importar plotly a nivel de modulo)",
    ),
    EntradaManifiesto(
        fuente="tools/reporting/render_html.py",
        tratamiento=VERBATIM,
        destino="tools/reporting/render_html.py",
        descripcion="Renderer HTML determinista y offline de reportes (stdlib html)",
    ),
    EntradaManifiesto(
        fuente="tools/reporting/publish.py",
        tratamiento=VERBATIM,
        destino="tools/reporting/publish.py",
        descripcion="Publicacion de reportes: governance, validacion, evidencia y render HTML",
    ),
    EntradaManifiesto(
        fuente="tools/datacontracts/__init__.py",
        tratamiento=VERBATIM,
        destino="tools/datacontracts/__init__.py",
        descripcion="Paquete de contratos de datos (v0.7), sin logica",
    ),
    EntradaManifiesto(
        fuente="tools/datacontracts/core.py",
        tratamiento=VERBATIM,
        destino="tools/datacontracts/core.py",
        descripcion="Contratos neutrales de datos (DataContract/ContractField/Constraint/BusinessRule/ContractVersion/CompatibilityPolicy), solo stdlib (v0.7 Change 0)",
    ),
    EntradaManifiesto(
        fuente="tools/datacontracts/validation.py",
        tratamiento=VERBATIM,
        destino="tools/datacontracts/validation.py",
        descripcion="Evaluacion deterministica de un DataContract contra un profile de ds_profile (validate_contract/validate_contract_against_profile_file), codigos CONTRACT-*, produce dsguard.checks.CheckResult (v0.7 Change 1)",
        stage_minimo="discovery",
    ),
    EntradaManifiesto(
        fuente="tools/datacontracts/evolution.py",
        tratamiento=VERBATIM,
        destino="tools/datacontracts/evolution.py",
        descripcion="Clasificacion deterministica de compatibilidad entre dos versiones de un DataContract (classify_contract_change), codigos CONTRACT-EVOLUTION-*, produce dsguard.checks.CheckResult (v0.7 Change 4)",
        stage_minimo="discovery",
    ),
    EntradaManifiesto(
        fuente="tools/autonomy/__init__.py",
        tratamiento=VERBATIM,
        destino="tools/autonomy/__init__.py",
        descripcion="Paquete de contrato de autonomia (v0.8), sin logica",
        stage_minimo="discovery",
    ),
    EntradaManifiesto(
        fuente="tools/autonomy/core.py",
        tratamiento=VERBATIM,
        destino="tools/autonomy/core.py",
        descripcion="Contrato neutral de autonomia (modos autonomous/supervised, POLICY_TABLE/resolve_action, catalogos STOP/LIMIT, codigos AUTONOMY-*, roles, ApprovalRef/PolicyApproval, PreApprovedDecision), solo stdlib (v0.8 Change 0)",
        stage_minimo="discovery",
    ),
    EntradaManifiesto(
        fuente="tools/autonomy/policy.py",
        tratamiento=VERBATIM,
        destino="tools/autonomy/policy.py",
        descripcion="Politica de autonomia de guardrails.json (parse_autonomy_policy fail-closed, fuentes selladas, resolve_methodological_decision), solo stdlib y core; recibe guard_policy_version_max del llamador (v0.8 Change 0)",
        stage_minimo="discovery",
    ),
    EntradaManifiesto(
        fuente="tools/datasources/__init__.py",
        tratamiento=VERBATIM,
        destino="tools/datasources/__init__.py",
        descripcion="Paquete de acceso neutral a fuentes de datos (v0.8 Change 1), sin logica",
        stage_minimo="discovery",
    ),
    EntradaManifiesto(
        fuente="tools/datasources/core.py",
        tratamiento=VERBATIM,
        destino="tools/datasources/core.py",
        descripcion="Tipos neutrales de fuentes (SourceRef/SourceCapabilities/ObservationRequest/SourceObservation/FieldObservation/SourceProvenance/SourceError), registro unico de codigos SOURCE-*, solo stdlib, sin ramificar por source_kind/tecnologia (v0.8 Change 1)",
        stage_minimo="discovery",
    ),
    EntradaManifiesto(
        fuente="tools/datasources/scan.py",
        tratamiento=VERBATIM,
        destino="tools/datasources/scan.py",
        descripcion="Escaneo por patron de secretos y localizadores fisicos (scan_secrets/scan_locators), puro sobre dicts, best-effort (v0.8 Change 1)",
        stage_minimo="discovery",
    ),
    EntradaManifiesto(
        fuente="tools/datasources/registry.py",
        tratamiento=VERBATIM,
        destino="tools/datasources/registry.py",
        descripcion="Validacion estatica y pura del registro .harmessi/sources.json y resolucion estatica del observer, sin importar codigo del proyecto (v0.8 Change 1)",
        stage_minimo="discovery",
    ),
    EntradaManifiesto(
        fuente="tools/datasources/runtime.py",
        tratamiento=VERBATIM,
        destino="tools/datasources/runtime.py",
        descripcion="Capa de I/O e importlib: observe_source (orden R16), compare_fingerprint, persistencia atomica en .harmessi/observations/; access_check inyectado, no importa autonomy/pathguard (v0.8 Change 1)",
        stage_minimo="discovery",
    ),
    EntradaManifiesto(
        fuente="tools/datasources/profile_bridge.py",
        tratamiento=VERBATIM,
        destino="tools/datasources/profile_bridge.py",
        descripcion="Puente profile.json (ds_profile) -> SourceObservation neutral, puro sobre dicts, no importa ds_profile (v0.8 Change 1)",
        stage_minimo="discovery",
    ),
    EntradaManifiesto(
        fuente="tools/datasources/file_observer.py",
        tratamiento=VERBATIM,
        destino="tools/datasources/file_observer.py",
        descripcion="Unico observer incluido por Harmessi (archivos locales via ds_profile), import perezoso de ds_profile dentro de funciones (v0.8 Change 1)",
        stage_minimo="experiment",
    ),
    EntradaManifiesto(
        fuente="tools/datacontracts/legacy_wording.py",
        tratamiento=VERBATIM,
        destino="tools/datacontracts/legacy_wording.py",
        descripcion="Catalogo LEGACY_PROFILE de mensajes v0.7 verbatim, usado por validate_contract_observation con wording=LEGACY_PROFILE (v0.8 Change 1)",
        stage_minimo="discovery",
    ),
    EntradaManifiesto(
        fuente="tools/modelquality/__init__.py",
        tratamiento=VERBATIM,
        destino="tools/modelquality/__init__.py",
        descripcion="Paquete de politicas de calidad de modelo (v0.7 Change 2), sin logica",
        capabilities=("predictive_modeling",),
    ),
    EntradaManifiesto(
        fuente="tools/modelquality/core.py",
        tratamiento=VERBATIM,
        destino="tools/modelquality/core.py",
        descripcion="Politicas neutrales de calidad de modelo (ModelQualityPolicy/MetricRequirement/EvaluationContext/ObservedMetric/BaselineReference), solo stdlib (v0.7 Change 2)",
        capabilities=("predictive_modeling",),
    ),
    EntradaManifiesto(
        fuente="tools/modelquality/validation.py",
        tratamiento=VERBATIM,
        destino="tools/modelquality/validation.py",
        descripcion="Evaluacion determinista de ModelQualityPolicy contra metricas ya reportadas, codigos QUALITY-*, produce dsguard.checks.CheckResult (v0.7 Change 2)",
        capabilities=("predictive_modeling",),
    ),
    EntradaManifiesto(
        fuente="tools/qualityevidence/__init__.py",
        tratamiento=VERBATIM,
        destino="tools/qualityevidence/__init__.py",
        descripcion="Paquete de evidencia de calidad de datos/modelo y drift (v0.7 Change 3), sin logica",
    ),
    EntradaManifiesto(
        fuente="tools/qualityevidence/core.py",
        tratamiento=VERBATIM,
        destino="tools/qualityevidence/core.py",
        descripcion="Tipos neutrales de evidencia de calidad (QualityEvidenceManifest/DriftEvidence/EvidenceSource/DeclarationRef/ScopeWindow), solo stdlib (v0.7 Change 3)",
    ),
    EntradaManifiesto(
        fuente="tools/qualityevidence/evidence.py",
        tratamiento=VERBATIM,
        destino="tools/qualityevidence/evidence.py",
        descripcion="Persistencia de evidencia de calidad (.harmessi/quality/) y computo de drift (absolute_diff/relative_diff), codigos QUALITYEVIDENCE-* (v0.7 Change 3)",
    ),
    # tools/cards (Change 20261005-cards-governance-integration, R8): opt-in por
    # capability; sin tests; los compartidos aplican si hay data_cards O
    # model_governance. Ningún módulo importa uno de capability ausente.
    EntradaManifiesto(
        fuente="tools/cards/__init__.py",
        tratamiento=VERBATIM,
        destino="tools/cards/__init__.py",
        descripcion="Paquete de Cards de governance (Data/Model Card, assessment), sin logica",
        capabilities_cualquiera=("data_cards", "model_governance"),
    ),
    EntradaManifiesto(
        fuente="tools/cards/core.py",
        tratamiento=VERBATIM,
        destino="tools/cards/core.py",
        descripcion="Tipos y utilidades neutrales de Cards (compartido data_cards/model_governance), solo stdlib",
        capabilities_cualquiera=("data_cards", "model_governance"),
    ),
    EntradaManifiesto(
        fuente="tools/cards/assess.py",
        tratamiento=VERBATIM,
        destino="tools/cards/assess.py",
        descripcion="Evaluacion de requisitos/evidencias/atestaciones de Cards (compartido)",
        capabilities_cualquiera=("data_cards", "model_governance"),
    ),
    EntradaManifiesto(
        fuente="tools/cards/resolvers.py",
        tratamiento=VERBATIM,
        destino="tools/cards/resolvers.py",
        descripcion="Resolvers de evidencia de Cards (compartido)",
        capabilities_cualquiera=("data_cards", "model_governance"),
    ),
    EntradaManifiesto(
        fuente="tools/cards/approvals.py",
        tratamiento=VERBATIM,
        destino="tools/cards/approvals.py",
        descripcion="Adaptador de resolucion de ApprovalRef sobre dsguard (compartido)",
        capabilities_cualquiera=("data_cards", "model_governance"),
    ),
    EntradaManifiesto(
        fuente="tools/cards/discovery.py",
        tratamiento=VERBATIM,
        destino="tools/cards/discovery.py",
        descripcion="Discovery determinista de Cards en governance/ y validacion de proyecto (compartido)",
        capabilities_cualquiera=("data_cards", "model_governance"),
    ),
    EntradaManifiesto(
        fuente="tools/cards/report.py",
        tratamiento=VERBATIM,
        destino="tools/cards/report.py",
        descripcion="Adaptador de Cards a reporting.core.Report (compartido)",
        capabilities_cualquiera=("data_cards", "model_governance"),
    ),
    EntradaManifiesto(
        fuente="tools/cards/datacard.py",
        tratamiento=VERBATIM,
        destino="tools/cards/datacard.py",
        descripcion="Data Card: esquema y evaluacion (capability data_cards)",
        capabilities=("data_cards",),
    ),
    EntradaManifiesto(
        fuente="tools/cards/modelcard.py",
        tratamiento=VERBATIM,
        destino="tools/cards/modelcard.py",
        descripcion="Model Card: esquema y evaluacion (capability model_governance)",
        capabilities=("model_governance",),
    ),
    EntradaManifiesto(
        fuente="tools/cards/govpolicy.py",
        tratamiento=VERBATIM,
        destino="tools/cards/govpolicy.py",
        descripcion="Policy de governance de riesgo de modelo (BASE_POLICY, hardening, merge)",
        capabilities=("model_governance",),
    ),
    EntradaManifiesto(
        fuente="tools/cards/modelgov.py",
        tratamiento=VERBATIM,
        destino="tools/cards/modelgov.py",
        descripcion="Assessment de governance de modelo (capability model_governance)",
        capabilities=("model_governance",),
    ),
    EntradaManifiesto(
        fuente="tools/cards/govconfig.py",
        tratamiento=VERBATIM,
        destino="tools/cards/govconfig.py",
        descripcion="Configuracion efectiva de governance: hardening de proyecto + capa local",
        capabilities=("model_governance",),
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/eda.md.tmpl",
        tratamiento=PLANTILLA,
        destino=".claude/skills/lead-data-scientist/eda.md",
        descripcion="Referencia de Project EDA (Bloque 6)",
    ),
    EntradaManifiesto(
        fuente=".claude/skills/lead-data-scientist/templates/eda.md",
        tratamiento=VERBATIM,
        destino=".claude/skills/lead-data-scientist/templates/eda.md",
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/production-readiness.md.tmpl",
        tratamiento=PLANTILLA,
        destino=".claude/skills/lead-data-scientist/production-readiness.md",
        descripcion="Referencia de los gates de production_readiness y mlops evidence add (Change 7 v0.3)",
        stage_minimo="production_candidate",
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/operations.md.tmpl",
        tratamiento=PLANTILLA,
        destino=".claude/skills/lead-data-scientist/operations.md",
        descripcion="Referencia de los gates de operations y mlops evidence add (Change 7 v0.3)",
        stage_minimo="production",
    ),
    EntradaManifiesto(
        fuente=".claude/settings.json",
        tratamiento=MERGE,
        destino=".claude/settings.json",
        descripcion="Fusión preservando claves existentes no conflictivas (R8)",
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/CLAUDE.md.tmpl",
        tratamiento=GENERADO,
        destino="CLAUDE.md",
        descripcion="Se crea si no existe; si existe requiere --integrar-claude (R9)",
    ),
    EntradaManifiesto(
        fuente=None,
        tratamiento=GENERADO,
        destino=".ds_init/control.json",
        descripcion="Manifiesto versionado de la instalación (hashes SHA-256, R12)",
    ),
)


# Rutas que nunca se instalan, sin importar el perfil (R7). Se usan tanto para
# documentar la exclusión como para que `preflight`/`planner` puedan validar
# que ninguna entrada del manifiesto las viola.
EXCLUSIONES_PERMANENTES: tuple = (
    "notebooks/",
    "data/",
    "docs/",
    "openspec/archive/",
    "openspec/changes/",
    "openspec/kdd/",
    "openspec/lifecycle/",
    ".harmessi/",
    "governance/",
    "requirements.txt",
    "requirements-lock.txt",
    "tools/tests/test_ds_guard.py",
    "tools/tests/test_hook_presupuesto.py",
    "tools/tests/test_nbrunner.py",
    "tools/tests/test_launcher_common.py",
    "tools/tests/test_pathguard.py",
    "tools/tests/test_hook_rutas.py",
    "tools/tests/test_kdd.py",
    "tools/tests/test_decision.py",
    "tools/tests/test_remediation.py",
    "tools/ds_profile/tests/__init__.py",
    "tools/ds_profile/tests/test_io_readers.py",
    "tools/ds_profile/tests/test_fingerprint.py",
    "tools/ds_profile/tests/test_column_stats.py",
    "tools/ds_profile/tests/test_quality_flags.py",
    "tools/ds_profile/tests/test_sampling.py",
    "tools/ds_profile/tests/test_holdout_guard.py",
    "tools/ds_profile/tests/test_report.py",
    "tools/ds_profile/tests/test_cli.py",
    "tools/dsimpact/tests/__init__.py",
    "tools/dsimpact/tests/test_git_source.py",
    "tools/dsimpact/tests/test_py_changes.py",
    "tools/dsimpact/tests/test_consumers.py",
    "tools/dsimpact/tests/test_notebooks.py",
    "tools/dsimpact/tests/test_scan_findings.py",
    "tools/dsimpact/tests/test_cli.py",
    "tools/dsimpact/tests/test_readonly.py",
    "tools/leadrun/tests/__init__.py",
    "tools/leadrun/tests/test_core.py",
    "tools/leadrun/tests/test_allowlist.py",
    "tools/leadrun/tests/test_scripts.py",
    "tools/leadrun/tests/test_notebooks.py",
    "tools/leadrun/tests/test_runtime.py",
    "tools/tests/test_v08_leadrun_neutrality.py",
    "tools/tests/test_ds_guard_exec.py",
    "tools/tests/test_notebook_runner.py",
)


def _leer_profile_json(perfil: str) -> dict:
    dir_perfil = resolver_dir_perfil(perfil)
    ruta = raiz_repo_origen() / "tools" / "ds_init" / "profiles" / dir_perfil / "profile.json"
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def manifest_para_perfil(perfil: str) -> list:
    """Devuelve la lista de `EntradaManifiesto` que aplican a `perfil`
    (identificador público de CLI, p. ej. `python-jupyter-data`), filtrando
    por lo declarado en `profiles/<dir_perfil>/profile.json` — `dir_perfil`
    resuelto vía `resolver_dir_perfil` (nunca `perfil` usado directamente como
    nombre de directorio).

    El único perfil del MVP (`python-jupyter-data`, R2) incluye todo
    `MANIFEST`; el filtro por `perfiles` de cada entrada solo importa si en el
    futuro hay más de un perfil y alguna entrada no aplica a todos.
    """
    config = _leer_profile_json(perfil)
    destinos_incluidos = config.get("incluye_todo", True)

    if destinos_incluidos:
        return list(MANIFEST)

    destinos_explicitos = set(config.get("destinos", []))
    return [entrada for entrada in MANIFEST if entrada.destino in destinos_explicitos]


def manifest_para_perfil_y_stage(perfil: str, stage: str) -> list:
    """Como `manifest_para_perfil(perfil)`, pero además filtra por bundle de
    instalación progresiva (R3 de `spec.md`, Change 7 v0.3): primero filtra
    por perfil (reusa `manifest_para_perfil`, sin duplicar esa lógica),
    después conserva solo las entradas cuyo `stage_minimo` sea `stage` o uno
    de los stages anteriores en `ORDEN_STAGES` (acumulativo — `experiment`
    incluye `discovery`, `production_candidate` incluye `experiment`, etc.).

    `manifest_para_perfil` (sin stage) NO se modifica ni se llama distinto por
    esta función existir: sigue devolviendo siempre el set completo para
    cualquier caller que no pase stage (R3)."""
    if stage not in ORDEN_STAGES:
        raise ValueError(f"stage inválido: {stage!r} (válidos: {ORDEN_STAGES})")
    limite = ORDEN_STAGES.index(stage)
    entradas = manifest_para_perfil(perfil)
    return [
        entrada
        for entrada in entradas
        if ORDEN_STAGES.index(entrada.stage_minimo) <= limite
    ]


def manifest_para_perfil_stage_y_capabilities(
    perfil: str, stage: str, capabilities_habilitadas
) -> list:
    """Como `manifest_para_perfil_y_stage(perfil, stage)`, pero además filtra
    por `capabilities` (eje ortogonal a `stage_minimo`, R2/R4 de `spec.md`
    Change `20260930-project-extension-and-installer-integration`): conserva
    solo las entradas cuyo `capabilities` sea `()` (sin filtro, siempre
    aplica) o un subconjunto de `capabilities_habilitadas` (iterable de
    strings, p. ej. `{"predictive_modeling"}` o `set()`).

    Wrapper puro y aditivo: llama a `manifest_para_perfil_y_stage` sin
    modificarla (R2, D1 de `design.md`) y compone el filtro de capabilities
    por encima -- nunca sustituye el filtro de stage (R4: ambos ejes se
    intersectan). Cualquier llamador existente que siga usando
    `manifest_para_perfil`/`manifest_para_perfil_y_stage` sin capabilities no
    ve ningún cambio de comportamiento (R5)."""
    entradas = manifest_para_perfil_y_stage(perfil, stage)
    return filtrar_entradas_por_capabilities(entradas, capabilities_habilitadas)


def filtrar_entradas_por_capabilities(entradas, capabilities_habilitadas) -> list:
    """UN helper de filtro por capabilities (R7 del Change
    `20261005-cards-governance-integration`), reutilizado por el planner, por
    `regenerar_control` y por Doctor. Una entrada aplica si:
    - `capabilities == ()` y `capabilities_cualquiera == ()` (sin filtro), o
    - `capabilities` es subconjunto de las habilitadas (si está declarada), y
    - `capabilities_cualquiera` intersecta las habilitadas (si está declarada).
    Ambas condiciones declaradas se exigen a la vez (conjunción)."""
    habilitadas = frozenset(capabilities_habilitadas)
    return [
        entrada
        for entrada in entradas
        if (not entrada.capabilities or set(entrada.capabilities) <= habilitadas)
        and (
            not entrada.capabilities_cualquiera
            or set(entrada.capabilities_cualquiera) & habilitadas
        )
    ]


def validar_capabilities(capabilities) -> list:
    """Valida un set de capabilities (D4): devuelve lista de mensajes (vacía =
    válido). Regla: `model_governance` exige `predictive_modeling`. Nombres
    desconocidos NO se validan aquí (R15: Doctor los reporta como WARN)."""
    capabilities = frozenset(capabilities)
    mensajes = []
    if "model_governance" in capabilities and "predictive_modeling" not in capabilities:
        mensajes.append(
            "la capability 'model_governance' requiere 'predictive_modeling' habilitada"
        )
    return mensajes


def capabilities_efectivas_sync(persistidas, enable, disable) -> frozenset:
    """Set efectivo de capabilities para `sync` (R5).

    - Sin flags (enable y disable vacíos): históricas = CONOCIDAS - disable
      (v0.8 intacto); opt-in = persistidas - disable. Sin lista persistida
      (legacy): opt-in deshabilitadas (R12).
    - Con flags y lista persistida: (persistidas | enable) - disable (nada
      deshabilitado se re-habilita ni nada habilitado se pierde sin pedirlo).
    - Con flags y sin lista (legacy): (default histórico | enable) - disable.
    """
    enable = frozenset(enable or ())
    disable = frozenset(disable or ())
    historicas = frozenset(CAPABILITIES_CONOCIDAS)
    if not enable and not disable:
        # Se conserva TODO lo persistido que no sea histórico (opt-in y nombres
        # desconocidos: nunca se descartan en silencio); lo histórico se recalcula.
        no_historicas_persistidas = (
            frozenset(persistidas) - historicas if persistidas is not None else frozenset()
        )
        return (historicas | no_historicas_persistidas) - disable
    base = frozenset(persistidas) if persistidas is not None else historicas
    return (base | enable) - disable
