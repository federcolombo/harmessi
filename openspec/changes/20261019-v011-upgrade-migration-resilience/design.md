# Diseño — 20261019-v011-upgrade-migration-resilience

## Decisión metodológica/técnica
- **D1** `upgrade` reutiliza la clasificación de baseline de `sync` (`control.clasificar_baseline`) y `writer.instalar` en vez de un motor nuevo; añade comparación de `harness_version` y plan de managed nuevos.
- **D2** Recovery = rollback al estado previo (no roll-forward): es el único camino cuya corrección se verifica con backups; el usuario re-ejecuta `upgrade`. Roll-forward diferido.
- **D3** El journal sale del staging descartable a un directorio propio dentro de `.ds_init/` para sobrevivir a la limpieza del staging; los backups quedan junto al journal hasta confirmar la transacción.
- **D4** Lock por archivo con pid/timestamp, sin dependencias; evita pisadas accidentales, no pretende resistir procesos hostiles.
- **D5** Dry-run por defecto en toda acción que escribe (patrón `--execute` existente).
- **D6** El test de completitud usa análisis AST de imports desde los entrypoints instalados + allowlist explícita, no heurística de nombres.
- **D7** Sin bump de versión aquí; Doctor compara contra `HARNESS_VERSION` vigente.

## Alternativas descartadas
Roll-forward automático (difícil de verificar); lock con dependencias externas; cambiar `install` sobre proyectos instalados; migrar datos del proyecto; Doctor en FAIL por simple diferencia de versión (queda WARN accionable).

## Riesgos
Pérdida de datos del proyecto (mitigado: dry-run por defecto, backups/journal persistentes, byte-identidad testeada, drift nunca adoptado). Estado mixto por fallo entre aplicar y regenerar control (mitigado: control dentro de la transacción + recover). Lock huérfano (mitigado: reporte con instrucción). Rutas de Windows y newlines en hashes (hash EOL-agnóstico existente).

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
