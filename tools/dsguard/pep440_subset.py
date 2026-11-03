"""PEP 440 subset supported by Harmessi (solo stdlib; no es PEP 440 completo).

Se usa para clasificar dependencias pre-aprobadas (`sdd.py`, M11) sin agregar
una dependencia como `packaging`.

Subset SOPORTADO
----------------
* Versión: `N(.N)*` seguida, opcionalmente y EN ESTE ORDEN, de `(a|b|rc)N`,
  `.postN` y `.devN` (`1.0`, `1.0a1`, `1.0b2`, `1.0rc1`, `1.0.post1`,
  `1.0.dev1`, `1.0rc1.dev2`, `1.0.post1.dev3`). Todo número es entero decimal
  ASCII.
* Segmento local `+<alfanumérico>(.|-|_ <alfanumérico>)*` SOLO en la versión
  instalada/consultada (`parse_version(..., permitir_local=True)`, usado por
  `satisfies`); se ignora al comparar. Nunca en los rangos.
* Normalización: minúsculas y espacios exteriores recortados.
* Rangos: operadores `>=`, `<=`, `>`, `<`, `==`, `!=` separados por coma
  (`>=1.2,<2`).
* Ordering semántico (nunca lexicográfico): `1.0.dev1 < 1.0a1 < 1.0b1 <
  1.0rc1 < 1.0 < 1.0.post1`; `1.0rc1.dev1 < 1.0rc1`; `1.0 == 1.0.0`;
  `1.0.post1.dev1 < 1.0.post1`; `2.9.0.post0 < 2.9.1.dev0`.

NO soportado (fail-closed: `ValueError` con mensaje claro)
----------------------------------------------------------
Epochs (`1!2.0`), wildcards (`==1.*`), `~=`, `===`, direct references
(`name @ url`), spellings alternativos (`alpha`, `beta`, `c`, `pre`,
`preview`, `rev`, `r`), separadores `-`/`_` en la parte de release/pre/post/dev,
pre/post/dev sin número (`1.0a`), versiones vacías o malformadas (`1..2`),
locales en rangos, marcadores de entorno y extras.

Límites exclusivos (reglas de PEP 440 que SÍ se implementan): `<V` NO admite un
pre-release (a/b/rc/dev) de la MISMA versión de release que V, salvo que V sea
pre-release (`<2` rechaza `2.0rc1` y `2.0.dev1`); `>V` NO admite un post-release
de la misma versión de release que V, salvo que V sea post-release (`>1`
rechaza `1.0.post1`). Es más estricto que el ordering puro: nunca aprueba de más.
Las demás reglas de PEP 440 sobre pre-releases (p. ej. que `>=1.0` no incluya
pre-releases de versiones posteriores salvo opt-in explícito) NO se implementan.
"""
from __future__ import annotations

import re
from functools import total_ordering

_RE_VERSION = re.compile(
    r"^(?P<release>[0-9]+(?:\.[0-9]+)*)"
    r"(?:(?P<pre>a|b|rc)(?P<pre_n>[0-9]+))?"
    r"(?:\.post(?P<post>[0-9]+))?"
    r"(?:\.dev(?P<dev>[0-9]+))?"
    r"(?:\+(?P<local>[a-z0-9]+(?:[._-][a-z0-9]+)*))?$",
    re.ASCII,
)

_RANGO_PRE = {"a": 0, "b": 1, "rc": 2}

# Mismo orden en que deben probarse (`>=`/`<=` antes que `>`/`<`).
_OPERADORES = (">=", "<=", "==", "!=", ">", "<")


def _diagnosticar(texto: str, permitir_local: bool) -> str:
    """Motivo claro de por qué `texto` (ya normalizado) está fuera del subset."""
    if not texto:
        return "version_vacia"
    if "@" in texto or "://" in texto:
        return f"direct_reference_no_soportada:{texto!r}"
    if "!" in texto:
        return f"epoch_no_soportado:{texto!r}"
    if "*" in texto:
        return f"wildcard_no_soportado:{texto!r}"
    if texto.startswith(("~", "=", "<", ">")):
        return f"operador_dentro_de_version:{texto!r}"
    if "+" in texto and not permitir_local:
        return f"local_no_permitido_en_rango:{texto!r}"
    if ".." in texto or texto.startswith(".") or texto.endswith("."):
        return f"componente_vacio:{texto!r}"
    base = texto.split("+", 1)[0]
    if "-" in base or "_" in base:
        return f"separador_no_soportado ('-'/'_'):{texto!r}"
    if re.search(r"(alpha|beta|preview|pre|rev|c|r)[0-9]*", re.sub(r"rc[0-9]*", "", base)):
        return f"spelling_alternativo_no_soportado:{texto!r}"
    if not re.match(r"^[0-9]", base):
        return f"componente_no_entero:{texto!r}"
    return f"fuera_del_subset_pep440:{texto!r}"


