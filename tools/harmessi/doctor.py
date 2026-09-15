"""`harmessi doctor`: diagnóstico de salud, solo lectura, de una instalación
de Harmessi (Bloque 2, reliability v0.2.0).

Corre desde el checkout fuente de Harmessi apuntando `--destino` a cualquier
repo (mismo modelo operativo que `tools.ds_init`, R14-análogo: nunca escribe
en el destino, salvo un archivo de prueba temporal propio para el check de
permisos, que siempre limpia). No repara nada -- ver `README.md` y el diseño
del Bloque 2 para qué queda deliberadamente fuera de v0.2 (instalar `doctor`
en el destino, `--fix`, `update`/`uninstall`).

Cada check es una función pura de la forma `(...) -> list[checks.CheckResult]`
(vocabulario neutral PASS/WARN/FAIL/N-A, Change 4 v0.3), nunca lanza --
cualquier excepción inesperada la atrapa `_ejecutar_check` y la convierte en
un `ResultadoCheck` de nivel `ERROR` (R: nunca un traceback crudo en uso
normal, mismo criterio que `writer.py`/`cli.py` de `ds_init`).
`_ejecutar_check`/`_ejecutar_check_con_dato` delegan la ejecución/captura de
excepciones en `tools.dsguard.checks` y traducen el resultado neutral a
`ResultadoCheck` (vocabulario público de Doctor, sin cambios de UX)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from tools import launcher_common
from tools.ds_init import control as control_mod
from tools.ds_init import manifest as manifest_mod
from tools.ds_init.version import HARNESS_VERSION
from tools.dsguard import checks
from tools.dsguard import pathguard

NIVEL_OK = "OK"
NIVEL_WARN = "WARN"
NIVEL_ERROR = "ERROR"

SECCION_CORE = "CORE"
SECCION_HARMESSI = "HARMESSI"
SECCION_RUNTIME = "RUNTIME"
_SECCIONES_ORDEN = (SECCION_CORE, SECCION_HARMESSI, SECCION_RUNTIME)

VERSION_PYTHON_MINIMA = (3, 9)

# Archivos administrados cuya ausencia es un `ERROR` (desactivan un
# guardrail de seguridad) -- el resto de las entradas del manifiesto que
# falten se reportan como `WARN` (degradación, no pérdida de un guardrail).
_RUTAS_CRITICAS = frozenset(
    {
        ".claude/settings.json",
        ".claude/agents/python-data-engineer.md",
        ".claude/agents/data-science-reviewer.md",
        ".claude/agents/metodologo.md",
        ".claude/agents/notebook-runner.md",
        ".claude/skills/lead-data-scientist/SKILL.md",
        "tools/dsguard/hook_presupuesto.py",
        "tools/dsguard/hook_launcher_presupuesto.py",
        "tools/dsguard/pathguard.py",
        "tools/dsguard/hook_rutas.py",
        "tools/dsguard/hook_launcher_rutas.py",
        "tools/nbrunner/hook_validar_comando.py",
        "tools/nbrunner/hook_launcher.py",
        "tools/launcher_common.py",
        ".claude/guardrails.json",
    }
)

_AGENTES_ESPERADOS = (
    ("python-data-engineer", ".claude/agents/python-data-engineer.md"),
    ("data-science-reviewer", ".claude/agents/data-science-reviewer.md"),
    ("metodologo", ".claude/agents/metodologo.md"),
    ("notebook-runner", ".claude/agents/notebook-runner.md"),
)

_ARCHIVOS_SKILL_ESPERADOS = (
    ".claude/skills/lead-data-scientist/SKILL.md",
    ".claude/skills/lead-data-scientist/sdd.md",
    ".claude/skills/lead-data-scientist/verificador.md",
    ".claude/skills/lead-data-scientist/templates/proposal.md",
    ".claude/skills/lead-data-scientist/templates/spec.md",
    ".claude/skills/lead-data-scientist/templates/design.md",
    ".claude/skills/lead-data-scientist/templates/tasks.md",
    ".claude/skills/lead-data-scientist/templates/verification.md",
)

_LANZADORES_ESPERADOS = (
    "tools/nbrunner/hook_launcher.py",
    "tools/dsguard/hook_launcher_presupuesto.py",
    "tools/dsguard/hook_launcher_rutas.py",
)

_PREFIJOS_SHELL = ("bash", "sh", "zsh", "dash", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh")


@dataclass(frozen=True)
class ResultadoCheck:
    """Resultado de un check individual de `doctor`. `ubicacion` es opcional
    (ruta o comando relevante, para que el mensaje sea accionable)."""

    nivel: str
    seccion: str
    codigo: str
    mensaje: str
    ubicacion: Optional[str] = None


_MAPA_STATUS_A_NIVEL = {
    checks.STATUS_PASS: NIVEL_OK,
    checks.STATUS_WARN: NIVEL_WARN,
    checks.STATUS_FAIL: NIVEL_ERROR,
}


def _traducir(seccion: str, r) -> ResultadoCheck:
    """Traduce un `checks.CheckResult` (vocabulario neutral del engine) a un
    `ResultadoCheck` público de Doctor. `N/A` no tiene mapeo hoy (ningún
    check de Doctor lo emite) -- pasa tal cual como nivel si algún día
    ocurre, en vez de fallar."""
    nivel = _MAPA_STATUS_A_NIVEL.get(r.status, r.status)
    return ResultadoCheck(nivel, seccion, r.code, r.message, r.subject)


def _ejecutar_check(seccion: str, codigo_base: str, funcion: Callable, *args) -> list:
    """Corre `funcion(*args)` (un check que devuelve `list[checks.CheckResult]`)
    vía `checks.ejecutar_checks` -- nunca deja escapar una excepción: se
    convierte en un `checks.CheckResult` FAIL/technical_error, traducido acá
    a `ResultadoCheck` ERROR (mismo comportamiento público que antes del
    retrofit)."""
    resultados = checks.ejecutar_checks([(codigo_base, funcion, args)])
    return [_traducir(seccion, r) for r in resultados]


def _ejecutar_check_con_dato(seccion: str, codigo_base: str, funcion: Callable, *args):
    """Como `_ejecutar_check`, pero para los dos checks que además producen
    un dato reusado por checks posteriores (`_leer_control_json`,
    `_check_settings`): devuelven `(dato_o_None, list[checks.CheckResult])`.
    Nunca lanza; ante excepción, devuelve `(None, [ResultadoCheck ERROR])`
    para que el resto de la orquestación se degrade explícitamente."""
    try:
        dato, resultados = funcion(*args)
        return dato, [_traducir(seccion, r) for r in resultados]
    except Exception as exc:  # noqa: BLE001 - red de cierre: doctor nunca debe crashear
        return None, [_traducir(seccion, checks.resultado_de_excepcion(codigo_base, exc))]


# --- CORE --------------------------------------------------------------------


def _check_version_python() -> list:
    if sys.version_info >= VERSION_PYTHON_MINIMA:
        return [
            checks.CheckResult(
                checks.STATUS_PASS,
                "CORE-PYTHON-VERSION",
                f"Python {sys.version.split()[0]} (mínimo soportado: "
                f"{'.'.join(map(str, VERSION_PYTHON_MINIMA))})",
            )
        ]
    return [
        checks.CheckResult(
            checks.STATUS_FAIL,
            "CORE-PYTHON-VERSION",
            f"Python {sys.version.split()[0]} es menor que el mínimo soportado "
            f"({'.'.join(map(str, VERSION_PYTHON_MINIMA))})",
        )
    ]


def _git(args: list, cwd: Path):
    return subprocess.run(["git", "-C", str(cwd)] + args, capture_output=True, text=True)


def _check_git_disponible() -> list:
    ruta_git = shutil.which("git")
    if not ruta_git:
        return [
            checks.CheckResult(
                checks.STATUS_FAIL, "CORE-GIT-DISPONIBLE", "No se encontró 'git' en el PATH"
            )
        ]
    try:
        resultado = subprocess.run(["git", "--version"], capture_output=True, text=True)
    except OSError as exc:
        return [
            checks.CheckResult(
                checks.STATUS_FAIL, "CORE-GIT-DISPONIBLE", f"'git' no se pudo ejecutar: {exc}"
            )
        ]
    if resultado.returncode != 0:
        return [
            checks.CheckResult(
                checks.STATUS_FAIL,
                "CORE-GIT-DISPONIBLE",
                "'git --version' terminó con código de error",
            )
        ]
    return [
        checks.CheckResult(
            checks.STATUS_PASS, "CORE-GIT-DISPONIBLE", resultado.stdout.strip(), subject=ruta_git
        )
    ]


def _check_repo_git_valido(destino: Path) -> list:
    if not destino.is_dir():
        return [
            checks.CheckResult(
                checks.STATUS_FAIL, "CORE-REPO-GIT", f"El destino no existe: {destino}"
            )
        ]
    try:
        resultado = _git(["rev-parse", "--is-inside-work-tree"], destino)
    except OSError as exc:
        return [
            checks.CheckResult(
                checks.STATUS_FAIL, "CORE-REPO-GIT", f"No se pudo invocar git: {exc}"
            )
        ]
    if resultado.returncode != 0 or resultado.stdout.strip() != "true":
        return [
            checks.CheckResult(
                checks.STATUS_FAIL,
                "CORE-REPO-GIT",
                f"{destino} no es un repositorio Git válido",
            )
        ]
    return [checks.CheckResult(checks.STATUS_PASS, "CORE-REPO-GIT", "Repositorio Git válido")]


def _check_working_tree(destino: Path) -> list:
    try:
        resultado = _git(["status", "--porcelain"], destino)
    except OSError as exc:
        return [
            checks.CheckResult(
                checks.STATUS_FAIL, "CORE-WORKING-TREE", f"No se pudo invocar git status: {exc}"
            )
        ]
    if resultado.returncode != 0:
        return [
            checks.CheckResult(
                checks.STATUS_FAIL,
                "CORE-WORKING-TREE",
                "No se pudo consultar el estado de git (repositorio inválido o corrupto)",
            )
        ]
    sucios = resultado.stdout.strip()
    if sucios:
        return [
            checks.CheckResult(
                checks.STATUS_WARN,
                "CORE-WORKING-TREE",
                f"Working tree con cambios sin confirmar ({len(sucios.splitlines())} entrada(s))",
            )
        ]
    return [checks.CheckResult(checks.STATUS_PASS, "CORE-WORKING-TREE", "Working tree limpio")]


def _check_venv(destino: Path) -> list:
    venv_dir = launcher_common.resolver_venv_dir(destino)
    interprete = launcher_common.ruta_interprete_venv(destino, venv_dir)
    if not interprete.is_file():
        return [
            checks.CheckResult(
                checks.STATUS_WARN,
                "CORE-VENV",
                f"No se encontró el intérprete del venv en {interprete} (venv_dir={venv_dir!r})",
                subject=str(interprete),
            )
        ]
    return [
        checks.CheckResult(
            checks.STATUS_PASS,
            "CORE-VENV",
            f"Intérprete encontrado en {interprete}",
            subject=str(interprete),
        )
    ]


def _probar_escritura(ruta: Path) -> None:
    """Escribe y borra `ruta`. Función propia (en vez de inline) para que
    los tests puedan forzar el camino `ERROR` parcheándola, sin depender de
    permisos de filesystem reales (frágil entre Windows/POSIX/CI)."""
    ruta.write_text("harmessi doctor\n", encoding="utf-8")
    ruta.read_text(encoding="utf-8")
    ruta.unlink()


def _check_permisos(destino: Path) -> list:
    ruta_prueba = destino / f".harmessi_doctor_tmp_{os.getpid()}"
    try:
        _probar_escritura(ruta_prueba)
    except OSError as exc:
        return [
            checks.CheckResult(
                checks.STATUS_FAIL,
                "CORE-PERMISOS",
                f"No se pudo escribir/leer en {destino}: {exc}",
            )
        ]
    finally:
        try:
            if ruta_prueba.exists():
                ruta_prueba.unlink()
        except OSError:
            pass
    return [checks.CheckResult(checks.STATUS_PASS, "CORE-PERMISOS", "Lectura/escritura verificadas")]


# --- HARMESSI ------------------------------------------------------------------


def _ruta_control(destino: Path) -> Path:
    return destino / control_mod.DIR_CONTROL / control_mod.NOMBRE_ARCHIVO_CONTROL


_CAMPOS_CONTROL_ESPERADOS = ("harness_version", "perfil", "fecha_utc", "configuracion", "archivos")


def _leer_control_json(destino: Path):
    """Devuelve `(contenido_o_None, list[checks.CheckResult])`. Nunca lanza:
    cualquier problema de lectura/parseo/schema se refleja en el resultado,
    y `contenido` queda en `None` para que los checks que dependen de él se
    degraden explícitamente (no asuman datos parciales)."""
    ruta = _ruta_control(destino)
    if not ruta.exists():
        return None, [
            checks.CheckResult(
                checks.STATUS_FAIL, "HARMESSI-CONTROL-JSON", f"No existe {ruta}", subject=str(ruta)
            )
        ]
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, [
            checks.CheckResult(
                checks.STATUS_FAIL,
                "HARMESSI-CONTROL-JSON",
                f"No se pudo leer/parsear {ruta}: {exc}",
                subject=str(ruta),
            )
        ]
    if not isinstance(contenido, dict):
        return None, [
            checks.CheckResult(
                checks.STATUS_FAIL,
                "HARMESSI-CONTROL-JSON",
                f"{ruta} no contiene un objeto JSON",
                subject=str(ruta),
            )
        ]
    faltantes = [campo for campo in _CAMPOS_CONTROL_ESPERADOS if campo not in contenido]
    if faltantes:
        return contenido, [
            checks.CheckResult(
                checks.STATUS_FAIL,
                "HARMESSI-CONTROL-JSON",
                f"control.json incompleto, faltan campos: {faltantes}",
                subject=str(ruta),
            )
        ]
    return contenido, [
        checks.CheckResult(
            checks.STATUS_PASS, "HARMESSI-CONTROL-JSON", "control.json válido", subject=str(ruta)
        )
    ]


def _check_archivos_administrados(destino: Path, control_data: Optional[dict]) -> list:
    if control_data is None:
        return [
            checks.CheckResult(
                checks.STATUS_WARN,
                "HARMESSI-ARCHIVOS-ESPERADOS",
                "No se puede determinar el perfil instalado sin control.json: chequeo omitido",
            )
        ]
    perfil = control_data.get("perfil")
    try:
        entradas = manifest_mod.manifest_para_perfil(perfil)
    except manifest_mod.PerfilDesconocidoError as exc:
        return [
            checks.CheckResult(checks.STATUS_FAIL, "HARMESSI-ARCHIVOS-ESPERADOS", str(exc))
        ]

    resultados = []
    for entrada in entradas:
        if entrada.destino == ".ds_init/control.json":
            continue  # verificado aparte (HARMESSI-CONTROL-JSON)
        ruta = destino / entrada.destino
        if ruta.exists():
            continue
        critico = entrada.destino in _RUTAS_CRITICAS
        resultados.append(
            checks.CheckResult(
                checks.STATUS_FAIL if critico else checks.STATUS_WARN,
                "HARMESSI-ARCHIVO-FALTANTE",
                f"Archivo administrado faltante: {entrada.destino}",
                subject=entrada.destino,
            )
        )
    if not resultados:
        resultados.append(
            checks.CheckResult(
                checks.STATUS_PASS,
                "HARMESSI-ARCHIVOS-ESPERADOS",
                f"Los {len(entradas)} archivo(s) administrados del perfil {perfil!r} están presentes",
            )
        )
    return resultados


def _check_hashes_drift(destino: Path, control_data: Optional[dict]) -> list:
    if control_data is None:
        return [
            checks.CheckResult(
                checks.STATUS_WARN,
                "HARMESSI-DRIFT",
                "No se puede verificar drift sin control.json: chequeo omitido",
            )
        ]
    archivos = control_data.get("archivos")
    if not isinstance(archivos, list):
        return [
            checks.CheckResult(
                checks.STATUS_FAIL, "HARMESSI-DRIFT", "control.json no tiene una lista 'archivos' válida"
            )
        ]

    resultados = []
    for entrada in archivos:
        if not isinstance(entrada, dict):
            continue
        ruta_rel = entrada.get("ruta")
        hash_esperado = entrada.get("sha256")
        if not ruta_rel:
            continue
        ruta_abs = destino / ruta_rel
        if not ruta_abs.exists():
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_FAIL,
                    "HARMESSI-DRIFT-FALTANTE",
                    f"Archivo administrado listado en control.json pero ausente: {ruta_rel}",
                    subject=ruta_rel,
                )
            )
            continue
        try:
            hash_real = control_mod.sha256_de_archivo(ruta_abs)
        except OSError as exc:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_FAIL,
                    "HARMESSI-DRIFT",
                    f"No se pudo calcular el hash de {ruta_rel}: {exc}",
                    subject=ruta_rel,
                )
            )
            continue
        if hash_real != hash_esperado:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_WARN,
                    "HARMESSI-DRIFT",
                    f"Modificado desde la instalación: {ruta_rel}",
                    subject=ruta_rel,
                )
            )
    if not resultados:
        resultados.append(
            checks.CheckResult(
                checks.STATUS_PASS,
                "HARMESSI-DRIFT",
                "Ningún archivo administrado difiere de su hash registrado",
            )
        )
    return resultados


def _check_agents(destino: Path) -> list:
    resultados = []
    for nombre, ruta_rel in _AGENTES_ESPERADOS:
        ruta = destino / ruta_rel
        if not ruta.exists():
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_FAIL,
                    "HARMESSI-AGENTE-FALTANTE",
                    f"Falta el agente {nombre!r}",
                    subject=ruta_rel,
                )
            )
            continue
        try:
            texto = ruta.read_text(encoding="utf-8")
        except OSError as exc:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_FAIL,
                    "HARMESSI-AGENTE-ILEGIBLE",
                    f"No se pudo leer el agente {nombre!r}: {exc}",
                    subject=ruta_rel,
                )
            )
            continue
        if not texto.startswith("---") or f"name: {nombre}" not in texto:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_WARN,
                    "HARMESSI-AGENTE-FRONTMATTER",
                    f"El agente {nombre!r} no tiene el frontmatter esperado",
                    subject=ruta_rel,
                )
            )
            continue
        resultados.append(
            checks.CheckResult(
                checks.STATUS_PASS, "HARMESSI-AGENTE", f"Agente {nombre!r} presente", subject=ruta_rel
            )
        )
    return resultados


def _check_skill_lead_data_scientist(destino: Path) -> list:
    faltantes = [ruta_rel for ruta_rel in _ARCHIVOS_SKILL_ESPERADOS if not (destino / ruta_rel).exists()]
    if faltantes:
        return [
            checks.CheckResult(
                checks.STATUS_WARN,
                "HARMESSI-SKILL-FALTANTE",
                f"Archivo(s) faltante(s) de la skill lead-data-scientist: {faltantes}",
            )
        ]
    return [
        checks.CheckResult(
            checks.STATUS_PASS,
            "HARMESSI-SKILL",
            "La skill lead-data-scientist está completa",
        )
    ]


def _check_settings(destino: Path):
    """Devuelve `(contenido_o_None, list[checks.CheckResult])` -- otros
    checks (hooks, dependencia de shell) reusan `contenido` sin releer el
    archivo."""
    ruta = destino / ".claude" / "settings.json"
    if not ruta.exists():
        return None, [
            checks.CheckResult(
                checks.STATUS_FAIL, "HARMESSI-SETTINGS", f"No existe {ruta}", subject=str(ruta)
            )
        ]
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, [
            checks.CheckResult(
                checks.STATUS_FAIL,
                "HARMESSI-SETTINGS",
                f"No se pudo leer/parsear {ruta}: {exc}",
                subject=str(ruta),
            )
        ]
    if not isinstance(contenido, dict) or "hooks" not in contenido:
        return contenido, [
            checks.CheckResult(
                checks.STATUS_FAIL,
                "HARMESSI-SETTINGS",
                f"{ruta} no tiene la clave 'hooks' esperada",
                subject=str(ruta),
            )
        ]
    return contenido, [
        checks.CheckResult(
            checks.STATUS_PASS, "HARMESSI-SETTINGS", "settings.json válido", subject=str(ruta)
        )
    ]


def _iterar_comandos_hooks(settings_data: dict):
    """Yields `(evento, matcher, comando)` para cada comando declarado bajo
    `hooks.<evento>[].hooks[].command` de un `settings.json` ya parseado."""
    hooks = settings_data.get("hooks") if isinstance(settings_data, dict) else None
    if not isinstance(hooks, dict):
        return
    for evento, entradas in hooks.items():
        if not isinstance(entradas, list):
            continue
        for entrada in entradas:
            if not isinstance(entrada, dict):
                continue
            matcher = entrada.get("matcher")
            for hook in entrada.get("hooks", []):
                if isinstance(hook, dict) and isinstance(hook.get("command"), str):
                    yield evento, matcher, hook["command"]


def _check_hooks(destino: Path, settings_data: Optional[dict]) -> list:
    if settings_data is None:
        return [
            checks.CheckResult(
                checks.STATUS_WARN, "HARMESSI-HOOKS", "No hay settings.json legible para revisar hooks"
            )
        ]
    comandos = list(_iterar_comandos_hooks(settings_data))
    if not comandos:
        return [
            checks.CheckResult(
                checks.STATUS_FAIL, "HARMESSI-HOOKS", "No hay hooks 'PreToolUse' configurados"
            )
        ]
    matchers = {matcher for evento, matcher, _ in comandos if evento == "PreToolUse"}
    resultados = []
    if "Bash" not in matchers:
        resultados.append(
            checks.CheckResult(
                checks.STATUS_FAIL,
                "HARMESSI-HOOKS",
                "Falta el hook PreToolUse del guardrail de notebook-runner (matcher 'Bash')",
            )
        )
    if not any(matcher and "PowerShell" in matcher for matcher in matchers):
        resultados.append(
            checks.CheckResult(
                checks.STATUS_FAIL,
                "HARMESSI-HOOKS",
                "Falta el hook PreToolUse del guardrail de presupuesto de sesión (matcher con 'PowerShell')",
            )
        )
    if not any(matcher and "NotebookEdit" in matcher for matcher in matchers):
        resultados.append(
            checks.CheckResult(
                checks.STATUS_FAIL,
                "HARMESSI-HOOKS",
                "Falta el hook PreToolUse de protección de rutas (matcher con 'NotebookEdit')",
            )
        )
    if not resultados:
        resultados.append(
            checks.CheckResult(
                checks.STATUS_PASS, "HARMESSI-HOOKS", f"{len(comandos)} hook(s) configurado(s)"
            )
        )
    return resultados


def _check_guardrails_json(destino: Path) -> list:
    """`.claude/guardrails.json` (Bloque 3): reusa `pathguard.cargar_config`
    directamente en vez de reimplementar su propio parseo/validación de
    schema -- si `pathguard` lo rechazaría en runtime (fail-closed, deniega
    todo), `doctor` debe reportarlo como `ERROR`, no revalidar con su propia
    lógica potencialmente distinta."""
    ruta = destino / pathguard.RUTA_CONFIG_RELATIVA
    if not ruta.exists():
        return [
            checks.CheckResult(
                checks.STATUS_WARN,
                "HARMESSI-GUARDRAILS-JSON",
                f"No existe {ruta}: pathguard usa los defaults seguros (data/raw protegido, "
                "sin holdouts ni write_scopes declarados)",
                subject=str(ruta),
            )
        ]
    try:
        config = pathguard.cargar_config(destino)
    except pathguard.ConfigGuardrailsError as exc:
        return [
            checks.CheckResult(
                checks.STATUS_FAIL,
                "HARMESSI-GUARDRAILS-JSON",
                f"guardrails.json corrupto -- pathguard lo trata como fail-closed (deniega todo): {exc}",
                subject=str(ruta),
            )
        ]
    return [
        checks.CheckResult(
            checks.STATUS_PASS,
            "HARMESSI-GUARDRAILS-JSON",
            f"guardrails.json válido ({len(config.holdouts)} holdout(s), "
            f"{len(config.data_raw)} patrón(es) data_raw, {len(config.write_scopes)} write_scope(s))",
            subject=str(ruta),
        )
    ]


def _check_coherencia_version(control_data: Optional[dict]) -> list:
    if control_data is None:
        return [
            checks.CheckResult(
                checks.STATUS_WARN,
                "HARMESSI-VERSION",
                "No se puede comparar la versión instalada sin control.json: chequeo omitido",
            )
        ]
    version_instalada = control_data.get("harness_version")
    if version_instalada == HARNESS_VERSION:
        return [
            checks.CheckResult(
                checks.STATUS_PASS,
                "HARMESSI-VERSION",
                f"Instalado con la versión actual del harness ({HARNESS_VERSION})",
            )
        ]
    return [
        checks.CheckResult(
            checks.STATUS_WARN,
            "HARMESSI-VERSION",
            f"Instalado con harness_version={version_instalada!r}, la versión actual de "
            f"este checkout es {HARNESS_VERSION!r} -- puede haber drift de manifiesto",
        )
    ]


# --- RUNTIME -------------------------------------------------------------------


def _check_launchers_existen(destino: Path) -> list:
    resultados = []
    for ruta_rel in _LANZADORES_ESPERADOS:
        ruta = destino / ruta_rel
        if ruta.exists():
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_PASS, "RUNTIME-LAUNCHER", f"{ruta_rel} presente", subject=ruta_rel
                )
            )
        else:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_FAIL,
                    "RUNTIME-LAUNCHER-FALTANTE",
                    f"Lanzador de hook faltante: {ruta_rel}",
                    subject=ruta_rel,
                )
            )
    return resultados


def _check_interprete_ejecuta_hooks(destino: Path) -> list:
    venv_dir = launcher_common.resolver_venv_dir(destino)
    interprete = launcher_common.ruta_interprete_venv(destino, venv_dir)
    if not interprete.is_file():
        return [
            checks.CheckResult(
                checks.STATUS_FAIL,
                "RUNTIME-INTERPRETE",
                f"No hay intérprete en {interprete}: los hooks no pueden ejecutarse",
                subject=str(interprete),
            )
        ]
    tools_dir = destino / "tools"
    codigo = f"import sys; sys.path.insert(0, {str(tools_dir)!r}); import dsguard.core; import nbrunner.core"
    try:
        resultado = subprocess.run(
            [str(interprete), "-c", codigo], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [
            checks.CheckResult(
                checks.STATUS_FAIL,
                "RUNTIME-INTERPRETE",
                f"No se pudo ejecutar el intérprete {interprete}: {exc}",
                subject=str(interprete),
            )
        ]
    if resultado.returncode != 0:
        return [
            checks.CheckResult(
                checks.STATUS_FAIL,
                "RUNTIME-INTERPRETE",
                f"El intérprete no pudo importar los módulos de los hooks: {resultado.stderr.strip()}",
                subject=str(interprete),
            )
        ]
    return [
        checks.CheckResult(
            checks.STATUS_PASS,
            "RUNTIME-INTERPRETE",
            f"{interprete} puede importar dsguard.core y nbrunner.core",
            subject=str(interprete),
        )
    ]


def _extraer_rutas_script(comando: str, destino: Path) -> list:
    """Extrae rutas de archivo del `command` de un hook (tokens entre
    comillas, con `${CLAUDE_PROJECT_DIR}` sustituido por `destino`) -- solo
    para el check de existencia de RUNTIME, no para ejecutar nada."""
    tokens = re.findall(r'"([^"]+)"', comando)
    rutas = []
    for token in tokens:
        token_resuelto = token.replace("${CLAUDE_PROJECT_DIR}", str(destino))
        rutas.append(Path(token_resuelto))
    return rutas


def _check_hooks_configurados_existen(destino: Path, settings_data: Optional[dict]) -> list:
    if settings_data is None:
        return [
            checks.CheckResult(
                checks.STATUS_WARN,
                "RUNTIME-HOOKS-EXISTEN",
                "No hay settings.json legible para verificar los scripts de los hooks",
            )
        ]
    comandos = list(_iterar_comandos_hooks(settings_data))
    if not comandos:
        return [
            checks.CheckResult(
                checks.STATUS_WARN, "RUNTIME-HOOKS-EXISTEN", "No hay hooks configurados para verificar"
            )
        ]
    resultados = []
    for evento, matcher, comando in comandos:
        rutas = [r for r in _extraer_rutas_script(comando, destino) if r.suffix in (".py", ".sh")]
        if not rutas:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_WARN,
                    "RUNTIME-HOOKS-EXISTEN",
                    f"No se pudo interpretar el script del hook {matcher!r} ({evento}): {comando}",
                )
            )
            continue
        for ruta in rutas:
            if ruta.is_file():
                resultados.append(
                    checks.CheckResult(
                        checks.STATUS_PASS,
                        "RUNTIME-HOOKS-EXISTEN",
                        f"Script del hook {matcher!r} ({evento}) existe: {ruta}",
                        subject=str(ruta),
                    )
                )
            else:
                resultados.append(
                    checks.CheckResult(
                        checks.STATUS_FAIL,
                        "RUNTIME-HOOKS-EXISTEN",
                        f"Script del hook {matcher!r} ({evento}) no existe: {ruta}",
                        subject=str(ruta),
                    )
                )
    return resultados


def _check_dependencia_shell(settings_data: Optional[dict]) -> list:
    if settings_data is None:
        return [
            checks.CheckResult(
                checks.STATUS_WARN,
                "RUNTIME-SHELL-DEP",
                "No hay settings.json legible para revisar dependencias de shell en los hooks",
            )
        ]
    comandos = list(_iterar_comandos_hooks(settings_data))
    if not comandos:
        return [
            checks.CheckResult(
                checks.STATUS_WARN, "RUNTIME-SHELL-DEP", "No hay hooks configurados para revisar"
            )
        ]
    resultados = []
    for evento, matcher, comando in comandos:
        primer_token = comando.strip().split(" ", 1)[0].strip('"').lower()
        nombre_ejecutable = primer_token[:-4] if primer_token.endswith(".exe") else primer_token
        if nombre_ejecutable in _PREFIJOS_SHELL:
            disponible = shutil.which(nombre_ejecutable) is not None
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_FAIL if not disponible else checks.STATUS_WARN,
                    "RUNTIME-SHELL-DEP",
                    f"Hook {matcher!r} ({evento}) depende de un shell externo ({nombre_ejecutable!r}), "
                    f"{'no encontrado en PATH' if not disponible else 'encontrado en PATH'}: {comando}",
                    subject=comando,
                )
            )
        else:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_PASS,
                    "RUNTIME-SHELL-DEP",
                    f"Hook {matcher!r} ({evento}) no depende de un shell externo",
                    subject=comando,
                )
            )
    return resultados


# --- Orquestación ----------------------------------------------------------


def ejecutar(destino) -> tuple:
    """Corre todos los checks (CORE, HARMESSI, RUNTIME, en ese orden) contra
    `destino`. Nunca lanza. Devuelve `(resultados, exit_code)`: `exit_code`
    es `0` si no hay ningún `ERROR`, `1` si hay al menos uno."""
    destino = Path(destino).resolve()
    resultados = []

    resultados += _ejecutar_check(SECCION_CORE, "CORE-PYTHON-VERSION", _check_version_python)
    resultados += _ejecutar_check(SECCION_CORE, "CORE-GIT-DISPONIBLE", _check_git_disponible)
    resultados += _ejecutar_check(SECCION_CORE, "CORE-REPO-GIT", _check_repo_git_valido, destino)
    resultados += _ejecutar_check(SECCION_CORE, "CORE-WORKING-TREE", _check_working_tree, destino)
    resultados += _ejecutar_check(SECCION_CORE, "CORE-VENV", _check_venv, destino)
    resultados += _ejecutar_check(SECCION_CORE, "CORE-PERMISOS", _check_permisos, destino)

    control_data, resultado_control = _ejecutar_check_con_dato(
        SECCION_HARMESSI, "HARMESSI-CONTROL-JSON", _leer_control_json, destino
    )
    resultados += resultado_control
    resultados += _ejecutar_check(
        SECCION_HARMESSI, "HARMESSI-ARCHIVOS-ESPERADOS", _check_archivos_administrados, destino, control_data
    )
    resultados += _ejecutar_check(SECCION_HARMESSI, "HARMESSI-DRIFT", _check_hashes_drift, destino, control_data)
    resultados += _ejecutar_check(SECCION_HARMESSI, "HARMESSI-AGENTE", _check_agents, destino)
    resultados += _ejecutar_check(
        SECCION_HARMESSI, "HARMESSI-SKILL", _check_skill_lead_data_scientist, destino
    )

    settings_data, resultados_settings = _ejecutar_check_con_dato(
        SECCION_HARMESSI, "HARMESSI-SETTINGS", _check_settings, destino
    )
    resultados += resultados_settings
    resultados += _ejecutar_check(SECCION_HARMESSI, "HARMESSI-HOOKS", _check_hooks, destino, settings_data)
    resultados += _ejecutar_check(SECCION_HARMESSI, "HARMESSI-GUARDRAILS-JSON", _check_guardrails_json, destino)
    resultados += _ejecutar_check(
        SECCION_HARMESSI, "HARMESSI-VERSION", _check_coherencia_version, control_data
    )

    resultados += _ejecutar_check(SECCION_RUNTIME, "RUNTIME-LAUNCHER", _check_launchers_existen, destino)
    resultados += _ejecutar_check(
        SECCION_RUNTIME, "RUNTIME-INTERPRETE", _check_interprete_ejecuta_hooks, destino
    )
    resultados += _ejecutar_check(
        SECCION_RUNTIME, "RUNTIME-HOOKS-EXISTEN", _check_hooks_configurados_existen, destino, settings_data
    )
    resultados += _ejecutar_check(SECCION_RUNTIME, "RUNTIME-SHELL-DEP", _check_dependencia_shell, settings_data)

    exit_code = 1 if any(r.nivel == NIVEL_ERROR for r in resultados) else 0
    return resultados, exit_code


def formatear(resultados: list) -> str:
    """Reporte de texto plano, agrupado por sección en el orden fijo
    CORE/HARMESSI/RUNTIME, con un resumen final de conteos por nivel. El
    segmento `[N/A]` del resumen es condicional: solo aparece si el conteo
    es mayor a 0 (ningún check de Doctor lo emite hoy, salida idéntica a
    antes del retrofit de Change 4)."""
    lineas = ["Harmessi doctor"]
    conteos = {NIVEL_OK: 0, NIVEL_WARN: 0, NIVEL_ERROR: 0, "N/A": 0}

    for seccion in _SECCIONES_ORDEN:
        entradas = [r for r in resultados if r.seccion == seccion]
        if not entradas:
            continue
        lineas.append(f"\n=== {seccion} ===")
        for r in entradas:
            conteos[r.nivel] = conteos.get(r.nivel, 0) + 1
            sufijo = f" ({r.ubicacion})" if r.ubicacion else ""
            lineas.append(f"[{r.nivel}] {r.codigo}: {r.mensaje}{sufijo}")

    resumen = f"{conteos[NIVEL_OK]} [OK], {conteos[NIVEL_WARN]} [WARN], {conteos[NIVEL_ERROR]} [ERROR]"
    if conteos.get("N/A", 0) > 0:
        resumen += f", {conteos['N/A']} [N/A]"
    lineas.append(f"\nResumen: {resumen}")
    return "\n".join(lineas)
