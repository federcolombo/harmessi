"""Tests de aislamiento de Changes paralelos (v0.11, Change 4B:
20261019-v011-parallel-change-isolation). Repos git temporales reales (patrón de test_scope.py);
nunca se usa este repositorio como fixture.

Un ajeno «cuenta» solo si, en el SNAPSHOT del commit baseline del Change propio (SHA completo), estaba
activo en tasks.md, con `scope_hash` y con todos los artefactos requeridos de su modo aprobados con hash
coherente; además su `scope_hash` en disco debe ser igual al del baseline (ancla inmutable)."""
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

from dsguard import core, scope, scope_amendments, sdd  # noqa: E402

DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"

# change_id con la forma real que exige la primitiva de aprobación (`YYYYMMDD-slug`).
A, B, C, D, Z = ("20260101-a", "20260101-b", "20260101-c", "20260101-d", "20260101-z")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, text=True)


def _crear_repo() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="dsguard_paralelos_test_"))
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    return repo


def _crear_change(repo: Path, change_id: str, rutas: list, estado: str = "en_implementacion",
                  control_texto=None, con_hash: bool = True, tasks_texto=None,
                  aprobado: bool = True, scope_hash=None, incluir_propio: bool = True,
                  modo: str = "completo", aprobar=None) -> Path:
    """Crea `openspec/changes/<id>/` con tasks.md, artefactos y control.json (alcance = rutas + su
    propio dir). Por defecto es un Change legítimo: activo (`en_implementacion`), con `scope_hash` y
    aprobación registrada de TODOS los artefactos requeridos del modo (hash real en `aprobaciones[]`).
    `aprobado=False` => `aprobaciones: []`; `aprobar=[...]` => solo esos artefactos; `con_hash=False`
    => sin scope_hash (legado); `scope_hash` pisa el hash; `incluir_propio=False` => el alcance no
    incluye el dir propio; `tasks_texto` pisa el contenido de tasks.md."""
    change_dir = repo / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True, exist_ok=True)
    (change_dir / "tasks.md").write_text(
        tasks_texto if tasks_texto is not None else
        f"# Tareas — {change_id}\n\nestado: {estado}\n\n## Tareas\n- [ ] algo\n", encoding="utf-8")
    requeridos = sdd.artefactos_requeridos(modo)
    for nombre in requeridos:
        (change_dir / nombre).write_text(f"# {nombre} — {change_id}\n\nAprobado.\n", encoding="utf-8")
    aprobaciones = []
    if aprobado:
        for nombre in (requeridos if aprobar is None else aprobar):
            aprobaciones.append({
                "artefacto": nombre,
                "hash": core.hash_lf_v1(change_dir / nombre),
                "algoritmo": "sha256/lf/v1",
                "registrado_utc": core.ahora_utc(),
            })
    autorizadas = list(rutas) + ([f"openspec/changes/{change_id}/**"] if incluir_propio else [])
    control = {
        "schema_version": 1,
        "change_id": change_id,
        "modo": modo,
        "origen": "test",
        "creado_utc": core.ahora_utc(),
        "alcance": {"rutas_autorizadas": autorizadas},
        "aprobaciones": aprobaciones,
        "transiciones": [],
        "sesiones": [],
    }
    if scope_hash is not None:
        control["alcance"]["scope_hash"] = scope_hash
    elif con_hash:
        control["alcance"]["scope_hash"] = scope_amendments.hash_alcance(autorizadas)
    if control_texto is None:
        core.escribir_control(change_dir / "control.json", control)
    else:
        (change_dir / "control.json").write_text(control_texto, encoding="utf-8")
    return change_dir


def _commit_base(repo: Path) -> str:
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return base


def _control_de(repo: Path, change_id: str, base) -> dict:
    control = json.loads((repo / "openspec" / "changes" / change_id / "control.json").read_text(encoding="utf-8"))
    if base is not None:
        control["baseline"] = {"commit": base}
    return control


def _escribir(repo: Path, *nombres: str) -> None:
    for n in nombres:
        destino = repo / n
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text("x = 1\n", encoding="utf-8")


def _pares(hallazgos) -> set:
    return {(h.codigo, h.ubicacion) for h in hallazgos}


def _codigos(hallazgos) -> set:
    return {h.codigo for h in hallazgos}


