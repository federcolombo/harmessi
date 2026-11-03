# Diseño — 20261021-v012-diagnosing-bugs

- Skill única, ≈70–100 líneas. Roles: lead-data-scientist, python-data-engineer, data-science-reviewer, metodologo.
- El Lead ejecuta y clasifica; el writer corrige la causa raíz y agrega el regression test; el reviewer lee. Ninguna capa nueva.
- Baseline focalizado = checkout/worktree o `git stash`-free lectura del commit baseline del Change (`control.json` baseline) y corrida del mínimo test que falla; sin tocar el árbol del usuario de forma destructiva.
- Riesgo: prueba/error disfrazado de workflow ⇒ cada paso exige una evidencia observable (hipótesis falsable).
## Decisiones materiales pendientes
Ninguna.
