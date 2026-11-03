"""Política congelada de un probe (v0.14 Change 2, R1-R2).

Por qué existe: el criterio con el que se interpretará la evidencia de un probe debe
fijarse ANTES de ejecutarlo y no poder cambiar después (si no, se podría elegir el criterio
mirando el resultado). `ProbePolicy` es inmutable (dataclass congelada) y su hash
determinista se persiste en `probe.json`. Este módulo solo valida y serializa: no ejecuta
nada ni decide candidates (la decisión es del Change 3).
Solo stdlib; sin red ni subprocess.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Tuple

POLICY_VERSION = 1

PRIMARIOS = ("passed",)
# duration_s no es determinista (depende del reloj/máquina): no es un criterio admisible.
SECUNDARIOS_VALIDOS = ("mean_score",)
MIN_SCENARIOS_DEFAULT = 3
TIE_POLICIES = ("equivalent", "secondary", "inconclusive")
REPEATS_MIN = 1
REPEATS_MAX = 3

_CLAVES_DICT = (
    "policy_version", "primary", "secondary", "tie_policy", "repeats", "min_stable_ratio", "min_delta",
    "min_scenarios",
)


class PolicyInvalida(ValueError):
    """La política de probe no cumple las reglas de R1."""


def _es_numero(valor) -> bool:
    if not isinstance(valor, (int, float)) or isinstance(valor, bool):
        return False
    try:
        return math.isfinite(valor)
    except OverflowError:  # int gigante que no cabe en float
        return False


@dataclass(frozen=True)
class ProbePolicy:
    """Criterio congelado de un probe. `secondary` se normaliza a tupla ordenada."""

    primary: str = "passed"
    secondary: Tuple[str, ...] = ()
    tie_policy: str = "equivalent"
    repeats: int = 1
    min_stable_ratio: float = 1.0
    min_delta: float = 0.0
    min_scenarios: int = MIN_SCENARIOS_DEFAULT

    def __post_init__(self) -> None:
        if self.primary not in PRIMARIOS or not isinstance(self.primary, str):
            raise PolicyInvalida(f"primary debe ser uno de {PRIMARIOS}")
        sec = self.secondary
        if isinstance(sec, (str, bytes)) or not isinstance(sec, (list, tuple, set, frozenset)):
            raise PolicyInvalida("secondary debe ser una colección de métricas")
        sec = list(sec)
        if not all(isinstance(s, str) and s in SECUNDARIOS_VALIDOS for s in sec):
            raise PolicyInvalida(f"secondary solo admite {SECUNDARIOS_VALIDOS}")
        if len(set(sec)) != len(sec):
            raise PolicyInvalida("secondary con duplicados")
        object.__setattr__(self, "secondary", tuple(sec))  # orden declarado, tal cual
        if not isinstance(self.tie_policy, str) or self.tie_policy not in TIE_POLICIES:
            raise PolicyInvalida(f"tie_policy debe ser uno de {TIE_POLICIES}")
        if isinstance(self.repeats, bool) or not isinstance(self.repeats, int) \
                or not REPEATS_MIN <= self.repeats <= REPEATS_MAX:
            raise PolicyInvalida(f"repeats debe ser un entero entre {REPEATS_MIN} y {REPEATS_MAX}")
        if not _es_numero(self.min_stable_ratio) or not 0 < self.min_stable_ratio <= 1:
            raise PolicyInvalida("min_stable_ratio debe estar en (0, 1]")
        if not _es_numero(self.min_delta) or self.min_delta < 0:
            raise PolicyInvalida("min_delta debe ser un número >= 0")
        if self.tie_policy == "secondary" and self.min_delta <= 0:
            raise PolicyInvalida("tie_policy='secondary' exige min_delta > 0")
        if isinstance(self.min_scenarios, bool) or not isinstance(self.min_scenarios, int) \
                or self.min_scenarios < 1:
            raise PolicyInvalida("min_scenarios debe ser un entero >= 1")

    def a_dict(self) -> dict:
        return {
            "policy_version": POLICY_VERSION,
            "primary": self.primary,
            "secondary": list(self.secondary),
            "tie_policy": self.tie_policy,
            "repeats": self.repeats,
            "min_stable_ratio": float(self.min_stable_ratio),
            "min_delta": float(self.min_delta),
            "min_scenarios": self.min_scenarios,
        }

    @classmethod
    def desde_dict(cls, datos) -> "ProbePolicy":
        """Valida claves, versión y valores; `PolicyInvalida` si algo no cuadra."""
        if not isinstance(datos, dict) or set(datos) != set(_CLAVES_DICT):
            raise PolicyInvalida("policy: claves inesperadas")
        version = datos["policy_version"]
        if isinstance(version, bool) or version != POLICY_VERSION:
            raise PolicyInvalida("policy_version no soportada")
        return cls(
            primary=datos["primary"], secondary=datos["secondary"], tie_policy=datos["tie_policy"],
            repeats=datos["repeats"], min_stable_ratio=datos["min_stable_ratio"],
            min_delta=datos["min_delta"], min_scenarios=datos["min_scenarios"],
        )


def hash_policy(policy: ProbePolicy) -> str:
    """sha256 del JSON canónico de la política (determinista, independiente del orden)."""
    if not isinstance(policy, ProbePolicy):
        raise PolicyInvalida("hash_policy requiere una ProbePolicy")
    texto = json.dumps(policy.a_dict(), sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()
