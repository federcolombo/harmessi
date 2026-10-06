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
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from tools import launcher_common
from tools.ds_init import control as control_mod
from tools.ds_init import legacy as legacy_mod
from tools.ds_init import manifest as manifest_mod
from tools.ds_init.version import HARNESS_VERSION
from tools.dsguard import checks
from tools.dsguard import maturity
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


def _capabilities_efectivas_de_control(control_data: Optional[dict]) -> frozenset:
    """Capabilities habilitadas según `control.json` (única fuente, R12/R54).
    Lista presente: literal. Ausente/no-lista (legacy): solo las históricas
    (`CAPABILITIES_CONOCIDAS`); las opt-in quedan deshabilitadas."""
    crudo = control_data.get("capabilities_habilitadas") if isinstance(control_data, dict) else None
    if isinstance(crudo, list):
        return frozenset(c for c in crudo if isinstance(c, str))
    return frozenset(manifest_mod.CAPABILITIES_CONOCIDAS)


def _entrada_solo_opt_in(entrada) -> bool:
    """True si TODAS las capabilities de la entrada (`capabilities` o
    `capabilities_cualquiera`) son opt-in (`CAPABILITIES_OPT_IN`)."""
    opt_in = set(getattr(manifest_mod, "CAPABILITIES_OPT_IN", _GOV_OPT_IN_FALLBACK))
    caps = set(entrada.capabilities) | set(getattr(entrada, "capabilities_cualquiera", ()) or ())
    return bool(caps) and caps <= opt_in


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
    installation_stage = control_data.get("installation_stage")
    try:
        if installation_stage is not None:
            # Change 7 v0.3 (R10 de spec.md): consciente de `installation_stage`
            # -- un archivo de un stage superior al instalado NUNCA se
            # reporta como faltante (ni FAIL ni WARN).
            entradas = manifest_mod.manifest_para_perfil_y_stage(perfil, installation_stage)
        else:
            # Legacy (sin `installation_stage` en control.json): comportamiento
            # EXACTO actual -- 0 cambio de UX/severidad para instalaciones
            # legacy, incluido este propio repositorio (R10/design.md §8).
            entradas = manifest_mod.manifest_para_perfil(perfil)
    except manifest_mod.PerfilDesconocidoError as exc:
        return [
            checks.CheckResult(checks.STATUS_FAIL, "HARMESSI-ARCHIVOS-ESPERADOS", str(exc))
        ]

    # M8 (hallazgo de hardening, Change 5): `capabilities_habilitadas`
    # persistida por `control.generar_control` (si el instalador la pasó).
    # `None` (ausente, instalación legacy o sin capabilities declaradas) ->
    # se asume TODO habilitado, comportamiento EXACTO de antes de esta
    # verificación (R5: sin esta opción, cero cambio). Si está presente, una
    # entrada cuyo `capabilities` no sea subconjunto de las habilitadas
    # nunca es "faltante de verdad": es `N/A -- capability not enabled`
    # (R3 de Change 4, implementado recién acá -- no estaba wireado).
    # Change 20261005 (R7/R12): el filtro es el helper único del manifiesto
    # (`filtrar_entradas_por_capabilities`). Lista ausente (legacy) = capabilities
    # históricas habilitadas y opt-in deshabilitadas; lista presente, literal.
    capabilities_habilitadas = _capabilities_efectivas_de_control(control_data)

    resultados = []
    for entrada in entradas:
        if entrada.destino == ".ds_init/control.json":
            continue  # verificado aparte (HARMESSI-CONTROL-JSON)
        ruta = destino / entrada.destino
        if ruta.exists():
            continue
        if not manifest_mod.filtrar_entradas_por_capabilities([entrada], capabilities_habilitadas):
            if _entrada_solo_opt_in(entrada):
                # I1 (R78): tooling de una capability opt-in no habilitada: sin
                # resultado por archivo; lo informa el N/A agregado HARMESSI-GOV-CAPABILITY.
                continue
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_NA,
                    "HARMESSI-CAPABILITY-DISABLED",
                    "No provisionado: capability "
                    f"{list(entrada.capabilities or getattr(entrada, 'capabilities_cualquiera', ()))} "
                    "no habilitada "
                    f"-- {entrada.destino}",
                    subject=entrada.destino,
                )
            )
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


