"""Tests de `tools.ds_init.writer` (Sesión 2): instalación real sobre un
repositorio Git temporal propio (nunca este repositorio, R14/AC15).

Cubre: instalación exitosa (staging se limpia, archivos quedan en destino),
colisión con archivo existente (se omite, no se sobrescribe), preservación de
claves no conflictivas en `.claude/settings.json` existente, y rollback
completo ante un fallo inyectado a mitad de la aplicación del journal.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from tools.ds_init import writer
from tools.ds_init.planner import construir_plan
from tools.ds_init.version import HARNESS_VERSION

# Referencia al `os.replace` real, importada antes de que ningún test
# patchee `tools.ds_init.writer.os.replace` (ver instrucción de invocación).
import os as _os_module

_OS_REPLACE_REAL = _os_module.replace

PERFIL = "python-jupyter-data"


def _crear_repo_git_temporal() -> Path:
    ruta = Path(tempfile.mkdtemp(prefix="ds_init_test_writer_"))
    subprocess.run(["git", "init", str(ruta)], capture_output=True, text=True, check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.name", "Test"], check=True)
    (ruta / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(ruta), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(ruta), "commit", "-m", "inicial"],
        capture_output=True,
        text=True,
        check=True,
    )
    return ruta


def _snapshot_arbol(ruta: Path) -> dict:
    """Nombres relativos -> hash de contenido, para todo archivo bajo `ruta`
    fuera de `.git/` (mismo criterio que `test_cli.py`, no mtime)."""
    snapshot = {}
    for archivo in ruta.rglob("*"):
        if not archivo.is_file():
            continue
        relativo = archivo.relative_to(ruta)
        if ".git" in relativo.parts:
            continue
        snapshot[str(relativo)] = hashlib.sha256(archivo.read_bytes()).hexdigest()
    return snapshot


def _dirs_staging_remanentes(ruta: Path) -> list:
    return [p.name for p in ruta.iterdir() if p.is_dir() and p.name.startswith(".ds_init_staging_")]


def _config_base(destino: Path, nombre: str = "proyecto-de-prueba") -> dict:
    return {
        "perfil": PERFIL,
        "nombre": nombre,
        "notebooks_dir": "notebooks",
        "venv_dir": ".venv",
        "destino": str(destino),
        "integrar_claude": False,
        "placeholders": {
            "NOMBRE_PROYECTO": nombre,
            "NOTEBOOKS_DIR": "notebooks",
            "VENV_DIR": ".venv",
            "FECHA_INSTALACION": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "HARNESS_VERSION": HARNESS_VERSION,
            "RUTAS_PROHIBIDAS_JSON": "[]",
        },
    }


class TestInstalacionExitosa(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_instalacion_exitosa_aplica_archivos_y_no_deja_staging(self):
        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)

        resultado = writer.instalar(plan, self.repo, config)

        self.assertTrue(len(resultado.aplicados) > 0)
        for ruta_relativa in resultado.aplicados:
            self.assertTrue(
                (self.repo / ruta_relativa).exists(),
                f"{ruta_relativa} no quedó presente en el destino",
            )

        self.assertEqual(
            _dirs_staging_remanentes(self.repo),
            [],
            "Quedó un directorio de staging sin limpiar tras una instalación exitosa",
        )

        # Archivo emblemático del harness realmente presente.
        self.assertTrue((self.repo / "tools" / "ds_guard.py").exists())
        self.assertTrue((self.repo / ".ds_init" / "control.json").exists())


class TestColisionOmiteSinSobrescribir(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_archivo_ya_existente_queda_omitido_y_no_se_sobrescribe(self):
        # `tools/ds_guard.py` es una entrada VERBATIM del manifiesto: la
        # colisionamos escribiendo contenido propio antes de instalar.
        destino_colision = self.repo / "tools" / "ds_guard.py"
        destino_colision.parent.mkdir(parents=True, exist_ok=True)
        contenido_original = "# contenido original del destino, no debe tocarse\n"
        destino_colision.write_text(contenido_original, encoding="utf-8")

        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)

        resultado = writer.instalar(plan, self.repo, config)

        self.assertIn("tools/ds_guard.py", resultado.omitidos)
        self.assertNotIn("tools/ds_guard.py", resultado.aplicados)
        self.assertEqual(destino_colision.read_text(encoding="utf-8"), contenido_original)


class TestPreservaConfiguracionExistente(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_clave_propia_no_conflictiva_sobrevive_al_merge(self):
        dir_claude = self.repo / ".claude"
        dir_claude.mkdir(parents=True, exist_ok=True)
        settings_existente = {
            "miClaveDeProyecto": {"algo": "propio"},
        }
        (dir_claude / "settings.json").write_text(
            json.dumps(settings_existente, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)

        writer.instalar(plan, self.repo, config)

        settings_final = json.loads((dir_claude / "settings.json").read_text(encoding="utf-8"))
        self.assertIn("miClaveDeProyecto", settings_final)
        self.assertEqual(settings_final["miClaveDeProyecto"], {"algo": "propio"})
        # Y las claves propias del harness también deben haber llegado.
        self.assertIn("hooks", settings_final)


class TestRollbackAnteFalloInyectado(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_fallo_a_mitad_de_journal_revierte_todo(self):
        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)

        snapshot_antes = _snapshot_arbol(self.repo)

        llamadas = {"n": 0}
        LIMITE_EXITOSO = 3  # deja pasar las primeras 3 aplicaciones, falla en la 4ta.

        def _replace_con_fallo(origen, destino_final):
            llamadas["n"] += 1
            if llamadas["n"] > LIMITE_EXITOSO:
                raise OSError("fallo inyectado por el test a mitad del journal")
            return _OS_REPLACE_REAL(origen, destino_final)

        with patch("tools.ds_init.writer.os.replace", side_effect=_replace_con_fallo):
            with self.assertRaises(writer.InstalacionAbortadaError):
                writer.instalar(plan, self.repo, config)

        self.assertGreater(llamadas["n"], LIMITE_EXITOSO, "el mock no llegó a inyectar el fallo")

        snapshot_despues = _snapshot_arbol(self.repo)
        self.assertEqual(
            snapshot_antes,
            snapshot_despues,
            "El destino quedó modificado tras un rollback: debía quedar exactamente como antes",
        )
        self.assertEqual(
            _dirs_staging_remanentes(self.repo),
            [],
            "Quedó un directorio de staging sin limpiar tras el rollback",
        )


class TestFalloGenerandoControlRevierteTodo(unittest.TestCase):
    """Reliability v0.2.0: `control.generar_control` corre dentro de la misma
    transacción protegida por rollback que la aplicación del journal — un
    fallo ahí (disco lleno, permiso denegado, etc.) debe revertir todo lo ya
    aplicado, igual que un fallo a mitad del journal."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_fallo_en_generar_control_revierte_instalacion_completa(self):
        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)

        snapshot_antes = _snapshot_arbol(self.repo)

        with patch(
            "tools.ds_init.writer.control_mod.generar_control",
            side_effect=OSError("fallo inyectado por el test generando control.json"),
        ):
            with self.assertRaises(writer.InstalacionAbortadaError) as ctx:
                writer.instalar(plan, self.repo, config)

        self.assertIsInstance(ctx.exception.__cause__, OSError)
        self.assertIn("generando control.json", str(ctx.exception.__cause__))

        snapshot_despues = _snapshot_arbol(self.repo)
        self.assertEqual(
            snapshot_antes,
            snapshot_despues,
            "El destino quedó modificado tras un fallo en generar_control: "
            "debía quedar exactamente como antes (incluyendo la ausencia de "
            "control.json)",
        )
        self.assertFalse((self.repo / ".ds_init" / "control.json").exists())
        self.assertFalse(
            (self.repo / ".ds_init").exists(),
            "El directorio .ds_init/ no debía quedar creado tras revertir una "
            "instalación nueva (sin control.json previo)",
        )
        self.assertEqual(
            _dirs_staging_remanentes(self.repo),
            [],
            "Quedó un directorio de staging sin limpiar tras el rollback por "
            "fallo en generar_control",
        )


