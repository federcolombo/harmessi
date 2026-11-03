"""Fakes de tests de probe: adapter determinista y suite temporal mínima."""
from __future__ import annotations

import json
from pathlib import Path

from tools.providers.core import InvocationResult

MARCA_BASE = "MARCA-BASE"
MARCA_CAND = "MARCA-CAND"


class FakeAdapter:
    """Duck-type de ProviderAdapter. La salida depende de qué marcador de guía contiene el
    prompt: MARCA-CAND => `salida_cand`; en otro caso => `salida_base`.
    `fallos = {"base"|"cand": [n_fallos_restantes, availability_error_o_None]}`."""

    provider_id = "fake"
    display_name = "Fake"
    cli_command = "fake"

    def __init__(self, salida_base: str = "", salida_cand: str = "", fallos=None) -> None:
        self.salida_base = salida_base
        self.salida_cand = salida_cand
        self.fallos = {k: list(v) for k, v in (fallos or {}).items()}
        self.invocaciones = 0
        self.prompts: list = []

    def detect(self):
        return None

    def invoke(self, request) -> InvocationResult:
        self.invocaciones += 1
        self.prompts.append(request.prompt)
        rol = "cand" if MARCA_CAND in request.prompt else "base"
        falla = self.fallos.get(rol)
        if falla and falla[0] > 0:
            falla[0] -= 1
            return InvocationResult("fake", 1, "", "fallo simulado", False, falla[1], 0.01)
        salida = self.salida_cand if rol == "cand" else self.salida_base
        return InvocationResult("fake", 0, salida, "", True, None, 0.01)


def crear_suite(directorio: Path, suite_id: str = "suite-fake", n: int = 3, sufijo: str = "") -> Path:
    """Escribe `<suite_id>.suite.json` y `<suite_id>.cases.json` en `directorio` (n casos con
    scorer contains `tok-<i>`). Devuelve la ruta del manifest de suite."""
    directorio = Path(directorio)
    directorio.mkdir(parents=True, exist_ok=True)
    escenarios = [
        {"scenario_id": f"caso-{i}", "prompt": f"Caso {i}{sufijo}: respondé.", "category": "sintetico",
         "tags": [], "expected": {"tipo": "contains", "valores": [f"tok-{i}"]}}
        for i in range(1, n + 1)
    ]
    (directorio / f"{suite_id}.cases.json").write_text(
        json.dumps({"case_contract_version": 1, "escenarios": escenarios}, ensure_ascii=False), encoding="utf-8")
    ruta = directorio / f"{suite_id}.suite.json"
    ruta.write_text(json.dumps({
        "suite_contract_version": 1, "suite_id": suite_id, "suite_version": 1,
        "cases_file": f"{suite_id}.cases.json", "case_ids": [e["scenario_id"] for e in escenarios],
    }), encoding="utf-8")
    return ruta
