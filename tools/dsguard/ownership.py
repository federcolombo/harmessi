"""Ownership de writers (Change 20261014-composable-skills-writer-semantics,
R10-R13, R16): parser y validador deterministas de la sección
`## Ownership de writers` de `tasks.md`.

Puro: sin I/O, sin red, sin dependencias fuera de la biblioteca estándar y del
propio paquete. Provider-neutral: trabaja con roles e instancias, nunca con
nombres de proveedor.

Gramática (markdown pequeño)::

    ## Ownership de writers
    ### <id> — <rol> — <tareas>
    - ruta/literal.py
    - directorio/**

El separador del encabezado es `—` o ` - `; `<tareas>` es opcional e
informativo. Cada entrada es una ruta repo-relativa con `/`: archivo exacto o
directorio terminado en `/**` (único comodín admitido, solo como sufijo). La
sección termina en el siguiente `## ` (nivel 2). Comentarios HTML, bloques de
código cercados con ``` y prosa se ignoran.

Una entrada literal que nombra un directorio (`tools/dsguard`, sin `/**`) NO se
interpreta como el directorio: es un archivo con ese nombre exacto. Para poseer
un directorio usar `dir/**`.

Fallo visible: un encabezado de sección con sufijo (`## Ownership de writers
(borrador)`) o duplicado produce OWNERSHIP-SECCION-ILEGIBLE; nunca se confunde
con una sección ausente.
"""
from __future__ import annotations

import fnmatch
import re
import sys
from dataclasses import dataclass, field
from typing import List, Tuple

from pathlib import Path

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


ROLES_WRITER = frozenset({"python-data-engineer"})

ENCABEZADO_SECCION = "## Ownership de writers"
UBICACION = "tasks.md#Ownership de writers"

_RE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_RE_SEPARADOR = re.compile(r"\s+(?:—|-)\s+")
_RE_ENCABEZADO_INSTANCIA = re.compile(r"^###(?!#)(.*)$")
_RE_BULLET = re.compile(r"^[-*]\s+(.*)$")
_SUFIJO_DIR = "/**"


@dataclass
class Instancia:
    """Una instancia writer con su ownership ya normalizado (sin entradas
    inválidas)."""

    id: str
    rol: str
    tareas: str = ""
    entradas: List[str] = field(default_factory=list)


def _es_dir(entrada: str) -> bool:
    return entrada.endswith(_SUFIJO_DIR)


def _normalizar_entrada(crudo: str) -> Tuple[str, str]:
    """`crudo` -> `(ruta_normalizada, motivo)`; `motivo` es None si es válida.
    Convierte `\\` a `/` antes de normalizar (para tratarlos como equivalentes)
    y restringe el comodín a la gramática de ownership."""
    valor = crudo.strip()
    if len(valor) >= 2 and valor.startswith("`") and valor.endswith("`"):
        valor = valor[1:-1].strip()
    valor = valor.replace("\\", "/")
    ruta, motivo = _sdd()._normalizar_entrada_alcance(valor)
    if motivo is not None:
        return None, motivo
    base = ruta[: -len(_SUFIJO_DIR)] if _es_dir(ruta) else ruta
    if "*" in base:
        return None, "comodín no permitido (solo '/**' como sufijo)"
    if not base:
        return None, "entrada vacía"
    return ruta, None


_RE_ENCABEZADO_SECCION = re.compile(r"^##\s+Ownership de writers\b(.*)$")
_RE_ENCABEZADO_NIVEL2 = re.compile(r"^##(?!#)\s")


_RE_ENCABEZADO_PARECIDO = re.compile(r"^##\s+ownership\s+de\s+writers?\b", re.IGNORECASE)


def _limpiar_texto(texto: str):
    """-> `(lineas, tragadas)`: líneas sin bloques ``` ni comentarios HTML (no
    cuentan) y, si una fence queda sin cerrar, las líneas originales que tragó."""
    originales = texto.splitlines()
    lineas = []
    en_codigo = False
    inicio_fence = 0
    for i, linea in enumerate(originales):
        if linea.strip().startswith("```"):
            en_codigo = not en_codigo
            if en_codigo:
                inicio_fence = i + 1
            lineas.append("")
            continue
        lineas.append("" if en_codigo else linea)
    tragadas = originales[inicio_fence:] if en_codigo else []
    sin_comentarios = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"),
                             "\n".join(lineas), flags=re.DOTALL)
    return sin_comentarios.split("\n"), tragadas


