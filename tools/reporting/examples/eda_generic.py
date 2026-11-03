"""Ejemplo genérico de reporte EDA (v0.6 Change 2, `20260918-eda-profile`).

Dominio neutro: "registros sintéticos" generados con `random.Random(RANDOM_STATE)`.
Columnas del dataset simulado: `record_id, grupo, segmento, medida, fecha_evento,
resultado`. Todo dato es inventado: no proviene de ningún proyecto ni fuente real.

Solo stdlib (sin pandas): las estadísticas se calculan con `statistics` y
contadores simples. `build_example_report()` es determinista: dos llamadas con el
mismo `RANDOM_STATE` producen el mismo `content_sha256`.

Sirve como referencia de cómo armar un reporte con el profile `eda`: capítulos
reales para los bloques aplicables, `omitted` con razón para los que no se
realizan y `not_applicable` para los que no tienen sentido en estos datos.
"""
from __future__ import annotations

import random
import statistics
from collections import Counter
from datetime import date, timedelta

from .. import core
from ..profiles import eda

# --- Constantes (bloque editable) ---------------------------------------------------

RANDOM_STATE = 42
N_REGISTROS = 400
N_BINS = 8
TOP_N_GRUPOS = 4
PROB_MEDIDA_NULA = 0.04
FECHA_INICIO = date(2024, 1, 1)
DIAS_RANGO = 366  # 2024 es bisiesto

GRUPOS = ("Grupo A", "Grupo B", "Grupo C", "Grupo D", "Grupo E", "Grupo F")
PESOS_GRUPO = (0.34, 0.24, 0.16, 0.12, 0.08, 0.06)
PROB_RESULTADO = {
    "Grupo A": 0.20,
    "Grupo B": 0.30,
    "Grupo C": 0.25,
    "Grupo D": 0.45,
    "Grupo E": 0.35,
    "Grupo F": 0.55,
}
SEGMENTOS = ("Segmento 1", "Segmento 2", "Segmento 3")

COLUMNAS = ("record_id", "grupo", "segmento", "medida", "fecha_evento", "resultado")

_POBLACION = f"Los {N_REGISTROS} registros sintéticos generados para este ejemplo"
_PERIODO = "Registros con fecha de evento entre enero y diciembre de 2024"


# --- Generación de datos sintéticos ---------------------------------------------------


def _generar_registros(semilla: int = RANDOM_STATE) -> list:
    """Genera `N_REGISTROS` filas sintéticas (dicts) de forma determinista."""
    rng = random.Random(semilla)
    registros = []
    for i in range(1, N_REGISTROS + 1):
        grupo = rng.choices(GRUPOS, weights=PESOS_GRUPO, k=1)[0]
        segmento = rng.choice(SEGMENTOS)
        medida = round(rng.gauss(50.0, 12.0), 2)
        if rng.random() < PROB_MEDIDA_NULA:
            medida = None
        fecha = FECHA_INICIO + timedelta(days=rng.randint(0, DIAS_RANGO - 1))
        resultado = 1 if rng.random() < PROB_RESULTADO[grupo] else 0
        registros.append(
            {
                "record_id": f"reg-{i:04d}",
                "grupo": grupo,
                "segmento": segmento,
                "medida": medida,
                "fecha_evento": fecha.isoformat(),
                "resultado": resultado,
            }
        )
    return registros


# --- Capítulos ---------------------------------------------------------------------------


