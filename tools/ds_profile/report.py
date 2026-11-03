"""Orquestación de `ds_profile run`: una única pasada streaming sobre el
dataset, ensamblado del dict de `profile.json` (y `profile.md` opcional) y
escritura atómica.

Deliberadamente NO importa `dsguard.core` (dependencia dura evitada a
propósito, `design.md`): reimplementa acá mismo el patrón de escritura
atómica `.tmp` + `os.replace` que ya usa `dsguard.core.escribir_texto_atomico`
-- `holdout_guard.py` es el único módulo de este paquete que sí depende de
`dsguard`, por diseño explícito.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import column_stats, fingerprint as fingerprint_mod, io_readers, quality_flags, sampling, schema as schema_mod

TOOL_VERSION = "0.1.0"
SCHEMA_VERSION = 1

# El tamaño de muestra del reservoir lo fija `sampling.decidir_plan`
# (tope por presupuesto de memoria, `max_filas_exactas` y 200_000).


class ArchivoInvalidoError(Exception):
    """`--input` no existe o no es un archivo regular."""


class LecturaFallidaError(Exception):
    """La lectura/perfilado de `--input` falló (archivo malformado, error del
    reader o memoria insuficiente). El mensaje es accionable."""


def _error_memoria(ruta, filas) -> LecturaFallidaError:
    return LecturaFallidaError(
        f"Memoria insuficiente al perfilar {ruta} tras {filas} filas. "
        "Bajá --max-mb-exactos/--max-filas-exactas para perfilar una muestra más chica."
    )


def _digest_fila(tupla: tuple) -> bytes:
    """Digest de 16 bytes de la fila (reemplaza retener la tupla completa)."""
    return hashlib.blake2b(repr(tupla).encode("utf-8", "surrogatepass"), digest_size=16).digest()


def _ahora_utc() -> str:
    """Mismo formato que `dsguard.core.ahora_utc()`: `YYYY-MM-DDTHH:MM:SSZ`,
    reimplementado localmente (ver docstring del módulo)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _escribir_atomico(path: Path, contenido: str) -> None:
    """Mismo patrón que `dsguard.core.escribir_texto_atomico`: `.tmp` en el
    mismo directorio + `os.replace`, creando los directorios que falten."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(contenido)
    os.replace(tmp, path)


def _slug(ruta_str: str) -> str:
    """`slug(ruta de --input)`: separadores de ruta y puntos -> `_`,
    minúsculas, solo `[a-z0-9_]`. Determinista a partir del string tal como
    se pasó por `--input` (no de la ruta resuelta), para que dos corridas
    con el mismo argumento produzcan el mismo `profile_id` por defecto."""
    texto = ruta_str.replace("\\", "/").replace("/", "_").replace(".", "_").lower()
    texto = re.sub(r"[^a-z0-9_]", "_", texto)
    texto = re.sub(r"_+", "_", texto).strip("_")
    return texto or "dataset"


def generar_markdown(perfil: dict) -> str:
    """Formateador puro: tabla/lista simple y legible sobre el dict YA
    calculado, sin ningún cálculo nuevo. Sin HTML."""
    calidad = perfil["calidad"]
    lineas = [
        f"# Perfil de datos: {perfil['dataset_path']}",
        "",
        f"- profile_id: `{perfil['profile_id']}`",
        f"- formato: {perfil['formato_detectado']}",
        f"- fingerprint: `{perfil['fingerprint']['hash']}` ({perfil['fingerprint']['algoritmo']})",
        f"- creado (UTC): {perfil['created_utc']}",
        f"- filas: {perfil['filas']}",
        f"- columnas: {perfil['columnas']}",
        f"- tamaño (bytes): {perfil['tamano_bytes']}",
        f"- muestreo activo: {perfil['sampling']['activo']} "
        f"(tamaño_muestra={perfil['sampling']['tamano_muestra']}"
        + (f", motivo={perfil['sampling']['motivo']}" if perfil['sampling'].get('motivo') else "")
        + ")",
        "",
        "## Calidad agregada",
        f"- columnas totalmente nulas: {calidad['columnas_totalmente_nulas'] or 'ninguna'}",
        f"- columnas constantes: {calidad['columnas_constantes'] or 'ninguna'}",
        f"- columnas alta cardinalidad: {calidad['columnas_alta_cardinalidad'] or 'ninguna'}",
        f"- columnas con posible problema de tipo: {calidad['columnas_posible_problema_tipo'] or 'ninguna'}",
        f"- filas duplicadas: {calidad['duplicados_fila']['valor']} ({calidad['duplicados_fila']['exactitud']})",
        "",
        "## Columnas",
        "",
        "| columna | dtype | nulls % | unique | flags |",
        "|---|---|---|---|---|",
    ]
    for nombre, detalle in perfil["columnas_detalle"].items():
        flags = ", ".join(detalle["flags"]) if detalle["flags"] else "-"
        lineas.append(
            f"| {nombre} | {detalle['dtype']} | {detalle['nulls']['pct']:.2f} | "
            f"{detalle['unique']['count']} ({detalle['unique']['exactitud']}) | {flags} |"
        )
    lineas.append("")
    return "\n".join(lineas) + "\n"


def generar_perfil(*args, **kwargs) -> dict:
    """Ver `_generar_perfil`: igual, pero un `MemoryError` en cualquier fase se
    informa como `LecturaFallidaError` accionable (sin traceback crudo)."""
    try:
        return _generar_perfil(*args, **kwargs)
    except MemoryError as exc:
        ruta = kwargs.get("ruta_input", args[0] if args else "<input>")
        raise _error_memoria(ruta, "N/D") from exc


def _procesar_fila(fila, acumuladores, orden_columnas, valores_completos, reservoir, digests_filas) -> None:
    for nombre in fila.keys():
        if nombre not in acumuladores:
            # Columna no vista en el header inicial (CSV con filas
            # irregulares) -- se agrega sobre la marcha, sin perder datos.
            acumuladores[nombre] = column_stats.AcumuladorColumna(nombre)
            orden_columnas.append(nombre)
            if valores_completos is not None:
                valores_completos[nombre] = []
        valor = fila.get(nombre)
        acumuladores[nombre].observar(valor)
        if valores_completos is not None and not (valor is None or (isinstance(valor, str) and valor.strip() == "")):
            valores_completos[nombre].append(valor)
    if reservoir is not None:
        reservoir.observar(fila)
    else:
        digests_filas.add(_digest_fila(schema_mod.fila_a_tupla(fila, orden_columnas)))


def _generar_perfil(
    ruta_input: Path,
    output_dir: Path,
    profile_id: Optional[str] = None,
    max_filas_exactas: int = 2_000_000,
    max_mb_exactos: int = 500,
    top_n: int = 20,
    seed: int = 42,
    incluir_markdown: bool = False,
) -> dict:
    """Corre `ds_profile` sobre `ruta_input` y escribe
    `<output_dir>/<profile_id>/profile.json` (+ `profile.md` si
    `incluir_markdown`), atómicamente. Nunca escribe nada si algo falla
    antes de terminar de calcular: `FormatoNoSoportadoError`/
    `DependenciaFaltanteError`/`ArchivoInvalidoError` se levantan ANTES de
    tocar el filesystem de salida.

    Devuelve `{"perfil": dict, "ruta_profile_json": Path, "ruta_profile_md":
    Optional[Path]}`."""
    ruta_input = Path(ruta_input)
    output_dir = Path(output_dir)

    if not ruta_input.exists() or not ruta_input.is_file():
        raise ArchivoInvalidoError(f"--input no existe o no es un archivo: {ruta_input}")

    formato = ruta_input.suffix.lower().lstrip(".")
    # Puede levantar FormatoNoSoportadoError / DependenciaFaltanteError --
    # se dejan propagar tal cual, el llamador (cli.py) las traduce a exit
    # code 1/3. Todavía no se creó ningún archivo de salida.
    try:
        lector = io_readers.abrir_lector(ruta_input)
    except (io_readers.FormatoNoSoportadoError, io_readers.DependenciaFaltanteError):
        raise
    except Exception as exc:  # noqa: BLE001 -- footer/encabezado ilegible, sin traceback crudo
        raise LecturaFallidaError(
            f"No se pudo abrir {ruta_input} ({type(exc).__name__}: {exc}). "
            "Verificá que el archivo no esté corrupto o truncado."
        ) from exc

    try:
        return _perfilar_con_lector(
            lector, ruta_input, output_dir, profile_id, formato,
            max_filas_exactas, max_mb_exactos, top_n, seed, incluir_markdown,
        )
    finally:
        _cerrar_lector(lector)


def _cerrar_lector(lector) -> None:
    """Cierra el lector si expone `close()` (Parquet: libera el handle)."""
    cerrar = getattr(lector, "close", None)
    if callable(cerrar):
        try:
            cerrar()
        except Exception:  # noqa: BLE001 -- el cierre nunca debe tapar el error/resultado real
            pass


def _perfilar_con_lector(
    lector, ruta_input, output_dir, profile_id, formato,
    max_filas_exactas, max_mb_exactos, top_n, seed, incluir_markdown,
) -> dict:
    """Cuerpo de `_generar_perfil` con el lector ya abierto (el llamador lo cierra)."""
    try:
        tamano_bytes = lector.tamano_bytes()
        filas_exactas_meta = lector.filas_exactas()
        schema_lector = dict(lector.schema())
        orden_columnas = list(schema_lector.keys())
    except Exception as exc:  # noqa: BLE001 -- se traduce a un error accionable
        raise LecturaFallidaError(
            f"No se pudo leer la metadata de {ruta_input} ({type(exc).__name__}: {exc}). "
            "Verificá que el archivo no esté corrupto o truncado."
        ) from exc

    # Decisión exacto/muestreado ANTES de leer filas: solo metadata + presupuesto.
    plan = sampling.decidir_plan(
        tamano_bytes, filas_exactas_meta, len(orden_columnas), max_mb_exactos, max_filas_exactas,
        schema=schema_lector,
    )
    modo_muestreado = plan["muestreado"]
    # Lectura columnar (B-11): solo exacto + lector con `iter_columna` + schema
    # plano. Muestreado y CSV siguen por filas (el reservoir necesita el orden de filas).
    modo_lectura = "columnar_v1" if _puede_columnar(lector, schema_lector, modo_muestreado) else "filas"

    if modo_lectura == "columnar_v1":
        filas_totales, duplicados_valor, columnas_detalle = _perfilar_columnar(
            lector, ruta_input, orden_columnas, top_n
        )
        exactitud_orden = "exacta"
        tamano_muestra_real = None
    else:
        filas_totales, duplicados_valor, columnas_detalle, exactitud_orden, tamano_muestra_real = _perfilar_por_filas(
            lector, ruta_input, orden_columnas, modo_muestreado, plan, seed, top_n
        )

    schema_final = {nombre: columnas_detalle[nombre]["dtype"] for nombre in orden_columnas}
    calidad = quality_flags.calcular_calidad(columnas_detalle, duplicados_valor, exactitud_orden)

    fp = fingerprint_mod.calcular_fingerprint(ruta_input)

    if profile_id is None:
        profile_id = f"{_slug(str(ruta_input))}__{fp['hash'][:12]}"

    perfil = {
        "schema_version": SCHEMA_VERSION,
        "tool": "ds_profile",
        "tool_version": TOOL_VERSION,
        "profile_id": profile_id,
        "dataset_path": str(ruta_input),
        "formato_detectado": formato,
        "fingerprint": fp,
        "created_utc": _ahora_utc(),
        "filas": filas_totales,
        "columnas": len(orden_columnas),
        "tamano_bytes": tamano_bytes,
        "schema": schema_final,
        "columnas_detalle": columnas_detalle,
        "calidad": calidad,
        "sampling": {
            "activo": modo_muestreado,
            "metodo": "reservoir_v1",
            "semilla": seed,
            "tamano_muestra": tamano_muestra_real,
            "motivo": plan["motivo"],
            "filas_observadas": filas_totales,
            "version_algoritmo": sampling.VERSION_ALGORITMO,
            "presupuesto_bytes": plan["presupuesto_bytes"],
            "estimado_bytes_exactos": plan["estimado_bytes"],
            # Campos aditivos v0.15 (sin cambiar VERSION_ALGORITMO/SCHEMA_VERSION):
            "estimacion": plan["estimacion"],
            "modo_lectura": modo_lectura,
        },
        "limites_aplicados": {
            "max_filas_exactas": max_filas_exactas,
            "max_mb_exactos": max_mb_exactos,
            "top_n": top_n,
            "seed": seed,
        },
    }

    perfil_dir = output_dir / profile_id
    ruta_json = perfil_dir / "profile.json"
    texto_json = json.dumps(perfil, indent=2, ensure_ascii=False) + "\n"
    _escribir_atomico(ruta_json, texto_json)

    ruta_md = None
    if incluir_markdown:
        ruta_md = perfil_dir / "profile.md"
        _escribir_atomico(ruta_md, generar_markdown(perfil))

    return {"perfil": perfil, "ruta_profile_json": ruta_json, "ruta_profile_md": ruta_md}


def _perfilar_por_filas(lector, ruta_input, orden_columnas, modo_muestreado, plan, seed, top_n):
    """Camino histórico: una pasada por filas (exacto o reservoir). Devuelve
    `(filas_totales, duplicados_valor, columnas_detalle, exactitud_orden,
    tamano_muestra_real)`."""
    reservoir = sampling.ReservoirSampler(plan["tamano_muestra"], seed) if modo_muestreado else None
    acumuladores = {nombre: column_stats.AcumuladorColumna(nombre) for nombre in orden_columnas}
    # Solo se retiene la lista completa de valores no nulos por columna en
    # modo exacto (spec.md: aceptable porque el dataset está bajo el
    # umbral). En modo muestreado, `valores_completos` queda `None` y los
    # valores para los estadísticos de orden se extraen de la muestra final
    # más abajo, después del loop.
    valores_completos = None if modo_muestreado else {nombre: [] for nombre in orden_columnas}
    # Duplicados exactos por digest (16 B/fila) en vez de retener cada tupla.
    digests_filas = None if modo_muestreado else set()

    filas_totales = 0
    iterador = iter(lector.iter_filas())
    while True:
        # Solo el avance del reader se traduce a error de lectura: un bug del
        # cálculo no debe parecer un archivo corrupto.
        try:
            fila = next(iterador, None)
        except Exception as exc:  # noqa: BLE001 -- errores del reader (pyarrow/csv/Unicode/OS)
            if isinstance(exc, MemoryError):
                raise _error_memoria(ruta_input, filas_totales) from exc
            raise LecturaFallidaError(
                f"Falló la lectura de {ruta_input} tras {filas_totales} filas "
                f"({type(exc).__name__}: {exc}). Verificá que el archivo no esté corrupto."
            ) from exc
        if fila is None:
            break
        filas_totales += 1
        try:
            _procesar_fila(fila, acumuladores, orden_columnas, valores_completos, reservoir, digests_filas)
        except MemoryError as exc:
            raise _error_memoria(ruta_input, filas_totales) from exc

    if modo_muestreado:
        muestra = reservoir.muestra()
        valores_para_orden = {nombre: [] for nombre in orden_columnas}
        for fila in muestra:
            for nombre in orden_columnas:
                valor = fila.get(nombre)
                if not (valor is None or (isinstance(valor, str) and valor.strip() == "")):
                    valores_para_orden[nombre].append(valor)
        duplicados_valor = len(muestra) - len({_digest_fila(schema_mod.fila_a_tupla(f, orden_columnas)) for f in muestra})
        exactitud_orden = "muestreada"
        tamano_muestra_real = len(muestra)
    else:
        valores_para_orden = valores_completos
        duplicados_valor = filas_totales - len(digests_filas)
        exactitud_orden = "exacta"
        tamano_muestra_real = None

    columnas_detalle = {
        nombre: column_stats.construir_metricas_columna(
            nombre, acumuladores[nombre], valores_para_orden.get(nombre, []), exactitud_orden, top_n
        )
        for nombre in orden_columnas
    }
    return filas_totales, duplicados_valor, columnas_detalle, exactitud_orden, tamano_muestra_real


# Tipos pyarrow anidados: el camino columnar cae a filas (el digest de fila
# y `to_pylist` por columna no están validados para ellos).
_PREFIJOS_ANIDADOS = ("list", "large_list", "fixed_size_list", "struct", "map")


def _puede_columnar(lector, schema_lector: dict, modo_muestreado: bool) -> bool:
    """Columnar solo si: modo exacto, el lector expone `iter_columna`, nombres
    de columna únicos y ningún tipo anidado."""
    if modo_muestreado or not callable(getattr(lector, "iter_columna", None)):
        return False
    if not schema_lector:
        return False
    # Un '.' en el nombre puede confundirse con un campo anidado en la proyección.
    if any("." in str(nombre) for nombre in schema_lector):
        return False
    nombres_unicos = getattr(lector, "nombres_unicos", None)
    if callable(nombres_unicos) and not nombres_unicos():
        return False
    if any(str(t).startswith(_PREFIJOS_ANIDADOS) for t in schema_lector.values()):
        return False
    return True


def _iterar_traduciendo_errores(iterable, ruta_input, etiqueta: str):
    """Itera `iterable`; un error del reader se traduce a `LecturaFallidaError`
    (o `_error_memoria`). Los errores del consumidor NO pasan por acá."""
    n = 0
    iterador = iter(iterable)
    while True:
        try:
            item = next(iterador)
        except StopIteration:
            return
        except Exception as exc:  # noqa: BLE001 -- errores del reader (pyarrow/OS)
            if isinstance(exc, MemoryError):
                raise _error_memoria(ruta_input, n) from exc
            raise LecturaFallidaError(
                f"Falló la lectura de {ruta_input} tras {n} {etiqueta} "
                f"({type(exc).__name__}: {exc}). Verificá que el archivo no esté corrupto."
            ) from exc
        n += 1
        yield item


def _perfilar_columnar(lector, ruta_input, orden_columnas, top_n):
    """Camino columnar de dos pases (Parquet + exacto). Pase 1: digests de fila
    por batches de todas las columnas, SIN retener valores (única métrica
    multi-columna: duplicados de fila). Pase 2: columna por columna con
    proyección; se acumulan solo los valores de esa columna, se construyen
    sus métricas y se liberan. Devuelve `(filas_totales, duplicados_valor,
    columnas_detalle)`, idénticos al camino por filas."""
    digests_filas = set()
    filas_totales = 0
    for fila in _iterar_traduciendo_errores(lector.iter_filas(), ruta_input, "filas"):
        filas_totales += 1
        try:
            digests_filas.add(_digest_fila(schema_mod.fila_a_tupla(fila, orden_columnas)))
        except MemoryError as exc:
            raise _error_memoria(ruta_input, filas_totales) from exc
    duplicados_valor = filas_totales - len(digests_filas)

    columnas_detalle = {}
    for nombre in orden_columnas:
        acumulador = column_stats.AcumuladorColumna(nombre)
        valores = []
        try:
            for valor in _iterar_traduciendo_errores(lector.iter_columna(nombre), ruta_input, f"valores de la columna {nombre!r}"):
                acumulador.observar(valor)
                if not (valor is None or (isinstance(valor, str) and valor.strip() == "")):
                    valores.append(valor)
            columnas_detalle[nombre] = column_stats.construir_metricas_columna(
                nombre, acumulador, valores, "exacta", top_n
            )
        except MemoryError as exc:
            raise _error_memoria(ruta_input, filas_totales) from exc
        finally:
            del valores
    return filas_totales, duplicados_valor, columnas_detalle