def _check_agents(destino: Path, control_data: Optional[dict]) -> list:
    """Verifica que los agentes de `_AGENTES_ESPERADOS` que aplican al
    `installation_stage` instalado estén presentes y con el frontmatter
    esperado (Change 20260925-doctor-stage-awareness: consciente de stage,
    mismo patrón que `_check_archivos_administrados`). La aplicabilidad de
    cada agente a un stage se resuelve consultando la fuente de verdad
    existente (`manifest_mod.manifest_para_perfil_y_stage`/
    `manifest_para_perfil` sobre `tools.ds_init.manifest.MANIFEST`, donde
    cada agente ya declara su `stage_minimo`) -- nunca una lista separada de
    agentes-por-stage ni una condición hardcodeada sobre el nombre del stage.
    Un agente que no aplica al stage instalado NO produce ningún
    `CheckResult` (ni PASS, ni FAIL, ni WARN): mismo criterio que un archivo
    administrado de un stage superior en `_check_archivos_administrados`,
    donde esa ausencia esperada tampoco se reporta.

    Comportamiento legacy preservado bit a bit (R5 de `spec.md`): si
    `control_data` es `None`, o no tiene clave `installation_stage`, se
    consideran esperados los 4 agentes de `_AGENTES_ESPERADOS`, exactamente
    como antes de este Change."""
    if control_data is None:
        # Sin control.json legible no se puede determinar perfil/stage --
        # comportamiento legacy: los 4 agentes se consideran esperados.
        destinos_aplicables = {ruta_rel for _, ruta_rel in _AGENTES_ESPERADOS}
    else:
        perfil = control_data.get("perfil")
        installation_stage = control_data.get("installation_stage")
        try:
            if installation_stage is not None:
                # Consciente de stage: un agente de un stage superior al
                # instalado no aplica.
                entradas = manifest_mod.manifest_para_perfil_y_stage(perfil, installation_stage)
            else:
                # Legacy (sin installation_stage en control.json):
                # comportamiento actual -- todo el manifest del perfil.
                entradas = manifest_mod.manifest_para_perfil(perfil)
        except manifest_mod.PerfilDesconocidoError:
            # Perfil desconocido: no se puede filtrar por stage. Ya se
            # reporta aparte en HARMESSI-ARCHIVOS-ESPERADOS -- acá se cae al
            # comportamiento legacy (los 4 agentes esperados) para no dejar
            # de detectar agentes realmente faltantes por un problema no
            # relacionado con este check.
            destinos_aplicables = {ruta_rel for _, ruta_rel in _AGENTES_ESPERADOS}
        else:
            destinos_aplicables = {entrada.destino for entrada in entradas}

    resultados = []
    for nombre, ruta_rel in _AGENTES_ESPERADOS:
        if ruta_rel not in destinos_aplicables:
            continue  # no aplica al stage instalado: ningún resultado (ni PASS/FAIL/WARN)
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


