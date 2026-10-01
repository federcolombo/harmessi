"""Tests de `tools.datasources.scan` (R19)."""
from __future__ import annotations

from tools.datasources import scan
from tools.datasources.core import CODE_ABSOLUTE_PATH, CODE_DSN_DETECTED, CODE_SECRET_DETECTED


def _codigos(hallazgos):
    return [h[0] for h in hallazgos]


def test_password_env_clave_se_marca():
    hallazgos = scan.scan_secrets({"password_env": "DB_PASSWORD"})
    assert CODE_SECRET_DETECTED in _codigos(hallazgos)


def test_config_ref_no_se_marca():
    hallazgos = scan.scan_secrets({"config_ref": "env:CUSTOMERS_DSN"})
    assert hallazgos == []


def test_hash_sha256_en_clave_fingerprint_value_no_se_marca():
    valor_hex = "a" * 64
    hallazgos = scan.scan_secrets({"fingerprint": {"algorithm": "sha256", "value": valor_hex}})
    assert hallazgos == []


def test_hash_sha256_en_clave_hash_no_se_marca():
    valor_hex = "b" * 64
    hallazgos = scan.scan_secrets({"hash": valor_hex})
    assert hallazgos == []


def test_exencion_hash_no_se_propaga_mas_alla_del_hijo_inmediato():
    """R19: la exención de clave hash/sha/fingerprint es de UN solo nivel. Un
    nieto de una clave hash (hijo de un hijo) ya no hereda la exención, aunque
    el código viejo (sin límite de profundidad) la propagaba sin fin -- ver
    hallazgo del reviewer sobre el Change 1 de v0.8."""
    valor_hex = "c" * 64
    hallazgos = scan.scan_secrets({"api_hash": {"anidado": {"valor": valor_hex}}})
    assert CODE_SECRET_DETECTED in _codigos(hallazgos)


def test_note_recuento_de_tokens_no_se_marca():
    hallazgos = scan.scan_secrets({"note": "recuento de tokens"})
    assert hallazgos == []


def test_clave_token_se_marca():
    hallazgos = scan.scan_secrets({"api_token": "cualquier_valor"})
    assert CODE_SECRET_DETECTED in _codigos(hallazgos)


def test_valor_con_prefijo_akia_se_marca_sin_clave_sospechosa():
    hallazgos = scan.scan_secrets({"nota": "AKIA1234567890ABCDEF"})
    assert CODE_SECRET_DETECTED in _codigos(hallazgos)


def test_valor_jwt_se_marca():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    hallazgos = scan.scan_secrets({"nota": jwt})
    assert CODE_SECRET_DETECTED in _codigos(hallazgos)


def test_hex_largo_en_clave_no_hash_se_marca():
    hallazgos = scan.scan_secrets({"algo": "a" * 40})
    assert CODE_SECRET_DETECTED in _codigos(hallazgos)


def test_dsn_esquema_usuario_password_host_se_marca():
    hallazgos = scan.scan_secrets({"conexion": "postgresql://user:clave@host:5432/db"})
    assert CODE_DSN_DETECTED in _codigos(hallazgos)


def test_dsn_server_password_se_marca():
    hallazgos = scan.scan_secrets({"conexion": "Server=miserver;Password=algo;"})
    assert CODE_DSN_DETECTED in _codigos(hallazgos)


def test_mensaje_no_reproduce_el_valor_sospechoso():
    valor_secreto = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    hallazgos = scan.scan_secrets({"nota": valor_secreto})
    for _, _, motivo in hallazgos:
        assert valor_secreto not in motivo


def test_scan_locators_windows_drive():
    hallazgos = scan.scan_locators({"path": r"C:\datos\x.csv"})
    assert CODE_ABSOLUTE_PATH in _codigos(hallazgos)


def test_scan_locators_unc():
    hallazgos = scan.scan_locators({"path": r"\\servidor\recurso\archivo.csv"})
    assert CODE_ABSOLUTE_PATH in _codigos(hallazgos)


def test_scan_locators_file_uri():
    hallazgos = scan.scan_locators({"path": "file:///datos/x.csv"})
    assert CODE_ABSOLUTE_PATH in _codigos(hallazgos)


def test_scan_locators_posix_absoluto():
    hallazgos = scan.scan_locators({"path": "/datos/raw/customers.parquet"})
    assert CODE_ABSOLUTE_PATH in _codigos(hallazgos)


def test_scan_locators_relativo_no_se_marca():
    hallazgos = scan.scan_locators({"path": "data/raw/customers.parquet"})
    assert hallazgos == []


def test_scan_secrets_recorre_listas_anidadas():
    hallazgos = scan.scan_secrets({"items": [{"password": "x"}, {"nota": "ok"}]})
    assert CODE_SECRET_DETECTED in _codigos(hallazgos)
