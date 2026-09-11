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
    """

    fuente: Optional[str]
    tratamiento: str
    destino: str
    descripcion: str = ""
    perfiles: tuple = field(default_factory=tuple)

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
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/agent_data_science_reviewer.md.tmpl",
        tratamiento=PLANTILLA,
        destino=".claude/agents/data-science-reviewer.md",
        descripcion="Subagente de revisión, solo lectura",
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/agent_metodologo.md.tmpl",
        tratamiento=PLANTILLA,
        destino=".claude/agents/metodologo.md",
        descripcion="Subagente de diseño experimental/metodología, solo lectura",
    ),
    EntradaManifiesto(
        fuente=f"{_dir_templates('python_jupyter_data')}/agent_notebook_runner.md.tmpl",
        tratamiento=PLANTILLA,
        destino=".claude/agents/notebook-runner.md",
        descripcion="Subagente de ejecución controlada de notebooks",
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
        fuente="tools/dsguard/kdd.py",
        tratamiento=VERBATIM,
        destino="tools/dsguard/kdd.py",
        descripcion="Lifecycle KDD del proyecto: state.json, criterios detectables, sync al cierre (Bloque 4)",
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
    "requirements.txt",
    "requirements-lock.txt",
    "tools/tests/test_ds_guard.py",
    "tools/tests/test_hook_presupuesto.py",
    "tools/tests/test_nbrunner.py",
    "tools/tests/test_launcher_common.py",
    "tools/tests/test_pathguard.py",
    "tools/tests/test_hook_rutas.py",
    "tools/tests/test_kdd.py",
    "tools/ds_profile/tests/__init__.py",
    "tools/ds_profile/tests/test_io_readers.py",
    "tools/ds_profile/tests/test_fingerprint.py",
    "tools/ds_profile/tests/test_column_stats.py",
    "tools/ds_profile/tests/test_quality_flags.py",
    "tools/ds_profile/tests/test_sampling.py",
    "tools/ds_profile/tests/test_holdout_guard.py",
    "tools/ds_profile/tests/test_report.py",
    "tools/ds_profile/tests/test_cli.py",
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
