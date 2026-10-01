# Propuesta — 20260930-project-extension-and-installer-integration

## Problema

`docs/roadmap/v0.8.md` (M8-M10, M12, enmiendas 2026-09-30) ya congeló 5 capacidades opt-in para
hacer instalable/configurable lo que Changes 0-3 construyeron, sin que una customización válida
genere drift: project capabilities (M8), fuentes externas file-backed de solo lectura (M9),
layering de configuración (M10), integridad detectiva de fuentes externas (M12) y adopción de
proyecto existente (B5). Ninguna está implementada todavía — `tools/ds_init/manifest.py` no tiene
ningún campo de capability, `tools/datasources/registry.py` no admite una fuente fuera del repo,
`tools/dsguard/pathguard.py` solo conoce una capa de config (`guardrails.json`), y no existe ningún
mecanismo de fingerprint pre/post alrededor de `tools/leadrun/runtime.py`.

**Auditoría explícita del instalador actual, antes de diseñar nada nuevo** (evidencia, no
suposición):

- `tools/ds_init/preflight.py::validar_destino` YA exige un repo Git existente con working tree
  limpio — **no exige un proyecto vacío**. No hay ninguna condición que rechace un repo con código
  del usuario ya presente.
- `tools/ds_init/preflight.py::detectar_colisiones` + `tools/ds_init/planner.py::_accion_para_entrada`
  YA implementan "nunca sobrescribir": un destino del manifiesto que ya existe en el repo se omite
  (`ACCION_OMITIR_EXISTENTE`), salvo los flujos ya documentados de `MERGE` (`.claude/settings.json`)
  y `CLAUDE.md` (`--integrar-claude` explícito). `tools/ds_init/cli.py` ya imprime la lista de
  omitidos en `--dry-run`/`--execute` ("Omitidos (ya existían en el destino, sin sobrescribir)").
