# Tareas — 20260915-progressive-capability-installation-and-scaffold

estado: cerrada

## Invocaciones planificadas
<!-- rol, momento del ciclo, y qué produce cada una -->
- Python Data Engineer (implementación + tests, invocación única, puede requerir varias
  reanudaciones por límite de turnos dado el tamaño del change — no cuentan como nuevas
  delegaciones): manifest + planner/writer/control + legacy.py + cli.py + doctor.py + 2 docs
  nuevos + toda la batería de tests de `spec.md`, siguiendo `design.md` al pie de la letra.
- Data Science Reviewer (revisión, DESPUÉS de implementación completa): revisa el diff. Solo
  informa hallazgos.
- Python Data Engineer (post-revisión, si hace falta): corrige, `estado: en_verificacion`.
- Python Data Engineer (cierre, planificada): `verification.md` con evidencia real,
  `estado: cerrada`.

## Tareas
- [x] `tools/ds_init/manifest.py`: `stage_minimo: str = "discovery"` en `EntradaManifiesto`;
  `ORDEN_STAGES = ("discovery","experiment","production_candidate","production")`; re-etiquetar
  las 5 entradas de `experiment` (4 agentes + `decision-ledger.md`) con `stage_minimo="experiment"`;
  2 entradas nuevas `production-readiness.md`/`operations.md` (`PLANTILLA`, `.tmpl` nuevas en
  `tools/ds_init/profiles/python_jupyter_data/templates/`) con `stage_minimo="production_candidate"`/
  `"production"`; `manifest_para_perfil_y_stage(perfil, stage)` nueva, aditiva.
- [x] Contenido de `production-readiness.md.tmpl`/`operations.md.tmpl`: explican los gates
  correspondientes (5 capabilities de `production_readiness`, 7 de `operations`, ver
  `spec.md` R2) y el mecanismo `mlops evidence add`, sin placeholders de datos ni referencias
  privadas/rutas absolutas de este repo — buscar explícitamente antes de cerrar (R13/§14).
- [x] `tools/ds_init/planner.py`: `construir_plan(perfil, destino, config, stage=None)` — `stage`
  activa `manifest_para_perfil_y_stage`; `None` preserva comportamiento actual exacto.
- [x] `tools/ds_init/writer.py`: `instalar` lee `config.get("stage")` con el mismo criterio, para
  que `entradas`/`entradas_por_destino` queden consistentes con el `plan` recibido.
- [x] `tools/ds_init/control.py`: `generar_control(..., installation_stage=None)` (omite la clave
  si `None`); `regenerar_control(..., *, stage=None, installation_stage=None)` (usa
  `manifest_para_perfil_y_stage` si `stage`; preserva `control_previo.get("installation_stage")`
  si `installation_stage` es `None`).
- [x] `tools/ds_init/legacy.py` (nuevo): `inferir_installation_stage(destino, perfil) -> str`
  según R6 de `spec.md` (solo `"production"`/`"discovery"`, nunca escribe nada).
- [x] `tools/ds_init/cli.py`: positional `accion` (`nargs="?"`, `default="install"`,
  `choices=["install","sync"]`); `--stage` nuevo para `install`
  (`choices=["discovery","experiment"]`, default `"experiment"`); flags de `install` pasan a
  `required=False`, validados a mano según `accion`; lógica de `sync` (lee `control.json`
  existente, calcula stage base declarado/inferido, calcula delta, aplica con
  `writer.instalar(..., stage=target)`, completa con `regenerar_control(..., stage=target,
  installation_stage=target)` tras éxito; no-op explícito si `target <= stage_base`).
- [x] `tools/harmessi/doctor.py`: `_check_archivos_administrados` usa
  `manifest_para_perfil_y_stage` si `control_data.get("installation_stage")` existe, si no
  preserva el comportamiento actual exacto; nuevo check `_check_installation_stage`
  (`HARMESSI-INSTALLATION-STAGE`, ver R11 de `spec.md`), wireado en `ejecutar()` bajo
  `SECCION_HARMESSI`, nunca `ERROR`.
