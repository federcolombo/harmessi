"""Vocabulario y mecánica SDD: estados, transiciones, gates, aprobaciones y
sesiones. No ejecuta `git` directamente (usa `repo.py` para eso) y no conoce
JSON de bajo nivel (usa `core.py` para eso).
"""
from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path
from typing import Optional

from . import repo as repo_mod
from .core import Finding, ahora_utc, escribir_control, hash_lf_v1, minutos_restantes, parsear_utc

# --- Estados y transiciones ----------------------------------------------------

ESTADOS_VALIDOS = {
    "propuesta_pendiente",
    "aprobada_diseño",
    "aprobada_implementacion",
    "en_implementacion",
    "en_verificacion",
    "cerrada",
    "descartada",
    "pausada_bloqueada",
}

# Estado actual -> conjunto de destinos válidos, según la tabla de la spec
# (sección 5.2). El destino "de vuelta" de `pausada_bloqueada` no es fijo: es
# el estado previo registrado en `control["transiciones"]`, resuelto en
# `es_transicion_valida`.
TRANSICIONES_VALIDAS = {
    "propuesta_pendiente": {
        "aprobada_diseño",
        "aprobada_implementacion",
        "descartada",
        "pausada_bloqueada",
    },
    "aprobada_diseño": {
        "aprobada_implementacion",
        "descartada",
        "pausada_bloqueada",
    },
    "aprobada_implementacion": {
        "en_implementacion",
        "pausada_bloqueada",
    },
    "en_implementacion": {
        "en_verificacion",
        "pausada_bloqueada",
    },
    "en_verificacion": {
        "cerrada",
        "en_implementacion",
        "pausada_bloqueada",
    },
    "pausada_bloqueada": {
        "descartada",
    },
    "cerrada": set(),
    "descartada": set(),
}


def _estado_previo_a_pausa(control: dict) -> Optional[str]:
    """`desde` de la última transición hacia `pausada_bloqueada` registrada en
    `control["transiciones"]` — es el estado al que `pausada_bloqueada` puede
    volver."""
    for entrada in reversed(control.get("transiciones", [])):
        if entrada.get("hacia") == "pausada_bloqueada":
            return entrada.get("desde")
    return None


def es_transicion_valida(control: dict, desde: str, hacia: str) -> bool:
    if desde not in ESTADOS_VALIDOS or hacia not in ESTADOS_VALIDOS:
        return False
    # Regla de modo: aprobada_diseño es exclusivo de modo completo.
    if hacia == "aprobada_diseño" and control.get("modo") == "abreviado":
        return False
    if hacia in TRANSICIONES_VALIDAS.get(desde, set()):
        return True
    if desde == "pausada_bloqueada":
        previo = _estado_previo_a_pausa(control)
        if previo is not None and hacia == previo:
            return True
    return False


# --- Parseo/escritura de `estado:` en tasks.md ---------------------------------

_PATRON_ESTADO_LINEA = re.compile(r"^estado:\s*(\S+)\s*$")


def _dividir_lineas_preservando_terminadores(texto: str) -> list:
    """Lista de (contenido_sin_terminador, terminador) por línea, soportando
    `\\n`, `\\r\\n` y `\\r` sueltos, sin normalizar nada."""
    lineas = []
    inicio = 0
    i = 0
    n = len(texto)
    while i < n:
        c = texto[i]
        if c == "\n":
            lineas.append((texto[inicio:i], "\n"))
            inicio = i + 1
            i += 1
        elif c == "\r":
            if i + 1 < n and texto[i + 1] == "\n":
                lineas.append((texto[inicio:i], "\r\n"))
                inicio = i + 2
                i += 2
            else:
                lineas.append((texto[inicio:i], "\r"))
                inicio = i + 1
                i += 1
        else:
            i += 1
    if inicio < n:
        lineas.append((texto[inicio:n], ""))
    return lineas


