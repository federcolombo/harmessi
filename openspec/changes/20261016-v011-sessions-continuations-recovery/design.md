# Diseño — 20261016-v011-sessions-continuations-recovery

- **D1** El aviso vive en los comandos `ds_guard` (determinista, probado), no en el protocolo de salida del hook: cambiar la salida del hook exigiría payload/semántica real no verificada.
- **D2** `--retomar` es opt-in y explícito; no se convierte en default para no alterar contratos de v0.10.
- **D3** Se hereda solo estado de gobernanza (rondas, reintentos, roles, tareas, continuaciones); presupuesto y deadline se calculan nuevos.
- **D4** Wall-clock intacto: sin pausa de reloj por T1; la mitigación es aviso + recovery sin pérdida.
- **D5** Uso operativo de `--minutos` largo se documenta como configuración de ejecución, no policy.
