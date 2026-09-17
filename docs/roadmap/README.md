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
- `v0.4`: activa — calidad científica + impacto + aislamiento + portabilidad + eficiencia.
- `v0.5`: planificada — evals, reporting, ML quality/data contracts y multi-provider.
- `v0.6+`: provisional — governance avanzada.
- `v1.0`: estabilización pública y contratos estables.
