"""Allowlist pura de FORMA de comando del runtime de ejecución del Lead
(v0.8 Change 2, `20260929-lead-execution-runtime`, T2).

Módulo puro sobre `str`/`tuple`: sin I/O de filesystem real. La única
resolución de rutas que hace es EN MEMORIA (split/normalización de strings),
nunca `Path.exists()`/`Path.resolve()` (spec.md R1, R8, R9). Importa
únicamente `re`, `typing`, `pathlib` (no usado para I/O, solo declarado como
import permitido por el encargo), `os.path` (solo funciones puras de
manipulación de strings: `normcase`/`normpath`/`isabs` — NUNCA `os.stat`,
`os.path.exists`, `os.path.realpath` ni ninguna otra función que toque el
disco) y `from . import core` (relativo).

Responsabilidad única: reconocer si un `argv`/texto de comando matchea una de
las 4 formas declarativas (`core.EXECUTION_FORMS`). NO decide autorización
semántica (`tools.autonomy`), NO consulta `control.json`, NO importa
filesystem real (R9, spec.md) — reutilizable sin cambios por el futuro hook
estricto de `v0.10.md` (M5 de Change 0).

Función pública: `evaluar_comando(argv_o_texto, alcance, interprete_autorizado)
-> (permitido: bool, forma: Optional[str], motivo: str)`.
"""
from __future__ import annotations

import os.path
import re
from typing import Optional, Tuple, Union

from . import core

# ---------------------------------------------------------------------------
# `normalizar_interprete` — RÉPLICA LITERAL de
# `tools/nbrunner/hook_validar_comando.py:46-51` (no reinventada, citada por
# línea, tal como exige el encargo). Solo usa `os.path.normcase`/
# `os.path.normpath`: manipulación pura de strings, sin tocar el disco.
# ---------------------------------------------------------------------------


def normalizar_interprete(ruta: str) -> str:
    """Normaliza separadores de ruta y mayúsculas/minúsculas (Windows) para
    poder comparar dos rutas de intérprete por igualdad exacta post-
    normalización. Réplica literal de
    `tools/nbrunner/hook_validar_comando.py:46-51`."""
    return os.path.normcase(os.path.normpath(ruta))


# ---------------------------------------------------------------------------
# Patrón de la forma (c) notebook — RÉPLICA LITERAL de la cola (parte después
# del intérprete entre comillas) de `PATRON_COMANDO`, definido en
# `tools/nbrunner/hook_validar_comando.py:66-69`:
#
#   PATRON_COMANDO = re.compile(
#       r'^"(?P<interprete>[^"]+)" tools/notebook_runner\.py run --manifest '
#       r'(?P<manifest>[A-Za-z0-9_./-]+)(?: --dry-run| --execute)?$'
#   )
#
# Acá el intérprete ya se valida por separado (mismo criterio,
# `normalizar_interprete`, comparación exacta) antes de intentar esta forma,
# así que solo se reutiliza la cola de la regex (desde `tools/notebook_...`
# hasta el final), carácter por carácter, sin relajar ni endurecer la clase
# de caracteres del manifest.
# ---------------------------------------------------------------------------

_PATRON_COMANDO_NOTEBOOK_RESTO = re.compile(
    r'^tools/notebook_runner\.py run --manifest '
    r'(?P<manifest>[A-Za-z0-9_./-]+)(?: --dry-run| --execute)?$'
)

# Clase de caracteres básica para flags de pytest — mismo criterio que
# `PATRON_COMANDO` usa para el manifest (`hook_validar_comando.py:66-68`).
_PATRON_FLAG = re.compile(r'^[A-Za-z0-9_./=-]+$')

# Forma del texto único aceptado como `argv_o_texto` (paridad con el texto
# que usa `hook_validar_comando.py`): `'"<interprete>" resto del comando'`.
# LIMITACIÓN DOCUMENTADA: el "resto" no se parsea con un shell-split
# completo (no entiende comillas anidadas, escapes, etc.) — se captura tal
# cual como string para matchear contra `_PATRON_COMANDO_NOTEBOOK_RESTO`, y
# se tokeniza por espacios simples (`str.split()`) solo para reconstruir un
# `argv`-like usado por las formas (a)/(b)/(d). Es deliberadamente más
# simple que un parser de shell: esta función reconoce FORMA, no ejecuta
# nada.
_PATRON_TEXTO = re.compile(r'^"(?P<interprete>[^"]*)"\s*(?P<resto>.*)$', re.DOTALL)


# ---------------------------------------------------------------------------
# Helpers de validación de rutas EN MEMORIA (sin tocar el disco) — mismo
# gotcha que `_validar_manifest` de `hook_validar_comando.py:72-110`
# documenta: rechazo EXPLÍCITO de rutas absolutas y de traversal ANTES de
# cualquier unión/contención, porque `Path(base) / absoluta` descartaría
# `base` en silencio.
# ---------------------------------------------------------------------------

