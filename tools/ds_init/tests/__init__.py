"""Suite de tests de `tools.ds_init`.

Toda prueba de esta suite que necesite un destino de instalación crea su propio
repositorio Git temporal (`tempfile.mkdtemp()` + `git init`); ninguna corre
contra el repositorio donde vive este código (R14/AC15 del cambio
`20260909-inicializador-harness-datos`).
"""
