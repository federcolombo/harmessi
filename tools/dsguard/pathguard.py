"""Protección de rutas (Bloque 3, reliability v0.2.0): holdouts, `data/raw`,
secretos, `.claude/guardrails.json` y `write_scopes` opcionales.

Enforcement real (garantía fuerte) para `Write`/`Edit`/`NotebookEdit`/`Read`/
`Grep`: estas tools traen una ruta estructurada y exacta en `tool_input`, así
que se puede resolver, normalizar y comparar con certeza.

Para `Bash`/`PowerShell` el enforcement es **best-effort, deliberadamente no
equivalente**: el comando es una cadena de shell arbitraria, no hay forma
confiable de parsearla sin un parser de shell completo (fuera de alcance de
v0.2, ver diseño del Bloque 3). El escaneo acá detecta referencias directas y
literales a una ruta protegida en el texto del comando; no detecta
indirección (variables, `cd` previo, comandos generados dinámicamente,
encoding). Se documenta así en cada mensaje de denegación relacionado.

Config: `<repo_root>/.claude/guardrails.json` (opcional -- ausente usa
defaults seguros). Ver `cargar_config` para el schema exacto.

Nota de implementación: los nombres de campo asumidos para `tool_input` de
`Write`/`Edit`/`NotebookEdit`/`Read`/`Grep` (`file_path`, `notebook_path`,
`path`) están tomados de la forma más común documentada de las tools de
Claude Code, con más de una clave probada por tool a modo de fallback
defensivo (mismo criterio que `hook_presupuesto._extraer_agent_id`) --
deberían reconfirmarse contra la documentación real de hooks antes de
depender de esto en producción con tráfico real no probado en este entorno.

Solo biblioteca estándar, mismo patrón que el resto de `tools/dsguard`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import repo as repo_mod
from .core import parsear_utc

# --- Config ------------------------------------------------------------------

RUTA_CONFIG_RELATIVA = ".claude/guardrails.json"

# Ruta protegida por el propio pathguard: ni el Lead ni ningún subagente
# pueden modificarla vía Write/Edit/NotebookEdit ni (best-effort) vía
# Bash/PowerShell. La única vía de edición en v0.2 es manual, fuera de
# Claude Code -- deliberado (ver diseño del Bloque 3): cualquier excepción de
# holdout debe quedar como acto humano auditable, no como algo que un agente
# pueda escribirse a sí mismo.
RUTA_GUARDRAILS_PROTEGIDA = ".claude/guardrails.json"

# Denylist de secretos: dura, no removible desde la config -- `secretos_extra`
# solo puede *agregar*, nunca sacar nada de acá (mismo criterio que
# `nbrunner.manifest.RUTAS_PROHIBIDAS_SIEMPRE`). Conservadora a propósito:
# certificados públicos (`.crt`/`.cer`) quedan fuera porque no son secretos
# per se; `.pem` sí se incluye entero pese a ser ambiguo (puede ser una clave
# privada) porque el costo de un falso positivo es mucho menor que el de
# dejar pasar una clave.
SECRETOS_HARDCODEADOS: tuple = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12",
    "id_rsa*",
    "id_ed25519*",
    "id_ecdsa*",
    ".ssh/**",
    "credentials.json",
    "*_credentials.json",
    "**/.aws/**",
    "**/.gcloud/**",
    "**/.azure/**",
    "*.kdbx",
)

# Default si `guardrails.json` no existe o no declara `data_raw` -- coincide
# con CLAUDE.md §1 ("data/raw/ es solo lectura") y con
# `nbrunner.manifest.RUTAS_PROHIBIDAS_SOLO_SALIDA`.
DATA_RAW_DEFAULT: tuple = ("data/raw/**",)


class ConfigGuardrailsError(Exception):
    """`guardrails.json` existe pero está corrupto o mal formado.

    A diferencia de `launcher_common.resolver_venv_dir` (que ante un
    `control.json` corrupto usa un default en silencio, porque ahí la
    corrupción no es un riesgo de seguridad), acá la corrupción es
    indistinguible de un intento de sabotaje del propio guardrail -- el
    llamador (`hook_rutas.py`) debe tratar esto como fail-closed (denegar),
    nunca recuperarse con un default."""


@dataclass(frozen=True)
class ConfigGuardrails:
    holdouts: tuple = ()
    data_raw: tuple = DATA_RAW_DEFAULT
    secretos_extra: tuple = ()
    write_scopes: dict = field(default_factory=dict)
    excepciones: tuple = ()


def _validar_lista_de_strings(valor, nombre_campo: str, ruta_config: Path) -> tuple:
    if not isinstance(valor, list) or not all(isinstance(x, str) for x in valor):
        raise ConfigGuardrailsError(f"{ruta_config}: {nombre_campo!r} debe ser una lista de strings")
    return tuple(valor)


def cargar_config(repo_root: Path) -> ConfigGuardrails:
    """Carga `<repo_root>/.claude/guardrails.json`. Si no existe, devuelve
    los defaults seguros (`data_raw` protegido, todo lo demás vacío) --
    ausencia de config NO es fail-closed, es "usar la política mínima
    conservadora". Si el archivo existe pero no se puede leer/parsear, o su
    schema es inválido, levanta `ConfigGuardrailsError` -- el llamador debe
    tratar eso como fail-closed."""
    ruta_config = repo_root / RUTA_CONFIG_RELATIVA
    if not ruta_config.exists():
        return ConfigGuardrails()

    try:
        contenido = ruta_config.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigGuardrailsError(f"No se pudo leer {ruta_config}: {exc}") from exc

    try:
        datos = json.loads(contenido)
    except ValueError as exc:
        raise ConfigGuardrailsError(f"{ruta_config} no es JSON válido: {exc}") from exc

    if not isinstance(datos, dict):
        raise ConfigGuardrailsError(f"{ruta_config} no contiene un objeto JSON")

    holdouts = _validar_lista_de_strings(datos.get("holdouts", []), "holdouts", ruta_config)
    data_raw = _validar_lista_de_strings(
        datos.get("data_raw", list(DATA_RAW_DEFAULT)), "data_raw", ruta_config
    )
    secretos_extra = _validar_lista_de_strings(
        datos.get("secretos_extra", []), "secretos_extra", ruta_config
    )
    excepciones = datos.get("excepciones", [])
    if not isinstance(excepciones, list) or not all(isinstance(e, dict) for e in excepciones):
        raise ConfigGuardrailsError(f"{ruta_config}: 'excepciones' debe ser una lista de objetos")
    write_scopes = datos.get("write_scopes", {})
    if not isinstance(write_scopes, dict):
        raise ConfigGuardrailsError(f"{ruta_config}: 'write_scopes' debe ser un objeto")
    for agente, patrones in write_scopes.items():
        if not isinstance(patrones, list) or not all(isinstance(p, str) for p in patrones):
            raise ConfigGuardrailsError(
                f"{ruta_config}: write_scopes[{agente!r}] debe ser una lista de strings"
            )

    return ConfigGuardrails(
        holdouts=holdouts,
        data_raw=data_raw,
        secretos_extra=secretos_extra,
        write_scopes={k: tuple(v) for k, v in write_scopes.items()},
        excepciones=tuple(excepciones),
    )


# --- Normalización y matching de rutas ---------------------------------------


def resolver_ruta_relativa(ruta_bruta: str, repo_root: Path) -> tuple:
    """Resuelve `ruta_bruta` (relativa o absoluta) contra `repo_root`,
    siguiendo symlinks y normalizando `.`/`..` (`Path.resolve()`, que no
    exige que el archivo exista -- así una ruta todavía inexistente, pero que
    *se crearía* dentro de una ubicación protegida, se evalúa igual por su
    ubicación prevista).

    Devuelve `(ruta_relativa_posix, dentro_del_repo)`. Si no se puede
    resolver, o si la ruta resuelta cae fuera de `repo_root`,
    `dentro_del_repo` es `False` (y `ruta_relativa_posix` es `None`) -- nunca
    lanza."""
    try:
        candidato = Path(ruta_bruta)
        if not candidato.is_absolute():
            candidato = repo_root / candidato
        resuelto = candidato.resolve()
        repo_resuelto = repo_root.resolve()
    except (OSError, RuntimeError, ValueError):
        return None, False

    try:
        relativo = resuelto.relative_to(repo_resuelto)
    except ValueError:
        return None, False

    return relativo.as_posix(), True


def _matchea_patrones(ruta_relativa_posix: str, patrones) -> bool:
    """Comparación case-insensitive (mismo criterio que
    `nbrunner.manifest._colisiona`: en NTFS/APFS case-insensitive, un
    casing distinto no debe poder esquivar una ruta protegida). Reusa
    `dsguard.repo.path_matches_any`, casefoldeando ambos lados antes."""
    ruta_normalizada = ruta_relativa_posix.casefold()
    patrones_normalizados = [p.casefold() for p in patrones]
    return repo_mod.path_matches_any(ruta_normalizada, patrones_normalizados)


def _excepcion_vigente(excepciones: tuple, ruta_relativa_posix: str, accion: str, ahora) -> bool:
    """Una excepción autoriza una ruta EXACTA (no un patrón -- a propósito,
    para que una excepción puntual no termine cubriendo un directorio entero
    por descuido de quien la escribe), para una `accion` exacta
    (`"read"`), sin vencer. Fecha ilegible o vencida => no vigente (fail
    conservador, nunca se asume vigente ante la duda)."""
    for excepcion in excepciones:
        if excepcion.get("accion") != accion:
            continue
        ruta_excepcion = excepcion.get("ruta")
        if not isinstance(ruta_excepcion, str):
            continue
        if ruta_excepcion.casefold() != ruta_relativa_posix.casefold():
            continue
        vence_utc = excepcion.get("vence_utc")
        if vence_utc:
            try:
                vencimiento = parsear_utc(vence_utc)
            except (ValueError, TypeError):
                continue
            if ahora > vencimiento:
                continue
        return True
    return False


# --- Evaluación: Write / Edit / NotebookEdit / Read ---------------------------

# Más de una clave posible por tool, en orden de preferencia -- ver nota de
# implementación al inicio del módulo sobre por qué esto es defensivo.
_CAMPOS_RUTA_POR_TOOL = {
    "Write": ("file_path", "path"),
    "Edit": ("file_path", "path"),
    "NotebookEdit": ("notebook_path", "file_path", "path"),
    "Read": ("file_path", "path"),
}

_TOOLS_ESCRITURA = ("Write", "Edit", "NotebookEdit")


def _extraer_ruta_bruta(tool_name: str, tool_input: dict) -> Optional[str]:
    for campo in _CAMPOS_RUTA_POR_TOOL.get(tool_name, ()):
        valor = tool_input.get(campo)
        if isinstance(valor, str) and valor:
            return valor
    return None


def _evaluar_ruta_estructurada(
    tool_name: str, tool_input: dict, agent_type: Optional[str], config: ConfigGuardrails, repo_root: Path
) -> tuple:
    ruta_bruta = _extraer_ruta_bruta(tool_name, tool_input)
    if ruta_bruta is None:
        return False, f"No se pudo determinar la ruta del tool call '{tool_name}': denegado (fail-closed)."

    ruta_relativa, dentro_del_repo = resolver_ruta_relativa(ruta_bruta, repo_root)
    if not dentro_del_repo:
        return False, f"Ruta fuera del repositorio o no resoluble: {ruta_bruta!r}."

    es_escritura = tool_name in _TOOLS_ESCRITURA

    if es_escritura and ruta_relativa.casefold() == RUTA_GUARDRAILS_PROTEGIDA.casefold():
        return False, "guardrails.json está protegido: no puede modificarse vía Write/Edit/NotebookEdit."

    patrones_secretos = SECRETOS_HARDCODEADOS + config.secretos_extra
    if _matchea_patrones(ruta_relativa, patrones_secretos):
        return False, f"Ruta protegida (secreto): {ruta_relativa}."

    if _matchea_patrones(ruta_relativa, config.holdouts):
        if es_escritura:
            return False, f"Ruta protegida (holdout, la escritura nunca está autorizada): {ruta_relativa}."
        if _excepcion_vigente(config.excepciones, ruta_relativa, "read", datetime.now(timezone.utc)):
            return True, f"Holdout con excepción de lectura vigente: {ruta_relativa}."
        return False, f"Ruta protegida (holdout, requiere excepción explícita en guardrails.json): {ruta_relativa}."

    if es_escritura and _matchea_patrones(ruta_relativa, config.data_raw):
        return False, f"data/raw es de solo lectura: {ruta_relativa}."

    if es_escritura and agent_type and config.write_scopes:
        scope = config.write_scopes.get(agent_type)
        if scope is None:
            return False, f"Agente {agent_type!r} no tiene write_scope declarado en guardrails.json."
        if not _matchea_patrones(ruta_relativa, scope):
            return False, f"Ruta fuera del write_scope declarado para {agent_type!r}: {ruta_relativa}."

    return True, "Ruta permitida."


def _evaluar_grep(tool_input: dict, config: ConfigGuardrails, repo_root: Path) -> tuple:
    ruta_bruta = tool_input.get("path")
    if ruta_bruta is None:
        # Grep sin `path` explícito busca ampliamente (p. ej. desde la raíz
        # del repo): no hay una ubicación puntual que resolver y chequear.
        # Limitación documentada del Bloque 3 (ver diseño): no cubierto en
        # v0.2, queda para v0.3+ (containment recursivo).
        return True, "Grep sin 'path' explícito: fuera de alcance de pathguard en v0.2."

    if not isinstance(ruta_bruta, str):
        return False, "Grep con 'path' de tipo inválido: denegado (fail-closed)."

    ruta_relativa, dentro_del_repo = resolver_ruta_relativa(ruta_bruta, repo_root)
    if not dentro_del_repo:
        return False, f"Ruta fuera del repositorio o no resoluble: {ruta_bruta!r}."

    patrones_secretos = SECRETOS_HARDCODEADOS + config.secretos_extra
    if _matchea_patrones(ruta_relativa, patrones_secretos):
        return False, f"Ruta protegida (secreto): {ruta_relativa}."

    if _matchea_patrones(ruta_relativa, config.holdouts):
        if _excepcion_vigente(config.excepciones, ruta_relativa, "read", datetime.now(timezone.utc)):
            return True, f"Holdout con excepción de lectura vigente: {ruta_relativa}."
        return False, f"Ruta protegida (holdout, requiere excepción explícita en guardrails.json): {ruta_relativa}."

    return True, "Ruta permitida."


# --- Evaluación: Bash / PowerShell (best-effort) ------------------------------

# Heurística de "esto parece una escritura": substrings, no gramática de
# shell real (deliberado, ver diseño del Bloque 3 -- no se construye un
# parser de shell en v0.2). Cubre los comandos directos más comunes en
# Bash/PowerShell; no pretende ser exhaustiva.
_PATRONES_ESCRITURA_SHELL: tuple = (
    "rm ", "rm\t", "remove-item",
    "mv ", "move-item",
    "cp ", "copy-item",
    "tee ",
    "sed -i", "sed --in-place",
    "truncate ", "dd ", "shred ",
    "chmod ", "chown ",
    "set-content", "add-content", "out-file", "new-item", "clear-content",
    "git add", "git rm",
)

# Redirección de shell (`>`, `>>`) detectada aparte, vía regex: un `>` suelto
# es indistinguible en texto libre de un `->` (p. ej. anotaciones de tipo de
# Python) o un `>=`/`=>` -- excluirlos explícitamente evita ese falso
# positivo concreto (confirmado en la práctica: `print(x, '->', y)` no debe
# leerse como una redirección).
_PATRON_REDIRECCION = re.compile(r"(?<![-=])>{1,2}(?!=)")

_OPERADORES_SHELL: tuple = ("&&", "||", ";", "|", "(", ")", "`", "$(", "<", ">>", ">")


def _es_escritura_shell(comando: str) -> bool:
    normalizado = comando.casefold()
    if _PATRON_REDIRECCION.search(comando):
        return True
    return any(patron in normalizado for patron in _PATRONES_ESCRITURA_SHELL)


def _tokens_de_comando(comando: str) -> list:
    """Tokenización deliberadamente ingenua (split por espacios tras
    reemplazar operadores comunes por espacios): no es un parser de shell,
    es lo mínimo para separar "palabras" del comando y poder buscar
    referencias literales a una ruta protegida en cada una."""
    normalizado = comando
    for operador in _OPERADORES_SHELL:
        normalizado = normalizado.replace(operador, " ")
    return [t.strip("'\"") for t in normalizado.split() if t.strip("'\"")]


def _comando_referencia_alguna(tokens: list, patrones, repo_root: Path) -> Optional[str]:
    """Primer token que matchea alguno de `patrones`, ya sea literalmente,
    resuelto como ruta relativa al repo, o (candidato extra) la parte de un
    token después de sus últimos ":" -- cubre puntualmente la sintaxis
    `git show <rev>:<ruta>` / `git log <rev>:<ruta>` (una fuga histórica
    conocida: un secreto/holdout borrado del working tree puede seguir
    siendo legible desde una revisión vieja) sin intentar interpretar la
    sintaxis de git en general. `None` si ningún candidato matchea.

    Best-effort: no detecta indirección (variables, `cd` previo, comandos
    generados dinámicamente, etc.), ver docstring del módulo."""
    for token in tokens:
        if token.startswith("-"):
            continue
        candidatos = [token]
        if ":" in token:
            candidatos.append(token.rpartition(":")[2])
        for candidato in candidatos:
            if not candidato:
                continue
            candidato_normalizado = candidato.replace("\\", "/")
            if _matchea_patrones(candidato_normalizado, patrones):
                return token
            ruta_relativa, dentro = resolver_ruta_relativa(candidato_normalizado, repo_root)
            if dentro and _matchea_patrones(ruta_relativa, patrones):
                return token
    return None


def _evaluar_shell(tool_input: dict, config: ConfigGuardrails, repo_root: Path) -> tuple:
    comando = tool_input.get("command")
    if not isinstance(comando, str) or not comando:
        return True, "Comando vacío o de tipo inválido: fuera de alcance de pathguard."

    tokens = _tokens_de_comando(comando)

    patrones_secretos = SECRETOS_HARDCODEADOS + config.secretos_extra
    referencia = _comando_referencia_alguna(tokens, patrones_secretos, repo_root)
    if referencia:
        return False, (
            f"Comando referencia una ruta protegida (secreto, escaneo best-effort, "
            f"no un parser de shell): {referencia!r}."
        )

    if config.holdouts:
        referencia = _comando_referencia_alguna(tokens, config.holdouts, repo_root)
        if referencia:
            return False, (
                f"Comando referencia una ruta protegida (holdout, escaneo best-effort; "
                f"las excepciones de lectura no aplican vía Bash/PowerShell): {referencia!r}."
            )

    referencia = _comando_referencia_alguna(tokens, (RUTA_GUARDRAILS_PROTEGIDA,), repo_root)
    if referencia and _es_escritura_shell(comando):
        return False, (
            f"Comando parece modificar guardrails.json (escaneo best-effort): {referencia!r}."
        )

    referencia = _comando_referencia_alguna(tokens, config.data_raw, repo_root)
    if referencia and _es_escritura_shell(comando):
        return False, (
            f"Comando parece escribir/borrar en data/raw (escaneo best-effort): {referencia!r}."
        )

    return True, "Comando permitido (escaneo best-effort; ver limitaciones documentadas del módulo)."


# --- Punto de entrada único ----------------------------------------------------


def evaluar_tool_call(payload: dict, config: ConfigGuardrails, repo_root: Path) -> tuple:
    """Devuelve `(permitido: bool, motivo: str)` para un payload de hook
    `PreToolUse` ya parseado. Función pura respecto de disco (salvo la
    resolución de rutas, que sí toca el filesystem para seguir symlinks) --
    no lanza por datos de entrada raros (tool_name desconocido, tool_input
    vacío), pero tampoco atrapa excepciones de bajo nivel a propósito: eso es
    responsabilidad del llamador (`hook_rutas.py`), que las trata como
    fail-closed. Mantenerla así permite que los tests vean fallar lo que
    realmente está roto, en vez de que un bug quede enmascarado acá."""
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    agent_type = payload.get("agent_type")

    if tool_name in _CAMPOS_RUTA_POR_TOOL:
        return _evaluar_ruta_estructurada(tool_name, tool_input, agent_type, config, repo_root)
    if tool_name == "Grep":
        return _evaluar_grep(tool_input, config, repo_root)
    if tool_name in ("Bash", "PowerShell"):
        return _evaluar_shell(tool_input, config, repo_root)

    return True, f"Herramienta {tool_name!r} fuera del alcance de pathguard: permitida."