def _check_fuentes_externas_permisos_os(destino: Path) -> list:
    """Diagnóstico de solo lectura, NUNCA reparación (R17): para cada fuente
    externa declarada en `.harmessi/local-overrides.json` (M9/M10), reporta
    si el sistema operativo TAMBIÉN parece protegerla contra escritura. En
    POSIX usa `os.access(ruta, os.W_OK)` (observable de forma confiable); en
    Windows usa el atributo `FILE_ATTRIBUTE_READONLY` (`os.stat_result.
    st_file_attributes`, solo disponible en Windows) -- documentado
    explícitamente como una señal PARCIAL, nunca una garantía completa de
    ACL. Si no se puede determinar (ruta inexistente, error de I/O al
    consultar, o plataforma sin la señal disponible), reporta
    `OS read-only guarantee: unknown/partial` como `WARN`, nunca como error
    ni como falso PASS. Sin ninguna fuente declarada, devuelve `[]` (Doctor
    no reporta nada para esta categoría -- comportamiento hoy, sin M9
    configurado, es cero cambio). Nunca muta nada (ni `chmod` ni `icacls`)."""
    fuentes = pathguard.leer_fuentes_externas_declaradas(destino)
    if not fuentes:
        return []

    resultados = []
    for source_id, declaracion in fuentes.items():
        if not isinstance(declaracion, dict):
            continue
        ruta_str = declaracion.get("path")
        if not isinstance(ruta_str, str) or not ruta_str:
            continue
        ruta = Path(ruta_str)

        if not ruta.exists():
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_WARN,
                    "M12-FUENTE-EXTERNA-PERMISOS",
                    f"Fuente externa {source_id!r} declarada read-only, pero la ruta no existe: "
                    "OS read-only guarantee: unknown/partial.",
                    subject=source_id,
                )
            )
            continue

        try:
            if os.name == "nt":
                try:
                    atributos = ruta.stat().st_file_attributes
                except (OSError, AttributeError):
                    resultados.append(
                        checks.CheckResult(
                            checks.STATUS_WARN,
                            "M12-FUENTE-EXTERNA-PERMISOS",
                            f"Fuente externa {source_id!r}: no se pudo consultar el atributo de "
                            "solo lectura de Windows. OS read-only guarantee: unknown/partial.",
                            subject=source_id,
                        )
                    )
                    continue
                if atributos & stat.FILE_ATTRIBUTE_READONLY:
                    resultados.append(
                        checks.CheckResult(
                            checks.STATUS_PASS,
                            "M12-FUENTE-EXTERNA-PERMISOS",
                            f"Fuente externa {source_id!r}: atributo de solo lectura de Windows "
                            "activo (NO es una garantía completa de ACL -- ver documentación M12).",
                            subject=source_id,
                        )
                    )
                else:
                    resultados.append(
                        checks.CheckResult(
                            checks.STATUS_WARN,
                            "M12-FUENTE-EXTERNA-PERMISOS",
                            f"Fuente externa {source_id!r}: el atributo de solo lectura de Windows "
                            "no está activo. OS read-only guarantee: unknown/partial -- la "
                            "protección de solo lectura depende únicamente de pathguard (Harmessi).",
                            subject=source_id,
                        )
                    )
            else:
                escribible = os.access(ruta, os.W_OK)
                if not escribible:
                    resultados.append(
                        checks.CheckResult(
                            checks.STATUS_PASS,
                            "M12-FUENTE-EXTERNA-PERMISOS",
                            f"Fuente externa {source_id!r}: permisos POSIX no permiten escritura "
                            "para el usuario actual.",
                            subject=source_id,
                        )
                    )
                else:
                    resultados.append(
                        checks.CheckResult(
                            checks.STATUS_WARN,
                            "M12-FUENTE-EXTERNA-PERMISOS",
                            f"Fuente externa {source_id!r}: el usuario actual tiene permiso de "
                            "escritura OS sobre esta ruta -- la protección de solo lectura depende "
                            "únicamente de pathguard (Harmessi), no del sistema operativo.",
                            subject=source_id,
                        )
                    )
        except OSError:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_WARN,
                    "M12-FUENTE-EXTERNA-PERMISOS",
                    f"Fuente externa {source_id!r}: error al consultar permisos. "
                    "OS read-only guarantee: unknown/partial.",
                    subject=source_id,
                )
            )
    return resultados


