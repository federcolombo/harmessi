# Diseño — 20260915-progressive-capability-installation-and-scaffold

## Decisión metodológica/técnica

### 1. Qué es realmente un "bundle" en este codebase (hallazgo de auditoría, no una elección)
`tools/ds_guard.py` importa TODO `tools/dsguard/*.py` a nivel de módulo, incondicionalmente
(línea 34-46). `.claude/settings.json` (un único archivo `MERGE`) conecta los 3 hooks
`PreToolUse` sin relación con stage. Ambos hechos, verificados por lectura directa, implican que
subdividir el CÓDIGO RUNTIME (`tools/`) por stage requeriría inventar imports condicionales/
perezosos en `ds_guard.py` y/o un `settings.json` parametrizado por stage — ambas cosas son
"ruptura arquitectónica"/"feature flags framework", explícitamente prohibidas por el usuario
(§22). Conclusión: los bundles de este change son agentes + docs de referencia de la skill +
(nuevo) 2 docs de scaffold — el código Python permanece SIEMPRE completo, en TODOS los stages.
Esto no contradice el principio "installation capabilities describen qué componentes físicos
están instalados": los componentes que varían progresivamente en esta versión del harness son
los de nivel "capability humana/agente", no los de nivel "librería interna" — coherente con que
el propio brief describe el contenido de cada bundle en términos de agentes/guardrails/docs, no
de módulos `.py` sueltos.

### 2. `stage_minimo` como campo aditivo del manifiesto, sin reescribir su forma
Se agrega `stage_minimo: str = "discovery"` a `EntradaManifiesto` (dataclass frozen, default
preserva cualquier construcción existente). Se descarta un manifiesto paralelo por stage (4
manifiestos completos) — el usuario pidió explícitamente "un catálogo canónico + metadata de
bundle/stage mínimo, evitar duplicar cuatro manifests completos" (§16). `manifest_para_perfil`
(usado hoy por `doctor.py`, `planner.py`, `check_manifest_parity.py`, tests) NO se toca — se
agrega `manifest_para_perfil_y_stage(perfil, stage)` como una función nueva y estrictamente
aditiva (filtra el resultado de `manifest_para_perfil` por `stage_minimo`), de forma que ningún
caller existente necesita cambiar una sola línea.

### 3. `construir_plan`/`writer.instalar` con `stage` opcional, nunca obligatorio
Ambas funciones ganan la capacidad de usar el manifiesto filtrado, activada solo si se les pasa
`stage` (o `config["stage"]`). Cuando no se pasa, el comportamiento es IDÉNTICO al actual —
invariante dura para no romper ningún test/caller existente que instale sin noción de stage.

### 4. `sync` reusa el mecanismo de instalación existente, no inventa uno nuevo
El planner YA trata cualquier destino existente como "omitir, nunca sobrescribir"
(`planner._accion_para_entrada`, `ACCION_OMITIR_EXISTENTE`) para todo lo que no sea `MERGE`/
`CLAUDE.md`. Esto significa que "instalar el bundle target sobre un destino que ya tiene el
bundle base" produce automáticamente el comportamiento correcto de `sync` (agrega solo el delta,
nunca toca lo existente) SIN escribir ninguna lógica de diffing nueva — `sync` es, en esencia,
"correr el instalador de nuevo pidiendo un stage mayor, sobre un destino ya instalado". Se
descartó explícitamente escribir un comparador de conjuntos custom (`instalado` vs `requerido`)
porque el planner ya resuelve exactamente ese problema por construcción.

### 5. `control.json` tras `sync`: por qué hace falta un `regenerar_control` posterior
`writer.instalar` arma `archivos_aplicados` a partir de `entradas_journal` — que en una corrida
de `sync` contiene SOLO el delta (las entradas omitidas por ya existir nunca entran al journal).
Si se usara ese `archivos_aplicados` tal cual para `generar_control`, el `control.json` resultante
solo listaría los archivos de ESTA corrida, perdiendo el registro (y por lo tanto la capacidad de
detectar drift) de los archivos instalados en corridas anteriores — un bug real, no cosmético.
Se decidió NO tocar `writer.instalar` (que ya está bien probado, bajo riesgo cero de cambiarlo)
y en cambio hacer que la orquestación de `sync` llame, inmediatamente después de un
`writer.instalar` exitoso, a `control.regenerar_control(destino, control_recién_escrito,
perfil=perfil, stage=target, installation_stage=target)` — que YA recalcula `archivos` desde el
manifiesto vigente completo (ahora filtrado por `stage` si se pasa), releyendo los hashes reales
de TODOS los archivos presentes en disco (los de antes + los recién agregados), sin depender de
qué se aplicó en qué corrida. Esto reusa una función ya existente y ya testeada
(`regenerar_control`), extendida de forma aditiva.

