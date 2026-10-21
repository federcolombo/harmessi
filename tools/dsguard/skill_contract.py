"""Validador estructural puro del contrato de skill componible
(Change 20261014-composable-skills-writer-semantics, R2/R3/R6/R7/R27).

Una skill componible es un `.md` en `.claude/skills/lead-data-scientist/skills/<name>.md`
con frontmatter de lista CERRADA (ver `CLAVES_*`). Este módulo solo valida
estructura: no evalúa calidad metodológica, no hace red y no escribe nada.
Solo stdlib; el parser de frontmatter es un subset propio de YAML (líneas
`clave: valor` y listas inline `[a, b]`). Neutral respecto de proveedores.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import sys

from .core import Finding


def _sdd():
    """Import perezoso de `sdd` (requiere `tools/` en sys.path por sus imports)."""
    try:
        from . import sdd
    except ModuleNotFoundError:
        raiz_tools = str(Path(__file__).resolve().parents[1])
        if raiz_tools not in sys.path:
            sys.path.insert(0, raiz_tools)
        from . import sdd
    return sdd


CLAVES_OBLIGATORIAS = ("name", "purpose", "when_to_load", "roles")
CLAVES_OPCIONALES = ("artifacts",)
CLAVES_PROHIBIDAS = (
    "tools",
    "allowed-tools",
    "permissions",
    "hooks",
    "model",
    "maxTurns",
    "install",
    "dependencies",
    "requires",
    "priority",
    "autonomy",
    "description",
)

ROL_LEAD = "lead-data-scientist"
DIR_SKILLS = ".claude/skills/lead-data-scientist/skills"
DIR_AGENTES = ".claude/agents"
ENCABEZADO_REFERENCIAS = "## Skills cargados"

SUPERFICIE_PROTEGIDA = "protected"
SUPERFICIE_OPTIMIZABLE = "optimizable"
SUPERFICIE_PROYECTO = "project-owned"

_DIR_SKILL_LEAD = (".claude", "skills", "lead-data-scientist")
_OPTIMIZABLES_LEAD = frozenset({"methodology.md", "eda.md", "kdd.md"})
_RAICES_PROTEGIDAS = frozenset({".claude", "tools", ".ds_init", ".harmessi"})
_ARCHIVOS_CHANGE_PROTEGIDOS = frozenset({"control.json", "amendments.jsonl"})

_RE_NOMBRE = re.compile(r"^[a-z][a-z0-9-]*$")
_RE_CLAVE_VALOR = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$")
_MARCADORES_SIN_SKILL = frozenset({"ninguna", "ninguno", "n/a", "na", "-"})
_RE_SEPARADOR_REFERENCIA = re.compile(r"\s*—\s*|\s+-\s+")


# --- Parser de frontmatter -------------------------------------------------------

def _quitar_comillas(valor: str) -> str:
    valor = valor.strip()
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in ("'", '"'):
        return valor[1:-1].strip()
    return valor


def _partir_lista(interior: str) -> list:
    """Parte `a, 'b, c', "d"` por comas respetando comillas simples/dobles."""
    elementos: list = []
    actual: list = []
    comilla: Optional[str] = None
    for car in interior:
        if comilla:
            actual.append(car)
            if car == comilla:
                comilla = None
        elif car in ("'", '"'):
            comilla = car
            actual.append(car)
        elif car == ",":
            elementos.append("".join(actual))
            actual = []
        else:
            actual.append(car)
    elementos.append("".join(actual))
    elementos = [_quitar_comillas(e) for e in elementos]
    if len(elementos) == 1 and elementos[0] == "":
        return []
    return elementos


def _parsear_valor(crudo: str):
    valor = crudo.strip()
    if valor.startswith("[") and valor.endswith("]"):
        return _partir_lista(valor[1:-1])
    return _quitar_comillas(valor)


def parsear_frontmatter(texto: str) -> tuple:
    """Devuelve `(dict | None, list[Finding])`. `None` si no hay frontmatter
    (bloque entre dos líneas `---` al inicio del archivo). Tolera BOM y CRLF.
    Valores: `str` o `list[str]` (listas inline)."""
    if texto.startswith("﻿"):
        texto = texto[1:]
    lineas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lineas or lineas[0].rstrip() != "---":
        return None, [Finding(
            "SKILL-FRONTMATTER-AUSENTE",
            "el archivo no empieza con un bloque de frontmatter delimitado por líneas '---'",
        )]
    cierre = None
    for i in range(1, len(lineas)):
        if lineas[i].rstrip() == "---":
            cierre = i
            break
    if cierre is None:
        return None, [Finding(
            "SKILL-FRONTMATTER-AUSENTE",
            "el frontmatter no tiene línea de cierre '---'",
        )]

    datos: dict = {}
    hallazgos: list = []
    for numero, linea in enumerate(lineas[1:cierre], start=2):
        if not linea.strip() or linea.lstrip().startswith("#"):
            continue
        m = _RE_CLAVE_VALOR.match(linea)
        if not m:
            hallazgos.append(Finding(
                "SKILL-CAMPO-NO-PERMITIDO",
                f"línea {numero} del frontmatter no tiene forma 'clave: valor' "
                f"(solo se admite el subset plano; sin anidación): {linea.strip()!r}",
            ))
            continue
        clave, valor = m.group(1), m.group(2)
        if clave in datos:
            hallazgos.append(Finding(
                "SKILL-CAMPO-NO-PERMITIDO",
                f"clave duplicada en el frontmatter: '{clave}'",
            ))
            continue
        datos[clave] = _parsear_valor(valor)
    return datos, hallazgos


# --- Roles y skills existentes ---------------------------------------------------

def _leer_texto(ruta: Path) -> Optional[str]:
    try:
        return ruta.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def roles_conocidos(repo_root: Path) -> set:
    """`lead-data-scientist` + el `name` del frontmatter de cada `.claude/agents/*.md`."""
    roles = {ROL_LEAD}
    directorio = Path(repo_root) / DIR_AGENTES
    if not directorio.is_dir():
        return roles
    for archivo in sorted(directorio.glob("*.md")):
        texto = _leer_texto(archivo)
        if texto is None:
            continue
        datos, _ = parsear_frontmatter(texto)
        if datos and isinstance(datos.get("name"), str) and datos["name"]:
            roles.add(datos["name"])
    return roles


def skills_existentes(repo_root: Path) -> set:
    directorio = Path(repo_root) / DIR_SKILLS
    if not directorio.is_dir():
        return set()
    return {p.stem for p in directorio.glob("*.md") if p.is_file()}


# --- Superficies del harness -----------------------------------------------------

def superficie_de_ruta(ruta: str) -> str:
    """Superficie (`protected|optimizable|project-owned`) de una ruta repo-relativa.
    Pura: recorta espacios, normaliza `\\`→`/`, quita `./` y `/` final y compara sin
    distinguir mayúsculas. Fail-safe => protected: no-str, vacía, absoluta (`/`, `\\`,
    letra de unidad o `:`), con `..`, con segmento terminado en `.` o espacio, o con
    comodines `*?[`. La clasificación es por ruta, no por contenido."""
    if not isinstance(ruta, str):
        return SUPERFICIE_PROTEGIDA
    texto = ruta.strip()
    if not texto or texto[0] in "/\\" or ":" in texto or any(c in texto for c in "*?["):
        return SUPERFICIE_PROTEGIDA
    crudas = texto.replace("\\", "/").casefold().split("/")
    if any(p not in ("", ".") and (p.endswith(".") or p != p.strip()) and p != ".." for p in crudas):
        return SUPERFICIE_PROTEGIDA
    partes = [p for p in crudas if p not in ("", ".")]
    if not partes or ".." in partes:
        return SUPERFICIE_PROTEGIDA
    base = _DIR_SKILL_LEAD
    if tuple(partes[:3]) == base:
        if len(partes) == 5 and partes[3] == "skills" and partes[4].endswith(".md"):
            return SUPERFICIE_OPTIMIZABLE
        if len(partes) == 4 and partes[3] in _OPTIMIZABLES_LEAD:
            return SUPERFICIE_OPTIMIZABLE
    if partes[0] in _RAICES_PROTEGIDAS:
        return SUPERFICIE_PROTEGIDA
    if (
        len(partes) >= 3
        and partes[0] == "openspec"
        and partes[1] == "changes"
        and partes[-1] in _ARCHIVOS_CHANGE_PROTEGIDOS
    ):
        return SUPERFICIE_PROTEGIDA
    return SUPERFICIE_PROYECTO


# --- Validación de una skill -----------------------------------------------------

def _linea_no_vacia(datos: dict, clave: str, ubic: str, hallazgos: list) -> None:
    if clave not in datos:
        hallazgos.append(Finding(
            "SKILL-CAMPO-FALTANTE", f"falta el campo obligatorio '{clave}'", ubic))
        return
    valor = datos[clave]
    if not isinstance(valor, str):
        hallazgos.append(Finding(
            "SKILL-CAMPO-FALTANTE",
            f"el campo '{clave}' debe ser una línea de texto, no una lista", ubic))
    elif not valor.strip():
        hallazgos.append(Finding(
            "SKILL-CAMPO-FALTANTE", f"el campo '{clave}' está vacío", ubic))


def _validar_artifacts(valor, ubic: str, hallazgos: list) -> None:
    if not isinstance(valor, list):
        hallazgos.append(Finding(
            "SKILL-CAMPO-NO-PERMITIDO",
            "el campo 'artifacts' debe ser una lista inline de rutas, p. ej. [a.md, dir/b.py]",
            ubic))
        return
    for crudo in valor:
        if any(c in crudo for c in "*?["):
            hallazgos.append(Finding(
                "SKILL-ARTIFACT-INVALIDO",
                f"artifact {crudo!r}: no se admiten comodines (rutas literales)", ubic))
            continue
        ruta, motivo = _sdd()._normalizar_entrada_alcance(crudo)
        if motivo:
            hallazgos.append(Finding(
                "SKILL-ARTIFACT-INVALIDO", f"artifact {crudo!r}: {motivo}", ubic))
        elif ruta is None or "*" in ruta:
            hallazgos.append(Finding(
                "SKILL-ARTIFACT-INVALIDO",
                f"artifact {crudo!r}: debe ser una ruta literal sin comodines", ubic))
        elif superficie_de_ruta(ruta) == SUPERFICIE_PROTEGIDA:
            hallazgos.append(Finding(
                "SKILL-ARTIFACT-SUPERFICIE-PROTEGIDA",
                f"artifact {crudo!r} apunta a la superficie protegida del harness: no declarar "
                "artefactos de enforcement/gobernanza ni de estado de Changes, ni para leer ni "
                "para escribir; quitalo de 'artifacts' o usá un artefacto del proyecto", ubic))


def validar_skill(ruta: Path, roles: set, ubicacion: Optional[str] = None) -> list:
    """Valida un archivo de skill. `ubicacion` por defecto = `ruta` con '/'."""
    ruta = Path(ruta)
    ubic = ubicacion if ubicacion is not None else ruta.as_posix()
    texto = _leer_texto(ruta)
    if texto is None:
        return [Finding("SKILL-FRONTMATTER-AUSENTE", "archivo ilegible (no es UTF-8 o no existe)", ubic)]

    datos, hallazgos = parsear_frontmatter(texto)
    hallazgos = [Finding(f.codigo, f.mensaje, ubic) for f in hallazgos]
    if datos is None:
        return hallazgos

    # Claves fuera de la lista cerrada
    permitidas = set(CLAVES_OBLIGATORIAS) | set(CLAVES_OPCIONALES)
    for clave in datos:
        if clave in permitidas:
            continue
        if clave in CLAVES_PROHIBIDAS:
            msg = (f"la clave '{clave}' está prohibida: una skill es guidance, no concede "
                   "permisos, herramientas, hooks, modelo, instalación ni autonomía")
        else:
            msg = f"clave desconocida '{clave}': el frontmatter admite solo una lista cerrada"
        hallazgos.append(Finding("SKILL-CAMPO-NO-PERMITIDO", msg, ubic))

    # name
    if "name" not in datos:
        hallazgos.append(Finding("SKILL-CAMPO-FALTANTE", "falta el campo obligatorio 'name'", ubic))
    else:
        nombre = datos["name"]
        if not isinstance(nombre, str) or not nombre:
            hallazgos.append(Finding(
                "SKILL-NOMBRE-INVALIDO", "'name' debe ser un texto no vacío", ubic))
        elif not _RE_NOMBRE.match(nombre):
            hallazgos.append(Finding(
                "SKILL-NOMBRE-INVALIDO",
                f"name {nombre!r} no es kebab-case (^[a-z][a-z0-9-]*$)", ubic))
        elif nombre != ruta.stem:
            hallazgos.append(Finding(
                "SKILL-NOMBRE-INVALIDO",
                f"name {nombre!r} no coincide con el nombre de archivo {ruta.stem!r}", ubic))

    _linea_no_vacia(datos, "purpose", ubic, hallazgos)
    _linea_no_vacia(datos, "when_to_load", ubic, hallazgos)

    # roles
    if "roles" not in datos:
        hallazgos.append(Finding("SKILL-CAMPO-FALTANTE", "falta el campo obligatorio 'roles'", ubic))
    elif not isinstance(datos["roles"], list):
        hallazgos.append(Finding(
            "SKILL-CAMPO-FALTANTE",
            "'roles' debe ser una lista inline no vacía, p. ej. [lead-data-scientist]", ubic))
    elif not datos["roles"]:
        hallazgos.append(Finding("SKILL-CAMPO-FALTANTE", "'roles' no puede estar vacía", ubic))
    else:
        for rol in datos["roles"]:
            if rol not in roles:
                hallazgos.append(Finding(
                    "SKILL-ROL-DESCONOCIDO",
                    f"rol desconocido {rol!r}; conocidos: {', '.join(sorted(roles))}", ubic))

    if "artifacts" in datos:
        _validar_artifacts(datos["artifacts"], ubic, hallazgos)

    return hallazgos


def validar_directorio_skills(repo_root: Path) -> list:
    """Valida `.claude/skills/lead-data-scientist/skills/*.md`. Directorio ausente => []."""
    repo_root = Path(repo_root)
    directorio = repo_root / DIR_SKILLS
    if not directorio.is_dir():
        return []
    roles = roles_conocidos(repo_root)
    hallazgos: list = []
    for archivo in sorted(directorio.glob("*.md")):
        if not archivo.is_file():
            continue
        relativa = f"{DIR_SKILLS}/{archivo.name}"
        hallazgos.extend(validar_skill(archivo, roles, ubicacion=relativa))
    return hallazgos


# --- Traza `## Skills cargados` de tasks.md --------------------------------------

def referencias_skills_cargados(texto_tasks: str) -> list:
    """Nombres de skill de los bullets `- <skill> — <tarea> — <motivo>` bajo
    `## Skills cargados` (separador `—` o ` - `). Ignora comentarios HTML, líneas
    no-bullet y marcadores de plantilla `<...>`. Sin duplicados, en orden."""
    seccion = _sdd()._contenido_de_seccion(texto_tasks, ENCABEZADO_REFERENCIAS)
    nombres: list = []
    for linea in seccion.splitlines():
        linea = linea.strip()
        if not (linea.startswith("- ") or linea.startswith("* ")):
            continue
        cuerpo = linea[2:].strip()
        if not cuerpo:
            continue
        nombre = _RE_SEPARADOR_REFERENCIA.split(cuerpo, maxsplit=1)[0].strip().strip("`").strip()
        if not nombre or (nombre.startswith("<") and nombre.endswith(">")):
            continue
        sin_ticks = cuerpo.replace("`", "").strip().casefold()
        primer_token = re.split(r"[\s,;:.–—]+", sin_ticks.lstrip(), maxsplit=1)[0]
        if (
            sin_ticks.startswith("(")
            or nombre.casefold() in _MARCADORES_SIN_SKILL
            or primer_token in _MARCADORES_SIN_SKILL
        ):
            continue
        if nombre not in nombres:
            nombres.append(nombre)
    return nombres


def validar_referencias_skills(texto_tasks: str, existentes: set) -> list:
    """`SKILL-REFERENCIA-DESCONOCIDA` por cada skill citada que no existe. Sección
    ausente o vacía => []."""
    return [
        Finding(
            "SKILL-REFERENCIA-DESCONOCIDA",
            f"la skill citada {nombre!r} en '## Skills cargados' no existe en {DIR_SKILLS}/",
            "tasks.md",
        )
        for nombre in referencias_skills_cargados(texto_tasks)
        if nombre not in existentes
    ]
