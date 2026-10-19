"""Alcance de un Change SDD: compara lo declarado (`control["alcance"]["rutas_autorizadas"]`) contra
lo realmente tocado -- working tree actual MÁS el diff completo desde `control["baseline"]["commit"]`
(Change 2 v0.4: 20260916-scope-and-change-isolation). Antes de este change, el chequeo (`ALCANCE-RUTA`,
duplicado en `sdd.gate_cierre`/`ds_guard.cmd_validate`) solo veía el working tree -- un archivo tocado
fuera de scope y ya commiteado quedaba invisible en cuanto el working tree volvía a estar limpio. Este
módulo consolida esa lógica en un solo lugar.

Reusa `repo._git` directamente (mismo patrón ya usado por `tools/dsimpact/git_source.py` en Change 1)
-- NUNCA importa `tools.dsimpact` desde acá: `dsguard` es core (discovery, siempre instalado),
`dsimpact` es opcional (`stage_minimo="experiment"`), invertir esa dependencia rompería cualquier
instalación en discovery (ver `design.md` §2 del change).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from . import core
from . import repo as repo_mod
from . import scope_amendments
from .core import Finding


class GitIlegibleError(ValueError):
    """La salida de git fue recibida (returncode 0) pero está malformada: NO equivale a «sin
    archivos tocados». `evaluar_alcance` la traduce a `ALCANCE-GIT-ILEGIBLE` (fail-closed)."""


def archivos_tocados_desde_baseline(repo_root: Path, baseline_commit: Optional[str]) -> list:
    """`git diff --name-status -z -M <baseline_commit>` contra el working tree actual (incluye
    commits ya hechos desde baseline Y cambios sin confirmar en una sola diff -- misma semántica
    que `git diff <ref>` nativo). Devuelve rutas relativas POSIX, parseadas con
    `repo.parse_name_status_z` (inmune a `core.quotepath`): rename -> ambas rutas (nueva y vieja),
    copy -> solo el destino. Devuelve [] SOLO si `baseline_commit` es None/vacío. Fail-closed
    (v0.11): un comando fallido (ref inválida/borrada) propaga `GitCommandError`, Git ausente
    propaga `RuntimeError`; si git responde OK pero la salida es malformada, lanza
    `GitIlegibleError`. `evaluar_alcance` traduce todo a `ALCANCE-GIT-ILEGIBLE`."""
    if not baseline_commit:
        return []
    try:
        entradas = repo_mod.diff_name_status(repo_root, baseline_commit)
    except repo_mod.GitCommandError:
        raise
    except repo_mod.GitOutputError as exc:
        # git respondió OK pero la salida es ilegible: fail-closed (no es «sin archivos»).
        raise GitIlegibleError(str(exc)) from exc
    rutas = []
    for codigo, nueva, vieja in entradas:
        rutas.append(Path(nueva).as_posix())
        if codigo.startswith("R") and vieja:
            rutas.append(Path(vieja).as_posix())
    return list(dict.fromkeys(rutas))


_PREFIJO_EXECUTIONS = ".harmessi/executions/"
_RUTA_LEDGER = "openspec/decisions/ledger.jsonl"


def es_output_intrinseco(ruta: str) -> bool:
    """True SOLO para outputs de bookkeeping del harness: `.harmessi/executions/**`
    y la ruta exacta `openspec/decisions/ledger.jsonl` (R38). Lista cerrada; no
    autoriza nada para `exec` (R39), solo los excluye del evaluador de alcance."""
    normalizada = str(ruta).replace("\\", "/")
    while normalizada.startswith("./"):
        normalizada = normalizada[2:]
    return normalizada.startswith(_PREFIJO_EXECUTIONS) or normalizada == _RUTA_LEDGER


def alcance_efectivo(change_dir, control: dict) -> tuple:
    """`(rutas, hallazgos)`: scope efectivo de un Change (R21-R25, R22). Función única de lectura
    del alcance: delega en `scope_amendments.estado_alcance` (scope inicial aprobado + cadena de
    enmiendas). Sin `amendments.jsonl` el resultado equivale a la caché de `control.json`
    (compatibilidad total). Si la cadena es inválida (`valido` False), `rutas` es `[]`
    (fail-closed: nada queda autorizado) y `hallazgos` trae `ALCANCE-ENMIENDA-INVALIDA`. Si la
    caché diverge de la cadena, gana la cadena y se agrega `ALCANCE-CACHE-DIVERGENTE`.
    `change_dir` None => no hay dónde buscar la cadena: se usa la caché, sin hallazgos."""
    if change_dir is None:
        rutas_cache = control.get("alcance", {}).get("rutas_autorizadas", [])
        return list(rutas_cache), []
    estado = scope_amendments.estado_alcance(Path(change_dir), control)
    hallazgos = list(estado.hallazgos)
    if not estado.valido:
        if not any(h.codigo == "ALCANCE-ENMIENDA-INVALIDA" for h in hallazgos):
            hallazgos.append(Finding(
                "ALCANCE-ENMIENDA-INVALIDA",
                "La cadena de enmiendas de alcance no es válida; nada queda autorizado.",
                None,
            ))
        return [], hallazgos
    return list(estado.rutas), hallazgos


def _resolver_change_dir(repo_root: Path, control: dict) -> Optional[Path]:
    """`openspec/changes/<change_id>` o, si no existe, `openspec/archive/<change_id>`. `None` si
    el control no trae `change_id` utilizable o ninguno de los dos directorios existe."""
    change_id = control.get("change_id")
    if not isinstance(change_id, str) or not change_id or change_id in (".", ".."):
        return None
    if "/" in change_id or "\\" in change_id:
        return None
    for base in ("changes", "archive"):
        candidato = repo_root / "openspec" / base / change_id
        if candidato.is_dir():
            return candidato
    return None


def evaluar_alcance(repo_root: Path, control: dict, change_dir=None) -> list:
    """[Finding("ALCANCE-RUTA", ...), ...] -- mismo código que ya usaban `cmd_validate`/`gate_cierre`;
    además emite `Finding("ALCANCE-GIT-ILEGIBLE")` (fail-closed) si la salida de git del diff desde
    baseline es ilegible (los hallazgos ALCANCE-RUTA del resto se siguen emitiendo). Unión
    deduplicada de `repo.list_dirty_files` (working tree) + `archivos_tocados_desde_baseline`
    (historial desde baseline), comparada contra el alcance efectivo (`alcance_efectivo`: scope
    aprobado + enmiendas gobernadas; sin enmiendas o sin `change_id`/directorio resoluble, la caché
    `rutas_autorizadas` como siempre) vía `repo.path_matches_any` (reusada tal cual). Propaga además
    `ALCANCE-ENMIENDA-INVALIDA` (cadena inválida: nada autorizado, todo archivo tocado queda fuera
    de alcance) y `ALCANCE-CACHE-DIVERGENTE`. `change_dir` opcional: si se pasa se usa tal cual; si no
    se pasa y no se puede resolver, un control con `alcance.scope_hash` es fail-closed
    (`ALCANCE-ENMIENDA-INVALIDA`, nada autorizado); sin él (legado) se usa la caché.

    Atribución a otros Changes (v0.11, 4B; «honesta, no autenticada»): una ruta fuera del alcance
    propio que cae en el alcance de exactamente un ajeno se reporta como informativa
    `ALCANCE-ATRIBUIDA-OTRO-CHANGE`; sin dueño => `ALCANCE-RUTA`; con varios dueños, o en el alcance
    propio Y de un ajeno => `ALCANCE-CONFLICTO-CHANGES`. Un ajeno cuenta solo si está activo en
    `tasks.md` y, verificado sobre su snapshot en el baseline propio (SHA completo), tiene estado activo,
    la aprobación de todos los artefactos requeridos y un `scope_hash` que no cambió en disco;
    sus patrones catch-all/protegidos se descartan. Estos controles elevan el costo de la evasión
    pero no la hacen imposible (control.json es editable); la atribución nunca amplía el alcance
    propio (D1)."""
    repo_root = Path(repo_root)
    if change_dir is None:
        change_dir = _resolver_change_dir(repo_root, control)
    alcance_control = control.get("alcance")
    tiene_ancla = isinstance(alcance_control, dict) and bool(alcance_control.get("scope_hash"))
    if change_dir is None and tiene_ancla:
        # Change con `scope_hash` (alcance gobernado) cuyo directorio no se puede resolver:
        # no se cae a la caché cruda (fail-closed).
        rutas_autorizadas = []
        findings_alcance = [Finding(
            "ALCANCE-ENMIENDA-INVALIDA",
            "No se pudo resolver el directorio del Change para validar el alcance gobernado.",
            None,
        )]
    else:
        rutas_autorizadas, findings_alcance = alcance_efectivo(change_dir, control)
    baseline_commit = control.get("baseline", {}).get("commit")

    tocados = set()
    findings = list(findings_alcance)
    motivos = []
    _errores_git = (repo_mod.GitCommandError, GitIlegibleError, repo_mod.GitOutputError, RuntimeError,
                   ValueError, OSError)
    try:
        tocados |= set(repo_mod.list_dirty_files(repo_root))
    except _errores_git as exc:
        motivos.append(f"working tree: {exc}")
    try:
        tocados |= set(archivos_tocados_desde_baseline(repo_root, baseline_commit))
    except _errores_git as exc:
        motivos.append(f"diff desde baseline: {exc}")
    if motivos:
        # Fail-closed: un único hallazgo; unknown Git state != clean Git state.
        findings.append(Finding(
            "ALCANCE-GIT-ILEGIBLE",
            "No se pudo leer el estado de git (" + "; ".join(motivos) + "); "
            "el alcance no puede verificarse.",
            None,
        ))

    candidatas = sorted(r for r in tocados if not es_output_intrinseco(r))
    otros = _alcances_otros_changes(repo_root, control) if candidatas else {"validos": {}, "invalidos": []}
    hay_fuera_de_propio = False
    cid_propio = control.get("change_id")
    prefijo_propio = f"openspec/changes/{cid_propio}/" if isinstance(cid_propio, str) and cid_propio else None
    for r in candidatas:
        propia = repo_mod.path_matches_any(r, rutas_autorizadas)
        duenos = sorted(cid for cid, rutas in otros["validos"].items() if repo_mod.path_matches_any(r, rutas))
        if prefijo_propio and r.startswith(prefijo_propio):
            duenos = []  # R5: artefactos del propio Change nunca se atribuyen ni chocan con ajenos
        if propia:
            if duenos:
                findings.append(Finding(
                    "ALCANCE-CONFLICTO-CHANGES",
                    f"Archivo en el alcance propio y en el de otro(s) Change(s) activo(s) y aprobado(s) "
                    f"({', '.join(duenos)}): {r}",
                    r,
                ))
            continue
        hay_fuera_de_propio = True
        if not duenos:
            findings.append(Finding("ALCANCE-RUTA", f"Archivo fuera de alcance: {r}", r))
        elif len(duenos) == 1:
            findings.append(Finding(
                "ALCANCE-ATRIBUIDA-OTRO-CHANGE",
                f"Archivo fuera de alcance propio, atribuido al Change activo y aprobado '{duenos[0]}': {r}",
                r,
            ))
        else:
            findings.append(Finding(
                "ALCANCE-CONFLICTO-CHANGES",
                f"Archivo en el alcance de varios Changes activos y aprobados ({', '.join(duenos)}) "
                f"y no en el propio: {r}",
                r,
            ))
    if hay_fuera_de_propio:
        for cid, motivo in otros["invalidos"]:
            findings.append(Finding(
                "ALCANCE-OTRO-CHANGE-INVALIDO",
                f"El alcance del Change activo y aprobado '{cid}' no es verificable ({motivo}); "
                f"no autoriza ninguna ruta.",
                f"openspec/changes/{cid}",
            ))
    return findings


# --- Changes paralelos (v0.11, Change 4B) --------------------------------------------------

# Hallazgos de scope que se muestran pero NO cuentan como incumplimiento (R7): consumidores
# (`validate`, `gate_cierre`, `transition`, `archive`) filtran por código con `bloqueantes`.
CODIGOS_INFORMATIVOS = frozenset({"ALCANCE-ATRIBUIDA-OTRO-CHANGE"})


def es_informativo(hallazgo) -> bool:
    """True si el hallazgo es solo informativo (no bloquea gate ni exit code)."""
    return hallazgo.codigo in CODIGOS_INFORMATIVOS


def bloqueantes(hallazgos) -> list:
    """Subconjunto de `hallazgos` que sí cuenta como incumplimiento (excluye los informativos)."""
    return [h for h in hallazgos if not es_informativo(h)]


_ESTADOS_ACTIVOS = ("aprobada_implementacion", "en_implementacion", "en_verificacion")


def otros_changes_activos(repo_root: Path, change_id_propio) -> list:
    """`[(change_id, change_dir), ...]` ordenado: Changes de `openspec/changes/` (nunca `archive`)
    distintos del propio cuyo `tasks.md` declara un estado activo
    (`aprobada_implementacion`/`en_implementacion`/`en_verificacion`). `tasks.md` ausente/ilegible o
    estado desconocido/no activo (propuesta, diseño, pausada, cerrada, descartada) => NO cuenta
    (fail-closed: atribuir menos es el lado seguro; un Change sin aprobar no absorbe rutas).
    Este es solo un prefiltro autodeclarado en disco: el estado definitivo se verifica en
    `_alcances_otros_changes` sobre el snapshot del ajeno en el commit baseline del Change propio
    (SHA completo), con la aprobación de todos los artefactos requeridos y `scope_hash` inmutable."""
    base = Path(repo_root) / "openspec" / "changes"
    if not base.is_dir():
        return []
    from . import sdd  # import perezoso: sdd importa scope a nivel de módulo
    activos = []
    for candidato in sorted(base.iterdir(), key=lambda p: p.name):
        if not candidato.is_dir() or candidato.name == change_id_propio:
            continue
        try:
            estado, _ = sdd.read_estado(candidato / "tasks.md")
        except (OSError, ValueError):
            continue
        if estado in _ESTADOS_ACTIVOS:
            activos.append((candidato.name, candidato))
    return activos


def _es_patron_catch_all(patron) -> bool:
    """True si el patrón no tiene prefijo literal de directorio (`*`, `**`, `**/*`, `*/**`, `*.py`,
    `s?c/**`, `[a-z]*/**`...): cubriría todo el repo y por eso no se usa para atribuir ni para conflicto."""
    if not isinstance(patron, str):
        return True
    p = patron.replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    primero = p.split("/", 1)[0]
    return primero == "" or any(c in primero for c in "*?[")


def _patron_ajeno_descartable(patron) -> bool:
    """True si un patrón de alcance AJENO no debe atribuir ni generar conflicto: catch-all, o ruta
    inválida/protegida según `scope_amendments.motivo_ruta_invalida` (`..`, `.`, absolutas, `.git`,
    `.harmessi`, `data/raw`, guardrails/settings) o cualquier cosa bajo `.claude/`."""
    if _es_patron_catch_all(patron):
        return True
    if scope_amendments.motivo_ruta_invalida(patron) is not None:
        return True
    return patron.split("/", 1)[0].lower() == ".claude"


_RE_COMMIT_COMPLETO = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")


def _aprobacion_ajena_verificada(repo_root: Path, commit: str, cid: str):
    """Snapshot del ajeno EN el commit baseline propio. Devuelve `(control_baseline, None)` si en ese
    snapshot el `tasks.md` declara un estado activo y TODOS los artefactos de
    `sdd.artefactos_requeridos(modo)` tienen su aprobación más reciente (`aprobaciones[]` del
    control-baseline) con el hash `hash_lf_v1` del contenido del artefacto leído también en el
    baseline, y `alcance.scope_hash` presente; si no, `(None, None)`. Nunca lanza (fail-closed).
    No lee el disco: un ajeno forjado en el árbol de trabajo no puede autoaprobarse."""
    import json
    from . import sdd  # import perezoso: sdd importa scope a nivel de módulo
    try:
        base = f"openspec/changes/{cid}/"
        tasks = repo_mod.leer_en_commit(repo_root, commit, base + "tasks.md")
        crudo_control = repo_mod.leer_en_commit(repo_root, commit, base + "control.json")
        if tasks is None or crudo_control is None:
            return None, None
        coincidencias = [m.group(1) for linea, _ in sdd._dividir_lineas_preservando_terminadores(
            tasks.decode("utf-8")) if (m := sdd._PATRON_ESTADO_LINEA.match(linea))]
        if len(coincidencias) != 1 or coincidencias[0] not in _ESTADOS_ACTIVOS:
            return None, None
        ctrl = json.loads(crudo_control.decode("utf-8-sig"))
        if not isinstance(ctrl, dict):
            return None, None
        alc = ctrl.get("alcance")
        if not (isinstance(alc, dict) and isinstance(alc.get("scope_hash"), str) and alc["scope_hash"]):
            return None, None
        modo = ctrl.get("modo")
        if not isinstance(modo, str) or modo not in ("completo", "abreviado"):
            modo = "completo"
        aprobaciones = ctrl.get("aprobaciones")
        if not isinstance(aprobaciones, list):
            return None, None
        for artefacto in sdd.artefactos_requeridos(modo):
            contenido = repo_mod.leer_en_commit(repo_root, commit, base + artefacto)
            if contenido is None:
                return None, None
            propias = [a for a in aprobaciones if isinstance(a, dict) and a.get("artefacto") == artefacto]
            reciente = sdd._aprobacion_mas_reciente({"aprobaciones": propias}, artefacto)
            if not reciente or reciente.get("algoritmo", sdd._ALGORITMO_APROBACION) != sdd._ALGORITMO_APROBACION:
                return None, None
            h = reciente.get("hash")
            if not (isinstance(h, str) and sdd._RE_SHA256_HEX.fullmatch(h)) or h == sdd._HASH_CERO:
                return None, None
            if core.hash_lf_v1_bytes(contenido) != h:
                return None, None
        return ctrl, None
    except Exception:  # fail-closed
        return None, None


def _alcances_otros_changes(repo_root: Path, control: dict) -> dict:
    """`{"validos": {change_id: rutas}, "invalidos": [(change_id, motivo)]}` con el alcance efectivo
    (`alcance_efectivo`, misma cadena de enmiendas) de cada otro Change abierto. `control.json`
    ajeno ausente/ilegible/no-objeto o cadena de enmiendas inválida => inválido y NO autoriza nada."""
    import json
    change_id = control.get("change_id")
    validos, invalidos = {}, []
    if not isinstance(change_id, str) or not change_id:
        # Sin identidad propia no se puede distinguir «otro» Change: sin atribución (comportamiento previo).
        return {"validos": validos, "invalidos": invalidos}
    baseline_propio = (control.get("baseline") or {}).get("commit") if isinstance(control.get("baseline"), dict) else None
    if not (isinstance(baseline_propio, str) and _RE_COMMIT_COMPLETO.fullmatch(baseline_propio)):
        return {"validos": validos, "invalidos": invalidos}  # baseline no es un SHA completo: nadie cuenta
    for cid, cdir in otros_changes_activos(repo_root, change_id):
        # Estado activo y aprobación se verifican en el snapshot del baseline propio (no en disco).
        ctrl_base, _ = _aprobacion_ajena_verificada(repo_root, baseline_propio, cid)
        if ctrl_base is None:
            continue  # inexistente/no activo/no aprobado en el baseline propio: no cuenta
        try:
            ajeno = json.loads((cdir / "control.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            invalidos.append((cid, "control.json ausente o ilegible"))
            continue
        if not isinstance(ajeno, dict):
            invalidos.append((cid, "control.json no es un objeto"))
            continue
        alcance_ajeno = ajeno.get("alcance")
        if not (isinstance(alcance_ajeno, dict)
                and alcance_ajeno.get("scope_hash") == ctrl_base["alcance"]["scope_hash"]):
            # Ancla inmutable: el scope_hash aprobado en el baseline no puede cambiar después.
            invalidos.append((cid, "scope_hash distinto del aprobado en el baseline"))
            continue
        try:
            rutas, hallazgos = alcance_efectivo(cdir, ajeno)
        except Exception as exc:  # lectura tolerante de un Change ajeno: cualquier fallo => inválido
            invalidos.append((cid, f"alcance ilegible: {type(exc).__name__}"))
            continue
        if any(h.codigo == "ALCANCE-ENMIENDA-INVALIDA" for h in hallazgos):
            invalidos.append((cid, "cadena de enmiendas inválida"))
            continue
        # Patrones ajenos catch-all, inválidos o protegidos no atribuyen ni generan conflicto.
        validos[cid] = [r for r in rutas if isinstance(r, str) and not _patron_ajeno_descartable(r)]
    return {"validos": validos, "invalidos": invalidos}