def _capitulo_calidad(registros: list) -> core.Chapter:
    n = len(registros)
    filas = []
    for col in COLUMNAS:
        valores = [r[col] for r in registros]
        n_nulos = sum(1 for v in valores if v is None)
        n_unicos = len({v for v in valores if v is not None})
        filas.append((col, n, n_nulos, round(n_nulos / n, 4), n_unicos))
    tabla = core.TableArtifact.from_rows(
        table_id="calidad_por_columna",
        title="Completitud y valores distintos por columna",
        columns=("columna", "n_registros", "n_nulos", "prop_nulos", "n_valores_distintos"),
        rows=filas,
        units={
            "n_registros": "registros",
            "n_nulos": "registros",
            "prop_nulos": "proporción (0 a 1)",
        },
        column_labels={
            "columna": "Columna",
            "n_registros": "Registros",
            "n_nulos": "Valores faltantes",
            "prop_nulos": "Proporción faltante",
            "n_valores_distintos": "Valores distintos",
        },
        description=(
            "Una fila por columna del conjunto sintético; la proporción faltante "
            "(n_nulos / n_registros) se expresa entre 0 y 1."
        ),
    )
    n_ids_unicos = len({r["record_id"] for r in registros})
    n_nulos_medida = sum(1 for r in registros if r["medida"] is None)
    insight = core.Insight(
        insight_id="ins-calidad-completitud",
        title="Completitud de los datos y unicidad de los identificadores",
        technical_claim=(
            f"De {n} registros, {n_ids_unicos} tienen record_id distinto; la columna medida "
            f"tiene {n_nulos_medida} valores faltantes ({n_nulos_medida / n:.2%} del total). "
            "Ver la tabla para el detalle de las demás columnas."
        ),
        business_claim=(
            "Se puede saber cuántos registros no tienen medida y si algún identificador se "
            "repite antes de usar los datos."
        ),
        evidence_refs=("calidad_por_columna",),
        population=_POBLACION,
        time_scope=_PERIODO,
        claim_type="descriptive",
    )
    return core.Chapter(
        chapter_id="data_quality",
        title="Calidad de los datos",
        summary="Se revisó cuántos valores faltan y si los identificadores se repiten.",
        tables=(tabla,),
        insights=(insight,),
        method_note="Conteo directo de nulos y de valores distintos por columna.",
        metadata={"eda_block": "data_quality"},
    )


def _capitulo_univariado(registros: list) -> core.Chapter:
    valores = [r["medida"] for r in registros if r["medida"] is not None]
    cuartiles = statistics.quantiles(valores, n=4, method="inclusive")
    media = statistics.fmean(valores)
    mediana = statistics.median(valores)
    desvio = statistics.pstdev(valores)
    minimo, maximo = min(valores), max(valores)
    resumen = core.TableArtifact.from_rows(
        table_id="resumen_medida",
        title="Resumen de la medida (unidades de medida)",
        columns=("estadistica", "valor"),
        rows=[
            ("Mínimo", round(minimo, 2)),
            ("Primer cuartil", round(cuartiles[0], 2)),
            ("Mediana", round(mediana, 2)),
            ("Media", round(media, 2)),
            ("Tercer cuartil", round(cuartiles[2], 2)),
            ("Máximo", round(maximo, 2)),
            ("Desvío estándar", round(desvio, 2)),
        ],
        units={"valor": "unidades de medida"},
        column_labels={"estadistica": "Estadística", "valor": "Valor"},
        description="Estadísticos descriptivos de la medida, sin contar los valores faltantes.",
    )

    ancho = (maximo - minimo) / N_BINS
    conteos = [0] * N_BINS
    for v in valores:
        conteos[min(int((v - minimo) / ancho), N_BINS - 1)] += 1
    filas_bins = []
    for i, c in enumerate(conteos):
        desde = minimo + i * ancho
        filas_bins.append((f"{desde:.1f} a {desde + ancho:.1f}", c))
    distribucion = core.TableArtifact.from_rows(
        table_id="distribucion_medida",
        title="Cantidad de registros por rango de la medida",
        columns=("rango_medida", "n_registros"),
        rows=filas_bins,
        units={"n_registros": "registros"},
        column_labels={"rango_medida": "Rango de la medida", "n_registros": "Registros"},
        description=f"{N_BINS} rangos de igual ancho entre el mínimo y el máximo observados.",
    )
    figura = core.FigureArtifact(
        figure_id="fig-distribucion-medida",
        title="Cómo se distribuye la medida",
        spec=core.FigureSpec(
            chart_type="bar",
            x="rango_medida",
            y=("n_registros",),
            x_label="Rango de la medida (unidades de medida)",
            y_label="Registros",
            unit="registros",
        ),
        backing_table_id="distribucion_medida",
        description="Barras con la cantidad de registros en cada rango de la medida.",
        alt_text="Gráfico de barras: cantidad de registros por rango de la medida.",
    )
    insight = core.Insight(
        insight_id="ins-univariado-medida",
        title="Valor central y dispersión de la medida",
        technical_claim=(
            f"La medida tiene media {media:.1f} y mediana {mediana:.1f} (desvío estándar "
            f"{desvio:.1f}, unidades de medida); va de {minimo:.1f} a {maximo:.1f}."
        ),
        business_claim=(
            "El valor típico de la medida y cuánto varía entre registros se pueden leer "
            "directamente de la tabla y del gráfico."
        ),
        evidence_refs=("resumen_medida", "distribucion_medida", "fig-distribucion-medida"),
        population="Registros sintéticos con medida informada (se excluyen los faltantes)",
        time_scope=_PERIODO,
        claim_type="descriptive",
    )
    return core.Chapter(
        chapter_id="univariate",
        title="Cómo se comporta la medida",
        summary="Resumen numérico y distribución de la única variable numérica del ejemplo.",
        tables=(resumen, distribucion),
        figures=(figura,),
        insights=(insight,),
        method_note="Cuartiles por método inclusivo; desvío estándar poblacional.",
        metadata={"eda_block": "univariate"},
    )


