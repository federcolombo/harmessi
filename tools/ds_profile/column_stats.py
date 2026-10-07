"""Clasificación de dtype y métricas por columna (Requisito 1 de `spec.md`).

Dos niveles, deliberadamente separados:

1. `AcumuladorColumna` -- streaming, una instancia por columna, corre sobre
   CADA fila del dataset sin importar el modo (exacto/muestreado). Retiene
   solo contadores y reducciones O(1): `nulls`, min/max numérico y de fecha,
   media/std (Welford) y los contadores que clasifican `dtype`/`binary_numeric`/
   `posible_problema_tipo` (exactos sobre todas las filas, sin lista de valores).
2. `construir_metricas_columna` -- opera sobre una lista de valores YA
   DECIDIDA por el orquestador (`report.py`): la lista de valores no nulos en
   modo exacto (acotada por el presupuesto de `sampling.decidir_plan`), o los
   valores de la muestra del `ReservoirSampler` en modo muestreado. De ahí sale
   lo que declara su propia `exactitud` (`unique`, `top_valores`,
   `mediana`/`cuantiles` y los flags de cardinalidad).
   `clasificar_dtype`/`es_binario_numerico` (sobre listas) se conservan como
   referencia de equivalencia con los acumuladores.

Todos los parseos (`_es_entero`/`_es_flotante`/`_parsear_fecha`) convierten
el valor a `str(valor)` antes de intentar parsear -- funciona igual para
strings crudos de CSV que para tipos nativos de Parquet (`int`/`float`/
`bool`/`datetime.date`/`datetime.datetime`): `str(datetime.date(2024,1,1))`
ya cae en el formato `%Y-%m-%d`, y `str(True)` nunca parsea como número.
"""
from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from datetime import datetime
from typing import Optional

# Formatos de fecha fijos, probados en este orden exacto (Requisito 1).
# Los dos últimos cubren `datetime.datetime` nativo de Parquet con
# microsegundos (columnas `timestamp`): sin ellos, `str(valor)` nunca
# matchea ninguno de los formatos anteriores vía `strptime` y la columna cae
# a `texto`, perdiendo `fecha_min`/`fecha_max` silenciosamente (hallazgo de
# `data-science-reviewer`).
FORMATOS_FECHA: tuple = (
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S.%f",
)

# Umbral de clasificación por dtype (entero/flotante/fecha) y de
# "casi_constante"/"alta_cardinalidad".
_UMBRAL_CLASIFICACION = 0.95
_UMBRAL_CASI_CONSTANTE = 0.99
_UMBRAL_ALTA_CARDINALIDAD = 0.95
_UMBRAL_POSIBLE_PROBLEMA_TIPO = 0.5

