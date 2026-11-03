# Diseño — 20261021-v013-portability-hardening

## dsimpact: la regla es «ausencia esperada por status»
`listar_cambios` ya clasifica cada archivo (added/modified/deleted/renamed). El contenido «antes» existe para todo menos `added`; el «después» existe para todo menos `deleted`. Si el status dice que debe existir y no se puede leer, es evidencia desconocida: se lanza `GitSourceError`, que la CLI ya sabe traducir. No se agrega un subcomando Git (la lista blanca de `dsguard.repo` no cambia): se usa `repo_mod._git(... "show" ...)` ya permitido y se inspecciona `returncode`/`stderr`. El working tree se lee con `read_text(encoding="utf-8", errors="replace")` envuelto: `OSError` ⇒ `GitSourceError`.

## Sección duplicada
Se cuenta el encabezado exacto a nivel de línea ignorando bloques de código y comentarios HTML (mismo criterio que el parser de la traza). Es un hallazgo, no una fusión: la ambigüedad la resuelve el humano/Lead editando `tasks.md`. Las referencias siguen leyéndose de la primera sección para que los demás hallazgos no desaparezcan.

## Consola
Función mínima `_consola_segura()` en cada CLI nueva (sin módulo compartido para no acoplar paquetes): `for s in (sys.stdout, sys.stderr): s.reconfigure(errors="replace")` bajo `try/except (AttributeError, ValueError, OSError)`.

## CI
Un único workflow chico. La lista de tests es explícita (no descubrimiento) para que sea rápida y estable entre OS. No se instala nada salvo `pytest`. Una prueba estructural lee el YAML como texto (sin PyYAML) y verifica invariantes. La ejecución remota no es observable desde acá y no se afirma.

## Portabilidad
`docs/portability.md` es el inventario vivo; el test estático impide que los módulos v0.13 reintroduzcan los patrones fáciles de detectar. El resto de `tools/**` (heredado) se audita y se registra como deuda cuando no se corrige, sin reescrituras masivas.

## Riesgos
Falsos positivos del test estático (se acota a una lista explícita de módulos); tests de symlink/junction dependen de privilegios (skip explícito); el comportamiento de Git con rutas Unicode depende de `core.quotepath` (el repo usa `-z`).

## No se reabre
Roles, hooks, permisos, T0/T1, contrato de `dsguard.repo`.

## Decisiones materiales pendientes
Ninguna.
