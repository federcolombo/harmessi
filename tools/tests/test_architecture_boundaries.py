"""Tests estructurales de la frontera core/adapter documentada en ARCHITECTURE.md (v0.4 Change 3:
20260916-portable-core). Protegen contra acoplamiento nuevo no autorizado: ningún módulo listado
como CORE debe importar un módulo ADAPTER, ni leer stdin directamente (proxy de "está actuando como
un hook", que es responsabilidad exclusiva del adapter). No es un analizador semántico -- es un
escaneo estructurado de imports (ast) + una búsqueda de texto acotada (sys.stdin), documentado como
límite deliberado (ver ARCHITECTURE.md, "no sobreingeniería").

Excepción documentada (ver ARCHITECTURE.md §2.3 y spec.md R2): `tools/dsguard/pathguard.py` se
incluye en `MODULOS_CORE` para ambos checks de abajo -- no importa nada de `MODULOS_ADAPTER` y no
lee stdin, así que ninguno de los dos checks lo marca. Su acoplamiento real es de *forma de datos*
(la función pública espera un `payload` con la forma exacta del JSON de `PreToolUse`), algo que un
escaneo de imports/texto no puede capturar -- queda documentado en prosa en ARCHITECTURE.md, no acá.

Segunda excepción análoga (ver ARCHITECTURE.md §2.3, párrafo "Segundo caso análogo"): `launcher_common.py`
está en `MODULOS_CORE` a pesar de contener `lanzar_hook` (que sí lee `CLAUDE_PROJECT_DIR`, específica
de Claude Code) porque el test de imports/stdin de este archivo escanea a nivel de archivo/import, no
a nivel de función -- no puede detectar que una sola función dentro de un archivo por lo demás neutro
(`resolver_venv_dir`, `ruta_interprete_venv`, `resolver_repo_root`, usadas también por `doctor.py`)
está acoplada al protocolo de hooks. Ese acoplamiento real queda documentado en prosa en
ARCHITECTURE.md §2.3/§4 punto 5, igual que el caso de `pathguard.py`.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]

# Listas derivadas EXACTAMENTE de ARCHITECTURE.md §2.1/§2.2 -- si ARCHITECTURE.md cambia de
# clasificación para algún módulo, estas listas deben actualizarse junto con el doc.
MODULOS_CORE = (
    "tools/dsguard/core.py",
    "tools/dsguard/repo.py",
    "tools/dsguard/checks.py",
    "tools/dsguard/sdd.py",
    "tools/dsguard/scope.py",
    "tools/dsguard/decision.py",
    "tools/dsguard/lifecycle.py",
    "tools/dsguard/kdd.py",
    "tools/dsguard/kdd_compat.py",
    "tools/dsguard/maturity.py",
    "tools/dsguard/readiness.py",
    "tools/dsguard/mlops_foundations.py",
    "tools/dsguard/mlops_evidence.py",
    "tools/dsguard/scientific_validity.py",
    "tools/dsguard/notebooks.py",
    "tools/dsguard/status.py",
    "tools/dsguard/pathguard.py",
    "tools/dsimpact/__init__.py",
    "tools/dsimpact/cli.py",
    "tools/dsimpact/consumers_py.py",
    "tools/dsimpact/consumers_text.py",
    "tools/dsimpact/generic_filter.py",
    "tools/dsimpact/git_source.py",
    "tools/dsimpact/notebooks_source.py",
    "tools/dsimpact/py_changes.py",
    "tools/dsimpact/scan.py",
    "tools/ds_profile/__init__.py",
    "tools/ds_profile/cli.py",
    "tools/ds_profile/column_stats.py",
    "tools/ds_profile/fingerprint.py",
    "tools/ds_profile/io_readers.py",
    "tools/ds_profile/quality_flags.py",
    "tools/ds_profile/report.py",
    "tools/ds_profile/sampling.py",
    "tools/ds_profile/schema.py",
    "tools/ds_profile/holdout_guard.py",
    "tools/reporting/core.py",
    "tools/reporting/governance.py",
    "tools/reporting/cli.py",
    "tools/reporting/profiles/eda.py",
    "tools/reporting/examples/eda_generic.py",
    "tools/reporting/evidence.py",
    "tools/reporting/validation.py",
    "tools/reporting/style.py",
    "tools/reporting/plotly_backend.py",
    "tools/reporting/render_html.py",
    "tools/reporting/publish.py",
    "tools/nbrunner/core.py",
    "tools/nbrunner/execute.py",
    "tools/nbrunner/fsdiff.py",
    "tools/nbrunner/manifest.py",
    "tools/ds_guard.py",
    "tools/harmessi/cli.py",
    "tools/harmessi/doctor.py",
    # Mixto -- ver excepción documentada arriba y ARCHITECTURE.md §2.3: la mayoría de sus funciones
    # (resolver_venv_dir/ruta_interprete_venv/resolver_repo_root) son neutras y usadas por
    # doctor.py; lanzar_hook es adapter pero vive en el mismo archivo (deuda §4 punto 5).
    "tools/launcher_common.py",
)

MODULOS_ADAPTER = (
    "tools/dsguard/hook_rutas.py",
    "tools/dsguard/hook_launcher_rutas.py",
    "tools/dsguard/hook_presupuesto.py",
    "tools/dsguard/hook_launcher_presupuesto.py",
    "tools/nbrunner/hook_validar_comando.py",
    "tools/nbrunner/hook_launcher.py",
)


def _nombre_modulo_de_ruta(ruta_relativa: str) -> str:
    """'tools/dsguard/pathguard.py' -> 'dsguard.pathguard' (para comparar contra los nombres que
    aparecen en sentencias `import`/`from ... import`, que se escriben como 'dsguard.pathguard' o
    'dsguard import pathguard' según el estilo del archivo -- ver abajo cómo se usa). Se descarta el
    prefijo 'tools' (nunca aparece en un import de Python dentro del propio paquete `tools`, que se
    referencia por sus subpaquetes: `dsguard`, `nbrunner`, etc.) y la extensión `.py`."""
    sin_extension = ruta_relativa[:-3] if ruta_relativa.endswith(".py") else ruta_relativa
    partes = sin_extension.split("/")
    if partes and partes[0] == "tools":
        partes = partes[1:]
    return ".".join(partes)


def _imports_nivel_modulo(ruta_absoluta: Path) -> list:
    """Todos los `import x`/`from x import y` de nivel superior (arbol.body, no anidados), devuelve
    una lista de strings con el nombre completo referenciado por cada import: para `import a.b`
    devuelve 'a.b'; para `from a import b` devuelve 'a.b'; para un import relativo sin módulo base
    (`from . import b`) devuelve solo 'b' (no hay módulo base que anteponer). Esta representación
    (dotted-name completo, o el nombre importado a secas si es relativo) es la más simple de comparar
    contra `MODULOS_ADAPTER`: alcanza con mirar el último componente separado por '.' de cada string
    y compararlo contra el nombre de archivo (sin extensión) de cada módulo adapter, sin importar si
    el import fue absoluto, relativo, o con `as`."""
    codigo = ruta_absoluta.read_text(encoding="utf-8")
    arbol = ast.parse(codigo, filename=str(ruta_absoluta))
    imports: list = []
    for nodo in arbol.body:
        if isinstance(nodo, ast.Import):
            imports.extend(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module:
                imports.extend(f"{nodo.module}.{alias.name}" for alias in nodo.names)
            else:
                # `from . import x` / `from .. import x`: sin módulo base explícito, el nombre
                # importado en sí es la referencia relevante.
                imports.extend(alias.name for alias in nodo.names)
    return imports


# Nombres de archivo (sin extensión) de cada módulo adapter, derivados de MODULOS_ADAPTER vía
# `_nombre_modulo_de_ruta` (se usa el último componente del dotted-name resultante). Es la forma
# canónica contra la que se compara cualquier import encontrado en un módulo CORE, sin importar el
# estilo del import (`import dsguard.hook_rutas`, `from dsguard import hook_rutas`, `from . import
# hook_rutas`, todos terminan en el componente 'hook_rutas').
NOMBRES_ADAPTER = frozenset(
    _nombre_modulo_de_ruta(ruta).rsplit(".", 1)[-1] for ruta in MODULOS_ADAPTER
)


class TestNingunCoreImportaAdapter(unittest.TestCase):
    def test_ningun_modulo_core_importa_un_modulo_adapter(self):
        violaciones = []
        for ruta_relativa in MODULOS_CORE:
            ruta_absoluta = REPO_ORIGEN / ruta_relativa
            for nombre_importado in _imports_nivel_modulo(ruta_absoluta):
                componente_final = nombre_importado.rsplit(".", 1)[-1]
                if componente_final in NOMBRES_ADAPTER:
                    violaciones.append(
                        f"{ruta_relativa} importa '{nombre_importado}' "
                        f"(resuelve al módulo adapter '{componente_final}')"
                    )
        self.assertEqual(
            violaciones,
            [],
            "Módulo(s) CORE importando un módulo ADAPTER -- prohibido por ARCHITECTURE.md §3.1 "
            f"('Core nunca importa un módulo adapter'): {violaciones}",
        )


class TestNingunCoreLeeStdinDirectamente(unittest.TestCase):
    def test_ningun_modulo_core_contiene_sys_stdin(self):
        violaciones = []
        for ruta_relativa in MODULOS_CORE:
            ruta_absoluta = REPO_ORIGEN / ruta_relativa
            codigo = ruta_absoluta.read_text(encoding="utf-8")
            if "sys.stdin" in codigo or "stdin.read" in codigo:
                violaciones.append(ruta_relativa)
        self.assertEqual(
            violaciones,
            [],
            "Módulo(s) CORE leyendo stdin directamente -- prohibido por ARCHITECTURE.md §3.1 "
            "('Core ... ni conoce sys.stdin/exit-code-como-decisión'), eso es responsabilidad "
            f"exclusiva del adapter: {violaciones}",
        )


if __name__ == "__main__":
    unittest.main()
