# Spec — 20260916-kdd-enforceable-checks

## Requisitos

1. `tools/dsguard/scientific_validity.py` expone `evaluar_scientific_checks(repo_root) -> list[CheckResult]`,
   siempre de solo lectura, nunca lanza, determinista (mismo estado de disco → mismo resultado).
2. `.harmessi/scientific-policy.json` (opcional): `schema_version=1`, secciones opcionales `temporal`,
   `holdout`, `leakage`, `baseline`, todas con campos opcionales. Ausente → todas las secciones N/A.
   Corrupto (JSON inválido o `schema_version` desconocida) → un único `CheckResult` FAIL
   `kind=technical_error`, código `SCI-POLICY`, bloqueando el resto (no se evalúa nada parcialmente).
3. **Cutoff** (`SCI-CUTOFF`): N/A si `temporal.declared != true`. Si declarado, evalúa
   `max(fecha_max de temporal.date_column en el profile.json de temporal.profile_path) <= temporal.cutoff_utc`.
   Nunca carga el dataset completo — solo lee `profile.json` de `ds_profile`. `profile_path` pasa por
   la misma protección de holdout/secretos que `pathguard`/`ds_profile.holdout_guard` (no se lee un
   profile dentro de un holdout sin excepción vigente). Fechas en formato `core.ahora_utc()`
   (`YYYY-MM-DDTHH:MM:SSZ`), comparadas como UTC-naive (mismo criterio que `ds_profile`, que no
   trackea timezone). WARN si falta info para evaluar (cutoff/columna/profile_path no declarados,
   profile ausente); FAIL si la info declarada es inconsistente/corrupta (fecha inválida, columna
   inexistente en el profile, columna no es dtype `fecha`, excede el cutoff).
4. **Holdout**: dos checks. `SCI-HOLDOUT-PROTECTION` (N/A si `holdout.declared != true`; FAIL si
   declarado pero `guardrails.json → holdouts` está vacío; PASS si hay protección estructural vía
   pathguard). `SCI-HOLDOUT-USAGE` (N/A si no declarado; evalúa `holdout.usage_declarations` contra
   las 5 operaciones prohibidas — `training`, `feature_engineering_fit`, `model_selection`,
   `hyperparameter_tuning`, `baseline_fitting`; FAIL si alguna se declara usada; WARN si falguna queda
   sin declarar explícitamente — "información insuficiente", nunca PASS por omisión; PASS solo si las
   5 se declaran explícitamente `used: false`, mencionando `holdout.final_evaluation` si está
   autorizada). Nunca lee el contenido del holdout. Compatible con excepciones de lectura de
   `guardrails.json` por no-interferencia (el check nunca abre el holdout).
5. **Leakage** (tres checks, ninguno usa correlación ni heurística de nombre de columna):
   `SCI-LEAKAGE-TARGET` (N/A sin `leakage.target`; WARN sin `leakage.features`; FAIL si
   `target in features`); `SCI-LEAKAGE-FORBIDDEN` (N/A sin `leakage.forbidden_features`; WARN sin
   `leakage.features`; FAIL si hay intersección); `SCI-LEAKAGE-SPLIT` (N/A sin
   `train_max_utc`/`validation_min_utc`; WARN si solo uno declarado; FAIL si fecha inválida o
   `train_max_utc >= validation_min_utc`). El leakage temporal (dataset excede cutoff) se cubre por
   `SCI-CUTOFF` — no se duplica un check aparte.
6. **Baseline** (`SCI-BASELINE`): N/A si `baseline.required != true`. FAIL si requerido sin
   `evidence_path`, si el archivo no existe, si está vacío (0 bytes), o si `evidence_sha256` declarado
   no coincide con el hash actual (evidencia obsoleta). PASS si el archivo existe, no está vacío, y
   (si se declaró hash) coincide. Nunca exige un algoritmo ni inspecciona el contenido del archivo.