### 6. Inferencia legacy: solo dos estados distinguibles con confianza
No hay señal en archivos pre-Change-7 para distinguir `experiment`/`production_candidate`/
`production` entre sí — todas las instalaciones anteriores a este change instalaban el 100% del
manifiesto de su época (`incluye_todo: true`, sin concepto de stage). La única distinción real
posible es "¿tiene los archivos que ahora se re-etiquetan `experiment` (agentes +
decision-ledger.md)?" — si sí, se asume el máximo compatible (`"production"`, tal como pide
`design.md`/brief §15: "inferir/calibrar como el stage físico equivalente más alto compatible");
si no (escenario atípico, instalación manualmente podada), `"discovery"` (piso conservador, nunca
sobre-reclama). Se descartó una heurística más fina (p. ej. "si existe algún archivo relacionado
con MLOps, asumir production_candidate") por ser exactamente el tipo de inferencia frágil basada
en señales débiles que el usuario pidió evitar explícitamente (§15: "no hacer una inferencia
frágil basada en un único archivo").

### 7. `legacy.py` como módulo nuevo, pequeño, de `ds_init` (no de `dsguard`)
La inferencia opera sobre archivos del INSTALADOR (`ds_init`), no sobre estado de madurez — vive
naturalmente en `tools/ds_init/`, junto a `manifest.py`/`control.py`, no en `tools/dsguard/`. No
se instala en ningún destino (como el resto de `tools/ds_init/`, es tooling del propio repo
Harmessi, nunca contenido del manifiesto instalable).

### 8. Doctor: fallback exacto a comportamiento legacy, nunca "casi igual"
`_check_archivos_administrados` usa el manifiesto filtrado por `installation_stage` SOLO si esa
clave existe en `control_data`; si no, usa `manifest_para_perfil(perfil)` sin filtrar — el mismo
código exacto que corre hoy. Esto garantiza que CUALQUIER instalación legacy (incluido este
propio repositorio Harmessi) vea EXACTAMENTE el mismo Doctor que antes de este change, sin
necesidad de correr ninguna migración explícita primero — la migración (`sync`) es opcional y
solo necesaria para quien realmente quiera que `installation_stage` quede persistido.

### 9. `HARMESSI-INSTALLATION-STAGE` como check nuevo y acotado, no unified status
Un único `CheckResult` adicional bajo `SECCION_HARMESSI`, con su propio código, que no cambia el
formato ni el agrupamiento de Doctor. Nunca `ERROR`/`FAIL` (regla explícita del usuario) — a
diferencia del resto de checks críticos de Doctor, este es deliberadamente "informativo con un
solo nivel de warning", porque `installation_stage` desalineado no es un problema de integridad
de la instalación (nada está roto), es una oportunidad de sincronizar.

### 10. Scaffold de `production_candidate`/`production`: solo documentación, nunca placeholders de
datos
Se decidió NO crear directorios/archivos placeholder para packaging/inference contract/inference
tests/trazabilidad fuerte/deployment/CI-CD/monitoring/etc. — cualquier archivo así corre el
riesgo real de confundirse con evidencia (aun sin registrarse como `artifact_evidence`, un
archivo llamado `contracts/inference_contract.md` vacío es exactamente el tipo de "placeholder
vacío" que el usuario pidió evitar, §14). En cambio, cada bundle nuevo agrega un único documento
de referencia de la skill (`production-readiness.md`/`operations.md`) que EXPLICA los gates
correspondientes y CÓMO registrar evidencia real — mismo tratamiento (`PLANTILLA`, sourced desde
un `.tmpl` nuevo) que `eda.md`/`kdd.md`/`decision-ledger.md` ya existentes.

### 11. CLI: positional `accion` con default, nunca subparsers obligatorios
Se agrega `accion` como el PRIMER argumento posicional de `cli.py`, `nargs="?"`, `default="install"`,
`choices=["install","sync"]`. Cualquier invocación existente (`python -m tools.ds_init --destino X
--nombre Y ...`, sin ese posicional) sigue funcionando exactamente igual porque argparse resuelve
el default sin que el usuario deba escribirlo. Se descartó `argparse.add_subparsers` (el patrón
que usa `ds_guard.py`) porque convertir el comando en subcomandos obligatorios rompería CUALQUIER
invocación existente que no incluya un subcomando explícito — script de instalación, README,
tests — violando la invariante dura de backward compatibility (R14). `--nombre`/
`--notebooks-dir`/`--venv-dir`/`--integrar-claude` pasan a `required=False` en el parser (para no
forzarlos en `sync`) y se validan a mano en `main()` según `args.accion` — patrón estándar de
argparse para flags condicionalmente requeridos.

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica.

## Alternativas descartadas
- Subdividir `tools/dsguard/*.py`/`tools/nbrunner/*.py` por stage con imports condicionales en
  `ds_guard.py` — rechazada, ver punto 1: requeriría un mecanismo de import perezoso/plugin,
  explícitamente prohibido (§22), y `settings.json` sigue conectando los hooks globalmente de
  todas formas, así que el ahorro real sería nulo (el hook de `nbrunner` seguiría exigiendo esos
  archivos siempre presentes).
- Cuatro manifiestos completos separados (uno por stage) — rechazada, ver punto 2: duplicación
  explícitamente pedida evitar por el usuario (§16).
- Reescribir `writer.instalar` para que `archivos_aplicados` siempre sea el set acumulado
  completo (no solo el delta) — rechazada, ver punto 5: tocar el corazón de `writer.py` (ya
  probado, con rollback delicado) para un caso de uso nuevo es más riesgoso que orquestar
  `regenerar_control` como paso posterior explícito, reusando código ya existente.
- Inferencia legacy de grano fino (intentar adivinar `experiment` vs `production_candidate` vs
  `production` a partir de heurísticas indirectas) — rechazada, ver punto 6: no hay señal
  confiable, y el usuario pidió explícitamente no inventar una inferencia frágil.
- Crear scaffold de archivos placeholder reales para packaging/inference contract/deployment/etc.
  — rechazada, ver punto 10: riesgo de confundirse con evidencia real, contradice §14/§20 del
  brief.
- `argparse.add_subparsers` obligatorio para `install`/`sync` — rechazada, ver punto 11: rompería
  la invocación plana actual, viola R14 (invariante dura de backward compatibility).
- Mover `project_stage` a `.ds_init/control.json` o `installation_stage` a `.harmessi/
  project.json` — rechazada explícitamente por el usuario (§10/§11): son ejes ortogonales por
  diseño, cada uno vive en su archivo de siempre.

## Riesgos
- La reclasificación de los 4 agentes a `experiment` significa que `_RUTAS_CRITICAS` de Doctor
  (que los marca `ERROR` si faltan) ahora solo aplica cuando `installation_stage` los incluye —
  mitigado porque el fallback legacy (punto 8) preserva el comportamiento actual para cualquier
  instalación existente, y una instalación NUEVA en `discovery` nunca declaró tener esos agentes,
  así que no hay ninguna expectativa previa que romper.
- `sync` reconstruye placeholders desde `control_previo["configuracion"]` — si esa configuración
  quedó incompleta en una instalación legacy muy antigua (campos `None`), las plantillas
  renderizadas de `experiment`+ podrían llevar placeholders vacíos — aceptado como riesgo menor
  documentado (mismo comportamiento que tendría una instalación nueva con esos mismos valores
  `None`, no es un caso nuevo introducido por este change).
- Dos documentos de skill nuevos sin contenido "accionable" más allá de explicar el mecanismo de
  evidencia podrían percibirse como poco útiles — aceptado conscientemente (punto 10): el costo
  de equivocarse hacia "más contenido" (placeholders que parecen evidencia) es mucho mayor que el
  costo de equivocarse hacia "menos contenido" (documentación pura).

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
Ver `proposal.md § Aprobación`.
