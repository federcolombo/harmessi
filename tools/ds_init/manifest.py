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
    """

    fuente: Optional[str]
    tratamiento: str
    destino: str
    descripcion: str = ""
    perfiles: tuple = field(default_factory=tuple)
    stage_minimo: str = "discovery"

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
        fuente="tools/dsguard/scientific_validity.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/scientific_validity.py",
        descripcion="Scientific validity checks (cutoff/holdout/leakage/baseline) sobre .harmessi/scientific-policy.json opcional, vía ds_guard science status (v0.4 Change 0)",
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
