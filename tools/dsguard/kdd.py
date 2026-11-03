"""Adapter publico de compatibilidad legacy v0.2 (Change 2:
20260914-lifecycle-migration-and-kdd-repoint). Las 10 etapas legacy y el
storage real viven en kdd_compat.py -- este modulo expone la misma
superficie publica que tenia en v0.2 (mismos nombres/firmas/retornos) para
que ds_guard.py/dsguard/decision.py/los tests existentes sigan funcionando
sin cambios de contrato, mientras el storage real pasa a ser
openspec/lifecycle/state.json.

evaluation/interpretation son sinonimos funcionales despues de migrar
(ambos mapean al mismo paso KDD interpretation_evaluation) -- ver
kdd_compat.MAPEO_LEGACY_A_KDD y design.md del change.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from . import kdd_compat, lifecycle

ETAPAS = kdd_compat.ETAPAS
ETAPAS_FUTURAS = kdd_compat.ETAPAS_FUTURAS
ESTADOS_ETAPA_VALIDOS = kdd_compat.ESTADOS_ETAPA_VALIDOS
ESTADOS_ETAPA_DESTINO_VALIDOS = kdd_compat.ESTADOS_ETAPA_DESTINO_VALIDOS


class KddEstadoError(Exception):
    """Excepcion publica del adapter -- envuelve tanto
    lifecycle.LifecycleEstadoError como kdd_compat.KddCompatError en el
    borde (ver design.md del change). Nunca se repara/sobreescribe."""


def state_path(repo_root: Path) -> Path:
    """Ruta del legacy (historico, read-only tras migrar). Para storage
    vivo usar lifecycle.state_path."""
    return kdd_compat.state_path_legacy(repo_root)


def _envolver(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (lifecycle.LifecycleEstadoError, kdd_compat.KddCompatError) as e:
        raise KddEstadoError(str(e)) from e


def kdd_init(repo_root: Path):
    return _envolver(kdd_compat.kdd_init, repo_root)


def kdd_status(repo_root: Path) -> dict:
    payload = _envolver(kdd_compat.kdd_status, repo_root)
    etapas_out = {}
    for etapa in ETAPAS:
        info = payload["etapas"][etapa]
        entrada_para_criterios = {"changes": info["changes"], "evidencia": info["evidencia"]}
        change_ids = info["changes"]
        no_localizados = [cid for cid in change_ids if _dir_del_change(repo_root, cid) is None]
        etapas_out[etapa] = {
            "estado": info["estado"],
            "changes": change_ids,
            "criterios_detectables": _criterios_detectables_etapa(repo_root, etapa, entrada_para_criterios),
            "changes_no_localizados": no_localizados,
        }
    return {"schema_version": payload.get("schema_version"), "etapas": etapas_out}


def kdd_transition(repo_root: Path, etapa: str, hacia: str, motivo: Optional[str] = None):
    return _envolver(kdd_compat.kdd_transition, repo_root, etapa, hacia, motivo=motivo)


def etapas_declaradas(control: dict) -> list:
    return kdd_compat.etapas_declaradas(control)


def validar_antes_de_cerrar(repo_root: Path, control: dict) -> list:
    return _envolver(kdd_compat.validar_antes_de_cerrar, repo_root, control)


def sync_al_cerrar(repo_root: Path, control: dict, change_id: str) -> dict:
    return _envolver(kdd_compat.sync_al_cerrar, repo_root, control, change_id)


# --- Criterios detectables (informativo, nunca bloquea) -- SIN CAMBIOS vs v0.2 ----

def _contenido_de_seccion(texto: str, encabezado: str) -> str:
    """Copia deliberada del helper homónimo de `sdd.py` -- ver docstring del
    módulo. Contenido de una sección `## Encabezado` hasta el próximo `## ` (o
    fin de archivo), sin comentarios HTML de plantilla, recortado."""
    patron = re.compile(
        r"^" + re.escape(encabezado) + r"\s*\n(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = patron.search(texto)
    if not m:
        return ""
    sin_comentarios = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.DOTALL)
    return sin_comentarios.strip()


# Etapa -> lista de (archivo relativo al directorio del cambio, encabezado)
# cuyo contenido no vacío, en al menos uno de los cambios referenciados como
# evidencia de la etapa, cuenta como criterio "detectable" cumplido. No juzga
# si el contenido es correcto -- solo si existe (v0.2, ver kdd.md).
_CRITERIOS_DETECTABLES = {
    "problem_understanding": [("proposal.md", "## Objetivo")],
    "data_understanding": [("spec.md", "## Unidad de análisis")],
    "data_preparation": [("proposal.md", "## Alcance")],
    "feature_engineering": [("spec.md", "## Cutoff / information boundary")],
    "modeling": [("spec.md", "## Baseline")],
    "evaluation": [("spec.md", "## Métrica primaria")],
    "interpretation": [("verification.md", "## Resultado final")],
}


def _dir_del_change(repo_root: Path, change_id: str) -> Optional[Path]:
    """Resuelve el directorio real de un cambio para leer evidencia: activo
    primero (`openspec/changes/<id>`), archivado como fallback
    (`openspec/archive/<id>`) -- un cambio cerrado puede haberse archivado
    (`ds_guard archive`) sin que eso cambie su evidencia KDD ya registrada.
    `None` si no está en ninguno de los dos: nunca levanta, el llamador
    decide qué hacer (v0.2: se ignora esa evidencia al calcular criterios
    detectables, sin bloquear nada -- comportamiento controlado, no un
    crash)."""
    activo = Path(repo_root) / "openspec" / "changes" / change_id
    if activo.exists():
        return activo
    archivado = Path(repo_root) / "openspec" / "archive" / change_id
    if archivado.exists():
        return archivado
    return None


def _criterios_detectables_etapa(repo_root: Path, etapa: str, entrada_etapa: dict) -> list:
    if etapa in ETAPAS_FUTURAS:
        return []
    criterios = _CRITERIOS_DETECTABLES.get(etapa, [])
    resultado = []
    change_ids = entrada_etapa.get("changes", [])
    for archivo, encabezado in criterios:
        cumplido = False
        for change_id in change_ids:
            change_dir = _dir_del_change(repo_root, change_id)
            if change_dir is None:
                continue
            ruta = change_dir / archivo
            if not ruta.exists():
                continue
            try:
                texto = ruta.read_text(encoding="utf-8")
            except OSError:
                continue
            if _contenido_de_seccion(texto, encabezado):
                cumplido = True
                break
        resultado.append({"criterio": f"{archivo}:{encabezado}", "cumplido": cumplido})
    return resultado