_PATRON_ABSOLUTA_DRIVE = re.compile(r'^[A-Za-z]:[\\/]')


def _es_ruta_absoluta(ruta: str) -> bool:
    """`True` si `ruta` es absoluta en POSIX (`/...`) o Windows (`C:\\...`,
    `\\...`). Chequeo manual (no `os.path.isabs`) para que el resultado no
    dependa de la plataforma donde corre este proceso — la misma llamada
    debe dar el mismo resultado en Windows y en POSIX (R9, pureza)."""
    if ruta.startswith("/") or ruta.startswith("\\"):
        return True
    return bool(_PATRON_ABSOLUTA_DRIVE.match(ruta))


def _tiene_traversal(ruta: str) -> bool:
    """`True` si algún componente de `ruta` (separada por `/` o `\\`) es
    `..`."""
    partes = re.split(r'[\\/]+', ruta)
    return ".." in partes


def _glob_asterisco(patron: str) -> "re.Pattern[str]":
    """Compila `patron` con la semántica de `fnmatch.fnmatchcase` restringida
    a `*` (cualquier secuencia de caracteres, incluida `/`); el resto de
    caracteres es literal. Se implementa con `re` para no ampliar los imports
    permitidos de este módulo (test de neutralidad de `tools/leadrun`)."""
    return re.compile("".join(".*" if c == "*" else re.escape(c) for c in patron) + r"\Z", re.DOTALL)


def _coincide_alcance(ruta: str, alcance: Tuple[str, ...]) -> bool:
    """`True` si `ruta` (ya validada como no-absoluta, sin traversal)
    coincide con alguna entrada de `alcance`: igualdad exacta o prefijo de
    directorio (criterio documentado: cada entrada de `alcance` se trata
    como una ruta de archivo exacta O un prefijo de directorio bajo el que
    `ruta` debe caer).

    Formas adicionales (R35-R36, `20261005-operational-autonomy-hardening`):
    - `dir/**`: el directorio mismo (p. ej. `pytest tools/tests`) y todos sus
      descendientes (prefijo `dir/`); no cubre hermanos como `dir_old/` porque
      el prefijo incluye la barra.
    - Entradas con `*` dentro de un segmento (p. ej. `tools/tests/test_x_*.py`):
      glob de `*` (equivalente a `fnmatchcase`) sobre la ruta completa. Sin `*`, comportamiento
      previo (exacto o prefijo de directorio plano).
    Todo en memoria, sin tocar el disco."""
    ruta_norm = ruta.replace("\\", "/")
    for entrada in alcance:
        entrada_norm = entrada.replace("\\", "/").rstrip("/")
        if not entrada_norm:
            continue
        if entrada_norm.endswith("/**"):
            base = entrada_norm[:-3].rstrip("/")
            if base and (ruta_norm == base or ruta_norm.startswith(base + "/")):
                return True
            continue
        if "*" in entrada_norm:
            if _glob_asterisco(entrada_norm).match(ruta_norm):
                return True
            continue
        if ruta_norm == entrada_norm or ruta_norm.startswith(entrada_norm + "/"):
            return True
    return False


def _validar_manifest_en_memoria(manifest_str: str) -> Tuple[bool, str]:
    """Adaptación EN MEMORIA (sin `Path.resolve()`, sin tocar el disco) de
    `_validar_manifest` (`hook_validar_comando.py:72-110`): mismo criterio de
    rechazo de absoluta/traversal ANTES de partir la ruta, y misma exigencia
    de contención bajo `openspec/changes/<id>/runs/<run-id>.json` — sin la
    verificación adicional de que el archivo exista de verdad en el
    filesystem (esta función es pura, esa verificación no aplica acá)."""
    if _es_ruta_absoluta(manifest_str):
        return False, "Comando rechazado: ruta de manifest absoluta no permitida."

    if _tiene_traversal(manifest_str):
        return False, "Comando rechazado: traversal detectado en la ruta del manifest."

    partes = re.split(r'[\\/]+', manifest_str)
    # openspec / changes / <id> / runs / <run-id>.json
    if (
        len(partes) != 5
        or partes[0] != "openspec"
        or partes[1] != "changes"
        or partes[2] == ""
        or partes[3] != "runs"
        or partes[4] == ""
        or not partes[4].endswith(".json")
    ):
        return (
            False,
            "Comando rechazado: el manifest debe estar bajo "
            "openspec/changes/<id>/runs/<run-id>.json.",
        )

    return True, "Manifest dentro de la raíz autorizada."


