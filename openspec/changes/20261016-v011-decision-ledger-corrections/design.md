# Diseño — 20261016-v011-decision-ledger-corrections

- **D1 Naming.** `correct` (no `amend`, ya usado por `scope amend`).
- **D2 Escritura.** Se lee el texto crudo (`newline=""`), se agrega la línea nueva y se escribe atómicamente con `escribir_texto_atomico`; las líneas previas no se reserializan.
- **D3 Cadena.** `prev_hash = sha256(linea_previa_sin_terminador_utf8)`. Primera entrada nueva sobre un ledger legacy encadena con la última línea legacy. Tolera CRLF/LF al hashear quitando solo `\r\n`/`\n` finales.
- **D4 Efectivo.** `efectivo` = campos originales sobrescritos por correcciones en orden de `seq`.
- **D5 Sin migración.** Ledgers v1 no se tocan; el primer append nuevo inicia la cadena.
- **D6 Límites.** Sin firmas ni PKI; `usuario` es declarado (T0), como el resto de operaciones del ledger.
