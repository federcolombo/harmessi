# Diseño — 20261021-v013-contract-inventory-compat

## Inventario como dato + test
El inventario es JSON (máquina) con vista humana mínima. La garantía no es la prosa sino el test que lo compara con el código: subcomandos reales, constantes de versión, rutas. Un contrato no clasificado (una CLI nueva sin entrada) rompe el test, que es el mecanismo barato para «saber qué habrá que congelar».

## Clasificación
- `public-candidate`: lo que un tercero consumiría y que ya tiene versión o test que lo ancle.
- `internal`: de uso interno del harness; puede cambiar sin aviso.
- `experimental`: nuevo o de uso opt-in sin historial (p. ej. conformance de providers, run manifest en su primera versión).
Ninguna clase implica estabilidad v1.0.

## Subcomandos reales
Se extraen sin ejecutar acciones: para CLIs con `_construir_parser`/`build_parser` se importa y se leen los `choices` del subparser; para `ds_guard.py` (parser dentro de `main`), se invoca `--help` por subproceso y se parsea la lista de comandos. Los exit codes son los observados al leer el código y se documentan como «observados», no «garantizados».

## Compatibilidad
Fixtures mínimos y genéricos derivados de la forma de los artefactos de cada release; la verificación contra los tags reales es un refuerzo opcional (skip si el tag no está). Un schema futuro se rechaza donde el contrato ya define ese comportamiento (`load_run`, `SourceObservation`).

## Deprecación
Convención + una primitiva mínima y vacía: valida entradas y emite un warning de formato fijo. Sin decoradores ni framework. Solo-checkout, para no ampliar el manifest instalado sin consumidor real.

## Riesgos
Falsos negativos si una CLI define subcomandos dinámicamente; el test lo señala como fallo explícito para clasificarla a mano.

## No se reabre
Contratos existentes, política de versiones, T0/T1.

## Decisiones materiales pendientes
Ninguna.