def _capitulo_bivariado(registros: list) -> core.Chapter:
    total = Counter(r["grupo"] for r in registros)
    positivos = Counter(r["grupo"] for r in registros if r["resultado"] == 1)
    filas = [
        (g, total[g], positivos[g], round(positivos[g] / total[g], 4))
        for g in GRUPOS
        if total[g] > 0
    ]
    tabla = core.TableArtifact.from_rows(
        table_id="tasa_por_grupo",
        title="Tasa de resultado positivo por grupo (con cantidad de registros)",
        columns=("grupo", "n_registros", "n_positivos", "tasa_resultado"),
        rows=filas,
        units={"n_registros": "registros", "n_positivos": "registros", "tasa_resultado": "proporción (0 a 1)"},
        column_labels={
            "grupo": "Grupo",
            "n_registros": "Registros del grupo (denominador)",
            "n_positivos": "Registros con resultado positivo",
            "tasa_resultado": "Tasa de resultado positivo",
        },
        description=(
            "Tabla completa: todos los grupos, con su denominador. La tasa es "
            "n_positivos / n_registros."
        ),
    )
    figura = core.FigureArtifact(
        figure_id="fig-tasa-por-grupo",
        title=f"Los {TOP_N_GRUPOS} grupos con mayor tasa de resultado positivo",
        spec=core.FigureSpec(
            chart_type="bar",
            x="grupo",
            y=("tasa_resultado",),
            top_n=TOP_N_GRUPOS,
            sort="descending",
            x_label="Grupo",
            y_label="Tasa de resultado positivo",
            unit="proporción (0 a 1)",
            denominator="n_registros",
        ),
        backing_table_id="tasa_por_grupo",
        description=(
            f"Muestra solo los {TOP_N_GRUPOS} grupos con mayor tasa; la tabla de respaldo "
            "contiene todos los grupos."
        ),
        alt_text="Gráfico de barras: tasa de resultado positivo de los grupos con mayor tasa.",
    )
    mayor = max(filas, key=lambda f: f[3])
    menor = min(filas, key=lambda f: f[3])
    insight = core.Insight(
        insight_id="ins-tasa-por-grupo",
        title="La tasa de resultado positivo difiere entre grupos",
        technical_claim=(
            f"La tasa más alta es la de {mayor[0]} ({mayor[3]:.1%} sobre {mayor[1]} registros) y "
            f"la más baja la de {menor[0]} ({menor[3]:.1%} sobre {menor[1]} registros)."
        ),
        business_claim=(
            "Los grupos no tienen la misma proporción de resultados positivos; conviene mirar "
            "también cuántos registros tiene cada uno antes de comparar."
        ),
        evidence_refs=("tasa_por_grupo", "fig-tasa-por-grupo"),
        population=_POBLACION,
        time_scope=_PERIODO,
        claim_type="associative",
        uncertainty=(
            "Es una asociación descriptiva sin intervalos de confianza; los grupos con pocos "
            "registros pueden variar por azar y no se estableció ninguna causa."
        ),
    )
    return core.Chapter(
        chapter_id="bivariate_target",
        title="Resultado positivo según el grupo",
        summary=(
            "Proporción de registros con resultado positivo en cada grupo. Es una lectura "
            "exploratoria: no se usa para elegir variables de un modelo."
        ),
        tables=(tabla,),
        figures=(figura,),
        insights=(insight,),
        method_note="Tasa simple = positivos / registros del grupo, sin ajustes.",
        metadata={"eda_block": "bivariate_target"},
    )


