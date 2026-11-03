"""Hook de telemetría de subagentes: eventos `SubagentStart` / `SubagentStop`
de Claude Code (v0.15 Change 4, `20261026-v015-runtime-observability`).
Solo biblioteca estándar y SIN imports del paquete `dsguard` ni de otros
hooks: nada que pueda fallar al importar fuera de `main()` (fail-open).

Registra en la sesión SDD activa `subagentes[agent_id]` con:
`{rol, inicio_utc, arranque_actual_utc, arranques, paradas, fin_utc,
duracion_s, continuaciones, ultimo_evento_utc}`.

- `SubagentStart` con `agent_id` nuevo: alta con `arranques=1`,
  `continuaciones=0`. Con `agent_id` existente (reanudación): `arranques += 1`
  SIN tocar `continuaciones` (las incrementa `hook_presupuesto` en
  `SendMessage`). Salvedad: no se observó si `SubagentStart` se dispara en
  una reanudación por `SendMessage`; `arranques` puede quedar subcontado.
- `SubagentStop`: `paradas += 1`, `fin_utc` y `duracion_s` acumulada. Un Stop
  SIN Start previo crea la instancia con `arranques=0` (intencional: se
  registra lo observado, sin inventar un arranque).

Privacidad: SOLO se leen `hook_event_name`, `agent_id` y `agent_type` del
payload. Nunca se lee ni persiste `last_assistant_message`,
`agent_transcript_path`, `transcript_path`, prompt ni `cwd`.

Fail-open: es telemetría. `main()` siempre devuelve 0 (errores a stderr).
Sin sesión activa no registra.

Concurrencia (limitación ACEPTADA, telemetría y enforcement): escritura
atómica con tmp único por proceso/hilo (`control.json.<pid>.<tid>.tmp`) +
`os.replace` con 3 reintentos cortos ante `PermissionError`, y el control.json
se relee inmediatamente antes de mutar y escribir (sección corta, sin trabajo
intermedio). No hay lock: queda una carrera residual de milisegundos. Efectos
concretos: (a) un alta puede perderse -- entonces `hook_presupuesto` no
encuentra el `agent_id` y permite el `SendMessage` sin contar; (b) un contador
de `continuaciones` incrementado por `hook_presupuesto` en esa ventana puede
revertirse. Ninguno corrompe el archivo.

Activación: requiere registrar los eventos en `.claude/settings.json`
(superficie protegida, paso humano; ver ARCHITECTURE.md §11.2). Mientras tanto
el hook está inactivo.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]

EVENTO_INICIO = "SubagentStart"
EVENTO_FIN = "SubagentStop"
ROL_DESCONOCIDO = "desconocido"
REINTENTOS_REEMPLAZO = 3
ESPERA_REINTENTO_S = 0.02
_FORMATO_UTC = "%Y-%m-%dT%H:%M:%SZ"


def _ahora_utc() -> str:
    return datetime.now(timezone.utc).strftime(_FORMATO_UTC)


def _segundos_entre(inicio: Optional[str], fin: str) -> Optional[float]:
    if not isinstance(inicio, str) or not inicio:
        return None
    try:
        delta = datetime.strptime(fin, _FORMATO_UTC) - datetime.strptime(inicio, _FORMATO_UTC)
    except (ValueError, TypeError):
        return None
    return max(0.0, delta.total_seconds())


def _hallar_sesion_activa(repo_root: Path) -> Optional[tuple]:
    """Copia mínima (sin efectos de import) de la búsqueda de
    `hook_presupuesto._hallar_sesion_activa`: `(control_path, control,
    sesion)` de la primera sesión con `estado_final == "activa"` bajo
    `openspec/changes/*/control.json`, o `None`. Nunca levanta: un
    control.json ilegible se ignora."""
    changes_dir = Path(repo_root) / "openspec" / "changes"
    if not changes_dir.is_dir():
        return None
    for change_dir in sorted(changes_dir.iterdir()):
        control_path = change_dir / "control.json"
        try:
            control = json.loads(control_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(control, dict):
            continue
        sesiones = control.get("sesiones", [])
        if not isinstance(sesiones, list):
            continue
        for sesion in sesiones:
            if isinstance(sesion, dict) and sesion.get("estado_final") == "activa":
                return control_path, control, sesion
    return None


def _escribir_atomico(control_path: Path, control: dict) -> None:
    """tmp único por proceso/hilo + `os.replace` con reintentos cortos ante
    `PermissionError`; el tmp nunca queda huérfano."""
    texto = json.dumps(control, indent=2, ensure_ascii=False) + "\n"
    tmp = control_path.with_name(f"{control_path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(texto, encoding="utf-8")
        for intento in range(REINTENTOS_REEMPLAZO):
            try:
                os.replace(tmp, control_path)
                return
            except PermissionError:
                if intento == REINTENTOS_REEMPLAZO - 1:
                    raise
                time.sleep(ESPERA_REINTENTO_S)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def registrar_evento(sesion: dict, evento: str, agent_id: str, agent_type: Optional[str],
                     ahora: Optional[str] = None) -> bool:
    """Muta `sesion["subagentes"]` in-place. Devuelve `True` si registró algo.
    Pura salvo por la mutación (el llamador persiste)."""
    if evento not in (EVENTO_INICIO, EVENTO_FIN):
        return False
    ahora = ahora or _ahora_utc()
    subagentes = sesion.get("subagentes")
    if not isinstance(subagentes, dict):
        subagentes = {"conteo": 0}
        sesion["subagentes"] = subagentes
    entrada = subagentes.get(agent_id)
    if not isinstance(entrada, dict):
        entrada = {}
        subagentes[agent_id] = entrada
    rol = agent_type if isinstance(agent_type, str) and agent_type else ROL_DESCONOCIDO
    entrada["rol"] = rol
    entrada.setdefault("continuaciones", 0)
    entrada.setdefault("arranques", 0)
    entrada.setdefault("paradas", 0)
    entrada.setdefault("duracion_s", 0.0)

    if evento == EVENTO_INICIO:
        entrada.setdefault("inicio_utc", ahora)
        entrada["arranques"] = int(entrada["arranques"]) + 1
        entrada["arranque_actual_utc"] = ahora
    else:
        entrada["paradas"] = int(entrada["paradas"]) + 1
        entrada["fin_utc"] = ahora
        segundos = _segundos_entre(entrada.get("arranque_actual_utc"), ahora)
        if segundos is not None:
            entrada["duracion_s"] = float(entrada["duracion_s"]) + segundos
        entrada["arranque_actual_utc"] = None
    entrada["ultimo_evento_utc"] = ahora
    return True


def procesar(repo_root: Path, evento: str, agent_id: str, agent_type: Optional[str]) -> bool:
    """Una sola sección corta: relee control.json, muta y escribe. `True` si
    escribió. Puede levantar (`main` lo captura: fail-open)."""
    hallado = _hallar_sesion_activa(repo_root)
    if hallado is None:
        return False
    control_path, control, sesion = hallado
    if not registrar_evento(sesion, evento, agent_id, agent_type):
        return False
    _escribir_atomico(control_path, control)
    return True


def main() -> int:
    """Siempre 0 (fail-open); los errores van a stderr."""
    try:
        texto = sys.stdin.read()
        payload = json.loads(texto) if texto.strip() else None
        if not isinstance(payload, dict):
            print("hook_subagentes: payload vacío o no es un objeto JSON; se ignora.", file=sys.stderr)
            return 0
        evento = payload.get("hook_event_name")
        agent_id = payload.get("agent_id")
        agent_type = payload.get("agent_type")
        if evento not in (EVENTO_INICIO, EVENTO_FIN):
            return 0
        if not isinstance(agent_id, str) or not agent_id:
            print("hook_subagentes: payload sin agent_id; no se registra.", file=sys.stderr)
            return 0
        procesar(REPO_ROOT, evento, agent_id, agent_type)
    except Exception as exc:  # noqa: BLE001 -- fail-open deliberado
        print(f"hook_subagentes: error ignorado (fail-open): {exc!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
