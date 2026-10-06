"""Vocabulario y mecánica SDD: estados, transiciones, gates, aprobaciones y
sesiones. No ejecuta `git` directamente (usa `repo.py` para eso) y no conoce
JSON de bajo nivel (usa `core.py` para eso).
"""
from __future__ import annotations

import fnmatch
import re
from datetime import timedelta
from pathlib import Path
from typing import Optional

from . import pep440_subset
from . import repo as repo_mod
from . import scope
from .core import Finding, ahora_utc, escribir_control, hash_lf_v1, leer_control, minutos_restantes, parsear_utc

# `tools/` ya está en `sys.path` en todo contexto real donde `dsguard.sdd` se
# importa (CLI: `ds_guard.py:23`; tests: `sys.path.insert(0, tools/)` antes de
# `from dsguard import sdd`) -- mismo patrón que `tools/leadrun/runtime.py`
# usa para `from dsguard import checks as dsguard_checks`, aplicado acá para
# el paquete hermano `autonomy` (v0.8 Change 3, `20260930-autonomous-sdd-and-
# remediation`). Sin tocar `tools/autonomy/core.py` (Change 0, cerrado): solo
# se consumen sus constantes/funciones ya existentes.
from autonomy import core as autonomy_core

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


# --- Primitiva de resolución de aprobación registrada (R1 de 20261006-sdd-parsers-
# and-guardrail-ownership) ------------------------------------------------------

_RE_CHANGE_ID_APROBACION = re.compile(r"[0-9]{8}-[a-z0-9][a-z0-9-]*")
_RE_SHA256_HEX = re.compile(r"[0-9a-f]{64}")
_ALGORITMO_APROBACION = "sha256/lf/v1"
RESERVADOS_WINDOWS = frozenset(
    ["con", "prn", "aux", "nul"] + [f"com{i}" for i in range(1, 10)] + [f"lpt{i}" for i in range(1, 10)]
)


def artefacto_con_forma_valida(artefacto) -> bool:
    """Nombre simple de archivo: sin separadores, `..`, `:`, punto/espacio
    final ni nombre reservado de Windows."""
    if not isinstance(artefacto, str) or not artefacto.strip():
        return False
    if artefacto != artefacto.strip() or artefacto == "." or "/" in artefacto or "\\" in artefacto:
        return False
    if ".." in artefacto or ":" in artefacto or artefacto != artefacto.rstrip(" ."):
        return False
    return artefacto.split(".")[0].strip().lower() not in RESERVADOS_WINDOWS


def artefacto_no_portable(artefacto) -> bool:
    """`True` si `artefacto` lleva `:` (unidad/ADS de Windows), punto/espacio
    final o es un nombre reservado de Windows (con o sin extensión)."""
    if not isinstance(artefacto, str):
        return True
    return (
        ":" in artefacto
        or artefacto != artefacto.rstrip(" .")
        or artefacto.split(".")[0].strip().lower() in RESERVADOS_WINDOWS
    )


def resolver_aprobacion_registrada(repo_root, change_id, artefacto, hash_esperado=None) -> dict:
    """Primitiva única de resolución (R1): `{estado, detalle, entrada,
    hash_vigente}` con `estado` en `verified | stale | missing | unresolvable`.

    Pasos: (1) forma de `change_id`/`artefacto`; (2) Change en
    `openspec/changes/<id>` u `openspec/archive/<id>`; (3) `control.json`
    legible con lista `aprobaciones`; (4) existe una entrada del artefacto
    (con `hash_esperado`, si se dio); (5) esa entrada es la MÁS RECIENTE del
    artefacto, si no `stale`; (6) el archivo en disco (dentro del Change)
    conserva el hash (`hash_lf_v1`), si no `stale`. Sin `hash_esperado`
    resuelve contra la última entrada y, si `verified`, devuelve su hash en
    `hash_vigente`. Solo lectura; nunca lanza (fail-closed `unresolvable`)."""
    try:
        return _resolver_aprobacion_registrada(repo_root, change_id, artefacto, hash_esperado)
    except Exception as exc:  # fail-closed
        return _resultado_aprobacion("unresolvable", f"resolución falló ({type(exc).__name__})")


def _resultado_aprobacion(estado: str, detalle: str, entrada=None, hash_vigente=None) -> dict:
    return {"estado": estado, "detalle": detalle, "entrada": entrada, "hash_vigente": hash_vigente}


def _resolver_aprobacion_registrada(repo_root, change_id, artefacto, hash_esperado) -> dict:
    # 1. Forma.
    if not isinstance(change_id, str) or not _RE_CHANGE_ID_APROBACION.fullmatch(change_id):
        return _resultado_aprobacion("unresolvable", "change_id con forma inválida")
    if not artefacto_con_forma_valida(artefacto):
        return _resultado_aprobacion("unresolvable", "artefacto con forma inválida o no portable")
    if hash_esperado is not None and not (
        isinstance(hash_esperado, str) and _RE_SHA256_HEX.fullmatch(hash_esperado)
    ):
        return _resultado_aprobacion("unresolvable", "hash_esperado con forma inválida")
    if hash_esperado == _HASH_CERO:
        return _resultado_aprobacion("missing", "hash de 64 ceros (placeholder): nunca es una aprobación")
    # 2. Change.
    raiz = Path(repo_root)
    carpeta = None
    for padre in ("changes", "archive"):
        candidata = raiz / "openspec" / padre / change_id
        if candidata.is_dir():
            carpeta = candidata
            break
    if carpeta is None:
        return _resultado_aprobacion("unresolvable", "Change inexistente (ni changes/ ni archive/)")
    # 3. control.json.
    try:
        control = leer_control(carpeta / "control.json")
    except Exception as exc:
        return _resultado_aprobacion("unresolvable", f"control.json ilegible ({type(exc).__name__})")
    aprobaciones = control.get("aprobaciones", []) if isinstance(control, dict) else None
    if not isinstance(aprobaciones, list):
        return _resultado_aprobacion("unresolvable", "control.json sin lista de aprobaciones válida")
    propias = [a for a in aprobaciones if isinstance(a, dict) and a.get("artefacto") == artefacto]
    # 4. Entrada del artefacto (con el hash esperado, si se dio).
    if hash_esperado is not None:
        coincidentes = [a for a in propias if a.get("hash") == hash_esperado]
        if not coincidentes:
            return _resultado_aprobacion("missing", "no hay aprobación registrada para ese artefacto y hash")
    elif not propias:
        return _resultado_aprobacion("missing", "no hay aprobación registrada para ese artefacto")
    # 5. La más reciente del artefacto.
    reciente = _aprobacion_mas_reciente({"aprobaciones": propias}, artefacto)
    hash_reciente = reciente.get("hash") if reciente else None
    if (
        not (isinstance(hash_reciente, str) and _RE_SHA256_HEX.fullmatch(hash_reciente))
        or hash_reciente == _HASH_CERO
    ):
        return _resultado_aprobacion("unresolvable", "la aprobación más reciente no tiene un hash válido", reciente)
    if hash_esperado is not None and hash_reciente != hash_esperado:
        return _resultado_aprobacion(
            "stale", "la aprobación fue reemplazada por una más reciente del artefacto", reciente
        )
    if reciente.get("algoritmo", _ALGORITMO_APROBACION) != _ALGORITMO_APROBACION:
        return _resultado_aprobacion("unresolvable", "algoritmo de hash de la aprobación no soportado", reciente)
    # 6. Archivo en disco, dentro del Change.
    archivo = carpeta / artefacto
    try:
        archivo.resolve().relative_to(carpeta.resolve())
    except (ValueError, OSError):
        return _resultado_aprobacion("unresolvable", "el artefacto sale del directorio del Change", reciente)
    if not archivo.is_file():
        return _resultado_aprobacion("missing", "el artefacto aprobado no existe en el Change", reciente)
    try:
        actual = hash_lf_v1(archivo)
    except Exception as exc:
        return _resultado_aprobacion(
            "unresolvable", f"no se pudo hashear el artefacto ({type(exc).__name__})", reciente
        )
    if actual != hash_reciente:
        return _resultado_aprobacion("stale", "el artefacto cambió en disco desde su aprobación", reciente)
    return _resultado_aprobacion("verified", "aprobación vigente y artefacto sin cambios", reciente, hash_reciente)


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

    findings += scope.evaluar_alcance(repo_root, control)

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