def _check_ownership_5_vias(destino: Path, control_data: Optional[dict]) -> list:
    """Ownership de 5 vías (R21 de B5 + R12 de M10): reporta EXPLÍCITAMENTE
    las categorías (1) archivo preexistente del usuario y (3)/(4) project
    config/local override soportados -- las categorías (2) managed file y
    (5) drift YA las cubren `_check_archivos_administrados`/
    `_check_hashes_drift`, este check NO las duplica."""
    resultados = []

    if control_data is not None:
        perfil = control_data.get("perfil")
        installation_stage = control_data.get("installation_stage")
        rutas_administradas = {
            a.get("ruta") for a in control_data.get("archivos", []) if isinstance(a, dict)
        }
        try:
            if installation_stage is not None:
                entradas = manifest_mod.manifest_para_perfil_y_stage(perfil, installation_stage)
            else:
                entradas = manifest_mod.manifest_para_perfil(perfil)
        except manifest_mod.PerfilDesconocidoError:
            entradas = []

        for entrada in entradas:
            if entrada.destino == ".ds_init/control.json":
                continue
            if entrada.destino in rutas_administradas:
                continue  # categoría (2)/(5), ya cubiertas por otros checks
            if _entrada_solo_opt_in(entrada) and not manifest_mod.filtrar_entradas_por_capabilities(
                [entrada], _capabilities_efectivas_de_control(control_data)
            ):
                continue  # I2: tooling de capability opt-in deshabilitada que quedó en disco
            ruta = destino / entrada.destino
            if ruta.exists():
                resultados.append(
                    checks.CheckResult(
                        checks.STATUS_PASS,
                        "HARMESSI-OWNERSHIP-USUARIO",
                        f"{entrada.destino}: archivo preexistente del usuario, Harmessi no lo "
                        "administra (omitido por colisión en la instalación, nunca sobrescrito).",
                        subject=entrada.destino,
                    )
                )

    ruta_project_config = destino / ".harmessi" / "project-config.json"
    if ruta_project_config.exists():
        resultados.append(
            checks.CheckResult(
                checks.STATUS_PASS,
                "HARMESSI-OWNERSHIP-PROJECT-CONFIG",
                "project-config.json presente: customización de proyecto soportada (M10).",
                subject=".harmessi/project-config.json",
            )
        )

    ruta_local_override = destino / ".harmessi" / "local-overrides.json"
    if ruta_local_override.exists():
        resultados.append(
            checks.CheckResult(
                checks.STATUS_PASS,
                "HARMESSI-OWNERSHIP-LOCAL-OVERRIDE",
                "local-overrides.json presente: override local soportado (M10).",
                subject=".harmessi/local-overrides.json",
            )
        )

    return resultados


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


def _check_installation_stage(destino: Path, control_data: Optional[dict]) -> list:
    """`HARMESSI-INSTALLATION-STAGE` (R11 de `spec.md`, Change 7 v0.3): solo
    lectura, nunca muta `.harmessi/project.json` ni `.ds_init/control.json`.
    Compara `project_stage` (madurez alcanzada, `maturity.py`) contra
    `installation_stage` (capacidades físicas instaladas, `control.json`) --
    ejes ortogonales que nunca se confunden entre sí (R9). Nunca `ERROR`/
    `FAIL` bajo ningún escenario (regla explícita del usuario, §18): sin
    datos suficientes -> `N/A`; `project_stage` más avanzado -> `WARN`
    accionable; `installation_stage` más avanzado o igual -> `PASS`."""
    codigo = "HARMESSI-INSTALLATION-STAGE"
    try:
        return _check_installation_stage_interno(destino, control_data, codigo)
    except Exception as exc:  # noqa: BLE001 - garantia dura: este check nunca puede dar ERROR
        # Blindaje explicito (hallazgo de revision, Change 7 v0.3): ademas de
        # `MaturityEstadoError` (la excepcion de dominio esperada de
        # `maturity.leer_estado`, ya manejada abajo), este check puede
        # toparse con un `OSError`/`UnicodeDecodeError` de bajo nivel -- p.
        # ej. una condicion de carrera TOCTOU entre el `.exists()` de abajo y
        # el `open()` interno de `leer_estado`. Sin este manejo, esa
        # excepcion escaparia hasta `checks.ejecutar_checks`, que la
        # convertiria en `FAIL`/`technical_error` (mapeado a `ERROR` por
        # Doctor) -- prohibido explicitamente para este check bajo cualquier
        # escenario (R11 de `spec.md`).
        return [
            checks.CheckResult(
                checks.STATUS_NA,
                codigo,
                f"No se pudo comparar project_stage vs installation_stage por un error "
                f"inesperado (nunca se trata como fallo bloqueante en este check): {exc!r}",
            )
        ]


