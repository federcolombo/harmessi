# Conceptos

Vocabulario del harness de Harmessi. Cada sección indica la ruta donde está definido el comportamiento.

## SDD: cambios con especificación

SDD (spec-driven development) organiza un cambio relevante en `openspec/changes/<change-id>/` con `proposal.md`, `spec.md`, `design.md` y `tasks.md` (definición completa en `.claude/skills/lead-data-scientist/sdd.md`). Las tareas pequeñas y claras no lo necesitan.

`tasks.md` lleva un campo `estado:` con el ciclo del Change. Valores que define `sdd.md`: `propuesta_pendiente`, `aprobada_diseño` (solo en el flujo completo, cuando la aprobación no fue conjunta), `aprobada_implementacion`, `en_implementacion`, `en_verificacion`, `cerrada`, `pausada_bloqueada` (sin acuerdo tras la segunda ronda) y `descartada` (rechazo definitivo).

Reglas clave:

- La aprobación debe quedar registrada con evidencia (usuario, fecha, alcance aprobado), nunca un «sí» sin más.
- Quien implementa no cambia el estado: lo gobierna el Lead mediante `ds_guard transition`, y `ds_guard validate` señala divergencias (`SDD-ESTADO-DIVERGENTE`).

## Roles (subagentes) y skills

Definidos en `.claude/skills/lead-data-scientist/SKILL.md` y `.claude/agents/`:

- **Lead** (la conversación principal, no un subagente): decide cuándo delegar, propone decisiones relevantes y espera aprobación. No edita archivos.
- **metodologo**: solo lectura; diseño experimental, validación temporal, leakage, métricas.
- **python-data-engineer**: único rol con permiso de escritura; no ejecuta código ni notebooks.
- **data-science-reviewer**: solo lectura; revisa diffs contra las convenciones y reglas anti-leakage.
- **notebook-runner**: ejecuta una corrida de notebook ya aprobada según un manifest versionado, restringido por un hook técnico.

Las **skills componibles** (`.claude/skills/lead-data-scientist/skills/<name>.md`) son guía metodológica pequeña. Nunca son autoridad: no cambian permisos, alcance, guardrails ni aprobaciones. Las que describe `SKILL.md` son `problem-framing`, `domain-modeling`, `diagnosing-bugs` y `codebase-design`; se cargan solo cuando su `when_to_load` aplica.

## Flujo de datos y anti-leakage

Convención de `CLAUDE.md` para proyectos instalados:

- Flujo fijo `raw/` → `interim/` → `processed/` → `scoring/` (o el que aplique). `raw/` es solo lectura; lo posterior lee de `interim/`. Los datos no se versionan.
- Las features de un corte usan solo información anterior a la fecha de corte.
- Un holdout o dataset sellado es intocable hasta la evaluación final: ninguna decisión de features, modelo, hiperparámetros, calibración o umbral se toma mirándolo.
- Un campo sin fecha que se comporta como evento (arranca el mismo día para varios registros, falta en los positivos) puede ser leakage.
- Las transformaciones que aprenden de los datos (escalado, imputación, encoding) van dentro del pipeline, ajustadas solo con train. Ante la duda, preguntar.

## Cards y governance

`tools/cards/` implementa Data Cards y Model Cards (opt-in, capacidades `data_cards` y `model_governance`; ver `README.md`). Una Card es una vista estructurada que referencia evidencia existente y valida que esté presente, vigente y coherente. Una Data Card declara `temporality` `current` o `as_of`; `as_of` es declarativo y no se verifica contra la fecha de la observación (`tools/cards/datacard.py`).

Harmessi gobierna evidencia: no afirma que un modelo o dataset sea ético, justo, seguro, privado ni conforme a normas, y no es un motor de cumplimiento (`README.md`). El ciclo de vida de producción llega hasta evidencia de preparación; despliegue y monitoreo son un límite de integración (`docs/production-lifecycle.md`).

## Mejora gobernada del harness

`tools/harmessi_improve/` (CLI: `python -m tools.harmessi_improve`, solo desde checkout) permite mejorar superficies Optimizable del harness con un flujo gobernado: candidate aislada (siempre bajo `.harmessi/improvement/`, nunca modifica el archivo activo) → probe (corrida de baseline contra candidate sobre la base de `docs/evaluation.md`) → decisión recalculada desde resultados reales → propuesta de promoción → lesson respaldada por evidencia. La promoción se aplica solo mediante un Change normal con aprobaciones del usuario; hay presupuestos acotados y un ciclo acotado.

Límites (`docs/releases/v0.14.0.md`, sección «Known limitations»):

- Los evals son proxies de texto deterministas, sin LLM-as-judge; un veredicto mide el proxy, no la calidad real.
- La procedencia no es criptográfica: la consistencia interna de `.harmessi/improvement` y `.harmessi/evals` no prueba quién escribió los archivos.
- El escaneo de privacidad es heurístico: texto libre dentro del límite de longitud puede contener contenido que la redacción no detecta.
- No modifica el harness en silencio, no auto-promueve, no toca superficies Protected y no envía telemetría (`README.md`).

Véase también `docs/security-and-trust.md`.
