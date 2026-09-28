# Harmessi — Roadmap de versiones

Este directorio es la fuente de planificación de alto nivel para el desarrollo autónomo de Harmessi.

## Cómo usarlo con Claude Code

1. Leer este archivo.
2. Leer el archivo de la versión activa.
3. Detectar el estado real del repositorio antes de ejecutar.
4. Continuar desde el primer Change pendiente.
5. Ejecutar la versión en autonomía acotada.
6. Detenerse solo ante una decisión material o al finalizar el hardening de la versión.

El roadmap define **qué** debe construirse y el orden.
Los artefactos SDD de cada Change definen **cómo** se implementa ese Change.

## Principio operativo

> LLM decide lo semántico; el binario calcula y hace cumplir lo determinista.

## Contrato de autonomía

Para cada Change:

`audit → SDD → implementación → tests → reviewer → fixes → re-tests → verification → close`

No pedir confirmación humana entre pasos normales.

Detenerse únicamente ante:

1. cambio arquitectónico material;
2. cambio incompatible de schema/contrato;
3. backward compatibility comprometida;
4. dependencia nueva relevante;
5. riesgo de pérdida o corrupción;
6. contradicción real entre requisitos;
7. necesidad de bypass/exemption no prevista;
8. expansión sustancial de scope;
9. reviewer demuestra que el enfoque aprobado es incorrecto;
10. bounded remediation agotada.

Máximo 2 ciclos writer ↔ reviewer.

## Eficiencia

- No agentes de espera/no-op.
- No auditorías duplicadas.
- No delegar si el Lead puede resolverlo.
- Un solo writer: `python-data-engineer`.
- Reviewer y metodólogo son read-only.
- Reanudar el mismo task-id ante turn limit.
- No repetir suites completas si un fix aislado no puede afectarlas, salvo gate final.

## Commits y publicación

La unidad lógica de trazabilidad es el **Change**.

Recomendación:
- cerrar cada Change con un commit local;
- no hacer tag ni GitHub Release hasta terminar el release hardening;
- no publicar una versión sin aprobación humana final.

Si el usuario define otra política de commits para una versión concreta, esa instrucción prevalece.

## Versiones

- `v0.3.0`: publicada.
- `v0.4.0`: publicada.
- `v0.5.0`: publicada.
- `v0.6.0`: publicada — Governed Reporting + EDA.
- `v0.7.0`: publicada — ML Quality & Data Contracts.
- `v0.8`: alcance congelado (READY) — Autonomous Project Runtime (autonomía del harness instalado +
  abstracción de fuentes de datos). Ver `v0.8.md`.
- `v0.9`: planificada — Model/Data Cards + Responsible AI / Model Risk (antes v0.8).
- `v0.10`: planificada — Integration & Stabilization (antes v0.9).
- `v1.0`: Stable Public Contracts.

Nota: el contrato de autonomía de arriba gobierna **cómo se desarrolla Harmessi**. La autonomía del
harness **instalado en un proyecto** (modos `autonomous`/`supervised`) es un contrato distinto y se
define en `v0.8.md`, Change 0.
