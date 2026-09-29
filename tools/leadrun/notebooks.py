"""Runtime de ejecución de notebooks del Lead (v0.8 Change 2,
`20260929-lead-execution-runtime`, T3).

Módulo de I/O que **compone** `tools.nbrunner.{core,execute,fsdiff,manifest}`
(R1/R11 de `spec.md`): no reimplementa ninguna validación previa a ejecución,
ni el motor de ejecución (`nbclient`), ni el diff de filesystem/cuarentena —
todo eso vive en `tools/nbrunner/` y se reusa tal cual, por import directo.
`tools.nbrunner.execute` importa `nbformat`/`nbclient` a nivel de módulo
(dependencias opcionales del stage `experiment`, mismo caso que `ds_profile`
en `tools/datasources/file_observer.py`, Change 1): se importa acá de forma
PEREZOSA, dentro de `ejecutar_manifest`, solo en el punto donde realmente se
ejecuta un notebook (`modo == "execute"` sin Findings bloqueantes), para que
importar este módulo -- y validar un manifest en `--dry-run` -- no requiera
tenerlas instaladas.
Dirección de dependencias: `tools.leadrun.notebooks` -> `tools.nbrunner.*`
(nunca al revés, R1/R2 de `spec.md`); además importa `tools.leadrun.core`
(relativo) para el catálogo de errores propio del paquete y
`tools.launcher_common` -- MISMO mecanismo ya usado por
`tools/nbrunner/hook_launcher.py`, `tools/dsguard/hook_presupuesto.py` y
`tools/harmessi/doctor.py` (`resolver_venv_dir`, lee
`<repo_root>/.ds_init/control.json`, default `.venv` si está ausente/corrupto
-- `tools/launcher_common.py:31-50`) para resolver el `.venv` real del
proyecto y así poder llamar a `manifest.validar_interprete` sin reinventar
esa resolución (el encargo pide explícitamente reusar "el mismo mecanismo que
ya usa el resto del repo, no inventar uno nuevo").

`tools/nbrunner/manifest.py`/`core.py` importan `dsguard.*` como paquete de
nivel superior (no `tools.dsguard.*`), así que requieren que el directorio
`tools/` esté en `sys.path` (mismo patrón documentado en
`tools/nbrunner/core.py:12-14` y replicado por
`tools/tests/test_harness_smoke.py:18-23`) -- este módulo lo garantiza él
mismo, antes de importar cualquier submódulo de `nbrunner`, para no depender
de que algún otro módulo ya lo haya hecho antes en el mismo proceso.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from tools.nbrunner import core as nbcore  # noqa: E402
from tools.nbrunner import fsdiff as nbfsdiff  # noqa: E402
from tools.nbrunner import manifest as nbmanifest  # noqa: E402
from tools import launcher_common  # noqa: E402

from . import core as leadrun_core  # noqa: E402,F401 -- reexportado para catálogo de errores propio

# Destino de cuarentena para salidas fuera de contrato (decisión de este
# módulo, no de `tools/nbrunner/fsdiff.py`, que recibe el destino como
# parámetro y no fija ninguna convención propia): un subdirectorio por
# manifest bajo `.harmessi/quarantine/`, análogo a `.harmessi/quality/` ya
# usado por `tools/qualityevidence` (`tools/ds_guard.py:108`, resumen de
# evidencia bajo `.harmessi/quality/`) -- mismo prefijo `.harmessi/` para
# artefactos operativos generados localmente, no versionados.
DIRECTORIO_CUARENTENA_BASE = ".harmessi/quarantine"


def _destino_cuarentena(repo_root: Path, manifest_path: Path) -> Path:
    return repo_root / DIRECTORIO_CUARENTENA_BASE / manifest_path.stem


def _artefacto_de_manifest(manifest_path: Path, repo_root: Path) -> str:
    """Identificador de `artefacto` usado en `control.json` (mismo campo que
    `aprobaciones[].artefacto`, `tools/dsguard/sdd.py:224-225`): la ruta del
    manifest relativa a `repo_root`, en POSIX, para que sea estable sin
    importar el separador de rutas del SO desde el que se invoque el CLI."""
    try:
        relativa = manifest_path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        relativa = manifest_path
    return relativa.as_posix()


def ejecutar_manifest(manifest_path, repo_root, control_data: dict, modo: str) -> dict:
    """Ejecuta la secuencia R11 (`spec.md`) sobre el manifest en
    `manifest_path`. NO imprime nada (separación lógica/IO, R11 del encargo):
    el llamador (`tools/notebook_runner.py`) es responsable de imprimir e
    interpretar el exit code.

    `modo` es `"dry_run"` o `"execute"` (mismo vocabulario que
    `manifest.validar_aprobacion`).

    Devuelve un dict::

        {
            "ok": bool,
            "findings": [dict, ...],  # Finding.to_dict() de cargar_manifest/
                                       # validar_interprete/validar_hash_notebook/
                                       # validar_rutas_prohibidas/validar_aprobacion
            "estado_aprobacion": "vigente"|"ausente"|"desincronizada"|"no_verificada",
            "ejecutado": bool,
            "resultado_ejecucion": Optional[dict],  # campos relevantes de
                                                      # execute.ResultadoEjecucion
                                                      # (no tiene to_dict(), se
                                                      # proyectan a mano acá)
            "fsdiff": Optional[dict],  # {"permitidos": [...], "fuera_de_contrato": [...],
                                        #  "cuarentena": [...]}
        }

    Secuencia (R11, ya fijada por `spec.md`, no se reordena acá):

    1. `manifest.cargar_manifest(manifest_path)` -- si lanza
       `ManifestInvalidoError`, se traduce a un `Finding` propio
       (`NBRUNNER-MANIFEST-INVALIDO`) y se corta acá: `ok=False`,
       `ejecutado=False`, sin ninguna otra validación.
    2. `manifest.validar_interprete` / `validar_hash_notebook` /
       `validar_rutas_prohibidas` -- se acumulan TODOS los `Finding`
       (no se corta en el primero), porque no dependen entre sí.
    3. `manifest.validar_aprobacion(control_data, artefacto, hash_manifest, modo)`
       -- `artefacto` es la ruta del manifest relativa a `repo_root` (POSIX,
       `_artefacto_de_manifest`), `hash_manifest` es `hash_lf_v1` del propio
       archivo de manifest (mismo algoritmo `sha256/lf/v1` que el resto del
       repo usa para `proposal.md`/`design.md`/`tasks.md`,
       `tools/dsguard/sdd.py:275`).
    4. Si `modo == "dry_run"`: nunca ejecuta (`ejecutado=False`); `ok` refleja
       únicamente si hubo `Finding`s bloqueantes en el paso 2 (la aprobación
       en `dry_run` nunca bloquea, ya lo garantiza `validar_aprobacion`).
    5. Si `modo == "execute"`: si hubo `Finding`s en el paso 2, o
       `estado_aprobacion` es `"ausente"`/`"desincronizada"`, NO ejecuta
       (`ok=False`, `ejecutado=False`). Si todo OK: snapshot antes
       (`fsdiff.snapshot`), `execute.ejecutar_notebook`, snapshot después,
       `fsdiff.diferencia`/`clasificar`, y cuarentena
       (`fsdiff.cuarentena`) de lo fuera de contrato, bajo
       `_destino_cuarentena(repo_root, manifest_path)`
       (`.harmessi/quarantine/<manifest_stem>/`, decisión de este módulo,
       documentada arriba). `ok` es `True` solo si
       `resultado_ejecucion.exit_ok` es `True` **y** no quedó nada en
       cuarentena (una salida fuera de contrato es, por decisión de este
       módulo, un fallo de la corrida -- no solo información -- porque
       implica que el notebook escribió o borró algo que el manifest no
       declaró, lo mismo que el propio manifest existe para prevenir).
    """
    if modo not in ("dry_run", "execute"):
        raise ValueError(f"modo inválido: {modo!r} (se esperaba 'dry_run' o 'execute')")

    manifest_path = Path(manifest_path)
    repo_root = Path(repo_root)

    resultado: dict = {
        "ok": False,
        "findings": [],
        "estado_aprobacion": "no_verificada",
        "ejecutado": False,
        "resultado_ejecucion": None,
        "fsdiff": None,
    }

    # 1. cargar_manifest -- si falla, se corta acá, sin ninguna otra validación.
    try:
        datos = nbmanifest.cargar_manifest(manifest_path)
    except nbmanifest.ManifestInvalidoError as exc:
        resultado["findings"] = [
            nbcore.Finding(
                "NBRUNNER-MANIFEST-INVALIDO",
                str(exc),
                str(manifest_path),
            ).to_dict()
        ]
        return resultado

    # 2. validar_interprete / validar_hash_notebook / validar_rutas_prohibidas.
    venv_dir = launcher_common.resolver_venv_dir(repo_root)
    venv_path = repo_root / venv_dir
    notebook_ruta_abs = repo_root / datos["notebook"]["ruta"]

    findings_previos = []
    findings_previos.extend(nbmanifest.validar_interprete(datos["interprete"], venv_path))
    findings_previos.extend(
        nbmanifest.validar_hash_notebook(notebook_ruta_abs, datos["notebook"]["hash_aprobado"])
    )
    findings_previos.extend(
        nbmanifest.validar_rutas_prohibidas(datos["entradas_permitidas"], datos["salidas_permitidas"])
    )
    resultado["findings"].extend(f.to_dict() for f in findings_previos)
    hubo_bloqueo_previo = len(findings_previos) > 0

    # 3. validar_aprobacion.
    artefacto = _artefacto_de_manifest(manifest_path, repo_root)
    hash_manifest = nbcore.hash_lf_v1(manifest_path)
    findings_aprobacion, estado_aprobacion = nbmanifest.validar_aprobacion(
        control_data, artefacto, hash_manifest, modo
    )
    resultado["estado_aprobacion"] = estado_aprobacion
    resultado["findings"].extend(f.to_dict() for f in findings_aprobacion)

    # 4. dry_run: nunca ejecuta.
    if modo == "dry_run":
        resultado["ok"] = not hubo_bloqueo_previo
        return resultado

    # 5. execute: si hubo bloqueo previo o la aprobación bloquea, no ejecuta.
    if hubo_bloqueo_previo or estado_aprobacion in ("ausente", "desincronizada"):
        resultado["ok"] = False
        resultado["ejecutado"] = False
        return resultado

    # `tools.nbrunner.execute` importa `nbformat`/`nbclient` a nivel de
    # módulo (dependencias del stage `experiment`, no del core): import
    # PEREZOSO acá, solo alcanzable en `modo == "execute"` sin Findings
    # bloqueantes, para no requerirlas solo para validar un manifest en
    # `--dry-run` -- mismo criterio que `ds_profile` en
    # `tools/datasources/file_observer.py` (Change 1).
    try:
        from tools.nbrunner import execute as nbexecute
    except ModuleNotFoundError as exc:
        resultado["ejecutado"] = False
        resultado["ok"] = False
        resultado["resultado_ejecucion"] = {
            "exit_ok": False,
            "error_info": (
                "ejecutar_manifest: faltan las dependencias de ejecución de "
                "notebooks ('nbformat'/'nbclient'). Corré "
                "'ds_init sync --stage experiment' para instalarlas."
            ),
        }
        resultado["_error_dependencias"] = str(exc)
        return resultado

    entradas_permitidas = list(datos["entradas_permitidas"])
    salidas_permitidas = list(datos["salidas_permitidas"])

    antes = nbfsdiff.snapshot(repo_root, entradas_permitidas + salidas_permitidas)
    resultado_ejecucion = nbexecute.ejecutar_notebook(
        notebook_ruta_abs,
        datos["timeout_segundos"],
        cwd=repo_root,
    )
    despues = nbfsdiff.snapshot(repo_root, entradas_permitidas + salidas_permitidas)
    diff = nbfsdiff.diferencia(antes, despues)
    permitidos, fuera_de_contrato = nbfsdiff.clasificar(diff, salidas_permitidas)

    movidos: list = []
    if fuera_de_contrato:
        destino = _destino_cuarentena(repo_root, manifest_path)
        movidos = nbfsdiff.cuarentena(repo_root, fuera_de_contrato, destino)

    resultado["ejecutado"] = True
    resultado["resultado_ejecucion"] = {
        "exit_ok": resultado_ejecucion.exit_ok,
        "duracion_segundos": resultado_ejecucion.duracion_segundos,
        "stdout_resumen": resultado_ejecucion.stdout_resumen,
        "stderr_resumen": resultado_ejecucion.stderr_resumen,
        "timeout_alcanzado": resultado_ejecucion.timeout_alcanzado,
        "posible_proceso_huerfano": resultado_ejecucion.posible_proceso_huerfano,
        "error_info": resultado_ejecucion.error_info,
    }
    resultado["fsdiff"] = {
        "permitidos": permitidos,
        "fuera_de_contrato": fuera_de_contrato,
        "cuarentena": [str(p) for p in movidos],
    }
    # Una salida fuera de contrato es, por decisión de este módulo (ver
    # docstring), un fallo de la corrida -- no solo información.
    resultado["ok"] = bool(resultado_ejecucion.exit_ok) and not fuera_de_contrato

    return resultado
