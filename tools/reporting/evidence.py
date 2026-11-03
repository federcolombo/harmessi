"""Evidencia persistida de reportes (v0.6 Change 3, `20260918-report-evidence-and-validation`).

Serializa un `Report` a un directorio de artefactos (una sola copia de cada
tabla/figura/insight), arma el manifest con hashes de los BYTES PERSISTIDOS,
lo relee (`load_report_dir`) y ofrece el aislamiento por hash contra artefactos
exploratory (`REPORT-ISOLATION-HASH`).

Solo importa stdlib, `reporting.core`, `reporting.governance`, `dsguard.*` y
`ds_profile.fingerprint`. Sin pandas/Plotly/HTML/red. Levantan `EvidenceError`:
`describe_source`, `describe_generated_source`, `write_report_dir` (rutas
inseguras), `read_within`, `read_report_dir`, `report_from_bytes`,
`load_report_dir` y `build_manifest` (solo por un `source_notebook` inválido);
los checks, `read_allowed` y `resolve_*` nunca lanzan. Este modulo NO decide
permisos de ESCRITURA (guard de governance/publish).

Invariante de lectura: cuando se pasa `repo_root` (`describe_source`,
`check_inputs_hash_isolation`, `exploratory_index_status`, y
`read_within`/`read_report_dir`/`load_report_dir` con `repo_root=`), la funcion
evalua ANTES `read_allowed` (mismo evaluador que el hook: secretos, holdouts
con/sin excepcion vigente, fuera del repo, `guardrails.json` corrupto =>
denegado) y no abre lo denegado. Sin `repo_root`, `read_within`,
`read_report_dir` y `load_report_dir` son uso local explicito y NO evaluan
acceso: el `publish` del Change 4 DEBE usar el camino con `repo_root`.
`resolve_harmessi_version` lee `.ds_init/control.json` (config del harness, no
datos) sin `read_allowed`, por diseño.

Limites honestos (spec R24):
- `read_allowed` recarga `guardrails.json` en cada llamada (costo, no correctitud).
- Con `out_dir` fuera del repo, la ruta que paso el propio usuario puede
  aparecer como `subject` en resultados de governance; los nombres de archivos
  dentro de un holdout pueden aparecer como `subject` de un FAIL (no se lee su
  contenido).
- La isolation por hash cubre copias byte-identicas, NO derivados.
- El indice exploratory depende de manifests existentes bajo el root
  exploratory de la policy; sin manifests no hay nada que comparar.
- Los sha256 son AUTOATESTADOS: prueban integridad frente a corrupcion o
  edicion parcial, no autoria ni aprobacion; quien reescribe de forma
  consistente artefactos Y manifest no es detectable.
- TOCTOU: entre `read_allowed` y la lectura, o entre hashear una fuente y usarla,
  el archivo puede cambiar; las lecturas son single-read pero no atomicas
  respecto del sistema de archivos.
- Un PASS de este modulo no significa que la evidencia sea adecuada.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

_TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from dsguard import checks, pathguard  # noqa: E402
from dsguard import core as dsguard_core  # noqa: E402
from dsguard import repo as repo_mod  # noqa: E402
from ds_profile import fingerprint as _fingerprint  # noqa: E402

from . import core as reporting_core  # noqa: E402
from . import governance  # noqa: E402

# --- Constantes ---------------------------------------------------------------

MANIFEST_SCHEMA_VERSION = 1
ALGORITHM = _fingerprint.ALGORITMO  # "sha256/bin/v1"

HOLDOUT_ACCESS_VALUES = ("none", "read")
ARTIFACT_KINDS = ("table", "figure", "report", "insights")
SOURCE_KINDS = ("file", "generated")

MANIFEST_FILENAME = reporting_core.MANIFEST_FILENAME
INSIGHTS_FILENAME = reporting_core.INSIGHTS_FILENAME
ARTIFACTS_DIRNAME = reporting_core.ARTIFACTS_DIRNAME
REPORT_JSON_PATH = f"{ARTIFACTS_DIRNAME}/report.json"
TABLES_DIR = f"{ARTIFACTS_DIRNAME}/tables"
FIGURES_DIR = f"{ARTIFACTS_DIRNAME}/figures"

# Cotas (fail-closed: superarlas es FAIL technical_error, nunca PASS).
MAX_DIRS_SCAN = 2000  # directorios recorridos bajo el root exploratory
MAX_FILES_HASH = 500  # archivos de input considerados por check
_MAX_MANIFEST_BYTES = 16 * 1024 * 1024  # manifest mas grande => cuenta como ilegible

CODE_ISOLATION_HASH = "REPORT-ISOLATION-HASH"

_SCOPE_EXPLORATORY = "exploratory"
_SCOPES_FLUJO_MODELO = ("model_valid", "operational")
_RE_SHA256 = re.compile(r"[0-9a-fA-F]{64}")
_RE_COMMIT = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_PROFUNDIDAD_MAX_JSON = 50
_ATRIBUTO_REPARSE_POINT = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT (symlinks/junctions en Windows)
_RESERVADOS_WINDOWS = frozenset(
    ["con", "prn", "aux", "nul"]
    + [f"com{i}" for i in range(1, 10)]
    + [f"lpt{i}" for i in range(1, 10)]
)

_AUTO: Any = object()  # sentinela: "resolver automaticamente"


class EvidenceError(Exception):
    """Error de evidencia: fuente inexistente/fuera del repo/sin acceso, params
    no JSON-seguros, directorio de reporte incompleto, corrupto o inseguro."""


@dataclass(frozen=True)
class ExploratoryIndex:
    """Estado del indice exploratory. `truncated`: se supero `MAX_DIRS_SCAN`;
    `error`: policy/repo/recorrido con error (`None` si no); `unreadable_manifests`:
    `manifest.json` ilegibles, demasiado grandes, sin acceso o de forma invalida."""

    index: dict = field(default_factory=dict)
    truncated: bool = False
    error: Optional[str] = None
    unreadable_manifests: int = 0


# --- Acceso de lectura (invariante: se evalua ANTES de abrir) ------------------


def _cargar_guardrails(repo: Path) -> tuple:
    """`(config|None, motivo|None)`. Fail-closed: guardrails corrupto => `(None, motivo)`."""
    try:
        return pathguard.cargar_config(repo), None
    except pathguard.ConfigGuardrailsError:
        return None, "guardrails.json ilegible o inválido (fail-closed)"
    except Exception:  # noqa: BLE001 -- fail-closed
        return None, "no se pudo cargar guardrails.json (fail-closed)"


def _evaluar_lectura(config: Any, motivo_config: Optional[str], repo: Path, path: Any) -> tuple:
    """`(permitido, motivo)` con un `config` ya cargado. Nunca lanza."""
    try:
        if config is None:
            return False, motivo_config or "guardrails.json no disponible (fail-closed)"
        if not isinstance(path, (str, Path)) or str(path) == "" or "\x00" in str(path):
            return False, "ruta inválida"
        relativa, dentro = pathguard.resolver_ruta_relativa(str(path), repo)
        if not dentro:
            return False, "ruta fuera del repositorio o no resoluble"
        permitido, motivo = pathguard.evaluar_tool_call(
            {"tool_name": "Read", "tool_input": {"file_path": relativa}}, config, repo
        )
        return bool(permitido), str(motivo)
    except Exception:  # noqa: BLE001 -- fail-closed
        return False, "error evaluando el acceso (fail-closed)"


def read_allowed(repo_root: Any, path: Any) -> tuple:
    """`(permitido, motivo)`: acceso de LECTURA a `path` segun el mismo evaluador
    que el hook (`pathguard.evaluar_tool_call` con `Read`): secretos, holdouts
    con/sin excepcion vigente, fuera del repo, `guardrails.json` corrupto =>
    `(False, motivo)`. Nunca lanza."""
    try:
        repo = Path(repo_root).resolve()
        config, motivo_config = _cargar_guardrails(repo)
        return _evaluar_lectura(config, motivo_config, repo, path)
    except Exception:  # noqa: BLE001 -- fail-closed
        return False, "error evaluando el acceso (fail-closed)"


# --- Helpers privados ---------------------------------------------------------


def _json_bytes(obj: Any) -> bytes:
    """JSON persistido determinista: claves ordenadas, indent 2, sin escapar
    no-ASCII, sin NaN, `\\n` final, UTF-8."""
    texto = json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    return texto.encode("utf-8")


def _sha256_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _es_json_seguro(valor: Any, profundidad: int = 0) -> bool:
    if profundidad > _PROFUNDIDAD_MAX_JSON:
        return False
    if valor is None or isinstance(valor, (bool, int, str)):
        return True
    if isinstance(valor, float):
        return math.isfinite(valor)
    if isinstance(valor, (list, tuple)):
        return all(_es_json_seguro(v, profundidad + 1) for v in valor)
    if isinstance(valor, dict):
        return all(isinstance(k, str) and _es_json_seguro(v, profundidad + 1) for k, v in valor.items())
    return False


def _copia_json(obj: Any) -> Any:
    """Copia normalizada (tuplas -> listas). Si no es serializable, devuelve el
    objeto tal cual (la validacion del manifest lo reportara)."""
    try:
        return json.loads(reporting_core.canonical_json(obj))
    except (reporting_core.ReportingContractError, ValueError, RecursionError):
        return obj


def _ruta_relativa_segura(rel: Any) -> bool:
    """Ruta relativa posix segura: sin `\\`, `:`, absoluta, `.`/`..`/vacios,
    control (`\\x00`), nombres de dispositivo de Windows ni segmentos que
    terminen en punto o espacio."""
    if not isinstance(rel, str) or not rel or "\\" in rel:
        return False
    if rel.startswith("/") or ":" in rel:
        return False
    for seg in rel.split("/"):
        if seg in ("", ".", ".."):
            return False
        if seg.endswith((".", " ")) or any(ord(c) < 32 for c in seg):
            return False
        if seg.split(".")[0].strip().casefold() in _RESERVADOS_WINDOWS:
            return False
    return True


def _unir(base: Path, rel_posix: str) -> Path:
    return base.joinpath(*rel_posix.split("/"))


def _subject_de(repo: Path, ruta: Path) -> str:
    """Ruta relativa al repo (posix); fuera del repo no expone la ruta local."""
    try:
        return ruta.relative_to(repo).as_posix()
    except ValueError:
        return f"<fuera-del-repo>/{ruta.name}"


def _es_enlace(ruta: Path) -> bool:
    """Symlink o reparse point (junction) en Windows."""
    try:
        if ruta.is_symlink():
            return True
        return bool(getattr(os.lstat(ruta), "st_file_attributes", 0) & _ATRIBUTO_REPARSE_POINT)
    except OSError:
        return False


# --- R3 / R4: fuentes ---------------------------------------------------------


def describe_source(
    repo_root: Any,
    path: Any,
    *,
    role: str = "input",
    rows: Optional[int] = None,
    min_date: Optional[str] = None,
    max_date: Optional[str] = None,
    date_column: Optional[str] = None,
) -> dict:
    """Fuente `kind="file"` (path relativo posix, sha256/bin/v1, size_bytes y
    opcionales no nulos). Evalua `read_allowed` ANTES de abrir el archivo
    (denegado => `EvidenceError` "acceso denegado", sin abrirlo). Levanta
    `EvidenceError` si el archivo no existe o resuelve fuera del repo (`..`,
    symlink). Solo lee el archivo para hashearlo."""
    if not isinstance(role, str) or not role.strip():
        raise EvidenceError(f"role debe ser un str no vacío (recibido {role!r})")
    if rows is not None and (isinstance(rows, bool) or not isinstance(rows, int) or rows < 0):
        raise EvidenceError(f"rows debe ser un int >= 0 o None (recibido {rows!r})")
    for nombre, valor in (("min_date", min_date), ("max_date", max_date), ("date_column", date_column)):
        if valor is not None and not isinstance(valor, str):
            raise EvidenceError(f"{nombre} debe ser str o None (recibido {valor!r})")
    if not isinstance(path, (str, Path)) or str(path) == "" or "\x00" in str(path):
        raise EvidenceError("path inválido")
    try:
        repo = Path(repo_root).resolve()
        candidato = Path(path)
        if not candidato.is_absolute():
            candidato = repo / candidato
        resuelto = candidato.resolve()
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        raise EvidenceError(f"no se pudo resolver la fuente ({type(exc).__name__})") from exc
    try:
        relativo = resuelto.relative_to(repo)
    except ValueError as exc:
        raise EvidenceError("la fuente resuelve fuera del repo") from exc
    etiqueta = relativo.as_posix()
    permitido, motivo = read_allowed(repo, resuelto)
    if not permitido:
        raise EvidenceError(f"acceso denegado a la fuente {etiqueta!r} (no se abrió): {motivo}")
    try:
        if not resuelto.is_file():
            raise EvidenceError(f"la fuente {etiqueta!r} no existe o no es un archivo")
        huella = _fingerprint.calcular_fingerprint(resuelto)
        tamano = resuelto.stat().st_size
    except OSError as exc:
        raise EvidenceError(f"no se pudo leer la fuente {etiqueta!r} ({type(exc).__name__})") from exc
    fuente: dict = {
        "kind": "file",
        "role": role,
        "path": etiqueta,
        "sha256": huella["hash"],
        "algorithm": huella["algoritmo"],
        "size_bytes": tamano,
    }
    for clave, valor in (("rows", rows), ("min_date", min_date), ("max_date", max_date), ("date_column", date_column)):
        if valor is not None:
            fuente[clave] = valor
    return fuente


def describe_generated_source(description: Any, params: Any, *, role: str = "input") -> dict:
    """Fuente `kind="generated"`: sha256 de `canonical_json(params)`. Levanta
    `EvidenceError` si `description` es vacía o `params` no es un dict JSON-seguro."""
    if not isinstance(description, str) or not description.strip():
        raise EvidenceError("description debe ser un str no vacío")
    if not isinstance(role, str) or not role.strip():
        raise EvidenceError(f"role debe ser un str no vacío (recibido {role!r})")
    if not isinstance(params, dict) or not _es_json_seguro(params):
        raise EvidenceError("params debe ser un dict JSON-seguro (claves str, floats finitos)")
    try:
        canonico = reporting_core.canonical_json(params)
    except reporting_core.ReportingContractError as exc:
        raise EvidenceError(f"params no serializable: {exc}") from exc
    return {
        "kind": "generated",
        "role": role,
        "description": description,
        "params": json.loads(canonico),
        "algorithm": ALGORITHM,
        "sha256": _sha256_bytes(canonico.encode("utf-8")),
    }


# --- R5: artefactos -----------------------------------------------------------


def expected_artifacts(report: reporting_core.Report) -> dict:
    """`{archivo_relativo: (id, kind)}`: el conjunto EXACTO de archivos que
    `prepare_artifacts` produce (insights, report, cada tabla y figura), en ese orden."""
    esperados: dict = {
        INSIGHTS_FILENAME: ("insights", "insights"),
        REPORT_JSON_PATH: ("report", "report"),
    }
    for tabla in report.iter_tables():
        esperados[f"{TABLES_DIR}/{tabla.table_id}.json"] = (tabla.table_id, "table")
    for figura in report.iter_figures():
        esperados[f"{FIGURES_DIR}/{figura.figure_id}.json"] = (figura.figure_id, "figure")
    return esperados


def prepare_artifacts(report: reporting_core.Report) -> dict:
    """Ruta relativa posix -> bytes UTF-8 (JSON determinista). `report.json`
    solo lleva ids de tablas/figuras/insights; cada artefacto se guarda una vez."""
    esqueleto = report.to_dict()
    esqueleto["chapters"] = [
        {
            "chapter_id": c.chapter_id,
            "title": c.title,
            "summary": c.summary,
            "method_note": c.method_note,
            "metadata": c.to_dict()["metadata"],
            "tables": [t.table_id for t in c.tables],
            "figures": [f.figure_id for f in c.figures],
            "insights": [i.insight_id for i in c.insights],
        }
        for c in report.chapters
    ]
    contenidos = {
        INSIGHTS_FILENAME: {"insights": [i.to_dict() for i in report.iter_insights()]},
        REPORT_JSON_PATH: esqueleto,
    }
    for tabla in report.iter_tables():
        contenidos[f"{TABLES_DIR}/{tabla.table_id}.json"] = tabla.to_dict()
    for figura in report.iter_figures():
        contenidos[f"{FIGURES_DIR}/{figura.figure_id}.json"] = figura.to_dict()
    return {rel: _json_bytes(contenidos[rel]) for rel in expected_artifacts(report)}


# --- R6: helpers de entorno ---------------------------------------------------


def new_run_id(now: Optional[datetime] = None, *, suffix: Optional[str] = None) -> str:
    """`run-YYYYMMDDTHHMMSSZ-<sufijo>`. Con `now` fijo el prefijo es determinista;
    el sufijo es aleatorio (6 hex) salvo que se pase `suffix` explícito."""
    if now is None:
        ahora = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        ahora = now.replace(tzinfo=timezone.utc)
    else:
        ahora = now.astimezone(timezone.utc)
    sufijo = suffix if suffix else secrets.token_hex(3)
    return f"run-{ahora.strftime('%Y%m%dT%H%M%SZ')}-{sufijo}"


def resolve_git_commit(repo_root: Any) -> tuple:
    """`(commit|None, dirty|None)`. Nunca lanza: sin git o sin commits => `(None, None)`."""
    try:
        repo = Path(repo_root)
        commit, _rama = repo_mod.get_head(repo)
        if not isinstance(commit, str) or _RE_COMMIT.fullmatch(commit) is None:
            return (None, None)
        sucios = repo_mod.list_dirty_files(repo)
        return (commit, bool(sucios))
    except Exception:  # noqa: BLE001 -- contrato: nunca lanza
        return (None, None)


def resolve_harmessi_version(repo_root: Any) -> Optional[str]:
    """`harness_version` de `.ds_init/control.json`; `None` si falta o es ilegible."""
    try:
        ruta = Path(repo_root) / ".ds_init" / "control.json"
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        version = datos.get("harness_version") if isinstance(datos, dict) else None
        return version if isinstance(version, str) and version.strip() else None
    except Exception:  # noqa: BLE001 -- contrato: nunca lanza
        return None


# --- R7: manifest -------------------------------------------------------------


def _generated_at(clock: Optional[Callable[[], Any]]) -> str:
    if clock is None:
        return dsguard_core.ahora_utc()
    valor = clock()
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=timezone.utc)
        return valor.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return valor


def _ruta_posix_relativa(valor: Any) -> str:
    """Normaliza a ruta relativa posix (`\\` -> `/`); `EvidenceError` si es
    absoluta, con unidad, `..`/`.`/vacios o no es str."""
    if not isinstance(valor, str) or not valor:
        raise EvidenceError("source_notebook.path debe ser un str no vacío")
    normalizada = valor.replace("\\", "/")
    if normalizada.startswith("/") or ":" in normalizada or "\x00" in normalizada:
        raise EvidenceError("source_notebook.path debe ser relativo al repo (sin unidad ni '/' inicial)")
    if any(seg in ("", ".", "..") for seg in normalizada.split("/")):
        raise EvidenceError("source_notebook.path no admite segmentos vacíos, '.' ni '..'")
    return normalizada


def _source_notebook(valor: Any, repo_root: Any) -> Optional[dict]:
    if valor is None:
        return None
    if isinstance(valor, dict):
        return {
            "path": _ruta_posix_relativa(valor.get("path")),
            "sha256": valor.get("sha256"),
            "algorithm": valor.get("algorithm", ALGORITHM),
        }
    # str/Path relativo al repo: se describe (con `read_allowed`); puede lanzar EvidenceError.
    return _source_notebook(describe_source(repo_root, valor), repo_root)


def build_manifest(
    report: reporting_core.Report,
    *,
    repo_root: Any,
    run_id: str,
    artifact_bytes: dict,
    sources: Any = (),
    exclusions: Any = (),
    holdout_access: str,
    data_cutoff: Optional[str] = None,
    source_notebook: Any = None,
    git_commit: Any = _AUTO,
    git_dirty: Any = _AUTO,
    harmessi_version: Any = _AUTO,
    clock: Optional[Callable[[], Any]] = None,
) -> dict:
    """Manifest `schema_version: 1`. Los sha256 de `artifacts[]` son de los BYTES
    PERSISTIDOS de `artifact_bytes` (nunca del objeto re-serializado); solo se
    listan los archivos de `expected_artifacts(report)` presentes en
    `artifact_bytes`. `holdout_access` es obligatorio (sin default). No se lista
    a sí mismo. Solo levanta `EvidenceError` por un `source_notebook` inválido."""
    if git_commit is _AUTO or git_dirty is _AUTO:
        commit_auto, dirty_auto = resolve_git_commit(repo_root)
        if git_commit is _AUTO:
            git_commit = commit_auto
        if git_dirty is _AUTO:
            git_dirty = dirty_auto
    if harmessi_version is _AUTO:
        harmessi_version = resolve_harmessi_version(repo_root)

    artefactos = []
    for rel, (identificador, kind) in sorted(expected_artifacts(report).items()):
        if rel in artifact_bytes:
            artefactos.append(
                {"id": identificador, "kind": kind, "file": rel, "sha256": _sha256_bytes(artifact_bytes[rel])}
            )

    sensibles = sorted(
        [t.table_id for t in report.iter_tables() if t.sensitive]
        + [f.figure_id for f in report.iter_figures() if f.sensitive]
    )
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "report_id": report.report_id,
        "run_id": run_id,
        "report_kind": report.report_kind,
        "decision_scope": report.decision_scope,
        "data_cutoff": data_cutoff,
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "harmessi_version": harmessi_version,
        "generated_at": _generated_at(clock),
        "sources": [_copia_json(s) for s in sources],
        "exclusions": [_copia_json(e) for e in exclusions],
        "holdout_access": holdout_access,
        "sensitivity": {"contains_sensitive": bool(sensibles), "sensitive_artifacts": sensibles},
        "source_notebook": _source_notebook(source_notebook, repo_root),
        "artifacts": artefactos,
        "hashes": {"report_content": report.content_sha256()},
    }


def manifest_to_bytes(manifest: dict) -> bytes:
    """Bytes persistidos de `manifest.json` (mismo formato determinista)."""
    return _json_bytes(manifest)


# --- R8: escritura ------------------------------------------------------------


def write_report_dir(out_dir: Any, artifact_bytes: dict, manifest: dict) -> list:
    """Escribe cada artefacto (atómico) y `manifest.json` ÚLTIMO. Devuelve las
    rutas relativas escritas, en orden. NO decide permisos (guard de
    governance/publish). Levanta `EvidenceError` ante rutas relativas inseguras
    o si `artifact_bytes` incluye `manifest.json`."""
    for rel, contenido in artifact_bytes.items():
        if not _ruta_relativa_segura(rel):
            raise EvidenceError(f"ruta relativa insegura en artifact_bytes: {rel!r}")
        if rel == MANIFEST_FILENAME:
            raise EvidenceError("artifact_bytes no debe incluir manifest.json (se escribe último)")
        if not isinstance(contenido, (bytes, bytearray)):
            raise EvidenceError(f"contenido de {rel!r} debe ser bytes")
    base = Path(out_dir)
    escritos = []
    for rel, contenido in artifact_bytes.items():
        dsguard_core.escribir_texto_atomico(_unir(base, rel), bytes(contenido).decode("utf-8"))
        escritos.append(rel)
    dsguard_core.escribir_texto_atomico(base / MANIFEST_FILENAME, manifest_to_bytes(manifest).decode("utf-8"))
    escritos.append(MANIFEST_FILENAME)
    return escritos


# --- R9: lectura verificada, single-read ---------------------------------------


def read_within(out_dir: Any, rel: Any, *, repo_root: Any = None) -> bytes:
    """Lee UNA vez los bytes de `<out_dir>/<rel>`. Exige `rel` seguro (sin `..`,
    `\\x00`, nombres reservados de Windows, absolutas), que la ruta resuelta
    quede bajo `out_dir.resolve()`, rechaza symlinks/junctions (el archivo y sus
    padres bajo `out_dir`) y, si se pasa `repo_root`, exige `read_allowed` ANTES
    de abrir. Todo fallo es `EvidenceError` (mensajes con rutas relativas)."""
    if not _ruta_relativa_segura(rel):
        raise EvidenceError(f"ruta relativa insegura: {rel!r}")
    try:
        base = Path(out_dir)
        base_resuelta = base.resolve()
        actual = base
        for parte in rel.split("/"):
            actual = actual / parte
            if _es_enlace(actual):
                raise EvidenceError(f"{rel}: symlink/junction no permitido bajo el directorio del reporte")
        resuelta = actual.resolve()
        resuelta.relative_to(base_resuelta)
    except EvidenceError:
        raise
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        raise EvidenceError(f"{rel}: ruta fuera del directorio del reporte o no resoluble ({type(exc).__name__})") from exc
    if repo_root is not None:
        permitido, motivo = read_allowed(repo_root, resuelta)
        if not permitido:
            raise EvidenceError(f"{rel}: acceso denegado (no se abrió): {motivo}")
    try:
        return resuelta.read_bytes()
    except OSError as exc:
        raise EvidenceError(f"{rel}: no se pudo leer ({type(exc).__name__})") from exc


def _parse_bytes(files: Any, rel: str) -> dict:
    """Objeto JSON de `files[rel]` (bytes ya leídos); `EvidenceError` nombrando `rel`."""
    if not isinstance(files, dict) or not isinstance(files.get(rel), (bytes, bytearray)):
        raise EvidenceError(f"{rel}: falta entre los archivos leídos")
    try:
        datos = json.loads(bytes(files[rel]).decode("utf-8"))
    except (ValueError, RecursionError) as exc:
        raise EvidenceError(f"{rel}: JSON corrupto ({exc})") from exc
    if not isinstance(datos, dict):
        raise EvidenceError(f"{rel}: se esperaba un objeto JSON")
    return datos


def _ids_de(capitulo: dict, clave: str) -> list:
    ids = capitulo.get(clave)
    if not isinstance(ids, list):
        raise EvidenceError(f"{REPORT_JSON_PATH}: capítulo sin lista {clave!r}")
    for i in ids:
        if not reporting_core.es_id_valido(i):
            raise EvidenceError(f"{REPORT_JSON_PATH}: id inválido {i!r} en {clave!r}")
    return ids


def _capitulos_del_esqueleto(esqueleto: dict) -> list:
    capitulos = esqueleto.get("chapters")
    if not isinstance(capitulos, list):
        raise EvidenceError(f"{REPORT_JSON_PATH}: 'chapters' debe ser una lista")
    salida = []
    for capitulo in capitulos:
        if not isinstance(capitulo, dict):
            raise EvidenceError(f"{REPORT_JSON_PATH}: capítulo no es un objeto")
        salida.append(
            (capitulo, _ids_de(capitulo, "tables"), _ids_de(capitulo, "figures"), _ids_de(capitulo, "insights"))
        )
    return salida


def report_from_bytes(files: dict, manifest: dict) -> reporting_core.Report:
    """Reconstruye el `Report` SOLO desde bytes ya leídos (`files`: ruta relativa
    -> bytes; sin tocar disco) y verifica `hashes.report_content` del `manifest`.
    `EvidenceError` si algo falta, no calza o el hash difiere."""
    if not isinstance(manifest, dict):
        raise EvidenceError(f"{MANIFEST_FILENAME}: se esperaba un objeto JSON")
    esqueleto = _parse_bytes(files, REPORT_JSON_PATH)
    insights_doc = _parse_bytes(files, INSIGHTS_FILENAME)
    lista_insights = insights_doc.get("insights")
    if not isinstance(lista_insights, list) or not all(isinstance(i, dict) for i in lista_insights):
        raise EvidenceError(f"{INSIGHTS_FILENAME}: se esperaba {{'insights': [objetos]}}")
    por_id = {i.get("insight_id"): i for i in lista_insights}

    capitulos = []
    for capitulo, ids_tablas, ids_figuras, ids_insights in _capitulos_del_esqueleto(esqueleto):
        completo = dict(capitulo)
        completo["tables"] = [_parse_bytes(files, f"{TABLES_DIR}/{i}.json") for i in ids_tablas]
        completo["figures"] = [_parse_bytes(files, f"{FIGURES_DIR}/{i}.json") for i in ids_figuras]
        insights = []
        for identificador in ids_insights:
            if identificador not in por_id:
                raise EvidenceError(f"{INSIGHTS_FILENAME}: falta el insight {identificador!r}")
            insights.append(por_id[identificador])
        completo["insights"] = insights
        capitulos.append(completo)

    datos = dict(esqueleto)
    datos["chapters"] = capitulos
    try:
        report = reporting_core.Report.from_dict(datos)
    except (reporting_core.ReportingContractError, TypeError, KeyError, ValueError, AttributeError) as exc:
        raise EvidenceError(f"{REPORT_JSON_PATH}: no se pudo reconstruir el Report ({exc})") from exc

    hashes = manifest.get("hashes")
    esperado = hashes.get("report_content") if isinstance(hashes, dict) else None
    if not isinstance(esperado, str):
        raise EvidenceError(f"{MANIFEST_FILENAME}: falta hashes.report_content")
    if report.content_sha256() != esperado:
        raise EvidenceError(
            f"{MANIFEST_FILENAME}: hashes.report_content no coincide con el Report cargado "
            f"(artefactos alterados o inconsistentes)"
        )
    return report


def read_report_dir(out_dir: Any, *, repo_root: Any = None) -> tuple:
    """`(files, manifest)`: lee UNA vez (vía `read_within`) manifest, report.json,
    insights.json y cada tabla/figura que report.json referencia. `files` mapea
    ruta relativa -> bytes (incluye `manifest.json`). `EvidenceError` ante
    faltantes, JSON corrupto, ids inseguros o accesos denegados."""
    base = Path(out_dir)
    files = {
        rel: read_within(base, rel, repo_root=repo_root)
        for rel in (MANIFEST_FILENAME, REPORT_JSON_PATH, INSIGHTS_FILENAME)
    }
    manifest = _parse_bytes(files, MANIFEST_FILENAME)
    esqueleto = _parse_bytes(files, REPORT_JSON_PATH)
    for _capitulo, ids_tablas, ids_figuras, _ids_insights in _capitulos_del_esqueleto(esqueleto):
        for directorio, ids in ((TABLES_DIR, ids_tablas), (FIGURES_DIR, ids_figuras)):
            for i in ids:
                rel = f"{directorio}/{i}.json"
                files[rel] = read_within(base, rel, repo_root=repo_root)
    return files, manifest


def load_report_dir(out_dir: Any, *, repo_root: Any = None) -> tuple:
    """`(Report, manifest)` reensamblados desde disco (`read_report_dir` +
    `report_from_bytes`). Verifica `Report.content_sha256()` contra
    `hashes.report_content`. Con `repo_root` evalua `read_allowed` antes de abrir
    cada archivo (denegado => `EvidenceError`); sin `repo_root` no evalua acceso
    (uso local). Levanta `EvidenceError` (nombrando el archivo)."""
    files, manifest = read_report_dir(out_dir, repo_root=repo_root)
    return report_from_bytes(files, manifest), manifest


# --- R10: indice exploratory --------------------------------------------------


def _leer_manifest_reporte(ruta: Path, config: Any, motivo_config: Optional[str], repo: Path) -> Optional[dict]:
    """Manifest con forma de reporte Harmessi, o `None` si es ilegible, muy
    grande, sin acceso o de forma inválida."""
    permitido, _motivo = _evaluar_lectura(config, motivo_config, repo, ruta)
    if not permitido:
        return None
    try:
        if ruta.stat().st_size > _MAX_MANIFEST_BYTES:
            return None
        datos = json.loads(ruta.read_bytes().decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    if (
        not isinstance(datos, dict)
        or "schema_version" not in datos
        or not isinstance(datos.get("report_id"), str)
        or not isinstance(datos.get("artifacts"), list)
    ):
        return None
    return datos


def _escanear_exploratory(repo: Path, root: str) -> ExploratoryIndex:
    base = _unir(repo, root)
    if not base.is_dir():
        return ExploratoryIndex()
    config, motivo_config = _cargar_guardrails(repo)
    indice: dict = {}
    truncado = False
    ilegibles = 0
    errores = []
    vistos = 0
    for dirpath, dirnames, filenames in os.walk(base, onerror=errores.append):
        dirnames.sort()
        vistos += 1
        if vistos > MAX_DIRS_SCAN:
            truncado = True
            break
        if MANIFEST_FILENAME not in filenames:
            continue
        datos = _leer_manifest_reporte(Path(dirpath) / MANIFEST_FILENAME, config, motivo_config, repo)
        if datos is None:
            ilegibles += 1
            continue
        dirnames[:] = []  # un reporte Harmessi es una hoja: no se desciende a artifacts/, tables/, figures/
        if datos.get("decision_scope") != _SCOPE_EXPLORATORY:
            continue
        try:
            dir_rel = Path(dirpath).relative_to(repo).as_posix()
        except ValueError:
            continue
        for artefacto in datos["artifacts"]:
            if not isinstance(artefacto, dict):
                continue
            sha, archivo = artefacto.get("sha256"), artefacto.get("file")
            if not isinstance(sha, str) or _RE_SHA256.fullmatch(sha) is None or not isinstance(archivo, str):
                continue
            indice.setdefault(sha.lower(), {"report_id": datos["report_id"], "file": f"{dir_rel}/{archivo}"})
    error = None
    if errores:
        error = f"no se pudo recorrer {root!r}: {len(errores)} subdirectorio(s) ilegible(s)"
    return ExploratoryIndex(index=indice, truncated=truncado, error=error, unreadable_manifests=ilegibles)


def exploratory_index_status(repo_root: Any) -> ExploratoryIndex:
    """Escanea el root exploratory de la policy buscando manifests de reportes
    exploratory (no desciende bajo un directorio que ya tiene un manifest de
    reporte). Acotado a `MAX_DIRS_SCAN`. Policy inválida, repo ilegible o error de
    recorrido => `error`; manifests ilegibles/inválidos se cuentan. Nunca lanza."""
    try:
        repo = Path(repo_root).resolve()
        policy = governance.load_policy(repo)
        root = policy.destination_roots[_SCOPE_EXPLORATORY]
    except Exception as exc:  # noqa: BLE001 -- nunca lanza
        return ExploratoryIndex(error=f"policy inválida o repo ilegible ({type(exc).__name__})")
    try:
        return _escanear_exploratory(repo, root)
    except Exception as exc:  # noqa: BLE001 -- nunca lanza
        return ExploratoryIndex(error=f"error inesperado indexando {root!r} ({type(exc).__name__})")


def exploratory_hash_index(repo_root: Any) -> dict:
    """`{sha256: {"report_id", "file"}}` (`file` relativo al repo, posix): wrapper
    de `exploratory_index_status(...).index`. Policy inválida => `{}`. Nunca lanza."""
    return exploratory_index_status(repo_root).index


# --- R11: aislamiento por hash ------------------------------------------------


def _res(
    status: str, message: str, subject: Optional[str] = None, *, tecnico: bool = False, detail: Optional[str] = None
) -> checks.CheckResult:
    return checks.CheckResult(
        status=status,
        code=CODE_ISOLATION_HASH,
        message=message,
        detail=detail,
        subject=subject,
        kind=checks.KIND_TECHNICAL_ERROR if tecnico else checks.KIND_CHECK,
    )


def _enumerar_input(entrada: Any, repo: Path, resultados: list, cupo: int) -> tuple:
    """`(candidatos, excedido)` de un input (archivo o directorio). Errores de
    recorrido se agregan a `resultados` como FAIL technical_error (fail-closed)."""
    if not isinstance(entrada, (str, Path)) or str(entrada) == "" or "\x00" in str(entrada):
        resultados.append(_res(checks.STATUS_FAIL, f"input inválido: {entrada!r}", tecnico=True))
        return [], False
    ruta = Path(entrada)
    if not ruta.is_absolute():
        ruta = repo / ruta
    ruta = Path(os.path.normpath(str(ruta)))
    subject = _subject_de(repo, ruta)
    if ruta.is_file():
        return [ruta], False
    if not ruta.is_dir():
        resultados.append(_res(checks.STATUS_FAIL, f"input inexistente o ilegible: {subject!r}", subject, tecnico=True))
        return [], False
    candidatos: list = []
    errores: list = []
    for dirpath, dirnames, filenames in os.walk(ruta, onerror=errores.append):
        dirnames.sort()
        candidatos.extend(Path(dirpath) / nombre for nombre in sorted(filenames))
        if len(candidatos) > cupo:
            break
    for error in errores:
        nombre = getattr(error, "filename", None)
        donde = _subject_de(repo, Path(nombre)) if isinstance(nombre, (str, Path)) else subject
        resultados.append(
            _res(
                checks.STATUS_FAIL,
                f"no verificable: subdirectorio ilegible en {donde!r} (fail-closed)",
                donde,
                tecnico=True,
            )
        )
    return candidatos, len(candidatos) > cupo


def _verificar_aislamiento(repo_root: Any, flow_scope: Any, inputs: Any, index: Any) -> list:
    if flow_scope == _SCOPE_EXPLORATORY:
        return [_res(checks.STATUS_NA, "flow_scope exploratory: el aislamiento por hash no aplica")]
    if flow_scope not in _SCOPES_FLUJO_MODELO:
        return [_res(checks.STATUS_FAIL, f"flow_scope inválido: {flow_scope!r}", tecnico=True)]
    if isinstance(inputs, (str, Path)):
        inputs = [inputs]
    try:
        lista = list(inputs)
    except TypeError:
        return [_res(checks.STATUS_FAIL, f"inputs no es iterable: {type(inputs).__name__}", tecnico=True)]
    if not lista:
        return [_res(checks.STATUS_NA, "sin inputs que comparar")]

    repo = Path(repo_root).resolve()
    if isinstance(index, ExploratoryIndex):
        estado = index
    elif isinstance(index, dict):
        estado = ExploratoryIndex(index=index)
    else:
        estado = exploratory_index_status(repo)
    if estado.error is not None:
        return [_res(checks.STATUS_FAIL, f"no se pudo indexar artefactos exploratory: {estado.error}", tecnico=True)]
    indice = estado.index
    resultados = []
    if estado.truncated:
        resultados.append(
            _res(
                checks.STATUS_FAIL,
                f"indice exploratory incompleto: se superó MAX_DIRS_SCAN={MAX_DIRS_SCAN} (fail-closed)",
                tecnico=True,
            )
        )
    if estado.unreadable_manifests > 0:
        resultados.append(
            _res(
                checks.STATUS_WARN,
                f"{estado.unreadable_manifests} manifest(s) bajo el root exploratory ilegibles o inválidos: "
                f"el índice puede estar incompleto",
            )
        )

    archivos = []
    excedido = False
    for entrada in lista:
        candidatos, desborda = _enumerar_input(entrada, repo, resultados, MAX_FILES_HASH - len(archivos))
        for candidato in candidatos:
            if len(archivos) >= MAX_FILES_HASH:
                desborda = True
                break
            archivos.append(candidato)
        if desborda:
            excedido = True
            break
    if excedido:
        resultados.append(
            _res(
                checks.STATUS_FAIL,
                f"se superó MAX_FILES_HASH={MAX_FILES_HASH} archivos de input (fail-closed)",
                tecnico=True,
            )
        )

    config, motivo_config = _cargar_guardrails(repo)
    for ruta in archivos:
        subject = _subject_de(repo, ruta)
        permitido, motivo = _evaluar_lectura(config, motivo_config, repo, ruta)
        if not permitido:
            resultados.append(
                _res(
                    checks.STATUS_FAIL,
                    "no verificable: acceso denegado (no se abrió)",
                    subject,
                    tecnico=True,
                    detail=motivo,
                )
            )
            continue
        try:
            sha = _fingerprint.calcular_fingerprint(ruta)["hash"]
        except OSError as exc:
            resultados.append(
                _res(checks.STATUS_FAIL, f"input ilegible: {subject!r} ({type(exc).__name__})", subject, tecnico=True)
            )
            continue
        origen = indice.get(sha)
        if origen is not None:
            resultados.append(
                _res(
                    checks.STATUS_FAIL,
                    f"el input {subject!r} es copia byte-idéntica de un artefacto exploratory "
                    f"(report_id={origen['report_id']!r}, file={origen['file']!r})",
                    subject,
                )
            )
    if not resultados:
        resultados.append(
            _res(
                checks.STATUS_PASS,
                f"{len(archivos)} archivo(s) de input sin coincidencia con "
                f"{len(indice)} artefacto(s) exploratory indexados (cubre copias byte-idénticas, no derivados)",
            )
        )
    return resultados


def check_inputs_hash_isolation(
    repo_root: Any, flow_scope: Any, inputs: Any, *, index: Optional[ExploratoryIndex] = None
) -> list:
    """`REPORT-ISOLATION-HASH`. En `model_valid`/`operational`: FAIL si el sha256
    de un input (o de cada archivo bajo un directorio input, hasta
    `MAX_FILES_HASH`) coincide con un artefacto exploratory persistido.
    `read_allowed` se evalúa por archivo ANTES de hashearlo (denegado => FAIL
    technical_error "no verificable", sin abrirlo). `exploratory` => N/A.
    Fail-closed (input ilegible/denegado, recorrido con error, cota superada,
    policy inválida => FAIL `technical_error`). `index` (un `ExploratoryIndex` ya
    calculado) evita reindexar; manifests exploratory ilegibles => WARN adicional.
    Nunca lanza."""
    try:
        return _verificar_aislamiento(repo_root, flow_scope, inputs, index)
    except Exception as exc:  # noqa: BLE001 -- contrato: nunca lanza
        return [_res(checks.STATUS_FAIL, f"error inesperado ({type(exc).__name__})", tecnico=True)]
