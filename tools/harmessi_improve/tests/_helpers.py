"""Helpers de tests de harmessi_improve: arma un repo temporal sintético."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

ACTIVO = ".claude/skills/lead-data-scientist/skills/diagnosing-bugs.md"
ACTIVO_2 = ".claude/skills/lead-data-scientist/methodology.md"
CONTENIDO_ACTIVO = "# Skill\nBase original.\n"
GLOSSARY_BASICO = "# Glosario\n\n## churn\n- estado: hypothesis\n- definicion: baja de clientes\n"


def crear_repo(raiz: Path, glossary: Optional[str] = None) -> Path:
    """Crea los archivos mínimos del repo sintético bajo `raiz` y lo devuelve."""
    archivos = {
        ACTIVO: CONTENIDO_ACTIVO,
        ACTIVO_2: "# Metodología\nTexto base.\n",
        "tools/x.py": "X = 1\n",
        ".claude/agents/a.md": "# agente\n",
        ".claude/guardrails.json": "{}\n",
        "docs/x.md": "# doc\n",
        "openspec/changes/x/proposal.md": "# propuesta\n",
    }
    if glossary is not None:
        archivos["GLOSSARY.md"] = glossary
    for rel, texto in archivos.items():
        ruta = raiz / rel
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(texto.encode("utf-8"))
    return raiz


def snapshot(raiz: Path) -> dict:
    """`{ruta_relativa_posix: bytes}` de todos los archivos bajo `raiz`."""
    return {
        p.relative_to(raiz).as_posix(): p.read_bytes()
        for p in sorted(raiz.rglob("*")) if p.is_file()
    }


PROVENANCE = {"proposer_kind": "script", "proposer_label": "test-proposer"}

CHANGE_ID = "20261023-promo-test"
TODOS_ARTEFACTOS = ("proposal.md", "spec.md", "design.md")


def crear_change(raiz: Path, proposal_hash: str, change_id: str = CHANGE_ID,
                 estado: str = "en_implementacion", canal: str = "console_confirmed",
                 aprobar=TODOS_ARTEFACTOS, alcance=(ACTIVO,), citar: bool = True,
                 channel_version="console/v1", control_change_id=None, texto_cita=None) -> Path:
    """Escribe `openspec/changes/<id>/{control.json,tasks.md,proposal.md,spec.md,design.md}` con
    aprobaciones (hash_lf_v1 correcto) por `canal` y alcance configurable. Devuelve el directorio."""
    import hashlib
    import json

    def hash_lf_v1(ruta):  # archivos escritos aquí ya son LF/UTF-8 sin BOM
        return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()

    d = raiz / "openspec" / "changes" / change_id
    d.mkdir(parents=True, exist_ok=True)
    cita = (texto_cita.format(h=proposal_hash) if texto_cita else f"proposal_hash: {proposal_hash}\n") \
        if citar else ""
    textos = {"proposal.md": f"# Propuesta\n{cita}", "spec.md": "# Spec\nR1.\n", "design.md": "# Diseño\nD.\n"}
    for nombre, texto in textos.items():
        (d / nombre).write_bytes(texto.encode("utf-8"))
    (d / "tasks.md").write_bytes(f"# Tareas\n\nestado: {estado}\n".encode("utf-8"))
    aprobaciones = [
        {"artefacto": a, "hash": hash_lf_v1(d / a), "algoritmo": "sha256/lf/v1",
         "registrado_utc": "2026-10-23T12:00:00Z", "approval_channel": canal,
         **({"channel_version": channel_version} if channel_version is not None else {})}
        for a in aprobar
    ]
    control = {"schema_version": 1, "change_id": control_change_id or change_id,
               "aprobaciones": aprobaciones,
               "alcance": {"rutas_autorizadas": list(alcance)}}
    (d / "control.json").write_bytes(json.dumps(control, indent=2).encode("utf-8"))
    return d
