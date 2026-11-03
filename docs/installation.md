# Instalacion

Esta guia describe como instalar Harmessi en un proyecto existente, verificar la
instalacion, actualizarla y recuperarla. Todo lo que figura aca sale del codigo y
del `README.md` del repositorio; lo que no se pudo observar se marca como limite.

## Requisitos

- Python 3.9 o superior es el minimo declarado (`VERSION_PYTHON_MINIMA = (3, 9)` en
  `tools/harmessi/doctor.py`); 3.9 no se ejecuta (no esta en CI ni se uso en la
  verificacion). Python 3.12 es la version verificada (CI en ubuntu, windows y macos,
  sobre una lista acotada de tests).
- Git.
- Un repositorio destino que sea un repo Git y tenga el working tree limpio.

Harmessi no tiene `pyproject.toml` ni `requirements.txt`: los CLIs usan la
biblioteca estandar. `ds_profile` solo necesita `pyarrow` si se perfilan archivos
Parquet (opcional; sin el, sale con codigo 3 y un mensaje claro).

## Instalar con `ds_init`

El instalador se ejecuta desde un checkout de Harmessi, no desde el proyecto destino.

```bash
git clone https://github.com/federcolombo/harmessi.git
cd harmessi
python -m venv .venv
.venv/Scripts/activate        # Windows (PowerShell: .venv\Scripts\Activate.ps1)
# source .venv/bin/activate    # macOS/Linux

# Ver el plan sin tocar nada (comportamiento por defecto):
python -m tools.ds_init --destino /ruta/a/tu/proyecto --nombre mi-proyecto

# Aplicarlo de verdad:
python -m tools.ds_init --destino /ruta/a/tu/proyecto --nombre mi-proyecto --execute
```

Acciones posicionales: `install` (por defecto), `sync`, `migrate-hashes`,
`upgrade`, `recover`. Opciones relevantes: `--destino` (obligatoria),
`--nombre` (obligatoria para `install`), `--notebooks-dir`, `--venv-dir`,
`--integrar-claude`, `--stage {discovery,experiment,production_candidate,production}`,
`--dry-run` (defecto) y `--execute`. Detalle en [cli-reference.md](cli-reference.md).

Desde 1.0.0 la instalacion incluye el asset managed `HARMESSI-LICENSE.txt`, con los
terminos y el aviso de los componentes de Harmessi (PolyForm Shield 1.0.0); no
relicencia tu proyecto. En un `upgrade` desde 0.15 el asset es una entrada nueva del
manifiesto y se crea como managed. Si luego lo borras a mano, `upgrade` no lo recrea
(queda como preservado: ausente del disco pero en el baseline); restauralo desde Git.

- `install --stage discovery` instala un bundle liviano; `experiment` (defecto)
  agrega el stack completo de agentes.
- `sync --stage <objetivo>` amplia un destino ya instalado hacia un stage mayor;
  es idempotente, no sobrescribe ni borra archivos.
- `--execute` escribe de forma atomica: valida el arbol staged completo antes de
  moverlo al destino y, ante una excepcion, revierte lo aplicado.

## Doctor: verificar una instalacion

Doctor es de solo diagnostico y corre **desde un checkout de Harmessi**, apuntando
al proyecto con `--destino`:

```bash
python -m tools.harmessi doctor --destino /ruta/a/tu/proyecto
```

Imprime una linea `[OK]` / `[WARN]` / `[ERROR]` por chequeo, agrupadas en `CORE`,
`HARMESSI` y `RUNTIME`, con un resumen. Sale con `0` si no hay `[ERROR]` y con `1`
en caso contrario. No repara nada.

### Por que Doctor no existe en el proyecto instalado

Un proyecto instalado **no incluye `tools/harmessi` ni `tools/ds_init`**: el
`MANIFEST` de `tools/ds_init/manifest.py` solo lista las rutas que se copian al
destino (agentes, skills, `tools/ds_guard.py`, `tools/dsguard/`, etc.), y esos dos
paquetes no estan entre ellas. Por eso `python -m tools.harmessi doctor` dentro del
proyecto instalado no funciona; hay que correrlo desde el checkout con `--destino`.
Lo mismo aplica a `ds_init` (`install`, `sync`, `upgrade`, `recover`).

