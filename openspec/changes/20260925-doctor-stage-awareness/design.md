# Diseño — 20260925-doctor-stage-awareness

## Decisión metodológica/técnica

**Fuente canónica reutilizable confirmada**: existe y es suficiente. `tools/ds_init/manifest.py`
ya tiene, para cada uno de los 4 agentes, una `EntradaManifiesto` con `destino` igual a la
`ruta_rel` de `_AGENTES_ESPERADOS` y `stage_minimo="experiment"` explícito (líneas 127-154), y ya
existe `manifest_para_perfil_y_stage(perfil, stage)` (líneas 811-830) que filtra por stage
reusando `manifest_para_perfil`. No hace falta introducir ninguna fuente de verdad nueva; el patrón
a replicar es literalmente el que ya usa `_check_archivos_administrados` (líneas 376-397) para el
mismo problema sobre archivos administrados en general.

**Cambio 1 — firma de `_check_agents`** (`tools/harmessi/doctor.py`, reemplaza líneas 498-539):

```python
def _check_agents(destino: Path, control_data: Optional[dict]) -> list:
```

Firma idéntica en forma a `_check_archivos_administrados(destino: Path, control_data:
Optional[dict]) -> list` (línea 376) — mismo tipo de segundo parámetro, mismo nombre, para que
cualquier lector reconozca el patrón de inmediato.

**Cambio 2 — cuerpo de `_check_agents`**: antes del bucle actual sobre `_AGENTES_ESPERADOS`, se
calcula un `set` de rutas `destino` (relativas) que aplican al `installation_stage` instalado.
Lógica exacta (misma estructura de `if/else`/`try/except` que `_check_archivos_administrados`,
para no introducir un tercer patrón distinto en el mismo archivo):

```python
def _check_agents(destino: Path, control_data: Optional[dict]) -> list:
    """Verifica que los agentes de `_AGENTES_ESPERADOS` que aplican al
    `installation_stage` instalado estén presentes y con el frontmatter
    esperado (Change 20260925-doctor-stage-awareness: consciente de stage,
    mismo patrón que `_check_archivos_administrados`). La aplicabilidad de
    cada agente a un stage se resuelve consultando la fuente de verdad
    existente (`manifest_mod.manifest_para_perfil_y_stage`/
    `manifest_para_perfil` sobre `tools.ds_init.manifest.MANIFEST`, donde
    cada agente ya declara su `stage_minimo`) -- nunca una lista separada de
    agentes-por-stage ni una condición hardcodeada sobre el nombre del stage.
    Un agente que no aplica al stage instalado NO produce ningún
    `CheckResult` (ni PASS, ni FAIL, ni WARN): mismo criterio que un archivo
    administrado de un stage superior en `_check_archivos_administrados`,
    donde esa ausencia esperada tampoco se reporta.

    Comportamiento legacy preservado bit a bit (R5 de `spec.md`): si
    `control_data` es `None`, o no tiene clave `installation_stage`, se
    consideran esperados los 4 agentes de `_AGENTES_ESPERADOS`, exactamente
    como antes de este Change."""
    if control_data is None:
        # Sin control.json legible no se puede determinar perfil/stage --
        # comportamiento legacy: los 4 agentes se consideran esperados.
        destinos_aplicables = {ruta_rel for _, ruta_rel in _AGENTES_ESPERADOS}
    else:
        perfil = control_data.get("perfil")
        installation_stage = control_data.get("installation_stage")
        try:
            if installation_stage is not None:
                # Consciente de stage: un agente de un stage superior al
                # instalado no aplica.
                entradas = manifest_mod.manifest_para_perfil_y_stage(perfil, installation_stage)
            else:
                # Legacy (sin installation_stage en control.json):
                # comportamiento actual -- todo el manifest del perfil.
                entradas = manifest_mod.manifest_para_perfil(perfil)
        except manifest_mod.PerfilDesconocidoError:
            # Perfil desconocido: no se puede filtrar por stage. Ya se
            # reporta aparte en HARMESSI-ARCHIVOS-ESPERADOS -- acá se cae al
            # comportamiento legacy (los 4 agentes esperados) para no dejar
            # de detectar agentes realmente faltantes por un problema no
            # relacionado con este check.
            destinos_aplicables = {ruta_rel for _, ruta_rel in _AGENTES_ESPERADOS}
        else:
            destinos_aplicables = {entrada.destino for entrada in entradas}

    resultados = []
    for nombre, ruta_rel in _AGENTES_ESPERADOS:
        if ruta_rel not in destinos_aplicables:
            continue  # no aplica al stage instalado: ningún resultado (ni PASS/FAIL/WARN)
        ruta = destino / ruta_rel
        if not ruta.exists():
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_FAIL,
                    "HARMESSI-AGENTE-FALTANTE",
                    f"Falta el agente {nombre!r}",
                    subject=ruta_rel,
                )
            )
            continue
        try:
            texto = ruta.read_text(encoding="utf-8")
        except OSError as exc:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_FAIL,
                    "HARMESSI-AGENTE-ILEGIBLE",
                    f"No se pudo leer el agente {nombre!r}: {exc}",
                    subject=ruta_rel,
                )
            )
            continue
        if not texto.startswith("---") or f"name: {nombre}" not in texto:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_WARN,
                    "HARMESSI-AGENTE-FRONTMATTER",
                    f"El agente {nombre!r} no tiene el frontmatter esperado",
                    subject=ruta_rel,
                )
            )
            continue
        resultados.append(
            checks.CheckResult(
                checks.STATUS_PASS, "HARMESSI-AGENTE", f"Agente {nombre!r} presente", subject=ruta_rel
            )
        )
    return resultados
```

