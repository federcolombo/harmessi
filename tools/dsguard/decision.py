"""Decision ledger del proyecto (`openspec/decisions/ledger.jsonl`), Bloque 5
(v0.2, `20260910-decision-ledger-bounded-remediation`) y correcciones append-only
(v0.11, `20261016-v011-decision-ledger-corrections`).

Archivo JSONL global del proyecto (no por cambio), de eventos inmutables
(`registrar`/`supersede`/`revocar`/`corregir`). El estado (`activa`/
`superseded`/`revocada`) de un `decision_id` nunca se almacena: se deriva
siempre escaneando el archivo completo (`resolver_estados`), mismo criterio ya
aplicado a `tasks.md estado:` frente a `control["transiciones"]` (ver
`sdd.py`) y a `kdd.py` frente a `state.json`. Los valores efectivos de una
decisión corregida (`efectivo`) también se derivan: la entrada original nunca
se reescribe y cada `corregir` conserva `valores_previos`.

Lectura (`leer_entradas`) tolerante a corrupción de línea: una línea que no
parsea como JSON se reporta como hallazgo y se omite, sin abortar la lectura
de las demás. Escritura (`decision_add`/`decision_supersede`/
`decision_revoke`/`decision_correct`) fail-closed: si hay líneas corruptas o
hallazgos de integridad (`verificar_integridad`) no se agrega nada. La
escritura es append que preserva los bytes previos (se lee el texto crudo, se
agrega la línea nueva y se escribe todo de forma atómica con
`core.escribir_texto_atomico`; las líneas existentes no se reserializan).

Integridad (R5/R6): las entradas nuevas llevan `prev_hash` = sha256 hex de la
línea anterior exacta (sin terminador). Es tamper-evidence contra edición
manual ingenua, NO autenticidad: quien recalcule la cadena no es detectado, y
la modificación de la última línea o su borrado tampoco (no hay entrada
posterior que la referencie).

No conoce Git (usa rutas relativas a `repo_root`, resuelto por el llamador vía
`repo.py`), igual que `kdd.py`.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from . import kdd
from .core import Finding, ahora_utc, escribir_texto_atomico

# Versión con la que se escriben las entradas nuevas; se leen la 1 (v0.10, sin
# `prev_hash`) y la 2 (con `prev_hash` obligatorio).
SCHEMA_VERSION_SOPORTADA = 2

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

ACCIONES = frozenset({"registrar", "supersede", "revocar", "corregir"})

# Lista cerrada de campos corregibles (R2). `tipo`, `decision_id` y las
# relaciones se cambian con supersede/revocar, no con corregir.
CAMPOS_CORREGIBLES = (
    "resumen",
    "rationale",
    "cita",
    "evidencia",
    "change_id",
    "kdd_etapa",
)


class LedgerError(Exception):
    """Fail-closed en escritura del ledger -- mismo espíritu que
    `kdd.KddEstadoError`: nunca se repara ni se sobreescribe automáticamente,
    se propaga para que el llamador decida."""


def ledger_path(repo_root: Path) -> Path:
    return Path(repo_root) / "openspec" / "decisions" / "ledger.jsonl"


def _resolver_ruta(ruta) -> Path:
    """Acepta la ruta del `.jsonl` o el `repo_root` (se resuelve al ledger)."""
    ruta = Path(ruta)
    if ruta.suffix == ".jsonl":
        return ruta
    return ledger_path(ruta)


def hash_linea(linea: str) -> str:
    """sha256 hex de una línea del ledger sin su terminador (`\\r\\n`/`\\n`)."""
    return hashlib.sha256(linea.rstrip("\r\n").encode("utf-8")).hexdigest()


# --- Lectura cruda ---------------------------------------------------------------

def _cargar(path: Path) -> tuple:
    """`(texto, registros, findings)`. `texto` es el contenido crudo (sin
    traducir saltos de línea) o `None` si el archivo no existe. Cada registro
    es `{"numero", "linea", "entrada"}` con `entrada=None` si la línea no es un
    objeto JSON válido (se reporta `DECISION-LINEA-CORRUPTA`)."""
    path = Path(path)
    if not path.exists():
        return None, [], []
    try:
        texto = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as e:
        return "", [], [
            Finding("DECISION-LINEA-CORRUPTA", "El ledger no es UTF-8 válido: " + str(e), str(path))
        ]

    registros = []
    findings = []
    for numero, cruda in enumerate(texto.split("\n"), start=1):
        linea = cruda[:-1] if cruda.endswith("\r") else cruda
        if not linea.strip():
            continue
        entrada = None
        try:
            parseada = json.loads(linea)
            if isinstance(parseada, dict):
                entrada = parseada
            else:
                findings.append(
                    Finding(
                        "DECISION-LINEA-CORRUPTA",
                        "Línea " + str(numero) + " no es un objeto JSON.",
                        str(path),
                    )
                )
        except json.JSONDecodeError as e:
            findings.append(
                Finding(
                    "DECISION-LINEA-CORRUPTA",
                    "Línea " + str(numero) + " no es JSON válido: " + str(e),
                    str(path),
                )
            )
        registros.append({"numero": numero, "linea": linea, "entrada": entrada})
    return texto, registros, findings


def leer_entradas(path: Path) -> tuple:
    """(entradas, findings). Si el archivo no existe, `([], [])` -- caso
    normal ("el ledger todavía no nació"), no un error. Si existe, parsea
    línea por línea (ignorando líneas vacías); cada línea inválida agrega un
    `Finding("DECISION-LINEA-CORRUPTA", ...)` y se omite del resultado. Las
    entradas válidas se devuelven en orden de aparición, con su `seq` tal
    cual está guardado (nunca recalculado acá)."""
    _, registros, findings = _cargar(Path(path))
    entradas = [r["entrada"] for r in registros if r["entrada"] is not None]
    return entradas, findings


# --- Integridad (R5/R6) --------------------------------------------------------------

def _verificar_registros(registros: list, path: Path) -> list:
    """Hallazgos de integridad (sin las líneas corruptas, que reporta
    `_cargar`): continuidad de `seq`, ids duplicados, referencias colgantes y
    cadena de `prev_hash`."""
    findings = []
    definidos = set()
    for reg in registros:
        e = reg["entrada"]
        if e is not None and e.get("accion") in ("registrar", "supersede") and e.get("decision_id"):
            definidos.add(e.get("decision_id"))

    vistos = set()
    seq_esperado = 0
    cadena_activa = False
    linea_previa = None
    for reg in registros:
        entrada = reg["entrada"]
        ubicacion = str(path) + ":" + str(reg["numero"])
        if entrada is None:
            linea_previa = reg["linea"]
            continue

        seq = entrada.get("seq")
        es_entero = isinstance(seq, int) and not isinstance(seq, bool)
        if not es_entero or seq != seq_esperado:
            findings.append(
                Finding(
                    "DECISION-SEQ-ROTO",
                    "seq esperado " + str(seq_esperado) + ", encontrado " + repr(seq),
                    ubicacion,
                )
            )
        seq_esperado = (seq + 1) if es_entero else (seq_esperado + 1)

        accion = entrada.get("accion")
        decision_id = entrada.get("decision_id")
        if accion in ("registrar", "supersede") and decision_id:
            if decision_id in vistos:
                findings.append(
                    Finding("DECISION-ID-DUPLICADO", "decision_id repetido: " + str(decision_id), ubicacion)
                )
            vistos.add(decision_id)

        if accion in ("supersede", "revocar", "corregir"):
            referencia = entrada.get("referencia")
            if referencia not in definidos:
                findings.append(
                    Finding(
                        "DECISION-REFERENCIA-COLGANTE",
                        "referencia inexistente en el ledger: " + repr(referencia),
                        ubicacion,
                    )
                )

        if "prev_hash" in entrada:
            cadena_activa = True
            esperado = hash_linea(linea_previa) if linea_previa is not None else None
            if entrada.get("prev_hash") != esperado:
                findings.append(
                    Finding(
                        "DECISION-CADENA-ROTA",
                        "prev_hash no coincide con el hash de la línea anterior.",
                        ubicacion,
                    )
                )
        elif cadena_activa or (
            isinstance(entrada.get("schema_version"), int) and entrada.get("schema_version") >= 2
        ):
            findings.append(
                Finding(
                    "DECISION-CADENA-FALTANTE",
                    "entrada sin prev_hash (dentro de la cadena iniciada o con schema_version >= 2).",
                    ubicacion,
                )
            )
        linea_previa = reg["linea"]
    return findings


def verificar_integridad(ruta) -> list:
    """Solo lectura. Devuelve la lista de hallazgos (vacía si el ledger es
    íntegro o no existe): `DECISION-LINEA-CORRUPTA`, `DECISION-SEQ-ROTO`,
    `DECISION-ID-DUPLICADO`, `DECISION-REFERENCIA-COLGANTE`,
    `DECISION-CADENA-ROTA`, `DECISION-CADENA-FALTANTE`. `ruta` puede ser la
    ruta del `.jsonl` o el `repo_root`. Tamper-evidence, no autenticidad."""
    path = _resolver_ruta(ruta)
    _, registros, findings = _cargar(path)
    return findings + _verificar_registros(registros, path)


# --- Escritura append ---------------------------------------------------------------

def _abrir_para_escribir(repo_root: Path) -> tuple:
    """`(path, texto, registros, entradas, bloqueo)`. `bloqueo` no vacío =
    fail-closed (R7): corrupto -> `DECISION-LEDGER-CORRUPTO`, inconsistente ->
    `DECISION-LEDGER-INCONSISTENTE` (seguido del detalle)."""
    path = ledger_path(repo_root)
    texto, registros, f_lectura = _cargar(path)
    f_integridad = _verificar_registros(registros, path)
    entradas = [r["entrada"] for r in registros if r["entrada"] is not None]
    bloqueo = []
    if f_lectura:
        bloqueo = [
            Finding(
                "DECISION-LEDGER-CORRUPTO",
                "El ledger tiene línea(s) corrupta(s); no se escribe nada hasta resolverlo.",
                str(path),
            )
        ] + f_lectura + f_integridad
    elif f_integridad:
        bloqueo = [
            Finding(
                "DECISION-LEDGER-INCONSISTENTE",
                "El ledger tiene hallazgos de integridad; no se escribe nada hasta resolverlo.",
                str(path),
            )
        ] + f_integridad
    return path, texto, registros, entradas, bloqueo


def _armar_entrada(registros: list, entradas: list, campos: dict) -> dict:
    """Antepone `schema_version`, `seq` y `prev_hash` (hash de la última línea
    existente, o `None` si el ledger está vacío) a los `campos` de la acción."""
    entrada = {
        "schema_version": SCHEMA_VERSION_SOPORTADA,
        "seq": len(entradas),
        "prev_hash": hash_linea(registros[-1]["linea"]) if registros else None,
    }
    entrada.update(campos)
    return entrada


def _escribir_append(path: Path, texto: Optional[str], entrada: dict) -> None:
    """Agrega UNA línea preservando byte a byte el contenido previo."""
    base = texto or ""
    if base and not base.endswith("\n"):
        base += "\n"
    escribir_texto_atomico(path, base + json.dumps(entrada, ensure_ascii=False) + "\n")


# --- Validaciones compartidas --------------------------------------------------

def _campos_vacios(campos: dict) -> list:
    faltantes = [nombre for nombre, valor in campos.items() if not valor]
    if not faltantes:
        return []
    return [
        Finding(
            "DECISION-CAMPO-VACIO",
            "Campo(s) obligatorio(s) vacío(s) o ausente(s): " + ", ".join(faltantes),
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


def _finding_referencia_invalida(referencia: str) -> Finding:
    return Finding(
        "DECISION-REFERENCIA-INVALIDA",
        "referencia no existe en el ledger como decisión registrada/supersedida: " + str(referencia),
    )


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
        findings.append(Finding("DECISION-TIPO-INVALIDO", "Tipo de decisión desconocido: " + str(tipo)))
    if kdd_etapa is not None and kdd_etapa not in kdd.ETAPAS:
        findings.append(Finding("KDD-ETAPA-DESCONOCIDA", "Etapa KDD desconocida: " + str(kdd_etapa)))
    if findings:
        return False, findings

    path, texto, registros, entradas, bloqueo = _abrir_para_escribir(repo_root)
    if bloqueo:
        return False, bloqueo

    if _decision_id_existe(entradas, decision_id):
        return False, [
            Finding("DECISION-ID-DUPLICADO", "decision_id ya usado en el ledger: " + str(decision_id))
        ]

    entrada = _armar_entrada(
        registros,
        entradas,
        {
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
        },
    )
    _escribir_append(path, texto, entrada)
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
        findings.append(Finding("DECISION-TIPO-INVALIDO", "Tipo de decisión desconocido: " + str(tipo)))
    if kdd_etapa is not None and kdd_etapa not in kdd.ETAPAS:
        findings.append(Finding("KDD-ETAPA-DESCONOCIDA", "Etapa KDD desconocida: " + str(kdd_etapa)))
    if findings:
        return False, findings

    path, texto, registros, entradas, bloqueo = _abrir_para_escribir(repo_root)
    if bloqueo:
        return False, bloqueo

    if _decision_id_existe(entradas, decision_id):
        return False, [
            Finding("DECISION-ID-DUPLICADO", "decision_id ya usado en el ledger: " + str(decision_id))
        ]

    if not _referencia_valida(entradas, referencia):
        return False, [_finding_referencia_invalida(referencia)]

    entrada = _armar_entrada(
        registros,
        entradas,
        {
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
        },
    )
    _escribir_append(path, texto, entrada)
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

    path, texto, registros, entradas, bloqueo = _abrir_para_escribir(repo_root)
    if bloqueo:
        return False, bloqueo

    if not _referencia_valida(entradas, referencia):
        return False, [_finding_referencia_invalida(referencia)]

    entrada = _armar_entrada(
        registros,
        entradas,
        {
            "decision_id": None,
            "utc": ahora_utc(),
            "accion": "revocar",
            "referencia": referencia,
            "motivo": motivo,
            "aprobado_por": usuario,
            "fecha_aprobacion": fecha,
            "registrado_por": registrado_por,
        },
    )
    _escribir_append(path, texto, entrada)
    return True, []


# --- Valores efectivos (D4) ----------------------------------------------------

def _entrada_base(entradas: list, decision_id: str) -> Optional[dict]:
    for e in entradas:
        if e.get("accion") in ("registrar", "supersede") and e.get("decision_id") == decision_id:
            return e
    return None


def _correcciones_de(entradas: list, decision_id: str) -> list:
    """Entradas `corregir` de una decisión, en orden de `seq` (estable)."""
    correcciones = [
        e for e in entradas if e.get("accion") == "corregir" and e.get("referencia") == decision_id
    ]

    def _clave(e):
        seq = e.get("seq")
        return seq if isinstance(seq, int) and not isinstance(seq, bool) else 0

    return sorted(correcciones, key=_clave)


def _copiar_valor(valor):
    return list(valor) if isinstance(valor, list) else valor


def _calcular_efectivo(entrada_base: dict, correcciones: list) -> dict:
    """Campos corregibles originales sobrescritos por las correcciones en
    orden de `seq`: gana la última corrección por campo."""
    efectivo = {campo: _copiar_valor(entrada_base.get(campo)) for campo in CAMPOS_CORREGIBLES}
    for correccion in correcciones:
        campos = correccion.get("campos")
        if not isinstance(campos, dict):
            continue
        for campo, valor in campos.items():
            if campo in efectivo:
                efectivo[campo] = _copiar_valor(valor)
    return efectivo


# --- correct -----------------------------------------------------------------

def decision_correct(
    repo_root: Path,
    decision_id: str,
    campos: dict,
    motivo: str,
    usuario: str,
    fecha: str,
    registrado_por: str = "lead",
) -> tuple:
    """Agrega UNA entrada `corregir` sobre `decision_id` (R1-R4). `campos` es
    `{campo: nuevo_valor}` con campos de `CAMPOS_CORREGIBLES`; `evidencia` es
    una lista de punteros, el resto son strings no vacíos."""
    findings = _campos_vacios(
        {"decision_id": decision_id, "motivo": motivo, "usuario": usuario, "fecha": fecha}
    )
    if not isinstance(campos, dict) or not campos:
        findings.append(Finding("DECISION-CAMPO-VACIO", "Sin campos a corregir."))
        return False, findings

    nuevos = {}
    for campo, valor in campos.items():
        if campo not in CAMPOS_CORREGIBLES:
            findings.append(
                Finding(
                    "DECISION-CAMPO-NO-CORREGIBLE",
                    "Campo no corregible: " + str(campo) + " (permitidos: " + ", ".join(CAMPOS_CORREGIBLES) + ")",
                )
            )
            continue
        if campo == "evidencia":
            if (
                not isinstance(valor, (list, tuple))
                or not valor
                or any(not isinstance(p, str) or not p.strip() for p in valor)
            ):
                findings.append(
                    Finding("DECISION-CAMPO-VACIO", "evidencia debe ser una lista no vacía de punteros no vacíos.")
                )
                continue
            nuevos[campo] = list(valor)
            continue
        if not isinstance(valor, str) or not valor.strip():
            findings.append(Finding("DECISION-CAMPO-VACIO", "Valor vacío para el campo: " + str(campo)))
            continue
        if campo == "kdd_etapa" and valor not in kdd.ETAPAS:
            findings.append(Finding("KDD-ETAPA-DESCONOCIDA", "Etapa KDD desconocida: " + str(valor)))
            continue
        nuevos[campo] = valor
    if findings:
        return False, findings

    path, texto, registros, entradas, bloqueo = _abrir_para_escribir(repo_root)
    if bloqueo:
        return False, bloqueo

    base = _entrada_base(entradas, decision_id)
    if base is None:
        return False, [_finding_referencia_invalida(decision_id)]

    efectivo_actual = _calcular_efectivo(base, _correcciones_de(entradas, decision_id))
    valores_previos = {campo: efectivo_actual.get(campo) for campo in nuevos}
    if all(efectivo_actual.get(campo) == valor for campo, valor in nuevos.items()):
        return False, [
            Finding(
                "DECISION-CORRECCION-SIN-CAMBIO",
                "La corrección no cambia ningún valor efectivo de " + str(decision_id),
            )
        ]

    entrada = _armar_entrada(
        registros,
        entradas,
        {
            "decision_id": None,
            "utc": ahora_utc(),
            "accion": "corregir",
            "referencia": decision_id,
            "campos": nuevos,
            "valores_previos": valores_previos,
            "motivo": motivo,
            "aprobado_por": usuario,
            "fecha_aprobacion": fecha,
            "registrado_por": registrado_por,
        },
    )
    _escribir_append(path, texto, entrada)
    return True, []


# --- Estado derivado -----------------------------------------------------------

def resolver_estados(entradas: list) -> dict:
    """Mapa `decision_id -> info` con `estado`, `superseded_por` y `revocado_por_seq`
    para cada `decision_id` visto en una entrada `registrar`/`supersede`.
    Precedencia: revocada > superseded > activa (R6). Escanea todas las
    entradas (no solo las posteriores por índice), por robustez ante ledgers
    reordenados manualmente -- nunca debería pasar en el flujo normal
    (append-only), pero no se asume. Las entradas `corregir` no afectan el
    estado."""
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
        correcciones = _correcciones_de(entradas, decision_id)
        efectivo = _calcular_efectivo(entrada, correcciones)
        # El filtro usa el change_id EFECTIVO (puede haber sido corregido).
        if change_id is not None and efectivo.get("change_id") != change_id:
            continue
        salida = dict(entrada)
        salida["estado"] = info_estado.get("estado", "activa")
        salida["correcciones"] = [dict(c) for c in correcciones]
        salida["efectivo"] = efectivo
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
            Finding("DECISION-ID-INEXISTENTE", "decision_id inexistente en el ledger: " + str(decision_id))
        ]

    info_estado = estados.get(decision_id, {"estado": "activa", "superseded_por": None, "revocado_por_seq": None})
    salida = dict(entrada_encontrada)
    salida["estado"] = info_estado["estado"]
    salida["superseded_por"] = info_estado["superseded_por"]

    correcciones = _correcciones_de(entradas, decision_id)
    salida["correcciones"] = [dict(c) for c in correcciones]
    salida["efectivo"] = _calcular_efectivo(entrada_encontrada, correcciones)

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