# --- Bounded remediation (control["remediaciones"]) ---------------------------

REMEDIATION_TIPOS = frozenset({"retry_tecnico", "bug", "metodologica"})


def _hallar_remediacion(control: dict, finding_id: Optional[str]) -> Optional[dict]:
    """Busca en `control.get("remediaciones", [])` una entrada cuyo
    `finding_id == finding_id`. Si `finding_id` es `None`, siempre devuelve
    `None` -- cada nota sin `finding_id` crea una remediación nueva (caso
    típico de `retry_tecnico` puntual, sin finding asociado)."""
    if finding_id is None:
        return None
    for remediacion in control.get("remediaciones", []):
        if remediacion.get("finding_id") == finding_id:
            return remediacion
    return None


def remediation_note(
    control: dict,
    remediation_tipo: str,
    causa: Optional[str],
    cambio_aplicado: Optional[str],
    resultado: Optional[str],
    session_id: str,
    finding_id: Optional[str] = None,
    origen: Optional[str] = None,
    max_intentos_default: int = 2,
) -> tuple:
    """(ok, findings, remediation_id). Ver spec R11-R15. Crea la remediación
    si no existe (ventana 1 automática, sin autorización humana). Si la
    ventana vigente está agotada, o la remediación ya está resuelta, o el
    tipo pedido es inconsistente con el ya fijado: no escribe nada (ni el
    intento ni bookkeeping de sesión -- eso es responsabilidad del
    llamador, `session_note`, que no debe incrementar `reintentos` si acá
    `ok` es `False`)."""
    if remediation_tipo not in REMEDIATION_TIPOS:
        return False, [
            Finding("REMEDIACION-TIPO-INVALIDO", f"Tipo de remediación inválido: {remediation_tipo}")
        ], None

    if remediation_tipo in ("bug", "metodologica") and not finding_id:
        return False, [
            Finding(
                "REMEDIACION-FINDING-REQUERIDO",
                f"'{remediation_tipo}' requiere --finding-id no vacío",
            )
        ], None

    remediacion = _hallar_remediacion(control, finding_id)

    if remediacion is not None:
        if remediacion.get("estado") == "resuelta":
            return False, [
                Finding(
                    "REMEDIACION-RESUELTA",
                    f"La remediación {remediacion.get('remediation_id')} ya está resuelta: no admite intentos nuevos",
                )
            ], None
        tipo_existente = remediacion.get("tipo")
        if tipo_existente is not None and tipo_existente != remediation_tipo:
            return False, [
                Finding(
                    "REMEDIACION-TIPO-INCONSISTENTE",
                    f"La remediación {remediacion.get('remediation_id')} ya está tipada como "
                    f"{tipo_existente}, no se puede registrar un intento como {remediation_tipo}",
                )
            ], None
    else:
        remediaciones = control.setdefault("remediaciones", [])
        remediation_id = f"r{len(remediaciones) + 1}"
        remediacion = {
            "remediation_id": remediation_id,
            "finding_id": finding_id,
            "origen": origen,
            "tipo": remediation_tipo,
            "estado": "abierta",
            "creado_utc": ahora_utc(),
            "ventanas": [
                {
                    "ventana": 1,
                    "max_intentos": max_intentos_default,
                    "autorizado_por": None,
                    "fecha_autorizacion": None,
                    "motivo": None,
                    "intentos": [],
                }
            ],
            "resuelto_utc": None,
            "resultado_final": None,
        }
        remediaciones.append(remediacion)

    ventana_vigente = remediacion["ventanas"][-1]
    if len(ventana_vigente["intentos"]) >= ventana_vigente["max_intentos"]:
        return False, [
            Finding(
                "REMEDIACION-LIMITE",
                f"Se agotaron los {ventana_vigente['max_intentos']} intentos de la ventana "
                f"{ventana_vigente['ventana']} para {finding_id or remediacion['remediation_id']}; "
                "usar 'ds_guard remediation extend' o 'resolve'",
            )
        ], None

    intento = {
        "attempt": len(ventana_vigente["intentos"]) + 1,
        "causa": causa,
        "cambio_aplicado": cambio_aplicado,
        "resultado": resultado,
        "session_id": session_id,
        "utc": ahora_utc(),
    }
    ventana_vigente["intentos"].append(intento)
    return True, [], remediacion["remediation_id"]


