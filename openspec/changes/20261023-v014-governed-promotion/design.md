# Diseño — 20261023-v014-governed-promotion

`promotion.py`: `PromocionBloqueada(motivos)`, `proponer_promocion`, `cargar_propuesta` (valida `proposal_hash`), `evaluar_gate`, `aplicar_promocion`. Reusa `decision.verificar_promotable`, `candidate.base_vigente`, `dsguard.sdd.resolver_aprobacion_registrada` (+ lectura de `approval_channel` en la entrada), `dsguard.scope.alcance_efectivo` y `dsguard.repo.path_matches_any`, `difflib.unified_diff`. El gate es una función pura de lectura; `aplicar_promocion` es la única que escribe y lo hace después de pasarlo, bajo `budget.bloqueo`.