def _check_installation_stage_interno(destino: Path, control_data: Optional[dict], codigo: str) -> list:
    ruta_project = maturity.state_path(destino)
    if not ruta_project.exists():
        return [
            checks.CheckResult(
                checks.STATUS_NA,
                codigo,
                f"No existe {ruta_project}: no se puede comparar project_stage vs "
                "installation_stage (proyecto sin 'ds_guard project init' todavía).",
            )
        ]
    try:
        estado_proyecto = maturity.leer_estado(ruta_project)
    except maturity.MaturityEstadoError as exc:
        return [
            checks.CheckResult(
                checks.STATUS_NA,
                codigo,
                f"{ruta_project} existe pero no es válido, no se puede comparar: {exc}",
            )
        ]
    project_stage = estado_proyecto.get("project_stage")

    if control_data is None:
        return [
            checks.CheckResult(
                checks.STATUS_NA,
                codigo,
                "No hay control.json legible: no se puede determinar installation_stage.",
            )
        ]

    perfil = control_data.get("perfil")
    installation_stage = control_data.get("installation_stage")
    if installation_stage is None:
        try:
            # Solo para MOSTRAR -- la inferencia nunca se persiste desde
            # Doctor (R6/R11 de spec.md).
            installation_stage = legacy_mod.inferir_installation_stage(destino, perfil)
        except manifest_mod.PerfilDesconocidoError as exc:
            return [
                checks.CheckResult(
                    checks.STATUS_NA,
                    codigo,
                    f"No se pudo inferir installation_stage (perfil desconocido): {exc}",
                )
            ]

    try:
        indice_project = manifest_mod.ORDEN_STAGES.index(project_stage)
        indice_instalacion = manifest_mod.ORDEN_STAGES.index(installation_stage)
    except ValueError:
        return [
            checks.CheckResult(
                checks.STATUS_NA,
                codigo,
                f"stage(s) no reconocido(s) en {manifest_mod.ORDEN_STAGES}: "
                f"project_stage={project_stage!r}, installation_stage={installation_stage!r}",
            )
        ]

    if indice_project > indice_instalacion:
        return [
            checks.CheckResult(
                checks.STATUS_WARN,
                codigo,
                f"project_stage ({project_stage!r}) más avanzado que installation_stage "
                f"({installation_stage!r}): capabilities físicas pendientes de sync -- correr "
                f"'python -m tools.ds_init sync --stage {project_stage} --execute'.",
            )
        ]
    return [
        checks.CheckResult(
            checks.STATUS_PASS,
            codigo,
            f"installation_stage ({installation_stage!r}) cubre project_stage ({project_stage!r}).",
        )
    ]


# --- GOVERNANCE (Change 20261005, R53-R58) ----------------------------------------

_GOV_OPT_IN_FALLBACK = ("data_cards", "model_governance")
_GOV_STAGES_NONE_WARN = frozenset({"production_candidate", "production"})
# Archivo exclusivo de cada capability opt-in (el tooling compartido no sirve
# para distinguir cuál está instalada).
_GOV_TOOLING_EXCLUSIVO = {
    "data_cards": "tools/cards/datacard.py",
    "model_governance": "tools/cards/modelcard.py",
}
# Directorios conocidos (R19) y documento de hardening (R22) por capability.
_GOV_DIRS_CONTENIDO = {
    "data_cards": ("governance/cards/data",),
    "model_governance": ("governance/cards/model", "governance/model-risk"),
}
_GOV_ARCHIVOS_CONTENIDO = {"model_governance": ("governance/policy/model-risk-hardening.json",)}
_GOV_KINDS_POR_CAPABILITY = {"data_cards": ("data",), "model_governance": ("model", "governance")}
_GOV_ANCHOR_NO_VERIFICADO = frozenset({"missing", "unresolvable", "stale"})
_GOV_CODIGOS_ANCHOR = frozenset({"ANCHOR-STALE", "ANCHOR-MISSING", "ANCHOR-UNRESOLVABLE"})
_GOV_FRASE = "card governance requirements not satisfied"
_GOV_NOTA_COMPLETE = (
    "complete ≠ éticamente aceptable/seguro/justo/compliant: solo indica que los requisitos "
    "de la policy están satisfechos con soportes verificados"
)