def _extraer_seccion(texto: str):
    """-> `(lineas | None, hallazgos)`. `None` = sección ausente (sin hallazgos)
    o inutilizable (duplicada o encabezado no canónico, ya reportado)."""
    lineas, tragadas = _limpiar_texto(texto)
    previos: List[Finding] = []
    for l in lineas:
        if _RE_ENCABEZADO_PARECIDO.match(l) and not _RE_ENCABEZADO_SECCION.match(l):
            previos.append(Finding(
                "OWNERSHIP-SECCION-ILEGIBLE",
                f"encabezado no canónico: '{l.strip()}' (esperado exactamente '{ENCABEZADO_SECCION}')",
                UBICACION,
            ))
    if any(_RE_ENCABEZADO_PARECIDO.match(l) for l in tragadas):
        previos.append(Finding(
            "OWNERSHIP-SECCION-ILEGIBLE",
            "bloque de código sin cerrar: tragó un encabezado de ownership",
            UBICACION,
        ))
    inicios = [i for i, l in enumerate(lineas) if _RE_ENCABEZADO_SECCION.match(l)]
    if not inicios:
        return None, previos
    if len(inicios) > 1:
        return None, previos + [Finding(
            "OWNERSHIP-SECCION-ILEGIBLE",
            f"sección duplicada: '{ENCABEZADO_SECCION}' aparece {len(inicios)} veces",
            UBICACION,
        )]
    hallazgos: List[Finding] = list(previos)
    inicio = inicios[0]
    sufijo = _RE_ENCABEZADO_SECCION.match(lineas[inicio]).group(1).strip()
    if sufijo:
        hallazgos.append(Finding(
            "OWNERSHIP-SECCION-ILEGIBLE",
            f"encabezado con sufijo: '{lineas[inicio].strip()}' (esperado exactamente '{ENCABEZADO_SECCION}')",
            UBICACION,
        ))
    cuerpo = []
    for linea in lineas[inicio + 1:]:
        if _RE_ENCABEZADO_NIVEL2.match(linea):
            break
        cuerpo.append(linea)
    return cuerpo, hallazgos


def parsear_ownership(texto_tasks: str) -> Tuple[List[Instancia], List[Finding]]:
    """Texto de `tasks.md` -> `(instancias, hallazgos)`. Sección ausente o vacía
    => `([], [])`. Reporta OWNERSHIP-SECCION-ILEGIBLE y
    OWNERSHIP-PATRON-INVALIDO; el resto de las reglas las aplica
    `validar_ownership`."""
    instancias: List[Instancia] = []
    hallazgos: List[Finding] = []
    lineas_seccion, hallazgos = _extraer_seccion(texto_tasks)
    if lineas_seccion is None:
        return instancias, hallazgos
    seccion = "\n".join(lineas_seccion)

    actual = None  # instancia en curso; None si el último encabezado fue ilegible
    en_bloque = False  # hubo algún encabezado `###` (legible o no)
    for linea in seccion.splitlines():
        texto = linea.strip()
        if not texto:
            continue
        m_enc = _RE_ENCABEZADO_INSTANCIA.match(texto)
        if m_enc:
            en_bloque = True
            partes = _RE_SEPARADOR.split(m_enc.group(1).strip(), maxsplit=2)
            if len(partes) < 2 or not _RE_ID.match(partes[0].strip()) or not partes[1].strip():
                hallazgos.append(Finding(
                    "OWNERSHIP-SECCION-ILEGIBLE",
                    f"encabezado malformado: '{texto}' (esperado: '### <id> — <rol> — <tareas>')",
                    UBICACION,
                ))
                actual = None
                continue
            actual = Instancia(
                id=partes[0].strip(),
                rol=partes[1].strip(),
                tareas=partes[2].strip() if len(partes) > 2 else "",
            )
            instancias.append(actual)
            continue
        m_bullet = _RE_BULLET.match(texto)
        if not m_bullet:
            continue  # prosa: se ignora
        crudo = m_bullet.group(1)
        if actual is None:
            if not en_bloque:
                hallazgos.append(Finding(
                    "OWNERSHIP-SECCION-ILEGIBLE",
                    f"entrada fuera de un encabezado '###': '{texto}'",
                    UBICACION,
                ))
            # tras un encabezado ilegible ya se informó el problema del bloque
            continue
        ruta, motivo = _normalizar_entrada(crudo)
        if motivo is not None:
            hallazgos.append(Finding(
                "OWNERSHIP-PATRON-INVALIDO",
                f"instancia '{actual.id}': entrada '{crudo.strip()}' inválida: {motivo}",
                UBICACION,
            ))
            continue
        if ruta not in actual.entradas:
            actual.entradas.append(ruta)
    return instancias, hallazgos


