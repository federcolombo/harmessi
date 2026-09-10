"""Tests de `tools.dsguard.pathguard` (Bloque 3, reliability v0.2.0):
protección de rutas -- holdouts, `data/raw`, secretos, `.claude/
guardrails.json` y `write_scopes`. Usa repositorios temporales propios
(nunca este repositorio)."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.dsguard import pathguard


def _crear_repo_temporal(prefix: str = "pathguard_test_") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def _escribir_config(repo: Path, datos: dict) -> Path:
    dir_claude = repo / ".claude"
    dir_claude.mkdir(parents=True, exist_ok=True)
    ruta = dir_claude / "guardrails.json"
    ruta.write_text(json.dumps(datos, indent=2), encoding="utf-8")
    return ruta


def _fecha(delta_horas: float) -> str:
    momento = datetime.now(timezone.utc) + timedelta(hours=delta_horas)
    return momento.strftime("%Y-%m-%dT%H:%M:%SZ")


class TestResolverRutaRelativa(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_ruta_relativa_dentro_del_repo(self):
        ruta_relativa, dentro = pathguard.resolver_ruta_relativa("notebooks/a.ipynb", self.repo)
        self.assertTrue(dentro)
        self.assertEqual(ruta_relativa, "notebooks/a.ipynb")

    def test_ruta_absoluta_dentro_del_repo(self):
        absoluta = str(self.repo / "notebooks" / "a.ipynb")
        ruta_relativa, dentro = pathguard.resolver_ruta_relativa(absoluta, self.repo)
        self.assertTrue(dentro)
        self.assertEqual(ruta_relativa, "notebooks/a.ipynb")

    def test_traversal_hacia_afuera_del_repo(self):
        _, dentro = pathguard.resolver_ruta_relativa("../fuera.txt", self.repo)
        self.assertFalse(dentro)

    def test_traversal_que_vuelve_adentro_es_valido(self):
        ruta_relativa, dentro = pathguard.resolver_ruta_relativa("sub/../notebooks/a.ipynb", self.repo)
        self.assertTrue(dentro)
        self.assertEqual(ruta_relativa, "notebooks/a.ipynb")

    def test_absoluta_fuera_del_repo(self):
        otra = _crear_repo_temporal("pathguard_test_otra_")
        try:
            _, dentro = pathguard.resolver_ruta_relativa(str(otra / "x.txt"), self.repo)
            self.assertFalse(dentro)
        finally:
            shutil.rmtree(otra, ignore_errors=True)

    def test_windows_backslash_y_posix_slash_equivalentes(self):
        rel_posix, dentro_posix = pathguard.resolver_ruta_relativa("data/raw/x.csv", self.repo)
        rel_back, dentro_back = pathguard.resolver_ruta_relativa("data\\raw\\x.csv", self.repo)
        self.assertTrue(dentro_posix and dentro_back)
        self.assertEqual(rel_posix, rel_back)

    def test_archivo_inexistente_se_resuelve_igual_por_su_ubicacion_prevista(self):
        ruta_relativa, dentro = pathguard.resolver_ruta_relativa("data/raw/no_existe_todavia.csv", self.repo)
        self.assertTrue(dentro)
        self.assertEqual(ruta_relativa, "data/raw/no_existe_todavia.csv")

    def test_symlink_que_escapa_del_repo(self):
        externo = _crear_repo_temporal("pathguard_test_externo_")
        try:
            enlace = self.repo / "escape_link"
            try:
                os.symlink(str(externo), str(enlace), target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("El entorno no permite crear symlinks (falta privilegio/Developer Mode)")
            _, dentro = pathguard.resolver_ruta_relativa("escape_link/nuevo.txt", self.repo)
            self.assertFalse(dentro)
        finally:
            shutil.rmtree(externo, ignore_errors=True)

    def test_ruta_invalida_no_lanza(self):
        # Caracteres nulos son inválidos como ruta en cualquier SO.
        _, dentro = pathguard.resolver_ruta_relativa("archivo\0malo.txt", self.repo)
        self.assertFalse(dentro)


class TestCargarConfig(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_config_ausente_usa_defaults_seguros(self):
        config = pathguard.cargar_config(self.repo)
        self.assertEqual(config.holdouts, ())
        self.assertEqual(config.data_raw, pathguard.DATA_RAW_DEFAULT)
        self.assertEqual(config.write_scopes, {})
        self.assertEqual(config.excepciones, ())

    def test_config_valida_se_carga_completa(self):
        _escribir_config(
            self.repo,
            {
                "holdouts": ["data/holdout/**"],
                "data_raw": ["data/raw/**", "data/external/**"],
                "secretos_extra": ["config/interno.json"],
                "write_scopes": {"python-data-engineer": ["notebooks/**"]},
                "excepciones": [{"ruta": "data/holdout/x.parquet", "accion": "read"}],
            },
        )
        config = pathguard.cargar_config(self.repo)
        self.assertEqual(config.holdouts, ("data/holdout/**",))
        self.assertEqual(config.data_raw, ("data/raw/**", "data/external/**"))
        self.assertEqual(config.secretos_extra, ("config/interno.json",))
        self.assertEqual(config.write_scopes, {"python-data-engineer": ("notebooks/**",)})
        self.assertEqual(len(config.excepciones), 1)

    def test_json_invalido_levanta_error_config(self):
        ruta = self.repo / ".claude"
        ruta.mkdir(parents=True)
        (ruta / "guardrails.json").write_text("{ esto no es json valido", encoding="utf-8")
        with self.assertRaises(pathguard.ConfigGuardrailsError):
            pathguard.cargar_config(self.repo)

    def test_no_es_un_objeto_json_levanta_error_config(self):
        ruta = self.repo / ".claude"
        ruta.mkdir(parents=True)
        (ruta / "guardrails.json").write_text("[1, 2, 3]", encoding="utf-8")
        with self.assertRaises(pathguard.ConfigGuardrailsError):
            pathguard.cargar_config(self.repo)

    def test_holdouts_con_tipo_invalido_levanta_error_config(self):
        _escribir_config(self.repo, {"holdouts": "no-es-una-lista"})
        with self.assertRaises(pathguard.ConfigGuardrailsError):
            pathguard.cargar_config(self.repo)

    def test_write_scopes_con_tipo_invalido_levanta_error_config(self):
        _escribir_config(self.repo, {"write_scopes": {"agente": "no-es-una-lista"}})
        with self.assertRaises(pathguard.ConfigGuardrailsError):
            pathguard.cargar_config(self.repo)

    def test_excepciones_con_tipo_invalido_levanta_error_config(self):
        _escribir_config(self.repo, {"excepciones": ["no-es-un-objeto"]})
        with self.assertRaises(pathguard.ConfigGuardrailsError):
            pathguard.cargar_config(self.repo)


class TestExcepcionVigente(unittest.TestCase):
    def test_sin_vencimiento_es_vigente(self):
        excepciones = ({"ruta": "data/holdout/x.parquet", "accion": "read"},)
        self.assertTrue(
            pathguard._excepcion_vigente(excepciones, "data/holdout/x.parquet", "read", datetime.now(timezone.utc))
        )

    def test_vencimiento_futuro_es_vigente(self):
        excepciones = (
            {"ruta": "data/holdout/x.parquet", "accion": "read", "vence_utc": _fecha(24)},
        )
        self.assertTrue(
            pathguard._excepcion_vigente(excepciones, "data/holdout/x.parquet", "read", datetime.now(timezone.utc))
        )

    def test_vencimiento_pasado_no_es_vigente(self):
        excepciones = (
            {"ruta": "data/holdout/x.parquet", "accion": "read", "vence_utc": _fecha(-24)},
        )
        self.assertFalse(
            pathguard._excepcion_vigente(excepciones, "data/holdout/x.parquet", "read", datetime.now(timezone.utc))
        )

    def test_fecha_ilegible_no_es_vigente(self):
        excepciones = (
            {"ruta": "data/holdout/x.parquet", "accion": "read", "vence_utc": "no-es-una-fecha"},
        )
        self.assertFalse(
            pathguard._excepcion_vigente(excepciones, "data/holdout/x.parquet", "read", datetime.now(timezone.utc))
        )

    def test_accion_distinta_no_matchea(self):
        excepciones = ({"ruta": "data/holdout/x.parquet", "accion": "write"},)
        self.assertFalse(
            pathguard._excepcion_vigente(excepciones, "data/holdout/x.parquet", "read", datetime.now(timezone.utc))
        )

    def test_ruta_distinta_no_matchea(self):
        excepciones = ({"ruta": "data/holdout/otro.parquet", "accion": "read"},)
        self.assertFalse(
            pathguard._excepcion_vigente(excepciones, "data/holdout/x.parquet", "read", datetime.now(timezone.utc))
        )

    def test_case_insensitive(self):
        excepciones = ({"ruta": "Data/Holdout/X.Parquet", "accion": "read"},)
        self.assertTrue(
            pathguard._excepcion_vigente(excepciones, "data/holdout/x.parquet", "read", datetime.now(timezone.utc))
        )


class TestEvaluarRutaEstructurada(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_temporal()
        self.config = pathguard.ConfigGuardrails(holdouts=("data/holdout/**",))

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _evaluar(self, tool_name, tool_input, agent_type=None, config=None):
        payload = {"tool_name": tool_name, "tool_input": tool_input}
        if agent_type:
            payload["agent_type"] = agent_type
        return pathguard.evaluar_tool_call(payload, config or self.config, self.repo)

    # -- allow del camino feliz --

    def test_write_ruta_legitima_permitida(self):
        permitido, _ = self._evaluar("Write", {"file_path": "notebooks/a.ipynb"})
        self.assertTrue(permitido)

    def test_edit_ruta_legitima_permitida(self):
        permitido, _ = self._evaluar("Edit", {"file_path": "tools/utils.py"})
        self.assertTrue(permitido)

    def test_read_ruta_legitima_permitida(self):
        permitido, _ = self._evaluar("Read", {"file_path": "README.md"})
        self.assertTrue(permitido)

    # -- secretos: deny siempre, lectura y escritura --

    def test_read_env_denegado(self):
        permitido, motivo = self._evaluar("Read", {"file_path": ".env"})
        self.assertFalse(permitido)
        self.assertIn("secreto", motivo)

    def test_write_env_denegado(self):
        permitido, _ = self._evaluar("Write", {"file_path": ".env"})
        self.assertFalse(permitido)

    def test_read_env_variante_denegado(self):
        permitido, _ = self._evaluar("Read", {"file_path": ".env.local"})
        self.assertFalse(permitido)

    def test_read_clave_privada_pem_denegado(self):
        permitido, _ = self._evaluar("Read", {"file_path": "certs/server.pem"})
        self.assertFalse(permitido)

    def test_read_id_rsa_denegado(self):
        permitido, _ = self._evaluar("Read", {"file_path": ".ssh/id_rsa"})
        self.assertFalse(permitido)

    def test_read_dentro_de_ssh_denegado(self):
        permitido, _ = self._evaluar("Read", {"file_path": ".ssh/config"})
        self.assertFalse(permitido)

    def test_read_credentials_json_denegado(self):
        permitido, _ = self._evaluar("Read", {"file_path": "config/aws_credentials.json"})
        self.assertFalse(permitido)

    def test_read_dentro_de_aws_denegado(self):
        permitido, _ = self._evaluar("Read", {"file_path": "home/.aws/credentials"})
        self.assertFalse(permitido)

    def test_read_kdbx_denegado(self):
        permitido, _ = self._evaluar("Read", {"file_path": "vault.kdbx"})
        self.assertFalse(permitido)

    def test_read_secreto_case_insensitive(self):
        permitido, _ = self._evaluar("Read", {"file_path": ".ENV"})
        self.assertFalse(permitido)

    def test_secretos_extra_del_config_denegado(self):
        config = pathguard.ConfigGuardrails(secretos_extra=("config/interno.json",))
        permitido, _ = self._evaluar("Read", {"file_path": "config/interno.json"}, config=config)
        self.assertFalse(permitido)

    def test_archivo_no_secreto_similar_permitido(self):
        # No debe haber falso positivo sobre nombres parecidos pero no
        # cubiertos por la denylist conservadora.
        permitido, _ = self._evaluar("Read", {"file_path": "notebooks/feature_keys.py"})
        self.assertTrue(permitido)

    # -- holdout --

    def test_write_holdout_denegado_siempre(self):
        permitido, motivo = self._evaluar("Write", {"file_path": "data/holdout/eval.parquet"})
        self.assertFalse(permitido)
        self.assertIn("holdout", motivo)

    def test_read_holdout_sin_excepcion_denegado(self):
        permitido, _ = self._evaluar("Read", {"file_path": "data/holdout/eval.parquet"})
        self.assertFalse(permitido)

    def test_read_holdout_con_excepcion_vigente_permitido(self):
        config = pathguard.ConfigGuardrails(
            holdouts=("data/holdout/**",),
            excepciones=({"ruta": "data/holdout/eval.parquet", "accion": "read"},),
        )
        permitido, motivo = self._evaluar("Read", {"file_path": "data/holdout/eval.parquet"}, config=config)
        self.assertTrue(permitido)
        self.assertIn("excepción", motivo)

    def test_read_holdout_con_excepcion_vencida_denegado(self):
        config = pathguard.ConfigGuardrails(
            holdouts=("data/holdout/**",),
            excepciones=(
                {"ruta": "data/holdout/eval.parquet", "accion": "read", "vence_utc": _fecha(-1)},
            ),
        )
        permitido, _ = self._evaluar("Read", {"file_path": "data/holdout/eval.parquet"}, config=config)
        self.assertFalse(permitido)

    def test_write_holdout_no_se_habilita_por_excepcion_de_lectura(self):
        config = pathguard.ConfigGuardrails(
            holdouts=("data/holdout/**",),
            excepciones=({"ruta": "data/holdout/eval.parquet", "accion": "read"},),
        )
        permitido, _ = self._evaluar("Write", {"file_path": "data/holdout/eval.parquet"}, config=config)
        self.assertFalse(permitido)

    def test_notebookedit_sobre_holdout_denegado(self):
        permitido, _ = self._evaluar("NotebookEdit", {"notebook_path": "data/holdout/eval.ipynb"})
        self.assertFalse(permitido)

    # -- data/raw --

    def test_write_data_raw_denegado(self):
        permitido, motivo = self._evaluar("Write", {"file_path": "data/raw/x.csv"}, config=pathguard.ConfigGuardrails())
        self.assertFalse(permitido)
        self.assertIn("solo lectura", motivo)

    def test_edit_data_raw_denegado(self):
        permitido, _ = self._evaluar("Edit", {"file_path": "data/raw/x.csv"}, config=pathguard.ConfigGuardrails())
        self.assertFalse(permitido)

    def test_read_data_raw_permitido(self):
        permitido, _ = self._evaluar("Read", {"file_path": "data/raw/x.csv"}, config=pathguard.ConfigGuardrails())
        self.assertTrue(permitido)

    def test_write_data_raw_archivo_inexistente_denegado(self):
        # No existe en disco todavía -- igual debe evaluarse por su ubicación
        # prevista, no por si el archivo ya está ahí.
        permitido, _ = self._evaluar(
            "Write", {"file_path": "data/raw/nuevo_no_creado.csv"}, config=pathguard.ConfigGuardrails()
        )
        self.assertFalse(permitido)

    # -- guardrails.json: protegido de escritura, lectura permitida --

    def test_write_guardrails_json_denegado(self):
        permitido, motivo = self._evaluar("Write", {"file_path": ".claude/guardrails.json"})
        self.assertFalse(permitido)
        self.assertIn("guardrails.json", motivo)

    def test_edit_guardrails_json_denegado(self):
        permitido, _ = self._evaluar("Edit", {"file_path": ".claude/guardrails.json"})
        self.assertFalse(permitido)

    def test_read_guardrails_json_permitido(self):
        permitido, _ = self._evaluar("Read", {"file_path": ".claude/guardrails.json"})
        self.assertTrue(permitido)

    # -- fuera del repo / no resoluble --

    def test_write_fuera_del_repo_denegado(self):
        permitido, motivo = self._evaluar("Write", {"file_path": "../fuera.txt"})
        self.assertFalse(permitido)
        self.assertIn("fuera del repositorio", motivo)

    def test_sin_ruta_determinable_denegado_fail_closed(self):
        permitido, motivo = self._evaluar("Write", {"content": "sin file_path"})
        self.assertFalse(permitido)
        self.assertIn("fail-closed", motivo)

    # -- symlink: la resolución debe seguirlo antes de comparar --

    def test_symlink_hacia_secreto_denegado(self):
        (self.repo / ".env").write_text("SECRET=1\n", encoding="utf-8")
        enlace = self.repo / "notas.txt"
        try:
            os.symlink(str(self.repo / ".env"), str(enlace))
        except (OSError, NotImplementedError):
            self.skipTest("El entorno no permite crear symlinks (falta privilegio/Developer Mode)")
        permitido, motivo = self._evaluar("Read", {"file_path": "notas.txt"})
        self.assertFalse(permitido)
        self.assertIn("secreto", motivo)

    # -- Windows vs POSIX --

    def test_backslash_windows_matchea_igual_que_posix(self):
        permitido_back, _ = self._evaluar(
            "Write", {"file_path": "data\\raw\\x.csv"}, config=pathguard.ConfigGuardrails()
        )
        permitido_posix, _ = self._evaluar(
            "Write", {"file_path": "data/raw/x.csv"}, config=pathguard.ConfigGuardrails()
        )
        self.assertEqual(permitido_back, permitido_posix)
        self.assertFalse(permitido_back)

    # -- write_scopes --

    def test_write_scopes_vacio_no_restringe(self):
        permitido, _ = self._evaluar(
            "Write", {"file_path": "tools/otra_cosa.py"}, agent_type="python-data-engineer",
            config=pathguard.ConfigGuardrails(),
        )
        self.assertTrue(permitido)

    def test_write_scopes_dentro_del_scope_permitido(self):
        config = pathguard.ConfigGuardrails(write_scopes={"python-data-engineer": ("notebooks/**",)})
        permitido, _ = self._evaluar(
            "Write", {"file_path": "notebooks/a.ipynb"}, agent_type="python-data-engineer", config=config
        )
        self.assertTrue(permitido)

    def test_write_scopes_fuera_del_scope_denegado(self):
        config = pathguard.ConfigGuardrails(write_scopes={"python-data-engineer": ("notebooks/**",)})
        permitido, motivo = self._evaluar(
            "Write", {"file_path": "tools/otra_cosa.py"}, agent_type="python-data-engineer", config=config
        )
        self.assertFalse(permitido)
        self.assertIn("write_scope", motivo)

    def test_write_scopes_agente_no_listado_denegado(self):
        config = pathguard.ConfigGuardrails(write_scopes={"python-data-engineer": ("notebooks/**",)})
        permitido, _ = self._evaluar(
            "Write", {"file_path": "notebooks/a.ipynb"}, agent_type="otro-agente", config=config
        )
        self.assertFalse(permitido)

    def test_write_scopes_no_aplica_al_lead(self):
        # agent_type ausente = Lead/sesión raíz: no se rediseñan sus
        # capacidades en este bloque, write_scopes no lo restringe.
        config = pathguard.ConfigGuardrails(write_scopes={"python-data-engineer": ("notebooks/**",)})
        permitido, _ = self._evaluar("Write", {"file_path": "tools/otra_cosa.py"}, agent_type=None, config=config)
        self.assertTrue(permitido)


class TestEvaluarGrep(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _evaluar(self, tool_input, config=None):
        payload = {"tool_name": "Grep", "tool_input": tool_input}
        return pathguard.evaluar_tool_call(payload, config or pathguard.ConfigGuardrails(), self.repo)

    def test_grep_con_path_legitimo_permitido(self):
        permitido, _ = self._evaluar({"pattern": "TODO", "path": "notebooks"})
        self.assertTrue(permitido)

    def test_grep_sobre_secreto_denegado(self):
        permitido, _ = self._evaluar({"pattern": "SECRET", "path": ".env"})
        self.assertFalse(permitido)

    def test_grep_sobre_holdout_sin_excepcion_denegado(self):
        config = pathguard.ConfigGuardrails(holdouts=("data/holdout/**",))
        permitido, _ = self._evaluar({"pattern": "x", "path": "data/holdout/eval.parquet"}, config=config)
        self.assertFalse(permitido)

    def test_grep_sobre_holdout_con_excepcion_permitido(self):
        config = pathguard.ConfigGuardrails(
            holdouts=("data/holdout/**",),
            excepciones=({"ruta": "data/holdout/eval.parquet", "accion": "read"},),
        )
        permitido, _ = self._evaluar({"pattern": "x", "path": "data/holdout/eval.parquet"}, config=config)
        self.assertTrue(permitido)

    def test_grep_sin_path_no_bloqueado_limitacion_documentada(self):
        permitido, motivo = self._evaluar({"pattern": "SECRET"})
        self.assertTrue(permitido)
        self.assertIn("fuera de alcance", motivo)


class TestEvaluarShell(unittest.TestCase):
    """Best-effort: ver limitaciones documentadas en el módulo. Estos tests
    cubren tanto lo que SÍ se detecta como, explícitamente, casos de
    indirección que NO se detectan -- para que ese comportamiento quede
    como regresión consciente, no como sorpresa futura."""

    def setUp(self):
        self.repo = _crear_repo_temporal()
        self.config = pathguard.ConfigGuardrails(holdouts=("data/holdout/**",))

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _evaluar(self, tool_name, comando, config=None):
        payload = {"tool_name": tool_name, "tool_input": {"command": comando}}
        return pathguard.evaluar_tool_call(payload, config or self.config, self.repo)

    def test_bash_comando_benigno_permitido(self):
        permitido, _ = self._evaluar("Bash", "git status")
        self.assertTrue(permitido)

    def test_bash_lectura_directa_de_secreto_denegado(self):
        permitido, motivo = self._evaluar("Bash", "cat .env")
        self.assertFalse(permitido)
        self.assertIn("secreto", motivo)

    def test_bash_git_show_de_secreto_denegado(self):
        permitido, _ = self._evaluar("Bash", "git show HEAD:.env")
        self.assertFalse(permitido)

    def test_bash_referencia_directa_a_holdout_denegado(self):
        permitido, _ = self._evaluar("Bash", "cat data/holdout/eval.parquet")
        self.assertFalse(permitido)

    def test_bash_holdout_con_excepcion_vigente_igual_denegado(self):
        # Decisión de diseño explícita: las excepciones NO aplican vía
        # Bash/PowerShell (solo a Read/Grep, donde se sabe con certeza que
        # es una lectura pura).
        config = pathguard.ConfigGuardrails(
            holdouts=("data/holdout/**",),
            excepciones=({"ruta": "data/holdout/eval.parquet", "accion": "read"},),
        )
        permitido, motivo = self._evaluar("Bash", "cat data/holdout/eval.parquet", config=config)
        self.assertFalse(permitido)
        self.assertIn("no aplican vía Bash", motivo)

    def test_bash_escritura_a_data_raw_con_redireccion_denegado(self):
        comando = "echo x " + chr(62) + " data/raw/y.csv"
        permitido, motivo = self._evaluar("Bash", comando, config=pathguard.ConfigGuardrails())
        self.assertFalse(permitido)
        self.assertIn("data/raw", motivo)

    def test_bash_borrado_de_data_raw_con_rm_denegado(self):
        permitido, _ = self._evaluar("Bash", "rm data/raw/y.csv", config=pathguard.ConfigGuardrails())
        self.assertFalse(permitido)

    def test_bash_lectura_de_data_raw_permitida(self):
        permitido, _ = self._evaluar("Bash", "cat data/raw/y.csv", config=pathguard.ConfigGuardrails())
        self.assertTrue(permitido)

    def test_bash_escritura_a_guardrails_json_denegado(self):
        comando = "echo x " + chr(62) + " .claude/guardrails.json"
        permitido, motivo = self._evaluar("Bash", comando)
        self.assertFalse(permitido)
        self.assertIn("guardrails.json", motivo)

    def test_bash_lectura_de_guardrails_json_permitida(self):
        permitido, _ = self._evaluar("Bash", "cat .claude/guardrails.json")
        self.assertTrue(permitido)

    def test_bash_arrow_de_tipos_no_es_falso_positivo_de_redireccion(self):
        comando = "python script.py " + chr(45) + chr(62) + " ok"
        permitido, _ = self._evaluar("Bash", comando, config=pathguard.ConfigGuardrails())
        self.assertTrue(permitido)

    def test_powershell_mismas_reglas_que_bash(self):
        permitido, _ = self._evaluar("PowerShell", "Get-Content .env")
        self.assertFalse(permitido)

    def test_powershell_remove_item_en_data_raw_denegado(self):
        permitido, _ = self._evaluar("PowerShell", "Remove-Item data/raw/y.csv", config=pathguard.ConfigGuardrails())
        self.assertFalse(permitido)

    def test_bash_indireccion_no_detectada_limitacion_documentada(self):
        """`cd` + comando separado: el token que borra ('x.csv') no
        contiene 'data/raw' en el mismo texto. No se detecta -- documentado
        como limitación de diseño (best-effort, no un parser de shell), no
        un bug a corregir en v0.2."""
        permitido, _ = self._evaluar(
            "Bash", "cd data/raw && rm x.csv", config=pathguard.ConfigGuardrails()
        )
        self.assertTrue(permitido)

    def test_bash_comando_vacio_permitido(self):
        permitido, _ = self._evaluar("Bash", "")
        self.assertTrue(permitido)


class TestEvaluarToolCallGenerico(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_tool_desconocida_permitida_passthrough(self):
        payload = {"tool_name": "Glob", "tool_input": {"pattern": "*.py"}}
        permitido, motivo = pathguard.evaluar_tool_call(payload, pathguard.ConfigGuardrails(), self.repo)
        self.assertTrue(permitido)
        self.assertIn("fuera del alcance", motivo)

    def test_tool_input_ausente_no_lanza(self):
        payload = {"tool_name": "Write"}
        permitido, _ = pathguard.evaluar_tool_call(payload, pathguard.ConfigGuardrails(), self.repo)
        self.assertFalse(permitido)


if __name__ == "__main__":
    unittest.main()