def _gov_limpiar(valor, maximo: int = 120) -> str:
    """Valor provisto por el usuario -> texto sin caracteres de control, truncado (R49)."""
    texto = "".join(c if c.isprintable() else "?" for c in str(valor))
    return texto if len(texto) <= maximo else texto[: maximo - 3] + "..."


def _gov_hay_json(directorio: Path) -> bool:
    try:
        return any(e.name.endswith(".json") for e in directorio.iterdir())
    except OSError:
        return False


def _gov_hay_contenido(destino: Path, capability: str) -> bool:
    if any(_gov_hay_json(destino / d) for d in _GOV_DIRS_CONTENIDO.get(capability, ())):
        return True
    return any((destino / f).exists() for f in _GOV_ARCHIVOS_CONTENIDO.get(capability, ()))


def _gov_project_stage(destino: Path) -> Optional[str]:
    """`project_stage` como `_check_installation_stage`; cualquier problema -> None."""
    try:
        ruta = maturity.state_path(destino)
        if not ruta.exists():
            return None
        return maturity.leer_estado(ruta).get("project_stage")
    except Exception:  # noqa: BLE001 - sin madurez legible: la fila NONE queda en N/A
        return None


def _gov_ownership(control_data: Optional[dict]) -> list:
    """R18: `archivos` no debe listar rutas bajo `governance/` (es del proyecto)."""
    archivos = control_data.get("archivos") if isinstance(control_data, dict) else None
    resultados = []
    for entrada in archivos if isinstance(archivos, list) else []:
        ruta = entrada.get("ruta") if isinstance(entrada, dict) else None
        if not isinstance(ruta, str):
            continue
        normalizada = ruta.replace("\\", "/").lstrip("./")
        if normalizada == "governance" or normalizada.startswith("governance/"):
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_WARN,
                    "HARMESSI-GOV-OWNERSHIP",
                    "control.json lista una ruta bajo governance/, que es contenido del proyecto "
                    f"(no administrado por Harmessi): {_gov_limpiar(ruta)}",
                    subject=_gov_limpiar(ruta),
                )
            )
    return resultados


def _gov_anchor_no_verificado(reporte) -> bool:
    for ancla in getattr(reporte, "anchors", ()) or ():
        if not isinstance(ancla, dict):
            continue
        estado = ancla.get("state") or (ancla.get("resolution") or {}).get("state")
        if estado in _GOV_ANCHOR_NO_VERIFICADO:
            return True
    return any(
        isinstance(h, dict) and h.get("code") in _GOV_CODIGOS_ANCHOR
        for h in getattr(reporte, "findings", ()) or ()
    )


