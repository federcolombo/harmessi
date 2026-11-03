# Diseño — 20261023-v014-lessons-and-improvement-cycle

- `lessons.py`: reutiliza `decision.decidir/cargar_decision`, `redact.redactar_texto`, `glossary.parsear_glossary`; el chequeo del Change abierto se factoriza desde `promotion` (función pública pequeña) sin duplicar lógica.
- `cycle.py`: orquesta `candidate.crear_candidate → probe.ejecutar_probe → decision.aplicar_decision`; guardia de anidamiento con lock `.harmessi/improvement/.cycle.lock` (`O_EXCL`); captura `PresupuestoAgotado` y reporta; nunca llama a `promotion`.
- `cli.py`: argparse, un handler por subcomando, mapeo de excepciones a códigos de salida; `__main__.py` delega.
