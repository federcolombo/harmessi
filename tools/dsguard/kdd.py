"""Lifecycle KDD del proyecto (Bloque 4, v0.2.0): estado de las 10 etapas en
`openspec/kdd/state.json`, separado del estado SDD por cambio (`tasks.md`).

No conoce Git (usa rutas relativas a `repo_root`, resuelto por el llamador vía
`repo.py`) y duplica deliberadamente el pequeño helper de secciones de
`sdd.py` (`_contenido_de_seccion`) en vez de importarlo: KDD se apoya en la
convención de artefactos de SDD, pero no depende de su código interno — ver
`kdd.md` §"Relación con SDD".

v0.2: solo valida estructura y transiciones. Ningún gate juzga calidad o
contenido metodológico (eso queda para v0.3+, ver `kdd.md`).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from .core import Finding, ahora_utc, escribir_texto_atomico

# --- Catálogo de etapas --------------------------------------------------------

ETAPAS = (
    "problem_understanding",
    "data_understanding",
    "data_preparation",
    "feature_engineering",
    "modeling",
    "evaluation",
    "interpretation",
    "production_readiness",
    "deployment",
    "monitoring",
)

# Declaradas en el catálogo pero sin gates ni campos obligatorios activos en
# v0.2 (SKILL.md/kdd.md): nacen en estado "futura" y no admiten transiciones
# todavía.
ETAPAS_FUTURAS = frozenset({"production_readiness", "deployment", "monitoring"})

ESTADOS_ETAPA_VALIDOS = frozenset({"no_iniciada", "en_progreso", "cerrada", "futura"})

# Estados a los que se puede pedir avanzar/retroceder vía `kdd transition`.
# "futura" nunca es un destino válido en v0.2 -- no hay forma de sacar una
# etapa de "futura" desde este comando todavía.
ESTADOS_ETAPA_DESTINO_VALIDOS = frozenset({"no_iniciada", "en_progreso", "cerrada"})

_TRANSICIONES_VALIDAS_ETAPA = {
    "no_iniciada": {"en_progreso"},
    "en_progreso": {"cerrada"},
    "cerrada": {"en_progreso"},
}

SCHEMA_VERSION_SOPORTADA = 1


class KddEstadoError(Exception):
    """`state.json` existe pero no es válido: JSON corrupto o schema inesperada.

    Nunca se repara ni se sobreescribe automáticamente -- se propaga para que
    el llamador decida (típicamente bloquear el comando, nunca continuar como
    si el archivo estuviera bien)."""


# --- Ruta y schema ----------------------------------------------------------

def state_path(repo_root: Path) -> Path:
    return Path(repo_root) / "openspec" / "kdd" / "state.json"


def estado_inicial() -> dict:
    ahora = ahora_utc()
    etapas = {}
    for etapa in ETAPAS:
        etapas[etapa] = {
            "estado": "futura" if etapa in ETAPAS_FUTURAS else "no_iniciada",
            "changes": [],
            "evidencia": [],
            "actualizado_utc": ahora,
        }
    return {
        "schema_version": SCHEMA_VERSION_SOPORTADA,
        "creado_utc": ahora,
        "etapas": etapas,
        "historial_transiciones": [],
    }


def leer_estado(path: Path) -> dict:
    """Lee y valida `state.json`. Levanta `FileNotFoundError` si no existe
    (caso "todavía no se corrió `kdd init`", distinto de corrupción) o
    `KddEstadoError` si existe pero el contenido no es válido."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}")
    with open(path, "r", encoding="utf-8") as f:
        try:
            datos = json.load(f)
        except json.JSONDecodeError as e:
            raise KddEstadoError(f"{path} no es JSON válido: {e}")

    if not isinstance(datos, dict):
        raise KddEstadoError(f"{path}: se esperaba un objeto JSON en la raíz")
    if datos.get("schema_version") != SCHEMA_VERSION_SOPORTADA:
        raise KddEstadoError(
            f"schema_version desconocida en {path}: {datos.get('schema_version')!r} "
            f"(se esperaba {SCHEMA_VERSION_SOPORTADA})"
        )
    etapas = datos.get("etapas")
    if not isinstance(etapas, dict) or set(etapas.keys()) != set(ETAPAS):
        raise KddEstadoError(
            f"{path}: 'etapas' debe tener exactamente las {len(ETAPAS)} etapas del catálogo KDD"
        )
    for etapa, entrada in etapas.items():
        if not isinstance(entrada, dict) or entrada.get("estado") not in ESTADOS_ETAPA_VALIDOS:
            raise KddEstadoError(f"{path}: etapa '{etapa}' con 'estado' ausente o inválido")
        if not isinstance(entrada.get("changes"), list) or not isinstance(entrada.get("evidencia"), list):
            raise KddEstadoError(f"{path}: etapa '{etapa}' con 'changes'/'evidencia' inválidos")
    if not isinstance(datos.get("historial_transiciones"), list):
        raise KddEstadoError(f"{path}: 'historial_transiciones' debe ser una lista")
    return datos


