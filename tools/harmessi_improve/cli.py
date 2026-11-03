"""CLI de `harmessi_improve`: `python -m tools.harmessi_improve <comando> ...` (v0.14 Change 5, R10).

Por qué existe: expone por línea de comandos el flujo gobernado ya implementado en el paquete
(candidate -> probe -> decide -> promote; lessons; ciclo acotado) SIN agregar reglas propias: cada
handler delega en la API del módulo correspondiente.

Códigos de salida:
- 0: ok. Incluye un `cycle` que terminó por agotar un presupuesto (`detenido_por` != null): es un fin
  determinista y esperado del ciclo, no un error; el JSON informa el recurso.
- 1: rechazo de regla o gate (CandidateRechazada, ProbeRechazado, PromocionBloqueada, LessonRechazada,
  PresupuestoAgotado, EvidenciaInvalida, PromocionNoRespaldada, ProbeIncompatible, ...).
- 2: uso inválido (argparse, política inválida, archivos de entrada ilegibles o mal formados).
- 3: error de entorno inesperado.
Los mensajes de error no llevan rutas absolutas del repo ni tracebacks. Sin telemetría.

`_resolver_adapter(provider_id)` es el único punto que toca `tools.providers` (import diferido de
`PROVIDER_REGISTRY`); los tests lo parchean para inyectar un adapter falso.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.harmessi_bench.core import EvalTarget
from tools.harmessi_improve import budget as _budget
from tools.harmessi_improve import candidate as _candidate
from tools.harmessi_improve import cycle as _cycle
from tools.harmessi_improve import decision as _decision
from tools.harmessi_improve import lessons as _lessons
from tools.harmessi_improve import probe as _probe
from tools.harmessi_improve import promotion as _promotion
from tools.harmessi_improve.policy import PolicyInvalida, ProbePolicy

# Única fuente de los códigos de salida (anclan el inventario de contratos, docs/contracts/inventory.json).
EXIT_OK = 0
EXIT_REGLA = 1
EXIT_USO = 2
EXIT_ENTORNO = 3

SALIDA_OK = EXIT_OK
SALIDA_REGLA = EXIT_REGLA
SALIDA_USO = EXIT_USO
SALIDA_ENTORNO = EXIT_ENTORNO

# Excepciones de regla/gate => salida 1.
_ERRORES_REGLA = (
    _candidate.CandidateRechazada,
    _candidate.CandidateCorrupta,
    _probe.ProbeRechazado,
    _probe.ProbeIncompatible,
    _probe.ProbeCorrupto,
    _budget.PresupuestoAgotado,
    _budget.PresupuestoInvalido,
    _decision.EvidenciaInvalida,
    _decision.PromocionNoRespaldada,
    _promotion.PromocionBloqueada,
    _promotion.PropuestaInvalida,
    _lessons.LessonRechazada,
    _cycle.CicloAnidado,
)


class _UsoInvalido(Exception):
    """Entrada inválida detectada por la CLI (salida 2)."""


class _EntornoNoDisponible(Exception):
    """Provider no disponible u otro problema de entorno previsto (salida 3)."""


# --- Utilidades --------------------------------------------------------------------

def _raiz_por_defecto() -> Path:
    return Path(__file__).resolve().parents[2]


def _raices_texto(repo_root: Path) -> list:
    candidatos = set()
    for ruta in (repo_root, repo_root.resolve()):
        candidatos.add(str(ruta))
        candidatos.add(ruta.as_posix())
    return sorted((c for c in candidatos if c), key=len, reverse=True)


def _sanear(valor, raices):
    """Reemplaza la ruta del repo por `<repo>` en todo texto (recursivo)."""
    if isinstance(valor, str):
        for raiz in raices:
            valor = valor.replace(raiz, "<repo>")
        return valor
    if isinstance(valor, dict):
        return {k: _sanear(v, raices) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_sanear(v, raices) for v in valor]
    return valor


def _mensaje_error(exc: Exception) -> str:
    """Mensaje limpio: ante `OSError` cita solo el nombre de archivo; con `codigo` lo antepone."""
    if isinstance(exc, OSError):
        nombre = Path(str(exc.filename)).name if exc.filename else ""
        causa = exc.strerror or type(exc).__name__
        return f"{causa}: {nombre}" if nombre else causa
    if isinstance(exc, _promotion.PromocionBloqueada):
        return "promoción bloqueada: " + ", ".join(exc.motivos)
    return str(exc) or type(exc).__name__


def _emitir(args, datos, texto: str, raices) -> None:
    if args.json:
        print(json.dumps(_sanear(datos, raices), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_sanear(texto, raices))


def _leer_texto(ruta: str) -> str:
    try:
        return Path(ruta).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _UsoInvalido(f"no se pudo leer el archivo de entrada: {_mensaje_error(exc) if isinstance(exc, OSError) else Path(ruta).name}") from None


def _leer_json(ruta: str):
    try:
        return json.loads(_leer_texto(ruta))
    except json.JSONDecodeError:
        raise _UsoInvalido(f"JSON inválido en el archivo de entrada: {Path(ruta).name}") from None


def _resolver_adapter(provider_id: str):
    """Devuelve el adapter del provider. Import diferido de `PROVIDER_REGISTRY`; los tests parchean
    esta función para inyectar un adapter falso."""
    from tools.providers import PROVIDER_REGISTRY

    adapter = PROVIDER_REGISTRY.get(provider_id)
    if adapter is None:
        raise _UsoInvalido(f"provider desconocido: {provider_id!r} (registrados: {sorted(PROVIDER_REGISTRY)})")
    info = adapter.detect()
    if info is not None and not info.available:
        raise _EntornoNoDisponible(f"provider {provider_id!r} no disponible: {info.detail}")
    return adapter


def _policy_desde_args(args) -> ProbePolicy:
    kwargs = {}
    for clave in ("repeats", "min_scenarios", "min_stable_ratio", "tie_policy", "min_delta"):
        valor = getattr(args, clave, None)
        if valor is not None:
            kwargs[clave] = valor
    try:
        return ProbePolicy(**kwargs)
    except PolicyInvalida as exc:
        raise _UsoInvalido(f"política inválida: {exc}") from None


def _target_desde_args(args) -> EvalTarget:
    return EvalTarget(provider_id=args.provider, model=args.model, effort=args.effort)


# --- Handlers ----------------------------------------------------------------------

def _cmd_budget_show(args, raiz: Path):
    presupuesto = _budget.cargar_presupuesto(raiz)
    datos = {"presupuesto": {k: getattr(presupuesto, k) for k in presupuesto.__dataclass_fields__},
             "estado": _budget.estado(raiz)}
    lineas = ["presupuesto:"] + [f"  {k}: {v}" for k, v in datos["presupuesto"].items()]
    lineas += ["estado:"] + [f"  {k}: {v}" for k, v in datos["estado"].items()]
    return datos, "\n".join(lineas)


def _cmd_candidate_create(args, raiz: Path):
    contenido = _leer_texto(args.content_file)
    provenance = {"proposer_kind": args.proposer_kind, "proposer_label": args.proposer_label}
    cand = _candidate.crear_candidate(raiz, args.base_surface, contenido, args.hypothesis, provenance,
                                      suite_ids=tuple(args.suite_id or ()))
    datos = cand.a_dict()
    return datos, f"candidate {cand.candidate_id} creada (status={cand.status}) sobre {cand.base_surface}"


def _cmd_candidate_list(args, raiz: Path):
    cands = _candidate.listar_candidates(raiz)
    datos = [c.a_dict() for c in cands]
    texto = "\n".join(f"{c.candidate_id}  {c.status}  {c.base_surface}" for c in cands) or "(sin candidates)"
    return datos, texto


def _cmd_candidate_show(args, raiz: Path):
    cand = _candidate.cargar_candidate(raiz, args.candidate_id)
    return cand.a_dict(), json.dumps(cand.a_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def _cmd_probe(args, raiz: Path):
    policy = _policy_desde_args(args)
    adapter = _resolver_adapter(args.provider)
    resultado = _probe.ejecutar_probe(
        raiz, args.candidate, args.suite, adapter, _target_desde_args(args), policy, args.probe_id,
        seed=args.seed, resume=args.resume)
    texto = f"probe {args.probe_id} de {args.candidate}: status={resultado.get('status')}"
    return resultado, texto


def _cmd_decide(args, raiz: Path):
    if args.apply:
        cand = _decision.aplicar_decision(raiz, args.probe_id)
        decision = _decision.cargar_decision(raiz, args.probe_id)
        datos = {"aplicada": True, "decision": decision, "candidate_status": cand.status}
        texto = (f"decisión {decision.get('verdict')} registrada para {args.probe_id}; "
                 f"candidate {cand.candidate_id} -> {cand.status}")
    else:
        decision = _decision.decidir(raiz, args.probe_id, registrar=False)
        datos = {"aplicada": False, "decision": decision}
        texto = f"decisión {decision.get('verdict')} para {args.probe_id} (no registrada; usá --apply)"
    return datos, texto


def _cmd_promote_propose(args, raiz: Path):
    propuesta = _promotion.proponer_promocion(raiz, args.candidate)
    return propuesta, f"propuesta de promoción escrita para {args.candidate}"


def _cmd_promote_gate(args, raiz: Path):
    motivos = _promotion.evaluar_gate(raiz, args.candidate, args.change_id)
    datos = {"candidate_id": args.candidate, "change_id": args.change_id, "pasa": not motivos, "motivos": list(motivos)}
    if motivos:
        # El gate bloqueado es un rechazo de regla: se informa en el cuerpo y sale con 1.
        raise _promotion.PromocionBloqueada(motivos)
    return datos, f"gate OK para {args.candidate} en {args.change_id}"


def _cmd_promote_apply(args, raiz: Path):
    resultado = _promotion.aplicar_promocion(raiz, args.candidate, args.change_id)
    return resultado, f"promoción aplicada: {args.candidate} en {args.change_id}"


def _parsear_evidencia(textos) -> list:
    refs = []
    for texto in textos:
        partes = texto.split(":")
        if len(partes) != 3 or not all(partes):
            raise _UsoInvalido("--evidence exige el formato probe_id:decision_hash:suite_id")
        refs.append({"probe_id": partes[0], "decision_hash": partes[1], "suite_id": partes[2]})
    return refs


def _cmd_lesson_add(args, raiz: Path):
    lesson = _lessons.crear_lesson(raiz, args.change_id, args.pattern, args.recommendation,
                                   list(args.context), _parsear_evidencia(args.evidence))
    return lesson, f"lesson {lesson.get('lesson_id')} registrada"


def _cmd_lesson_list(args, raiz: Path):
    lecciones = _lessons.listar_lessons(raiz)
    texto = "\n".join(f"{x.get('lesson_id')}  {x.get('pattern')}" for x in lecciones) or "(sin lessons)"
    return lecciones, texto


def _cmd_lesson_applicable(args, raiz: Path):
    res = _lessons.lessons_aplicables(raiz, list(args.context))
    texto = (f"{len(res['aplicables'])} aplicables, {len(res['descartadas'])} descartadas\n"
             + "\n".join(f"  {x.get('lesson_id')}  {x.get('pattern')}" for x in res["aplicables"]))
    return res, texto


def _cmd_cycle(args, raiz: Path):
    propuestas = _leer_json(args.proposals_file)
    if not isinstance(propuestas, list):
        raise _UsoInvalido("--proposals-file debe contener una lista JSON de propuestas")
    policy = _policy_desde_args(args)
    adapter = _resolver_adapter(args.provider)
    res = _cycle.ejecutar_ciclo(raiz, propuestas, args.suite, adapter, _target_desde_args(args), policy, seed=args.seed)
    texto = (f"ciclo: {len(res['resultados'])} candidates, {len(res['rechazos'])} rechazos, "
             f"detenido_por={res['detenido_por']}")
    return res, texto


# --- Parser ------------------------------------------------------------------------

def _agregar_policy(p: argparse.ArgumentParser) -> None:
    p.add_argument("--repeats", type=int, default=None)
    p.add_argument("--min-scenarios", type=int, default=None, dest="min_scenarios")
    p.add_argument("--min-stable-ratio", type=float, default=None, dest="min_stable_ratio")
    p.add_argument("--tie-policy", default=None, dest="tie_policy")
    p.add_argument("--min-delta", type=float, default=None, dest="min_delta")


def _agregar_target(p: argparse.ArgumentParser) -> None:
    p.add_argument("--provider", required=True)
    p.add_argument("--model", default=None)
    p.add_argument("--effort", default=None)
    p.add_argument("--seed", type=int, default=None)


def _construir_parser() -> argparse.ArgumentParser:
    comun = argparse.ArgumentParser(add_help=False)
    comun.add_argument("--repo-root", default=None, dest="repo_root",
                       help="Raíz del repo (default: la del checkout de este paquete).")
    comun.add_argument("--json", action="store_true")

    parser = argparse.ArgumentParser(prog="python -m tools.harmessi_improve",
                                     description="Ciclo de mejora gobernado de Harmessi (v0.14).")
    sub = parser.add_subparsers(dest="comando", required=True)

    def hoja(grupo, nombre, func, ayuda):
        p = grupo.add_parser(nombre, parents=[comun], help=ayuda)
        p.set_defaults(func=func)
        return p

    p_budget = sub.add_parser("budget", help="Presupuesto de mejora.")
    hoja(p_budget.add_subparsers(dest="sub", required=True), "show", _cmd_budget_show, "Muestra presupuesto y consumo.")

    p_cand = sub.add_parser("candidate", help="Candidates.")
    g = p_cand.add_subparsers(dest="sub", required=True)
    p = hoja(g, "create", _cmd_candidate_create, "Crea una candidate.")
    p.add_argument("--base-surface", required=True, dest="base_surface")
    p.add_argument("--content-file", required=True, dest="content_file")
    p.add_argument("--hypothesis", required=True)
    p.add_argument("--proposer-kind", default="human", choices=["llm", "human", "script"], dest="proposer_kind")
    p.add_argument("--proposer-label", default="cli", dest="proposer_label")
    p.add_argument("--suite-id", action="append", default=None, dest="suite_id")
    hoja(g, "list", _cmd_candidate_list, "Lista candidates.")
    p = hoja(g, "show", _cmd_candidate_show, "Muestra una candidate.")
    p.add_argument("candidate_id")

    p = hoja(sub, "probe", _cmd_probe, "Ejecuta un probe baseline-vs-candidate.")
    p.add_argument("--candidate", required=True)
    p.add_argument("--suite", required=True)
    _agregar_target(p)
    p.add_argument("--probe-id", required=True, dest="probe_id")
    _agregar_policy(p)
    p.add_argument("--resume", action="store_true")

    p = hoja(sub, "decide", _cmd_decide, "Decide sobre la evidencia de un probe.")
    p.add_argument("--probe-id", required=True, dest="probe_id")
    p.add_argument("--apply", action="store_true", help="Registra la decisión y transiciona la candidate.")

    p_prom = sub.add_parser("promote", help="Promoción gobernada.")
    g = p_prom.add_subparsers(dest="sub", required=True)
    p = hoja(g, "propose", _cmd_promote_propose, "Escribe la propuesta de promoción.")
    p.add_argument("--candidate", required=True)
    p = hoja(g, "gate", _cmd_promote_gate, "Evalúa el gate de promoción (solo lectura).")
    p.add_argument("--candidate", required=True)
    p.add_argument("--change-id", required=True, dest="change_id")
    p = hoja(g, "apply", _cmd_promote_apply, "Aplica la promoción si el gate pasa.")
    p.add_argument("--candidate", required=True)
    p.add_argument("--change-id", required=True, dest="change_id")

    p_les = sub.add_parser("lesson", help="Biblioteca de lessons.")
    g = p_les.add_subparsers(dest="sub", required=True)
    p = hoja(g, "add", _cmd_lesson_add, "Registra una lesson (exige un Change abierto).")
    p.add_argument("--change-id", required=True, dest="change_id")
    p.add_argument("--pattern", required=True)
    p.add_argument("--recommendation", required=True)
    p.add_argument("--context", nargs="+", required=True)
    p.add_argument("--evidence", nargs="+", required=True, help="probe_id:decision_hash:suite_id")
    hoja(g, "list", _cmd_lesson_list, "Lista lessons.")
    p = hoja(g, "applicable", _cmd_lesson_applicable, "Lessons aplicables a un contexto.")
    p.add_argument("--context", nargs="+", required=True)

    p = hoja(sub, "cycle", _cmd_cycle, "Ciclo acotado de mejora.")
    p.add_argument("--proposals-file", required=True, dest="proposals_file")
    p.add_argument("--suite", required=True)
    _agregar_target(p)
    _agregar_policy(p)

    return parser


# --- Entrada -----------------------------------------------------------------------

def _consola_segura() -> None:
    """Best-effort: con consola no UTF-8 los caracteres no representables se reemplazan."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv=None) -> int:
    _consola_segura()
    parser = _construir_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as salida:  # argparse: 2 ante uso inválido, 0 ante --help
        return salida.code if isinstance(salida.code, int) else SALIDA_USO
    raiz = Path(args.repo_root) if args.repo_root else _raiz_por_defecto()
    raices = _raices_texto(raiz)
    try:
        datos, texto = args.func(args, raiz)
    except _UsoInvalido as exc:
        print(_sanear(str(exc), raices), file=sys.stderr)
        return SALIDA_USO
    except _ERRORES_REGLA as exc:
        print(_sanear(_mensaje_error(exc), raices), file=sys.stderr)
        return SALIDA_REGLA
    except _EntornoNoDisponible as exc:
        print(_sanear(str(exc), raices), file=sys.stderr)
        return SALIDA_ENTORNO
    except Exception as exc:  # error de entorno inesperado: sin traceback ni rutas
        print(_sanear(f"error inesperado ({type(exc).__name__}): {_mensaje_error(exc)}", raices), file=sys.stderr)
        return SALIDA_ENTORNO
    _emitir(args, datos, texto, raices)
    return SALIDA_OK


if __name__ == "__main__":
    sys.exit(main())