def read_estado(tasks_path: Path):
    """(estado, findings). `estado` es `None` si hubo error (ver `findings`)."""
    with open(tasks_path, "r", encoding="utf-8", newline="") as f:
        contenido = f.read()
    lineas = _dividir_lineas_preservando_terminadores(contenido)
    coincidencias = []
    for contenido_linea, _ in lineas:
        m = _PATRON_ESTADO_LINEA.match(contenido_linea)
        if m:
            coincidencias.append(m.group(1))
    if len(coincidencias) == 0:
        return None, [
            Finding("SDD-ESTADO-ILEGIBLE", "No se encontró una línea 'estado:' en tasks.md", str(tasks_path))
        ]
    if len(coincidencias) >= 2:
        return None, [
            Finding(
                "SDD-ESTADO-DUPLICADO",
                f"Se encontraron {len(coincidencias)} líneas 'estado:' en tasks.md",
                str(tasks_path),
            )
        ]
    estado = coincidencias[0]
    if estado not in ESTADOS_VALIDOS:
        return None, [
            Finding("SDD-ESTADO-ILEGIBLE", f"Estado '{estado}' no es un estado SDD válido", str(tasks_path))
        ]
    return estado, []


def write_estado(tasks_path: Path, nuevo_estado: str) -> bool:
    """Reescribe únicamente la línea `estado:` (una sola ocurrencia exigida),
    preservando el resto del archivo carácter por carácter, incluidos los
    finales de línea de las demás líneas. Devuelve False sin escribir nada si
    no hay exactamente una línea `estado:`."""
    with open(tasks_path, "r", encoding="utf-8", newline="") as f:
        contenido = f.read()
    lineas = _dividir_lineas_preservando_terminadores(contenido)
    indices = [i for i, (c, _) in enumerate(lineas) if _PATRON_ESTADO_LINEA.match(c)]
    if len(indices) != 1:
        return False
    idx = indices[0]
    _, terminador = lineas[idx]
    lineas[idx] = (f"estado: {nuevo_estado}", terminador)
    nuevo_contenido = "".join(c + t for c, t in lineas)
    tasks_path = Path(tasks_path)
    tmp = tasks_path.parent / (tasks_path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(nuevo_contenido)
    import os

    os.replace(tmp, tasks_path)
    return True


# --- Secciones de texto libre (Próximo paso / evidencia de cierre) -------------

def _contenido_de_seccion(texto: str, encabezado: str) -> str:
    """Contenido de una sección `## Encabezado` hasta el próximo `## ` (o fin de
    archivo), sin comentarios HTML de plantilla, recortado."""
    patron = re.compile(
        r"^" + re.escape(encabezado) + r"\s*\n(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = patron.search(texto)
    if not m:
        return ""
    sin_comentarios = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.DOTALL)
    return sin_comentarios.strip()


def hallar_proximo_paso(tasks_path: Path) -> str:
    with open(tasks_path, "r", encoding="utf-8") as f:
        contenido = f.read()
    return _contenido_de_seccion(contenido, "## Próximo paso exacto")


_SECCIONES_EVIDENCIA_CIERRE = ("## Evidencia obtenida", "## Resultado final")


def _tiene_evidencia_real(texto_verification: str) -> bool:
    return any(_contenido_de_seccion(texto_verification, s) for s in _SECCIONES_EVIDENCIA_CIERRE)


def _tiene_seccion_verificacion_en_tasks(texto_tasks: str) -> bool:
    for encabezado in ("## Verificación", "## Verificacion"):
        if _contenido_de_seccion(texto_tasks, encabezado):
            return True
    return False


# --- Aprobaciones --------------------------------------------------------------

def artefactos_requeridos(modo: str) -> list:
    if modo == "abreviado":
        return ["proposal.md"]
    return ["proposal.md", "spec.md", "design.md"]


def _aprobacion_mas_reciente(control: dict, artefacto: str) -> Optional[dict]:
    candidatas = [a for a in control.get("aprobaciones", []) if a.get("artefacto") == artefacto]
    if not candidatas:
        return None
    # Append-only: la última de la lista ya es la más reciente; se ordena por
    # 'registrado_utc' además para ser robustos ante reordenamientos manuales.
    return sorted(candidatas, key=lambda a: a.get("registrado_utc", ""))[-1]


# --- Gates -----------------------------------------------------------------

def gate_implementacion(
    control: dict,
    tasks_path: Path,
    sesion_activa: Optional[dict],
    exigir_estado_valido: bool = True,
) -> list:
    """Ver spec 5.3. `sesion_activa` no se usa dentro del gate: la exigencia de
    sesión activa la aplica el llamador (`validate`/`transition`), que agrega
    `SESION-AUSENTE` por separado — así el mismo gate sirve para el chequeo
    "sin sesión" de `→ aprobada_implementacion`."""
    findings = []
    change_dir = Path(tasks_path).parent

    if exigir_estado_valido:
        estado, err = read_estado(tasks_path)
        if err:
            return err
        if estado not in ("aprobada_implementacion", "en_implementacion"):
            findings.append(
                Finding(
                    "SDD-TRANSICION-INVALIDA",
                    f"Estado actual '{estado}' no habilita el gate de implementación",
                    str(tasks_path),
                )
            )

    modo = control.get("modo", "completo")
    for artefacto in artefactos_requeridos(modo):
        aprobacion = _aprobacion_mas_reciente(control, artefacto)
        if aprobacion is None:
            findings.append(
                Finding("APROB-AUSENTE", f"No hay aprobación registrada para {artefacto}", artefacto)
            )
            continue
        ruta_artefacto = change_dir / artefacto
        if not ruta_artefacto.exists():
            findings.append(
                Finding("APROB-AUSENTE", f"El artefacto {artefacto} no existe en disco", artefacto)
            )
            continue
        hash_actual = hash_lf_v1(ruta_artefacto)
        if hash_actual != aprobacion.get("hash"):
            findings.append(
                Finding(
                    "APROB-HASH-DESINCRONIZADO",
                    f"El hash actual de {artefacto} no coincide con la aprobación registrada",
                    artefacto,
                )
            )
    return findings


def gate_cierre(control: dict, tasks_path: Path, sesion_activa: Optional[dict], repo_root: Path) -> list:
    findings = []
    change_dir = Path(tasks_path).parent
    modo = control.get("modo", "completo")

    if modo == "completo":
        verification_path = change_dir / "verification.md"
        if not verification_path.exists():
            findings.append(
                Finding("SDD-SIN-EVIDENCIA", "No existe verification.md", str(verification_path))
            )
        else:
            texto = verification_path.read_text(encoding="utf-8")
            if not _tiene_evidencia_real(texto):
                findings.append(
                    Finding(
                        "SDD-SIN-EVIDENCIA",
                        "verification.md existe pero no tiene contenido real en "
                        "'Evidencia obtenida' ni en 'Resultado final'",
                        str(verification_path),
                    )
                )
    else:
        texto_tasks = Path(tasks_path).read_text(encoding="utf-8")
        if not _tiene_seccion_verificacion_en_tasks(texto_tasks):
            findings.append(
                Finding(
                    "SDD-SIN-EVIDENCIA",
                    "tasks.md no tiene una sección '## Verificación' con contenido real",
                    str(tasks_path),
                )
            )

    rutas_autorizadas = control.get("alcance", {}).get("rutas_autorizadas", [])
    for ruta in repo_mod.files_out_of_scope(repo_root, rutas_autorizadas):
        findings.append(Finding("ALCANCE-RUTA", f"Archivo fuera de alcance: {ruta}", ruta))

    return findings


# --- transition ------------------------------------------------------------

def _agregar_transicion(control: dict, desde: str, hacia: str, reconciliado: bool = False) -> None:
    entrada = {"utc": ahora_utc(), "desde": desde, "hacia": hacia}
    if reconciliado:
        entrada["reconciliado"] = True
    control.setdefault("transiciones", []).append(entrada)


def _findings_del_gate(
    hacia: str,
    control: dict,
    tasks_path: Path,
    sesion_activa: Optional[dict],
    repo_root: Path,
) -> list:
    """Gate correspondiente al destino pedido, según la tabla de la spec 5.4.
    No decide si la transición en sí es válida (eso ya lo resolvió el
    llamador) — solo evalúa contenido/sesión para ese destino puntual."""
    findings = []
    if hacia == "aprobada_implementacion":
        findings += gate_implementacion(control, tasks_path, sesion_activa, exigir_estado_valido=False)
    elif hacia == "en_implementacion":
        if sesion_activa is None:
            findings.append(Finding("SESION-AUSENTE", "Se requiere sesión activa para pasar a en_implementacion"))
        # exigir_estado_valido=False: el chequeo de estado previo ya lo hizo
        # `es_transicion_valida()` antes de llegar acá; repetirlo con
        # exigir_estado_valido=True excluía predecesores legítimos como
        # `en_verificacion` o el resume desde `pausada_bloqueada` (bug corregido).
        findings += gate_implementacion(control, tasks_path, sesion_activa, exigir_estado_valido=False)
    elif hacia == "en_verificacion":
        if sesion_activa is None:
            findings.append(Finding("SESION-AUSENTE", "Se requiere sesión activa para pasar a en_verificacion"))
    elif hacia == "cerrada":
        if sesion_activa is None:
            findings.append(Finding("SESION-AUSENTE", "Se requiere sesión activa para pasar a cerrada"))
        findings += gate_cierre(control, tasks_path, sesion_activa, repo_root)
    elif hacia == "pausada_bloqueada":
        if not hallar_proximo_paso(tasks_path):
            findings.append(Finding("SDD-PROXIMO-PASO-VACIO", "La sección 'Próximo paso exacto' está vacía"))
    # aprobada_diseño / descartada: solo la validación de la tabla de
    # transiciones (5.2), ya aplicada por el llamador; sin gate de contenido
    # adicional ni sesión exigida.
    return findings


def transition(
    control: dict,
    tasks_path: Path,
    control_path: Path,
    repo_root: Path,
    hacia: str,
    sesion_activa: Optional[dict],
):
    """Implementa el orden de 3 pasos de la spec (5.4).

    Desviación deliberada respecto del listado literal de parámetros de la
    spec: en vez de recibir `desde_esperado` aparte, esta función lee el
    estado actual directamente de `tasks_path` (única fuente de verdad) y
    agrega `control_path`/`repo_root`, necesarios para persistir
    `control.json` y para el chequeo de alcance de `gate_cierre`. Documentado
    también en la respuesta final de la sesión.

    Devuelve `(ok: bool, findings: list[Finding])`. Si `ok` es False, no se
    escribió nada (ni `tasks.md` ni `control.json`). Caso especial de
    reconciliación/idempotencia (spec 5.8): si `tasks.md` ya está en el
    destino pedido, se corre igual el gate correspondiente por seguridad y,
    si pasa, se agrega (una sola vez) la entrada faltante a
    `control["transiciones"]` sin volver a tocar `tasks.md`; si ya estaba
    reconciliado, no se reescribe nada.
    """
    tasks_path = Path(tasks_path)

    if hacia not in ESTADOS_VALIDOS:
        return False, [Finding("SDD-TRANSICION-INVALIDA", f"Estado destino desconocido: {hacia}")]

    estado_actual, err = read_estado(tasks_path)
    if err:
        return False, err

    transiciones = control.get("transiciones", [])
    ultima_hacia = transiciones[-1].get("hacia") if transiciones else None

    if estado_actual == hacia:
        # Ya estamos en el destino pedido: ventana de reconciliación (spec
        # 5.8) o repetición idempotente de una transición ya aplicada.
        findings = _findings_del_gate(hacia, control, tasks_path, sesion_activa, repo_root)
        if findings:
            return False, findings
        if ultima_hacia == hacia:
            # Ya reconciliado: la última transición registrada ya termina en
            # el destino pedido, no hay nada que agregar ni escribir.
            return True, []
        desde_bridge = ultima_hacia if ultima_hacia is not None else estado_actual
        _agregar_transicion(control, desde_bridge, hacia, reconciliado=True)
        escribir_control(control_path, control)
        return True, []

    if not es_transicion_valida(control, estado_actual, hacia):
        return False, [
            Finding("SDD-TRANSICION-INVALIDA", f"Transición inválida: {estado_actual} -> {hacia}")
        ]

    findings = _findings_del_gate(hacia, control, tasks_path, sesion_activa, repo_root)
    if findings:
        return False, findings

    escrito = write_estado(tasks_path, hacia)
    if not escrito:
        return False, [Finding("SDD-ESTADO-ILEGIBLE", "No se pudo escribir 'estado:' (línea no única)")]

    _agregar_transicion(control, estado_actual, hacia)
    escribir_control(control_path, control)
    return True, []


# --- Sesiones ----------------------------------------------------------------

class SesionYaActivaError(Exception):
    pass


class SesionAusenteError(Exception):
    pass


def _sesion_activa(control: dict) -> Optional[dict]:
    for s in control.get("sesiones", []):
        if s.get("estado_final") == "activa":
            return s
    return None


def session_start(
    control: dict,
    modo: str = "estandar",
    minutos: int = 90,
    max_tareas: int = 3,
    max_roles: int = 2,
    max_reintentos: int = 2,
    max_rondas_revision: int = 2,
    max_continuaciones_por_subagente: int = 1,
) -> dict:
    activa = _sesion_activa(control)
    if activa is not None:
        raise SesionYaActivaError(f"Ya hay una sesión activa: {activa.get('id')}")
    sesiones = control.setdefault("sesiones", [])
    nuevo_id = f"s{len(sesiones) + 1}"
    inicio_utc = ahora_utc()
    # `deadline_utc` se calcula una única vez acá (inicio + presupuesto de
    # minutos), nunca recalculado en cada lectura, para que sea estable aunque
    # cambie el reloj del sistema entre chequeos (ver design.md §1).
    deadline_dt = parsear_utc(inicio_utc) + timedelta(minutes=minutos)
    entrada = {
        "id": nuevo_id,
        "inicio_utc": inicio_utc,
        "cierre_utc": None,
        "modo": modo,
        "presupuesto": {
            "minutos": minutos,
            "max_tareas": max_tareas,
            "max_roles": max_roles,
            "max_reintentos": max_reintentos,
            "max_rondas_revision": max_rondas_revision,
            "max_continuaciones_por_subagente": max_continuaciones_por_subagente,
        },
        "deadline_utc": deadline_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "minutos_consumidos": 0.0,
        "resultado": None,
        "subagentes": {},
        "tareas": [],
        "roles": [],
        "reintentos": 0,
        "rondas_revision": 0,
        "estado_final": "activa",
    }
    sesiones.append(entrada)
    return entrada


def session_note(control: dict, rol: Optional[str], tipo: str, tarea: Optional[str] = None) -> dict:
    if tipo not in ("planificada", "reintento", "ronda"):
        raise ValueError(f"tipo de nota inválido: {tipo!r}")
    activa = _sesion_activa(control)
    if activa is None:
        raise SesionAusenteError("No hay sesión activa: 'session note' requiere una sesión abierta")
    if tipo == "reintento":
        activa["reintentos"] = activa.get("reintentos", 0) + 1
    elif tipo == "ronda":
        activa["rondas_revision"] = activa.get("rondas_revision", 0) + 1
    # "planificada" no incrementa ningún contador de límite (no hay eventos[]).
    if tarea:
        tareas = activa.get("tareas")
        if not isinstance(tareas, list):
            # Formato viejo (entero) o ausente — nunca debería darse en una
            # sesión recién abierta con `session_start`, pero por robustez no
            # se pisa un contador entero real: se re-arranca como lista vacía
            # solo si no era ya una lista.
            tareas = []
        if tarea not in tareas:
            tareas.append(tarea)
        activa["tareas"] = tareas
    if rol:
        roles = activa.setdefault("roles", [])
        if rol not in roles:
            roles.append(rol)
    return activa


def _cantidad(valor) -> float:
    """Cantidad numérica a partir de un campo que puede venir como lista
    (formato vigente, p. ej. `tareas: [...]`) o como entero (formato viejo,
    p. ej. una sesión cerrada anterior a este fix). Nunca explota con
    `TypeError` sobre ninguno de los dos formatos."""
    if isinstance(valor, list):
        return len(valor)
    if valor is None:
        return 0
    return valor


def chequear_limites(sesion: dict) -> list:
    findings = []
    presupuesto = sesion.get("presupuesto", {})

    cantidad_tareas = _cantidad(sesion.get("tareas"))
    if cantidad_tareas > presupuesto.get("max_tareas", float("inf")):
        findings.append(
            Finding(
                "SESION-LIMITE-TAREAS",
                f"Tareas ({cantidad_tareas}) supera el máximo de la sesión ({presupuesto.get('max_tareas')})",
            )
        )
    if len(sesion.get("roles", [])) > presupuesto.get("max_roles", float("inf")):
        findings.append(
            Finding(
                "SESION-LIMITE-ROLES",
                f"Roles ({len(sesion.get('roles', []))}) supera el máximo de la sesión ({presupuesto.get('max_roles')})",
            )
        )
    if sesion.get("reintentos", 0) > presupuesto.get("max_reintentos", float("inf")):
        findings.append(
            Finding(
                "SESION-LIMITE-REINTENTOS",
                f"Reintentos ({sesion.get('reintentos')}) supera el máximo de la sesión ({presupuesto.get('max_reintentos')})",
            )
        )
    if sesion.get("rondas_revision", 0) > presupuesto.get("max_rondas_revision", float("inf")):
        findings.append(
            Finding(
                "SESION-LIMITE-RONDAS",
                f"Rondas de revisión ({sesion.get('rondas_revision')}) supera el máximo de la sesión ({presupuesto.get('max_rondas_revision')})",
            )
        )

    restantes = minutos_restantes(sesion)
    if restantes < 0:
        minutos_transcurridos = presupuesto.get("minutos", 0) - restantes
        findings.append(
            Finding(
                "SESION-LIMITE-TIEMPO",
                f"Tiempo transcurrido ({minutos_transcurridos:.1f} min) supera el presupuesto ({presupuesto.get('minutos')} min)",
            )
        )
    return findings


def session_status(control: dict) -> dict:
    activa = _sesion_activa(control)
    if activa is None:
        return {"activa": False}
    from datetime import datetime, timezone

    inicio = parsear_utc(activa["inicio_utc"])
    minutos_transcurridos = (datetime.now(timezone.utc) - inicio).total_seconds() / 60.0
    findings = chequear_limites(activa)
    return {
        "activa": True,
        "id": activa.get("id"),
        "minutos_transcurridos": minutos_transcurridos,
        "presupuesto": activa.get("presupuesto"),
        "tareas": activa.get("tareas"),
        "roles": activa.get("roles"),
        "reintentos": activa.get("reintentos"),
        "rondas_revision": activa.get("rondas_revision"),
        "findings": [f.to_dict() for f in findings],
    }


def session_close(control: dict, estado_final: str) -> dict:
    """Cierra la sesión activa. `minutos_consumidos` y `resultado` se derivan
    siempre a partir del momento real de cierre (nunca de un flag ni de una
    estimación previa) — no existe ningún parámetro para declararlos a mano
    (ver design.md §4)."""
    if estado_final not in ("completada", "pausada"):
        raise ValueError(f"estado_final inválido: {estado_final!r}")
    activa = _sesion_activa(control)
    if activa is None:
        raise SesionAusenteError("No hay sesión activa para cerrar")
    momento_cierre_utc = ahora_utc()
    activa["cierre_utc"] = momento_cierre_utc
    activa["estado_final"] = estado_final

    inicio = parsear_utc(activa["inicio_utc"])
    momento_cierre = parsear_utc(momento_cierre_utc)
    activa["minutos_consumidos"] = (momento_cierre - inicio).total_seconds() / 60.0

    restantes = minutos_restantes(activa)
    activa["resultado"] = "dentro_de_presupuesto" if restantes >= 0 else "excedida"
    return activa
