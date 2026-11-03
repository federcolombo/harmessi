# Verificación — 20261016-v011-git-scope-fail-closed

## Resumen
Change 1 de v0.11: Git & Scope fail-closed. Un fallo de Git (comando, ref inválida, Git ausente, salida malformada) ya no se interpreta como estado limpio ni como «sin archivos». SDD aprobado por hash (T0/declared, autorización anticipada).

## Implementación
`repo.py` (bytes sin universal newlines, returncode verificado, `validar_ref`, rename → ambas rutas, copy → destino, R/C en cualquier columna), `scope.py` (sin `except Exception`, único `ALCANCE-GIT-ILEGIBLE`), `notebooks.py` (distinción nuevo / rev inválida / git roto), `ds_guard.py` (`_error_git` exit 3 en status/validate/archive/init/notebook-diff), `mlops_foundations.py` (WARN explícito si Git falla), docs `verificador.md` + plantilla, tests nuevos `test_git_failclosed.py` y `test_git_failclosed_cli.py`, fixtures de tests existentes.

## Reviewer
Ciclo 1 (data-science-reviewer): 0 altos, 5 medios (M1–M5), 8 bajos. Todos resueltos salvo M4 (`dsimpact/git_source.py`, fuera de scope → DIFERIDA, registrada en el roadmap). M3 (`init` en repo sin commits → exit 3) es intencional y está documentado. No se usó el ciclo 2: sin blockers ni HIGH; el fix posterior (`^{commit}` → `^0`) es mecánico.

## Evidencia obtenida
- Dirigidos: 128 OK / 1 skipped (`test_git_failclosed`, `test_git_failclosed_cli`, `test_scope`, `test_git_paths_unicode_consumers`, `test_git_name_status_z`).
- Primera corrida amplia (209 módulos, paralela): 28 módulos con fallo; los 28 fallaban igual en el baseline (worktree de `main`) → preexistentes/entorno, no atribuibles.
- Corrida focalizada de 50 módulos (P=2): reveló una regresión real: el instalador rechaza `{{commit}}` en `notebooks.py` («Placeholder sin resolver»). Corregida (`^0`).
- Confirmación del fix, seriales en foreground: `ds_init.test_cards_capabilities` 46 OK, `ds_init.test_integracion_instalacion` 1 OK, `harmessi.test_doctor_governance` 32 OK, `harmessi.test_doctor_guardrails` 38 OK, `harmessi.test_doctor_skill_contract` 9 OK.
- Dos corridas amplias/focalizadas fueron terminadas por presión de memoria (incidente de recursos, no funcional; no atribuible al Change). Estrategia adaptada a release train: regresión completa diferida a Change 6 en batches seriales.

## Incidentes
Sesiones s1 y s2 vencieron por reloj (wall-clock) esperando tests; recovery soportado (cerrar `pausada` + abrir nueva), sin pérdida de estado. Evidencia para Change 3.
La emergencia de recursos (OOM) cambió la estrategia de tests; nada se debilitó en el producto.

## Limitaciones
`test_cr_en_nombre_se_preserva` se omite en Windows (R6 verificado con subprocess mockeado). Los artefactos de código los escribió `python-data-engineer`; el Lead ejecutó los tests. `dsimpact/git_source.py` conserva fail-open en lectura de contenido (deuda diferida).

## Divergencias respecto del SDD
design D1 nombra `_git_ok`; el código usa `_verificar`. R5: `show`/`rev-parse` usan validación de ref, no `--`. R10 se excepciona: rename, `init` sin commits y `notebook-diff --tocados` cambian bajo Git sano de forma intencional.

## Pendientes
Change 2. Regresión completa en Change 6.

## Resultado final
Change 1 verificado: gate técnico satisfecho con tests dirigidos (128 OK / 1 skipped) y confirmación serial del fix del instalador; sin hallazgos abiertos del reviewer salvo la deuda diferida M4.