class _Base(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo()
        self.addCleanup(shutil.rmtree, self.repo, True)


class TestAtribucion(_Base):
    def test_dos_changes_disjuntos_cada_uno_valida_limpio(self):
        _crear_change(self.repo, A, ["a.py"])
        _crear_change(self.repo, B, ["b.py"])
        base = _commit_base(self.repo)
        _escribir(self.repo, "a.py", "b.py")
        hall_a = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        hall_b = scope.evaluar_alcance(self.repo, _control_de(self.repo, B, base))
        self.assertEqual(_pares(hall_a), {("ALCANCE-ATRIBUIDA-OTRO-CHANGE", "b.py")})
        self.assertEqual(_pares(hall_b), {("ALCANCE-ATRIBUIDA-OTRO-CHANGE", "a.py")})
        self.assertEqual(scope.bloqueantes(hall_a), [])
        self.assertIn(f"'{B}'", hall_a[0].mensaje)

    def test_ruta_sin_dueno_es_alcance_ruta(self):
        _crear_change(self.repo, A, ["a.py"])
        _crear_change(self.repo, B, ["b.py"])
        base = _commit_base(self.repo)
        _escribir(self.repo, "huerfana.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertEqual(_pares(hall), {("ALCANCE-RUTA", "huerfana.py")})

    def test_ruta_en_dos_ajenos_es_conflicto(self):
        _crear_change(self.repo, A, ["a.py"])
        _crear_change(self.repo, B, ["comun.py"])
        _crear_change(self.repo, C, ["comun.py"])
        base = _commit_base(self.repo)
        _escribir(self.repo, "comun.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertEqual(_pares(hall), {("ALCANCE-CONFLICTO-CHANGES", "comun.py")})
        self.assertEqual(len(scope.bloqueantes(hall)), 1)

    def test_ruta_propia_y_ajena_es_conflicto(self):
        _crear_change(self.repo, A, ["comun.py"])
        _crear_change(self.repo, B, ["comun.py"])
        base = _commit_base(self.repo)
        _escribir(self.repo, "comun.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertEqual(_pares(hall), {("ALCANCE-CONFLICTO-CHANGES", "comun.py")})

    def test_cadena_ajena_invalida_ruta_sigue_siendo_alcance_ruta(self):
        _crear_change(self.repo, A, ["a.py"])
        dir_b = _crear_change(self.repo, B, ["b.py"])
        (dir_b / "amendments.jsonl").write_text("esto no es json\n", encoding="utf-8")
        base = _commit_base(self.repo)
        _escribir(self.repo, "b.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        codigos = _codigos(hall)
        self.assertIn(("ALCANCE-RUTA", "b.py"), _pares(hall))
        self.assertIn("ALCANCE-OTRO-CHANGE-INVALIDO", codigos)
        self.assertNotIn("ALCANCE-ATRIBUIDA-OTRO-CHANGE", codigos)

    def test_scope_hash_falso_ajeno_es_invalido(self):
        _crear_change(self.repo, A, ["a.py"])
        _crear_change(self.repo, B, ["b.py"], scope_hash="ab" * 32)
        base = _commit_base(self.repo)
        _escribir(self.repo, "b.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertIn(("ALCANCE-RUTA", "b.py"), _pares(hall))
        self.assertIn("ALCANCE-OTRO-CHANGE-INVALIDO", _codigos(hall))
        self.assertNotIn("ALCANCE-ATRIBUIDA-OTRO-CHANGE", _codigos(hall))

    def test_control_ajeno_ilegible(self):
        _crear_change(self.repo, A, ["a.py"])
        dir_b = _crear_change(self.repo, B, ["b.py"])
        base = _commit_base(self.repo)  # legítimo en el baseline; se corrompe después en disco
        (dir_b / "control.json").write_text("{ no es json", encoding="utf-8")
        _escribir(self.repo, "b.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertEqual(_codigos(hall), {"ALCANCE-RUTA", "ALCANCE-OTRO-CHANGE-INVALIDO"})

    def test_change_ajeno_cerrado_o_descartado_no_atribuye(self):
        _crear_change(self.repo, A, ["a.py"])
        _crear_change(self.repo, B, ["b.py"], estado="cerrada")
        _crear_change(self.repo, C, ["c.py"], estado="descartada")
        base = _commit_base(self.repo)
        _escribir(self.repo, "b.py", "c.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertEqual(_pares(hall), {("ALCANCE-RUTA", "b.py"), ("ALCANCE-RUTA", "c.py")})
        self.assertEqual([c for c, _ in scope.otros_changes_activos(self.repo, A)], [])

    def _assert_no_absorbe(self, ajeno_kwargs: dict, rutas_ajeno=("b.py",)):
        _crear_change(self.repo, A, ["a.py"])
        _crear_change(self.repo, B, list(rutas_ajeno), **ajeno_kwargs)
        base = _commit_base(self.repo)
        _escribir(self.repo, "b.py", "otra.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertEqual(_pares(hall), {("ALCANCE-RUTA", "b.py"), ("ALCANCE-RUTA", "otra.py")})

    def test_ajeno_catch_all_no_absorbe(self):
        for patron in ("**", "*", "**/*", "*/**", "*.py"):
            with self.subTest(patron=patron):
                self.setUp()
                self._assert_no_absorbe({}, rutas_ajeno=(patron,))

    def test_ajeno_patrones_invalidos_o_protegidos_no_absorben(self):
        casos = [
            ("./**", "z.py"),
            ("**/x", "x"),
            ("[a-z]*/**", "src/x.py"),
            ("s?c/**", "src/x.py"),
            (".claude/**", ".claude/x.py"),
            ("data/raw/**", "data/raw/x.csv"),
            ("../**", "z.py"),
            (".git/**", ".git/x"),
        ]
        for patron, archivo in casos:
            with self.subTest(patron=patron):
                self.setUp()
                _crear_change(self.repo, A, ["a.py"])
                _crear_change(self.repo, B, [patron])
                base = _commit_base(self.repo)
                # .git/x no se puede escribir en un repo real: se usa un archivo ordinario.
                destino = archivo if not archivo.startswith(".git/") else "z.py"
                _escribir(self.repo, destino)
                hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
                self.assertEqual(_pares(hall), {("ALCANCE-RUTA", destino)})

    def test_ajeno_propuesta_pendiente_no_absorbe(self):
        self._assert_no_absorbe({"estado": "propuesta_pendiente"})

    def test_ajeno_aprobada_diseno_no_absorbe(self):
        self._assert_no_absorbe({"estado": "aprobada_diseño"})

    def test_ajeno_pausada_bloqueada_no_absorbe(self):
        self._assert_no_absorbe({"estado": "pausada_bloqueada"})

    def test_ajeno_sin_scope_hash_no_absorbe(self):
        self._assert_no_absorbe({"con_hash": False})

    def test_ajeno_tasks_ilegible_no_absorbe(self):
        self._assert_no_absorbe({"tasks_texto": "sin estado ni nada\n"})

    def test_ajeno_estado_desconocido_no_absorbe(self):
        self._assert_no_absorbe({"estado": "inventado"})

    def test_ajeno_sin_aprobacion_verificada_no_absorbe(self):
        # Activo, con scope_hash coherente y en baseline, pero `aprobaciones: []`.
        self._assert_no_absorbe({"aprobado": False})

    def test_ajeno_con_proposal_modificado_tras_aprobar_no_absorbe(self):
        _crear_change(self.repo, A, ["a.py"])
        dir_b = _crear_change(self.repo, B, ["b.py"])
        (dir_b / "proposal.md").write_text("# Propuesta cambiada\n", encoding="utf-8")  # hash stale
        base = _commit_base(self.repo)
        _escribir(self.repo, "b.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertEqual(_pares(hall), {("ALCANCE-RUTA", "b.py")})

    def test_ajeno_fabricado_tras_el_baseline_no_absorbe(self):
        # B nace DESPUÉS del baseline de A, con aprobación y scope_hash coherentes: no cuenta.
        _crear_change(self.repo, A, ["a.py"])
        base = _commit_base(self.repo)
        _crear_change(self.repo, B, ["b.py"])
        _escribir(self.repo, "b.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertIn(("ALCANCE-RUTA", "b.py"), _pares(hall))
        self.assertNotIn("ALCANCE-ATRIBUIDA-OTRO-CHANGE", _codigos(hall))
        # Aun commiteado después, sigue sin estar en el baseline.
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "B fabricado")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertIn(("ALCANCE-RUTA", "b.py"), _pares(hall))
        self.assertNotIn("ALCANCE-ATRIBUIDA-OTRO-CHANGE", _codigos(hall))

    def test_ajeno_fabricado_no_genera_conflicto_con_ruta_propia(self):
        _crear_change(self.repo, A, ["a.py"])
        base = _commit_base(self.repo)
        _crear_change(self.repo, B, ["a.py"])
        _escribir(self.repo, "a.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertNotIn("ALCANCE-CONFLICTO-CHANGES", _codigos(hall))

    def test_baseline_ausente_no_atribuye(self):
        _crear_change(self.repo, A, ["a.py"])
        _crear_change(self.repo, B, ["b.py"])
        _commit_base(self.repo)
        _escribir(self.repo, "b.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, None))
        self.assertEqual(_pares(hall), {("ALCANCE-RUTA", "b.py")})

    def test_baseline_ref_invalida_no_atribuye(self):
        _crear_change(self.repo, A, ["a.py"])
        _crear_change(self.repo, B, ["b.py"])
        _commit_base(self.repo)
        _escribir(self.repo, "b.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, "deadbeef" * 5))
        self.assertIn(("ALCANCE-RUTA", "b.py"), _pares(hall))
        self.assertNotIn("ALCANCE-ATRIBUIDA-OTRO-CHANGE", _codigos(hall))
        self.assertIn("ALCANCE-GIT-ILEGIBLE", _codigos(hall))

    def test_ajeno_activo_aprobado_valido_si_atribuye(self):
        for estado in ("aprobada_implementacion", "en_implementacion", "en_verificacion"):
            with self.subTest(estado=estado):
                self.setUp()
                _crear_change(self.repo, A, ["a.py"])
                _crear_change(self.repo, B, ["b.py"], estado=estado)
                base = _commit_base(self.repo)
                _escribir(self.repo, "b.py")
                hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
                self.assertEqual(_pares(hall), {("ALCANCE-ATRIBUIDA-OTRO-CHANGE", "b.py")})

    def test_ajeno_legitimo_editando_sus_artefactos_sigue_atribuyendo(self):
        _crear_change(self.repo, A, ["a.py"])
        dir_b = _crear_change(self.repo, B, ["b.py"])
        base = _commit_base(self.repo)
        (dir_b / "tasks.md").write_text(
            f"# Tareas — {B}\n\nestado: en_verificacion\n\n## Tareas\n- [x] algo\n", encoding="utf-8")
        _escribir(self.repo, "b.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertEqual(_pares(hall), {
            ("ALCANCE-ATRIBUIDA-OTRO-CHANGE", "b.py"),
            ("ALCANCE-ATRIBUIDA-OTRO-CHANGE", f"openspec/changes/{B}/tasks.md"),
        })

    def _hall_a(self, base):
        return scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))

    def test_evasion_reviewer_ajeno_forjado_en_working_tree_no_absorbe(self):
        # B preexiste en el baseline como propuesta sin aprobar; luego se forja en disco: tasks activo,
        # aprobaciones con hash coherente, scope_hash coherente y rutas tools/**.
        _crear_change(self.repo, A, ["a.py"])
        dir_b = _crear_change(self.repo, B, ["b.py"], estado="propuesta_pendiente", aprobado=False)
        base = _commit_base(self.repo)
        forjado = _crear_change(self.repo, B, ["tools/**"])  # reescribe tasks/artefactos/control en disco
        self.assertEqual(forjado, dir_b)
        _escribir(self.repo, "tools/x.py")
        hall = self._hall_a(base)
        self.assertIn(("ALCANCE-RUTA", "tools/x.py"), _pares(hall))
        self.assertNotIn("ALCANCE-ATRIBUIDA-OTRO-CHANGE", _codigos(hall))
        self.assertNotIn("ALCANCE-OTRO-CHANGE-INVALIDO", _codigos(hall))

    def test_modo_completo_solo_proposal_aprobado_en_baseline_no_cuenta(self):
        _crear_change(self.repo, A, ["a.py"])
        _crear_change(self.repo, B, ["b.py"], aprobar=["proposal.md"])
        base = _commit_base(self.repo)
        _escribir(self.repo, "b.py")
        self.assertEqual(_pares(self._hall_a(base)), {("ALCANCE-RUTA", "b.py")})

    def test_modo_abreviado_con_proposal_aprobado_si_cuenta(self):
        _crear_change(self.repo, A, ["a.py"])
        _crear_change(self.repo, B, ["b.py"], modo="abreviado")
        base = _commit_base(self.repo)
        _escribir(self.repo, "b.py")
        self.assertEqual(_pares(self._hall_a(base)), {("ALCANCE-ATRIBUIDA-OTRO-CHANGE", "b.py")})

    def test_ancla_scope_hash_distinta_del_baseline_es_invalido(self):
        _crear_change(self.repo, A, ["a.py"])
        dir_b = _crear_change(self.repo, B, ["b.py"])
        base = _commit_base(self.repo)
        ruta_ctrl = dir_b / "control.json"
        ctrl = json.loads(ruta_ctrl.read_text(encoding="utf-8"))
        ctrl["alcance"]["scope_hash"] = "cd" * 32
        core.escribir_control(ruta_ctrl, ctrl)
        _escribir(self.repo, "b.py")
        hall = self._hall_a(base)
        self.assertIn("ALCANCE-OTRO-CHANGE-INVALIDO", _codigos(hall))
        self.assertIn(("ALCANCE-RUTA", "b.py"), _pares(hall))
        self.assertNotIn("ALCANCE-ATRIBUIDA-OTRO-CHANGE", _codigos(hall))

    def test_ajeno_legitimo_con_enmienda_valida_posterior_atribuye_ruta_nueva(self):
        # (d) B es legítimo en el baseline de A; luego recibe una enmienda de alcance VÁLIDA (cadena real
        # creada con scope_amendments) que agrega `nueva.py`. El alcance efectivo se calcula desde disco,
        # así que `nueva.py` se atribuye a B (informativo); el scope_hash ancla no cambia.
        _crear_change(self.repo, A, ["a.py"])
        dir_b = _crear_change(self.repo, B, ["b.py"])
        base = _commit_base(self.repo)
        ruta_ctrl = dir_b / "control.json"
        control_b = json.loads(ruta_ctrl.read_text(encoding="utf-8"))
        ancla = control_b["alcance"]["scope_hash"]
        estado = scope_amendments.estado_alcance(dir_b, control_b)
        plan = scope_amendments.planificar_enmienda(estado, ["nueva.py"], [], (), lambda r: (r, None))
        self.assertEqual(plan.errores, ())
        scope_amendments.aplicar_enmienda(
            dir_b, plan, motivo="prueba", usuario="tester", fecha="2026-10-13",
            campos_t1={"approval_channel": "console_confirmed", "confirmed_at": "2026-10-13T00:00:00Z",
                       "channel_version": "console/v1"},
            esperado_hash_antes=plan.hash_antes, utc="2026-10-13T00:00:00Z")
        # La cadena es válida y el ancla en disco sigue igual a la del baseline.
        control_b = json.loads(ruta_ctrl.read_text(encoding="utf-8"))
        self.assertEqual(control_b["alcance"]["scope_hash"], ancla)
        self.assertTrue(scope_amendments.estado_alcance(dir_b, control_b).valido)
        _escribir(self.repo, "nueva.py")
        hall = self._hall_a(base)
        self.assertIn(("ALCANCE-ATRIBUIDA-OTRO-CHANGE", "nueva.py"), _pares(hall))
        self.assertNotIn("ALCANCE-OTRO-CHANGE-INVALIDO", _codigos(hall))
        self.assertNotIn("ALCANCE-RUTA", _codigos(hall))
        self.assertEqual(scope.bloqueantes(hall), [])

    def test_baseline_no_hexadecimal_completo_no_atribuye(self):
        _crear_change(self.repo, A, ["a.py"])
        _crear_change(self.repo, B, ["b.py"])
        base = _commit_base(self.repo)
        _escribir(self.repo, "b.py")
        for ref in ("HEAD", base[:12], "master"):
            with self.subTest(ref=ref):
                hall = self._hall_a(ref)
                self.assertNotIn("ALCANCE-ATRIBUIDA-OTRO-CHANGE", _codigos(hall))
                self.assertIn(("ALCANCE-RUTA", "b.py"), _pares(hall))

    def test_ajeno_aprobado_despues_del_baseline_no_atribuye(self):
        _crear_change(self.repo, A, ["a.py"])
        _crear_change(self.repo, B, ["b.py"], estado="propuesta_pendiente", aprobado=False)
        base = _commit_base(self.repo)
        # B se aprueba y activa legítimamente DESPUÉS del baseline de A, incluso commiteado.
        _crear_change(self.repo, B, ["b.py"])
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "B aprobado tras baseline de A")
        _escribir(self.repo, "b.py")
        hall = self._hall_a(base)
        # Nada se atribuye a B: ni b.py ni los artefactos de B modificados tras el baseline.
        self.assertEqual(_pares(hall), {
            ("ALCANCE-RUTA", "b.py"),
            ("ALCANCE-RUTA", f"openspec/changes/{B}/tasks.md"),
            ("ALCANCE-RUTA", f"openspec/changes/{B}/control.json"),
        })

    def test_ajeno_no_activo_no_genera_conflicto_con_el_propio(self):
        _crear_change(self.repo, A, ["comun.py"])
        _crear_change(self.repo, B, ["comun.py"], estado="propuesta_pendiente")
        _crear_change(self.repo, C, ["comun.py"], con_hash=False)
        _crear_change(self.repo, D, ["**"])
        base = _commit_base(self.repo)
        _escribir(self.repo, "comun.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertEqual(hall, [])

    def test_ajeno_no_activo_con_control_ilegible_se_ignora_sin_hallazgo(self):
        _crear_change(self.repo, A, ["a.py"])
        _crear_change(self.repo, B, ["b.py"], estado="pausada_bloqueada", control_texto="{ roto")
        base = _commit_base(self.repo)
        _escribir(self.repo, "b.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertEqual(_codigos(hall), {"ALCANCE-RUTA"})

    def test_ajeno_catch_all_no_genera_conflicto_con_ruta_propia(self):
        _crear_change(self.repo, A, ["a.py"])
        _crear_change(self.repo, B, ["**"])
        base = _commit_base(self.repo)
        _escribir(self.repo, "a.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertEqual(hall, [])

    def test_ajeno_con_otras_rutas_validas_y_catch_all_solo_descarta_el_catch_all(self):
        _crear_change(self.repo, A, ["a.py"])
        _crear_change(self.repo, B, ["**", "src/**"])
        (self.repo / "src").mkdir()
        base = _commit_base(self.repo)
        _escribir(self.repo, "src/x.py", "otra.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertEqual(_pares(hall), {("ALCANCE-ATRIBUIDA-OTRO-CHANGE", "src/x.py"), ("ALCANCE-RUTA", "otra.py")})

    def test_r5_artefactos_del_propio_no_se_atribuyen_a_ajenos(self):
        _crear_change(self.repo, A, ["a.py"])
        _crear_change(self.repo, B, [f"openspec/changes/{A}/**"])
        base = _commit_base(self.repo)
        (self.repo / "openspec" / "changes" / A / "nota.md").write_text("n\n", encoding="utf-8")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertEqual(hall, [])

    def test_r5_ruta_bajo_dir_propio_fuera_del_alcance_propio_es_alcance_ruta(self):
        # El alcance propio NO incluye su dir; un ajeno sí lo cubre: igualmente es ALCANCE-RUTA.
        _crear_change(self.repo, A, ["a.py"], incluir_propio=False)
        _crear_change(self.repo, B, [f"openspec/changes/{A}/**"])
        base = _commit_base(self.repo)
        ruta = f"openspec/changes/{A}/nota.md"
        _escribir(self.repo, ruta)
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertEqual(_pares(hall), {("ALCANCE-RUTA", ruta)})

    def test_sin_change_id_propio_no_consulta_otros(self):
        _crear_change(self.repo, B, ["b.py"])
        base = _commit_base(self.repo)
        _escribir(self.repo, "b.py")
        control = {"alcance": {"rutas_autorizadas": ["a.py"]}, "baseline": {"commit": base}}
        hall = scope.evaluar_alcance(self.repo, control)
        self.assertEqual(_pares(hall), {("ALCANCE-RUTA", "b.py")})

    def test_sin_otros_changes_resultado_identico(self):
        _crear_change(self.repo, A, ["a.py"])
        base = _commit_base(self.repo)
        _escribir(self.repo, "a.py", "fuera.py")
        hall = scope.evaluar_alcance(self.repo, _control_de(self.repo, A, base))
        self.assertEqual(_pares(hall), {("ALCANCE-RUTA", "fuera.py")})

    def test_otros_changes_activos_excluye_propio_y_archive(self):
        _crear_change(self.repo, A, ["a.py"])
        _crear_change(self.repo, B, ["b.py"])
        (self.repo / "openspec" / "archive" / Z).mkdir(parents=True)
        self.assertEqual([c for c, _ in scope.otros_changes_activos(self.repo, A)], [B])

    def test_informativos_constante(self):
        self.assertEqual(scope.CODIGOS_INFORMATIVOS, frozenset({"ALCANCE-ATRIBUIDA-OTRO-CHANGE"}))


class TestGateCierre(_Base):
    """Nivel función (armar transition/archive completos por CLI es desproporcionado): el gate de cierre
    usado por `sdd.transition(..., 'cerrada')` y `archive` filtra con `scope.bloqueantes`."""

    def _armar(self, ajeno_rutas):
        _crear_change(self.repo, A, ["a.py"], estado="en_verificacion", aprobado=False)
        _crear_change(self.repo, B, ajeno_rutas)
        base = _commit_base(self.repo)
        (self.repo / "openspec" / "changes" / A / "verification.md").write_text(
            f"# Verificación — {A}\n\n## Evidencia obtenida\nCorrida real de prueba, output X.\n", encoding="utf-8")
        control = _control_de(self.repo, A, base)
        sdd.session_start(control, minutos=90)
        tasks = self.repo / "openspec" / "changes" / A / "tasks.md"
        return control, tasks

    def _alcance_gate(self, control, tasks):
        hall = sdd._findings_del_gate("cerrada", control, tasks, sdd._sesion_activa(control), self.repo)
        return hall, [h for h in scope.bloqueantes(hall) if h.codigo.startswith("ALCANCE-")]

    def test_informativo_no_bloquea_el_gate_de_cierre(self):
        control, tasks = self._armar(["b.py"])
        _escribir(self.repo, "b.py")
        hall, bloq = self._alcance_gate(control, tasks)
        self.assertIn("ALCANCE-ATRIBUIDA-OTRO-CHANGE", _codigos(hall))
        self.assertEqual(bloq, [])

    def test_conflicto_bloquea_el_gate_de_cierre(self):
        control, tasks = self._armar(["a.py"])
        _escribir(self.repo, "a.py")
        _, bloq = self._alcance_gate(control, tasks)
        self.assertEqual({h.codigo for h in bloq}, {"ALCANCE-CONFLICTO-CHANGES"})


class TestCli(_Base):
    def _validate(self, change_id: str):
        res = subprocess.run(
            [sys.executable, str(DS_GUARD), "validate", "--change-id", change_id, "--json"],
            cwd=str(self.repo), capture_output=True, text=True, encoding="utf-8")
        return res, json.loads(res.stdout)

    def test_validate_atribuida_informativa_exit_0_y_huerfana_exit_1(self):
        _crear_change(self.repo, A, ["a.py"], estado="propuesta_pendiente", aprobado=False)
        _crear_change(self.repo, B, ["b.py"])
        base = _commit_base(self.repo)
        for cid in (A, B):
            ruta = self.repo / "openspec" / "changes" / cid / "control.json"
            control = json.loads(ruta.read_text(encoding="utf-8"))
            control["baseline"] = {"commit": base}
            core.escribir_control(ruta, control)
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "baseline en control")
        _escribir(self.repo, "a.py", "b.py")

        res, payload = self._validate(A)
        codigos = {f["codigo"] for f in payload["findings"]}
        self.assertIn("ALCANCE-ATRIBUIDA-OTRO-CHANGE", codigos, res.stdout)
        self.assertEqual(res.returncode, 0, res.stdout)

        # Sin dueño: bloquea.
        _escribir(self.repo, "huerfana.py")
        res, payload = self._validate(A)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("ALCANCE-RUTA", {f["codigo"] for f in payload["findings"]})


if __name__ == "__main__":
    unittest.main()
