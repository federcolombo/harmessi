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
import sys
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
    "tools/dsguard/skill_contract.py",
    "tools/dsguard/ownership.py",
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
    "tools/datacontracts/core.py",
    "tools/datacontracts/validation.py",
    "tools/datacontracts/evolution.py",
    "tools/autonomy/core.py",
    "tools/autonomy/policy.py",
    "tools/datasources/core.py",
    "tools/datasources/scan.py",
    "tools/datasources/registry.py",
    "tools/datasources/runtime.py",
    "tools/datasources/profile_bridge.py",
    "tools/datasources/file_observer.py",
    "tools/modelquality/core.py",
    "tools/modelquality/validation.py",
    "tools/qualityevidence/core.py",
    "tools/qualityevidence/evidence.py",
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


# --- Frontera managed vs evidence (v0.10 Change 1: 20261008-cross-platform-managed-hashing) ---
# `tools/ds_init/managed_hash.py` es la primitive única de hash de archivos managed. Debe ser
# stdlib-only y solo la usan `tools/ds_init/` y `tools/harmessi/doctor.py`; cards, datasources,
# reporting, ds_profile y dsguard hashean evidencia/pins con sus propios contratos.
RUTA_MANAGED_HASH = "tools/ds_init/managed_hash.py"
CONSUMIDORES_PERMITIDOS_MANAGED_HASH = ("tools/ds_init/", "tools/harmessi/doctor.py")