def remediation_resolve(control: dict, remediation_id: str, resultado: Optional[str]) -> tuple:
    for remediacion in control.get("remediaciones", []):
        if remediacion.get("remediation_id") == remediation_id:
            if remediacion.get("estado") == "resuelta":
                return False, [
                    Finding(
                        "REMEDIACION-YA-RESUELTA",
                        f"La remediación {remediation_id} ya estaba resuelta",
                    )
                ]
            remediacion["estado"] = "resuelta"
            remediacion["resuelto_utc"] = ahora_utc()
            remediacion["resultado_final"] = resultado
            return True, []
    return False, [Finding("REMEDIACION-INEXISTENTE", f"No existe la remediación: {remediation_id}")]


def remediation_extend(
    control: dict,
    remediation_id: str,
    usuario: str,
    fecha: str,
    motivo: str,
    max_intentos: int = 2,
) -> tuple:
    for remediacion in control.get("remediaciones", []):
        if remediacion.get("remediation_id") == remediation_id:
            if remediacion.get("estado") == "resuelta":
                return False, [
                    Finding(
                        "REMEDIACION-RESUELTA",
                        f"La remediación {remediation_id} ya está resuelta: reabrir requiere una remediación nueva, no extender la cerrada",
                    )
                ], None
            if not usuario or not fecha or not motivo:
                return False, [
                    Finding(
                        "REMEDIACION-CAMPO-VACIO",
                        "usuario/fecha/motivo son obligatorios para 'remediation extend'",
                    )
                ], None
            ventanas = remediacion["ventanas"]
            nueva_ventana_num = len(ventanas) + 1
            ventanas.append(
                {
                    "ventana": nueva_ventana_num,
                    "max_intentos": max_intentos,
                    "autorizado_por": usuario,
                    "fecha_autorizacion": fecha,
                    "motivo": motivo,
                    "intentos": [],
                }
            )
            return True, [], nueva_ventana_num
    return False, [Finding("REMEDIACION-INEXISTENTE", f"No existe la remediación: {remediation_id}")], None


# --- Sesiones ----------------------------------------------------------------

class SesionYaActivaError(Exception):
    pass


class SesionAusenteError(Exception):
    pass


class RemediacionLimiteError(Exception):
    """Un intento de remediación (`session note --tipo reintento
    --remediation-tipo ...`) se rehusó -- ver `remediation_note`. Lleva los
    `Finding` para que el llamador (`cmd_session_note`) los traduzca a exit 2,
    mismo patrón que `SesionAusenteError`."""

    def __init__(self, findings: list):
        self.findings = findings
        super().__init__("; ".join(f.mensaje for f in findings))


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
        # v0.8 Change 3 (R13-R14 de spec.md, D6 de design.md): contador
        # autorreportado por el Lead, sin enforcement técnico real -- un Lead
        # que omite el autorreporte no es detectado por este mecanismo. Ver
        # `session_note(tipo="subagente", ...)` y `limite_subagentes_alcanzado`.
        "subagentes": {"conteo": 0},
        "tareas": [],
        "roles": [],
        "reintentos": 0,
        "rondas_revision": 0,
        "estado_final": "activa",
    }
    sesiones.append(entrada)
    return entrada


def session_note(
    control: dict,
    rol: Optional[str],
    tipo: str,
    tarea: Optional[str] = None,
    finding_id: Optional[str] = None,
    remediation_tipo: Optional[str] = None,
    causa: Optional[str] = None,
    cambio_aplicado: Optional[str] = None,
    resultado: Optional[str] = None,
    max_intentos_remediacion: int = 2,
    evento: Optional[str] = None,
) -> dict:
    """Ver también `tipo == "subagente"` (v0.8 Change 3, R13-R14 de `spec.md`,
    D6 de `design.md`): autorreportado por el Lead, sin enforcement técnico
    real -- un Lead que omite el autorreporte no es detectado por este
    mecanismo. `evento` (`"abrir"|"cerrar"`) solo aplica cuando
    `tipo == "subagente"`; se agrega al final de la firma, con default `None`,
    para no romper ningún llamador existente que no lo pase."""
    if tipo not in ("planificada", "reintento", "ronda", "subagente"):
        raise ValueError(f"tipo de nota inválido: {tipo!r}")
    activa = _sesion_activa(control)
    if activa is None:
        raise SesionAusenteError("No hay sesión activa: 'session note' requiere una sesión abierta")
    if tipo == "subagente":
        if evento not in ("abrir", "cerrar"):
            raise ValueError(f"evento de nota de subagente inválido: {evento!r}")
        subagentes = activa.get("subagentes")
        if not isinstance(subagentes, dict):
            # Formato viejo (`{}` sin usar, o ausente) -- se re-arranca en la
            # forma nueva sin pisar un valor real si ya lo hubiera.
            subagentes = {"conteo": 0}
        conteo = subagentes.get("conteo", 0)
        if evento == "abrir":
            subagentes["conteo"] = conteo + 1
        else:
            if conteo <= 0:
                raise ValueError(
                    "No hay subagentes abiertos registrados: 'cerrar' sin una "
                    "apertura previa no se admite (no baja de 0)"
                )
            subagentes["conteo"] = conteo - 1
        activa["subagentes"] = subagentes
    elif tipo == "reintento":
        if remediation_tipo is not None:
            # Bounded remediation (R11-R18): si `remediation_note` rehúsa
            # (ventana agotada, tipo inválido, etc.), no se toca nada -- ni la
            # remediación ni el agregado `reintentos` de la sesión. Regresión
            # cero para quien no use estos flags: ver rama `else` de abajo.
            ok, findings_remediacion, _remediation_id = remediation_note(
                control,
                remediation_tipo,
                causa,
                cambio_aplicado,
                resultado,
                session_id=activa["id"],
                finding_id=finding_id,
                origen=rol,
                max_intentos_default=max_intentos_remediacion,
            )
            if not ok:
                raise RemediacionLimiteError(findings_remediacion)
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
        "subagentes": (activa.get("subagentes") or {}).get("conteo", 0),
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


# --- Autonomía v0.8 Change 3 (`20260930-autonomous-sdd-and-remediation`) ------
#
# `approval_mode` (control["aprobacion_modo"]), checkpoints de negocio
# (control["decisiones_preaprobadas"]) y presupuesto agregado entre sesiones.
# Compone `tools.autonomy.core` (Change 0, cerrado) sin tocarlo: solo se leen
# sus constantes/funciones de validación ya existentes (`validate_pre_approved`,
# `CODE_PREAPPROVED_INVALID`, `CODE_LIMIT_AGGREGATE_BUDGET`). Ver D1-D2/D4 de
# `openspec/changes/20260930-autonomous-sdd-and-remediation/design.md`.

