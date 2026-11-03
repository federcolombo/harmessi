# Diseño — 20261021-v012-skill-selection-composition

- Solo criterio (docs) + test: el Lead ya carga y registra skills; falta decir cuándo y cómo de forma consistente. No se agrega código ni código de hallazgo (D4 del roadmap): una traza más estricta en el binario exigiría decidir qué es «material», que es juicio semántico del Lead.
- El test «toda skill distribuida figura en la tabla de selección» es el consumidor determinista que evita que una skill futura quede sin criterio de selección.
- Cambio de la regla de conflicto (D2): por pedido explícito de la autorización de v0.12; no toca permisos/hooks/roles/runtime; la capa superior siempre gana.
- `SKILL.md`: el párrafo único se divide en viñetas cortas; se conservan las frases exigidas por tests previos (el writer verifica y ajusta tests de forma coherente).
## Decisiones materiales pendientes
Ninguna.