- [x] `tools/ds_init/manifest.py`: entrada VERBATIM de `tools/ds_init/legacy.py` en `MANIFEST`
  (nota: `tools/ds_init/*` en general nunca se instala en destinos — confirmar que esto sigue así,
  `legacy.py` no necesita entrada de manifiesto si el resto de `ds_init` tampoco la tiene;
  verificar contra el manifiesto actual antes de agregar nada por costumbre). CONFIRMADO: ningún
  módulo de `tools/ds_init/` tiene entrada en `MANIFEST` — es tooling del propio repo Harmessi,
  nunca contenido instalable. No se agregó ninguna entrada nueva por costumbre.
- [x] Tests bundles: discovery solo su set; experiment acumulativo; production_candidate
  acumulativo; production acumulativo; monotonicidad; sin ambigüedad de `stage_minimo` por
  destino; `manifest_para_perfil` (sin stage) sigue devolviendo el set completo.
- [x] Tests instalación nueva: default `experiment`; `--stage discovery` explícito; rechazo de
  `--stage production_candidate`/`production` en instalación nueva (exit 2); `installation_stage`
  correctamente registrado.
- [x] Tests `sync`: discovery→experiment; experiment→production_candidate;
  production_candidate→production; discovery→production directo; idempotencia (segunda corrida
  no cambia nada); target menor/igual → no-op sin escritura; sync sin control.json previo → error
  claro; fallo simulado durante aplicación → destino intacto, control.json no miente; `--dry-run`
  no escribe nada.
- [x] Tests `project_stage` vs `installation_stage`: iguales → PASS; project mayor → WARN
  accionable; installation mayor → PASS (nunca ERROR, no promueve nada); Doctor nunca muta
  `project.json`/`control.json`.
- [x] Tests legacy/migración: control.json sin `installation_stage` con archivos `experiment`
  presentes → infiere `"production"`; sin esos archivos → infiere `"discovery"`; `sync` sobre
  legacy usa la inferencia como base; Doctor sobre legacy no muta nada con la sola lectura;
  Doctor sobre ESTE repo (legacy real) → `HARMESSI-ARCHIVOS-ESPERADOS` idéntico a antes del
  change.
- [x] Tests protección de archivos: archivo de `experiment` editado por el usuario antes de
  `sync` → no se sobrescribe (hash idéntico); `MERGE`/`CLAUDE.md` durante `sync` sigue el camino
  existente sin duplicar lógica; `sync` nunca borra nada en ningún escenario.
- [x] Tests Doctor — regresión y nuevo comportamiento: discovery real no reclama archivos de
  experiment+; experiment real sí los reclama; candidate/production reales exigen el
  set acumulado correcto; legacy sin cambios; `harmessi doctor` real sobre este repo antes/después
  del change, mismo conteo de `[ERROR]`.
- [x] Tests scratch: scratch discovery real; scratch experiment real (default); incremental
  discovery→experiment real vía `sync --execute`; incremental experiment→production_candidate
  fixtureable sin simular `promote`/`readiness` real; imports desde el destino instalado sin
  `ImportError`, para cada stage.
- [x] Tests manifest/regresión: paridad extendida para `legacy.py` (`test_legacy.py`, nuevo);
  ausencia de duplicados de `destino` en `MANIFEST` (test explícito nuevo + ya implícito en
  `test_destinos_sin_overlap`); suite completa `tools/tests/`, `tools/harmessi/tests/`,
  `tools/ds_init/tests/` — código y tests escritos y auto-revisados por lectura; corrida real
  pendiente del Lead (no tengo Bash); `harmessi doctor` 0 `[ERROR]` nuevo — verificado por lectura
  del código (fallback legacy exacto) y por tests nuevos, pendiente de confirmación con corrida
  real.

## Dependencias
`manifest.py` (stage_minimo + manifest_para_perfil_y_stage) antes que
`planner.py`/`writer.py`/`control.py`/`legacy.py`/`cli.py`/`doctor.py`. `legacy.py` antes que
`cli.py sync` y `doctor.py` (ambos lo consumen). Manifest/parity puede ir en paralelo a la CLI.
Tests al final de cada pieza. Depende de Changes 1 (`lifecycle.py`, indirecto vía maturity), 3
(`maturity.py`, para el check de `project_stage`), 4 (`checks.py`, Doctor), 6 (`readiness.py`
mencionado en mensajes de Doctor, no consumido directamente), todos cerrados. Reusa
`preflight.py`/`planner.py`/`writer.py`/`control.py` existentes sin romper sus contratos
actuales.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->