# ---------------------------------------------------------------------------
# Reconocimiento de las 5 formas (R8)
# ---------------------------------------------------------------------------


def _evaluar_forma_script(argv: Tuple[str, ...], alcance: Tuple[str, ...]) -> Tuple[bool, str]:
    if len(argv) < 2:
        return False, "falta la ruta del script"
    ruta = argv[1]
    if not ruta.endswith(".py"):
        return False, f"{ruta!r} no tiene extensión .py"
    if _es_ruta_absoluta(ruta):
        return False, "ruta de script absoluta no permitida"
    if _tiene_traversal(ruta):
        return False, "traversal detectado en la ruta del script"
    if not _coincide_alcance(ruta, alcance):
        return False, f"{ruta!r} fuera del alcance autorizado"
    return True, ""


def _evaluar_forma_pytest(argv: Tuple[str, ...], alcance: Tuple[str, ...]) -> Tuple[bool, str]:
    """`-m pytest <rutas...> [flags/valores]` — cada token que matchea una
    ruta de `alcance` cuenta como ruta; cualquier otro token debe matchear la
    clase de caracteres básica de flag (`_PATRON_FLAG`, incluye los valores
    de flags como `-k EXPR` que no empiezan con `-`, p. ej. spec.md R8: caso
    `["-k", "test_algo"]`). Rutas absolutas o con traversal se rechazan
    EXPLÍCITAMENTE antes de intentar la clase de flag (para que una ruta
    maliciosa disfrazada de "flag" no se cuele solo por matchear la clase de
    caracteres, que sí admite `/`)."""
    if len(argv) < 3 or argv[1] != "-m" or argv[2] != "pytest":
        return False, "no matchea '-m pytest'"
    resto = argv[3:]
    if not resto:
        return False, "falta al menos una ruta de test"
    hay_ruta = False
    for token in resto:
        if _es_ruta_absoluta(token):
            return False, f"{token!r}: ruta absoluta no permitida"
        if _tiene_traversal(token):
            return False, f"{token!r}: traversal detectado"
        if _coincide_alcance(token, alcance):
            hay_ruta = True
            continue
        if not _PATRON_FLAG.match(token):
            return False, f"{token!r} no es una ruta dentro del alcance ni un flag/valor válido"
    if not hay_ruta:
        return False, "no se encontró ninguna ruta dentro del alcance"
    return True, ""


def _evaluar_forma_notebook(texto_resto: str) -> Tuple[bool, str]:
    match = _PATRON_COMANDO_NOTEBOOK_RESTO.match(texto_resto)
    if not match:
        return (
            False,
            "no matchea el template exacto de "
            "'tools/notebook_runner.py run --manifest <ruta> [--dry-run|--execute]'",
        )
    return _validar_manifest_en_memoria(match.group("manifest"))


def _evaluar_forma_cli_diagnostic(argv: Tuple[str, ...]) -> Tuple[bool, str]:
    if len(argv) >= 2 and argv[1] == "tools/ds_guard.py":
        return True, ""
    if len(argv) >= 3 and argv[1] == "-m" and argv[2] in ("tools.ds_profile", "tools.harmessi"):
        return True, ""
    return False, "no matchea ninguna variante de cli_diagnostic"


_PATRON_DEPENDENCY_INSTALL_SPEC = re.compile(r'^[^=\s]+==[^=\s]+$')


def _evaluar_forma_dependency_install(argv: Tuple[str, ...]) -> Tuple[bool, str]:
    """`-m pip install --no-deps <nombre>==<versión>` -- patrón CERRADO de 6
    tokens totales (argv[0] es el intérprete, ya validado aparte por
    `evaluar_comando`). Esta función solo reconoce la FORMA sintáctica (un
    único token final con la forma 'algo==algo', sin espacios): la validación
    semántica real de nombre/versión (PEP 503, rango aprobado) vive en
    `tools/dsguard/sdd.py`/`tools/ds_guard.py`, ANTES de que el comando
    llegue acá (R25 de spec.md) -- mismo principio ya establecido por R9 de
    Change 2 ('allowlist.py no decide autorización semántica'). El patrón
    cerrado de 6 tokens y comparación LITERAL (no un regex laxo sobre todo
    el comando) es la defensa: ningún flag extra, ninguna ruta, ningún
    segundo paquete puede colarse sin agregar o cambiar un token, lo que
    rompe la longitud exacta o la comparación literal de abajo."""
    if len(argv) != 6:
        return False, "se esperaban exactamente 6 tokens (intérprete -m pip install --no-deps <nombre>==<versión>)"
    if tuple(argv[1:5]) != ("-m", "pip", "install", "--no-deps"):
        return False, "no matchea '-m pip install --no-deps'"
    spec = argv[5]
    if not _PATRON_DEPENDENCY_INSTALL_SPEC.match(spec):
        return False, f"{spec!r} no matchea el patrón <nombre>==<versión> (un solo '==', sin espacios)"
    return True, ""


# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------


def evaluar_comando(
    argv_o_texto: Union[Tuple[str, ...], list, str],
    alcance: Tuple[str, ...],
    interprete_autorizado: str,
) -> Tuple[bool, Optional[str], str]:
    """Reconoce la FORMA de un comando (R8). Función pura: el mismo
    `(argv_o_texto, alcance, interprete_autorizado)` da siempre el mismo
    resultado, sin I/O, sin consultar `tools.autonomy` ni `control.json`
    (R9) — ni siquiera sabe que ese concepto existe.

    Acepta `argv_o_texto` como `list[str]`/`tuple[str, ...]` (preferido) o
    como un único string `'"<interprete>" resto del comando'` (paridad con
    `hook_validar_comando.py`; ver limitación de parseo documentada arriba
    en `_PATRON_TEXTO`).

    Orden de verificación:
    1. Metacaracteres de encadenamiento prohibidos (`core.
       contiene_metacaracter_prohibido`) — en cualquier elemento de `argv`,
       o en el texto completo si viene como string. Si hay alguno,
       `(False, None, motivo)` inmediato, sin evaluar formas.
    2. Intérprete: normalizado con `normalizar_interprete` (réplica literal
       de `hook_validar_comando.py:46-51`) y comparado por igualdad exacta
       contra `interprete_autorizado` (que el llamador ya entrega
       normalizado, spec.md R8). Si no coincide, rechazo inmediato.
    3. Las 5 formas, en orden (a) script, (b) pytest, (c) notebook,
       (d) cli_diagnostic, (e) dependency_install — la primera que matchea
       gana.
    """
    if isinstance(argv_o_texto, str):
        if core.contiene_metacaracter_prohibido(argv_o_texto):
            return False, None, "el comando contiene un metacarácter de encadenamiento prohibido"
        match = _PATRON_TEXTO.match(argv_o_texto)
        if not match:
            return (
                False,
                None,
                'no se pudo interpretar el texto: se esperaba \'"<interprete>" resto del comando\'',
            )
        interprete_bruto = match.group("interprete")
        resto = match.group("resto").strip()
        resto_tokens = tuple(resto.split()) if resto else ()
        argv: Tuple[str, ...] = (interprete_bruto,) + resto_tokens
        texto_resto = resto
    elif isinstance(argv_o_texto, (list, tuple)):
        if len(argv_o_texto) == 0:
            return False, None, "argv vacío"
        for i, item in enumerate(argv_o_texto):
            if not isinstance(item, str):
                return False, None, f"argv[{i}] no es str"
            if core.contiene_metacaracter_prohibido(item):
                return (
                    False,
                    None,
                    f"argv[{i}] contiene un metacarácter de encadenamiento prohibido",
                )
        argv = tuple(argv_o_texto)
        interprete_bruto = argv[0]
        texto_resto = " ".join(argv[1:])
    else:
        return False, None, f"tipo de argv_o_texto no soportado: {type(argv_o_texto).__name__}"

    # R18: comparación simétrica -- se normalizan AMBOS lados, así que el
    # llamador puede entregar el intérprete autorizado en cualquier forma
    # (case/separadores) sin cambiar el resultado.
    interprete_normalizado = normalizar_interprete(interprete_bruto)
    if not isinstance(interprete_autorizado, str) or not interprete_autorizado:
        return False, None, "intérprete no autorizado"
    interprete_autorizado = normalizar_interprete(interprete_autorizado)
    if interprete_normalizado != interprete_autorizado:
        return False, None, "intérprete no autorizado"

    motivos = []

    ok, motivo = _evaluar_forma_script(argv, alcance)
    if ok:
        return True, "script", ""
    motivos.append(f"script: {motivo}")

    ok, motivo = _evaluar_forma_pytest(argv, alcance)
    if ok:
        return True, "pytest", ""
    motivos.append(f"pytest: {motivo}")

    ok, motivo = _evaluar_forma_notebook(texto_resto)
    if ok:
        return True, "notebook", ""
    motivos.append(f"notebook: {motivo}")

    ok, motivo = _evaluar_forma_cli_diagnostic(argv)
    if ok:
        return True, "cli_diagnostic", ""
    motivos.append(f"cli_diagnostic: {motivo}")

    ok, motivo = _evaluar_forma_dependency_install(argv)
    if ok:
        return True, "dependency_install", ""
    motivos.append(f"dependency_install: {motivo}")

    return False, None, "ninguna forma reconocida — " + "; ".join(motivos)
