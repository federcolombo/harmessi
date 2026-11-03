"""Generador del fixture real de Data Card v1 del tag v0.14.0 (v0.15, Change evidence-privacy-hardening, T1).

SOLO-CHECKOUT: no se instala en proyectos ni lo corre la suite normal. Los hashes de la Card (pins de
evidencia, `revision_id`) atan contenido, por eso el fixture NO se escribe a mano: se genera con el
CODIGO DEL TAG que lo produjo, no con el checkout actual (docs/versioning.md exige este fixture al
subir el kind_schema_version de la Data Card de 1 a 2).

Uso (desde cualquier directorio):

    git archive v0.14.0 --prefix=tree/ -o v0.14.0.tar     # o: git archive v0.14.0 | tar -x -C <dir>
    mkdir <dir_tree> && tar -x -f v0.14.0.tar -C <dir_tree> --strip-components=1
    python tools/tests/fixtures/compat/generate_datacard_v014.py --tree <dir_tree> --out tools/tests/fixtures/compat/v0_14

(`<dir_tree>` debe ser un directorio nuevo y vacio fuera del repo; el script no escribe en el.)
El script hace `chdir(<dir_tree>)` y antepone el arbol a `sys.path`, de modo que importa `tools.*`
del tag; aborta si el paquete importado no vive en el arbol o si HARNESS_VERSION != "0.14.0".

Receta: helpers de tests del propio tag (`tools.cards.tests.test_datacard`): observacion real
"ventas" persistida en un proyecto temporal, `fuente` + `armar_card` (kind_schema_version=1,
card_id "producto-a", sin `temporality`) y `datacard.write_data_card` con reloj fijo. Copia los bytes
de la Card a `--out/data_card.json` (sin conversion de fin de linea) y escribe
`--out/MANIFEST_data_card.json` con su sha256. NO toca `MANIFEST.json` ni los otros fixtures.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

TAG_ORIGEN = "v0.14.0"
VERSION_ESPERADA = "0.14.0"
RELOJ_FIJO = "2026-10-04T00:00:00Z"
NOMBRE_FIXTURE = "data_card.json"
NOMBRE_MANIFIESTO = "MANIFEST_data_card.json"


def _preparar_arbol(arbol: Path) -> None:
    """Fija cwd y sys.path en el arbol del tag y verifica que `tools` venga de ahi."""
    if not (arbol / "tools" / "cards" / "datacard.py").is_file():
        raise SystemExit(f"--tree no parece un arbol de {TAG_ORIGEN} (falta tools/cards/datacard.py)")
    os.chdir(arbol)
    sys.path.insert(0, str(arbol))
    for nombre in [n for n in sys.modules if n == "tools" or n.startswith("tools.")]:
        del sys.modules[nombre]
    import tools  # noqa: PLC0415
    import tools.cards  # noqa: PLC0415

    # `tools` puede ser namespace package (sin __init__.py): se usa `__path__`.
    raiz_arbol = arbol.resolve()
    for paquete in (tools, tools.cards):
        for entrada in list(paquete.__path__):
            ruta = Path(entrada).resolve()
            if ruta != raiz_arbol and raiz_arbol not in ruta.parents:
                raise SystemExit(f"`{paquete.__name__}` se importo de {ruta}, fuera del arbol {arbol}")
    from tools.ds_init.version import HARNESS_VERSION  # noqa: PLC0415

    if HARNESS_VERSION != VERSION_ESPERADA:
        raise SystemExit(f"HARNESS_VERSION del arbol es {HARNESS_VERSION!r}; se esperaba {VERSION_ESPERADA!r}")


def _importar_test_datacard(arbol: Path):
    """Importa `tools.cards.tests.test_datacard`; si no es importable como paquete, por ruta."""
    try:
        return importlib.import_module("tools.cards.tests.test_datacard")
    except ImportError:
        ruta = arbol / "tools" / "cards" / "tests" / "test_datacard.py"
        spec = importlib.util.spec_from_file_location("test_datacard_v014", ruta)
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = modulo
        spec.loader.exec_module(modulo)
        return modulo


def _generar(arbol: Path, salida: Path) -> str:
    """Genera la Card con codigo del tag y devuelve el sha256 de los bytes copiados."""
    from tools.cards import datacard  # noqa: PLC0415

    td = _importar_test_datacard(arbol)
    with tempfile.TemporaryDirectory(prefix="fixture datacard v014 ") as tmp:
        raiz = Path(tmp)
        obs = td.hacer_obs("ventas")
        td.persistir_obs(raiz, obs)
        f = td.fuente("src-ventas", obs)
        card = td.armar_card([f])
        ruta = datacard.write_data_card(raiz, card, clock=lambda: RELOJ_FIJO)
        datos = Path(ruta).read_bytes()

    contenido = json.loads(datos.decode("utf-8"))
    if contenido.get("kind_schema_version") != 1 or contenido.get("card_kind") != "data_card":
        raise SystemExit(
            f"la Card generada no es data_card v1: card_kind={contenido.get('card_kind')!r}, "
            f"kind_schema_version={contenido.get('kind_schema_version')!r}")
    salida.mkdir(parents=True, exist_ok=True)
    (salida / NOMBRE_FIXTURE).write_bytes(datos)
    return hashlib.sha256(datos).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Genera el fixture de Data Card v1 de v0.14.0 (solo-checkout).")
    parser.add_argument("--tree", required=True, help="Directorio con el arbol de `git archive v0.14.0`.")
    parser.add_argument("--out", required=True, help="Destino del fixture (p. ej. tools/tests/fixtures/compat/v0_14).")
    args = parser.parse_args(argv)

    salida = Path(args.out).resolve()  # resolver antes del chdir al arbol
    arbol = Path(args.tree).resolve()
    _preparar_arbol(arbol)
    sha = _generar(arbol, salida)

    manifiesto = {
        "fixtures": {NOMBRE_FIXTURE: {"sha256": sha}},
        "generador": "tools/tests/fixtures/compat/generate_datacard_v014.py",
        "harmessi_version": VERSION_ESPERADA,
        "tag_origen": TAG_ORIGEN,
    }
    (salida / NOMBRE_MANIFIESTO).write_bytes(
        (json.dumps(manifiesto, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
    print(f"fixture de Data Card de {TAG_ORIGEN} escrito en {salida} ({NOMBRE_FIXTURE} + {NOMBRE_MANIFIESTO})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
