#!/usr/bin/env python
"""`ds_guard`: verificador determinista para el proceso SDD de este proyecto.

Sesión A: `status`, `validate`, `approve`, `transition`, `session
{start,note,status,close}`. Sesión B agrega `notebook-diff` y `archive`. Sesión
de corrección agrega `init` (scaffolding de un cambio nuevo desde plantillas).

Códigos de salida generales (ver spec.md):
    0 correcto
    1 gate/validación incumplida (incluye SESION-AUSENTE)
    2 error de uso/configuración
    3 error de entorno/git/herramienta

Solo biblioteca estándar. No instala ni importa nada fuera de `tools/dsguard`.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as importlib_metadata
import json
import sys
from pathlib import Path
from typing import NamedTuple, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import launcher_common  # noqa: E402 -- solo-stdlib, ya usado por los lanzadores de hooks (T3b-2, M11 dependency install: R27/R34).

# La consola/pipe que invoca este CLI puede estar en una codificación distinta
# de UTF-8 (p. ej. cp1252 en Windows). Forzamos stdout/stderr a UTF-8 real para
# que el texto en español (tildes, "ñ") y el JSON de salida sean deterministas
# sin importar quién lo invoque (terminal, subprocess de test, etc.).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dsguard import (  # noqa: E402
    checks,
    core,
    decision,
    efficiency,
    kdd,
    kdd_compat,
    lifecycle,
    maturity,
    mlops_evidence,
    mlops_foundations,
    notebooks,
    pathguard,
    readiness,
    repo,
    scientific_validity,
    scope,
    sdd,
    status,
)


# --- Helpers compartidos --------------------------------------------------

def _repo_root() -> Path:
    return repo.find_repo_root(Path.cwd())


def _change_dir(repo_root: Path, change_id: str) -> Path:
    return repo_root / "openspec" / "changes" / change_id


def _cargar_change(repo_root: Path, change_id: str):
    """Devuelve (change_dir, tasks_path, control_path, control) o levanta
    SystemExit con el código de error apropiado si algo no está en orden."""
    change_dir = _change_dir(repo_root, change_id)
    tasks_path = change_dir / "tasks.md"
    control_path = change_dir / "control.json"
    if not tasks_path.exists() or not control_path.exists():
        print(
            f"No existen tasks.md/control.json para el cambio '{change_id}' en {change_dir}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        control = core.leer_control(control_path)
    except core.ControlJsonError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(2)
    return change_dir, tasks_path, control_path, control


def _imprimir_findings(findings: list, exit_code: int, como_json: bool) -> None:
    if como_json:
        print(core.formatear_findings_json(findings, exit_code))
    else:
        print(core.formatear_findings_texto(findings))


# --- status -----------------------------------------------------------------

def _resumen_quality_evidence(repo_root: Path) -> dict:
    """Resumen de solo lectura de `.harmessi/quality/` (v0.7 Change 4:
    20260922-quality-integration-and-cli, R15 de spec.md): NUNCA vive en
    `tools/dsguard/status.py` (ver `design.md` decisión 4 del Change -- ese
    módulo está dentro del perímetro de neutralidad v0.7). Import perezoso de
    `tools.qualityevidence.evidence` DENTRO de esta función, mismo criterio
    que `_importar_dsimpact`. Un manifest corrupto/con hash inconsistente se
    reporta como entrada individual, nunca aborta el resumen completo. Nunca
    lanza una excepción no controlada."""
    qe_core = _importar_perezoso("qualityevidence", "core")
    qe_evidence = _importar_perezoso("qualityevidence", "evidence")
    if qe_core is None or qe_evidence is None:
        return {"disponible": False, "mensaje": "tools.qualityevidence no disponible en este stage"}

    directorio = Path(repo_root) / ".harmessi" / "quality"
    if not directorio.is_dir():
        return {"disponible": False, "mensaje": "sin evidencia de calidad todavía"}

    try:
        ids_evidencia = sorted(p.name for p in directorio.iterdir() if p.is_dir())
    except OSError:
        return {"disponible": False, "mensaje": "sin evidencia de calidad todavía"}

    entradas: list = []
    conteos = {"PASS": 0, "WARN": 0, "FAIL": 0, "N/A": 0}
    technical_errors = 0
    generated_at_mas_reciente = None
    for evidence_id in ids_evidencia:
        try:
            manifest = qe_evidence.read_manifest(repo_root, evidence_id)
        except qe_core.QualityEvidenceError as exc:
            entradas.append({"evidence_id": evidence_id, "valido": False, "motivo": str(exc)})
            continue
        except Exception as exc:  # noqa: BLE001 - nunca aborta el resumen completo
            entradas.append({"evidence_id": evidence_id, "valido": False, "motivo": str(exc)})
            continue
        for r in manifest.check_results:
            conteos[r["status"]] = conteos.get(r["status"], 0) + 1
        technical_errors += len(manifest.technical_errors)
        entradas.append({"evidence_id": evidence_id, "valido": True, "generated_at": manifest.generated_at})
        if generated_at_mas_reciente is None or manifest.generated_at > generated_at_mas_reciente:
            generated_at_mas_reciente = manifest.generated_at

    return {
        "disponible": True,
        "entradas": entradas,
        "conteos": conteos,
        "technical_errors": technical_errors,
        "generated_at_mas_reciente": generated_at_mas_reciente,
    }


def cmd_status_unificado(args: argparse.Namespace) -> int:
    """Rama nueva de `status` (sin `--change-id`, Change 8 v0.3:
    20260915-unified-status-surface): status unificado de proyecto, de solo
    lectura, vía `dsguard.status.evaluar_status`. Exit code 0 siempre (es
    informativo, nunca "falla" por contenido -- mismo criterio que `project
    status`/`mlops status`), salvo error de entorno real (p. ej. no estar en
    un repo Git, que sigue devolviendo 3, igual que la rama SDD).

    Extensión aditiva v0.7 Change 4 (`quality_evidence`, R15 de spec.md):
    calculada DESPUÉS de `status.evaluar_status`, sin modificarlo, agregada
    como clave nueva al final -- nunca reemplaza ni reordena las 8 claves
    existentes (R16: `evaluar_status` es idéntica antes y después de este
    Change)."""
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    resultado = status.evaluar_status(repo_root)
    quality_evidence = _resumen_quality_evidence(repo_root)
    if args.json:
        payload = status.formatear_json(resultado)
        payload["quality_evidence"] = quality_evidence
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(status.formatear_texto(resultado, verbose=args.verbose))
        print()
        print("Quality evidence (v0.7, informativo):")
        if not quality_evidence.get("disponible"):
            print(f"  {quality_evidence.get('mensaje')}")
        else:
            conteos = quality_evidence["conteos"]
            print(
                f"  {conteos['PASS']} PASS, {conteos['WARN']} WARN, {conteos['FAIL']} FAIL, "
                f"{conteos['N/A']} N/A (technical_errors={quality_evidence['technical_errors']})"
            )
            if quality_evidence.get("generated_at_mas_reciente"):
                print(f"  más reciente: {quality_evidence['generated_at_mas_reciente']}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    # Bifurcación (R1 de spec.md, Change 8 v0.3: 20260915-unified-status-surface):
    # sin --change-id -> nuevo status unificado de proyecto; con --change-id ->
    # comportamiento SDD EXACTO existente, sin ningún cambio de lógica debajo de
    # este punto (invariante dura: cualquier invocación con --change-id sigue
    # produciendo exactamente el mismo resultado que antes de este change).
    if not args.change_id:
        return cmd_status_unificado(args)

    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    estado, err = sdd.read_estado(tasks_path)

    discrepancia = None
    if estado is not None:
        transiciones = control.get("transiciones", [])
        if transiciones and transiciones[-1].get("hacia") != estado:
            discrepancia = (
                f"tasks.md dice '{estado}' pero la última transición registrada en "
                f"control.json dice '{transiciones[-1].get('hacia')}'"
            )

    sesion_activa = sdd._sesion_activa(control)
    sesion_info = sdd.session_status(control)

    rutas_autorizadas = control.get("alcance", {}).get("rutas_autorizadas", [])
    fuera_de_alcance = [
        r for r in repo.files_out_of_scope(repo_root, rutas_autorizadas) if not scope.es_output_intrinseco(r)
    ]

    # Verificación informativa de los checkpoints pre-aprobados (no cambia exit codes).
    checkpoints_estado = sdd.verificar_checkpoints(repo_root, control) if control.get("decisiones_preaprobadas") else []

    if args.json:
        payload = {
            "change_id": args.change_id,
            "estado": estado,
            "errores_estado": [f.to_dict() for f in err],
            "discrepancia": discrepancia,
            "sesion": sesion_info,
            "fuera_de_alcance": fuera_de_alcance,
            "checkpoints": checkpoints_estado,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Cambio: {args.change_id}")
        print(f"Estado (tasks.md): {estado if estado is not None else 'ILEGIBLE'}")
        for f in err:
            print(f"  [{f.codigo}] {f.mensaje}")
        if discrepancia:
            print(f"Discrepancia: {discrepancia}")
        if sesion_activa:
            print(
                f"Sesión activa: {sesion_info['id']} "
                f"({sesion_info['minutos_transcurridos']:.1f} min transcurridos)"
            )
        else:
            print("Sin sesión activa.")
        if fuera_de_alcance:
            print("Archivos fuera de alcance (informativo):")
            for r in fuera_de_alcance:
                print(f"  - {r}")
        if checkpoints_estado:
            print("Checkpoints:")
            for c in checkpoints_estado:
                print(f"  - [{c['estado']}] {c['summary']}: {c['detalle']}")

    return 0


# --- validate -----------------------------------------------------------------

def cmd_validate(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    findings = []

    estado, err = sdd.read_estado(tasks_path)
    findings += err

    sesion_activa = sdd._sesion_activa(control)

    # scope.evaluar_alcance se evalúa UNA sola vez por invocación: si --gate cierre va a
    # correr gate_cierre (que ya lo incluye internamente), no se duplica acá; en cualquier
    # otro caso (sin --gate, --gate implementacion, o --gate cierre que no llega a correr
    # gate_cierre por SESION-AUSENTE) se evalúa acá directamente, para no perder cobertura.
    gate_cierre_va_a_correr = args.gate == "cierre" and (
        sesion_activa is not None or estado == "cerrada"
    )
    if not gate_cierre_va_a_correr:
        findings += scope.evaluar_alcance(repo_root, control)

    for linea in repo.diff_check(repo_root):
        findings.append(core.Finding("ALCANCE-WHITESPACE", linea))

    if args.gate:
        # Excepción (spec requisito 8): un cambio ya cerrado puede validar el
        # gate de cierre sin sesión activa, sin el finding bloqueante
        # SESION-AUSENTE -- mismo patrón que ya usa `cmd_archive` al llamar
        # `gate_cierre(..., None, ...)` (tools/ds_guard.py, cmd_archive). La
        # transición real a `cerrada` (`transition --a cerrada`) sigue
        # exigiendo sesión activa sin excepción, vía `_findings_del_gate`.
        if sesion_activa is None and not (args.gate == "cierre" and estado == "cerrada"):
            findings.append(
                core.Finding("SESION-AUSENTE", f"Se requiere sesión activa para validar el gate '{args.gate}'")
            )
        else:
            if args.gate == "implementacion":
                findings += sdd.gate_implementacion(control, tasks_path, sesion_activa)
            elif args.gate == "cierre":
                findings += sdd.gate_cierre(control, tasks_path, sesion_activa, repo_root)

    if sesion_activa is not None:
        findings += sdd.chequear_limites(sesion_activa)

    exit_code = 1 if findings else 0
    _imprimir_findings(findings, exit_code, args.json)
    return exit_code


# --- approve --------------------------------------------------------------

def cmd_approve(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    error_usuario = core.validar_usuario_sin_email(args.usuario)
    if error_usuario:
        print(error_usuario, file=sys.stderr)
        return 2
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    for artefacto in args.artefacto:
        if not (change_dir / artefacto).exists():
            print(f"El artefacto no existe: {artefacto}", file=sys.stderr)
            return 2

    # Alcance autorizado (R22-R25 de 20261005-operational-autonomy-hardening):
    # válido en CUALQUIER approval_mode. Sección ausente o sin bullets -> no se
    # toca el alcance. Hallazgos -> exit 2 sin escribir nada (todo-o-nada).
    # `proposal.md` se lee UNA sola vez (bytes): de esos mismos bytes salen el
    # texto parseado y el hash (misma algoritmia que `core.hash_lf_v1`), así no
    # hay ventana TOCTOU entre lo parseado y lo registrado.
    hash_proposal = None
    texto_proposal = None
    if "proposal.md" in args.artefacto:
        crudo_proposal = (change_dir / "proposal.md").read_bytes()
        decodificado = crudo_proposal.decode("utf-8-sig")
        normalizado = decodificado.replace("\r\n", "\n").replace("\r", "\n")
        hash_proposal = hashlib.sha256(normalizado.encode("utf-8")).hexdigest()
        texto_proposal = normalizado
        texto_alcance = texto_proposal
        declaradas, hallazgos_alcance = sdd.parsear_alcance_autorizado(texto_alcance)
        if hallazgos_alcance:
            print(core.formatear_findings_texto(hallazgos_alcance), file=sys.stderr)
            return 2
        if declaradas:
            md_defecto = list(_PLANTILLAS_POR_MODO.get(control.get("modo"), _PLANTILLAS_POR_MODO["completo"]))
            md_defecto = [f"{n}.md" for n in md_defecto]
            nuevas = sorted(set(_rutas_por_defecto_change(args.change_id, md_defecto)) | set(declaradas))
            previas = control.setdefault("alcance", {}).get("rutas_autorizadas", [])
            agregadas = sorted(set(nuevas) - set(previas))
            retiradas = sorted(set(previas) - set(nuevas))
            control["alcance"]["rutas_autorizadas"] = nuevas
            print(f"alcance autorizado materializado ({len(nuevas)} rutas)")
            for r in agregadas:
                print(f"  + {r}")
            for r in retiradas:
                print(f"  - {r}")

    # Checkpoints de negocio (T5, R3-R6 de 20260930-autonomous-sdd-and-remediation):
    # si se aprueba `proposal.md` y el Change declara `approval_mode:
    # checkpoints`, se parsea su sección `## Checkpoints de negocio` y se
    # persiste en `control["decisiones_preaprobadas"]` -- reemplaza el
    # contenido anterior (refleja el `proposal.md` que se está aprobando
    # ahora, no se acumula entre re-aprobaciones). Fail-closed (R3, "nunca un
    # checkpoint fantasma"): si hay algún bullet inválido, se rechaza la
    # aprobación de `proposal.md` completa (exit 2, no se escribe nada) en vez
    # de aceptar una lista de checkpoints parcialmente inválida.
    if "proposal.md" in args.artefacto and sdd.resolver_approval_mode(control) == "checkpoints":
        # `hash_proposal` (calculado arriba, una vez) sirve para la entrada de
        # `aprobaciones` y para materializar `@approved` (D1-D4 del SDD).

        def _resolver_approved(change_id_ref: str):
            if change_id_ref == args.change_id:
                return hash_proposal, "proposal.md de este Change"
            res = sdd.resolver_aprobacion_registrada(repo_root, change_id_ref, "proposal.md")
            if res.get("estado") == "verified":
                return res.get("hash_vigente"), res.get("detalle", "")
            return None, f"{res.get('estado')}: {res.get('detalle', '')}"

        checkpoints, hallazgos_checkpoints = sdd.parsear_checkpoints_de_propuesta(
            texto_proposal, change_id=args.change_id, resolver_approved=_resolver_approved
        )
        if hallazgos_checkpoints:
            print(core.formatear_findings_texto(hallazgos_checkpoints), file=sys.stderr)
            return 2
        control["decisiones_preaprobadas"] = checkpoints
        con_ceros = sdd.checkpoints_con_placeholder_cero(texto_proposal)
        if con_ceros:
            print(
                "deprecated: checkpoints con hash de 64 ceros (placeholder, no verificable); "
                "usar `@approved` o el hash real. ids: " + ", ".join(con_ceros),
                file=sys.stderr,
            )

        # Dependencias pre-aprobadas del proyecto (M11, adenda post-cierre
        # 2026-09-30 de `docs/roadmap/v0.8.md`): mismo criterio que los
        # checkpoints de negocio -- se parsea junto con `proposal.md` en
        # `approval_mode: checkpoints`, se persiste en
        # `control["dependencias_preaprobadas"]` (reemplaza en cada
        # re-aprobación, no se acumula), y fail-closed: un bullet inválido
        # rechaza la aprobación COMPLETA (exit 2, no se escribe nada).
        dependencias, hallazgos_dependencias = sdd.parsear_dependencias_preaprobadas(texto_proposal)
        if hallazgos_dependencias:
            print(core.formatear_findings_texto(hallazgos_dependencias), file=sys.stderr)
            return 2
        control["dependencias_preaprobadas"] = dependencias

    entradas = []
    for artefacto in args.artefacto:
        ruta = change_dir / artefacto
        if artefacto == "proposal.md" and hash_proposal is not None:
            hash_valor = hash_proposal  # mismo hash que se materializó en los checkpoints (sin releer)
        else:
            hash_valor = core.hash_lf_v1(ruta)
        entrada = {
            "artefacto": artefacto,
            "algoritmo": "sha256/lf/v1",
            "hash": hash_valor,
            "registrado_utc": core.ahora_utc(),
            "usuario": args.usuario,
            "fecha_declarada": args.fecha,
            "alcance_aprobado": args.alcance,
            "cita": args.cita,
        }
        control.setdefault("aprobaciones", []).append(entrada)
        entradas.append(entrada)

    core.escribir_control(control_path, control)

    for e in entradas:
        print(f"{e['artefacto']}: {e['hash']}")
    print("el hash acredita identidad de contenido, no aprobación humana")
    return 0


# --- transition -----------------------------------------------------------

def cmd_transition(args: argparse.Namespace) -> int:
    if args.a not in sdd.ESTADOS_VALIDOS:
        print(f"Estado destino desconocido: {args.a}", file=sys.stderr)
        return 2

    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    if args.a == "cerrada":
        # Pre-chequeo KDD (Bloque 4): corre ANTES de tocar tasks.md/control.json,
        # para que un state.json ausente/corrupto bloquee el cierre de forma
        # atómica en vez de dejarlo cerrado sin evidencia KDD sincronizada
        # ("no debe quedar silenciosamente inconsistente"). Si el cambio no
        # declara ninguna etapa KDD, esto es un no-op (lista vacía).
        pre_findings = kdd.validar_antes_de_cerrar(repo_root, control)
        if pre_findings:
            _imprimir_findings(pre_findings, 1, args.json)
            return 1

    sesion_activa = sdd._sesion_activa(control)
    ok, findings = sdd.transition(control, tasks_path, control_path, repo_root, args.a, sesion_activa)

    if not ok:
        _imprimir_findings(findings, 1, args.json)
        return 1

    kdd_sync_resultado = None
    kdd_sync_error = None
    if args.a == "cerrada":
        try:
            kdd_sync_resultado = kdd.sync_al_cerrar(repo_root, control, args.change_id)
        except Exception as e:  # nunca silencioso: la transición SDD ya se aplicó
            kdd_sync_error = str(e)

    if args.json:
        payload = {"transicion_aplicada": args.a}
        if kdd_sync_resultado is not None:
            payload["kdd_sync"] = kdd_sync_resultado
        if kdd_sync_error is not None:
            payload["kdd_sync_error"] = kdd_sync_error
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"Transición aplicada -> {args.a}")
        if kdd_sync_resultado is not None:
            if kdd_sync_resultado["sincronizado"]:
                print(f"KDD sincronizado: {', '.join(kdd_sync_resultado['etapas_actualizadas'])}")
            else:
                print(f"KDD: {kdd_sync_resultado['motivo']}")
        if kdd_sync_error is not None:
            print(f"[KDD-SYNC-FALLO] {kdd_sync_error}", file=sys.stderr)

    return 1 if kdd_sync_error is not None else 0


# --- autonomy budgets (v0.8 Change 3: 20260930-autonomous-sdd-and-remediation) -
#
# `autonomy.budgets` en `.claude/guardrails.json` (R8-R9 de spec.md, D5 de
# design.md): extensión aditiva de la policy de Change 0, validada acá (no en
# `tools/autonomy/policy.py`, que ignora claves desconocidas por diseño) --
# mismo patrón de composición que `_resolver_aprobacion_exec` (Change 2).

_BUDGET_DEFAULTS = {
    "session_minutes": 90,
    "aggregate_minutes": None,
    "max_sessions": None,
    "max_concurrent_subagents": None,
    "remediation_max_intentos_default": 2,
}


class BudgetsInvalidosError(Exception):
    """`autonomy.budgets` declara un valor presente pero inválido (R9:
    fail-closed -- no-entero, negativo o cero). Lleva los `core.Finding` con
    código `AUTONOMY-POLICY-LIMITS` para que el llamador (CLI) los traduzca a
    exit 2, mismo patrón que `sdd.RemediacionLimiteError`."""

    def __init__(self, findings: list):
        self.findings = findings
        super().__init__("; ".join(f.mensaje for f in findings))


def _resolver_budgets(repo_root: Path) -> dict:
    """Lee `.claude/guardrails.json` -> `autonomy.budgets` y devuelve un dict
    con las 5 claves de policy SIEMPRE presentes: `session_minutes`,
    `aggregate_minutes`, `max_sessions`, `max_concurrent_subagents`,
    `remediation_max_intentos_default` (R8 de spec.md). Ausencia del archivo,
    de la clave `autonomy`/`autonomy.budgets`, o de una clave individual
    dentro de ese dict -> el literal hardcodeado de hoy (`_BUDGET_DEFAULTS`),
    cero cambio de comportamiento sin declarar la clave.

    Fail-closed (R9): un valor PRESENTE pero inválido (no-entero -- bool
    excluido --, negativo o cero) para cualquiera de las 5 claves levanta
    `BudgetsInvalidosError` con el código `AUTONOMY-POLICY-LIMITS`
    (`tools.autonomy.core.CODE_POLICY_LIMITS`, ya reservado por Change 0 para
    justamente esto: límites de policy mal formados) -- nunca se trata como
    ausente ni se degrada en silencio al default.

    Reusa `pathguard.cargar_config` para el mismo fail-closed que ya aplica
    `_resolver_aprobacion_exec` ante un `guardrails.json` corrupto o con
    `version` no soportada (acá, ante ese caso, se degrada a los defaults de
    budgets sin lanzar -- el resto del CLI ya reporta ese error de
    `guardrails.json` por su cuenta cuando corresponde; esta función nunca
    bloquea nada por sí sola salvo el caso puntual de R9). `autonomy.budgets`
    no es una clave que `ConfigGuardrails`/`cargar_config` conozcan, así que
    el JSON crudo se relee aparte para llegar a ella -- mismo patrón que
    `_resolver_aprobacion_exec` ya usa para llegar a `autonomy`."""
    return _resolver_budgets_con_fuentes(repo_root)[0]


# Mapeo legacy `autonomy.limits` -> clave canónica de `autonomy.budgets`
# (R1 de 20261005-operational-autonomy-hardening). Solo estos dos ejes.
_LIMITS_A_BUDGETS = {
    "max_sessions": "max_sessions",
    "max_total_minutes": "aggregate_minutes",
}


AVISO_GUARDRAILS_ILEGIBLE = "guardrails.json ilegible: los límites configurados NO se aplican"


def _aviso_guardrails_ilegible(repo_root: Path) -> Optional[str]:
    """I3: `AVISO_GUARDRAILS_ILEGIBLE` si `.claude/guardrails.json` EXISTE pero no
    se puede leer (corrupto, versión no soportada, no-objeto) o `autonomy` no es
    objeto; `None` en cualquier otro caso (incluido archivo ausente). Solo
    informativo: el resolvedor sigue degradando a defaults, sin cambiar exit codes."""
    pathguard_mod = _importar_perezoso("dsguard", "pathguard")
    if pathguard_mod is None:
        return None
    ruta_config = Path(repo_root) / pathguard_mod.RUTA_CONFIG_RELATIVA
    if not ruta_config.exists():
        return None
    try:
        pathguard_mod.cargar_config(repo_root)
        guardrails_dict = json.loads(ruta_config.read_text(encoding="utf-8"))
    except (pathguard_mod.ConfigGuardrailsError, OSError, ValueError):
        return AVISO_GUARDRAILS_ILEGIBLE
    if not isinstance(guardrails_dict, dict):
        return AVISO_GUARDRAILS_ILEGIBLE
    if "autonomy" in guardrails_dict and not isinstance(guardrails_dict["autonomy"], dict):
        return AVISO_GUARDRAILS_ILEGIBLE
    return None


def _leer_valores_brutos_budgets(repo_root: Path) -> tuple:
    """Lee y valida `autonomy.budgets` y `autonomy.limits` de `guardrails.json`.
    Devuelve `(valores_budgets, valores_limits)`: dos dicts ya validados, el
    segundo con las claves traducidas a la clave canónica de budgets
    (`max_total_minutes` -> `aggregate_minutes`). Ausencia de archivo/clave,
    config corrupta o `autonomy` no-dict -> dicts vacíos (sin cambio de
    comportamiento). Valor presente e inválido (no entero positivo, bool
    excluido) o `limits` no-dict -> `BudgetsInvalidosError`
    (`AUTONOMY-POLICY-LIMITS`, R3). Claves desconocidas dentro de `limits` se
    ignoran acá (las reporta `tools/autonomy/policy.py`)."""
    vacios = ({}, {})

    pathguard_mod = _importar_perezoso("dsguard", "pathguard")
    if pathguard_mod is None:
        return vacios

    ruta_config = Path(repo_root) / pathguard_mod.RUTA_CONFIG_RELATIVA
    if not ruta_config.exists():
        return vacios

    try:
        pathguard_mod.cargar_config(repo_root)
    except pathguard_mod.ConfigGuardrailsError:
        return vacios

    try:
        guardrails_dict = json.loads(ruta_config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return vacios
    if not isinstance(guardrails_dict, dict):
        return vacios

    autonomy_dict = guardrails_dict.get("autonomy")
    if not isinstance(autonomy_dict, dict):
        return vacios

    hallazgos: list = []
    codigo = sdd.autonomy_core.CODE_POLICY_LIMITS

    def _es_valido(valor) -> bool:
        return isinstance(valor, int) and not isinstance(valor, bool) and valor > 0

    valores_budgets: dict = {}
    budgets_dict = autonomy_dict.get("budgets")
    if "budgets" in autonomy_dict and not isinstance(budgets_dict, dict):
        # I4: `budgets` presente y no-dict (null, número, string, lista) es inválido, igual que `limits`.
        hallazgos.append(
            core.Finding(
                codigo,
                f"autonomy.budgets = {budgets_dict!r} inválido: debe ser un objeto",
                str(ruta_config),
            )
        )
    if isinstance(budgets_dict, dict):
        for clave in _BUDGET_DEFAULTS:
            if clave not in budgets_dict:
                continue
            valor = budgets_dict[clave]
            if not _es_valido(valor):
                hallazgos.append(
                    core.Finding(
                        codigo,
                        f"autonomy.budgets.{clave} = {valor!r} inválido: debe ser un entero positivo",
                        str(ruta_config),
                    )
                )
                continue
            valores_budgets[clave] = valor

    valores_limits: dict = {}
    if "limits" in autonomy_dict:
        limits_dict = autonomy_dict["limits"]
        if not isinstance(limits_dict, dict):
            hallazgos.append(
                core.Finding(
                    codigo,
                    f"autonomy.limits = {limits_dict!r} inválido: debe ser un objeto",
                    str(ruta_config),
                )
            )
        else:
            for clave_limits, clave_budgets in _LIMITS_A_BUDGETS.items():
                if clave_limits not in limits_dict:
                    continue
                valor = limits_dict[clave_limits]
                if not _es_valido(valor):
                    hallazgos.append(
                        core.Finding(
                            codigo,
                            f"autonomy.limits.{clave_limits} = {valor!r} inválido: debe ser un entero positivo",
                            str(ruta_config),
                        )
                    )
                    continue
                valores_limits[clave_budgets] = valor

    if hallazgos:
        raise BudgetsInvalidosError(hallazgos)

    return valores_budgets, valores_limits


def _resolver_budgets_con_fuentes(repo_root: Path) -> tuple:
    """Variante de `_resolver_budgets` que además devuelve la fuente efectiva
    por eje: `(dict_de_5_claves, fuentes)` con `fuentes[clave]` en
    `'budgets'`, `'limits'`, `'ambas (mínimo=N)'` o `'default'` (R2/R4). Para
    `max_sessions` y `aggregate_minutes`, si `budgets` y `limits` declaran el
    eje, gana el MENOR (más estricto); nunca uno amplía al otro."""
    resultado = dict(_BUDGET_DEFAULTS)
    fuentes_base = "guardrails ilegible" if _aviso_guardrails_ilegible(repo_root) else "default"
    fuentes = {clave: fuentes_base for clave in _BUDGET_DEFAULTS}

    valores_budgets, valores_limits = _leer_valores_brutos_budgets(repo_root)

    for clave in _BUDGET_DEFAULTS:
        en_budgets = clave in valores_budgets
        en_limits = clave in valores_limits
        if en_budgets and en_limits:
            minimo = min(valores_budgets[clave], valores_limits[clave])
            resultado[clave] = minimo
            fuentes[clave] = f"ambas (mínimo={minimo})"
        elif en_budgets:
            resultado[clave] = valores_budgets[clave]
            fuentes[clave] = "budgets"
        elif en_limits:
            resultado[clave] = valores_limits[clave]
            fuentes[clave] = "limits"

    return resultado, fuentes


_EJES_AGREGADOS = (
    ("aggregate_minutes", "minutos_consumidos_totales"),
    ("max_sessions", "sesiones_totales"),
)


def _resumen_limites_agregados(control: dict, repo_root: Path, budgets: dict, fuentes: dict) -> dict:
    """Vista de solo lectura de los límites agregados efectivos por eje:
    `{eje: {"efectivo", "fuente", "valores", "consumo", "restante"}}`.
    `restante = max(0, límite - consumo)` (None si no hay límite). `valores`
    lista `budgets`/`limits` por separado solo cuando ambos están declarados y
    difieren (R4)."""
    agregado = sdd.presupuesto_agregado(control)
    valores_budgets, valores_limits = _leer_valores_brutos_budgets(repo_root)
    resumen: dict = {}
    for eje, clave_consumo in _EJES_AGREGADOS:
        efectivo = budgets[eje]
        consumo = agregado[clave_consumo]
        restante = None if efectivo is None else max(0, efectivo - consumo)
        valores = None
        if (
            eje in valores_budgets
            and eje in valores_limits
            and valores_budgets[eje] != valores_limits[eje]
        ):
            valores = {"budgets": valores_budgets[eje], "limits": valores_limits[eje]}
        resumen[eje] = {
            "efectivo": efectivo,
            "fuente": fuentes[eje],
            "valores": valores,
            "consumo": consumo,
            "restante": restante,
        }
    return resumen


def _linea_limite_agregado(eje: str, info: dict) -> str:
    texto = (
        f"{eje}: efectivo={info['efectivo']} fuente={info['fuente']} "
        f"consumo={info['consumo']:.1f} restante={info['restante']}"
        if isinstance(info["consumo"], float)
        else f"{eje}: efectivo={info['efectivo']} fuente={info['fuente']} "
        f"consumo={info['consumo']} restante={info['restante']}"
    )
    if info["valores"]:
        texto += f" (budgets={info['valores']['budgets']}, limits={info['valores']['limits']})"
    return texto


# --- config layering (v0.8 Change 4: 20260930-project-extension-and-
# installer-integration, M10) -----------------------------------------------
#
# R10-R13 de spec.md, D3 de design.md: tres capas explícitas `managed
# defaults -> project config -> local machine overrides -> effective config`,
# compuestas ACÁ (nunca en `tools/dsguard/pathguard.py` ni en
# `tools/autonomy/policy.py` -- esos dos siguen siendo la única fuente de la
# policy humana, el techo de toda restricción) -- mismo patrón de composición
# externa que `_resolver_budgets` arriba, aplicado a dos archivos nuevos:
#   - `.harmessi/project-config.json`: versionado en git, customización de
#     proyecto compartida por todo el equipo.
#   - `.harmessi/local-overrides.json`: NO versionado (entrada sugerida en
#     `.gitignore` del manifiesto), restricciones propias de esta máquina.
# Ninguno de los dos archivos existe todavía en ningún proyecto real -- su
# AUSENCIA TOTAL es el caso normal/esperado (proyecto sin ninguna capa
# configurada, cero cambio de comportamiento), no un error. Un archivo
# presente pero corrupto (no-JSON, o JSON cuya raíz no es un objeto) degrada
# en silencio a "capa vacía" por el mismo motivo -- un archivo mal formado no
# debe impedir que el resto de Harmessi funcione (a diferencia de
# `_BUDGET_DEFAULTS`/R9, acá no hay un caso de "valor individual inválido"
# reservado: cada consumidor de estas capas valida sus propias claves).
#
# Principio general de layering para que otros consumidores lo reusen
# (dependencias de M11/T3, fuentes externas de M9/T4, cualquier restricción
# nueva futura): cualquier capa nueva de restricción lee estas MISMAS capas
# vía `resolver_project_config`/`resolver_local_override` y aplica SU PROPIA
# lógica de intersección fail-closed sobre la clave que le corresponda --
# este módulo no centraliza el schema completo de todas las claves posibles
# de `project-config.json`/`local-overrides.json`, cada consumidor documenta
# las suyas (p. ej. `dependencias_efectivas` de R26 documenta su propia clave
# de restricción de dependencias, separada de `mode` que resuelve acá).

def _leer_capa_json(ruta: Path) -> dict:
    """Lector genérico fail-closed de una capa de config M10. Ausencia total
    del archivo -> `{}` (caso normal, no un error). Archivo presente pero no
    es JSON válido, o su raíz no es un objeto (`dict`) -- p. ej. una lista o
    un escalar en la raíz -- -> también `{}`, degradación silenciosa, misma
    razón que la ausencia total: un archivo corrupto no debe bloquear nada
    por sí solo. No usa `pathguard.cargar_config` (ese lee `guardrails.json`
    específicamente, con su propio schema versionado `ConfigGuardrails`) --
    `project-config.json`/`local-overrides.json` son JSON simple sin ese
    contrato, de ahí un lector propio y deliberadamente más permisivo."""
    if not ruta.exists():
        return {}
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(datos, dict):
        return {}
    return datos


def resolver_project_config(repo_root: Path) -> dict:
    """Capa `project config` (R10): `.harmessi/project-config.json`,
    versionado en git. Ver `_leer_capa_json` para la semántica fail-closed de
    ausencia/corrupción."""
    return _leer_capa_json(Path(repo_root) / ".harmessi" / "project-config.json")


def resolver_local_override(repo_root: Path) -> dict:
    """Capa `local machine overrides` (R10): `.harmessi/local-overrides.json`,
    NO versionado (propio de esta máquina). Ver `_leer_capa_json` para la
    semántica fail-closed de ausencia/corrupción."""
    return _leer_capa_json(Path(repo_root) / ".harmessi" / "local-overrides.json")


def resolver_modo_efectivo(modo_policy_humana: str, project_config: dict, local_override: dict) -> str:
    """Resuelve el `mode` efectivo (R11: fail-closed, `permiso_efectivo =
    policy_humana ∩ project_config ∩ local_override` -- un override SOLO
    restringe, nunca amplía).

    Implementación: "cualquier capa que declare `mode: supervised` gana" --
    equivalente a tomar, entre `modo_policy_humana` y cualquier valor
    reconocido declarado en `project_config`/`local_override`, el MÁS
    RESTRICTIVO del vocabulario cerrado `{"autonomous", "supervised"}` (hoy
    el único par posible; `"supervised"` es estrictamente más restrictivo que
    `"autonomous"`). Equivale a una intersección: el resultado nunca es más
    permisivo que `modo_policy_humana` ni que ninguna capa que declare
    `"supervised"` válidamente.

    Precedencia entre `project_config` y `local_override`: NO IMPORTA cuál de
    las dos declara `"supervised"` -- cualquiera de las dos alcanza para
    restringir (ninguna capa puede "cancelar" la restricción de la otra; ese
    sería justo el caso de ampliación prohibido por R11). Por eso este
    método, a propósito, no usa una precedencia de "una capa tapa a la otra"
    -- usa unión de restricciones, que es la única semántica consistente con
    "solo restringe, nunca amplía" cuando hay más de una capa inferior.

    Given/When/Then exacto de R11: policy humana `supervised` + local
    override que declara `mode: autonomous` -> el modo efectivo sigue siendo
    `supervised` (el intento de ampliación se ignora en esa clave). Policy
    humana `autonomous` + local override `mode: supervised` -> efectivo
    `supervised` (restricción válida, se aplica).

    Valores desconocidos/no-string en la clave `"mode"` de cualquier capa
    (p. ej. `123`, `null`, `"algo-no-reconocido"`) se ignoran por completo --
    fail-closed: solo un valor reconocido del vocabulario cerrado puede
    restringir, nunca se interpreta nada ambiguo como restricción válida. Si
    ninguna capa declara un `"mode"` reconocido, el efectivo es
    `modo_policy_humana` sin cambios (backward compatible con un proyecto sin
    ninguna capa M10 configurada)."""
    vocabulario_reconocido = {"autonomous", "supervised"}

    candidatos = [modo_policy_humana]
    for capa in (project_config, local_override):
        valor = capa.get("mode")
        if isinstance(valor, str) and valor in vocabulario_reconocido:
            candidatos.append(valor)

    if "supervised" in candidatos:
        return "supervised"
    return modo_policy_humana


def resolver_output_roots(repo_root: Path) -> list:
    """Output roots declarados (R18, M12) -- UNIÓN (no intersección: es una
    declaración aditiva/cooperativa, no una restricción de algo pre-existente
    como M11) de `project-config.json` y `local-overrides.json`, clave
    `output_roots` (lista de strings). Deduplicado, orden estable (primero
    project config, después local override, sin repetir). `[]` si ninguna
    capa declara nada -- backward compat total (comportamiento hoy: nadie
    consulta esto, cero cambio). Control COOPERATIVO, no sandbox: no
    intercepta escrituras, no reemplaza pathguard ni el fingerprint pre/post
    -- documentado explícitamente acá y en la ayuda del CLI nuevo."""
    vistos: list = []
    for capa in (resolver_project_config(repo_root), resolver_local_override(repo_root)):
        raices = capa.get("output_roots")
        if isinstance(raices, list):
            for r in raices:
                if isinstance(r, str) and r and r not in vistos:
                    vistos.append(r)
    return vistos


def cmd_output_roots_list(args: argparse.Namespace) -> int:
    """`ds_guard output-roots list` (R18): imprime los output roots
    declarados vía `resolver_output_roots` -- puramente informativo, control
    COOPERATIVO, no sandbox (no intercepta escrituras, no reemplaza
    pathguard ni el fingerprint pre/post de M12)."""
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    raices = resolver_output_roots(repo_root)
    if args.json:
        print(json.dumps({"output_roots": raices}, ensure_ascii=False))
    else:
        if raices:
            for r in raices:
                print(r)
        else:
            print("(sin output roots declarados)")
    return 0


# --- session ----------------------------------------------------------------

def cmd_session_start(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    try:
        budgets, fuentes_budgets = _resolver_budgets_con_fuentes(repo_root)
    except BudgetsInvalidosError as e:
        print(core.formatear_findings_texto(e.findings), file=sys.stderr)
        return 2
    aviso_guardrails = _aviso_guardrails_ilegible(repo_root)
    if aviso_guardrails:
        print(f"AVISO: {aviso_guardrails}", file=sys.stderr)

    # `--minutos` explícito del llamador manda siempre, sin consultar policy
    # (R8 de spec.md); solo si el flag no se pasó (`None`, ver default de
    # argparse) se resuelve desde `autonomy.budgets.session_minutes`.
    minutos = args.minutos if args.minutos is not None else budgets["session_minutes"]

    # R12/R12a de spec.md, ENMENDADO (decisión humana explícita registrada en
    # el decision ledger, `ds_guard decision list --change-id
    # 20260930-autonomous-sdd-and-remediation`, ver también
    # `verification.md` de ese Change): tanto `max_sessions` COMO
    # `aggregate_minutes` son LIMIT efectivos -- ambos bloquean abrir una
    # ventana nueva al alcanzarlos o superarlos. La afirmación anterior de
    # que `aggregate_minutes` era "puramente informativo" (R11 tal como se
    # interpretó originalmente) quedó superseded: el propio catálogo LIMIT
    # de `tools.autonomy.core` (`CHECKPOINT_RESUMABLE`) siempre implicó que
    # agotar CUALQUIERA de los dos ejes agregados produce un checkpoint
    # resumible -- eso solo puede cumplirse si ambos ejes impiden abrir una
    # ventana nueva, no solo uno. Se chequea ANTES de llamar a
    # `sdd.session_start` y antes de escribir nada -- si se rechaza,
    # `control.json` queda intacto. Nunca produce STOP ni aprobación humana
    # automática (siguen siendo LIMIT, no STOP_CATALOG); nunca se resetea
    # cerrando/reabriendo (R12a, `presupuesto_agregado` suma sobre TODAS las
    # sesiones de `control["sesiones"]`, sin excepción).
    findings_limite_agregado = sdd.chequear_limite_agregado(
        control,
        {
            "max_sessions": budgets["max_sessions"],
            "aggregate_minutes": budgets["aggregate_minutes"],
        },
    )
    if findings_limite_agregado:
        print(core.formatear_findings_texto(findings_limite_agregado), file=sys.stderr)
        # Fuente efectiva de cada límite agregado (R4 de 20261005-operational-autonomy-hardening).
        print(
            "Fuente de límites agregados: "
            f"aggregate_minutes={budgets['aggregate_minutes']} ({fuentes_budgets['aggregate_minutes']}), "
            f"max_sessions={budgets['max_sessions']} ({fuentes_budgets['max_sessions']})",
            file=sys.stderr,
        )
        return 2

    try:
        entrada = sdd.session_start(
            control,
            modo=args.modo,
            minutos=minutos,
            max_tareas=args.max_tareas,
            max_roles=args.max_roles,
            max_reintentos=args.max_reintentos,
            max_rondas_revision=args.max_rondas,
        )
    except sdd.SesionYaActivaError as e:
        print(str(e), file=sys.stderr)
        return 2

    core.escribir_control(control_path, control)
    print(f"Sesión iniciada: {entrada['id']}")
    return 0


def cmd_session_note(args: argparse.Namespace) -> int:
    if args.remediation_tipo is not None and args.tipo != "reintento":
        print(
            "--remediation-tipo solo es válido junto con --tipo reintento",
            file=sys.stderr,
        )
        return 2

    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    try:
        budgets = _resolver_budgets(repo_root)
    except BudgetsInvalidosError as e:
        print(core.formatear_findings_texto(e.findings), file=sys.stderr)
        return 2

    try:
        sdd.session_note(
            control,
            args.rol,
            args.tipo,
            args.tarea,
            finding_id=args.finding_id,
            remediation_tipo=args.remediation_tipo,
            causa=args.causa,
            cambio_aplicado=args.cambio_aplicado,
            resultado=args.resultado,
            # R20 de spec.md: default de policy, no el literal `2` hardcodeado
            # en la firma de `sdd.remediation_note`.
            max_intentos_remediacion=budgets["remediation_max_intentos_default"],
        )
    except (sdd.SesionAusenteError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 2
    except sdd.RemediacionLimiteError as e:
        print(core.formatear_findings_texto(e.findings), file=sys.stderr)
        return 2

    core.escribir_control(control_path, control)
    return 0


def cmd_session_status(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    estado = sdd.session_status(control)

    # Sección de límites agregados efectivos (aditiva, informativa: nunca cambia el exit code).
    limites_agregados = None
    error_limites = None
    try:
        budgets_ef, fuentes_ef = _resolver_budgets_con_fuentes(repo_root)
        limites_agregados = _resumen_limites_agregados(control, repo_root, budgets_ef, fuentes_ef)
    except BudgetsInvalidosError as e:
        error_limites = core.formatear_findings_texto(e.findings)
    avisos = [a for a in (_aviso_guardrails_ilegible(repo_root),) if a]

    if args.json:
        payload = dict(estado)
        payload["avisos"] = avisos
        payload["limites_agregados"] = limites_agregados if error_limites is None else {"error": error_limites}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        if not estado["activa"]:
            print("No hay sesión activa.")
        else:
            print(f"Sesión activa: {estado['id']} ({estado['minutos_transcurridos']:.1f} min transcurridos)")
            print(
                f"tareas={estado['tareas']} roles={estado['roles']} "
                f"reintentos={estado['reintentos']} rondas_revision={estado['rondas_revision']}"
            )
            for f in estado["findings"]:
                print(f"  [{f['codigo']}] {f['mensaje']}")
        for aviso in avisos:
            print(f"AVISO: {aviso}")
        print("Límites agregados efectivos:")
        if error_limites is not None:
            print(f"  (inválidos) {error_limites}")
        else:
            for eje, _clave in _EJES_AGREGADOS:
                print("  " + _linea_limite_agregado(eje, limites_agregados[eje]))
    return 0


def cmd_session_close(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    try:
        cerrada = sdd.session_close(control, args.estado)
    except sdd.SesionAusenteError as e:
        print(str(e), file=sys.stderr)
        return 2

    core.escribir_control(control_path, control)

    # Mensaje final visible (spec requisito 7): según `estado_final` +
    # `resultado`, ambos ya derivados automáticamente por `session_close` --
    # nunca a partir de un flag declarado a mano.
    estado_final = cerrada.get("estado_final")
    resultado = cerrada.get("resultado")
    if resultado == "excedida":
        print("🛑 PRESUPUESTO AGOTADO")
    elif estado_final == "completada":
        print("✅ SESIÓN TERMINADA")
    elif estado_final == "pausada":
        print("⏸️ SESIÓN PAUSADA")
    print("Sesión cerrada.")
    return 0


def cmd_session_aggregate(args: argparse.Namespace) -> int:
    """`session aggregate` (T5, v0.8 Change 3): expone `sdd.presupuesto_
    agregado(control)` + `sdd.chequear_limite_agregado(control, ...)` contra
    los topes agregados configurados (`autonomy.budgets.aggregate_minutes`/
    `max_sessions`, R8-R12 de spec.md). Puramente informativo, exit code 0
    siempre que no haya un error de uso/entorno -- mismo criterio que `session
    status`: agotar un límite agregado nunca bloquea esta consulta, solo se
    reporta (R11: checkpoint resumible, nunca STOP ni aprobación automática)."""
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    try:
        budgets, fuentes_budgets = _resolver_budgets_con_fuentes(repo_root)
    except BudgetsInvalidosError as e:
        print(core.formatear_findings_texto(e.findings), file=sys.stderr)
        return 2

    agregado = sdd.presupuesto_agregado(control)
    config_agregado = {
        "aggregate_minutes": budgets["aggregate_minutes"],
        "max_sessions": budgets["max_sessions"],
    }
    findings = sdd.chequear_limite_agregado(control, config_agregado)
    resumen = _resumen_limites_agregados(control, repo_root, budgets, fuentes_budgets)
    avisos = [a for a in (_aviso_guardrails_ilegible(repo_root),) if a]

    if args.json:
        payload = dict(agregado)
        payload["avisos"] = avisos
        payload["limites_configurados"] = config_agregado
        payload["limites_fuentes"] = {eje: resumen[eje]["fuente"] for eje, _c in _EJES_AGREGADOS}
        payload["restante"] = {eje: resumen[eje]["restante"] for eje, _c in _EJES_AGREGADOS}
        payload["findings"] = [f.to_dict() for f in findings]
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for aviso in avisos:
            print(f"AVISO: {aviso}")
        print(
            f"Sesiones totales: {agregado['sesiones_totales']} "
            f"(abiertas: {agregado['sesiones_abiertas']}) — "
            f"minutos consumidos: {agregado['minutos_consumidos_totales']:.1f}"
        )
        if config_agregado["aggregate_minutes"] is not None or config_agregado["max_sessions"] is not None:
            print(
                f"Límites configurados: aggregate_minutes={config_agregado['aggregate_minutes']} "
                f"max_sessions={config_agregado['max_sessions']}"
            )
            for eje, _clave in _EJES_AGREGADOS:
                print("  " + _linea_limite_agregado(eje, resumen[eje]))
        for f in findings:
            print(f"  [{f.codigo}] {f.mensaje}")
    return 0


def cmd_session_efficiency(args: argparse.Namespace) -> int:
    """`session efficiency` (M11/adenda post-cierre 2026-09-30, "Eficiencia
    writer -> Lead" de `docs/roadmap/v0.8.md`): expone
    `sdd.calcular_metricas_eficiencia(control)`. Puramente informativo/de
    observación (nunca gate numérico), mismo criterio que `session
    aggregate`/`session status`: exit 0 salvo error de uso/entorno."""
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    metricas = sdd.calcular_metricas_eficiencia(control)

    if args.json:
        print(json.dumps(metricas, ensure_ascii=False))
    else:
        print(f"writer_lead_cycles: {metricas['writer_lead_cycles']}")
        print(f"remediation_cycles: {metricas['remediation_cycles']}")
        print(f"executions_count: {metricas['executions_count']}")
        print(f"execution_duration_total_seconds: {metricas['execution_duration_total_seconds']:.1f}")
    return 0


# --- dependency (M11: 20260930-autonomous-sdd-and-remediation, adenda) -------
#
# `dependency classify`: consulta/clasificación pura (no instala nada, no
# bloquea nada por sí sola -- análogo a `session aggregate`). Lee
# `control["dependencias_preaprobadas"]` (poblado por `cmd_approve` cuando el
# Change está en `approval_mode: checkpoints`).

def dependencias_efectivas(control: dict, repo_root: Path) -> list:
    """`dependencias_efectivas` (R26): `control['dependencias_preaprobadas']`
    restringido por `project-config.json`/`local-overrides.json` (M10, T2) --
    nunca ampliado. Ambas capas (si declaran algo bajo la clave
    `'dependencias_preaprobadas'`, misma forma que `control`: lista de
    `{"nombre": str, "rango": str}`) solo pueden ACOTAR: una entrada de
    `control['dependencias_preaprobadas']` sobrevive al resultado final SOLO
    si, para cada capa que declare ALGO bajo esa clave, existe una entrada
    correspondiente (mismo nombre canonicalizado) en esa capa -- si una capa
    no declara la clave en absoluto, no restringe nada (backward compat,
    mismo criterio que `resolver_modo_efectivo`). El RANGO final de una
    entrada que sobrevive es la entrada de `control` tal cual (esta función
    NO intenta intersectar dos rangos numéricos entre capas -- decisión
    documentada: eso queda fuera de alcance de este Change, una capa inferior
    puede como mucho EXCLUIR una dependencia completa, no angostar su rango a
    un subrango -- si hiciera falta angostar rango en el futuro es una
    extensión aparte). Nombres comparados vía `sdd._canonicalizar_nombre_paquete`
    en ambos lados."""
    dependencias_control = control.get("dependencias_preaprobadas", [])

    capas = (resolver_project_config(repo_root), resolver_local_override(repo_root))
    sets_restriccion = []
    for capa in capas:
        valor = capa.get("dependencias_preaprobadas")
        if isinstance(valor, list):
            sets_restriccion.append(
                {
                    sdd._canonicalizar_nombre_paquete(entrada.get("nombre", ""))
                    for entrada in valor
                    if isinstance(entrada, dict)
                }
            )

    if not sets_restriccion:
        return dependencias_control

    resultado = []
    for entrada in dependencias_control:
        nombre_canonico = sdd._canonicalizar_nombre_paquete(entrada.get("nombre", ""))
        if all(nombre_canonico in permitidos for permitidos in sets_restriccion):
            resultado.append(entrada)
    return resultado


def _construir_spec_pip(nombre: str, version: str) -> str:
    """`'<nombre>==<versión>'`, el único token final que acepta
    `allowlist._evaluar_forma_dependency_install` (R24/R37: pin exacto, el
    rango aprobado NUNCA se serializa hacia pip -- acá ya se recibió una
    `version` exacta, no un rango)."""
    return f"{nombre}=={version}"


def _capturar_evidencia_entorno(nombre: str) -> dict:
    """Snapshot best-effort vía `importlib.metadata` (stdlib, sin dependencia
    nueva, R33/R38): versión previa instalada de `nombre` (`None` si no
    estaba instalado) + el set de nombres de distribuciones instaladas (para
    comparar pre/post, R39). Nunca lanza: cualquier error de
    `importlib.metadata` se trata como 'no determinable' (versión previa
    `None`, set vacío) -- no bloquea la instalación por un problema de
    lectura del entorno."""
    try:
        version_previa = importlib_metadata.version(nombre)
    except importlib_metadata.PackageNotFoundError:
        version_previa = None
    except Exception:  # noqa: BLE001 - best-effort, nunca bloquea
        version_previa = None

    try:
        distribuciones = {d.name for d in importlib_metadata.distributions() if d.name}
    except Exception:  # noqa: BLE001 - best-effort
        distribuciones = set()

    return {"version_previa": version_previa, "distribuciones": distribuciones}


def cmd_dependency_install(args: argparse.Namespace) -> int:
    """`ds_guard dependency install --change-id <id> --nombre <n> --version
    <v>` (M11, T3b-2 de 20260930-project-extension-and-installer-
    integration): clasifica ANTES de construir cualquier `ExecutionRequest`
    (R25), resuelve el intérprete del `.venv` del proyecto (R27/R34),
    construye el comando cerrado de 6 tokens (R24/R37) y lo ejecuta vía
    `_ejecutar_exec_comun` con `omitir_gate_por_artefacto=True` (reuso del
    runtime gobernado de Change 2, sin pasar por el gate de aprobación-por-
    artefacto genérico -- fix aplicado por el Lead tras el reporte del
    writer: sin esto, `supervised` quedaba denegado siempre, ver docstring
    de `_ejecutar_exec_comun`).

    Nota de diseño (deviación documentada respecto del pseudocódigo del
    encargo, ver reporte final): `approval_override` solo se construye como
    dict cuando el modo efectivo es `"supervised"` -- en `"autonomous"` se
    deja `None`. Motivo: `leadrun_core.ExecutionRecord` (Change 2, no
    tocado) exige `approval is None` cuando `mode == "autonomous"`
    (invariante ya usado por las otras 3 formas: en autonomous, `_resolver_
    aprobacion_exec` siempre devuelve `approval=None`) -- pasar el dict de
    `dependency_preapproval` incondicionalmente rompería esa invariante y
    haría fallar CADA instalación en modo autonomous (el caso de uso
    principal de M11), vía una excepción capturada silenciosamente por
    `leadrun_runtime.ejecutar` (`record=None`, `LEADRUN-RUNTIME` FAIL)."""
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    # R35: forma del nombre, ANTES de canonicalizar/clasificar.
    if not sdd.validar_forma_nombre_paquete(args.nombre):
        print(
            f"Nombre de paquete inválido o con forma no soportada: {args.nombre!r} "
            "(sin URL/path/VCS/extras/múltiples paquetes/metacaracteres).",
            file=sys.stderr,
        )
        return 2

    nombre_canonico = sdd._canonicalizar_nombre_paquete(args.nombre)

    # R26: dependencias_efectivas, con nombres canonicalizados en ambos
    # lados antes de clasificar (R36 -- clasificar_dependencia en sí NO
    # canonicaliza, recibe los valores ya canonicalizados).
    deps_efectivas = dependencias_efectivas(control, repo_root)
    deps_efectivas_canonicas = [
        {"nombre": sdd._canonicalizar_nombre_paquete(d.get("nombre", "")), "rango": d.get("rango", "")}
        for d in deps_efectivas
        if isinstance(d, dict)
    ]

    # R25: clasificación ANTES de construir cualquier ExecutionRequest.
    clasificacion = sdd.clasificar_dependencia(nombre_canonico, args.version, deps_efectivas_canonicas)
    if clasificacion != "no_stop":
        print(
            f"Dependencia rechazada (clasificación: {clasificacion}): "
            f"{args.nombre}=={args.version} no está pre-aprobada dentro del rango vigente.",
            file=sys.stderr,
        )
        return 2

    # R27/R34: intérprete construido por el runtime, NUNCA recibido libre
    # (este subcomando no tiene ningún flag --interpreter). Normalizado acá
    # mismo (`leadrun_allowlist.normalizar_interprete`): a diferencia de
    # `exec script/pytest/notebook` (donde el LLAMADOR humano/Lead ya pasa
    # `--interpreter` normalizado por convención, ver
    # `tools/tests/test_ds_guard_exec.py`), acá es `ds_guard.py` quien
    # construye el intérprete, así que es quien debe normalizarlo antes de
    # usarlo como `request.interpreter` -- si no, `evaluar_comando` compara
    # `argv[0]` YA normalizado internamente contra un `interprete_autorizado`
    # sin normalizar y rechaza por "intérprete no autorizado" pese a ser la
    # misma ruta (bug encontrado por test, corregido acá).
    leadrun_allowlist_mod = _importar_perezoso("leadrun", "allowlist")
    if leadrun_allowlist_mod is None:
        print(_mensaje_paquete_no_instalado("leadrun", "experiment"), file=sys.stderr)
        return 3
    venv_dir = launcher_common.resolver_venv_dir(repo_root)
    interprete = launcher_common.ruta_interprete_venv(repo_root, venv_dir)
    interprete_str = leadrun_allowlist_mod.normalizar_interprete(str(interprete))

    # R24/R37: argv fijo de 6 tokens, versión EXACTA (nunca el rango).
    spec = _construir_spec_pip(args.nombre, args.version)
    argv = [interprete_str, "-m", "pip", "install", "--no-deps", spec]

    # `modo` (para el ExecutionRecord) sin pasar por el gate de aprobación-
    # por-artefacto genérico (R25 ya autorizó esta acción puntual).
    modo, error_modo = _resolver_modo_autonomia(repo_root)
    if error_modo:
        print(f"No se pudo resolver el modo de autonomía: {error_modo}", file=sys.stderr)
        return 2

    # R28: approval compuesto acá, referencia a la pre-aprobación (sin
    # ApprovalRef nueva por instalación individual) -- solo en modo
    # supervised, ver docstring de esta función.
    approval_override = None
    if modo == "supervised":
        approval_override = {
            "tipo": "dependency_preapproval",
            "dependencia": {"nombre": args.nombre, "version": args.version},
            "declarado_en": "proposal.md",
        }

    # R38: evidencia de entorno PRE-instalación.
    evidencia_pre = _capturar_evidencia_entorno(args.nombre)

    artefacto = f"dependency:{nombre_canonico}"
    # `hash_comando` no se usa para ningún gate de aprobación en este
    # subcomando (ver `approval_override` arriba) -- se pasa igual a
    # `_ejecutar_exec_comun` porque su firma lo exige, con un valor
    # determinista y trazable (no un placeholder vacío).
    hash_comando = hashlib.sha256(spec.encode("utf-8")).hexdigest()

    # `_ejecutar_exec_comun` arma el `ExecutionRequest` a partir de
    # `args.interpreter`/`args.timeout` -- este subcomando no expone esos
    # flags al usuario (R31/R34), se inyectan acá con el valor ya resuelto /
    # el mismo default que ya usa `exec script` (`--timeout`, default 600).
    args.interpreter = interprete_str
    args.timeout = getattr(args, "timeout", None) or 600

    info_salida: dict = {}
    codigo_salida = _ejecutar_exec_comun(
        args,
        repo_root,
        control,
        control_path,
        "dependency_install",
        argv,
        artefacto,
        hash_comando,
        approval_override=approval_override,
        omitir_gate_por_artefacto=True,
        modo_resuelto=modo,
        info_salida=info_salida,
    )

    # R29/R38/R39 (hallazgo del reviewer T8, ciclo 2, corregido): antes, un
    # `codigo_salida != 0` retornaba ACÁ MISMO, saltando por completo la
    # revalidación (R29), la detección de instalaciones inesperadas (R39) y
    # la persistencia de evidencia (R38) -- exactamente el caso donde esa
    # evidencia importa más (una instalación que falló a mitad de camino,
    # posiblemente con efectos secundarios, es la que más necesita quedar
    # documentada para revisión humana). Ninguno de R38/R39/`tasks.md`
    # condiciona esta captura al éxito de la instalación. Ahora se captura
    # SIEMPRE que hubo una ejecución real (`record is not None` -- si
    # `_ejecutar_exec_comun` rechazó la solicitud ANTES de ejecutar nada,
    # por allowlist o infraestructura, no hay nada que capturar/persistir),
    # y el exit code devuelto al final sigue siendo el real de la
    # instalación, nunca enmascarado como éxito.
    record = info_salida.get("record")
    resultado_r29 = "ok"
    inesperadas: list = []
    if record is not None:
        evidencia_post = _capturar_evidencia_entorno(args.nombre)
        if codigo_salida != 0:
            resultado_r29 = "instalacion_fallida"
        elif evidencia_post["version_previa"] != args.version:
            resultado_r29 = "version_no_coincide"
            print(
                f"ADVERTENCIA (R29): versión efectivamente instalada "
                f"({evidencia_post['version_previa']!r}) no coincide con la solicitada "
                f"({args.version!r}) -- evidencia para revisión humana, instalación YA "
                "aplicada, no se revierte.",
                file=sys.stderr,
            )

        # R39: diferencia inesperada en el set de distribuciones instaladas
        # (más allá del propio paquete solicitado) -- reportada como
        # `CheckResult(kind=technical_error)`, SIN STOP nuevo.
        esperado = evidencia_pre["distribuciones"] | {nombre_canonico}
        inesperadas = sorted(
            {sdd._canonicalizar_nombre_paquete(d) for d in evidencia_post["distribuciones"]}
            - {sdd._canonicalizar_nombre_paquete(d) for d in esperado}
        )
        if inesperadas:
            resultado_check_r39 = checks.CheckResult(
                checks.STATUS_WARN,
                "DEPENDENCY-UNEXPECTED-INSTALL",
                f"--no-deps no evitó instalaciones adicionales inesperadas: {inesperadas} -- "
                "evidencia para revisión humana, sin STOP nuevo (R39).",
                kind=checks.KIND_TECHNICAL_ERROR,
            )
            _imprimir_check_results([resultado_check_r39], args.json, "dependency install (R39)")

        # R38: evidencia de entorno pre/post persistida, trazable junto a la
        # referencia de `ExecutionRecord` ya existente (R28).
        referencia_preaprobacion = approval_override or {
            "tipo": "dependency_preapproval",
            "dependencia": {"nombre": args.nombre, "version": args.version},
            "declarado_en": "proposal.md",
        }
        evidencia = {
            "paquete": args.nombre,
            "version_previa": evidencia_pre["version_previa"],
            "version_solicitada": args.version,
            "version_posterior": evidencia_post["version_previa"],
            "resultado": resultado_r29,
            "distribuciones_inesperadas": inesperadas,
            "referencia_preaprobacion": referencia_preaprobacion,
            "execution_id": record["execution_id"],
            "duration_seconds": record["duration_seconds"],
            "exit_code": record["exit_code"],
        }
        ruta_evidencia = (
            repo_root / ".harmessi" / "executions" / record["execution_id"] / "dependency_evidence.json"
        )
        ruta_evidencia.parent.mkdir(parents=True, exist_ok=True)
        core.escribir_texto_atomico(
            ruta_evidencia,
            json.dumps(evidencia, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )

    return codigo_salida


def cmd_dependency_classify(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    dependencias_preaprobadas = control.get("dependencias_preaprobadas", [])
    resultado = sdd.clasificar_dependencia(args.nombre, args.version, dependencias_preaprobadas)

    if args.json:
        print(json.dumps({"clasificacion": resultado}, ensure_ascii=False))
    else:
        print(resultado)
    return 0


# --- remediation --------------------------------------------------------------

def cmd_remediation_resolve(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    ok, findings = sdd.remediation_resolve(control, args.remediation_id, args.resultado)
    if not ok:
        _imprimir_findings(findings, 1, args.json)
        return 1

    core.escribir_control(control_path, control)
    if args.json:
        print(json.dumps({"remediation_id": args.remediation_id, "estado": "resuelta"}, ensure_ascii=False))
    else:
        print(f"Remediación resuelta: {args.remediation_id}")
    return 0


def cmd_remediation_extend(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    error_usuario = core.validar_usuario_sin_email(args.usuario)
    if error_usuario:
        print(error_usuario, file=sys.stderr)
        return 2
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    ok, findings, ventana = sdd.remediation_extend(
        control, args.remediation_id, args.usuario, args.fecha, args.motivo, max_intentos=args.max_intentos
    )
    if not ok:
        _imprimir_findings(findings, 1, args.json)
        return 1

    core.escribir_control(control_path, control)
    if args.json:
        print(json.dumps({"remediation_id": args.remediation_id, "ventana": ventana}, ensure_ascii=False))
    else:
        print(f"Ventana {ventana} agregada a la remediación {args.remediation_id}")
    return 0


# --- decision -------------------------------------------------------------

def cmd_decision_add(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    error_usuario = core.validar_usuario_sin_email(args.usuario)
    if error_usuario:
        print(error_usuario, file=sys.stderr)
        return 2

    ok, findings = decision.decision_add(
        repo_root,
        args.decision_id,
        args.tipo,
        args.resumen,
        args.rationale,
        args.usuario,
        args.fecha,
        args.cita,
        change_id=args.change_id,
        kdd_etapa=args.kdd_etapa,
        evidencia=args.evidencia,
    )
    if not ok:
        _imprimir_findings(findings, 2, args.json)
        return 2

    if args.json:
        print(json.dumps({"decision_id": args.decision_id, "accion": "registrar"}, ensure_ascii=False))
    else:
        print(f"Decisión registrada: {args.decision_id}")
    return 0


def cmd_decision_supersede(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    error_usuario = core.validar_usuario_sin_email(args.usuario)
    if error_usuario:
        print(error_usuario, file=sys.stderr)
        return 2

    ok, findings = decision.decision_supersede(
        repo_root,
        args.referencia,
        args.decision_id,
        args.tipo,
        args.resumen,
        args.rationale,
        args.usuario,
        args.fecha,
        args.cita,
        change_id=args.change_id,
        kdd_etapa=args.kdd_etapa,
        evidencia=args.evidencia,
    )
    if not ok:
        _imprimir_findings(findings, 2, args.json)
        return 2

    if args.json:
        print(
            json.dumps(
                {"decision_id": args.decision_id, "accion": "supersede", "referencia": args.referencia},
                ensure_ascii=False,
            )
        )
    else:
        print(f"Decisión {args.referencia} supersedida por {args.decision_id}")
    return 0


def cmd_decision_revoke(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    error_usuario = core.validar_usuario_sin_email(args.usuario)
    if error_usuario:
        print(error_usuario, file=sys.stderr)
        return 2

    ok, findings = decision.decision_revoke(
        repo_root, args.referencia, args.motivo, args.usuario, args.fecha
    )
    if not ok:
        _imprimir_findings(findings, 2, args.json)
        return 2

    if args.json:
        print(json.dumps({"accion": "revocar", "referencia": args.referencia}, ensure_ascii=False))
    else:
        print(f"Decisión revocada: {args.referencia}")
    return 0


def cmd_decision_list(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3

    entradas, findings = decision.decision_list(
        repo_root, tipo=args.tipo, estado=args.estado, change_id=args.change_id
    )
    if args.json:
        print(
            json.dumps(
                {"decisiones": entradas, "findings": [f.to_dict() for f in findings]},
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        for f in findings:
            print(f"  [{f.codigo}] {f.mensaje}")
        for e in entradas:
            print(f"{e.get('decision_id')} [{e.get('tipo')}] estado={e.get('estado')}: {e.get('resumen')}")
    return 0


def cmd_decision_show(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3

    entrada, findings = decision.decision_show(repo_root, args.decision_id)
    if entrada is None:
        _imprimir_findings(findings, 1, args.json)
        return 1

    if args.json:
        print(json.dumps({"decision": entrada, "findings": [f.to_dict() for f in findings]}, indent=2, ensure_ascii=False))
    else:
        for clave, valor in entrada.items():
            print(f"{clave}: {valor}")
        for f in findings:
            print(f"  [{f.codigo}] {f.mensaje}")
    return 0


# --- notebook-diff -----------------------------------------------------------

def cmd_notebook_diff(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    estado, err_estado = sdd.read_estado(tasks_path)

    if args.tocados:
        rutas = [r for r in repo.list_dirty_files(repo_root) if r.endswith(".ipynb")]
    else:
        rutas = list(args.path or [])
    if not rutas:
        print("Debe indicar --path (repetible) o --tocados", file=sys.stderr)
        return 2

    if args.contra == "baseline":
        rev = control.get("baseline", {}).get("commit")
        if not rev:
            print("No hay baseline.commit registrado en control.json", file=sys.stderr)
            return 2
    else:
        rev = args.contra

    bloqueantes = list(err_estado)
    informativos = []
    resumen_total = []
    conteos_total = {"agregadas": 0, "eliminadas": 0, "modificadas": 0, "solo_ejecucion": 0}

    for ruta in rutas:
        resultado = notebooks.diff_archivo(repo_root, ruta, rev, estado)
        if resultado.get("error_uso") is not None:
            print(resultado["error_uso"].mensaje, file=sys.stderr)
            return 2
        bloqueantes += resultado["bloqueantes"]
        informativos += resultado["informativos"]
        resumen_total += resultado["resumen"]
        for clave in conteos_total:
            conteos_total[clave] += resultado["conteos"].get(clave, 0)

    recorte = None
    if len(resumen_total) > args.max_celdas:
        recorte = {"mostradas": args.max_celdas, "totales": len(resumen_total)}
        resumen_total = resumen_total[: args.max_celdas]

    exit_code = 1 if bloqueantes else 0
    todos = bloqueantes + informativos

    if args.json:
        payload = {
            "findings": [f.to_dict() for f in todos],
            "exit_code": exit_code,
            "conteos": conteos_total,
            "resumen_celdas": resumen_total,
            "recorte": recorte,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(core.formatear_findings_texto(todos))
        print(
            f"{conteos_total['agregadas']} celdas agregadas, "
            f"{conteos_total['eliminadas']} eliminadas, "
            f"{conteos_total['modificadas']} celdas modificadas, "
            f"{conteos_total['solo_ejecucion']} solo_ejecucion"
        )
        if recorte:
            print(
                f"Recortado: se muestran {recorte['mostradas']} de "
                f"{recorte['totales']} celdas cambiadas"
            )

    return exit_code


# --- science (v0.4 Change 0: 20260916-kdd-enforceable-checks) ----------------

def cmd_science_status(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    resultados = scientific_validity.evaluar_scientific_checks(repo_root)
    if args.json:
        print(json.dumps({"resultados": [r.to_dict() for r in resultados]}, ensure_ascii=False))
    else:
        print("Scientific Validity\n")
        for r in resultados:
            print(f"{r.status:<6} {r.code}: {r.message}")
        conteos = checks.contar_por_status(resultados)
        print(f"\nResumen: {conteos[checks.STATUS_PASS]} PASS, {conteos[checks.STATUS_WARN]} WARN, "
              f"{conteos[checks.STATUS_FAIL]} FAIL, {conteos[checks.STATUS_NA]} N/A")
    return checks.exit_code(resultados)


# --- efficiency (v0.4 Change 4: 20260916-agent-efficiency-and-token-governance) --

def cmd_efficiency_report(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    resultados = efficiency.evaluar_eficiencia_change(repo_root, args.change_id)
    if args.json:
        print(json.dumps({"resultados": [r.to_dict() for r in resultados]}, ensure_ascii=False))
    else:
        print(f"Agent Efficiency Report -- {args.change_id}\n")
        for r in resultados:
            print(f"{r.status:<6} {r.code}: {r.message}")
        conteos = checks.contar_por_status(resultados)
        print(f"\nResumen: {conteos[checks.STATUS_PASS]} PASS, {conteos[checks.STATUS_WARN]} WARN, "
              f"{conteos[checks.STATUS_FAIL]} FAIL, {conteos[checks.STATUS_NA]} N/A")
    return checks.exit_code(resultados)


# --- impact scan (v0.4 Change 1: 20260916-impact-preflight) ----------------

def _importar_dsimpact():
    """Import perezoso opcional de `tools.dsimpact` -- mismo patrón que
    `dsguard.status._importar_doctor`: prueba ambas formas de import, nunca
    un import a nivel de archivo (ver `design.md` §4 del change: `dsimpact`
    se instala solo desde `stage_minimo="experiment"`, pero `ds_guard.py` se
    instala siempre desde discovery). Nunca deja escapar una excepción."""
    try:
        from dsimpact import scan as dsimpact_scan  # type: ignore
        return dsimpact_scan
    except Exception:  # noqa: BLE001 - degradación con gracia, nunca excepción cruda
        pass
    try:
        from tools.dsimpact import scan as dsimpact_scan  # type: ignore
        return dsimpact_scan
    except Exception:  # noqa: BLE001
        return None


def cmd_impact_scan(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    dsimpact_scan = _importar_dsimpact()
    if dsimpact_scan is None:
        print(
            "impact preflight no está instalado en este stage -- correr "
            "'ds_init sync --stage experiment --execute' (tools/dsimpact/ requiere stage experiment).",
            file=sys.stderr,
        )
        return 3
    try:
        resultado = dsimpact_scan.ejecutar_scan(repo_root, args.since, args.staged)
    except Exception as e:  # noqa: BLE001 - GitSourceError u otro, nunca traceback crudo
        print(str(e), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
    else:
        try:
            from dsimpact import cli as dsimpact_cli  # type: ignore
        except Exception:  # noqa: BLE001
            from tools.dsimpact import cli as dsimpact_cli  # type: ignore
        print(dsimpact_cli.formatear_texto(resultado))
    return 0


# --- contract / quality (v0.7 Change 4: 20260922-quality-integration-and-cli) --
#
# Subcomandos delgados: cada `cmd_*` parsea argumentos, carga JSON de disco,
# llama UNA función pública del paquete correspondiente (`tools.datacontracts`,
# `tools.modelquality`, `tools.qualityevidence`, `tools.dsimpact`), y formatea
# la salida -- CERO lógica de dominio acá (R3 de spec.md). Import perezoso
# opcional dentro de cada función, mismo patrón EXACTO que `_importar_dsimpact`
# (dos formas de import, nunca deja escapar una excepción, degradación con
# exit code 3 si el paquete no está instalado en el stage actual).
#
# STOP explícito (ver tasks.md de ese Change): ningún resultado de
# `contract`/`quality` condiciona `project readiness`/`project promote`, el
# exit code de `status`, ni el lifecycle, bajo ninguna circunstancia.

def _importar_perezoso(paquete: str, modulo: str):
    """Import perezoso opcional de `<paquete>.<modulo>` (si `tools/` ya está
    en `sys.path[0]`, como ocurre al invocar este archivo directamente) o
    `tools.<paquete>.<modulo>` (invocación como `python -m tools.ds_guard`) --
    mismo patrón de dos formas que `_importar_dsimpact`. Nunca deja escapar
    una excepción: `None` si ninguna de las dos formas importa."""
    try:
        return __import__(f"{paquete}.{modulo}", fromlist=[modulo])
    except Exception:  # noqa: BLE001 - degradación con gracia, nunca excepción cruda
        pass
    try:
        return __import__(f"tools.{paquete}.{modulo}", fromlist=[modulo])
    except Exception:  # noqa: BLE001
        return None


def _mensaje_paquete_no_instalado(paquete: str, stage_minimo: str) -> str:
    return (
        f"{paquete} no está instalado en este stage -- correr "
        f"'ds_init sync --stage {stage_minimo} --execute' (tools/{paquete}/ requiere stage {stage_minimo})."
    )


def _cargar_json(ruta_str: str):
    """`(datos, error_mensaje)`. `error_mensaje` no es `None` si el archivo no
    existe, no es legible, o no es JSON válido -- nunca lanza."""
    ruta = Path(ruta_str)
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"No se pudo leer {ruta_str}: {type(exc).__name__}"
    try:
        return json.loads(texto), None
    except json.JSONDecodeError as exc:
        return None, f"{ruta_str} no contiene JSON válido: {exc}"


def _imprimir_check_results(resultados: list, como_json: bool, titulo: str) -> None:
    if como_json:
        print(json.dumps({"resultados": [r.to_dict() for r in resultados]}, ensure_ascii=False))
        return
    print(f"{titulo}\n")
    for r in resultados:
        subject = f" [{r.subject}]" if r.subject else ""
        print(f"{r.status:<6} {r.code}{subject}: {r.message}")
    conteos = checks.contar_por_status(resultados)
    print(
        f"\nResumen: {conteos[checks.STATUS_PASS]} PASS, {conteos[checks.STATUS_WARN]} WARN, "
        f"{conteos[checks.STATUS_FAIL]} FAIL, {conteos[checks.STATUS_NA]} N/A"
    )


def _registrar_evidencia_calidad(
    repo_root: Path,
    *,
    subject_kind: str,
    declaration_kind: str,
    declaration_id: str,
    declaration_version,
    content_sha256: str,
    fuente_path: str,
    fuente_role: str,
    resultados: list,
):
    """`(evidence_id, error_mensaje)`. Import perezoso de
    `tools.qualityevidence.{core,evidence}`; `error_mensaje` no es `None` si
    el paquete no está instalado o la escritura falla -- nunca lanza."""
    qe_core = _importar_perezoso("qualityevidence", "core")
    qe_evidence = _importar_perezoso("qualityevidence", "evidence")
    if qe_core is None or qe_evidence is None:
        return None, _mensaje_paquete_no_instalado("qualityevidence", "experiment")
    try:
        fuente = qe_evidence.describe_source_file(repo_root, fuente_path, role=fuente_role)
        declaracion = qe_core.DeclarationRef(
            declaration_kind=declaration_kind,
            declaration_id=declaration_id,
            version=declaration_version,
            content_sha256=content_sha256,
        )
        manifest = qe_evidence.build_manifest(
            subject_kind=subject_kind, declaration=declaracion, source=fuente, results=resultados
        )
        qe_evidence.write_manifest(repo_root, manifest)
        return manifest.evidence_id, None
    except qe_core.QualityEvidenceError as exc:
        return None, str(exc)


# --- exec (v0.8 Change 2 T6: 20260929-lead-execution-runtime) --------------
#
# Subcomandos `exec script|pytest|notebook`: componen `leadrun.core`/
# `leadrun.allowlist`/`leadrun.runtime` (T1-T5, YA IMPLEMENTADOS) con la
# aprobación (`execute_project_code` x modo, R12/R14 de spec.md). Mismo
# patrón de composición que `_access_check_real` (Change 1 T6): imports
# perezosos, fail-closed, nunca lanza.

def _resolver_modo_autonomia(repo_root: Path) -> tuple:
    """`(modo, error_motivo)`. `error_motivo` es `None` si se resolvió
    correctamente (incluido el caso 'autonomy no declarada -> supervised por
    default'); un string no vacío si hubo un fallo de infraestructura real
    (guardrails.json ilegible/corrupto/versión no soportada, o 'autonomy'
    declarada pero `tools.autonomy` no instalado) -- en ese caso `modo` es
    `"supervised"` (fail-closed) pero el llamador debe tratarlo como un
    fallo bloqueante, no como un 'supervised normal'. Extraído de la primera
    mitad de `_resolver_aprobacion_exec` (Change 2/3) como refactor puro,
    sin cambiar su comportamiento externo -- reusado acá por
    `cmd_dependency_install` (R25: no pasa por el gate de aprobación-por-
    artefacto genérico, pero sí necesita `modo` para el `ExecutionRecord` y
    para no ocultar un fallo real de infraestructura)."""
    pathguard_mod = _importar_perezoso("dsguard", "pathguard")
    if pathguard_mod is None:
        return "supervised", "tools.dsguard.pathguard no disponible: denegado (fail-closed)"

    try:
        pathguard_mod.cargar_config(repo_root)
    except pathguard_mod.ConfigGuardrailsError as exc:
        return "supervised", f"guardrails.json inválido o versión no soportada: {exc}"

    ruta_config = Path(repo_root) / pathguard_mod.RUTA_CONFIG_RELATIVA
    guardrails_dict: dict = {}
    if ruta_config.exists():
        try:
            guardrails_dict = json.loads(ruta_config.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return "supervised", f"guardrails.json ilegible: {type(exc).__name__}"
        if not isinstance(guardrails_dict, dict):
            return "supervised", "guardrails.json no contiene un objeto JSON: denegado"

    if "autonomy" not in guardrails_dict:
        modo = "supervised"
    else:
        autonomy_mod = _importar_perezoso("autonomy", "policy")
        autonomy_core_mod = _importar_perezoso("autonomy", "core")
        if autonomy_mod is None or autonomy_core_mod is None:
            return "supervised", (
                "guardrails.json declara 'autonomy' pero tools.autonomy no está "
                "instalado en este stage: denegado (fail-closed)"
            )
        policy, _hallazgos = autonomy_mod.parse_autonomy_policy(
            guardrails_dict, pathguard_mod.POLICY_VERSION_MAX
        )
        modo = policy.mode

    return modo, None


def _resolver_aprobacion_exec(
    repo_root: Path,
    control_data: dict,
    artefacto: str,
    hash_comando: str,
    hash_legacy: "Optional[str]" = None,
):
    """Devuelve `(permitido, executed_by, mode, approval, motivo)` (R12/R14).

    `hash_legacy` (R9b/D5 de `20261002-exec-approval-registration`, solo
    `exec script`): si la aprobación no es vigente con `hash_comando` (v2) y
    la entrada MÁS RECIENTE del artefacto tiene `algoritmo == "sha256/lf/v1"`,
    se acepta también `hash_legacy` (hash solo del contenido del script). Una
    entrada v2 (u otra) con hash distinto NO cae al camino legacy. La
    aprobación legacy se reporta solo por stderr; `approval` es el mismo dict
    que la aprobación v2 (sin marca `legacy`).

    - `pathguard.cargar_config` inválido/versión no soportada -> denegado
      (fail-closed, mismo criterio que `_access_check_real`).
    - `autonomy` no declarada en el guardrails.json crudo -> modo efectivo
      `"supervised"` (default).
    - `autonomy` declarada pero `tools.autonomy` no instalado -> denegado
      (fail-closed).
    - `resolve_action("execute_project_code", modo)`: `autonomous` ejecuta
      sin aprobación por corrida; `supervised` exige aprobación humana
      vigente registrada en `control.json` (vía
      `nbrunner.manifest.validar_aprobacion`, `modo="execute"` siempre).
    - Nunca lanza (fail-closed ante cualquier error inesperado)."""
    try:
        modo, error_modo = _resolver_modo_autonomia(repo_root)
        if error_modo is not None:
            return False, None, modo, None, error_modo

        autonomy_core_mod = _importar_perezoso("autonomy", "core")
        if autonomy_core_mod is None:
            return False, None, modo, None, "tools.autonomy.core no disponible: denegado (fail-closed)"

        decision = autonomy_core_mod.resolve_action("execute_project_code", modo)

        if decision.executor == "lead" and decision.approval == "none":
            return True, "lead", modo, None, "autonomous: sin aprobación por corrida"

        if decision.approval == "human":
            nbrunner_manifest = _importar_perezoso("nbrunner", "manifest")
            if nbrunner_manifest is None:
                return False, None, modo, None, "tools.nbrunner.manifest no disponible: denegado (fail-closed)"
            findings, estado = nbrunner_manifest.validar_aprobacion(
                control_data or {}, artefacto, hash_comando, modo="execute"
            )
            if estado == "vigente":
                return True, "human", modo, {"tipo": "human_manifest_aprobado"}, ""
            if hash_legacy is not None:
                reciente = nbrunner_manifest._aprobacion_mas_reciente(control_data or {}, artefacto)
                # `sha256/argv-canonical-json`: legacy de `exec pytest` con intérprete crudo (I6).
                if reciente is not None and reciente.get("algoritmo") in (
                    "sha256/lf/v1",
                    "sha256/argv-canonical-json",
                ):
                    _f_legacy, estado_legacy = nbrunner_manifest.validar_aprobacion(
                        control_data or {}, artefacto, hash_legacy, modo="execute"
                    )
                    if estado_legacy == "vigente":
                        print(
                            "aprobación legacy (sha256/lf/v1): no liga argumentos; "
                            "re-aprobar con 'ds_guard exec approve script'",
                            file=sys.stderr,
                        )
                        # El aviso legacy va solo a stderr: `approval` no lleva marca `legacy`
                        # (la suite preexistente de exec exige exactamente este dict).
                        return True, "human", modo, {"tipo": "human_manifest_aprobado"}, ""
            return False, None, modo, None, f"aprobación {estado} para {artefacto!r}"

        return False, None, modo, None, f"composición de aprobación no soportada: {decision!r}"
    except Exception as exc:  # noqa: BLE001 - fail-closed ante cualquier error inesperado
        return False, None, "supervised", None, f"error inesperado resolviendo aprobación ({type(exc).__name__}): denegado"


def _leadrun_modulos():
    """`(leadrun_core, leadrun_allowlist, leadrun_runtime)` o `(None, None,
    None)` si el paquete no está instalado en este stage. Import perezoso,
    mismo patrón que `_importar_perezoso` pero para los 3 módulos a la vez
    (siempre se usan juntos en los subcomandos `exec`)."""
    leadrun_core = _importar_perezoso("leadrun", "core")
    leadrun_allowlist = _importar_perezoso("leadrun", "allowlist")
    leadrun_runtime = _importar_perezoso("leadrun", "runtime")
    if leadrun_core is None or leadrun_allowlist is None or leadrun_runtime is None:
        return None, None, None
    return leadrun_core, leadrun_allowlist, leadrun_runtime


def _capturar_fingerprints_fuentes_externas(repo_root: Path) -> dict:
    """Fingerprint tamaño+mtime de TODAS las fuentes declaradas en
    `fuentes_externas` (M9/M10, `.harmessi/local-overrides.json`) -- R14 de
    M12 (`20260930-project-extension-and-installer-integration`). Sin hash de
    contenido en esta versión (deuda explícita documentada, R14 lo permite:
    "nunca por default"). `{}` si no hay ninguna fuente declarada (cero
    overhead). Cada entrada: `{"existe": True, "size": int, "mtime": float}`
    si el archivo existe y es legible; `{"existe": False}` si no (el archivo
    desapareció -- también es información relevante para R15)."""
    fuentes = pathguard.leer_fuentes_externas_declaradas(repo_root)
    resultado: dict = {}
    for source_id, declaracion in fuentes.items():
        if not isinstance(declaracion, dict):
            continue
        ruta_str = declaracion.get("path")
        if not isinstance(ruta_str, str) or not ruta_str:
            continue
        ruta = Path(ruta_str)
        try:
            if not ruta.exists():
                resultado[source_id] = {"existe": False}
                continue
            stat = ruta.stat()
            resultado[source_id] = {"existe": True, "size": stat.st_size, "mtime": stat.st_mtime}
        except OSError:
            resultado[source_id] = {"existe": False}
    return resultado


def _comparar_fingerprints(pre: dict, post: dict) -> list:
    """Compara fingerprints pre/post (R15): devuelve una lista de
    `(source_id, detalle_str)` para cada fuente cuyo fingerprint cambió
    (tamaño, mtime, o existencia). Vacía si no hubo ningún cambio."""
    discrepancias = []
    for source_id, valor_pre in pre.items():
        valor_post = post.get(source_id, {"existe": False})
        if valor_pre != valor_post:
            discrepancias.append((source_id, f"antes={valor_pre!r} despues={valor_post!r}"))
    return discrepancias


def _validar_request_exec(args: argparse.Namespace, command_form: str, argv: list, control: dict, timeout=None):
    """Arma el `ExecutionRequest` y evalúa la allowlist (R6 de
    `20261002-exec-approval-registration`). Devuelve `(request, codigo)`:
    `codigo` es `None` si todo es válido; si no, ya se imprimió el mensaje a
    stderr y `codigo` es el exit code (2). Compartido por
    `_ejecutar_exec_comun` y `exec approve` (lo que el runtime rechazaría no
    puede aprobarse). `timeout=None` usa `args.timeout` si existe, o 600
    (default de `exec`) en `exec approve`, que no tiene `--timeout`."""
    leadrun_core, leadrun_allowlist, _leadrun_runtime = _leadrun_modulos()
    if leadrun_core is None:
        print(_mensaje_paquete_no_instalado("leadrun", "experiment"), file=sys.stderr)
        return None, 3

    scope = tuple(control.get("alcance", {}).get("rutas_autorizadas", []))
    if timeout is None:
        timeout = getattr(args, "timeout", 600)

    try:
        request = leadrun_core.ExecutionRequest(
            command_form=command_form,
            interpreter=args.interpreter,
            argv=tuple(argv),
            scope=scope,
            timeout_seconds=timeout,
        )
    except leadrun_core.ExecutionError as exc:
        print(str(exc), file=sys.stderr)
        return None, 2

    permitido_forma, _forma, motivo_forma = leadrun_allowlist.evaluar_comando(
        request.argv, request.scope, request.interpreter
    )
    if not permitido_forma:
        print(f"Comando rechazado por la allowlist: {motivo_forma}", file=sys.stderr)
        return None, 2
    return request, None


def _ejecutar_exec_comun(
    args: argparse.Namespace,
    repo_root: Path,
    control: dict,
    control_path: Path,
    command_form: str,
    argv: list,
    artefacto: str,
    hash_comando,
    approval_override: "Optional[dict]" = None,
    omitir_gate_por_artefacto: bool = False,
    modo_resuelto: "Optional[str]" = None,
    info_salida: "Optional[dict]" = None,
    hash_legacy: "Optional[str]" = None,
) -> int:
    """Pasos 4-9 comunes a `exec script|pytest|notebook` (ver encargo del
    Lead): construye el `ExecutionRequest`, evalúa la allowlist (defensa en
    profundidad #1: si rechaza, exit 2 SIN evaluar aprobación ni ejecutar),
    resuelve la aprobación (`_resolver_aprobacion_exec`) y, si está
    permitido, delega en `leadrun.runtime.ejecutar`.

    `approval_override`/`omitir_gate_por_artefacto` (T3b-2, M11 `dependency
    install`, R25/R28 -- corrección post-reporte del hallazgo #3 del writer:
    el gate por-artefacto de `_resolver_aprobacion_exec` exige, en
    `supervised`, una aprobación humana registrada vía `nbrunner_manifest.
    validar_aprobacion` para `artefacto` -- mecanismo pensado para archivos
    reales del repo (`cmd_approve` exige que `artefacto` exista como archivo
    bajo `change_dir`), no aplicable a un par nombre/versión de dependencia.
    Sin este bypass, `dependency install` quedaría denegado SIEMPRE en
    `supervised`, aunque la dependencia esté pre-aprobada y clasifique
    `no_stop` -- contradice R25 ("la clasificación autoriza la acción").
    Cuando `omitir_gate_por_artefacto=True`: NO se llama a
    `_resolver_aprobacion_exec` en absoluto (ni su rama de aprobación humana
    ni su rama autonomous) -- en cambio, `modo` se resuelve vía
    `_resolver_modo_autonomia` (mismo helper, sin la rama de aprobación-por-
    artefacto), `executed_by` queda fijo en `"lead"` (esta forma nunca la
    ejecuta un humano) y `approval` es directamente `approval_override` (el
    llamador, `cmd_dependency_install`, ya decidió su contenido -- `None` en
    autonomous por la invariante de `ExecutionRecord`, el dict de
    `dependency_preapproval` en supervised). Un error de infraestructura real
    de `_resolver_modo_autonomia` (guardrails.json corrupto, `tools.autonomy`
    no instalado) SIGUE bloqueando (exit 2), no se oculta. Ningún call site
    existente (`cmd_exec_script`/`cmd_exec_pytest`/`cmd_exec_notebook`) pasa
    `omitir_gate_por_artefacto=True` -- default `False`, cero cambio de
    comportamiento para esas 3 formas (que siguen pasando por el gate
    genérico completo, incluida la rama de aprobación humana en
    supervised).

    `modo_resuelto` (hallazgo #3 del reviewer T8, corregido): cuando
    `omitir_gate_por_artefacto=True` Y el llamador ya resolvió `modo` por su
    cuenta (p. ej. `cmd_dependency_install`, que necesita conocerlo ANTES de
    esta llamada para decidir el contenido de `approval_override`), se lo
    pasa acá en vez de dejar que esta función lo vuelva a resolver -- evita
    una doble llamada a `_resolver_modo_autonomia` y la ventana TOCTOU
    teórica que eso abría (si `guardrails.json` cambiara entre ambas
    resoluciones, `approval_override` podría quedar construido para un modo
    distinto del que finalmente se usa). Si es `None` (default), se resuelve
    acá como antes -- backward compatible.

    `info_salida` (hallazgo #2 del reviewer T8, R38): dict mutable opcional
    que el llamador provee para recibir de vuelta `{"record": ...}` (la
    misma forma que `leadrun_runtime.ejecutar` devuelve) sin cambiar el tipo
    de retorno de esta función (sigue siendo `int`, el exit code) -- usado
    por `cmd_dependency_install` para persistir evidencia de entorno junto
    al `execution_id` real (R38), sin tener que recalcularlo de forma
    duplicada/frágil."""
    leadrun_core, leadrun_allowlist, leadrun_runtime = _leadrun_modulos()
    if leadrun_core is None:
        print(_mensaje_paquete_no_instalado("leadrun", "experiment"), file=sys.stderr)
        return 3

    request, codigo_request = _validar_request_exec(args, command_form, argv, control, timeout=args.timeout)
    if codigo_request is not None:
        return codigo_request

    if omitir_gate_por_artefacto:
        if modo_resuelto is not None:
            modo = modo_resuelto
        else:
            modo, error_modo = _resolver_modo_autonomia(repo_root)
            if error_modo is not None:
                print(f"Aprobación denegada: {error_modo}", file=sys.stderr)
                return 2
        executed_by = "lead"
        approval = approval_override
    else:
        permitido_aprob, executed_by, modo, approval, motivo_aprob = _resolver_aprobacion_exec(
            repo_root, control, artefacto, hash_comando, hash_legacy
        )
        if not permitido_aprob:
            print(f"Aprobación denegada: {motivo_aprob}", file=sys.stderr)
            return 2

        if approval_override is not None:
            approval = approval_override

    # Fingerprint pre-ejecución de fuentes externas declaradas (R14 de M12,
    # `20260930-project-extension-and-installer-integration`): captura ANTES
    # de invocar el runtime, compuesto acá mismo (no toca `tools/leadrun/`).
    # `{}` (cero overhead) si no hay ninguna fuente declarada.
    fingerprints_pre = _capturar_fingerprints_fuentes_externas(repo_root)

    resultado = leadrun_runtime.ejecutar(request, repo_root, executed_by, modo, approval, control)

    # Métricas de eficiencia writer -> Lead (adenda post-cierre 2026-09-30,
    # punto 3 de "Corrección y adenda post-cierre" de `docs/roadmap/v0.8.md`):
    # referencia LIVIANA a la ejecución (no duplica el `ExecutionRecord`
    # completo, ya persistido por `leadrun_runtime.ejecutar` en
    # `.harmessi/executions/`) -- solo `execution_id`/`duration_seconds` (del
    # `record` ya devuelto) + `command_form` (ya disponible como parámetro).
    # Responsabilidad de `ds_guard.py` (Change 3): NO toca
    # `tools/leadrun/core.py`/`runtime.py` (Change 2, cerrado). Se persiste
    # acá porque, antes de este fix, ningún punto de `_ejecutar_exec_comun`
    # escribía `control.json` (discrepancia encontrada y corregida durante
    # esta misma tarea).
    #
    # Límite honesto (hallazgo de revisión, documentado, no resuelto con un
    # mecanismo nuevo): `control` se carga una sola vez al inicio de esta
    # función y se reescribe recién acá, después de que `leadrun_runtime.
    # ejecutar` termina -- una ventana que puede durar hasta
    # `request.timeout_seconds` (minutos), mucho más larga que la de
    # cualquier otro comando de este archivo (todos hacen lectura-
    # modificación-escritura casi instantánea). `escribir_control` es
    # atómico (tmp + `os.replace`, `tools/dsguard/core.py`) pero NO tiene
    # locking entre procesos: si otra invocación de `ds_guard` escribe
    # `control.json` durante esa ventana, esta escritura la pisaría (lost
    # update) por operar sobre una copia en memoria desactualizada. El
    # modelo operativo real de Harmessi es un único Lead invocando el CLI
    # de forma serial (sin orquestación multi-proceso propia), lo que hace
    # este riesgo poco probable en la práctica, pero no imposible si un
    # subagente concurrente también invoca `ds_guard` mientras el Lead
    # corre una ejecución larga -- mismo criterio de "límite honesto,
    # documentado, no resuelto" que subagentes concurrentes (R13) o timeout
    # de proceso huérfano (Change 2, R10); no se agrega un lock de archivo
    # nuevo para esto.
    if resultado.get("record") is not None:
        ejecuciones = control.setdefault("metricas_eficiencia", {}).setdefault("ejecuciones", [])
        ejecuciones.append(
            {
                "execution_id": resultado["record"]["execution_id"],
                "duration_seconds": resultado["record"]["duration_seconds"],
                "command_form": command_form,
            }
        )
        core.escribir_control(control_path, control)

    # Fingerprint post-ejecución (R15 de M12): recalculado solo si había algo
    # declarado (`fingerprints_pre` no vacío -- cero overhead si no hay
    # fuentes externas declaradas). Si `tools.autonomy.core` no está
    # disponible en este stage, se omite todo el chequeo de integridad --
    # fail-open para este DIAGNÓSTICO post-hoc (no para la ejecución: la
    # ejecución ya ocurrió, esto es evidencia adicional, no un gate).
    if fingerprints_pre:
        autonomy_core_mod = _importar_perezoso("autonomy", "core")
        if autonomy_core_mod is not None:
            fingerprints_post = _capturar_fingerprints_fuentes_externas(repo_root)
            discrepancias = _comparar_fingerprints(fingerprints_pre, fingerprints_post)
            if discrepancias and resultado.get("record") is not None:
                codigo_data_loss_risk = next(
                    e.code for e in autonomy_core_mod.STOP_CATALOG if e.key == "data_loss_risk"
                )
                for source_id, detalle in discrepancias:
                    resultado["checks"].append(
                        checks.CheckResult(
                            checks.STATUS_FAIL,
                            codigo_data_loss_risk,
                            f"La fuente externa {source_id!r} cambió durante la ventana "
                            f"gobernada de esta ejecución ({detalle}) -- evidencia para "
                            "revisión humana, no una afirmación de causalidad (pudo "
                            "cambiarla un proceso externo).",
                        ).to_dict()
                    )
                # R16: evidencia LOCAL junto al `ExecutionRecord`, nunca
                # portable (nunca en `DataContract`/`SourceObservation`).
                execution_id = resultado["record"]["execution_id"]
                ruta_fingerprints = (
                    repo_root / ".harmessi" / "executions" / execution_id / "fingerprints.json"
                )
                ruta_fingerprints.parent.mkdir(parents=True, exist_ok=True)
                core.escribir_texto_atomico(
                    ruta_fingerprints,
                    json.dumps(
                        {
                            "pre": fingerprints_pre,
                            "post": fingerprints_post,
                            "discrepancias": dict(discrepancias),
                        },
                        indent=2,
                        sort_keys=True,
                        ensure_ascii=False,
                    )
                    + "\n",
                )

    # `resultado["checks"]` son dicts (`CheckResult.to_dict()`); se
    # reconstruyen como `CheckResult` para reusar `_imprimir_check_results`/
    # `checks.exit_code` sin duplicar esa lógica de formateo/exit code.
    resultados_check = [
        checks.CheckResult(
            status=d["status"],
            code=d["code"],
            message=d["message"],
            detail=d.get("detail"),
            subject=d.get("subject"),
            kind=d.get("kind", checks.KIND_CHECK),
        )
        for d in resultado["checks"]
    ]

    if args.json:
        payload = {"resultados": [r.to_dict() for r in resultados_check]}
        if resultado.get("record") is not None:
            payload["execution_id"] = resultado["record"]["execution_id"]
        print(json.dumps(payload, ensure_ascii=False))
    else:
        _imprimir_check_results(resultados_check, False, f"exec {command_form}")
        if resultado.get("record") is not None:
            print(f"\nexecution_id: {resultado['record']['execution_id']}")

    if info_salida is not None:
        info_salida["record"] = resultado.get("record")

    return checks.exit_code(resultados_check)


ALGORITMO_EXEC_SCRIPT_V2 = "sha256/script-content+argv/v2"


class ExecSpec(NamedTuple):
    """Resultado de un builder `_construir_exec_<forma>` (D1 de
    `20261002-exec-approval-registration`): todo lo que `exec` y `exec
    approve` necesitan para ejecutar / registrar la MISMA identidad.
    `hash_legacy` solo aplica a script (R9b): hash histórico solo-contenido."""

    forma: str
    argv: list
    artefacto: str
    hash_comando: str
    algoritmo: str
    hash_legacy: "Optional[str]" = None


class _ErrorExec(Exception):
    """Error de construcción de un `ExecSpec`: mensaje para stderr + exit code."""

    def __init__(self, mensaje: str, codigo: int = 2):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo


def _modulos_leadrun_o_error():
    modulos = _leadrun_modulos()
    if modulos[0] is None:
        raise _ErrorExec(_mensaje_paquete_no_instalado("leadrun", "experiment"), 3)
    return modulos


def _construir_exec_script(args: argparse.Namespace, repo_root: Path) -> ExecSpec:
    """Builder puro de `exec script` (R9, M1: hash v2 contenido+argv)."""
    leadrun_core, leadrun_allowlist, _rt = _modulos_leadrun_o_error()

    args_extra = list(args.script_args or [])
    if args_extra and args_extra[0] == "--":
        args_extra = args_extra[1:]
    argv = [args.interpreter, args.script, *args_extra]

    try:
        hash_contenido = core.hash_lf_v1(Path(repo_root) / args.script)
    except (OSError, UnicodeDecodeError) as exc:
        raise _ErrorExec(f"No se pudo calcular el hash del script {args.script!r}: {exc}", 2)

    ruta_script = Path(args.script)
    if ruta_script.is_absolute():
        try:
            ruta_script = ruta_script.relative_to(Path(repo_root))
        except ValueError:
            pass  # fuera del repo: la allowlist lo rechaza igual; se hashea tal cual
    identidad = {
        "algorithm": ALGORITMO_EXEC_SCRIPT_V2,
        "script": ruta_script.as_posix(),
        "script_sha256": hash_contenido,
        "argv": [leadrun_allowlist.normalizar_interprete(args.interpreter), args.script, *args_extra],
    }
    return ExecSpec(
        forma="script",
        argv=argv,
        artefacto=args.script,
        hash_comando=leadrun_core.content_sha256(identidad),
        algoritmo=ALGORITMO_EXEC_SCRIPT_V2,
        hash_legacy=hash_contenido,
    )


def _construir_exec_pytest(args: argparse.Namespace, repo_root: Path) -> ExecSpec:
    """Builder puro de `exec pytest` (R8): hash del argv canónico, sin cambios."""
    leadrun_core, leadrun_allowlist, _rt = _modulos_leadrun_o_error()

    flags_extra = list(args.pytest_args or [])
    if flags_extra and flags_extra[0] == "--":
        flags_extra = flags_extra[1:]
    argv = [args.interpreter, "-m", "pytest", *args.paths, *flags_extra]
    # R19: la identidad usa el intérprete NORMALIZADO; la ejecución usa el valor provisto.
    argv_identidad = [leadrun_allowlist.normalizar_interprete(args.interpreter), *argv[1:]]
    hash_identidad = leadrun_core.content_sha256(argv_identidad)
    # I6: aprobaciones previas registradas con el intérprete CRUDO siguen valiendo
    # (solo cuando el crudo difiere del normalizado).
    hash_crudo = leadrun_core.content_sha256(list(argv))
    hash_legacy = hash_crudo if hash_crudo != hash_identidad else None

    return ExecSpec(
        forma="pytest",
        argv=argv,
        artefacto="pytest:" + "|".join(args.paths),
        hash_comando=hash_identidad,
        algoritmo="sha256/argv-canonical-json",
        hash_legacy=hash_legacy,
    )


def _construir_exec_notebook(args: argparse.Namespace, repo_root: Path) -> ExecSpec:
    """Builder puro de `exec notebook` (R10): hash LF del manifest, sin cambios."""
    _modulos_leadrun_o_error()

    modo_flag = "--execute" if args.execute else "--dry-run"
    argv = [args.interpreter, "tools/notebook_runner.py", "run", "--manifest", args.manifest, modo_flag]

    try:
        hash_comando = core.hash_lf_v1(Path(repo_root) / args.manifest)
    except (OSError, UnicodeDecodeError) as exc:
        raise _ErrorExec(f"No se pudo calcular el hash del manifest {args.manifest!r}: {exc}", 2)

    return ExecSpec(
        forma="notebook",
        argv=argv,
        artefacto=args.manifest,
        hash_comando=hash_comando,
        algoritmo="sha256/lf/v1",
    )


def _cmd_exec_con_builder(args: argparse.Namespace, construir) -> int:
    """Esqueleto común de `cmd_exec_*`: repo_root -> change -> builder -> ejecutar."""
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    _change_dir_, _tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    try:
        spec = construir(args, repo_root)
    except _ErrorExec as exc:
        print(exc.mensaje, file=sys.stderr)
        return exc.codigo

    return _ejecutar_exec_comun(
        args, repo_root, control, control_path, spec.forma, spec.argv, spec.artefacto, spec.hash_comando,
        hash_legacy=spec.hash_legacy,
    )


def cmd_exec_script(args: argparse.Namespace) -> int:
    return _cmd_exec_con_builder(args, _construir_exec_script)


def cmd_exec_pytest(args: argparse.Namespace) -> int:
    return _cmd_exec_con_builder(args, _construir_exec_pytest)


def cmd_exec_notebook(args: argparse.Namespace) -> int:
    return _cmd_exec_con_builder(args, _construir_exec_notebook)


# --- exec approve (20261002-exec-approval-registration) ----------------------

def _registrar_aprobacion_exec(control: dict, control_path: Path, spec: ExecSpec, args: argparse.Namespace) -> dict:
    """Agrega la entrada a `control["aprobaciones"]` (misma estructura que
    `cmd_approve`, R11) y persiste con `core.escribir_control`. El hash sale
    SIEMPRE del builder, nunca del humano (R2)."""
    entrada = {
        "artefacto": spec.artefacto,
        "algoritmo": spec.algoritmo,
        "hash": spec.hash_comando,
        "registrado_utc": core.ahora_utc(),
        "usuario": args.usuario,
        "fecha_declarada": args.fecha,
        "alcance_aprobado": args.alcance,
        "cita": args.cita,
    }
    control.setdefault("aprobaciones", []).append(entrada)
    core.escribir_control(control_path, control)
    return entrada


def _cmd_exec_approve_con_builder(args: argparse.Namespace, construir) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    error_usuario = core.validar_usuario_sin_email(args.usuario)
    if error_usuario:
        print(error_usuario, file=sys.stderr)
        return 2
    _change_dir_, _tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    try:
        spec = construir(args, repo_root)
    except _ErrorExec as exc:
        print(exc.mensaje, file=sys.stderr)
        return exc.codigo

    # Fail-closed (R12): mismo request + allowlist que el runtime; sin escritura si falla.
    _request, codigo = _validar_request_exec(args, spec.forma, spec.argv, control)
    if codigo is not None:
        return codigo

    entrada = _registrar_aprobacion_exec(control, control_path, spec, args)
    print(f"artefacto: {entrada['artefacto']}")
    print(f"algoritmo: {entrada['algoritmo']}")
    print(f"hash: {entrada['hash']}")
    return 0


def cmd_exec_approve_script(args: argparse.Namespace) -> int:
    return _cmd_exec_approve_con_builder(args, _construir_exec_script)


def cmd_exec_approve_pytest(args: argparse.Namespace) -> int:
    return _cmd_exec_approve_con_builder(args, _construir_exec_pytest)


def cmd_exec_approve_notebook(args: argparse.Namespace) -> int:
    return _cmd_exec_approve_con_builder(args, _construir_exec_notebook)


# Argumentos semánticos compartidos por `exec <forma>` y `exec approve <forma>`
# (D4): una sola definición para que no puedan divergir.

def _agregar_args_exec_script(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--change-id", required=True, dest="change_id")
    parser.add_argument("--interpreter", required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("script_args", nargs=argparse.REMAINDER, help="Argumentos del script, tras '--'.")


_DESCRIPCION_EXEC_APPROVE = (
    "Registra en control.json la aprobación de la ejecución EXACTA descrita por los mismos "
    "argumentos que 'exec <forma>': el hash lo calcula la herramienta (nunca se suministra) y "
    "cualquier cambio de target, flags, orden, script, argumentos o manifest invalida la "
    "aprobación. Modelo de confianza: declaración humana registrada (usuario/fecha/alcance/"
    "cita), sin autenticación criptográfica; no distingue humano de agente (deuda v0.10)."
)


def _agregar_args_exec_pytest(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--change-id", required=True, dest="change_id")
    parser.add_argument("--interpreter", required=True)
    parser.add_argument("--paths", required=True, nargs="+")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER, help="Flags extra de pytest, tras '--'.")


def _agregar_args_exec_notebook(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--change-id", required=True, dest="change_id")
    parser.add_argument("--interpreter", required=True)
    parser.add_argument("--manifest", required=True)
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--dry-run", action="store_true", dest="dry_run")
    grupo.add_argument("--execute", action="store_true", dest="execute")


def _agregar_args_aprobacion_humana(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--usuario", required=True)
    parser.add_argument("--fecha", required=True)
    parser.add_argument("--alcance", required=True)
    parser.add_argument("--cita", required=True)


# --- source (v0.8 Change 1 T6: 20260928-source-neutral-data-access) ---------
#
# `access_check` real (R24, D8): compone `dsguard.pathguard.cargar_config`
# (fail-closed de versión) + `tools.autonomy.policy.parse_autonomy_policy` +
# `effective_source_access`/`is_source_sealed`. `datasources` NO importa
# `autonomy` ni `pathguard` (R25/D8); esta composición vive únicamente acá.
# Reglas fijas (no negociables, ver tarea del Lead):
#   - guardrails.json ilegible/corrupto (incl. versión no soportada) -> denegado;
#   - clave "autonomy" presente en el guardrails.json crudo pero el paquete
#     tools.autonomy no está instalado -> denegado (fail-closed: no se puede
#     evaluar una policy que el runtime no entiende);
#   - guardrails.json sin clave "autonomy" -> sin sellos, default read
#     permitido / write denegado (mismo criterio que Change 0);
#   - fuente sellada (`is_source_sealed`) -> siempre denegada, motivo con la
#     palabra "sellad" (para que `runtime.observe_source` lo traduzca a
#     SOURCE-SEALED en vez de SOURCE-ACCESS-DENIED);
#   - "write" -> siempre denegado en v0.8 (vocabulario reservado);
#   - cualquier error inesperado -> denegado (fail-closed), nunca lanza.

def _access_check_real(repo_root: Path):
    """Devuelve un callable `access_check(source_id, access_mode) ->
    (permitido, motivo)` apto para `tools.datasources.runtime.observe_source`
    (R24, D8)."""

    def _check(source_id: str, access_mode: str) -> tuple:
        try:
            pathguard_mod = _importar_perezoso("dsguard", "pathguard")
            if pathguard_mod is None:
                return False, "tools.dsguard.pathguard no disponible: acceso denegado (fail-closed)"

            try:
                pathguard_mod.cargar_config(repo_root)
            except pathguard_mod.ConfigGuardrailsError as exc:
                return False, f"guardrails.json inválido o versión no soportada: {exc}"

            ruta_config = Path(repo_root) / pathguard_mod.RUTA_CONFIG_RELATIVA
            guardrails_dict: dict = {}
            if ruta_config.exists():
                try:
                    guardrails_dict = json.loads(ruta_config.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    return False, f"guardrails.json ilegible: {type(exc).__name__}"
                if not isinstance(guardrails_dict, dict):
                    return False, "guardrails.json no contiene un objeto JSON: acceso denegado"

            if access_mode == "write":
                return False, "write no soportado (vocabulario reservado, v0.8)"

            if "autonomy" not in guardrails_dict:
                # Sin sellos declarados: comportamiento default (Change 0):
                # read permitido, write denegado (ya cortado arriba).
                return True, "permitido (sin policy de autonomy declarada)"

            autonomy_mod = _importar_perezoso("autonomy", "policy")
            if autonomy_mod is None:
                return False, (
                    "guardrails.json declara 'autonomy' pero tools.autonomy no está "
                    "instalado en este stage: acceso denegado (fail-closed)"
                )

            policy, _hallazgos = autonomy_mod.parse_autonomy_policy(
                guardrails_dict, pathguard_mod.POLICY_VERSION_MAX
            )
            if autonomy_mod.is_source_sealed(policy, source_id):
                return False, f"fuente sellada por policy humana: {source_id!r}"

            acceso = autonomy_mod.effective_source_access(policy, source_id, registry_access=None)
            if access_mode == "read" and not acceso.read:
                return False, f"lectura no permitida por policy de autonomy para {source_id!r}"
            return True, "permitido"
        except Exception as exc:  # noqa: BLE001 - fail-closed ante cualquier error inesperado
            return False, f"error inesperado evaluando acceso ({type(exc).__name__}): acceso denegado"

    return _check


def cmd_source_list(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    ds_runtime = _importar_perezoso("datasources", "runtime")
    if ds_runtime is None:
        print(_mensaje_paquete_no_instalado("datasources", "discovery"), file=sys.stderr)
        return 3

    data, resultados = ds_runtime.load_registry(repo_root)
    if data is None:
        # SOURCE-REGISTRY-MISSING es WARN informativo (exit 0), cualquier otro
        # (JSON ilegible/inválido) se imprime con su propio exit code.
        if args.json:
            print(json.dumps({"fuentes": [], "resultados": [r.to_dict() for r in resultados]}, ensure_ascii=False))
        else:
            for r in resultados:
                print(f"{r.status:<6} {r.code}: {r.message}")
        return checks.exit_code(resultados)

    fuentes = data.get("sources", []) if isinstance(data.get("sources"), list) else []
    filas = [
        {
            "source_id": f.get("source_id"),
            "role": f.get("role"),
            "observer": f.get("observer"),
            "sensitivity": f.get("sensitivity"),
            "access_mode": f.get("access_mode"),
        }
        for f in fuentes
        if isinstance(f, dict)
    ]
    if args.json:
        print(json.dumps({"fuentes": filas}, ensure_ascii=False))
    else:
        if not filas:
            print("(registro sin fuentes)")
        for fila in filas:
            print(
                f"{fila['source_id']:<24} role={fila['role']:<16} observer={fila['observer']:<40} "
                f"sensitivity={fila['sensitivity']:<10} access_mode={fila['access_mode']}"
            )
    return 0


def cmd_source_check(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    ds_runtime = _importar_perezoso("datasources", "runtime")
    if ds_runtime is None:
        print(_mensaje_paquete_no_instalado("datasources", "discovery"), file=sys.stderr)
        return 3

    resultados = ds_runtime.check_registry(repo_root)
    _imprimir_check_results(resultados, args.json, "Source check")
    return checks.exit_code(resultados)


def cmd_source_observe(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    ds_runtime = _importar_perezoso("datasources", "runtime")
    if ds_runtime is None:
        print(_mensaje_paquete_no_instalado("datasources", "discovery"), file=sys.stderr)
        return 3

    request: dict = {"source_id": args.source_id}
    if args.facet:
        request["facets"] = list(args.facet)
    if args.exactness is not None:
        request["exactness"] = args.exactness
    if args.as_of is not None:
        request["as_of"] = args.as_of

    options_extra = {"_repo_root": str(repo_root)}
    local_override = resolver_local_override(repo_root)
    fuentes_externas = local_override.get("fuentes_externas")
    if isinstance(fuentes_externas, dict):
        declaracion = fuentes_externas.get(args.source_id)
        if isinstance(declaracion, dict):
            ruta_externa = declaracion.get("path")
            if isinstance(ruta_externa, str) and ruta_externa:
                options_extra["ruta_externa_absoluta"] = ruta_externa

    observation, resultados = ds_runtime.observe_source(
        repo_root, args.source_id, request, access_check=_access_check_real(repo_root),
        options_extra=options_extra,
    )

    observation_id = None
    if observation is not None:
        observation_id = f"{observation.source_id}__{observation.content_sha256()[:12]}"

    if args.json:
        payload = {"resultados": [r.to_dict() for r in resultados]}
        if observation_id is not None:
            payload["observation_id"] = observation_id
        print(json.dumps(payload, ensure_ascii=False))
    else:
        _imprimir_check_results(resultados, False, f"Source observe: {args.source_id}")
        if observation_id is not None:
            print(f"\nObservación persistida: {observation_id}")
    return checks.exit_code(resultados)


def _ruta_observacion_invalida(ruta_str: str) -> bool:
    """`True` si `ruta_str` puede escapar del repo (componente `..`, ruta
    absoluta): mismo criterio de validación mínima que `_change_id_invalido`
    aplica para `change_id`."""
    if ".." in Path(ruta_str).parts:
        return True
    if Path(ruta_str).is_absolute():
        return True
    return False


def cmd_source_check_stale(args: argparse.Namespace) -> int:
    if _ruta_observacion_invalida(args.observation):
        print(
            f"--observation inválida: {args.observation!r}. Debe ser una ruta repo-relativa sin '..'",
            file=sys.stderr,
        )
        return 2
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    ds_core = _importar_perezoso("datasources", "core")
    ds_runtime = _importar_perezoso("datasources", "runtime")
    if ds_core is None or ds_runtime is None:
        print(_mensaje_paquete_no_instalado("datasources", "discovery"), file=sys.stderr)
        return 3

    datos_stored, error = _cargar_json(args.observation)
    if error is not None:
        print(error, file=sys.stderr)
        return 2
    try:
        stored = ds_core.SourceObservation.from_dict(datos_stored)
    except ds_core.SourceError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    fresh, resultados_observe = ds_runtime.observe_source(
        repo_root,
        stored.source_id,
        {"source_id": stored.source_id, "facets": ["fingerprint"]},
        access_check=_access_check_real(repo_root),
    )
    if fresh is None:
        _imprimir_check_results(resultados_observe, args.json, "Source check-stale")
        return checks.exit_code(resultados_observe)

    resultado = ds_runtime.compare_fingerprint(stored, fresh)
    resultados = resultados_observe + [resultado]
    _imprimir_check_results(resultados, args.json, "Source check-stale")
    return checks.exit_code(resultados)


# --- contract validate ------------------------------------------------------

def cmd_contract_validate(args: argparse.Namespace) -> int:
    if bool(args.profile) == bool(args.observation):
        print(
            "contract validate requiere exactamente uno de --profile / --observation",
            file=sys.stderr,
        )
        return 2
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    dc_core = _importar_perezoso("datacontracts", "core")
    dc_validation = _importar_perezoso("datacontracts", "validation")
    if dc_core is None or dc_validation is None:
        print(_mensaje_paquete_no_instalado("datacontracts", "discovery"), file=sys.stderr)
        return 3

    datos_contrato, error = _cargar_json(args.contract)
    if error is not None:
        print(error, file=sys.stderr)
        return 2
    try:
        contrato = dc_core.DataContract.from_dict(datos_contrato)
    except dc_core.DataContractError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.observation:
        resultados, error_obs = _validar_contrato_contra_observacion(dc_core, repo_root, contrato, args.observation)
        if error_obs is not None:
            print(error_obs, file=sys.stderr)
            return 2
        fuente_path = args.observation
        fuente_role = "observation"
    else:
        resultados = dc_validation.validate_contract_against_profile_file(contrato, Path(args.profile), repo_root)
        fuente_path = args.profile
        fuente_role = "profile"

    evidence_id = None
    if args.record_evidence:
        evidence_id, error_evidencia = _registrar_evidencia_calidad(
            repo_root,
            subject_kind="data_contract_evaluation",
            declaration_kind="data_contract",
            declaration_id=contrato.contract_id,
            declaration_version=contrato.version.version,
            content_sha256=contrato.content_sha256(),
            fuente_path=fuente_path,
            fuente_role=fuente_role,
            resultados=resultados,
        )
        if error_evidencia is not None:
            print(f"No se pudo registrar evidencia: {error_evidencia}", file=sys.stderr)

    if args.json:
        payload = {"resultados": [r.to_dict() for r in resultados]}
        if evidence_id is not None:
            payload["evidence_id"] = evidence_id
        print(json.dumps(payload, ensure_ascii=False))
    else:
        _imprimir_check_results(resultados, False, f"Contract validate: {args.contract}")
        if evidence_id is not None:
            print(f"\nEvidencia registrada: {evidence_id}")
    return checks.exit_code(resultados)


def _validar_contrato_contra_observacion(dc_core, repo_root: Path, contrato, observation_path: str) -> tuple:
    """`(resultados, error_mensaje)`. Réplica del nivel de guarda que
    `validate_contract_against_profile_file` aplica sobre `--profile` (R37):
    guard de holdout ANTES de abrir el archivo, vía el mismo
    `ds_profile.holdout_guard.verificar_permitido` que usa `datacontracts`.
    `error_mensaje` no es `None` ante cualquier fallo -- nunca lanza hacia el
    llamador (la excepción, si ocurriera, no está contemplada porque todas
    las ramas devuelven explícitamente)."""
    ds_core = _importar_perezoso("datasources", "core")
    dc_validation = _importar_perezoso("datacontracts", "validation")
    if ds_core is None or dc_validation is None:
        return [], _mensaje_paquete_no_instalado("datasources", "discovery")

    try:
        holdout_guard = _importar_perezoso("ds_profile", "holdout_guard")
        if holdout_guard is None:
            return [], "ds_profile.holdout_guard no disponible en este stage"
        permitido, motivo = holdout_guard.verificar_permitido(Path(observation_path), Path(repo_root))
        if not permitido:
            return [], f"No se puede leer la observación: ruta denegada por el guard de holdout ({motivo})"
    except Exception as exc:  # noqa: BLE001 - nunca escapa
        return [], f"Error evaluando el guard de holdout: {type(exc).__name__}"

    datos_obs, error = _cargar_json(observation_path)
    if error is not None:
        return [], error
    try:
        observation = ds_core.SourceObservation.from_dict(datos_obs)
    except ds_core.SourceError as exc:
        return [], str(exc)

    resultados = dc_validation.validate_contract_observation(contrato, observation, wording=None)
    return resultados, None


# --- contract diff -----------------------------------------------------------

def cmd_contract_diff(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()  # noqa: F841 - solo para validar que estamos en un repo (consistencia con el resto de subcomandos)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    dc_core = _importar_perezoso("datacontracts", "core")
    dc_evolution = _importar_perezoso("datacontracts", "evolution")
    if dc_core is None or dc_evolution is None:
        print(_mensaje_paquete_no_instalado("datacontracts", "discovery"), file=sys.stderr)
        return 3

    datos_old, error = _cargar_json(args.old)
    if error is not None:
        print(error, file=sys.stderr)
        return 2
    datos_new, error = _cargar_json(args.new)
    if error is not None:
        print(error, file=sys.stderr)
        return 2
    try:
        old = dc_core.DataContract.from_dict(datos_old)
        new = dc_core.DataContract.from_dict(datos_new)
    except dc_core.DataContractError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    policy = None
    if args.policy:
        datos_policy, error = _cargar_json(args.policy)
        if error is not None:
            print(error, file=sys.stderr)
            return 2
        try:
            policy = dc_core.CompatibilityPolicy.from_dict(datos_policy)
        except dc_core.DataContractError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    resultados = dc_evolution.classify_contract_change(old, new, policy)

    if args.json:
        print(json.dumps({"resultados": [r.to_dict() for r in resultados]}, ensure_ascii=False))
    else:
        print(f"Contract diff: {args.old} -> {args.new}")
        if old.contract_id != new.contract_id:
            print(
                f"  ADVERTENCIA: contract_id distinto ({old.contract_id!r} -> {new.contract_id!r}); "
                "se compara la estructura, no la identidad."
            )
        print()
        for r in resultados:
            print(f"{r.status:<6} {r.code} [{r.subject}]: {r.message}")
        por_codigo: dict = {}
        for r in resultados:
            por_codigo[r.code] = por_codigo.get(r.code, 0) + 1
        print("\nResumen por categoría:")
        if not por_codigo:
            print("  (sin cambios detectados)")
        for codigo, cantidad in sorted(por_codigo.items()):
            print(f"  {codigo}: {cantidad}")
    return 0


# --- contract impact -----------------------------------------------------------

_EXTENSIONES_IMPACT_TEXTO_PLANO = (".yaml", ".yml", ".toml", ".md")


def cmd_contract_impact(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    dc_core = _importar_perezoso("datacontracts", "core")
    git_source = _importar_perezoso("dsimpact", "git_source")
    consumers_py = _importar_perezoso("dsimpact", "consumers_py")
    consumers_text = _importar_perezoso("dsimpact", "consumers_text")
    notebooks_source = _importar_perezoso("dsimpact", "notebooks_source")
    if None in (dc_core, git_source, consumers_py, consumers_text, notebooks_source):
        print(_mensaje_paquete_no_instalado("dsimpact", "experiment"), file=sys.stderr)
        return 3

    datos_contrato, error = _cargar_json(args.contract)
    if error is not None:
        print(error, file=sys.stderr)
        return 2
    try:
        contrato = dc_core.DataContract.from_dict(datos_contrato)
    except dc_core.DataContractError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.fields:
        nombres_campo = set(args.fields.split(","))
    else:
        nombres_campo = {campo.name for campo in contrato.fields}
    targets = {contrato.contract_id} | nombres_campo

    try:
        ruta_contrato_relativa = Path(args.contract).resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        ruta_contrato_relativa = None

    try:
        candidatos = git_source.listar_consumidores_candidatos(repo_root)
    except git_source.GitSourceError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    findings: list = []
    for candidato in candidatos:
        if candidato == ruta_contrato_relativa:
            continue
        ruta_abs = repo_root / candidato
        if not ruta_abs.exists():
            continue
        try:
            texto = ruta_abs.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        if candidato.endswith(".py"):
            for m in consumers_py.buscar_en_texto_python(texto, set(), targets):
                findings.append(
                    {
                        "changed_item": m["changed_item"],
                        "consumer": candidato,
                        "evidence_type": "CONTRACT_REFERENCE",
                        "location": f"{candidato}:{m['linea']}",
                        "evidence": m["fragmento"],
                    }
                )
        elif candidato.endswith(".ipynb"):
            celdas, error_parseo = notebooks_source.celdas_codigo(texto, candidato)
            if error_parseo:
                continue
            for indice, texto_celda in celdas:
                for m in consumers_py.buscar_en_texto_python(texto_celda, set(), targets):
                    findings.append(
                        {
                            "changed_item": m["changed_item"],
                            "consumer": candidato,
                            "evidence_type": "CONTRACT_REFERENCE",
                            "location": f"{candidato}#cell:{indice}:{m['linea']}",
                            "evidence": m["fragmento"],
                        }
                    )
        elif candidato.endswith(".json"):
            for m in consumers_text.buscar_en_json(texto, targets):
                findings.append(
                    {
                        "changed_item": m["changed_item"],
                        "consumer": candidato,
                        "evidence_type": "CONTRACT_REFERENCE",
                        "location": candidato,
                        "evidence": m["fragmento"],
                    }
                )
        elif candidato.endswith(_EXTENSIONES_IMPACT_TEXTO_PLANO):
            for m in consumers_text.buscar_en_texto_plano(texto, targets):
                findings.append(
                    {
                        "changed_item": m["changed_item"],
                        "consumer": candidato,
                        "evidence_type": "CONTRACT_REFERENCE",
                        "location": f"{candidato}:{m['linea']}",
                        "evidence": m["fragmento"],
                    }
                )

    consumidores_unicos = sorted({f["consumer"] for f in findings})
    resultado = {
        "contract_id": contrato.contract_id,
        "targets": sorted(targets),
        "findings": findings,
        "summary": {"consumers": len(consumidores_unicos), "findings": len(findings)},
    }

    if args.json:
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
    else:
        print(f"Contract impact: {args.contract} (contract_id={contrato.contract_id})")
        print(f"  targets: {', '.join(sorted(targets))}")
        print()
        print("Potentially affected consumers:")
        if not findings:
            print("  (ningún consumidor potencial detectado)")
        else:
            por_consumer: dict = {}
            for f in findings:
                por_consumer.setdefault(f["consumer"], []).append(f)
            for consumer in sorted(por_consumer):
                print(f"  {consumer}")
                for f in por_consumer[consumer]:
                    print(f"    [{f['evidence_type']}] '{f['changed_item']}' (location={f['location']})")
        print(
            f"\nSummary: {resultado['summary']['consumers']} potentially affected consumers "
            f"({resultado['summary']['findings']} findings)"
        )
    return 0


# --- quality evaluate ---------------------------------------------------------

def cmd_quality_evaluate(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    mq_core = _importar_perezoso("modelquality", "core")
    mq_validation = _importar_perezoso("modelquality", "validation")
    if mq_core is None or mq_validation is None:
        print(_mensaje_paquete_no_instalado("modelquality", "discovery"), file=sys.stderr)
        return 3

    datos_policy, error = _cargar_json(args.policy)
    if error is not None:
        print(error, file=sys.stderr)
        return 2
    datos_metricas, error = _cargar_json(args.metrics)
    if error is not None:
        print(error, file=sys.stderr)
        return 2
    if not isinstance(datos_metricas, list):
        print(f"{args.metrics}: se esperaba una lista de métricas observadas", file=sys.stderr)
        return 2

    datos_baselines = []
    if args.baselines:
        datos_baselines, error = _cargar_json(args.baselines)
        if error is not None:
            print(error, file=sys.stderr)
            return 2
        if not isinstance(datos_baselines, list):
            print(f"{args.baselines}: se esperaba una lista de baselines", file=sys.stderr)
            return 2

    try:
        policy = mq_core.ModelQualityPolicy.from_dict(datos_policy)
        observed_metrics = [mq_core.ObservedMetric.from_dict(m) for m in datos_metricas]
        baselines = [mq_core.BaselineReference.from_dict(b) for b in datos_baselines]
    except mq_core.ModelQualityError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    resultados = mq_validation.evaluate_policy(policy, observed_metrics, baselines)

    evidence_id = None
    if args.record_evidence:
        evidence_id, error_evidencia = _registrar_evidencia_calidad(
            repo_root,
            subject_kind="model_quality_evaluation",
            declaration_kind="model_quality_policy",
            declaration_id=policy.policy_id,
            declaration_version=None,
            content_sha256=policy.content_sha256(),
            fuente_path=args.metrics,
            fuente_role="metrics",
            resultados=resultados,
        )
        if error_evidencia is not None:
            print(f"No se pudo registrar evidencia: {error_evidencia}", file=sys.stderr)

    if args.json:
        payload = {"resultados": [r.to_dict() for r in resultados]}
        if evidence_id is not None:
            payload["evidence_id"] = evidence_id
        print(json.dumps(payload, ensure_ascii=False))
    else:
        _imprimir_check_results(resultados, False, f"Quality evaluate: {args.policy}")
        if evidence_id is not None:
            print(f"\nEvidencia registrada: {evidence_id}")
    return checks.exit_code(resultados)


# --- quality evidence show ----------------------------------------------------

def cmd_quality_evidence_show(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    qe_core = _importar_perezoso("qualityevidence", "core")
    qe_evidence = _importar_perezoso("qualityevidence", "evidence")
    if qe_core is None or qe_evidence is None:
        print(_mensaje_paquete_no_instalado("qualityevidence", "experiment"), file=sys.stderr)
        return 3

    try:
        manifest = qe_evidence.read_manifest(repo_root, args.evidence_id)
    except qe_core.QualityEvidenceError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"Quality evidence: {manifest.evidence_id}")
        print(f"  subject_kind: {manifest.subject_kind}")
        print(
            f"  declaration: {manifest.declaration.declaration_kind}={manifest.declaration.declaration_id} "
            f"(version={manifest.declaration.version})"
        )
        print(f"  generated_at: {manifest.generated_at}")
        conteos: dict = {}
        for r in manifest.check_results:
            conteos[r["status"]] = conteos.get(r["status"], 0) + 1
        print(
            f"  check_results: {conteos.get('PASS', 0)} PASS, {conteos.get('WARN', 0)} WARN, "
            f"{conteos.get('FAIL', 0)} FAIL, {conteos.get('N/A', 0)} N/A"
        )
        print(f"  technical_errors: {len(manifest.technical_errors)}")
    return 0


# --- quality drift -------------------------------------------------------------

def cmd_quality_drift(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    qe_core = _importar_perezoso("qualityevidence", "core")
    qe_evidence = _importar_perezoso("qualityevidence", "evidence")
    if qe_core is None or qe_evidence is None:
        print(_mensaje_paquete_no_instalado("qualityevidence", "experiment"), file=sys.stderr)
        return 3

    try:
        drift = qe_evidence.drift_from_profiles(
            repo_root,
            metric_name=args.metric,
            baseline_profile_path=args.baseline_profile,
            current_profile_path=args.current_profile,
            field=args.field,
            column=args.column,
            comparison_mode=args.mode,
            threshold=args.threshold,
            baseline_label=args.baseline_label,
            current_label=args.current_label,
        )
    except qe_core.QualityEvidenceError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(drift.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"Quality drift: {drift.metric_name}")
        print(f"  baseline_value: {drift.baseline_value!r} ({drift.baseline_label})")
        print(f"  current_value: {drift.current_value!r} ({drift.current_label})")
        print(f"  observed_difference: {drift.observed_difference!r} ({drift.comparison_mode})")
        print(f"  result: {drift.result_status} -- {drift.result_message}")
    return 0


# --- cards (Change 20261005-cards-governance-integration, R43-R52) ---------

# Capability que habilita cada kind de Card (R45).
_CARDS_CAPABILITY_DE_KIND = {"data": "data_cards", "model": "model_governance", "governance": "model_governance"}
_CARDS_CODE_CAPABILITY_OFF = "CARDS-CAPABILITY-DISABLED"
_CARDS_CODE_SIN_CARDS = "CARDS-NONE-FOUND"


def _cards_leer_control(repo_root: Path) -> tuple:
    """`(control|None, error|None)`: `.ds_init/control.json` si existe. Ilegible -> error."""
    ruta = repo_root / ".ds_init" / "control.json"
    if not ruta.is_file():
        return None, None
    datos, error = _cargar_json(str(ruta))
    if error is not None:
        return None, "no se pudo interpretar .ds_init/control.json"
    return (datos if isinstance(datos, dict) else {}), None


def _cards_nota(discovery_mod) -> str:
    modelgov_mod = _importar_perezoso("cards", "modelgov")
    nota = getattr(modelgov_mod, "NOTA_COMPLETENESS", None) if modelgov_mod is not None else None
    return nota or discovery_mod.NOTA_COMPLETENESS_FALLBACK


def _cards_resultados(pv, faltantes_cap: list, limpiar=None) -> list:
    """CheckResult de la validación (los de cada Card + hallazgos de configuración WARN)."""
    resultados: list = []
    for kind in faltantes_cap:
        resultados.append(
            checks.CheckResult(
                checks.STATUS_NA, _CARDS_CODE_CAPABILITY_OFF,
                f"cards {kind}: capability {_CARDS_CAPABILITY_DE_KIND[kind]} no habilitada; no se validan",
            )
        )
    for reporte in pv.reports:
        resultados.extend(reporte.check_results)
    gov = pv.governance
    if gov is not None:
        _l = limpiar or (lambda t, *a: str(t))
        for h in getattr(gov, "findings", ()) or ():
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_WARN, _l(getattr(h, "code", "GOVCFG"), None, 80),
                    "governance project configuration finding", detail=_l(getattr(h, "detail", ""), None),
                )
            )
    if not pv.reports and not faltantes_cap:
        resultados.append(
            checks.CheckResult(checks.STATUS_NA, _CARDS_CODE_SIN_CARDS, "no hay Cards de governance en las rutas conocidas")
        )
    return resultados


def _cards_gating(discovery_mod, repo_root: Path, kinds_pedidos: list, explicito: bool) -> tuple:
    """`(kinds_a_validar|None, kinds_deshabilitados, exit|None)`. Sin control.json no hay
    gating (R45). Implícito (discovery): los kinds deshabilitados se omiten con N/A;
    explícito (`--kind`/`--path`): kind deshabilitado -> exit 2."""
    control, error = _cards_leer_control(repo_root)
    if error is not None:
        print(error, file=sys.stderr)
        return None, [], 2
    if control is None:
        return (kinds_pedidos or None), [], None
    cap = discovery_mod.estado_capabilities(control)
    if cap["invalida"]:
        for m in cap["invalida"]:
            print(f"capabilities inválidas: {m}", file=sys.stderr)
        return None, [], 2
    kinds = kinds_pedidos or list(discovery_mod.KINDS)
    habilitados = [k for k in kinds if _CARDS_CAPABILITY_DE_KIND[k] in cap["habilitadas"]]
    apagados = [k for k in kinds if k not in habilitados]
    if apagados and explicito:
        for k in apagados:
            print(f"capability {_CARDS_CAPABILITY_DE_KIND[k]} no habilitada: no se puede operar sobre Cards '{k}'", file=sys.stderr)
        return None, apagados, 2
    return habilitados, apagados, None


def _cards_importar():
    discovery_mod = _importar_perezoso("cards", "discovery")
    if discovery_mod is None:
        print(_mensaje_paquete_no_instalado("cards", "discovery"), file=sys.stderr)
    return discovery_mod


def _cards_gating_por_reportes(discovery_mod, repo_root: Path, pv) -> int:
    """Gating de `--path`: según el kind real de cada Card validada. 0 ok, 2 deshabilitado."""
    control, _error = _cards_leer_control(repo_root)
    if _error:
        # Fail-closed (cierre de revisión ciclo 2): un control ilegible no desactiva el gating.
        print(f"cards: control de instalación ilegible: {_error}", file=sys.stderr)
        return 2
    if control is None:
        return 0
    cap = discovery_mod.estado_capabilities(control)
    for r in pv.reports:
        capacidad = _CARDS_CAPABILITY_DE_KIND.get(r.kind)
        if capacidad is not None and capacidad not in cap["habilitadas"]:
            print(f"capability {capacidad} no habilitada: no se puede operar sobre Cards '{r.kind}'", file=sys.stderr)
            return 2
    return 0


def _cards_imprimir_humano(discovery_mod, pv, resultados: list, nota: str, titulo: str) -> None:
    print(f"{titulo}\n")
    for n in pv.notes:
        print(f"Aviso: {n}")
    for r in pv.reports:
        print(f"[{r.kind}] {r.card_id or '(sin card_id)'}  revision={r.revision_id or '-'}  estado={r.status}  archivo={r.rel_path}")
        pol = r.policy or {}
        if r.kind == "governance":
            print(f"    governance_completeness={r.status}  risk_level declarado={pol.get('declared_level')} efectivo={pol.get('effective_level')}")
            politica = pol.get("policy") or {}
            for lado in sorted(politica):
                if isinstance(politica[lado], dict):
                    print("    policy " + lado + ": " + ", ".join(f"{k}={politica[lado][k]}" for k in sorted(politica[lado])))
            print(f"    configuración: {pol.get('config_state')}")
        for req in r.requirements:
            print(f"    requisito {req['requirement_id']} ({req['severity']}): {req['state']}")
        for ev in r.evidence:
            if ev["state"] != "fresh":
                print(f"    evidencia {ev['evidence_id']}: {ev['state']}")
        for an in r.anchors:
            print(f"    atestación anchored {an['attestation_id']}: {an['state']} {an.get('detail') or ''}".rstrip())
        for h in r.findings:
            print(f"    hallazgo {h['code']} {h['path']}: {h['detail']}")
    print()
    _imprimir_check_results(resultados, False, "Resultados")
    print(f"\nNota: {nota}")


def _cards_emitir(discovery_mod, pv, resultados: list, como_json: bool, titulo: str, extra: Optional[dict] = None) -> None:
    nota = _cards_nota(discovery_mod)
    if como_json:
        payload = {
            "resultados": [r.to_dict() for r in resultados],
            "cards": [discovery_mod.report_a_dict(r) for r in pv.reports],
            "nota": nota,
        }
        if extra:
            payload.update(extra)
        print(json.dumps(payload, ensure_ascii=False))
    else:
        _cards_imprimir_humano(discovery_mod, pv, resultados, nota, titulo)


def cmd_cards_validate(args: argparse.Namespace) -> int:
    """Valida Cards de governance (solo lectura, R44/R51)."""
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    discovery_mod = _cards_importar()
    if discovery_mod is None:
        return 3
    kinds_pedidos = [args.kind] if args.kind else []
    explicito = bool(args.kind or args.path)
    kinds, apagados, salida = _cards_gating(discovery_mod, repo_root, kinds_pedidos, bool(args.kind))
    if salida is not None:
        return salida
    if not args.path and kinds is not None and not kinds:
        pv = discovery_mod.ProjectValidation(reports=(), governance=None, notes=())
    else:
        # Con --path el gating se aplica luego según el kind real de cada Card.
        filtro = None if args.path else kinds
        pv = discovery_mod.validar_proyecto(repo_root, kinds=filtro, paths=args.path or None)
    if args.path and args.kind:
        # M-2: `--kind` incompatible con el kind real de un `--path` es un error de uso.
        for r in pv.reports:
            if r.kind not in (args.kind, discovery_mod.KIND_DESCONOCIDO):
                print(
                    f"--kind {args.kind} es incompatible con el kind real ({r.kind}) de {r.rel_path}",
                    file=sys.stderr,
                )
                return 2
    if args.path:
        salida = _cards_gating_por_reportes(discovery_mod, repo_root, pv)
        if salida:
            return salida
    resultados = _cards_resultados(pv, [] if explicito else apagados, discovery_mod.limpiar_texto)
    _cards_emitir(discovery_mod, pv, resultados, args.json, "Cards validate")
    return checks.exit_code(resultados)


def cmd_cards_report(args: argparse.Namespace) -> int:
    """Valida y publica el reporte HTML de UNA Card con reporting.publish (R50)."""
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    discovery_mod = _cards_importar()
    report_mod = _importar_perezoso("cards", "report")
    if discovery_mod is None or report_mod is None:
        print(_mensaje_paquete_no_instalado("cards", "discovery"), file=sys.stderr)
        return 3
    previo = discovery_mod.validar_proyecto(repo_root, paths=[args.path])
    salida = _cards_gating_por_reportes(discovery_mod, repo_root, previo)
    if salida:
        return salida
    try:
        publicado, pv = report_mod.publicar_card(repo_root, args.path, out_dir=args.out_dir)
    except ImportError:
        print(_mensaje_paquete_no_instalado("reporting", "discovery"), file=sys.stderr)
        return 3
    resultados = _cards_resultados(pv, [], discovery_mod.limpiar_texto) + list(publicado.results)
    _cards_emitir(discovery_mod, pv, resultados, args.json, "Cards report", extra={"out_dir": publicado.out_dir})
    if not args.json and publicado.out_dir:
        print(f"Reporte: {publicado.out_dir}")
    return checks.exit_code(resultados)


# --- archive --------------------------------------------------------------

def cmd_archive(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    estado, err_estado = sdd.read_estado(tasks_path)
    if err_estado:
        _imprimir_findings(err_estado, 1, args.json)
        return 1
    if estado != "cerrada":
        finding = core.Finding(
            "SDD-ARCHIVO-ESTADO-INVALIDO",
            f"Estado actual '{estado}' no permite archivar (se requiere 'cerrada')",
            str(tasks_path),
        )
        _imprimir_findings([finding], 1, args.json)
        return 1

    findings_gate = sdd.gate_cierre(control, tasks_path, None, repo_root)
    if findings_gate:
        _imprimir_findings(findings_gate, 1, args.json)
        return 1

    ruta_relativa_change = change_dir.relative_to(repo_root).as_posix()
    resultado_ls = repo._git(repo_root, "ls-files", "--", ruta_relativa_change)
    if not resultado_ls.stdout.strip():
        finding = core.Finding(
            "SDD-ARCHIVO-NO-VERSIONADO",
            f"El directorio del cambio no está versionado: {ruta_relativa_change}",
            ruta_relativa_change,
        )
        _imprimir_findings([finding], 1, args.json)
        return 1

    if not repo.is_tree_clean(repo_root):
        finding = core.Finding(
            "ALCANCE-TREE-SUCIO",
            "El working tree no está limpio: no se puede archivar",
        )
        _imprimir_findings([finding], 1, args.json)
        return 1

    destino_relativo = f"openspec/archive/{args.change_id}"
    destino_abs = repo_root / "openspec" / "archive" / args.change_id
    if destino_abs.exists():
        print(f"El destino ya existe, no se pisa: {destino_relativo}", file=sys.stderr)
        return 2

    if not args.execute:
        if args.json:
            print(
                json.dumps(
                    {
                        "dry_run": True,
                        "origen": ruta_relativa_change,
                        "destino": destino_relativo,
                    },
                    ensure_ascii=False,
                )
            )
        else:
            print(f"[dry-run] {ruta_relativa_change} -> {destino_relativo} (nada movido)")
        return 0

    # `git mv` no crea el directorio padre del destino: en un repo donde
    # `openspec/archive/` todavía no existe (primer archivado), el rename
    # fallaría con "No such file or directory". Solo se crea el padre, nunca
    # el destino final (`openspec/archive/<id>/`), que lo crea el propio
    # `git mv` como parte del rename.
    (repo_root / "openspec" / "archive").mkdir(parents=True, exist_ok=True)

    resultado_mv = repo._git(repo_root, "mv", ruta_relativa_change, destino_relativo)
    if resultado_mv.returncode != 0:
        print(f"git mv falló: {resultado_mv.stderr.strip()}", file=sys.stderr)
        return 3

    nuevo_control_path = destino_abs / "control.json"
    control["archivado"] = {"utc": core.ahora_utc(), "destino": destino_relativo}
    core.escribir_control(nuevo_control_path, control)

    if args.json:
        print(
            json.dumps(
                {"archivado": True, "origen": ruta_relativa_change, "destino": destino_relativo},
                ensure_ascii=False,
            )
        )
    else:
        print(f"Archivado: {ruta_relativa_change} -> {destino_relativo}")
    return 0


# --- kdd ---------------------------------------------------------------------

def cmd_kdd_init(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3

    ruta_lifecycle = lifecycle.state_path(repo_root)
    if not ruta_lifecycle.exists():
        ruta_legacy = kdd.state_path(repo_root)
        if ruta_legacy.exists():
            print(
                f"{ruta_legacy.relative_to(repo_root).as_posix()} (legacy) existe pero no se migro. "
                "Correr 'ds_guard lifecycle migrate' primero.",
                file=sys.stderr,
            )
            return 2

    try:
        estado, creado = kdd.kdd_init(repo_root)
    except kdd.KddEstadoError as e:
        print(str(e), file=sys.stderr)
        return 1

    ruta_relativa = lifecycle.state_path(repo_root).relative_to(repo_root).as_posix()
    if args.json:
        print(json.dumps({"creado": creado, "ruta": ruta_relativa}, ensure_ascii=False))
    else:
        if creado:
            print(f"KDD inicializado: {ruta_relativa}")
        else:
            print(f"{ruta_relativa} ya existía: init es idempotente, no se modificó nada.")
    return 0


def cmd_kdd_status(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3

    ruta_lifecycle = lifecycle.state_path(repo_root)
    if not ruta_lifecycle.exists():
        ruta_legacy = kdd.state_path(repo_root)
        if ruta_legacy.exists():
            print(
                f"{ruta_legacy.relative_to(repo_root).as_posix()} (legacy) existe pero no se migro. "
                "Correr 'ds_guard lifecycle migrate' primero.",
                file=sys.stderr,
            )
        else:
            print(f"{ruta_lifecycle.relative_to(repo_root).as_posix()} no existe. Correr 'ds_guard kdd init' primero.", file=sys.stderr)
        return 2
    try:
        payload = kdd.kdd_status(repo_root)
    except kdd.KddEstadoError as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for etapa in kdd.ETAPAS:
            info = payload["etapas"][etapa]
            print(f"{etapa}: {info['estado']} ({len(info['changes'])} cambio(s))")
            for c in info["criterios_detectables"]:
                marca = "OK" if c["cumplido"] else "--"
                print(f"    [{marca}] {c['criterio']}")
            if info["changes_no_localizados"]:
                print(
                    "    (no localizados en openspec/changes/ ni openspec/archive/: "
                    + ", ".join(info["changes_no_localizados"])
                    + ")"
                )
    return 0


def cmd_kdd_transition(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3

    ruta_lifecycle = lifecycle.state_path(repo_root)
    if not ruta_lifecycle.exists():
        ruta_legacy = kdd.state_path(repo_root)
        if ruta_legacy.exists():
            print(
                f"{ruta_legacy.relative_to(repo_root).as_posix()} (legacy) existe pero no se migro. "
                "Correr 'ds_guard lifecycle migrate' primero.",
                file=sys.stderr,
            )
        else:
            print(f"{ruta_lifecycle.relative_to(repo_root).as_posix()} no existe. Correr 'ds_guard kdd init' primero.", file=sys.stderr)
        return 2

    try:
        ok, findings = kdd.kdd_transition(repo_root, args.etapa, args.a, motivo=args.motivo)
    except kdd.KddEstadoError as e:
        print(str(e), file=sys.stderr)
        return 1

    if ok:
        if args.json:
            print(json.dumps({"transicion_aplicada": {"etapa": args.etapa, "hacia": args.a}}, ensure_ascii=False))
        else:
            print(f"Transición KDD aplicada -> {args.etapa}: {args.a}")
        return 0

    _imprimir_findings(findings, 1, args.json)
    return 1


# --- lifecycle -----------------------------------------------------------------

def cmd_lifecycle_migrate(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3

    try:
        resultado = kdd_compat.migrar_desde_legacy(repo_root)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2
    except (lifecycle.LifecycleEstadoError, kdd_compat.KddCompatError) as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(resultado, ensure_ascii=False))
    else:
        if resultado["migrado"]:
            print(f"Migracion completa -> {lifecycle.state_path(repo_root).relative_to(repo_root).as_posix()}")
        else:
            print(resultado["motivo"])
    return 0


# --- project -------------------------------------------------------------------

def cmd_project_init(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    try:
        estado, creado = maturity.project_init(repo_root, stage=args.stage, adopt=args.adopt)
    except maturity.MaturityEstadoError as e:
        print(str(e), file=sys.stderr)
        return 1
    ruta_relativa = maturity.state_path(repo_root).relative_to(repo_root).as_posix()
    if args.json:
        print(json.dumps({"creado": creado, "ruta": ruta_relativa, "estado": estado}, ensure_ascii=False))
    else:
        if creado:
            via = estado["stage_history"][-1]["via"]
            print(f"project.json inicializado -> {ruta_relativa} (project_stage={estado['project_stage']}, via={via})")
        else:
            print(f"{ruta_relativa} ya existía: init es idempotente, no se modificó nada.")
    return 0


def cmd_project_calibrate(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    try:
        estado = maturity.calibrar(repo_root, args.stage, args.reason)
    except maturity.MaturityEstadoError as e:
        print(str(e), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"project_stage": estado["project_stage"]}, ensure_ascii=False))
    else:
        print(f"Calibrado -> project_stage={estado['project_stage']} (via=calibrate)")
    return 0


def cmd_project_set_risk(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    try:
        estado = maturity.set_risk(repo_root, args.nivel, args.reason)
    except maturity.MaturityEstadoError as e:
        print(str(e), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"risk_level": estado["risk_level"]}, ensure_ascii=False))
    else:
        print(f"risk_level -> {estado['risk_level']}")
    return 0


def cmd_project_status(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    try:
        payload = maturity.project_status(repo_root)
    except FileNotFoundError:
        ruta_relativa = maturity.state_path(repo_root).relative_to(repo_root).as_posix()
        print(f"{ruta_relativa} no existe. Correr 'ds_guard project init' primero.", file=sys.stderr)
        return 2
    except maturity.MaturityEstadoError as e:
        print(str(e), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"project_stage: {payload['project_stage']}")
        print(f"risk_level: {payload['risk_level']} ({payload['risk_status']})")
        if payload["origen_stage"]:
            o = payload["origen_stage"]
            print(f"origen del stage actual: via={o['via']} reason={o['reason']!r} utc={o['utc']}")
    return 0


# --- readiness / promote (Change 6, v0.3) -----------------------------------

def cmd_project_readiness(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    resultados = readiness.evaluar_readiness(repo_root, args.target)
    ready = not checks.hay_bloqueo(resultados)
    if args.json:
        payload = {
            "target": args.target,
            "ready": ready,
            "resultados": [r.to_dict() for r in resultados],
        }
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"Readiness: {args.target}\n")
        for r in resultados:
            print(f"{r.status:<6} {r.message}")
        print(f"\nResultado: {'READY' if ready else 'NOT READY'}")
    return checks.exit_code(resultados)


def cmd_project_promote(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    try:
        resultado = readiness.promote(repo_root, args.stage, args.reason)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2
    except readiness.PromotionError as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.json:
        payload = {
            "promovido": resultado["promovido"],
            "project_stage": resultado["project_stage"],
            "resultados": [r.to_dict() for r in resultado["resultados"]],
        }
        print(json.dumps(payload, ensure_ascii=False))
    else:
        if resultado["promovido"]:
            print(f"Promovido -> project_stage={resultado['project_stage']} (via=promote)")
        else:
            print(f"No promovido: readiness con FAIL para target={args.stage}")
            for r in resultado["resultados"]:
                print(f"{r.status:<6} {r.message}")
    return 0 if resultado["promovido"] else 1


# --- mlops -----------------------------------------------------------------

_NOMBRE_CAPABILITY_MLOPS = {
    mlops_foundations.CODIGO_REPRODUCIBILIDAD: "reproducibility",
    mlops_foundations.CODIGO_VERSIONADO: "versioning",
    mlops_foundations.CODIGO_LINEAGE: "lineage",
    mlops_foundations.CODIGO_ARTIFACTS: "artifacts",
}


def cmd_mlops_status(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    resultados = mlops_foundations.evaluar_foundations(repo_root)
    if args.json:
        print(json.dumps([r.to_dict() for r in resultados], ensure_ascii=False))
    else:
        stage_result = resultados[0]
        etiqueta_stage = stage_result.subject or "no determinado"
        print(f"MLOps Foundations (project_stage: {etiqueta_stage})\n")
        for r in resultados[1:]:
            nombre = _NOMBRE_CAPABILITY_MLOPS.get(r.code, r.code)
            print(f"{nombre:<20}{r.status:<6} {r.message}")
        conteos = checks.contar_por_status(resultados[1:])
        print(
            f"\nResumen: {conteos[checks.STATUS_PASS]} PASS, {conteos[checks.STATUS_WARN]} WARN, "
            f"{conteos[checks.STATUS_FAIL]} FAIL, {conteos[checks.STATUS_NA]} N/A"
        )
    return checks.exit_code(resultados)


def cmd_mlops_record(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    resultados = mlops_foundations.evaluar_foundations(repo_root)
    try:
        resultado_registro = mlops_foundations.registrar_evidencia(repo_root, resultados)
    except FileNotFoundError:
        ruta_relativa = lifecycle.state_path(repo_root).relative_to(repo_root).as_posix()
        print(
            f"{ruta_relativa} no existe. Correr 'ds_guard lifecycle migrate' o inicializar lifecycle primero.",
            file=sys.stderr,
        )
        return 2
    except lifecycle.LifecycleEstadoError as e:
        print(str(e), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(resultado_registro, ensure_ascii=False))
    else:
        print(f"Evidencia registrada -> {', '.join(resultado_registro['capacidades_actualizadas'])}")
    return checks.exit_code(resultados)


def cmd_mlops_evidence_add(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    try:
        resultado = mlops_evidence.agregar_evidencia(
            repo_root, args.tier, args.capability, args.artifact, args.reason
        )
    except FileNotFoundError:
        ruta_relativa = lifecycle.state_path(repo_root).relative_to(repo_root).as_posix()
        print(
            f"{ruta_relativa} no existe. Correr 'ds_guard lifecycle migrate' o inicializar lifecycle primero.",
            file=sys.stderr,
        )
        return 2
    except (mlops_evidence.EvidenciaError, lifecycle.LifecycleEstadoError) as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(resultado, ensure_ascii=False))
    else:
        entrada = resultado["entrada"]
        if resultado["duplicado"]:
            print(f"Evidencia ya registrada (duplicado, no se agrega de nuevo): {entrada['path']}")
        else:
            print(f"Evidencia agregada: {entrada['path']} (sha256={entrada['sha256'][:12]}...)")
    return 0


# --- init -------------------------------------------------------------------

# Artefactos posibles de un cambio: si cualquiera ya existe, `init` no toca
# nada (nunca sobreescribe un cambio existente).
_ARTEFACTOS_CAMBIO = ("proposal.md", "tasks.md", "spec.md", "design.md", "control.json")

_PLANTILLAS_POR_MODO = {
    "abreviado": ("proposal", "tasks"),
    "completo": ("proposal", "tasks", "spec", "design"),
}


def _rutas_por_defecto_change(change_id: str, archivos_md: list) -> list:
    """Artefactos por defecto de un Change en `rutas_autorizadas`: los `.md`
    creados por `init`, `control.json` y `verification.md` (R37; `init` no crea
    este último). Compartido por `cmd_init` y `cmd_approve` (R24)."""
    base = f"openspec/changes/{change_id}"
    rutas = [f"{base}/{nombre}" for nombre in archivos_md]
    rutas.append(f"{base}/control.json")
    rutas.append(f"{base}/verification.md")
    return rutas


def _change_id_invalido(change_id: str) -> bool:
    """True si `change_id` puede escapar de `openspec/changes/<change_id>/`:
    componente `..`, separador de ruta (`/` o `\\`) o ruta absoluta. `init` es
    la primera escritura "desde cero" para un `change_id` (a diferencia del
    resto de los comandos, que exigen que el directorio ya exista vía
    `_cargar_change`), así que acá sí hay que validar antes de escribir."""
    if ".." in Path(change_id).parts:
        return True
    if "/" in change_id or "\\" in change_id:
        return True
    if Path(change_id).is_absolute():
        return True
    return False


def cmd_init(args: argparse.Namespace) -> int:
    if _change_id_invalido(args.change_id):
        print(
            f"--change-id inválido: {args.change_id!r}. Debe ser un slug simple "
            "(letras, dígitos, guiones) sin separadores de ruta ni '..'",
            file=sys.stderr,
        )
        return 2

    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir = _change_dir(repo_root, args.change_id)

    ya_presentes = [a for a in _ARTEFACTOS_CAMBIO if (change_dir / a).exists()]
    if ya_presentes:
        print(
            f"El cambio '{args.change_id}' ya tiene artefactos en {change_dir}: "
            f"{', '.join(ya_presentes)} — 'init' nunca sobreescribe un cambio existente",
            file=sys.stderr,
        )
        return 2

    templates_dir = repo_root / ".claude" / "skills" / "lead-data-scientist" / "templates"
    nombres_md = _PLANTILLAS_POR_MODO[args.modo]

    archivos_creados = []
    for nombre in nombres_md:
        plantilla_path = templates_dir / f"{nombre}.md"
        if not plantilla_path.exists():
            ya_creados = ", ".join(archivos_creados) if archivos_creados else "(ninguno)"
            print(
                f"Falta la plantilla requerida: {plantilla_path}. "
                f"Artefactos ya creados en esta corrida: {ya_creados}",
                file=sys.stderr,
            )
            return 3
        texto = plantilla_path.read_text(encoding="utf-8")
        texto = texto.replace("<change-id>", args.change_id)
        core.escribir_texto_atomico(change_dir / f"{nombre}.md", texto)
        archivos_creados.append(f"{nombre}.md")

    commit, rama = repo.get_head(repo_root)
    baseline = {
        "commit": commit,
        "rama": rama,
        "capturado_utc": core.ahora_utc(),
    }
    rutas_autorizadas = _rutas_por_defecto_change(args.change_id, archivos_creados)

    # `aprobacion_modo` (R1/D1 de 20260930-autonomous-sdd-and-remediation):
    # ausente el flag -> `per_change` (default, idéntico al comportamiento de
    # hoy para cualquier Change que no lo declare explícitamente).
    aprobacion_modo = args.approval_mode if args.approval_mode is not None else sdd.APPROVAL_MODE_DEFAULT

    control = {
        "schema_version": 1,
        "change_id": args.change_id,
        "modo": args.modo,
        "aprobacion_modo": aprobacion_modo,
        "origen": "ds_guard init",
        "creado_utc": core.ahora_utc(),
        "baseline": baseline,
        "alcance": {"rutas_autorizadas": rutas_autorizadas},
        "aprobaciones": [],
        "transiciones": [],
        "sesiones": [],
    }
    core.escribir_control(change_dir / "control.json", control)
    archivos_creados.append("control.json")

    if args.json:
        print(
            json.dumps(
                {
                    "change_id": args.change_id,
                    "modo": args.modo,
                    "archivos_creados": archivos_creados,
                    "baseline": baseline,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"Cambio inicializado: {args.change_id} (modo {args.modo})")
        for nombre_archivo in archivos_creados:
            print(f"  creado: openspec/changes/{args.change_id}/{nombre_archivo}")
    return 0


# --- argparse -----------------------------------------------------------------

def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ds_guard", description=__doc__)
    subparsers = parser.add_subparsers(dest="comando", required=True)

    p_init = subparsers.add_parser(
        "init", help="Crea el scaffolding de un cambio nuevo desde las plantillas versionadas."
    )
    p_init.add_argument("--change-id", required=True)
    p_init.add_argument("--modo", required=True, choices=["completo", "abreviado"])
    p_init.add_argument(
        "--approval-mode",
        choices=list(sdd.APPROVAL_MODES),
        default=None,
        dest="approval_mode",
        help=(
            "Modo de aprobación del Change (R1/D1 de "
            "20260930-autonomous-sdd-and-remediation): 'per_change' (default, "
            "backward-compatible) o 'checkpoints' (opt-in, M7). Ausente -> "
            "'per_change', comportamiento idéntico a hoy."
        ),
    )
    p_init.add_argument("--json", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_status = subparsers.add_parser(
        "status",
        help=(
            "Con --change-id: estado del cambio SDD (informativo). Sin --change-id: status "
            "unificado de proyecto (Change 8 v0.3), de solo lectura."
        ),
    )
    p_status.add_argument("--change-id", required=False, default=None)
    p_status.add_argument("--json", action="store_true")
    p_status.add_argument(
        "--verbose",
        action="store_true",
        help="Solo aplica a la rama sin --change-id: detalle completo de checks en vez del resumen compacto.",
    )
    p_status.set_defaults(func=cmd_status)

    p_validate = subparsers.add_parser("validate", help="Corre chequeos deterministas sobre el cambio.")
    p_validate.add_argument("--change-id", required=True)
    p_validate.add_argument("--gate", choices=["implementacion", "cierre"], default=None)
    p_validate.add_argument("--json", action="store_true")
    p_validate.set_defaults(func=cmd_validate)

    p_approve = subparsers.add_parser("approve", help="Registra la aprobación (hash) de uno o más artefactos.")
    p_approve.add_argument("--change-id", required=True)
    p_approve.add_argument("--artefacto", action="append", required=True, dest="artefacto")
    p_approve.add_argument("--usuario", required=True)
    p_approve.add_argument("--fecha", required=True)
    p_approve.add_argument("--alcance", required=True)
    p_approve.add_argument("--cita", required=True)
    p_approve.set_defaults(func=cmd_approve)

    p_transition = subparsers.add_parser("transition", help="Aplica una transición de estado SDD.")
    p_transition.add_argument("--change-id", required=True)
    p_transition.add_argument("--a", required=True, dest="a")
    p_transition.add_argument("--motivo", default=None)
    p_transition.add_argument("--json", action="store_true")
    p_transition.set_defaults(func=cmd_transition)

    p_session = subparsers.add_parser("session", help="Gestión de sesiones de trabajo.")
    session_sub = p_session.add_subparsers(dest="subcomando", required=True)

    p_session_start = session_sub.add_parser("start")
    p_session_start.add_argument("--change-id", required=True)
    p_session_start.add_argument("--modo", default="estandar")
    # Default `None` (v0.8 Change 3, R8 de spec.md): si el llamador no pasa
    # `--minutos` explícito, `cmd_session_start` resuelve el valor desde
    # `autonomy.budgets.session_minutes` (o `90` si esa policy no está
    # declarada) -- ver `_resolver_budgets`. Un `--minutos` explícito manda
    # siempre, sin consultar policy.
    p_session_start.add_argument("--minutos", type=int, default=None)
    p_session_start.add_argument("--max-tareas", type=int, default=3)
    p_session_start.add_argument("--max-roles", type=int, default=2)
    p_session_start.add_argument("--max-reintentos", type=int, default=2)
    p_session_start.add_argument("--max-rondas", type=int, default=2)
    p_session_start.set_defaults(func=cmd_session_start)

    p_session_note = session_sub.add_parser("note")
    p_session_note.add_argument("--change-id", required=True)
    p_session_note.add_argument("--rol", default=None)
    p_session_note.add_argument("--tipo", required=True, choices=["planificada", "reintento", "ronda"])
    p_session_note.add_argument("--tarea", default=None)
    p_session_note.add_argument("--finding-id", default=None, dest="finding_id")
    p_session_note.add_argument(
        "--remediation-tipo",
        default=None,
        dest="remediation_tipo",
        choices=["retry_tecnico", "bug", "metodologica"],
    )
    p_session_note.add_argument("--causa", default=None)
    p_session_note.add_argument("--cambio-aplicado", default=None, dest="cambio_aplicado")
    p_session_note.add_argument("--resultado", default=None)
    p_session_note.set_defaults(func=cmd_session_note)

    p_session_status = session_sub.add_parser("status")
    p_session_status.add_argument("--change-id", required=True)
    p_session_status.add_argument("--json", action="store_true")
    p_session_status.set_defaults(func=cmd_session_status)

    p_session_close = session_sub.add_parser("close")
    p_session_close.add_argument("--change-id", required=True)
    p_session_close.add_argument("--estado", required=True, choices=["completada", "pausada"])
    p_session_close.set_defaults(func=cmd_session_close)

    p_session_aggregate = session_sub.add_parser(
        "aggregate",
        help=(
            "Presupuesto agregado entre sesiones del Change (R10-R12 de "
            "20260930-autonomous-sdd-and-remediation): minutos consumidos "
            "totales, cantidad de sesiones, y si algún tope agregado "
            "configurado (autonomy.budgets.aggregate_minutes/max_sessions) ya "
            "se alcanzó o superó. Informativo, nunca bloqueante (mismo "
            "criterio que 'session status')."
        ),
    )
    p_session_aggregate.add_argument("--change-id", required=True)
    p_session_aggregate.add_argument("--json", action="store_true")
    p_session_aggregate.set_defaults(func=cmd_session_aggregate)

    p_session_efficiency = session_sub.add_parser(
        "efficiency",
        help=(
            "Métricas de observación de eficiencia writer -> Lead (adenda "
            "post-cierre 2026-09-30 de 20260930-autonomous-sdd-and-remediation): "
            "writer_lead_cycles, remediation_cycles, executions_count, "
            "execution_duration_total_seconds. Informativo, nunca gate."
        ),
    )
    p_session_efficiency.add_argument("--change-id", required=True)
    p_session_efficiency.add_argument("--json", action="store_true")
    p_session_efficiency.set_defaults(func=cmd_session_efficiency)

    p_notebook_diff = subparsers.add_parser(
        "notebook-diff", help="Diff por celdas de uno o más .ipynb contra una revisión de git. Nunca ejecuta."
    )
    p_notebook_diff.add_argument("--change-id", required=True)
    p_notebook_diff.add_argument("--path", action="append", default=None)
    p_notebook_diff.add_argument("--tocados", action="store_true")
    p_notebook_diff.add_argument("--contra", default="baseline")
    p_notebook_diff.add_argument("--max-celdas", type=int, default=200, dest="max_celdas")
    p_notebook_diff.add_argument("--json", action="store_true")
    p_notebook_diff.set_defaults(func=cmd_notebook_diff)

    p_kdd = subparsers.add_parser("kdd", help="Lifecycle KDD del proyecto (openspec/kdd/state.json).")
    kdd_sub = p_kdd.add_subparsers(dest="subcomando", required=True)

    p_kdd_init = kdd_sub.add_parser("init", help="Crea openspec/kdd/state.json si no existe (idempotente).")
    p_kdd_init.add_argument("--json", action="store_true")
    p_kdd_init.set_defaults(func=cmd_kdd_init)

    p_kdd_status = kdd_sub.add_parser(
        "status", help="Estado de las 10 etapas KDD y criterios detectables (informativo)."
    )
    p_kdd_status.add_argument("--json", action="store_true")
    p_kdd_status.set_defaults(func=cmd_kdd_status)

    p_kdd_transition = kdd_sub.add_parser("transition", help="Avanza/retrocede el estado de una etapa KDD.")
    p_kdd_transition.add_argument("--etapa", required=True, choices=list(kdd.ETAPAS))
    p_kdd_transition.add_argument(
        "--a", required=True, dest="a", choices=sorted(kdd.ESTADOS_ETAPA_DESTINO_VALIDOS)
    )
    p_kdd_transition.add_argument("--motivo", default=None)
    p_kdd_transition.add_argument("--json", action="store_true")
    p_kdd_transition.set_defaults(func=cmd_kdd_transition)

    p_lifecycle = subparsers.add_parser(
        "lifecycle", help="Lifecycle metodologico neutral del proyecto (openspec/lifecycle/state.json)."
    )
    lifecycle_sub = p_lifecycle.add_subparsers(dest="subcomando", required=True)
    p_lifecycle_migrate = lifecycle_sub.add_parser(
        "migrate", help="Migra openspec/kdd/state.json (legacy v0.2) a openspec/lifecycle/state.json."
    )
    p_lifecycle_migrate.add_argument("--json", action="store_true")
    p_lifecycle_migrate.set_defaults(func=cmd_lifecycle_migrate)

    p_project = subparsers.add_parser("project", help="Estado de madurez/gobernanza del proyecto (.harmessi/project.json).")
    project_sub = p_project.add_subparsers(dest="subcomando", required=True)

    p_project_init = project_sub.add_parser("init")
    grupo_init = p_project_init.add_mutually_exclusive_group()
    grupo_init.add_argument("--stage", choices=list(maturity.STAGES_INIT_PERMITIDOS), default=None)
    grupo_init.add_argument("--adopt", action="store_true")
    p_project_init.add_argument("--json", action="store_true")
    p_project_init.set_defaults(func=cmd_project_init)

    p_project_calibrate = project_sub.add_parser("calibrate")
    p_project_calibrate.add_argument("--stage", required=True, choices=list(maturity.PROJECT_STAGES))
    p_project_calibrate.add_argument("--reason", required=True)
    p_project_calibrate.add_argument("--json", action="store_true")
    p_project_calibrate.set_defaults(func=cmd_project_calibrate)

    p_project_set_risk = project_sub.add_parser("set-risk")
    p_project_set_risk.add_argument("nivel", choices=list(maturity.RISK_LEVELS))
    p_project_set_risk.add_argument("--reason", required=True)
    p_project_set_risk.add_argument("--json", action="store_true")
    p_project_set_risk.set_defaults(func=cmd_project_set_risk)

    p_project_status = project_sub.add_parser("status")
    p_project_status.add_argument("--json", action="store_true")
    p_project_status.set_defaults(func=cmd_project_status)

    p_project_readiness = project_sub.add_parser(
        "readiness", help="Matriz de readiness hacia un target de madurez (solo lectura)."
    )
    p_project_readiness.add_argument("--target", required=True, choices=list(readiness.TARGETS_VALIDOS))
    p_project_readiness.add_argument("--json", action="store_true")
    p_project_readiness.set_defaults(func=cmd_project_readiness)

    p_project_promote = project_sub.add_parser(
        "promote", help="Promueve project_stage al proximo stage secuencial, gateado por readiness."
    )
    p_project_promote.add_argument("stage", choices=list(readiness.TARGETS_VALIDOS))
    p_project_promote.add_argument("--reason", required=True)
    p_project_promote.add_argument("--json", action="store_true")
    p_project_promote.set_defaults(func=cmd_project_promote)

    p_mlops = subparsers.add_parser("mlops", help="Fundamentos MLOps del proyecto (openspec/lifecycle/state.json -> mlops).")
    mlops_sub = p_mlops.add_subparsers(dest="subcomando", required=True)

    p_mlops_status = mlops_sub.add_parser("status", help="Evalúa los fundamentos MLOps (solo lectura).")
    p_mlops_status.add_argument("--json", action="store_true")
    p_mlops_status.set_defaults(func=cmd_mlops_status)

    p_mlops_record = mlops_sub.add_parser("record", help="Evalúa y persiste evidencia de los fundamentos MLOps en lifecycle/state.json.")
    p_mlops_record.add_argument("--json", action="store_true")
    p_mlops_record.set_defaults(func=cmd_mlops_record)

    p_mlops_evidence = mlops_sub.add_parser(
        "evidence", help="Evidencia de artifact para los tiers production_readiness/operations."
    )
    mlops_evidence_sub = p_mlops_evidence.add_subparsers(dest="subcomando_evidence", required=True)

    p_mlops_evidence_add = mlops_evidence_sub.add_parser("add", help="Registra evidencia de un artifact.")
    p_mlops_evidence_add.add_argument("--tier", required=True, choices=list(mlops_evidence.TIERS_EVIDENCIABLES))
    p_mlops_evidence_add.add_argument("--capability", required=True)
    p_mlops_evidence_add.add_argument("--artifact", required=True)
    p_mlops_evidence_add.add_argument("--reason", required=True)
    p_mlops_evidence_add.add_argument("--json", action="store_true")
    p_mlops_evidence_add.set_defaults(func=cmd_mlops_evidence_add)

    p_science = subparsers.add_parser("science", help="Scientific validity checks (cutoff/holdout/leakage/baseline), solo lectura.")
    science_sub = p_science.add_subparsers(dest="subcomando", required=True)
    p_science_status = science_sub.add_parser("status", help="Evalúa los scientific validity checks (.harmessi/scientific-policy.json opcional).")
    p_science_status.add_argument("--json", action="store_true")
    p_science_status.set_defaults(func=cmd_science_status)

    p_efficiency = subparsers.add_parser(
        "efficiency", help="Reporte de eficiencia de agentes por Change (solo lectura)."
    )
    efficiency_sub = p_efficiency.add_subparsers(dest="subcomando", required=True)
    p_efficiency_report = efficiency_sub.add_parser(
        "report", help="Reevalúa sesiones/remediaciones de un Change contra su propio presupuesto declarado."
    )
    p_efficiency_report.add_argument("--change-id", required=True)
    p_efficiency_report.add_argument("--json", action="store_true")
    p_efficiency_report.set_defaults(func=cmd_efficiency_report)

    p_impact = subparsers.add_parser(
        "impact", help="Impact Preflight estático (tools/dsimpact), solo lectura."
    )
    impact_sub = p_impact.add_subparsers(dest="subcomando", required=True)
    p_impact_scan = impact_sub.add_parser(
        "scan", help="Escanea un diff de Git y reporta consumidores potencialmente afectados."
    )
    grupo_impact = p_impact_scan.add_mutually_exclusive_group(required=True)
    grupo_impact.add_argument("--since", default=None)
    grupo_impact.add_argument("--staged", action="store_true")
    p_impact_scan.add_argument("--json", action="store_true")
    p_impact_scan.set_defaults(func=cmd_impact_scan)

    p_contract = subparsers.add_parser(
        "contract",
        help="Contratos de datos (tools/datacontracts, v0.7 Change 4): validate/diff/impact, solo lectura.",
    )
    contract_sub = p_contract.add_subparsers(dest="subcomando", required=True)

    p_contract_validate = contract_sub.add_parser(
        "validate",
        help=(
            "Valida un DataContract contra evidencia real: --profile (profile.json, v0.7) o "
            "--observation (SourceObservation persistida, v0.8 Change 1), mutuamente excluyentes."
        ),
    )
    p_contract_validate.add_argument("--contract", required=True)
    grupo_contract_validate = p_contract_validate.add_mutually_exclusive_group(required=True)
    grupo_contract_validate.add_argument("--profile", default=None)
    grupo_contract_validate.add_argument("--observation", default=None)
    p_contract_validate.add_argument("--record-evidence", action="store_true", dest="record_evidence")
    p_contract_validate.add_argument("--json", action="store_true")
    p_contract_validate.set_defaults(func=cmd_contract_validate)

    p_contract_diff = contract_sub.add_parser(
        "diff", help="Clasifica el cambio de compatibilidad entre dos versiones de un DataContract."
    )
    p_contract_diff.add_argument("--old", required=True)
    p_contract_diff.add_argument("--new", required=True)
    p_contract_diff.add_argument("--policy", default=None)
    p_contract_diff.add_argument("--json", action="store_true")
    p_contract_diff.set_defaults(func=cmd_contract_diff)

    p_contract_impact = contract_sub.add_parser(
        "impact",
        help=(
            "Impact preflight de un contrato (composición de tools/dsimpact), solo lectura. "
            "--since/--staged son aceptados por el parser pero no tienen efecto observable en "
            "este Change (reservados para un futuro Change que compare dos versiones vía Git)."
        ),
    )
    p_contract_impact.add_argument("--contract", required=True)
    grupo_contract_impact = p_contract_impact.add_mutually_exclusive_group()
    grupo_contract_impact.add_argument("--since", default=None)
    grupo_contract_impact.add_argument("--staged", action="store_true")
    p_contract_impact.add_argument("--fields", default=None, help="Lista separada por comas; default: todos los fields del contrato.")
    p_contract_impact.add_argument("--json", action="store_true")
    p_contract_impact.set_defaults(func=cmd_contract_impact)

    p_exec = subparsers.add_parser(
        "exec",
        help=(
            "Runtime de ejecución del Lead (tools/leadrun, v0.8 Change 2): script/pytest/notebook, "
            "con la composición de aprobación execute_project_code x modo (autonomous/supervised)."
        ),
    )
    exec_sub = p_exec.add_subparsers(dest="subcomando", required=True)

    p_exec_script = exec_sub.add_parser("script", help="Ejecuta un script .py dentro del alcance autorizado del Change.")
    _agregar_args_exec_script(p_exec_script)
    p_exec_script.add_argument("--timeout", type=int, default=600)
    p_exec_script.add_argument("--json", action="store_true")
    p_exec_script.set_defaults(func=cmd_exec_script)

    p_exec_pytest = exec_sub.add_parser("pytest", help="Ejecuta pytest sobre rutas dentro del alcance autorizado del Change.")
    _agregar_args_exec_pytest(p_exec_pytest)
    p_exec_pytest.add_argument("--timeout", type=int, default=600)
    p_exec_pytest.add_argument("--json", action="store_true")
    p_exec_pytest.set_defaults(func=cmd_exec_pytest)

    p_exec_notebook = exec_sub.add_parser("notebook", help="Ejecuta un notebook vía tools/notebook_runner.py, según un manifest.")
    _agregar_args_exec_notebook(p_exec_notebook)
    p_exec_notebook.add_argument("--timeout", type=int, default=600)
    p_exec_notebook.add_argument("--json", action="store_true")
    p_exec_notebook.set_defaults(func=cmd_exec_notebook)

    # exec approve {pytest,script,notebook} (20261002-exec-approval-registration)
    p_exec_approve = exec_sub.add_parser(
        "approve",
        help="Registra la aprobación humana de una ejecución exacta (supervised).",
        description=_DESCRIPCION_EXEC_APPROVE,
    )
    approve_sub = p_exec_approve.add_subparsers(dest="forma_aprobar", required=True)

    p_ap_pytest = approve_sub.add_parser(
        "pytest", help="Aprueba una ejecución exacta de pytest.", description=_DESCRIPCION_EXEC_APPROVE
    )
    _agregar_args_exec_pytest(p_ap_pytest)
    _agregar_args_aprobacion_humana(p_ap_pytest)
    p_ap_pytest.set_defaults(func=cmd_exec_approve_pytest)

    p_ap_script = approve_sub.add_parser(
        "script",
        help="Aprueba una ejecución exacta de script (contenido + argv).",
        description=_DESCRIPCION_EXEC_APPROVE,
    )
    _agregar_args_exec_script(p_ap_script)
    _agregar_args_aprobacion_humana(p_ap_script)
    p_ap_script.set_defaults(func=cmd_exec_approve_script)

    p_ap_notebook = approve_sub.add_parser(
        "notebook",
        help="Aprueba la ejecución de un notebook según su manifest.",
        description=_DESCRIPCION_EXEC_APPROVE,
    )
    _agregar_args_exec_notebook(p_ap_notebook)
    _agregar_args_aprobacion_humana(p_ap_notebook)
    p_ap_notebook.set_defaults(func=cmd_exec_approve_notebook)

    p_dependency = subparsers.add_parser(
        "dependency",
        help=(
            "Clasificación (M11, Change 3) e instalación gobernada aditiva "
            "(M11, resolución 2026-09-30, Change 4) de dependencias del "
            "proyecto pre-aprobadas."
        ),
    )
    dependency_sub = p_dependency.add_subparsers(dest="subcomando", required=True)

    p_dependency_classify = dependency_sub.add_parser(
        "classify",
        help=(
            "Clasifica nombre+version contra control['dependencias_preaprobadas']: "
            "'no_stop' si está listada y en rango, o el código STOP de "
            "new_dependency en cualquier otro caso."
        ),
    )
    p_dependency_classify.add_argument("--change-id", required=True)
    p_dependency_classify.add_argument("--nombre", required=True)
    p_dependency_classify.add_argument("--version", required=True)
    p_dependency_classify.add_argument("--json", action="store_true")
    p_dependency_classify.set_defaults(func=cmd_dependency_classify)

    p_dependency_install = dependency_sub.add_parser(
        "install",
        help=(
            "Instala una dependencia del proyecto pre-aprobada (M11, resolución 2026-09-30): "
            "clasifica (R25), resuelve el .venv del proyecto (R27/R34), construye el comando "
            "cerrado -m pip install --no-deps <nombre>==<versión> (R24/R37) y lo ejecuta vía el "
            "runtime gobernado de Change 2. Sin --interpreter, sin ningún flag libre de pip "
            "(R31/R34)."
        ),
    )
    p_dependency_install.add_argument("--change-id", required=True, dest="change_id")
    p_dependency_install.add_argument("--nombre", required=True)
    p_dependency_install.add_argument("--version", required=True)
    p_dependency_install.add_argument("--json", action="store_true")
    p_dependency_install.set_defaults(func=cmd_dependency_install)

    p_output_roots = subparsers.add_parser(
        "output-roots",
        help=(
            "Output roots declarados para que código del proyecto los consulte (R18, M12). "
            "Control COOPERATIVO, no sandbox: informativo, no intercepta escrituras arbitrarias, "
            "no reemplaza pathguard ni el fingerprint pre/post de fuentes externas."
        ),
    )
    output_roots_sub = p_output_roots.add_subparsers(dest="subcomando", required=True)

    p_output_roots_list = output_roots_sub.add_parser(
        "list",
        help="Imprime los output roots declarados en project-config.json/local-overrides.json (unión).",
    )
    p_output_roots_list.add_argument("--json", action="store_true")
    p_output_roots_list.set_defaults(func=cmd_output_roots_list)

    p_source = subparsers.add_parser(
        "source",
        help=(
            "Fuentes de datos neutrales (tools/datasources, v0.8 Change 1): list/check/observe/"
            "check-stale. Best-effort en el escaneo de secretos/localizadores (R19); sin timeout "
            "en proceso (R17): un observer colgado bloquea el proceso que lo invoca."
        ),
    )
    source_sub = p_source.add_subparsers(dest="subcomando", required=True)

    p_source_list = source_sub.add_parser("list", help="Lista las fuentes del registro (.harmessi/sources.json).")
    p_source_list.add_argument("--json", action="store_true")
    p_source_list.set_defaults(func=cmd_source_list)

    p_source_check = source_sub.add_parser("check", help="Validación estática del registro (sin importar observers).")
    p_source_check.add_argument("--json", action="store_true")
    p_source_check.set_defaults(func=cmd_source_check)

    p_source_observe = source_sub.add_parser(
        "observe",
        help=(
            "Observa una fuente (access_check real + import del observer + persistencia). "
            "Best-effort en el escaneo de secretos/localizadores (R19); sin timeout en proceso (R17)."
        ),
    )
    p_source_observe.add_argument("--source-id", required=True, dest="source_id")
    p_source_observe.add_argument("--facet", action="append", default=None)
    p_source_observe.add_argument("--exactness", default=None, choices=["any", "exact"])
    p_source_observe.add_argument("--as-of", default=None, dest="as_of")
    p_source_observe.add_argument("--json", action="store_true")
    p_source_observe.set_defaults(func=cmd_source_observe)

    p_source_check_stale = source_sub.add_parser(
        "check-stale", help="Compara una observación persistida contra una re-observación de fingerprint."
    )
    p_source_check_stale.add_argument("--observation", required=True)
    p_source_check_stale.add_argument("--json", action="store_true")
    p_source_check_stale.set_defaults(func=cmd_source_check_stale)

    p_quality = subparsers.add_parser(
        "quality",
        help="Calidad de modelo y evidencia (tools/modelquality, tools/qualityevidence, v0.7 Change 4).",
    )
    quality_sub = p_quality.add_subparsers(dest="subcomando", required=True)

    p_quality_evaluate = quality_sub.add_parser(
        "evaluate", help="Evalúa una ModelQualityPolicy contra métricas ya observadas."
    )
    p_quality_evaluate.add_argument("--policy", required=True)
    p_quality_evaluate.add_argument("--metrics", required=True)
    p_quality_evaluate.add_argument("--baselines", default=None)
    p_quality_evaluate.add_argument("--record-evidence", action="store_true", dest="record_evidence")
    p_quality_evaluate.add_argument("--json", action="store_true")
    p_quality_evaluate.set_defaults(func=cmd_quality_evaluate)

    p_quality_evidence = quality_sub.add_parser(
        "evidence", help="Evidencia de calidad persistida (.harmessi/quality/<evidence_id>/manifest.json)."
    )
    quality_evidence_sub = p_quality_evidence.add_subparsers(dest="subcomando_evidence", required=True)
    p_quality_evidence_show = quality_evidence_sub.add_parser("show", help="Muestra un manifest de evidencia ya persistido.")
    p_quality_evidence_show.add_argument("--evidence-id", required=True, dest="evidence_id")
    p_quality_evidence_show.add_argument("--json", action="store_true")
    p_quality_evidence_show.set_defaults(func=cmd_quality_evidence_show)

    p_quality_drift = quality_sub.add_parser(
        "drift", help="Calcula drift entre dos profile.json (solo lectura, nunca escribe evidencia)."
    )
    p_quality_drift.add_argument("--baseline-profile", required=True, dest="baseline_profile")
    p_quality_drift.add_argument("--current-profile", required=True, dest="current_profile")
    p_quality_drift.add_argument("--metric", required=True)
    p_quality_drift.add_argument("--field", required=True)
    p_quality_drift.add_argument(
        "--column",
        default=None,
        help=(
            "Nombre de columna (requerido por drift_from_profiles para field != 'filas': "
            "nulls_count/unique_count/min/max)."
        ),
    )
    p_quality_drift.add_argument("--mode", required=True, choices=["absolute_diff", "relative_diff"])
    p_quality_drift.add_argument("--threshold", type=float, default=None)
    p_quality_drift.add_argument("--baseline-label", default="baseline", dest="baseline_label")
    p_quality_drift.add_argument("--current-label", default="current", dest="current_label")
    p_quality_drift.add_argument("--json", action="store_true")
    p_quality_drift.set_defaults(func=cmd_quality_drift)

    p_cards = subparsers.add_parser(
        "cards", help="Cards de governance (Data Card, Model Card, assessment): validación y reporte."
    )
    cards_sub = p_cards.add_subparsers(dest="subcomando", required=True)
    p_cards_validate = cards_sub.add_parser(
        "validate", help="Valida Cards por rutas conocidas o --path (solo lectura)."
    )
    p_cards_validate.add_argument("--path", action="append", default=[], help="Archivo de Card (repetible).")
    p_cards_validate.add_argument("--kind", choices=["data", "model", "governance"], default=None)
    p_cards_validate.add_argument("--json", action="store_true")
    p_cards_validate.set_defaults(func=cmd_cards_validate)
    p_cards_report = cards_sub.add_parser(
        "report", help="Valida y publica el reporte de UNA Card (reporting.publish)."
    )
    p_cards_report.add_argument("--path", required=True)
    p_cards_report.add_argument("--out-dir", default=None, dest="out_dir")
    p_cards_report.add_argument("--json", action="store_true")
    p_cards_report.set_defaults(func=cmd_cards_report)

    p_archive = subparsers.add_parser(
        "archive", help="Archiva un cambio cerrado de openspec/changes/ a openspec/archive/ (git mv)."
    )
    p_archive.add_argument("--change-id", required=True)
    grupo_archive = p_archive.add_mutually_exclusive_group()
    grupo_archive.add_argument("--dry-run", action="store_true", help="No mueve nada (comportamiento por defecto).")
    grupo_archive.add_argument("--execute", action="store_true", help="Ejecuta el git mv real.")
    p_archive.add_argument("--json", action="store_true")
    p_archive.set_defaults(func=cmd_archive)

    p_remediation = subparsers.add_parser(
        "remediation", help="Bounded remediation (control['remediaciones']): resolve/extend."
    )
    remediation_sub = p_remediation.add_subparsers(dest="subcomando", required=True)

    p_remediation_resolve = remediation_sub.add_parser("resolve")
    p_remediation_resolve.add_argument("--change-id", required=True)
    p_remediation_resolve.add_argument("--remediation-id", required=True, dest="remediation_id")
    p_remediation_resolve.add_argument("--resultado", required=True)
    p_remediation_resolve.add_argument("--json", action="store_true")
    p_remediation_resolve.set_defaults(func=cmd_remediation_resolve)

    p_remediation_extend = remediation_sub.add_parser("extend")
    p_remediation_extend.add_argument("--change-id", required=True)
    p_remediation_extend.add_argument("--remediation-id", required=True, dest="remediation_id")
    p_remediation_extend.add_argument("--usuario", required=True)
    p_remediation_extend.add_argument("--fecha", required=True)
    p_remediation_extend.add_argument("--motivo", required=True)
    p_remediation_extend.add_argument("--max-intentos", type=int, default=2, dest="max_intentos")
    p_remediation_extend.add_argument("--json", action="store_true")
    p_remediation_extend.set_defaults(func=cmd_remediation_extend)

    p_decision = subparsers.add_parser("decision", help="Decision ledger del proyecto (openspec/decisions/ledger.jsonl).")
    decision_sub = p_decision.add_subparsers(dest="subcomando", required=True)

    def _agregar_flags_comunes_decision(p):
        p.add_argument("--decision-id", required=True, dest="decision_id")
        p.add_argument("--tipo", required=True, choices=sorted(decision.TIPOS_DECISION))
        p.add_argument("--resumen", required=True)
        p.add_argument("--rationale", required=True)
        p.add_argument("--usuario", required=True)
        p.add_argument("--fecha", required=True)
        p.add_argument("--cita", required=True)
        p.add_argument("--change-id", default=None, dest="change_id")
        p.add_argument("--kdd-etapa", default=None, dest="kdd_etapa", choices=list(kdd.ETAPAS))
        p.add_argument("--evidencia", action="append", default=None)
        p.add_argument("--json", action="store_true")

    p_decision_add = decision_sub.add_parser("add")
    _agregar_flags_comunes_decision(p_decision_add)
    p_decision_add.set_defaults(func=cmd_decision_add)

    p_decision_supersede = decision_sub.add_parser("supersede")
    _agregar_flags_comunes_decision(p_decision_supersede)
    p_decision_supersede.add_argument("--referencia", required=True)
    p_decision_supersede.set_defaults(func=cmd_decision_supersede)

    p_decision_revoke = decision_sub.add_parser("revoke")
    p_decision_revoke.add_argument("--referencia", required=True)
    p_decision_revoke.add_argument("--motivo", required=True)
    p_decision_revoke.add_argument("--usuario", required=True)
    p_decision_revoke.add_argument("--fecha", required=True)
    p_decision_revoke.add_argument("--json", action="store_true")
    p_decision_revoke.set_defaults(func=cmd_decision_revoke)

    p_decision_list = decision_sub.add_parser("list")
    p_decision_list.add_argument("--tipo", default=None, choices=sorted(decision.TIPOS_DECISION))
    p_decision_list.add_argument("--estado", default=None, choices=["activa", "superseded", "revocada"])
    p_decision_list.add_argument("--change-id", default=None, dest="change_id")
    p_decision_list.add_argument("--json", action="store_true")
    p_decision_list.set_defaults(func=cmd_decision_list)

    p_decision_show = decision_sub.add_parser("show")
    p_decision_show.add_argument("--decision-id", required=True, dest="decision_id")
    p_decision_show.add_argument("--json", action="store_true")
    p_decision_show.set_defaults(func=cmd_decision_show)

    return parser


def main(argv=None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