7. CLI: `python -m tools.ds_guard science status [--json]`. Exit code vía `checks.exit_code` (1 si hay
   algún FAIL). Estrictamente read-only: nunca escribe `project.json`, `lifecycle/state.json`,
   `control.json`, `scientific-policy.json`, evidence, decision ledger, ni SDD.
8. `tools/dsguard/status.py` agrega una sección `"science"` (lista de `CheckResult.to_dict()`) al
   dict de `evaluar_status`, y una sección "Scientific Validity" en `formatear_texto` — sin duplicar
   la lógica de `scientific_validity.py`.
9. `tools/ds_init/manifest.py` agrega una `EntradaManifiesto` VERBATIM para
   `tools/dsguard/scientific_validity.py`. No se agrega ningún template de `scientific-policy.json`
   (mismo criterio que `.harmessi/project.json`: `.harmessi/` ya está en `EXCLUSIONES_PERMANENTES`).
10. `.claude/skills/lead-data-scientist/methodology.md` y su `.tmpl` de instalación
    (`tools/ds_init/profiles/python_jupyter_data/templates/methodology.md.tmpl`) se actualizan de
    forma idéntica entre sí, con una sección nueva mínima sobre scientific checks + 2 ítems nuevos en
    "Acciones prohibidas del Lead".
11. No se modifica `readiness.py`, la matriz de promotion, el schema de `lifecycle/state.json`, ni se
    agregan fases CRISP-DM.

## Criterios de aceptación

- [ ] `evaluar_scientific_checks` sobre un repo sin `.harmessi/scientific-policy.json` devuelve 7
      resultados, todos N/A (salvo que alguna sub-regla dependa de `guardrails.json`, que también
      puede estar ausente → sigue N/A).
- [ ] Policy corrupta (JSON inválido / `schema_version` desconocida) → exactamente 1 `CheckResult`
      FAIL `kind=technical_error`, código `SCI-POLICY`.
- [ ] Cutoff: casos no aplica / dentro / excede / fecha inválida / columna faltante / dtype no fecha /
      profile ausente / profile dentro de holdout sin excepción, todos cubiertos por tests.
- [ ] Holdout: identificado sin holdouts en guardrails (FAIL), identificado con holdouts (PASS),
      operación prohibida usada (FAIL), declaración incompleta (WARN), 5 operaciones declaradas
      `false` + final_evaluation autorizada (PASS con mención), excepción de lectura de guardrails.json
      no interfiere.
- [ ] Leakage: target en features (FAIL), target fuera (PASS), forbidden feature presente (FAIL),
      split inválido (FAIL), split válido (PASS), sin policy (N/A para las tres).
- [ ] Baseline: no requerido (N/A), requerido + evidencia válida (PASS), requerido sin evidencia
      (FAIL), evidencia vacía (FAIL), hash declarado no coincide (FAIL).
- [ ] `ds_guard science status` y `--json` corren sobre un repo temporal real (subprocess), exit code
      0 si no hay FAIL, 1 si hay algún FAIL.
- [ ] Read-only verificado byte-a-byte: correr `science status`/`evaluar_scientific_checks` no
      modifica ningún archivo de estado existente (usar `dsguard.core.capturar_bytes` antes/después).
- [ ] `ds_guard status` (sin `--change-id`) incluye la sección `science` en JSON y en texto.
- [ ] `tools/tests/test_manifest_dsguard_parity.py` tiene una clase nueva que verifica la entrada
      VERBATIM de `scientific_validity.py`.
- [ ] Suite completa (`tools/tests`, `tools/ds_init/tests`, `tools/ds_profile/tests`,
      `tools/harmessi/tests`) pasa; `check_manifest_parity` y `harmessi doctor` no reportan errores
      nuevos atribuibles a este cambio.

## Cutoff / information boundary
No aplica como dataset propio de este cambio — este cambio construye la infraestructura que verifica
cutoffs declarados por *otros* cambios futuros (mismo patrón que
`20260911-ds-profile-project-eda`).

## Baseline (condicional — modeling)
No aplica: este cambio no entrena ni evalúa un modelo, construye el mecanismo que verifica la
existencia de baseline de *otros* cambios futuros.
