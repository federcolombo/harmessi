# Spec — 20260915-checks-engine-foundation

## Requisitos
Ver `proposal.md § Alcance` y `design.md` para el detalle completo. Schema canónico del engine:

```python
@dataclass(frozen=True)
class CheckResult:
    status: str              # "PASS" | "WARN" | "FAIL" | "N/A"
    code: str
    message: str              # obligatorio SIEMPRE (no solo N/A)
    detail: Optional[str] = None
    subject: Optional[str] = None
    kind: str = "check"        # "check" | "technical_error" (ajuste del usuario)
```

Mapeo Doctor: `PASS→"OK"`, `WARN→"WARN"`, `FAIL→"ERROR"`, `subject→ubicacion`. Exit code del
engine: `1` si hay algún `FAIL`, `0` si no — `WARN`/`N/A` nunca afectan el exit code.

## Criterios de aceptación
<!-- checklist o Given/When/Then, verificables -->

**Engine:**
- `ejecutar_checks([(code, fn, args)])` con un check que devuelve `[CheckResult(PASS,...)]` →
  resultado preservado tal cual.
- Con un check que devuelve `[CheckResult(WARN,...)]` → preservado, no bloquea.
- Con un check que devuelve `[CheckResult(FAIL,...)]` → preservado, `hay_bloqueo`/`exit_code` lo
  detectan.
- Con un check que devuelve `[CheckResult(NA,...)]` → preservado, no bloquea, no cuenta como
  PASS ni FAIL.
- `CheckResult(status="N/A", code="X", message="")` (mensaje vacío) → `ValueError` al construir
  (regla universal, no solo N/A).
- Múltiples checks en `registros`: orden de `resultados` preserva el orden de `registros` (y el
  orden interno de cada `list[CheckResult]` devuelta).
- Un check que lanza una excepción NO detiene la ejecución de los checks siguientes en
  `registros` (no short-circuit) — el resultado incluye un
  `CheckResult(FAIL, "{code}-EXCEPCION", "Fallo inesperado ejecutando el check: {exc!r}")` en su
  lugar.
- `contar_por_status([...])` devuelve el conteo correcto por cada uno de los 4 valores.
- `hay_bloqueo([...])` es `True` sii hay al menos un `FAIL`; `False` con solo PASS/WARN/N/A
  (incluso mezclados).
- `exit_code([...])` es `1` sii `hay_bloqueo`, si no `0`.
- `filtrar_por_status([...], "WARN")` devuelve solo los de ese status, preservando orden.
- `CheckResult` es serializable a dict simple (verificable con `dataclasses.asdict` o un
  `to_dict()` propio — decidir en implementación, sin agregar formatters de texto/JSON
  adicionales).
- `status` fuera de `{PASS,WARN,FAIL,N/A}` al construir `CheckResult` → `ValueError`.
- Un check que devuelve `CheckResult(FAIL, ...)` normalmente (sin excepción) → `kind == "check"`
  (default).
- Una excepción inesperada capturada por `ejecutar_checks` → `status == "FAIL"`,
  `kind == "technical_error"`, `code == "{codigo_base}-EXCEPCION"`.
- Ambos casos (`kind="check"` con FAIL, `kind="technical_error"`) bloquean igual —
  `hay_bloqueo`/`exit_code` no distinguen por `kind`, solo por `status`.
- `kind` fuera de `{"check","technical_error"}` al construir `CheckResult` → `ValueError`. La
  serialización a dict conserva `kind`.

**Doctor (retrofit):**
- `doctor.ejecutar(destino)` sigue devolviendo `(list[ResultadoCheck], exit_code)` — mismo tipo,
  mismos campos (`nivel/seccion/codigo/mensaje/ubicacion`) que antes del retrofit.
- Sobre este mismo repo (checkout local de Harmessi), después del retrofit: mismos
  códigos de check, mismos mensajes, mismo agrupamiento CORE/HARMESSI/RUNTIME, mismo orden,
  mismo exit code, y el mismo conteo **27 [OK], 3 [WARN], 0 [ERROR]** que reportó el usuario tras
  Change 3 (verificable corriendo `harmessi doctor` real antes/después del retrofit y comparando
  línea por línea, salvo diferencia explicada por un hallazgo real nuevo).
- Un check individual (ej. `_check_version_python`) devuelve internamente `list[CheckResult]`
  con `status` del vocabulario nuevo — verificable llamándolo directo en un test.
- Si algún `CheckResult` interno tuviera `status="N/A"` (no ocurre hoy, test sintético/mockeado),
  `formatear()` lo muestra como `[N/A]` y agrega un 4to segmento al resumen; con conteo N/A = 0
  (caso real actual), el resumen tiene exactamente el mismo formato de 3 segmentos que hoy
  (`"N [OK], N [WARN], N [ERROR]"`, sin segmento N/A visible).
- `test_doctor.py` existente sigue pasando sin modificar sus aserciones (verificable corriendo la
  suite).

**Manifest:**
- `tools/dsguard/checks.py` tiene entrada VERBATIM en `MANIFEST`.
- Instalación scratch deja `checks.py` presente en destino.
- `harmessi doctor` corrido sobre un destino recién instalado desde cero sigue funcionando (no
  requiere `checks.py` instalado ahí para funcionar, ya que doctor corre desde el checkout
  FUENTE — pero verificar que no se rompe nada si igual está presente).

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Baseline (condicional — modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Métrica primaria (condicional — modeling, evaluation)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Métricas secundarias (opcional)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.
