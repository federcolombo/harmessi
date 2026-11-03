# Spec — 20261001-v08-release-hardening

Notación: `Rn` con criterio verificable, `Given/When/Then` cuando aplica. Organizado por los 11
casos (A-K) del encargo del autor (2026-10-01), que mapean 1:1 a los Casos A-I + "Regresión por
default" + "Métricas de eficiencia" ya congelados en `docs/roadmap/v0.8.md` ("Change 5 —
v0.8-release-hardening"). Ningún requisito reabre `tools/autonomy/core.py`, `tools/autonomy/
policy.py`, `tools/datasources/core.py`, `tools/leadrun/core.py`/`runtime.py` (Changes 0-2,
cerrados) ni los artefactos aprobados por hash de Change 3/Change 4 (cerrados) — todo lo de acá
EJERCITA esos módulos end-to-end, nunca los edita.

Este Change tiene DOS fases dentro del mismo `tasks.md` (R0): primero SDD (este documento,
`proposal.md`, `design.md` — sin implementación), después, tras aprobación humana por hash,
ejecución real de los escenarios A-K con evidencia persistida. Ningún requisito de abajo se
considera cumplido por diseño solamente — cada uno exige evidencia real de ejecución.

## 0. Alcance de verificación (R0)

**R0 — Fixtures 100% sintéticos y genéricos.** Ningún escenario usa datos reales, dominios ni
organizaciones particulares (mismo principio ya fijado por el roadmap para Changes 0-4).
- Aceptación: cada fixture de proyecto scratch creado para este Change se audita visualmente antes
  de usarse — nombres de columnas/datasets genéricos (`cliente_sintetico`, `evento_generico`, etc.).

## A. Autonomous end-to-end (R1-R4)

**R1 — Proyecto scratch con `autonomous` + `approval_mode: checkpoints`.** Instalación fresca,
objetivo sintético aprobado con checkpoints de negocio declarados en `proposal.md` (Change 3/M7).
**R2 — Cero ejecuciones humanas intermedias.** Desde la aprobación inicial hasta el cierre: el
writer escribe, el Lead ejecuta (script/pytest/notebook según corresponda), corre tests,
remediation si hace falta, genera evidence/reporting — el humano solo interviene en: (a) la
aprobación inicial del Change, (b) los checkpoints de negocio ya declarados, (c) un STOP material
real si ocurriera. Ninguna otra intervención cuenta como "no humana".
- Given un objetivo aprobado con checkpoints declarados, When el Lead ejecuta el ciclo completo
  (escribir → ejecutar → testear → remediar si aplica → reportar → cerrar), Then el registro de
  sesión (`control["sesiones"]`) y los `ExecutionRecord` persistidos son la ÚNICA evidencia de
  ejecución — ninguna ejecución directa fuera del runtime gobernado cuenta para el cierre.
**R3 — Evidence/reporting real producidos.** Al menos un `ExecutionRecord` con `exit_code == 0`,
al menos un reporte (`tools/reporting`) o evidencia de calidad (`tools/qualityevidence`) generado
por el flujo, no simulado.
**R4 — Métrica funcional del roadmap satisfecha.** `human code executions = 0` verificable
contando invocaciones directas de `Bash`/`PowerShell` del humano fuera de la aprobación/checkpoints
(trazabilidad ya existente, sin mecanismo nuevo).
- Verificación: demostración en vivo conducida por el Lead (no simulable por un test unitario sin
  mockear la esencia misma de "autonomía real" — ver `design.md` para la justificación de por qué
  este caso no es 100% pytest-automatizable).

## B. Project without predictive modeling (R5-R7)

**R5 — `predictive_modeling=false` no provisiona assets exclusivos de ML.** Los 3 assets de
`tools/modelquality/*` (únicos marcados `capabilities=("predictive_modeling",)`, Change 4/M8) no se
instalan.
**R6 — Doctor no los marca `MISSING`/`ERROR`.** Reporta `N/A — capability not enabled` (ya
implementado y testeado a nivel unitario en Change 4 — este Change lo ejercita en un proyecto
scratch real, no mockeado).
**R7 — Capabilities activas siguen funcionando, sin segunda distribución.** El resto del perfil
(`installation_stage` sin cambios) se instala igual que siempre; activar la capability después
(`sync`) provisiona lo faltante sin romper nada existente.
- Verificación: test de integración nuevo (pytest, instalación real vía `writer.instalar` + Doctor
  real) — extiende el patrón de `tools/ds_init/tests/test_integracion_instalacion.py`.

## C. External file-backed read-only (R8-R12)

**R8 — Lectura OK.** `ds_guard source observe` sobre una fuente externa declarada en
`.harmessi/local-overrides.json` (M9, Change 4) completa exitosamente contra un archivo real fuera
del repo del proyecto.
**R9 — Write/Edit/Move/Delete bloqueados donde Harmessi controla.** Confirmado mediante el hook de
`pathguard.py` real (no solo la función `evaluar_tool_call` aislada, como en los tests unitarios de
Change 4) — `move`/`delete` vía Bash quedan fuera del control estricto de `pathguard` (best-effort
documentado, Change 0) y se verifican como tales, sin sobre-afirmar protección.
**R10 — Fingerprint pre/post.** Una ejecución gobernada que modifica la fuente externa por su
cuenta deja `fingerprints.json` real con discrepancia detectada (M12, Change 4).
**R11 — `data_loss_risk` real, sin afirmar causalidad.** El `CheckResult` real (no mockeado)
contiene el texto exacto ya verificado a nivel unitario.
**R12 — Diagnóstico OS honesto, sin claims de sandbox.** `harmessi doctor` real sobre el fixture
reporta el estado de permisos OS observado de verdad (no simulado), incluido el caso
`unknown/partial` si el entorno de CI no permite determinarlo con certeza.
- Verificación: test de integración end-to-end (pytest, sin mocks de `subprocess`/`importlib.
  metadata` donde sea viable — reutiliza el patrón de `test_ds_guard_source_integrity.py` de Change
  4 pero con una ejecución real, no mockeada).

## D. Source-neutral (R13-R15)

**R13 — File-backed.** Ya cubierto por el Caso C (R8) — no se duplica acá.
**R14 — SQL-like con `sqlite3` de la stdlib.** Un adapter mínimo del proyecto (fuera del core de
Harmessi) implementa el contrato de `tools/datasources` (factory + `capabilities()` + `observe()`)
sobre una base `sqlite3` sintética — demuestra que el contrato sirve una fuente NO orientada a
archivos, **sin validar SQLite como producto** y **sin agregar ninguna dependencia nueva a
Harmessi** (`sqlite3` ya es stdlib).
**R15 — Adapter `module:callable` custom del proyecto.** Registrado en `.harmessi/sources.json`
sin modificar ningún archivo administrado; `harmessi doctor` 0 `ERROR`.
- Verificación: test de integración nuevo, fixture con un adapter de ejemplo escrito como parte del
  proyecto scratch (no del core de Harmessi).

## E. Overrides / config layering (R16-R19)

**R16 — Project config soportada.** `.harmessi/project-config.json` declarando una restricción
real (p. ej. `mode: supervised`) se respeta.
**R17 — Local override soportado.** `.harmessi/local-overrides.json` idem, capa adicional.
**R18 — Customización válida no produce drift.** `harmessi doctor` real sobre un proyecto con
ambas capas declaradas reporta las categorías nuevas de M10 (Change 4), nunca `HARMESSI-DRIFT`.
**R19 — Mutación de un managed file SÍ produce drift; policy siempre es techo.** Editar a mano un
archivo administrado real (no simulado) dispara `HARMESSI-DRIFT`; una policy humana `supervised` +
un override que declara `autonomous` sigue resolviendo `supervised` (R11 de Change 4, ya testeado
a nivel unitario — este Change lo repite contra un `harmessi doctor`/`ds_guard` reales).
- Verificación: test de integración (pytest, instalación real + mutación real de un archivo +
  Doctor real).

## F. Existing project adoption (R20-R22)

**R20 — Repo scratch preexistente con código y brief, git limpio.** Mismo escenario que el test
end-to-end ya escrito en Change 4 (`TestAdopcionProyectoExistente`,
`tools/ds_init/tests/test_cli.py`) — este Change lo re-ejecuta como parte de la regresión formal de
cierre, sin reescribirlo.
**R21 — Harmessi no sobrescribe nada del usuario; ownership correcto; Doctor 0 `ERROR`.** Ya
verificado a nivel unitario en Change 4 (`_check_ownership_5_vias`) — este Change confirma que
sigue en verde como parte de la regresión combinada (no requiere trabajo nuevo si Change 4 sigue
cerrado y sin regresiones).
**R22 — El runtime puede trabajar con código ya existente.** Una ejecución gobernada
(`ds_guard exec script`) sobre un script que YA estaba en el repo adoptado (no instalado por
Harmessi) completa normalmente.
- Verificación: extiende el test de adopción ya existente con un paso de ejecución real sobre un
  script preexistente del usuario.

## G. Dependency pre-approval (R23-R40)

**R23 — Dependencia aprobada dentro de rango, pin exacto, operación gobernada.** Ya verificado a
nivel unitario/CLI en Change 4 (24 tests en `test_ds_guard_dependency_install.py`) — este Change
confirma que la regresión sigue en verde, sin repetir el trabajo de Change 4.
**R24 — Sin shell arbitrario.** Confirmado por el patrón cerrado de 6 tokens (R24 de Change 4), sin
nuevo trabajo.
**R25 — Fuera de rango → STOP.** Idem, ya cubierto.
**R26 — Sin transitivas automáticas.** Idem, ya cubierto (`--no-deps` obligatorio).
**R27 — Evidence pre/post.** Idem, ya cubierto (`dependency_evidence.json`, incluido el camino de
fallo, hallazgo del reviewer de Change 4 ya corregido).

**R28 — Instalación REAL, 100% local, sin red (decisión 2026-10-01, RESUELTA: la regresión de
Change 4, toda mockeada, NO alcanza como evidencia de hardening para una capability nueva y
sensible).** Un paquete Python mínimo empaquetado como wheel vía `zipfile` + metadata manual de la
stdlib (sin `build`/`setuptools`/`wheel` como dependencia nueva de Harmessi ni de su suite de
tests); resolución local de pip configurada por entorno TEMPORAL del proceso (`PIP_NO_INDEX=1`,
`PIP_FIND_LINKS=<dir del wheel>`), nunca como flag del `argv` gobernado — el comando final sigue
siendo EXACTAMENTE `<venv-python> -m pip install --no-deps <nombre>==<versión>`, sin
`--find-links`/`--index-url`/paths/flags libres agregados al comando permitido. Ninguna ruta
absoluta de esta máquina se versiona (`tempfile.TemporaryDirectory()` por test).

Los 13 puntos exigidos, cada uno un test explícito:
- **R29** — paquete local `A`, versión exacta, pre-aprobado.
- **R30** — versión dentro del rango humano aprobado.
- **R31** — instalación real, `exit_code == 0`.
- **R32** — paquete ausente antes (confirmado vía `importlib.metadata` real, sin mock).
- **R33** — paquete/versión correcto después (idem, real).
- **R34** — `ExecutionRecord` real persistido en `.harmessi/executions/`.
- **R35** — `approval`/evidencia ligada a la pre-aprobación real (`dependency_evidence.json` real).
- **R36** — sin paquetes adicionales inesperados (comparación real de
  `importlib.metadata.distributions()` pre/post).
- **R37** — sin acceso de red (`PIP_NO_INDEX=1`; documentar honestamente si el entorno de CI no
  permite aislar la red del proceso de test a mayores).
- **R38** — instalación únicamente en el `.venv` del proyecto scratch, nunca el de Harmessi.
- **R39** — mismo paquete fuera de rango → STOP `new_dependency` real; paquete no aprobado → STOP
  real; ninguna instalación ocurre en ningún de los dos casos STOP (confirmado por
  `importlib.metadata` real sin cambios).
- **R40** — cláusula de escape: si el entorno real de pip hace imposible demostrar esto sin
  modificar el contrato cerrado de M11, STOP y explicar por qué — nunca relajar la allowlist ni
  agregar un flag al comando gobernado para "hacer pasar" el test.

- Verificación: regresión dirigida (re-ejecutar los 24 tests de Change 4, sin editarlos) + el
  escenario nuevo de instalación real local (R28-R40), en un archivo de test propio de este Change.

## H. Budgets / checkpoints (R41-R44)

**R41 — Aggregate budget efectivo.** Ya corregido y testeado en Change 3 (adenda post-cierre,
`TestAggregateMinutesLimitEfectivo`, 11 escenarios) — este Change confirma regresión en verde.
**R42 — `max_sessions` y no evasión.** Idem, ya cubierto (R12a, Change 3).
**R43 — Business checkpoints.** Idem, ya cubierto (`parsear_checkpoints_de_propuesta`).
**R44 — Los 12 STOP universales intactos.** Confirmado por `STOP_CATALOG` inmutable (test ya
existente, `test_v08_change3_neutrality.py`) — sin trabajo nuevo si Changes 0-3 siguen cerrados sin
regresión.
- Verificación: regresión dirigida (re-ejecutar suites existentes de Change 3), sin nuevos tests
  salvo que la regresión descubra algo — en cuyo caso se documenta como hallazgo, no como feature.

## I. Efficiency (R45-R46)

**R45 — Métricas reportadas.** `ds_guard session efficiency` real sobre una sesión de un escenario
de este mismo Change (p. ej. el Caso A) produce `writer_lead_cycles`/`executions_count`/
`execution_duration`/`remediation_cycles` reales, no sintéticos.
**R46 — Sin thresholds arbitrarios.** Las métricas se reportan como benchmark informativo en
`verification.md` de este Change — ningún gate numérico nuevo se introduce.
- Verificación: una corrida real de `ds_guard session efficiency` sobre al menos un escenario ya
  ejecutado para otro caso (reuso, no una corrida dedicada nueva).

## J. Domain context compatibility (R47-R49)

**R47 — Artefacto de contexto de dominio no administrado, sin drift.** Al menos un proyecto scratch
de este Change incluye un `GLOSSARY.md` sintético (o equivalente) en la raíz del repo, NUNCA
agregado al manifiesto de `tools/ds_init/manifest.py` — `harmessi doctor` real no lo reporta como
`HARMESSI-DRIFT` ni de ninguna otra forma (no es un managed file, Doctor lo ignora igual que
cualquier archivo de negocio no administrado).
**R48 — Sin conflicto con installer/adoption/config layering.** El mismo proyecto scratch ejercita
al menos uno de los Casos E/F (overrides o adopción) CON el `GLOSSARY.md` presente, confirmando que
su presencia no cambia ningún resultado de esos casos.
**R49 — El Lead puede consultar el contexto sin modificar archivos administrados.** Una lectura
real del `GLOSSARY.md` (vía `Read`/`Grep`, interceptados por `pathguard` como cualquier archivo del
proyecto) no requiere ni produce ninguna escritura en un archivo administrado.
- **Explícitamente NO se implementa ninguna skill de domain-modeling, glossary manager, ni
  mecanismo de lectura formal** — este caso es pura compatibilidad arquitectónica (adenda
  2026-10-01 del roadmap).
- Verificación: test de integración nuevo, mínimo (crear el archivo, correr Doctor, confirmar
  ausencia de drift; combinar con el fixture de Caso E o F ya construido).

## K. Backward compatibility (R50-R54)

**R50 — Proyecto sin ninguna opción nueva se comporta exactamente igual que antes.** Instalación
fresca sin `approval_mode`/capabilities/fuente externa/overrides/dependencias pre-aprobadas
declaradas — comportamiento idéntico al de Change 2 (pre-M7-M12).
**R51 — `supervised` sigue funcionando sobre el mismo runtime.** Sin segundo runtime, confirmado.
**R52 — Upgrade desde v0.7.** Dry-run por defecto, archivo sin cambios se actualiza, archivo con
drift se reporta como conflicto y nunca se pisa en silencio, el upgrade no activa `autonomous`.
**R53 — Fresh discovery / fresh experiment / manifest parity / regresión completa / privacy /
portability / Doctor / git diff --check / coherencia de versión.** Checklist combinado, cada ítem
ya tiene su propio mecanismo verificado por Changes anteriores — este Change confirma que TODOS
siguen en verde juntos, en la misma corrida de cierre.
**R54 — Regresión completa del repositorio en verde.** Mismo criterio que el cierre de Change 3/4:
cero fallas en el conjunto completo de `tools/` (lotes secuenciales si hace falta memoria, patrón
ya aceptado).
- Verificación: regresión completa final + checklist de cierre, análogo al de Change 3/4.

## Resultado final exigido

Al cerrar este Change (fase de implementación, no este SDD): `verification.md` declara
explícitamente `READY FOR v0.8.0 RELEASE` o `NOT READY FOR v0.8.0 RELEASE`, con la evidencia de
cada caso A-K citada. Ningún push/tag/release real se ejecuta como parte de este veredicto.
