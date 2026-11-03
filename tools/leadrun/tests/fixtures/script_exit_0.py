"""Fixture sintética (100% sintética, sin nada real del proyecto) para
`tools/leadrun/tests/test_scripts.py`: sale con `exit(0)` tras imprimir un
mensaje corto por stdout."""
print("hola desde script_exit_0")
raise SystemExit(0)
