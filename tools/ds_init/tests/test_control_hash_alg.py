"""Tests de hash managed en `tools.ds_init.control` (Change
`20261008-cross-platform-managed-hashing`): `hash_alg` en entradas nuevas,
`clasificar_baseline`, `regenerar_control` (total y conservador) y
`migrar_hashes`. Todo con bytes explícitos en directorios temporales (sin
depender de `core.autocrlf` del host ni de este repositorio)."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tools.ds_init import control as control_mod
from tools.ds_init import managed_hash
from tools.ds_init import manifest as manifest_mod

PERFIL = "python-jupyter-data"
CONFIG = {"nombre": "p", "notebooks_dir": "notebooks", "venv_dir": ".venv"}

# Rutas reales del manifiesto usadas como "archivos administrados" de prueba.
RUTA_A = "tools/ds_guard.py"
RUTA_B = "tools/dsguard/core.py"
RUTA_C = "tools/dsguard/repo.py"
RUTA_D = ".claude/settings.json"
RUTA_E = "tools/dsguard/sdd.py"
RUTA_F = "tools/dsguard/kdd.py"
RUTA_G = "tools/dsguard/checks.py"

LF = b"hello\nworld\n"
CRLF = b"hello\r\nworld\r\n"
MODIFICADO = b"hello\nWORLD\n"


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _sha_canonico(datos: bytes) -> str:
    return _sha(datos.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))


def _escribir(destino: Path, ruta: str, datos: bytes) -> None:
    ruta_absoluta = destino / ruta
    ruta_absoluta.parent.mkdir(parents=True, exist_ok=True)
    ruta_absoluta.write_bytes(datos)


def _entrada_nueva(ruta: str, datos: bytes) -> dict:
    return {"ruta": ruta, "sha256": _sha_canonico(datos), "hash_alg": managed_hash.ALG_TEXTO}


def _entrada_legacy(ruta: str, datos: bytes) -> dict:
    return {"ruta": ruta, "sha256": _sha(datos)}


def _control(archivos: list, **extra) -> dict:
    control = {
        "harness_version": "0.0.0",
        "perfil": PERFIL,
        "fecha_utc": "2026-01-01T00:00:00Z",
        "configuracion": {**CONFIG, "destino": "."},
        "archivos": archivos,
    }
    control.update(extra)
    return control


def _escribir_control(destino: Path, control: dict) -> Path:
    ruta = destino / ".ds_init" / "control.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(control, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="")
    return ruta


def _resultado(aplicados=(), actualizados=(), sin_cambios=(), omitidos=()) -> SimpleNamespace:
    return SimpleNamespace(
        aplicados=list(aplicados),
        actualizados=list(actualizados),
        sin_cambios=list(sin_cambios),
        omitidos=list(omitidos),
    )


class _BaseTmp(unittest.TestCase):
    def setUp(self):
        self.destino = Path(tempfile.mkdtemp(prefix="ds_init_test_hash_alg_"))
        self.addCleanup(shutil.rmtree, self.destino, ignore_errors=True)

    def _por_ruta(self, control: dict) -> dict:
        return {e["ruta"]: e for e in control["archivos"]}


class TestManifestContenido(unittest.TestCase):
    def test_contenido_por_defecto_es_texto(self):
        entrada = manifest_mod.EntradaManifiesto(fuente="x", tratamiento=manifest_mod.VERBATIM, destino="x")
        self.assertEqual(entrada.contenido, "texto")

    def test_contenido_invalido_se_rechaza(self):
        with self.assertRaises(ValueError):
            manifest_mod.EntradaManifiesto(
                fuente="x", tratamiento=manifest_mod.VERBATIM, destino="x", contenido="raro"
            )

    def test_contenido_de_ruta_conocida_y_desconocida(self):
        self.assertEqual(manifest_mod.contenido_de(RUTA_A), "texto")
        self.assertEqual(manifest_mod.contenido_de("ruta/que/no/existe.bin"), "texto")


class TestParidadContenidos(unittest.TestCase):
    def test_contenidos_validos_coinciden_con_managed_hash(self):
        self.assertEqual(
            tuple(manifest_mod.CONTENIDOS_VALIDOS),
            (managed_hash.CONTENIDO_TEXTO, managed_hash.CONTENIDO_BINARIO),
        )


class TestGenerarControlHashAlg(_BaseTmp):
    def test_entrada_binaria_usa_algoritmo_binario_y_no_normaliza_eol(self):
        otro = Path(tempfile.mkdtemp(prefix="ds_init_test_hash_alg_"))
        self.addCleanup(shutil.rmtree, otro, ignore_errors=True)
        _escribir(self.destino, RUTA_A, b"a\r\nb\r\n")
        _escribir(otro, RUTA_A, b"a\nb\n")
        with mock.patch.object(manifest_mod, "contenido_de", return_value="binario"):
            c_crlf = control_mod.generar_control(self.destino, PERFIL, CONFIG, [RUTA_A])
            c_lf = control_mod.generar_control(otro, PERFIL, CONFIG, [RUTA_A])
        self.assertEqual(c_crlf["archivos"][0]["hash_alg"], managed_hash.ALG_BINARIO)
        self.assertEqual(c_crlf["archivos"][0]["sha256"], _sha(b"a\r\nb\r\n"))
        self.assertNotEqual(c_crlf["archivos"][0]["sha256"], c_lf["archivos"][0]["sha256"])

    def test_entradas_nuevas_tienen_hash_alg(self):
        _escribir(self.destino, RUTA_A, LF)
        control = control_mod.generar_control(self.destino, PERFIL, CONFIG, [RUTA_A])
        entrada = control["archivos"][0]
        self.assertEqual(set(entrada), {"ruta", "sha256", "hash_alg"})
        self.assertEqual(entrada["hash_alg"], managed_hash.ALG_TEXTO)
        self.assertNotIn("schema_version", control)

    def test_lf_y_crlf_dan_el_mismo_sha256(self):
        otro = Path(tempfile.mkdtemp(prefix="ds_init_test_hash_alg_"))
        self.addCleanup(shutil.rmtree, otro, ignore_errors=True)
        _escribir(self.destino, RUTA_A, LF)
        _escribir(otro, RUTA_A, CRLF)
        c_lf = control_mod.generar_control(self.destino, PERFIL, CONFIG, [RUTA_A])
        c_crlf = control_mod.generar_control(otro, PERFIL, CONFIG, [RUTA_A])
        self.assertEqual(c_lf["archivos"][0]["sha256"], c_crlf["archivos"][0]["sha256"])
        self.assertEqual(c_lf["archivos"][0]["sha256"], _sha(LF))

    def test_contenido_distinto_da_sha256_distinto(self):
        _escribir(self.destino, RUTA_A, LF)
        _escribir(self.destino, RUTA_B, MODIFICADO)
        control = control_mod.generar_control(self.destino, PERFIL, CONFIG, [RUTA_A, RUTA_B])
        self.assertNotEqual(control["archivos"][0]["sha256"], control["archivos"][1]["sha256"])

    def test_control_escrito_a_disco_es_determinista(self):
        _escribir(self.destino, RUTA_A, LF)
        control_mod.generar_control(self.destino, PERFIL, CONFIG, [RUTA_A], fecha_utc="2026-01-01T00:00:00Z")
        ruta = self.destino / ".ds_init" / "control.json"
        primero = ruta.read_bytes()
        control_mod.generar_control(self.destino, PERFIL, CONFIG, [RUTA_A], fecha_utc="2026-01-01T00:00:00Z")
        self.assertEqual(primero, ruta.read_bytes())
        self.assertTrue(primero.endswith(b"\n"))

    def test_entradas_conservadas_verbatim_y_delta_gana(self):
        _escribir(self.destino, RUTA_A, LF)
        _escribir(self.destino, RUTA_B, LF)
        conservada_b = {"ruta": RUTA_B, "sha256": "f" * 64, "hash_alg": managed_hash.ALG_TEXTO}
        conservada_c = {"ruta": RUTA_C, "sha256": "e" * 64}  # legacy, sin hash_alg, archivo ni existe
        conservada_a = {"ruta": RUTA_A, "sha256": "d" * 64}
        control = control_mod.generar_control(
            self.destino,
            PERFIL,
            CONFIG,
            [RUTA_A],
            entradas_conservadas=[conservada_c, conservada_b, conservada_a, conservada_c],
        )
        self.assertEqual([e["ruta"] for e in control["archivos"]], [RUTA_C, RUTA_B, RUTA_A])
        por_ruta = self._por_ruta(control)
        self.assertEqual(por_ruta[RUTA_C], conservada_c)
        self.assertEqual(por_ruta[RUTA_B], conservada_b)
        # El delta gana sobre la conservada de la misma ruta.
        self.assertEqual(por_ruta[RUTA_A]["sha256"], _sha(LF))
        self.assertEqual(por_ruta[RUTA_A]["hash_alg"], managed_hash.ALG_TEXTO)


class TestClasificarBaseline(_BaseTmp):
    def test_clasifica_ok_legacy_drift_desconocido_y_omite_ausentes(self):
        _escribir(self.destino, RUTA_A, CRLF)  # baseline nuevo sobre CRLF -> ok
        _escribir(self.destino, RUTA_B, CRLF)  # legacy con hash de la forma LF -> ok_legacy
        _escribir(self.destino, RUTA_C, MODIFICADO)  # contenido cambiado -> drift
        _escribir(self.destino, RUTA_E, LF)  # hash_alg desconocido
        previo = _control(
            [
                _entrada_nueva(RUTA_A, LF),
                _entrada_legacy(RUTA_B, LF),
                _entrada_nueva(RUTA_C, LF),
                {"ruta": RUTA_E, "sha256": _sha(LF), "hash_alg": "sha256/futuro/v9"},
                _entrada_nueva(RUTA_F, LF),  # archivo ausente
                "no soy un dict",
                {"sha256": "x"},  # sin ruta
            ]
        )
        clasificacion = control_mod.clasificar_baseline(self.destino, previo)
        self.assertEqual(
            {r: v["estado"] for r, v in clasificacion.items()},
            {
                RUTA_A: managed_hash.ESTADO_OK,
                RUTA_B: managed_hash.ESTADO_OK_LEGACY,
                RUTA_C: managed_hash.ESTADO_DRIFT,
                RUTA_E: managed_hash.ESTADO_ALG_DESCONOCIDO,
            },
        )
        self.assertNotIn(RUTA_F, clasificacion)
        self.assertEqual(clasificacion[RUTA_A]["entrada"], previo["archivos"][0])


class TestRegenerarControlTotal(_BaseTmp):
    def _crear_todos(self):
        rutas = [
            e.destino
            for e in manifest_mod.manifest_para_perfil(PERFIL)
            if e.destino != ".ds_init/control.json"
        ]
        for ruta in rutas:
            _escribir(self.destino, ruta, b"linea 1\r\nlinea 2 " + ruta.encode("utf-8") + b"\r\n")
        return rutas

    def test_rebaseline_total_escribe_hash_alg_y_verifica(self):
        rutas = self._crear_todos()
        previo = _control([{"ruta": "obsoleto.md", "sha256": "0" * 64}])
        nuevo = control_mod.regenerar_control(self.destino, previo)
        self.assertEqual({e["ruta"] for e in nuevo["archivos"]}, set(rutas))
        for entrada in nuevo["archivos"]:
            self.assertEqual(entrada["hash_alg"], managed_hash.ALG_TEXTO)
            estado, detalle = managed_hash.verificar_entrada(self.destino / entrada["ruta"], entrada)
            self.assertEqual(estado, managed_hash.ESTADO_OK, detalle)

    def test_rebaseline_total_rehashea_contenido_modificado(self):
        rutas = self._crear_todos()
        previo = _control([_entrada_nueva(rutas[0], LF)])
        nuevo = control_mod.regenerar_control(self.destino, previo)
        self.assertIn(rutas[0], {e["ruta"] for e in nuevo["archivos"]})

    def test_total_con_archivo_ausente_sigue_fallando_alto(self):
        self._crear_todos()
        (self.destino / RUTA_A).unlink()
        with self.assertRaises(FileNotFoundError):
            control_mod.regenerar_control(self.destino, _control([]))


class TestRegenerarControlConservador(_BaseTmp):
    def _regenerar(self, previo: dict, resultado=None, preexistentes=None) -> dict:
        clasificacion = control_mod.clasificar_baseline(self.destino, previo)
        return control_mod.regenerar_control(
            self.destino,
            previo,
            clasificacion=clasificacion,
            resultado=resultado if resultado is not None else _resultado(),
            preexistentes=preexistentes,
        )

    def test_merge_preexistente_sin_baseline_no_se_adopta(self):
        _escribir(self.destino, RUTA_D, b'{"del": "usuario"}\n')
        nuevo = self._regenerar(
            _control([]), _resultado(aplicados=[RUTA_D]), preexistentes={RUTA_D}
        )
        self.assertNotIn(RUTA_D, self._por_ruta(nuevo))

    def test_archivo_realmente_nuevo_se_hashea_con_preexistentes_dado(self):
        _escribir(self.destino, RUTA_D, b'{"a": 1}\n')
        nuevo = self._regenerar(_control([]), _resultado(aplicados=[RUTA_D]), preexistentes=set())
        self.assertEqual(self._por_ruta(nuevo)[RUTA_D]["sha256"], _sha(b'{"a": 1}\n'))

    def test_preexistente_sin_baseline_pero_sin_cambios_si_se_registra(self):
        _escribir(self.destino, RUTA_B, LF)
        nuevo = self._regenerar(
            _control([]), _resultado(sin_cambios=[RUTA_B]), preexistentes={RUTA_B}
        )
        self.assertIn(RUTA_B, self._por_ruta(nuevo))

    def test_entrada_no_clasificable_se_conserva_verbatim(self):
        # Simula un error de E/S en la clasificacion: la ruta no figura en ella.
        _escribir(self.destino, RUTA_B, LF)
        previa = _entrada_nueva(RUTA_B, LF)
        nuevo = control_mod.regenerar_control(
            self.destino, _control([previa]), clasificacion={}, resultado=_resultado()
        )
        self.assertEqual(self._por_ruta(nuevo)[RUTA_B], previa)

    def test_entrada_sin_sha256_string_se_conserva_verbatim(self):
        malformada = {"ruta": RUTA_C}
        nuevo = self._regenerar(_control([malformada]))
        self.assertEqual(self._por_ruta(nuevo)[RUTA_C], malformada)

    def test_fuera_del_manifiesto_con_drift_se_conserva(self):
        _escribir(self.destino, "otro/archivo.md", MODIFICADO)
        previa = _entrada_nueva("otro/archivo.md", LF)
        nuevo = self._regenerar(_control([previa]))
        self.assertEqual(self._por_ruta(nuevo)["otro/archivo.md"], previa)

    def test_fuera_del_manifiesto_con_algoritmo_desconocido_se_conserva(self):
        _escribir(self.destino, "otro/archivo.md", LF)
        previa = {"ruta": "otro/archivo.md", "sha256": _sha(LF), "hash_alg": "sha256/futuro/v9"}
        nuevo = self._regenerar(_control([previa]))
        self.assertEqual(self._por_ruta(nuevo)["otro/archivo.md"], previa)

    def test_fuera_del_manifiesto_ausente_del_disco_se_descarta(self):
        nuevo = self._regenerar(_control([_entrada_nueva("otro/archivo.md", LF)]))
        self.assertNotIn("otro/archivo.md", self._por_ruta(nuevo))

    def test_drift_se_conserva_sin_rehash(self):
        _escribir(self.destino, RUTA_B, MODIFICADO)
        previa = _entrada_nueva(RUTA_B, LF)
        nuevo = self._regenerar(_control([previa]))
        self.assertEqual(self._por_ruta(nuevo)[RUTA_B], previa)

    def test_algoritmo_desconocido_se_conserva_tal_cual(self):
        _escribir(self.destino, RUTA_B, LF)
        previa = {"ruta": RUTA_B, "sha256": _sha(LF), "hash_alg": "sha256/futuro/v9"}
        nuevo = self._regenerar(_control([previa]))
        self.assertEqual(self._por_ruta(nuevo)[RUTA_B], previa)

    def test_ok_legacy_migra_al_algoritmo_vigente(self):
        _escribir(self.destino, RUTA_F, CRLF)
        nuevo = self._regenerar(_control([_entrada_legacy(RUTA_F, LF)]))
        entrada = self._por_ruta(nuevo)[RUTA_F]
        self.assertEqual(entrada["hash_alg"], managed_hash.ALG_TEXTO)
        self.assertEqual(entrada["sha256"], _sha(LF))

    def test_pristine_ok_se_conserva(self):
        _escribir(self.destino, RUTA_A, CRLF)
        previa = _entrada_nueva(RUTA_A, LF)
        nuevo = self._regenerar(_control([previa]))
        self.assertEqual(self._por_ruta(nuevo)[RUTA_A], previa)

    def test_existente_sin_entrada_previa_no_se_adopta(self):
        _escribir(self.destino, RUTA_E, LF)
        _escribir(self.destino, RUTA_A, LF)
        nuevo = self._regenerar(_control([_entrada_nueva(RUTA_A, LF)]))
        self.assertNotIn(RUTA_E, self._por_ruta(nuevo))
        self.assertIn(RUTA_A, self._por_ruta(nuevo))

    def test_archivo_creado_en_la_corrida_se_hashea(self):
        _escribir(self.destino, RUTA_G, CRLF)
        nuevo = self._regenerar(_control([]), _resultado(aplicados=[RUTA_G]))
        entrada = self._por_ruta(nuevo)[RUTA_G]
        self.assertEqual(entrada["sha256"], _sha(LF))
        self.assertEqual(entrada["hash_alg"], managed_hash.ALG_TEXTO)

    def test_archivo_actualizado_pristine_recibe_hash_del_contenido_nuevo(self):
        _escribir(self.destino, RUTA_B, LF)
        previo = _control([_entrada_nueva(RUTA_B, LF)])
        clasificacion = control_mod.clasificar_baseline(self.destino, previo)  # antes de escribir
        _escribir(self.destino, RUTA_B, MODIFICADO)  # el writer actualiza el archivo
        nuevo = control_mod.regenerar_control(
            self.destino, previo, clasificacion=clasificacion, resultado=_resultado(actualizados=[RUTA_B])
        )
        self.assertEqual(self._por_ruta(nuevo)[RUTA_B]["sha256"], _sha(MODIFICADO))

    def test_merge_con_drift_previo_conserva_entrada_previa(self):
        _escribir(self.destino, RUTA_D, b'{"mi": "config"}\n')
        previa = _entrada_nueva(RUTA_D, b'{"original": true}\n')
        nuevo = self._regenerar(_control([previa]), _resultado(aplicados=[RUTA_D]))
        self.assertEqual(self._por_ruta(nuevo)[RUTA_D], previa)

    def test_merge_sin_entrada_previa_se_registra(self):
        _escribir(self.destino, RUTA_D, b'{"a": 1}\n')
        nuevo = self._regenerar(_control([]), _resultado(aplicados=[RUTA_D]))
        self.assertEqual(self._por_ruta(nuevo)[RUTA_D]["sha256"], _sha(b'{"a": 1}\n'))

    def test_sin_cambios_migra_con_hash_nuevo(self):
        _escribir(self.destino, RUTA_B, CRLF)
        nuevo = self._regenerar(_control([_entrada_legacy(RUTA_B, LF)]), _resultado(sin_cambios=[RUTA_B]))
        entrada = self._por_ruta(nuevo)[RUTA_B]
        self.assertEqual(entrada["hash_alg"], managed_hash.ALG_TEXTO)
        self.assertEqual(entrada["sha256"], _sha(LF))

    def test_ruta_ausente_del_disco_no_se_incluye(self):
        nuevo = self._regenerar(_control([_entrada_nueva(RUTA_C, LF)]))
        self.assertNotIn(RUTA_C, self._por_ruta(nuevo))

    def test_entradas_fuera_del_manifiesto_quedan_ausentes(self):
        _escribir(self.destino, "otro/archivo.md", LF)
        nuevo = self._regenerar(_control([_entrada_nueva("otro/archivo.md", LF)]))
        self.assertNotIn("otro/archivo.md", self._por_ruta(nuevo))

    def test_control_en_disco_conserva_las_entradas(self):
        _escribir(self.destino, RUTA_B, MODIFICADO)
        previa = _entrada_nueva(RUTA_B, LF)
        self._regenerar(_control([previa]))
        en_disco = json.loads((self.destino / ".ds_init" / "control.json").read_text(encoding="utf-8"))
        self.assertEqual(self._por_ruta(en_disco)[RUTA_B], previa)
        self.assertEqual(en_disco["fecha_utc"], "2026-01-01T00:00:00Z")


class TestMigrarHashes(_BaseTmp):
    def _leer_control(self) -> dict:
        return json.loads((self.destino / ".ds_init" / "control.json").read_text(encoding="utf-8"))

    def _armar(self) -> bytes:
        _escribir(self.destino, RUTA_A, CRLF)  # legacy verificable (hash de forma LF)
        _escribir(self.destino, RUTA_B, MODIFICADO)  # legacy con contenido modificado
        _escribir(self.destino, RUTA_C, LF)  # ya actual
        _escribir(self.destino, RUTA_E, LF)  # hash_alg desconocido
        ruta = _escribir_control(
            self.destino,
            _control(
                [
                    _entrada_legacy(RUTA_A, LF),
                    _entrada_legacy(RUTA_B, LF),
                    _entrada_nueva(RUTA_C, LF),
                    {"ruta": RUTA_E, "sha256": _sha(LF), "hash_alg": "sha256/futuro/v9"},
                ],
                installation_stage="experiment",
            ),
        )
        return ruta.read_bytes()

    def test_dry_run_no_escribe(self):
        antes = self._armar()
        informe = control_mod.migrar_hashes(self.destino)
        self.assertEqual(antes, (self.destino / ".ds_init" / "control.json").read_bytes())
        self.assertEqual(informe.migradas, [RUTA_A])
        self.assertEqual(informe.no_verificables, [RUTA_B])
        self.assertEqual(informe.ya_actuales, [RUTA_C])
        self.assertEqual(informe.desconocidas, [RUTA_E])

    def test_execute_migra_solo_verificables(self):
        self._armar()
        antes = self._leer_control()
        informe = control_mod.migrar_hashes(self.destino, ejecutar=True)
        despues = self._leer_control()
        self.assertEqual(informe.migradas, [RUTA_A])

        por_ruta = self._por_ruta(despues)
        self.assertEqual(por_ruta[RUTA_A]["hash_alg"], managed_hash.ALG_TEXTO)
        self.assertEqual(por_ruta[RUTA_A]["sha256"], _sha(LF))
        estado, detalle = managed_hash.verificar_entrada(self.destino / RUTA_A, por_ruta[RUTA_A])
        self.assertEqual(estado, managed_hash.ESTADO_OK, detalle)

        # Modificado y desconocido quedan intactos; el drift persiste.
        previas = self._por_ruta(antes)
        self.assertEqual(por_ruta[RUTA_B], previas[RUTA_B])
        self.assertNotIn("hash_alg", por_ruta[RUTA_B])
        self.assertEqual(por_ruta[RUTA_E], previas[RUTA_E])
        self.assertEqual(por_ruta[RUTA_C], previas[RUTA_C])

        # Resto de claves y orden de entradas preservados.
        self.assertEqual(despues["installation_stage"], "experiment")
        self.assertEqual(despues["fecha_utc"], antes["fecha_utc"])
        self.assertEqual([e["ruta"] for e in despues["archivos"]], [e["ruta"] for e in antes["archivos"]])

    def test_execute_es_idempotente(self):
        self._armar()
        control_mod.migrar_hashes(self.destino, ejecutar=True)
        tras_primera = (self.destino / ".ds_init" / "control.json").read_bytes()
        informe = control_mod.migrar_hashes(self.destino, ejecutar=True)
        self.assertEqual(informe.migradas, [])
        self.assertIn(RUTA_A, informe.ya_actuales)
        self.assertEqual(tras_primera, (self.destino / ".ds_init" / "control.json").read_bytes())

    def test_archivo_ausente_es_no_verificable(self):
        _escribir_control(self.destino, _control([_entrada_legacy(RUTA_A, LF)]))
        informe = control_mod.migrar_hashes(self.destino, ejecutar=True)
        self.assertEqual(informe.no_verificables, [RUTA_A])
        self.assertEqual(informe.migradas, [])

    def test_sin_control_levanta_error_claro(self):
        with self.assertRaises(FileNotFoundError):
            control_mod.migrar_hashes(self.destino)


if __name__ == "__main__":
    unittest.main()
