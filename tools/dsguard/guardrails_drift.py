"""Drift de `.claude/guardrails.json` contra la plantilla instalada (R25-R30).

Módulo puro: sin I/O, solo stdlib; NO importa `autonomy` (ni estática ni dinámicamente).
`comparar` ignora las rutas MUTABLES (`RUTAS_MUTABLES`: valores que el usuario edita
legítimamente para habilitar la autonomía); cualquier otra diferencia es drift. Que una
ruta sea mutable NO significa que su valor sea válido: `validar_autonomia_mutable` valida
esos valores usando `parse_autonomy_policy` INYECTADO por el llamador (doctor).

Sin afirmaciones de seguridad ni de aprobación: solo reporta diferencias y hallazgos.
"""
from __future__ import annotations

import json

# Rutas que no cuentan como drift (cerradas; ampliar requiere un Change).
RUTAS_MUTABLES = (
    "version",
    "autonomy.mode",
    "autonomy.version",
    "autonomy.budgets",
    "autonomy.limits",
)

_CLAVE_AUTONOMY = "autonomy"
# Derivadas de `RUTAS_MUTABLES` (la tupla gobierna el comportamiento).
_PREFIJO_AUTONOMY = _CLAVE_AUTONOMY + "."
_CLAVES_TOP_MUTABLES = tuple(r for r in RUTAS_MUTABLES if "." not in r)
_CLAVES_AUTONOMY_MUTABLES = tuple(
    r[len(_PREFIJO_AUTONOMY):] for r in RUTAS_MUTABLES if r.startswith(_PREFIJO_AUTONOMY)
)

NIVEL_ERROR = "error"
NIVEL_WARN = "warn"

CODE_INVALID = "AUTONOMY-POLICY-INVALID"
CODE_LIMITS = "AUTONOMY-POLICY-LIMITS"
CODE_UNKNOWN_KEY = "AUTONOMY-POLICY-UNKNOWN-KEY"
CODE_UNAVAILABLE = "AUTONOMY-POLICY-UNAVAILABLE"

# Claves conocidas de `autonomy.budgets` / `autonomy.limits` (R29).
CLAVES_BUDGETS = (
    "session_minutes",
    "aggregate_minutes",
    "max_sessions",
    "max_concurrent_subagents",
    "remediation_max_intentos_default",
)
CLAVES_LIMITS = ("max_sessions", "max_total_minutes")


def normalizar(guardrails: dict) -> dict:
    """Copia de `guardrails` sin las rutas mutables. `autonomy` se descarta si queda vacío."""
    if not isinstance(guardrails, dict):
        raise ValueError("guardrails no es un objeto JSON (dict)")
    resultado = {k: v for k, v in guardrails.items() if k not in _CLAVES_TOP_MUTABLES}
    autonomia = resultado.get(_CLAVE_AUTONOMY)
    if isinstance(autonomia, dict):
        resto = {k: v for k, v in autonomia.items() if k not in _CLAVES_AUTONOMY_MUTABLES}
        if resto:
            resultado[_CLAVE_AUTONOMY] = resto
        else:
            del resultado[_CLAVE_AUTONOMY]
    return resultado


def _canon(valor) -> str:
    """Forma canónica comparable; distingue `true` de `1` (a diferencia de `==`)."""
    try:
        return json.dumps(valor, sort_keys=True, ensure_ascii=True)
    except (TypeError, ValueError):
        return repr(valor)


def comparar(actual: dict, baseline: dict) -> list:
    """Rutas que difieren tras normalizar (`[]` = sin drift).

    Rutas de primer nivel; para `autonomy` (ambos objetos) se informan sus claves
    (`autonomy.<clave>`). Entradas que no son dict: `ValueError` (el llamador es fail-closed).
    """
    a = normalizar(actual)
    b = normalizar(baseline)
    rutas = []
    for clave in sorted(set(a) | set(b), key=str):
        en_a, en_b = clave in a, clave in b
        if en_a and en_b and _canon(a[clave]) == _canon(b[clave]):
            continue
        if (
            clave == _CLAVE_AUTONOMY
            and isinstance(a.get(clave, {}), dict)
            and isinstance(b.get(clave, {}), dict)
        ):
            # Detalle por sub-clave aun si la plantilla no trae `autonomy` (baseline = {}).
            sub_a, sub_b = a.get(clave, {}), b.get(clave, {})
            for sub in sorted(set(sub_a) | set(sub_b), key=str):
                if sub in sub_a and sub in sub_b and _canon(sub_a[sub]) == _canon(sub_b[sub]):
                    continue
                rutas.append("%s.%s" % (clave, sub))
            continue
        rutas.append(str(clave))
    return rutas