APPROVAL_MODES = ("per_change", "checkpoints")
APPROVAL_MODE_DEFAULT = "per_change"


def resolver_approval_mode(control: dict) -> str:
    """`control["aprobacion_modo"]` -> `"per_change"` | `"checkpoints"` (R1 de
    `spec.md`). Ausente, `None` o cualquier valor que no sea exactamente
    `"checkpoints"` resuelve `"per_change"` -- el default de hoy, sin excepción
    ni error: esta función solo *lee*, nunca valida/rechaza un valor mal
    formado (eso, si hace falta, es responsabilidad de un gate aparte, fuera
    de esta invocación)."""
    valor = control.get("aprobacion_modo")
    if valor == "checkpoints":
        return "checkpoints"
    return APPROVAL_MODE_DEFAULT


_RE_CHECKPOINT_BULLET = re.compile(
    r"^-\s+\*\*(?P<id>[^*]+)\*\*:\s*(?P<resumen>.+?)\s*—\s*alcance:\s*(?P<alcance>.+?)"
    r"\s*—\s*aprobacion:\s*(?P<change_id>[0-9]{8}-[a-z0-9][a-z0-9-]*)/proposal\.md@"
    r"(?P<hash>[0-9a-f]{64}|approved)\s*$"
)

_HASH_CERO = "0" * 64


def checkpoints_con_placeholder_cero(texto: str) -> list:
    """Ids de los bullets de `## Checkpoints de negocio` cuyo hash son 64
    ceros (legacy, R10): se aceptan sintácticamente pero NUNCA cuentan como
    aprobados. Lista vacía si no hay sección o ninguno."""
    seccion = _contenido_de_seccion(texto, "## Checkpoints de negocio")
    ids: list = []
    for linea in (seccion or "").splitlines():
        m = _RE_CHECKPOINT_BULLET.match(linea.strip())
        if m and m.group("hash") == _HASH_CERO:
            ids.append(m.group("id").strip())
    return ids


def verificar_checkpoints(repo_root, control: dict) -> list:
    """Verificación posterior (R8): resuelve cada
    `control["decisiones_preaprobadas"][*].approval_ref` con
    `resolver_aprobacion_registrada` -> `[{summary, estado, detalle}]`, con
    `estado` en `verified | stale | missing | placeholder | unresolvable`.
    Hash de 64 ceros => `placeholder` (nunca `verified`). Solo lectura; nunca
    lanza."""
    resultado: list = []
    decisiones = control.get("decisiones_preaprobadas", []) if isinstance(control, dict) else []
    if not isinstance(decisiones, list):
        return resultado
    for decision in decisiones:
        decision = decision if isinstance(decision, dict) else {}
        resumen = decision.get("summary")
        ref = decision.get("approval_ref")
        if not isinstance(ref, dict):
            estado, detalle = "unresolvable", "approval_ref ausente o con forma inválida"
        elif ref.get("hash") == _HASH_CERO:
            estado, detalle = "placeholder", "hash de 64 ceros (legacy): nunca cuenta como aprobado"
        else:
            r = resolver_aprobacion_registrada(
                repo_root, ref.get("change_id"), ref.get("artefacto"), ref.get("hash")
            )
            if ref.get("hash") is None:  # sin hash no hay checkpoint concreto
                r = _resultado_aprobacion("unresolvable", "approval_ref sin hash")
            estado, detalle = r["estado"], r["detalle"]
        resultado.append({"summary": resumen, "estado": estado, "detalle": detalle})
    return resultado


