"""Observabilidad de eficiencia de agentes (v0.4 Change 4:
20260916-agent-efficiency-and-token-governance): agrega señales que YA
EXISTEN en `control.json` (sesiones/remediaciones) para revisión
retrospectiva -- no inventa un mecanismo de captura nuevo (ver
`design`/`proposal.md` del change: poblar automáticamente el campo
`subagentes` de sesión, hoy muerto, requeriría un hook nuevo, fuera de
alcance).

Reusa `sdd.chequear_limites` TAL CUAL para sesiones -- no reimplementa el
cálculo de límites. Estrictamente de solo lectura: nunca llama
`session_note`/`remediation_note`/`remediation_resolve`/`remediation_extend`/
`escribir_control`/`session_start`/`session_close`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import checks, core, sdd

CODIGO_SESION_LIMITE = "EFICIENCIA-SESION-LIMITE"
CODIGO_SESION_DELEGACIONES = "EFICIENCIA-SESION-DELEGACIONES"
CODIGO_REMEDIACION_INTENTOS = "EFICIENCIA-REMEDIACION-INTENTOS"
CODIGO_REMEDIACION_REPETIDA = "EFICIENCIA-REMEDIACION-REPETIDA"


def evaluar_sesion(sesion: dict) -> list:
    """CheckResult(s) para UNA sesión (activa o cerrada). Reusa
    `sdd.chequear_limites(sesion)` tal cual -- un CheckResult WARN por cada
    Finding que devuelva (mismo mensaje reusado tal cual), o un único PASS
    si `chequear_limites` no devuelve nada."""
    sesion_id = sesion.get("id", "?")
    findings = sdd.chequear_limites(sesion)
    if not findings:
        return [checks.CheckResult(
            checks.STATUS_PASS, CODIGO_SESION_LIMITE,
            f"Sesión {sesion_id} dentro de todos los límites declarados.", subject=sesion_id,
        )]
    return [
        checks.CheckResult(checks.STATUS_WARN, CODIGO_SESION_LIMITE, f.mensaje, subject=sesion_id)
        for f in findings
    ]


def evaluar_delegaciones_sesion(sesion: dict) -> list:
    """N/A si la sesión no declara `max_roles` en su presupuesto. WARN si
    `len(roles) >= max_roles` declarado. PASS si no."""
    sesion_id = sesion.get("id", "?")
    max_roles = sesion.get("presupuesto", {}).get("max_roles")
    if max_roles is None:
        return [checks.CheckResult(
            checks.STATUS_NA, CODIGO_SESION_DELEGACIONES,
            f"Sesión {sesion_id} no declara 'max_roles' en su presupuesto.", subject=sesion_id,
        )]
    roles = sesion.get("roles", []) or []
    if len(roles) >= max_roles:
        return [checks.CheckResult(
            checks.STATUS_WARN, CODIGO_SESION_DELEGACIONES,
            f"Sesión {sesion_id} usó {len(roles)} rol(es) distintos ({', '.join(roles)}), "
            f"en o sobre su máximo declarado ({max_roles}).", subject=sesion_id,
        )]
    return [checks.CheckResult(
        checks.STATUS_PASS, CODIGO_SESION_DELEGACIONES,
        f"Sesión {sesion_id}: {len(roles)}/{max_roles} roles usados.", subject=sesion_id,
    )]


def evaluar_remediacion(remediacion: dict) -> list:
    """N/A si no hay ventanas registradas. WARN (`CODIGO_REMEDIACION_INTENTOS`)
    si la ventana vigente agotó sus intentos. WARN adicional
    (`CODIGO_REMEDIACION_REPETIDA`) si hay >=2 intentos en la ventana vigente
    y TODOS declaran exactamente la misma 'causa' (comparación de string
    exacta, determinista -- nunca similitud difusa ni juicio semántico).
    Devuelve PASS único si ninguna señal aplica."""
    rid = remediacion.get("remediation_id", "?")
    ventanas = remediacion.get("ventanas", [])
    if not ventanas:
        return [checks.CheckResult(
            checks.STATUS_NA, CODIGO_REMEDIACION_INTENTOS,
            f"Remediación {rid} sin ventanas registradas.", subject=rid,
        )]
    ventana_vigente = ventanas[-1]
    intentos = ventana_vigente.get("intentos", []) or []
    max_intentos = ventana_vigente.get("max_intentos", 2)

    resultados = []
    if len(intentos) >= max_intentos:
        resultados.append(checks.CheckResult(
            checks.STATUS_WARN, CODIGO_REMEDIACION_INTENTOS,
            f"Remediación {rid} agotó los {max_intentos} intentos de su ventana "
            f"{ventana_vigente.get('ventana')} vigente.", subject=rid,
        ))

    causas = [i.get("causa") for i in intentos if i.get("causa")]
    if len(causas) >= 2 and len(set(causas)) == 1:
        resultados.append(checks.CheckResult(
            checks.STATUS_WARN, CODIGO_REMEDIACION_REPETIDA,
            f"Remediación {rid}: {len(causas)} intento(s) con la misma 'causa' declarada "
            "textualmente (no necesariamente consecutivos) -- posible reintento sin variación "
            "real (el juicio semántico de si es genuinamente repetitivo sigue siendo del Lead).",
            subject=rid,
        ))

    if not resultados:
        resultados.append(checks.CheckResult(
            checks.STATUS_PASS, CODIGO_REMEDIACION_INTENTOS,
            f"Remediación {rid} sin señales de ineficiencia detectadas.", subject=rid,
        ))
    return resultados


def _ruta_control(repo_root: Path, change_id: str) -> Optional[Path]:
    """`openspec/changes/<id>/control.json` si existe; si no,
    `openspec/archive/<id>/control.json` si existe; si ninguno, `None` (el
    llamador lo traduce a `technical_error`)."""
    candidatos = (
        Path(repo_root) / "openspec" / "changes" / change_id / "control.json",
        Path(repo_root) / "openspec" / "archive" / change_id / "control.json",
    )
    for c in candidatos:
        if c.exists():
            return c
    return None


def evaluar_eficiencia_change(repo_root, change_id: str) -> list:
    """Orquestador: lee `control.json` (`changes/` o `archive/`), evalúa CADA
    sesión (todas, activa o cerrada) con `evaluar_sesion` +
    `evaluar_delegaciones_sesion`, y CADA remediación con
    `evaluar_remediacion`. Nunca lanza -- `control.json` ausente/corrupto: un
    único CheckResult FAIL `kind=technical_error`. Sin sesiones/remediaciones:
    listas vacías, sin resultados de esa categoría (no es un error, un change
    puede no tener remediaciones todavía)."""
    repo_root = Path(repo_root)
    ruta = _ruta_control(repo_root, change_id)
    if ruta is None:
        return [checks.CheckResult(
            checks.STATUS_FAIL, "EFICIENCIA-CONTROL-AUSENTE",
            f"No existe control.json para el change '{change_id}' en "
            f"openspec/changes/{change_id}/ ni openspec/archive/{change_id}/.",
            kind=checks.KIND_TECHNICAL_ERROR,
        )]
    try:
        control = core.leer_control(ruta)
    except core.ControlJsonError as exc:
        return [checks.CheckResult(
            checks.STATUS_FAIL, "EFICIENCIA-CONTROL-INVALIDO",
            f"{ruta} existe pero no es válido: {exc}", kind=checks.KIND_TECHNICAL_ERROR,
        )]

    resultados = []
    for sesion in control.get("sesiones", []) or []:
        resultados.extend(evaluar_sesion(sesion))
        resultados.extend(evaluar_delegaciones_sesion(sesion))
    for remediacion in control.get("remediaciones", []) or []:
        resultados.extend(evaluar_remediacion(remediacion))
    return resultados