def _hallazgo(code: str, path: str, detail: str, nivel: str) -> dict:
    return {"code": code, "path": path, "detail": detail, "nivel": nivel}


def _es_entero_positivo(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor > 0


def validar_autonomia_mutable(guardrails, guard_policy_version_max, parse_policy=None) -> list:
    """Valida los valores de las rutas mutables. Devuelve lista de dicts
    `{code, path, detail, nivel}`; `[]` si no hay sección `autonomy` o es válida.

    `parse_policy` es el callable `parse_autonomy_policy` INYECTADO por el llamador (este
    módulo no importa `autonomy`). Con sección `autonomy` y sin `parse_policy`: hallazgo
    error `AUTONOMY-POLICY-UNAVAILABLE` (fail-closed).

    Nivel `error`: valores inválidos o requisitos insatisfechos de `mode: autonomous`.
    Nivel `warn`: claves desconocidas.
    """
    return evaluar_autonomia(guardrails, guard_policy_version_max, parse_policy)[0]


def evaluar_autonomia(guardrails, guard_policy_version_max, parse_policy=None) -> tuple:
    """Como `validar_autonomia_mutable` pero devuelve `(hallazgos, modo_efectivo)`; el modo
    sale de la policy parseada (`supervised` si no hay policy/sección o ante duda)."""
    if not isinstance(guardrails, dict):
        return [_hallazgo(CODE_INVALID, "", "not_a_dict", NIVEL_ERROR)], "supervised"
    if _CLAVE_AUTONOMY not in guardrails:
        return [], "supervised"
    if not callable(parse_policy):
        return [_hallazgo(CODE_UNAVAILABLE, _CLAVE_AUTONOMY, "policy_parser_not_provided", NIVEL_ERROR)], "supervised"

    hallazgos = []
    vistos = set()

    def _agregar(code, path, detail, nivel):
        if path in vistos:
            return
        vistos.add(path)
        hallazgos.append(_hallazgo(code, path, detail, nivel))

    try:
        politica, de_policy = parse_policy(guardrails, guard_policy_version_max)
        modo = getattr(politica, "mode", "supervised")
        if modo not in ("supervised", "autonomous"):
            modo = "supervised"
    except Exception:
        return [_hallazgo(CODE_INVALID, _CLAVE_AUTONOMY, "unexpected_input", NIVEL_ERROR)], "supervised"
    for h in de_policy:
        nivel = NIVEL_WARN if h.code == CODE_UNKNOWN_KEY else NIVEL_ERROR
        _agregar(h.code, h.path, h.detail_key, nivel)

    autonomia = guardrails.get(_CLAVE_AUTONOMY)
    if isinstance(autonomia, dict):
        if "budgets" in autonomia:
            budgets = autonomia["budgets"]
            if not isinstance(budgets, dict):
                _agregar(CODE_LIMITS, "budgets", "not_a_dict", NIVEL_ERROR)
            else:
                for clave in CLAVES_BUDGETS:
                    if clave in budgets and not _es_entero_positivo(budgets[clave]):
                        _agregar(CODE_LIMITS, "budgets.%s" % clave, "not_positive_int", NIVEL_ERROR)
                for clave in sorted((k for k in budgets if k not in CLAVES_BUDGETS), key=str):
                    _agregar(CODE_UNKNOWN_KEY, "budgets.%s" % clave, "unknown_key", NIVEL_WARN)
        if "limits" in autonomia:
            limites = autonomia["limits"]
            if not isinstance(limites, dict):
                _agregar(CODE_INVALID, "limits", "not_a_dict", NIVEL_ERROR)
            else:
                for clave in sorted((k for k in limites if k not in CLAVES_LIMITS), key=str):
                    _agregar(CODE_UNKNOWN_KEY, "limits.%s" % clave, "unknown_key", NIVEL_WARN)
    return hallazgos, modo
