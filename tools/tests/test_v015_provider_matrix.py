"""Tests de la matriz de soporte de providers (v0.15 Change 2, R1, R3, R4).

Anclan `docs/providers.md` a `SOPORTE_DECLARADO`: la doc y el codigo coinciden y
ningun provider se declara por encima de `contract-tested` sin un registro de
evidencia (provider, nivel). Solo parsean markdown y comparan con la tabla
declarada: no invocan ninguna CLI real, asi que no dependen de que `claude`
exista en el host ni del sistema operativo.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from tools.providers import PROVIDER_REGISTRY
from tools.providers.conformance import NIVELES_SOPORTE, SOPORTE_DECLARADO

RAIZ = Path(__file__).resolve().parents[2]
RUTA_DOC = RAIZ / "docs" / "providers.md"

NIVEL_BASE = "contract-tested"
CAMPOS_EVIDENCIA = ("provider", "nivel", "fecha", "os", "cli_version", "comando", "resultado")


def _limpiar(celda: str) -> str:
    return celda.strip().strip("`").strip()


def _seccion(texto: str, titulo: str) -> str:
    """Cuerpo de la seccion `## titulo` hasta el siguiente `## ` (no corta en `###`)."""
    m = re.search(rf"^## {re.escape(titulo)}\s*\n(.*?)(?=^## |\Z)", texto, re.MULTILINE | re.DOTALL)
    if m is None:
        raise AssertionError(f"falta la seccion '## {titulo}' en docs/providers.md")
    return m.group(1)


def _filas_tabla(seccion: str) -> list:
    """Primera tabla markdown de la seccion: lista de dicts encabezado -> celda limpia."""
    lineas = [ln.strip() for ln in seccion.splitlines() if ln.strip().startswith("|")]
    if len(lineas) < 3:
        raise AssertionError("tabla ausente o sin filas")
    encabezados = [_limpiar(c) for c in lineas[0].strip("|").split("|")]
    filas = []
    for ln in lineas[2:]:  # salta encabezado y separador
        celdas = [_limpiar(c) for c in ln.strip("|").split("|")]
        if len(celdas) != len(encabezados):
            raise AssertionError(f"fila con {len(celdas)} celdas, se esperaban {len(encabezados)}: {ln}")
        filas.append(dict(zip(encabezados, celdas)))
    return filas


def _leer_doc() -> str:
    assert RUTA_DOC.is_file(), f"falta {RUTA_DOC}"
    return RUTA_DOC.read_text(encoding="utf-8")


def niveles_doc(texto: str) -> dict:
    return {f["provider"]: f["nivel_declarado"] for f in _filas_tabla(_seccion(texto, "Matriz de soporte"))}


def registros_doc(texto: str) -> list:
    return _filas_tabla(_seccion(texto, "Registro de evidencia live"))


def sobreventas(soporte: dict, registros: list) -> list:
    """Providers declarados por encima de `contract-tested` sin registro (provider, nivel)."""
    respaldados = {(r["provider"], r["nivel"]) for r in registros}
    problemas = []
    for provider_id, entrada in soporte.items():
        nivel = entrada["nivel_declarado"]
        if NIVELES_SOPORTE.index(nivel) > NIVELES_SOPORTE.index(NIVEL_BASE):
            if (provider_id, nivel) not in respaldados:
                problemas.append(f"{provider_id}: {nivel} sin registro de evidencia")
    return problemas


class TestMatrizCoincideConCodigo(unittest.TestCase):
    def test_tabla_de_la_doc_coincide_con_soporte_declarado(self):
        doc = niveles_doc(_leer_doc())
        self.assertEqual(set(doc), set(SOPORTE_DECLARADO))
        self.assertEqual(set(doc), set(PROVIDER_REGISTRY))
        for provider_id, entrada in SOPORTE_DECLARADO.items():
            with self.subTest(provider=provider_id):
                self.assertEqual(doc[provider_id], entrada["nivel_declarado"])

    def test_niveles_de_la_doc_son_validos(self):
        for provider_id, nivel in niveles_doc(_leer_doc()).items():
            self.assertIn(nivel, NIVELES_SOPORTE, provider_id)

    def test_columnas_de_niveles_coinciden_con_el_registro_de_evidencia(self):
        texto = _leer_doc()
        filas = _filas_tabla(_seccion(texto, "Matriz de soporte"))
        registros = registros_doc(texto)
        smoke_o_mas = NIVELES_SOPORTE.index("locally-smoke-tested")
        for fila in filas:
            provider_id = fila["provider"]
            col_detected = next(v for k, v in fila.items() if k.startswith("detected"))
            col_smoke = next(v for k, v in fila.items() if k.startswith("smoke-tested"))
            col_live = fila["live-validated"]
            with self.subTest(provider=provider_id):
                self.assertTrue(col_detected.startswith("si"))
                self.assertTrue(fila["contract-tested"].startswith("si"))
                hay_live = (provider_id, "live-validated") in {(r["provider"], r["nivel"]) for r in registros}
                hay_smoke = any(
                    r["provider"] == provider_id and NIVELES_SOPORTE.index(r["nivel"]) >= smoke_o_mas
                    for r in registros
                )
                self.assertEqual(col_live.startswith("si"), hay_live)
                self.assertEqual(col_smoke.startswith("si"), hay_smoke)
                if provider_id in ("codex", "gemini", "grok"):
                    self.assertTrue(col_smoke.startswith("no"))
                    self.assertTrue(col_live.startswith("no"))

    def test_antigravity_no_es_adapter_y_la_doc_lo_aclara(self):
        self.assertNotIn("antigravity", PROVIDER_REGISTRY)
        self.assertIn("antigravity", _leer_doc().lower())


class TestRegistroDeEvidencia(unittest.TestCase):
    def test_registros_tienen_los_campos_obligatorios(self):
        registros = registros_doc(_leer_doc())
        self.assertTrue(registros)
        for registro in registros:
            for campo in CAMPOS_EVIDENCIA:
                with self.subTest(provider=registro.get("provider"), campo=campo):
                    self.assertTrue(registro.get(campo, "").strip())
            self.assertRegex(registro["fecha"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertIn(registro["nivel"], NIVELES_SOPORTE)

    def test_todo_nivel_declarado_sobre_contract_tested_tiene_registro(self):
        self.assertEqual(sobreventas(SOPORTE_DECLARADO, registros_doc(_leer_doc())), [])

    def test_claude_code_live_validated_con_registro_de_host_unico(self):
        registros = registros_doc(_leer_doc())
        coincidentes = [r for r in registros if (r["provider"], r["nivel"]) == ("claude_code", "live-validated")]
        self.assertEqual(len(coincidentes), 1)
        self.assertEqual(coincidentes[0]["fecha"], "2026-10-26")
        self.assertIn("HARMESSI_LIVE_PROVIDER=1", coincidentes[0]["comando"])
        self.assertIn("host unico", _leer_doc())

    def test_doc_no_declara_live_validated_para_codex_gemini_grok(self):
        texto = _leer_doc()
        niveles = niveles_doc(texto)
        registros = registros_doc(texto)
        for provider_id in ("codex", "gemini", "grok"):
            with self.subTest(provider=provider_id):
                self.assertEqual(niveles[provider_id], NIVEL_BASE)
                self.assertFalse([r for r in registros if r["provider"] == provider_id])

    def test_negativo_sobreventa_sintetica_sin_registro_se_detecta(self):
        soporte = {
            "codex": {"nivel_declarado": "live-validated"},
            "grok": {"nivel_declarado": "locally-smoke-tested"},
            "gemini": {"nivel_declarado": NIVEL_BASE},
        }
        registros = [
            {"provider": "grok", "nivel": "live-validated"},  # nivel distinto: no respalda
        ]
        problemas = sobreventas(soporte, registros)
        self.assertEqual(len(problemas), 2)
        self.assertTrue(any(p.startswith("codex") for p in problemas))
        self.assertTrue(any(p.startswith("grok") for p in problemas))

    def test_positivo_sintetico_con_registro_coincidente_no_falla(self):
        soporte = {"codex": {"nivel_declarado": "live-validated"}}
        registros = [{"provider": "codex", "nivel": "live-validated"}]
        self.assertEqual(sobreventas(soporte, registros), [])


if __name__ == "__main__":
    unittest.main()
