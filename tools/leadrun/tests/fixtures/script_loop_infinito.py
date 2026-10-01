"""Fixture sintética para `tools/leadrun/tests/test_scripts.py`: bucle
infinito, usada para probar `timeout_seconds`."""
import time

while True:
    time.sleep(0.05)
