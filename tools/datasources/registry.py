"""Validación estática y pura del registro `.harmessi/sources.json` (R12-R14).

Puro sobre dicts: sin I/O directo. `resolve_observer_file` recibe `exists_fn`
INYECTADO (nunca usa `Path`/`os`): el I/O real lo hace `runtime.py` (fuera de
este Change), pasando un `exists_fn` real; los tests de este paquete pasan un
`exists_fn` fake (p. ej. un `set`/`dict` de rutas "existentes").
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

from . import scan
from .core import (
    CODE_ID_DUPLICATE,
    CODE_OBSERVER_UNRESOLVED,
    CODE_REGISTRY_INVALID,
    validate_source_ref,
)

SCHEMA_VERSION = 1

# Forma mínima de un `callable` de observer (segundo tramo de
# `módulo:callable`): identificador simple, sin `.`/`:`/separadores.
_RE_CALLABLE_SIMPLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def validate_registry(data: Any) -> list:
    """Validación estructural y semántica PURA del registro completo:
    `{"schema_version": 1, "sources": [SourceRef-dict, ...]}`. Devuelve
    `[(code, path, motivo), ...]`; nunca lanza. Ids únicos y canónicos,
    campos de cada `SourceRef` (R4, vía `core.validate_source_ref`), y scan
    de secretos/localizadores (R19) sobre cada entrada completa (`options`
    incluido)."""
    hallazgos: list = []

    if not isinstance(data, dict):
        return [(CODE_REGISTRY_INVALID, "$", f"se esperaba dict, se recibió {type(data).__name__}")]

    if data.get("schema_version") != SCHEMA_VERSION:
        hallazgos.append(
            (CODE_REGISTRY_INVALID, "$.schema_version", f"se esperaba {SCHEMA_VERSION}, se recibió {data.get('schema_version')!r}")
        )

    fuentes = data.get("sources")
    if not isinstance(fuentes, list):
        hallazgos.append((CODE_REGISTRY_INVALID, "$.sources", f"se esperaba list, se recibió {type(fuentes).__name__}"))
        return hallazgos

    ids_vistos: dict = {}
    for i, entrada in enumerate(fuentes):
        ruta_base = f"$.sources[{i}]"
        hallazgos_entrada = validate_source_ref(entrada)
        for code, path, motivo in hallazgos_entrada:
            sub_path = path[1:] if path.startswith("$") else path
            hallazgos.append((code, f"{ruta_base}{sub_path}", motivo))

        if isinstance(entrada, dict):
            source_id = entrada.get("source_id")
            if isinstance(source_id, str):
                if source_id in ids_vistos:
                    hallazgos.append(
                        (CODE_ID_DUPLICATE, f"{ruta_base}.source_id", f"source_id duplicado {source_id!r}")
                    )
                else:
                    ids_vistos[source_id] = i

            # Scan de secretos/localizadores (R19) sobre la entrada completa.
            for code, pointer, motivo in scan.scan_secrets(entrada, ruta_base):
                hallazgos.append((code, pointer, motivo))
            for code, pointer, motivo in scan.scan_locators(entrada, ruta_base):
                hallazgos.append((code, pointer, motivo))

    return hallazgos


def resolve_observer_file(
    repo_root_marker: Any,
    observer_ref: str,
    exists_fn: Callable[[str], bool],
) -> Optional[str]:
    """Dado `observer_ref = "a.b.c:factory"`, prueba las rutas candidatas
    `a/b/c.py` y `a/b/c/__init__.py` (relativas al repo) llamando a
    `exists_fn(ruta_relativa)`; devuelve la primera que exista o `None`.

    PURO: no importa el módulo ni toca el sistema de archivos directamente
    (eso es responsabilidad de `runtime.py`, que construye `exists_fn` a
    partir de `Path(repo_root)`). `repo_root_marker` no se usa para I/O aquí;
    se acepta por firma para que el llamador pueda pasar el mismo valor que
    usa para construir `exists_fn` (informativo, ignorado en este módulo).

    Rechaza (devuelve `None` sin llamar a `exists_fn`) si `observer_ref` no
    tiene la forma `módulo:callable`, o si algún componente del módulo es
    vacío, `..`, o si el módulo completo pretende ser una ruta absoluta
    (empieza con `/` o con `letra:`)."""
    if not isinstance(observer_ref, str) or ":" not in observer_ref:
        return None
    modulo, _, _callable = observer_ref.partition(":")
    if modulo == "" or _callable == "":
        return None
    # `_callable` debe ser un identificador simple (sin `.`/`:`/separadores):
    # un `observer_ref` con más de un `:` (p. ej. `"C:.observers:factory"`,
    # donde `partition` corta en el primer `:` y deja un resto ambiguo con
    # una unidad de disco Windows) no tiene la forma `módulo:callable` y se
    # rechaza sin generar candidatos ni llamar a `exists_fn`.
    if _RE_CALLABLE_SIMPLE.fullmatch(_callable) is None:
        return None
    if modulo.startswith("/") or modulo.startswith("\\"):
        return None
    if len(modulo) >= 2 and modulo[1] == ":" and modulo[0].isalpha():
        return None
    componentes = modulo.split(".")
    for comp in componentes:
        if comp == "" or comp == "..":
            return None

    base = "/".join(componentes)
    candidatas = (f"{base}.py", f"{base}/__init__.py")
    for candidata in candidatas:
        if exists_fn(candidata):
            return candidata
    return None


def check_registry_static(data: Any, exists_fn: Callable[[str], bool]) -> list:
    """Compone `validate_registry` con la resolución estática del `observer`
    de cada entrada válida: si no resuelve, agrega un hallazgo WARN
    `SOURCE-OBSERVER-UNRESOLVED` (nunca error fatal: el paquete puede estar
    instalado en el `.venv`, D7)."""
    hallazgos = list(validate_registry(data))

    if not isinstance(data, dict):
        return hallazgos
    fuentes = data.get("sources")
    if not isinstance(fuentes, list):
        return hallazgos

    for i, entrada in enumerate(fuentes):
        if not isinstance(entrada, dict):
            continue
        observer_ref = entrada.get("observer")
        if not isinstance(observer_ref, str):
            continue
        # Solo se intenta resolver si el observer ya pasó su propia
        # validación de forma (si no, ya hay un SOURCE-OBSERVER-MALFORMED).
        ruta_base = f"$.sources[{i}]"
        ya_malformado = any(
            code == "SOURCE-OBSERVER-MALFORMED" and path == f"{ruta_base}.observer"
            for code, path, _ in hallazgos
        )
        if ya_malformado:
            continue
        resuelto = resolve_observer_file(None, observer_ref, exists_fn)
        if resuelto is None:
            hallazgos.append(
                (CODE_OBSERVER_UNRESOLVED, f"{ruta_base}.observer", f"no se pudo resolver {observer_ref!r} como archivo del repo")
            )

    return hallazgos