Todo el bloque interno del `for` (existencia, lectura, frontmatter, `PASS`) queda **byte a byte
igual** al código actual (líneas 501-538): el único cambio de comportamiento es el `continue`
temprano por `ruta_rel not in destinos_aplicables`, y el cálculo previo de ese set.

**Cambio 3 — call site en `ejecutar()`** (`tools/harmessi/doctor.py:1047`):

```python
resultados += _ejecutar_check(SECCION_HARMESSI, "HARMESSI-AGENTE", _check_agents, destino, control_data)
```

(agrega `control_data` al final, mismo `control_data` ya calculado en la línea 1039 y ya reusado
por `_check_archivos_administrados` en la línea 1044 — no se calcula de nuevo, no se lee
`control.json` dos veces).

**Cambio 4 — tests existentes que rompen por la firma nueva** (`tools/harmessi/tests/test_doctor.py`,
líneas 235-242): los dos tests que llaman a `_check_agents(self.repo)` con un solo argumento deben
pasar a llamar `_check_agents(self.repo, control_data)`, obteniendo `control_data` con
`doctor_mod._leer_control_json(self.repo)` primero (mismo patrón ya usado en
`test_archivos_administrados_ok`, líneas 195-198, del mismo archivo).

**Por qué NO se emite ni siquiera un `N/A` para un agente que no aplica**: la consigna del usuario
plantea esto como una decisión a tomar mirando el caso análogo. `_check_archivos_administrados`
(líneas 403-418) resuelve el caso análogo (archivo de un stage superior) sin emitir absolutamente
ningún `CheckResult` por esa entrada — ni siquiera está en la lista `entradas` que se itera, porque
`manifest_para_perfil_y_stage` ya la excluyó aguas arriba. Replicar ese mismo criterio para
`_check_agents` (excluir vía `continue`, sin generar ningún `CheckResult`) es la opción consistente
con R1-R2 (0 `[ERROR]`) y con no introducir un vocabulario de severidad nuevo (`N/A`) que
`_ejecutar_check`/los tests de conteo de otros checks no esperan. Se decide explícitamente NO
emitir un `N/A` "informativo" por agente no aplicable, para no arriesgar romper el conteo esperado
por tests existentes de `test_doctor.py` que asumen ciertos totales de resultados por sección.

