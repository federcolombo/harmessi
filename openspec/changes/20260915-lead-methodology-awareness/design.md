# Diseño — 20260915-lead-methodology-awareness

## Decisión metodológica/técnica

### 1. Un único documento nuevo (`methodology.md`), no fragmentación
El brief permite "UN documento nuevo... si reduce claramente complejidad de SKILL.md" y prohíbe
explícitamente fragmentar en muchos archivos nuevos. Todo el contenido normativo de las 23
secciones del brief (jerarquía, stage behavior, status, alignment, readiness, promotion, risk,
lifecycle, KDD, foundations, evidence, SDD, decision ledger, one-writer, delegación,
remediation, notebooks, EDA, human-in-the-loop, fail-closed, adopción, workflow, prohibiciones)
vive en `methodology.md`, leído bajo demanda (mismo patrón ya establecido por `kdd.md`/`eda.md`/
`decision-ledger.md` — nunca por defecto, para no inflar el contexto de cada invocación del Lead).
`SKILL.md` gana solo un pointer, igual de compacto que los pointers ya existentes.

### 2. Corrección puntual, no reescritura, de los 5 documentos existentes
`SKILL.md`/`kdd.md`/`decision-ledger.md`/`verificador.md` tienen contenido operativo VÁLIDO hoy
(routing de subagentes, ciclo SDD, comandos de sesión/aprobación/remediation) que este change no
toca. Se editan quirúrgicamente: (a) la frase de encuadre desactualizada en `SKILL.md`/`kdd.md`/
`decision-ledger.md` (una sección/párrafo cada uno), (b) las entradas de comando faltantes en
`verificador.md` (agregadas al final de la lista existente, mismo formato, sin reordenar lo que ya
había). Esto minimiza el riesgo de romper referencias cruzadas ya correctas en el resto de esos
documentos.

### 3. `production-readiness.md.tmpl`/`operations.md.tmpl`: fix de una línea, no revisión completa
Ambos documentos (escritos en Change 7) ya son correctos en el resto de su contenido — el único
error real es la línea de sintaxis de `promote`. Se corrige exactamente esa línea en cada archivo,
sin tocar el resto (ya explica bien la distinción instalación-física vs. madurez, ya advierte
contra evidencia falsa).

### 4. Sincronización `.tmpl` ↔ renderizado como parte explícita de cada edición
Este repo es una instalación self-hosted: `.claude/skills/lead-data-scientist/*.md` son copias
YA RENDERIZADAS de sus `.tmpl` (con la excepción de `production-readiness.md`/`operations.md`,
que — como ya se documentó en el cierre de Change 8 — todavía no están renderizadas en este propio
repo, porque este repo nunca corrió `ds_init sync --stage production`). Cada edición de contenido
se aplica en la fuente `.tmpl` (el contrato real que viaja a cualquier proyecto instalado) Y,
cuando existe, en la copia local ya renderizada de este repo (para que la verificación de este
change contra este propio repo refleje el contenido real, y para no introducir drift nuevo entre
"lo que se instalaría" y "lo que este repo tiene"). Para `production-readiness.md`/`operations.md`,
que no existen todavía localmente, solo se corrige el `.tmpl` — no se auto-genera la copia
faltante (eso sería una operación de instalación real, `ds_init sync`, fuera de alcance de este
change y ya documentada como pendiente).

### 5. Tests: contenido liviano sobre los `.tmpl`, nunca un parser de Markdown
Se verifica PRESENCIA/AUSENCIA de cadenas concretas (nombres de fases/pasos/stages, sintaxis
exacta de comandos, frases de prohibición) sobre el contenido de texto plano de los `.tmpl` —
`open(ruta).read()` + `assertIn`/`assertNotIn`, mismo nivel de sofisticación que los tests de
manifest existentes (`test_manifest.py`). Nunca se construye un AST de Markdown ni se valida
estructura de headings — el brief lo prohíbe explícitamente y no aporta valor real para contenido
prosa.

### 6. El bug de `promote --target` se corrige solo en documentación, `ds_guard.py` no se toca
Confirmado por lectura directa: `tools/ds_guard.py` YA acepta correctamente la sintaxis posicional
(`project promote <stage> --reason ...`) — el bug está exclusivamente en los dos documentos que
describían mal esa sintaxis, nunca en el propio parser. No hay ningún cambio de comportamiento de
`ds_guard.py` en este change — coherente con "no cambiar runtime sin necesidad" (brief §26), ya
que la corrección es puramente de documentación describiendo correctamente un comportamiento que
ya existe.

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica — cambio de documentación/orquestación del harness.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica.

## Alternativas descartadas
- Reescribir `SKILL.md` completo integrando toda la nueva awareness inline — rechazada:
  contradice explícitamente el brief ("SKILL.md debe seguir siendo una entrada compacta") y el
  riesgo de romper referencias/routing ya correcto es mucho mayor que agregar un pointer acotado.
- Fragmentar en varios documentos nuevos (uno por sección del brief) — rechazada explícitamente
  por el usuario (§25: "NO fragmentar en muchos archivos nuevos").
- Corregir el bug de `promote --target` modificando `ds_guard.py` para ACEPTAR también `--target`
  como alias (backward-compat hacia el error de documentación) — rechazada: el error está en la
  documentación, no en el código; agregar un alias nuevo al parser real sería cambiar runtime sin
  necesidad real (prohibido por §26) para compensar un bug que se resuelve enteramente arreglando
  el texto.
- Auto-renderizar `production-readiness.md`/`operations.md` en este repo como parte de este change
  (corriendo `ds_init sync`) — rechazada: eso sería una operación de instalación real sobre este
  propio repo, fuera del alcance declarado ("no cambiar runtime sin necesidad"), y ya está
  documentada como pendiente desde el cierre de Change 8.
- Construir un parser de Markdown para verificar estructura de secciones — rechazada
  explícitamente por el usuario (§27).

## Riesgos
- Duplicación conceptual entre `methodology.md` (nuevo) y los documentos existentes
  (`kdd.md`/`eda.md`/`decision-ledger.md`/`production-readiness.md`/`operations.md`, que ya
  explican correctamente sus propios dominios) — mitigado con referencias cruzadas explícitas en
  vez de repetir contenido: `methodology.md` remite a esos documentos para el detalle operativo de
  cada mecanismo, y se limita a la jerarquía/comportamiento/reglas transversales que hoy no vive en
  ningún lado.
- `production-readiness.md`/`operations.md` seguirán ausentes de la copia local de este repo tras
  este change (solo se corrige el `.tmpl`) — aceptado conscientemente (punto 4): auto-renderizarlos
  requeriría una operación de instalación real fuera de alcance; el bug de sintaxis igual queda
  corregido en la fuente que cualquier instalación nueva/sincronizada sí va a usar.
- Verificar "ningún comando documentado usa sintaxis que `ds_guard.py` rechace" (criterio de
  aceptación) requiere correr cada comando real (aunque sea en modo `--help`/read-only) — se hace
  como parte de la verificación del Lead con Bash, no como responsabilidad del subagente
  implementador (que no tiene Bash).

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
Ver `proposal.md § Aprobación`.