def _capitulo_temporal(registros: list) -> core.Chapter:
    total = Counter(r["fecha_evento"][:7] for r in registros)
    positivos = Counter(r["fecha_evento"][:7] for r in registros if r["resultado"] == 1)
    meses = sorted(total)
    filas = [(m, total[m], round(positivos[m] / total[m], 4)) for m in meses]
    tabla = core.TableArtifact.from_rows(
        table_id="registros_por_mes",
        title="Registros y tasa de resultado positivo por mes",
        columns=("mes", "n_registros", "tasa_resultado"),
        rows=filas,
        units={"n_registros": "registros", "tasa_resultado": "proporción (0 a 1)"},
        column_labels={
            "mes": "Mes del evento",
            "n_registros": "Registros",
            "tasa_resultado": "Tasa de resultado positivo",
        },
        description="Agrupación por mes calendario de fecha_evento.",
    )
    figura = core.FigureArtifact(
        figure_id="fig-registros-por-mes",
        title="Cantidad de registros por mes",
        spec=core.FigureSpec(
            chart_type="line",
            x="mes",
            y=("n_registros",),
            x_label="Mes del evento",
            y_label="Registros",
            unit="registros",
        ),
        backing_table_id="registros_por_mes",
        description="Línea con la cantidad mensual de registros.",
        alt_text="Gráfico de líneas: cantidad de registros por mes durante 2024.",
    )
    mes_max = max(filas, key=lambda f: f[1])
    mes_min = min(filas, key=lambda f: f[1])
    insight = core.Insight(
        insight_id="ins-temporal-volumen",
        title="Cantidad de registros por mes",
        technical_claim=(
            f"Los {len(meses)} meses observados tienen entre {mes_min[1]} ({mes_min[0]}) y "
            f"{mes_max[1]} ({mes_max[0]}) registros; no se evaluó tendencia ni estacionalidad "
            "con un método formal."
        ),
        business_claim=(
            "Se puede ver en qué meses hubo más y menos registros; no se afirma ninguna "
            "tendencia."
        ),
        evidence_refs=("registros_por_mes", "fig-registros-por-mes"),
        population=_POBLACION,
        time_scope=_PERIODO,
        claim_type="descriptive",
        uncertainty=(
            f"Con entre {mes_min[1]} y {mes_max[1]} registros por mes, las diferencias "
            "mensuales pueden ser ruido de muestreo."
        ),
    )
    return core.Chapter(
        chapter_id="temporal",
        title="Evolución mensual",
        summary="Cómo se distribuyen los registros y el resultado positivo a lo largo de 2024.",
        tables=(tabla,),
        figures=(figura,),
        insights=(insight,),
        method_note="Meses calendario a partir de fecha_evento (formato AAAA-MM).",
        metadata={"eda_block": "temporal"},
    )