# `float()` de stdlib acepta estos literales -- se excluyen a propósito para
# que una columna de texto con "NaN"/"Infinity" no se clasifique como
# flotante.
_FLOTANTE_EXCLUIDOS = frozenset(
    {"nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}
)

REGEX_POSIBLE_ID = re.compile(r"^(id|.*_id|uuid|guid)$", re.IGNORECASE)


# --- Parseo -------------------------------------------------------------


def _texto(valor) -> str:
    return str(valor).strip()


def _es_entero(valor) -> bool:
    texto = _texto(valor)
    if not texto:
        return False
    cuerpo = texto[1:] if texto[0] in "+-" else texto
    return bool(cuerpo) and cuerpo.isdigit()


def _es_flotante(valor) -> bool:
    texto = _texto(valor)
    if not texto or texto.casefold() in _FLOTANTE_EXCLUIDOS:
        return False
    try:
        float(texto)
    except ValueError:
        return False
    return True


def _a_float(valor) -> float:
    return float(_texto(valor))


def _parsear_fecha(valor) -> Optional[datetime]:
    texto = _texto(valor)
    if not texto:
        return None
    for formato in FORMATOS_FECHA:
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    return None


def clasificar_dtype(valores_no_nulos: list) -> str:
    """Orden fijo (Requisito 1): booleano -> entero -> flotante -> fecha ->
    texto. Un dataset sin valores no nulos clasifica como `texto` (no hay
    evidencia de otra cosa; no se marca `constante` porque esa flag exige al
    menos 1 valor no nulo)."""
    if not valores_no_nulos:
        return "texto"

    distintos_normalizados = {_texto(v).casefold() for v in valores_no_nulos}
    if distintos_normalizados and distintos_normalizados <= {"true", "false"}:
        return "booleano"

    total = len(valores_no_nulos)
    if sum(1 for v in valores_no_nulos if _es_entero(v)) / total >= _UMBRAL_CLASIFICACION:
        return "entero"
    if sum(1 for v in valores_no_nulos if _es_flotante(v)) / total >= _UMBRAL_CLASIFICACION:
        return "flotante"
    if (
        sum(1 for v in valores_no_nulos if _parsear_fecha(v) is not None) / total
        >= _UMBRAL_CLASIFICACION
    ):
        return "fecha"
    return "texto"


def es_binario_numerico(valores_no_nulos: list, dtype: str) -> bool:
    """`True` solo si `dtype` ya salió `"entero"`/`"flotante"` Y el conjunto
    de esos valores parseados a `float` (mismo helper `_a_float`/`_es_flotante`
    usado para clasificar) es exactamente `{0.0, 1.0}` (ambos presentes,
    ningún otro valor). Una columna con un único valor repetido (ej. solo
    `"0"`) no es binaria numérica -- cae en el flag `constante` existente.
    Sin inferencia por nombre de columna."""
    if dtype not in ("entero", "flotante"):
        return False
    valores_float = {_a_float(v) for v in valores_no_nulos if _es_flotante(v)}
    return valores_float == {0.0, 1.0}


def _fraccion_numero_o_fecha(valores: list) -> float:
    if not valores:
        return 0.0
    coincidencias = sum(1 for v in valores if _es_flotante(v) or _parsear_fecha(v) is not None)
    return coincidencias / len(valores)


# --- Acumulador streaming (siempre exacto) -------------------------------


class AcumuladorColumna:
    """Una instancia por columna, alimentada con CADA fila del dataset (sin
    importar el modo exacto/muestreado -- spec.md: "las métricas de
    metadata... son siempre exactas, calculadas en streaming"). No retiene
    ningún valor individual: solo contadores y reducciones incrementales
    (Welford para media/std, comparación directa para min/max)."""

    def __init__(self, nombre: str) -> None:
        self.nombre = nombre
        self.total = 0
        self.nulos = 0
        self.n_numerico = 0
        self.media = 0.0
        self._m2 = 0.0
        self.min_numerico: Optional[float] = None
        self.max_numerico: Optional[float] = None
        self.min_fecha: Optional[datetime] = None
        self.max_fecha: Optional[datetime] = None
        # Contadores O(1) para clasificar dtype y derivar flags en streaming,
        # exactos sobre TODAS las filas (sin retener valores).
        self.n_entero = 0
        self.n_fecha = 0
        self.n_num_o_fecha = 0
        self.solo_booleano = True
        self._floats_distintos: set = set()
        self._floats_desbordado = False

    def observar(self, valor) -> None:
        self.total += 1
        if valor is None or (isinstance(valor, str) and valor.strip() == ""):
            self.nulos += 1
            return

        if self.solo_booleano and _texto(valor).casefold() not in ("true", "false"):
            self.solo_booleano = False
        if _es_entero(valor):
            self.n_entero += 1

        es_flotante = _es_flotante(valor)
        if es_flotante:
            numero = _a_float(valor)
            self.n_numerico += 1
            if not self._floats_desbordado:
                self._floats_distintos.add(numero)
                if len(self._floats_distintos) > 2:
                    self._floats_desbordado = True
                    self._floats_distintos = set()
            if self.min_numerico is None or numero < self.min_numerico:
                self.min_numerico = numero
            if self.max_numerico is None or numero > self.max_numerico:
                self.max_numerico = numero
            # Welford: media/varianza incrementales, sin retener la lista.
            delta = numero - self.media
            self.media += delta / self.n_numerico
            delta2 = numero - self.media
            self._m2 += delta * delta2

        fecha = _parsear_fecha(valor)
        if es_flotante or fecha is not None:
            self.n_num_o_fecha += 1
        if fecha is not None:
            self.n_fecha += 1
            if self.min_fecha is None or fecha < self.min_fecha:
                self.min_fecha = fecha
            if self.max_fecha is None or fecha > self.max_fecha:
                self.max_fecha = fecha

    def desviacion_estandar(self) -> Optional[float]:
        """Desviación estándar poblacional (`sqrt(m2/n)`). `None` si no hubo
        ningún valor numérico; `0.0` si hubo exactamente uno."""
        if self.n_numerico == 0:
            return None
        if self.n_numerico == 1:
            return 0.0
        return math.sqrt(self._m2 / self.n_numerico)

    @property
    def filas_no_nulas(self) -> int:
        return self.total - self.nulos

    def clasificar_dtype(self) -> str:
        """Mismo criterio y orden que `clasificar_dtype(lista)` pero desde los
        contadores (exacto sobre todas las filas, sin lista de valores)."""
        total = self.filas_no_nulas
        if total == 0:
            return "texto"
        if self.solo_booleano:
            return "booleano"
        if self.n_entero / total >= _UMBRAL_CLASIFICACION:
            return "entero"
        if self.n_numerico / total >= _UMBRAL_CLASIFICACION:
            return "flotante"
        if self.n_fecha / total >= _UMBRAL_CLASIFICACION:
            return "fecha"
        return "texto"

    def es_binario_numerico(self, dtype: str) -> bool:
        return (
            dtype in ("entero", "flotante")
            and not self._floats_desbordado
            and self._floats_distintos == {0.0, 1.0}
        )

    def fraccion_numero_o_fecha(self) -> float:
        total = self.filas_no_nulas
        return self.n_num_o_fecha / total if total else 0.0


# --- Estadísticos de orden/cardinalidad (exactos o sobre la muestra) ----


def _cuantiles(datos_ordenados: list) -> Optional[dict]:
    n = len(datos_ordenados)
    if n == 0:
        return None
    if n == 1:
        v = datos_ordenados[0]
        return {"p25": v, "p50": v, "p75": v, "p95": v, "p99": v}
    cortes = statistics.quantiles(datos_ordenados, n=100, method="inclusive")
    return {
        "p25": cortes[24],
        "p50": cortes[49],
        "p75": cortes[74],
        "p95": cortes[94],
        "p99": cortes[98],
    }


def _formatear_numero(valor: Optional[float], dtype: str):
    """Si `dtype` es `entero` y el valor es un entero exacto, lo devuelve
    como `int` (para que el JSON no muestre `5.0` en una columna entera).
    En cualquier otro caso lo devuelve tal cual."""
    if valor is None:
        return None
    if dtype == "entero" and float(valor).is_integer():
        return int(valor)
    return valor


def construir_metricas_columna(
    nombre: str,
    acumulador: AcumuladorColumna,
    valores_orden: list,
    exactitud_orden: str,
    top_n: int,
) -> dict:
    """Combina lo siempre-exacto de `acumulador` con lo calculado sobre
    `valores_orden` (lista de valores no nulos -- completa en modo exacto,
    extraída de la muestra final en modo muestreado; `exactitud_orden` es
    `"exacta"`/`"muestreada"` acorde)."""
    total = acumulador.total
    nulos = acumulador.nulos
    # Denominador de las flags de cardinalidad: en modo muestreado `distintos` y
    # las frecuencias salen de la muestra, así que se comparan contra la muestra.
    filas_no_nulas_total = acumulador.filas_no_nulas
    filas_no_nulas = len(valores_orden) if exactitud_orden == "muestreada" else filas_no_nulas_total

    dtype = acumulador.clasificar_dtype()

    distintos = len(set(_texto(v) for v in valores_orden))
    contador = Counter(_texto(v) for v in valores_orden)
    top_valores = [{"valor": valor, "frecuencia": frecuencia} for valor, frecuencia in contador.most_common(top_n)]

    detalle: dict = {
        "dtype": dtype,
        "nulls": {
            "count": nulos,
            "pct": (nulos / total * 100.0) if total else 0.0,
            "exactitud": "exacta",
        },
        "unique": {"count": distintos, "exactitud": exactitud_orden},
        "top_valores": top_valores,
        "exactitud_estadisticos": exactitud_orden,
        "flags": [],
    }

    if dtype in ("entero", "flotante"):
        detalle["min"] = _formatear_numero(acumulador.min_numerico, dtype)
        detalle["max"] = _formatear_numero(acumulador.max_numerico, dtype)
        detalle["media"] = acumulador.media if acumulador.n_numerico else None
        detalle["std"] = acumulador.desviacion_estandar()
        numericos_orden = sorted(_a_float(v) for v in valores_orden if _es_flotante(v))
        detalle["mediana"] = statistics.median(numericos_orden) if numericos_orden else None
        detalle["cuantiles"] = _cuantiles(numericos_orden)
    elif dtype == "fecha":
        detalle["fecha_min"] = acumulador.min_fecha.isoformat() if acumulador.min_fecha else None
        detalle["fecha_max"] = acumulador.max_fecha.isoformat() if acumulador.max_fecha else None

    if acumulador.es_binario_numerico(dtype):
        detalle["flags"].append("binary_numeric")

    if dtype == "texto" and acumulador.fraccion_numero_o_fecha() >= _UMBRAL_POSIBLE_PROBLEMA_TIPO:
        detalle["flags"].append("posible_problema_tipo")

    if filas_no_nulas > 0 and distintos == 1:
        detalle["flags"].append("constante")
    elif filas_no_nulas > 0 and top_valores and (top_valores[0]["frecuencia"] / filas_no_nulas) >= _UMBRAL_CASI_CONSTANTE:
        detalle["flags"].append("casi_constante")

    if filas_no_nulas > 0 and (distintos / filas_no_nulas) > _UMBRAL_ALTA_CARDINALIDAD:
        detalle["flags"].append("alta_cardinalidad")

    if (filas_no_nulas > 1 and distintos == filas_no_nulas) or REGEX_POSIBLE_ID.match(nombre):
        detalle["flags"].append("posible_id")

    return detalle
