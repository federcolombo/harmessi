# Ciclo de vida production / deployment / monitoring

Decisión de v0.15 (Change `20261026-v015-ds-core-debt`, B-14). Es una decisión de alcance: no agrega código ni integraciones.

## Decisión

1. **Harmessi cubre hasta la evidencia de readiness.** Las plantillas `production-readiness.md.tmpl` y `operations.md.tmpl` son *guidance-only*: ayudan al equipo a documentar qué evidencia real falta para considerar un modelo listo para producción y cómo se operaría. No ejecutan ni verifican despliegues.
2. **Deployment, monitoring y MLOps son frontera de integración.** El proyecto aporta la evidencia real (resultados de evaluación, Cards, observaciones, reportes); Harmessi no despliega ni monitorea. No integra Airflow, MLflow, Kubernetes ni CI/CD cloud, y no incorpora métricas de modelo en el binario.
3. **`no_iniciada` es un estado legítimo.** Un proyecto cuyo lifecycle de `deployment` o `monitoring` figura `no_iniciada` no está incompleto ni bloqueado por Harmessi: esas etapas pertenecen a la plataforma del equipo.
4. **Integraciones: POST-v1.** Cualquier integración con herramientas de despliegue u observabilidad se evalúa después de v1 (ver `docs/roadmap/v0.15-debt-matrix.md`, ítem P-20, categoría D POST-v1).

## Qué significa en la práctica

| Etapa | Qué hace Harmessi | Qué queda al proyecto |
|---|---|---|
| Production readiness | Guía y estructura para la evidencia | Producir y mantener la evidencia |
| Operations | Guía (plantilla) | Runbooks y operación reales |
| Deployment | Nada (frontera) | Despliegue con su plataforma |
| Monitoring | Nada (frontera) | Monitoreo y alertas con su plataforma |

Un `project_stage` de `production` en `.harmessi/project.json` registra el estado *alcanzado* declarado por el proyecto; no implica que Harmessi haya verificado un despliegue.

## Limitaciones

- Esta decisión no valida que la evidencia de readiness sea suficiente; eso es criterio del equipo y del Lead.
- No hay conectores a sistemas externos de despliegue o monitoreo.