def entradas_solapan(a: str, b: str) -> bool:
    """¿Se solapan dos entradas ya normalizadas? Exacto con la gramática:
    literal==literal; literal dentro de `dir/**`; `a/**` vs `b/**` si son
    iguales o uno es prefijo de directorio del otro. Sin distinguir mayúsculas."""
    a = a.casefold()
    b = b.casefold()
    dir_a = a[: -len(_SUFIJO_DIR)] if _es_dir(a) else None
    dir_b = b[: -len(_SUFIJO_DIR)] if _es_dir(b) else None
    if dir_a is None and dir_b is None:
        return a == b
    if dir_a is not None and dir_b is None:
        return b.startswith(dir_a + "/")
    if dir_a is None and dir_b is not None:
        return a.startswith(dir_b + "/")
    return dir_a == dir_b or dir_a.startswith(dir_b + "/") or dir_b.startswith(dir_a + "/")


def entrada_cubierta(entrada: str, alcance: List[str]) -> bool:
    """¿La entrada normalizada está cubierta por el alcance efectivo?
    Literal: igualdad o `fnmatch` con algún patrón. `dir/**`: solo si existe un
    patrón `X/**` con `dir == X` o `dir` bajo `X` (un patrón literal nunca
    cubre un directorio completo)."""
    ent = entrada.casefold()
    patrones = [p.casefold() for p in alcance]
    if _es_dir(ent):
        directorio = ent[: -len(_SUFIJO_DIR)]
        for p in patrones:
            if _es_dir(p):
                x = p[: -len(_SUFIJO_DIR)]
                if directorio == x or directorio.startswith(x + "/"):
                    return True
        return False
    return any(p == ent or fnmatch.fnmatchcase(ent, p) for p in patrones)


def validar_ownership(instancias: List[Instancia], alcance_rutas: List[str]) -> List[Finding]:
    """Reglas semánticas sobre instancias ya parseadas: id duplicado, rol
    inválido, instancia vacía, solapes entre instancias y entradas fuera del
    alcance efectivo. Dos entradas de la MISMA instancia que solapan no son error."""
    hallazgos: List[Finding] = []
    vistos = {}
    for inst in instancias:
        clave = inst.id.casefold()
        if clave in vistos:
            hallazgos.append(Finding(
                "OWNERSHIP-ID-DUPLICADO",
                f"el id de instancia '{inst.id}' está repetido",
                UBICACION,
            ))
        vistos[clave] = True
        if inst.rol not in ROLES_WRITER:
            hallazgos.append(Finding(
                "OWNERSHIP-ROL-INVALIDO",
                f"instancia '{inst.id}': rol '{inst.rol}' no es un rol writer "
                f"({', '.join(sorted(ROLES_WRITER))})",
                UBICACION,
            ))
        if not inst.entradas:
            hallazgos.append(Finding(
                "OWNERSHIP-VACIO",
                f"instancia '{inst.id}' sin entradas válidas de ownership",
                UBICACION,
            ))

    for i, inst_a in enumerate(instancias):
        for inst_b in instancias[i + 1:]:
            for ea in inst_a.entradas:
                for eb in inst_b.entradas:
                    if entradas_solapan(ea, eb):
                        hallazgos.append(Finding(
                            "OWNERSHIP-SOLAPADO",
                            f"las instancias '{inst_a.id}' ('{ea}') y '{inst_b.id}' ('{eb}') se solapan",
                            UBICACION,
                        ))

    for inst in instancias:
        for entrada in inst.entradas:
            if not entrada_cubierta(entrada, alcance_rutas):
                hallazgos.append(Finding(
                    "OWNERSHIP-FUERA-DE-ALCANCE",
                    f"instancia '{inst.id}': '{entrada}' no está cubierta por el alcance efectivo",
                    UBICACION,
                ))
    return hallazgos


def evaluar_ownership(texto_tasks: str, alcance_rutas: List[str]) -> List[Finding]:
    """Parsea y valida. Sin sección `## Ownership de writers` => `[]`."""
    instancias, hallazgos = parsear_ownership(texto_tasks)
    if not instancias and not hallazgos:
        return []
    return hallazgos + validar_ownership(instancias, alcance_rutas)
