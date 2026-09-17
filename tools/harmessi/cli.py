"""Interfaz de línea de comandos de `harmessi` (Bloque 2, reliability
v0.2.0; subcomando `providers` agregado en v0.5 Change 0,
`multi-provider-adapters`; subcomando `routing` agregado en v0.5 Change 2,
`provider-routing`; subcomando `fallback` agregado en v0.5 Change 3,
`fallback-and-handoffs`). Soporta `doctor`, `providers`, `routing` y
`fallback`; `init` (hoy `python -m tools.ds_init`), `update` y `uninstall`
quedan para versiones futuras -- ver `tools/harmessi/__init__.py`.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from . import doctor as doctor_mod


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.harmessi",
        description=(
            "CLI de Harmessi. Soporta los subcomandos 'doctor', 'providers', 'routing' y 'fallback'."
        ),
    )
    subparsers = parser.add_subparsers(dest="subcomando", required=True)

    doctor_parser = subparsers.add_parser(
        "doctor", help="Diagnóstico de salud (solo lectura) de una instalación de Harmessi."
    )
    doctor_parser.add_argument(
        "--destino",
        default=".",
        help="Repo del proyecto a diagnosticar (default: directorio actual).",
    )

    providers_parser = subparsers.add_parser(
        "providers", help="Adapters de proveedor de IA (v0.5 Change 0)."
    )
    providers_subparsers = providers_parser.add_subparsers(
        dest="providers_subcomando", required=True
    )
    providers_list_parser = providers_subparsers.add_parser(
        "list", help="Detecta y lista los proveedores registrados (claude_code, codex, gemini, grok)."
    )
    providers_list_parser.add_argument(
        "--json", action="store_true", help="Formato de salida JSON en vez de tabla de texto."
    )

    routing_parser = subparsers.add_parser(
        "routing", help="Resolución declarativa de provider/model/effort por rol+tarea (v0.5 Change 2)."
    )
    routing_subparsers = routing_parser.add_subparsers(
        dest="routing_subcomando", required=True
    )

    routing_show_parser = routing_subparsers.add_parser(
        "show", help="Muestra la política de routing declarada (o su ausencia)."
    )
    routing_show_parser.add_argument(
        "--policy",
        default=None,
        help="Ruta a la política de routing (default: .harmessi/routing.json).",
    )
    routing_show_parser.add_argument(
        "--json", action="store_true", help="Formato de salida JSON en vez de texto."
    )

    routing_resolve_parser = routing_subparsers.add_parser(
        "resolve", help="Resuelve provider/model/effort para un rol+tipo de tarea dados."
    )
    routing_resolve_parser.add_argument("--role", required=True, help="Rol a resolver.")
    routing_resolve_parser.add_argument(
        "--task-type", default="default", help="Tipo de tarea (default: 'default')."
    )
    routing_resolve_parser.add_argument(
        "--policy",
        default=None,
        help="Ruta a la política de routing (default: .harmessi/routing.json).",
    )
    routing_resolve_parser.add_argument(
        "--check-availability",
        action="store_true",
        help="Chequea disponibilidad real vía tools.providers.list_providers().",
    )
    routing_resolve_parser.add_argument(
        "--json", action="store_true", help="Formato de salida JSON en vez de texto."
    )

    fallback_parser = subparsers.add_parser(
        "fallback", help="Motor de fallback técnico entre proveedores (v0.5 Change 3)."
    )
    fallback_subparsers = fallback_parser.add_subparsers(
        dest="fallback_subcomando", required=True
    )

    fallback_resolve_chain_parser = fallback_subparsers.add_parser(
        "resolve-chain",
        help=(
            "Resuelve la cadena candidata provider_id + fallback_chain para un rol+tarea, "
            "e informa disponibilidad de cada uno, sin invocar nada."
        ),
    )
    fallback_resolve_chain_parser.add_argument("--role", required=True, help="Rol a resolver.")
    fallback_resolve_chain_parser.add_argument(
        "--task-type", default="default", help="Tipo de tarea (default: 'default')."
    )
    fallback_resolve_chain_parser.add_argument(
        "--policy",
        default=None,
        help="Ruta a la política de routing (default: .harmessi/routing.json).",
    )
    fallback_resolve_chain_parser.add_argument(
        "--json", action="store_true", help="Formato de salida JSON en vez de texto."
    )

    fallback_invoke_parser = fallback_subparsers.add_parser(
        "invoke",
        help="Resuelve la cadena de fallback y la invoca de verdad vía tools.fallback.core.",
    )
    fallback_invoke_parser.add_argument("--role", required=True, help="Rol a resolver.")
    fallback_invoke_parser.add_argument("--prompt", required=True, help="Prompt a invocar.")
    fallback_invoke_parser.add_argument(
        "--task-type", default="default", help="Tipo de tarea (default: 'default')."
    )
    fallback_invoke_parser.add_argument(
        "--policy",
        default=None,
        help="Ruta a la política de routing (default: .harmessi/routing.json).",
    )
    fallback_invoke_parser.add_argument("--model", default=None, help="Modelo a pedir (opcional).")
    fallback_invoke_parser.add_argument("--effort", default=None, help="Effort a pedir (opcional).")
    fallback_invoke_parser.add_argument(
        "--json", action="store_true", help="Formato de salida JSON en vez de texto."
    )

    return parser


def _formatear_providers_tabla(infos: list) -> str:
    """Tabla de texto simple (provider_id, available, version, detail),
    mismo criterio de `doctor.formatear`: una línea por entrada, sin
    dependencias de terceros."""
    lineas = ["Harmessi providers"]
    for info in infos:
        version = info.version or "-"
        lineas.append(
            f"[{'OK' if info.available else 'NO'}] {info.provider_id}: version={version} -- {info.detail}"
        )
    return "\n".join(lineas)


def _providers_info_a_dict(info) -> dict:
    return {
        "provider_id": info.provider_id,
        "display_name": info.display_name,
        "cli_command": info.cli_command,
        "available": info.available,
        "authenticated": info.authenticated,
        "version": info.version,
        "capabilities": {
            "streaming": info.capabilities.streaming,
            "tool_use": info.capabilities.tool_use,
            "thinking_effort": info.capabilities.thinking_effort,
            "handoff": info.capabilities.handoff,
        },
        "detail": info.detail,
    }


def _formatear_routing_policy_texto(policy, ruta_mostrada: str) -> str:
    """Mismo criterio que `_formatear_providers_tabla`: texto simple, sin
    dependencias de terceros. Si no hay política declarada (`rules=[]` y
    `default is None`), lo dice explícitamente -- nunca un JSON/tabla vacía
    sin contexto."""
    if not policy.rules and policy.default is None:
        return f"sin política de routing declarada en {ruta_mostrada}"

    lineas = [f"Harmessi routing policy ({ruta_mostrada})"]
    for regla in policy.rules:
        lineas.append(
            f"- role={regla.role} task_type={regla.task_type} -> "
            f"provider_id={regla.provider_id} model={regla.model} effort={regla.effort} "
            f"-- {regla.reason}"
        )
    if policy.default is not None:
        regla = policy.default
        lineas.append(
            f"- [default] provider_id={regla.provider_id} model={regla.model} "
            f"effort={regla.effort} -- {regla.reason}"
        )
    else:
        lineas.append("- [default] no declarado")
    return "\n".join(lineas)


def _routing_policy_a_dict(policy) -> dict:
    return {
        "rules": [dataclasses.asdict(regla) for regla in policy.rules],
        "default": dataclasses.asdict(policy.default) if policy.default is not None else None,
    }


def _formatear_routing_decision_texto(decision) -> str:
    disponibilidad = (
        "sin chequear" if decision.provider_available is None
        else ("disponible" if decision.provider_available else "no disponible")
    )
    return (
        f"role={decision.role} task_type={decision.task_type} matched={decision.matched} "
        f"rule_source={decision.rule_source} provider_id={decision.provider_id} "
        f"model={decision.model} effort={decision.effort} "
        f"provider_available={disponibilidad} -- {decision.reason}"
    )


def _resolver_decision_routing(role: str, task_type: str, ruta_policy_arg):
    """Carga la política y resuelve la `RoutingDecision`, reusando el mismo
    criterio de carga que el subcomando `routing` (mismo manejo de errores).
    Devuelve `(decision, ruta_policy)`; lanza las mismas excepciones que
    `load_policy` -- el llamador las atrapa con el mismo patrón que
    `routing`."""
    from tools.routing.core import resolve
    from tools.routing.policy import DEFAULT_POLICY_PATH, load_policy

    ruta_policy = Path(ruta_policy_arg) if ruta_policy_arg else DEFAULT_POLICY_PATH
    policy = load_policy(Path(ruta_policy_arg) if ruta_policy_arg else None)
    decision = resolve(policy, role=role, task_type=task_type)
    return decision, ruta_policy


def _cadena_candidata(decision) -> list:
    """Arma `[provider_id] + fallback_chain` a partir de una
    `RoutingDecision`, salteando el `provider_id` si es `None` (sin regla
    matcheada)."""
    cadena = []
    if decision.provider_id is not None:
        cadena.append(decision.provider_id)
    cadena.extend(decision.fallback_chain)
    return cadena


def _formatear_resolve_chain_texto(decision, cadena: list, disponibilidad: dict) -> str:
    lineas = [
        f"role={decision.role} task_type={decision.task_type} matched={decision.matched} "
        f"cadena={cadena}"
    ]
    for provider_id in cadena:
        lineas.append(f"- {provider_id}: {disponibilidad[provider_id]}")
    if not cadena:
        lineas.append("- (cadena vacía: sin provider_id resuelto ni fallback_chain declarada)")
    return "\n".join(lineas)


def _formatear_fallback_outcome_texto(outcome) -> str:
    if outcome.final_provider_id is not None:
        estado = f"éxito con provider_id={outcome.final_provider_id}"
    elif outcome.blocked_reason is not None:
        estado = f"bloqueado -- {outcome.blocked_reason}"
    elif outcome.exhausted:
        estado = "cadena agotada sin éxito"
    else:
        # Defensivo: por contrato, `FallbackOutcome` siempre trae
        # `final_provider_id`, `blocked_reason` o `exhausted=True` -- esta
        # rama no debería alcanzarse nunca en la práctica.
        estado = "estado inesperado"
    return (
        f"resultado: {estado}\n"
        f"handoffs intentados: {len(outcome.handoffs)}\n"
        + "\n".join(
            f"  - {registro.provider_id}: ok={registro.ok} "
            f"availability_error={registro.availability_error} -- {registro.reason}"
            for registro in outcome.handoffs
        )
    )


def main(argv: list = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)

    if args.subcomando == "doctor":
        try:
            resultados, codigo = doctor_mod.ejecutar(Path(args.destino))
        except Exception as exc:  # noqa: BLE001 - defensa final: doctor no debe crashear crudo
            print(f"[ABORTADO] harmessi doctor: fallo inesperado: {exc!r}", file=sys.stderr)
            return 1
        print(doctor_mod.formatear(resultados))
        return codigo

    if args.subcomando == "providers" and args.providers_subcomando == "list":
        # Import diferido (mismo criterio que `core.list_providers`): evita
        # cargar los 4 adapters cuando el subcomando invocado es 'doctor'.
        from tools.providers import list_providers

        try:
            infos = list_providers()
        except Exception as exc:  # noqa: BLE001 - defensa final, mismo criterio que 'doctor'
            print(f"[ABORTADO] harmessi providers list: fallo inesperado: {exc!r}", file=sys.stderr)
            return 1

        if args.json:
            print(json.dumps([_providers_info_a_dict(info) for info in infos], ensure_ascii=False, indent=2))
        else:
            print(_formatear_providers_tabla(infos))
        return 0

    if args.subcomando == "routing":
        # Import diferido (mismo criterio que 'providers'): evita cargar
        # tools.routing cuando el subcomando invocado es otro.
        from tools.routing.core import resolve
        from tools.routing.policy import DEFAULT_POLICY_PATH, load_policy

        ruta_policy = Path(args.policy) if args.policy else DEFAULT_POLICY_PATH
        try:
            policy = load_policy(Path(args.policy) if args.policy else None)
        except (ValueError, json.JSONDecodeError, FileNotFoundError) as exc:
            print(
                f"[ABORTADO] harmessi routing {args.routing_subcomando}: "
                f"política de routing inválida en {ruta_policy}: {exc!r}",
                file=sys.stderr,
            )
            return 1
        except Exception as exc:  # noqa: BLE001 - defensa final, mismo criterio que 'doctor'/'providers'
            print(
                f"[ABORTADO] harmessi routing {args.routing_subcomando}: fallo inesperado: {exc!r}",
                file=sys.stderr,
            )
            return 1

        if args.routing_subcomando == "show":
            if args.json:
                print(json.dumps(_routing_policy_a_dict(policy), ensure_ascii=False, indent=2))
            else:
                print(_formatear_routing_policy_texto(policy, str(ruta_policy)))
            return 0

        if args.routing_subcomando == "resolve":
            available_providers = None
            if args.check_availability:
                from tools.providers import list_providers

                try:
                    infos = list_providers()
                except Exception as exc:  # noqa: BLE001 - defensa final
                    print(
                        f"[ABORTADO] harmessi routing resolve: fallo detectando disponibilidad: {exc!r}",
                        file=sys.stderr,
                    )
                    return 1
                available_providers = {info.provider_id for info in infos if info.available}

            decision = resolve(
                policy,
                role=args.role,
                task_type=args.task_type,
                available_providers=available_providers,
            )
            if args.json:
                print(json.dumps(dataclasses.asdict(decision), ensure_ascii=False, indent=2))
            else:
                print(_formatear_routing_decision_texto(decision))
            return 0

    if args.subcomando == "fallback":
        # Import diferido (mismo criterio que 'routing'/'providers'): evita
        # cargar tools.fallback/tools.providers cuando el subcomando
        # invocado es otro.
        from tools.providers import PROVIDER_REGISTRY
        from tools.routing.policy import DEFAULT_POLICY_PATH

        ruta_policy = Path(args.policy) if args.policy else DEFAULT_POLICY_PATH
        try:
            decision, ruta_policy = _resolver_decision_routing(
                args.role, args.task_type, args.policy
            )
        except (ValueError, json.JSONDecodeError, FileNotFoundError) as exc:
            print(
                f"[ABORTADO] harmessi fallback {args.fallback_subcomando}: "
                f"política de routing inválida en {ruta_policy}: {exc!r}",
                file=sys.stderr,
            )
            return 1
        except Exception as exc:  # noqa: BLE001 - defensa final, mismo criterio que 'routing'
            print(
                f"[ABORTADO] harmessi fallback {args.fallback_subcomando}: fallo inesperado: {exc!r}",
                file=sys.stderr,
            )
            return 1

        cadena = _cadena_candidata(decision)

        if args.fallback_subcomando == "resolve-chain":
            disponibilidad = {}
            for provider_id in cadena:
                adapter = PROVIDER_REGISTRY.get(provider_id)
                if adapter is None:
                    disponibilidad[provider_id] = "no_registrado"
                    continue
                try:
                    info = adapter.detect()
                    disponibilidad[provider_id] = "disponible" if info.available else "no_disponible"
                except Exception as exc:  # noqa: BLE001 - un adapter roto no crashea el CLI
                    disponibilidad[provider_id] = f"error detectando: {exc!r}"

            if args.json:
                print(
                    json.dumps(
                        {
                            "role": decision.role,
                            "task_type": decision.task_type,
                            "matched": decision.matched,
                            "cadena": cadena,
                            "disponibilidad": disponibilidad,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(_formatear_resolve_chain_texto(decision, cadena, disponibilidad))
            return 0

        if args.fallback_subcomando == "invoke":
            if not cadena:
                print(
                    f"[ABORTADO] harmessi fallback invoke: sin provider_id ni fallback_chain "
                    f"resueltos para role={args.role!r} task_type={args.task_type!r} "
                    f"(matched={decision.matched}) -- nada para invocar",
                    file=sys.stderr,
                )
                return 1

            from tools.fallback.core import invoke_with_fallback
            from tools.providers import InvocationRequest

            adapters = []
            no_registrados = []
            for provider_id in cadena:
                adapter = PROVIDER_REGISTRY.get(provider_id)
                if adapter is None:
                    no_registrados.append(provider_id)
                    continue
                adapters.append(adapter)

            if not adapters:
                print(
                    "[ABORTADO] harmessi fallback invoke: ningún provider_id de la cadena "
                    f"{cadena!r} está registrado en PROVIDER_REGISTRY",
                    file=sys.stderr,
                )
                return 1

            request = InvocationRequest(
                prompt=args.prompt, role=args.role, model=args.model, effort=args.effort
            )
            outcome = invoke_with_fallback(request, adapters)

            if args.json:
                salida = dataclasses.asdict(outcome)
                salida["no_registrados"] = no_registrados
                print(json.dumps(salida, ensure_ascii=False, indent=2))
            else:
                texto = _formatear_fallback_outcome_texto(outcome)
                if no_registrados:
                    texto += f"\n(no registrados, saltados: {no_registrados})"
                print(texto)
            return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
