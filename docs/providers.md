# Providers: matriz de soporte y evidencia

Estado: v0.15 (Change `20261026-v015-provider-reality`). Esta página es la fuente publicada del soporte de
providers. Ningún provider figura con un nivel superior a la evidencia registrada acá; un test
(`tools/tests/test_v015_provider_matrix.py`) compara esta matriz con `SOPORTE_DECLARADO` en
`tools/providers/conformance.py`.

## Niveles

Orden: `detected` < `contract-tested` < `locally-smoke-tested` < `live-validated`.

- `detected`: el adapter intenta detectar la CLI (`detect()`); no implica que funcione.
- `contract-tested`: el adapter cumple el contrato de `ProviderAdapter` contra dobles de `shutil.which` y `subprocess.run` (sin red, sin credenciales). No prueba el comportamiento de la CLI real.
- `locally-smoke-tested`: además, `detect()` real encuentra la CLI y obtiene su versión en un host concreto.
- `live-validated`: además, una invocación real mínima terminó con `ok=True` (doble opt-in: `--live` y `HARMESSI_LIVE_PROVIDER=1`).

En el código, `NIVELES_SOPORTE` solo contiene `contract-tested`, `locally-smoke-tested` y `live-validated`; la columna `smoke-tested` de la matriz equivale a `locally-smoke-tested`. `detected` no es un nivel de `NIVELES_SOPORTE`: en la matriz significa que el adapter implementa `detect()`; que la CLI esté realmente instalada en un host concreto solo consta en el registro de evidencia (para `claude_code`, el `smoke_detect_real` del 2026-10-26; en `codex`, `gemini` y `grok` falló en ese host).

## Matriz de soporte

`nivel_declarado` es el valor de `SOPORTE_DECLARADO[provider]["nivel_declarado"]`.

| provider | detected (adapter implementa detect()) | contract-tested | smoke-tested (= locally-smoke-tested) | live-validated | nivel_declarado | limitaciones |
|---|---|---|---|---|---|---|
| `claude_code` | si | si | si | si (host unico) | `live-validated` | validado en un solo host, una version de CLI y Windows; ver registro |
| `codex` | si | si | no | no | `contract-tested` | CLI no verificada en vivo; el adapter ignora model y effort |
| `gemini` | si | si | no | no | `contract-tested` | CLI no verificada en vivo; cubre tambien Gemini/Antigravity |
| `grok` | si | si | no | no | `contract-tested` | CLI no verificada en vivo |

No hay adapter `antigravity`: no existe CLI ni evidencia para él. Gemini/Antigravity se cubre por el adapter
`gemini`, con el mismo nivel `contract-tested`.

## Registro de evidencia live

Cada fila es una evidencia concreta de un nivel `locally-smoke-tested` o `live-validated`. Un provider no puede
declararse en esos niveles sin una fila acá con su `provider` y `nivel`.

| provider | nivel | fecha | os | python | cli_version | comando | resultado |
|---|---|---|---|---|---|---|---|
| `claude_code` | `live-validated` | 2026-10-26 | Windows 11 Pro 10.0.22631 | 3.12.5 | 2.1.310 (Claude Code) | `HARMESSI_LIVE_PROVIDER=1 python -m tools.providers.conformance --smoke --live --json` | nivel_alcanzado=live-validated; smoke_detect_real ok; live_invocacion ok (invocacion real minima con ok=True); 6 chequeos de contrato con dobles ok |

Notas de la corrida (transcripción literal de lo observado el 2026-10-26):

- `claude_code`: `smoke_detect_real` ok con version `2.1.310 (Claude Code)`; `live_invocacion` ok (`invocacion real minima con ok=True`). Usó la sesión ya autenticada del host; no se agregaron credenciales.
- `codex`, `gemini`, `grok`: `nivel_alcanzado=contract-tested`. `smoke_detect_real` con `ok=False` (`CLI no disponible en este host: sin evidencia de smoke`). Para `codex`, `live_invocacion`: `invocacion real fallida (exit=127, error=unavailable)`.
- No se instaló ninguna CLI ni se usaron credenciales adicionales.

### Límites de la evidencia

- Host único (una máquina Windows 11), una sola versión de CLI (`2.1.310`).
- No reproducible en CI: requiere la CLI instalada y una sesión autenticada.
- No cubre otros sistemas operativos ni otras versiones de la CLI.
- No valida la calidad semántica de las respuestas: solo que una invocación mínima terminó con `ok=True`.
- El registro es histórico, no una promesa vigente: una versión nueva de la CLI no queda cubierta hasta repetir la corrida con el comando registrado.

## Límites heurísticos de conformance

El chequeo de `tools/providers/conformance.py` es heurístico y no exhaustivo. Se cerró el falso positivo de
`--model=x` (un modelo pasado como `--flag=modelo` se reconoce como modelo con flag). Siguen sin detectarse, y
quedan documentados como límite conocido (B-09, parcial):

- `communicate` / `stdin.write`: datos enviados por stdin tras crear un proceso no se inspeccionan.
- `os.system` / `os.popen`: lanzamientos por esas vías no pasan por los dobles.
- from-imports: el mapeo de originales depende de que el adapter importe a nivel de módulo.
- `partial` / callables: un `subprocess.run` envuelto en `functools.partial` u otro callable puede eludir el doble.
- Restauración de parches: no hay test que verifique que los parches de los dobles se restauran tras cada chequeo.

Pasar conformance con dobles no garantiza el comportamiento de la CLI real.

## Routing y fallback

- El routing es declarativo y determinista (rol + tipo de tarea, política opcional). No infiere ni optimiza.
- `provider_available` en la decisión de routing es informativo: nunca cambia el `provider_id` resuelto.
- El fallback automático se habilita solo por `availability_error` en `{quota, unavailable, unauthenticated}`
  (`is_fallback_eligible` es la única decisión). Un `ok=False` con `availability_error=None` (error semántico o
  de código) nunca dispara fallback: se propaga tal cual, sin probar otro provider. Aplica igual a los 4 providers.
  Verificado por tests en `tools/fallback/tests/` y `tools/routing/tests/`.

## Provider-neutrality: qué se promete y qué no

- Los 4 adapters implementan el mismo contrato `ProviderAdapter` y pasan conformance con dobles.
- Solo Claude Code está validado en vivo (host único, ver registro). No se afirma equivalencia de comportamiento
  entre providers.
- T2 (canal de aprobación separado / seguridad por provider) queda POST-v1. Razón: exige providers instalados y
  credenciales para validar equivalencia de comportamiento, fuera de lo verificable en este entorno; v1 no lo exige
  porque su criterio es una matriz sin soporte superior a la evidencia.

## Cómo repetir la validación

```
HARMESSI_LIVE_PROVIDER=1 python -m tools.providers.conformance --smoke --live --json
```

La invocación live puede costar dinero y nunca corre por defecto. Al repetirla en otro host o versión, agregar una
fila al registro con fecha, OS, versión de CLI, comando y resultado; no editar las filas existentes.
