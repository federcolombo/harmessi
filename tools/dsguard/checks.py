"""Motor neutral de checks (Change 4, v0.3): vocabulario canónico
PASS/WARN/FAIL/N-A, reutilizable por cualquier consumidor futuro
(readiness, promotion) sin conocer CRISP-DM/project_stage/risk_level/MLOps
ni Doctor específicamente.

Principio: "check everything, report everything" -- nunca frena ante un
FAIL, nunca deja escapar una excepción inesperada de un check individual.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

STATUS_PASS = "PASS"
STATUS_WARN = "WARN"
STATUS_FAIL = "FAIL"
STATUS_NA = "N/A"
_STATUS_VALIDOS = frozenset({STATUS_PASS, STATUS_WARN, STATUS_FAIL, STATUS_NA})

KIND_CHECK = "check"
KIND_TECHNICAL_ERROR = "technical_error"
_KINDS_VALIDOS = frozenset({KIND_CHECK, KIND_TECHNICAL_ERROR})


@dataclass(frozen=True)
class CheckResult:
    """Resultado de un check individual. `message` es obligatorio siempre
    (no solo para N/A -- una sola regla sin casos especiales). `kind`
    distingue un FAIL funcional (`"check"`, default) de un error técnico
    inesperado capturado por `ejecutar_checks` (`"technical_error"`) --
    ambos bloquean igual, `kind` es metadata de diagnóstico, no cambia la
    semántica de bloqueo (ver design.md del change)."""

    status: str
    code: str
    message: str
    detail: Optional[str] = None
    subject: Optional[str] = None
    kind: str = KIND_CHECK

    def __post_init__(self) -> None:
        if self.status not in _STATUS_VALIDOS:
            raise ValueError(f"status inválido: {self.status!r} (válidos: {sorted(_STATUS_VALIDOS)})")
        if not self.message:
            raise ValueError("'message' es obligatorio (no puede estar vacío)")
        if self.kind not in _KINDS_VALIDOS:
            raise ValueError(f"kind inválido: {self.kind!r} (válidos: {sorted(_KINDS_VALIDOS)})")

    def to_dict(self) -> dict:
        d = {"status": self.status, "code": self.code, "message": self.message, "kind": self.kind}
        if self.detail:
            d["detail"] = self.detail
        if self.subject:
            d["subject"] = self.subject
        return d


def resultado_de_excepcion(codigo_base: str, exc: Exception) -> CheckResult:
    """CheckResult FAIL/technical_error para una excepción inesperada
    capturada al correr un check -- mismo formato de mensaje que ya usaba
    `doctor._ejecutar_check` en v0.2, ahora centralizado acá para que
    cualquier llamador (`ejecutar_checks`, o un caller doctor-local como
    `_ejecutar_check_con_dato`) lo reuse sin duplicar el texto."""
    return CheckResult(
        STATUS_FAIL,
        f"{codigo_base}-EXCEPCION",
        f"Fallo inesperado ejecutando el check: {exc!r}",
        kind=KIND_TECHNICAL_ERROR,
    )


def ejecutar_checks(registros: list) -> list:
    """registros: [(codigo_base, funcion, args_tuple), ...]. Corre cada
    `funcion(*args_tuple)` (debe devolver `list[CheckResult]`), nunca
    frena: una excepción inesperada de un check no impide correr los
    siguientes, se convierte en `resultado_de_excepcion(...)` en su lugar.
    Preserva el orden de `registros` y el orden interno de cada resultado."""
    resultados: list = []
    for codigo_base, funcion, args in registros:
        try:
            resultados.extend(funcion(*args))
        except Exception as exc:  # noqa: BLE001 - nunca debe escapar de un check individual
            resultados.append(resultado_de_excepcion(codigo_base, exc))
    return resultados


def contar_por_status(resultados: list) -> dict:
    conteos = {STATUS_PASS: 0, STATUS_WARN: 0, STATUS_FAIL: 0, STATUS_NA: 0}
    for r in resultados:
        conteos[r.status] = conteos.get(r.status, 0) + 1
    return conteos


def hay_bloqueo(resultados: list) -> bool:
    return any(r.status == STATUS_FAIL for r in resultados)


def exit_code(resultados: list) -> int:
    return 1 if hay_bloqueo(resultados) else 0


def filtrar_por_status(resultados: list, status: str) -> list:
    return [r for r in resultados if r.status == status]
