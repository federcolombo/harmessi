# Diseño — 20261023-v014-candidate-model-isolation

- `candidate.py`: dataclass `Candidate`, `CandidateRechazada(codigo)`, `CandidateCorrupta`, `crear_candidate(repo_root, base_surface, content, hypothesis, provenance, suite_ids=(), budget=None)`, `cargar_candidate`, `listar_candidates`, `base_vigente`, `transicionar`. Escritura atómica (tmp + `os.replace`). La raíz de datos es `repo_root/.harmessi/improvement`; toda ruta resuelta se verifica dentro de esa raíz.
- `budget.py`: `ImprovementBudget` (validación y techos), `cargar_presupuesto`, `consumir`, `estado`, `verificar_wall_clock`; errores `PresupuestoInvalido`, `PresupuestoAgotado`.
- Reutiliza `superficie_de_ruta` (clasificación), `redactar_texto` (privacidad), `hash_contenido` (hash normalizado de EOL) y `glossary.parsear_glossary` (términos del proyecto). No hay clasificación de superficies propia.
- Orden de validación fail-closed: tipo/ruta → superficie → base legible → contenido/privacidad → idempotencia → budget → escritura.
- Sin CLI en este Change; se agrega en el Change 5.
