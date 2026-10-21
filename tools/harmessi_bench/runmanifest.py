"""Run manifest de una corrida de eval (v0.13 Change 2).

Identifica con qué configuración del harness se obtuvo la evidencia: ids,
hashes y versiones. NO captura variables de entorno, hostname, usuario, rutas
absolutas, prompts completos, salidas del modelo ni credenciales.

Puro salvo lectura de archivos del checkout y de Git de solo lectura: Git se
consulta únicamente vía `tools.dsguard.repo` (import diferido, así este módulo
no arrastra `subprocess` al importarse). Sin providers ni red; no escribe
archivos (la persistencia es de `storage`).
"""
from __future__ import annotations

import copy
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import List, Optional

from tools.dsguard.skill_contract import DIR_SKILLS, SUPERFICIE_OPTIMIZABLE, superficie_de_ruta
from tools.ds_init.version import HARNESS_VERSION
from tools.harmessi_bench.core import EVALUATOR_VERSION
from tools.harmessi_bench.redact import redactar_texto
from tools.harmessi_bench.suite import bloque_suite

MANIFEST_VERSION = 1

GIT_DESCONOCIDO = "unknown"
HASH_ILEGIBLE = "unreadable"

# Raíz del checkout por defecto: tools/harmessi_bench/runmanifest.py -> repo.
_RAIZ_REPO_DEFAULT = Path(__file__).resolve().parents[2]

# Directorio del skill orquestador y archivo de la política de runtime,
# derivados de `DIR_SKILLS` (no se repiten literales de rutas del proveedor).
_DIR_LEAD = PurePosixPath(DIR_SKILLS).parent
_RUTA_GUARDRAILS = PurePosixPath(PurePosixPath(DIR_SKILLS).parts[0]) / "guardrails.json"

# Claves materiales de primer nivel (cambian la identidad de la evidencia).
# `target` se aplana en `target.provider_id|model|effort`.
CLAVES_MATERIALES = (
    "manifest_version",
    "harmessi_version",
    "skills",
    "surfaces_hash",
    "guardrails_hash",
    "evaluator_version",
    "suite",
    "cases_hash",
)
_CLAVES_TARGET = ("provider_id", "model", "effort")

# Campos sin los cuales un manifest no sirve para comparar (R8).
CAMPOS_REQUERIDOS = CLAVES_MATERIALES + ("target", "identity_hash")


def hash_contenido(datos: bytes) -> str:
    """sha256 hex del contenido normalizando finales de línea (CRLF y CR
    sueltos -> LF) para que el hash no dependa del sistema operativo."""
    normalizado = datos.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalizado).hexdigest()


def _hash_archivo(ruta: Path) -> str:
    try:
        return hash_contenido(ruta.read_bytes())
    except OSError:
        return HASH_ILEGIBLE


def hash_skills(repo_root: Path) -> dict:
    """`{nombre: sha256}` de `<repo_root>/<DIR_SKILLS>/*.md`, ordenado por
    nombre. Directorio ausente => `{}`."""
    directorio = Path(repo_root) / Path(*PurePosixPath(DIR_SKILLS).parts)
    if not directorio.is_dir():
        return {}
    return {ruta.stem: _hash_archivo(ruta) for ruta in sorted(directorio.glob("*.md")) if ruta.is_file()}


def _entradas_superficies(repo_root: Path) -> list:
    """Lista ordenada `[ruta_relativa, sha256]` de las superficies Optimizable
    (`skill_contract.superficie_de_ruta`) del skill orquestador: `skills/*.md`
    y los `.md` raíz clasificados como Optimizable."""
    base = Path(repo_root) / Path(*_DIR_LEAD.parts)
    entradas = []
    if base.is_dir():
        candidatos = sorted(base.glob("*.md")) + sorted((base / "skills").glob("*.md"))
        for ruta in candidatos:
            if not ruta.is_file():
                continue
            relativa = (_DIR_LEAD / ruta.relative_to(base).as_posix()).as_posix()
            if superficie_de_ruta(relativa) == SUPERFICIE_OPTIMIZABLE:
                entradas.append([relativa, _hash_archivo(ruta)])
    entradas.sort()
    return entradas