def _todos_los_imports(ruta_absoluta: Path) -> list:
    """Todos los imports del archivo (incluye anidados en funciones) como tuplas
    `(nivel, nombre_completo)`; `nivel > 0` indica import relativo."""
    arbol = ast.parse(ruta_absoluta.read_text(encoding="utf-8"), filename=str(ruta_absoluta))
    imports: list = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            imports.extend((0, alias.name) for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            base = nodo.module or ""
            if base:
                imports.append((nodo.level, base))
            imports.extend(
                (nodo.level, f"{base}.{alias.name}" if base else alias.name) for alias in nodo.names
            )
    return imports


class TestFronteraManagedHash(unittest.TestCase):
    def test_managed_hash_importa_solo_stdlib(self):
        violaciones = []
        for nivel, nombre in _todos_los_imports(REPO_ORIGEN / RUTA_MANAGED_HASH):
            raiz = nombre.split(".")[0]
            if nivel > 0:
                violaciones.append(f"import relativo: {'.' * nivel}{nombre}")
            elif raiz == "tools" or raiz not in sys.stdlib_module_names:
                violaciones.append(f"no stdlib: {nombre}")
        self.assertEqual(
            violaciones,
            [],
            f"{RUTA_MANAGED_HASH} debe usar solo stdlib (sin tools.* ni imports relativos): {violaciones}",
        )

    def test_ningun_modulo_fuera_de_ds_init_y_doctor_importa_managed_hash(self):
        violaciones = []
        for ruta in sorted((REPO_ORIGEN / "tools").rglob("*.py")):
            relativa = ruta.relative_to(REPO_ORIGEN).as_posix()
            if relativa.startswith(CONSUMIDORES_PERMITIDOS_MANAGED_HASH):
                continue
            partes = relativa.split("/")
            if "tests" in partes[:-1] or partes[-1].startswith("test_"):
                continue  # los tests de la frontera no son módulos de producto
            for _nivel, nombre in _todos_los_imports(ruta):
                if "managed_hash" in nombre.split("."):
                    violaciones.append(f"{relativa} importa '{nombre}'")
        self.assertEqual(
            violaciones,
            [],
            "Frontera managed vs evidence (ARCHITECTURE.md §8.2): solo tools/ds_init/ y "
            f"tools/harmessi/doctor.py pueden importar managed_hash: {violaciones}",
        )


# `tools/dsguard/human_presence.py` es la señal T1 (`console_confirmed`): stdlib-only, sin acoplarse
# a ningún provider, y Cards (vistas de governance) no la importan: no crean ni elevan T1.
RUTA_HUMAN_PRESENCE = "tools/dsguard/human_presence.py"
NOMBRES_PROVIDER = ("claude", "codex", "gemini", "chatgpt", "anthropic")


class TestFronteraHumanPresence(unittest.TestCase):
    def test_human_presence_importa_solo_stdlib(self):
        violaciones = []
        for nivel, nombre in _todos_los_imports(REPO_ORIGEN / RUTA_HUMAN_PRESENCE):
            raiz = nombre.split(".")[0]
            if nivel > 0:
                violaciones.append(f"import relativo: {'.' * nivel}{nombre}")
            elif raiz == "tools" or raiz not in sys.stdlib_module_names:
                violaciones.append(f"no stdlib: {nombre}")
        self.assertEqual(
            violaciones,
            [],
            f"{RUTA_HUMAN_PRESENCE} debe usar solo stdlib (sin tools.* ni imports relativos): {violaciones}",
        )

    def test_human_presence_no_menciona_providers_en_imports(self):
        violaciones = [
            nombre
            for _nivel, nombre in _todos_los_imports(REPO_ORIGEN / RUTA_HUMAN_PRESENCE)
            if any(p in nombre.lower() for p in NOMBRES_PROVIDER)
        ]
        self.assertEqual(
            violaciones,
            [],
            f"{RUTA_HUMAN_PRESENCE} no debe importar módulos de provider: {violaciones}",
        )

    def test_ningun_modulo_de_cards_importa_human_presence(self):
        violaciones = []
        for ruta in sorted((REPO_ORIGEN / "tools" / "cards").glob("*.py")):
            if ruta.name == "approvals.py":
                continue
            for _nivel, nombre in _todos_los_imports(ruta):
                if "human_presence" in nombre.split("."):
                    violaciones.append(f"{ruta.name} importa '{nombre}'")
        self.assertEqual(
            violaciones,
            [],
            "Cards no crean ni elevan T1 (ARCHITECTURE.md §8.3): solo tools/cards/approvals.py "
            f"puede referenciar human_presence: {violaciones}",
        )


# --- Frontera de enmiendas gobernadas (v0.10 Change 3: 20261013-governed-amendments) ---
# `scope_amendments.py` y `guardrails_adoption.py` son stdlib + imports relativos del mismo paquete
# (`from .core import Finding`, `from . import guardrails_drift`). No importan `tools.*`, providers ni
# `human_presence`: reciben `campos_t1` ya resueltos; la primitive de presencia se invoca solo desde
# `tools/ds_guard.py`. Cards/datasources/reporting/ds_profile no los importan.
RUTAS_ENMIENDAS = (
    "tools/dsguard/scope_amendments.py",
    "tools/dsguard/guardrails_adoption.py",
)
NOMBRES_ENMIENDAS = ("scope_amendments", "guardrails_adoption")
DIRS_SIN_ACCESO_A_ENMIENDAS = (
    "tools/cards",
    "tools/datasources",
    "tools/reporting",
    "tools/ds_profile",
)


class TestFronteraEnmiendasGobernadas(unittest.TestCase):
    def test_modulos_de_enmiendas_importan_solo_stdlib_y_paquete(self):
        violaciones = []
        for ruta in RUTAS_ENMIENDAS:
            for nivel, nombre in _todos_los_imports(REPO_ORIGEN / ruta):
                raiz = nombre.split(".")[0]
                if nivel == 1:
                    continue  # import relativo del mismo paquete dsguard
                if nivel > 1:
                    violaciones.append(f"{ruta}: import relativo fuera del paquete: {nombre}")
                elif raiz == "tools" or raiz not in sys.stdlib_module_names:
                    violaciones.append(f"{ruta}: no stdlib: {nombre}")
        self.assertEqual(
            violaciones,
            [],
            f"Los módulos de enmiendas deben usar solo stdlib + imports relativos de dsguard: {violaciones}",
        )

    def test_modulos_de_enmiendas_no_mencionan_providers(self):
        violaciones = [
            f"{ruta}: {nombre}"
            for ruta in RUTAS_ENMIENDAS
            for _nivel, nombre in _todos_los_imports(REPO_ORIGEN / ruta)
            if any(p in nombre.lower() for p in NOMBRES_PROVIDER)
        ]
        self.assertEqual(violaciones, [], f"No deben importar módulos de provider: {violaciones}")

    def test_modulos_de_enmiendas_no_importan_human_presence(self):
        violaciones = [
            f"{ruta}: {nombre}"
            for ruta in RUTAS_ENMIENDAS
            for _nivel, nombre in _todos_los_imports(REPO_ORIGEN / ruta)
            if "human_presence" in nombre.split(".")
        ]
        self.assertEqual(
            violaciones,
            [],
            "Reciben campos_t1 ya resueltos; la presencia T1 se invoca solo desde tools/ds_guard.py "
            f"(ARCHITECTURE.md §8.4): {violaciones}",
        )

    def test_cards_datasources_reporting_ds_profile_no_importan_enmiendas(self):
        violaciones = []
        for directorio in DIRS_SIN_ACCESO_A_ENMIENDAS:
            for ruta in sorted((REPO_ORIGEN / directorio).rglob("*.py")):
                for _nivel, nombre in _todos_los_imports(ruta):
                    if any(n in nombre.split(".") for n in NOMBRES_ENMIENDAS):
                        violaciones.append(f"{ruta.relative_to(REPO_ORIGEN).as_posix()} importa '{nombre}'")
        self.assertEqual(
            violaciones,
            [],
            f"Cards/datasources/reporting/ds_profile no deben importar enmiendas/adopciones: {violaciones}",
        )


# --- Frontera de skills componibles y ownership (v0.10 Change 4: 20261014-composable-skills-writer-semantics) ---
# `skill_contract.py` y `ownership.py` son validadores puros: stdlib + módulos hermanos de `dsguard`
# (import relativo nivel 1), neutrales respecto de proveedores. No hay registry/loader/marketplace
# de skills: el Lead lee los archivos directamente.
RUTAS_SKILLS_OWNERSHIP = (
    "tools/dsguard/skill_contract.py",
    "tools/dsguard/ownership.py",
)
NOMBRES_PROVEEDOR_Y_MENSAJERIA = ("Claude", "Codex", "Gemini", "SendMessage")


class TestFronteraSkillsYOwnership(unittest.TestCase):
    def test_modulos_importan_solo_stdlib_y_hermanos_dsguard(self):
        violaciones = []
        for ruta in RUTAS_SKILLS_OWNERSHIP:
            for nivel, nombre in _todos_los_imports(REPO_ORIGEN / ruta):
                raiz = nombre.split(".")[0]
                if nivel == 1:
                    continue  # import relativo de un módulo hermano de dsguard
                if nivel > 1:
                    violaciones.append(f"{ruta}: import relativo fuera del paquete: {nombre}")
                elif raiz == "tools" or raiz not in sys.stdlib_module_names:
                    violaciones.append(f"{ruta}: no stdlib: {nombre}")
        self.assertEqual(
            violaciones,
            [],
            f"skill_contract/ownership deben usar solo stdlib + hermanos dsguard: {violaciones}",
        )

    def test_modulos_no_contienen_nombres_de_proveedor_ni_sendmessage(self):
        violaciones = []
        for ruta in RUTAS_SKILLS_OWNERSHIP:
            codigo = (REPO_ORIGEN / ruta).read_text(encoding="utf-8")
            for nombre in NOMBRES_PROVEEDOR_Y_MENSAJERIA:
                if nombre in codigo:
                    violaciones.append(f"{ruta} contiene '{nombre}'")
        self.assertEqual(violaciones, [], f"Módulos deben ser neutrales al proveedor: {violaciones}")

    def test_no_existe_registry_loader_ni_marketplace_de_skills(self):
        encontrados = []
        for patron in ("skill_registry*", "skill_loader*", "skill_marketplace*"):
            encontrados.extend(
                p.relative_to(REPO_ORIGEN).as_posix()
                for p in (REPO_ORIGEN / "tools").rglob(patron)
            )
        self.assertEqual(
            encontrados,
            [],
            f"No debe existir registry/loader/marketplace de skills en v0.10: {encontrados}",
        )


if __name__ == "__main__":
    unittest.main()