## Actualizar (`upgrade`)

```bash
python -m tools.ds_init upgrade --destino <ruta>             # dry-run (defecto)
python -m tools.ds_init upgrade --destino <ruta> --execute   # aplicar
```

`upgrade` lleva un proyecto instalado a la version actual del harness. Solo
actualiza archivos managed que siguen intactos (coinciden con su baseline
registrado), crea los managed nuevos del manifest, y fusiona `settings.json`. No
toca archivos del proyecto (notebooks, datos, Cards, Data Contracts, ledger de
decisiones, enmiendas, `GLOSSARY.md`, aprobaciones en
`openspec/changes/**/control.json`), no sobrescribe un `guardrails.json` existente
y reporta los archivos con drift sin tocarlos. Es idempotente; sin nada pendiente
imprime "Nada que hacer" y sale con 0.

Ventana de compatibilidad (`docs/versioning.md`): desde v0.15 se soporta la lectura
de artefactos de la version actual y las dos menores previas (0.15, 0.14 y 0.13),
limitada a artefactos con test. Los artefactos `harmessi_improve` tienen ventana
0.14-0.15. Lo anterior a la ventana se lee por mejor esfuerzo, sin promesa. La
politica de deprecacion esta en `docs/deprecation.md`.

Limites: no hay downgrade ni migracion de datos; `upgrade` no recrea un managed
que borraste a mano (restauralo desde Git).

## Recuperacion (`recover`)

```bash
python -m tools.ds_init recover --destino <ruta>             # dry-run (defecto)
python -m tools.ds_init recover --destino <ruta> --execute   # revertir
```

Si el proceso se interrumpe (kill, corte de energia) pueden quedar un directorio
`.ds_init_staging_<timestamp>/` y un journal `.ds_init/journal/<timestamp>/`.
`install`, `sync` y `upgrade` lo detectan y se niegan a seguir, apuntando a
`recover`. `recover` revierte al ultimo estado consistente (solo rollback, nunca
roll-forward). Con `--forzar` revierte tambien un archivo editado despues de la
interrupcion y guarda tu copia como `<ruta>.recover-bak`.

## Troubleshooting

Solo se listan situaciones documentadas en el `README.md` o presentes en el codigo.

| Situacion | Que significa / que hacer |
|---|---|
| `ds_init` se niega a continuar y apunta a `recover` | Quedo un staging o journal huerfano de una corrida interrumpida. Correr `recover --destino <ruta>` (y luego `--execute`). |
| `recover` sale con codigo 2 y muestra pasos manuales | Journal ilegible, backup faltante, ruta de journal invalida, o un archivo a revertir fue editado tras la interrupcion (usar `--forzar` solo si aceptas ese resultado). No toca nada. |
| Queda `.ds_init/lock` tras un kill | El lock es cooperativo y no se detecta el pid a proposito: borrarlo a mano solo si no hay ningun proceso `ds_init` vivo. |
| Doctor: `HARMESSI-VERSION` en WARN | El proyecto esta en una version anterior; el remedio es `upgrade`. |
| Doctor: `HARMESSI-MIGRACION` en FAIL / WARN | FAIL: hay staging o journal parcial (usar `recover`). WARN: lock sobrante o journal completo. |
| `ds_profile` sale con codigo 3 | Se pidio un Parquet y `pyarrow` no esta instalado. |
| `ds_guard impact scan` sale con codigo 3 | Instalacion `discovery`: `tools/dsimpact/` no esta presente. |
| `python -m tools.harmessi doctor` no funciona en el proyecto | Esperado: Doctor no se instala. Correrlo desde el checkout con `--destino`. |

Codigos de salida generales de `ds_guard`: ver [cli-reference.md](cli-reference.md).

## Limites

La ejecucion de la suite de tests se observo solo en Windows. Linux y macOS no
estan validados por ejecucion. Ver `docs/portability.md`.