def _capitulo_concentracion(registros: list) -> core.Chapter:
    total = Counter(r["grupo"] for r in registros)
    n = len(registros)
    ordenados = sorted(total.items(), key=lambda kv: (-kv[1], kv[0]))
    filas = []
    acumulado = 0.0
    for grupo, cantidad in ordenados:
        participacion = cantidad / n
        acumulado += participacion
        filas.append((grupo, cantidad, round(participacion, 4), round(acumulado, 4)))
    tabla = core.TableArtifact.from_rows(
        table_id="concentracion_por_grupo",
        title="Participación de cada grupo en el total de registros",
        columns=("grupo", "n_registros", "participacion", "participacion_acumulada"),
        rows=filas,
        units={
            "n_registros": "registros",
            "participacion": "proporción (0 a 1)",
            "participacion_acumulada": "proporción (0 a 1)",
        },
        column_labels={
            "grupo": "Grupo",
            "n_registros": "Registros",
            "participacion": "Participación",
            "participacion_acumulada": "Participación acumulada",
        },
        description="Grupos ordenados de mayor a menor cantidad de registros.",
    )
    figura = core.FigureArtifact(
        figure_id="fig-concentracion-por-grupo",
        title="Qué parte de los registros aporta cada grupo",
        spec=core.FigureSpec(
            chart_type="bar",
            x="grupo",
            y=("participacion",),
            sort="descending",
            x_label="Grupo",
            y_label="Participación en el total",
            unit="proporción (0 a 1)",
        ),
        backing_table_id="concentracion_por_grupo",
        description="Barras con la participación de cada grupo, de mayor a menor.",
        alt_text="Gráfico de barras: participación de cada grupo en el total de registros.",
    )
    primero = filas[0]
    dos_primeros = filas[1][3]
    ultimo = filas[-1]
    insight = core.Insight(
        insight_id="ins-concentracion-grupos",
        title="Participación de los grupos más grandes",
        technical_claim=(
            f"{primero[0]} aporta {primero[2]:.1%} de los registros y los dos grupos más "
            f"grandes juntos acumulan {dos_primeros:.1%}."
        ),
        business_claim=(
            f"Los grupos no aportan lo mismo al total: {primero[0]} tiene {primero[1]} "
            f"registros y {ultimo[0]} tiene {ultimo[1]}."
        ),
        evidence_refs=("concentracion_por_grupo", "fig-concentracion-por-grupo"),
        population=_POBLACION,
        time_scope=_PERIODO,
        claim_type="descriptive",
        uncertainty=(
            f"El grupo más chico ({ultimo[0]}) tiene {ultimo[1]} registros: las proporciones "
            "de grupos con pocos registros son menos precisas."
        ),
    )
    return core.Chapter(
        chapter_id="concentration",
        title="Concentración por grupo",
        summary="Qué proporción del total aporta cada grupo.",
        tables=(tabla,),
        figures=(figura,),
        insights=(insight,),
        method_note="Participación = registros del grupo / total de registros.",
        metadata={"eda_block": "concentration"},
    )


def _capitulo_poblacion(registros: list) -> core.Chapter:
    n = len(registros)
    con_medida = sum(1 for r in registros if r["medida"] is not None)
    excluidos = n - con_medida
    fechas = sorted(r["fecha_evento"] for r in registros)
    filas = [
        ("Unidad de análisis", "Un registro sintético por fila (record_id)"),
        ("Registros totales", str(n)),
        ("Registros con medida informada", str(con_medida)),
        ("Registros sin medida (excluidos solo del resumen de la medida)", str(excluidos)),
        ("Primera fecha de evento", fechas[0]),
        ("Última fecha de evento", fechas[-1]),
        ("Denominador de las tasas", "Registros del grupo o del mes, sin exclusiones"),
    ]
    tabla = core.TableArtifact.from_rows(
        table_id="poblacion_y_unidad",
        title="Unidad de análisis y población cubierta",
        columns=("aspecto", "detalle"),
        rows=filas,
        column_labels={"aspecto": "Aspecto", "detalle": "Detalle"},
        description="Define qué es una fila y qué registros entran en cada cálculo del informe.",
    )
    insight = core.Insight(
        insight_id="ins-poblacion-unidad",
        title="Cada fila es un registro y todos entran en los conteos",
        technical_claim=(
            f"La unidad de análisis es el registro; los conteos y tasas usan los {n} registros. "
            f"El resumen de la medida excluye {excluidos} registros sin medida informada "
            f"({con_medida} tienen medida). Las fechas van de {fechas[0]} a {fechas[-1]}."
        ),
        business_claim=(
            "Las cifras por grupo y por mes incluyen todos los registros; solo el resumen de "
            f"la medida deja afuera los {excluidos} registros sin medida."
        ),
        evidence_refs=("poblacion_y_unidad",),
        population=_POBLACION,
        time_scope=_PERIODO,
        claim_type="descriptive",
    )
    return core.Chapter(
        chapter_id="population_and_unit",
        title="Qué se está analizando",
        summary="Unidad de análisis, población cubierta y denominadores usados.",
        tables=(tabla,),
        insights=(insight,),
        metadata={"eda_block": "population_and_unit"},
    )