def _escribir_estado(path: Path, estado: dict) -> None:
    texto = json.dumps(estado, indent=2, ensure_ascii=False) + "\n"
    escribir_texto_atomico(path, texto)


# --- init --------------------------------------------------------------------

def kdd_init(repo_root: Path):
    """(estado, creado: bool). Idempotente: si `state.json` ya existe y es
    válido, lo devuelve tal cual sin tocarlo (`creado=False`). Si existe pero
    está corrupto, deja que `KddEstadoError` se propague -- nunca lo
    sobreescribe."""
    path = state_path(repo_root)
    if path.exists():
        return leer_estado(path), False
    estado = estado_inicial()
    _escribir_estado(path, estado)
    return estado, True


# --- Criterios detectables (informativo, nunca bloquea) ------------------------

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


def kdd_status(repo_root: Path) -> dict:
    """Informativo puro: nunca levanta por contenido, solo por
    `state.json` ausente/corrupto (responsabilidad del llamador via
    `FileNotFoundError`/`KddEstadoError`)."""
    path = state_path(repo_root)
    estado = leer_estado(path)
    etapas_out = {}
    for etapa in ETAPAS:
        entrada = estado["etapas"][etapa]
        change_ids = entrada.get("changes", [])
        # Informativo (no persiste en state.json, no cambia su schema): un
        # change_id que no aparece ni en openspec/changes/ ni en
        # openspec/archive/ no crashea nada -- se reporta acá para que no
        # quede invisible, en vez de tratarse como "criterio no cumplido" sin
        # explicación.
        no_localizados = [cid for cid in change_ids if _dir_del_change(repo_root, cid) is None]
        etapas_out[etapa] = {
            "estado": entrada["estado"],
            "changes": list(change_ids),
            "criterios_detectables": _criterios_detectables_etapa(repo_root, etapa, entrada),
            "changes_no_localizados": no_localizados,
        }
    return {"schema_version": estado.get("schema_version"), "etapas": etapas_out}


# --- transition ----------------------------------------------------------------

def kdd_transition(repo_root: Path, etapa: str, hacia: str, motivo: Optional[str] = None):
    """(ok: bool, findings: list[Finding]). Si `ok`, ya escribió `state.json`
    atómicamente; si no, no escribió nada. Nunca reevalúa ni toca evidencia --
    eso es responsabilidad exclusiva de `sync_al_cerrar`. Deja propagar
    `FileNotFoundError`/`KddEstadoError` al llamador si `state.json` no existe
    o está corrupto."""
    if etapa not in ETAPAS:
        return False, [Finding("KDD-ETAPA-DESCONOCIDA", f"Etapa KDD desconocida: {etapa}")]
    if hacia not in ESTADOS_ETAPA_DESTINO_VALIDOS:
        return False, [
            Finding("KDD-ETAPA-DESTINO-INVALIDO", f"Estado destino desconocido para una etapa KDD: {hacia}")
        ]

    path = state_path(repo_root)
    estado = leer_estado(path)

    entrada = estado["etapas"][etapa]
    actual = entrada["estado"]

    if actual == "futura":
        return False, [
            Finding(
                "KDD-ETAPA-FUTURA",
                f"La etapa '{etapa}' es futura en v0.2: no admite transiciones todavía",
            )
        ]

    if hacia not in _TRANSICIONES_VALIDAS_ETAPA.get(actual, set()):
        return False, [Finding("KDD-TRANSICION-INVALIDA", f"Transición inválida: {actual} -> {hacia}")]

    if hacia == "cerrada" and not entrada.get("evidencia"):
        return False, [
            Finding(
                "KDD-SIN-EVIDENCIA",
                f"La etapa '{etapa}' no tiene evidencia registrada todavía: no se puede cerrar",
            )
        ]

    entrada["estado"] = hacia
    entrada["actualizado_utc"] = ahora_utc()
    hist_entry = {"utc": ahora_utc(), "etapa": etapa, "desde": actual, "hacia": hacia}
    if motivo:
        hist_entry["motivo"] = motivo
    estado.setdefault("historial_transiciones", []).append(hist_entry)

    _escribir_estado(path, estado)
    return True, []


