"""Decision ledger del proyecto (`openspec/decisions/ledger.jsonl`), Bloque 5
(v0.2, `20260910-decision-ledger-bounded-remediation`).

Archivo JSONL global del proyecto (no por cambio), de eventos inmutables
(`registrar`/`supersede`/`revocar`). El estado (`activa`/`superseded`/
`revocada`) de un `decision_id` nunca se almacena: se deriva siempre
escaneando el archivo completo (`resolver_estados`), mismo criterio ya
aplicado a `tasks.md estado:` frente a `control["transiciones"]` (ver
`sdd.py`) y a `kdd.py` frente a `state.json`.

Lectura (`leer_entradas`) tolerante a corrupción de línea: una línea que no
parsea como JSON se reporta como hallazgo y se omite, sin abortar la lectura
de las demás. Escritura (`decision_add`/`decision_supersede`/
`decision_revoke`) fail-closed: si cualquier línea existente está corrupta,
no se agrega nada. Escritura siempre atómica: se lee el archivo completo, se
agrega la línea nueva, se escribe todo a un `.tmp` + `os.replace` (nunca un
`open(..., "a")` directo) -- mismo patrón que `core.escribir_texto_atomico`.

No conoce Git (usa rutas relativas a `repo_root`, resuelto por el llamador vía
`repo.py`), igual que `kdd.py`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from . import kdd
from .core import Finding, ahora_utc, escribir_texto_atomico

SCHEMA_VERSION_SOPORTADA = 1

TIPOS_DECISION = frozenset(
    {
        "target",
        "unidad_de_analisis",
        "cutoff",
        "split_strategy",
        "metrica_primaria",
        "baseline",
        "feature_decision",
        "model_decision",
        "threshold",
        "criterio_metodologico",
        "produccion",
        "excepcion_metodologica",
    }
)

ACCIONES = frozenset({"registrar", "supersede", "revocar"})


class LedgerError(Exception):
    """Fail-closed en escritura del ledger -- mismo espíritu que
    `kdd.KddEstadoError`: nunca se repara ni se sobreescribe automáticamente,
    se propaga para que el llamador decida."""


def ledger_path(repo_root: Path) -> Path:
    return Path(repo_root) / "openspec" / "decisions" / "ledger.jsonl"


# --- Lectura tolerante --------------------------------------------------------

def leer_entradas(path: Path) -> tuple:
    """(entradas, findings). Si el archivo no existe, `([], [])` -- caso
    normal ("el ledger todavía no nació"), no un error. Si existe, parsea
    línea por línea (ignorando líneas vacías); cada línea inválida agrega un
    `Finding("DECISION-LINEA-CORRUPTA", ...)` y se omite del resultado. Las
    entradas válidas se devuelven en orden de aparición, con su `seq` tal
    cual está guardado (nunca recalculado acá)."""
    path = Path(path)
    if not path.exists():
        return [], []
    entradas = []
    findings = []
    with open(path, "r", encoding="utf-8") as f:
        for numero_linea, linea in enumerate(f, start=1):
            if not linea.strip():
                continue
            try:
                entrada = json.loads(linea)
            except json.JSONDecodeError as e:
                findings.append(
                    Finding(
                        "DECISION-LINEA-CORRUPTA",
                        f"Línea {numero_linea} no es JSON válido: {e}",
                        str(path),
                    )
                )
                continue
            entradas.append(entrada)
    return entradas, findings


def _todas_las_lineas_validas(path: Path) -> tuple:
    """(ok, findings). Usado antes de escribir: reusa `leer_entradas` pero
    exige cero corruptas para devolver `ok=True`."""
    entradas, findings = leer_entradas(path)
    if findings:
        return False, findings
    return True, []


# --- Validaciones compartidas --------------------------------------------------

def _campos_vacios(campos: dict) -> list:
    faltantes = [nombre for nombre, valor in campos.items() if not valor]
    if not faltantes:
        return []
    return [
        Finding(
            "DECISION-CAMPO-VACIO",
            f"Campo(s) obligatorio(s) vacío(s) o ausente(s): {', '.join(faltantes)}",
        )
    ]


def _decision_id_existe(entradas: list, decision_id: str) -> bool:
    return any(
        e.get("accion") in ("registrar", "supersede") and e.get("decision_id") == decision_id
        for e in entradas
    )


def _referencia_valida(entradas: list, referencia: str) -> bool:
    return any(
        e.get("accion") in ("registrar", "supersede") and e.get("decision_id") == referencia
        for e in entradas
    )


def _escribir_entradas(path: Path, entradas: list) -> None:
    lineas = [json.dumps(e, ensure_ascii=False) for e in entradas]
    texto = "\n".join(lineas) + "\n" if lineas else ""
    escribir_texto_atomico(path, texto)


# --- add -----------------------------------------------------------------

def decision_add(
    repo_root: Path,
    decision_id: str,
    tipo: str,
    resumen: str,
    rationale: str,
    usuario: str,
    fecha: str,
    cita: str,
    change_id: Optional[str] = None,
    kdd_etapa: Optional[str] = None,
    evidencia: Optional[list] = None,
    registrado_por: str = "lead",
) -> tuple:
    findings = []
    findings += _campos_vacios(
        {
            "decision_id": decision_id,
            "tipo": tipo,
            "resumen": resumen,
            "rationale": rationale,
            "usuario": usuario,
            "fecha": fecha,
            "cita": cita,
        }
    )
    if tipo and tipo not in TIPOS_DECISION:
        findings.append(Finding("DECISION-TIPO-INVALIDO", f"Tipo de decisión desconocido: {tipo}"))
    if kdd_etapa is not None and kdd_etapa not in kdd.ETAPAS:
        findings.append(Finding("KDD-ETAPA-DESCONOCIDA", f"Etapa KDD desconocida: {kdd_etapa}"))
    if findings:
        return False, findings

    path = ledger_path(repo_root)
    entradas, findings_lectura = leer_entradas(path)
    if findings_lectura:
        return False, [
            Finding(
                "DECISION-LEDGER-CORRUPTO",
                "El ledger tiene línea(s) corrupta(s); no se escribe nada hasta resolverlo.",
                str(path),
            )
        ]

    if _decision_id_existe(entradas, decision_id):
        return False, [
            Finding("DECISION-ID-DUPLICADO", f"decision_id ya usado en el ledger: {decision_id}")
        ]

    entrada = {
        "schema_version": SCHEMA_VERSION_SOPORTADA,
        "seq": len(entradas),
        "decision_id": decision_id,
        "utc": ahora_utc(),
        "accion": "registrar",
        "referencia": None,
        "tipo": tipo,
        "resumen": resumen,
        "rationale": rationale,
        "change_id": change_id,
        "kdd_etapa": kdd_etapa,
        "evidencia": list(evidencia or []),
        "aprobado_por": usuario,
        "fecha_aprobacion": fecha,
        "cita": cita,
        "registrado_por": registrado_por,
    }
    entradas.append(entrada)
    _escribir_entradas(path, entradas)
    return True, []


# --- supersede -------------------------------------------------------------

def decision_supersede(
    repo_root: Path,
    referencia: str,
    decision_id: str,
    tipo: str,
    resumen: str,
    rationale: str,
    usuario: str,
    fecha: str,
    cita: str,
    change_id: Optional[str] = None,
    kdd_etapa: Optional[str] = None,
    evidencia: Optional[list] = None,
    registrado_por: str = "lead",
) -> tuple:
    findings = []
    findings += _campos_vacios(
        {
            "referencia": referencia,
            "decision_id": decision_id,
            "tipo": tipo,
            "resumen": resumen,
            "rationale": rationale,
            "usuario": usuario,
            "fecha": fecha,
            "cita": cita,
        }
    )
    if tipo and tipo not in TIPOS_DECISION:
        findings.append(Finding("DECISION-TIPO-INVALIDO", f"Tipo de decisión desconocido: {tipo}"))
    if kdd_etapa is not None and kdd_etapa not in kdd.ETAPAS:
        findings.append(Finding("KDD-ETAPA-DESCONOCIDA", f"Etapa KDD desconocida: {kdd_etapa}"))
    if findings:
        return False, findings

    path = ledger_path(repo_root)
    entradas, findings_lectura = leer_entradas(path)
    if findings_lectura:
        return False, [
            Finding(
                "DECISION-LEDGER-CORRUPTO",
                "El ledger tiene línea(s) corrupta(s); no se escribe nada hasta resolverlo.",
                str(path),
            )
        ]

    if _decision_id_existe(entradas, decision_id):
        return False, [
            Finding("DECISION-ID-DUPLICADO", f"decision_id ya usado en el ledger: {decision_id}")
        ]

    if not _referencia_valida(entradas, referencia):
        return False, [
            Finding(
                "DECISION-REFERENCIA-INVALIDA",
                f"referencia no existe en el ledger como decisión registrada/supersedida: {referencia}",
            )
        ]

    entrada = {
        "schema_version": SCHEMA_VERSION_SOPORTADA,
        "seq": len(entradas),
        "decision_id": decision_id,
        "utc": ahora_utc(),
        "accion": "supersede",
        "referencia": referencia,
        "tipo": tipo,
        "resumen": resumen,
        "rationale": rationale,
        "change_id": change_id,
        "kdd_etapa": kdd_etapa,
        "evidencia": list(evidencia or []),
        "aprobado_por": usuario,
        "fecha_aprobacion": fecha,
        "cita": cita,
        "registrado_por": registrado_por,
    }
    entradas.append(entrada)
    _escribir_entradas(path, entradas)
    return True, []


# --- revoke ------------------------------------------------------------------

def decision_revoke(
    repo_root: Path,
    referencia: str,
    motivo: str,
    usuario: str,
    fecha: str,
    registrado_por: str = "lead",
) -> tuple:
    findings = _campos_vacios(
        {"referencia": referencia, "motivo": motivo, "usuario": usuario, "fecha": fecha}
    )
    if findings:
        return False, findings

    path = ledger_path(repo_root)
    entradas, findings_lectura = leer_entradas(path)
    if findings_lectura:
        return False, [
            Finding(
                "DECISION-LEDGER-CORRUPTO",
                "El ledger tiene línea(s) corrupta(s); no se escribe nada hasta resolverlo.",
                str(path),
            )
        ]

    if not _referencia_valida(entradas, referencia):
        return False, [
            Finding(
                "DECISION-REFERENCIA-INVALIDA",
                f"referencia no existe en el ledger como decisión registrada/supersedida: {referencia}",
            )
        ]

    entrada = {
        "schema_version": SCHEMA_VERSION_SOPORTADA,
        "seq": len(entradas),
        "decision_id": None,
        "utc": ahora_utc(),
        "accion": "revocar",
        "referencia": referencia,
        "motivo": motivo,
        "aprobado_por": usuario,
        "fecha_aprobacion": fecha,
        "registrado_por": registrado_por,
    }
    entradas.append(entrada)
    _escribir_entradas(path, entradas)
    return True, []


# --- Estado derivado -----------------------------------------------------------

def resolver_estados(entradas: list) -> dict:
    """`{decision_id: {"estado": ..., "superseded_por": ..., "revocado_por_seq": ...}}`
    para cada `decision_id` visto en una entrada `registrar`/`supersede`.
    Precedencia: revocada > superseded > activa (R6). Escanea todas las
    entradas (no solo las posteriores por índice), por robustez ante ledgers
    reordenados manualmente -- nunca debería pasar en el flujo normal
    (append-only), pero no se asume."""
    estados: dict = {}
    for entrada in entradas:
        if entrada.get("accion") in ("registrar", "supersede"):
            decision_id = entrada.get("decision_id")
            if decision_id is not None and decision_id not in estados:
                estados[decision_id] = {
                    "estado": "activa",
                    "superseded_por": None,
                    "revocado_por_seq": None,
                }

    for entrada in entradas:
        if entrada.get("accion") == "supersede":
            referencia = entrada.get("referencia")
            if referencia in estados:
                estados[referencia]["superseded_por"] = entrada.get("decision_id")

    for entrada in entradas:
        if entrada.get("accion") == "revocar":
            referencia = entrada.get("referencia")
            if referencia in estados:
                estados[referencia]["revocado_por_seq"] = entrada.get("seq")

    for decision_id, info in estados.items():
        if info["revocado_por_seq"] is not None:
            info["estado"] = "revocada"
        elif info["superseded_por"] is not None:
            info["estado"] = "superseded"
        else:
            info["estado"] = "activa"

    return estados


# --- list / show ---------------------------------------------------------------

def decision_list(
    repo_root: Path,
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    change_id: Optional[str] = None,
) -> tuple:
    path = ledger_path(repo_root)
    entradas, findings = leer_entradas(path)
    estados = resolver_estados(entradas)

    resultado = []
    for entrada in entradas:
        if entrada.get("accion") not in ("registrar", "supersede"):
            continue
        decision_id = entrada.get("decision_id")
        info_estado = estados.get(decision_id, {})
        if tipo is not None and entrada.get("tipo") != tipo:
            continue
        if estado is not None and info_estado.get("estado") != estado:
            continue
        if change_id is not None and entrada.get("change_id") != change_id:
            continue
        salida = dict(entrada)
        salida["estado"] = info_estado.get("estado", "activa")
        resultado.append(salida)

    return resultado, findings


def decision_show(repo_root: Path, decision_id: str) -> tuple:
    path = ledger_path(repo_root)
    entradas, findings = leer_entradas(path)
    estados = resolver_estados(entradas)

    entrada_encontrada = None
    for entrada in entradas:
        if entrada.get("accion") in ("registrar", "supersede") and entrada.get("decision_id") == decision_id:
            entrada_encontrada = entrada  # la última (registrar o supersede) con ese id -- solo puede haber una

    if entrada_encontrada is None:
        return None, findings + [
            Finding("DECISION-ID-INEXISTENTE", f"decision_id inexistente en el ledger: {decision_id}")
        ]

    info_estado = estados.get(decision_id, {"estado": "activa", "superseded_por": None, "revocado_por_seq": None})
    salida = dict(entrada_encontrada)
    salida["estado"] = info_estado["estado"]
    salida["superseded_por"] = info_estado["superseded_por"]

    detalle = None
    if info_estado["estado"] == "revocada":
        for entrada in entradas:
            if entrada.get("accion") == "revocar" and entrada.get("referencia") == decision_id:
                detalle = {
                    "accion": "revocar",
                    "motivo": entrada.get("motivo"),
                    "aprobado_por": entrada.get("aprobado_por"),
                    "fecha_aprobacion": entrada.get("fecha_aprobacion"),
                }
    elif info_estado["estado"] == "superseded":
        for entrada in entradas:
            if entrada.get("accion") == "supersede" and entrada.get("referencia") == decision_id:
                detalle = {
                    "accion": "supersede",
                    "decision_id": entrada.get("decision_id"),
                    "resumen": entrada.get("resumen"),
                }
    salida["detalle_afectacion"] = detalle

    return salida, findings