def parsear_checkpoints_de_propuesta(texto: str, change_id=None, resolver_approved=None) -> tuple:
    """Checkpoints de negocio (`## Checkpoints de negocio` de `proposal.md`,
    condicional a `approval_mode: checkpoints`, R3-R4 de `spec.md`; D2 de
    `design.md`) -> `(checkpoints_validos, hallazgos)`.

    `checkpoints_validos` es una `list[dict]`, cada elemento con la forma
    EXACTA de `PreApprovedDecision.to_dict()` (`approval_ref`, `decision_type`,
    `scope`, `summary`) y `decision_type == "business_checkpoint"`, ya
    validado sin hallazgos por `tools.autonomy.core.validate_pre_approved`
    (sin tocar esa función). `hallazgos` es `list[Finding]` (este módulo, no
    `PolicyFinding`) -- uno por cada bullet que no parseó o que parseó pero no
    validó; nunca se agrega el checkpoint correspondiente a
    `checkpoints_validos` en esos casos (sin checkpoint fantasma, ver riesgo
    de `design.md`).

    `@approved` (R5-R7 de `20261006-sdd-parsers-and-guardrail-ownership`):
    en vez de `@<64 hex>` el bullet puede terminar en `@approved`; entonces se
    invoca `resolver_approved(change_id_referenciado) -> (hash | None,
    detalle)` y el checkpoint se materializa SIEMPRE con el hash concreto
    devuelto. Sin `resolver_approved`, o con hash `None`/inválido/cero, el
    bullet da un hallazgo `CODE_PREAPPROVED_INVALID` (nunca un checkpoint sin
    hash real). `change_id` (Change que se aprueba) es informativo: la
    decisión de qué hash corresponde a cada referencia es del resolver. Los
    64 ceros legacy se aceptan sintácticamente (ver
    `checkpoints_con_placeholder_cero`).

    Se devuelve una tupla en vez de solo la lista (decisión de implementación
    de esta invocación, T1): un checkpoint mal formado no debe desaparecer en
    silencio -- el llamador (CLI, fuera de esta invocación) decide qué hacer
    con `hallazgos` (típicamente: rechazar la aprobación de la propuesta).

    Formato de bullet (uno por línea, ajustado durante esta invocación --
    el ejemplo ilustrativo de D2 de `design.md` (`... — tipo:
    business_checkpoint`) no incluye `change_id`, pero `ApprovalRef`/
    `_validar_ref` de `tools.autonomy.core` lo exige como uno de los 3
    campos obligatorios (`artefacto`, `change_id`, `hash`) -- con el
    formato literal de D2, ningún checkpoint podría pasar nunca
    `validate_pre_approved` sin hallazgos. Corregido acá agregando
    `change_id` explícito al bullet; detalle completo en `tasks.md` §T1 de
    este Change, sin reabrir el hash aprobado de `design.md`):

        - **<id>**: <resumen> — alcance: <ruta1>, <ruta2> — aprobacion:
          <change_id>/proposal.md@<hash-sha256>

    Ejemplo real (hash de relleno de 64 hex, no uno real de este repo):

        - **budget-sprint3**: Aprobar el tope de presupuesto agregado del
          sprint 3 — alcance: tools/dsguard/sdd.py, tools/tests/test_lifecycle.py
          — aprobacion: 20260930-autonomous-sdd-and-remediation/proposal.md@
          0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcd

    `id` no es una clave aparte de `PreApprovedDecision` (no existe en
    `to_dict()`): se embebe como prefijo de `summary` (`"<id>: <resumen>"`),
    sin inventar un campo nuevo fuera del vocabulario ya validado por
    `validate_pre_approved`. `artefacto` es siempre el literal `"proposal.md"`
    (nunca se lee del bullet: `validate_pre_approved`/`_scope_item_detail` ya
    lo exige así, R3 de `spec.md`).
    """
    seccion = _contenido_de_seccion(texto, "## Checkpoints de negocio")
    checkpoints_validos: list = []
    hallazgos: list = []
    if not seccion:
        return checkpoints_validos, hallazgos

    ubicacion = "proposal.md#Checkpoints de negocio"
    for linea in seccion.splitlines():
        linea = linea.strip()
        if not linea or not linea.startswith("-"):
            continue
        m = _RE_CHECKPOINT_BULLET.match(linea)
        if not m:
            hallazgos.append(
                Finding(
                    autonomy_core.CODE_PREAPPROVED_INVALID,
                    f"Bullet de checkpoint con formato ambiguo/incompleto: {linea!r}",
                    ubicacion,
                )
            )
            continue

        hash_bullet = m.group("hash")
        if hash_bullet == "approved":
            # `@approved` (R5-R7): se resuelve contra la aprobación REAL
            # registrada; nunca se materializa sin un hash concreto.
            hash_bullet, motivo = None, "sin resolver_approved"
            if resolver_approved is not None:
                try:
                    candidato_hash, motivo = resolver_approved(m.group("change_id"))
                except Exception as exc:  # fail-closed
                    candidato_hash, motivo = None, f"resolver_approved falló ({type(exc).__name__})"
                if (
                    isinstance(candidato_hash, str)
                    and _RE_SHA256_HEX.fullmatch(candidato_hash)
                    and candidato_hash != _HASH_CERO
                ):
                    hash_bullet = candidato_hash
            if hash_bullet is None:
                hallazgos.append(
                    Finding(
                        autonomy_core.CODE_PREAPPROVED_INVALID,
                        f"Checkpoint '@approved' no resoluble ({motivo}): {linea!r}",
                        ubicacion,
                    )
                )
                continue

        alcance = [item.strip() for item in m.group("alcance").split(",") if item.strip()]
        candidato = {
            "approval_ref": {
                "artefacto": "proposal.md",
                "change_id": m.group("change_id"),
                "hash": hash_bullet,
            },
            "decision_type": "business_checkpoint",
            "scope": alcance,
            "summary": f"{m.group('id').strip()}: {m.group('resumen').strip()}",
        }
        hallazgos_validacion = autonomy_core.validate_pre_approved(
            candidato, known_types=("business_checkpoint",)
        )
        if hallazgos_validacion:
            for h in hallazgos_validacion:
                hallazgos.append(
                    Finding(
                        h.code,
                        f"Checkpoint inválido en '{h.path}': {h.detail_key}",
                        ubicacion,
                    )
                )
            continue

        checkpoints_validos.append(candidato)

    return checkpoints_validos, hallazgos


CODE_ALCANCE_INVALIDO = "SDD-ALCANCE-INVALIDO"
_ALCANCE_MAX_ENTRADAS = 500
_ALCANCE_MAX_LARGO = 260
_RE_ALCANCE_PROHIBIDOS = re.compile(r"""[\s$;&|<>()"'`?\[\]{}!]""")
_RE_ALCANCE_UNIDAD_WINDOWS = re.compile(r"^[A-Za-z]:")
# Rutas del propio harness/datos que una propuesta nunca puede autorizar (I7/I8); también se
# rechazan patrones que las cubran (p. ej. `.claude/**`, `data/**`).
_ALCANCE_RUTAS_PROTEGIDAS = (
    ".claude/guardrails.json",
    ".claude/settings.json",
    ".claude/settings.local.json",
    "data/raw/x",
)


def _normalizar_entrada_alcance(crudo: str) -> tuple:
    """Normaliza UNA entrada de `## Alcance autorizado` -> `(ruta, motivo)`.
    `motivo` es None si es válida (R23 de 20261005-operational-autonomy-hardening)."""
    valor = crudo.strip()
    if len(valor) >= 2 and valor.startswith("`") and valor.endswith("`"):
        valor = valor[1:-1].strip()
    if not valor:
        return None, "entrada vacía"
    if len(valor) > _ALCANCE_MAX_LARGO:
        return None, f"más de {_ALCANCE_MAX_LARGO} caracteres"
    if "\\" in valor:
        return None, "backslash no permitido (usar '/')"
    if valor.startswith("/") or valor.startswith("~") or _RE_ALCANCE_UNIDAD_WINDOWS.match(valor):
        return None, "ruta absoluta o con '~' no permitida"
    if _RE_ALCANCE_PROHIBIDOS.search(valor):
        return None, "espacios o caracteres de shell/glob no permitidos"
    while valor.startswith("./"):
        valor = valor[2:]
    while "//" in valor:
        valor = valor.replace("//", "/")
    if valor.endswith("/"):
        valor = valor + "**"
    if not valor or valor == ".":
        return None, "entrada vacía"
    if valor.startswith("/"):
        return None, "ruta absoluta no permitida"
    if ":" in valor:
        return None, "':' no permitido"
    segmentos = valor.split("/")
    if ".." in segmentos or "." in segmentos:
        return None, "segmento '.' o '..' no permitido"
    primero = segmentos[0].rstrip(". ").lower()
    if primero in (".git", ".harmessi"):
        return None, f"{primero} no permitido"
    if any(seg.endswith(".") or seg.endswith(" ") for seg in segmentos):
        return None, "segmento que termina en '.' o espacio no permitido"
    minuscula = valor.lower()
    if minuscula == "data/raw" or minuscula.startswith("data/raw/"):
        return None, "data/raw no permitido"
    for protegida in _ALCANCE_RUTAS_PROTEGIDAS:
        if fnmatch.fnmatchcase(protegida, minuscula):
            return None, f"la ruta protegida {protegida} no puede autorizarse"
    if "*" in segmentos[0]:
        return None, "el primer segmento no puede contener '*' (alcance repo-wide)"
    for i, seg in enumerate(segmentos):
        if "**" in seg and not (seg == "**" and i == len(segmentos) - 1):
            return None, "'**' solo permitido como último segmento completo"
    return valor, None