# --- Evaluaciones -------------------------------------------------------------------------


def _evaluaciones() -> list:
    """Estado declarado de los 11 bloques del catálogo (razones distintas entre sí)."""
    return [
        eda.BlockEvaluation("data_quality", "applicable"),
        eda.BlockEvaluation("univariate", "applicable"),
        eda.BlockEvaluation(
            "bivariate_target",
            "applicable",
            limitations="Solo tasa por grupo; no se midió asociación con otras variables.",
        ),
        eda.BlockEvaluation(
            "multivariate",
            "omitted",
            "Hay una sola variable numérica, así que no existe estructura conjunta entre "
            "variables continuas que estudiar",
        ),
        eda.BlockEvaluation(
            "temporal",
            "applicable",
            limitations="Conteo mensual descriptivo; sin prueba formal de tendencia.",
        ),
        eda.BlockEvaluation("concentration", "applicable"),
        eda.BlockEvaluation(
            "segmentation",
            "omitted",
            "El ejemplo prioriza mostrar la estructura del informe y no busca perfiles de "
            "grupos más allá de los ya definidos",
        ),
        eda.BlockEvaluation(
            "entity_relations",
            "not_applicable",
            "Existe una única tabla, sin otras entidades ni claves foráneas que relacionar",
        ),
        eda.BlockEvaluation(
            "process_cycles",
            "not_applicable",
            "Cada registro es un evento único, sin estados ni etapas sucesivas que permitan "
            "medir duraciones",
        ),
        eda.BlockEvaluation(
            "leakage_review",
            "omitted",
            "El ejemplo es exploratorio y sintético: no hay proceso real ni momento de "
            "decisión cuya disponibilidad temporal revisar",
        ),
        eda.BlockEvaluation("population_and_unit", "applicable"),
    ]


# --- API pública -----------------------------------------------------------------------------


def build_example_report() -> core.Report:
    """Arma el reporte EDA de ejemplo, 100% sintético y determinista."""
    registros = _generar_registros(RANDOM_STATE)
    n_total = len(registros)
    n_sin_medida = sum(1 for r in registros if r["medida"] is None)
    capitulos = (
        _capitulo_calidad(registros),
        _capitulo_univariado(registros),
        _capitulo_bivariado(registros),
        _capitulo_temporal(registros),
        _capitulo_concentracion(registros),
        _capitulo_poblacion(registros),
    )
    return eda.build_eda_report(
        report_id="eda-registros-sinteticos",
        title="Exploración de registros sintéticos",
        decision_scope="exploratory",
        chapters=capitulos,
        evaluations=_evaluaciones(),
        target="resultado",
        time_column="fecha_evento",
        summary=(
            f"Exploración de {len(registros)} registros sintéticos de 2024: calidad de los datos, "
            "comportamiento de la medida, resultado por grupo, evolución mensual y concentración."
        ),
        conclusion=(
            f"La medida tiene {n_sin_medida} valores faltantes de {n_total} registros "
            f"({n_sin_medida / n_total:.2%}). Las diferencias entre grupos son descriptivas y "
            "exploratorias: no prueban causas ni deben usarse para elegir variables de un "
            "modelo. Los datos de este ejemplo son inventados."
        ),
        metadata={"origen": "sintetico", "random_state": RANDOM_STATE},
    )