- **Conclusión de la auditoría**: la garantía central de B5 ("nunca sobrescribir un archivo del
  usuario", "no exigir proyecto vacío") **ya existe y funciona**. Este Change NO la duplica — agrega
  lo que falta: un mensaje de colisión más informativo (tipo de conflicto, qué quería instalar
  Harmessi, alternativas soportadas — hoy solo imprime la ruta), la categorización de ownership de 5
  vías en Doctor (hoy Doctor no distingue "archivo preexistente del usuario, nunca tocado" de
  ninguna otra categoría porque esos destinos ni siquiera entran al registro de hashes), y una suite
  de tests que ejercite explícitamente el escenario de adopción de punta a punta (no existe hoy:
  todos los tests de `ds_init` usan un directorio destino vacío).
- Auditoría de Change 2 (`tools/leadrun/`, cerrado): confirmado en Change 3/M11 (ver
  `openspec/changes/20260930-autonomous-sdd-and-remediation/`) que no existe ninguna primitiva
  gobernada de instalación de dependencias — se reafirma acá, sin volver a auditar.

## Objetivo

Implementar M8 (capability-aware provisioning), M9 (fuentes externas file-backed read-only), M10
(layering de configuración), M12 (integridad detectiva de fuentes externas) y la adopción de
proyecto existente (B5) — todas opt-in, backward-compatible, sin reabrir Changes 0-3.

## Evidencia

- `docs/roadmap/v0.8.md`: decisiones M8 (project capabilities), M9 (fuentes externas), M10
  (layering), M12 (integridad detectiva), y las secciones "Change 4" / "B1-B5" del mismo documento.
- `tools/ds_init/preflight.py:50-113` (`validar_destino`, `detectar_colisiones`) — adopción ya
  soportada en su núcleo, confirmado por lectura directa.
- `tools/ds_init/planner.py:40-66` (`_accion_para_entrada`) — "nunca sobrescribir" ya implementado.
- `tools/ds_init/cli.py:145-148,256-258` — mensaje de colisión hoy mínimo (solo ruta).
- `tools/ds_init/manifest.py` (`EntradaManifiesto`) — sin ningún campo de capability hoy, solo
  `stage_minimo`/`perfiles`.
- `tools/datasources/registry.py`/`core.py` (Change 1, cerrado) — el registro de fuentes no admite
  hoy una declaración de path externo al repo; `SourceRef`/`SourceObservation` no tienen ningún
  campo de path (por diseño, M9 no lo cambia: el path externo vive en local override, M10, nunca en
  el core neutral).
- `tools/dsguard/pathguard.py` (Change 0, `POLICY_VERSION_MAX=2`) — una sola capa de config
  (`guardrails.json`), sin ningún concepto de project config/local override todavía.
- `tools/leadrun/runtime.py` (Change 2, cerrado) — sin ningún fingerprint de entradas antes/después
  de ejecutar.

## Supuestos descartados

- Que había que diseñar un modo `--adopt-existing` desde cero: la auditoría confirma que el
  instalador ya soporta la adopción en su núcleo (repo existente, working tree limpio, sin
  sobrescribir). No se crea un modo nuevo — se mejora el mensaje de colisión y se agrega la
  categorización de ownership en Doctor, que sí faltan.
- Que la integridad de fuentes externas (M12) necesitaba tocar `tools/leadrun/core.py`/`runtime.py`:
  el fingerprint pre/post se compone ALREDEDOR de una ejecución ya gobernada (antes de llamar
  `runtime.ejecutar`, después de que devuelve), sin modificar esos archivos cerrados.

## Alcance

- **M8 — Project capabilities**: `EntradaManifiesto` gana un campo aditivo `capabilities: tuple`
  (default `()` = sin filtro, comportamiento idéntico a hoy); `manifest_para_perfil_y_stage` (o una
  función hermana) filtra también por capability habilitada; vocabulario inicial:
  `predictive_modeling` (candidatos `data_analysis`/`reporting` quedan declarados pero sin
  filtrado real en este Change si no hay entradas que dependan de ellos — solo se implementa el
  filtro para capabilities con contenido real que excluir); Doctor reporta `N/A — capability not
  enabled` para lo no provisionado por elección explícita, nunca `MISSING`/`ERROR`.
- **M9 — Fuentes externas file-backed de solo lectura**: extiende el registro de `tools/datasources`
  (Change 1) con una declaración de path externo que vive en la capa de local override (M10) — el
  core de `datasources` no cambia; `pathguard` hace enforcement de solo-lectura sobre esa ruta.
- **M10 — Layering de configuración**: `managed defaults → project config → local overrides →
  effective config`, compuesto en `ds_guard.py` (no en `pathguard.py`/`tools/autonomy/policy.py`,
  cerrados) — mismo patrón de composición externa ya usado para budgets (Change 3).
- **M12 — Integridad detectiva**: fingerprint tamaño+mtime (hash opcional) antes/después de una
  ejecución gobernada (Change 2) que declare una fuente file-backed read-only como entrada; una
  discrepancia mapea a `data_loss_risk` (STOP 7 ya existente, sin STOP nuevo); Doctor diagnostica
  permisos OS de solo lectura, sin mutar nada.
- **B5 — Adopción de proyecto existente**: mensaje de colisión enriquecido (ruta, tipo de conflicto,
  asset que Harmessi quería instalar, alternativas soportadas); categorización de ownership de 5
  vías en `harmessi doctor`; test end-to-end de adopción (repo con código/brief existentes, sin
  Harmessi, working tree limpio).
- Instalación/configuración del modo de autonomía y coherencia de versión de policy con
  guard/runtime (M2/M4, ya descriptas en el roadmap original de este Change, sin cambios); camino de
  upgrade plan-first desde v0.7.
- **Instalación gobernada de dependencias pre-aprobadas (M11, resolución 2026-09-30 — supersede la
  versión anterior de este bullet):** una dependencia pre-aprobada por la propuesta humana (nombre +
  rango de versión, Change 3) SÍ puede instalarse en modo `autonomous` sin intervención humana
  adicional, mediante una **extensión aditiva** del runtime público de Change 2
  (`tools/leadrun/`) — 5ª forma cerrada `dependency_install` (`-m pip install --no-deps
  <nombre>==<versión>`, patrón fijo, sin flags libres), reutilizando `scripts.ejecutar_script`
  (exactamente el mismo camino que ya usa `cli_diagnostic`) y `runtime.ejecutar` de punta a punta —
  ningún segundo runtime, ningún shell arbitrario. Ver `design.md` D7 (por qué es aditiva, no una
  reapertura material) y `spec.md` R24-R41 (el mecanismo completo, incluidas las cuatro guardas de
  la aprobación 2026-09-30: intérprete, identidad de paquete, rango vs. versión exacta, evidencia de
  entorno pre/post).

## Fuera de alcance

- Cualquier modificación MATERIAL de `tools/leadrun/core.py`/`runtime.py` (Change 2, cerrado) o de
  `tools/autonomy/core.py`/`policy.py` (Change 0, cerrado) — es decir, cualquier cambio que altere
  el comportamiento de las 4 formas/campos/funciones ya existentes. La extensión ADITIVA de R24
  (5ª forma `dependency_install`, sin tocar las 4 existentes) es la única excepción explícita,
  acotada y verificada por los propios tests de Change 2 sin editar (ver `design.md` D7).
- Instalación de dependencias por cualquier vía FUERA del patrón cerrado de R24 (sin `--no-deps`,
  con flags libres, múltiples paquetes por invocación, rango en vez de pin exacto, shell genérico) —
  la única vía soportada es la forma `dependency_install` acotada de `spec.md` R24-R41.
- Instalación de dependencias de Harmessi (solo-stdlib) por este mecanismo — es exclusivo para
  dependencias del proyecto, nunca del propio Harmessi.
- Mover/renombrar automáticamente archivos del usuario durante una adopción.
- Mutación de permisos del sistema operativo (`chmod`/`icacls`) — Doctor solo diagnostica.
- Sandbox preventivo de modificación de fuentes — M12 es defensa detectiva, nunca prevención.
- Catálogo de conectores, SQL en el core, marketplace de adapters.

## Holdout policy (condicional)

N/A — este Change no toca datos ni fuentes reales, solo el mecanismo de declaración/enforcement.

## Criterios de aceptación (spec-lite)

Ver `spec.md`.

## Decisión técnica (design-lite)

Ver `design.md`.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->