# --- Vínculo con el cierre de un cambio SDD -------------------------------------

def etapas_declaradas(control: dict) -> list:
    """Etapas que un cambio declara en `control["kdd"]` (`etapa_primaria` +
    `etapas_afectadas`, deduplicadas, en ese orden). Lista vacía si el cambio
    no declara ninguna -- caso normal para cambios sin decisión de lifecycle."""
    kdd_decl = control.get("kdd") or {}
    etapas = []
    primaria = kdd_decl.get("etapa_primaria")
    if primaria:
        etapas.append(primaria)
    for e in kdd_decl.get("etapas_afectadas") or []:
        if e not in etapas:
            etapas.append(e)
    return etapas


def validar_antes_de_cerrar(repo_root: Path, control: dict) -> list:
    """Pre-chequeo estructural, corrido ANTES de escribir la transición SDD a
    `cerrada` (spec: "si el sync mecánico falla, el cierre no debe quedar
    silenciosamente inconsistente"). Si el cambio no declara ninguna etapa
    KDD, no hay nada que validar. Nunca escribe nada."""
    etapas = etapas_declaradas(control)
    if not etapas:
        return []
    path = state_path(repo_root)
    try:
        estado = leer_estado(path)
    except FileNotFoundError:
        return [
            Finding(
                "KDD-NO-INICIALIZADO",
                "El cambio declara etapa(s) KDD pero openspec/kdd/state.json no existe. "
                "Correr 'ds_guard kdd init' antes de cerrar.",
                str(path),
            )
        ]
    except KddEstadoError as e:
        return [Finding("KDD-ESTADO-CORRUPTO", str(e), str(path))]

    desconocidas = [e for e in etapas if e not in estado.get("etapas", {})]
    if desconocidas:
        return [
            Finding(
                "KDD-ETAPA-DESCONOCIDA",
                f"Etapa(s) KDD declaradas en control.json no reconocidas: {', '.join(desconocidas)}",
            )
        ]
    return []


def sync_al_cerrar(repo_root: Path, control: dict, change_id: str) -> dict:
    """Se invoca solo DESPUÉS de que la transición SDD a `cerrada` ya se
    escribió, y solo si `validar_antes_de_cerrar` no encontró nada. Agrega
    punteros/evidencia a `state.json` para cada etapa declarada -- nunca
    avanza `estado` de ninguna etapa. Idempotente: reintentar el sync del
    mismo `change_id` no duplica entradas."""
    etapas = etapas_declaradas(control)
    if not etapas:
        return {"sincronizado": False, "motivo": "el cambio no declara etapa_primaria ni etapas_afectadas"}

    path = state_path(repo_root)
    estado = leer_estado(path)

    modo = control.get("modo", "completo")
    if modo == "completo":
        artefacto = f"openspec/changes/{change_id}/verification.md"
    else:
        artefacto = f"openspec/changes/{change_id}/tasks.md#Verificación"

    ahora = ahora_utc()
    actualizadas = []
    for etapa in etapas:
        entrada = estado["etapas"].get(etapa)
        if entrada is None:
            continue
        cambios = entrada.setdefault("changes", [])
        if change_id not in cambios:
            cambios.append(change_id)
        evidencia = entrada.setdefault("evidencia", [])
        if not any(ev.get("change_id") == change_id for ev in evidencia):
            evidencia.append({"change_id": change_id, "artefacto": artefacto})
        entrada["actualizado_utc"] = ahora
        actualizadas.append(etapa)

    _escribir_estado(path, estado)
    return {"sincronizado": True, "etapas_actualizadas": actualizadas}
