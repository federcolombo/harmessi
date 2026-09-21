"""Validacion de reportes y de su evidencia persistida (v0.6 Change 3,
`20260918-report-evidence-and-validation`, tanda B + ciclo reviewer 1).

Tres niveles, una puerta:
- `validate_report(report, *, scientific_policy=None)`: Report en memoria
  (figuras, insights y, si aplica, perfil EDA).
- `validate_manifest(manifest, report=None)`: manifest (+ coherencia con el Report).
- `validate_report_dir(repo_root, out_dir)`: LA PUERTA COMPLETA sobre disco, en orden
  fijo: manifest -> integridad de artefactos (+ conjunto esperado) -> fuentes ->
  contenido (Report cargado) -> governance -> aislamiento por hash. Solo lectura.

Principio: se verifica existencia y coherencia ESTRUCTURAL y se hace cumplir lo
determinista. Ausencia de evidencia no es PASS. Todo resultado es un
`dsguard.checks.CheckResult`; cada regla devuelve un PASS si no hay violaciones y
una entrada por violacion. Ninguna funcion publica lanza: cada regla corre bajo
`_ejecutar` (una excepcion inesperada se convierte en FAIL `technical_error` con
codigo `<CODIGO>-EXCEPCION`; el mensaje lleva el TIPO de la excepcion, no su texto,
para no filtrar rutas locales).

Invariante de lectura: ningun archivo (manifest, artefacto, fuente, input) se abre
sin evaluar ANTES `evidence.read_allowed`. Una fuente denegada es FAIL
`REPORT-SOURCE-UNVERIFIABLE` (technical_error): NUNCA PASS ni STALE, y no se abre.
El directorio del reporte se lee UNA vez (`evidence.read_report_dir`): los mismos
bytes se hashean (`REPORT-ARTIFACT-HASH`) y construyen el Report
(`evidence.report_from_bytes`), sin releer disco. Si esa lectura falla, se relee
solo el manifest y cada artefacto listado individualmente (ruta de error).

`scientific_policy`: `validate_report_dir` la lee UNA vez del disco
(`scientific_validity.leer_policy`) y ese mismo dict alimenta a todo lo que la usa
(EDA). Si esta corrupta, FAIL `technical_error` `REPORT-SCI-POLICY` y NO se
evalua parcialmente lo que dependa de ella (se omite la validacion EDA); governance
lee la policy por su cuenta y reporta su propio fallo.

Interpretaciones de la spec (marcadas): `out_dir` relativo se interpreta contra
`repo_root`; `REPORT-EXPLORATORY-IN-MODEL-FLOW` es un FAIL agregado que se emite
ademas de `REPORT-ISOLATION-INPUT`/`REPORT-ISOLATION-HASH` cuando alguno falla en
un flujo `model_valid`/`operational`; `REPORT-MANIFEST-CONSISTENCY` tambien compara
`sensitivity.contains_sensitive`.

Limites honestos (spec R24):
- NO se evalua si una conclusion excede la evidencia ni si la evidencia es adecuada:
  un insight puede referenciar una tabla irrelevante y pasar.
- Los sha256 son AUTOATESTADOS: prueban integridad frente a corrupcion o edicion
  parcial, no autoria ni aprobacion. Un manifest reescrito de forma consistente
  junto con los artefactos NO se detecta; el ancla externa (firma, registro
  aparte) es del hardening.
- La isolation por hash cubre copias byte-identicas, no derivados.
- El indice exploratory depende de manifests existentes bajo el root.
- `git_dirty` es informativo (WARN); no bloquea.
- TOCTOU: hay una ventana entre `read_allowed` y la lectura, y entre hashear una
  fuente y usarla; las lecturas son single-read pero no atomicas.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from dsguard import checks  # noqa: E402
from dsguard import scientific_validity  # noqa: E402

from . import core as reporting_core  # noqa: E402
from . import evidence  # noqa: E402
from . import governance  # noqa: E402
from .profiles import eda as eda_profile  # noqa: E402

# --- Codigos ------------------------------------------------------------------

CODE_FIGURE_NO_TABLE = "REPORT-FIGURE-NO-TABLE"
CODE_FIGURE_DANGLING_TABLE = "REPORT-FIGURE-DANGLING-TABLE"
CODE_FIGURE_SPEC_COLUMNS = "REPORT-FIGURE-SPEC-COLUMNS"
CODE_FIGURE_TABLE_EMPTY = "REPORT-FIGURE-TABLE-EMPTY"
CODE_SENSITIVE_FIGURE = "REPORT-SENSITIVE-FIGURE"
CODE_INSIGHT_CLAIMS = "REPORT-INSIGHT-CLAIMS"
CODE_INSIGHT_NO_EVIDENCE = "REPORT-INSIGHT-NO-EVIDENCE"
CODE_INSIGHT_DANGLING_REF = "REPORT-INSIGHT-DANGLING-REF"
CODE_INSIGHT_UNCERTAINTY = "REPORT-INSIGHT-UNCERTAINTY"
CODE_INSIGHT_REVIEW_REQUIRED = "REPORT-INSIGHT-REVIEW-REQUIRED"
CODE_MANIFEST_SCHEMA = "REPORT-MANIFEST-SCHEMA"
CODE_MANIFEST_CONSISTENCY = "REPORT-MANIFEST-CONSISTENCY"
CODE_SOURCES_NONE = "REPORT-SOURCES-NONE"
CODE_PROVENANCE = "REPORT-PROVENANCE"
CODE_MANIFEST_MISSING = "REPORT-MANIFEST-MISSING"
CODE_MANIFEST_UNREADABLE = "REPORT-MANIFEST-UNREADABLE"
CODE_ARTIFACT_MISSING = "REPORT-ARTIFACT-MISSING"
CODE_ARTIFACT_HASH = "REPORT-ARTIFACT-HASH"
CODE_ARTIFACT_UNLISTED = "REPORT-ARTIFACT-UNLISTED"
CODE_ARTIFACT_SET = "REPORT-ARTIFACT-SET"
CODE_SOURCE_MISSING = "REPORT-SOURCE-MISSING"
CODE_SOURCE_STALE = "REPORT-SOURCE-STALE"
CODE_SOURCE_UNVERIFIABLE = "REPORT-SOURCE-UNVERIFIABLE"
CODE_EXPLORATORY_IN_MODEL_FLOW = "REPORT-EXPLORATORY-IN-MODEL-FLOW"
CODE_SCI_POLICY = "REPORT-SCI-POLICY"
CODE_LOAD = "REPORT-LOAD"
CODE_INPUT = "REPORT-INPUT"
CODE_EDA = "REPORT-EDA"
CODE_DIR = "REPORT-DIR"

CODES = (
    CODE_FIGURE_NO_TABLE,
    CODE_FIGURE_DANGLING_TABLE,
    CODE_FIGURE_SPEC_COLUMNS,
    CODE_FIGURE_TABLE_EMPTY,
    CODE_SENSITIVE_FIGURE,
    CODE_INSIGHT_CLAIMS,
    CODE_INSIGHT_NO_EVIDENCE,
    CODE_INSIGHT_DANGLING_REF,
    CODE_INSIGHT_UNCERTAINTY,
    CODE_INSIGHT_REVIEW_REQUIRED,
    CODE_MANIFEST_SCHEMA,
    CODE_MANIFEST_CONSISTENCY,
    CODE_SOURCES_NONE,
    CODE_PROVENANCE,
    CODE_MANIFEST_MISSING,
    CODE_MANIFEST_UNREADABLE,
    CODE_ARTIFACT_MISSING,
    CODE_ARTIFACT_HASH,
    CODE_ARTIFACT_UNLISTED,
    CODE_ARTIFACT_SET,
    CODE_SOURCE_MISSING,
    CODE_SOURCE_STALE,
    CODE_SOURCE_UNVERIFIABLE,
    CODE_EXPLORATORY_IN_MODEL_FLOW,
    CODE_SCI_POLICY,
    CODE_LOAD,
    CODE_INPUT,
)

MAX_ARTIFACT_FILES_SCAN = 5000  # archivos recorridos bajo artifacts/ (fail-closed si se supera)

_SCOPES_FLUJO_MODELO = ("model_valid", "operational")
_CLAIM_DESCRIPTIVE = "descriptive"
_CLAIMS_REVISION = ("causal", "recommendation")
_RE_SHA256 = re.compile(r"[0-9a-fA-F]{64}")
_RE_COMMIT = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_RAIZ_PERMITIDA = (reporting_core.MANIFEST_FILENAME, reporting_core.REPORT_FILENAME)
_ATRIBUTO_REPARSE_POINT = 0x400
_CAMPOS_MANIFEST = (
    "schema_version", "report_id", "run_id", "report_kind", "decision_scope", "data_cutoff",
    "git_commit", "git_dirty", "harmessi_version", "generated_at", "sources", "exclusions",
    "holdout_access", "sensitivity", "source_notebook", "artifacts", "hashes",
)


# --- Helpers ------------------------------------------------------------------


def _res(status: str, code: str, message: str, subject: Optional[str] = None, *,
         tecnico: bool = False, detail: Optional[str] = None) -> checks.CheckResult:
    return checks.CheckResult(
        status=status,
        code=code,
        message=message,
        detail=detail,
        subject=subject,
        kind=checks.KIND_TECHNICAL_ERROR if tecnico else checks.KIND_CHECK,
    )


def _excepcion(base: str, exc: Exception) -> checks.CheckResult:
    """FAIL technical_error `<base>-EXCEPCION` con el TIPO de la excepcion (sin su texto: puede llevar rutas)."""
    return checks.CheckResult(
        checks.STATUS_FAIL,
        f"{base}-EXCEPCION",
        f"Fallo inesperado ejecutando el check ({type(exc).__name__})",
        kind=checks.KIND_TECHNICAL_ERROR,
    )


def _ejecutar(registros: list) -> list:
    """Como `checks.ejecutar_checks` (nunca frena, preserva el orden) pero sin filtrar el texto de la excepcion."""
    resultados: list = []
    for base, funcion, args in registros:
        try:
            resultados.extend(funcion(*args))
        except Exception as exc:  # noqa: BLE001 -- nunca debe escapar de una regla
            resultados.append(_excepcion(base, exc))
    return resultados


def _resumir(code: str, violaciones: list, mensaje_pass: str, *, status: str = checks.STATUS_FAIL) -> list:
    """Un PASS si no hay violaciones; si no, una entrada `(mensaje, subject)` por violacion."""
    if not violaciones:
        return [_res(checks.STATUS_PASS, code, mensaje_pass)]
    return [_res(status, code, mensaje, subject) for mensaje, subject in violaciones]


def _str_no_vacio(valor: Any) -> bool:
    return isinstance(valor, str) and bool(valor.strip())


def _es_sha(valor: Any) -> bool:
    return isinstance(valor, str) and _RE_SHA256.fullmatch(valor) is not None


def _es_int_no_neg(valor: Any) -> bool:
    return type(valor) is int and valor >= 0


def _ruta_segura(rel: Any) -> bool:
    """Ruta relativa posix segura (misma regla que `evidence`: sin `..`, `\\x00`, nombres reservados)."""
    return evidence._ruta_relativa_segura(rel)


def _unir(base: Path, rel_posix: str) -> Path:
    return base.joinpath(*rel_posix.split("/"))


def _sha_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _es_enlace(ruta: Path) -> bool:
    try:
        if ruta.is_symlink():
            return True
        return bool(getattr(os.lstat(ruta), "st_file_attributes", 0) & _ATRIBUTO_REPARSE_POINT)
    except OSError:
        return False


def _sensibles_de(report: reporting_core.Report) -> list:
    return sorted(
        [t.table_id for t in report.iter_tables() if t.sensitive]
        + [f.figure_id for f in report.iter_figures() if f.sensitive]
    )


# --- R12: figuras -------------------------------------------------------------


def _regla_figura_sin_tabla(report: Any) -> list:
    v = [
        (f"la figura {f.figure_id!r} no declara backing_table_id (ningún gráfico sin su tabla)", f.figure_id)
        for f in report.iter_figures()
        if f.backing_table_id is None
    ]
    return _resumir(CODE_FIGURE_NO_TABLE, v, "Toda figura declara su tabla de respaldo.")


def _regla_figura_tabla_colgante(report: Any) -> list:
    v = []
    for f in report.iter_figures():
        if f.backing_table_id is not None and report.get_table(f.backing_table_id) is None:
            v.append(
                (
                    f"la figura {f.figure_id!r} apunta a backing_table_id {f.backing_table_id!r}, "
                    f"que no es una tabla del reporte",
                    f.figure_id,
                )
            )
    return _resumir(CODE_FIGURE_DANGLING_TABLE, v, "Todo backing_table_id resuelve a una tabla del reporte.")


def _regla_figura_columnas(report: Any) -> list:
    v = []
    for f in report.iter_figures():
        tabla = report.get_table(f.backing_table_id) if f.backing_table_id is not None else None
        if tabla is None:
            continue
        usadas = list(dict.fromkeys(f.spec.columns_used()))
        faltan = [c for c in usadas if c not in tabla.columns]
        if faltan:
            v.append(
                (
                    f"la figura {f.figure_id!r} usa columnas ausentes en la tabla {tabla.table_id!r}: "
                    f"{', '.join(repr(c) for c in faltan)}",
                    f.figure_id,
                )
            )
    return _resumir(CODE_FIGURE_SPEC_COLUMNS, v, "Las columnas de cada spec existen en su tabla de respaldo.")


def _regla_figura_tabla_vacia(report: Any) -> list:
    v = []
    for f in report.iter_figures():
        tabla = report.get_table(f.backing_table_id) if f.backing_table_id is not None else None
        if tabla is not None and len(tabla.rows) == 0:
            v.append((f"la figura {f.figure_id!r} está respaldada por la tabla vacía {tabla.table_id!r}", f.figure_id))
    return _resumir(CODE_FIGURE_TABLE_EMPTY, v, "Ninguna tabla de respaldo está vacía.")


def _regla_figura_sensible(report: Any) -> list:
    v = []
    for f in report.iter_figures():
        tabla = report.get_table(f.backing_table_id) if f.backing_table_id is not None else None
        if tabla is not None and tabla.sensitive and not f.sensitive:
            v.append(
                (
                    f"la figura {f.figure_id!r} no es sensible pero su tabla {tabla.table_id!r} sí: "
                    f"posible fuga vía gráfico (decisión del revisor)",
                    f.figure_id,
                )
            )
    return _resumir(
        CODE_SENSITIVE_FIGURE, v, "Ninguna figura no sensible depende de una tabla sensible.", status=checks.STATUS_WARN
    )


# --- R13: insights ------------------------------------------------------------


def _regla_insight_claims(report: Any) -> list:
    v = []
    for i in report.iter_insights():
        vacios = [
            campo
            for campo in ("technical_claim", "business_claim", "population", "time_scope")
            if not _str_no_vacio(getattr(i, campo, None))
        ]
        if vacios:
            v.append((f"el insight {i.insight_id!r} tiene campos vacíos: {', '.join(vacios)}", i.insight_id))
    return _resumir(CODE_INSIGHT_CLAIMS, v, "Todo insight declara claims, población y horizonte temporal.")


def _regla_insight_sin_evidencia(report: Any) -> list:
    v = [
        (f"el insight {i.insight_id!r} no tiene evidence_refs (afirmación sin sustento verificable)", i.insight_id)
        for i in report.iter_insights()
        if len(i.evidence_refs) == 0
    ]
    return _resumir(CODE_INSIGHT_NO_EVIDENCE, v, "Todo insight declara evidence_refs.")


def _regla_insight_ref_colgante(report: Any) -> list:
    v = []
    for i in report.iter_insights():
        for ref in i.evidence_refs:
            if report.get_artifact(ref) is None:
                v.append(
                    (
                        f"el insight {i.insight_id!r} referencia {ref!r}, que no es tabla ni figura del reporte",
                        i.insight_id,
                    )
                )
    return _resumir(CODE_INSIGHT_DANGLING_REF, v, "Toda evidence_ref resuelve a una tabla o figura del reporte.")


def _regla_insight_incertidumbre(report: Any) -> list:
    v = [
        (f"el insight {i.insight_id!r} es {i.claim_type!r} y no declara uncertainty", i.insight_id)
        for i in report.iter_insights()
        if i.claim_type != _CLAIM_DESCRIPTIVE and not _str_no_vacio(i.uncertainty)
    ]
    return _resumir(
        CODE_INSIGHT_UNCERTAINTY, v, "Todo insight no descriptivo declara uncertainty.", status=checks.STATUS_WARN
    )


def _regla_insight_revision(report: Any) -> list:
    v = [
        (
            f"el insight {i.insight_id!r} es {i.claim_type!r}: requiere revisión semántica del "
            f"Lead/metodólogo (el binario no juzga si excede la evidencia)",
            i.insight_id,
        )
        for i in report.iter_insights()
        if i.claim_type in _CLAIMS_REVISION
    ]
    return _resumir(
        CODE_INSIGHT_REVIEW_REQUIRED, v, "Sin insights causal/recommendation que requieran revisión.",
        status=checks.STATUS_WARN,
    )


def _regla_eda(report: Any, scientific_policy: Any) -> list:
    return list(eda_profile.validate_eda_report(report, scientific_policy=scientific_policy))


def _validar_report(report: Any, scientific_policy: Any, incluir_eda: bool) -> list:
    if not isinstance(report, reporting_core.Report):
        return [
            _res(
                checks.STATUS_FAIL, CODE_INPUT, f"el objeto validado no es un Report ({type(report).__name__})",
                tecnico=True,
            )
        ]
    registros = [
        (CODE_FIGURE_NO_TABLE, _regla_figura_sin_tabla, (report,)),
        (CODE_FIGURE_DANGLING_TABLE, _regla_figura_tabla_colgante, (report,)),
        (CODE_FIGURE_SPEC_COLUMNS, _regla_figura_columnas, (report,)),
        (CODE_FIGURE_TABLE_EMPTY, _regla_figura_tabla_vacia, (report,)),
        (CODE_SENSITIVE_FIGURE, _regla_figura_sensible, (report,)),
        (CODE_INSIGHT_CLAIMS, _regla_insight_claims, (report,)),
        (CODE_INSIGHT_NO_EVIDENCE, _regla_insight_sin_evidencia, (report,)),
        (CODE_INSIGHT_DANGLING_REF, _regla_insight_ref_colgante, (report,)),
        (CODE_INSIGHT_UNCERTAINTY, _regla_insight_incertidumbre, (report,)),
        (CODE_INSIGHT_REVIEW_REQUIRED, _regla_insight_revision, (report,)),
    ]
    metadata = report.metadata if isinstance(report.metadata, dict) else {}
    if incluir_eda and (report.report_kind == "eda" or "eda" in metadata):
        registros.append((CODE_EDA, _regla_eda, (report, scientific_policy)))
    return _ejecutar(registros)


def validate_report(report: Any, *, scientific_policy: Optional[dict] = None) -> list:
    """Figuras + insights (+ perfil EDA con el MISMO `scientific_policy`). Un PASS por
    regla sin violaciones. Nunca lanza."""
    try:
        return _validar_report(report, scientific_policy, True)
    except Exception as exc:  # noqa: BLE001 -- contrato: nunca lanza
        return [_excepcion("REPORT-VALIDATE", exc)]


# --- R15: manifest ------------------------------------------------------------


def _problemas_fuente(i: int, s: Any, add) -> None:
    campo = f"sources[{i}]"
    if not isinstance(s, dict):
        add(campo, "no es un objeto")
        return
    kind = s.get("kind")
    if kind not in evidence.SOURCE_KINDS:
        add(campo, f"kind {kind!r} fuera de {evidence.SOURCE_KINDS}")
    if not _str_no_vacio(s.get("role")):
        add(campo, "role debe ser un str no vacío")
    if not _es_sha(s.get("sha256")):
        add(campo, "sha256 debe ser 64 hex")
    if not _str_no_vacio(s.get("algorithm")):
        add(campo, "algorithm debe ser un str no vacío")
    if kind == "file":
        if not _ruta_segura(s.get("path")):
            add(campo, "path debe ser relativo posix, seguro y sin unidad (no se repite el valor recibido)")
        if not _es_int_no_neg(s.get("size_bytes")):
            add(campo, "size_bytes debe ser un int >= 0")
        if "rows" in s and not _es_int_no_neg(s.get("rows")):
            add(campo, "rows debe ser un int >= 0")
        for opcional in ("min_date", "max_date", "date_column"):
            if opcional in s and not isinstance(s[opcional], str):
                add(campo, f"{opcional} debe ser un str")
    elif kind == "generated":
        if not _str_no_vacio(s.get("description")):
            add(campo, "description debe ser un str no vacío")
        if not isinstance(s.get("params"), dict):
            add(campo, "params debe ser un objeto")


def _problemas_manifest(m: dict) -> list:
    problemas: list = []

    def add(campo: str, mensaje: str) -> None:
        problemas.append((f"{campo}: {mensaje}", campo))

    for campo in _CAMPOS_MANIFEST:
        if campo not in m:
            add(campo, "falta el campo")
    if "schema_version" in m and (type(m["schema_version"]) is not int or m["schema_version"] != evidence.MANIFEST_SCHEMA_VERSION):
        add("schema_version", f"se esperaba {evidence.MANIFEST_SCHEMA_VERSION}, se recibió {m['schema_version']!r}")
    if "report_id" in m and not reporting_core.es_id_valido(m["report_id"]):
        add("report_id", f"id inválido: {m['report_id']!r}")
    if "run_id" in m and not _str_no_vacio(m["run_id"]):
        add("run_id", "debe ser un str no vacío")
    if "report_kind" in m and m["report_kind"] not in reporting_core.REPORT_KINDS:
        add("report_kind", f"{m['report_kind']!r} fuera de {reporting_core.REPORT_KINDS}")
    if "decision_scope" in m and m["decision_scope"] not in reporting_core.DECISION_SCOPES:
        add("decision_scope", f"{m['decision_scope']!r} fuera de {reporting_core.DECISION_SCOPES}")
    if "data_cutoff" in m and m["data_cutoff"] is not None and not isinstance(m["data_cutoff"], str):
        add("data_cutoff", "debe ser str o null")
    if "git_commit" in m and m["git_commit"] is not None and (
        not isinstance(m["git_commit"], str) or _RE_COMMIT.fullmatch(m["git_commit"]) is None
    ):
        add("git_commit", "debe ser un sha de 40/64 hex minúsculas o null")
    if "git_dirty" in m and m["git_dirty"] is not None and not isinstance(m["git_dirty"], bool):
        add("git_dirty", "debe ser bool o null")
    if "harmessi_version" in m and m["harmessi_version"] is not None and not _str_no_vacio(m["harmessi_version"]):
        add("harmessi_version", "debe ser un str no vacío o null")
    if "generated_at" in m:
        ok = False
        if isinstance(m["generated_at"], str):
            try:
                datetime.strptime(m["generated_at"], "%Y-%m-%dT%H:%M:%SZ")
                ok = True
            except ValueError:
                ok = False
        if not ok:
            add("generated_at", f"formato inválido (se esperaba YYYY-MM-DDTHH:MM:SSZ): {m['generated_at']!r}")
    if "sources" in m:
        if not isinstance(m["sources"], list):
            add("sources", "debe ser una lista")
        else:
            for i, s in enumerate(m["sources"]):
                _problemas_fuente(i, s, add)
    if "exclusions" in m:
        if not isinstance(m["exclusions"], list):
            add("exclusions", "debe ser una lista")
        else:
            for i, e in enumerate(m["exclusions"]):
                if not isinstance(e, dict) or not _str_no_vacio(e.get("description")) or not isinstance(e.get("reason"), str):
                    add(f"exclusions[{i}]", "requiere description (str no vacío) y reason (str)")
                elif e.get("rows_excluded") is not None and not _es_int_no_neg(e.get("rows_excluded")):
                    add(f"exclusions[{i}]", "rows_excluded debe ser un int >= 0 o null")
    if "holdout_access" in m and m["holdout_access"] not in evidence.HOLDOUT_ACCESS_VALUES:
        add("holdout_access", f"{m['holdout_access']!r} fuera de {evidence.HOLDOUT_ACCESS_VALUES}")
    if "sensitivity" in m:
        s = m["sensitivity"]
        if not isinstance(s, dict) or not isinstance(s.get("contains_sensitive"), bool) or not (
            isinstance(s.get("sensitive_artifacts"), list) and all(isinstance(x, str) for x in s["sensitive_artifacts"])
        ):
            add("sensitivity", "requiere contains_sensitive (bool) y sensitive_artifacts (lista de str)")
    if "source_notebook" in m and m["source_notebook"] is not None:
        n = m["source_notebook"]
        if not isinstance(n, dict) or not _ruta_segura(n.get("path")) or not _es_sha(n.get("sha256")) or not _str_no_vacio(n.get("algorithm")):
            add("source_notebook", "requiere path relativo posix, sha256 (64 hex) y algorithm, o null")
    if "artifacts" in m:
        if not isinstance(m["artifacts"], list):
            add("artifacts", "debe ser una lista")
        else:
            vistos: set = set()
            for i, a in enumerate(m["artifacts"]):
                campo = f"artifacts[{i}]"
                if not isinstance(a, dict):
                    add(campo, "no es un objeto")
                    continue
                if not _str_no_vacio(a.get("id")):
                    add(campo, "id debe ser un str no vacío")
                if a.get("kind") not in evidence.ARTIFACT_KINDS:
                    add(campo, f"kind {a.get('kind')!r} fuera de {evidence.ARTIFACT_KINDS}")
                if not _ruta_segura(a.get("file")):
                    add(campo, "file debe ser relativo posix y seguro (no se repite el valor recibido)")
                elif a["file"] in vistos:
                    add(campo, f"file duplicado: {a['file']!r}")
                else:
                    vistos.add(a["file"])
                if not _es_sha(a.get("sha256")):
                    add(campo, "sha256 debe ser 64 hex")
    if "hashes" in m:
        h = m["hashes"]
        if not isinstance(h, dict) or not _es_sha(h.get("report_content")):
            add("hashes", "requiere report_content (64 hex)")
    return problemas


def _regla_manifest_schema(manifest: Any) -> list:
    if not isinstance(manifest, dict):
        return [_res(checks.STATUS_FAIL, CODE_MANIFEST_SCHEMA, f"el manifest no es un objeto JSON ({type(manifest).__name__})")]
    return _resumir(CODE_MANIFEST_SCHEMA, _problemas_manifest(manifest), "El manifest cumple el esquema v1.")


def _regla_manifest_consistencia(manifest: Any, report: Any) -> list:
    if report is None:
        return [_res(checks.STATUS_NA, CODE_MANIFEST_CONSISTENCY, "sin Report: no hay contra qué comparar el manifest")]
    if not isinstance(report, reporting_core.Report):
        return [_res(checks.STATUS_FAIL, CODE_MANIFEST_CONSISTENCY, "el objeto a comparar no es un Report", tecnico=True)]
    if not isinstance(manifest, dict):
        return [_res(checks.STATUS_FAIL, CODE_MANIFEST_CONSISTENCY, "el manifest no es un objeto JSON")]
    v = []
    for campo, esperado in (
        ("report_id", report.report_id),
        ("report_kind", report.report_kind),
        ("decision_scope", report.decision_scope),
    ):
        if manifest.get(campo) != esperado:
            v.append((f"{campo}: manifest={manifest.get(campo)!r} vs Report={esperado!r}", campo))
    hashes = manifest.get("hashes")
    declarado = hashes.get("report_content") if isinstance(hashes, dict) else None
    if declarado != report.content_sha256():
        v.append(("hashes.report_content no coincide con Report.content_sha256()", "hashes.report_content"))
    sensibles = _sensibles_de(report)
    sens = manifest.get("sensitivity")
    lista = sens.get("sensitive_artifacts") if isinstance(sens, dict) else None
    if not isinstance(lista, list) or not all(isinstance(x, str) for x in lista) or sorted(lista) != sensibles:
        v.append(
            (
                f"sensitivity.sensitive_artifacts: manifest={lista!r} vs Report={sensibles!r}",
                "sensitivity.sensitive_artifacts",
            )
        )
    if isinstance(sens, dict) and sens.get("contains_sensitive") != bool(sensibles):
        v.append(
            (
                f"sensitivity.contains_sensitive: manifest={sens.get('contains_sensitive')!r} vs Report={bool(sensibles)!r}",
                "sensitivity.contains_sensitive",
            )
        )
    return _resumir(CODE_MANIFEST_CONSISTENCY, v, "El manifest es coherente con el Report.")


def _regla_fuentes_ausentes(manifest: Any) -> list:
    fuentes = manifest.get("sources") if isinstance(manifest, dict) else None
    if not isinstance(fuentes, list) or len(fuentes) == 0:
        return [
            _res(
                checks.STATUS_FAIL, CODE_SOURCES_NONE,
                "el manifest no declara fuentes (sources vacío): sin fuentes no hay evidencia de origen",
            )
        ]
    return [_res(checks.STATUS_PASS, CODE_SOURCES_NONE, f"El manifest declara {len(fuentes)} fuente(s).")]


def _regla_procedencia(manifest: Any) -> list:
    if not isinstance(manifest, dict):
        return [_res(checks.STATUS_WARN, CODE_PROVENANCE, "sin manifest legible: procedencia no verificable")]
    v = []
    if not manifest.get("git_commit"):
        v.append(("git_commit ausente: reproducibilidad degradada", "git_commit"))
    if manifest.get("git_dirty") is True:
        v.append(("git_dirty=true: el árbol de trabajo tenía cambios sin commitear", "git_dirty"))
    if not manifest.get("harmessi_version"):
        v.append(("harmessi_version ausente: reproducibilidad degradada", "harmessi_version"))
    return _resumir(
        CODE_PROVENANCE, v, "Procedencia completa (commit limpio y versión de Harmessi).", status=checks.STATUS_WARN
    )


def _validar_manifest(manifest: Any, report: Any) -> list:
    return _ejecutar(
        [
            (CODE_MANIFEST_SCHEMA, _regla_manifest_schema, (manifest,)),
            (CODE_MANIFEST_CONSISTENCY, _regla_manifest_consistencia, (manifest, report)),
            (CODE_SOURCES_NONE, _regla_fuentes_ausentes, (manifest,)),
            (CODE_PROVENANCE, _regla_procedencia, (manifest,)),
        ]
    )


def validate_manifest(manifest: Any, report: Any = None) -> list:
    """Esquema, coherencia con el Report (solo si se pasa), fuentes y procedencia.
    Nunca lanza."""
    try:
        return _validar_manifest(manifest, report)
    except Exception as exc:  # noqa: BLE001 -- contrato: nunca lanza
        return [_excepcion("REPORT-MANIFEST", exc)]


# --- R16: puerta completa -----------------------------------------------------


def _resolver_out(repo: Path, out_dir: Any) -> Path:
    ruta = Path(out_dir)
    if not ruta.is_absolute():
        ruta = repo / ruta
    return ruta.resolve()


def _out_relativo(repo: Path, out: Path) -> str:
    """Ruta relativa posix al repo; fuera del repo no expone la ruta local."""
    try:
        return out.relative_to(repo).as_posix()
    except ValueError:
        return f"<fuera-del-repo>/{out.name}"


def _out_para_governance(repo: Path, out: Path) -> str:
    """Governance necesita la ruta real para detectar un destino fuera del repo."""
    try:
        return out.relative_to(repo).as_posix()
    except ValueError:
        return str(out)


def _leer_manifest(repo: Path, out: Path, estado: dict) -> list:
    """Paso 1 + lectura UNICA del directorio (`read_report_dir`, con `read_allowed`
    antes de cada apertura). Deja `files`, `manifest` (y `error_lectura` si la
    lectura completa fallo) en `estado`."""
    ruta = out / reporting_core.MANIFEST_FILENAME
    nombre = reporting_core.MANIFEST_FILENAME
    permitido, motivo = evidence.read_allowed(repo, ruta)
    if not permitido:
        return [
            _res(
                checks.STATUS_FAIL, CODE_MANIFEST_UNREADABLE,
                f"no verificable: acceso denegado al {nombre}, no se abrió", subject=nombre, tecnico=True, detail=motivo,
            )
        ]
    if not os.path.lexists(ruta):
        return [
            _res(
                checks.STATUS_FAIL, CODE_MANIFEST_MISSING,
                f"no existe {nombre} en el directorio del reporte "
                f"(un reporte sin manifest no es válido aunque exista {reporting_core.REPORT_FILENAME})",
                subject=nombre,
            )
        ]
    try:
        files, manifest = evidence.read_report_dir(out, repo_root=repo)
        estado["files"], estado["manifest"] = files, manifest
    except evidence.EvidenceError as exc:
        estado["error_lectura"] = str(exc)
        try:  # ruta de error: solo el manifest, para seguir verificando integridad
            crudo = evidence.read_within(out, nombre, repo_root=repo)
            manifest = json.loads(crudo.decode("utf-8"))
        except (evidence.EvidenceError, ValueError, RecursionError) as exc2:
            return [
                _res(
                    checks.STATUS_FAIL, CODE_MANIFEST_UNREADABLE,
                    f"{nombre} ilegible o con JSON inválido: {exc2}", subject=nombre, tecnico=True,
                )
            ]
        if not isinstance(manifest, dict):
            return [
                _res(
                    checks.STATUS_FAIL, CODE_MANIFEST_UNREADABLE,
                    f"{nombre} no es un objeto JSON ({type(manifest).__name__})", subject=nombre, tecnico=True,
                )
            ]
        estado["files"], estado["manifest"] = {nombre: crudo}, manifest
    return [
        _res(checks.STATUS_PASS, CODE_MANIFEST_MISSING, f"{nombre} presente."),
        _res(checks.STATUS_PASS, CODE_MANIFEST_UNREADABLE, f"{nombre} legible."),
    ]


def _construir_report(estado: dict) -> list:
    """Reconstruye el Report SOLO desde los bytes ya leidos (sin tocar disco). No emite resultados."""
    if "error_lectura" in estado:
        estado["report_error"] = estado["error_lectura"]
        return []
    try:
        estado["report"] = evidence.report_from_bytes(estado["files"], estado["manifest"])
    except evidence.EvidenceError as exc:
        estado["report_error"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        estado["report_error"] = f"error inesperado reconstruyendo el Report ({type(exc).__name__})"
    return []


def _cargar_policy(repo: Path, estado: dict) -> list:
    """Lee la policy científica UNA vez; el mismo dict se pasa a todo lo que la use."""
    try:
        estado["policy"] = scientific_validity.leer_policy(repo)
    except scientific_validity.ScientificPolicyError as exc:
        estado["policy_ok"] = False
        return [
            _res(
                checks.STATUS_FAIL, CODE_SCI_POLICY,
                f"Policy científica inválida (SCI-POLICY, fail-closed): {exc}. "
                f"Se omite lo que depende de ella (validación EDA).",
                tecnico=True,
            )
        ]
    estado["policy_ok"] = True
    return [_res(checks.STATUS_PASS, CODE_SCI_POLICY, "Policy científica leída una vez desde disco.")]


def _entradas_validas(lista: Any) -> list:
    """Entradas de `artifacts` que son dict con `file` seguro."""
    if not isinstance(lista, list):
        return []
    return [e for e in lista if isinstance(e, dict) and _ruta_segura(e.get("file"))]


def _leer_artefacto(repo: Path, out: Path, rel: str, cache: dict) -> tuple:
    """`(bytes|None, motivo|None)`; `motivo == "missing"` si no existe. Reusa `cache`
    (los bytes ya leidos por `read_report_dir`); si no esta, lo lee UNA vez con acceso evaluado."""
    if rel in cache:
        return cache[rel], None
    if not os.path.lexists(_unir(out, rel)):
        return None, "missing"
    try:
        cache[rel] = evidence.read_within(out, rel, repo_root=repo)
    except evidence.EvidenceError as exc:
        return None, str(exc)
    return cache[rel], None


def _violaciones_conjunto(lista: Any, report: Any) -> list:
    """`REPORT-ARTIFACT-SET`: el manifest debe listar EXACTAMENTE `expected_artifacts(report)`."""
    v: list = []
    if not isinstance(lista, list):
        return [("el manifest no tiene una lista 'artifacts'", "artifacts")]
    for i, entrada in enumerate(lista):
        if not isinstance(entrada, dict):
            v.append((f"artifacts[{i}] no es un objeto", f"artifacts[{i}]"))
        elif not _ruta_segura(entrada.get("file")):
            v.append((f"artifacts[{i}]: ruta insegura o inválida (no se repite el valor recibido)", f"artifacts[{i}]"))
    if report is None:
        return v
    if len(lista) == 0:
        return v + [("'artifacts' está vacío: no hay artefactos verificables", "artifacts")]
    esperado = evidence.expected_artifacts(report)
    listados: dict = {}
    for entrada in _entradas_validas(lista):
        rel = entrada["file"]
        if rel in listados:
            v.append((f"artefacto listado más de una vez: {rel!r}", rel))
        listados[rel] = (entrada.get("id"), entrada.get("kind"))
    for rel, (identificador, kind) in esperado.items():
        if rel not in listados:
            v.append((f"artefacto esperado y no listado en el manifest: {rel!r}", rel))
        elif listados[rel] != (identificador, kind):
            v.append(
                (
                    f"{rel!r}: id/kind del manifest {listados[rel]!r} no coincide con el esperado {(identificador, kind)!r}",
                    rel,
                )
            )
    for rel in listados:
        if rel not in esperado:
            v.append((f"artefacto listado que no corresponde al Report: {rel!r}", rel))
    return v


def _no_listados(out: Path, listados: set) -> list:
    """Archivos/enlaces del out_dir que el manifest no lista (excepto manifest.json y report.html)."""
    hallados: list = []
    excedido = False
    try:
        nombres = sorted(os.listdir(out))
    except OSError:
        # Fail-closed: no poder listar NO es "nada sin listar".
        return [], False, True
    for nombre in nombres:
        if nombre in _RAIZ_PERMITIDA:
            continue
        ruta = out / nombre
        if nombre == reporting_core.ARTIFACTS_DIRNAME:
            if _es_enlace(ruta):
                hallados.append((f"enlace no permitido: {nombre!r}", nombre))
                continue
            n = 0
            for dirpath, dirnames, filenames in os.walk(ruta):
                dirnames.sort()
                for d in list(dirnames):
                    if _es_enlace(Path(dirpath, d)):
                        rel = Path(dirpath, d).relative_to(out).as_posix()
                        hallados.append((f"enlace no permitido bajo artifacts/: {rel!r}", rel))
                        dirnames.remove(d)
                for archivo in sorted(filenames):
                    n += 1
                    if n > MAX_ARTIFACT_FILES_SCAN:
                        return hallados, True, False
                    rel = Path(dirpath, archivo).relative_to(out).as_posix()
                    if rel not in listados:
                        hallados.append((f"archivo bajo artifacts/ no listado en el manifest: {rel!r}", rel))
        elif nombre == reporting_core.INSIGHTS_FILENAME:
            if nombre not in listados:
                hallados.append((f"{nombre!r} no está listado en el manifest", nombre))
        else:
            hallados.append((f"archivo en la raíz del reporte no listado en el manifest: {nombre!r}", nombre))
    return hallados, excedido, False


def _paso_artefactos(repo: Path, out: Path, manifest: dict, files: dict, report: Any) -> list:
    lista = manifest.get("artifacts")
    conjunto = _violaciones_conjunto(lista, report)
    if report is None and not conjunto:
        res_set = [_res(checks.STATUS_NA, CODE_ARTIFACT_SET, "sin Report cargado: el conjunto esperado no se puede calcular")]
    else:
        res_set = _resumir(CODE_ARTIFACT_SET, conjunto, "El manifest lista exactamente los artefactos del Report.")

    entradas = _entradas_validas(lista)
    cache = dict(files)
    faltantes: list = []
    alterados: list = []
    no_verificables: list = []
    for entrada in entradas:
        rel = entrada["file"]
        contenido, motivo = _leer_artefacto(repo, out, rel, cache)
        if motivo == "missing":
            faltantes.append((f"artefacto listado sin archivo: {rel!r}", rel))
        elif motivo is not None:
            no_verificables.append((f"no verificable: {motivo}", rel))
        else:
            esperado = entrada.get("sha256")
            if not isinstance(esperado, str) or _sha_bytes(contenido) != esperado.lower():
                alterados.append((f"los bytes de {rel!r} no coinciden con el sha256 del manifest (alterado)", rel))
    resultados = _resumir(CODE_ARTIFACT_MISSING, faltantes, "Todos los artefactos listados existen.")
    if alterados or no_verificables:
        resultados += [_res(checks.STATUS_FAIL, CODE_ARTIFACT_HASH, m, s) for m, s in alterados]
        resultados += [_res(checks.STATUS_FAIL, CODE_ARTIFACT_HASH, m, s, tecnico=True) for m, s in no_verificables]
    else:
        resultados.append(
            _res(checks.STATUS_PASS, CODE_ARTIFACT_HASH, "Los bytes de cada artefacto coinciden con el manifest.")
        )
    resultados += res_set

    sin_listar, excedido, error_listado = _no_listados(out, {e["file"] for e in entradas})
    if error_listado:
        return resultados + [
            _res(
                checks.STATUS_FAIL, CODE_ARTIFACT_UNLISTED,
                "no verificable: no se pudo listar el directorio del reporte", tecnico=True,
            )
        ]
    if excedido:
        resultados.append(
            _res(
                checks.STATUS_FAIL, CODE_ARTIFACT_UNLISTED,
                f"se superó MAX_ARTIFACT_FILES_SCAN={MAX_ARTIFACT_FILES_SCAN} (fail-closed)", tecnico=True,
            )
        )
    resultados += _resumir(
        CODE_ARTIFACT_UNLISTED, sin_listar, "Nada en el directorio del reporte queda sin listar.",
        status=checks.STATUS_WARN,
    )
    return resultados


def _fuentes_file(manifest: dict) -> list:
    fuentes = manifest.get("sources")
    if not isinstance(fuentes, list):
        return []
    return [s for s in fuentes if isinstance(s, dict) and s.get("kind") == "file"]


def _paso_fuentes(repo: Path, manifest: dict) -> list:
    fuentes = _fuentes_file(manifest)
    if not fuentes:
        return [
            _res(checks.STATUS_NA, codigo, "sin fuentes de tipo file que verificar")
            for codigo in (CODE_SOURCE_MISSING, CODE_SOURCE_STALE, CODE_SOURCE_UNVERIFIABLE)
        ]
    faltantes: list = []
    stale: list = []
    resultados_unv: list = []
    for s in fuentes:
        ruta = s.get("path")
        if not _ruta_segura(ruta):
            resultados_unv.append(_res(
                checks.STATUS_FAIL, CODE_SOURCE_UNVERIFIABLE,
                "no verificable: path de fuente inseguro o inválido, no se abrió", tecnico=True,
            ))
            continue
        # Acceso ANTES de cualquier stat/hash: una fuente denegada no se abre ni se declara stale.
        permitido, motivo = evidence.read_allowed(repo, _unir(repo, ruta))
        if not permitido:
            resultados_unv.append(_res(
                checks.STATUS_FAIL, CODE_SOURCE_UNVERIFIABLE,
                "no verificable: acceso denegado, no se abrió", ruta, tecnico=True, detail=motivo,
            ))
            continue
        if not os.path.lexists(_unir(repo, ruta)):
            faltantes.append((f"la fuente {ruta!r} no existe", ruta))
            continue
        try:
            actual = evidence.describe_source(repo, ruta)
        except evidence.EvidenceError as exc:
            if str(exc).startswith("acceso denegado"):
                resultados_unv.append(_res(
                    checks.STATUS_FAIL, CODE_SOURCE_UNVERIFIABLE,
                    "no verificable: acceso denegado, no se abrió", ruta, tecnico=True,
                ))
            else:
                faltantes.append((f"fuente ilegible o fuera del repo: {exc}", ruta))
            continue
        esperado = s.get("sha256")
        if not isinstance(esperado, str) or actual["sha256"] != esperado.lower():
            stale.append((f"la fuente {ruta!r} cambió desde que se generó el reporte (sha256 distinto)", ruta))
    if not resultados_unv:
        resultados_unv = [_res(checks.STATUS_PASS, CODE_SOURCE_UNVERIFIABLE, "Todas las fuentes file eran legibles.")]
    return (
        _resumir(CODE_SOURCE_MISSING, faltantes, "Todas las fuentes file existen.")
        + _resumir(CODE_SOURCE_STALE, stale, "Ninguna fuente file cambió desde la generación.")
        + resultados_unv
    )


def _paso_contenido(estado: dict, scientific_policy: Any, incluir_eda: bool) -> list:
    manifest = estado["manifest"]
    if "report_error" in estado:
        return [
            _res(
                checks.STATUS_FAIL, CODE_LOAD,
                f"no se pudo cargar el reporte desde disco: {estado['report_error']}", tecnico=True,
            )
        ] + validate_manifest(manifest, None)
    report = estado["report"]
    return _validar_report(report, scientific_policy, incluir_eda) + validate_manifest(manifest, report)


def _paso_gobernanza(repo: Path, out: Path, manifest: dict) -> list:
    sens = manifest.get("sensitivity")
    lista = sens.get("sensitive_artifacts") if isinstance(sens, dict) else None
    ctx = governance.GovernanceContext(
        repo_root=repo,
        report_id=manifest.get("report_id"),
        report_kind=manifest.get("report_kind"),
        decision_scope=manifest.get("decision_scope"),
        out_dir=_out_para_governance(repo, out),
        sources=tuple(s["path"] for s in _fuentes_file(manifest) if isinstance(s.get("path"), str)),
        holdout_access=manifest.get("holdout_access"),
        data_cutoff=manifest.get("data_cutoff"),
        sensitive_artifacts=tuple(lista) if isinstance(lista, list) else (),
    )
    return governance.evaluate_governance(ctx)


def _paso_aislamiento(repo: Path, manifest: dict, previos: list) -> list:
    scope = manifest.get("decision_scope")
    if scope not in _SCOPES_FLUJO_MODELO:
        return [
            _res(checks.STATUS_NA, CODE_EXPLORATORY_IN_MODEL_FLOW, "el aislamiento aplica solo a model_valid/operational")
        ]
    inputs = [s["path"] for s in _fuentes_file(manifest) if isinstance(s.get("path"), str)]
    indice = evidence.exploratory_index_status(repo)  # una sola vez; el WARN de ilegibles se propaga
    por_hash = evidence.check_inputs_hash_isolation(repo, scope, inputs, index=indice)
    agregados = [
        r
        for r in list(previos) + por_hash
        if r.status == checks.STATUS_FAIL
        and r.kind == checks.KIND_CHECK
        and r.code in (governance.CODE_ISOLATION_INPUT, evidence.CODE_ISOLATION_HASH)
    ]
    if agregados:
        detalle = "; ".join(f"{r.code}: {r.subject or r.message}" for r in agregados)
        agregado = _res(
            checks.STATUS_FAIL, CODE_EXPLORATORY_IN_MODEL_FLOW,
            f"un output exploratory alimenta un flujo {scope!r} ({len(agregados)} hallazgo(s))", detail=detalle,
        )
    else:
        agregado = _res(
            checks.STATUS_PASS, CODE_EXPLORATORY_IN_MODEL_FLOW,
            "Sin señales de origen exploratory en las fuentes (ruta, manifest o hash; no cubre derivados).",
        )
    return por_hash + [agregado]


def _validar_dir(repo_root: Any, out_dir: Any) -> list:
    repo = Path(repo_root).resolve()
    out = _resolver_out(repo, out_dir)
    estado: dict = {}

    resultados = _ejecutar([("REPORT-MANIFEST", _leer_manifest, (repo, out, estado))])
    manifest = estado.get("manifest")
    if manifest is None:  # (1) sin manifest legible: corta
        return resultados
    resultados += _ejecutar([(CODE_LOAD, _construir_report, (estado,))])

    resultados += _ejecutar(
        [
            ("REPORT-ARTIFACT", _paso_artefactos, (repo, out, manifest, estado.get("files", {}), estado.get("report"))),
            ("REPORT-SOURCE", _paso_fuentes, (repo, manifest)),
            (CODE_SCI_POLICY, _cargar_policy, (repo, estado)),
        ]
    )
    resultados += _ejecutar(
        [(CODE_LOAD, _paso_contenido, (estado, estado.get("policy"), estado.get("policy_ok", False)))]
    )
    gobernanza = _ejecutar([("REPORT-GOVERNANCE", _paso_gobernanza, (repo, out, manifest))])
    resultados += gobernanza
    resultados += _ejecutar([("REPORT-ISOLATION", _paso_aislamiento, (repo, manifest, gobernanza))])
    return resultados


def validate_report_dir(repo_root: Any, out_dir: Any) -> list:
    """Puerta completa sobre un directorio de reporte (solo lectura). Orden:
    manifest -> integridad de artefactos y conjunto -> fuentes -> contenido ->
    governance -> aislamiento por hash. `out_dir` relativo se interpreta contra
    `repo_root`. Ningun archivo se abre sin `read_allowed` previo. Nunca lanza."""
    try:
        return _validar_dir(repo_root, out_dir)
    except Exception as exc:  # noqa: BLE001 -- contrato: nunca lanza
        return [_excepcion(CODE_DIR, exc)]