def parsear_alcance_autorizado(texto: str) -> tuple:
    """Sección `## Alcance autorizado` de `proposal.md` -> `(rutas, hallazgos)`.
    Función pura (R22-R26). Solo se consideran líneas bullet (`- ...`); el resto
    (comentarios de plantilla, prosa) se ignora. Todo-o-nada: cualquier entrada
    inválida produce un `Finding` `SDD-ALCANCE-INVALIDO`; el llamador debe
    rechazar la aprobación completa. `rutas` son únicas y en orden de aparición.
    Título exacto: `## Alcance` (otra sección) no se confunde con esta."""
    seccion = _contenido_de_seccion(texto, "## Alcance autorizado")
    rutas: list = []
    hallazgos: list = []
    if not seccion:
        return rutas, hallazgos

    ubicacion = "proposal.md#Alcance autorizado"
    entradas = []
    for linea in seccion.splitlines():
        linea = linea.strip()
        if linea.startswith("- ") or linea == "-":
            entradas.append(linea[1:])
        elif linea.startswith("* ") or linea.startswith("+ "):
            # M4: bullets no soportados -> hallazgo, nunca se ignoran en silencio.
            hallazgos.append(
                Finding(
                    CODE_ALCANCE_INVALIDO,
                    f"Bullet no soportado {linea!r}: usar '- ruta'",
                    ubicacion,
                )
            )
    if len(entradas) > _ALCANCE_MAX_ENTRADAS:
        hallazgos.append(
            Finding(
                CODE_ALCANCE_INVALIDO,
                f"Más de {_ALCANCE_MAX_ENTRADAS} entradas en el alcance autorizado ({len(entradas)})",
                ubicacion,
            )
        )
        return [], hallazgos
    for crudo in entradas:
        ruta, motivo = _normalizar_entrada_alcance(crudo)
        if motivo is not None:
            hallazgos.append(
                Finding(CODE_ALCANCE_INVALIDO, f"Entrada de alcance inválida {crudo.strip()!r}: {motivo}", ubicacion)
            )
            continue
        if ruta not in rutas:
            rutas.append(ruta)
    if hallazgos:
        return [], hallazgos
    return rutas, hallazgos


def presupuesto_agregado(control: dict) -> dict:
    """Vista derivada pura (sin I/O, sin escritura) sobre `control["sesiones"]`
    (R10, R12, R12a de `spec.md`; D4 de `design.md`) --

        {"minutos_consumidos_totales": float, "sesiones_totales": int,
         "sesiones_abiertas": int}

    Para una sesión cerrada, usa su `minutos_consumidos` ya persistido (igual
    que `session_close` lo dejó). Para la sesión activa (`estado_final ==
    "activa"`, a lo sumo una, `_sesion_activa`), calcula sus minutos
    consumidos hasta el momento con la MISMA lógica que ya usa
    `session_status` (`inicio_utc` vía `parsear_utc`, contra el momento
    actual vía `parsear_utc(ahora_utc())`) -- no se duplica con una copia
    ligeramente distinta.

    `sesiones_totales = len(control.get("sesiones", []))`: ya satisface R12a
    (reapertura tras `pausada_bloqueada` consume una nueva unidad de
    `max_sessions`) sin ingeniería adicional -- decisión congelada de D4 de
    `design.md`, ver ahí el razonamiento completo. Esta función no llama a
    `session_start` ni lo modifica: una consulta nunca infla el conteo.
    """
    sesiones = control.get("sesiones", [])
    minutos_totales = 0.0
    sesiones_abiertas = 0
    ahora = parsear_utc(ahora_utc())

    for sesion in sesiones:
        if sesion.get("estado_final") == "activa":
            sesiones_abiertas += 1
            inicio = parsear_utc(sesion["inicio_utc"])
            minutos_totales += (ahora - inicio).total_seconds() / 60.0
        else:
            minutos_totales += sesion.get("minutos_consumidos", 0.0) or 0.0

    return {
        "minutos_consumidos_totales": minutos_totales,
        "sesiones_totales": len(sesiones),
        "sesiones_abiertas": sesiones_abiertas,
    }


def chequear_limite_agregado(control: dict, config_budgets: Optional[dict]) -> list:
    """Compara `presupuesto_agregado(control)` contra `config_budgets`
    (`{"aggregate_minutes": ..., "max_sessions": ...}`, ambas claves
    opcionales -- ausente = sin límite en ese eje; `config_budgets` puede ser
    `None`, equivalente a `{}`) y devuelve una lista de `Finding` con código
    `AUTONOMY-LIMIT-AGGREGATE-BUDGET` (`tools.autonomy.core.
    CODE_LIMIT_AGGREGATE_BUDGET`, ya reservado por Change 0, reutilizado tal
    cual -- ningún código nuevo) cuando el consumo agregado ya alcanzó o
    superó el límite configurado en cualquiera de los dos ejes (tiempo,
    cantidad de sesiones).

    Agotar este límite produce `checkpoint_resumable`, NUNCA STOP ni
    aprobación automática (R11 de `spec.md`, cita textual). Esta función es
    puramente informativa: no lanza excepción, no escribe nada en `control`,
    no impide `session_start` ni ningún otro llamado -- decidir qué hacer con
    el `Finding` devuelto (p. ej. negarse a abrir una sesión nueva) es
    responsabilidad exclusiva del llamador (CLI, fuera de esta invocación).
    Su firma no tiene ningún parámetro de "usuario"/"aprobado_por": no puede
    pedir aprobación humana, ni implícita ni explícitamente.
    """
    findings: list = []
    agregado = presupuesto_agregado(control)
    config_budgets = config_budgets or {}

    limite_minutos = config_budgets.get("aggregate_minutes")
    if limite_minutos is not None and agregado["minutos_consumidos_totales"] >= limite_minutos:
        findings.append(
            Finding(
                autonomy_core.CODE_LIMIT_AGGREGATE_BUDGET,
                f"Presupuesto agregado de tiempo alcanzado/excedido: "
                f"{agregado['minutos_consumidos_totales']:.1f} min >= {limite_minutos} min",
            )
        )

    limite_sesiones = config_budgets.get("max_sessions")
    if limite_sesiones is not None and agregado["sesiones_totales"] >= limite_sesiones:
        findings.append(
            Finding(
                autonomy_core.CODE_LIMIT_AGGREGATE_BUDGET,
                f"Cantidad de sesiones ({agregado['sesiones_totales']}) alcanzó/superó "
                f"el máximo agregado configurado ({limite_sesiones})",
            )
        )

    return findings


