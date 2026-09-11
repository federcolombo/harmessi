# Diseño — 20260910-sincronizar-plantillas-bloque5

## Decisión metodológica/técnica
Sincronización mecánica de contenido: copiar los fragmentos ya aprobados de Bloque 5 desde los
archivos vivos (`sdd.md`, `SKILL.md`, `verificador.md`) hacia sus contrapartes `.tmpl`, y crear
`decision-ledger.md.tmpl` como copia verbatim (sin placeholders, ya que el archivo fuente no
referencia datos específicos del proyecto instalado). Se preserva `{{NOMBRE_PROYECTO}}` en
`SKILL_lead_data_scientist.md.tmpl` — es el único placeholder real involucrado en este cambio.

## Target / Features / Split / Leakage risks (condicionales)
No aplica — cambio técnico de tooling/harness (sincronización de plantillas), sin decisión de ML
de fondo.

## Reproducibilidad (opcional)
No aplica — no hay aleatoriedad involucrada.

## Alternativas descartadas
- Automatizar `check_manifest_parity` para que compare contenido/hash de cada `.tmpl` contra su
  archivo vivo y solo liste las que difieren de verdad: descartado para este cambio — es una
  mejora de tooling más amplia, no pedida, y cambiaría el contrato actual (informativo,
  incondicional) de `listar_plantillas()`. Queda como posible mejora futura, no deuda formal de
  Bloque 5 (no fue pedida por el usuario).
- Reemplazar el placeholder `{{NOMBRE_PROYECTO}}` por texto genérico en vez de mantenerlo:
  descartado — rompería la instalación real en proyectos con nombre distinto de "harmessi".

## Riesgos
- Copiar contenido a mano puede introducir un desvío sutil (espacios, saltos de línea) respecto
  del archivo vivo: mitigado verificando con `diff` línea por línea antes de cerrar el cambio
  (criterios de aceptación de `spec.md`).
- Que el nuevo `decision-ledger.md.tmpl` quede huérfano del manifiesto (archivo creado pero sin
  `EntradaManifiesto`): mitigado incluyendo el registro en el manifiesto como criterio de
  aceptación explícito (R5).

## Aprobación humana
El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único por
cambio y vive en la sección "Aprobación" de `proposal.md` — no se duplica acá.
