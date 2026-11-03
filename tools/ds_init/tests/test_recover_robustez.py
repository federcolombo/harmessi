"""Robustez de `recover` y del journal (reviewer ciclo 1 de Change 5): fase
`aplicando` persistida antes del primer movimiento (M1), backup ausente como
fallo (M2), detección de ediciones posteriores y `--forzar` (M3), validación
de rutas del journal (M4), journal atómico (M5), residuo limpiable (B2) y
`migrate-hashes --execute` con lock y abort ante huérfanos (B4)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.ds_init import recover as recover_mod
from tools.ds_init import writer
from tools.ds_init.tests.test_upgrade import _BaseUpgrade, _correr, _hashes_arbol

_FALLO_ROLLBACK = [{"destino": "simulado", "error": "proceso muerto"}]


class TestRecoverRobustez(_BaseUpgrade):
    def recover(self, *extra):
        return _correr(["recover", "--destino", str(self.repo), *extra])

    def dir_journal(self) -> Path:
        return next((self.repo / ".ds_init" / "journal").iterdir())

    def interrumpir_aplicando(self, fases_vistas: list = None) -> None:
        """Corta `upgrade --execute` justo después del primer `os.replace` de
        aplicación, sin rollback automático."""
        real = os.replace
        cuenta = {"n": 0}

        def _replace(origen, destino):
            cuenta["n"] += 1
            if cuenta["n"] == 1 and fases_vistas is not None:
                datos = json.loads((self.dir_journal() / "journal.json").read_text(encoding="utf-8"))
                fases_vistas.append(datos["fase"])
            if cuenta["n"] == 2:
                raise OSError("corte simulado")
            return real(origen, destino)

        with mock.patch.object(writer, "_revertir_journal", return_value=_FALLO_ROLLBACK), mock.patch(
            "os.replace", _replace
        ):
            codigo, _out, _err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 1)

    # M1
    def test_fase_aplicando_persistida_antes_del_primer_replace(self):
        self.simular_v010()
        antes = _hashes_arbol(self.repo)
        fases = []
        self.interrumpir_aplicando(fases)
        self.assertEqual(fases, ["aplicando"])
        codigo, _out, err = self.recover("--execute")
        self.assertEqual(codigo, 0, err)
        self.assertEqual(antes, _hashes_arbol(self.repo))

    # M2
    def test_revertir_journal_falla_si_falta_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino, journal = Path(tmp) / "d", Path(tmp) / "j"
            destino.mkdir()
            journal.mkdir()
            (destino / "a.txt").write_text("nuevo", encoding="utf-8")
            entradas = [{"destino": "a.txt", "accion": writer.ACCION_JOURNAL_REEMPLAZAR_MERGE, "aplicado": True}]
            fallos = writer._revertir_journal(entradas, destino, journal)
            self.assertEqual(len(fallos), 1)
            self.assertIn("backup", fallos[0]["error"])

    def test_recover_vuelve_a_detectar_dentro_del_lock(self):
        self.simular_v010()
        self.interrumpir_aplicando()
        with mock.patch.object(recover_mod, "detectar", wraps=recover_mod.detectar) as espia:
            codigo, _out, err = self.recover("--execute")
        self.assertEqual(codigo, 0, err)
        self.assertEqual(espia.call_count, 2)

    # M3
    def test_edicion_posterior_aborta_y_forzar_conserva_copia(self):
        self.simular_v010()
        antes = _hashes_arbol(self.repo)
        self.interrumpir_aplicando()
        datos = json.loads((self.dir_journal() / "journal.json").read_text(encoding="utf-8"))
        aplicada = next(e for e in datos["entradas"] if e.get("aplicado"))
        rel = aplicada["destino"]
        self.assertIn("sha256_nuevo", aplicada)
        with open(self.repo / rel, "a", encoding="utf-8", newline="") as f:
            f.write("\n# edicion del usuario tras la interrupcion\n")
        editado = _hashes_arbol(self.repo)

        codigo, salida, _err = self.recover()
        self.assertEqual(codigo, 0)
        self.assertIn("AVISO", salida)
        self.assertEqual(editado, _hashes_arbol(self.repo))

        codigo, _out, err = self.recover("--execute")
        self.assertEqual(codigo, 2)
        self.assertIn(rel, err)
        self.assertEqual(editado, _hashes_arbol(self.repo))

        codigo, _out, err = self.recover("--execute", "--forzar")
        self.assertEqual(codigo, 0, err)
        bak = self.repo / (rel + ".recover-bak")
        self.assertTrue(bak.is_file())
        self.assertIn("edicion del usuario", bak.read_text(encoding="utf-8"))
        if rel in antes:
            self.assertEqual(antes[rel], _hashes_arbol(self.repo)[rel])
        else:
            self.assertFalse((self.repo / rel).exists())

    # M4
    def test_rutas_invalidas_del_journal_exit_2(self):
        self.simular_v010()
        invalidas = [
            "../evil.txt",
            "a:b/x.txt",
            ".git/config",
            "/abs/x.txt",
            "tools\\x.py",
            "no/esta/en/el/manifest.txt",
        ]
        antes = _hashes_arbol(self.repo)
        for ruta in invalidas:
            with self.subTest(ruta=ruta):
                d = self.repo / ".ds_init" / "journal" / "20260101T000000000000Z"
                d.mkdir(parents=True)
                (d / "journal.json").write_text(
                    json.dumps(
                        {
                            "fase": "aplicando",
                            "entradas": [{"destino": ruta, "accion": "crear", "aplicado": True}],
                        }
                    ),
                    encoding="utf-8",
                )
                for extra in ((), ("--execute",)):
                    codigo, _out, err = self.recover(*extra)
                    self.assertEqual(codigo, 2)
                    self.assertIn("ruta inválida", err)
                (d / "journal.json").unlink()
                d.rmdir()
                (self.repo / ".ds_init" / "journal").rmdir()
        self.assertEqual(antes, _hashes_arbol(self.repo))

    # M5
    def test_journal_se_escribe_de_forma_atomica(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "j" / "journal.json"
            with mock.patch.object(writer, "_REEMPLAZO_ATOMICO", side_effect=OSError("boom")):
                with self.assertRaises(OSError):
                    writer._escribir_journal(ruta, [], writer.FASE_APLICANDO)
            self.assertFalse(ruta.exists())
            self.assertEqual(list(ruta.parent.iterdir()), [])
            writer._escribir_journal(ruta, [], writer.FASE_APLICANDO)
            self.assertEqual(json.loads(ruta.read_text(encoding="utf-8"))["fase"], "aplicando")

    # B2
    def test_directorio_de_journal_sin_json_es_residuo_limpiable(self):
        d = self.repo / ".ds_init" / "journal" / "20260101T000000000000Z"
        (d / "backups").mkdir(parents=True)
        codigo, salida, _err = self.recover()
        self.assertEqual(codigo, 0)
        self.assertIn("residuo", salida)
        codigo, _out, err = self.recover("--execute")
        self.assertEqual(codigo, 0, err)
        self.assertFalse((self.repo / ".ds_init" / "journal").exists())

    # B4
    def test_migrate_hashes_execute_aborta_con_huerfanos(self):
        (self.repo / ".ds_init_staging_20260101T000000000000Z").mkdir()
        codigo, _out, err = _correr(["migrate-hashes", "--destino", str(self.repo), "--execute"])
        self.assertEqual(codigo, 1)
        self.assertIn("recover", err)

    def test_migrate_hashes_execute_toma_y_libera_el_lock(self):
        codigo, _out, err = _correr(["migrate-hashes", "--destino", str(self.repo), "--execute"])
        self.assertEqual(codigo, 0, err)
        self.assertFalse((self.repo / ".ds_init" / "lock").exists())
        (self.repo / ".ds_init" / "lock").write_text("{}", encoding="utf-8")
        codigo, _out, err = _correr(["migrate-hashes", "--destino", str(self.repo), "--execute"])
        self.assertEqual(codigo, 1)
        self.assertIn("lock", err)


if __name__ == "__main__":
    unittest.main()