def hash_superficies(repo_root: Path) -> str:
    """sha256 de la lista ordenada `(ruta_relativa, sha256)` de las superficies
    Optimizable (ver `_entradas_superficies`)."""
    texto = json.dumps(_entradas_superficies(repo_root), ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def diagnosticar(repo_root: Path) -> List[str]:
    """Problemas que invalidan la identidad del manifest (M1): directorio de
    skills o de superficies ausente, skills vacío, o algún hash ilegible
    (skill, superficie o guardrails). Lista vacía => identidad confiable."""
    raiz = Path(repo_root)
    problemas: List[str] = []
    if not (raiz / Path(*PurePosixPath(DIR_SKILLS).parts)).is_dir():
        problemas.append("directorio_skills_ausente")
    if not (raiz / Path(*_DIR_LEAD.parts)).is_dir():
        problemas.append("directorio_superficies_ausente")
    skills = hash_skills(raiz)
    if not skills:
        problemas.append("skills_vacio")
    problemas.extend(f"hash_ilegible:skill:{n}" for n, h in skills.items() if h == HASH_ILEGIBLE)
    problemas.extend(
        f"hash_ilegible:superficie:{rel}" for rel, h in _entradas_superficies(raiz) if h == HASH_ILEGIBLE
    )
    if hash_guardrails(raiz) == HASH_ILEGIBLE:
        problemas.append("hash_ilegible:guardrails")
    return problemas


def hash_guardrails(repo_root: Path) -> Optional[str]:
    """sha256 del archivo de política de runtime, o `None` si no existe."""
    ruta = Path(repo_root) / Path(*_RUTA_GUARDRAILS.parts)
    if not ruta.is_file():
        return None
    return _hash_archivo(ruta)


def leer_git(repo_root: Path) -> dict:
    """`{"commit", "clean"}` vía `tools.dsguard.repo`. Cualquier fallo (no es
    repo, Git ausente, salida ilegible) => `commit="unknown"`, `clean=None`;
    nunca un valor inventado y nunca lanza. Unknown != clean."""
    commit = GIT_DESCONOCIDO
    limpio = None
    try:
        from tools.dsguard import repo as repo_mod

        obtenido, _rama = repo_mod.get_head(Path(repo_root))
        if isinstance(obtenido, str) and obtenido.strip():
            commit = obtenido.strip()
    except Exception:  # noqa: BLE001 - Git no confiable => unknown
        commit = GIT_DESCONOCIDO
    if commit != GIT_DESCONOCIDO:
        try:
            from tools.dsguard import repo as repo_mod

            resultado = repo_mod.is_tree_clean(Path(repo_root))
            limpio = resultado if isinstance(resultado, bool) else None
        except Exception:  # noqa: BLE001
            limpio = None
    return {"commit": commit, "clean": limpio}


def _material(manifest: dict) -> dict:
    """Vista aplanada de los campos materiales (`target.*` incluidos)."""
    plano = {clave: manifest.get(clave) for clave in CLAVES_MATERIALES}
    target = manifest.get("target")
    target = target if isinstance(target, dict) else {}
    for clave in _CLAVES_TARGET:
        plano[f"target.{clave}"] = target.get(clave)
    return plano


def calcular_identity_hash(manifest: dict) -> str:
    """sha256 de la serialización canónica de los campos materiales. No
    depende de `run_id`, timestamps, plataforma, `git` ni `seed`."""
    texto = json.dumps(_material(manifest), sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def diferencias_materiales(a: dict, b: dict) -> List[str]:
    """Lista ordenada de claves materiales que difieren entre dos manifests
    (p. ej. `skills`, `target.model`). Tolera claves ausentes (valen `None`)."""
    plano_a, plano_b = _material(a), _material(b)
    return sorted(clave for clave in plano_a if plano_a[clave] != plano_b[clave])


def campos_faltantes(manifest) -> List[str]:
    """Campos requeridos ausentes; un manifest que no es dict => todos."""
    if not isinstance(manifest, dict):
        return list(CAMPOS_REQUERIDOS)
    faltantes = [clave for clave in CAMPOS_REQUERIDOS if clave not in manifest]
    if "target" in manifest and not isinstance(manifest["target"], dict):
        faltantes.append("target")
    # M1: identidad no confiable (problemas declarados, skills vacío o hash ilegible).
    skills = manifest.get("skills")
    if "skills" in manifest and (
        not isinstance(skills, dict) or not skills or HASH_ILEGIBLE in skills.values()
    ):
        faltantes.append("skills")
    if manifest.get("guardrails_hash") == HASH_ILEGIBLE:
        faltantes.append("guardrails_hash")
    if manifest.get("problemas"):
        faltantes.append("problemas")
    return sorted(set(faltantes))


def evaluar_compatibilidad(existente: dict, nuevo: dict) -> List[str]:
    """Incompatibilidades materiales entre dos manifests (R10): lista vacía =>
    compatible. `git.commit` distinto NO es material (ver
    `advertencias_compatibilidad`). Un manifest inválido es incompatible."""
    faltantes_existente = campos_faltantes(existente)
    faltantes_nuevo = campos_faltantes(nuevo)
    if faltantes_existente or faltantes_nuevo:
        return ["manifest_incompleto"]
    return diferencias_materiales(existente, nuevo)


def advertencias_compatibilidad(existente: dict, nuevo: dict) -> List[str]:
    """Diferencias no materiales pero dignas de aviso (hoy: `git.commit`)."""
    avisos: List[str] = []
    try:
        commit_a = (existente.get("git") or {}).get("commit")
        commit_b = (nuevo.get("git") or {}).get("commit")
    except AttributeError:
        return avisos
    if commit_a != commit_b:
        avisos.append("git.commit distinto (no material)")
    return avisos


def _ahora_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def construir_manifest(
    run_id: str,
    target,
    suite=None,
    cases_hash: Optional[str] = None,
    seed: Optional[int] = None,
    repo_root: Optional[Path] = None,
    evaluator_version: str = EVALUATOR_VERSION,
    started_utc: Optional[str] = None,
    finished_utc: Optional[str] = None,
) -> dict:
    """Arma el run manifest (JSON-serializable). `repo_root` es la raíz del
    checkout de la que se leen skills, superficies, guardrails y Git (por
    defecto, el checkout de este módulo); es inyectable para tests con
    directorios temporales. `target` es un `EvalTarget` (o dict equivalente)."""
    raiz = Path(repo_root) if repo_root is not None else _RAIZ_REPO_DEFAULT
    if isinstance(target, dict):
        datos_target = {clave: target.get(clave) for clave in _CLAVES_TARGET}
    else:
        datos_target = {clave: getattr(target, clave, None) for clave in _CLAVES_TARGET}
    # model/effort vienen del usuario: se redactan (la identidad usa el valor ya redactado).
    for clave in ("model", "effort"):
        datos_target[clave] = redactar_texto(datos_target[clave])
    git = leer_git(raiz)
    inicio = started_utc if started_utc is not None else _ahora_utc()
    fin = finished_utc if finished_utc is not None else _ahora_utc()
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "run_id": run_id,
        "harmessi_version": HARNESS_VERSION,
        "git": git,
        "skills": hash_skills(raiz),
        "surfaces_hash": hash_superficies(raiz),
        "guardrails_hash": hash_guardrails(raiz),
        "target": datos_target,
        "evaluator_version": evaluator_version,
        "suite": bloque_suite(suite),
        "cases_hash": cases_hash,
        "seed": seed,
        "platform": {
            "system": platform.system(),
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "started_utc": inicio,
        "finished_utc": fin,
        # No material: una entrada por ejecución (la primera corrida y cada resume).
        "sesiones": [
            {"started_utc": inicio, "finished_utc": fin, "git_commit": git["commit"], "seed": seed}
        ],
        # No material: problemas que invalidan la identidad (M1); [] si es confiable.
        "problemas": diagnosticar(raiz),
    }
    manifest["identity_hash"] = calcular_identity_hash(manifest)
    return manifest


def _sesion_de(manifest: dict) -> dict:
    return {
        "started_utc": manifest.get("started_utc"),
        "finished_utc": manifest.get("finished_utc"),
        "git_commit": (manifest.get("git") or {}).get("commit"),
        "seed": manifest.get("seed"),
    }


def finalizar_manifest(manifest: dict, finished_utc: Optional[str] = None) -> dict:
    """Copia del manifest con `finished_utc` (y el de la última sesión)
    actualizado al terminar la corrida. No toca ningún campo material."""
    resultado = copy.deepcopy(manifest)
    fin = finished_utc if finished_utc is not None else _ahora_utc()
    resultado["finished_utc"] = fin
    sesiones = resultado.get("sesiones")
    if isinstance(sesiones, list) and sesiones and isinstance(sesiones[-1], dict):
        sesiones[-1]["finished_utc"] = fin
    return resultado


def agregar_sesion(existente: dict, nuevo: dict) -> dict:
    """Manifest de un resume: parte del `existente` (los campos materiales ya
    se validaron compatibles), conserva sus sesiones (o sintetiza una desde sus
    campos si no tenía) y agrega la sesión de `nuevo`. Actualiza `finished_utc`,
    `git` y `seed` informativos con los de la última sesión."""
    resultado = copy.deepcopy(existente)
    previas = existente.get("sesiones")
    if not isinstance(previas, list) or not previas:
        previas = [_sesion_de(existente)]
    resultado["sesiones"] = copy.deepcopy(previas) + [_sesion_de(nuevo)]
    resultado["finished_utc"] = nuevo.get("finished_utc")
    resultado["git"] = copy.deepcopy(nuevo.get("git"))
    resultado["seed"] = nuevo.get("seed")
    return resultado
