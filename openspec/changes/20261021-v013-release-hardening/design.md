# Diseño — 20261021-v013-release-hardening

## Enfoque
Mismo patrón que v0.11/v0.12: marcadores de versión → notas → smoke → baseline una sola vez (último paso de código) → regresión completa → instalación/upgrade/Doctor → dogfood → privacidad → verification.md → commit de release.

## Decisiones
- **Baseline una vez:** `regenerar_control` se ejecuta después de que todo archivo managed esté en su forma final; cualquier edición posterior a managed obliga a repetirlo y se evita.
- **Regresión por módulo con ledger fuera del repo:** serial, foreground, tandas acotadas (máquina con poca memoria); un fallo se corrige y se repite solo ese módulo.
- **Upgrade desde el tag real:** `git archive v0.12.0` a un directorio temporal, instalado con su propio `ds_init`, y luego actualizado con el `ds_init` actual; los archivos de proyecto se verifican por sha256 antes/después.
- **Imports desde el destino:** se ejecuta Python con `-I` y `cwd` en el destino instalado, con `sys.path` limitado a él, para detectar módulos faltantes del manifest.
- **Dogfood de evaluación con adapters falsos:** deterministas y gratuitos; el candidate se modela como una variante del conjunto de skills (superficie Optimizable) en un directorio temporal, sin tocar el harness real; la evidencia que se compara es determinista.
- **Wording de CI:** «workflow presente y validado estructuralmente; ejecución remota no observada».

## Riesgos
Duración de la regresión; falsos positivos del barrido de privacidad (se excluyen los Changes que describen el barrido); sensibilidad de Doctor al árbol sucio.

## No se reabre
Roles, hooks, permisos, T0/T1, contratos de v0.13.

## Decisiones materiales pendientes
Ninguna.
