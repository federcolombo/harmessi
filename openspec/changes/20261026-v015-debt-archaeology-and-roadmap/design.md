# Diseño — 20261026-v015-debt-archaeology-and-roadmap

## Decisión metodológica/técnica
Documentación pura, sin código. Una tabla única de deuda con categorías mutuamente excluyentes y una columna
"bloquea v1" que alimenta la conclusión de C7. El roadmap congela 8 Changes secuenciales; los intermedios no hacen
regresión completa y C7 la hace serial (P=1) con ledger.
Principio: "Close what matters. Explicitly classify what does not."

Decisiones fijadas en `docs/roadmap/v0.15.md`: D1 T2 POST-v1; D2 ningún soporte de provider por encima de la
evidencia; D3 ventana de compat 0.15/0.14/0.13 limitada a artefactos con test; D4 H1 se cierra con payload real o
ACCEPTED LIMITATION; D5 sin PKI; D6 production/deployment/monitoring = guidance; D7 v0.15 no crea v1.0.0.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica: no hay aleatoriedad ni ejecución. Los conteos se calculan contando filas de la tabla.

## Alternativas descartadas
- Una tabla por categoría: permite duplicar ítems entre categorías.
- Incluir implementación de deuda en este Change: mezcla auditoría con cambios y rompe la secuencia de Changes.
- Declarar v1.0 al cerrar v0.15: contradice "no declarar v1.0 solo por cantidad de features".

## Riesgos
- La evidencia proviene de lectura/grep del brief de auditoría, no de una corrida: puede haber ítems mal clasificados. Mitigación: cada Change revalida sus ítems con su impact preflight.
- El roadmap congelado puede quedar corto: la regla de expansión sustancial de scope (README de roadmap) obliga a detenerse.
- Ítems de la categoría C pueden cambiar con la observación real de CI (C-33); se actualiza en C7.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
