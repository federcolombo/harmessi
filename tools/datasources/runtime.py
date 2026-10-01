"""Capa de I/O e `importlib` de `datasources` (v0.8 Change 1, T3, R13/R16-R23/R26).

Lee `.harmessi/sources.json`, resuelve estáticamente el registro
(`check_registry`, sin importar código del proyecto), orquesta la
observación de una fuente (`observe_source`, R16) y compara frescura
(`compare_fingerprint`, R26).

Imports permitidos: stdlib (`os`, `pathlib`, `importlib`, `hashlib`, `json`,
`datetime`, `sys`) + `dsguard.checks` (vía `sys.path.insert`, mismo patrón que
`tools/datacontracts/validation.py:67-71`) + los módulos puros propios
(`core`, `scan`, `registry`, relativos). NO importa `tools.autonomy` ni
`tools.dsguard.pathguard` (D8): el control de acceso real (`access_check`) lo
compone `tools/ds_guard.py` (T6) y se inyecta acá como parámetro obligatorio
de `observe_source` (R25).

**Límite conocido (R17): sin timeout en proceso.** `observe_source` ejecuta
el `factory`/`capabilities`/`observe` del observer de forma síncrona, en el
mismo proceso, sin ningún mecanismo de timeout: un observer colgado bloquea
el proceso que lo invoca. El timeout lo aportará el runtime de ejecución del
Change 2 (M6 del roadmap); se documenta aquí como límite honesto, no como
oversight.

`check_registry` es *best-effort* sobre patrones de secretos/localizadores
(R19): puede tener falsos negativos/positivos, no reemplaza a `pathguard`.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

_TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from dsguard import checks  # noqa: E402

from . import core  # noqa: E402
from . import registry  # noqa: E402
from . import scan  # noqa: E402

CheckResult = checks.CheckResult

# ---------------------------------------------------------------------------
# load_registry / check_registry (R13)
# ---------------------------------------------------------------------------


def load_registry(repo_root: Any) -> tuple:
    """Lee `<repo_root>/.harmessi/sources.json`. Nunca lanza.

    - Ausente -> `(None, [CheckResult(WARN, CODE_REGISTRY_MISSING, ...)])`.
    - JSON ilegible / no dict -> `(None, [CheckResult(FAIL,
      CODE_REGISTRY_INVALID, ..., kind=technical_error)])`.
    - Válido -> `(dict, [])`.
    """
    try:
        ruta = Path(repo_root) / ".harmessi" / "sources.json"
        if not ruta.is_file():
            return None, [
                CheckResult(
                    checks.STATUS_WARN,
                    core.CODE_REGISTRY_MISSING,
                    "no hay fuentes registradas (falta .harmessi/sources.json)",
                )
            ]
        try:
            texto = ruta.read_text(encoding="utf-8")
            data = json.loads(texto)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return None, [
                CheckResult(
                    checks.STATUS_FAIL,
                    core.CODE_REGISTRY_INVALID,
                    f"registro ilegible: {type(exc).__name__}",
                    kind=checks.KIND_TECHNICAL_ERROR,
                )
            ]
        if not isinstance(data, dict):
            return None, [
                CheckResult(
                    checks.STATUS_FAIL,
                    core.CODE_REGISTRY_INVALID,
                    f"registro inválido: se esperaba dict, se recibió {type(data).__name__}",
                )
            ]
        return data, []
    except Exception as exc:  # noqa: BLE001 - nunca escapa
        return None, [checks.resultado_de_excepcion(core.CODE_REGISTRY_INVALID, exc)]


# Severidad de cada código que puede devolver `registry.check_registry_static`.
_SEVERIDAD_REGISTRO = {
    core.CODE_OBSERVER_UNRESOLVED: checks.STATUS_WARN,
}


def check_registry(repo_root: Any) -> list:
    """`check_registry(repo_root)` estático (R13): compone `load_registry` +
    `registry.check_registry_static` con un `exists_fn` real que SOLO llama a
    `Path.is_file()` (nunca abre/importa el módulo del observer). Nunca
    lanza."""
    try:
        data, resultados = load_registry(repo_root)
        if data is None:
            return resultados

        repo_root_path = Path(repo_root)

        def exists_fn(ruta_relativa: str) -> bool:
            try:
                return (repo_root_path / ruta_relativa).is_file()
            except OSError:
                return False

        hallazgos = registry.check_registry_static(data, exists_fn)
        for code, path, motivo in hallazgos:
            status = _SEVERIDAD_REGISTRO.get(code, checks.STATUS_FAIL)
            resultados.append(CheckResult(status, code, motivo, subject=path))
        return resultados
    except Exception as exc:  # noqa: BLE001 - nunca escapa
        return [checks.resultado_de_excepcion(core.CODE_REGISTRY_INVALID, exc)]


# ---------------------------------------------------------------------------
# Helpers de observe_source
# ---------------------------------------------------------------------------


def _redactar_si_hace_falta(texto: str) -> str:
    """Pasa `texto` por `scan.scan_secrets`/`scan.scan_locators`; si alguno
    encuentra algo, devuelve `"[REDACTADO]"` en vez del texto original."""
    if scan.scan_secrets(texto) or scan.scan_locators(texto):
        return "[REDACTADO]"
    return texto


def _error_observer(exc: Exception) -> CheckResult:
    """`technical_error SOURCE-OBSERVER-ERROR` para cualquier excepción de
    import/factory/`capabilities()`/`observe()` (R16 paso 3). `message` no
    referencia rutas absolutas locales; `detail` = `type(exc).__name__` +
    primeros 300 caracteres de `str(exc)`, redactado si el scan de R19
    encuentra algo."""
    crudo = f"{type(exc).__name__}: {str(exc)[:300]}"
    return CheckResult(
        checks.STATUS_FAIL,
        core.CODE_OBSERVER_ERROR,
        "el observer falló al importarse o ejecutarse",
        detail=_redactar_si_hace_falta(crudo),
        kind=checks.KIND_TECHNICAL_ERROR,
    )


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _buscar_fuente(data: dict, source_id: str) -> Optional[dict]:
    fuentes = data.get("sources")
    if not isinstance(fuentes, list):
        return None
    for entrada in fuentes:
        if isinstance(entrada, dict) and entrada.get("source_id") == source_id:
            return entrada
    return None


def _filtrar_facetas(
    facets_dict: dict, facetas_permitidas: set, exactness_pedida: str
) -> tuple:
    """Filtra un dict de facetas (de campo o de dataset) contra el conjunto
    `facetas_permitidas` (pedidas ∩ declaradas). Devuelve
    `(dict_filtrado, nombres_no_soportados_por_exactitud, invalido)`.

    - Clave fuera de `facetas_permitidas` -> `invalido = True` (R16 paso 6:
      "trae facetas no pedidas/no declaradas").
    - Con `exactness_pedida == "exact"`, una faceta devuelta como
      `"approximate"` se descarta (R18): se agrega a
      `nombres_no_soportados_por_exactitud`, no se persiste."""
    resultado: dict = {}
    no_soportadas: list = []
    invalido = False
    if not isinstance(facets_dict, dict):
        return resultado, no_soportadas, True
    for clave, valor in facets_dict.items():
        if clave not in facetas_permitidas:
            invalido = True
            continue
        exactitud_faceta = valor.get("exactness") if isinstance(valor, dict) else None
        if exactness_pedida == "exact" and exactitud_faceta == "approximate":
            no_soportadas.append(clave)
            continue
        resultado[clave] = valor
    return resultado, no_soportadas, invalido


def _a_dict_observacion(resultado_bruto: Any) -> Optional[dict]:
    if isinstance(resultado_bruto, core.SourceObservation):
        return resultado_bruto.to_dict()
    if isinstance(resultado_bruto, dict):
        return resultado_bruto
    return None


# ---------------------------------------------------------------------------
# observe_source (R16)
# ---------------------------------------------------------------------------


def observe_source(
    repo_root: Any,
    source_id: str,
    request: Any,
    access_check: Optional[Callable[[str, str], tuple]],
    options_extra: Optional[dict] = None,
) -> tuple:
    """Observa `source_id` según el registro de `repo_root`. Orden
    OBLIGATORIO (R16, D8): registro -> `access_check` (antes de importar) ->
    import del observer -> capacidades -> intersección de facetas -> observe
    -> normalización -> provenance + sensibilidad -> gate de
    portabilidad/secretos -> persistencia atómica.

    `access_check(source_id, access_mode)` es OBLIGATORIO: recibe el
    `source_id` y el `access_mode` efectivo (string, `SourceRef.access_mode`)
    de la fuente registrada, y debe devolver `(permitido: bool, motivo: str)`.
    Es el mínimo necesario para que `ds_guard.py` (T6) componga la policy real
    sin que `datasources` conozca `autonomy`/`pathguard` (R25/D8). Si
    `access_check` es `None`, lanza, o deniega, se corta ANTES de tocar el
    observer.

    `options_extra` (opcional, M9): claves que se agregan a las `options` que
    se pasan al `factory` del observer SOLO si el registro no las declaraba ya
    (`setdefault`, nunca pisa lo que el registro declara explícitamente). Se
    usa para inyectar infraestructura como `_repo_root` o
    `ruta_externa_absoluta` sin que `datasources` conozca de dónde vienen.

    Devuelve `(SourceObservation | None, list[CheckResult])`. Nunca lanza."""
    try:
        return _observe_source_interno(repo_root, source_id, request, access_check, options_extra)
    except Exception as exc:  # noqa: BLE001 - red de seguridad final
        return None, [checks.resultado_de_excepcion(core.CODE_OBSERVER_ERROR, exc)]


def _observe_source_interno(repo_root, source_id, request, access_check, options_extra=None) -> tuple:
    # --- Paso 1: registro ---------------------------------------------------
    data, resultados_registro = load_registry(repo_root)
    if data is None:
        return None, resultados_registro

    entrada = _buscar_fuente(data, source_id)
    if entrada is None:
        return None, [
            CheckResult(checks.STATUS_FAIL, core.CODE_UNKNOWN, f"fuente desconocida: {source_id!r}")
        ]

    try:
        source_ref = core.SourceRef.from_dict(entrada)
    except core.SourceError as exc:
        return None, [CheckResult(checks.STATUS_FAIL, exc.code, exc.message)]

    # --- Paso 2: access_check, ANTES de importar nada -----------------------
    if access_check is None:
        return None, [
            CheckResult(
                checks.STATUS_FAIL,
                core.CODE_ACCESS_DENIED,
                "observe_source requiere access_check; ninguno fue provisto (fail-closed, R25)",
            )
        ]
    try:
        permitido, motivo = access_check(source_id, source_ref.access_mode)
    except Exception as exc:  # noqa: BLE001
        return None, [
            CheckResult(
                checks.STATUS_FAIL,
                core.CODE_ACCESS_DENIED,
                f"access_check lanzó una excepción: {type(exc).__name__}",
                kind=checks.KIND_TECHNICAL_ERROR,
            )
        ]
    if not permitido:
        motivo_str = str(motivo) if motivo else "acceso denegado"
        code = core.CODE_SEALED if "sellad" in motivo_str.casefold() else core.CODE_ACCESS_DENIED
        return None, [CheckResult(checks.STATUS_FAIL, code, motivo_str)]

    # --- Paso 3: import + factory + capabilities() + observe() -------------
    modulo_nombre, _, callable_nombre = source_ref.observer.partition(":")
    try:
        mod = importlib.import_module(modulo_nombre)
        factory = getattr(mod, callable_nombre)
        options_efectivas = dict(source_ref.options)
        if options_extra:
            for clave, valor in options_extra.items():
                options_efectivas.setdefault(clave, valor)  # NUNCA pisa una clave que el registro ya declaró
        observer = factory(source_id, options_efectivas)
    except Exception as exc:  # noqa: BLE001
        return None, [_error_observer(exc)]

    try:
        capabilities_bruto = observer.capabilities()
    except Exception as exc:  # noqa: BLE001
        return None, [_error_observer(exc)]

    # --- Paso 4: capacidades validadas --------------------------------------
    try:
        caps_dict = (
            capabilities_bruto.to_dict()
            if isinstance(capabilities_bruto, core.SourceCapabilities)
            else capabilities_bruto
        )
        capabilities = core.SourceCapabilities.from_dict(caps_dict)
    except core.SourceError as exc:
        return None, [CheckResult(checks.STATUS_FAIL, exc.code, exc.message)]
    except Exception as exc:  # noqa: BLE001 - forma inesperada de capabilities()
        return None, [
            CheckResult(
                checks.STATUS_FAIL,
                core.CODE_CAPABILITIES_INVALID,
                f"capabilities() devolvió una forma inválida: {type(exc).__name__}",
            )
        ]

    # --- Paso 5: pedido acotado a las facetas soportadas --------------------
    try:
        if isinstance(request, core.ObservationRequest):
            obs_request = request
        else:
            req_dict = dict(request) if request is not None else {"source_id": source_id}
            req_dict.setdefault("source_id", source_id)
            obs_request = core.ObservationRequest.from_dict(req_dict)
    except core.SourceError as exc:
        return None, [CheckResult(checks.STATUS_FAIL, exc.code, exc.message)]

    facetas_declaradas = set(capabilities.facets.keys())
    facetas_pedidas = set(obs_request.facets) if obs_request.facets else set(facetas_declaradas)
    facetas_soportadas = facetas_pedidas & facetas_declaradas
    facetas_no_declaradas = sorted(facetas_pedidas - facetas_declaradas)

    resultados: list = []
    for faceta in facetas_no_declaradas:
        resultados.append(
            CheckResult(
                checks.STATUS_WARN,
                core.CODE_FACET_UNSUPPORTED,
                f"faceta pedida no declarada por el observer: {faceta}",
                subject=faceta,
            )
        )

    request_al_observer = core.ObservationRequest(
        source_id=source_id,
        facets=tuple(sorted(facetas_soportadas)),
        exactness=obs_request.exactness,
        as_of=obs_request.as_of,
        max_rows=obs_request.max_rows,
        sample_size=obs_request.sample_size,
    )

    # --- Paso 6: observe() + normalización -----------------------------------
    try:
        resultado_bruto = observer.observe(request_al_observer.to_dict())
    except Exception as exc:  # noqa: BLE001
        return None, [_error_observer(exc)]

    obs_dict = _a_dict_observacion(resultado_bruto)
    if obs_dict is None:
        return None, resultados + [
            CheckResult(
                checks.STATUS_FAIL,
                core.CODE_OBSERVATION_INVALID,
                f"observe() devolvió {type(resultado_bruto).__name__}, se esperaba dict o SourceObservation",
            )
        ]

    unsupported_extra: set = set(facetas_no_declaradas)

    dataset_bruto = obs_dict.get("dataset", {}) or {}
    dataset_filtrado, no_soportadas_dataset, invalido_dataset = _filtrar_facetas(
        {k: v for k, v in dataset_bruto.items() if k != "sampling"},
        facetas_soportadas,
        obs_request.exactness,
    )
    if "sampling" in dataset_bruto:
        dataset_filtrado["sampling"] = dataset_bruto["sampling"]
    unsupported_extra |= set(no_soportadas_dataset)
    for faceta in no_soportadas_dataset:
        resultados.append(
            CheckResult(
                checks.STATUS_WARN,
                core.CODE_FACET_UNSUPPORTED,
                f"faceta de dataset descartada por exactitud pedida: {faceta}",
                detail="exactness",
                subject=faceta,
            )
        )
    if invalido_dataset:
        return None, resultados + [
            CheckResult(
                checks.STATUS_FAIL,
                core.CODE_OBSERVATION_INVALID,
                "la observación trae facetas de dataset no pedidas/no declaradas",
            )
        ]

    campos_brutos = obs_dict.get("fields", [])
    if not isinstance(campos_brutos, list):
        return None, resultados + [
            CheckResult(checks.STATUS_FAIL, core.CODE_OBSERVATION_INVALID, "fields: se esperaba una lista")
        ]

    campos_normalizados = []
    for campo_bruto in campos_brutos:
        campo_dict = campo_bruto.to_dict() if isinstance(campo_bruto, core.FieldObservation) else campo_bruto
        if not isinstance(campo_dict, dict):
            return None, resultados + [
                CheckResult(checks.STATUS_FAIL, core.CODE_OBSERVATION_INVALID, "fields[]: se esperaba dict")
            ]
        facets_filtrados, no_soportadas_campo, invalido_campo = _filtrar_facetas(
            campo_dict.get("facets", {}), facetas_soportadas, obs_request.exactness
        )
        if invalido_campo:
            return None, resultados + [
                CheckResult(
                    checks.STATUS_FAIL,
                    core.CODE_OBSERVATION_INVALID,
                    f"el campo {campo_dict.get('name')!r} trae facetas no pedidas/no declaradas",
                )
            ]
        unsupported_extra |= set(no_soportadas_campo)
        for faceta in no_soportadas_campo:
            resultados.append(
                CheckResult(
                    checks.STATUS_WARN,
                    core.CODE_FACET_UNSUPPORTED,
                    f"faceta descartada por exactitud pedida en {campo_dict.get('name')!r}: {faceta}",
                    detail="exactness",
                    subject=f"{campo_dict.get('name')}.{faceta}",
                )
            )
        nuevo = dict(campo_dict)
        nuevo["facets"] = facets_filtrados
        campos_normalizados.append(nuevo)

    # --- Paso 7: provenance calculada por el runtime (R21) -------------------
    provenance_bruta = obs_dict.get("provenance") if isinstance(obs_dict.get("provenance"), dict) else {}
    source_kind = provenance_bruta.get("source_kind")
    tool_versions = provenance_bruta.get("tool_versions") if isinstance(provenance_bruta.get("tool_versions"), dict) else {}

    hash_codigo = None
    archivo_modulo = getattr(mod, "__file__", None)
    if archivo_modulo:
        try:
            with open(archivo_modulo, "rb") as fh:
                crudo = fh.read()
            normalizado = crudo.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            hash_codigo = hashlib.sha256(normalizado).hexdigest()
        except OSError:
            hash_codigo = None
    if hash_codigo is None:
        resultados.append(
            CheckResult(
                checks.STATUS_WARN,
                core.CODE_OBSERVER_CODE_UNHASHABLE,
                "no se pudo calcular observer_code_sha256: el módulo no tiene archivo fuente legible",
            )
        )

    provenance = core.SourceProvenance(
        source_id=source_id,
        observer_id=source_ref.observer,
        observer_code_sha256=hash_codigo,
        access_mode=source_ref.access_mode,
        source_kind=source_kind,
        generated_at=_ahora_iso(),
        tool_versions=tool_versions,
        requested_facets=tuple(sorted(facetas_pedidas)),
        unsupported_facets=tuple(sorted(unsupported_extra)),
    )

    try:
        observation = core.SourceObservation(
            source_id=source_id,
            provenance=provenance,
            dataset=dataset_filtrado,
            fields=tuple(core.FieldObservation.from_dict(c) for c in campos_normalizados),
            omitted_facets=(),
        )
    except core.SourceError as exc:
        return None, resultados + [CheckResult(checks.STATUS_FAIL, exc.code, exc.message)]

    # --- Paso 8: sensibilidad (R22), ANTES del hash/persistencia -----------
    if source_ref.sensitivity == "sensitive":
        campos_sensibles = []
        omitidos = list(observation.omitted_facets)
        hubo_omision = False
        for campo in observation.fields:
            facets_campo = dict(campo.facets)
            for clave in ("value_distribution", "value_range", "time_range"):
                if clave in facets_campo:
                    del facets_campo[clave]
                    omitidos.append({"field": campo.name, "facet": clave, "reason": "sensitivity"})
                    hubo_omision = True
            campos_sensibles.append(
                core.FieldObservation(
                    name=campo.name,
                    type_family=campo.type_family,
                    native_type=campo.native_type,
                    facets=facets_campo,
                )
            )
        if hubo_omision:
            observation = core.SourceObservation(
                source_id=observation.source_id,
                provenance=observation.provenance,
                dataset=observation.dataset,
                fields=tuple(campos_sensibles),
                omitted_facets=tuple(omitidos),
            )
            resultados.append(
                CheckResult(
                    checks.STATUS_WARN,
                    core.CODE_FACET_OMITTED,
                    "facetas omitidas antes de persistir por sensibilidad de la fuente (sensitivity=sensitive)",
                )
            )

    # --- Paso 9: gate de portabilidad/secretos (R19/R20) ---------------------
    obs_dict_final = observation.to_dict()
    hallazgos_scan = scan.scan_secrets(obs_dict_final) + scan.scan_locators(obs_dict_final)
    if hallazgos_scan:
        resultados_gate = [
            CheckResult(
                checks.STATUS_FAIL,
                code,
                f"gate de portabilidad: {motivo}",
                subject=pointer,
            )
            for code, pointer, motivo in hallazgos_scan
        ]
        return None, resultados + resultados_gate

    # --- Paso 10: persistencia atómica (R23) ---------------------------------
    try:
        resultado_persistencia = _persistir_observacion(repo_root, observation)
    except Exception as exc:  # noqa: BLE001
        return None, resultados + [
            CheckResult(
                checks.STATUS_FAIL,
                core.CODE_PERSIST_ERROR,
                f"error al persistir la observación: {type(exc).__name__}",
                kind=checks.KIND_TECHNICAL_ERROR,
            )
        ]
    if resultado_persistencia is not None:
        return None, resultados + [resultado_persistencia]

    return observation, resultados


def _persistir_observacion(repo_root: Any, observation) -> Optional[CheckResult]:
    """Escritura atómica de `observation.json` bajo
    `.harmessi/observations/<observation_id>/`. Devuelve `None` si quedó
    persistida (o ya existía con bytes idénticos), o un `CheckResult` FAIL si
    hay una colisión de hash con contenido distinto."""
    content_hash = observation.content_sha256()
    observation_id = f"{observation.source_id}__{content_hash[:12]}"
    dir_path = Path(repo_root) / ".harmessi" / "observations" / observation_id
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / "observation.json"

    payload = json.dumps(observation.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    payload_bytes = payload.encode("utf-8")

    if file_path.exists():
        existente = file_path.read_bytes()
        if existente == payload_bytes:
            return None
        return CheckResult(
            checks.STATUS_FAIL,
            core.CODE_PERSIST_ERROR,
            f"colisión de hash: {observation_id} ya existe con contenido distinto",
        )

    tmp_path = dir_path / (file_path.name + ".tmp")
    try:
        tmp_path.write_bytes(payload_bytes)
        os.replace(tmp_path, file_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return None


# ---------------------------------------------------------------------------
# compare_fingerprint (R26)
# ---------------------------------------------------------------------------


def compare_fingerprint(stored: Any, fresh: Any) -> CheckResult:
    """Compara `dataset.fingerprint` de dos observaciones (dict o
    `SourceObservation`, aceptado por firma). Pura, nunca lanza.

    - Mismo `source_id` requerido; distinto -> FAIL `SOURCE-OBSERVATION-INVALID`.
    - Ambos con fingerprint y mismo `algorithm`: igual `value` -> PASS,
      distinto -> FAIL `SOURCE-OBSERVATION-STALE`.
    - Falta fingerprint en alguno, o `algorithm` distinto -> WARN
      `SOURCE-FRESHNESS-UNVERIFIABLE` (nunca PASS por ausencia).
    - `snapshot.as_of` distinto se reporta en `detail` sin afectar el status.
    """
    try:
        stored_dict = stored.to_dict() if hasattr(stored, "to_dict") else dict(stored)
        fresh_dict = fresh.to_dict() if hasattr(fresh, "to_dict") else dict(fresh)
    except Exception:  # noqa: BLE001
        return CheckResult(
            checks.STATUS_FAIL,
            core.CODE_OBSERVATION_INVALID,
            "no se pudo interpretar alguna de las dos observaciones para comparar fingerprint",
        )

    stored_id = stored_dict.get("source_id")
    fresh_id = fresh_dict.get("source_id")
    if stored_id != fresh_id:
        return CheckResult(
            checks.STATUS_FAIL,
            core.CODE_OBSERVATION_INVALID,
            f"source_id distinto entre observaciones: {stored_id!r} vs {fresh_id!r}",
        )

    stored_dataset = stored_dict.get("dataset") or {}
    fresh_dataset = fresh_dict.get("dataset") or {}
    stored_fp = stored_dataset.get("fingerprint")
    fresh_fp = fresh_dataset.get("fingerprint")

    stored_as_of = (stored_dataset.get("snapshot") or {}).get("as_of")
    fresh_as_of = (fresh_dataset.get("snapshot") or {}).get("as_of")
    detail = None
    if stored_as_of != fresh_as_of:
        detail = f"snapshot.as_of distinto: {stored_as_of!r} vs {fresh_as_of!r}"

    if not isinstance(stored_fp, dict) or not isinstance(fresh_fp, dict):
        return CheckResult(
            checks.STATUS_WARN,
            core.CODE_FRESHNESS_UNVERIFIABLE,
            "fingerprint ausente en alguna observación: frescura no verificable",
            detail=detail,
        )

    if stored_fp.get("algorithm") != fresh_fp.get("algorithm"):
        return CheckResult(
            checks.STATUS_WARN,
            core.CODE_FRESHNESS_UNVERIFIABLE,
            "algoritmo de fingerprint distinto entre observaciones: frescura no verificable",
            detail=detail,
        )

    if stored_fp.get("value") == fresh_fp.get("value"):
        return CheckResult(
            checks.STATUS_PASS,
            core.CODE_OBSERVATION_STALE,
            "fingerprint idéntico: la observación sigue vigente",
            detail=detail,
        )

    return CheckResult(
        checks.STATUS_FAIL,
        core.CODE_OBSERVATION_STALE,
        "fingerprint distinto: la observación está desactualizada",
        detail=detail,
    )
