"""Ventana de compatibilidad v0.15 (Change 1 `20261026-v015-contract-stabilization`, R1-R3, R5, R10).

Ventana pre-v1: versión actual + 2 menores previas (0.15, 0.14, 0.13), limitada a artefactos con
test. Este módulo:
- ancla la ventana documentada en `docs/versioning.md`;
- lee con los lectores ACTUALES los fixtures reales de v0.14.0 (generados por
  `tools/tests/fixtures/compat/generate_v014.py` con el código del tag, no escritos a mano) y los
  baselines `.ds_init/control.json` reales de v0.13.0 y v0.14.0 (`git show <tag>:...`);
- verifica el rechazo fail-closed de cada lector (campo desconocido, clave ausente, versión no
  soportada, versión ausente);
- ancla las constantes de versión (R10): cambiarlas obliga a tocar este test.

Los fixtures de improve no incluyen `content.md` ni `change.diff`: la propuesta se valida a nivel
`proposal_hash` (ver `test_propuesta_v014_hash_interno`). Sin red.
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from tools.ds_init import control as control_mod
from tools.ds_init import managed_hash
from tools.ds_init.version import HARNESS_VERSION
from tools.harmessi_bench.runmanifest import MANIFEST_VERSION
from tools.harmessi_improve import budget as budget_mod
from tools.harmessi_improve import candidate as candidate_mod
from tools.harmessi_improve import decision as decision_mod
from tools.harmessi_improve import lessons as lessons_mod
from tools.harmessi_improve import policy as policy_mod
from tools.harmessi_improve import probe as probe_mod
from tools.harmessi_improve import promotion as promotion_mod

RAIZ = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "compat"
V014 = FIXTURES / "v0_14"
GENERADOR = FIXTURES / "generate_v014.py"
VERSIONING = RAIZ / "docs" / "versioning.md"
INVENTARIO = RAIZ / "docs" / "contracts" / "inventory.json"

PROBE_ID = "p1"
ARTEFACTOS_IMPROVE = (
    "candidate.json", "probe.json", "decision.json", "proposal.json",
    "lesson.json", "budget_state.json", "policy.json",
)


def _fx(nombre: str) -> dict:
    return json.loads((V014 / nombre).read_text(encoding="utf-8"))


# --- R1: ancla de la ventana en la doc -----------------------------------------------

def _seccion_ventana() -> str:
    texto = VERSIONING.read_text(encoding="utf-8")
    inicio = texto.index("## Ventana de compatibilidad")
    siguiente = texto.find("\n## ", inicio + 1)
    return texto[inicio:] if siguiente == -1 else texto[inicio:siguiente]


def test_ventana_documentada_lista_013_a_015():
    seccion = _seccion_ventana()
    for version in ("0.15", "0.14", "0.13"):
        assert version in seccion, f"la ventana documentada no lista {version}"
    assert "artefactos con test" in seccion
    assert "best-effort" in seccion
    assert "0.11" in seccion and "0.12" in seccion  # salen de la promesa, tratados best-effort


# --- R10: constantes de versión ------------------------------------------------------

def test_constantes_de_version_ancladas():
    # Versión vigente >= 0.15.0: un release posterior (p. ej. 1.0.0) no debe romper este ancla histórica.
    partes = tuple(int(x) for x in HARNESS_VERSION.split("."))
    assert partes >= (0, 15, 0), HARNESS_VERSION
    assert MANIFEST_VERSION == 1
    assert json.loads(INVENTARIO.read_text(encoding="utf-8"))["inventory_version"] == 1
    assert candidate_mod.CANDIDATE_CONTRACT_VERSION == 1
    assert probe_mod.PROBE_CONTRACT_VERSION == 1
    assert decision_mod.DECISION_CONTRACT_VERSION == 1
    assert promotion_mod.PROPOSAL_CONTRACT_VERSION == 1
    assert lessons_mod.LESSON_CONTRACT_VERSION == 1
    assert budget_mod.BUDGET_VERSION == 1
    assert policy_mod.POLICY_VERSION == 1


# --- R3: integridad del MANIFEST y lectura de fixtures v0_14 --------------------------

def test_manifest_de_fixtures_coincide_con_los_archivos():
    manifiesto = _fx("MANIFEST.json")
    assert manifiesto["tag_origen"] == "v0.14.0"
    assert sorted(manifiesto["fixtures"]) == sorted(ARTEFACTOS_IMPROVE)
    for nombre, datos in manifiesto["fixtures"].items():
        # Se normaliza CRLF -> LF: autocrlf de Windows puede alterar los bytes en el checkout.
        crudo = (V014 / nombre).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(crudo).hexdigest() == datos["sha256"], nombre


def test_candidate_v014_se_lee_con_lector_actual():
    datos = _fx("candidate.json")
    cand = candidate_mod.Candidate.desde_dict(datos)
    assert cand.contract_version == 1
    assert cand.candidate_id == datos["candidate_id"]
    assert cand.provenance["harness_version"] == "0.14.0"


def test_probe_v014_se_lee_con_lector_actual():
    datos = probe_mod._validar_probe(_fx("probe.json"), PROBE_ID)
    assert datos["contract_version"] == 1
    # El bloque policy del probe es el fixture policy.json (consistencia de hash interno).
    assert datos["policy"] == _fx("policy.json")
    assert policy_mod.hash_policy(policy_mod.ProbePolicy.desde_dict(datos["policy"])) == datos["policy_hash"]


def test_policy_v014_se_lee_con_lector_actual():
    politica = policy_mod.ProbePolicy.desde_dict(_fx("policy.json"))
    assert politica.a_dict() == _fx("policy.json")


def test_budget_state_v014_se_lee_con_lector_actual():
    datos = budget_mod._validar_estado(_fx("budget_state.json"))
    assert datos["budget_version"] == 1


def test_propuesta_v014_hash_interno():
    datos = _fx("proposal.json")
    assert datos["contract_version"] == 1
    assert promotion_mod._hash_propuesta(datos) == datos["proposal_hash"]
    assert datos["proposal_id"] == datos["candidate_id"]


def _instalar(tmp_path: Path, subruta: str, nombre: str, datos: dict) -> Path:
    """Escribe `datos` en `<tmp>/.harmessi/improvement/<subruta>/<nombre>` y devuelve `<tmp>`."""
    destino = tmp_path / ".harmessi" / "improvement" / subruta
    destino.mkdir(parents=True, exist_ok=True)
    (destino / nombre).write_text(json.dumps(datos, indent=2), encoding="utf-8")
    return tmp_path


def test_decision_v014_se_lee_con_lector_actual(tmp_path):
    datos = _fx("decision.json")
    raiz = _instalar(tmp_path, f"decisions/{PROBE_ID}", "decision.json", datos)
    leida = decision_mod.cargar_decision(raiz, PROBE_ID)  # recomputa decision_hash
    assert leida == datos and leida["contract_version"] == 1


def test_lesson_v014_se_lee_con_lector_actual(tmp_path):
    datos = _fx("lesson.json")
    raiz = _instalar(tmp_path, "lessons", f"{datos['lesson_id']}.json", datos)
    leida = lessons_mod.cargar_lesson(raiz, datos["lesson_id"])  # recomputa lesson_hash e id
    assert leida == datos and leida["contract_version"] == 1


def test_evidencia_de_v014_es_consistente_entre_artefactos():
    decision, lesson, cand = _fx("decision.json"), _fx("lesson.json"), _fx("candidate.json")
    assert lesson["evidence_refs"][0]["decision_hash"] == decision["decision_hash"]
    assert cand["candidate_id"] == decision["candidate_id"] == _fx("proposal.json")["candidate_id"]


# --- R2: rechazo fail-closed por lector ----------------------------------------------------

def _leer_candidate(datos, tmp_path):
    return candidate_mod.Candidate.desde_dict(datos)


def _leer_probe(datos, tmp_path):
    return probe_mod._validar_probe(datos, PROBE_ID)


def _leer_policy(datos, tmp_path):
    return policy_mod.ProbePolicy.desde_dict(datos)


def _leer_budget(datos, tmp_path):
    return budget_mod._validar_estado(datos)


def _leer_decision(datos, tmp_path):
    raiz = _instalar(tmp_path, f"decisions/{PROBE_ID}", "decision.json", datos)
    return decision_mod.cargar_decision(raiz, PROBE_ID)


def _leer_proposal(datos, tmp_path):
    # `change.diff` ficticio: los chequeos de claves y versión ocurren antes del hash del diff.
    candidate_id = _fx("proposal.json")["candidate_id"]  # id del fixture, no del dato mutado
    raiz = _instalar(tmp_path, f"proposals/{candidate_id}", "proposal.json", datos)
    (tmp_path / ".harmessi" / "improvement" / "proposals" / candidate_id / "change.diff").write_bytes(b"")
    return promotion_mod.cargar_propuesta(raiz, candidate_id)


def _leer_lesson(datos, tmp_path):
    raiz = _instalar(tmp_path, "lessons", f"{_fx('lesson.json')['lesson_id']}.json", datos)
    return lessons_mod.cargar_lesson(raiz, _fx("lesson.json")["lesson_id"])


# (nombre, fixture, campo de versión, lector, excepción)
LECTORES = [
    ("candidate", "candidate.json", "contract_version", _leer_candidate, candidate_mod.CandidateCorrupta),
    ("probe", "probe.json", "contract_version", _leer_probe, probe_mod.ProbeCorrupto),
    ("decision", "decision.json", "contract_version", _leer_decision, decision_mod.EvidenciaInvalida),
    ("proposal", "proposal.json", "contract_version", _leer_proposal, promotion_mod.PropuestaInvalida),
    ("lesson", "lesson.json", "contract_version", _leer_lesson, lessons_mod.LessonRechazada),
    ("budget_state", "budget_state.json", "budget_version", _leer_budget, budget_mod.PresupuestoInvalido),
    ("policy", "policy.json", "policy_version", _leer_policy, policy_mod.PolicyInvalida),
]
_IDS = [fila[0] for fila in LECTORES]


def _mensaje(exc) -> str:
    return str(exc.value) + " " + str(getattr(exc.value, "args", ""))


@pytest.mark.parametrize("nombre, fixture, campo, leer, excepcion", LECTORES, ids=_IDS)
def test_campo_desconocido_se_rechaza(nombre, fixture, campo, leer, excepcion, tmp_path):
    datos = _fx(fixture)
    datos["campo_inesperado_v015"] = 1
    with pytest.raises(excepcion) as exc:
        leer(datos, tmp_path)
    if nombre != "lesson":
        assert "claves inesperadas" in _mensaje(exc)


@pytest.mark.parametrize("nombre, fixture, campo, leer, excepcion", LECTORES, ids=_IDS)
def test_clave_ausente_se_rechaza(nombre, fixture, campo, leer, excepcion, tmp_path):
    datos = _fx(fixture)
    ausente = next(clave for clave in sorted(datos) if clave != campo)
    del datos[ausente]
    with pytest.raises(excepcion) as exc:
        leer(datos, tmp_path)
    if nombre != "lesson":
        assert "claves inesperadas" in _mensaje(exc)


@pytest.mark.parametrize("valor", [2, 99, True])
@pytest.mark.parametrize("nombre, fixture, campo, leer, excepcion", LECTORES, ids=_IDS)
def test_version_no_soportada_se_rechaza(nombre, fixture, campo, leer, excepcion, valor, tmp_path):
    datos = _fx(fixture)
    datos[campo] = valor
    with pytest.raises(excepcion) as exc:
        leer(datos, tmp_path)
    if nombre != "lesson":
        assert "no soportada" in _mensaje(exc)


@pytest.mark.parametrize("nombre, fixture, campo, leer, excepcion", LECTORES, ids=_IDS)
def test_version_ausente_se_rechaza(nombre, fixture, campo, leer, excepcion, tmp_path):
    datos = _fx(fixture)
    del datos[campo]
    with pytest.raises(excepcion):
        leer(datos, tmp_path)


def test_lesson_rechazos_llevan_el_codigo_de_corrupta(tmp_path):
    datos = _fx("lesson.json")
    datos["contract_version"] = 2
    with pytest.raises(lessons_mod.LessonRechazada) as exc:
        _leer_lesson(datos, tmp_path)
    assert exc.value.codigo == lessons_mod.LESSON_CORRUPTA


# --- R5: baselines reales de v0.13.0 y v0.14.0 --------------------------------------------------
# Cada baseline es el `.ds_init/control.json` del PROPIO repo de Harmessi en ese tag (`git show`).

@pytest.mark.parametrize("version, harness", [("v0_13", "0.13.0"), ("v0_14", "0.14.0")])
def test_baseline_real_del_tag_se_lee_con_lectores_actuales(version, harness, tmp_path):
    ruta = FIXTURES / version / "ds_init_control.json"
    control = json.loads(ruta.read_text(encoding="utf-8"))
    assert control["harness_version"] == harness
    # Decisión B-02: el baseline no tiene schema_version; se versiona por harness_version + hash_alg.
    assert "schema_version" not in control
    entradas = control_mod._entradas_previas_validas(control)
    assert entradas, "el baseline del tag debe tener entradas válidas"
    for entrada in control["archivos"]:
        assert entrada.get("hash_alg") in managed_hash.ALGORITMOS_CONOCIDOS, entrada.get("ruta", entrada)
    # migrar_hashes (dry-run) lee el baseline instalado sin lanzar y no marca algoritmos desconocidos.
    destino = tmp_path / "proyecto"
    (destino / control_mod.DIR_CONTROL).mkdir(parents=True)
    (destino / control_mod.DIR_CONTROL / control_mod.NOMBRE_ARCHIVO_CONTROL).write_bytes(ruta.read_bytes())
    informe = control_mod.migrar_hashes(destino)
    assert not informe.desconocidas and not informe.migradas
    # Los archivos no existen en el tmp: ninguna entrada puede quedar "ya actual" por contenido;
    # todas se clasifican (no se pierde ninguna). Se acepta cualquier mezcla ya_actuales/no_verificables.
    clasificadas = len(informe.ya_actuales) + len(informe.no_verificables)
    assert clasificadas == len(control["archivos"])


# --- R3: regeneración estructural contra el tag (skip si falta) ----------------------------------

def _git(*argumentos: str):
    if shutil.which("git") is None:
        pytest.skip("git no está disponible")
    return subprocess.run(["git", *argumentos], cwd=str(RAIZ), capture_output=True, timeout=120)


def test_regeneracion_estructural_contra_el_tag_v014(tmp_path):
    if _git("rev-parse", "-q", "--verify", "refs/tags/v0.14.0^{commit}").returncode != 0:
        pytest.skip("el tag v0.14.0 no existe localmente")
    archivo = _git("archive", "--format=tar", "v0.14.0")
    if archivo.returncode != 0:
        pytest.skip("git archive v0.14.0 falló")
    tar_ruta = tmp_path / "v0.14.0.tar"
    tar_ruta.write_bytes(archivo.stdout)
    arbol = tmp_path / "arbol"
    arbol.mkdir()
    with tarfile.open(tar_ruta) as tar:
        tar.extractall(arbol)  # noqa: S202 - archivo propio generado por git archive local
    salida = tmp_path / "generado"
    # `-I`: aislado; el generador antepone el árbol del tag a sys.path.
    resultado = subprocess.run(
        [sys.executable, "-I", str(GENERADOR), "--tree", str(arbol), "--out", str(salida)],
        capture_output=True, timeout=600,
    )
    assert resultado.returncode == 0, resultado.stderr.decode("utf-8", errors="replace")
    for nombre in ARTEFACTOS_IMPROVE:
        committeado = json.loads((V014 / nombre).read_text(encoding="utf-8"))
        generado = json.loads((salida / nombre).read_text(encoding="utf-8"))
        # Estructura, no bytes: claves de primer nivel y campos de versión (los hashes y timestamps varían).
        assert sorted(generado) == sorted(committeado), nombre
        for campo in ("contract_version", "budget_version", "policy_version"):
            assert generado.get(campo) == committeado.get(campo), f"{nombre}:{campo}"
    assert json.loads((salida / "MANIFEST.json").read_text(encoding="utf-8"))["tag_origen"] == "v0.14.0"


def test_los_fixtures_committeados_no_se_mutan_en_memoria():
    # Guarda: los tests de rechazo mutan copias, nunca el dict cacheado (cada _fx relee del disco).
    a = _fx("candidate.json")
    b = copy.deepcopy(a)
    a["campo_inesperado_v015"] = 1
    assert "campo_inesperado_v015" not in _fx("candidate.json") and "campo_inesperado_v015" not in b