def _gov_resultados_de_reporte(reporte) -> list:
    """Una Card/assessment ya validado -> filas de R55 (D11: Doctor lee el estado, no lo decide)."""
    asesoramiento = reporte.kind == "governance"
    sufijo = "ASSESSMENT" if asesoramiento else "CARD"
    etiqueta = f"{reporte.kind} {_gov_limpiar(reporte.card_id)} ({_gov_limpiar(reporte.rel_path)})"
    ruta = _gov_limpiar(reporte.rel_path)
    estado = reporte.status
    resultados = []
    if estado == "complete":
        resultados.append(
            checks.CheckResult(
                checks.STATUS_PASS, f"HARMESSI-GOV-{sufijo}-COMPLETE", f"{etiqueta}: {_GOV_NOTA_COMPLETE}.", subject=ruta
            )
        )
    elif estado in ("stale", "incomplete"):
        resultados.append(
            checks.CheckResult(
                checks.STATUS_WARN,
                f"HARMESSI-GOV-{sufijo}-{estado.upper()}",
                f"{etiqueta}: {_GOV_FRASE} (estado {estado}).",
                subject=ruta,
            )
        )
    else:  # invalid o estado no reconocido: no se puede confiar en el artefacto
        resultados.append(
            checks.CheckResult(
                checks.STATUS_FAIL,
                "HARMESSI-GOV-CARD-INVALID",
                f"{etiqueta}: {_GOV_FRASE}; artefacto inválido (estado {_gov_limpiar(estado)}).",
                subject=ruta,
            )
        )
    if _gov_anchor_no_verificado(reporte):
        resultados.append(
            checks.CheckResult(
                checks.STATUS_WARN,
                "HARMESSI-GOV-ANCHOR-UNVERIFIED",
                f"{etiqueta}: atestación anchored sin verificar (missing/unresolvable/stale): "
                f"{_GOV_FRASE}.",
                subject=ruta,
            )
        )
    return resultados


