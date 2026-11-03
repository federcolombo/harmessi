"""Tests de la ventana de cierre por ascendencia git (Change 20261027-v015-scope-closure-corrective, T1).

Repos git temporales reales; Changes sinteticos (solo `control.json`, sin `tasks.md`, de modo que
no cuentan como ajenos activos para la atribucion). Nunca usa este repositorio como fixture.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import scope  # noqa: E402

A, B, C = "20261001-cambio-a", "20261002-cambio-b", "20261003-cambio-c"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True,
                          text=True).stdout.strip()


def _commit(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def _escribir(repo: Path, ruta: str, texto: str = "x = 1\n") -> None:
    destino = repo / ruta
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")


def _control(cid: str, baseline: str, rutas: list) -> dict:
    return {"schema_version": 1, "change_id": cid, "baseline": {"commit": baseline},
            "alcance": {"rutas_autorizadas": list(rutas) + [f"openspec/changes/{cid}/**"]}}


def _guardar_control(repo: Path, control: dict) -> None:
    _escribir(repo, f"openspec/changes/{control['change_id']}/control.json", json.dumps(control))


class _Base(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="dsguard_ventana_"))
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@example.com")
        _git(self.repo, "config", "user.name", "Test")
        _escribir(self.repo, "base.py")
        self.c0 = _commit(self.repo, "inicial")

    def codigos(self, hallazgos, codigo):
        return [h for h in hallazgos if h.codigo == codigo]

    def rutas_bloqueantes(self, control):
        return sorted(h.ubicacion for h in scope.evaluar_alcance(self.repo, control)
                      if h.codigo == "ALCANCE-RUTA")

    def armar_a_luego_b(self, a_fuera: bool = False):
        """A: baseline c0, trabaja en c1 (dentro de scope; opcional un archivo fuera). B: baseline c1."""
        self.control_a = _control(A, self.c0, ["a_dentro.py"])
        _guardar_control(self.repo, self.control_a)
        _escribir(self.repo, "a_dentro.py")
        if a_fuera:
            _escribir(self.repo, "a_fuera.py")
        self.c1 = _commit(self.repo, "trabajo de A")
        self.control_b = _control(B, self.c1, ["b_exclusivo.py", "fuera_post.py"])
        _guardar_control(self.repo, self.control_b)
        _escribir(self.repo, "b_exclusivo.py")
        self.c2 = _commit(self.repo, "trabajo de B")


class TestVentanaCierre(_Base):
    def test_caso1_archivos_exclusivos_del_sucesor_no_bloquean_al_antecesor(self):
        self.armar_a_luego_b()
        self.assertEqual(self.rutas_bloqueantes(self.control_a), [])
        hallazgos = scope.evaluar_alcance(self.repo, self.control_a)
        acotada = self.codigos(hallazgos, scope.COD_VENTANA_ACOTADA)
        self.assertEqual(len(acotada), 1)
        self.assertIn(self.c1[:12], acotada[0].mensaje)
        self.assertIn(B, acotada[0].mensaje)
        self.assertIn("ventana del sucesor", acotada[0].mensaje)
        self.assertEqual(scope.bloqueantes(hallazgos), [])
        # Sin ventana (comportamiento previo) el archivo de B sí aparecería.
        self.assertIn("b_exclusivo.py", scope.archivos_tocados_desde_baseline(self.repo, self.c0))

    def test_caso2_archivo_de_a_fuera_de_scope_dentro_de_su_ventana_bloquea_a(self):
        self.armar_a_luego_b(a_fuera=True)
        self.assertEqual(self.rutas_bloqueantes(self.control_a), ["a_fuera.py"])

    def test_edicion_posterior_al_baseline_del_sucesor_bloquea_al_sucesor_no_al_antecesor(self):
        self.armar_a_luego_b()
        _escribir(self.repo, "otro_fuera.py")
        _commit(self.repo, "trabajo posterior fuera de alcance")
        self.assertEqual(self.rutas_bloqueantes(self.control_a), [])
        self.assertEqual(self.rutas_bloqueantes(self.control_b), ["otro_fuera.py"])

    def test_caso9_sin_sucesor_comportamiento_identico_al_previo(self):
        control = _control(A, self.c0, ["a_dentro.py"])
        _guardar_control(self.repo, control)
        _escribir(self.repo, "a_dentro.py")
        _escribir(self.repo, "a_fuera.py")
        _commit(self.repo, "trabajo")
        _escribir(self.repo, "sucio_fuera.py")  # sin commitear
        self.assertEqual(scope.frontera_ventana(self.repo, control), (None, [], []))
        hallazgos = scope.evaluar_alcance(self.repo, control)
        self.assertEqual(sorted(h.ubicacion for h in hallazgos if h.codigo == "ALCANCE-RUTA"),
                         ["a_fuera.py", "sucio_fuera.py"])
        self.assertEqual(self.codigos(hallazgos, scope.COD_VENTANA_ACOTADA), [])
        self.assertEqual(self.codigos(hallazgos, scope.COD_VENTANA_AMBIGUA), [])

    def test_archivos_sucios_siguen_sin_ventana(self):
        self.armar_a_luego_b()
        _escribir(self.repo, "sucio_fuera.py")
        self.assertEqual(self.rutas_bloqueantes(self.control_a), ["sucio_fuera.py"])

    def test_hasta_none_conserva_diff_contra_working_tree(self):
        self.armar_a_luego_b()
        _escribir(self.repo, "sucio.py")
        con_default = scope.archivos_tocados_desde_baseline(self.repo, self.c0)
        self.assertEqual(con_default, scope.archivos_tocados_desde_baseline(self.repo, self.c0, None))
        self.assertIn("b_exclusivo.py", con_default)
        acotado = scope.archivos_tocados_desde_baseline(self.repo, self.c0, self.c1)
        self.assertNotIn("b_exclusivo.py", acotado)
        self.assertIn("a_dentro.py", acotado)

    def test_candidato_con_baseline_no_resoluble_se_ignora(self):
        control_a = _control(A, self.c0, ["a_dentro.py"])
        _guardar_control(self.repo, control_a)
        _guardar_control(self.repo, _control(B, "1" * 40, []))
        _guardar_control(self.repo, _control(C, "no-es-un-sha", []))
        self.assertEqual(scope.frontera_ventana(self.repo, control_a), (None, [], []))

    def test_changes_con_el_mismo_baseline_no_son_sucesores(self):
        control_a = _control(A, self.c0, [])
        _guardar_control(self.repo, _control(B, self.c0, []))
        self.assertEqual(scope.frontera_ventana(self.repo, control_a), (None, [], []))

    def test_cadena_secuencial_elige_el_sucesor_mas_cercano(self):
        self.armar_a_luego_b()
        _escribir(self.repo, "c_trabajo.py")
        c3 = _commit(self.repo, "trabajo posterior")
        _guardar_control(self.repo, _control(C, c3, []))
        _commit(self.repo, "control de C")
        frontera, ids, hallazgos = scope.frontera_ventana(self.repo, self.control_a)
        self.assertEqual((frontera, ids, hallazgos), (self.c1, [B], []))

    def test_cadena_abc_la_frontera_de_b_es_el_baseline_de_c(self):
        self.armar_a_luego_b()
        _escribir(self.repo, "b_dentro.py")
        c3 = _commit(self.repo, "mas trabajo de B")
        control_c = _control(C, c3, [])
        _guardar_control(self.repo, control_c)
        _escribir(self.repo, "c_exclusivo.py")
        _commit(self.repo, "trabajo de C")
        self.assertEqual(scope.frontera_ventana(self.repo, self.control_b), (c3, [C], []))
        self.assertEqual(scope.frontera_ventana(self.repo, self.control_a)[0], self.c1)
        # B no absorbe lo posterior al baseline de C.
        rutas_b = [h.ubicacion for h in scope.evaluar_alcance(self.repo, self.control_b)
                   if h.codigo == "ALCANCE-RUTA"]
        self.assertNotIn("c_exclusivo.py", rutas_b)
        self.assertEqual(rutas_b, ["b_dentro.py"])

    def test_candidato_descartado_no_acota_la_ventana(self):
        self.armar_a_luego_b()
        _escribir(self.repo, f"openspec/changes/{B}/tasks.md", "# T\n\nestado: descartada\n")
        _commit(self.repo, "B descartado")
        self.assertEqual(scope.frontera_ventana(self.repo, self.control_a), (None, [], []))
        # Un estado ilegible/no descartado conserva el candidato.
        _escribir(self.repo, f"openspec/changes/{B}/tasks.md", "# T\n\nestado: en_implementacion\n")
        _commit(self.repo, "B reactivado")
        self.assertEqual(scope.frontera_ventana(self.repo, self.control_a), (self.c1, [B], []))

    def test_empate_de_distancia_se_desempata_por_change_id_menor(self):
        control_a = _control(A, self.c0, [])
        _escribir(self.repo, "x1.py")
        _commit(self.repo, "rama 1")
        sha1 = _git(self.repo, "rev-parse", "HEAD")
        _git(self.repo, "checkout", "-q", self.c0)
        _escribir(self.repo, "x2.py")
        sha2 = _commit(self.repo, "rama 2")
        self.assertNotEqual(sha1, sha2)
        # Ambos baselines deben estar en el historial de HEAD: se fusiona la rama 1.
        _git(self.repo, "merge", "-q", "--no-edit", sha1)
        # El id menor (B) queda con sha2 para verificar que no se elige por sha.
        _guardar_control(self.repo, _control(B, sha2, []))
        _guardar_control(self.repo, _control(C, sha1, []))
        frontera, ids, hallazgos = scope.frontera_ventana(self.repo, control_a)
        self.assertEqual((frontera, ids, hallazgos), (sha2, [B], []))
        evaluados = scope.evaluar_alcance(self.repo, control_a)
        self.assertEqual(self.codigos(evaluados, scope.COD_VENTANA_AMBIGUA), [])
        self.assertEqual(len(self.codigos(evaluados, scope.COD_VENTANA_ACOTADA)), 1)

    def test_candidato_en_rama_lateral_no_ancestral_de_head_no_acota(self):
        rama = _git(self.repo, "rev-parse", "--abbrev-ref", "HEAD")
        control_a = _control(A, self.c0, ["a_dentro.py"])
        _guardar_control(self.repo, control_a)
        _git(self.repo, "checkout", "-q", "-b", "lateral")
        _escribir(self.repo, "lateral.py")
        sha_lateral = _commit(self.repo, "rama lateral")
        _git(self.repo, "checkout", "-q", rama)
        _escribir(self.repo, "a_dentro.py")
        _escribir(self.repo, "a_fuera.py")
        _commit(self.repo, "trabajo de A")
        _guardar_control(self.repo, _control(B, sha_lateral, []))
        self.assertEqual(scope.frontera_ventana(self.repo, control_a), (None, [], []))
        self.assertIn("a_fuera.py", self.rutas_bloqueantes(control_a))

    def test_codigos_nuevos_son_informativos(self):
        self.assertIn("ALCANCE-VENTANA-ACOTADA", scope.CODIGOS_INFORMATIVOS)
        self.assertIn("ALCANCE-VENTANA-AMBIGUA", scope.CODIGOS_INFORMATIVOS)


class TestRepoSinPlaceholders(unittest.TestCase):
    """Regresión: el literal de doble llave tras `^` en el código fuente hacía abortar la instalación (placeholder sin resolver)."""

    def test_modulos_dsguard_sin_placeholders_pendientes(self):
        from ds_init import templating  # noqa: E402
        for ruta in sorted((REPO_ORIGEN / "tools" / "dsguard").glob("*.py")):
            texto = ruta.read_text(encoding="utf-8")
            self.assertTrue(templating.verificar_sin_placeholders_pendientes(texto), ruta.name)

    def test_resolver_commit_usa_peel_simple(self):
        from dsguard import repo  # noqa: E402
        self.assertNotIn("^{" + "{commit}}", (REPO_ORIGEN / "tools" / "dsguard" / "repo.py").read_text(encoding="utf-8"))
        sha = repo.resolver_commit(REPO_ORIGEN, "HEAD")
        self.assertRegex(sha, r"^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
