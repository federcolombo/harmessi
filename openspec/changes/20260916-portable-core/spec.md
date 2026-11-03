# Spec — 20260916-portable-core

## Requisitos

### R1 — `ARCHITECTURE.md`
Ya escrito por el Lead directamente (documentación, mismo criterio que `proposal.md`/`design.md` de
cualquier change). Debe reflejar el estado REAL del código (verificado por lectura directa, no
inventado): inventario CORE/ADAPTER, el caso especial de `pathguard.py`, y la deuda de
`hook_presupuesto.py`/`hook_validar_comando.py`/eager-import de `ds_guard.py`/instalador
Claude-específico.

### R2 — `tools/tests/test_architecture_boundaries.py`
Listas fijas `MODULOS_CORE`/`MODULOS_ADAPTER` (rutas relativas, ej. `"tools/dsguard/pathguard.py"`),
derivadas EXACTAMENTE de `ARCHITECTURE.md` §2.1/§2.2 (misma fuente de verdad, sin inventar una
tercera clasificación paralela). Dos checks, mismo patrón `ast.parse` que
`tools/tests/test_manifest_dsguard_parity.py` (reusar ese estilo, no reinventar el parseo de
imports):

1. **Ningún módulo CORE importa un módulo ADAPTER**: para cada archivo en `MODULOS_CORE`, parsear
   sus `import`/`from ... import` de nivel módulo (mismo criterio que
   `test_manifest_dsguard_parity._nombres_importados_de_dsguard`: solo nivel superior, no anidado)
   y verificar que ninguno resuelve a un módulo de `MODULOS_ADAPTER`.
2. **Ningún módulo CORE contiene `sys.stdin` en su código fuente** (test basado en texto, límite
   documentado explícitamente en el docstring del test: no es un analizador semántico, es un grep
   estructurado sobre el código fuente — suficiente para este propósito, ver "no sobreingeniería"
   del brief).

Ambos tests deben FALLAR si alguien agrega en el futuro un import prohibido o una lectura de stdin
directa a un módulo ya clasificado como CORE — protección real contra nuevo acoplamiento, no
decorativa.

Excepción documentada en el propio test: `pathguard.py` se incluye en `MODULOS_CORE` para el check
de imports (no importa nada de `MODULOS_ADAPTER`) y para el check de stdin (no lee stdin) — su
acoplamiento es de *forma de datos*, no de import ni de I/O, así que ninguno de los dos checks
estructurales lo detecta ni necesita excepción especial; el acoplamiento real ya está documentado en
prosa en `ARCHITECTURE.md` §2.3, no es algo que un test de imports/stdin pueda capturar.

### R3 — Sin reestructuración física
Ningún archivo existente se mueve, renombra, ni cambia de import/comportamiento. Cero riesgo de
romper instalaciones existentes.

## Criterios de aceptación
- [ ] `test_architecture_boundaries.py` pasa hoy (documenta el estado real, no un estado aspiracional
      que ya estaría roto).
- [ ] Si se agrega manualmente (a modo de prueba local, no parte del commit) un `import
      hook_rutas` dentro de, por ejemplo, `checks.py`, el test de imports falla — confirmar esto
      como parte de la verificación del Lead antes de cerrar (prueba de que el test realmente
      protege algo, no solo pasa trivialmente).
- [ ] `ARCHITECTURE.md` no contradice el código real (Lead verifica cada afirmación de clasificación
      contra el archivo real antes de cerrar).
- [ ] Suite completa sigue pasando (nada existente se tocó).