def _check_governance(destino: Path, control_data: Optional[dict]) -> list:
    """`HARMESSI-GOV-*` (R53-R58, tabla R55). Solo lectura; capabilities solo desde
    `control.json` (R12/R54); no toca drift ni el manifiesto (R56). Doctor lee el
    estado ya derivado por `tools.cards` -- nunca lo decide (D11). ERROR queda para
    configuración inválida, capabilities inválidas y artefactos `invalid`."""
    resultados = _gov_ownership(control_data)
    if control_data is None:
        resultados.append(
            checks.CheckResult(
                checks.STATUS_NA,
                "HARMESSI-GOV-CAPABILITY",
                "Sin control.json legible: no se pueden determinar las capabilities de governance.",
            )
        )
        return resultados

    crudo = control_data.get("capabilities_habilitadas")
    habilitadas = _capabilities_efectivas_de_control(control_data)
    opt_in = tuple(getattr(manifest_mod, "CAPABILITIES_OPT_IN", _GOV_OPT_IN_FALLBACK))
    validas = tuple(getattr(manifest_mod, "CAPABILITIES_VALIDAS", manifest_mod.CAPABILITIES_CONOCIDAS + opt_in))

    desconocidas = [c for c in (crudo if isinstance(crudo, list) else []) if c not in validas]
    if desconocidas:
        resultados.append(
            checks.CheckResult(
                checks.STATUS_WARN,
                "HARMESSI-GOV-CAPABILITY-UNKNOWN",
                f"Capability(s) no reconocida(s) en control.json: {[_gov_limpiar(c) for c in desconocidas]} "
                f"(válidas: {list(validas)}).",
            )
        )
    mensajes_invalidas = manifest_mod.validar_capabilities(sorted(c for c in habilitadas if c in validas))
    if mensajes_invalidas:
        resultados.append(
            checks.CheckResult(
                checks.STATUS_FAIL,
                "HARMESSI-GOV-CAPABILITY-INVALID",
                "Combinación de capabilities inválida: " + "; ".join(_gov_limpiar(m, 200) for m in mensajes_invalidas),
            )
        )

    kinds_por_capability = {}
    for capability in opt_in:
        if capability in habilitadas:
            if capability == "model_governance" and mensajes_invalidas:
                continue  # combinación inválida: ya es ERROR, no se valida contenido
            kinds_por_capability[capability] = _GOV_KINDS_POR_CAPABILITY.get(capability, ())
            continue
        tooling = _GOV_TOOLING_EXCLUSIVO.get(capability)
        if tooling and (destino / tooling).exists():
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_NA,
                    "HARMESSI-GOV-INSTALLED-DISABLED",
                    f"Capability {capability!r} deshabilitada con su tooling presente (installed-but-disabled).",
                    subject=tooling,
                )
            )
        if _gov_hay_contenido(destino, capability):
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_NA,
                    "HARMESSI-GOV-CONTENT-DISABLED",
                    f"Hay contenido de governance en rutas conocidas pero la capability {capability!r} "
                    "está deshabilitada: no se valida.",
                )
            )
    if not any(c in habilitadas for c in opt_in):
        resultados.append(
            checks.CheckResult(
                checks.STATUS_NA,
                "HARMESSI-GOV-CAPABILITY",
                "Ninguna capability opt-in de governance (data_cards/model_governance) habilitada.",
            )
        )
    if not kinds_por_capability:
        return resultados

    try:
        from tools.cards import discovery  # import perezoso (R58)
    except Exception as exc:  # noqa: BLE001 - tooling ausente/roto: WARN, nunca ERROR
        resultados.append(
            checks.CheckResult(
                checks.STATUS_WARN,
                "HARMESSI-GOV-TOOLING",
                f"No se pudo importar tools.cards (capability habilitada): {_gov_limpiar(repr(exc), 200)}",
            )
        )
        return resultados

    kinds = [k for ks in kinds_por_capability.values() for k in ks]
    validacion = discovery.validar_proyecto(destino, kinds=kinds)

    gobierno = getattr(validacion, "governance", None)
    if "model_governance" in kinds_por_capability and gobierno is not None:
        codigos = sorted({_gov_limpiar(getattr(h, "code", "?")) for h in getattr(gobierno, "findings", ())})
        if gobierno.state == "invalid":
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_FAIL,
                    "HARMESSI-GOV-CONFIG-INVALID",
                    f"Hardening/capa local inválida o relajada ({', '.join(codigos) or 'sin detalle'}): "
                    f"{_GOV_FRASE}.",
                    subject=getattr(gobierno, "project_hardening_path", None),
                )
            )
        elif gobierno.state == "unresolvable":
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_WARN,
                    "HARMESSI-GOV-CONFIG-UNRESOLVABLE",
                    f"Hardening presente pero no resoluble ({', '.join(codigos) or 'sin detalle'}): "
                    f"{_GOV_FRASE}.",
                    subject=getattr(gobierno, "project_hardening_path", None),
                )
            )

    reportes = list(getattr(validacion, "reports", ()))
    for capability, ks in kinds_por_capability.items():
        if any(r.kind in ks for r in reportes):
            continue
        etapa = _gov_project_stage(destino)
        if etapa in _GOV_STAGES_NONE_WARN:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_WARN,
                    "HARMESSI-GOV-NONE",
                    f"Capability {capability!r} habilitada sin Cards con project_stage={etapa!r}: "
                    f"{_GOV_FRASE}.",
                )
            )
        else:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_NA,
                    "HARMESSI-GOV-NONE",
                    f"Capability {capability!r} habilitada, todavía sin Cards.",
                )
            )
    for reporte in reportes:
        resultados += _gov_resultados_de_reporte(reporte)
    return resultados


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
    resultados += _ejecutar_check(
        SECCION_HARMESSI, "HARMESSI-OWNERSHIP", _check_ownership_5_vias, destino, control_data
    )
    resultados += _ejecutar_check(SECCION_HARMESSI, "HARMESSI-AGENTE", _check_agents, destino, control_data)
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
        SECCION_HARMESSI, "M12-FUENTE-EXTERNA-PERMISOS", _check_fuentes_externas_permisos_os, destino
    )
    resultados += _ejecutar_check(
        SECCION_HARMESSI, "HARMESSI-VERSION", _check_coherencia_version, control_data
    )
    resultados += _ejecutar_check(
        SECCION_HARMESSI, "HARMESSI-INSTALLATION-STAGE", _check_installation_stage, destino, control_data
    )
    resultados += _ejecutar_check(
        SECCION_HARMESSI, "HARMESSI-GOV", _check_governance, destino, control_data
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
