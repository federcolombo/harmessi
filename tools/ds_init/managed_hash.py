"""Primitive única de hash de archivos administrados (managed) por Harmessi.

Resuelve los falsos `HARMESSI-DRIFT` por diferencias de fin de línea (LF/CRLF)
entre plataformas. Solo stdlib; lectura en streaming por bloques (nunca carga
el archivo completo en memoria) y sin comportamiento específico de OS.

Algoritmos:
- `sha256/eol-lf/v1` (texto): opera sobre BYTES, sin decodificar. Convierte
  CRLF -> LF y luego CR solitario -> LF. No quita BOM ni toca espacios, tabs,
  Unicode ni mayúsculas. El resultado no depende del tamaño de bloque.
- `sha256/bin/v1` (binario): bytes exactos.

Una entrada de baseline sin `hash_alg` es legacy (hash de bytes crudos); se
verifica aceptando SOLO diferencias de EOL (forma cruda, LF o CRLF).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ALG_TEXTO = "sha256/eol-lf/v1"
ALG_BINARIO = "sha256/bin/v1"

CONTENIDO_TEXTO = "texto"
CONTENIDO_BINARIO = "binario"

ESTADO_OK = "ok"
ESTADO_OK_LEGACY = "ok_legacy"
ESTADO_DRIFT = "drift"
ESTADO_ALG_DESCONOCIDO = "algoritmo_desconocido"

ALGORITMOS_CONOCIDOS = (ALG_TEXTO, ALG_BINARIO)

_BLOQUE_DEFECTO = 65536


def algoritmo_para_contenido(contenido: str) -> str:
    """Algoritmo vigente para un tipo de contenido del manifest. Se elige
    exclusivamente por `contenido` (sin heurísticas). `ValueError` si el
    contenido es desconocido."""
    if contenido == CONTENIDO_TEXTO:
        return ALG_TEXTO
    if contenido == CONTENIDO_BINARIO:
        return ALG_BINARIO
    raise ValueError(f"contenido desconocido: {contenido!r}")


def _validar_bloque(bloque: int) -> None:
    if not isinstance(bloque, int) or isinstance(bloque, bool) or bloque < 1:
        raise ValueError(f"tamaño de bloque inválido: {bloque!r}")


def _iterar_bloques_canonicos(ruta, bloque: int):
    """Genera tuplas `(crudo, canonico)` por bloque leído: los bytes crudos y
    su forma LF-canónica (CRLF -> LF, CR -> LF). `canonico` puede ser `b""`
    (bloque que era solo el `\\n` de un CRLF partido).

    Lleva un flag de «\\r pendiente»: si un bloque termina en `\\r`, ese `\\r`
    ya se emitió como `\\n`; si el bloque siguiente empieza con `\\n`, se
    descarta ese `\\n` para no duplicar el salto (era un CRLF partido). Así el
    resultado es idéntico para cualquier tamaño de bloque."""
    cr_pendiente = False
    with open(ruta, "rb") as f:
        while True:
            datos = f.read(bloque)
            if not datos:
                break
            crudo = datos
            if cr_pendiente and datos[:1] == b"\n":
                datos = datos[1:]
            if not datos:
                cr_pendiente = False
                yield crudo, b""
                continue
            cr_pendiente = datos.endswith(b"\r")
            yield crudo, datos.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def hash_managed_file(ruta, algoritmo: str, bloque: int = _BLOQUE_DEFECTO) -> str:
    """Hash SHA-256 (hex) de `ruta` según `algoritmo`. `ValueError` si el
    algoritmo es desconocido. Errores de E/S se propagan."""
    if algoritmo not in ALGORITMOS_CONOCIDOS:
        raise ValueError(f"algoritmo desconocido: {algoritmo!r}")
    _validar_bloque(bloque)
    hasher = hashlib.sha256()
    if algoritmo == ALG_TEXTO:
        for _crudo, canonico in _iterar_bloques_canonicos(ruta, bloque):
            hasher.update(canonico)
    else:
        with open(ruta, "rb") as f:
            for trozo in iter(lambda: f.read(bloque), b""):
                hasher.update(trozo)
    return hasher.hexdigest()


def hash_crudo_file(ruta) -> str:
    """SHA-256 (hex) de los bytes crudos de `ruta`. Es el hash de las entradas
    legacy (sin `hash_alg`)."""
    hasher = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(_BLOQUE_DEFECTO), b""):
            hasher.update(trozo)
    return hasher.hexdigest()


def _hashes_legacy(ruta, bloque: int) -> tuple:
    """(crudo, forma LF, forma CRLF) calculados en una sola pasada."""
    h_crudo = hashlib.sha256()
    h_lf = hashlib.sha256()
    h_crlf = hashlib.sha256()
    for crudo, canonico in _iterar_bloques_canonicos(ruta, bloque):
        h_crudo.update(crudo)
        h_lf.update(canonico)
        h_crlf.update(canonico.replace(b"\n", b"\r\n"))
    return h_crudo.hexdigest(), h_lf.hexdigest(), h_crlf.hexdigest()


def verificar_entrada(
    ruta,
    entrada: dict,
    bloque: int = _BLOQUE_DEFECTO,
    contenido: str = CONTENIDO_TEXTO,
) -> tuple:
    """Verifica `ruta` contra una entrada de baseline `{ruta, sha256, hash_alg?}`.

    Devuelve `(estado, detalle)` con estado en `ESTADO_OK`, `ESTADO_OK_LEGACY`,
    `ESTADO_DRIFT` o `ESTADO_ALG_DESCONOCIDO` (fail-closed: nunca `ok`).

    - Con `hash_alg` conocido: compara el hash managed (hex esperado
      case-insensitive).
    - Con `hash_alg` presente pero desconocido o no-str: no calcula nada.
    - Sin `hash_alg` (legacy): una sola pasada que calcula hash crudo, LF y
      CRLF; `ok_legacy` si el esperado coincide con alguno, si no `drift`.
    - `sha256` ausente o no-str: `drift`.
    - `contenido` solo afecta la vía legacy: con `binario` se acepta SOLO el
      hash crudo (nunca las formas LF/CRLF). Valor inválido: `ValueError`.

    Errores de E/S (OSError, FileNotFoundError) se propagan."""
    _validar_bloque(bloque)
    if contenido not in (CONTENIDO_TEXTO, CONTENIDO_BINARIO):
        raise ValueError(f"contenido desconocido: {contenido!r}")
    if "hash_alg" in entrada:
        alg = entrada["hash_alg"]
        if not isinstance(alg, str) or alg not in ALGORITMOS_CONOCIDOS:
            return ESTADO_ALG_DESCONOCIDO, f"algoritmo desconocido: {alg!r}"
    else:
        alg = None

    esperado = entrada.get("sha256")
    if not isinstance(esperado, str):
        return ESTADO_DRIFT, "sha256 esperado ausente o inválido"
    esperado = esperado.lower()

    if alg is not None:
        actual = hash_managed_file(ruta, alg, bloque)
        if actual == esperado:
            return ESTADO_OK, f"coincide ({alg})"
        return ESTADO_DRIFT, f"hash distinto ({alg})"

    if contenido == CONTENIDO_BINARIO:
        if hash_crudo_file(ruta) == esperado:
            return ESTADO_OK_LEGACY, "legacy verificable (forma crudo, binario)"
        return ESTADO_DRIFT, "legacy binario: no coincide con el hash crudo"

    crudo, forma_lf, forma_crlf = _hashes_legacy(ruta, bloque)
    for nombre, valor in (("crudo", crudo), ("lf", forma_lf), ("crlf", forma_crlf)):
        if valor == esperado:
            return ESTADO_OK_LEGACY, f"legacy verificable (forma {nombre})"
    return ESTADO_DRIFT, "legacy: no coincide con forma cruda, LF ni CRLF"
