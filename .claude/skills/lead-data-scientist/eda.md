# Project EDA — referencia

Se lee bajo demanda, cuando el Lead necesita correr o interpretar una EDA que informe decisiones
de modelado (target, features, universo), o cuando un cambio entra en `data_understanding`/
`data_preparation`/`feature_engineering`. Nunca se carga por defecto.

## 1. Qué es y qué no es

Project EDA es el único tipo de EDA válido en v0.2 para decisiones de modelado. Distinto de la EDA
exploratoria/personal (fuera de alcance hasta v0.3+): Project EDA nunca mira más allá de lo que la
fase de modelado podría usar después -- mismo universo de datos, mismo cutoff, mismo holdout
protegido.

`ds_profile` (`tools/ds_profile/`, `python -m tools.ds_profile run ...`) calcula hechos y flags
deterministas sobre un dataset -- nunca decide qué significan para el negocio. Project EDA es lo
que el Lead hace con esos hechos: interpretarlos contra el cutoff/unidad de análisis ya declarados,
derivar hipótesis, documentar riesgos de leakage. La separación es literal: "el binario calcula y
hace cumplir lo determinista; el LLM decide lo semántico".

## 2. Model-valid EDA -- criterios

Una EDA es válida para decisiones de modelado si y solo si:

1. **Cutoff respetado**: si el cambio declaró un cutoff (`spec.md -> ## Cutoff / information
   boundary`), ningún dataset perfilado ni ninguna conclusión usa información posterior a esa
   fecha.
2. **Holdout no tocado**, salvo autorización explícita transcripta (routing "Sensible" de
   `SKILL.md`, sin atajos -- `ds_profile` además se niega técnicamente vía `holdout_guard.py`, ver
   `design.md` del Bloque 6).
3. **Ninguna foto sin fecha convertida en feature** sin documentar el riesgo (la clase de leakage
   de CLAUDE.md §2: un campo que arranca en la misma fecha para varios registros, se apila en un
   día, o falta en los positivos).
4. **Reproducible**: toda conclusión cita el `profile_id`/fingerprint de la corrida de `ds_profile`
   que la sustenta -- nunca un número de memoria.
5. **Hipótesis, no decisiones**: Project EDA deriva hipótesis; la decisión de target/features/
   modelo sigue el flujo normal de CLAUDE.md §3 (proponer y esperar aprobación explícita).

## 3. Cómo la conduce el Lead

- Corre `ds_profile` él mismo por Bash (es lectura pura sobre datos ya en `interim/`/
  `processed/`, mismo criterio que ya usa para `git diff`/`ds_guard status` -- no hace falta
  delegar).
- Interpreta `profile.json`/`profile.md`: qué flags importan para la decisión en curso, qué amerita
  seguir mirando.
- Si hace falta un análisis puntual que `ds_profile` no cubre (un cruce entre columnas, una
  visualización), se lo pide a `python-data-engineer` como snippet o celda de notebook -- no se
  extiende `ds_profile` para eso.
- Ante cualquier señal de leakage (columna que "arranca" en la fecha de corte, cardinalidad rota,
  constante rara, distribución que huye del cutoff), escala a `metodologo` antes de sacar
  conclusiones -- routing ya existente de `SKILL.md` (fila "Metodológica"), sin cambios.
- Documenta hallazgos en el artefacto de la sección 4; nunca decide automáticamente a partir de un
  flag.

## 4. Artefacto: `eda.md` (opcional)

Plantilla en `.claude/skills/lead-data-scientist/templates/eda.md`. Se instancia como
`openspec/changes/<change-id>/eda.md` **solo cuando el Lead determina que el cambio necesita
Project EDA** -- no forma parte del set fijo de artefactos que crea `ds_guard init` ni que exige
`ds_guard validate`; es evidencia opcional, no un gate nuevo. Se referencia desde `proposal.md`/
`spec.md` del mismo cambio, y su `profile_id`/fingerprint puede citarse en `verification.md` cuando
corresponda (ver `kdd.md` §8, fila "Fingerprint de dataset/artefacto").

## 5. Relación con KDD

Sin gates nuevos. `ds_profile`/`eda.md` alimentan con evidencia real los criterios detectables ya
existentes: `spec.md -> ## Unidad de análisis` (`data_understanding`), `spec.md -> ## Cutoff /
information boundary` (`feature_engineering`), `verification.md -> ## Fingerprint de dataset/
artefacto` (cambio sensible o reproducibilidad crítica). No se toca `kdd.py`; sigue siendo
`detectable`, no `enforceable` (deuda de v0.3+, ver `kdd.md` §7).