def limite_subagentes_alcanzado(control: dict, max_concurrentes: Optional[int]) -> bool:
    """`True` si el conteo autorreportado de subagentes concurrentes
    (`activa["subagentes"]["conteo"]`, poblado por `session_note(
    tipo="subagente", evento="abrir"|"cerrar")`) ya alcanzó o superó
    `max_concurrentes` (v0.8 Change 3, R13-R14 de `spec.md`, D6 de
    `design.md`). Autorreportado por el Lead, sin enforcement técnico real --
    un Lead que omite el autorreporte no es detectado por este mecanismo:
    esta función es solo la consulta que un llamador (CLI/Lead, fuera de esta
    invocación) haría ANTES de invocar el tool `Agent`; no bloquea nada por
    sí sola, no escribe nada en `control`.

    `False` sin sesión activa, o si `max_concurrentes is None` (sin límite
    configurado) -- en cualquier otro caso ("hay sesión activa" Y "hay límite
    configurado"), `True` solo si el conteo ya llegó al máximo.
    """
    if max_concurrentes is None:
        return False
    activa = _sesion_activa(control)
    if activa is None:
        return False
    conteo = (activa.get("subagentes") or {}).get("conteo", 0)
    return conteo >= max_concurrentes


# --- M11: pre-aprobación de dependencias del proyecto (adenda post-cierre ----
# 2026-09-30, "Corrección y adenda post-cierre" de
# `docs/roadmap/v0.8.md`) -------------------------------------------------
#
# Extiende, sin reabrirlo, el STOP `new_dependency` (STOP 4, `tools.autonomy.
# core.STOP_CATALOG`) y el mecanismo de `approval_mode: checkpoints` (M7).
# `STOP_CATALOG`/`POLICY_TABLE` de `tools.autonomy.core` NO se tocan: la
# clasificación vive acá y solo los consulta. Esto NO es una vía de
# instalación de dependencias -- solo clasifica si una solicitud dispara STOP
# o no (M11, congelado en el roadmap).

# Código nuevo y legítimo (a diferencia de los checkpoints de negocio, que
# reutilizan `autonomy_core.CODE_PREAPPROVED_INVALID`): una dependencia
# pre-aprobada no es un `PreApprovedDecision` (M11 no crea un tipo de "decisión"
# por dependencia, la trazabilidad de la aprobación humana ya la da el hash de
# `proposal.md` completo al aprobarlo, no una `ApprovalRef` por dependencia
# individual) -- por eso no existía ningún código previo para bullets de
# dependencias mal formados.
CODE_DEPENDENCY_PREAPPROVAL_INVALID = "SDD-DEPENDENCY-PREAPPROVAL-INVALID"

_RE_DEPENDENCY_BULLET = re.compile(r"^-\s*(?P<nombre>[^:]*?)\s*:\s*(?P<rango>.+?)\s*$")

def _parsear_version(version: str) -> tuple:
    """Alias fino de `pep440_subset.parse_version` (acepta local). Lanza
    `ValueError` si `version` está fuera del subset."""
    return pep440_subset.parse_version(version, permitir_local=True)


def _parsear_rango_version(rango: str) -> list:
    """Alias fino de `pep440_subset.parse_range` (subset PEP 440 soportado
    por Harmessi, R15-R20 de `20261006-sdd-parsers-and-guardrail-ownership`).
    Lanza `ValueError` con el motivo si el rango no entra en el subset."""
    return pep440_subset.parse_range(rango)


def _version_satisface_rango(version: str, rango: str) -> bool:
    """Alias fino de `pep440_subset.satisfies` (fail-closed, nunca lanza)."""
    return pep440_subset.satisfies(version, rango)


def parsear_dependencias_preaprobadas(texto: str) -> tuple:
    """Sección `## Dependencias pre-aprobadas` de `proposal.md` (M11) ->
    `(dependencias_validas, hallazgos)`.

    `dependencias_validas` es `list[dict]`, cada elemento
    `{"nombre": str, "rango": str}` -- SIN un tipo `PreApprovedDecision` (M11
    no reutiliza ese tipo: es una lista simple de dependencias, no una
    decisión con `approval_ref`, ver comentario de módulo arriba).
    `hallazgos` es `list[Finding]` con código
    `CODE_DEPENDENCY_PREAPPROVAL_INVALID`, uno por bullet mal formado (sin
    `:`, nombre vacío, rango vacío o no parseable por
    `_parsear_rango_version`) -- nunca se agrega la dependencia
    correspondiente a `dependencias_validas` en esos casos (sin dependencia
    fantasma, mismo criterio que `parsear_checkpoints_de_propuesta`).

    Formato de bullet (uno por línea, ejemplo):

        - package-a: >=1.2,<2

    Sección ausente (o vacía) -> `([], [])`, sin error."""
    seccion = _contenido_de_seccion(texto, "## Dependencias pre-aprobadas")
    dependencias_validas: list = []
    hallazgos: list = []
    if not seccion:
        return dependencias_validas, hallazgos

    ubicacion = "proposal.md#Dependencias pre-aprobadas"
    for linea in seccion.splitlines():
        linea = linea.strip()
        if not linea or not linea.startswith("-"):
            continue
        m = _RE_DEPENDENCY_BULLET.match(linea)
        if not m:
            hallazgos.append(
                Finding(
                    CODE_DEPENDENCY_PREAPPROVAL_INVALID,
                    f"Bullet de dependencia con formato ambiguo/incompleto (sin ':'): {linea!r}",
                    ubicacion,
                )
            )
            continue
        nombre = m.group("nombre").strip()
        rango = m.group("rango").strip()
        if not nombre:
            hallazgos.append(
                Finding(
                    CODE_DEPENDENCY_PREAPPROVAL_INVALID,
                    f"Bullet de dependencia con nombre vacío: {linea!r}",
                    ubicacion,
                )
            )
            continue
        if not rango:
            hallazgos.append(
                Finding(
                    CODE_DEPENDENCY_PREAPPROVAL_INVALID,
                    f"Bullet de dependencia con rango vacío: {linea!r}",
                    ubicacion,
                )
            )
            continue
        try:
            _parsear_rango_version(rango)
        except ValueError as exc:
            hallazgos.append(
                Finding(
                    CODE_DEPENDENCY_PREAPPROVAL_INVALID,
                    f"Bullet de dependencia con rango no parseable ({exc}): {linea!r}",
                    ubicacion,
                )
            )
            continue
        dependencias_validas.append({"nombre": nombre, "rango": rango})

    return dependencias_validas, hallazgos


