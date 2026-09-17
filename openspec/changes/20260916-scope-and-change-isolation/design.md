# Design — 20260916-scope-and-change-isolation

## 1. Por qué esto es una extensión, no una construcción desde cero
La auditoría encontró que `ALCANCE-RUTA`/`files_out_of_scope` YA EXISTEN y ya corren en
`cmd_validate`/`gate_cierre`. Construir un mecanismo paralelo nuevo violaría "no duplicar" (brief) y
"scope declarado ↔ git diff real" ya está parcialmente resuelto -- solo falta que el "diff real"
cubra más que el working tree instantáneo.

## 2. Por qué `dsguard` no importa `dsimpact`
Change 1 estableció la dirección `dsimpact -> dsguard` (dsimpact reusa `repo._git`). Importar
`dsimpact` desde `dsguard` invertiría esa dependencia y además `dsguard` es core (discovery,
siempre instalado) mientras `dsimpact` es opcional (`stage_minimo="experiment"`, import perezoso
en `ds_guard.py`) -- un import directo rompería cualquier instalación en discovery, el mismo
problema que ya resolvió el import perezoso de `impact scan`. `scope.py` reimplementa el mismo
patrón de `git diff --name-status -M <ref>` de forma LOCAL y pequeña (10-15 líneas), igual que
`dsimpact.git_source` lo hace reusando `repo._git` -- no es una tercera reimplementación de un
wrapper de subprocess (sigue siendo `repo_mod._git`), es una tercera instancia del mismo patrón de
armar el comando/parsear `--name-status`, ya replicado antes sin objeción (`dsimpact.git_source`).

## 3. Por qué se prefiere fail-open acá y fail-closed en otros módulos
`pathguard`/`scientific_validity` protegen contra riesgo real (fuga de secretos/holdouts, falsa
validez científica) -- fail-closed es correcto ahí. Acá, un `baseline.commit` roto es un problema de
*higiene de metadata* de un Change viejo, no un vector de riesgo: bloquear `validate`/`cierre` de
CUALQUIER Change con un `control.json` de formato previo por este motivo sería una regresión de
disponibilidad real a cambio de una ganancia de seguridad marginal (el check de working tree, que sí
sigue funcionando, ya cubre el caso más común y más peligroso: cambios sin commitear todavía).

## 4. Consolidación: un solo lugar de verdad
Antes: `cmd_validate` (`ds_guard.py`) y `gate_cierre` (`sdd.py`) tenían el MISMO bucle
`for r in repo.files_out_of_scope(...): findings.append(Finding("ALCANCE-RUTA", ...))` duplicado
literalmente. Después: ambos llaman `scope.evaluar_alcance(repo_root, control)`. Si en el futuro se
quiere ampliar el chequeo de nuevo, se edita un solo lugar.

## 5. Riesgos aceptados / límites conocidos
- No detecta un archivo tocado, commiteado, y luego REVERTIDO por completo (incluyendo el commit
  que lo tocó, ej. vía `git reset --hard` a un punto anterior a esa modificación) -- en ese caso ya
  no hay diferencia real entre baseline y el estado actual, correctamente sin finding (no es una
  limitación, es el comportamiento correcto).
- No distingue "expansión accidental" de "cambio encadenado deliberado pero no re-declarado en
  `rutas_autorizadas`" -- ambos casos producen el mismo `ALCANCE-RUTA`, la distinción semántica
  sigue siendo del Lead/reviewer, igual que hoy.
- No integra con `dsimpact` (Change 1) -- son conceptos relacionados pero distintos (scope =
  "¿tocaste algo que no declaraste?", impact = "¿qué podría consumir lo que tocaste?"), mezclarlos
  sería expandir el alcance de este Change sin necesidad real declarada por el brief.
