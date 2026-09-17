# Verificación — 20260917-multi-provider-adapters

## Evidencia obtenida

- **Regresión, suite `tools/providers/tests`**: `.venv/Scripts/python.exe -m pytest
  tools/providers/tests -q` → `27 passed, 8 subtests passed` en `0.23s`.
- **Regresión, suite `tools/harmessi/tests`**: `.venv/Scripts/python.exe -m pytest
  tools/harmessi/tests -q` → `84 passed` en `321.50s` (0:05:21). Ambas suites se corrieron
  secuencialmente (no en paralelo) por una limitación real del entorno: un intento anterior de
  correrlas juntas en background fue terminado por el sistema por presión de memoria (bajo memoria
  del sistema, no relacionado con el código) — se resolvió corriéndolas por separado, sin necesidad
  de reintentar la combinada.
- **Smoke real de `ClaudeCodeAdapter`, fuera de la suite de tests** (tal como preveía `tasks.md`):
  el Lead ejecutó manualmente `claude -p "Respondé unicamente con la palabra OK." --output-format
  json` desde la raíz del repo. Resultado real: `subtype: "success"`, `is_error: false`, `result:
  "OK"`, `session_id: 0256fb57-1c59-4a95-a548-cd58bc096491`, `duration_ms: 1594`,
  `total_cost_usd: 0.0735766`. Confirma end-to-end que el comando que arma
  `ClaudeCodeAdapter.invoke()` (`claude -p <prompt> --output-format json`) es válido contra la CLI
  real y produce una respuesta JSON parseable con la forma esperada (`result`, `is_error`,
  `subtype`). No se repitió esta invocación real más de una vez (tiene costo real en la cuenta del
  usuario) — evidencia suficiente para este Change, no hace falta repetirla en Changes futuros de
  v0.5 salvo que cambie el contrato de `invoke()`.
- **Reviewer, ronda 1** (`data-science-reviewer`): revisó el diff completo. 4 hallazgos
  "importante" (ningún bloqueante): (1) `invoke()` de los 4 adapters sin `try/except` alrededor de
  `subprocess.run` (riesgo TOCTOU + timeout no capturado); (2) `classify_availability_error` con
  patrones `"authentication"`/`"401"`/`"429"` propensos a falso positivo por substring sin anclaje;
  (3) `test_providers_cli.py` invocaba `claude --version` real sin mock ni `skipif`, a diferencia
  del resto de la suite; (4) campo `role`/`translate_role()` declarado en el contrato pero sin uso
  real en ningún adapter, sin aclarar si era intencional. Más 3 hallazgos "menor" (sin cobertura de
  excepción en `invoke()`, asimetría de cobertura entre adapters, `tasks.md` con checkboxes
  desactualizados).
- **Fixes aplicados** (única reinvocación correctiva del Change, cuenta 1 de 2 del contrato de
  autonomía): los 4 adapters ahora capturan `OSError`/`subprocess.TimeoutExpired` en `invoke()`;
  `classify_availability_error` reescrita (sacó `"no such file"` del bucket `unavailable`,
  `429`/`401` con límite de palabra vía regex, `"authentication"` genérico reemplazado por frases
  específicas); `role`/`translate_role()` documentado explícitamente como placeholder deliberado de
  contrato para Change 2 (`design.md`, "Riesgos"); `test_providers_cli.py` reescrito con
  `monkeypatch` sobre `tools.providers.list_providers`, sin I/O de proceso real; agregado test de
  timeout en `invoke()`; `tasks.md` actualizado. Limitación aceptada y documentada en un test
  dedicado: el caso límite de un traceback tipo `"line 429, in <module>"` sigue matcheando `quota`
  (los límites de palabra rodean el número igual ahí) — no se resolvió por no ser el foco del fix y
  no bloquear nada de este Change.
- **Alcance**: `python tools/ds_guard.py status --change-id 20260917-multi-provider-adapters --json`
  → `"fuera_de_alcance": []` (tras agregar las 12 rutas de implementación a
  `control.json.alcance.rutas_autorizadas`, que originalmente solo tenía los 5 artefactos SDD del
  scaffolding).
- **Privacidad**: no aplica un sweep dedicado a este Change (no se creó contenido con
  nombres/rutas de AGD/UNCO/clientes — todo el contenido nuevo es genérico de proveedores de IA
  públicos); el sweep transversal obligatorio se hace en Change 5 (hardening).
- **Cero dependencias nuevas**: confirmado por lectura — todos los imports de `tools/providers/*`
  son `abc`, `dataclasses`, `pathlib`, `typing`, `shutil`, `subprocess`, `time`, `re`, `json`
  (stdlib).

## Fingerprint de dataset/artefacto
No aplica — cambio de infraestructura del harness (adapters de proveedor), no involucra datos de un
proyecto DS.

## Diferencias contra la spec

Ninguna respecto a los requisitos R1-R8 de `spec.md`. Los fixes de la sección de evidencia no
cambiaron ningún contrato público, solo endurecieron el comportamiento interno tal como preveía
`design.md` ("Riesgos").

## Limitaciones

1. `codex.py`/`gemini.py`/`grok.py`: comando de invocación best-effort, no verificado contra la CLI
   real (ausente en este entorno) — se revisita cuando exista necesidad real o acceso a esas CLIs.
2. `classify_availability_error` sigue siendo heurística de texto; el caso límite de "429" dentro de
   un traceback de Python no se distingue de un código HTTP real (documentado y aceptado, ver
   sección de evidencia obtenida).
3. `authenticated` de `ProviderInfo` es siempre `None` para los 4 adapters — no hay forma barata y
   limpia de verificar autenticación sin invocar una sesión real; queda como limitación explícita,
   no una señal inventada.
4. Antigravity (IDE de Google) queda fuera de alcance de "Gemini/Antigravity" — solo se implementó
   Gemini CLI, con la justificación ya en `proposal.md`.
5. El campo `role`/`translate_role()` sigue sin uso real — es contrato reservado para Change 2
   (routing), no una limitación a resolver en este Change.

## Pendientes derivados

Ninguno bloqueante. Las 5 limitaciones de arriba quedan como deuda documentada para v0.5+ (Changes
posteriores de multi-provider/routing) y para el sweep de privacidad transversal de Change 5
(hardening).

## Resultado final

Change 0 (multi-provider-adapters) completo: contrato core neutral + 4 adapters + tests + wiring
CLI implementados, revisados (1 ronda, 4 hallazgos importantes corregidos) y verificados (111 tests
totales entre las 2 suites afectadas + 1 smoke real de `claude_code` + alcance limpio); listo para
cierre SDD y commit local.