def clasificar_dependencia(nombre: str, version: str, dependencias_preaprobadas: list) -> str:
    """Clasifica una solicitud de dependencia del proyecto (M11): `"no_stop"`
    si `nombre` figura EXACTO (case-sensitive) en `dependencias_preaprobadas`
    y `version` satisface el `rango` de esa entrada; en cualquier otro caso
    (nombre no listado, versión fuera de rango, o `version` no parseable)
    devuelve el código STOP de `new_dependency`
    (`tools.autonomy.core.STOP_CATALOG`, buscado programáticamente -- nunca
    hardcodeado). Función PURA: no escribe nada, no lanza excepción por una
    versión rara (fail-closed: la trata como "no satisface")."""
    for entrada in dependencias_preaprobadas or []:
        if entrada.get("nombre") == nombre:
            if _version_satisface_rango(version, entrada.get("rango", "")):
                return "no_stop"
            break
    # Búsqueda sobre el símbolo PÚBLICO `STOP_CATALOG` (no
    # `autonomy_core._stop_code`, privado por convención -- hallazgo de
    # revisión, corregido: cruzaba el límite de encapsulamiento del módulo
    # sin necesidad, ya que `STOP_CATALOG` alcanza y es parte del contrato
    # público de `tools.autonomy.core`, Change 0, sin tocarlo).
    return next(e.code for e in autonomy_core.STOP_CATALOG if e.key == "new_dependency")


def _canonicalizar_nombre_paquete(nombre: str) -> str:
    """PEP 503: normaliza `-`/`_`/`.` a `-` y pasa a minúsculas, para que
    `"My-Package"`, `"my_package"`, `"my.package"` comparen igual sin
    autorizar nunca un paquete DISTINTO (R36)."""
    return re.sub(r"[-_.]+", "-", nombre).lower()


# Patrón de un nombre de distribución PyPI simple (R35): letras/dígitos/
# '-'/'_'/'.', empieza y termina con alfanumérico, sin URL/path/extras/
# espacios/metacaracteres. Deliberadamente estricto: cualquier forma no
# cubierta acá (URL, path, `file:`, `git+...`, `name @ ...`, `pkg[extra]`,
# múltiples paquetes separados por espacio/coma, metacaracteres de shell)
# se rechaza por NO matchear, no por una lista de denylist -- allowlist
# positiva, más robusta que enumerar cada forma prohibida. Ninguno de los
# caracteres prohibidos por R35 (`/`, `\`, espacio, `@`, `[`, `]`, `:`,
# `;`, `&`, `|`, backtick, `$`, `(`, `)`, `<`, `>`, salto de línea) está en
# la clase `[A-Za-z0-9._-]`, así que quedan excluidos por construcción, no
# por chequeo explícito.
_PATRON_NOMBRE_PAQUETE_SIMPLE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")


def validar_forma_nombre_paquete(nombre: str) -> bool:
    """`True` solo si `nombre` es un nombre de distribución PyPI simple (R35):
    sin URL (`http://`, `https://`, cualquier `://`), sin path (`/` o `\\`),
    sin `file:`, sin VCS (`git+...`, `hg+...`, `svn+...`, `bzr+...`), sin
    direct reference (`name @ url`, es decir sin espacio ni `@`), sin extras
    (`package[extra]`, es decir sin `[`/`]`), sin múltiples paquetes (sin
    espacios/comas), sin metacaracteres de shell (`;`, `&`, `|`, `` ` ``,
    `$`, `(`, `)`, `<`, `>`, salto de línea). Fail-closed: cualquier `nombre`
    que no sea `str`, esté vacío, o no matchee EXACTAMENTE
    `_PATRON_NOMBRE_PAQUETE_SIMPLE` devuelve `False`."""
    if not isinstance(nombre, str) or not nombre:
        return False
    return bool(_PATRON_NOMBRE_PAQUETE_SIMPLE.match(nombre))


# --- Métricas de eficiencia writer -> Lead (adenda post-cierre 2026-09-30, ---
# punto 3 de "Corrección y adenda post-cierre" de `docs/roadmap/v0.8.md`) ----
#
# Vistas derivadas puras sobre datos ya existentes en `control.json` (más la
# referencia liviana de ejecuciones, aditiva, poblada por `ds_guard.py`) --
# observación para Change 5, nunca gate numérico.

def calcular_metricas_eficiencia(control: dict) -> dict:
    """`{"writer_lead_cycles": int, "remediation_cycles": int,
    "executions_count": int, "execution_duration_total_seconds": float}`.

    - `writer_lead_cycles`: suma de `len(tareas)` de todas las sesiones --
      cada tarea registrada (`session_note(tipo="planificada", tarea=...)`)
      ya representa un ciclo writer -> Lead completo.
    - `remediation_cycles`: suma de intentos ya registrados en la ventana
      vigente (última) de cada remediación de `control["remediaciones"]`.
    - `executions_count`/`execution_duration_total_seconds`: derivados de
      `control["metricas_eficiencia"]["ejecuciones"]` (referencias livianas
      pobladas por `ds_guard.py` tras cada ejecución gobernada exitosa con
      `record`). Ausente (Change/`control.json` anterior a este fix, o
      ninguna ejecución gobernada corrida todavía) -> `0`/`0.0`, sin romper
      backward compatibility.

    Función PURA: sin I/O, sin escritura."""
    sesiones = control.get("sesiones", [])
    writer_lead_cycles = sum(len(s.get("tareas", []) or []) for s in sesiones)

    remediaciones = control.get("remediaciones", [])
    remediation_cycles = 0
    for r in remediaciones:
        ventanas = r.get("ventanas") or [{}]
        remediation_cycles += len(ventanas[-1].get("intentos", []) or [])

    ejecuciones = control.get("metricas_eficiencia", {}).get("ejecuciones", [])
    executions_count = len(ejecuciones)
    execution_duration_total_seconds = sum(
        float(e.get("duration_seconds", 0.0) or 0.0) for e in ejecuciones
    )

    return {
        "writer_lead_cycles": writer_lead_cycles,
        "remediation_cycles": remediation_cycles,
        "executions_count": executions_count,
        "execution_duration_total_seconds": execution_duration_total_seconds,
    }