@total_ordering
class Version:
    """Versión del subset; ordenable. La comparación ignora el segmento local."""

    __slots__ = ("texto", "local", "clave")

    def __init__(self, texto: str, local, clave: tuple) -> None:
        self.texto = texto
        self.local = local
        self.clave = clave

    def __eq__(self, otra) -> bool:
        return isinstance(otra, Version) and self.clave == otra.clave

    def __lt__(self, otra) -> bool:
        if not isinstance(otra, Version):
            return NotImplemented
        return self.clave < otra.clave

    def __hash__(self) -> int:
        return hash(self.clave)

    def __repr__(self) -> str:
        return f"Version({self.texto!r})"


def parse_version(texto: str, permitir_local: bool = False) -> Version:
    """Parsea `texto` al subset. `ValueError` con motivo claro si no entra."""
    if not isinstance(texto, str):
        raise ValueError("version_no_es_texto")
    normal = texto.strip().lower()
    m = _RE_VERSION.match(normal)
    if m is None:
        raise ValueError(_diagnosticar(normal, permitir_local))
    local = m.group("local")
    if local is not None and not permitir_local:
        raise ValueError(f"local_no_permitido_en_rango:{normal!r}")

    release = [int(p) for p in m.group("release").split(".")]
    while len(release) > 1 and release[-1] == 0:  # 1.0 == 1.0.0
        release.pop()

    pre = (_RANGO_PRE[m.group("pre")], int(m.group("pre_n"))) if m.group("pre") else None
    post = int(m.group("post")) if m.group("post") is not None else None
    dev = int(m.group("dev")) if m.group("dev") is not None else None

    # Fase pre: dev sin pre ni post va antes de todo pre-release.
    if pre is None and post is None and dev is not None:
        clave_pre = (-1,)
    elif pre is None:
        clave_pre = (1,)
    else:
        clave_pre = (0, pre[0], pre[1])
    clave_post = (0,) if post is None else (1, post)
    clave_dev = (1,) if dev is None else (0, dev)
    return Version(normal, local, (tuple(release), clave_pre, clave_post, clave_dev))


def compare(a, b) -> int:
    """-1/0/1. Acepta `Version` o texto (sin local)."""
    va = a if isinstance(a, Version) else parse_version(a, permitir_local=True)
    vb = b if isinstance(b, Version) else parse_version(b, permitir_local=True)
    if va.clave < vb.clave:
        return -1
    if va.clave > vb.clave:
        return 1
    return 0


def parse_range(texto: str) -> list:
    """`">=1.2,<2"` -> `[(">=", Version), ("<", Version)]`. `ValueError` si el
    rango está vacío, algún término no tiene operador soportado o su versión
    queda fuera del subset (incluye locales)."""
    if not isinstance(texto, str):
        raise ValueError("rango_no_es_texto")
    texto = texto.strip()
    if not texto:
        raise ValueError("rango_vacio")
    terminos = []
    for termino in texto.split(","):
        termino = termino.strip()
        if not termino:
            raise ValueError("termino_vacio")
        if termino.startswith("==="):
            raise ValueError(f"operador_no_soportado ('==='):{termino!r}")
        if termino.startswith("~="):
            raise ValueError(f"operador_no_soportado ('~='):{termino!r}")
        operador = next((op for op in _OPERADORES if termino.startswith(op)), None)
        if operador is None:
            raise ValueError(f"operador_no_soportado:{termino!r}")
        terminos.append((operador, parse_version(termino[len(operador):], permitir_local=False)))
    return terminos


def _es_prerelease(v: Version) -> bool:
    """Tiene fase a/b/rc o dev (clave: `(release, pre, post, dev)`)."""
    return v.clave[1][0] == 0 or v.clave[3][0] == 0


def _es_postrelease(v: Version) -> bool:
    return v.clave[2][0] == 1


def satisfies(version: str, rango: str) -> bool:
    """`True` si `version` (puede llevar `+local`) cumple TODOS los términos de
    `rango`. Fail-closed: `False` (nunca lanza) ante cualquier `ValueError`."""
    try:
        v = parse_version(version, permitir_local=True)
        terminos = parse_range(rango)
    except (ValueError, TypeError, AttributeError):
        return False
    for operador, version_rango in terminos:
        cmp = compare(v, version_rango)
        if operador == ">=" and not cmp >= 0:
            return False
        if operador == "<=" and not cmp <= 0:
            return False
        if operador == ">" and not cmp > 0:
            return False
        if operador == "<" and not cmp < 0:
            return False
        # Exclusión de PEP 440 en límites exclusivos (misma versión de release).
        mismo_release = v.clave[0] == version_rango.clave[0]
        if operador == "<" and mismo_release and _es_prerelease(v) and not _es_prerelease(version_rango):
            return False
        if operador == ">" and mismo_release and _es_postrelease(v) and not _es_postrelease(version_rango):
            return False
        if operador == "==" and cmp != 0:
            return False
        if operador == "!=" and cmp == 0:
            return False
    return True
