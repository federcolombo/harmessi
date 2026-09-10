#!/usr/bin/env python
"""`ds_guard`: verificador determinista para el proceso SDD de este proyecto.

Sesión A: `status`, `validate`, `approve`, `transition`, `session
{start,note,status,close}`. Sesión B agrega `notebook-diff` y `archive`. Sesión
de corrección agrega `init` (scaffolding de un cambio nuevo desde plantillas).

Códigos de salida generales (ver spec.md):
    0 correcto
    1 gate/validación incumplida (incluye SESION-AUSENTE)
    2 error de uso/configuración
    3 error de entorno/git/herramienta

Solo biblioteca estándar. No instala ni importa nada fuera de `tools/dsguard`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# La consola/pipe que invoca este CLI puede estar en una codificación distinta
# de UTF-8 (p. ej. cp1252 en Windows). Forzamos stdout/stderr a UTF-8 real para
# que el texto en español (tildes, "ñ") y el JSON de salida sean deterministas
# sin importar quién lo invoque (terminal, subprocess de test, etc.).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dsguard import core, kdd, notebooks, repo, sdd  # noqa: E402


# --- Helpers compartidos --------------------------------------------------

def _repo_root() -> Path:
    return repo.find_repo_root(Path.cwd())


def _change_dir(repo_root: Path, change_id: str) -> Path:
    return repo_root / "openspec" / "changes" / change_id


def _cargar_change(repo_root: Path, change_id: str):
    """Devuelve (change_dir, tasks_path, control_path, control) o levanta
    SystemExit con el código de error apropiado si algo no está en orden."""
    change_dir = _change_dir(repo_root, change_id)
    tasks_path = change_dir / "tasks.md"
    control_path = change_dir / "control.json"
    if not tasks_path.exists() or not control_path.exists():
        print(
            f"No existen tasks.md/control.json para el cambio '{change_id}' en {change_dir}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        control = core.leer_control(control_path)
    except core.ControlJsonError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(2)
    return change_dir, tasks_path, control_path, control


def _imprimir_findings(findings: list, exit_code: int, como_json: bool) -> None:
    if como_json:
        print(core.formatear_findings_json(findings, exit_code))
    else:
        print(core.formatear_findings_texto(findings))


# --- status -----------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    estado, err = sdd.read_estado(tasks_path)

    discrepancia = None
    if estado is not None:
        transiciones = control.get("transiciones", [])
        if transiciones and transiciones[-1].get("hacia") != estado:
            discrepancia = (
                f"tasks.md dice '{estado}' pero la última transición registrada en "
                f"control.json dice '{transiciones[-1].get('hacia')}'"
            )

    sesion_activa = sdd._sesion_activa(control)
    sesion_info = sdd.session_status(control)

    rutas_autorizadas = control.get("alcance", {}).get("rutas_autorizadas", [])
    fuera_de_alcance = repo.files_out_of_scope(repo_root, rutas_autorizadas)

    if args.json:
        payload = {
            "change_id": args.change_id,
            "estado": estado,
            "errores_estado": [f.to_dict() for f in err],
            "discrepancia": discrepancia,
            "sesion": sesion_info,
            "fuera_de_alcance": fuera_de_alcance,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Cambio: {args.change_id}")
        print(f"Estado (tasks.md): {estado if estado is not None else 'ILEGIBLE'}")
        for f in err:
            print(f"  [{f.codigo}] {f.mensaje}")
        if discrepancia:
            print(f"Discrepancia: {discrepancia}")
        if sesion_activa:
            print(
                f"Sesión activa: {sesion_info['id']} "
                f"({sesion_info['minutos_transcurridos']:.1f} min transcurridos)"
            )
        else:
            print("Sin sesión activa.")
        if fuera_de_alcance:
            print("Archivos fuera de alcance (informativo):")
            for r in fuera_de_alcance:
                print(f"  - {r}")

    return 0


# --- validate -----------------------------------------------------------------

def cmd_validate(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    findings = []

    estado, err = sdd.read_estado(tasks_path)
    findings += err

    rutas_autorizadas = control.get("alcance", {}).get("rutas_autorizadas", [])
    for r in repo.files_out_of_scope(repo_root, rutas_autorizadas):
        findings.append(core.Finding("ALCANCE-RUTA", f"Archivo fuera de alcance: {r}", r))
    for linea in repo.diff_check(repo_root):
        findings.append(core.Finding("ALCANCE-WHITESPACE", linea))

    sesion_activa = sdd._sesion_activa(control)

    if args.gate:
        # Excepción (spec requisito 8): un cambio ya cerrado puede validar el
        # gate de cierre sin sesión activa, sin el finding bloqueante
        # SESION-AUSENTE -- mismo patrón que ya usa `cmd_archive` al llamar
        # `gate_cierre(..., None, ...)` (tools/ds_guard.py, cmd_archive). La
        # transición real a `cerrada` (`transition --a cerrada`) sigue
        # exigiendo sesión activa sin excepción, vía `_findings_del_gate`.
        if sesion_activa is None and not (args.gate == "cierre" and estado == "cerrada"):
            findings.append(
                core.Finding("SESION-AUSENTE", f"Se requiere sesión activa para validar el gate '{args.gate}'")
            )
        else:
            if args.gate == "implementacion":
                findings += sdd.gate_implementacion(control, tasks_path, sesion_activa)
            elif args.gate == "cierre":
                findings += sdd.gate_cierre(control, tasks_path, sesion_activa, repo_root)

    if sesion_activa is not None:
        findings += sdd.chequear_limites(sesion_activa)

    exit_code = 1 if findings else 0
    _imprimir_findings(findings, exit_code, args.json)
    return exit_code


# --- approve --------------------------------------------------------------

def cmd_approve(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    for artefacto in args.artefacto:
        if not (change_dir / artefacto).exists():
            print(f"El artefacto no existe: {artefacto}", file=sys.stderr)
            return 2

    entradas = []
    for artefacto in args.artefacto:
        ruta = change_dir / artefacto
        hash_valor = core.hash_lf_v1(ruta)
        entrada = {
            "artefacto": artefacto,
            "algoritmo": "sha256/lf/v1",
            "hash": hash_valor,
            "registrado_utc": core.ahora_utc(),
            "usuario": args.usuario,
            "fecha_declarada": args.fecha,
            "alcance_aprobado": args.alcance,
            "cita": args.cita,
        }
        control.setdefault("aprobaciones", []).append(entrada)
        entradas.append(entrada)

    core.escribir_control(control_path, control)

    for e in entradas:
        print(f"{e['artefacto']}: {e['hash']}")
    print("el hash acredita identidad de contenido, no aprobación humana")
    return 0


# --- transition -----------------------------------------------------------

def cmd_transition(args: argparse.Namespace) -> int:
    if args.a not in sdd.ESTADOS_VALIDOS:
        print(f"Estado destino desconocido: {args.a}", file=sys.stderr)
        return 2

    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    if args.a == "cerrada":
        # Pre-chequeo KDD (Bloque 4): corre ANTES de tocar tasks.md/control.json,
        # para que un state.json ausente/corrupto bloquee el cierre de forma
        # atómica en vez de dejarlo cerrado sin evidencia KDD sincronizada
        # ("no debe quedar silenciosamente inconsistente"). Si el cambio no
        # declara ninguna etapa KDD, esto es un no-op (lista vacía).
        pre_findings = kdd.validar_antes_de_cerrar(repo_root, control)
        if pre_findings:
            _imprimir_findings(pre_findings, 1, args.json)
            return 1

    sesion_activa = sdd._sesion_activa(control)
    ok, findings = sdd.transition(control, tasks_path, control_path, repo_root, args.a, sesion_activa)

    if not ok:
        _imprimir_findings(findings, 1, args.json)
        return 1

    kdd_sync_resultado = None
    kdd_sync_error = None
    if args.a == "cerrada":
        try:
            kdd_sync_resultado = kdd.sync_al_cerrar(repo_root, control, args.change_id)
        except Exception as e:  # nunca silencioso: la transición SDD ya se aplicó
            kdd_sync_error = str(e)

    if args.json:
        payload = {"transicion_aplicada": args.a}
        if kdd_sync_resultado is not None:
            payload["kdd_sync"] = kdd_sync_resultado
        if kdd_sync_error is not None:
            payload["kdd_sync_error"] = kdd_sync_error
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"Transición aplicada -> {args.a}")
        if kdd_sync_resultado is not None:
            if kdd_sync_resultado["sincronizado"]:
                print(f"KDD sincronizado: {', '.join(kdd_sync_resultado['etapas_actualizadas'])}")
            else:
                print(f"KDD: {kdd_sync_resultado['motivo']}")
        if kdd_sync_error is not None:
            print(f"[KDD-SYNC-FALLO] {kdd_sync_error}", file=sys.stderr)

    return 1 if kdd_sync_error is not None else 0


# --- session ----------------------------------------------------------------

def cmd_session_start(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    try:
        entrada = sdd.session_start(
            control,
            modo=args.modo,
            minutos=args.minutos,
            max_tareas=args.max_tareas,
            max_roles=args.max_roles,
            max_reintentos=args.max_reintentos,
            max_rondas_revision=args.max_rondas,
        )
    except sdd.SesionYaActivaError as e:
        print(str(e), file=sys.stderr)
        return 2

    core.escribir_control(control_path, control)
    print(f"Sesión iniciada: {entrada['id']}")
    return 0


def cmd_session_note(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    try:
        sdd.session_note(control, args.rol, args.tipo, args.tarea)
    except (sdd.SesionAusenteError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 2

    core.escribir_control(control_path, control)
    return 0


def cmd_session_status(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    estado = sdd.session_status(control)
    if args.json:
        print(json.dumps(estado, indent=2, ensure_ascii=False))
    else:
        if not estado["activa"]:
            print("No hay sesión activa.")
        else:
            print(f"Sesión activa: {estado['id']} ({estado['minutos_transcurridos']:.1f} min transcurridos)")
            print(
                f"tareas={estado['tareas']} roles={estado['roles']} "
                f"reintentos={estado['reintentos']} rondas_revision={estado['rondas_revision']}"
            )
            for f in estado["findings"]:
                print(f"  [{f['codigo']}] {f['mensaje']}")
    return 0


def cmd_session_close(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    try:
        cerrada = sdd.session_close(control, args.estado)
    except sdd.SesionAusenteError as e:
        print(str(e), file=sys.stderr)
        return 2

    core.escribir_control(control_path, control)

    # Mensaje final visible (spec requisito 7): según `estado_final` +
    # `resultado`, ambos ya derivados automáticamente por `session_close` --
    # nunca a partir de un flag declarado a mano.
    estado_final = cerrada.get("estado_final")
    resultado = cerrada.get("resultado")
    if resultado == "excedida":
        print("🛑 PRESUPUESTO AGOTADO")
    elif estado_final == "completada":
        print("✅ SESIÓN TERMINADA")
    elif estado_final == "pausada":
        print("⏸️ SESIÓN PAUSADA")
    print("Sesión cerrada.")
    return 0


# --- notebook-diff -----------------------------------------------------------

def cmd_notebook_diff(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    estado, err_estado = sdd.read_estado(tasks_path)

    if args.tocados:
        rutas = [r for r in repo.list_dirty_files(repo_root) if r.endswith(".ipynb")]
    else:
        rutas = list(args.path or [])
    if not rutas:
        print("Debe indicar --path (repetible) o --tocados", file=sys.stderr)
        return 2

    if args.contra == "baseline":
        rev = control.get("baseline", {}).get("commit")
        if not rev:
            print("No hay baseline.commit registrado en control.json", file=sys.stderr)
            return 2
    else:
        rev = args.contra

    bloqueantes = list(err_estado)
    informativos = []
    resumen_total = []
    conteos_total = {"agregadas": 0, "eliminadas": 0, "modificadas": 0, "solo_ejecucion": 0}

    for ruta in rutas:
        resultado = notebooks.diff_archivo(repo_root, ruta, rev, estado)
        if resultado.get("error_uso") is not None:
            print(resultado["error_uso"].mensaje, file=sys.stderr)
            return 2
        bloqueantes += resultado["bloqueantes"]
        informativos += resultado["informativos"]
        resumen_total += resultado["resumen"]
        for clave in conteos_total:
            conteos_total[clave] += resultado["conteos"].get(clave, 0)

    recorte = None
    if len(resumen_total) > args.max_celdas:
        recorte = {"mostradas": args.max_celdas, "totales": len(resumen_total)}
        resumen_total = resumen_total[: args.max_celdas]

    exit_code = 1 if bloqueantes else 0
    todos = bloqueantes + informativos

    if args.json:
        payload = {
            "findings": [f.to_dict() for f in todos],
            "exit_code": exit_code,
            "conteos": conteos_total,
            "resumen_celdas": resumen_total,
            "recorte": recorte,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(core.formatear_findings_texto(todos))
        print(
            f"{conteos_total['agregadas']} celdas agregadas, "
            f"{conteos_total['eliminadas']} eliminadas, "
            f"{conteos_total['modificadas']} celdas modificadas, "
            f"{conteos_total['solo_ejecucion']} solo_ejecucion"
        )
        if recorte:
            print(
                f"Recortado: se muestran {recorte['mostradas']} de "
                f"{recorte['totales']} celdas cambiadas"
            )

    return exit_code


# --- archive --------------------------------------------------------------

def cmd_archive(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir, tasks_path, control_path, control = _cargar_change(repo_root, args.change_id)

    estado, err_estado = sdd.read_estado(tasks_path)
    if err_estado:
        _imprimir_findings(err_estado, 1, args.json)
        return 1
    if estado != "cerrada":
        finding = core.Finding(
            "SDD-ARCHIVO-ESTADO-INVALIDO",
            f"Estado actual '{estado}' no permite archivar (se requiere 'cerrada')",
            str(tasks_path),
        )
        _imprimir_findings([finding], 1, args.json)
        return 1

    findings_gate = sdd.gate_cierre(control, tasks_path, None, repo_root)
    if findings_gate:
        _imprimir_findings(findings_gate, 1, args.json)
        return 1

    ruta_relativa_change = change_dir.relative_to(repo_root).as_posix()
    resultado_ls = repo._git(repo_root, "ls-files", "--", ruta_relativa_change)
    if not resultado_ls.stdout.strip():
        finding = core.Finding(
            "SDD-ARCHIVO-NO-VERSIONADO",
            f"El directorio del cambio no está versionado: {ruta_relativa_change}",
            ruta_relativa_change,
        )
        _imprimir_findings([finding], 1, args.json)
        return 1

    if not repo.is_tree_clean(repo_root):
        finding = core.Finding(
            "ALCANCE-TREE-SUCIO",
            "El working tree no está limpio: no se puede archivar",
        )
        _imprimir_findings([finding], 1, args.json)
        return 1

    destino_relativo = f"openspec/archive/{args.change_id}"
    destino_abs = repo_root / "openspec" / "archive" / args.change_id
    if destino_abs.exists():
        print(f"El destino ya existe, no se pisa: {destino_relativo}", file=sys.stderr)
        return 2

    if not args.execute:
        if args.json:
            print(
                json.dumps(
                    {
                        "dry_run": True,
                        "origen": ruta_relativa_change,
                        "destino": destino_relativo,
                    },
                    ensure_ascii=False,
                )
            )
        else:
            print(f"[dry-run] {ruta_relativa_change} -> {destino_relativo} (nada movido)")
        return 0

    # `git mv` no crea el directorio padre del destino: en un repo donde
    # `openspec/archive/` todavía no existe (primer archivado), el rename
    # fallaría con "No such file or directory". Solo se crea el padre, nunca
    # el destino final (`openspec/archive/<id>/`), que lo crea el propio
    # `git mv` como parte del rename.
    (repo_root / "openspec" / "archive").mkdir(parents=True, exist_ok=True)

    resultado_mv = repo._git(repo_root, "mv", ruta_relativa_change, destino_relativo)
    if resultado_mv.returncode != 0:
        print(f"git mv falló: {resultado_mv.stderr.strip()}", file=sys.stderr)
        return 3

    nuevo_control_path = destino_abs / "control.json"
    control["archivado"] = {"utc": core.ahora_utc(), "destino": destino_relativo}
    core.escribir_control(nuevo_control_path, control)

    if args.json:
        print(
            json.dumps(
                {"archivado": True, "origen": ruta_relativa_change, "destino": destino_relativo},
                ensure_ascii=False,
            )
        )
    else:
        print(f"Archivado: {ruta_relativa_change} -> {destino_relativo}")
    return 0


# --- kdd ---------------------------------------------------------------------

def cmd_kdd_init(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3

    try:
        estado, creado = kdd.kdd_init(repo_root)
    except kdd.KddEstadoError as e:
        print(str(e), file=sys.stderr)
        return 1

    ruta_relativa = kdd.state_path(repo_root).relative_to(repo_root).as_posix()
    if args.json:
        print(json.dumps({"creado": creado, "ruta": ruta_relativa}, ensure_ascii=False))
    else:
        if creado:
            print(f"KDD inicializado: {ruta_relativa}")
        else:
            print(f"{ruta_relativa} ya existía: init es idempotente, no se modificó nada.")
    return 0


def cmd_kdd_status(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3

    ruta = kdd.state_path(repo_root)
    if not ruta.exists():
        print(
            f"{ruta.relative_to(repo_root).as_posix()} no existe. Correr 'ds_guard kdd init' primero.",
            file=sys.stderr,
        )
        return 2
    try:
        payload = kdd.kdd_status(repo_root)
    except kdd.KddEstadoError as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for etapa in kdd.ETAPAS:
            info = payload["etapas"][etapa]
            print(f"{etapa}: {info['estado']} ({len(info['changes'])} cambio(s))")
            for c in info["criterios_detectables"]:
                marca = "OK" if c["cumplido"] else "--"
                print(f"    [{marca}] {c['criterio']}")
            if info["changes_no_localizados"]:
                print(
                    "    (no localizados en openspec/changes/ ni openspec/archive/: "
                    + ", ".join(info["changes_no_localizados"])
                    + ")"
                )
    return 0


def cmd_kdd_transition(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3

    ruta = kdd.state_path(repo_root)
    if not ruta.exists():
        print(
            f"{ruta.relative_to(repo_root).as_posix()} no existe. Correr 'ds_guard kdd init' primero.",
            file=sys.stderr,
        )
        return 2

    try:
        ok, findings = kdd.kdd_transition(repo_root, args.etapa, args.a, motivo=args.motivo)
    except kdd.KddEstadoError as e:
        print(str(e), file=sys.stderr)
        return 1

    if ok:
        if args.json:
            print(json.dumps({"transicion_aplicada": {"etapa": args.etapa, "hacia": args.a}}, ensure_ascii=False))
        else:
            print(f"Transición KDD aplicada -> {args.etapa}: {args.a}")
        return 0

    _imprimir_findings(findings, 1, args.json)
    return 1


# --- init -------------------------------------------------------------------

# Artefactos posibles de un cambio: si cualquiera ya existe, `init` no toca
# nada (nunca sobreescribe un cambio existente).
_ARTEFACTOS_CAMBIO = ("proposal.md", "tasks.md", "spec.md", "design.md", "control.json")

_PLANTILLAS_POR_MODO = {
    "abreviado": ("proposal", "tasks"),
    "completo": ("proposal", "tasks", "spec", "design"),
}


def _change_id_invalido(change_id: str) -> bool:
    """True si `change_id` puede escapar de `openspec/changes/<change_id>/`:
    componente `..`, separador de ruta (`/` o `\\`) o ruta absoluta. `init` es
    la primera escritura "desde cero" para un `change_id` (a diferencia del
    resto de los comandos, que exigen que el directorio ya exista vía
    `_cargar_change`), así que acá sí hay que validar antes de escribir."""
    if ".." in Path(change_id).parts:
        return True
    if "/" in change_id or "\\" in change_id:
        return True
    if Path(change_id).is_absolute():
        return True
    return False


def cmd_init(args: argparse.Namespace) -> int:
    if _change_id_invalido(args.change_id):
        print(
            f"--change-id inválido: {args.change_id!r}. Debe ser un slug simple "
            "(letras, dígitos, guiones) sin separadores de ruta ni '..'",
            file=sys.stderr,
        )
        return 2

    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 3
    change_dir = _change_dir(repo_root, args.change_id)

    ya_presentes = [a for a in _ARTEFACTOS_CAMBIO if (change_dir / a).exists()]
    if ya_presentes:
        print(
            f"El cambio '{args.change_id}' ya tiene artefactos en {change_dir}: "
            f"{', '.join(ya_presentes)} — 'init' nunca sobreescribe un cambio existente",
            file=sys.stderr,
        )
        return 2

    templates_dir = repo_root / ".claude" / "skills" / "lead-data-scientist" / "templates"
    nombres_md = _PLANTILLAS_POR_MODO[args.modo]

    archivos_creados = []
    for nombre in nombres_md:
        plantilla_path = templates_dir / f"{nombre}.md"
        if not plantilla_path.exists():
            ya_creados = ", ".join(archivos_creados) if archivos_creados else "(ninguno)"
            print(
                f"Falta la plantilla requerida: {plantilla_path}. "
                f"Artefactos ya creados en esta corrida: {ya_creados}",
                file=sys.stderr,
            )
            return 3
        texto = plantilla_path.read_text(encoding="utf-8")
        texto = texto.replace("<change-id>", args.change_id)
        core.escribir_texto_atomico(change_dir / f"{nombre}.md", texto)
        archivos_creados.append(f"{nombre}.md")

    commit, rama = repo.get_head(repo_root)
    baseline = {
        "commit": commit,
        "rama": rama,
        "capturado_utc": core.ahora_utc(),
    }
    rutas_autorizadas = [
        f"openspec/changes/{args.change_id}/{nombre}" for nombre in archivos_creados
    ]
    rutas_autorizadas.append(f"openspec/changes/{args.change_id}/control.json")

    control = {
        "schema_version": 1,
        "change_id": args.change_id,
        "modo": args.modo,
        "origen": "ds_guard init",
        "creado_utc": core.ahora_utc(),
        "baseline": baseline,
        "alcance": {"rutas_autorizadas": rutas_autorizadas},
        "aprobaciones": [],
        "transiciones": [],
        "sesiones": [],
    }
    core.escribir_control(change_dir / "control.json", control)
    archivos_creados.append("control.json")

    if args.json:
        print(
            json.dumps(
                {
                    "change_id": args.change_id,
                    "modo": args.modo,
                    "archivos_creados": archivos_creados,
                    "baseline": baseline,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"Cambio inicializado: {args.change_id} (modo {args.modo})")
        for nombre_archivo in archivos_creados:
            print(f"  creado: openspec/changes/{args.change_id}/{nombre_archivo}")
    return 0


# --- argparse -----------------------------------------------------------------

def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ds_guard", description=__doc__)
    subparsers = parser.add_subparsers(dest="comando", required=True)

    p_init = subparsers.add_parser(
        "init", help="Crea el scaffolding de un cambio nuevo desde las plantillas versionadas."
    )
    p_init.add_argument("--change-id", required=True)
    p_init.add_argument("--modo", required=True, choices=["completo", "abreviado"])
    p_init.add_argument("--json", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_status = subparsers.add_parser("status", help="Estado actual del cambio (informativo).")
    p_status.add_argument("--change-id", required=True)
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=cmd_status)

    p_validate = subparsers.add_parser("validate", help="Corre chequeos deterministas sobre el cambio.")
    p_validate.add_argument("--change-id", required=True)
    p_validate.add_argument("--gate", choices=["implementacion", "cierre"], default=None)
    p_validate.add_argument("--json", action="store_true")
    p_validate.set_defaults(func=cmd_validate)

    p_approve = subparsers.add_parser("approve", help="Registra la aprobación (hash) de uno o más artefactos.")
    p_approve.add_argument("--change-id", required=True)
    p_approve.add_argument("--artefacto", action="append", required=True, dest="artefacto")
    p_approve.add_argument("--usuario", required=True)
    p_approve.add_argument("--fecha", required=True)
    p_approve.add_argument("--alcance", required=True)
    p_approve.add_argument("--cita", required=True)
    p_approve.set_defaults(func=cmd_approve)

    p_transition = subparsers.add_parser("transition", help="Aplica una transición de estado SDD.")
    p_transition.add_argument("--change-id", required=True)
    p_transition.add_argument("--a", required=True, dest="a")
    p_transition.add_argument("--motivo", default=None)
    p_transition.add_argument("--json", action="store_true")
    p_transition.set_defaults(func=cmd_transition)

    p_session = subparsers.add_parser("session", help="Gestión de sesiones de trabajo.")
    session_sub = p_session.add_subparsers(dest="subcomando", required=True)

    p_session_start = session_sub.add_parser("start")
    p_session_start.add_argument("--change-id", required=True)
    p_session_start.add_argument("--modo", default="estandar")
    p_session_start.add_argument("--minutos", type=int, default=90)
    p_session_start.add_argument("--max-tareas", type=int, default=3)
    p_session_start.add_argument("--max-roles", type=int, default=2)
    p_session_start.add_argument("--max-reintentos", type=int, default=2)
    p_session_start.add_argument("--max-rondas", type=int, default=2)
    p_session_start.set_defaults(func=cmd_session_start)

    p_session_note = session_sub.add_parser("note")
    p_session_note.add_argument("--change-id", required=True)
    p_session_note.add_argument("--rol", default=None)
    p_session_note.add_argument("--tipo", required=True, choices=["planificada", "reintento", "ronda"])
    p_session_note.add_argument("--tarea", default=None)
    p_session_note.set_defaults(func=cmd_session_note)

    p_session_status = session_sub.add_parser("status")
    p_session_status.add_argument("--change-id", required=True)
    p_session_status.add_argument("--json", action="store_true")
    p_session_status.set_defaults(func=cmd_session_status)

    p_session_close = session_sub.add_parser("close")
    p_session_close.add_argument("--change-id", required=True)
    p_session_close.add_argument("--estado", required=True, choices=["completada", "pausada"])
    p_session_close.set_defaults(func=cmd_session_close)

    p_notebook_diff = subparsers.add_parser(
        "notebook-diff", help="Diff por celdas de uno o más .ipynb contra una revisión de git. Nunca ejecuta."
    )
    p_notebook_diff.add_argument("--change-id", required=True)
    p_notebook_diff.add_argument("--path", action="append", default=None)
    p_notebook_diff.add_argument("--tocados", action="store_true")
    p_notebook_diff.add_argument("--contra", default="baseline")
    p_notebook_diff.add_argument("--max-celdas", type=int, default=200, dest="max_celdas")
    p_notebook_diff.add_argument("--json", action="store_true")
    p_notebook_diff.set_defaults(func=cmd_notebook_diff)

    p_kdd = subparsers.add_parser("kdd", help="Lifecycle KDD del proyecto (openspec/kdd/state.json).")
    kdd_sub = p_kdd.add_subparsers(dest="subcomando", required=True)

    p_kdd_init = kdd_sub.add_parser("init", help="Crea openspec/kdd/state.json si no existe (idempotente).")
    p_kdd_init.add_argument("--json", action="store_true")
    p_kdd_init.set_defaults(func=cmd_kdd_init)

    p_kdd_status = kdd_sub.add_parser(
        "status", help="Estado de las 10 etapas KDD y criterios detectables (informativo)."
    )
    p_kdd_status.add_argument("--json", action="store_true")
    p_kdd_status.set_defaults(func=cmd_kdd_status)

    p_kdd_transition = kdd_sub.add_parser("transition", help="Avanza/retrocede el estado de una etapa KDD.")
    p_kdd_transition.add_argument("--etapa", required=True, choices=list(kdd.ETAPAS))
    p_kdd_transition.add_argument(
        "--a", required=True, dest="a", choices=sorted(kdd.ESTADOS_ETAPA_DESTINO_VALIDOS)
    )
    p_kdd_transition.add_argument("--motivo", default=None)
    p_kdd_transition.add_argument("--json", action="store_true")
    p_kdd_transition.set_defaults(func=cmd_kdd_transition)

    p_archive = subparsers.add_parser(
        "archive", help="Archiva un cambio cerrado de openspec/changes/ a openspec/archive/ (git mv)."
    )
    p_archive.add_argument("--change-id", required=True)
    grupo_archive = p_archive.add_mutually_exclusive_group()
    grupo_archive.add_argument("--dry-run", action="store_true", help="No mueve nada (comportamiento por defecto).")
    grupo_archive.add_argument("--execute", action="store_true", help="Ejecuta el git mv real.")
    p_archive.add_argument("--json", action="store_true")
    p_archive.set_defaults(func=cmd_archive)

    return parser


def main(argv=None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
