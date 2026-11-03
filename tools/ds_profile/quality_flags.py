"""Calidad agregada del dataset: pura agregación/filtrado sobre
`columnas_detalle` ya calculado por `column_stats.py` -- ningún cálculo
nuevo acá."""
from __future__ import annotations


def calcular_calidad(columnas_detalle: dict, duplicados_valor: int, exactitud_duplicados: str) -> dict:
    totalmente_nulas = [
        nombre for nombre, detalle in columnas_detalle.items() if detalle["nulls"]["pct"] == 100.0
    ]
    constantes = [nombre for nombre, detalle in columnas_detalle.items() if "constante" in detalle["flags"]]
    alta_cardinalidad = [
        nombre for nombre, detalle in columnas_detalle.items() if "alta_cardinalidad" in detalle["flags"]
    ]
    posible_problema_tipo = [
        nombre for nombre, detalle in columnas_detalle.items() if "posible_problema_tipo" in detalle["flags"]
    ]
    return {
        "columnas_totalmente_nulas": totalmente_nulas,
        "columnas_constantes": constantes,
        "duplicados_fila": {"valor": duplicados_valor, "exactitud": exactitud_duplicados},
        "columnas_alta_cardinalidad": alta_cardinalidad,
        "columnas_posible_problema_tipo": posible_problema_tipo,
    }
