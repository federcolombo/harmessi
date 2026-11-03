"""Generador de fixtures reales de contratos `harmessi_improve` del tag v0.14.0 (v0.15 Change 1, T5).

SOLO-CHECKOUT: no se instala en proyectos ni lo corre la suite normal. Los hashes internos de los
contratos improve (candidate_id, policy_hash, decision_hash, proposal_hash, lesson_hash) atan el
contenido, por eso los fixtures NO se escriben a mano: se generan con el CODIGO DEL TAG que los
produjo, no con el checkout actual.

Uso (desde cualquier directorio):

    git archive v0.14.0 --prefix=tree/ -o v0.14.0.tar     # o: git archive v0.14.0 | tar -x -C <dir>
    mkdir <dir_tree> && tar -x -f v0.14.0.tar -C <dir_tree> --strip-components=1
    python tools/tests/fixtures/compat/generate_v014.py --tree <dir_tree> --out tools/tests/fixtures/compat/v0_14

(`<dir_tree>` debe ser un directorio nuevo y vacio fuera del repo; el script no escribe en el.)
El script hace `chdir(<dir_tree>)` y antepone el arbol a `sys.path`, de modo que importa
`tools.*` del tag y no del checkout actual; aborta si el paquete importado no vive en el arbol.

Flujo (con `crear_repo` y `FakeAdapter` del propio arbol, sin red): candidate create -> probe
(repeats=2) -> decide --apply -> promote propose -> lesson add. Copia a `--out` los artefactos
`candidate.json`, `probe.json`, `decision.json`, `proposal.json`, `lesson.json`,
`budget_state.json` y `policy.json` (este ultimo es el bloque `policy` de `probe.json`, que es lo
que lee `ProbePolicy.desde_dict`), y escribe `MANIFEST.json` con el tag de origen y el sha256 de
cada fixture. El repo de trabajo es temporal; el arbol y el checkout no se modifican.

Campos volátiles: `candidate.created_utc` y `budget_state.started_utc` usan el reloj real (no
reproducibles); `policy.json` es DERIVADO (bloque `policy` de `probe.json`), no un archivo del tag.
Los sha256 de `MANIFEST.json` son por tanto específicos de la corrida que generó los fixtures.

Determinismo: contenido y reloj (`ahora`) fijos; quedan volatiles solo los campos propios del
probe (timestamps de corrida, run ids). Los tests comparan estructura (claves y versiones), no
bytes. Los archivos se escriben tal cual (bytes), sin conversion de fin de linea.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

TAG_ORIGEN = "v0.14.0"
VERSION_ESPERADA = "0.14.0"
CHANGE_ID = "20261023-fixture-compat"
SUITE_ID = "suite-fake"
PROBE_ID = "p1"
AHORA = datetime(2026, 10, 23, 14, 0, tzinfo=timezone.utc)
FIXTURES = (
    "candidate.json", "probe.json", "decision.json", "proposal.json",
    "lesson.json", "budget_state.json", "policy.json",
)


def _preparar_arbol(arbol: Path) -> None:
    """Fija cwd y sys.path en el arbol del tag y verifica que `tools` venga de ahi."""
    if not (arbol / "tools" / "harmessi_improve").is_dir():
        raise SystemExit(f"--tree no parece un arbol de {TAG_ORIGEN} (falta tools/harmessi_improve)")
    os.chdir(arbol)
    sys.path.insert(0, str(arbol))
    for nombre in [n for n in sys.modules if n == "tools" or n.startswith("tools.")]:
        del sys.modules[nombre]
    import tools  # noqa: PLC0415
    import tools.harmessi_improve  # noqa: PLC0415

    # `tools` es un namespace package (sin __init__.py): `__file__` es None, se usa `__path__`.
    # Cada entrada debe ser el propio `<arbol>/tools` (o estar dentro del arbol).
    raiz_arbol = arbol.resolve()
    for paquete in (tools, tools.harmessi_improve):
        for entrada in list(paquete.__path__):
            ruta = Path(entrada).resolve()
            if ruta != raiz_arbol and raiz_arbol not in ruta.parents:
                raise SystemExit(f"`{paquete.__name__}` se importo de {ruta}, fuera del arbol {arbol}")
    from tools.ds_init.version import HARNESS_VERSION  # noqa: PLC0415

    if HARNESS_VERSION != VERSION_ESPERADA:
        raise SystemExit(f"HARNESS_VERSION del arbol es {HARNESS_VERSION!r}; se esperaba {VERSION_ESPERADA!r}")


def _correr_flujo(raiz: Path, aux: Path) -> None:
    """Ejecuta el flujo real del tag sobre `raiz` (repo sintetico temporal)."""
    from tools.harmessi_bench.core import EvalTarget
    from tools.harmessi_improve import candidate as cand
    from tools.harmessi_improve import decision as dec
    from tools.harmessi_improve import lessons as les
    from tools.harmessi_improve import probe as pr
    from tools.harmessi_improve import promotion as pm
    from tools.harmessi_improve.policy import ProbePolicy
    from tools.harmessi_improve.tests._fakes import MARCA_BASE, MARCA_CAND, FakeAdapter, crear_suite
    from tools.harmessi_improve.tests._helpers import ACTIVO, PROVENANCE, crear_change, crear_repo

    crear_repo(raiz)
    (raiz / ACTIVO).write_bytes(f"# Skill\n{MARCA_BASE}\n".encode("utf-8"))
    suite = crear_suite(aux, SUITE_ID)
    contenido = f"# Skill\n{MARCA_CAND}\nvariante\n"
    adapter = FakeAdapter("tok-1", "tok-1 tok-2 tok-3")  # baseline 1/3, candidate 3/3

    c = cand.crear_candidate(raiz, ACTIVO, contenido, "la variante mejora el orden", dict(PROVENANCE))
    pr.ejecutar_probe(raiz, c.candidate_id, suite, adapter, EvalTarget("fake", model="m1", effort="low"),
                      ProbePolicy(repeats=2), PROBE_ID, ahora=AHORA)
    d = dec.decidir(raiz, PROBE_ID)
    dec.aplicar_decision(raiz, PROBE_ID, ahora=AHORA)
    pm.proponer_promocion(raiz, c.candidate_id)
    crear_change(raiz, "h", change_id=CHANGE_ID)  # Change abierto FALSO: solo habilita lesson add
    refs = [{"probe_id": PROBE_ID, "decision_hash": d["decision_hash"], "suite_id": SUITE_ID}]
    les.crear_lesson(raiz, CHANGE_ID, pattern="Las variantes con pasos numerados mejoran el seguimiento",
                     recommendation="Preferir pasos numerados", contexts=["python-debugging"],
                     evidence_refs=refs, ahora=AHORA)


def _unico(directorio: Path, patron: str) -> Path:
    encontrados = sorted(directorio.glob(patron))
    if len(encontrados) != 1:
        raise SystemExit(f"se esperaba 1 archivo para {patron!r} en {directorio}, hay {len(encontrados)}")
    return encontrados[0]


def _copiar_fixtures(raiz: Path, salida: Path) -> dict:
    imp = raiz / ".harmessi" / "improvement"
    origenes = {
        "candidate.json": _unico(imp / "candidates", "*/candidate.json"),
        "probe.json": imp / "probes" / PROBE_ID / "probe.json",
        "decision.json": imp / "decisions" / PROBE_ID / "decision.json",
        "proposal.json": _unico(imp / "proposals", "*/proposal.json"),
        "lesson.json": _unico(imp / "lessons", "*.json"),
        "budget_state.json": imp / "budget_state.json",
    }
    salida.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for nombre, origen in origenes.items():
        datos = origen.read_bytes()
        (salida / nombre).write_bytes(datos)
        hashes[nombre] = hashlib.sha256(datos).hexdigest()
    # policy: bloque `policy` del probe, serializado igual que el resto de artefactos del tag.
    politica = json.loads(origenes["probe.json"].read_text(encoding="utf-8"))["policy"]
    datos = (json.dumps(politica, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    (salida / "policy.json").write_bytes(datos)
    hashes["policy.json"] = hashlib.sha256(datos).hexdigest()
    return {nombre: hashes[nombre] for nombre in FIXTURES}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Genera fixtures de compat de v0.14.0 (solo-checkout).")
    parser.add_argument("--tree", required=True, help="Directorio con el arbol de `git archive v0.14.0`.")
    parser.add_argument("--out", required=True, help="Destino de los fixtures (p. ej. tools/tests/fixtures/compat/v0_14).")
    args = parser.parse_args(argv)

    salida = Path(args.out).resolve()  # resolver antes del chdir al arbol
    arbol = Path(args.tree).resolve()
    _preparar_arbol(arbol)

    with tempfile.TemporaryDirectory(prefix="fixtures v014 ") as tmp, \
            tempfile.TemporaryDirectory(prefix="suite v014 ") as tmp_aux:
        raiz = Path(tmp) / "repo"
        raiz.mkdir()
        _correr_flujo(raiz, Path(tmp_aux))
        hashes = _copiar_fixtures(raiz, salida)

    manifiesto = {
        "tag_origen": TAG_ORIGEN,
        "harmessi_version": VERSION_ESPERADA,
        "generador": "tools/tests/fixtures/compat/generate_v014.py",
        "fixtures": {nombre: {"sha256": hashes[nombre]} for nombre in sorted(hashes)},
    }
    (salida / "MANIFEST.json").write_bytes(
        (json.dumps(manifiesto, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
    print(f"fixtures de {TAG_ORIGEN} escritos en {salida} ({len(hashes)} archivos + MANIFEST.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
