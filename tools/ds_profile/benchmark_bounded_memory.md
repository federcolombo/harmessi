# Benchmark manual: `ds_profile` con memoria acotada (NO gateado)

Reproduce aproximadamente el caso real del feedback de Harmessi 0.8.0 (Parquet de ~620 k filas × 27 columnas, ~20 MB comprimido) sin versionar
datos. Requiere `pyarrow` (el benchmark genera el Parquet en un directorio temporal). Se ejecuta a mano desde la raíz del repo:

```
python benchmark_bounded_memory.py   # guardá el script de abajo con ese nombre
```

Qué esperar con los defaults (`--max-mb-exactos 500`):

- `sampling.activo = true`, `sampling.motivo = "memoria_estimada"` (620 570 × 27 × 96 B ≈ 1,6 GB > 500 MiB), decidido antes de leer filas.
- `sampling.tamano_muestra` ≤ 200 000; `filas_observadas = 620570`.
- `nulls`, `min/max`, `media/std`, `dtype` exactos; `unique`, `top_valores`, `mediana`, `cuantiles` y `duplicados_fila` marcados `muestreada`.
- Pico de `tracemalloc` acotado por la muestra (el valor exacto depende de la plataforma y NO es un criterio de aceptación).

`BYTES_POR_CELDA = 96` es una estimación conservadora de orden de magnitud, no un tope duro: con strings largos el uso real puede exceder el
presupuesto; si la memoria es una preocupación, bajá `--max-mb-exactos`.

## Script

```python
import sys, time, tracemalloc, tempfile, random
from pathlib import Path
import pyarrow as pa, pyarrow.parquet as pq
sys.path.insert(0, ".")
from tools.ds_profile import report

N, C = 620_570, 27
rnd = random.Random(0)
cols = {}
for j in range(C):
    if j % 3 == 0: cols[f"c{j}"] = [rnd.randint(0, 10**6) for _ in range(N)]
    elif j % 3 == 1: cols[f"c{j}"] = [rnd.random() * 100 for _ in range(N)]
    else: cols[f"c{j}"] = [f"cat{rnd.randint(0, 5000)}" for _ in range(N)]
tmp = Path(tempfile.mkdtemp())
ruta = tmp / "caso_real.parquet"
pq.write_table(pa.table(cols), ruta, row_group_size=50_000)
print("parquet MB:", round(ruta.stat().st_size / 1e6, 1))
del cols
tracemalloc.start()
t = time.time()
perfil = report.generar_perfil(ruta, tmp / "out")["perfil"]
pico = tracemalloc.get_traced_memory()[1] / 1e6
print("segundos:", round(time.time() - t, 1), "| pico tracemalloc MB:", round(pico, 1))
print("sampling:", perfil["sampling"])
```

## Medición de referencia (2026-10-07, Windows 11, Python 3.12, pyarrow 20)

El script completo (620 570 × 27) no terminó en ~40 min con `tracemalloc` activo (costo por celda del parseo de fechas, anterior a este Change)
y se abortó; no es un criterio de aceptación. Medición reducida, Parquet de 40 000 × 27 (1,08 M celdas), `tracemalloc`:

| Modo | `--max-mb-exactos` | Pico `tracemalloc` | `sampling` |
|---|---|---|---|
| exacto | 500 | 57,0 MB (≈ 53 B/celda, bajo la estimación de 96) | `activo=false` |
| muestreado | 2 | 18,2 MB | `activo=true`, `motivo=tamano_archivo`, `tamano_muestra=1000` |

La memoria del modo muestreado depende de `tamano_muestra × columnas`, no de las filas totales.