## Target (condicional)

No aplica.

## Features permitidas/prohibidas (condicional)

No aplica.

## Estrategia de split/validación (condicional)

No aplica.

## Leakage risks (condicional)

No aplica — no hay datos, target ni holdout involucrados en este Change.

## Reproducibilidad (opcional)

No aplica (`RANDOM_STATE` no relevante: sin aleatoriedad involucrada). Los tests nuevos que
instalen un scratch en `discovery`/`experiment` reusan el patrón determinista ya existente en
`test_doctor.py` (`_instalar_harness_real_con_stage`, líneas 85-98), sin necesidad de fixtures
nuevas de infraestructura.

## Alternativas descartadas

- **Lista hardcodeada `_AGENTES_POR_STAGE = {"experiment": (...), ...}` dentro de `doctor.py`**:
  descartada explícitamente — duplicaría `stage_minimo` que ya vive en `MANIFEST`, violando R6 y
  el principio de fuente única de verdad; cualquier cambio futuro de `stage_minimo` de un agente en
  `manifest.py` quedaría desincronizado de Doctor si no se recuerda tocar ambos lugares.
- **Condición hardcodeada `if installation_stage == "experiment": ...`**: descartada por la misma
  razón — no generaliza a `production_candidate`/`production` sin repetir la condición, y
  duplicaría lógica que `manifest_para_perfil_y_stage`/`ORDEN_STAGES` ya resuelven de forma
  genérica y acumulativa.
- **Emitir un `CheckResult` de nivel `N/A`/informativo por cada agente no aplicable al stage**:
  descartada — el usuario la dejó como opción a evaluar, pero introduce un vocabulario de severidad
  no usado hoy en ningún otro check de Doctor para este caso exacto (el caso análogo,
  `_check_archivos_administrados`, no lo hace), y arriesga romper aserciones de conteo de otros
  tests de `test_doctor.py` sin ningún beneficio funcional claro (R2 solo exige 0 `ERROR`, no un
  reporte positivo de "no aplica").
- **Filtrar por stage con un `if installation_stage in ("experiment", "production_candidate",
  "production")`**: descartada por ser una forma menos explícita del mismo problema que la
  condición hardcodeada — no reusa `ORDEN_STAGES` ni `manifest_para_perfil_y_stage`, y quedaría
  desincronizada si se agrega un stage nuevo entre `experiment` y `production_candidate` en el
  futuro.

## Riesgos

- **Riesgo de regresión en instalaciones legacy**: mitigado por R5/design — la rama
  `control_data is None` / sin `installation_stage` reproduce exactamente el código anterior (no
  hay ningún cambio de comportamiento observable para esos dos casos, verificado por los tests
  existentes `test_agents_ok`/`test_agents_error_si_falta` una vez adaptados a la firma nueva, más
  el test explícito de legacy sin `installation_stage`).
- **Riesgo de que `manifest_para_perfil_y_stage` lance `ValueError` si `installation_stage` tiene un
  valor fuera de `ORDEN_STAGES`**: mismo riesgo preexistente que ya corre `_check_archivos_administrados`
  hoy sin capturarlo explícitamente (no está envuelto en `try/except ValueError` en el código
  actual) — fuera de alcance de este Change introducir manejo nuevo para ese caso, ya que
  replicamos el patrón existente sin ampliarlo; si `_ejecutar_check` no captura excepciones no
  esperadas, las convierte en `ResultadoCheck` de nivel `ERROR` (contrato ya documentado en el
  docstring del módulo, líneas 12-15), consistente con el resto de checks.
- **Riesgo de que la implementación real termine leyendo `control.json` una segunda vez**: mitigado
  explícitamente en el diseño del call site (Cambio 3): se reusa el `control_data` ya calculado en
  `ejecutar()`, nunca se vuelve a invocar `_leer_control_json` dentro de `_check_agents`.

## Aprobación humana

Ver sección "Aprobación" de `proposal.md` — no se duplica acá.