class TestControlJsonParticipaDeLaTransaccion(unittest.TestCase):
    """Reliability v0.2.0 (segunda vuelta): `.ds_init/control.json` participa
    de la misma transacción protegida por rollback que el resto del journal.
    Si ya existía (reinstalación sobre un proyecto ya inicializado), se
    respalda antes de regenerarlo y se restaura exactamente si
    `generar_control` falla -- incluso si alcanzó a escribir contenido
    parcial antes de fallar, porque su escritura no es atómica."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _escribir_control_previo(self, contenido: str) -> Path:
        # `newline=""` preserva literalmente los "\n" de `contenido`, igual
        # que `writer._escribir_texto` -- sin esto, el modo texto de Windows
        # los traduciría a CRLF y la comparación byte a byte del test daría
        # un falso negativo (no un problema de `writer.py`, sino de este
        # helper de setup).
        dir_control = self.repo / ".ds_init"
        dir_control.mkdir(parents=True, exist_ok=True)
        ruta_control = dir_control / "control.json"
        with open(ruta_control, "w", encoding="utf-8", newline="") as f:
            f.write(contenido)
        return ruta_control

    def test_reinstalacion_con_control_previo_y_fallo_restaura_el_original_byte_a_byte(self):
        control_previo = (
            '{\n  "harness_version": "0.1.0-previa",\n  "perfil": "otra-cosa",\n'
            '  "archivos": []\n}\n'
        )
        ruta_control = self._escribir_control_previo(control_previo)

        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)

        with patch(
            "tools.ds_init.writer.control_mod.generar_control",
            side_effect=OSError("fallo inyectado por el test generando control.json"),
        ):
            with self.assertRaises(writer.InstalacionAbortadaError):
                writer.instalar(plan, self.repo, config)

        self.assertTrue(ruta_control.exists(), "El control.json anterior no debía desaparecer")
        self.assertEqual(
            ruta_control.read_bytes(),
            control_previo.encode("utf-8"),
            "El control.json restaurado no es byte a byte igual al anterior",
        )
        # El resto del rollback también se completó: nada del harness quedó
        # instalado.
        self.assertFalse((self.repo / "tools" / "ds_guard.py").exists())
        self.assertEqual(_dirs_staging_remanentes(self.repo), [])

    def test_reinstalacion_con_escritura_parcial_de_control_restaura_el_original(self):
        """`control.generar_control` escribe con `open(..., "w")`, que trunca
        el archivo antes de volcar el JSON: no es atómico. Este test simula
        justamente ese peor caso -- el mock alcanza a truncar/escribir un
        fragmento antes de fallar -- para confirmar que el backup tomado
        antes de tocar el archivo permite restaurar el original igual, no
        solo cuando el fallo ocurre antes de cualquier escritura."""
        control_previo = '{"harness_version": "0.1.0-previa", "archivos": []}\n'
        ruta_control = self._escribir_control_previo(control_previo)

        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)

        def _generar_control_con_escritura_parcial(destino, perfil, config, archivos_aplicados):
            Path(destino, ".ds_init", "control.json").write_text(
                '{"harness_ver', encoding="utf-8"
            )
            raise OSError("fallo inyectado por el test a mitad de la escritura")

        with patch(
            "tools.ds_init.writer.control_mod.generar_control",
            side_effect=_generar_control_con_escritura_parcial,
        ):
            with self.assertRaises(writer.InstalacionAbortadaError):
                writer.instalar(plan, self.repo, config)

        self.assertEqual(
            ruta_control.read_bytes(),
            control_previo.encode("utf-8"),
            "El control.json truncado a medio escribir no se restauró al original",
        )
        self.assertEqual(_dirs_staging_remanentes(self.repo), [])


class TestRollbackResilienteAntePropioFallo(unittest.TestCase):
    """Reliability v0.2.0: si revertir una entrada puntual del journal falla
    (p. ej. no se puede restaurar un backup), `_revertir_journal` debe seguir
    intentando revertir el resto, y `instalar()` debe seguir levantando
    `InstalacionAbortadaError` (nunca la excepción cruda del fallo de
    rollback), preservando la excepción original como causa y nombrando la
    entrada que no pudo restaurarse."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        # Pre-existe settings.json para forzar una entrada
        # "reemplazar-merge" en el journal: así el rollback tiene que
        # restaurar un backup, que es el paso que vamos a hacer fallar.
        dir_claude = self.repo / ".claude"
        dir_claude.mkdir(parents=True, exist_ok=True)
        (dir_claude / "settings.json").write_text(
            json.dumps({"miClaveDeProyecto": {"algo": "propio"}}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_fallo_al_restaurar_un_backup_no_detiene_el_resto_del_rollback(self):
        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)

        snapshot_antes = _snapshot_arbol(self.repo)

        _COPY2_REAL = shutil.copy2

        def _copy2_falla_al_restaurar(origen, destino_final, *args, **kwargs):
            # Distingue la copia de creación del backup (origen bajo el
            # destino real) de la restauración durante el rollback (origen
            # bajo `staging/.backup/`) — solo la segunda debe fallar.
            if ".backup" in str(origen):
                raise OSError("fallo inyectado por el test al restaurar el backup")
            return _COPY2_REAL(origen, destino_final, *args, **kwargs)

        with patch(
            "tools.ds_init.writer.control_mod.generar_control",
            side_effect=RuntimeError("fallo inyectado por el test generando control.json"),
        ), patch(
            "tools.ds_init.writer.shutil.copy2", side_effect=_copy2_falla_al_restaurar
        ):
            with self.assertRaises(writer.InstalacionAbortadaError) as ctx:
                writer.instalar(plan, self.repo, config)

        excepcion = ctx.exception
        # La excepción que disparó el rollback (no la del propio rollback)
        # queda preservada como causa principal.
        self.assertIsInstance(excepcion.__cause__, RuntimeError)
        self.assertIn("generando control.json", str(excepcion.__cause__))
        # El mensaje nombra la entrada que no se pudo restaurar.
        self.assertIn(".claude/settings.json", str(excepcion))

        snapshot_despues = _snapshot_arbol(self.repo)
        rutas_distintas = {
            ruta
            for ruta in set(snapshot_antes) | set(snapshot_despues)
            if snapshot_antes.get(ruta) != snapshot_despues.get(ruta)
        }
        # Único archivo que no pudo volver a su estado original: aquel cuyo
        # backup no se pudo restaurar. Todo lo demás sí se revirtió, a pesar
        # del fallo puntual. `_snapshot_arbol` guarda rutas con el separador
        # nativo del SO (Windows usa "\\"), a diferencia del mensaje de
        # `InstalacionAbortadaError` (que usa siempre "/", tal como están
        # las rutas en el manifiesto).
        self.assertEqual(rutas_distintas, {str(Path(".claude") / "settings.json")})
        self.assertFalse(
            (self.repo / "tools" / "ds_guard.py").exists(),
            "Una entrada 'crear' no relacionada con el fallo de rollback debía "
            "revertirse igual",
        )
        self.assertFalse((self.repo / ".ds_init" / "control.json").exists())
        self.assertEqual(_dirs_staging_remanentes(self.repo), [])


class TestFalloAntesDeAplicarJournalNoDejaStaging(unittest.TestCase):
    """Hallazgo 1: un fallo en `_preparar_backups`/`_escribir_journal` (antes
    de que `_aplicar_journal` arranque) también debe abortar limpio, sin
    directorio `.ds_init_staging_*` remanente en el destino."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_fallo_en_preparar_backups_aborta_y_limpia_staging(self):
        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)

        snapshot_antes = _snapshot_arbol(self.repo)

        with patch(
            "tools.ds_init.writer._preparar_backups",
            side_effect=OSError("fallo inyectado por el test antes de aplicar el journal"),
        ):
            with self.assertRaises(writer.InstalacionAbortadaError):
                writer.instalar(plan, self.repo, config)

        snapshot_despues = _snapshot_arbol(self.repo)
        self.assertEqual(
            snapshot_antes,
            snapshot_despues,
            "El destino quedó modificado tras abortar antes de aplicar el journal",
        )
        self.assertEqual(
            _dirs_staging_remanentes(self.repo),
            [],
            "Quedó un directorio de staging sin limpiar tras un fallo en _preparar_backups",
        )


if __name__ == "__main__":
    unittest.main()
