"""Catálogo de mensajes "legacy" (v0.7, orientados a "perfil") usado por el gate de
forma propio de `validate_contract_observation` (`tools/datacontracts/validation.py`,
T5 del Change 1 de v0.8, R29-R35 de `spec.md`) cuando se invoca desde los wrappers v0.7
(`validate_contract`/`validate_contract_against_profile_file`, `wording=LEGACY_PROFILE`).

DECISIÓN A CONFIRMAR POR EL LEAD (ver reporte de la tarea): con la Estrategia A elegida
para T5 (`validation._observation_como_profile_like`, "bridge inverso"), las funciones
`_regla_*` heredadas de v0.7 NO fueron tocadas -- siguen generando su texto de siempre
(en español, orientado a "perfil"/"columna") sea cual sea el `wording` pasado a
`validate_contract_observation`. Por lo tanto este catálogo NO cubre esos mensajes (sería
trabajo perdido: nunca se consultan desde ahí). Solo cubre los DOS mensajes del gate de
forma propio de `validate_contract_observation` (`_observation_valida_forma`), que sí es
código nuevo de T5 y sí distingue "perfil" (modo legacy) de "observación" (modo neutral,
ver el dict `_WORDING_NEUTRAL` en `validation.py`). Esto es una SIMPLIFICACIÓN frente a
R33 de `spec.md` (que pedía un catálogo NEUTRAL "distinto" en un sentido más amplio,
cubriendo también las reglas) -- el criterio de cierre real de este paso es R34 (paridad
exacta), no "mensajes neutrales" per se, así que se priorizó no tocar `_regla_*`.
"""
from __future__ import annotations

LEGACY_PROFILE = {
    "evidence_invalid": "El perfil no es válido: {motivo}",
    "evidence_wrong_type": (
        "'observation' no es una SourceObservation ni un dict con esa forma "
        "(se recibió {tipo})."
    ),
}
